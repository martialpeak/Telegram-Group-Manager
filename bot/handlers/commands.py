"""
دستورات ربات تلگرام
"""

import logging
from datetime import datetime, timedelta, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatPermissions
from telegram.ext import ContextTypes
from telegram.constants import ChatType

from config import MAX_WARNINGS, ADMIN_IDS
import bot.db.database as db
from bot.core import moderation as mod
from bot.core.knowledge_engine import learn_from_feedback
from bot.core.user_levels import (
    get_config, is_valid_level, level_label, level_summary, LEVEL_ORDER,
    next_auto_level,
)
from bot.utils.helpers import mention, send_and_delete, esc, parse_duration, format_duration
from i18n import t

logger = logging.getLogger(__name__)


def _is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS




# ─── helper: پیدا کردن target از reply یا user_id ───────────────────────────

async def _get_target(update, context) -> tuple:
    """
    برمی‌گردونه (user_id, full_name, mention_str) یا (None, None, None)
    اولویت تشخیص:
      ۱. reply → کاربر ریپلای‌شده
      ۲. user_id عددی → مستقیم
      ۳. @username → اول از DB (message_log) وگرنه از تلگرام get_chat
    """
    from bot.utils.helpers import mention as _mention
    if update.message.reply_to_message:
        u = update.message.reply_to_message.from_user
        return u.id, u.full_name, _mention(u)
    args = list(context.args) if context.args else []
    if not args:
        return None, None, None

    raw = args[0]
    chat_id = update.message.chat_id

    # عدد — user_id مستقیم
    try:
        uid = int(raw)
        return uid, str(uid), f"کاربر <code>{uid}</code>"
    except ValueError:
        pass

    # @username — اول از DB (کاربرایی که ربات قبلاً تو گروه دیدتشون)
    username = raw.lstrip("@")
    if username:
        uname_lower = username.lower()
        try:
            found = await db.find_user_by_username(uname_lower, chat_id)
            if found:
                return (
                    found["user_id"],
                    found["full_name"] or username,
                    f"@{username}",
                )
        except Exception:
            pass

        # fallback: مستقیم از تلگرام (فقط اگه ربات قبلاً باهاش تعامل داشته)
        try:
            chat_member = await context.bot.get_chat(f"@{username}")
            uid = chat_member.id
            name = getattr(chat_member, "full_name", None) or username
            return uid, name, f"@{username}"
        except Exception:
            pass

    return None, None, None



# ─── طراحی مدرن و شکیل رابط کاربری منوها ─────────────────────────────────────

def get_start_text(bot_username: str, user, chat_type: ChatType, level: str = None, q_limit: str = None, rank_name: str = None) -> str:
    bot_link = f"@{bot_username}" if bot_username else "ربات"
    if chat_type == ChatType.PRIVATE:
        return (
            "🤖 <b>دستیار و مدیر هوشمند گروه</b>\n\n"
            "<blockquote>"
            "مجهز به هوش مصنوعی ترکیبی (Groq + Gemini)، سیستم شنود و نظارت ویس با Whisper، "
            "خلاصه‌ساز گفت‌وگوها، مدیریت هوشمند تخلفات و پایگاه دانش خودآموز."
            "</blockquote>\n\n"
            "💡 <b>نحوه پرسش و پاسخ با هوش مصنوعی:</b>\n"
            f"در گروه کافیست روی پیام ربات ریپلای بزنید یا بنویسید:\n"
            f"👉 <code>{bot_link} سوال شما</code>\n\n"
            "👇 <i>برای مشاهده راهنمای دستورات، بخش مورد نظر را لمس کنید:</i>"
        )
    else:
        rank_display = rank_name if rank_name and rank_name != "clean" else "عادی و پاک"
        lvl_lbl = level_label(level) if level else "ساده"
        q_disp = q_limit or "نامحدود"
        return (
            "🤖 <b>ربات هوشمند مدیریت گروه</b>\n\n"
            "<blockquote>"
            f"👤 کاربر: {mention(user)}\n"
            f"🏅 سطح کاربری: <b>{lvl_lbl}</b>\n"
            f"❓ سهمیه سوال امروز: <b>{q_disp}</b>\n"
            f"🏆 وضعیت انضباطی: <b>{rank_display}</b>"
            "</blockquote>\n\n"
            f"💬 <b>پرسش از AI:</b> ریپلای روی پیام ربات یا منشن <code>{bot_link}</code>\n\n"
            "👇 <i>برای دسترسی سریع به دستورات، دکمه‌های زیر را لمس کنید:</i>"
        )


def get_start_keyboard(bot_username: str, is_admin: bool, is_private: bool, user_id: int) -> InlineKeyboardMarkup:
    rows = []
    if is_private and bot_username:
        rows.append([
            InlineKeyboardButton("➕ افزودن ربات به گروه", url=f"https://t.me/{bot_username}?startgroup=true")
        ])
    rows.append([
        InlineKeyboardButton("👤 دستورات کاربران", callback_data="help_user"),
        InlineKeyboardButton("🛡️ دستورات ادمین", callback_data="help_admin"),
    ])
    rows.append([
        InlineKeyboardButton("🤖 امکانات هوش مصنوعی", callback_data="help_ai"),
    ])
    if not is_private:
        rows.append([
            InlineKeyboardButton("📊 پروفایل و وضعیت من", callback_data=f"myrank_{user_id}")
        ])
    return InlineKeyboardMarkup(rows)


def get_help_user_text() -> str:
    return (
        "📖 <b>راهنمای دستورات اعضای گروه:</b>\n\n"
        "<blockquote>"
        "🔹 <code>/price [نام کالا یا ارز]</code> ▫️ استعلام قیمت روز کالاها (ترب)، طلا، دلار و رمزارزها\n"
        "🔹 <code>/time</code> ▫️ تقویم خورشیدی و میلادی، روز هفته و ساعت رسمی ایران\n"
        "🔹 <code>/info</code> ▫️ شناسنامه، سطح و آمار کامل شما یا کاربر دیگر\n"
        "🔹 <code>/myrank</code> ▫️ مشاهده پروفایل، رتبه و وضعیت جریمه\n"
        "🔹 <code>/mystats</code> ▫️ آمار پیام‌ها، لینک‌ها و فعالیت روزانه شما\n"
        "🔹 <code>/levels</code> ▫️ راهنمای سطوح کاربری و پیش‌نیازهای ارتقاء\n"
        "🔹 <code>/summary</code> ▫️ خلاصه‌سازی مباحث اخیر گروه با هوش مصنوعی\n"
        "🔹 <code>/punishment</code> ▫️ مشاهده سیستم رنک‌های جریمه گروه\n"
        "🔹 <code>/report</code> ▫️ گزارش پیام متخلف به ادمین‌ها (ریپلای)\n"
        "🔹 <code>/clear</code> ▫️ پاکسازی حافظه موقت گفتگو با هوش مصنوعی"
        "</blockquote>\n\n"
        "💡 <i>روی هر دستور ضربه بزنید تا در متن چت کپی شود.</i>"
    )


def get_help_admin_text() -> str:
    return (
        "🛡️ <b>راهنمای دستورات مدیریت و نظارت:</b>\n\n"
        "<blockquote>"
        "⚠️ <b>اقدامات نظارتی و انضباطی:</b>\n"
        "• <code>/info</code> ▫️ شناسنامه کاربر + دکمه‌های اخطار، میوت و بن سریع\n"
        "• <code>/banned</code> ▫️ لیست افراد بن‌شده اخیر + دکمه آنبن فوری\n"
        "• <code>/purge [تعداد]</code> ▫️ پاکسازی سریع پیام‌ها (ریپلای یا تعداد)\n"
        "• <code>/warn</code> ▫️ اخطار دستی به کاربر (ریپلای)\n"
        "• <code>/unwarn</code> ▫️ پاک کردن یک اخطار (ریپلای)\n"
        "• <code>/mute [دقیقه]</code> ▫️ سکوت موقت کاربر (ریپلای)\n"
        "• <code>/unmute</code> ▫️ لغو سکوت و آزادسازی (ریپلای)\n"
        "• <code>/ban [مدت] [دلیل]</code> ▫️ اخراج/مسدودسازی کاربر\n"
        "• <code>/unban [آیدی/ریپلای]</code> ▫️ لغو مسدودیت کاربر\n\n"
        "📊 <b>آمار و پایش گروه:</b>\n"
        "• <code>/stats</code> ▫️ آمار کلی پیام‌ها و اعضا\n"
        "• <code>/violations</code> ▫️ گزارش آمار تخلفات\n"
        "• <code>/reports</code> ▫️ بررسی پیام‌های گزارش‌شده\n"
        "• <code>/warnings</code> ▫️ مشاهده لیست اخطارهای کاربران\n\n"
        "🔒 <b>امنیت و قفل‌ها:</b>\n"
        "• <code>/lock</code> | <code>/unlock</code> ▫️ قفل مدیا (عکس، ویدیو، ویس، استیکر)\n"
        "• <code>/locks</code> ▫️ مشاهده وضعیت قفل‌های فعال\n"
        "• <code>/lockdown</code> ▫️ قفل اضطراری کل گروه\n\n"
        "⚙️ <b>سیستم و هوش مصنوعی:</b>\n"
        "• <code>/price</code> ▫️ استعلام قیمت کالاها (ترب)، دلار، طلا و کریپتو\n"
        "• <code>/summary [تعداد]</code> ▫️ خلاصه گفتگوهای اخیر با AI\n"
        "• <code>/settings</code> ▫️ پنل شیشه‌ای تنظیمات\n"
        "• <code>/update</code> ▫️ آپدیت آنلاین از GitHub"
        "</blockquote>"
    )


