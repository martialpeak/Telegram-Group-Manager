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


async def _expire_warnings_job(context=None):
    import bot.db.database as db
    await db.expire_old_warnings(days=30)
    logger.info("🗑️ اخطارهای قدیمی پاک شدند.")


async def _daily_scheduler():
    """هر ۲۴ ساعت یه بار job های پاکسازی رو اجرا کن"""
    import asyncio
    while True:
        await asyncio.sleep(86400)  # ۲۴ ساعت
        try:
            await _expire_warnings_job()
            await db.cleanup_old_conversations(days=30)
            await db.cleanup_old_message_logs(days=90)
            logger.info("🗑️ پاکسازی روزانه DB انجام شد.")
        except Exception as e:
            logger.warning(f"daily scheduler error: {e}")


async def _announcements_scheduler(application):
    """
    بررسی دوره‌ای و اعلان خودکار آفرهای بازی رایگان و اخبار فناوری به گروه‌های عضو
    """
    import asyncio
    from bot.core.news_deals import get_free_games, get_tech_news
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton

    await asyncio.sleep(120)  # تأخیر ۲ دقیقه‌ای اولیه پس از شروع

    while True:
        try:
            # ۱. بررسی آفرهای بازی رایگان برای گروه‌های عضو
            game_chats = await db.get_subscribed_announcement_chats("games")
            if game_chats:
                games = await get_free_games(limit=1)
                if games:
                    latest = games[0]
                    g_title = latest["title"]
                    text = (
                        "🎁 <b>آفر جدید و بازی رایگان ویژه!</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"🕹 <b>{g_title}</b>\n"
                        "<blockquote>"
                        f"📱 <b>پلتفرم:</b> <b>{latest['platform']}</b>\n"
                        f"💰 <b>ارزش اصلی:</b> <b>{latest['worth']}</b> ➔ <b>۱۰۰٪ رایگان!</b>\n"
                        f"⏰ <b>مهلت دریافت:</b>\n   <b>{latest['end_date_shamsi']}</b>\n"
                        f"🔗 <a href=\"{latest['link']}\">جهت دریافت رایگان اینجا کلیک کنید</a>"
                        "</blockquote>\n\n"
                        "💡 <i>نکته: بازی پس از فعال‌سازی برای همیشه در اکانت شما باقی می‌ماند.</i>"
                    )
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("📥 دریافت مستقیم بازی", url=latest["link"])],
                        [InlineKeyboardButton("🎮 مشاهده سایر بازی‌های رایگان", callback_data="menu_games")],
                    ])
                    for chat_id in game_chats:
                        try:
                            st = await db.get_announcement_settings(chat_id)
                            if st.get("last_game_title") != g_title:
                                await application.bot.send_message(
                                    chat_id=chat_id,
                                    text=text,
                                    parse_mode="HTML",
                                    reply_markup=kb,
                                    disable_web_page_preview=True,
                                )
                                await db.update_last_announced(chat_id, "game", g_title)
                                await asyncio.sleep(1.5)
                        except Exception as ce:
                            logger.warning(f"Could not send game announcement to {chat_id}: {ce}")

            # ۲. بررسی اخبار فناوری و هوش مصنوعی برای گروه‌های عضو
            news_chats = await db.get_subscribed_announcement_chats("news")
            if news_chats:
                from bot.core.news_deals import has_persian_chars
                news_items = await get_tech_news(limit=4)
                # اولویت قطعی با اخباری است که به فارسی ترجمه شده باشند
                valid_item = None
                for it in news_items:
                    if has_persian_chars(it.get("title", "")):
                        valid_item = it
                        break
                if valid_item:
                    n_item = valid_item
                    n_title = n_item["title"]
                    source_label = f"🌐 {n_item['source']} (ترجمه هوشمند)" if n_item.get("is_foreign") else f"🇮🇷 {n_item['source']}"
                    n_text = (
                        "📢 <b>فوری / تازه‌ترین خبر فناوری و هوش مصنوعی:</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"📌 <b>{n_title}</b>\n"
                    )
                    if n_item.get("is_foreign") and n_item.get("orig_title") and n_item["orig_title"] != n_title:
                        n_text += f"<i>🌐 تیتر اصلی: {n_item['orig_title']}</i>\n"
                    n_text += (
                        "<blockquote>"
                        f"📝 {n_item['desc']}...\n\n"
                        f"🏷 <i>دسته‌بندی: {n_item['tag']} | منبع: {source_label}</i>\n"
                        f"🔗 <a href=\"{n_item['link']}\">مطالعه کامل خبر</a>"
                        "</blockquote>"
                    )
                    n_kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("📰 مطالعه کامل خبر", url=n_item["link"])],
                        [InlineKeyboardButton("🌐 سایر اخبار امروز", callback_data="news_cat_all")],
                    ])
                    for chat_id in news_chats:
                        try:
                            st = await db.get_announcement_settings(chat_id)
                            if st.get("last_news_title") != n_title:
                                await application.bot.send_message(
                                    chat_id=chat_id,
                                    text=n_text,
                                    parse_mode="HTML",
                                    reply_markup=n_kb,
                                    disable_web_page_preview=True,
                                )
                                await db.update_last_announced(chat_id, "news", n_title)
                                await asyncio.sleep(1.5)
                        except Exception as ce:
                            logger.warning(f"Could not send news announcement to {chat_id}: {ce}")

        except Exception as e:
            logger.warning(f"announcements scheduler error: {e}")

        await asyncio.sleep(7200)  # هر ۲ ساعت یکبار


