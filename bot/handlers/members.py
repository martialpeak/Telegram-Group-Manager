"""
هندلرهای ورود و خروج اعضا
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import ADMIN_IDS
import bot.db.database as db
from bot.core.user_levels import get_config, level_label
from bot.utils.helpers import send_and_delete
from i18n import t

logger = logging.getLogger(__name__)


def _is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


async def on_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
    for member in message.new_chat_members:
        if member.is_bot:
            continue

        chat_id = message.chat_id

        # ── ست کردن تگ سطح فعلی کاربر ──────────────────────────────────────
        level = await db.get_user_level(member.id, chat_id)
        cfg   = get_config(level)
        from bot.core.moderation import _set_status_tag
        if level != "simple":
            await _set_status_tag(context.bot, chat_id, member.id, cfg.tag)

        # ── کیبورد خوش‌آمدگویی ────────────────────────────────────────────
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(t("rules_btn"), callback_data="rules"),
            InlineKeyboardButton(t("rank_btn"),  callback_data=f"myrank_{member.id}"),
        ]])

        await send_and_delete(
            message,
            t("welcome", name=member.full_name),
            delay=60,
            reply_markup=keyboard,
        )


async def on_left_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.left_chat_member:
        return
    member = message.left_chat_member
    if member.is_bot:
        return

    chat_id = message.chat_id

    # ── کیبورد بن سریع — فقط برای ادمین‌ها (مخفی براشون) ─────────────────
    # وقتی ادمین روی این پیام کلید بن رو بزنه، کاربر خارج‌شده بن می‌شه
    # تا نتونه برگرده
    keyboard = None
    if ADMIN_IDS:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                t("ban_btn"),
                callback_data=f"qban_{member.id}",
            ),
        ]])

    await send_and_delete(
        message,
        t("left_notify", name=member.full_name, user_id=member.id),
        delay=120,
        reply_markup=keyboard,
    )


async def on_quick_ban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    بن سریع کاربر از طریق کلید روی پیام خروج.
    pattern: qban_<user_id>
    فقط ادمین می‌تونه استفاده کنه.
    """
    query = update.callback_query

    if not _is_admin(query.from_user.id):
        await query.answer(t("ban_done_admin"), show_alert=True)
        return

    data = query.data
    try:
        user_id = int(data.split("_")[1])
    except (IndexError, ValueError):
        await query.answer("داده نامعتبر.", show_alert=True)
        return

    chat_id = query.message.chat_id

    # بن دائم
    from bot.core import moderation as mod
    await mod._ban(context.bot, chat_id, user_id, until_date=None)
    await db.add_punishment(user_id, chat_id, "ban", -1, "بن از پیام خروج")

    await query.answer("🚫 بن شد.", show_alert=False)
    try:
        # اگه پیام روی message log هست، reference بگیر
        left_msg = query.message
        left_name = "کاربر"
        # متن پیام رو parse کن تا اسم کاربر رو دربیاریم
        import re
        text = left_msg.text or left_msg.caption or ""
        m = re.search(r"<b>(.+?)</b>", text)
        if m:
            left_name = m.group(1)

        await query.edit_message_text(
            t("ban_done", name=left_name) + f"\n🆔 <code>{user_id}</code>",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"quick ban edit message failed: {e}")
