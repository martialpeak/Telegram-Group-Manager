"""
سیستم چندزبانه ربات
Bot language system — fa (Persian) / en (English)
"""

import os
from dotenv import dotenv_values

_ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")


def get_lang() -> str:
    vals = dotenv_values(_ENV_PATH)
    lang = vals.get("BOT_LANG", os.getenv("BOT_LANG", "fa")).lower()
    return lang if lang in ("fa", "en") else "fa"


# ── string table ─────────────────────────────────────────────────────────────

_STRINGS: dict[str, dict[str, str]] = {

    # ── welcome / left ───────────────────────────────
    "welcome": {
        "fa": "👋 *{name}* عزیز، به گروه خوش اومدی! 🎉\n\n📌 برای صحبت با ربات منشنش کن یا روی پیامش ریپلای بزن.",
        "en": "👋 Welcome *{name}*! 🎉\n\n📌 Mention the bot or reply to its messages to ask questions.",
    },
    "left": {
        "fa": "👋 *{name}* از گروه خارج شد.",
        "en": "👋 *{name}* has left the group.",
    },

    # ── warnings / punishments ───────────────────────
    "warn_insult": {
        "fa": "⚠️ {name} عزیز، استفاده از کلمات توهین‌آمیز مجاز نیست.\nاخطار {warn}/{max} — تکرار منجر به حذف از گروه می‌شود.",
        "en": "⚠️ {name}, using offensive language is not allowed.\nWarning {warn}/{max} — repeating will result in removal.",
    },
    "warn_spam": {
        "fa": "⚠️ {name} عزیز، ارسال اسپم ممنوع است.\nاخطار {warn}/{max}",
        "en": "⚠️ {name}, sending spam is not allowed.\nWarning {warn}/{max}",
    },
    "banned": {
        "fa": "🚫 {name} به دلیل تخلف مکرر از گروه حذف شد.",
        "en": "🚫 {name} has been removed from the group due to repeated violations.",
    },
    "banned_temp": {
        "fa": "🚫 *{name}* به مدت *{duration}* از گروه بن شد.\n📌 دلیل: {reason}",
        "en": "🚫 *{name}* has been banned for *{duration}*.\n📌 Reason: {reason}",
    },
    "muted": {
        "fa": "🔇 {name} به مدت {duration} دقیقه محدود شد.",
        "en": "🔇 {name} has been muted for {duration} minutes.",
    },

    # ── level restrictions ───────────────────────────
    "no_media": {
        "fa": "🚫 {name}، سطح شما ({level}) اجازه ارسال مدیا ندارد.",
        "en": "🚫 {name}, your level ({level}) does not allow sending media.",
    },
    "no_links": {
        "fa": "🚫 {name}، سطح شما ({level}) اجازه ارسال لینک ندارد.",
        "en": "🚫 {name}, your level ({level}) does not allow sending links.",
    },
    "no_forward": {
        "fa": "🚫 {name}، سطح شما ({level}) اجازه فوروارد پیام ندارد.",
        "en": "🚫 {name}, your level ({level}) does not allow forwarding messages.",
    },
    "query_limit": {
        "fa": "⏳ {name}، سهمیه روزانه سوال از ربات ({limit} عدد) تموم شد. فردا دوباره امتحان کن.",
        "en": "⏳ {name}, you have reached your daily bot query limit ({limit}). Try again tomorrow.",
    },

    # ── upgrade ──────────────────────────────────────
    "upgraded": {
        "fa": "🎉 {name} به سطح {level} ارتقاء پیدا کرد!",
        "en": "🎉 {name} has been upgraded to {level}!",
    },

    # ── misc ─────────────────────────────────────────
    "request_handled": {
        "fa": "✅ {response}",
        "en": "✅ {response}",
    },
    "learned": {
        "fa": "🧠 ممنون! این رو یاد گرفتم.",
        "en": "🧠 Got it! I learned from your correction.",
    },

    # ── report ───────────────────────────────────────
    "report_confirm": {
        "fa": "✅ گزارش شما ثبت شد و برای ادمین‌ها ارسال شد.\n🔖 شماره گزارش: #{report_id}",
        "en": "✅ Your report has been submitted to the admins.\n🔖 Report ID: #{report_id}",
    },
    "report_self": {
        "fa": "❌ نمیتونی به خودت گزارش بدی.",
        "en": "❌ You cannot report yourself.",
    },
    "report_admin": {
        "fa": "❌ گزارش ادمین ممکن نیست.",
        "en": "❌ You cannot report an admin.",
    },
    "report_limit": {
        "fa": "⏳ امروز به حد مجاز گزارش رسیدی (۳ عدد). فردا دوباره امتحان کن.",
        "en": "⏳ You have reached your daily report limit (3). Try again tomorrow.",
    },
    "report_how": {
        "fa": "📌 روی پیامی که می‌خوای گزارش بدی ریپلای بزن، بعد /report بنویس.",
        "en": "📌 Reply to the message you want to report, then type /report.",
    },

    # ── admin notifications ──────────────────────────
    "report_notify": {
        "fa": (
            "🚨 *گزارش جدید — #{report_id}*\n\n"
            "👤 گزارش‌دهنده: {reporter}\n"
            "🎯 گزارش‌شده: {reported}\n"
            "📌 دلیل: {reason}\n"
            "💬 متن پیام:\n`{text}`\n\n"
            "📎 لینک: [مشاهده]({link})"
        ),
        "en": (
            "🚨 *New Report — #{report_id}*\n\n"
            "👤 Reporter: {reporter}\n"
            "🎯 Reported: {reported}\n"
            "📌 Reason: {reason}\n"
            "💬 Message:\n`{text}`\n\n"
            "📎 Link: [View]({link})"
        ),
    },

    # ── settings panel buttons ───────────────────────
    "settings_title": {
        "fa": "⚙️ *پنل تنظیمات ربات*\nیک مورد را برای تغییر انتخاب کنید:",
        "en": "⚙️ *Bot Settings Panel*\nSelect a setting to change:",
    },
    "settings_current": {
        "fa": "⚙️ *تنظیمات فعلی:*",
        "en": "⚙️ *Current Settings:*",
    },
    "settings_saved": {
        "fa": "✅ `{key}` به `{value}` تغییر کرد.\n\n⚠️ برای اعمال تغییرات ربات را ری‌استارت کنید:\n`sudo systemctl restart telegram-bot`",
        "en": "✅ `{key}` changed to `{value}`.\n\n⚠️ Restart the bot to apply changes:\n`sudo systemctl restart telegram-bot`",
    },
    "settings_prompt": {
        "fa": "✏️ *تغییر {desc}*\n\nمقدار فعلی: `{current}`\n\nمقدار جدید را بنویسید یا /cancel:",
        "en": "✏️ *Change {desc}*\n\nCurrent value: `{current}`\n\nEnter new value or /cancel:",
    },
    "settings_invalid": {
        "fa": "❌ {error}\nدوباره مقدار را وارد کنید یا /cancel بزنید:",
        "en": "❌ {error}\nEnter the value again or type /cancel:",
    },
    "settings_cancelled": {
        "fa": "❌ لغو شد.",
        "en": "❌ Cancelled.",
    },

    # ── myrank / mystats ─────────────────────────────
    "myrank_title": {
        "fa": "👤 {name}\n\n🏅 سطح: {level}\n📸 مدیا: {media}\n🔗 لینک امروز: {links}\n↩️ فوروارد امروز: {fwds}\n❓ سوال امروز: {queries}\n💬 کل پیام‌ها: {total}\n⚠️ اخطار: {warns}/3{upgrade}",
        "en": "👤 {name}\n\n🏅 Level: {level}\n📸 Media: {media}\n🔗 Links today: {links}\n↩️ Forwards today: {fwds}\n❓ Bot queries today: {queries}\n💬 Total messages: {total}\n⚠️ Warnings: {warns}/3{upgrade}",
    },
    "upgrade_progress": {
        "fa": "\n📈 تا ارتقاء به {next}: {remaining} پیام",
        "en": "\n📈 Until upgrade to {next}: {remaining} messages",
    },
    "mystats_title": {
        "fa": "📊 *آمار روزانه*",
        "en": "📊 *Daily Stats*",
    },

    # ── rules (popup) ────────────────────────────────
    "rules_text": {
        "fa": "📋 قوانین:\n۱. احترام به همه\n۲. بدون اسپم و تبلیغ\n۳. بدون توهین\n۴. ارسال محتوای مناسب",
        "en": "📋 Rules:\n1. Respect everyone\n2. No spam or ads\n3. No offensive language\n4. Post appropriate content",
    },
    "rules_btn": {
        "fa": "📋 قوانین گروه",
        "en": "📋 Group Rules",
    },
    "rank_btn": {
        "fa": "🏅 سطح من",
        "en": "🏅 My Level",
    },

    # ── start ────────────────────────────────────────
    "start_title": {
        "fa": "🤖 *ربات هوشمند مدیریت گروه*",
        "en": "🤖 *Smart Group Manager Bot*",
    },
    "start_ask": {
        "fa": "📌 *برای پرسیدن سوال:*\n• منشن: `@{bot} سوالت`\n• یا ریپلای روی پیام ربات",
        "en": "📌 *To ask a question:*\n• Mention: `@{bot} your question`\n• Or reply to the bot's message",
    },
    "start_admin_cmds": {
        "fa": "📌 *دستورات:*",
        "en": "📌 *Commands:*",
    },

    # ── group only ───────────────────────────────────
    "group_only": {
        "fa": "این دستور فقط در گروه کار می‌کند.",
        "en": "This command only works in a group.",
    },
}


def t(key: str, **kwargs) -> str:
    """
    ترجمه یک کلید با پارامترهای اختیاری.
    Translation of a key with optional format parameters.

    Usage:
        t("welcome", name="Ali")
        t("warn_insult", name="@user", warn=1, max=3)
    """
    lang    = get_lang()
    entry   = _STRINGS.get(key, {})
    text    = entry.get(lang) or entry.get("fa") or key
    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError:
            pass
    return text