def get_help_ai_text() -> str:
    return (
        "🤖 <b>امکانات پیشرفته هوش مصنوعی ربات:</b>\n\n"
        "<blockquote>"
        "🛍️ <b>استعلام قیمت کالا و مشاوره خرید (/price):</b>\n"
        "اتصال زنده به ترب برای دریافت قیمت انواع لوازم خانگی (مثل جاروبرقی)، گوشی، لپ‌تاپ و قطعات با لینک خرید. به همراه نرخ لحظه‌ای طلا، سکه، دلار و کریپتو (BTC/TON).\n\n"
        "🎙️ <b>فحاشی‌یاب و اسپم‌یاب صوتی (Groq Whisper):</b>\n"
        "پیام‌های صوتی (ویس) در کمتر از یک ثانیه رونویسی و تحلیل می‌شوند؛ در صورت وجود فحاشی یا تبلیغ صوتی، ویس فوراً حذف و اخطار صادر می‌شود.\n\n"
        "📊 <b>خلاصه‌ساز هوشمند گفت‌وگوها (/summary):</b>\n"
        "با دستور <code>/summary</code> خلاصه‌ای منظم از موضوعات مهم و سوالات مطرح‌شده در پیام‌های اخیر دریافت کنید.\n\n"
        "💬 <b>پاسخ‌گویی و مشاوره تخصصی:</b>\n"
        "پاسخ دقیق به سوالات فنی، شبکه، مقایسه خرید محصولات و اطلاعات عمومی با ریپلای یا منشن.\n\n"
        "🧠 <b>پایگاه دانش خودآموز:</b>\n"
        "پاسخ‌های تأییدشده توسط اعضا ذخیره می‌شوند تا به سوالات تکراری بدون معطلی پاسخ داده شود."
        "</blockquote>"
    )


def get_help_keyboard(tab: str, is_admin: bool) -> InlineKeyboardMarkup:
    rows = []
    btns = []
    if tab != "user":
        btns.append(InlineKeyboardButton("👤 دستورات کاربران", callback_data="help_user"))
    if tab != "admin":
        btns.append(InlineKeyboardButton("🛡️ دستورات ادمین", callback_data="help_admin"))
    if tab != "ai":
        btns.append(InlineKeyboardButton("🤖 امکانات AI", callback_data="help_ai"))

    for i in range(0, len(btns), 2):
        rows.append(btns[i:i+2])

    rows.append([InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="help_main")])
    return InlineKeyboardMarkup(rows)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_username = context.bot.username
    user = update.message.from_user
    chat = update.message.chat

    level_val = None
    q_val = None
    rank_name = None

    if chat.type != ChatType.PRIVATE:
        level_val = await db.get_user_level(user.id, chat.id)
        cfg = get_config(level_val)
        q_val = "نامحدود" if cfg.daily_queries == -1 else str(cfg.daily_queries)
        from bot.core.punishment_ranks import get_rank_name
        rank = await db.get_punishment_rank(user.id, chat.id)
        rank_name = get_rank_name(rank)

    text = get_start_text(
        bot_username=bot_username,
        user=user,
        chat_type=chat.type,
        level=level_val,
        q_limit=q_val,
        rank_name=rank_name,
    )
    is_adm = _is_admin(user.id)
    is_priv = (chat.type == ChatType.PRIVATE)
    kb = get_start_keyboard(bot_username, is_adm, is_priv, user.id)

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=kb,
    )


# ─── /myrank ─────────────────────────────────────────────────────────────────

async def cmd_myrank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    chat = update.message.chat
    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text(t("group_only"))
        return

    level    = await db.get_user_level(user.id, chat.id)
    cfg      = get_config(level)
    today_q  = await db.get_query_count(user.id, chat.id)
    today_lk = await db.get_daily_action(user.id, chat.id, "link")
    today_fw = await db.get_daily_action(user.id, chat.id, "forward")
    total_m  = await db.get_message_count(user.id, chat.id)
    warns    = await db.get_warnings(user.id, chat.id)
    points   = await db.get_points(user.id, chat.id)

    limit_q  = "نامحدود" if cfg.daily_queries  == -1 else f"{today_q}/{cfg.daily_queries}"
    limit_lk = "ممنوع"   if cfg.daily_links    ==  0 else ("نامحدود" if cfg.daily_links    == -1 else f"{today_lk}/{cfg.daily_links}")
    limit_fw = "ممنوع"   if cfg.daily_forwards ==  0 else ("نامحدود" if cfg.daily_forwards == -1 else f"{today_fw}/{cfg.daily_forwards}")

    next_lv      = next_auto_level(level)
    upgrade_line = ""
    if next_lv and cfg.auto_upgrade_msgs:
        remaining    = max(0, cfg.auto_upgrade_msgs - total_m)
        upgrade_line = f"\n📈 تا ارتقاء به {level_label(next_lv)}: {remaining} پیام"

    # آستانه امتیازی
    from bot.handlers.messages import UPGRADE_THRESHOLDS
    points_line = ""
    if level in UPGRADE_THRESHOLDS:
        threshold, next_pts_lv = UPGRADE_THRESHOLDS[level]
        points_line = f"\n⭐ امتیاز: {points} | آستانه بعدی: {threshold}"
    else:
        points_line = f"\n⭐ امتیاز: {points}"

    # رنک جریمه
    from bot.core.punishment_ranks import get_rank_name, get_rank_config
    punishment_rank = await db.get_punishment_rank(user.id, chat.id)
    if punishment_rank and punishment_rank != "clean":
        rank_info = get_rank_config(punishment_rank)
        punishment_line = f"\n🔒 رنک جریمه: {get_rank_name(punishment_rank)}"
    else:
        punishment_line = ""

    tag = mention(user)
    await update.message.reply_text(
        f"👤 <b>پروفایل کاربری {tag}</b>\n\n"
        f"<blockquote>"
        f"🏅 سطح کاربری: <b>{level_label(level)}</b>\n"
        f"📸 ارسال مدیا: {'مجاز ✅' if cfg.can_media else 'مسدود ❌'}\n"
        f"🔗 لینک امروز: <code>{limit_lk}</code>\n"
        f"↩️ فوروارد امروز: <code>{limit_fw}</code>\n"
        f"❓ سهمیه سوال: <code>{limit_q}</code>\n"
        f"💬 کل پیام‌ها: <b>{total_m}</b>\n"
        f"⚠️ اخطارها: <b>{warns}/3</b>"
        f"{points_line}"
        f"{upgrade_line}"
        f"{punishment_line}"
        f"</blockquote>",
        parse_mode="HTML",
    )


# ─── /mystats ────────────────────────────────────────────────────────────────

async def cmd_mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    chat = update.message.chat
    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text(t("group_only"))
        return

    today_q  = await db.get_query_count(user.id, chat.id)
    today_lk = await db.get_daily_action(user.id, chat.id, "link")
    today_fw = await db.get_daily_action(user.id, chat.id, "forward")
    total_m  = await db.get_message_count(user.id, chat.id)
    warns    = await db.get_warnings(user.id, chat.id)
    level    = await db.get_user_level(user.id, chat.id)
    cfg      = get_config(level)
    extra    = await db.get_user_daily_stats(user.id, chat.id)
    points   = await db.get_points(user.id, chat.id)

    q_lim  = "نامحدود" if cfg.daily_queries  == -1 else str(cfg.daily_queries)
    lk_lim = "ممنوع"   if cfg.daily_links    ==  0 else ("نامحدود" if cfg.daily_links    == -1 else str(cfg.daily_links))
    fw_lim = "ممنوع"   if cfg.daily_forwards ==  0 else ("نامحدود" if cfg.daily_forwards == -1 else str(cfg.daily_forwards))

    def _bar(used: int, limit) -> str:
        if not isinstance(limit, int) or limit <= 0:
            return ""
        pct    = min(used / limit, 1.0)
        filled = int(pct * 8)
        return " [" + "█" * filled + "░" * (8 - filled) + f"] {used}/{limit}"

    lk_bar = _bar(today_lk, cfg.daily_links)
    fw_bar = _bar(today_fw, cfg.daily_forwards)
    q_bar  = _bar(today_q,  cfg.daily_queries)

    next_lv      = next_auto_level(level)
    upgrade_line = ""
    if next_lv and cfg.auto_upgrade_msgs:
        done  = total_m
        pct   = min(done / cfg.auto_upgrade_msgs, 1.0)
        bar_f = int(pct * 10)
        bar   = "█" * bar_f + "░" * (10 - bar_f)
        upgrade_line = (
            f"\n📈 <b>ارتقاء به {level_label(next_lv)}:</b>\n"
            f"  <code>[{bar}] {done}/{cfg.auto_upgrade_msgs} پیام</code>"
        )

    # آستانه امتیازی
    from bot.handlers.messages import UPGRADE_THRESHOLDS
    if level in UPGRADE_THRESHOLDS:
        threshold, _ = UPGRADE_THRESHOLDS[level]
        pts_line = f"\n⭐ امتیاز: <b>{points}</b> | آستانه بعدی: <b>{threshold}</b>"
    else:
        pts_line = f"\n⭐ امتیاز: <b>{points}</b>"

    tag = mention(user)
    await update.message.reply_text(
        f"📊 <b>آمار فعالیت روزانه — {tag}</b>\n\n"
        f"<blockquote>"
        f"🏅 سطح کاربری: <b>{level_label(level)}</b>\n"
        f"💬 پیام امروز: <b>{extra['msgs_today']}</b>\n"
        f"💬 کل پیام‌ها: <b>{total_m}</b>\n\n"
        f"📌 <b>مصرف روزانه:</b>\n"
        f"• لینک: <code>{lk_bar if lk_bar else ' ' + lk_lim}</code>\n"
        f"• فوروارد: <code>{fw_bar if fw_bar else ' ' + fw_lim}</code>\n"
        f"• سوال ربات: <code>{q_bar if q_bar else ' ' + q_lim}</code>\n\n"
        f"⚠️ <b>وضعیت انضباطی:</b>\n"
        f"• اخطار فعلی: <b>{warns}/{MAX_WARNINGS}</b>\n"
        f"• تخلف امروز: <b>{extra['violations_today']}</b>\n"
        f"• میوت این هفته: <b>{extra['mutes_week']}</b>\n"
        f"• بن کل: <b>{extra['bans_total']}</b>"
        f"{pts_line}"
        f"{upgrade_line}"
        f"</blockquote>",
        parse_mode="HTML",
    )


