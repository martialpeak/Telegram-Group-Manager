"""
پنل تنظیمات از طریق تلگرام — فقط ادمین
دستور: /settings
"""

import os
import logging
from dotenv import set_key, dotenv_values
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters

from config import ADMIN_IDS

logger   = logging.getLogger(__name__)
ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")


# ── خواندن / نوشتن .env ──────────────────────────────
def _get(key: str, default: str = "—") -> str:
    return dotenv_values(ENV_PATH).get(key, default)

def _set(key: str, value: str):
    set_key(ENV_PATH, key, value)


# ── کیبوردها ─────────────────────────────────────────
def _main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🤖 Gemini Model",   callback_data="cfg_ai_model"),
            InlineKeyboardButton("🔑 Gemini API Key", callback_data="cfg_gemini_key"),
        ],
        [
            InlineKeyboardButton("⚠️ Max Warnings",   callback_data="cfg_max_warn"),
            InlineKeyboardButton("🕐 Spam Window",    callback_data="cfg_spam_window"),
        ],
        [
            InlineKeyboardButton("📨 Spam Limit",     callback_data="cfg_spam_max"),
            InlineKeyboardButton("🎯 AI Confidence",  callback_data="cfg_min_conf"),
        ],
        [
            InlineKeyboardButton("🌐 Bot Language",   callback_data="cfg_bot_lang"),
            InlineKeyboardButton("📊 Show Current",   callback_data="cfg_show"),
        ],
        [
            InlineKeyboardButton("🏅 Level Limits",   callback_data="cfg_levels_menu"),
        ],
        [
            InlineKeyboardButton("❌ Close",          callback_data="cfg_close"),
        ],
    ])


def _levels_keyboard() -> InlineKeyboardMarkup:
    from bot.core.user_levels import LEVEL_ORDER, LEVELS
    rows = []
    for lv in LEVEL_ORDER:
        c  = LEVELS[lv]
        q  = "∞" if c.daily_queries  == -1 else str(c.daily_queries)
        lk = "✗" if c.daily_links    ==  0 else ("∞" if c.daily_links    == -1 else str(c.daily_links))
        fw = "✗" if c.daily_forwards ==  0 else ("∞" if c.daily_forwards == -1 else str(c.daily_forwards))
        rows.append([InlineKeyboardButton(
            f"{c.label}  |  ❓{q}  🔗{lk}  ↩{fw}  📸{'✅' if c.can_media else '❌'}",
            callback_data=f"cfg_lv_{lv}",
        )])
    rows.append([InlineKeyboardButton("🔙 برگشت", callback_data="cfg_back")])
    return InlineKeyboardMarkup(rows)


def _level_detail_keyboard(level: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("❓ سوال/روز",     callback_data=f"cfg_lv_{level}_queries"),
            InlineKeyboardButton("🔗 لینک/روز",     callback_data=f"cfg_lv_{level}_links"),
        ],
        [
            InlineKeyboardButton("↩️ فوروارد/روز",  callback_data=f"cfg_lv_{level}_forwards"),
            InlineKeyboardButton("📸 مجاز مدیا",    callback_data=f"cfg_lv_{level}_media"),
        ],
        [InlineKeyboardButton("🔙 برگشت به سطوح", callback_data="cfg_levels_menu")],
    ])


def _level_summary_text(level: str) -> str:
    from bot.core.user_levels import LEVELS
    c  = LEVELS[level]
    q  = "نامحدود" if c.daily_queries  == -1 else str(c.daily_queries)
    lk = "ممنوع"   if c.daily_links    ==  0 else ("نامحدود" if c.daily_links    == -1 else str(c.daily_links))
    fw = "ممنوع"   if c.daily_forwards ==  0 else ("نامحدود" if c.daily_forwards == -1 else str(c.daily_forwards))
    return (
        f"🏅 <b>سطح {c.label}</b>\n\n"
        f"❓ سوال/روز:      <code>{q}</code>\n"
        f"🔗 لینک/روز:      <code>{lk}</code>\n"
        f"↩️ فوروارد/روز:  <code>{fw}</code>\n"
        f"📸 مدیا:          <code>{'✅' if c.can_media else '❌'}</code>\n\n"
        "یک مورد برای تغییر انتخاب کن:"
    )


def _current_settings() -> str:
    lang_label = "🇮🇷 Persian" if _get("BOT_LANG", "fa") == "fa" else "🇬🇧 English"
    key = _get("GEMINI_API_KEY", "")
    key_display = f"{key[:8]}..." if len(key) > 8 else ("تنظیم نشده" if not key else key)
    return (
        "⚙️ <b>Current Settings:</b>\n\n"
        f"🤖 Gemini Model:    <code>{_get('GEMINI_MODEL', 'gemini-2.5-flash')}</code>\n"
        f"🔑 Gemini API Key:  <code>{key_display}</code>\n"
        f"⚠️ Max Warnings:    <code>{_get('MAX_WARNINGS')}</code>\n"
        f"🕐 Spam Window:     <code>{_get('SPAM_TIME_WINDOW')} sec</code>\n"
        f"📨 Spam Limit:      <code>{_get('SPAM_MAX_MESSAGES')} msg</code>\n"
        f"🎯 AI Confidence:   <code>{_get('MIN_CONFIDENCE')}</code>\n"
        f"🌐 Bot Language:    {lang_label}\n"
        f"🧠 Learning:        <code>{_get('LEARNING_ENABLED')}</code>\n"
    )


