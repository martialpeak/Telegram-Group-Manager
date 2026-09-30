"""
سیستم استعلام و اطلاع‌رسانی اخبار فناوری، هوش مصنوعی، VPN و بازی‌های رایگان
شامل تبدیل تاریخ میلادی مهلت‌های دریافت به تقویم شمسی به وقت تهران
"""

import html
import asyncio
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


# ─── موتور ترجمه هوشمند اخبار و فیدهای خبری بین‌المللی ───────────────────────

_translation_cache: dict[str, str] = {}


async def translate_to_persian(text: str) -> str:
    """ترجمه متن انگلیسی اخبار به فارسی روان (ترکیب هوش مصنوعی و مترجم ابری)"""
    if not text or not text.strip():
        return ""
    clean = html.unescape(text.strip())
    if clean in _translation_cache:
        return _translation_cache[clean]

    # ۱. تلاش با ماژول هوش مصنوعی سیستم در صورت فعال بودن
    try:
        from bot.core.ai_analyzer import translate_text
        ai_res = await asyncio.wait_for(translate_text(clean, "فارسی"), timeout=3.0)
        if ai_res and len(ai_res.strip()) > 3:
            _translation_cache[clean] = ai_res.strip()
            return ai_res.strip()
    except Exception:
        pass

    # ۲. فال‌بک سریع وب‌سرویس گوگل ترنسلیت
    try:
        url = "https://translate.googleapis.com/translate_a/single"
        params = {
            "client": "gtx",
            "sl": "en",
            "tl": "fa",
            "dt": "t",
            "q": clean,
        }
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data and isinstance(data, list) and data[0]:
                    translated = "".join(part[0] for part in data[0] if part and part[0]).strip()
                    if translated:
                        _translation_cache[clean] = translated
                        return translated
    except Exception as e:
        logger.warning(f"Google translate fallback failed: {e}")

    return clean


async def _fetch_single_feed(client: httpx.AsyncClient, name: str, url: str, is_foreign: bool, default_tag: str) -> list[dict]:
    """دریافت و استخراج خبر از یک فید RSS یا Atom"""
    try:
        resp = await client.get(url)
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.text)
        items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry") or root.findall(".//entry")
        feed_items = []
        for it in items[:8]:
            title = it.findtext("title") or it.findtext("{http://www.w3.org/2005/Atom}title") or ""
            title = html.unescape(" ".join(title.strip().split()))
            link_node = it.find("{http://www.w3.org/2005/Atom}link")
            link = ""
            if link_node is not None:
                link = link_node.attrib.get("href", "")
            if not link:
                link = it.findtext("link") or ""

            desc = it.findtext("description") or it.findtext("{http://www.w3.org/2005/Atom}summary") or it.findtext("{http://www.w3.org/2005/Atom}content") or ""
            clean_desc = re.sub(r"<[^>]+>", " ", desc or "").strip()
            clean_desc = html.unescape(" ".join(clean_desc.split()))[:140]

            pub_date = it.findtext("pubDate") or it.findtext("{http://www.w3.org/2005/Atom}published") or it.findtext("{http://www.w3.org/2005/Atom}updated") or ""

            if title:
                feed_items.append({
                    "title": title,
                    "link": link,
                    "desc": clean_desc,
                    "pub_date": pub_date,
                    "source": name,
                    "is_foreign": is_foreign,
                    "tag": default_tag,
                })
        return feed_items
    except Exception as e:
        logger.warning(f"Error fetching feed {name}: {e}")
        return []


