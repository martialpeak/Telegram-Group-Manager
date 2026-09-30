"""
سیستم استعلام و اطلاع‌رسانی اخبار فناوری، هوش مصنوعی، VPN و بازی‌های رایگان
شامل تبدیل تاریخ میلادی مهلت‌های دریافت به تقویم شمسی به وقت تهران
"""

import logging
import re
from datetime import datetime, timezone, timedelta
import httpx
import xml.etree.ElementTree as ET
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.utils.helpers import gregorian_to_jalali, to_persian_digits, PERSIAN_MONTHS, PERSIAN_WEEKDAYS

logger = logging.getLogger(__name__)


def parse_date_to_shamsi(date_str: str | None) -> str:
    """تبدیل زمان انقضا/مهلت به تقویم شمسی به وقت تهران"""
    if not date_str or date_str in ("N/A", "Unknown", "", "None"):
        return "⏳ محدود / نامشخص (تا اتمام سهمیه عرضه)"

    clean = str(date_str).replace("Z", "+00:00").strip()
    dt = None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(clean, fmt)
            break
        except (ValueError, TypeError):
            pass

    if not dt:
        return f"⏳ {date_str}"

    # تبدیل به وقت رسمی ایران (UTC+03:30)
    tehran_tz = timezone(timedelta(hours=3, minutes=30))
    if dt.tzinfo:
        dt_tehran = dt.astimezone(tehran_tz)
    else:
        dt_tehran = dt.replace(tzinfo=timezone.utc).astimezone(tehran_tz)

    jy, jm, jd = gregorian_to_jalali(dt_tehran.year, dt_tehran.month, dt_tehran.day)
    w_name = PERSIAN_WEEKDAYS[dt_tehran.weekday()]
    m_name = PERSIAN_MONTHS[jm] if 1 <= jm <= 12 else ""
    time_fa = to_persian_digits(dt_tehran.strftime("%H:%M"))
    d_fa = to_persian_digits(str(jd))
    y_fa = to_persian_digits(str(jy))

    return f"🗓 {w_name}، {d_fa} {m_name} {y_fa} — ساعت {time_fa} (به وقت تهران)"


async def get_free_games(limit: int = 5) -> list[dict]:
    """
    دریافت بازی‌های ۱۰۰٪ رایگان و آفرهای معتبر برای کامپیوتر و گوشی
    از اپیک گیمز، استیم و پایگاه گیمرپاور
    """
    games = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    # ۱. استعلام از فروشگاه اپیک گیمز (Epic Games Store)
    try:
        epic_url = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions?locale=en-US&country=US&allowCountries=US"
        async with httpx.AsyncClient(timeout=8, follow_redirects=True, headers=headers) as client:
            resp = await client.get(epic_url)
            if resp.status_code == 200:
                data = resp.json()
                elements = data.get("data", {}).get("Catalog", {}).get("searchStore", {}).get("elements", [])
                for el in elements:
                    promos = el.get("promotions")
                    if promos:
                        offers = promos.get("promotionalOffers", [])
                        if offers:
                            offer_list = offers[0].get("promotionalOffers", [])
                            if offer_list and offer_list[0].get("discountSetting", {}).get("discountPercentage") == 0:
                                title = el.get("title", "")
                                slug = el.get("productSlug") or el.get("urlSlug") or ""
                                link = f"https://store.epicgames.com/p/{slug}" if slug else "https://store.epicgames.com/free-games"
                                orig_p = el.get("price", {}).get("totalPrice", {}).get("originalPrice", 0) / 100
                                end_d = offer_list[0].get("endDate")
                                games.append({
                                    "title": title,
                                    "platform": "💻 کامپیوتر (Epic Games)",
                                    "worth": f"${orig_p:.2f}" if orig_p else "پولی",
                                    "link": link,
                                    "end_date": end_d,
                                    "end_date_shamsi": parse_date_to_shamsi(end_d),
                                    "source": "Epic Games",
                                })
    except Exception as e:
        logger.warning(f"Epic Games freebies fetch error: {e}")

    # ۲. استعلام از پایگاه GamerPower (استیم، کامپیوتر، اندروید و iOS)
    try:
        gp_url = "https://www.gamerpower.com/api/giveaways?type=game&sort-by=popularity"
        async with httpx.AsyncClient(timeout=8, follow_redirects=True, headers=headers) as client:
            resp = await client.get(gp_url)
            if resp.status_code == 200:
                gp_list = resp.json()
                for item in gp_list:
                    if len(games) >= limit + 3:
                        break
                    plat = item.get("platforms", "")
                    plat_fa = "💻 کامپیوتر (PC)"
                    if "Android" in plat:
                        plat_fa = "📱 گوشی (Android)"
                    elif "iOS" in plat or "iPhone" in plat:
                        plat_fa = "🍏 گوشی (iOS)"
                    elif "Steam" in plat:
                        plat_fa = "🎮 کامپیوتر (Steam)"
                    elif "Playstation" in plat:
                        plat_fa = "🎮 پلی‌استیشن (PS)"
                    elif "Xbox" in plat:
                        plat_fa = "🎮 ایکس‌باکس (Xbox)"

                    title = item.get("title", "")
                    # جلوگیری از بازی‌های تکراری
                    if any(g["title"].lower() in title.lower() or title.lower() in g["title"].lower() for g in games):
                        continue

                    end_d = item.get("end_date")
                    link = item.get("open_giveaway_url") or item.get("gamerpower_url")
                    games.append({
                        "title": title,
                        "platform": plat_fa,
                        "worth": item.get("worth", "رایگان"),
                        "link": link,
                        "end_date": end_d,
                        "end_date_shamsi": parse_date_to_shamsi(end_d),
                        "source": plat,
                    })
    except Exception as e:
        logger.warning(f"GamerPower fetch error: {e}")

    return games[:limit]


