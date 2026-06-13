import os
from dotenv import load_dotenv

load_dotenv()

# ── تلگرام ───────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ── زبان ربات ─────────────────────────────────────────
BOT_LANG = os.getenv("BOT_LANG", "fa")

# ── Gemini AI ─────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

# ── مدیریت گروه ──────────────────────────────────────
MAX_WARNINGS       = int(os.getenv("MAX_WARNINGS", "3"))
SPAM_TIME_WINDOW   = int(os.getenv("SPAM_TIME_WINDOW", "60"))
SPAM_MAX_MESSAGES  = int(os.getenv("SPAM_MAX_MESSAGES", "5"))
MIN_CONFIDENCE     = float(os.getenv("MIN_CONFIDENCE", "0.60"))

# ── یادگیری ──────────────────────────────────────────
LEARNING_ENABLED    = os.getenv("LEARNING_ENABLED", "true").lower() == "true"
LEARNING_BATCH_SIZE = int(os.getenv("LEARNING_BATCH_SIZE", "50"))
LEARNING_MIN_SCORE  = float(os.getenv("LEARNING_MIN_SCORE", "0.75"))
SEARCH_TOP_K        = int(os.getenv("SEARCH_TOP_K", "5"))

# ── ادمین‌ها ──────────────────────────────────────────
_raw = os.getenv("ADMIN_IDS", "")
ADMIN_IDS = [int(x.strip()) for x in _raw.split(",") if x.strip().isdigit()]

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
