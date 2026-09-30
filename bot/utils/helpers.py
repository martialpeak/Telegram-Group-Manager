"""
توابع کمکی مشترک
"""

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from html import escape as _html_escape

from telegram import Update, Message
from telegram.ext import ContextTypes


def esc(text: str) -> str:
    """escape HTML special characters for Telegram parse_mode=HTML"""
    return _html_escape(str(text))

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

    asyncio.create_task(_delete_later())
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


# ─── تقویم خورشیدی (جلالی/شمسی) و ساعت رسمی ایران ───────────────────────────

PERSIAN_WEEKDAYS = {
    0: "دوشنبه",
    1: "سه‌شنبه",
    2: "چهارشنبه",
    3: "پنج‌شنبه",
    4: "جمعه",
    5: "شنبه",
    6: "یکشنبه",
}

PERSIAN_MONTHS = [
    "",
    "فروردین", "اردیبهشت", "خرداد",
    "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر",
    "دی", "بهمن", "اسفند",
]

GREGORIAN_MONTHS_FA = [
    "",
    "ژانویه", "فوریه", "مارس",
    "آوریل", "مه", "ژوئن",
    "ژوئیه", "اوت", "سپتامبر",
    "اکتبر", "نوامبر", "دسامبر",
]


def to_persian_digits(val) -> str:
    """تبدیل اعداد انگلیسی به فارسی"""
    en_to_fa = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
    return str(val).translate(en_to_fa)


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    """تبدیل دقیق تاریخ میلادی به خورشیدی (شمسی) بدون نیاز به کتابخانه جانبی"""
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 - 80 + gd + g_d_m[gm - 1]
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + (days % 31)
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + ((days - 186) % 30)
    return jy, jm, jd


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    """تبدیل معکوس تاریخ خورشیدی به میلادی"""
    if jy > 979:
        gy = 1600
        jy -= 979
    else:
        gy = 621
    days = (365 * jy) + ((jy // 33) * 8) + (((jy % 33) + 3) // 4) + 78 + jd + ((jm - 1) * 31 if jm < 7 else ((jm - 7) * 30) + 186)
    gy += 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    sal_a = [0, 31, 29 if ((gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    gm = 0
    while gm < 13 and days >= sal_a[gm]:
        days -= sal_a[gm]
        gm += 1
    gd = days + 1
    return gy, gm, gd


def get_tehran_now() -> datetime:
    """دریافت زمان کنونی به وقت رسمی ایران (UTC+03:30 ثابت)"""
    tz = timezone(timedelta(hours=3, minutes=30))
    return datetime.now(tz)


def get_persian_date_info(dt: datetime = None) -> dict:
    """محاسبه کامل اطلاعات تقویم و ساعت به وقت تهران"""
    if dt is None:
        dt = get_tehran_now()
    jy, jm, jd = gregorian_to_jalali(dt.year, dt.month, dt.day)
    weekday_name = PERSIAN_WEEKDAYS[dt.weekday()]
    month_name = PERSIAN_MONTHS[jm]
    time_str = dt.strftime("%H:%M")
    time_fa = to_persian_digits(time_str)
    date_fa_num = f"{jy:04d}/{jm:02d}/{jd:02d}"
    date_fa_full = f"{weekday_name}، {to_persian_digits(jd)} {month_name} {to_persian_digits(jy)}"
    g_weekday_name = dt.strftime("%A")
    g_month_name = dt.strftime("%B")
    g_month_fa = GREGORIAN_MONTHS_FA[dt.month] if 1 <= dt.month <= 12 else g_month_name
    date_g_fa = f"{dt.day} {g_month_fa} {dt.year} ({dt.strftime('%Y-%m-%d')})"
    date_g_full = f"{g_weekday_name}, {dt.day} {g_month_name} {dt.year}"

    return {
        "jy": jy,
        "jm": jm,
        "jd": jd,
        "weekday_name": weekday_name,
        "month_name": month_name,
        "time_str": time_str,
        "time_fa": time_fa,
        "date_fa_num": date_fa_num,
        "date_fa_full": date_fa_full,
        "g_weekday_name": g_weekday_name,
        "g_month_name": g_month_name,
        "g_month_fa": g_month_fa,
        "date_g_fa": date_g_fa,
        "date_g_full": date_g_full,
    }


def is_datetime_query(question: str) -> bool:
    """
    تشخیص اینکه آیا سوال در مورد تاریخ، روز هفته، یا ساعت کنونی است یا نه
    """
    if not question:
        return False
    q = question.lower().strip()
    if len(q) < 3:
        return False

    # فیلتر موارد غیرمرتبط مثل ساعت مچی یا کالاهای خرید
    product_filters = [
        "ساعت هوشمند", "ساعت مچی", "خرید ساعت", "قیمت ساعت", "تعمیر ساعت",
        "بند ساعت", "مارک ساعت", "ساعت دیواری", "ساعت رولکس", "ساعت کاسیو",
        "ساعت اپل", "ساعت شیائومی"
    ]
    if any(p in q for p in product_filters):
        return False

    # الگوهای تاریخ و روز هفته
    date_patterns = [
        r"امروز\s+چندم",
        r"چند\s*شنب",
        r"امروز\s+چه\s*روزی",
        r"امروز\s+چه\s*تاریخ",
        r"تاریخ\s+(امروز|الان|کنونی|روز|شمسی|میلادی)",
        r"امروز\s+چندمه",
        r"\bچندمه\b",
        r"چندمین\s+روز",
        r"امروز\s+چند\s*(م|ام)?\s*(ماه|برج)",
        r"روز\s+هفته\s+(چیه|چندمه|کدومه|چند\s*شنبه)",
        r"تقویم\s+امروز",
    ]
    for pat in date_patterns:
        if re.search(pat, q):
            return True

    # الگوهای ساعت و زمان لحظه‌ای
    time_patterns = [
        r"ساعت\s+(چنده|چند\s*است|چند\s*هست|دقیق)",
        r"الان\s+ساعت\s+چنده",
        r"ساعت\s+الان",
        r"ساعت\s+رسمی",
        r"ساعت\s+(به\s*وقت\s+)?تهران\s*(چنده|چند\s*است)?",
    ]
    for pat in time_patterns:
        if re.search(pat, q):
            return True

    return False


def get_datetime_response(question: str = "") -> str:
    """
    تولید پاسخ شکیل، دقیق و مستقیم به تاریخ و ساعت جاری ایران
    """
    info = get_persian_date_info()
    q = (question or "").lower()

    is_time_only = (
        any(w in q for w in ["ساعت چنده", "ساعت چند است", "ساعت چند هست", "الان ساعت چنده", "ساعت الان"])
        and not any(w in q for w in ["چندمه", "چندم", "شنبه", "تاریخ", "روز", "تقویم", "ماه"])
    )

    if is_time_only:
        return (
            f"⏰ ساعت رسمی کشور: <b>{info['time_fa']}</b>\n\n"
            "<blockquote>"
            f"🗓 <b>امروز:</b> {info['date_fa_full']}\n"
            f"🌐 <b>میلادی:</b> {info['date_g_full']}\n"
            f"🇮🇷 <b>ساعت تهران:</b> {info['time_fa']}  <code>({info['time_str']})</code>"
            "</blockquote>"
        )

    return (
        f"📅 امروز <b>{info['date_fa_full']}</b> است.\n\n"
        "<blockquote>"
        f"🗓 <b>روز هفته:</b> {info['weekday_name']}\n"
        f"☀️ <b>تاریخ خورشیدی:</b> {to_persian_digits(info['jd'])} {info['month_name']} {to_persian_digits(info['jy'])}  <code>({to_persian_digits(info['date_fa_num'])})</code>\n"
        f"🌐 <b>تاریخ میلادی:</b> {info['date_g_fa']}\n"
        f"⏰ <b>ساعت رسمی (تهران):</b> {info['time_fa']}  <code>({info['time_str']})</code>"
        "</blockquote>"
    )