# ─── /levels ─────────────────────────────────────────────────────────────────

async def cmd_levels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(level_summary(), parse_mode="HTML")


# ─── /setlevel ───────────────────────────────────────────────────────────────

async def cmd_setlevel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        await update.message.reply_text("❌ فقط ادمین‌ها میتونن سطح تغییر بدن.")
        return

    args = list(context.args) if context.args else []

    # تشخیص target و سطح
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        target_mention = mention(update.message.reply_to_message.from_user)
        level_arg = args[0].lower() if args else None
    elif args:
        try:
            target_id = int(args[0])
            target_mention = f"کاربر <code>{target_id}</code>"
            level_arg = args[1].lower() if len(args) > 1 else None
        except ValueError:
            await update.message.reply_text(
                f"استفاده: /setlevel <user_id> <سطح>\nسطوح: {' | '.join(LEVEL_ORDER)}"
            )
            return
    else:
        await update.message.reply_text(
            f"روی پیام ریپلای بزن یا /setlevel <user_id> <سطح>\nسطوح: {' | '.join(LEVEL_ORDER)}"
        )
        return

    if not level_arg:
        await update.message.reply_text(
            f"سطح رو مشخص کن.\nسطوح: {' | '.join(LEVEL_ORDER)}"
        )
        return

    if not is_valid_level(level_arg):
        await update.message.reply_text(
            f"❌ سطح نامعتبر!\nسطوح معتبر: {' | '.join(LEVEL_ORDER)}"
        )
        return

    chat_id = update.message.chat_id
    cfg     = get_config(level_arg)
    await db.set_user_level(target_id, chat_id, level_arg, update.message.from_user.id)
    # ریست شمارش پیام جلوگیری از ارتقاء خودکار
    await db.reset_message_count(target_id, chat_id)

    tag_text = cfg.tag if level_arg != "simple" else "ساده"
    from bot.core.moderation import _set_status_tag
    await _set_status_tag(context.bot, chat_id, target_id, tag_text)

    await update.message.reply_text(
        f"✅ سطح {target_mention} به {level_label(level_arg)} تغییر کرد.",
        parse_mode="HTML",
    )


# ─── /search ─────────────────────────────────────────────────────────────────

async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("استفاده: /search [کلمه کلیدی]")
        return
    query   = " ".join(context.args)
    results = await db.search_messages(query, update.message.chat_id, limit=5)
    if not results:
        await update.message.reply_text(f"🔍 نتیجه‌ای برای «{query}» پیدا نشد.")
        return
    text = f"🔍 نتایج جستجو برای «{query}»:\n\n"
    for r in results:
        date  = r["date"][:10]
        text += f"👤 {r['name']} [{date}]:\n{r['text'][:200]}\n\n"
    await update.message.reply_text(text)


# ─── /learn ──────────────────────────────────────────────────────────────────

async def cmd_learn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        return
    count = await learn_from_feedback()
    await update.message.reply_text(f"🧠 {count} مورد جدید یاد گرفته شد.")


# ─── /clear — پاک کردن حافظه مکالمه کاربر با ربات ──────────────────────────────

async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    پاک کردن تاریخچه گفت‌وگوی شخصی کاربر با ربات.
    برای شروع مکالمه تازه و حفظ حریم خصوصی.
    """
    user = update.message.from_user
    chat_id = update.message.chat_id
    try:
        await db.clear_conversation(user.id, chat_id)
        await update.message.reply_text(
            "🧹 حافظه گفت‌وگوی شما با ربات پاک شد.\n"
            "از الان ربات مکالمه قبلی رو یادش نمیاد."
        )
    except Exception as e:
        logger.warning(f"cmd_clear failed: {e}")
        await update.message.reply_text("❌ خطا در پاک‌سازی حافظه.")


# ─── /warn ───────────────────────────────────────────────────────────────────

async def cmd_warn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        return
    target_id, _, target_mention = await _get_target(update, context)
    if not target_id:
        await update.message.reply_text("روی پیام ریپلای بزن یا /warn <user_id> [دلیل]")
        return
    chat_id = update.message.chat_id
    # اگه user_id آرگومان بود، بقیه args دلیل هستن
    if update.message.reply_to_message:
        reason = " ".join(context.args) or "تخلف"
    else:
        reason = " ".join(context.args[1:]) or "تخلف"
    warn_count = await db.add_warning(target_id, chat_id, reason)
    # ثبت رویداد اخطار
    try:
        await db.log_action(
            chat_id=chat_id, action="warn", user_id=target_id,
            actor_id=update.message.from_user.id,
            target_name=target_mention, reason=reason,
        )
    except Exception:
        pass

    if warn_count >= MAX_WARNINGS:
        await mod._ban(context.bot, chat_id, target_id)
        await db.reset_warnings(target_id, chat_id)
        try:
            await db.log_action(
                chat_id=chat_id, action="ban", user_id=target_id,
                actor_id=update.message.from_user.id,
                target_name=target_mention, reason=f"اخطار مکرر ({warn_count})",
            )
        except Exception:
            pass
        await update.message.reply_text(
            t("banned", name=target_mention), parse_mode="HTML"
        )
    else:
        await mod.apply_warn_tag(context.bot, chat_id, target_id, warn_count)
        await update.message.reply_text(
            t("warn_insult", name=target_mention, warn=warn_count, max=MAX_WARNINGS),
            parse_mode="HTML",
        )


# ─── /unwarn ─────────────────────────────────────────────────────────────────

async def cmd_unwarn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        return
    target_id, _, target_mention = await _get_target(update, context)
    if not target_id:
        await update.message.reply_text("روی پیام ریپلای بزن یا /unwarn <user_id>")
        return
    chat_id = update.message.chat_id
    await db.reset_warnings(target_id, chat_id)
    await mod.apply_warn_tag(context.bot, chat_id, target_id, 0)
    await update.message.reply_text(
        f"✅ اخطارهای {target_mention} پاک شد.", parse_mode="HTML"
    )


# ─── /warnings ───────────────────────────────────────────────────────────────

async def cmd_warnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target_id, target_name, _ = await _get_target(update, context)
    if not target_id:
        await update.message.reply_text("روی پیام ریپلای بزن یا /warnings <user_id>")
        return
    count = await db.get_warnings(target_id, update.message.chat_id)
    await update.message.reply_text(
        f"📋 {target_name} — اخطار: {count}/{MAX_WARNINGS}"
    )


# ─── /mute ───────────────────────────────────────────────────────────────────

async def cmd_mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        return
    target_id, _, target_mention = await _get_target(update, context)
    if not target_id:
        await update.message.reply_text("روی پیام ریپلای بزن یا /mute <user_id> [دقیقه]")
        return
    chat_id = update.message.chat_id

    # اگه reply بود، args[0] دقیقه است. اگه user_id بود، args[1] دقیقه است
    args = list(context.args) if context.args else []
    minute_arg = args[1] if not update.message.reply_to_message and len(args) > 1 else (args[0] if update.message.reply_to_message and args else None)
    if minute_arg:
        try:
            minutes = max(1, int(minute_arg))
        except ValueError:
            minutes = await mod._next_mute_minutes(target_id, chat_id)
    else:
        minutes = await mod._next_mute_minutes(target_id, chat_id)

    duration_lbl = mod._format_minutes(minutes)
    await mod._mute(context.bot, chat_id, target_id, minutes=minutes)
    await db.add_punishment(target_id, chat_id, "mute", minutes * 60, "میوت دستی ادمین")
    await mod.apply_mute_tag(context.bot, chat_id, target_id, duration_lbl)
    # ثبت رویداد میوت
    try:
        await db.log_action(
            chat_id=chat_id, action="mute", user_id=target_id,
            actor_id=update.message.from_user.id,
            target_name=target_mention, reason=f"میوت دستی {duration_lbl}",
        )
    except Exception:
        pass
    await update.message.reply_text(
        f"🔇 {target_mention} به مدت <b>{duration_lbl}</b> میوت شد.",
        parse_mode="HTML",
    )


# ─── /unmute ─────────────────────────────────────────────────────────────────

async def cmd_unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        return
    target_id, _, target_mention = await _get_target(update, context)
    if not target_id:
        await update.message.reply_text("روی پیام ریپلای بزن یا /unmute <user_id>")
        return
    chat_id = update.message.chat_id
    all_perms = ChatPermissions(
        can_send_messages=True, can_send_audios=True,
        can_send_documents=True, can_send_photos=True,
        can_send_videos=True, can_send_voice_notes=True,
        can_send_polls=True, can_send_other_messages=True,
    )
    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id, user_id=target_id, permissions=all_perms
        )
    except Exception as e:
        logger.warning(f"unmute ناموفق: {e}")
    warns = await db.get_warnings(target_id, chat_id)
    await mod.apply_warn_tag(context.bot, chat_id, target_id, warns)
    await update.message.reply_text(
        f"🔊 میوت {target_mention} برداشته شد.", parse_mode="HTML"
    )


# ─── /ban ────────────────────────────────────────────────────────────────────

async def cmd_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /ban              → بن پلکانی (ریپلای)
    /ban <user_id>    → بن پلکانی با ID
    /ban @username    → بن با یوزرنیم
    /ban 30m          → ریپلای + مدت
    /ban <user_id> 1h دلیل → ID + مدت + دلیل
    """
    if not _is_admin(update.message.from_user.id):
        return

    args = list(context.args) if context.args else []
    chat_id = update.message.chat_id

    # تشخیص target با helper مشترک (reply / user_id / @username)
    target_id, target_name, target_mention = await _get_target(update, context)
    if not target_id:
        await update.message.reply_text(
            "❌ کاربر پیدا نشد!\n\n"
            "روش‌های صحیح:\n"
            "• روی پیام کاربر ریپلای بزن و /ban بنویس\n"
            "• <code>/ban user_id</code> (شناسه عددی)\n"
            "• <code>/ban @username</code> (فقط اگه کاربر قبلاً تو گروه پیام داده باشه)\n\n"
            "نکته: برای یوزرنیم، ربات باید کاربر رو قبلاً تو گروه دیده باشه.",
            parse_mode="HTML",
        )
        return

    # اگه target از آرگومان اومده (نه reply)، args[0] مصرف شده و باید حذف بشه
    if not update.message.reply_to_message and args:
        args = args[1:]

    reason       = "تخلف"
    until_date   = None
    duration_txt = "دائم"

    if args:
        seconds = parse_duration(args[0])
        if seconds:
            until_date   = datetime.now(tz=timezone.utc) + timedelta(seconds=seconds)
            duration_txt = format_duration(seconds)
            args = args[1:]
        if args:
            reason = " ".join(args)
    else:
        days, duration_txt = await mod._next_ban_duration(target_id, chat_id)
        if days:
            until_date = datetime.now(tz=timezone.utc) + timedelta(days=days)

    await mod._ban(context.bot, chat_id, target_id, until_date=until_date)
    duration_secs = (
        int((until_date - datetime.now(tz=timezone.utc)).total_seconds())
        if until_date else -1
    )
    await db.add_punishment(target_id, chat_id, "ban", duration_secs, reason)
    # ثبت رویداد بن با دلیل
    try:
        await db.log_action(
            chat_id=chat_id, action="ban", user_id=target_id,
            actor_id=update.message.from_user.id,
            target_name=target_name,
            reason=f"{reason} ({duration_txt})",
        )
    except Exception:
        pass

    # نمایش لول جریمه
    from bot.core.punishment_levels import get_next_punishment_level, get_level_name
    warnings = await db.get_warnings(target_id, chat_id)
    level = get_next_punishment_level(warnings if isinstance(warnings, int) else len(warnings))

    if until_date:
        await update.message.reply_text(
            t("banned_temp", name=target_mention, duration=duration_txt, reason=reason)
            + f"\n\n🎯 لول جریمه: {get_level_name(level)}",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            t("banned", name=target_mention)
            + f"\n\n🎯 لول جریمه: {get_level_name(level)}",
            parse_mode="HTML",
        )


