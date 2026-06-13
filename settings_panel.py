"""
پنل تنظیمات از طریق تلگرام — فقط ادمین
دستور: /settings
"""

import os
import logging
from dotenv import set_key, dotenv_values
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from config import ADMIN_IDS

logger  = logging.getLogger(__name__)
ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")

# ── وضعیت مکالمه ────────────────────────────────────
WAIT_VALUE = 1   # منتظر مقدار جدید از کاربر


# ── خواندن مقدار فعلی از .env ────────────────────────
def _get(key: str, default: str = "—") -> str:
    vals = dotenv_values(ENV_PATH)
    return vals.get(key, default)


def _set(key: str, value: str):
    set_key(ENV_PATH, key, value)


# ── کیبورد اصلی ──────────────────────────────────────
def _main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🤖 AI Model",         callback_data="cfg_ai_model"),
            InlineKeyboardButton("⚠️ Max Warnings",     callback_data="cfg_max_warn"),
        ],
        [
            InlineKeyboardButton("🕐 Spam Window",      callback_data="cfg_spam_window"),
            InlineKeyboardButton("📨 Spam Limit",       callback_data="cfg_spam_max"),
        ],
        [
            InlineKeyboardButton("🎯 AI Confidence",    callback_data="cfg_min_conf"),
            InlineKeyboardButton("🔗 Ollama URL",       callback_data="cfg_ollama_url"),
        ],
        [
            InlineKeyboardButton("🌐 Bot Language",     callback_data="cfg_bot_lang"),
            InlineKeyboardButton("📊 Show Current",     callback_data="cfg_show"),
        ],
        [
            InlineKeyboardButton("❌ Close",            callback_data="cfg_close"),
        ],
    ])


def _current_settings() -> str:
    lang_label = "🇮🇷 Persian" if _get("BOT_LANG", "fa") == "fa" else "🇬🇧 English"
    return (
        "⚙️ *Current Settings:*\n\n"
        f"🤖 AI Model:         `{_get('AI_MODEL')}`\n"
        f"🔗 Ollama URL:       `{_get('OLLAMA_BASE_URL')}`\n"
        f"⚠️ Max Warnings:     `{_get('MAX_WARNINGS')}`\n"
        f"🕐 Spam Window:      `{_get('SPAM_TIME_WINDOW')} sec`\n"
        f"📨 Spam Limit:       `{_get('SPAM_MAX_MESSAGES')} msg`\n"
        f"🎯 AI Confidence:    `{_get('MIN_CONFIDENCE')}`\n"
        f"🌐 Bot Language:     {lang_label}\n"
        f"🧠 Learning:         `{_get('LEARNING_ENABLED')}`\n"
    )


# ── هندلر /settings ──────────────────────────────────
async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    await update.message.reply_text(
        "⚙️ *پنل تنظیمات ربات*\n"
        "یک مورد را برای تغییر انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=_main_keyboard(),
    )


# ── callback تنظیمات ─────────────────────────────────
async def on_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id not in ADMIN_IDS:
        return

    data = query.data

    if data == "cfg_close":
        await query.message.delete()
        return

    if data == "cfg_show":
        await query.edit_message_text(
            _current_settings(),
            parse_mode="HTML",
            reply_markup=_main_keyboard(),
        )
        return

    # نگه‌داری کلید در context برای مرحله بعد
    key_map = {
        "cfg_ai_model":    ("AI_MODEL",         "AI model name (e.g. llama3 / gemma2:2b)"),
        "cfg_max_warn":    ("MAX_WARNINGS",      "Max warnings before ban (number)"),
        "cfg_spam_window": ("SPAM_TIME_WINDOW",  "Spam detection window in seconds"),
        "cfg_spam_max":    ("SPAM_MAX_MESSAGES", "Max messages in spam window"),
        "cfg_min_conf":    ("MIN_CONFIDENCE",    "AI confidence threshold — 0.0 to 1.0"),
        "cfg_ollama_url":  ("OLLAMA_BASE_URL",   "Ollama server URL (e.g. http://localhost:11434)"),
        "cfg_bot_lang":    ("BOT_LANG",          "Bot language — fa (Persian) or en (English)"),
    }

    if data not in key_map:
        return

    env_key, description = key_map[data]
    current_val          = _get(env_key)
    context.user_data["settings_key"]  = env_key
    context.user_data["settings_msgid"] = query.message.message_id
    context.user_data["settings_chatid"] = query.message.chat_id

    await query.edit_message_text(
        f"✏️ *تغییر {description}*\n\n"
        f"مقدار فعلی: `{current_val}`\n\n"
        f"مقدار جدید را بنویسید یا /cancel برای انصراف:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ انصراف", callback_data="cfg_cancel")
        ]]),
    )
    return WAIT_VALUE


