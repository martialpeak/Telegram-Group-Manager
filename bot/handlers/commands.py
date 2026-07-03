"""
دستورات ربات تلگرام
"""

import logging
from datetime import datetime, timedelta, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import ContextTypes
from telegram.constants import ChatType

from config import MAX_WARNINGS, ADMIN_IDS
import bot.db.database as db
from bot.core import moderation as mod
from bot.core.knowledge_engine import learn_from_feedback
from bot.core.user_levels import (
    get_config, is_valid_level, level_label, level_summary, LEVEL_ORDER,
    next_auto_level,
)
from bot.utils.helpers import mention, send_and_delete, parse_duration, format_duration
from i18n import t

logger = logging.getLogger(__name__)


def _is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS




# ─── helper: پیدا کردن target از reply یا user_id ───────────────────────────

async def _get_target(update, context) -> tuple:
    """
    برمی‌گردونه (user_id, full_name, mention_str) یا (None, None, None)
    اولویت تشخیص:
      ۱. reply → کاربر ریپلای‌شده
      ۲. user_id عددی → مستقیم
      ۳. @username → اول از DB (message_log) وگرنه از تلگرام get_chat
    """
    from bot.utils.helpers import mention as _mention
    if update.message.reply_to_message:
        u = update.message.reply_to_message.from_user
        return u.id, u.full_name, _mention(u)
    args = list(context.args) if context.args else []
    if not args:
        return None, None, None

    raw = args[0]
    chat_id = update.message.chat_id

    # عدد — user_id مستقیم
    try:
        uid = int(raw)
        return uid, str(uid), f"کاربر <code>{uid}</code>"
    except ValueError:
        pass

    # @username — اول از DB (کاربرایی که ربات قبلاً تو گروه دیدتشون)
    username = raw.lstrip("@")
    if username:
        uname_lower = username.lower()
        try:
            found = await db.find_user_by_username(uname_lower, chat_id)
            if found:
                return (
                    found["user_id"],
                    found["full_name"] or username,
                    f"@{username}",
                )
        except Exception:
            pass

        # fallback: مستقیم از تلگرام (فقط اگه ربات قبلاً باهاش تعامل داشته)
        try:
            chat_member = await context.bot.get_chat(f"@{username}")
            uid = chat_member.id
            name = getattr(chat_member, "full_name", None) or username
            return uid, name, f"@{username}"
        except Exception:
            pass

    return None, None, None



async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_username = context.bot.username
    user = update.message.from_user
    chat = update.message.chat

    level_info = ""
    if chat.type != ChatType.PRIVATE:
        level = await db.get_user_level(user.id, chat.id)
        cfg   = get_config(level)
        q     = "نامحدود" if cfg.daily_queries == -1 else str(cfg.daily_queries)
        level_info = f"\n🏅 سطح شما: {level_label(level)} | سوال روزانه: {q}\n"

    await update.message.reply_text(
        "<b>🤖 ربات هوشمند مدیریت گروه</b>\n"
        f"{level_info}\n"
        "<b>📌 برای پرسیدن سوال:</b>\n"
        f"• منشن: <code>@{bot_username} سوالت</code>\n"
        "• یا ریپلای روی پیام ربات\n\n"
        "<b>📌 دستورات:</b>\n"
        "/myrank — سطح و آمار شما\n"
        "/mystats — آمار روزانه شما\n"
        "/levels — نمایش سطوح\n"
        "/report — گزارش پیام (ریپلای)\n\n"
        "<b>📌 دستورات ادمین:</b>\n"
        "/setlevel — تغییر سطح کاربر\n"
        "/warn — اخطار دستی (ریپلای)\n"
        "/unwarn — پاک کردن اخطار (ریپلای)\n"
        "/mute [دقیقه] — میوت دستی (ریپلای)\n"
        "/unmute — رفع میوت (ریپلای)\n"
        "/ban [مدت] [دلیل] — بن (ریپلای)\n"
        "/unban — آنبن (ریپلای یا user_id)\n"
        "/warnings — نمایش اخطارها (ریپلای)\n"
        "/reports — گزارش‌های در انتظر\n"
        "/stats — آمار گروه\n"
        "/violations — آمار تخلفات\n"
        "/search [متن] — جستجو در تاریخچه\n"
        "/learn — یادگیری از فیدبک‌ها\n"
        "/settings — پنل تنظیمات\n"
        "/update — آپدیت ربات از GitHub\n"
        "/clear — پاک کردن حافظه گفت‌وگوی شما با ربات",
        parse_mode="HTML",
    )


# ─── /myrank ─────────────────────────────────────────────────────────────────