def format_free_games_message(games: list[dict]) -> tuple[str, InlineKeyboardMarkup]:
    """قالب‌بندی کارت بازی‌های رایگان جهت ارسال در گروه یا منو"""
    if not games:
        text = "🎮 <b>در حال حاضر آفر رایگان فعالی در سرورها یافت نشد!</b>\nلطفاً ساعاتی دیگر مجدداً بررسی کنید."
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 بررسی مجدد", callback_data="game_refresh")]])
        return text, kb

    lines = [
        "🎁 <b>آفرهای ویژه و بازی‌های ۱۰۰٪ رایگان (کامپیوتر و موبایل):</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━\n",
    ]

    kb_buttons = []

    for i, g in enumerate(games):
        title = g["title"]
        plat = g["platform"]
        worth = g["worth"]
        deadline = g["end_date_shamsi"]
        link = g["link"]

        lines.append(f"🕹 <b>{i+1}. {title}</b>")
        lines.append("<blockquote>")
        lines.append(f"📱 <b>پلتفرم:</b> <b>{plat}</b>")
        lines.append(f"💰 <b>ارزش اصلی:</b> <b>{worth}</b> ➔ <b>۱۰۰٪ رایگان!</b>")
        lines.append(f"⏰ <b>مهلت دریافت:</b>\n   <b>{deadline}</b>")
        lines.append(f"🔗 <a href=\"{link}\">جهت دریافت رایگان اینجا کلیک کنید</a>")
        lines.append("</blockquote>\n")

        # دکمه مستقیم برای ۲ بازی اول
        if i < 2:
            short_t = title[:20] + "..." if len(title) > 20 else title
            kb_buttons.append([InlineKeyboardButton(f"📥 دریافت {short_t}", url=link)])

    lines.append("💡 <i>نکته: بازی‌ها پس از افزودن به اکانت شما، برای همیشه رایگان باقی می‌مانند.</i>")

    kb_buttons.append([
        InlineKeyboardButton("🔄 بروزرسانی بازی‌ها", callback_data="game_refresh"),
        InlineKeyboardButton("🔙 بازگشت به منو", callback_data="menu_main"),
    ])

    return "\n".join(lines), InlineKeyboardMarkup(kb_buttons)


