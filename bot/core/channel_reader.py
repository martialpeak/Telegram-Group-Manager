"""
خواندن تاریخچه کانال‌ها با Telethon (User API).
نیاز به TELEGRAM_API_ID و TELEGRAM_API_HASH داره.

نکته مهم: Telethon نیازی به session لاگین شده نداره اگر کانال public باشه —
می‌تونه با bot token هم کار کنه (به‌عنوان bot، نه user).
"""

import logging
import asyncio

logger = logging.getLogger(__name__)

# کلاینت Telethon (lazy init)
_telethon_client = None


async def _get_client():
    """ساخت یا برگرداندن کلاینت Telethon"""
    global _telethon_client
    if _telethon_client is not None:
        return _telethon_client

    from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, TELEGRAM_BOT_TOKEN

    if not TELEGRAM_API_ID or not TELEGRAM_API_HASH:
        raise RuntimeError("TELEGRAM_API_ID یا TELEGRAM_API_HASH تنظیم نشده")

    from telethon import TelegramClient
    # استفاده از bot token — نیازی به شماره تلفن نیست
    session_name = "bot_session"
    client = TelegramClient(
        session_name,
        int(TELEGRAM_API_ID),
        TELEGRAM_API_HASH,
    )
    await client.start(bot_token=TELEGRAM_BOT_TOKEN)
    _telethon_client = client
    logger.info("✅ کلاینت Telethon راه‌اندازی شد")
    return client


async def read_channel_messages(channel: str, limit: int = 200) -> list[dict]:
    """
    خواندن پیام‌های اخیر یک کانال.
    channel: @username یا لینک
    برمی‌گردونه: list of {text, date, has_media, id}
    """
    try:
        client = await _get_client()
        # نرمال‌سازی channel
        clean = channel.strip()
        if clean.startswith("https://t.me/"):
            clean = "@" + clean.split("/")[-1]
        if not clean.startswith("@"):
            clean = "@" + clean

        messages = []
        async for msg in client.iter_messages(clean, limit=limit):
            # فقط پیام‌های متنی (نه مدیا، سرویس، فوروارد خالی)
            if msg.text and len(msg.text.strip()) > 30:
                messages.append({
                    "id": msg.id,
                    "text": msg.text,
                    "date": str(msg.date),
                    "has_media": bool(msg.media),
                })
        logger.info(f"📥 {len(messages)} پیام متنی از {clean} خوانده شد")
        return messages
    except Exception as e:
        logger.warning(f"read_channel_messages {channel} failed: {e}")
        return []


async def close_client():
    """بستن کلاینت هنگام shutdown"""
    global _telethon_client
    if _telethon_client is not None:
        try:
            await _telethon_client.disconnect()
        except Exception:
            pass
        _telethon_client = None