async def cmd_myrank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    chat = update.message.chat
    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text(t("group_only"))
        return

    level    = await db.get_user_level(user.id, chat.id)
    cfg      = get_config(level)
    today_q  = await db.get_query_count(user.id, chat.id)
    today_lk = await db.get_daily_action(user.id, chat.id, "link")
    today_fw = await db.get_daily_action(user.id, chat.id, "forward")
    total_m  = await db.get_message_count(user.id, chat.id)
    warns    = await db.get_warnings(user.id, chat.id)
    points   = await db.get_points(user.id, chat.id)

    limit_q  = "نامحدود" if cfg.daily_queries  == -1 else f"{today_q}/{cfg.daily_queries}"
    limit_lk = "ممنوع"   if cfg.daily_links    ==  0 else ("نامحدود" if cfg.daily_links    == -1 else f"{today_lk}/{cfg.daily_links}")
    limit_fw = "ممنوع"   if cfg.daily_forwards ==  0 else ("نامحدود" if cfg.daily_forwards == -1 else f"{today_fw}/{cfg.daily_forwards}")

    next_lv      = next_auto_level(level)
    upgrade_line = ""
    if next_lv and cfg.auto_upgrade_msgs:
        remaining    = max(0, cfg.auto_upgrade_msgs - total_m)
        upgrade_line = f"\n📈 تا ارتقاء به {level_label(next_lv)}: {remaining} پیام"

    # آستانه امتیازی
    from bot.handlers.messages import UPGRADE_THRESHOLDS
    points_line = ""
    if level in UPGRADE_THRESHOLDS:
        threshold, next_pts_lv = UPGRADE_THRESHOLDS[level]
        points_line = f"\n⭐ امتیاز: {points} | آستانه بعدی: {threshold}"
    else:
        points_line = f"\n⭐ امتیاز: {points}"

    tag = mention(user)
    await update.message.reply_text(
        f"👤 {tag}\n\n"
        f"🏅 سطح: {level_label(level)}\n"
        f"📸 مدیا: {'✅' if cfg.can_media else '❌'}\n"
        f"🔗 لینک امروز: {limit_lk}\n"
        f"↩️ فوروارد امروز: {limit_fw}\n"
        f"❓ سوال امروز: {limit_q}\n"
        f"💬 کل پیام‌ها: {total_m}\n"
        f"⚠️ اخطار: {warns}/3"
        f"{points_line}"
        f"{upgrade_line}",
        parse_mode="HTML",
    )


# ─── /mystats ────────────────────────────────────────────────────────────────

async def cmd_mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    chat = update.message.chat
    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text(t("group_only"))
        return

    today_q  = await db.get_query_count(user.id, chat.id)
    today_lk = await db.get_daily_action(user.id, chat.id, "link")
    today_fw = await db.get_daily_action(user.id, chat.id, "forward")
    total_m  = await db.get_message_count(user.id, chat.id)
    warns    = await db.get_warnings(user.id, chat.id)
    level    = await db.get_user_level(user.id, chat.id)
    cfg      = get_config(level)
    extra    = await db.get_user_daily_stats(user.id, chat.id)
    points   = await db.get_points(user.id, chat.id)

    q_lim  = "نامحدود" if cfg.daily_queries  == -1 else str(cfg.daily_queries)
    lk_lim = "ممنوع"   if cfg.daily_links    ==  0 else ("نامحدود" if cfg.daily_links    == -1 else str(cfg.daily_links))
    fw_lim = "ممنوع"   if cfg.daily_forwards ==  0 else ("نامحدود" if cfg.daily_forwards == -1 else str(cfg.daily_forwards))

    def _bar(used: int, limit) -> str:
        if not isinstance(limit, int) or limit <= 0:
            return ""
        pct    = min(used / limit, 1.0)
        filled = int(pct * 8)
        return " [" + "█" * filled + "░" * (8 - filled) + f"] {used}/{limit}"

    lk_bar = _bar(today_lk, cfg.daily_links)
    fw_bar = _bar(today_fw, cfg.daily_forwards)
    q_bar  = _bar(today_q,  cfg.daily_queries)

    next_lv      = next_auto_level(level)
    upgrade_line = ""
    if next_lv and cfg.auto_upgrade_msgs:
        done  = total_m
        pct   = min(done / cfg.auto_upgrade_msgs, 1.0)
        bar_f = int(pct * 10)
        bar   = "█" * bar_f + "░" * (10 - bar_f)
        upgrade_line = (
            f"\n📈 *ارتقاء به {level_label(next_lv)}:*\n"
            f"  [{bar}] {done}/{cfg.auto_upgrade_msgs} پیام"
        )

    # آستانه امتیازی
    from bot.handlers.messages import UPGRADE_THRESHOLDS
    if level in UPGRADE_THRESHOLDS:
        threshold, _ = UPGRADE_THRESHOLDS[level]
        pts_line = f"\n⭐ امتیاز: {points} | آستانه بعدی: {threshold}"
    else:
        pts_line = f"\n⭐ امتیاز: {points}"

    tag = mention(user)
    await update.message.reply_text(
        f"📊 *آمار روزانه* — {tag}\n"
        "━━━━━━━━━━━━━━\n\n"
        f"🏅 سطح: {level_label(level)}\n"
        f"💬 پیام امروز: {extra['msgs_today']}\n"
        f"💬 کل پیام‌ها: {total_m}\n\n"
        "📌 *مصرف امروز:*\n"
        f"  🔗 لینک:{lk_bar if lk_bar else ' ' + lk_lim}\n"
        f"  ↩️ فوروارد:{fw_bar if fw_bar else ' ' + fw_lim}\n"
        f"  ❓ سوال ربات:{q_bar if q_bar else ' ' + q_lim}\n\n"
        "⚠️ *وضعیت:*\n"
        f"  اخطار فعلی: {warns}/{MAX_WARNINGS}\n"
        f"  تخلف امروز: {extra['violations_today']}\n"
        f"  میوت این هفته: {extra['mutes_week']}\n"
        f"  بن کل: {extra['bans_total']}"
        f"{pts_line}"
        f"{upgrade_line}",
        parse_mode="HTML",
    )


