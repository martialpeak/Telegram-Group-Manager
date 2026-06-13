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
            InlineKeyboardButton("🤖 Gemini Model",     callback_data="cfg_ai_model"),
            InlineKeyboardButton("🔑 Gemini API Key",   callback_data="cfg_gemini_key"),
        ],
        [
            InlineKeyboardButton("⚠️ Max Warnings",     callback_data="cfg_max_warn"),
            InlineKeyboardButton("🕐 Spam Window",      callback_data="cfg_spam_window"),
        ],
        [
            InlineKeyboardButton("📨 Spam Limit",       callback_data="cfg_spam_max"),
            InlineKeyboardButton("🎯 AI Confidence",    callback_data="cfg_min_conf"),
        ],
        [
            InlineKeyboardButton("🌐 Bot Language",     callback_data="cfg_bot_lang"),
            InlineKeyboardButton("📊 Show Current",     callback_data="cfg_show"),
        ],
        [
            InlineKeyboardButton("🏅 Level Limits",     callback_data="cfg_levels_menu"),
        ],
        [
            InlineKeyboardButton("❌ Close",            callback_data="cfg_close"),
        ],
    ])


def _current_settings() -> str:
    lang_label = "🇮🇷 Persian" if _get("BOT_LANG", "fa") == "fa" else "🇬🇧 English"
    key = _get("GEMINI_API_KEY", "")
    key_display = f"{key[:8]}..." if len(key) > 8 else ("تنظیم نشده" if not key else key)
    return (
        "⚙️ *Current Settings:*\n\n"
        f"🤖 Gemini Model:     `{_get('GEMINI_MODEL', 'gemini-2.5-flash')}`\n"
        f"🔑 Gemini API Key:   `{key_display}`\n"
        f"⚠️ Max Warnings:     `{_get('MAX_WARNINGS')}`\n"
        f"🕐 Spam Window:      `{_get('SPAM_TIME_WINDOW')} sec`\n"
        f"📨 Spam Limit:       `{_get('SPAM_MAX_MESSAGES')} msg`\n"
        f"🎯 AI Confidence:    `{_get('MIN_CONFIDENCE')}`\n"
        f"🌐 Bot Language:     {lang_label}\n"
        f"🧠 Learning:         `{_get('LEARNING_ENABLED')}`\n"
    )


def _levels_keyboard() -> InlineKeyboardMarkup:
    from bot.core.user_levels import LEVEL_ORDER
    rows = []
    for lv in LEVEL_ORDER:
        rows.append([InlineKeyboardButton(f"✏️ {lv}", callback_data=f"cfg_lv_{lv}")])
    rows.append([InlineKeyboardButton("🔙 برگشت", callback_data="cfg_back")])
    return InlineKeyboardMarkup(rows)


def _level_detail_keyboard(level: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("❓ سوال/روز",      callback_data=f"cfg_lv_{level}_queries"),
            InlineKeyboardButton("🔗 لینک/روز",      callback_data=f"cfg_lv_{level}_links"),
        ],
        [
            InlineKeyboardButton("↩️ فوروارد/روز",   callback_data=f"cfg_lv_{level}_forwards"),
            InlineKeyboardButton("📸 مجاز مدیا",     callback_data=f"cfg_lv_{level}_media"),
        ],
        [InlineKeyboardButton("🔙 برگشت", callback_data="cfg_levels_menu")],
    ])