async def get_tech_news(category: str | None = None, limit: int = 5) -> list[dict]:
    """
    دریافت اخبار فناوری، هوش مصنوعی و اینترنت/VPN
    category: None (همه), 'ai' (هوش مصنوعی), 'vpn' (وی‌پی‌ان و امنیت)
    """
    feeds = [
        ("زومیت", "https://www.zoomit.ir/feed/"),
        ("دیجیاتو", "https://digiato.com/feed"),
    ]

    ai_keywords = [
        "هوش مصنوعی", "چت جی پی تی", "gpt", "gemini", "جمنای", "جمینی",
        "open ai", "openai", "deepmind", "کلود", "claude", "llm", "مدل هوش مصنوعی", "ابرهوش"
    ]
    vpn_keywords = [
        "vpn", "وی پی ان", "فیلتر", "فیلترینگ", "اینترنت", "پروکسی", "proxy",
        "آزادی اینترنت", "محدودیت اینترنت", "سایبر", "امنیت", "حریم خصوصی", "بدافزار"
    ]

    items_list = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }

    async with httpx.AsyncClient(timeout=8, follow_redirects=True, headers=headers) as client:
        for source_name, url in feeds:
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    root = ET.fromstring(resp.text)
                    feed_items = root.findall(".//item")
                    for item in feed_items:
                        title = item.find("title").text if item.find("title") is not None else ""
                        link = item.find("link").text if item.find("link") is not None else ""
                        desc = item.find("description").text if item.find("description") is not None else ""
                        clean_desc = re.sub(r"<[^>]+>", " ", desc or "").strip()
                        clean_desc = " ".join(clean_desc.split())[:130]
                        pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""

                        t_lower = title.lower()
                        d_lower = clean_desc.lower()

                        tag = "💻 فناوری"
                        if any(k in t_lower or k in d_lower for k in ai_keywords):
                            tag = "🤖 هوش مصنوعی"
                        elif any(k in t_lower or k in d_lower for k in vpn_keywords):
                            tag = "🛡️ اینترنت و VPN"

                        if category == "ai" and tag != "🤖 هوش مصنوعی":
                            continue
                        if category == "vpn" and tag != "🛡️ اینترنت و VPN":
                            continue

                        items_list.append({
                            "title": title,
                            "link": link,
                            "desc": clean_desc,
                            "tag": tag,
                            "source": source_name,
                            "date": pub_date,
                        })
            except Exception as e:
                logger.warning(f"Error reading RSS from {source_name}: {e}")

    # اولویت‌بندی اخبار AI و VPN در صورت عدم تعیین دسته
    if not category:
        items_list.sort(key=lambda x: (x["tag"] != "🤖 هوش مصنوعی", x["tag"] != "🛡️ اینترنت و VPN"))

    return items_list[:limit]


def format_tech_news_message(news: list[dict], category: str | None = None) -> tuple[str, InlineKeyboardMarkup]:
    """قالب‌بندی اخبار فناوری و AI جهت نمایش در گروه"""
    if not news:
        text = "📰 <b>در حال حاضر خبر جدیدی در این بخش یافت نشد!</b>"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 تلاش مجدد", callback_data="news_cat_all")]])
        return text, kb

    cat_titles = {
        "ai": "🤖 اخبار ویژه هوش مصنوعی (AI)",
        "vpn": "🛡️ اخبار اینترنت، فیلترینگ و VPN",
    }
    header_title = cat_titles.get(category, "📰 تازه‌ترین اخبار هوش مصنوعی، اینترنت و تکنولوژی:")

    lines = [
        f"<b>{header_title}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━\n",
    ]

    for i, n in enumerate(news):
        lines.append(f"📌 <b>{i+1}. {n['title']}</b>")
        lines.append("<blockquote>")
        if n["desc"]:
            lines.append(f"📝 {n['desc']}...")
        lines.append(f"🏷 <i>دسته‌بندی: {n['tag']} | منبع: {n['source']}</i>\n🔗 <a href=\"{n['link']}\">مطالعه متن کامل خبر</a>")
        lines.append("</blockquote>\n")

    lines.append("🌐 <i>اطلاع‌رسانی بروزترین تحولات فناوری جهان</i>")

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🤖 فقط هوش مصنوعی", callback_data="news_cat_ai"),
            InlineKeyboardButton("🛡️ اخبار اینترنت/VPN", callback_data="news_cat_vpn"),
        ],
        [
            InlineKeyboardButton("💻 همه اخبار", callback_data="news_cat_all"),
            InlineKeyboardButton("🔄 بروزرسانی", callback_data=f"news_cat_{category or 'all'}"),
        ],
        [
            InlineKeyboardButton("🔙 بازگشت به منو", callback_data="menu_main"),
        ]
    ])

    return "\n".join(lines), kb