# ─── /levels ─────────────────────────────────────────────────────────────────

async def cmd_levels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(level_summary(), parse_mode="HTML")


# ─── /setlevel ───────────────────────────────────────────────────────────────

async def cmd_setlevel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        await update.message.reply_text("❌ فقط ادمین‌ها میتونن سطح تغییر بدن.")
        return

    args = list(context.args) if context.args else []

    # تشخیص target و سطح
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        target_mention = mention(update.message.reply_to_message.from_user)
        level_arg = args[0].lower() if args else None
    elif args:
        try:
            target_id = int(args[0])
            target_mention = f"کاربر <code>{target_id}</code>"
            level_arg = args[1].lower() if len(args) > 1 else None
        except ValueError:
            await update.message.reply_text(
                f"استفاده: /setlevel <user_id> <سطح>\nسطوح: {' | '.join(LEVEL_ORDER)}"
            )
            return
    else:
        await update.message.reply_text(
            f"روی پیام ریپلای بزن یا /setlevel <user_id> <سطح>\nسطوح: {' | '.join(LEVEL_ORDER)}"
        )
        return

    if not level_arg:
        await update.message.reply_text(
            f"سطح رو مشخص کن.\nسطوح: {' | '.join(LEVEL_ORDER)}"
        )
        return

    if not is_valid_level(level_arg):
        await update.message.reply_text(
            f"❌ سطح نامعتبر!\nسطوح معتبر: {' | '.join(LEVEL_ORDER)}"
        )
        return

    chat_id = update.message.chat_id
    cfg     = get_config(level_arg)
    await db.set_user_level(target_id, chat_id, level_arg, update.message.from_user.id)

    tag_text = cfg.tag if level_arg != "simple" else "ساده"
    from bot.core.moderation import _set_status_tag
    await _set_status_tag(context.bot, chat_id, target_id, tag_text)

    await update.message.reply_text(
        f"✅ سطح {target_mention} به {level_label(level_arg)} تغییر کرد.",
        parse_mode="HTML",
    )


# ─── /search ─────────────────────────────────────────────────────────────────

async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("استفاده: /search [کلمه کلیدی]")
        return
    query   = " ".join(context.args)
    results = await db.search_messages(query, update.message.chat_id, limit=5)
    if not results:
        await update.message.reply_text(f"🔍 نتیجه‌ای برای «{query}» پیدا نشد.")
        return
    text = f"🔍 نتایج جستجو برای «{query}»:\n\n"
    for r in results:
        date  = r["date"][:10]
        text += f"👤 {r['name']} [{date}]:\n{r['text'][:200]}\n\n"
    await update.message.reply_text(text)


# ─── /learn ──────────────────────────────────────────────────────────────────

async def cmd_learn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        return
    count = await learn_from_feedback()
    await update.message.reply_text(f"🧠 {count} مورد جدید یاد گرفته شد.")


# ─── /clear — پاک کردن حافظه مکالمه کاربر با ربات ──────────────────────────────

