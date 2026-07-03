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
            InlineKeyboardButton("🤖 Groq Model",     callback_data="cfg_groq_model"),
            InlineKeyboardButton("🔑 Groq API Key",   callback_data="cfg_groq_key"),
        ],
        [
            InlineKeyboardButton("⚡ Quick Models",    callback_data="cfg_models_menu"),
        ],
        [
            InlineKeyboardButton("📚 Training Channels", callback_data="cfg_channels_menu"),
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
        st = "✗" if c.daily_stickers ==  0 else ("∞" if c.daily_stickers == -1 else str(c.daily_stickers))
        rows.append([InlineKeyboardButton(
            f"{c.label}  |  ❓{q}  🔗{lk}  ↩{fw}  🎭{st}  📸{'✅' if c.can_media else '❌'}",
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
        [
            InlineKeyboardButton("🎭 استیکر/روز",   callback_data=f"cfg_lv_{level}_stickers"),
        ],
        [InlineKeyboardButton("🔙 برگشت به سطوح", callback_data="cfg_levels_menu")],
    ])


# مدل‌های Groq قابل‌انتخاب (سریع‌ترین انتخاب با یه کلیک)
GROQ_MODELS = [
    ("llama-3.3-70b-versatile", "🧠 Llama 3.3 70B (قوی‌ترین - پیشنهادی)"),
    ("llama-3.1-8b-instant",    "⚡ Llama 3.1 8B (سریع‌ترین)"),
    ("deepseek-r1-distill-llama-70b", "🔬 DeepSeek R1 (استدلال قوی)"),
    ("qwen-2.5-coder-32b",      "💻 Qwen 2.5 Coder 32B"),
    ("mixtral-8x7b-32768",      "🔀 Mixtral 8x7B"),
    ("gemma2-9b-it",            "✨ Gemma2 9B"),
]


def _models_keyboard() -> InlineKeyboardMarkup:
    from dotenv import dotenv_values
    current = dotenv_values(ENV_PATH).get("GROQ_MODEL", "llama-3.3-70b-versatile")
    rows = []
    for model_id, label in GROQ_MODELS:
        marker = "✅ " if model_id == current else "▫️ "
        rows.append([InlineKeyboardButton(
            f"{marker}{label}",
            callback_data=f"cfg_model_{model_id}",
        )])
    rows.append([InlineKeyboardButton("🔙 برگشت", callback_data="cfg_back")])
    return InlineKeyboardMarkup(rows)


def _level_summary_text(level: str) -> str:
    from bot.core.user_levels import LEVELS
    c  = LEVELS[level]
    q  = "نامحدود" if c.daily_queries  == -1 else str(c.daily_queries)
    lk = "ممنوع"   if c.daily_links    ==  0 else ("نامحدود" if c.daily_links    == -1 else str(c.daily_links))
    fw = "ممنوع"   if c.daily_forwards ==  0 else ("نامحدود" if c.daily_forwards == -1 else str(c.daily_forwards))
    st = "ممنوع"   if c.daily_stickers ==  0 else ("نامحدود" if c.daily_stickers == -1 else str(c.daily_stickers))
    return (
        f"🏅 <b>سطح {c.label}</b>\n\n"
        f"❓ سوال/روز:      <code>{q}</code>\n"
        f"🔗 لینک/روز:      <code>{lk}</code>\n"
        f"↩️ فوروارد/روز:  <code>{fw}</code>\n"
        f"🎭 استیکر/روز:   <code>{st}</code>\n"
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
    # هم در PV هم در گروه کار می‌کنه
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

    # ── منوی مدیریت کانال‌های آموزشی ──────────────────────────────────────
    if data == "cfg_channels_menu":
        context.user_data.pop("settings_key", None)
        from config import TRAINING_CHANNELS
        if TRAINING_CHANNELS:
            channels_text = "\n".join(f"✅ {c}" for c in TRAINING_CHANNELS)
        else:
            channels_text = "📭 هیچ کانالی تنظیم نشده."
        await query.edit_message_text(
            f"📚 <b>مدیریت کانال‌های آموزشی</b>\n\n"
            f"این کانال‌ها منبع یادگیری ربات هستن. "
            f"محتوای اونا با دستور <code>/sync</code> خونده می‌شه.\n\n"
            f"<b>کانال‌های فعلی:</b>\n{channels_text}\n\n"
            f"برای افزودن: <code>/addchannel @channelname</code>\n"
            f"برای حذف: <code>/delchannel @channelname</code>\n"
            f"برای همگام‌سازی: <code>/sync</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 برگشت", callback_data="cfg_back"),
            ]]),
        )
        return

    # ── منوی انتخاب سریع مدل Groq ─────────────────────────────────────────
    if data == "cfg_models_menu":
        context.user_data.pop("settings_key", None)
        await query.edit_message_text(
            "🤖 <b>انتخاب مدل Groq</b>\n\n"
            "مدل‌های قوی‌تر دقیق‌تر ولی کندترن.\n"
            "مدل‌های سریع‌تر برای پاسخ‌های کوتاه مناسب‌ترن.\n\n"
            "✅ = مدل فعلی",
            parse_mode="HTML",
            reply_markup=_models_keyboard(),
        )
        return

    # ── انتخاب مدل با یه کلیک: cfg_model_<model_id> ─────────────────────
    if data.startswith("cfg_model_"):
        # model_id ممکنه خودش dash داشته باشه، پس کل داده بعد از cfg_model_ رو بگیر
        model_id = data[len("cfg_model_"):]
        # اعتبارسنجی
        valid_ids = [m[0] for m in GROQ_MODELS]
        if model_id not in valid_ids:
            await query.answer("مدل نامعتبر!", show_alert=True)
            return
        _set("GROQ_MODEL", model_id)
        # reload کانفیگ در حافظه
        import config as _config
        _config.GROQ_MODEL = model_id
        # reload کلاینت groq در knowledge_engine و ai_analyzer
        try:
            import bot.core.knowledge_engine as _ke
            import bot.core.ai_analyzer as _aa
            if _config.GROQ_API_KEY:
                from groq import Groq
                _client = Groq(api_key=_config.GROQ_API_KEY)
                _ke._groq_client = _client
                _aa._groq_client = _client
        except Exception as e:
            logger.warning(f"reload groq client failed: {e}")
        await query.answer(f"✅ مدل به {model_id} تغییر کرد", show_alert=False)
        await query.edit_message_text(
            f"🤖 <b>انتخاب مدل Groq</b>\n\n"
            f"✅ مدل فعلی: <code>{model_id}</code>\n\n"
            "تغییرات بلافاصله اعمال شد.",
            parse_mode="HTML",
            reply_markup=_models_keyboard(),
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
            "stickers": ("استیکر/گیف روزانه", "عدد  |  0 = ممنوع  |  -1 = نامحدود"),
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
            "stickers": str(cfg.daily_stickers),
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
        "cfg_groq_model":  ("GROQ_MODEL",        "Groq model name"),
        "cfg_groq_key":    ("GROQ_API_KEY",      "Groq API Key"),
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
    # اگه /cancel فرستاده
    if new_value.lower() in ("/cancel", "cancel"):
        context.user_data.pop("settings_key", None)
        await update.message.reply_text("❌ لغو شد.")
        return

    # ── تغییر سطح ────────────────────────────────────
    if env_key.startswith("LEVEL_"):
        _, level, field = env_key.split("_", 2)
        err = _validate_level_field(field, new_value)
        if err:
            await update.message.reply_text(f"❌ {err}\nدوباره وارد کن یا /cancel بزن:")
            return

        _apply_level_change(level, field, new_value)
        context.user_data.pop("settings_key", None)

        chat_id = context.user_data.pop("settings_chatid", None) or update.message.chat_id
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
            await update.message.reply_text(
                f"✅ سطح <b>{level}</b> — <b>{field}</b> به <code>{new_value}</code> تغییر کرد.",
                parse_mode="HTML",
                reply_markup=_level_detail_keyboard(level),
            )
        return

    # ── تغییر .env ───────────────────────────────────
    err = _validate(env_key, new_value)
    if err:
        await update.message.reply_text(f"❌ {err}\nدوباره وارد کن یا /cancel بزن:")
        return

    _set(env_key, new_value)
    context.user_data.pop("settings_key", None)

    chat_id = context.user_data.pop("settings_chatid", None) or update.message.chat_id
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
        await update.message.reply_text(
            f"✅ <b>{env_key}</b> به <code>{new_value}</code> تغییر کرد.",
            parse_mode="HTML",
        )

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
    elif key == "GROQ_API_KEY":
        if len(value) < 10:
            return "API Key معتبر نیست"
    elif key == "GROQ_MODEL":
        # لیست مدل‌های Groq قابل‌استفاده (به‌روزرسانی ۲۰۲۵)
        valid = [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "llama3-70b-8192",
            "llama3-8b-8192",
            "gemma2-9b-it",
            "gemma2-9b-it",
            "deepseek-r1-distill-llama-70b",
            "qwen-2.5-coder-32b",
            "mixtral-8x7b-32768",
        ]
        if value not in valid:
            return f"مدل باید یکی از اینها باشد:\n{', '.join(valid)}"
    return ""


def _validate_level_field(field: str, value: str) -> str:
    if field in ("queries", "links", "forwards", "stickers"):
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
    elif field == "stickers":
        cfg.daily_stickers = int(value)
    elif field == "media":
        cfg.can_media      = value.lower() == "true"
    # ذخیره در .env تا بعد از restart هم باقی بمونه
    env_key = f"LEVEL_{level.upper()}_{field.upper()}"
    set_key(ENV_PATH, env_key, value)


# ── /update — آپدیت ربات از داخل تلگرام ─────────────
async def cmd_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    git pull + pip install + systemctl restart
    فقط ادمین — هم در PV هم در گروه
    """
    if update.effective_user.id not in ADMIN_IDS:
        return

    msg = await update.message.reply_text("🔄 در حال بررسی آپدیت...")

    import asyncio, subprocess, sys, os

    bot_dir = os.path.dirname(os.path.abspath(__file__))

    async def _run(cmd: list[str]) -> tuple[int, str]:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=bot_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=120)
        return proc.returncode, out.decode(errors="replace").strip()

    try:
        # ۱. وضعیت فعلی
        _, current = await _run(["git", "rev-parse", "--short", "HEAD"])

        # ۲. fetch
        await msg.edit_text("🔄 دریافت تغییرات از GitHub...")
        rc, _ = await _run(["git", "fetch", "origin"])
        if rc != 0:
            await msg.edit_text("❌ خطا در git fetch. اتصال به GitHub را بررسی کن.")
            return

        # ۳. مقایسه
        _, remote = await _run(["git", "rev-parse", "--short", "origin/main"])
        if current == remote:
            await msg.edit_text(
                f"✅ ربات به‌روز است.\n📌 نسخه فعلی: <code>{current}</code>",
                parse_mode="HTML",
            )
            return

        # ۴. pull
        await msg.edit_text("⬇️ دانلود آپدیت...")
        rc, pull_out = await _run(["git", "pull", "--ff-only", "origin", "main"])
        if rc != 0:
            await msg.edit_text(f"❌ خطا در git pull:\n<code>{pull_out[:300]}</code>", parse_mode="HTML")
            return

        _, new_ver = await _run(["git", "rev-parse", "--short", "HEAD"])

        # ۵. نمایش changelog
        _, changes = await _run(["git", "log", "--oneline", f"{current}..HEAD"])
        changes_txt = changes[:400] if changes else "بدون تغییر"

        # ۶. آپدیت پکیج‌ها
        await msg.edit_text("📦 آپدیت پکیج‌های Python...")
        venv_pip = os.path.join(bot_dir, "venv", "bin", "pip")
        if not os.path.exists(venv_pip):
            venv_pip = sys.executable.replace("python", "pip")
        await _run([venv_pip, "install", "-q", "-r", os.path.join(bot_dir, "requirements.txt")])

        # ۷. ذخیره اطلاعات برای پیام بعد از restart
        import json
        restart_info = {
            "chat_id":     update.message.chat_id,
            "admin_id":    update.effective_user.id,
            "old_ver":     current,
            "new_ver":     new_ver,
            "changes":     changes_txt,
        }
        with open(os.path.join(bot_dir, ".restart_notify.json"), "w", encoding="utf-8") as f:
            json.dump(restart_info, f, ensure_ascii=False)

        await msg.edit_text(
            f"✅ <b>آپدیت موفق!</b>\n\n"
            f"📌 نسخه قبلی: <code>{current}</code>\n"
            f"📌 نسخه جدید: <code>{new_ver}</code>\n\n"
            f"📋 تغییرات:\n<code>{changes_txt}</code>\n\n"
            "♻️ در حال ری‌استارت — بعد از چند ثانیه پیام تأیید می‌رسه...",
            parse_mode="HTML",
        )

        await asyncio.sleep(2)

        python = sys.executable
        os.execv(python, [python] + sys.argv)

    except asyncio.TimeoutError:
        await msg.edit_text("❌ عملیات آپدیت timeout شد. سرور را بررسی کن.")
    except Exception as e:
        logger.error(f"cmd_update error: {e}")
        await msg.edit_text(f"❌ خطای غیرمنتظره:\n<code>{str(e)[:300]}</code>", parse_mode="HTML")


# ── ثبت handler ها در app ────────────────────────────
def register(app):
    """همه handler های settings رو یکجا ثبت می‌کنه"""
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("cancel",   cmd_cancel))
    app.add_handler(CommandHandler("update",   cmd_update))
    app.add_handler(CallbackQueryHandler(on_settings_callback, pattern=r"^cfg_"))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            on_settings_value,
        ),
        group=10,
    )
