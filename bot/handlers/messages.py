"""
هندلرهای پیام متنی، مدیا و تصحیح
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.constants import ChatType

from config import (
    MAX_WARNINGS, SPAM_TIME_WINDOW, SPAM_MAX_MESSAGES,
    ADMIN_IDS, MIN_CONFIDENCE,
)
import bot.db.database as db
from bot.core import moderation as mod
from bot.core.ai_analyzer import analyze_message
from bot.core.knowledge_engine import answer_question, learn_from_feedback
from bot.core.user_levels import get_config, level_label, next_auto_level
from bot.utils.helpers import mention, send_and_delete, is_addressing_bot, build_vote_keyboard
from i18n import t

logger = logging.getLogger(__name__)

# ذخیره موقت آخرین پاسخ‌های ربات برای دریافت فیدبک
_pending_answers: dict[str, dict] = {}

# cache کاربرانی که تگ گرفتن در این session — جلوگیری از API call مکرر
_tagged_users: set[tuple[int, int]] = set()

_MIN_CORRECTION_LEN = 10
_MAX_CORRECTION_LEN = 1000
_MAX_FB_PER_HOUR    = 5
_VOTES_TO_CONFIRM   = 2
_VOTES_TO_REJECT    = 3

# آستانه‌های ارتقاء بر اساس امتیاز
UPGRADE_THRESHOLDS = {
    "simple":  (100,  "bronze"),
    "bronze":  (500,  "silver"),
    "silver":  (2000, "gold"),
}


def _is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


def _validate_correction(text: str) -> tuple[bool, str]:
    text = text.strip()
    if len(text) < _MIN_CORRECTION_LEN:
        return False, f"❌ تصحیح خیلی کوتاهه! حداقل {_MIN_CORRECTION_LEN} کاراکتر بنویس."
    if len(text) > _MAX_CORRECTION_LEN:
        return False, f"❌ تصحیح خیلی طولانیه! حداکثر {_MAX_CORRECTION_LEN} کاراکتر."
    if len(set(text.replace(" ", ""))) < 3:
        return False, "❌ این تصحیح معتبر نیست. لطفاً جواب واقعی بنویس."
    return True, ""


# ─── بررسی محدودیت‌های سطح کاربری ────────────────────────────────────────────

async def _check_level_restrictions(message, bot) -> bool:
    """
    True = پیام تخلف داشت و متوقف شد
    False = اشکالی نیست
    """
    user    = message.from_user
    chat_id = message.chat_id

    if _is_admin(user.id):
        return False

    level  = await db.get_user_level(user.id, chat_id)
    config = get_config(level)
    tag    = mention(user)
    lv_lbl = level_label(level)

    # ── فوروارد ──────────────────────────────────────────────────────────────
    is_forward = bool(message.forward_origin)
    if is_forward:
        if config.daily_forwards == 0:
            await mod.handle_level_violation(bot, message, "فوروارد ممنوع")
            return True
        if config.daily_forwards != -1:
            count = await db.increment_daily_action(user.id, chat_id, "forward")
            if count > config.daily_forwards:
                await mod.handle_level_violation(
                    bot, message,
                    f"تجاوز از سقف فوروارد روزانه ({config.daily_forwards})",
                )
                return True

    # ── مدیا ─────────────────────────────────────────────────────────────────
    has_media = any([
        message.photo, message.video, message.document,
        message.audio, message.voice, message.video_note,
        message.sticker, message.animation,
    ])
    if has_media and not config.can_media:
        await mod.handle_level_violation(bot, message, "ارسال مدیا ممنوع")
        return True

    # ── استیکر / گیف / انیمیشن ──────────────────────────────────────────────
    has_sticker = bool(message.sticker or message.animation)
    if has_sticker:
        if config.daily_stickers == 0:
            await mod.handle_level_violation(bot, message, "ارسال استیکر/گیف ممنوع")
            return True
        if config.daily_stickers != -1:
            count = await db.increment_daily_action(user.id, chat_id, "sticker")
            if count > config.daily_stickers:
                await mod.handle_level_violation(
                    bot, message,
                    f"تجاوز از سقف استیکر/گیف روزانه ({config.daily_stickers})",
                )
                return True

    return False


# ─── بررسی آستانه ارتقاء بر اساس امتیاز ─────────────────────────────────────

async def _check_upgrade_threshold(bot, user, chat_id: int, points: int):
    """اگه کاربر به آستانه ارتقاء رسید، به ادمین اطلاع بده"""
    level = await db.get_user_level(user.id, chat_id)
    if level not in UPGRADE_THRESHOLDS:
        return
    threshold, to_level = UPGRADE_THRESHOLDS[level]
    if points < threshold:
        return
    # چک کن pending نداشته باشه
    existing = await db.get_upgrade_pending(user.id, chat_id)
    if existing:
        return
    # ذخیره
    await db.save_upgrade_pending(user.id, chat_id, level, to_level, points)
    # اطلاع به ادمین‌ها
    tag = mention(user)
    from bot.core.user_levels import level_label as _lv_lbl
    text = (
        f"🎖️ <b>درخواست ارتقاء سطح</b>\n\n"
        f"👤 کاربر: {tag}\n"
        f"📊 امتیاز: {points}\n"
        f"🏅 از: {level} → {to_level}\n"
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ تأیید", callback_data=f"upg_approve_{user.id}_{chat_id}"),
        InlineKeyboardButton("❌ رد",    callback_data=f"upg_reject_{user.id}_{chat_id}"),
    ]])
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=text,
                parse_mode="HTML",
                reply_markup=keyboard,
            )
        except Exception:
            pass


# ─── هندلر مدیا/فوروارد ──────────────────────────────────────────────────────

async def on_media_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.from_user:
        return
    if message.from_user.is_bot:
        return
    if message.chat.type == ChatType.PRIVATE:
        return

    # auto-tag
    user = message.from_user
    tag_key = (user.id, message.chat_id)
    if tag_key not in _tagged_users:
        _tagged_users.add(tag_key)
        level_for_tag = await db.get_user_level(user.id, message.chat_id)
        from bot.core.moderation import _set_status_tag
        from bot.core.user_levels import get_config as _get_cfg
        _cfg = _get_cfg(level_for_tag)
        await _set_status_tag(context.bot, message.chat_id, user.id, _cfg.tag)

    await _check_level_restrictions(message, context.bot)

    # ── امتیاز مدیا ──────────────────────────────────────────────────────────
    if not _is_admin(user.id):
        is_sticker_type = bool(message.sticker or message.animation)
        delta = 1 if is_sticker_type else 2
        pts = await db.add_points(user.id, message.chat_id, delta)
        await _check_upgrade_threshold(context.bot, user, message.chat_id, pts)


# ─── هندلر اصلی پیام‌های متنی ────────────────────────────────────────────────

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return

    user = message.from_user
    if not user or user.is_bot:
        return

    chat = message.chat

    if chat.type == ChatType.PRIVATE:
        await _handle_private(update, context)
        return

    # اگه این پیام قبلاً به عنوان تصحیح پردازش شده، skip کن
    if context.user_data.pop("_correction_handled", False):
        return

    if not _is_admin(user.id):
        blocked = await _check_level_restrictions(message, context.bot)
        if blocked:
            return

    if _is_admin(user.id):
        await db.log_message(
            user.id, chat.id, user.username or "",
            user.full_name, message.text, "normal", 1.0,
        )
        # ادمین هم می‌تونه با mention سوال بپرسه
        bot_username = context.bot.username
        if is_addressing_bot(message, bot_username):
            clean_q = message.text.strip().replace(f"@{bot_username}", "").strip()
            result  = await answer_question(clean_q, chat.id)
            await message.reply_text(f"🤖 {result['answer']}")
        return

    text = message.text.strip()
    if len(text) < 2:
        return

    # ── auto-tag: اولین پیام هر کاربر در این session تگش ست می‌شه ──────────
    tag_key = (user.id, chat.id)
    if tag_key not in _tagged_users:
        _tagged_users.add(tag_key)
        level_for_tag = await db.get_user_level(user.id, chat.id)
        from bot.core.moderation import _set_status_tag
        from bot.core.user_levels import get_config as _get_cfg
        _cfg = _get_cfg(level_for_tag)
        await _set_status_tag(context.bot, chat.id, user.id, _cfg.tag)

    # ── اسپم سرعتی ───────────────────────────────────────────────────────────
    is_rate_spam = await db.track_spam(user.id, chat.id, SPAM_TIME_WINDOW, SPAM_MAX_MESSAGES)

    # ── شمارش پیام برای ارتقاء خودکار ───────────────────────────────────────
    msg_count = await db.increment_message_count(user.id, chat.id)
    level     = await db.get_user_level(user.id, chat.id)
    next_lv   = next_auto_level(level)
    if next_lv:
        threshold = get_config(level).auto_upgrade_msgs
        if threshold and msg_count >= threshold:
            await db.set_user_level(user.id, chat.id, next_lv, set_by=0)
            new_cfg = get_config(next_lv)
            from bot.core.moderation import _set_status_tag
            await _set_status_tag(context.bot, chat.id, user.id, new_cfg.tag)
            await chat.send_message(
                f"🎉 {mention(user)} به سطح {level_label(next_lv)} ارتقاء پیدا کرد!",
                parse_mode="HTML",
            )

    # ── امتیاز پیام متنی: +1 ─────────────────────────────────────────────────
    pts = await db.add_points(user.id, chat.id, 1)
    await _check_upgrade_threshold(context.bot, user, chat.id, pts)

    # ── تحلیل AI ─────────────────────────────────────────────────────────────
    bot_username = context.bot.username
    is_mentioned = is_addressing_bot(message, bot_username)

    # اگه مستقیم mention شده → جواب بده (صرف‌نظر از نوع AI)
    if is_mentioned:
        clean_q = text.replace(f"@{bot_username}", "").strip()
        # پیام خیلی کوتاه و بی‌معنی — نادیده بگیر
        if len(clean_q) < 2:
            return

        level  = await db.get_user_level(user.id, chat.id)
        config = get_config(level)
        if config.daily_queries != -1:
            count = await db.increment_query_count(user.id, chat.id)
            if count > config.daily_queries:
                await send_and_delete(
                    message,
                    t("query_limit", name=user.full_name, limit=config.daily_queries),
                    delay=15,
                )
                await db.log_message(
                    user.id, chat.id, user.username or "",
                    user.full_name, text, "request_limit", 1.0,
                )
                return
        else:
            await db.increment_query_count(user.id, chat.id)

        result  = await answer_question(clean_q, chat.id)
        no_answer = result.get("source") == "none"

        key = f"{user.id}_{message.message_id}"
        _pending_answers[key] = {
            "question": clean_q,
            "answer":   result["answer"],
            "user_id":  user.id,
            "chat_id":  chat.id,
            "msg_id":   message.message_id,
            "user_name": user.full_name,
            "chat_title": chat.title or "PV",
        }

        if no_answer:
            # ربات جواب نداره — به ادمین اطلاع بده
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            admin_keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    "✍️ پاسخ و تأیید",
                    callback_data=f"adm_ans_{key}"
                ),
                InlineKeyboardButton(
                    "🚫 نادیده",
                    callback_data=f"adm_skip_{key}"
                ),
            ]])
            admin_text = (
                f"❓ <b>سوال بی‌جواب</b>\n\n"
                f"👤 کاربر: {mention(user)}\n"
                f"💬 گروه: {chat.title or 'PV'}\n\n"
                f"سوال:\n<code>{clean_q[:300]}</code>\n\n"
                "پاسخی بنویس تا هم کاربر جواب بگیره هم ربات یاد بگیره:"
            )
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=admin_text,
                        parse_mode="HTML",
                        reply_markup=admin_keyboard,
                    )
                except Exception:
                    pass
            # به کاربر پیام موقت بده
            await send_and_delete(
                message,
                f"🤖 سوالت ثبت شد و به ادمین ارسال شد. به زودی جواب می‌گیری!",
                delay=300,
            )
        else:
            # ربات جواب داره — مستقیم نشون بده
            answer_text = t("request_handled", response=result["answer"])
            source_label = "📚" if result.get("source") == "knowledge_base" else "🤖"
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ درسته",   callback_data=f"fb_ok_{key}"),
                InlineKeyboardButton("❌ اشتباهه", callback_data=f"fb_no_{key}"),
            ]])
            await message.reply_text(f"{source_label} {answer_text}", reply_markup=keyboard)

        await db.log_message(
            user.id, chat.id, user.username or "",
            user.full_name, text, "request", 1.0,
        )
        return

    analysis   = await analyze_message(text)
    msg_type   = analysis["type"]
    confidence = analysis["confidence"]

    logger.info(
        f"[{chat.title}] {user.full_name}: "
        f"{msg_type}({confidence:.2f}) — {analysis['reason']}"
    )

    if is_rate_spam and msg_type == "normal":
        # فقط وقتی پیام‌های متعدد و سریع همزمان با محتوای مشکوک باشه
        # rate spam به تنهایی بدون تأیید AI اقدام نمی‌کنه
        logger.info(f"[{chat.title}] {user.full_name}: rate-spam detected but AI said normal — skipping")

    # ── اقدام مدیریتی ────────────────────────────────────────────────────────
    reply_text = None
    parse_mode = None

    if msg_type == "insult" and confidence >= 0.90:
        reply_text, parse_mode = await mod.handle_insult(context.bot, message, analysis)

    elif msg_type == "spam" and confidence >= 0.92:
        reply_text, parse_mode = await mod.handle_spam(context.bot, message, analysis)

    elif msg_type == "request" and confidence >= MIN_CONFIDENCE:
        # mention نشده — فقط log کن
        await db.log_message(
            user.id, chat.id, user.username or "",
            user.full_name, text, "request_ignored", confidence,
        )
        return

    else:
        await db.log_message(
            user.id, chat.id, user.username or "",
            user.full_name, text, "normal", confidence,
        )

    if reply_text:
        await send_and_delete(message, reply_text, delay=300, parse_mode=parse_mode)


# ─── پیام خصوصی ──────────────────────────────────────────────────────────────

async def _handle_private(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    text    = message.text.strip()
    if text.startswith("/"):
        return
    result = await answer_question(text, chat_id=0)
    await message.reply_text(f"🤖 {result['answer']}")


# ─── تصحیح ───────────────────────────────────────────────────────────────────

async def on_correction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = context.user_data.get("awaiting_correction")
    if not key:
        return
    correction = update.message.text.strip()
    valid, err_msg = _validate_correction(correction)
    if not valid:
        await update.message.reply_text(err_msg)
        return
    context.user_data.pop("awaiting_correction")
    # علامت‌گذاری که این پیام تصحیح بود — on_message باید skip کنه
    context.user_data["_correction_handled"] = True
    info = _pending_answers.pop(key, None)
    if not info:
        await update.message.reply_text("⚠️ زمان ثبت تصحیح گذشته. دوباره سوال بپرس.")
        return
    user = update.message.from_user
    prev = await db.count_user_corrections(user.id, info["chat_id"], info["question"])
    if prev >= 2:
        await update.message.reply_text("⚠️ قبلاً برای این سوال تصحیح فرستادی!")
        return
    fb_id = await db.save_feedback(
        info["user_id"], info["chat_id"],
        info["question"], info["answer"],
        correct=False, correction=correction,
    )
    vote_kb = build_vote_keyboard(fb_id, 0, 0)
    await update.message.reply_text(
        f"📝 تصحیح دریافت شد!\n\n"
        f"❓ <b>سوال:</b> {info['question'][:100]}\n"
        f"💬 <b>تصحیح:</b> {correction[:200]}\n\n"
        f"دیگران می‌تونن تایید یا رد کنن 👇\n"
        f"(نیاز به {_VOTES_TO_CONFIRM} رای موافق)",
        parse_mode="HTML",
        reply_markup=vote_kb,
    )
    await update.message.reply_text(t("learned"))


# ─── Export برای callbacks (دسترسی به _pending_answers) ─────────────────────

def get_pending_answers() -> dict:
    return _pending_answers
