"""
هندلرهای ورود و خروج اعضا
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.utils.helpers import send_and_delete
from i18n import t

logger = logging.getLogger(__name__)


async def on_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
    for member in message.new_chat_members:
        if member.is_bot:
            continue
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
    await send_and_delete(
        message,
        t("left", name=member.full_name),
        delay=30,
    )