def _level_summary_text(level: str) -> str:
    from bot.core.user_levels import LEVELS
    c = LEVELS[level]
    q  = "نامحدود" if c.daily_queries  == -1 else str(c.daily_queries)
    lk = "ممنوع"   if c.daily_links    ==  0 else ("نامحدود" if c.daily_links    == -1 else str(c.daily_links))
    fw = "ممنوع"   if c.daily_forwards ==  0 else ("نامحدود" if c.daily_forwards == -1 else str(c.daily_forwards))
    return (
        f"🏅 *سطح {c.label}*\n\n"
        f"❓ سوال/روز:     `{q}`\n"
        f"🔗 لینک/روز:     `{lk}`\n"
        f"↩️ فوروارد/روز: `{fw}`\n"
        f"📸 مدیا:         `{'✅' if c.can_media else '❌'}`\n\n"
        "یک مورد برای تغییر انتخاب کن:"
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

    if data == "cfg_back":
        await query.edit_message_text(
            "⚙️ *پنل تنظیمات ربات*\nیک مورد را برای تغییر انتخاب کنید:",
            parse_mode="HTML",
            reply_markup=_main_keyboard(),
        )
        return

    if data == "cfg_show":
        await query.edit_message_text(
            _current_settings(),
            parse_mode="HTML",
            reply_markup=_main_keyboard(),
        )
        return

    # ── منوی سطوح ────────────────────────────────────
    if data == "cfg_levels_menu":
        await query.edit_message_text(
            "🏅 *تنظیم محدودیت‌های سطوح کاربری*\nسطح موردنظر را انتخاب کن:",
            parse_mode="HTML",
            reply_markup=_levels_keyboard(),
        )
        return

    # ── جزئیات یک سطح ────────────────────────────────
    # مثال: cfg_lv_bronze
    if data.startswith("cfg_lv_") and data.count("_") == 2:
        level = data.split("_")[2]
        await query.edit_message_text(
            _level_summary_text(level),
            parse_mode="HTML",
            reply_markup=_level_detail_keyboard(level),
        )
        return

    # ── تغییر یک فیلد خاص سطح ────────────────────────
    # مثال: cfg_lv_bronze_queries
    if data.startswith("cfg_lv_") and data.count("_") == 3:
        _, _, level, field = data.split("_", 3)
        field_labels = {
            "queries":  ("سوال روزانه",      "عدد یا -1 برای نامحدود"),
            "links":    ("لینک روزانه",       "عدد، 0 برای ممنوع، -1 برای نامحدود"),
            "forwards": ("فوروارد روزانه",    "عدد، 0 برای ممنوع، -1 برای نامحدود"),
            "media":    ("اجازه مدیا",        "true یا false"),
        }
        if field not in field_labels:
            return
        label, hint = field_labels[field]
        from bot.core.user_levels import LEVELS
        lv_cfg = LEVELS[level]
        current = {
            "queries":  str(lv_cfg.daily_queries),
            "links":    str(lv_cfg.daily_links),
            "forwards": str(lv_cfg.daily_forwards),
            "media":    str(lv_cfg.can_media).lower(),
        }[field]

        context.user_data["settings_key"]     = f"LEVEL_{level}_{field}"
        context.user_data["settings_msgid"]   = query.message.message_id
        context.user_data["settings_chatid"]  = query.message.chat_id
        context.user_data["settings_level"]   = level

        await query.edit_message_text(
            f"✏️ *تغییر {label} — سطح {level}*\n\n"
            f"مقدار فعلی: `{current}`\n"
            f"راهنما: {hint}\n\n"
            "مقدار جدید را بنویسید یا /cancel برای انصراف:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ انصراف", callback_data="cfg_cancel")
            ]]),
        )
        return WAIT_VALUE

    # ── تنظیمات عادی ─────────────────────────────────
    key_map = {
        "cfg_ai_model":    ("GEMINI_MODEL",   "Gemini model name (e.g. gemini-2.5-flash / gemini-2.0-flash)"),
        "cfg_gemini_key":  ("GEMINI_API_KEY", "Gemini API Key (from aistudio.google.com)"),
        "cfg_max_warn":    ("MAX_WARNINGS",   "Max warnings before ban (number)"),
        "cfg_spam_window": ("SPAM_TIME_WINDOW", "Spam detection window in seconds"),
        "cfg_spam_max":    ("SPAM_MAX_MESSAGES", "Max messages in spam window"),
        "cfg_min_conf":    ("MIN_CONFIDENCE", "AI confidence threshold — 0.0 to 1.0"),
        "cfg_bot_lang":    ("BOT_LANG",       "Bot language — fa (Persian) or en (English)"),
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

    # ── ذخیره تغییر سطح در حافظه (user_levels.LEVELS) ───────────────────────
    if env_key.startswith("LEVEL_"):
        _, level, field = env_key.split("_", 2)
        error_msg = _validate_level_field(field, new_value)
        if error_msg:
            await update.message.reply_text(
                f"❌ {error_msg}\nدوباره وارد کنید یا /cancel بزنید:",
                parse_mode="HTML",
            )
            context.user_data["settings_key"] = env_key
            return WAIT_VALUE

        _apply_level_change(level, field, new_value)
        context.user_data.pop("settings_level", None)

        try:
            await update.message.delete()
            chat_id = context.user_data.pop("settings_chatid", None)
            msg_id  = context.user_data.pop("settings_msgid", None)
            if chat_id and msg_id:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=(
                        f"✅ سطح *{level}* — *{field}* به `{new_value}` تغییر کرد\n\n"
                        + _level_summary_text(level)
                    ),
                    parse_mode="HTML",
                    reply_markup=_level_detail_keyboard(level),
                )
        except Exception:
            await update.message.reply_text(
                f"✅ سطح {level} — {field} = `{new_value}` تغییر کرد.\n"
                "⚠️ تغییر فقط تا ری‌استارت ربات پایدار است.\n"
                "برای دائمی شدن، مقادیر را در `user_levels.py` هم ویرایش کنید.",
                parse_mode="HTML",
            )
        logger.info(f"Level {level}.{field} changed to '{new_value}' by {update.effective_user.id}")
        return ConversationHandler.END

    # ── تنظیمات معمولی (.env) ─────────────────────────────────────────────────
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
    elif key == "GEMINI_API_KEY":
        if len(value) < 10:
            return "API Key معتبر نیست"
    elif key == "GEMINI_MODEL":
        valid_models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-pro"]
        if value not in valid_models:
            return f"مدل باید یکی از اینها باشد: {', '.join(valid_models)}"
    elif key == "BOT_LANG":
        if value not in ("fa", "en"):
            return "Must be 'fa' (Persian) or 'en' (English)"
    return ""


def _validate_level_field(field: str, value: str) -> str:
    if field in ("queries", "links", "forwards"):
        try:
            v = int(value)
            if v < -1:
                return "باید عدد >= -1 باشد (-1 نامحدود، 0 ممنوع)"
        except ValueError:
            return "باید عدد صحیح باشد"
    elif field == "media":
        if value.lower() not in ("true", "false"):
            return "باید true یا false باشد"
    return ""


def _apply_level_change(level: str, field: str, value: str):
    """تغییر live در شیء LEVELS — تا ری‌استارت بعدی پایدار است"""
    from bot.core.user_levels import LEVELS
    cfg = LEVELS[level]
    if field == "queries":
        cfg.daily_queries = int(value)
    elif field == "links":
        cfg.daily_links = int(value)
    elif field == "forwards":
        cfg.daily_forwards = int(value)
    elif field == "media":
        cfg.can_media = value.lower() == "true"


# ── ساخت ConversationHandler ─────────────────────────
def build_settings_handler() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(on_settings_callback, pattern=r"^cfg_(?!cancel$|close$|show$|back$)"),
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
