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
        _gemini_model = genai.GenerativeModel(GEMINI_MODEL)
    except Exception as e:
        logger.warning(f"Gemini init failed: {e}")

PROMPT_TEMPLATE = (
    "تو دستیار هوشمند یک گروه تلگرامی هستی.{context}\n"
    "سوال کاربر: {question}\n\n"
    "پاسخ کوتاه، مفید و به زبان فارسی بده. "
    "اگر اطلاعات کافی نداری صادقانه بگو."
)


# ─── Cache key ───────────────────────────────────────────────────────────────

def _cache_key(question: str) -> str:
    return hashlib.md5(question.strip().lower().encode()).hexdigest()


# ─── جستجوی شباهت در پایگاه دانش ────────────────────────────────────────────

async def _search_knowledge(question: str, chat_id: int) -> Optional[dict]:
    items = await db.get_knowledge(chat_id)
    if not items:
        return None
    q_words = set(question.lower().split())
    best, best_score = None, 0.0
    for item in items:
        words = set(item["question"].lower().split())
        if not q_words:
            continue
        common = len(q_words & words)
        score = common / max(len(q_words), 1)
        if score > best_score:
            best_score = score
            best = {**item, "score": score}
    return best if best and best_score >= CACHE_MIN_SCORE else None


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
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500,
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
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,
                    max_output_tokens=500,
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
        logger.info(f"Cache hit (score={cached['score']:.2f}): {question[:50]}")
        return {
            "answer": cached["answer"],
            "source": "cache",
            "confidence": cached["score"],
        }

    # ۲. تاریخچه گروه برای context
    history = await _search_history(question, chat_id)
    context = ""
    if history:
        lines = "\n".join(f"- {m['name']}: {m['text']}" for m in history[:5])
        context = f"\nاطلاعات مرتبط از گروه:\n{lines}\n"

    # ۳. Groq (primary)
    answer = await _generate_groq(question, context)
    source = "groq"

    # ۴. Gemini (fallback)
    if not answer:
        logger.info("Groq unavailable, trying Gemini...")
        answer = await _generate_gemini(question, context)
        source = "gemini"

    # ۵. ذخیره در cache برای دفعه بعد
    if answer:
        await db.save_knowledge(
            question=question,
            answer=answer,
            chat_id=chat_id,
            source=source,
            score=0.80,
        )
        logger.info(f"Answer via {source}, cached for future use")

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