async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    پاک کردن تاریخچه گفت‌وگوی شخصی کاربر با ربات.
    برای شروع مکالمه تازه و حفظ حریم خصوصی.
    """
    user = update.message.from_user
    chat_id = update.message.chat_id
    try:
        await db.clear_conversation(user.id, chat_id)
        await update.message.reply_text(
            "🧹 حافظه گفت‌وگوی شما با ربات پاک شد.\n"
            "از الان ربات مکالمه قبلی رو یادش نمیاد."
        )
    except Exception as e:
        logger.warning(f"cmd_clear failed: {e}")
        await update.message.reply_text("❌ خطا در پاک‌سازی حافظه.")


# ─── /warn ───────────────────────────────────────────────────────────────────

async def cmd_warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        return
    target_id, _, target_mention = await _get_target(update, context)
    if not target_id:
        await update.message.reply_text("روی پیام ریپلای بزن یا /warn <user_id> [دلیل]")
        return
    chat_id = update.message.chat_id
    # اگه user_id آرگومان بود، بقیه args دلیل هستن
    if update.message.reply_to_message:
        reason = " ".join(context.args) or "تخلف"
    else:
        reason = " ".join(context.args[1:]) or "تخلف"
    warn_count = await db.add_warning(target_id, chat_id, reason)
    # ثبت رویداد اخطار
    try:
        await db.log_action(
            chat_id=chat_id, action="warn", user_id=target_id,
            actor_id=update.message.from_user.id,
            target_name=target_mention, reason=reason,
        )
    except Exception:
        pass

    if warn_count >= MAX_WARNINGS:
        await mod._ban(context.bot, chat_id, target_id)
        await db.reset_warnings(target_id, chat_id)
        try:
            await db.log_action(
                chat_id=chat_id, action="ban", user_id=target_id,
                actor_id=update.message.from_user.id,
                target_name=target_mention, reason=f"اخطار مکرر ({warn_count})",
            )
        except Exception:
            pass
        await update.message.reply_text(
            t("banned", name=target_mention), parse_mode="HTML"
        )
    else:
        await mod.apply_warn_tag(context.bot, chat_id, target_id, warn_count)
        await update.message.reply_text(
            t("warn_insult", name=target_mention, warn=warn_count, max=MAX_WARNINGS),
            parse_mode="HTML",
        )


# ─── /unwarn ─────────────────────────────────────────────────────────────────

async def cmd_unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        return
    target_id, _, target_mention = await _get_target(update, context)
    if not target_id:
        await update.message.reply_text("روی پیام ریپلای بزن یا /unwarn <user_id>")
        return
    chat_id = update.message.chat_id
    await db.reset_warnings(target_id, chat_id)
    await mod.apply_warn_tag(context.bot, chat_id, target_id, 0)
    await update.message.reply_text(
        f"✅ اخطارهای {target_mention} پاک شد.", parse_mode="HTML"
    )


# ─── /warnings ───────────────────────────────────────────────────────────────

async def cmd_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id, target_name, _ = await _get_target(update, context)
    if not target_id:
        await update.message.reply_text("روی پیام ریپلای بزن یا /warnings <user_id>")
        return
    count = await db.get_warnings(target_id, update.message.chat_id)
    await update.message.reply_text(
        f"📋 {target_name} — اخطار: {count}/{MAX_WARNINGS}"
    )


# ─── /mute ───────────────────────────────────────────────────────────────────

async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        return
    target_id, _, target_mention = await _get_target(update, context)
    if not target_id:
        await update.message.reply_text("روی پیام ریپلای بزن یا /mute <user_id> [دقیقه]")
        return
    chat_id = update.message.chat_id

    # اگه reply بود، args[0] دقیقه است. اگه user_id بود، args[1] دقیقه است
    args = list(context.args) if context.args else []
    minute_arg = args[1] if not update.message.reply_to_message and len(args) > 1 else (args[0] if update.message.reply_to_message and args else None)
    if minute_arg:
        try:
            minutes = max(1, int(minute_arg))
        except ValueError:
            minutes = await mod._next_mute_minutes(target_id, chat_id)
    else:
        minutes = await mod._next_mute_minutes(target_id, chat_id)

    duration_lbl = mod._format_minutes(minutes)
    await mod._mute(context.bot, chat_id, target_id, minutes=minutes)
    await db.add_punishment(target_id, chat_id, "mute", minutes * 60, "میوت دستی ادمین")
    await mod.apply_mute_tag(context.bot, chat_id, target_id, duration_lbl)
    # ثبت رویداد میوت
    try:
        await db.log_action(
            chat_id=chat_id, action="mute", user_id=target_id,
            actor_id=update.message.from_user.id,
            target_name=target_mention, reason=f"میوت دستی {duration_lbl}",
        )
    except Exception:
        pass
    await update.message.reply_text(
        f"🔇 {target_mention} به مدت <b>{duration_lbl}</b> میوت شد.",
        parse_mode="HTML",
    )


# ─── /unmute ─────────────────────────────────────────────────────────────────

async def cmd_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        return
    target_id, _, target_mention = await _get_target(update, context)
    if not target_id:
        await update.message.reply_text("روی پیام ریپلای بزن یا /unmute <user_id>")
        return
    chat_id = update.message.chat_id
    all_perms = ChatPermissions(
        can_send_messages=True, can_send_audios=True,
        can_send_documents=True, can_send_photos=True,
        can_send_videos=True, can_send_voice_notes=True,
        can_send_polls=True, can_send_other_messages=True,
    )
    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id, user_id=target_id, permissions=all_perms
        )
    except Exception as e:
        logger.warning(f"unmute ناموفق: {e}")
    warns = await db.get_warnings(target_id, chat_id)
    await mod.apply_warn_tag(context.bot, chat_id, target_id, warns)
    await update.message.reply_text(
        f"🔊 میوت {target_mention} برداشته شد.", parse_mode="HTML"
    )


# ─── /ban ────────────────────────────────────────────────────────────────────

async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /ban              → بن پلکانی (ریپلای)
    /ban <user_id>    → بن پلکانی با ID
    /ban @username    → بن با یوزرنیم
    /ban 30m          → ریپلای + مدت
    /ban <user_id> 1h دلیل → ID + مدت + دلیل
    """
    if not _is_admin(update.message.from_user.id):
        return

    args = list(context.args) if context.args else []
    chat_id = update.message.chat_id

    # تشخیص target با helper مشترک (reply / user_id / @username)
    target_id, target_name, target_mention = await _get_target(update, context)
    if not target_id:
        await update.message.reply_text(
            "❌ کاربر پیدا نشد!\n\n"
            "روش‌های صحیح:\n"
            "• روی پیام کاربر ریپلای بزن و /ban بنویس\n"
            "• <code>/ban user_id</code> (شناسه عددی)\n"
            "• <code>/ban @username</code> (فقط اگه کاربر قبلاً تو گروه پیام داده باشه)\n\n"
            "نکته: برای یوزرنیم، ربات باید کاربر رو قبلاً تو گروه دیده باشه.",
            parse_mode="HTML",
        )
        return

    # اگه target از آرگومان اومده (نه reply)، args[0] مصرف شده و باید حذف بشه
    if not update.message.reply_to_message and args:
        args = args[1:]

    reason       = "تخلف"
    until_date   = None
    duration_txt = "دائم"

    if args:
        seconds = parse_duration(args[0])
        if seconds:
            until_date   = datetime.now(tz=timezone.utc) + timedelta(seconds=seconds)
            duration_txt = format_duration(seconds)
            args = args[1:]
        if args:
            reason = " ".join(args)
    else:
        days, duration_txt = await mod._next_ban_duration(target_id, chat_id)
        if days:
            until_date = datetime.now(tz=timezone.utc) + timedelta(days=days)

    await mod._ban(context.bot, chat_id, target_id, until_date=until_date)
    duration_secs = (
        int((until_date - datetime.now(tz=timezone.utc)).total_seconds())
        if until_date else -1
    )
    await db.add_punishment(target_id, chat_id, "ban", duration_secs, reason)
    # ثبت رویداد بن با دلیل
    try:
        await db.log_action(
            chat_id=chat_id, action="ban", user_id=target_id,
            actor_id=update.message.from_user.id,
            target_name=target_name,
            reason=f"{reason} ({duration_txt})",
        )
    except Exception:
        pass

    if until_date:
        await update.message.reply_text(
            t("banned_temp", name=target_mention, duration=duration_txt, reason=reason),
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            t("banned", name=target_mention), parse_mode="HTML"
        )