# ── /settings ────────────────────────────────────────
async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return
    await update.message.reply_text(
        "⚙️ <b>پنل تنظیمات ربات</b>\nیک مورد را برای تغییر انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=_main_keyboard(),
    )


# ── callback handler (همه cfg_* اینجا) ──────────────
async def on_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id not in ADMIN_IDS:
        return

    data = query.data

    # ── ناوبری ───────────────────────────────────────
    if data == "cfg_close":
        await query.message.delete()
        return

    if data == "cfg_back":
        context.user_data.pop("settings_key", None)
        await query.edit_message_text(
            "⚙️ <b>پنل تنظیمات ربات</b>\nیک مورد را برای تغییر انتخاب کنید:",
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

    if data == "cfg_levels_menu":
        context.user_data.pop("settings_key", None)
        await query.edit_message_text(
            "🏅 <b>تنظیم محدودیت‌های سطوح کاربری</b>\nسطح موردنظر را انتخاب کن:",
            parse_mode="HTML",
            reply_markup=_levels_keyboard(),
        )
        return

    # ── نمایش جزئیات سطح: cfg_lv_bronze ─────────────
    parts = data.split("_")
    # cfg_lv_<level>  →  ['cfg', 'lv', '<level>']
    if data.startswith("cfg_lv_") and len(parts) == 3:
        level = parts[2]
        context.user_data.pop("settings_key", None)
        await query.edit_message_text(
            _level_summary_text(level),
            parse_mode="HTML",
            reply_markup=_level_detail_keyboard(level),
        )
        return

    # ── انتخاب فیلد سطح: cfg_lv_bronze_queries ──────
    # cfg_lv_<level>_<field>  →  ['cfg', 'lv', '<level>', '<field>']
    if data.startswith("cfg_lv_") and len(parts) == 4:
        level = parts[2]
        field = parts[3]
        field_labels = {
            "queries":  ("سوال روزانه",    "عدد  |  -1 = نامحدود"),
            "links":    ("لینک روزانه",    "عدد  |  0 = ممنوع  |  -1 = نامحدود"),
            "forwards": ("فوروارد روزانه", "عدد  |  0 = ممنوع  |  -1 = نامحدود"),
            "media":    ("اجازه مدیا",     "true  یا  false"),
        }
        if field not in field_labels:
            return
        label, hint = field_labels[field]
        from bot.core.user_levels import LEVELS
        cfg = LEVELS[level]
        current = {
            "queries":  str(cfg.daily_queries),
            "links":    str(cfg.daily_links),
            "forwards": str(cfg.daily_forwards),
            "media":    str(cfg.can_media).lower(),
        }[field]

        context.user_data["settings_key"]    = f"LEVEL_{level}_{field}"
        context.user_data["settings_msgid"]  = query.message.message_id
        context.user_data["settings_chatid"] = query.message.chat_id

        await query.edit_message_text(
            f"✏️ <b>تغییر {label} — سطح {level}</b>\n\n"
            f"مقدار فعلی: <code>{current}</code>\n"
            f"راهنما: {hint}\n\n"
            "مقدار جدید را بنویسید یا /cancel برای انصراف:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ انصراف", callback_data="cfg_cancel")
            ]]),
        )
        return

    if data == "cfg_cancel":
        context.user_data.pop("settings_key", None)
        await query.edit_message_text(
            "⚙️ <b>پنل تنظیمات ربات</b>\nیک مورد را برای تغییر انتخاب کنید:",
            parse_mode="HTML",
            reply_markup=_main_keyboard(),
        )
        return

    # ── تنظیمات .env ─────────────────────────────────
    key_map = {
        "cfg_ai_model":    ("GEMINI_MODEL",      "Gemini model name"),
        "cfg_gemini_key":  ("GEMINI_API_KEY",    "Gemini API Key"),
        "cfg_max_warn":    ("MAX_WARNINGS",      "Max warnings before ban"),
        "cfg_spam_window": ("SPAM_TIME_WINDOW",  "Spam detection window (seconds)"),
        "cfg_spam_max":    ("SPAM_MAX_MESSAGES", "Max messages in spam window"),
        "cfg_min_conf":    ("MIN_CONFIDENCE",    "AI confidence threshold (0.0 – 1.0)"),
        "cfg_bot_lang":    ("BOT_LANG",          "Bot language — fa یا en"),
    }
    if data not in key_map:
        return

    env_key, description = key_map[data]
    context.user_data["settings_key"]    = env_key
    context.user_data["settings_msgid"]  = query.message.message_id
    context.user_data["settings_chatid"] = query.message.chat_id

    await query.edit_message_text(
        f"✏️ <b>تغییر {description}</b>\n\n"
        f"مقدار فعلی: <code>{_get(env_key)}</code>\n\n"
        "مقدار جدید را بنویسید یا /cancel برای انصراف:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ انصراف", callback_data="cfg_cancel")
        ]]),
    )


