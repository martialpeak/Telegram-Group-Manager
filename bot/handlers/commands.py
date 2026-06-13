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


# ─── /start ──────────────────────────────────────────────────────────────────

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
        "/update — آپدیت ربات از GitHub",
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

    limit_q  = "نامحدود" if cfg.daily_queries  == -1 else f"{today_q}/{cfg.daily_queries}"
    limit_lk = "ممنوع"   if cfg.daily_links    ==  0 else ("نامحدود" if cfg.daily_links    == -1 else f"{today_lk}/{cfg.daily_links}")
    limit_fw = "ممنوع"   if cfg.daily_forwards ==  0 else ("نامحدود" if cfg.daily_forwards == -1 else f"{today_fw}/{cfg.daily_forwards}")

    next_lv      = next_auto_level(level)
    upgrade_line = ""
    if next_lv and cfg.auto_upgrade_msgs:
        remaining    = max(0, cfg.auto_upgrade_msgs - total_m)
        upgrade_line = f"\n📈 تا ارتقاء به {level_label(next_lv)}: {remaining} پیام"

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
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "روی پیام کاربر موردنظر ریپلای بزنید.\n"
            f"استفاده: /setlevel <سطح>\nسطوح: {' | '.join(LEVEL_ORDER)}"
        )
        return
    if not context.args:
        await update.message.reply_text(
            f"سطح رو مشخص کن: /setlevel <سطح>\nسطوح: {' | '.join(LEVEL_ORDER)}"
        )
        return

    new_level = context.args[0].lower()
    if not is_valid_level(new_level):
        await update.message.reply_text(
            f"❌ سطح نامعتبر!\nسطوح معتبر: {' | '.join(LEVEL_ORDER)}"
        )
        return

    target  = update.message.reply_to_message.from_user
    chat_id = update.message.chat_id
    cfg     = get_config(new_level)

    await db.set_user_level(target.id, chat_id, new_level, update.message.from_user.id)

    tag_text = "" if new_level == "simple" else cfg.tag
    from bot.core.moderation import _set_status_tag
    await _set_status_tag(context.bot, chat_id, target.id, tag_text)
    tag_note = f" | تگ: {cfg.label}" if tag_text else " | تگ حذف شد"

    await update.message.reply_text(
        f"✅ سطح {mention(target)} به {level_label(new_level)} تغییر کرد.{tag_note}",
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


# ─── /warn ───────────────────────────────────────────────────────────────────

async def cmd_warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("روی پیام کاربر موردنظر ریپلای بزنید.")
        return
    target     = update.message.reply_to_message.from_user
    chat_id    = update.message.chat_id
    reason     = " ".join(context.args) or "تخلف"
    warn_count = await db.add_warning(target.id, chat_id, reason)

    if warn_count >= MAX_WARNINGS:
        await mod._ban(context.bot, chat_id, target.id)
        await db.reset_warnings(target.id, chat_id)
        await update.message.reply_text(
            t("banned", name=mention(target)), parse_mode="HTML"
        )
    else:
        await mod.apply_warn_tag(context.bot, chat_id, target.id, warn_count)
        await update.message.reply_text(
            t("warn_insult", name=mention(target), warn=warn_count, max=MAX_WARNINGS),
            parse_mode="HTML",
        )


# ─── /unwarn ─────────────────────────────────────────────────────────────────

async def cmd_unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("روی پیام کاربر موردنظر ریپلای بزنید.")
        return
    target  = update.message.reply_to_message.from_user
    chat_id = update.message.chat_id
    await db.reset_warnings(target.id, chat_id)
    await mod.apply_warn_tag(context.bot, chat_id, target.id, 0)
    await update.message.reply_text(
        f"✅ اخطارهای {mention(target)} پاک شد.", parse_mode="HTML"
    )


# ─── /warnings ───────────────────────────────────────────────────────────────

async def cmd_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text("روی پیام کاربر موردنظر ریپلای بزنید.")
        return
    target = update.message.reply_to_message.from_user
    count  = await db.get_warnings(target.id, update.message.chat_id)
    await update.message.reply_text(
        f"📋 {target.full_name} — اخطار: {count}/{MAX_WARNINGS}"
    )


# ─── /mute ───────────────────────────────────────────────────────────────────

async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("روی پیام کاربر موردنظر ریپلای بزنید.")
        return
    target  = update.message.reply_to_message.from_user
    chat_id = update.message.chat_id

    if context.args:
        try:
            minutes = max(1, int(context.args[0]))
        except ValueError:
            minutes = await mod._next_mute_minutes(target.id, chat_id)
    else:
        minutes = await mod._next_mute_minutes(target.id, chat_id)

    duration_lbl = mod._format_minutes(minutes)
    await mod._mute(context.bot, chat_id, target.id, minutes=minutes)
    await db.add_punishment(target.id, chat_id, "mute", minutes * 60, "میوت دستی ادمین")
    await mod.apply_mute_tag(context.bot, chat_id, target.id, duration_lbl)
    await update.message.reply_text(
        f"🔇 {mention(target)} به مدت *{duration_lbl}* میوت شد.",
        parse_mode="HTML",
    )


# ─── /unmute ─────────────────────────────────────────────────────────────────

async def cmd_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("روی پیام کاربر موردنظر ریپلای بزنید.")
        return
    target  = update.message.reply_to_message.from_user
    chat_id = update.message.chat_id
    all_perms = ChatPermissions(
        can_send_messages=True, can_send_audios=True,
        can_send_documents=True, can_send_photos=True,
        can_send_videos=True, can_send_voice_notes=True,
        can_send_polls=True, can_send_other_messages=True,
    )
    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id, user_id=target.id, permissions=all_perms
        )
    except Exception as e:
        logger.warning(f"unmute ناموفق: {e}")
    warns = await db.get_warnings(target.id, chat_id)
    await mod.apply_warn_tag(context.bot, chat_id, target.id, warns)
    await update.message.reply_text(
        f"🔊 میوت {mention(target)} برداشته شد.", parse_mode="HTML"
    )