# ─── /unban ──────────────────────────────────────────────────────────────────

async def cmd_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        return
    chat_id = update.message.chat_id
    target_id = None
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
    elif context.args:
        try:
            target_id = int(context.args[0])
        except ValueError:
            pass
    if not target_id:
        await update.message.reply_text("روی پیام ریپلای بزن یا /unban <user_id>")
        return

    # آخرین دلیل بن رو از حافظه بخون
    ban_info = await db.get_last_ban_reason(target_id, chat_id)

    try:
        await context.bot.unban_chat_member(
            chat_id=chat_id, user_id=target_id, only_if_banned=True,
        )
        # ثبت رویداد آنبن
        try:
            await db.log_action(
                chat_id=chat_id, action="unban", user_id=target_id,
                actor_id=update.message.from_user.id,
                target_name=str(target_id),
            )
        except Exception:
            pass
        # نمایش دلیل بن قبلی (اگه هست)
        if ban_info:
            date_str = ban_info.get("date", "")[:16] if ban_info.get("date") else ""
            await update.message.reply_text(
                f"✅ کاربر <code>{target_id}</code> آنبن شد.\n\n"
                f"📋 <b>دلیل بن قبلی:</b>\n"
                f"📝 {ban_info['reason']}\n"
                f"📅 {date_str}",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(
                f"✅ کاربر <code>{target_id}</code> آنبن شد.\n\n"
                f"📋 دلیل بنی ثبت نشده بود."
            )
    except Exception as e:
        await update.message.reply_text(f"❌ آنبن ناموفق: {e}")


# ─── /stats ──────────────────────────────────────────────────────────────────

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        return
    chat_id = update.message.chat_id
    stats   = await db.get_stats(chat_id)
    daily   = await db.get_daily_stats(chat_id)

    await update.message.reply_text(
        "📊 *آمار گروه*\n"
        "━━━━━━━━━━━━━━\n\n"
        "📅 *امروز:*\n"
        f"  👥 کاربران فعال: {daily.get('active_users_today', 0)}\n"
        f"  💬 پیام عادی: {daily.get('normal', 0)}\n"
        f"  🔴 توهین: {daily.get('insult', 0)}\n"
        f"  📢 اسپم: {daily.get('spam', 0)}\n"
        f"  ⚠️ اخطار داده شده: {daily.get('warns_today', 0)}\n"
        f"  🔇 میوت امروز: {daily.get('mutes_today', 0)}\n"
        f"  🚫 بن امروز: {daily.get('bans_today', 0)}\n"
        f"  🔗 لینک ارسالی: {daily.get('links_today', 0)}\n"
        f"  ↩️ فوروارد: {daily.get('forwards_today', 0)}\n\n"
        "📈 *کل تاریخ:*\n"
        f"  🔴 توهین: {stats.get('insult', 0)}\n"
        f"  📢 اسپم: {stats.get('spam', 0)}\n"
        f"  ❓ سوال پاسخ‌داده: {stats.get('request', 0)}\n"
        f"  👥 کاربران اخطارخورده: {stats.get('warned_users', 0)}\n"
        f"  🧠 دانش ذخیره‌شده: {stats.get('knowledge_items', 0)} مورد",
        parse_mode="HTML",
    )


# ─── /violations ─────────────────────────────────────────────────────────────

async def cmd_violations(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        return
    chat_id = update.message.chat_id
    v = await db.get_violation_stats(chat_id)
    total = v["total"]
    week  = v["week"]

    top_lines = ""
    for i, u in enumerate(v["top_violators"], 1):
        top_lines += f"  {i}. {esc(u['name'])} — {u['count']} تخلف\n"
    if not top_lines:
        top_lines = "  هنوز تخلفی ثبت نشده\n"

    await update.message.reply_text(
        "🔍 *آمار تخلفات*\n"
        "━━━━━━━━━━━━━━\n\n"
        "📅 *۷ روز گذشته:*\n"
        f"  🔴 توهین: {week.get('insult', 0)}\n"
        f"  📢 اسپم: {week.get('spam', 0)}\n"
        f"  🔇 میوت: {week.get('mutes', 0)}\n"
        f"  🚫 بن: {week.get('bans', 0)}\n\n"
        "📈 *کل تاریخ:*\n"
        f"  🔴 توهین: {total.get('insult', 0)}\n"
        f"  📢 اسپم: {total.get('spam', 0)}\n"
        f"  🔇 میوت: {total.get('mutes', 0)}\n"
        f"  🚫 بن: {total.get('bans', 0)}\n\n"
        "🏆 *پرتخلف‌ترین کاربران:*\n"
        f"{top_lines}",
        parse_mode="HTML",
    )


# ─── /report ─────────────────────────────────────────────────────────────────

async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user    = message.from_user
    chat    = message.chat

    if chat.type == ChatType.PRIVATE:
        await message.reply_text(t("group_only"))
        return

    if not message.reply_to_message:
        await send_and_delete(message, t("report_how"), delay=15)
        return

    target_msg  = message.reply_to_message
    target_user = target_msg.from_user

    if _is_admin(target_user.id):
        await send_and_delete(message, t("report_admin"), delay=10)
        return
    if target_user.id == user.id:
        await send_and_delete(message, t("report_self"), delay=10)
        return

    today_reports = await db.get_user_report_today(user.id, chat.id)
    if today_reports >= 3:
        await send_and_delete(message, t("report_limit"), delay=12)
        return

    reason       = " ".join(context.args) if context.args else "محتوای نامناسب"
    message_text = target_msg.text or target_msg.caption or "[مدیا/استیکر]"

    report_id = await db.save_report(
        reporter_id=user.id,
        reported_id=target_user.id,
        chat_id=chat.id,
        message_id=target_msg.message_id,
        message_text=message_text[:500],
        reason=reason,
    )

    await send_and_delete(
        message,
        t("report_confirm", report_id=report_id),
        delay=20,
    )

    try:
        await context.bot.delete_message(chat.id, message.message_id)
    except Exception:
        pass

    notify_text = t(
        "report_notify",
        report_id=report_id,
        reporter=mention(user),
        reported=mention(target_user),
        reason=reason,
        text=message_text[:200],
        link=f"https://t.me/c/{str(chat.id)[4:]}/{target_msg.message_id}",
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("⚠️ اخطار",  callback_data=f"rpt_warn_{report_id}_{target_user.id}_{chat.id}"),
        InlineKeyboardButton("🔇 میوت",   callback_data=f"rpt_mute_{report_id}_{target_user.id}_{chat.id}"),
        InlineKeyboardButton("🚫 بن",     callback_data=f"rpt_ban_{report_id}_{target_user.id}_{chat.id}"),
        InlineKeyboardButton("✅ نادیده", callback_data=f"rpt_ignore_{report_id}"),
    ]])

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=notify_text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        except Exception:
            pass


# ─── /reports ────────────────────────────────────────────────────────────────

