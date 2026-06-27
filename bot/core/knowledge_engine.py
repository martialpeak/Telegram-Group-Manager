"""
موتور دانش — Cache → Groq (primary) → Gemini (fallback)
جواب‌های AI در cache ذخیره می‌شن تا درخواست‌های تکراری API نزنن
"""

import logging
import asyncio
import hashlib
from typing import Optional

from config import (
    GROQ_API_KEY, GROQ_MODEL,
    GEMINI_API_KEY, GEMINI_MODEL,
    SEARCH_TOP_K, LEARNING_MIN_SCORE,
    CACHE_MIN_SCORE, CACHE_TTL_HOURS,
)
import bot.db.database as db

logger = logging.getLogger(__name__)

# ── راه‌اندازی Groq ───────────────────────────────────────────────────────────
_groq_client = None
if GROQ_API_KEY:
    try:
        from groq import Groq
        _groq_client = Groq(api_key=GROQ_API_KEY)
    except Exception as e:
        logger.warning(f"Groq init failed: {e}")

# ── راه‌اندازی Gemini ─────────────────────────────────────────────────────────
_gemini_model = None
if GEMINI_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        # gemini-2.5-flash مدل فعلی پیشنهادی Google
        _model_name = GEMINI_MODEL if GEMINI_MODEL else "gemini-2.5-flash"
        _gemini_model = genai.GenerativeModel(_model_name)
    except Exception as e:
        logger.warning(f"Gemini init failed: {e}")

# ── System prompt برای پاسخ‌دهی (تخصصی VPN/شبکه) ─────────────────────────────
ANSWER_SYSTEM_PROMPT = (
    "تو یک متخصص فنی در حوزه VPN، شبکه، کانفیگ‌های v2ray/xray، پروتکل‌های "
    "پروکسی (vless, vmess, trojan, shadowsocks, hysteria, wireguard) و مسائل "
    "اینترنت آزاد هستی که در یک گروه تلگرامی فارسی‌زبان کمک می‌کنی.\n\n"
    "اصول پاسخ‌گویی:\n"
    "- همیشه به فارسی روان، دقیق و کاربردی پاسخ بده.\n"
    "- برای سوالات فنی، جزئیات و مراحل واضح بده؛ اگه کانفیگ/دستور لازمه، با بلوک کد بنویس.\n"
    "- پروتکل‌ها، پورت‌ها و تنظیمات رو با مثال‌های واقعی توضیح بده.\n"
    "- اگه اطلاعات قطعی نداری، صادقانه بگو «مطمئن نیستم» و پیشنهاد بده کجا جستجو کنن.\n"
    "- از اغراق، وعده‌های غیرواقعی یا اطلاعات قدیمی/اشتباه خودداری کن.\n"
    "- پاسخ رو ساختارمند بنویس: اگه چند نکته داری، شماره‌گذاری کن.\n"
    "- لحن دوستانه اما حرفه‌ای داشته باش.\n"
    "- برای سوالات امنیتی، روی محرمانگی و روش‌های امن تأکید کن.\n"
)

PROMPT_TEMPLATE = (
    "{context}"
    "سوال کاربر: {question}\n\n"
    "به این سوال به‌طور کامل و دقیق پاسخ بده:"
)


# ─── Cache key ───────────────────────────────────────────────────────────────

def _cache_key(question: str) -> str:
    return hashlib.md5(question.strip().lower().encode()).hexdigest()


def _normalize_question(text: str) -> str:
    """حذف کاراکترهای اضافه، علائم و کلمات توقف برای مقایسه بهتر"""
    import re
    text = text.strip().lower()
    # حذف علائم نگارشی و کاراکترهای خاص
    text = re.sub(r'[،؟!؟.,?!:;"\'\-_()]+', ' ', text)
    # حذف کلمات توقف فارسی و انگلیسی
    stop_words = {
        'سلام', 'خب', 'خوب', 'ببین', 'بگو', 'ممنون', 'مرسی', 'لطفا', 'لطفاً',
        'hello', 'hi', 'hey', 'please', 'thanks', 'ok', 'okay',
        'the', 'a', 'an', 'is', 'are', 'was', 'were',
    }
    words = [w for w in text.split() if w and w not in stop_words]
    return ' '.join(words)


def _similarity(q1: str, q2: str) -> float:
    """شباهت بین دو سوال با در نظر گرفتن کلمات مشترک"""
    w1 = set(_normalize_question(q1).split())
    w2 = set(_normalize_question(q2).split())
    if not w1 or not w2:
        return 0.0
    common = len(w1 & w2)
    # Jaccard similarity
    union = len(w1 | w2)
    jaccard = common / union if union else 0.0
    # overlap نسبت به سوال کوتاه‌تر
    overlap = common / min(len(w1), len(w2))
    # میانگین وزن‌دار
    return 0.4 * jaccard + 0.6 * overlap


# ─── جستجوی شباهت در پایگاه دانش ────────────────────────────────────────────

