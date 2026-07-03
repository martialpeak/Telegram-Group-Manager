"""
هندلرهای ورود و خروج اعضا
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import ADMIN_IDS
import bot.db.database as db
from bot.core.user_levels import get_config, level_label
from bot.utils.helpers import send_and_delete, safe_mention, escape_html
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
        try:
            level = await db.get_user_level(member.id, chat_id)
            cfg = get_config(level)
            from bot.core.moderation import _set_status_tag
            if level != "simple":
                await _set_status_tag(context.bot, chat_id, member.id, cfg.tag)
        except Exception as e:
            logger.warning(f"set status tag for new member failed: {e}")

        # ── ثبت پروفایل کاربر در دیتابیس ───────────────────────────────────
        try:
            await db.upsert_user_profile(member, chat_id)
        except Exception as e:
            logger.warning(f"upsert profile failed: {e}")

        # ── ثبت رویداد ورود ────────────────────────────────────────────────
        try:
            await db.log_action(
                chat_id=chat_id, action="join", user_id=member.id,
                target_name=member.full_name,
            )
        except Exception:
            pass

        # ── کیبورد خوش‌آمدگویی ────────────────────────────────────────────
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(t("rules_btn"), callback_data="rules"),
            InlineKeyboardButton(t("rank_btn"),  callback_data=f"myrank_{member.id}"),
        ]])

        # از safe_mention استفاده می‌کنیم تا کاراکترهای HTML اسم خراب نکنن
        welcome_text = (
            f"👋 <b>{escape_html(member.full_name)}</b> عزیز، "
            f"به گروه خوش اومدی! 🎉\n\n"
            f"📌 برای صحبت با ربات منشنش کن یا روی پیامش ریپلای بزن."
        )
        try:
            await send_and_delete(
                message,
                welcome_text,
                delay=120,
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.error(f"welcome message send failed: {e}")


async def on_left_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.left_chat_member:
        return
    member = message.left_chat_member
    if member.is_bot:
        return

    chat_id = message.chat_id

    # ── ثبت رویداد خروج ────────────────────────────────────────────────────
    try:
        await db.log_action(
            chat_id=chat_id, action="leave", user_id=member.id,
            target_name=member.full_name,
        )
    except Exception:
        pass

    # ── کیبورد بن سریع — فقط برای ادمین‌ها ─────────────────────────────────
    keyboard = None
    if ADMIN_IDS:
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                t("ban_btn"),
                callback_data=f"qban_{member.id}",
            ),
        ]])

    # escape شده تا اسم کاربر HTML رو خراب نکنه
    left_text = (
        f"👋 <b>{escape_html(member.full_name)}</b> از گروه خارج شد.\n\n"
        f"🆔 شناسه: <code>{member.id}</code>"
    )
    try:
        await send_and_delete(
            message,
            left_text,
            delay=120,
            reply_markup=keyboard,
        )
    except Exception as e:
        logger.error(f"left message send failed: {e}")


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
    # ثبت رویداد بن
    try:
        await db.log_action(
            chat_id=chat_id, action="ban", user_id=user_id,
            actor_id=query.from_user.id,
            target_name=f"کاربر {user_id}", reason="بن از پیام خروج",
        )
    except Exception:
        pass

    await query.answer("🚫 بن شد.", show_alert=False)
    try:
        await query.edit_message_text(
            f"🚫 کاربر بن شد.\n🆔 <code>{user_id}</code>",
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"quick ban edit message failed: {e}")
