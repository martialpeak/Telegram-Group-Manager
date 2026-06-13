"""
موتور دانش و یادگیری — جستجو در پایگاه دانش و تاریخچه گروه + پاسخ با Gemini
"""

import logging
import asyncio
from typing import Optional

import google.generativeai as genai

from config import GEMINI_API_KEY, GEMINI_MODEL, SEARCH_TOP_K, LEARNING_MIN_SCORE
import bot.db.database as db

logger = logging.getLogger(__name__)

# ── راه‌اندازی Gemini ─────────────────────────────────────────────────────────
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    _model = genai.GenerativeModel(GEMINI_MODEL)
else:
    _model = None


# ─── جستجوی ساده بر اساس کلمه ───────────────────────────────────────────────

async def _search_knowledge(question: str, chat_id: int) -> Optional[dict]:
    items = await db.get_knowledge(chat_id)
    if not items:
        return None
    q_words = set(question.lower().split())
    best, best_score = None, 0
    for item in items:
        words = set(item["question"].lower().split())
        common = len(q_words & words)
        score = common / max(len(q_words), 1)
        if score > best_score:
            best_score = score
            best = {**item, "score": score}
    return best if best and best_score >= 0.4 else None


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


# ─── پاسخ با Gemini ──────────────────────────────────────────────────────────

async def _generate_answer(question: str, context_msgs: list[dict]) -> Optional[str]:
    if not _model:
        return None

    context = ""
    if context_msgs:
        lines = "\n".join(f"- {m['name']}: {m['text']}" for m in context_msgs[:5])
        context = f"\nاطلاعات مرتبط از گروه:\n{lines}\n"

    prompt = (
        f"تو دستیار هوشمند یک گروه تلگرامی هستی.{context}\n"
        f"سوال کاربر: {question}\n\n"
        "پاسخ کوتاه، مفید و به زبان فارسی بده. "
        "اگر اطلاعات کافی نداری صادقانه بگو."
    )

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: _model.generate_content(
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
        logger.warning(f"Gemini answer generation failed: {e}")
        return None


# ─── پاسخ به سوالات ──────────────────────────────────────────────────────────

async def answer_question(question: str, chat_id: int) -> dict:
    # ۱. جستجو در پایگاه دانش
    kb_result = await _search_knowledge(question, chat_id)
    if kb_result and kb_result["score"] >= LEARNING_MIN_SCORE:
        await db.increment_use(kb_result["id"])
        return {
            "answer": kb_result["answer"],
            "source": "knowledge_base",
            "confidence": kb_result["score"],
        }

    # ۲. جستجو در تاریخچه گروه
    history_results = await _search_history(question, chat_id)

    # ۳. پاسخ با Gemini
    answer = await _generate_answer(question, history_results)

    # ۴. ذخیره برای یادگیری
    if answer:
        await db.save_knowledge(
            question=question,
            answer=answer,
            chat_id=chat_id,
            source="gemini",
            score=0.70,
        )

    return {
        "answer": answer or "متاسفم، اطلاعات کافی برای پاسخ به این سوال ندارم.",
        "source": "gemini" if answer else "none",
        "confidence": 0.8 if answer else 0.0,
        "history_used": len(history_results),
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