async def on_settings_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("settings_key", None)
    await query.edit_message_text(
        "⚙️ *پنل تنظیمات ربات*\nیک مورد را برای تغییر انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=_main_keyboard(),
    )
    return ConversationHandler.END


async def on_settings_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت مقدار جدید از کاربر"""
    if update.effective_user.id not in ADMIN_IDS:
        return ConversationHandler.END

    env_key = context.user_data.pop("settings_key", None)
    if not env_key:
        return ConversationHandler.END

    new_value = update.message.text.strip()

    # اعتبارسنجی
    error_msg = _validate(env_key, new_value)
    if error_msg:
        await update.message.reply_text(
            f"❌ {error_msg}\nدوباره مقدار را وارد کنید یا /cancel بزنید:",
            parse_mode="HTML",
        )
        context.user_data["settings_key"] = env_key
        return WAIT_VALUE

    # ذخیره در .env
    _set(env_key, new_value)

    # حذف پیام قدیمی و نمایش پنل جدید
    try:
        await update.message.delete()
        chat_id = context.user_data.pop("settings_chatid", None)
        msg_id  = context.user_data.pop("settings_msgid", None)
        if chat_id and msg_id:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=(
                    f"✅ *{env_key}* به `{new_value}` تغییر کرد\n\n"
                    "⚙️ پنل تنظیمات:\n"
                    "یک مورد را برای تغییر انتخاب کنید:"
                ),
                parse_mode="HTML",
                reply_markup=_main_keyboard(),
            )
    except Exception:
        await update.message.reply_text(
            f"✅ `{env_key}` = `{new_value}` ذخیره شد.\n\n"
            "⚠️ برای اعمال تغییرات ربات باید ری‌استارت شود:\n"
            "`sudo systemctl restart telegram-bot`",
            parse_mode="HTML",
        )

    logger.info(f"Setting {env_key} changed to '{new_value}' by user {update.effective_user.id}")
    return ConversationHandler.END


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("settings_key", None)
    await update.message.reply_text("❌ لغو شد.")
    return ConversationHandler.END


# ── اعتبارسنجی ───────────────────────────────────────
def _validate(key: str, value: str) -> str:
    """برمیگردونه پیام خطا یا رشته خالی اگه معتبر بود"""
    if key in ("MAX_WARNINGS", "SPAM_TIME_WINDOW", "SPAM_MAX_MESSAGES"):
        if not value.isdigit() or int(value) < 1:
            return "باید یک عدد مثبت باشد"
    elif key == "MIN_CONFIDENCE":
        try:
            v = float(value)
            if not (0.0 <= v <= 1.0):
                return "باید بین 0.0 و 1.0 باشد"
        except ValueError:
            return "باید یک عدد اعشاری باشد (مثلاً 0.60)"
    elif key == "OLLAMA_BASE_URL":
        if not value.startswith("http"):
            return "Must start with http:// or https://"
    elif key == "BOT_LANG":
        if value not in ("fa", "en"):
            return "Must be 'fa' (Persian) or 'en' (English)"
    return ""


# ── ساخت ConversationHandler ─────────────────────────
def build_settings_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(on_settings_callback, pattern=r"^cfg_(?!cancel|close|show)"),
        ],
        states={
            WAIT_VALUE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    on_settings_value,
                ),
                CommandHandler("cancel", cmd_cancel),
                CallbackQueryHandler(on_settings_cancel, pattern=r"^cfg_cancel$"),
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        per_message=False,
        per_chat=False,
        per_user=True,
    )
