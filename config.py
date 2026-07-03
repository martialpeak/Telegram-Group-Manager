import os
from dotenv import load_dotenv

load_dotenv()

# ── تلگرام ───────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ── زبان ربات ─────────────────────────────────────────
BOT_LANG = os.getenv("BOT_LANG", "fa")

# ── AI Provider ───────────────────────────────────────
# primary: groq | gemini
AI_PROVIDER    = os.getenv("AI_PROVIDER", "groq")

# Groq (primary — 14400 req/day free)
GROQ_API_KEY   = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL     = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Gemini (fallback — 1500 req/day free)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# ── Cache ─────────────────────────────────────────────
# حداقل شباهت برای استفاده از cache
CACHE_MIN_SCORE    = float(os.getenv("CACHE_MIN_SCORE", "0.75"))
# مدت نگهداری cache به ساعت
CACHE_TTL_HOURS    = int(os.getenv("CACHE_TTL_HOURS", "24"))

# ── مدیریت گروه ──────────────────────────────────────
MAX_WARNINGS       = int(os.getenv("MAX_WARNINGS", "3"))
SPAM_TIME_WINDOW   = int(os.getenv("SPAM_TIME_WINDOW", "60"))
SPAM_MAX_MESSAGES  = int(os.getenv("SPAM_MAX_MESSAGES", "5"))
MIN_CONFIDENCE     = float(os.getenv("MIN_CONFIDENCE", "0.80"))

# ── یادگیری ──────────────────────────────────────────
LEARNING_ENABLED    = os.getenv("LEARNING_ENABLED", "true").lower() == "true"
LEARNING_BATCH_SIZE = int(os.getenv("LEARNING_BATCH_SIZE", "50"))
LEARNING_MIN_SCORE  = float(os.getenv("LEARNING_MIN_SCORE", "0.75"))
SEARCH_TOP_K        = int(os.getenv("SEARCH_TOP_K", "5"))

# ── ادمین‌ها ──────────────────────────────────────────
_raw = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in _raw.split(",") if x.strip().isdigit()]

# ── کانال‌های آموزشی — منبع یادگیری ربات ──────────────────────────────────────
# با کاما جدا شده: @channel1,@channel2
_raw_channels = os.getenv("TRAINING_CHANNELS", "")
TRAINING_CHANNELS = [
    c.strip() for c in _raw_channels.split(",") if c.strip()
]


def add_training_channel(channel: str) -> bool:
    """افزودن کانال آموزشی و ذخیره در .env. True اگر موفق بود."""
    import os as _os
    from dotenv import set_key as _set_key, dotenv_values as _dv
    _env = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".env")
    channel = channel.strip()
    if not channel.startswith("@"):
        channel = "@" + channel
    # اگه از قبل هست، چیزی اضافه نکن
    existing = [c.strip() for c in _dv(_env).get("TRAINING_CHANNELS", "").split(",") if c.strip()]
    if channel in existing:
        return False
    existing.append(channel)
    _set_key(_env, "TRAINING_CHANNELS", ",".join(existing))
    TRAINING_CHANNELS[:] = existing
    return True


def remove_training_channel(channel: str) -> bool:
    """حذف کانال آموزشی. True اگر حذف شد."""
    import os as _os
    from dotenv import set_key as _set_key, dotenv_values as _dv
    _env = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".env")
    channel = channel.strip()
    if not channel.startswith("@"):
        channel = "@" + channel
    existing = [c.strip() for c in _dv(_env).get("TRAINING_CHANNELS", "").split(",") if c.strip()]
    if channel not in existing:
        return False
    existing.remove(channel)
    _set_key(_env, "TRAINING_CHANNELS", ",".join(existing))
    TRAINING_CHANNELS[:] = existing
    return True

# ── تنظیمات سرچ در وب ─────────────────────────────────────────────────────────
WEB_SEARCH_ENABLED = os.getenv("WEB_SEARCH_ENABLED", "true").lower() == "true"
WEB_SEARCH_MAX_RESULTS = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "3"))

# ── تاخیر حداقل پاسخ AI (ثانیه) — برای نمایش بهتر لودینگ ─────────────────────
AI_MIN_RESPONSE_DELAY = float(os.getenv("AI_MIN_RESPONSE_DELAY", "4"))

# ── پیام‌ها ───────────────────────────────────────────
MESSAGES = {
    "warn_insult": (
        "⚠️ {name} عزیز، استفاده از کلمات توهین‌آمیز مجاز نیست.\n"
        "اخطار {warn}/{max} — تکرار منجر به حذف از گروه می‌شود."
    ),
    "warn_spam": (
        "⚠️ {name} عزیز، ارسال اسپم ممنوع است.\n"
        "اخطار {warn}/{max}"
    ),
    "banned":          "🚫 {name} به دلیل تخلف مکرر از گروه حذف شد.",
    "banned_temp":     "🚫 <b>{name}</b> به مدت <b>{duration}</b> از گروه بن شد.\n📌 دلیل: {reason}",
    "muted":           "🔇 {name} به مدت {duration} دقیقه محدود شد.",
    "request_handled": "✅ {response}",
    "learned":         "🧠 ممنون! این رو یاد گرفتم.",
    "welcome": (
        "👋 <b>{name}</b> عزیز، به گروه خوش اومدی! 🎉\n\n"
        "📌 برای صحبت با ربات منشنش کن یا روی پیامش ریپلای بزن."
    ),
    "left":        "👋 <b>{name}</b> از گروه خارج شد.",
    "no_media":    "🚫 {name}، سطح شما ({level}) اجازه ارسال مدیا ندارد.",
    "no_links":    "🚫 {name}، سطح شما ({level}) اجازه ارسال لینک ندارد.",
    "no_forward":  "🚫 {name}، سطح شما ({level}) اجازه فوروارد پیام ندارد.",
    "query_limit": "⏳ {name}، سهمیه روزانه سوال از ربات ({limit} عدد) تموم شد. فردا دوباره امتحان کن.",
}
