"""
عملیات مدیریتی: اخطار، سکوت، بن، حذف پیام
سیستم مجازات پلکانی — هر بار تکرار، مجازات سنگین‌تر
سیستم بازبینی ادمین — AI پیشنهاد می‌ده، ادمین تأیید/رد می‌کنه
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from telegram import Bot, ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import TelegramError

from config import MAX_WARNINGS, ADMIN_IDS
from i18n import t
import bot.db.database as db

logger = logging.getLogger(__name__)

# ─── جداول پلکانی ────────────────────────────────────────────────────────────
# میوت: ۱۰m → ۳۰m → ۳h → ۲۴h → ۴۸h
MUTE_STEPS = [10, 30, 180, 1440, 2880]       # دقیقه
# بن موقت: ۱d → ۳d → ۷d → ۳۰d → دائم
BAN_STEPS_DAYS = [1, 3, 7, 30, None]         # None = دائم


def _mention(user) -> str:
    if user.username:
        return f"@{user.username}"
    name = user.full_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<a href="tg://user?id={user.id}">{name}</a>'

# ─── محاسبه مدت پلکانی ───────────────────────────────────────────────────────

async def _next_mute_minutes(user_id: int, chat_id: int) -> int:
    count = await db.get_punishment_count(user_id, chat_id, "mute")
    idx   = min(count, len(MUTE_STEPS) - 1)
    return MUTE_STEPS[idx]


async def _next_ban_duration(user_id: int, chat_id: int):
    """برمیگردونه: (days: int | None, label: str)"""
    count = await db.get_punishment_count(user_id, chat_id, "ban")
    idx   = min(count, len(BAN_STEPS_DAYS) - 1)
    days  = BAN_STEPS_DAYS[idx]
    if days is None:
        return None, "دائم"
    return days, f"{days} روز"


def _format_minutes(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} دقیقه"
    if minutes < 1440:
        return f"{minutes // 60} ساعت"
    return f"{minutes // 1440} روز"


# ─── تگ وضعیت ────────────────────────────────────────────────────────────────

async def _set_status_tag(bot: Bot, chat_id: int, user_id: int, tag: str):
    """
    setChatMemberTag — در Bot API 9.0 اضافه شد.
    python-telegram-bot 21.x هنوز wrapper ندارد، مستقیم HTTP می‌زنیم.
    """
    try:
        token = bot.token
        url   = f"https://api.telegram.org/bot{token}/setChatMemberTag"
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json={
                "chat_id": chat_id,
                "user_id": user_id,
                "tag":     tag,
            })
        data = resp.json()
        if not data.get("ok"):
            logger.warning(f"setChatMemberTag failed: {data.get('description')}")
    except Exception as e:
        logger.warning(f"setChatMemberTag exception برای {user_id}: {e}")


async def apply_warn_tag(bot: Bot, chat_id: int, user_id: int, warn_count: int):
    if warn_count <= 0:
        level = await db.get_user_level(user_id, chat_id)
        from bot.core.user_levels import get_config
        cfg = get_config(level)
        tag = cfg.tag if cfg.tag else "ساده"
    elif warn_count == 1:
        tag = "اخطار 1"
    elif warn_count == 2:
        tag = "اخطار 2"
    else:
        tag = f"اخطار {warn_count}"
    await _set_status_tag(bot, chat_id, user_id, tag)


async def apply_mute_tag(bot: Bot, chat_id: int, user_id: int, duration_label: str):
    await _set_status_tag(bot, chat_id, user_id, f"میوت {duration_label}")


# ─── اقدام مستقیم توهین (بدون بازبینی) ──────────────────────────────────────

async def _do_insult_action(
    bot: Bot, message, analysis: dict, user, chat_id: int, tag: str
) -> tuple[str | None, str | None]:
    """منطق اصلی اخطار/بن برای توهین — فقط وقتی ادمین قابل دسترس نیست"""
    warn_count = await db.add_warning(user.id, chat_id, analysis.get("reason", "توهین"))
    await db.add_points(user.id, chat_id, -5)

    if warn_count >= MAX_WARNINGS:
        days, label = await _next_ban_duration(user.id, chat_id)
        until = (datetime.now(tz=timezone.utc) + timedelta(days=days)) if days else None
        await _ban(bot, chat_id, user.id, until_date=until)
        await db.add_punishment(user.id, chat_id, "ban",
                                days * 86400 if days else -1, "repeated insult")
        await db.reset_warnings(user.id, chat_id)
        if days:
            return t("banned_temp", name=tag, duration=label, reason="repeated insult"), "HTML"
        return t("banned", name=tag), "HTML"

    await apply_warn_tag(bot, chat_id, user.id, warn_count)
    reply = t("warn_insult", name=tag, warn=warn_count, max=MAX_WARNINGS)
    await _notify_user(bot, user.id,
        f"⚠️ پیام شما در گروه حذف شد.\n"
        f"اخطار: {warn_count}/{MAX_WARNINGS}\n"
        f"دلیل: {analysis.get('reason','توهین')}"
    )
    return reply, "HTML"


# ─── اقدام مستقیم اسپم (بدون بازبینی) ───────────────────────────────────────

async def _do_spam_action(
    bot: Bot, message, analysis: dict, user, chat_id: int, tag: str
) -> tuple[str | None, str | None]:
    """منطق اصلی اخطار/میوت برای اسپم — فقط وقتی ادمین قابل دسترس نیست"""
    warn_count = await db.add_warning(user.id, chat_id, analysis.get("reason", "spam"))
    await db.add_points(user.id, chat_id, -5)

    if warn_count >= MAX_WARNINGS:
        days, label = await _next_ban_duration(user.id, chat_id)
        until = (datetime.now(tz=timezone.utc) + timedelta(days=days)) if days else None
        await _ban(bot, chat_id, user.id, until_date=until)
        await db.add_punishment(user.id, chat_id, "ban",
                                days * 86400 if days else -1, "repeated spam")
        await db.reset_warnings(user.id, chat_id)
        if days:
            return t("banned_temp", name=tag, duration=label, reason="repeated spam"), "HTML"
        return t("banned", name=tag), "HTML"

    minutes      = await _next_mute_minutes(user.id, chat_id)
    duration_lbl = _format_minutes(minutes)
    await _mute(bot, chat_id, user.id, minutes=minutes)
    await db.add_punishment(user.id, chat_id, "mute", minutes * 60, "spam")
    await apply_warn_tag(bot, chat_id, user.id, warn_count)
    await apply_mute_tag(bot, chat_id, user.id, duration_lbl)
    await _notify_user(bot, user.id,
        f"⚠️ پیام شما در گروه حذف شد و {duration_lbl} میوت شدید.\n"
        f"اخطار: {warn_count}/{MAX_WARNINGS}\n"
        f"دلیل: {analysis.get('reason','spam')}"
    )
    return (
        t("warn_spam", name=tag, warn=warn_count, max=MAX_WARNINGS)
        + f"\n🔇 <b>{duration_lbl}</b>",
        "HTML",
    )


# ─── هندلرهای اصلی با بازبینی ────────────────────────────────────────────────

async def handle_insult(bot: Bot, message, analysis: dict) -> tuple[str | None, str | None]:
    user, chat_id = message.from_user, message.chat_id
    msg_text = message.text or ""
    await _delete(bot, chat_id, message.message_id)
    await db.log_message(
        user.id, chat_id, user.username or "",
        user.full_name, msg_text, "insult",
        analysis.get("confidence", 1.0),
    )

    # ذخیره برای بازبینی
    review_id = await db.save_moderation_review(
        user_id=user.id, chat_id=chat_id,
        action="insult", message_text=msg_text[:500],
        ai_reason=analysis.get("reason", ""), confidence=analysis.get("confidence", 0),
    )

    tag = _mention(user)
    notified = False
    for admin_id in ADMIN_IDS:
        try:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "✅ درست بود",
                    callback_data=f"rev_approve_{review_id}_{user.id}_{chat_id}_insult",
                ),
                InlineKeyboardButton(
                    "❌ اشتباه بود",
                    callback_data=f"rev_reject_{review_id}_{user.id}_{chat_id}_insult",
                ),
            ]])
            await bot.send_message(
                chat_id=admin_id,
                text=(
                    f"🔍 <b>بازبینی تشخیص توهین</b>\n\n"
                    f"👤 کاربر: {tag}\n"
                    f"🤖 دلیل AI: {analysis.get('reason','')}\n"
                    f"📊 اطمینان: {analysis.get('confidence', 0):.0%}\n\n"
                    f"💬 پیام:\n<code>{msg_text[:300]}</code>\n\n"
                    "آیا تشخیص درست بود؟"
                ),
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            notified = True
        except Exception:
            pass

    if not notified:
        # هیچ ادمینی دریافت نکرد — اقدام مستقیم
        return await _do_insult_action(bot, message, analysis, user, chat_id, tag)

    return None, None


async def handle_spam(bot: Bot, message, analysis: dict) -> tuple[str | None, str | None]:
    user, chat_id = message.from_user, message.chat_id
    msg_text = message.text or ""
    await _delete(bot, chat_id, message.message_id)
    await db.log_message(
        user.id, chat_id, user.username or "",
        user.full_name, msg_text, "spam",
        analysis.get("confidence", 1.0),
    )

    # ذخیره برای بازبینی
    review_id = await db.save_moderation_review(
        user_id=user.id, chat_id=chat_id,
        action="spam", message_text=msg_text[:500],
        ai_reason=analysis.get("reason", ""), confidence=analysis.get("confidence", 0),
    )

    tag = _mention(user)
    notified = False
    for admin_id in ADMIN_IDS:
        try:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "✅ درست بود",
                    callback_data=f"rev_approve_{review_id}_{user.id}_{chat_id}_spam",
                ),
                InlineKeyboardButton(
                    "❌ اشتباه بود",
                    callback_data=f"rev_reject_{review_id}_{user.id}_{chat_id}_spam",
                ),
            ]])
            await bot.send_message(
                chat_id=admin_id,
                text=(
                    f"🔍 <b>بازبینی تشخیص اسپم</b>\n\n"
                    f"👤 کاربر: {tag}\n"
                    f"🤖 دلیل AI: {analysis.get('reason','')}\n"
                    f"📊 اطمینان: {analysis.get('confidence', 0):.0%}\n\n"
                    f"💬 پیام:\n<code>{msg_text[:300]}</code>\n\n"
                    "آیا تشخیص درست بود؟"
                ),
                parse_mode="HTML",
                reply_markup=keyboard,
            )
            notified = True
        except Exception:
            pass

    if not notified:
        # هیچ ادمینی دریافت نکرد — اقدام مستقیم
        return await _do_spam_action(bot, message, analysis, user, chat_id, tag)

    return None, None


async def handle_level_violation(bot: Bot, message, violation: str) -> tuple[str, str]:
    """
    تخلف سطحی — پیام حذف و اطلاع‌رسانی می‌شه (بدون اخطار/میوت).
    پیام اطلاع‌رسانی بعد از ۱۰ دقیقه پاک میشه.
    """
    user, chat_id = message.from_user, message.chat_id
    await _delete(bot, chat_id, message.message_id)
    tag  = _mention(user)
    text = f"ℹ️ {tag}، پیام حذف شد: {violation}"
    sent = await bot.send_message(chat_id, text, parse_mode="HTML")

    # پیام اطلاع‌رسانی بعد از ۱۰ دقیقه پاک می‌شه — از task امن استفاده کن
    asyncio.ensure_future(_delete_after(bot, chat_id, sent.message_id, 600))
    await _notify_user(bot, user.id,
        f"ℹ️ پیام شما در گروه حذف شد.\nدلیل: {violation}"
    )
    return text, "HTML"


async def _delete_after(bot: Bot, chat_id: int, msg_id: int, delay: int):
    """بعد از delay ثانیه پیام رو پاک کن — coroutine امن برای schedule"""
    await asyncio.sleep(delay)
    await _delete(bot, chat_id, msg_id)


async def _notify_user(bot: Bot, user_id: int, text: str):
    """ارسال پیام به PV کاربر — اگه نشد، نادیده بگیر"""
    try:
        await bot.send_message(chat_id=user_id, text=text)
    except Exception:
        pass  # کاربر ربات رو بلاک کرده یا start نزده


# ─── عملیات پایه ─────────────────────────────────────────────────────────────

async def _delete(bot: Bot, chat_id: int, msg_id: int):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=msg_id)
    except TelegramError as e:
        logger.warning(f"حذف پیام ناموفق: {e}")


async def _ban(bot: Bot, chat_id: int, user_id: int, until_date=None):
    try:
        await bot.ban_chat_member(
            chat_id=chat_id, user_id=user_id, until_date=until_date
        )
        mode = f"تا {until_date}" if until_date else "دائم"
        logger.info(f"بن ({mode}): user={user_id} chat={chat_id}")
    except TelegramError as e:
        logger.error(f"بن ناموفق: {e}")


async def _mute(bot: Bot, chat_id: int, user_id: int, minutes: int = 10):
    await db.add_points(user_id, chat_id, -10)  # میوت
    until = datetime.now(tz=timezone.utc) + timedelta(minutes=minutes)
    no_send = ChatPermissions(
        can_send_messages=False,
        can_send_audios=False,
        can_send_documents=False,
        can_send_photos=False,
        can_send_videos=False,
        can_send_voice_notes=False,
        can_send_polls=False,
        can_send_other_messages=False,
    )
    try:
        await bot.restrict_chat_member(
            chat_id=chat_id, user_id=user_id,
            permissions=no_send, until_date=until,
        )
    except TelegramError as e:
        logger.error(f"سکوت ناموفق: {e}")