# ─── /ban ────────────────────────────────────────────────────────────────────

async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /ban              → بن پلکانی
    /ban 30m          → ۳۰ دقیقه
    /ban 2h           → ۲ ساعت
    /ban 7d           → ۷ روز
    /ban 1h دلیل      → با دلیل
    """
    if not _is_admin(update.message.from_user.id):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "روی پیام کاربر موردنظر ریپلای بزنید.\n"
            "مثال: /ban 1h اسپم  یا  /ban  (پلکانی)"
        )
        return

    target  = update.message.reply_to_message.from_user
    chat_id = update.message.chat_id
    reason  = "تخلف"
    until_date   = None
    duration_txt = "دائم"

    args = list(context.args)
    if args:
        seconds = parse_duration(args[0])
        if seconds:
            until_date   = datetime.now(tz=timezone.utc) + timedelta(seconds=seconds)
            duration_txt = format_duration(seconds)
            args = args[1:]
        if args:
            reason = " ".join(args)
    else:
        days, duration_txt = await mod._next_ban_duration(target.id, chat_id)
        if days:
            until_date = datetime.now(tz=timezone.utc) + timedelta(days=days)

    await mod._ban(context.bot, chat_id, target.id, until_date=until_date)
    duration_secs = (
        int((until_date - datetime.now(tz=timezone.utc)).total_seconds())
        if until_date else -1
    )
    await db.add_punishment(target.id, chat_id, "ban", duration_secs, reason)

    if until_date:
        await update.message.reply_text(
            t("banned_temp", name=mention(target), duration=duration_txt, reason=reason),
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            t("banned", name=mention(target)), parse_mode="HTML"
        )


# ─── /unban ──────────────────────────────────────────────────────────────────

async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        return
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
    try:
        await context.bot.unban_chat_member(
            chat_id=update.message.chat_id, user_id=target_id, only_if_banned=True,
        )
        await update.message.reply_text(f"✅ کاربر {target_id} آنبن شد.")
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
