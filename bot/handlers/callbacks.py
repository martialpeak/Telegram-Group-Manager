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
from bot.utils.helpers import mention, build_vote_keyboard
from bot.handlers.messages import get_pending_answers
from i18n import t

logger = logging.getLogger(__name__)

_MAX_FB_PER_HOUR  = 5
_VOTES_TO_CONFIRM = 2
_VOTES_TO_REJECT  = 3
_MIN_CORRECTION_LEN = 10


def _is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


# ─── callback عمومی (rules / myrank) ─────────────────────────────────────────

async def on_general_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data

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
        if result["ups"] >= _VOTES_TO_CONFIRM:
            await db.save_knowledge(
                question=fb["question"], answer=fb["correction"],
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

    if action == "warn":
        warn_count = await db.add_warning(user_id, chat_id, f"گزارش #{report_id}")
        await mod.apply_warn_tag(context.bot, chat_id, user_id, warn_count)
        result_txt = f"⚠️ اخطار #{warn_count} داده شد"

    elif action == "mute":
        minutes      = await mod._next_mute_minutes(user_id, chat_id)
        duration_lbl = mod._format_minutes(minutes)
        await mod._mute(context.bot, chat_id, user_id, minutes=minutes)
        await db.add_punishment(
            user_id, chat_id, "mute", minutes * 60, f"گزارش #{report_id}"
        )
        await mod.apply_mute_tag(context.bot, chat_id, user_id, duration_lbl)
        result_txt = f"🔇 میوت {duration_lbl}"

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
    else:
        return

    await query.edit_message_text(
        query.message.text + f"\n\n✅ *اقدام انجام شد: {result_txt}*",
        parse_mode="HTML",
    )