# ── دریافت مقدار متنی ────────────────────────────────
async def on_settings_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        return

    env_key = context.user_data.get("settings_key")
    if not env_key:
        return   # این پیام مربوط به settings نیست

    new_value = update.message.text.strip()

    # ── تغییر سطح ────────────────────────────────────
    if env_key.startswith("LEVEL_"):
        _, level, field = env_key.split("_", 2)
        err = _validate_level_field(field, new_value)
        if err:
            await update.message.reply_text(f"❌ {err}\nدوباره وارد کن یا /cancel بزن:")
            return

        _apply_level_change(level, field, new_value)
        context.user_data.pop("settings_key", None)

        chat_id = context.user_data.pop("settings_chatid", None)
        msg_id  = context.user_data.pop("settings_msgid", None)
        try:
            await update.message.delete()
        except Exception:
            pass
        try:
            if chat_id and msg_id:
                await context.bot.edit_message_text(
                    chat_id=chat_id, message_id=msg_id,
                    text=(
                        f"✅ سطح <b>{level}</b> — <b>{field}</b> به "
                        f"<code>{new_value}</code> تغییر کرد\n\n"
                        + _level_summary_text(level)
                    ),
                    parse_mode="HTML",
                    reply_markup=_level_detail_keyboard(level),
                )
            else:
                await update.message.reply_text(
                    f"✅ سطح {level} — {field} = <code>{new_value}</code> تغییر کرد.",
                    parse_mode="HTML",
                )
        except Exception as e:
            logger.warning(f"edit message failed: {e}")
        return

    # ── تغییر .env ───────────────────────────────────
    err = _validate(env_key, new_value)
    if err:
        await update.message.reply_text(f"❌ {err}\nدوباره وارد کن یا /cancel بزن:")
        return

    _set(env_key, new_value)
    context.user_data.pop("settings_key", None)

    chat_id = context.user_data.pop("settings_chatid", None)
    msg_id  = context.user_data.pop("settings_msgid", None)
    try:
        await update.message.delete()
    except Exception:
        pass
    try:
        if chat_id and msg_id:
            await context.bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id,
                text=(
                    f"✅ <b>{env_key}</b> به <code>{new_value}</code> تغییر کرد\n\n"
                    "⚙️ <b>پنل تنظیمات ربات</b>\nیک مورد را برای تغییر انتخاب کنید:"
                ),
                parse_mode="HTML",
                reply_markup=_main_keyboard(),
            )
        else:
            await update.message.reply_text(
                f"✅ <code>{env_key}</code> = <code>{new_value}</code> ذخیره شد.\n"
                "⚠️ برای اعمال: <code>sudo systemctl restart telegram-bot</code>",
                parse_mode="HTML",
            )
    except Exception as e:
        logger.warning(f"edit message failed: {e}")

    logger.info(f"Setting {env_key} = '{new_value}' by {update.effective_user.id}")


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.pop("settings_key", None):
        await update.message.reply_text("❌ لغو شد.")


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
            return "باید عدد اعشاری باشد (مثلاً 0.80)"
    elif key == "GEMINI_API_KEY":
        if len(value) < 10:
            return "API Key معتبر نیست"
    elif key == "GEMINI_MODEL":
        valid = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.5-pro"]
        if value not in valid:
            return f"مدل باید یکی از اینها باشد: {', '.join(valid)}"
    elif key == "BOT_LANG":
        if value not in ("fa", "en"):
            return "باید fa یا en باشد"
    return ""


def _validate_level_field(field: str, value: str) -> str:
    if field in ("queries", "links", "forwards"):
        try:
            if int(value) < -1:
                return "باید عدد >= -1 باشد (-1 نامحدود، 0 ممنوع)"
        except ValueError:
            return "باید عدد صحیح باشد"
    elif field == "media":
        if value.lower() not in ("true", "false"):
            return "باید true یا false باشد"
    return ""


def _apply_level_change(level: str, field: str, value: str):
    from bot.core.user_levels import LEVELS
    cfg = LEVELS[level]
    if field == "queries":
        cfg.daily_queries  = int(value)
    elif field == "links":
        cfg.daily_links    = int(value)
    elif field == "forwards":
        cfg.daily_forwards = int(value)
    elif field == "media":
        cfg.can_media      = value.lower() == "true"


# ── ثبت handler ها در app ────────────────────────────
def register(app):
    """همه handler های settings رو یکجا ثبت می‌کنه"""
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("cancel",   cmd_cancel))
    app.add_handler(CallbackQueryHandler(on_settings_callback, pattern=r"^cfg_"))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            on_settings_value,
        ),
        group=10,
    )
