"""
توابع کمکی مشترک
"""

import asyncio
import logging
from telegram import Message

logger = logging.getLogger(__name__)


def _escape_html(text: str) -> str:
    """escape کاراکترهای HTML برای استفاده داخل parse_mode=HTML"""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def safe_mention(user) -> str:
    """
    mention امن با HTML parse — همیشه escape شده.
    اگه username داشت: @username
    وگرنه: <a href="tg://user?id=...">اسم escape شده</a>
    """
    if user.username:
        return f"@{user.username}"
    name = _escape_html(getattr(user, "full_name", "") or "کاربر")
    return f'<a href="tg://user?id={user.id}">{name}</a>'


def mention(user) -> str:
    """
    تگ واقعی کاربر — فرمت HTML:
    - اگه username داشت: @username
    - اگه نداشت: inline mention با HTML
    """
    return safe_mention(user)


def escape_html(text) -> str:
    """wrapper عمومی برای escape رشته‌های دلخواه"""
    return _escape_html(str(text) if text is not None else "")


async def send_and_delete(
    chat_or_message,
    text: str,
    delay: int = 30,
    parse_mode: str = "HTML",
    reply_markup=None,
):
    """
    پیام ارسال میکنه و بعد از delay ثانیه خودکار پاکش میکنه.
    """
    if hasattr(chat_or_message, "reply_text"):
        sent = await chat_or_message.reply_text(
            text, parse_mode=parse_mode, reply_markup=reply_markup
        )
        chat_id = chat_or_message.chat_id
    else:
        sent = await chat_or_message.send_message(
            text, parse_mode=parse_mode, reply_markup=reply_markup
        )
        chat_id = chat_or_message.id

    async def _delete_later():
        await asyncio.sleep(delay)
        try:
            bot = sent.get_bot()
            await bot.delete_message(chat_id=chat_id, message_id=sent.message_id)
        except Exception:
            pass

    asyncio.ensure_future(_delete_later())
    return sent


def is_addressing_bot(message: Message, bot_username: str) -> bool:
    """
    بررسی اینکه پیام خطاب به ربات هست یا نه.
    ۱. mention مستقیم: @botname در متن — همیشه فعال
    ۲. ریپلای روی پیام ربات — تقریباً همیشه جواب بده (مگر تعارفات خالص)
    """
    import re
    text = (message.text or message.caption or "").strip()

    # منشن مستقیم — همیشه فعال
    if f"@{bot_username}" in text:
        return True

    # ریپلای روی پیام ربات
    if not (
        message.reply_to_message
        and message.reply_to_message.from_user
        and message.reply_to_message.from_user.username == bot_username
    ):
        return False

    clean = re.sub(r"\s+", " ", text).strip()

    # خالی — رد کن
    if not clean:
        return False

    # فقط ایموجی یا علامت — رد کن
    if len(clean.replace(" ", "")) < 2:
        return False

    # پیام‌های تک‌کلمه‌ای تعارفی خالص — رد کن
    _GREETINGS_ONLY = re.compile(
        r"^(ممنون|مرسی|تشکر|اوکی|ok|okay|thanks|thank\s?you|"
        r"👍|👎|❤️|😊|🙏|👌|✅|❌|ارادت|نه|آره|بله|عالی|باشه|خوب|بسیار)$",
        re.IGNORECASE,
    )
    if _GREETINGS_ONLY.match(clean):
        return False

    # هر پیام دیگه که ریپلای روی ربات باشه → جواب بده
    # (آسان‌گیرتر شد — قبلاً شرط طول/کلمه داشت که خیلی سخت‌گیرانه بود)
    return True


def build_vote_keyboard(fb_id: int, ups: int, downs: int):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(f"👍 {ups}",   callback_data=f"vote_up_{fb_id}"),
        InlineKeyboardButton(f"👎 {downs}", callback_data=f"vote_dn_{fb_id}"),
    ]])


def parse_duration(raw: str) -> int:
    """تبدیل رشته مدت (30m، 2h، 7d) به ثانیه. 0 اگه فرمت نامعتبر."""
    import re
    m = re.fullmatch(r"(\d+)([mhd])", raw.lower())
    if not m:
        return 0
    val, unit = int(m.group(1)), m.group(2)
    return val * {"m": 60, "h": 3600, "d": 86400}[unit]


def format_duration(seconds: int) -> str:
    if seconds < 3600:
        return f"{seconds // 60} دقیقه"
    if seconds < 86400:
        return f"{seconds // 3600} ساعت"
    return f"{seconds // 86400} روز"