async def cmd_reports(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_admin(update.message.from_user.id):
        return
    chat_id = update.message.chat_id
    pending = await db.get_pending_reports(chat_id, limit=5)
    counts  = await db.get_report_count(chat_id)

    if not pending:
        await update.message.reply_text(
            f"📭 گزارش در انتظر بررسی وجود ندارد.\n"
            f"✅ بررسی‌شده: {counts.get('reviewed', 0)} | "
            f"❌ نادیده: {counts.get('ignored', 0)}",
        )
        return

    text = (
        f"📋 *گزارش‌های در انتظر: {len(pending)}*\n"
        f"✅ بررسی‌شده: {counts.get('reviewed', 0)} | "
        f"❌ نادیده: {counts.get('ignored', 0)}\n"
        "━━━━━━━━━━━━━━\n\n"
    )
    for r in pending:
        date  = r["created_at"][:16]
        text += (
            f"🔖 *#{r['id']}* — {date}\n"
            f"🎯 کاربر: `{r['reported_id']}`\n"
            f"📌 دلیل: {r['reason']}\n"
            f"💬 پیام: {r['message_text'][:100]}\n\n"
        )
    await update.message.reply_text(text, parse_mode="HTML")


# ─── /tagall — تگ همه اعضای گروه ────────────────────────────────────────────

async def cmd_tagall(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    تگ همه کاربرانی که در DB ثبت شدن رو بر اساس سطحشون ست می‌کنه.
    فقط ادمین — در گروه اجرا می‌شه.
    """
    if not _is_admin(update.message.from_user.id):
        return
    chat = update.message.chat
    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text("این دستور فقط در گروه کار می‌کند.")
        return

    from bot.core.moderation import _set_status_tag

    msg = await update.message.reply_text("⏳ در حال تگ کردن اعضا...")

    # همه کاربرانی که سطح non-simple دارن
    chat_levels = await db.get_chat_levels(chat.id)
    tagged_non_simple = 0
    for entry in chat_levels:
        cfg = get_config(entry["level"])
        try:
            await _set_status_tag(context.bot, chat.id, entry["user_id"], cfg.tag)
            tagged_non_simple += 1
        except Exception:
            pass

    # همه کاربرانی که در message_log هستن ولی سطح ندارن (simple)
    tagged_simple = 0
    try:
        import bot.db.database as _db
        import aiosqlite
        async with aiosqlite.connect(_db.DB_PATH) as _conn:
            cur = await _conn.execute(
                """SELECT DISTINCT user_id FROM message_log
                   WHERE chat_id=?
                   AND user_id NOT IN (
                       SELECT user_id FROM user_levels WHERE chat_id=?
                   )""",
                (chat.id, chat.id),
            )
            rows = await cur.fetchall()
        for (uid,) in rows:
            try:
                await _set_status_tag(context.bot, chat.id, uid, "ساده")
                tagged_simple += 1
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"tagall simple error: {e}")

    await msg.edit_text(
        f"✅ تگ‌گذاری کامل شد:\n"
        f"  🏅 سطح‌دار: {tagged_non_simple} نفر\n"
        f"  👤 ساده: {tagged_simple} نفر"
    )


# ─── /testbtn — تست کلیدهای اینلاین (دیباگ) ──────────────────────────────────

async def cmd_testbtn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    دستور تست برای بررسی کلیدهای اینلاین و تشخیص مشکلات.
    فقط ادمین.
    """
    if not _is_admin(update.message.from_user.id):
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تست دکمه ۱", callback_data="tbtn_ok"),
            InlineKeyboardButton("❌ تست دکمه ۲", callback_data="tbtn_no"),
        ],
        [
            InlineKeyboardButton("🔗 تست لینک", callback_data="tbtn_link"),
        ],
    ])
    try:
        sent = await update.message.reply_text(
            "🧪 <b>تست کلیدهای اینلاین</b>\n\n"
            "اگه این کلیدها رو می‌بینی یعنی کلیدها درست کار می‌کنن.\n"
            "اگه پیام بدون کلید نشون داده شد، مشکل از دسترسی ربات به گروهه.",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        logger.info(f"✅ test buttons sent to chat {update.message.chat_id}, msg {sent.message_id}")
    except Exception as e:
        logger.error(f"❌ test buttons failed: {e}")
        await update.message.reply_text(f"❌ خطا در ارسال کلیدها: <code>{e}</code>", parse_mode="HTML")


# ─── /top — برترین کاربران گروه ──────────────────────────────────────────────

async def cmd_top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """جدول امتیازها — ۱۰ کاربر برتر گروه"""
    chat = update.message.chat
    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text(t("group_only"))
        return

    users = await db.get_top_users(chat.id, 10)
    if not users:
        await update.message.reply_text("📊 هنوز امتیازی ثبت نشده!")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 برترین کاربران گروه", "━━━━━━━━━━━━━━━━━━━━━━━━", ""]
    for i, u in enumerate(users):
        name = u["full_name"] or f"کاربر {u['user_id']}"
        # escape HTML و کوتاه کردن اسم طولانی
        from bot.utils.helpers import escape_html
        name = escape_html(name)[:25]
        rank_icon = medals[i] if i < 3 else f"{i+1}."
        lines.append(f"{rank_icon} <a href=\"tg://user?id={u['user_id']}\">{name}</a> — ⭐ {u['points']:,}")

    lines.append("")
    lines.append("💡 با فعالیت و کمک به بقیه امتیاز جمع کن!")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ─── /addfilter /delfilter /filters — فیلتر کلمات ممنوعه ─────────────────────

async def cmd_addfilter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اضافه کردن کلمه ممنوعه — فقط ادمین"""
    if not _is_admin(update.message.from_user.id):
        return
    word = " ".join(context.args).strip() if context.args else ""
    if not word:
        await update.message.reply_text("استفاده: /addfilter <کلمه>")
        return
    added = await db.add_chat_filter(update.message.chat_id, word, update.message.from_user.id)
    if added:
        await update.message.reply_text(f"✅ کلمه <code>{esc(word)}</code> فیلتر شد. پیام‌های حاوی اون حذف میشن.", parse_mode="HTML")
    else:
        await update.message.reply_text("⚠️ این کلمه قبلاً فیلتر شده.")


async def cmd_delfilter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف کلمه ممنوعه — فقط ادمین"""
    if not _is_admin(update.message.from_user.id):
        return
    word = " ".join(context.args).strip() if context.args else ""
    if not word:
        await update.message.reply_text("استفاده: /delfilter <کلمه>")
        return
    removed = await db.remove_chat_filter(update.message.chat_id, word)
    if removed:
        await update.message.reply_text(f"✅ کلمه <code>{esc(word)}</code> از فیلترها حذف شد.", parse_mode="HTML")
    else:
        await update.message.reply_text("❌ این کلمه توی لیست فیلتر نیست.")


async def cmd_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """لیست کلمات ممنوعه"""
    words = await db.get_chat_filters(update.message.chat_id)
    if not words:
        await update.message.reply_text("📋 هیچ کلمه‌ای فیلتر نشده. با /addfilter اضافه کن.")
        return
    lines = [f"📋 کلمات فیلتر شده ({len(words)}):", ""]
    lines.extend(f"   • <code>{esc(w)}</code>" for w in words)
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


# ─── /remind — یادآوری ───────────────────────────────────────────────────────

async def cmd_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """یادآوری با تاخیر: /remind 2h متن پیام"""
    args = list(context.args) if context.args else []
    if len(args) < 2:
        await update.message.reply_text(
            "استفاده: /remind <زمان> <متن>\n"
            "مثال: /remind 30m چایی دم کن\n"
            "واحد: m=دقیقه، h=ساعت، d=روز"
        )
        return

    from bot.utils.helpers import parse_duration
    duration = parse_duration(args[0])
    if duration <= 0 or duration > 86400 * 7:
        await update.message.reply_text("❌ زمان نامعتبر. حداکثر ۷ روز. مثال: /remind 2h متن")
        return

    text = " ".join(args[1:])
    user = update.message.from_user
    chat_id = update.message.chat_id

    async def _send_reminder():
        mention_user = f'<a href="tg://user?id={user.id}">{esc(user.full_name)}</a>'
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"⏰ یادآوری برای {mention_user}:\n\n💬 {esc(text)}",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"reminder send failed: {e}")

    import asyncio as _asyncio
    context.application.create_task(_delayed_task(duration, _send_reminder))

    from bot.utils.helpers import format_duration
    await update.message.reply_text(
        f"✅ یادآوری ثبت شد ({format_duration(duration)} دیگه):\n💬 {esc(text)}",
        parse_mode="HTML",
    )


async def _delayed_task(seconds: int, coro_fn):
    """اجرای یک coroutine بعد از تاخیر مشخص"""
    import asyncio as _asyncio
    await _asyncio.sleep(seconds)
    try:
        await coro_fn()
    except Exception as e:
        logger.warning(f"delayed task failed: {e}")


# ─── /lock /unlock /locks — قفل انواع پیام ───────────────────────────────────

_LOCK_LABELS = {
    "links": "🔗 لینک",
    "photos": "📸 عکس",
    "videos": "🎬 ویدیو",
    "voice": "🎙 ویس",
    "stickers": "🎨 استیکر/گیف",
    "forwards": "↩️ فوروارد",
    "all": "🔒 کل گروه",
}


