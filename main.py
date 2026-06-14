"""
نقطه ورود اصلی ربات
"""

import logging
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    filters,
)

from config import TELEGRAM_BOT_TOKEN
import bot.db.database as db
import bot.handlers as handlers
import settings_panel

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(application):
    await db.init_db()
    logger.info("✅ پایگاه داده آماده شد.")
    logger.info("🚀 ربات در حال اجرا است.")


def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN تنظیم نشده! فایل .env را بررسی کنید.")
        return

    app = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # ── پنل تنظیمات ──────────────────────────────────────────────────────────
    settings_panel.register(app)

    # ── دستورات ──────────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",      handlers.cmd_start))
    app.add_handler(CommandHandler("search",     handlers.cmd_search))
    app.add_handler(CommandHandler("learn",      handlers.cmd_learn))
    app.add_handler(CommandHandler("warn",       handlers.cmd_warn))
    app.add_handler(CommandHandler("ban",        handlers.cmd_ban))
    app.add_handler(CommandHandler("unban",      handlers.cmd_unban))
    app.add_handler(CommandHandler("mute",       handlers.cmd_mute))
    app.add_handler(CommandHandler("unmute",     handlers.cmd_unmute))
    app.add_handler(CommandHandler("unwarn",     handlers.cmd_unwarn))
    app.add_handler(CommandHandler("warnings",   handlers.cmd_warnings))
    app.add_handler(CommandHandler("report",     handlers.cmd_report))
    app.add_handler(CommandHandler("reports",    handlers.cmd_reports))
    app.add_handler(CommandHandler("stats",      handlers.cmd_stats))
    app.add_handler(CommandHandler("violations", handlers.cmd_violations))
    app.add_handler(CommandHandler("mystats",    handlers.cmd_mystats))
    app.add_handler(CommandHandler("setlevel",   handlers.cmd_setlevel))
    app.add_handler(CommandHandler("levels",     handlers.cmd_levels))
    app.add_handler(CommandHandler("myrank",     handlers.cmd_myrank))
    app.add_handler(CommandHandler("tagall",     handlers.cmd_tagall))

    # ── Callback ها ───────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(handlers.on_report_callback,  pattern=r"^rpt_"))
    app.add_handler(CallbackQueryHandler(handlers.on_general_callback, pattern=r"^(rules|myrank_)"))
    app.add_handler(CallbackQueryHandler(handlers.on_feedback_callback, pattern=r"^fb_"))
    app.add_handler(CallbackQueryHandler(handlers.on_feedback_callback, pattern=r"^vote_"))
    app.add_handler(CallbackQueryHandler(handlers.on_admin_answer_callback, pattern=r"^adm_"))
    app.add_handler(CallbackQueryHandler(handlers.on_upgrade_callback, pattern=r"^upg_"))
    # پاسخ متنی ادمین به سوال — group=9 قبل از settings (group=10)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_admin_answer_text),
        group=9,
    )

    # ── پیام متنی ─────────────────────────────────────────────────────────────
    # group=0: تصحیح (باید قبل از on_message اجرا بشه)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_correction),
        group=0,
    )
    # group=1: پردازش اصلی
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_message),
        group=1,
    )

    # ── مدیا، فوروارد، استیکر ────────────────────────────────────────────────
    media_filter = (
        filters.PHOTO | filters.VIDEO | filters.Document.ALL |
        filters.AUDIO | filters.VOICE | filters.VIDEO_NOTE |
        filters.Sticker.ALL | filters.ANIMATION | filters.FORWARDED
    )
    app.add_handler(
        MessageHandler(media_filter, handlers.on_media_message),
        group=2,
    )

    # ── عضو جدید و خروج ──────────────────────────────────────────────────────
    app.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handlers.on_new_member)
    )
    app.add_handler(
        MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, handlers.on_left_member)
    )

    logger.info("🤖 ربات شروع به polling کرد...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