# ─── /unban ──────────────────────────────────────────────────────────────────

async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        return
    chat_id = update.message.chat_id
    target_id = None
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
    elif context.args:
        try:
            target_id = int(context.args[0])
        except ValueError:
            pass
    if not target_id:
        await update.message.reply_text("روی پیام ریپلای بزن یا /unban <user_id>")
        return

    # آخرین دلیل بن رو از حافظه بخون
    ban_info = await db.get_last_ban_reason(target_id, chat_id)

    try:
        await context.bot.unban_chat_member(
            chat_id=chat_id, user_id=target_id, only_if_banned=True,
        )
        # ثبت رویداد آنبن
        try:
            await db.log_action(
                chat_id=chat_id, action="unban", user_id=target_id,
                actor_id=update.message.from_user.id,
                target_name=str(target_id),
            )
        except Exception:
            pass
        # نمایش دلیل بن قبلی (اگه هست)
        if ban_info:
            date_str = ban_info.get("date", "")[:16] if ban_info.get("date") else ""
            await update.message.reply_text(
                f"✅ کاربر <code>{target_id}</code> آنبن شد.\n\n"
                f"📋 <b>دلیل بن قبلی:</b>\n"
                f"📝 {ban_info['reason']}\n"
                f"📅 {date_str}",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(
                f"✅ کاربر <code>{target_id}</code> آنبن شد.\n\n"
                f"📋 دلیل بنی ثبت نشده بود."
            )
    except Exception as e:
        await update.message.reply_text(f"❌ آنبن ناموفق: {e}")


# ─── /stats ──────────────────────────────────────────────────────────────────

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        return
    chat_id = update.message.chat_id
    stats   = await db.get_stats(chat_id)
    daily   = await db.get_daily_stats(chat_id)

    await update.message.reply_text(
        "📊 *آمار گروه*\n"
        "━━━━━━━━━━━━━━\n\n"
        "📅 *امروز:*\n"
        f"  👥 کاربران فعال: {daily.get('active_users_today', 0)}\n"
        f"  💬 پیام عادی: {daily.get('normal', 0)}\n"
        f"  🔴 توهین: {daily.get('insult', 0)}\n"
        f"  📢 اسپم: {daily.get('spam', 0)}\n"
        f"  ⚠️ اخطار داده شده: {daily.get('warns_today', 0)}\n"
        f"  🔇 میوت امروز: {daily.get('mutes_today', 0)}\n"
        f"  🚫 بن امروز: {daily.get('bans_today', 0)}\n"
        f"  🔗 لینک ارسالی: {daily.get('links_today', 0)}\n"
        f"  ↩️ فوروارد: {daily.get('forwards_today', 0)}\n\n"
        "📈 *کل تاریخ:*\n"
        f"  🔴 توهین: {stats.get('insult', 0)}\n"
        f"  📢 اسپم: {stats.get('spam', 0)}\n"
        f"  ❓ سوال پاسخ‌داده: {stats.get('request', 0)}\n"
        f"  👥 کاربران اخطارخورده: {stats.get('warned_users', 0)}\n"
        f"  🧠 دانش ذخیره‌شده: {stats.get('knowledge_items', 0)} مورد",
        parse_mode="HTML",
    )


# ─── /violations ─────────────────────────────────────────────────────────────

async def cmd_violations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        return
    chat_id = update.message.chat_id
    v = await db.get_violation_stats(chat_id)
    total = v["total"]
    week  = v["week"]

    top_lines = ""
    for i, u in enumerate(v["top_violators"], 1):
        top_lines += f"  {i}. {u['name']} — {u['count']} تخلف\n"
    if not top_lines:
        top_lines = "  هنوز تخلفی ثبت نشده\n"

    await update.message.reply_text(
        "🔍 *آمار تخلفات*\n"
        "━━━━━━━━━━━━━━\n\n"
        "📅 *۷ روز گذشته:*\n"
        f"  🔴 توهین: {week.get('insult', 0)}\n"
        f"  📢 اسپم: {week.get('spam', 0)}\n"
        f"  🔇 میوت: {week.get('mutes', 0)}\n"
        f"  🚫 بن: {week.get('bans', 0)}\n\n"
        "📈 *کل تاریخ:*\n"
        f"  🔴 توهین: {total.get('insult', 0)}\n"
        f"  📢 اسپم: {total.get('spam', 0)}\n"
        f"  🔇 میوت: {total.get('mutes', 0)}\n"
        f"  🚫 بن: {total.get('bans', 0)}\n\n"
        "🏆 *پرتخلف‌ترین کاربران:*\n"
        f"{top_lines}",
        parse_mode="HTML",
    )


# ─── /report ─────────────────────────────────────────────────────────────────

async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user    = message.from_user
    chat    = message.chat

    if chat.type == ChatType.PRIVATE:
        await message.reply_text(t("group_only"))
        return

    if not message.reply_to_message:
        await send_and_delete(message, t("report_how"), delay=15)
        return

    target_msg  = message.reply_to_message
    target_user = target_msg.from_user

    if _is_admin(target_user.id):
        await send_and_delete(message, t("report_admin"), delay=10)
        return
    if target_user.id == user.id:
        await send_and_delete(message, t("report_self"), delay=10)
        return

    today_reports = await db.get_user_report_today(user.id, chat.id)
    if today_reports >= 3:
        await send_and_delete(message, t("report_limit"), delay=12)
        return

    reason       = " ".join(context.args) if context.args else "محتوای نامناسب"
    message_text = target_msg.text or target_msg.caption or "[مدیا/استیکر]"

    report_id = await db.save_report(
        reporter_id=user.id,
        reported_id=target_user.id,
        chat_id=chat.id,
        message_id=target_msg.message_id,
        message_text=message_text[:500],
        reason=reason,
    )

    await send_and_delete(
        message,
        t("report_confirm", report_id=report_id),
        delay=20,
    )

    try:
        await context.bot.delete_message(chat.id, message.message_id)
    except Exception:
        pass

    notify_text = t(
        "report_notify",
        report_id=report_id,
        reporter=mention(user),
        reported=mention(target_user),
        reason=reason,
        text=message_text[:200],
        link=f"https://t.me/c/{str(chat.id)[4:]}/{target_msg.message_id}",
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("⚠️ اخطار",  callback_data=f"rpt_warn_{report_id}_{target_user.id}_{chat.id}"),
        InlineKeyboardButton("🔇 میوت",   callback_data=f"rpt_mute_{report_id}_{target_user.id}_{chat.id}"),
        InlineKeyboardButton("🚫 بن",     callback_data=f"rpt_ban_{report_id}_{target_user.id}_{chat.id}"),
        InlineKeyboardButton("✅ نادیده", callback_data=f"rpt_ignore_{report_id}"),
    ]])

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=notify_text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        except Exception:
            pass


