import os
from dotenv import load_dotenv

load_dotenv()

# ── تلگرام ───────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ── زبان ربات ─────────────────────────────────────────
# fa = فارسی  |  en = English
BOT_LANG = os.getenv("BOT_LANG", "fa")

# ── Ollama (هوش مصنوعی محلی) ─────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
AI_MODEL        = os.getenv("AI_MODEL", "llama3")          # مدل اصلی
EMBED_MODEL     = os.getenv("EMBED_MODEL", "nomic-embed-text")  # مدل embedding

# ── مدیریت گروه ──────────────────────────────────────
MAX_WARNINGS       = int(os.getenv("MAX_WARNINGS", "3"))
SPAM_TIME_WINDOW   = int(os.getenv("SPAM_TIME_WINDOW", "60"))
SPAM_MAX_MESSAGES  = int(os.getenv("SPAM_MAX_MESSAGES", "5"))
MIN_CONFIDENCE     = float(os.getenv("MIN_CONFIDENCE", "0.60"))

# ── یادگیری ──────────────────────────────────────────
LEARNING_ENABLED        = os.getenv("LEARNING_ENABLED", "true").lower() == "true"
# هر چند پیام یک‌بار مدل fine-tune اطلاعاتش رو آپدیت کنه
LEARNING_BATCH_SIZE     = int(os.getenv("LEARNING_BATCH_SIZE", "50"))
# کمترین امتیاز برای ذخیره پاسخ به عنوان دانش معتبر
LEARNING_MIN_SCORE      = float(os.getenv("LEARNING_MIN_SCORE", "0.75"))
# حداکثر نتیجه جستجو
SEARCH_TOP_K            = int(os.getenv("SEARCH_TOP_K", "5"))

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
    "banned_temp":     "🚫 *{name}* به مدت *{duration}* از گروه بن شد.\n📌 دلیل: {reason}",
    "muted":           "🔇 {name} به مدت {duration} دقیقه محدود شد.",
    "request_handled": "✅ {response}",
    "learned":         "🧠 ممنون! این رو یاد گرفتم.",
    # ورود و خروج
    "welcome": (
        "👋 *{name}* عزیز، به گروه خوش اومدی! 🎉\n\n"
        "📌 برای صحبت با ربات منشنش کن یا روی پیامش ریپلای بزن."
    ),
    "left":   "👋 *{name}* از گروه خارج شد.",
    # سطح کاربری
    "no_media":    "🚫 {name}، سطح شما ({level}) اجازه ارسال مدیا ندارد.",
    "no_links":    "🚫 {name}، سطح شما ({level}) اجازه ارسال لینک ندارد.",
    "no_forward":  "🚫 {name}، سطح شما ({level}) اجازه فوروارد پیام ندارد.",
    "query_limit": "⏳ {name}، سهمیه روزانه سوال از ربات ({limit} عدد) تموم شد. فردا دوباره امتحان کن.",
}