async def cmd_lock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قفل کردن نوع پیام — فقط ادمین: /lock links"""
    if not _is_admin(update.message.from_user.id):
        return
    arg = context.args[0].lower() if context.args else ""
    if arg not in db.LOCK_TYPES:
        await update.message.reply_text(
            "استفاده: /lock <نوع>\nانواع: " + " | ".join(db.LOCK_TYPES)
        )
        return
    await db.set_chat_lock(update.message.chat_id, arg, True, update.message.from_user.id)
    await update.message.reply_text(
        f"🔒 {_LOCK_LABELS[arg]} قفل شد — اعضای عادی نمی‌تونن بفرستن."
    )


async def cmd_unlock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """باز کردن نوع پیام — فقط ادمین: /unlock links"""
    if not _is_admin(update.message.from_user.id):
        return
    arg = context.args[0].lower() if context.args else ""
    if arg not in db.LOCK_TYPES:
        await update.message.reply_text(
            "استفاده: /unlock <نوع>\nانواع: " + " | ".join(db.LOCK_TYPES)
        )
        return
    await db.set_chat_lock(update.message.chat_id, arg, False, update.message.from_user.id)
    await update.message.reply_text(f"🔓 {_LOCK_LABELS[arg]} باز شد.")


async def cmd_locks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """وضعیت قفل‌های گروه"""
    locks = await db.get_chat_locks(update.message.chat_id)
    lines = ["🔒 قفل‌های گروه", "━━━━━━━━━━━━━━━━━━━━━━━━", ""]
    for lt in db.LOCK_TYPES:
        status = "🔒 قفل" if locks.get(lt) else "🔓 باز"
        lines.append(f"{_LOCK_LABELS[lt]}: {status}")
    await update.message.reply_text("\n".join(lines))


# ─── /lockdown — قفل کل گروه موقت ────────────────────────────────────────────

async def cmd_lockdown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قفل کل گروه برای مدت مشخص — فقط ادمین: /lockdown 10m"""
    if not _is_admin(update.message.from_user.id):
        return
    args = list(context.args) if context.args else []
    if not args:
        await update.message.reply_text(
            "استفاده: /lockdown <زمان>\nمثال: /lockdown 10m (۱۰ دقیقه)\nواحد: m=دقیقه، h=ساعت"
        )
        return
    from bot.utils.helpers import parse_duration, format_duration
    duration = parse_duration(args[0])
    if duration <= 0 or duration > 86400:
        await update.message.reply_text("❌ زمان نامعتبر. حداکثر ۲۴ ساعت. مثال: /lockdown 10m")
        return

    chat_id = update.message.chat_id
    await db.set_chat_lock(chat_id, "all", True, update.message.from_user.id)
    await update.message.reply_text(
        f"🔒 گروه قفل شد ({format_duration(duration)}) — فقط ادمین‌ها می‌تونن پیام بدن."
    )

    async def _auto_unlock():
        import asyncio as _asyncio
        await _asyncio.sleep(duration)
        await db.set_chat_lock(chat_id, "all", False, 0)
        try:
            await context.bot.send_message(chat_id=chat_id, text="🔓 گروه باز شد!")
        except Exception:
            pass

    import asyncio as _asyncio
    context.application.create_task(_auto_unlock())


async def cmd_unlockdown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """باز کردن فوری گروه — فقط ادمین"""
    if not _is_admin(update.message.from_user.id):
        return
    await db.set_chat_lock(update.message.chat_id, "all", False, update.message.from_user.id)
    await update.message.reply_text("🔓 گروه باز شد.")


# ─── /tr — مترجم ─────────────────────────────────────────────────────────────

async def cmd_translate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ترجمه متن: /tr en Hello world یا /tr fa سلام"""
    args = list(context.args) if context.args else []
    if len(args) < 2:
        await update.message.reply_text(
            "استفاده: /tr <زبان> <متن>\n"
            "مثال: /tr en سلام دنیا\n"
            "زبان‌ها: fa (فارسی)، en (انگلیسی)، ar (عربی)، tr (ترکی)"
        )
        return

    lang_codes = {
        "fa": "فارسی", "en": "انگلیسی", "ar": "عربی",
        "tr": "ترکی استانبولی", "de": "آلمانی", "fr": "فرانسوی",
        "ru": "روسی", "es": "اسپانیایی", "zh": "چینی",
    }
    lang = lang_codes.get(args[0].lower())
    if not lang:
        await update.message.reply_text(
            "❌ زبان نامعتبر. زبان‌ها: " + " | ".join(lang_codes.keys())
        )
        return

    text = " ".join(args[1:])
    from bot.core.ai_analyzer import translate_text
    result = await translate_text(text, lang)
    if result:
        from bot.utils.helpers import escape_html
        await update.message.reply_text(
            f"🌐 ترجمه به {lang}:\n\n{escape_html(result)}",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("❌ ترجمه ناموفق بود. بعداً تلاش کن.")


# ─── /punishment — نمایش رنک‌های جریمه ────────────────────────────────────────

async def cmd_punishment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش سیستم رنک جریمه"""
    from bot.core.punishment_ranks import get_all_ranks_summary

    text = get_all_ranks_summary()
    await update.message.reply_text(text, parse_mode="HTML")


# ─── /setpunishment — تنظیم رنک جریمه ────────────────────────────────────────

async def cmd_setpunishment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تنظیم رنک جریمه کاربر — فقط ادمین"""
    if not _is_admin(update.message.from_user.id):
        return

    from bot.core.punishment_ranks import RANK_ORDER, get_rank_name, get_rank_config

    args = list(context.args) if context.args else []

    # تشخیص target
    if update.message.reply_to_message:
        target_id = update.message.reply_to_message.from_user.id
        target_mention = mention(update.message.reply_to_message.from_user)
        rank_arg = args[0].lower() if args else None
    elif args:
        try:
            target_id = int(args[0])
            target_mention = f"کاربر <code>{target_id}</code>"
            rank_arg = args[1].lower() if len(args) > 1 else None
        except ValueError:
            await update.message.reply_text(
                f"استفاده: /setpunishment <user_id> <رنک>\n"
                f"رنک‌ها: {' | '.join(RANK_ORDER)}"
            )
            return
    else:
        await update.message.reply_text(
            f"روی پیام ریپلای بزن یا /setpunishment <user_id> <رنک>\n"
            f"رنک‌ها: {' | '.join(RANK_ORDER)}"
        )
        return

    if not rank_arg:
        await update.message.reply_text(
            f"رنک رو مشخص کن.\n"
            f"رنک‌ها: {' | '.join(RANK_ORDER)}"
        )
        return

    if rank_arg not in RANK_ORDER:
        await update.message.reply_text(
            f"❌ رنک نامعتبر!\n"
            f"رنک‌های معتبر: {' | '.join(RANK_ORDER)}"
        )
        return

    chat_id = update.message.chat_id
    await db.set_punishment_rank(target_id, chat_id, rank_arg, update.message.from_user.id)

    # نمایش اطلاعات رنک
    rank_info = get_rank_config(rank_arg)
    limit = "نامحدود" if rank_info.daily_limit == -1 else str(rank_info.daily_limit)

    # ─── فقط برای clean → باز کردن سکوت فوری ─────────────────────────────
    import logging as _log_mod
    _log2 = _log_mod.getLogger("setpunishment")

    if rank_arg == "clean":
        try:
            from telegram import ChatPermissions
            perms = ChatPermissions(
                can_send_messages=True, can_send_audios=True, can_send_documents=True,
                can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
                can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
                can_add_web_page_previews=True, can_change_info=True, can_invite_users=True,
                can_pin_messages=True, can_manage_topics=True)
            _log2.info(f"🔓 CLEAN: unrestricting user {target_id} in chat {chat_id}")
            result = await context.bot.restrict_chat_member(chat_id=chat_id, user_id=target_id, permissions=perms)
            _log2.info(f"🔓 CLEAN result: {result}")
            restriction_text = "🔓 دسترسی کامل برگردانده شد"
        except Exception as e:
            _log2.error(f"❌ CLEAN failed: {e}")
            restriction_text = f"⚠️ خطا: {e}"
    else:
        rank_info_new = get_rank_config(rank_arg)
        limit_new = "نامحدود" if rank_info_new.daily_limit == -1 else f"{rank_info_new.daily_limit} پیام در روز"
        restriction_text = f"📋 محدودیت روزانه: {limit_new}\n💬 پیام‌های اضافی حذف میشن"

    await update.message.reply_text(
        f"✅ رنک جریمه {target_mention} به <b>{get_rank_name(rank_arg)}</b> تغییر کرد.\n\n"
        f"{restriction_text}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 محدودیت روزانه: {limit}\n"
        f"💬 سوال از ربات: {'✅' if rank_info.can_ask_bot else '❌'}\n"
        f"🔗 ارسال لینک: {'✅' if rank_info.can_send_link else '❌'}\n"
        f"↩️ فوروارد: {'✅' if rank_info.can_forward else '❌'}",
        parse_mode="HTML",
    )


# ─── /punishment — نمایش رنک‌های جریمه ────────────────────────────────────────

async def cmd_sync(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    همگام‌سازی دانش از کانال‌های آموزشی تنظیم‌شده.
    فقط ادمین.
    """
    if not _is_admin(update.message.from_user.id):
        return

    from config import TRAINING_CHANNELS
    if not TRAINING_CHANNELS:
        await update.message.reply_text(
            "❌ هیچ کانال آموزشی تنظیم نشده!\n\n"
            "برای تنظیم، فایل .env رو ویرایش کن:\n"
            "<code>TRAINING_CHANNELS=@channel1,@channel2</code>",
            parse_mode="HTML",
        )
        return

    msg = await update.message.reply_text(
        f"📚 در حال همگام‌سازی از {len(TRAINING_CHANNELS)} کانال...\n"
        f"این عملیات ممکنه چند دقیقه طول بکشه."
    )

    try:
        from bot.core.knowledge_engine import sync_training_channels
        total = await sync_training_channels()
        if total == 0:
            await msg.edit_text(
                "⚠️ هیچ مطلبی یاد گرفته نشد!\n\n"
                "علت‌های ممکن:\n"
                "• کانال public نیست (باید یوزرنیم داشته باشه)\n"
                "• سرور به t.me دسترسی نداره (فیلتر)\n"
                "• کانال خالی هست یا مطالب خیلی کوتاه هستن\n\n"
                f"📚 کانال‌های تنظیم‌شده: {', '.join(TRAINING_CHANNELS)}",
            )
            return
        await msg.edit_text(
            f"✅ همگام‌سازی کامل شد!\n\n"
            f"📊 تعداد مطالب یادگرفته‌شده: {total}\n"
            f"📚 کانال‌ها: {', '.join(TRAINING_CHANNELS)}"
        )
    except Exception as e:
        logger.error(f"sync failed: {e}")
        await msg.edit_text(f"❌ خطا در همگام‌سازی: <code>{str(e)[:200]}</code>", parse_mode="HTML")


# ─── /recent — نمایش رویدادهای اخیر گروه ──────────────────────────────────────

ACTION_LABELS = {
    "join":    "➕ ورود",
    "leave":   "➖ خروج",
    "ban":     "🚫 بن",
    "unban":   "✅ آن‌بن",
    "mute":    "🔇 میوت",
    "unmute":  "🔊 آن‌میوت",
    "warn":    "⚠️ اخطار",
    "unwarn":  "🧹 پاک‌سازی اخطار",
    "report":  "🚨 گزارش",
}