# ─── /reports ────────────────────────────────────────────────────────────────

async def cmd_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        return
    chat_id = update.message.chat_id
    pending = await db.get_pending_reports(chat_id, limit=5)
    counts  = await db.get_report_count(chat_id)

    if not pending:
        await update.message.reply_text(
            f"📭 گزارش در انتظر بررسی وجود ندارد.\n"
            f"✅ بررسی‌شده: {counts.get('reviewed', 0)} | "
            f"❌ نادیده: {counts.get('ignored', 0)}",
        )
        return

    text = (
        f"📋 *گزارش‌های در انتظر: {len(pending)}*\n"
        f"✅ بررسی‌شده: {counts.get('reviewed', 0)} | "
        f"❌ نادیده: {counts.get('ignored', 0)}\n"
        "━━━━━━━━━━━━━━\n\n"
    )
    for r in pending:
        date  = r["created_at"][:16]
        text += (
            f"🔖 *#{r['id']}* — {date}\n"
            f"🎯 کاربر: `{r['reported_id']}`\n"
            f"📌 دلیل: {r['reason']}\n"
            f"💬 پیام: {r['message_text'][:100]}\n\n"
        )
    await update.message.reply_text(text, parse_mode="HTML")


# ─── /tagall — تگ همه اعضای گروه ────────────────────────────────────────────

