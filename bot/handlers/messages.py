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

_MIN_CORRECTION_LEN = 10
_MAX_CORRECTION_LEN = 1000
_MAX_FB_PER_HOUR    = 5
_VOTES_TO_CONFIRM   = 2
_VOTES_TO_REJECT    = 3


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
            txt, pm = await mod.handle_level_violation(bot, message, "فوروارد ممنوع")
            await bot.send_message(message.chat_id, txt, parse_mode=pm)
            return True
        if config.daily_forwards != -1:
            count = await db.increment_daily_action(user.id, chat_id, "forward")
            if count > config.daily_forwards:
                txt, pm = await mod.handle_level_violation(
                    bot, message,
                    f"تجاوز از سقف فوروارد روزانه ({config.daily_forwards})",
                )
                await bot.send_message(message.chat_id, txt, parse_mode=pm)
                return True

    # ── مدیا ─────────────────────────────────────────────────────────────────
    has_media = any([
        message.photo, message.video, message.document,
        message.audio, message.voice, message.video_note,
        message.sticker, message.animation,
    ])
    if has_media and not config.can_media:
        txt, pm = await mod.handle_level_violation(bot, message, "ارسال مدیا ممنوع")
        await bot.send_message(message.chat_id, txt, parse_mode=pm)
        return True

    # ── لینک ─────────────────────────────────────────────────────────────────
    text     = message.text or message.caption or ""
    entities = list(message.entities or []) + list(message.caption_entities or [])
    has_link = (
        any(e.type in ("url", "text_link") for e in entities)
        or "http://" in text or "https://" in text or "t.me/" in text
    )
    if has_link:
        if config.daily_links == 0:
            txt, pm = await mod.handle_level_violation(bot, message, "ارسال لینک ممنوع")
            await bot.send_message(message.chat_id, txt, parse_mode=pm)
            return True
        if config.daily_links != -1:
            count = await db.increment_daily_action(user.id, chat_id, "link")
            if count > config.daily_links:
                txt, pm = await mod.handle_level_violation(
                    bot, message,
                    f"تجاوز از سقف لینک روزانه ({config.daily_links})",
                )
                await bot.send_message(message.chat_id, txt, parse_mode=pm)
                return True

    return False


# ─── هندلر مدیا/فوروارد ──────────────────────────────────────────────────────

async def on_media_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.from_user:
        return
    if message.chat.type == ChatType.PRIVATE:
        return
    await _check_level_restrictions(message, context.bot)


# ─── هندلر اصلی پیام‌های متنی ────────────────────────────────────────────────

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return

    user = message.from_user
    chat = message.chat

    if chat.type == ChatType.PRIVATE:
        await _handle_private(update, context)
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
            try:
                await context.bot.set_chat_member_tag(
                    chat_id=chat.id, user_id=user.id, tag=new_cfg.label,
                )
            except Exception as e:
                logger.warning(f"auto-upgrade tag set failed: {e}")
            await chat.send_message(
                f"🎉 {mention(user)} به سطح {level_label(next_lv)} ارتقاء پیدا کرد!",
                parse_mode="HTML",
            )

    # ── تحلیل AI ─────────────────────────────────────────────────────────────
    bot_username = context.bot.username
    is_mentioned = is_addressing_bot(message, bot_username)

    # اگه مستقیم mention شده → جواب بده (صرف‌نظر از نوع AI)
    if is_mentioned:
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

        clean_q = text.replace(f"@{bot_username}", "").strip()
        result  = await answer_question(clean_q, chat.id)
        answer_text = t("request_handled", response=result["answer"])

        key = f"{user.id}_{message.message_id}"
        _pending_answers[key] = {
            "question": clean_q,
            "answer":   result["answer"],
            "user_id":  user.id,
            "chat_id":  chat.id,
        }
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
        msg_type   = "spam"
        confidence = 0.9
        analysis.update({"type": "spam", "reason": "ارسال سریع پیام‌های متعدد", "confidence": 0.9})

    # ── اقدام مدیریتی ────────────────────────────────────────────────────────
    reply_text = None
    parse_mode = None

    if msg_type == "insult" and confidence >= MIN_CONFIDENCE:
        reply_text, parse_mode = await mod.handle_insult(context.bot, message, analysis)

    elif msg_type == "spam" and confidence >= MIN_CONFIDENCE:
        reply_text, parse_mode = await mod.handle_spam(context.bot, message, analysis)

    elif msg_type == "request" and confidence >= MIN_CONFIDENCE:
        bot_username = context.bot.username
        if not is_addressing_bot(message, bot_username):
            await db.log_message(
                user.id, chat.id, user.username or "",
                user.full_name, text, "request_ignored", confidence,
            )
            return

        # ── بررسی سهمیه روزانه ───────────────────────────────────────────────
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
                return
        else:
            await db.increment_query_count(user.id, chat.id)

        # ── پاسخ ─────────────────────────────────────────────────────────────
        clean_q = text.replace(f"@{bot_username}", "").strip()
        result  = await answer_question(clean_q, chat.id)
        reply_text = t("request_handled", response=result["answer"])

        key = f"{user.id}_{message.message_id}"
        _pending_answers[key] = {
            "question": clean_q,
            "answer":   result["answer"],
            "user_id":  user.id,
            "chat_id":  chat.id,
        }
        source_label = "📚" if result.get("source") == "knowledge_base" else "🤖"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ درسته",   callback_data=f"fb_ok_{key}"),
            InlineKeyboardButton("❌ اشتباهه", callback_data=f"fb_no_{key}"),
        ]])
        await message.reply_text(
            f"{source_label} {reply_text}", reply_markup=keyboard
        )
        await db.log_message(
            user.id, chat.id, user.username or "",
            user.full_name, text, "request", confidence,
        )
        return

    else:
        await db.log_message(
            user.id, chat.id, user.username or "",
            user.full_name, text, "normal", confidence,
        )

    if reply_text:
        await send_and_delete(message, reply_text, delay=45, parse_mode=parse_mode)


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
        f"❓ *سوال:* {info['question'][:100]}\n"
        f"💬 *تصحیح:* {correction[:200]}\n\n"
        f"دیگران می‌تونن تایید یا رد کنن 👇\n"
        f"_(نیاز به {_VOTES_TO_CONFIRM} رای موافق)_",
        parse_mode="HTML",
        reply_markup=vote_kb,
    )
    await update.message.reply_text(t("learned"))


# ─── Export برای callbacks (دسترسی به _pending_answers) ─────────────────────

def get_pending_answers() -> dict:
    return _pending_answers