async def cmd_recent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    نمایش آخرین رویدادهای گروه (ورود، خروج، بن، میوت، ...).
    فقط ادمین. در گروه اجرا می‌شه.
    """
    if not _is_admin(update.message.from_user.id):
        return

    chat = update.message.chat
    if chat.type == ChatType.PRIVATE:
        await update.message.reply_text("این دستور فقط در گروه کار می‌کند.")
        return

    # تعداد رویدادها (پیش‌فرض ۱۵، حداکثر ۵۰)
    limit = 15
    if context.args:
        try:
            limit = max(5, min(50, int(context.args[0])))
        except ValueError:
            pass

    actions = await db.get_recent_actions(chat.id, limit=limit)
    if not actions:
        await update.message.reply_text("📭 هنوز هیچ رویدادی ثبت نشده.")
        return

    text = f"📋 <b>رویدادهای اخیر گروه</b> ({len(actions)} مورد)\n"
    text += "━━━━━━━━━━━━━━━\n\n"

    for a in actions:
        label = ACTION_LABELS.get(a["action"], a["action"])
        date = (a["created_at"] or "")[:16]
        name = a.get("target_name") or "نامشخص"
        # اگه user_id هست، قابل کلیکش کن
        if a.get("user_id"):
            name = f'<a href="tg://user?id={a["user_id"]}">{name}</a>'
        else:
            name = f"<code>{name}</code>"

        line = f"{label} — {name}\n   🕐 {date}"
        if a.get("reason"):
            line += f"\n   📝 {a['reason'][:80]}"
        text += line + "\n\n"

    # اگه متن خیلی طولانیه، تقسیم کن
    if len(text) > 4000:
        for i in range(0, len(text), 4000):
            await update.message.reply_text(text[i:i+4000], parse_mode="HTML")
    else:
        await update.message.reply_text(text, parse_mode="HTML")


# ─── /addchannel — افزودن کانال آموزشی ────────────────────────────────────────

async def cmd_addchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """افزودن کانال آموزشی برای یادگیری ربات. فقط ادمین."""
    if not _is_admin(update.message.from_user.id):
        return
    if not context.args:
        await update.message.reply_text(
            "استفاده: <code>/addchannel @channelname</code>",
            parse_mode="HTML",
        )
        return
    channel = context.args[0].strip()
    from config import add_training_channel, TRAINING_CHANNELS
    added = add_training_channel(channel)
    if added:
        await update.message.reply_text(
            f"✅ کانال {channel} به کانال‌های آموزشی اضافه شد.\n\n"
            f"📚 کانال‌های فعلی: {', '.join(TRAINING_CHANNELS) or 'هیچ'}\n\n"
            f"برای یادگیری از این کانال، دستور /sync رو بزن.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            f"⚠️ کانال {channel} از قبل موجود است.\n"
            f"📚 کانال‌های فعلی: {', '.join(TRAINING_CHANNELS) or 'هیچ'}",
            parse_mode="HTML",
        )


# ─── /delchannel — حذف کانال آموزشی ───────────────────────────────────────────

async def cmd_delchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف کانال آموزشی. فقط ادمین."""
    if not _is_admin(update.message.from_user.id):
        return
    if not context.args:
        await update.message.reply_text(
            "استفاده: <code>/delchannel @channelname</code>",
            parse_mode="HTML",
        )
        return
    channel = context.args[0].strip()
    from config import remove_training_channel, TRAINING_CHANNELS
    removed = remove_training_channel(channel)
    if removed:
        await update.message.reply_text(
            f"✅ کانال {channel} حذف شد.\n"
            f"📚 کانال‌های فعلی: {', '.join(TRAINING_CHANNELS) or 'هیچ'}",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            f"⚠️ کانال {channel} در لیست نبود.\n"
            f"📚 کانال‌های فعلی: {', '.join(TRAINING_CHANNELS) or 'هیچ'}",
            parse_mode="HTML",
        )


# ─── /summary — خلاصه‌سازی پیام‌های گروه با هوش مصنوعی ───────────────────────

async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    خلاصه پیام‌های اخیر گروه با هوش مصنوعی (/summary یا /kholase)
    """
    message = update.message
    if not message:
        return

    chat = message.chat
    if chat.type == ChatType.PRIVATE:
        await message.reply_text(
            "📌 دستور خلاصه‌ساز مختص گروه‌ها است. آن را داخل گروه اجرا کنید.",
            parse_mode="HTML",
        )
        return

    status_msg = await message.reply_text(
        "⏳ <b>در حال تحلیل و خلاصه‌سازی گفت‌وگوهای اخیر با هوش مصنوعی...</b>",
        parse_mode="HTML",
    )

    try:
        from bot.core.ai_analyzer import generate_group_summary
        # تعداد پیام برای خلاصه (پیش‌فرض ۵۰ پیام، یا قابل تنظیم توسط آرگومان)
        limit = 50
        if context.args and context.args[0].isdigit():
            limit = min(int(context.args[0]), 100)

        recent_messages = await db.get_messages_for_summary(chat.id, limit=limit)
        if not recent_messages or len(recent_messages) < 3:
            await status_msg.edit_text(
                "💬 <b>پیام کافی برای خلاصه‌سازی در حافظه ربات یافت نشد.</b>\n"
                "ربات باید مدتی در گروه پیام‌های ارسالی را ثبت کند.",
                parse_mode="HTML",
            )
            return

        summary_text = await generate_group_summary(recent_messages)
        await status_msg.edit_text(
            summary_text,
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"Error in cmd_summary: {e}")
        try:
            await status_msg.edit_text(
                "❌ متأسفانه در حین تولید خلاصه خطایی رخ داد.",
                parse_mode="HTML",
            )
        except Exception:
            pass


# ─── /info — شناسنامه و اطلاعات جامع کاربر ───────────────────────────────────

async def build_user_info_card(context, chat, target_user_id: int, target_name: str, target_mention_str: str, viewer_id: int) -> tuple[str, InlineKeyboardMarkup | None]:
    level = await db.get_user_level(target_user_id, chat.id)
    points = await db.get_points(target_user_id, chat.id)
    warns = await db.get_warnings(target_user_id, chat.id)
    total_m = await db.get_message_count(target_user_id, chat.id)

    from bot.core.punishment_ranks import get_rank_name
    rank = await db.get_punishment_rank(target_user_id, chat.id)
    rank_disp = get_rank_name(rank) if rank and rank != "clean" else "عادی و پاک"

    cfg = get_config(level)
    today_q = await db.get_query_count(target_user_id, chat.id)
    today_lk = await db.get_daily_action(target_user_id, chat.id, "link")
    today_fw = await db.get_daily_action(target_user_id, chat.id, "forward")
    extra = await db.get_user_daily_stats(target_user_id, chat.id)

    total_mutes = await db.get_punishment_count(target_user_id, chat.id, "mute")
    total_bans = await db.get_punishment_count(target_user_id, chat.id, "ban")
    first_seen = await db.get_user_first_seen(target_user_id, chat.id)
    first_seen_str = first_seen[:16] if first_seen else "نامشخص / عضو جدید"

    tg_status = "👤 عضو عادی"
    try:
        cm = await context.bot.get_chat_member(chat.id, target_user_id)
        st = getattr(cm, "status", "")
        if st in ("creator", "owner"):
            tg_status = "👑 مالک / سازنده گروه"
        elif st == "administrator":
            tg_status = "🛡️ ادمین گروه"
        elif st == "restricted":
            tg_status = "🔇 محدود / میوت‌شده"
        elif st == "kicked":
            tg_status = "🚫 بن / اخراج‌شده"
        elif st == "left":
            tg_status = "🚪 خارج‌شده از گروه"
    except Exception:
        pass

    q_lim = "نامحدود" if cfg.daily_queries == -1 else f"{today_q}/{cfg.daily_queries}"
    lk_lim = "ممنوع" if cfg.daily_links == 0 else ("نامحدود" if cfg.daily_links == -1 else f"{today_lk}/{cfg.daily_links}")
    fw_lim = "ممنوع" if cfg.daily_forwards == 0 else ("نامحدود" if cfg.daily_forwards == -1 else f"{today_fw}/{cfg.daily_forwards}")

    text = (
        f"👤 <b>شناسنامه و وضعیت کاربر</b>\n\n"
        f"<blockquote>"
        f"🆔 شناسه عددی: <code>{target_user_id}</code>\n"
        f"👤 کاربر: {target_mention_str}\n"
        f"🏷️ موقعیت در گروه: <b>{tg_status}</b>\n"
        f"🏅 سطح کاربری: <b>{level_label(level)}</b>\n"
        f"⭐ امتیاز فعالیت: <b>{points}</b>\n"
        f"🏆 رنک جریمه: <b>{rank_disp}</b>"
        f"</blockquote>\n\n"
        f"📊 <b>فعالیت در این گروه:</b>\n"
        f"<blockquote>"
        f"• کل پیام‌های ارسالی: <b>{total_m}</b>\n"
        f"• پیام‌های امروز: <b>{extra['msgs_today']}</b>\n"
        f"• سهمیه سوال هوش مصنوعی: <code>{q_lim}</code>\n"
        f"• سهمیه ارسال لینک: <code>{lk_lim}</code>\n"
        f"• سهمیه فوروارد: <code>{fw_lim}</code>\n"
        f"• اولین مشاهده در ربات: <code>{first_seen_str}</code>"
        f"</blockquote>\n\n"
        f"🛡️ <b>سوابق انضباطی:</b>\n"
        f"<blockquote>"
        f"• اخطارهای فعال: <b>{warns}/{MAX_WARNINGS}</b>\n"
        f"• دفعات میوت در تاریخچه: <b>{total_mutes}</b>\n"
        f"• دفعات بن در تاریخچه: <b>{total_bans}</b>\n"
        f"• تخلفات امروز: <b>{extra['violations_today']}</b>"
        f"</blockquote>"
    )

    kb = None
    if _is_admin(viewer_id) and target_user_id != viewer_id:
        rows = [
            [
                InlineKeyboardButton("⚠️ اخطار (+۱)", callback_data=f"ainf_warn_{target_user_id}"),
                InlineKeyboardButton("🔇 میوت (۳۰د)", callback_data=f"ainf_mute_{target_user_id}"),
                InlineKeyboardButton("🚫 بن", callback_data=f"ainf_ban_{target_user_id}"),
            ],
            [
                InlineKeyboardButton("🔄 به‌روزرسانی اطلاعات", callback_data=f"ainf_ref_{target_user_id}"),
            ]
        ]
        kb = InlineKeyboardMarkup(rows)

    return text, kb


async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    نمایش شناسنامه و آمار جامع کاربر (/info یا /whois)
    """
    message = update.message
    if not message:
        return

    chat = message.chat
    if chat.type == ChatType.PRIVATE:
        await message.reply_text("📌 دستور اطلاعات کاربر مختص گروه‌ها است.")
        return

    viewer = message.from_user
    # اگر ریپلای یا آرگومان نبود، اطلاعات خود ارسال‌کننده نمایش داده شود
    if not message.reply_to_message and not context.args:
        target_id = viewer.id
        target_name = viewer.full_name
        target_mention = mention(viewer)
    else:
        target_id, target_name, target_mention = await _get_target(update, context)

    if not target_id:
        await message.reply_text(
            "❓ کاربر مشخص نشد. روی پیام کاربر ریپلای بزنید یا آیدی عددی/نام‌کاربری وارد کنید:\n"
            "مثال: <code>/info @username</code> یا <code>/info 123456789</code>",
            parse_mode="HTML",
        )
        return

    card_text, kb = await build_user_info_card(
        context=context,
        chat=chat,
        target_user_id=target_id,
        target_name=target_name,
        target_mention_str=target_mention,
        viewer_id=viewer.id,
    )

    await message.reply_text(
        card_text,
        parse_mode="HTML",
        reply_markup=kb,
    )


