"""
هندلرهای Callback — فیدبک، رای‌گیری، گزارش، عمومی
"""

import logging
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import ContextTypes

from config import ADMIN_IDS
import bot.db.database as db
from bot.core import moderation as mod
from bot.core.user_levels import get_config, level_label
from bot.utils.helpers import mention, build_vote_keyboard, esc
from bot.handlers.messages import get_pending_answers
from i18n import t

logger = logging.getLogger(__name__)

_MAX_FB_PER_HOUR  = 5
_VOTES_TO_CONFIRM = 2
_VOTES_TO_REJECT  = 3
_MIN_CORRECTION_LEN = 10


def _is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


# ─── callback پاسخ ادمین به سوال بی‌جواب ─────────────────────────────────────

async def on_admin_answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data

    if not _is_admin(query.from_user.id):
        return

    pending = get_pending_answers()

    # ── نادیده گرفتن ─────────────────────────────────────────────────────────
    if data.startswith("adm_skip_"):
        key = data[9:]
        pending.pop(key, None)
        try:
            await query.edit_message_text(
                query.message.text + "\n\n🚫 <i>نادیده گرفته شد.</i>",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    # ── پاسخ ادمین ───────────────────────────────────────────────────────────
    if data.startswith("adm_ans_"):
        key = data[8:]
        info = pending.get(key)
        if not info:
            await query.answer("این سوال دیگه فعال نیست.", show_alert=True)
            return
        context.user_data["admin_answering"] = key
        try:
            await query.edit_message_text(
                query.message.text + "\n\n✏️ <i>پاسخ خود را بنویسید:</i>",
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception:
            pass
        return


async def on_admin_answer_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت متن پاسخ ادمین و ارسال به کاربر + ذخیره در دانش"""
    if not _is_admin(update.effective_user.id):
        return

    key = context.user_data.get("admin_answering")
    if not key:
        return

    answer_text = update.message.text.strip()
    if len(answer_text) < 3:
        await update.message.reply_text("❌ پاسخ خیلی کوتاهه.")
        return

    context.user_data.pop("admin_answering")
    pending = get_pending_answers()
    info    = pending.pop(key, None)

    if not info:
        await update.message.reply_text("⚠️ زمان پاسخ گذشته یا قبلاً پاسخ داده شده.")
        return

    # ذخیره در دانش
    from bot.core.knowledge_engine import _normalize_question
    from bot.db.database import save_knowledge
    norm_q  = _normalize_question(info["question"])
    store_q = norm_q if len(norm_q) >= 3 else info["question"]
    await save_knowledge(
        question=store_q,
        answer=answer_text,
        chat_id=info["chat_id"],
        source="admin_answer",
        score=0.98,
    )

    # ارسال پاسخ به کاربر در گروه
    try:
        await context.bot.send_message(
            chat_id=info["chat_id"],
            text=(
                f"✅ پاسخ سوال شما:\n\n"
                f"❓ <b>{info['question'][:200]}</b>\n\n"
                f"💬 {answer_text}"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"ارسال پاسخ ادمین به گروه ناموفق: {e}")

    await update.message.reply_text(
        f"✅ پاسخ ارسال و در دانش ذخیره شد.\n"
        f"سوال: <code>{info['question'][:100]}</code>",
        parse_mode="HTML",
    )


# ─── callback عمومی (rules / myrank) ─────────────────────────────────────────

async def on_general_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data

    # ── تست کلیدهای اینلاین ────────────────────────────────────────────────
    if data == "tbtn_ok":
        await query.answer("✅ دکمه اول کار کرد!", show_alert=True)
        return
    if data == "tbtn_no":
        await query.answer("❌ دکمه دوم کار کرد!", show_alert=True)
        return
    if data == "tbtn_link":
        await query.answer("🔗 دکمه لینک کار کرد!", show_alert=True)
        return

    if data == "rules":
        await query.answer(t("rules_text"), show_alert=True)

    elif data.startswith("myrank_"):
        try:
            uid = int(data.split("_")[1])
        except (ValueError, IndexError):
            await query.answer()
            return
        chat_id = query.message.chat_id
        level   = await db.get_user_level(uid, chat_id)
        cfg     = get_config(level)
        warns   = await db.get_warnings(uid, chat_id)
        q       = "نامحدود" if cfg.daily_queries == -1 else str(cfg.daily_queries)
        await query.answer(
            f"🏅 سطح: {level_label(level)}\n"
            f"⚠️ اخطار: {warns}/3\n"
            f"❓ سوال روزانه: {q}",
            show_alert=True,
        )
    else:
        await query.answer()


# ─── callback فیدبک و رای‌گیری ───────────────────────────────────────────────

async def on_feedback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    data    = query.data
    voter   = query.from_user
    pending = get_pending_answers()

    # ── درسته ────────────────────────────────────────────────────────────────
    if data.startswith("fb_ok_"):
        key  = data[6:]
        info = pending.pop(key, None)
        if not info:
            await query.answer("این فیدبک دیگه فعال نیست.", show_alert=True)
            return
        allowed = await db.check_feedback_rate(voter.id, info["chat_id"], _MAX_FB_PER_HOUR)
        if not allowed:
            await query.answer("⏳ خیلی زیاد فیدبک دادی! کمی صبر کن.", show_alert=True)
            return
        await db.save_feedback(
            info["user_id"], info["chat_id"],
            info["question"], info["answer"], correct=True,
        )
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("🙏 ممنون از تاییدت!")

    # ── اشتباهه ──────────────────────────────────────────────────────────────
    elif data.startswith("fb_no_"):
        key  = data[6:]
        info = pending.get(key)
        if not info:
            await query.answer("این فیدبک دیگه فعال نیست.", show_alert=True)
            return
        allowed = await db.check_feedback_rate(voter.id, info["chat_id"], _MAX_FB_PER_HOUR)
        if not allowed:
            await query.answer("⏳ خیلی زیاد فیدبک دادی! کمی صبر کن.", show_alert=True)
            return
        prev = await db.count_user_corrections(voter.id, info["chat_id"], info["question"])
        if prev >= 2:
            await query.answer("⚠️ قبلاً این سوال رو تصحیح کردی!", show_alert=True)
            return
        context.user_data["awaiting_correction"] = key
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            f"✏️ جواب درست رو بنویس تا یاد بگیرم 👇\n"
            f"_(حداقل {_MIN_CORRECTION_LEN} کاراکتر)_",
            parse_mode="HTML",
        )
        # امتیاز به کاربر برای تصحیح
        await db.add_points(voter.id, info["chat_id"], 5)

    # ── رای روی تصحیح ────────────────────────────────────────────────────────
    elif data.startswith("vote_up_") or data.startswith("vote_dn_"):
        is_up = data.startswith("vote_up_")
        try:
            fb_id = int(data[8:])
        except ValueError:
            return
        result = await db.vote_correction(fb_id, voter.id, 1 if is_up else -1)
        fb     = await db.get_feedback_by_id(fb_id)
        if not fb:
            return
        # امتیاز برای رای‌دهنده
        await db.add_points(voter.id, fb["chat_id"], 2)
        if result["ups"] >= _VOTES_TO_CONFIRM:
            from bot.core.knowledge_engine import _normalize_question
            norm_q = _normalize_question(fb["question"])
            store_q = norm_q if len(norm_q) >= 3 else fb["question"]
            await db.save_knowledge(
                question=store_q, answer=fb["correction"],
                chat_id=fb["chat_id"], source="community_verified", score=0.92,
            )
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(
                f"✅ تصحیح تایید و یاد گرفته شد! ({result['ups']} رای موافق)"
            )
        elif result["downs"] >= _VOTES_TO_REJECT:
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(
                f"🗑️ تصحیح رد شد. ({result['downs']} رای مخالف)"
            )
        else:
            try:
                await query.edit_message_reply_markup(
                    reply_markup=build_vote_keyboard(fb_id, result["ups"], result["downs"])
                )
            except Exception:
                pass
            label = "👍" if is_up else "👎"
            await query.answer(
                f"{label} رای ثبت شد. موافق:{result['ups']} مخالف:{result['downs']}"
            )


# ─── callback گزارش ──────────────────────────────────────────────────────────

async def on_report_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data

    if not _is_admin(query.from_user.id):
        await query.answer("❌ فقط ادمین‌ها میتونن اقدام کنن.", show_alert=True)
        return

    parts  = data.split("_")
    action = parts[1]

    # ── تأیید رد گزارش ───────────────────────────────────────────────────────
    if action == "ignore":
        report_id = int(parts[2])
        await db.update_report_status(report_id, "ignored")
        await query.edit_message_text(
            query.message.text + "\n\n✅ *نادیده گرفته شد*",
            parse_mode="HTML",
        )
        return

    try:
        report_id = int(parts[2])
        user_id   = int(parts[3])
        chat_id   = int(parts[4])
    except (IndexError, ValueError):
        await query.answer("داده نامعتبر.", show_alert=True)
        return

    await db.update_report_status(report_id, "reviewed")

    # امتیاز به گزارش‌دهنده
    reporter_id = None
    try:
        import aiosqlite
        async with aiosqlite.connect(db.DB_PATH) as _db:
            cur = await _db.execute(
                "SELECT reporter_id FROM reports WHERE id=?", (report_id,)
            )
            row = await cur.fetchone()
            if row:
                reporter_id = row[0]
    except Exception:
        pass

    if action == "warn":
        warn_count = await db.add_warning(user_id, chat_id, f"گزارش #{report_id}")
        await mod.apply_warn_tag(context.bot, chat_id, user_id, warn_count)
        result_txt = f"⚠️ اخطار #{warn_count} داده شد"
        if reporter_id:
            await db.add_points(reporter_id, chat_id, 4)

    elif action == "mute":
        minutes      = await mod._next_mute_minutes(user_id, chat_id)
        duration_lbl = mod._format_minutes(minutes)
        await mod._mute(context.bot, chat_id, user_id, minutes=minutes)
        await db.add_punishment(
            user_id, chat_id, "mute", minutes * 60, f"گزارش #{report_id}"
        )
        await mod.apply_mute_tag(context.bot, chat_id, user_id, duration_lbl)
        result_txt = f"🔇 میوت {duration_lbl}"
        if reporter_id:
            await db.add_points(reporter_id, chat_id, 4)

    elif action == "ban":
        days, label = await mod._next_ban_duration(user_id, chat_id)
        until = (
            datetime.now(tz=timezone.utc) + timedelta(days=days)
        ) if days else None
        await mod._ban(context.bot, chat_id, user_id, until_date=until)
        await db.add_punishment(
            user_id, chat_id, "ban",
            days * 86400 if days else -1,
            f"گزارش #{report_id}",
        )
        result_txt = f"🚫 بن {label}"
        if reporter_id:
            await db.add_points(reporter_id, chat_id, 4)
    else:
        return

    await query.edit_message_text(
        query.message.text + f"\n\n✅ *اقدام انجام شد: {result_txt}*",
        parse_mode="HTML",
    )


# ─── callback تأیید/رد ارتقاء سطح ───────────────────────────────────────────

async def on_upgrade_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data

    if not _is_admin(query.from_user.id):
        await query.answer("❌ فقط ادمین‌ها میتونن اقدام کنن.", show_alert=True)
        return

    if data.startswith("upg_approve_"):
        parts   = data[12:].split("_")
        try:
            user_id = int(parts[0])
            chat_id = int(parts[1])
        except (IndexError, ValueError):
            return

        pending = await db.get_upgrade_pending(user_id, chat_id)
        if not pending:
            await query.answer("درخواست ارتقاء دیگه موجود نیست.", show_alert=True)
            try:
                await query.message.delete()
            except Exception:
                pass
            return

        to_level = pending["to_level"]
        await db.set_user_level(user_id, chat_id, to_level, set_by=query.from_user.id)

        from bot.core.moderation import _set_status_tag
        from bot.core.user_levels import get_config as _get_cfg, level_label as _lv_lbl
        new_cfg = _get_cfg(to_level)
        await _set_status_tag(context.bot, chat_id, user_id, new_cfg.tag)

        # ساخت mention بدون آبجکت User — فقط ID داریم
        user_mention = f'<a href="tg://user?id={user_id}">{user_id}</a>'
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎉 {user_mention} به سطح {_lv_lbl(to_level)} ارتقاء پیدا کرد!",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"upgrade announce failed: {e}")

        await db.delete_upgrade_pending(user_id, chat_id)
        try:
            await query.message.delete()
        except Exception:
            pass

    elif data.startswith("upg_reject_"):
        parts   = data[11:].split("_")
        try:
            user_id = int(parts[0])
            chat_id = int(parts[1])
        except (IndexError, ValueError):
            return

        # کم کردن ۵۰ امتیاز
        try:
            current_pts = await db.get_points(user_id, chat_id)
        except Exception:
            current_pts = 0
        new_pts = await db.add_points(user_id, chat_id, -50)

        # حذف درخواست ارتقاء
        await db.delete_upgrade_pending(user_id, chat_id)

        # اعلام به کاربر
        user_mention = f'<a href="tg://user?id={user_id}">{user_id}</a>'
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ درخواست ارتقاء {user_mention} رد شد.\n"
                     f"⭐ امتیاز: {current_pts} → {new_pts} (−50)",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"upgrade reject announce failed: {e}")

        try:
            await query.message.delete()
        except Exception:
            pass


# ─── callback بازبینی مدیریت (تأیید/رد تشخیص AI) ────────────────────────────

async def on_moderation_review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    pattern: rev_approve_{review_id}_{user_id}_{chat_id}_{action}
             rev_reject_{review_id}_{user_id}_{chat_id}_{action}
    """
    query = update.callback_query
    await query.answer()

    if not _is_admin(query.from_user.id):
        return

    data  = query.data
    parts = data.split("_")
    # parts[0]=rev, parts[1]=approve/reject, parts[2]=review_id,
    # parts[3]=user_id, parts[4]=chat_id, parts[5]=action
    try:
        decision  = parts[1]           # approve یا reject
        review_id = int(parts[2])
        user_id   = int(parts[3])
        chat_id   = int(parts[4])
        action    = parts[5]           # insult یا spam
    except (IndexError, ValueError):
        await query.answer("داده نامعتبر.", show_alert=True)
        return

    review = await db.get_moderation_review(review_id)
    if not review or review["status"] != "pending":
        try:
            await query.edit_message_text(
                query.message.text + "\n\n⚠️ قبلاً پردازش شده.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    from bot.core.moderation import (
        apply_warn_tag, apply_mute_tag,
        _mute, _ban, _next_ban_duration, _next_mute_minutes,
        _format_minutes, _notify_user,
    )
    from config import MAX_WARNINGS as _MAX_WARNS

    if decision == "approve":
        await db.update_moderation_review(review_id, "approved")
        warn_count = await db.add_warning(user_id, chat_id, review["ai_reason"] or "تخلف")
        await db.add_points(user_id, chat_id, -5)

        if warn_count >= _MAX_WARNS:
            days, label = await _next_ban_duration(user_id, chat_id)
            from datetime import datetime, timedelta, timezone
            until = (datetime.now(tz=timezone.utc) + timedelta(days=days)) if days else None
            await _ban(context.bot, chat_id, user_id, until_date=until)
            await db.add_punishment(
                user_id, chat_id, "ban",
                days * 86400 if days else -1, action,
            )
            await db.reset_warnings(user_id, chat_id)
            result_txt = f"🚫 بن {label}"
        elif action == "spam":
            minutes      = await _next_mute_minutes(user_id, chat_id)
            duration_lbl = _format_minutes(minutes)
            await _mute(context.bot, chat_id, user_id, minutes=minutes)
            await db.add_punishment(user_id, chat_id, "mute", minutes * 60, action)
            await apply_mute_tag(context.bot, chat_id, user_id, duration_lbl)
            result_txt = f"🔇 میوت {duration_lbl} + اخطار {warn_count}"
        else:
            result_txt = f"⚠️ اخطار {warn_count}"

        await apply_warn_tag(context.bot, chat_id, user_id, warn_count)

        try:
            await _notify_user(
                context.bot, user_id,
                f"⚠️ پیام شما در گروه حذف شد.\n"
                f"اخطار: {warn_count}/{_MAX_WARNS}\n"
                f"دلیل: {review['ai_reason'] or 'تخلف'}",
            )
        except Exception:
            pass

        try:
            await query.edit_message_text(
                query.message.text + f"\n\n✅ <b>تأیید شد — {result_txt}</b>",
                parse_mode="HTML",
            )
        except Exception:
            pass

    elif decision == "reject":
        await db.update_moderation_review(review_id, "rejected")
        await db.save_false_positive(
            action=action,
            message_text=review["message_text"] or "",
            ai_reason=review["ai_reason"] or "",
        )
        try:
            await query.edit_message_text(
                query.message.text + "\n\n❌ <b>رد شد — یاد گرفته شد</b>",
                parse_mode="HTML",
            )
        except Exception:
            pass
