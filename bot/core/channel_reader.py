"""
خواندن مطالب کانال‌های public تلگرام با scraping نسخه‌ی وب.
راه‌حل بدون نیاز به API — فقط httpx و BeautifulSoup.

کاربرد: کانال‌های public (که یوزرنیم دارن) یه نسخه‌ی وب دارن:
    https://t.me/s/channelname
که می‌تونیم مطالبش رو از HTML استخراج کنیم.
"""

import re
import logging
import httpx

logger = logging.getLogger(__name__)

# cache موقت برای جلوگیری از درخواست تکراری
_last_sync: dict[str, int] = {}  # channel -> last message count


def _normalize_channel(channel: str) -> str:
    """تبدیل @channel یا لینک به نام کانال"""
    clean = channel.strip()
    if clean.startswith("https://t.me/"):
        clean = clean.split("/")[-1]
    if clean.startswith("@"):
        clean = clean[1:]
    # حذف کوئری‌استرینگ
    clean = clean.split("?")[0].split("/")[0]
    return clean


async def read_channel_messages(channel: str, limit: int = 100) -> list[dict]:
    """
    خواندن پیام‌های اخیر یک کانال public از نسخه‌ی وب t.me/s/
    برمی‌گردونه: list of {text, date, has_media, id}
    """
    clean = _normalize_channel(channel)
    if not clean:
        logger.warning(f"channel name empty after normalize: {channel}")
        return []

    url = f"https://t.me/s/{clean}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "fa,en;q=0.9",
    }

    try:
        # اول صفحه‌ی قبل رو بگیر (پیام‌های قدیمی‌تر)
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning(f"channel {clean}: HTTP {resp.status_code}")
                return []

            html = resp.text

        # parse با BeautifulSoup
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.error("beautifulsoup4 نصب نیست! pip install beautifulsoup4")
            return []

        soup = BeautifulSoup(html, "html.parser")
        messages = []

        # هر پیام تو div با class="tgme_widget_message_wrap" هست
        for wrap in soup.select(".tgme_widget_message_wrap"):
            try:
                msg_div = wrap.select_one(".tgme_widget_message")
                if not msg_div:
                    continue
                msg_id = msg_div.get("data-post", "").split("/")[-1]

                # متن پیام
                text_el = msg_div.select_one(".tgme_widget_message_text")
                text = text_el.get_text("\n", strip=True) if text_el else ""
                if not text or len(text) < 30:
                    continue

                # تاریخ
                date_el = msg_div.select_one(".tgme_widget_message_date")
                date = ""
                if date_el and date_el.find("time"):
                    date = date_el.find("time").get("datetime", "")

                # مدیا
                has_media = bool(
                    msg_div.select_one(
                        ".tgme_widget_message_photo, .tgme_widget_message_video, "
                        ".tgme_widget_message_document, .tgme_widget_message_video_player"
                    )
                )

                messages.append({
                    "id": msg_id,
                    "text": text,
                    "date": date,
                    "has_media": has_media,
                })
            except Exception as e:
                logger.debug(f"parse message failed: {e}")
                continue

        # ترتیب chronologic (قدیمی به جدید)
        messages.sort(key=lambda m: int(m["id"]) if m["id"].isdigit() else 0)

        # محدود کردن به limit (آخرین‌ها)
        if len(messages) > limit:
            messages = messages[-limit:]

        logger.info(f"📥 {len(messages)} پیام از @{clean} استخراج شد")
        return messages

    except httpx.ConnectError as e:
        logger.warning(f"channel {clean} connect failed (maybe filtered): {e}")
        return []
    except Exception as e:
        logger.warning(f"read_channel_messages {channel} failed: {e}")
        return []


async def close_client():
    """compatibility — چیزی برای بستن نیست"""
    pass