# ─── /banned — مشاهده لیست کاربران بن‌شده اخیر ────────────────────────────────

async def cmd_banned(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    نمایش کاربران بن‌شده اخیر با امکان آنبن سریع (/banned یا /bans)
    """
    message = update.message
    if not message:
        return

    chat = message.chat
    user = message.from_user
    if chat.type == ChatType.PRIVATE:
        await message.reply_text("📌 این دستور مختص گروه‌ها است.")
        return

    if not _is_admin(user.id):
        await message.reply_text("❌ فقط ادمین‌ها به لیست افراد مسدودشده دسترسی دارند.")
        return

    bans = await db.get_recent_banned_users(chat.id, limit=8)
    if not bans:
        await message.reply_text(
            "✅ <b>هیچ کاربری در تاریخچه مسدودیت‌های این گروه ثبت نشده است.</b>",
            parse_mode="HTML",
        )
        return

    lines = []
    unban_buttons = []
    for i, b in enumerate(bans, 1):
        uid = b["user_id"]
        name = b["name"][:18]
        date_str = b["created_at"][:16] if b.get("created_at") else ""
        reason = b.get("reason") or "تخلف"
        actor = f"توسط ادمین <code>{b['actor_id']}</code>" if b.get("actor_id") else "توسط سیستم/AI"

        lines.append(
            f"<b>{i}. {name}</b> (<code>{uid}</code>)\n"
            f"   📅 تاریخ: <code>{date_str}</code> | {actor}\n"
            f"   📌 علت: <i>{reason}</i>"
        )
        unban_buttons.append(
            InlineKeyboardButton(f"🔓 آنبن: {name[:12]}", callback_data=f"qunb_{uid}")
        )

    cards = "\n\n".join(lines)
    text = (
        f"🚫 <b>لیست کاربران بن‌شده اخیر در گروه:</b>\n\n"
        f"<blockquote>\n{cards}\n</blockquote>\n\n"
        f"💡 <i>جهت رفع مسدودیت هر کاربر، دکمه مربوطه را لمس کنید:</i>"
    )

    rows = [unban_buttons[i:i+2] for i in range(0, len(unban_buttons), 2)]
    kb = InlineKeyboardMarkup(rows) if rows else None

    await message.reply_text(text, parse_mode="HTML", reply_markup=kb)


# ─── /purge — پاکسازی سریع پیام‌ها ──────────────────────────────────────────

async def cmd_purge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    پاکسازی سریع پیام‌ها (/purge یا /del) — فقط ادمین
    """
    message = update.message
    if not message:
        return

    chat = message.chat
    user = message.from_user
    if chat.type == ChatType.PRIVATE or not _is_admin(user.id):
        return

    # ۱. حالت ریپلای: پاکسازی از پیام ریپلای‌شده تا این پیام
    if message.reply_to_message:
        from_id = message.reply_to_message.message_id
        to_id = message.message_id

        if to_id - from_id > 100:
            from_id = to_id - 100

        deleted_count = 0
        for mid in range(from_id, to_id + 1):
            try:
                await context.bot.delete_message(chat.id, mid)
                deleted_count += 1
            except Exception:
                pass

        status = await chat.send_message(
            f"🧹 <b>{deleted_count} پیام با موفقیت پاکسازی شد.</b>",
            parse_mode="HTML",
        )
        import asyncio
        await asyncio.sleep(3)
        try:
            await status.delete()
        except Exception:
            pass
        return

    # ۲. حالت عددی: /purge 15
    count = 10
    if context.args and context.args[0].isdigit():
        count = min(int(context.args[0]), 100)

    cur_id = message.message_id
    deleted_count = 0
    for mid in range(cur_id, cur_id - count - 1, -1):
        try:
            await context.bot.delete_message(chat.id, mid)
            deleted_count += 1
        except Exception:
            pass

    status = await chat.send_message(
        f"🧹 <b>{deleted_count} پیام اخیر با موفقیت پاکسازی شد.</b>",
        parse_mode="HTML",
    )
    import asyncio
    await asyncio.sleep(3)
    try:
        await status.delete()
    except Exception:
        pass


# ─── /help — راهنمای جامع دستورات ────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش منوی راهنما (معادل /start اما اختصاصی راهنما)"""
    await cmd_start(update, context)


# ─── /price — استعلام هوشمند قیمت کالا (ترب)، طلا، ارز و رمزارزها ───────────

async def cmd_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    استعلام هوشمند قیمت کالا (ترب)، طلا، سکه، ارز و رمزارزها (/price یا /gheymat)
    """
    message = update.message
    if not message:
        return

    query = " ".join(context.args).strip() if context.args else ""

    if not query:
        # منوی تعاملی و دسته‌بندی‌شده استعلام قیمت
        from bot.core.knowledge_engine import search_price_all
        res = await search_price_all("")

        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("💵 نرخ ارز و دلار", callback_data="prc_currency"),
                InlineKeyboardButton("🪙 طلا و انواع سکه", callback_data="prc_gold"),
            ],
            [
                InlineKeyboardButton("⚡ بازار رمزارزها (BTC/TON)", callback_data="prc_crypto"),
            ],
            [
                InlineKeyboardButton("🧹 قیمت انواع جاروبرقی", callback_data="prc_it_جاروبرقی"),
                InlineKeyboardButton("📱 قیمت روز موبایل", callback_data="prc_it_گوشی موبایل"),
            ],
            [
                InlineKeyboardButton("💻 قیمت لپ‌تاپ", callback_data="prc_it_لپ تاپ"),
                InlineKeyboardButton("🎮 قیمت کنسول PS5", callback_data="prc_it_پلی استیشن 5"),
            ],
        ])
        await message.reply_text(res["text"], parse_mode="HTML", reply_markup=kb)
        return

    status_msg = await message.reply_text("🔍 در حال استعلام قیمت لحظه‌ای...")

    from bot.core.knowledge_engine import search_price_all
    res = await search_price_all(query)

    # ساخت دکمه‌های متناسب با نوع نتیجه
    kb_rows = []
    if res.get("type") == "product" and res.get("search_url"):
        import urllib.parse
        enc = urllib.parse.quote(res.get("query", query))
        kb_rows.append([
            InlineKeyboardButton("🔗 مشاهده همه فروشگاه‌ها در ترب", url=res["search_url"]),
        ])
        kb_rows.append([
            InlineKeyboardButton("🔄 بروزرسانی قیمت", callback_data=f"prc_it_{enc[:30]}"),
        ])
    elif res.get("type") == "crypto":
        kb_rows.append([
            InlineKeyboardButton("🔄 بروزرسانی رمزارزها", callback_data="prc_crypto"),
            InlineKeyboardButton("💵 نرخ ارز و دلار", callback_data="prc_currency"),
        ])
    elif res.get("type") == "gold":
        kb_rows.append([
            InlineKeyboardButton("🔄 بروزرسانی طلا و سکه", callback_data="prc_gold"),
            InlineKeyboardButton("💵 نرخ ارز و دلار", callback_data="prc_currency"),
        ])
    elif res.get("type") == "currency":
        kb_rows.append([
            InlineKeyboardButton("🔄 بروزرسانی نرخ ارز", callback_data="prc_currency"),
            InlineKeyboardButton("🪙 طلا و انواع سکه", callback_data="prc_gold"),
        ])

    kb = InlineKeyboardMarkup(kb_rows) if kb_rows else None

    try:
        await status_msg.edit_text(res["text"], parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
    except Exception:
        await message.reply_text(res["text"], parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)


# ─── /time /date — ساعت رسمی، روز هفته و تقویم خورشیدی و میلادی ──────────────

async def cmd_datetime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    نمایش ساعت رسمی کشور، روز هفته و تقویم خورشیدی و میلادی (/time, /date, /saat)
    """
    message = update.message
    if not message:
        return
    from bot.utils.helpers import get_datetime_response
    txt = get_datetime_response()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 بروزرسانی زمان", callback_data="dt_refresh")],
    ])
    await message.reply_text(txt, parse_mode="HTML", reply_markup=kb)