async def post_init(application):
    await db.init_db()
    # scheduler برای پاک کردن اخطارهای قدیمی — هر ۲۴ ساعت
    import asyncio
    asyncio.create_task(_daily_scheduler())
    asyncio.create_task(_announcements_scheduler(application))
    logger.info("✅ پایگاه داده آماده شد.")
    logger.info("🚀 ربات در حال اجرا است.")

    # ── چک پیام آپدیت بعد از restart ────────────────
    import json, os
    notify_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".restart_notify.json")
    if os.path.exists(notify_file):
        try:
            with open(notify_file, encoding="utf-8") as f:
                info = json.load(f)
            os.remove(notify_file)

            text = (
                f"🚀 <b>ربات با موفقیت ری‌استارت شد!</b>\n\n"
                f"📌 نسخه قبلی: <code>{info['old_ver']}</code>\n"
                f"📌 نسخه جدید: <code>{info['new_ver']}</code>\n\n"
                f"📋 تغییرات:\n<code>{info['changes']}</code>"
            )
            # پیام به ادمین در همون چتی که /update زده
            await application.bot.send_message(
                chat_id=info["chat_id"],
                text=text,
                parse_mode="HTML",
            )
            logger.info(f"✅ پیام آپدیت به {info['chat_id']} ارسال شد.")
        except Exception as e:
            logger.warning(f"notify after restart failed: {e}")


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
    app.add_handler(CommandHandler("clear",      handlers.cmd_clear))
    app.add_handler(CommandHandler("testbtn",    handlers.cmd_testbtn))
    app.add_handler(CommandHandler("sync",       handlers.cmd_sync))
    app.add_handler(CommandHandler("recent",     handlers.cmd_recent))
    app.add_handler(CommandHandler("addchannel", handlers.cmd_addchannel))
    app.add_handler(CommandHandler("delchannel", handlers.cmd_delchannel))
    app.add_handler(CommandHandler("punishment", handlers.cmd_punishment))
    app.add_handler(CommandHandler("top", handlers.cmd_top))
    app.add_handler(CommandHandler("addfilter", handlers.cmd_addfilter))
    app.add_handler(CommandHandler("delfilter", handlers.cmd_delfilter))
    app.add_handler(CommandHandler("filters", handlers.cmd_filters))
    app.add_handler(CommandHandler("remind", handlers.cmd_remind))
    app.add_handler(CommandHandler("lock", handlers.cmd_lock))
    app.add_handler(CommandHandler("unlock", handlers.cmd_unlock))
    app.add_handler(CommandHandler("locks", handlers.cmd_locks))
    app.add_handler(CommandHandler("lockdown", handlers.cmd_lockdown))
    app.add_handler(CommandHandler("unlockdown", handlers.cmd_unlockdown))
    app.add_handler(CommandHandler("tr", handlers.cmd_translate))
    app.add_handler(CommandHandler("setpunishment", handlers.cmd_setpunishment))
    app.add_handler(CommandHandler("summary", handlers.cmd_summary))
    app.add_handler(CommandHandler("kholase", handlers.cmd_summary))
    app.add_handler(CommandHandler("info", handlers.cmd_info))
    app.add_handler(CommandHandler("whois", handlers.cmd_info))
    app.add_handler(CommandHandler("banned", handlers.cmd_banned))
    app.add_handler(CommandHandler("bans", handlers.cmd_banned))
    app.add_handler(CommandHandler("purge", handlers.cmd_purge))
    app.add_handler(CommandHandler("del", handlers.cmd_purge))
    app.add_handler(CommandHandler("help", handlers.cmd_help))
    app.add_handler(CommandHandler("rahnama", handlers.cmd_help))
    app.add_handler(CommandHandler("price", handlers.cmd_price))
    app.add_handler(CommandHandler("gheymat", handlers.cmd_price))
    app.add_handler(CommandHandler("gheimat", handlers.cmd_price))
    app.add_handler(CommandHandler("crypto", handlers.cmd_price))
    app.add_handler(CommandHandler("arz", handlers.cmd_price))
    app.add_handler(CommandHandler("time", handlers.cmd_datetime))
    app.add_handler(CommandHandler("date", handlers.cmd_datetime))
    app.add_handler(CommandHandler("saat", handlers.cmd_datetime))
    app.add_handler(CommandHandler("tarikh", handlers.cmd_datetime))
    app.add_handler(CommandHandler("calendar", handlers.cmd_datetime))
    app.add_handler(CommandHandler("profile", handlers.cmd_profile))
    app.add_handler(CommandHandler("me", handlers.cmd_profile))
    app.add_handler(CommandHandler("topkarma", handlers.cmd_topkarma))
    app.add_handler(CommandHandler("karma", handlers.cmd_topkarma))
    app.add_handler(CommandHandler("menu", handlers.cmd_menu))
    app.add_handler(CommandHandler("panel", handlers.cmd_menu))
    app.add_handler(CommandHandler("dashboard", handlers.cmd_menu))
    app.add_handler(CommandHandler("freegames", handlers.cmd_free_games))
    app.add_handler(CommandHandler("games", handlers.cmd_free_games))
    app.add_handler(CommandHandler("deals", handlers.cmd_free_games))
    app.add_handler(CommandHandler("bazi", handlers.cmd_free_games))
    app.add_handler(CommandHandler("technews", handlers.cmd_tech_news))
    app.add_handler(CommandHandler("news", handlers.cmd_tech_news))
    app.add_handler(CommandHandler("akhbar", handlers.cmd_tech_news))
    app.add_handler(CommandHandler("ainews", handlers.cmd_tech_news))
    app.add_handler(CommandHandler("vpnnews", handlers.cmd_tech_news))
    app.add_handler(CommandHandler("kharejinews", handlers.cmd_tech_news))
    app.add_handler(CommandHandler("foreignnews", handlers.cmd_tech_news))
    app.add_handler(CommandHandler("autogames", handlers.cmd_autogames))
    app.add_handler(CommandHandler("autonews", handlers.cmd_autonews))
    app.add_handler(CommandHandler("weather", handlers.cmd_weather))
    app.add_handler(CommandHandler("hava", handlers.cmd_weather))
    app.add_handler(CommandHandler("havashenasi", handlers.cmd_weather))
    app.add_handler(CommandHandler("ocr", handlers.cmd_ocr))
    app.add_handler(CommandHandler("read", handlers.cmd_ocr))
    app.add_handler(CommandHandler("matn", handlers.cmd_ocr))
    app.add_handler(CommandHandler("متن", handlers.cmd_ocr))
    app.add_handler(CommandHandler("اسکن", handlers.cmd_ocr))

    # ── Callback ها ───────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(handlers.on_report_callback,  pattern=r"^rpt_"))
    app.add_handler(CallbackQueryHandler(handlers.on_general_callback, pattern=r"^(rules|myrank_|tbtn_|help_|ainf_|qunb_|prc_|dt_|menu_|prof_|game_|news_|weather_|ocr_)"))
    app.add_handler(CallbackQueryHandler(handlers.on_feedback_callback, pattern=r"^fb_"))
    app.add_handler(CallbackQueryHandler(handlers.on_feedback_callback, pattern=r"^vote_"))
    app.add_handler(CallbackQueryHandler(handlers.on_admin_answer_callback, pattern=r"^adm_"))
    app.add_handler(CallbackQueryHandler(handlers.on_upgrade_callback, pattern=r"^upg_"))
    app.add_handler(CallbackQueryHandler(handlers.on_moderation_review_callback, pattern=r"^rev_"))
    # بن سریع از پیام خروج — pattern qban_
    app.add_handler(CallbackQueryHandler(handlers.on_quick_ban_callback, pattern=r"^qban_"))
    app.add_handler(CallbackQueryHandler(handlers.on_captcha_callback, pattern=r"^captcha_"))
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

    # ── یادگیری real-time از کانال‌های آموزشی ──────────────────────────────────
    # channel_post از کانال‌ها، message از گروه‌ها — هر دو رو هندل کن
    app.add_handler(
        MessageHandler(
            (filters.TEXT & ~filters.COMMAND & filters.ChatType.CHANNEL),
            handlers.on_channel_message,
        ),
        group=3,
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