async def _search_knowledge(question: str, chat_id: int) -> Optional[dict]:
    items = await db.get_knowledge(chat_id)
    if not items:
        return None
    best, best_score = None, 0.0
    for item in items:
        score = _similarity(question, item["question"])
        if score > best_score:
            best_score = score
            best = {**item, "score": score}
    if best and best_score >= CACHE_MIN_SCORE:
        logger.info(f"Cache hit (score={best_score:.2f}): '{question[:40]}' ≈ '{best['question'][:40]}'")
        return best
    return None


async def _search_history(query: str, chat_id: int) -> list[dict]:
    keywords = [w for w in query.split() if len(w) > 2][:5]
    results, seen = [], set()
    for kw in keywords:
        msgs = await db.search_messages(kw, chat_id, limit=5)
        for m in msgs:
            if m["text"] not in seen:
                seen.add(m["text"])
                results.append(m)
    return results[:SEARCH_TOP_K]


# ─── تولید پاسخ با Groq ──────────────────────────────────────────────────────

async def _generate_groq(question: str, context: str) -> Optional[str]:
    if not _groq_client:
        return None
    prompt = PROMPT_TEMPLATE.format(context=context, question=question)
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: _groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": ANSWER_SYSTEM_PROMPT,
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,   # کمی بالاتر = پاسخ طبیعی‌تر ولی هنوز دقیق
                max_tokens=2500,   # پاسخ‌های کامل و تخصصی
                top_p=0.9,
            )
        )
        answer = response.choices[0].message.content.strip()
        return answer if answer and len(answer) > 5 else None
    except Exception as e:
        logger.warning(f"Groq answer failed: {e}")
        return None


# ─── تولید پاسخ با Gemini ────────────────────────────────────────────────────

async def _generate_gemini(question: str, context: str) -> Optional[str]:
    if not _gemini_model:
        return None
    import google.generativeai as genai
    prompt = PROMPT_TEMPLATE.format(context=context, question=question)
    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: _gemini_model.generate_content(
                f"{ANSWER_SYSTEM_PROMPT}\n\n{prompt}",
                generation_config=genai.types.GenerationConfig(
                    temperature=0.2,
                    max_output_tokens=2500,
                    top_p=0.9,
                ),
            )
        )
        answer = response.text.strip()
        return answer if answer and len(answer) > 5 else None
    except Exception as e:
        logger.warning(f"Gemini answer failed: {e}")
        return None


# ─── پاسخ به سوال ────────────────────────────────────────────────────────────

async def answer_question(question: str, chat_id: int) -> dict:
    # ۱. Cache — پایگاه دانش
    cached = await _search_knowledge(question, chat_id)
    if cached:
        await db.increment_use(cached["id"])
        return {
            "answer": cached["answer"],
            "source": "knowledge_base",
            "confidence": cached["score"],
        }

    # ۲. تاریخچه گروه برای context
    history = await _search_history(question, chat_id)
    context = ""
    if history:
        lines = "\n".join(
            f"- {m['name']}: {m['text']}" for m in history[:5]
        )
        context = (
            "\n\nاطلاعات مرتبط از تاریخچه گروه "
            "(این داده‌ها از گفت‌وگوی قبلی کاربران هستن، "
            "می‌تونی برای غنی‌تر کردن پاسخ ازشون استفاده کنی):\n"
            f"{lines}\n\n"
        )

    # ۳. Groq (primary)
    answer = await _generate_groq(question, context)
    source = "groq"

    # ۴. Gemini (fallback)
    if not answer:
        logger.info("Groq unavailable, trying Gemini...")
        answer = await _generate_gemini(question, context)
        source = "gemini"

    # ۵. ذخیره در cache با سوال normalize شده برای match بهتر
    if answer:
        normalized = _normalize_question(question)
        store_q = normalized if len(normalized) >= 3 else question
        await db.save_knowledge(
            question=store_q,
            answer=answer,
            chat_id=chat_id,
            source=source,
            score=0.80,
        )
        logger.info(f"Answer via {source}, cached: '{store_q[:50]}'")

    return {
        "answer": answer or "متاسفم، اطلاعات کافی برای پاسخ به این سوال ندارم.",
        "source": source if answer else "none",
        "confidence": 0.8 if answer else 0.0,
        "history_used": len(history),
    }


# ─── یادگیری از فیدبک ────────────────────────────────────────────────────────

async def learn_from_feedback() -> int:
    feedbacks = await db.get_pending_feedback(limit=50)
    if not feedbacks:
        return 0
    count = 0
    for fb in feedbacks:
        if fb["answer"] and len(fb["answer"]) > 5:
            await db.save_knowledge(
                question=fb["question"],
                answer=fb["answer"],
                chat_id=fb["chat_id"],
                source="user_feedback",
                score=0.95,
            )
            count += 1
    logger.info(f"🧠 {count} مورد از فیدبک یاد گرفته شد.")
    return count