async def get_tech_news(category: str | None = None, limit: int = 5) -> list[dict]:
    """
    دریافت اخبار فناوری، هوش مصنوعی و اینترنت/VPN از سایت‌های معتبر خارجی و داخلی به همراه ترجمه هوشمند
    category: None (همه), 'ai' (هوش مصنوعی), 'vpn' (وی‌پی‌ان و امنیت), 'foreign' (فقط رسانه‌های خارجی), 'domestic' (داخلی)
    """
    feeds_config = [
        # رسانه‌های معتبر خارجی
        ("The Verge", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", True, "🤖 هوش مصنوعی"),
        ("TechCrunch", "https://techcrunch.com/category/artificial-intelligence/feed/", True, "🤖 هوش مصنوعی"),
        ("The Hacker News", "https://feeds.feedburner.com/TheHackersNews", True, "🛡️ اینترنت و VPN"),
        ("Wired", "https://www.wired.com/feed/category/security/latest/rss", True, "🛡️ اینترنت و VPN"),
        ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", True, "💻 فناوری"),
        # رسانه‌های معتبر داخلی
        ("زومیت", "https://www.zoomit.ir/feed/", False, "💻 فناوری"),
        ("دیجیاتو", "https://digiato.com/feed", False, "💻 فناوری"),
    ]

    ai_keywords = [
        "هوش مصنوعی", "چت جی پی تی", "gpt", "gemini", "جمنای", "جمینی",
        "open ai", "openai", "deepmind", "کلود", "claude", "llm", "مدل هوش مصنوعی", "ابرهوش",
        "deepseek", "anthropic", "artificial intelligence", "copilot", "reasoning model", "sora"
    ]
    vpn_keywords = [
        "vpn", "وی پی ان", "فیلتر", "فیلترینگ", "اینترنت", "پروکسی", "proxy",
        "آزادی اینترنت", "محدودیت اینترنت", "سایبر", "امنیت", "حریم خصوصی", "بدافزار",
        "censorship", "firewall", "cybersecurity", "exploit", "cve-", "malware", "zero-day",
        "breach", "ransomware", "backdoor", "encryption", "surveillance"
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    }

    raw_items = []
    async with httpx.AsyncClient(timeout=8, follow_redirects=True, headers=headers) as client:
        fetch_tasks = [
            _fetch_single_feed(client, name, url, is_foreign, def_tag)
            for name, url, is_foreign, def_tag in feeds_config
        ]
        results = await asyncio.gather(*fetch_tasks)
        for r in results:
            raw_items.extend(r)

    # برچسب‌گذاری دقیق موضوعی
    filtered_items = []
    for item in raw_items:
        t_lower = item["title"].lower()
        d_lower = item["desc"].lower()

        tag = item["tag"]
        if any(k in t_lower or k in d_lower for k in ai_keywords):
            tag = "🤖 هوش مصنوعی"
        elif any(k in t_lower or k in d_lower for k in vpn_keywords):
            tag = "🛡️ اینترنت و VPN"

        item["tag"] = tag

        # فیلتر بر اساس دسته‌بندی درخواستی
        if category == "ai" and tag != "🤖 هوش مصنوعی":
            continue
        if category == "vpn" and tag != "🛡️ اینترنت و VPN":
            continue
        if category == "foreign" and not item["is_foreign"]:
            continue
        if category in ("domestic", "iran") and item["is_foreign"]:
            continue

        filtered_items.append(item)

    # اولویت‌بندی هوشمند: تنوع منابع و ترجیح اخبار مهم
    if not category:
        # در حالت کلی: اخبار هوش مصنوعی و اینترنت/VPN اولویت بالاتر دارند
        filtered_items.sort(key=lambda x: (x["tag"] != "🤖 هوش مصنوعی", x["tag"] != "🛡️ اینترنت و VPN"))

    # انتخاب آیتم‌های برتر با حذف موارد کاملاً مشابه
    selected = []
    seen_titles = set()
    for it in filtered_items:
        key = it["title"][:25].lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        selected.append(it)
        if len(selected) >= limit:
            break

    # ترجمه هم‌زمان به زبان فارسی برای اخبار خارجی انتخاب‌شده
    async def _translate_entry(item: dict) -> dict:
        if item.get("is_foreign"):
            orig_t = item["title"]
            fa_title = await translate_to_persian(orig_t)
            fa_desc = await translate_to_persian(item["desc"]) if item["desc"] else ""
            item["orig_title"] = orig_t
            item["title"] = fa_title
            item["desc"] = fa_desc
            item["is_translated"] = True
        return item

    if selected:
        selected = list(await asyncio.gather(*[_translate_entry(it) for it in selected]))

    return selected


def format_tech_news_message(news: list[dict], category: str | None = None) -> tuple[str, InlineKeyboardMarkup]:
    """قالب‌بندی اخبار فناوری و AI جهت نمایش در گروه با ترجمه فارسی"""
    if not news:
        text = "📰 <b>در حال حاضر خبر جدیدی در این بخش یافت نشد!</b>"
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔄 تلاش مجدد", callback_data="news_cat_all")]])
        return text, kb

    cat_titles = {
        "ai": "🤖 تازه‌ترین اخبار هوش مصنوعی جهان (AI)",
        "vpn": "🛡️ اخبار اینترنت، فیلترینگ و امنیت سایبری",
        "foreign": "🌐 گزیده اخبار معتبرترین رسانه‌های خارجی (ترجمه‌شده)",
        "domestic": "🇮🇷 اخبار برگزیده تکنولوژی ایران",
    }
    header_title = cat_titles.get(category, "📰 تازه‌ترین اخبار فناوری، هوش مصنوعی و اینترنت جهان:")

    lines = [
        f"<b>{header_title}</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━\n",
    ]

    for i, n in enumerate(news):
        lines.append(f"📌 <b>{i+1}. {n['title']}</b>")
        if n.get("is_foreign") and n.get("orig_title"):
            lines.append(f"<i>🌐 تیتر اصلی: {n['orig_title']}</i>")
        lines.append("<blockquote>")
        if n["desc"]:
            lines.append(f"📝 {n['desc']}...")
        source_badge = f"🌐 {n['source']} (ترجمه هوشمند)" if n.get("is_foreign") else f"🇮🇷 {n['source']}"
        lines.append(f"🏷 <i>دسته‌بندی: {n['tag']} | منبع: {source_badge}</i>\n🔗 <a href=\"{n['link']}\">مطالعه متن کامل خبر</a>")
        lines.append("</blockquote>\n")

    lines.append("🌐 <i>اطلاع‌رسانی لحظه‌ای رویدادهای مهم تکنولوژی جهان</i>")

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🤖 هوش مصنوعی (AI)", callback_data="news_cat_ai"),
            InlineKeyboardButton("🛡️ اینترنت و VPN", callback_data="news_cat_vpn"),
        ],
        [
            InlineKeyboardButton("🌐 رسانه‌های خارجی (ترجمه)", callback_data="news_cat_foreign"),
            InlineKeyboardButton("🇮🇷 رسانه‌های داخلی", callback_data="news_cat_domestic"),
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