async def cmd_tagall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    تگ همه کاربرانی که در DB ثبت شدن رو بر اساس سطحشون ست می‌کنه.
    فقط ادمین — در گروه اجرا می‌شه.
    """
    if not _is_admin(update.message.from_user.id):
        return
    chat = update.message.chat
    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text("این دستور فقط در گروه کار می‌کند.")
        return

    from bot.core.moderation import _set_status_tag

    msg = await update.message.reply_text("⏳ در حال تگ کردن اعضا...")

    # همه کاربرانی که سطح non-simple دارن
    chat_levels = await db.get_chat_levels(chat.id)
    tagged_non_simple = 0
    for entry in chat_levels:
        cfg = get_config(entry["level"])
        try:
            await _set_status_tag(context.bot, chat.id, entry["user_id"], cfg.tag)
            tagged_non_simple += 1
        except Exception:
            pass

    # همه کاربرانی که در message_log هستن ولی سطح ندارن (simple)
    tagged_simple = 0
    try:
        import bot.db.database as _db
        import aiosqlite
        async with aiosqlite.connect(_db.DB_PATH) as _conn:
            cur = await _conn.execute(
                """SELECT DISTINCT user_id FROM message_log
                   WHERE chat_id=?
                   AND user_id NOT IN (
                       SELECT user_id FROM user_levels WHERE chat_id=?
                   )""",
                (chat.id, chat.id),
            )
            rows = await cur.fetchall()
        for (uid,) in rows:
            try:
                await _set_status_tag(context.bot, chat.id, uid, "ساده")
                tagged_simple += 1
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"tagall simple error: {e}")

    await msg.edit_text(
        f"✅ تگ‌گذاری کامل شد:\n"
        f"  🏅 سطح‌دار: {tagged_non_simple} نفر\n"
        f"  👤 ساده: {tagged_simple} نفر"
    )


# ─── /testbtn — تست کلیدهای اینلاین (دیباگ) ──────────────────────────────────

async def cmd_testbtn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    دستور تست برای بررسی کلیدهای اینلاین و تشخیص مشکلات.
    فقط ادمین.
    """
    if not _is_admin(update.message.from_user.id):
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تست دکمه ۱", callback_data="tbtn_ok"),
            InlineKeyboardButton("❌ تست دکمه ۲", callback_data="tbtn_no"),
        ],
        [
            InlineKeyboardButton("🔗 تست لینک", callback_data="tbtn_link"),
        ],
    ])
    try:
        sent = await update.message.reply_text(
            "🧪 <b>تست کلیدهای اینلاین</b>\n\n"
            "اگه این کلیدها رو می‌بینی یعنی کلیدها درست کار می‌کنن.\n"
            "اگه پیام بدون کلید نشون داده شد، مشکل از دسترسی ربات به گروهه.",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        logger.info(f"✅ test buttons sent to chat {update.message.chat_id}, msg {sent.message_id}")
    except Exception as e:
        logger.error(f"❌ test buttons failed: {e}")
        await update.message.reply_text(f"❌ خطا در ارسال کلیدها: <code>{e}</code>", parse_mode="HTML")


# ─── /sync — همگام‌سازی از کانال‌های آموزشی ─────────────────────────────────────

async def cmd_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    همگام‌سازی دانش از کانال‌های آموزشی تنظیم‌شده.
    فقط ادمین.
    """
    if not _is_admin(update.message.from_user.id):
        return

    from config import TRAINING_CHANNELS
    if not TRAINING_CHANNELS:
        await update.message.reply_text(
            "❌ هیچ کانال آموزشی تنظیم نشده!\n\n"
            "برای تنظیم، فایل .env رو ویرایش کن:\n"
            "<code>TRAINING_CHANNELS=@channel1,@channel2</code>",
            parse_mode="HTML",
        )
        return

    msg = await update.message.reply_text(
        f"📚 در حال همگام‌سازی از {len(TRAINING_CHANNELS)} کانال...\n"
        f"این عملیات ممکنه چند دقیقه طول بکشه."
    )

    try:
        from bot.core.knowledge_engine import sync_training_channels
        total = await sync_training_channels()
        await msg.edit_text(
            f"✅ همگام‌سازی کامل شد!\n\n"
            f"📊 تعداد مطالب یادگرفته‌شده: {total}\n"
            f"📚 کانال‌ها: {', '.join(TRAINING_CHANNELS)}"
        )
    except Exception as e:
        logger.error(f"sync failed: {e}")
        await msg.edit_text(f"❌ خطا در همگام‌سازی: <code>{str(e)[:200]}</code>", parse_mode="HTML")


# ─── /recent — نمایش رویدادهای اخیر گروه ──────────────────────────────────────

ACTION_LABELS = {
    "join":    "➕ ورود",
    "leave":   "➖ خروج",
    "ban":     "🚫 بن",
    "unban":   "✅ آن‌بن",
    "mute":    "🔇 میوت",
    "unmute":  "🔊 آن‌میوت",
    "warn":    "⚠️ اخطار",
    "unwarn":  "🧹 پاک‌سازی اخطار",
    "report":  "🚨 گزارش",
}


async def cmd_recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    نمایش آخرین رویدادهای گروه (ورود، خروج، بن، میوت، ...).
    فقط ادمین. در گروه اجرا می‌شه.
    """
    if not _is_admin(update.message.from_user.id):
        return

    chat = update.message.chat
    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text("این دستور فقط در گروه کار می‌کند.")
        return

    # تعداد رویدادها (پیش‌فرض ۱۵، حداکثر ۵۰)
    limit = 15
    if context.args:
        try:
            limit = max(5, min(50, int(context.args[0])))
        except ValueError:
            pass

    actions = await db.get_recent_actions(chat.id, limit=limit)
    if not actions:
        await update.message.reply_text("📭 هنوز هیچ رویدادی ثبت نشده.")
        return

    text = f"📋 <b>رویدادهای اخیر گروه</b> ({len(actions)} مورد)\n"
    text += "━━━━━━━━━━━━━━━\n\n"

    for a in actions:
        label = ACTION_LABELS.get(a["action"], a["action"])
        date = (a["created_at"] or "")[:16]
        name = a.get("target_name") or "نامشخص"
        # اگه user_id هست، قابل کلیکش کن
        if a.get("user_id"):
            name = f'<a href="tg://user?id={a["user_id"]}">{name}</a>'
        else:
            name = f"<code>{name}</code>"

        line = f"{label} — {name}\n   🕐 {date}"
        if a.get("reason"):
            line += f"\n   📝 {a['reason'][:80]}"
        text += line + "\n\n"

    # اگه متن خیلی طولانیه، تقسیم کن
    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            await update.message.reply_text(text[i:i+4000], parse_mode="HTML")
    else:
        await update.message.reply_text(text, parse_mode="HTML")


# ─── /addchannel — افزودن کانال آموزشی ────────────────────────────────────────

async def cmd_addchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """افزودن کانال آموزشی برای یادگیری ربات. فقط ادمین."""
    if not _is_admin(update.message.from_user.id):
        return
    if not context.args:
        await update.message.reply_text(
            "استفاده: <code>/addchannel @channelname</code>",
            parse_mode="HTML",
        )
        return
    channel = context.args[0].strip()
    from config import add_training_channel, TRAINING_CHANNELS
    added = add_training_channel(channel)
    if added:
        await update.message.reply_text(
            f"✅ کانال {channel} به کانال‌های آموزشی اضافه شد.\n\n"
            f"📚 کانال‌های فعلی: {', '.join(TRAINING_CHANNELS) or 'هیچ'}\n\n"
            f"برای یادگیری از این کانال، دستور /sync رو بزن.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            f"⚠️ کانال {channel} از قبل موجود است.\n"
            f"📚 کانال‌های فعلی: {', '.join(TRAINING_CHANNELS) or 'هیچ'}",
            parse_mode="HTML",
        )


# ─── /delchannel — حذف کانال آموزشی ───────────────────────────────────────────

async def cmd_delchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف کانال آموزشی. فقط ادمین."""
    if not _is_admin(update.message.from_user.id):
        return
    if not context.args:
        await update.message.reply_text(
            "استفاده: <code>/delchannel @channelname</code>",
            parse_mode="HTML",
        )
        return
    channel = context.args[0].strip()
    from config import remove_training_channel, TRAINING_CHANNELS
    removed = remove_training_channel(channel)
    if removed:
        await update.message.reply_text(
            f"✅ کانال {channel} حذف شد.\n"
            f"📚 کانال‌های فعلی: {', '.join(TRAINING_CHANNELS) or 'هیچ'}",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            f"⚠️ کانال {channel} در لیست نبود.\n"
            f"📚 کانال‌های فعلی: {', '.join(TRAINING_CHANNELS) or 'هیچ'}",
            parse_mode="HTML",
        )
