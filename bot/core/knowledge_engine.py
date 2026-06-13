"""
موتور دانش و یادگیری — جستجوی semantic در پایگاه دانش و تاریخچه گروه
"""

import logging
from typing import Optional

import httpx
import numpy as np

from config import (
    OLLAMA_BASE_URL, AI_MODEL, EMBED_MODEL,
    SEARCH_TOP_K, LEARNING_MIN_SCORE,
)
import bot.db.database as db

logger = logging.getLogger(__name__)


# ─── Embedding با Ollama ──────────────────────────────────────────────────────

async def _embed(text: str) -> Optional[list[float]]:
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                f"{OLLAMA_BASE_URL}/api/embeddings",
                json={"model": EMBED_MODEL, "prompt": text},
            )
            r.raise_for_status()
            return r.json()["embedding"]
    except Exception as e:
        logger.warning(f"Embedding ناموفق: {e}")
        return None


def _cosine(a: list, b: list) -> float:
    a, b = np.array(a, dtype=float), np.array(b, dtype=float)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.dot(a, b) / denom) if denom > 0 else 0.0


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

    # ۳. تولید پاسخ با AI
    answer = await _generate_answer(question, history_results)

    # ۴. ذخیره برای یادگیری آینده
    if answer:
        await db.save_knowledge(
            question=question,
            answer=answer,
            chat_id=chat_id,
            source="ai_generated",
            score=0.55,
        )

    return {
        "answer": answer or "متاسفم، جواب این سوال رو پیدا نکردم. ادمین‌های گروه می‌تونن کمک کنن.",
        "source": "ai_generated",
        "confidence": 0.7 if answer else 0.0,
        "history_used": len(history_results),
    }


async def _search_knowledge(question: str, chat_id: int) -> Optional[dict]:
    items = await db.get_knowledge(chat_id)
    if not items:
        return None

    q_vec = await _embed(question)

    if q_vec:
        best, best_score = None, -1.0
        for item in items:
            i_vec = await _embed(item["question"])
            if i_vec:
                score = _cosine(q_vec, i_vec)
                if score > best_score:
                    best_score = score
                    best = {**item, "score": score}
        return best if best and best_score > 0.6 else None
    else:
        # Fallback: جستجوی کلمه‌ای
        q_words = set(question.lower().split())
        best, best_score = None, -1
        for item in items:
            words = set(item["question"].lower().split())
            common = len(q_words & words)
            if common > best_score:
                best_score = common
                best = {**item, "score": min(common / max(len(q_words), 1), 1.0)}
        return best if best and best_score > 0 else None


async def _search_history(query: str, chat_id: int) -> list[dict]:
    keywords = [w for w in query.split() if len(w) > 2][:5]
    results = []
    seen = set()
    for kw in keywords:
        msgs = await db.search_messages(kw, chat_id, limit=5)
        for m in msgs:
            if m["text"] not in seen:
                seen.add(m["text"])
                results.append(m)
    return results[:SEARCH_TOP_K]


async def _generate_answer(question: str, context_msgs: list[dict]) -> Optional[str]:
    context = ""
    if context_msgs:
        context = "\n".join(f"- {m['name']}: {m['text']}" for m in context_msgs[:5])
        context = f"\nاطلاعات مرتبط از گروه:\n{context}\n"

    prompt = (
        f"یک سوال از یک کاربر گروه تلگرام داری.{context}\n"
        f"سوال: {question}\n\n"
        "پاسخ کوتاه، مفید و فارسی بده. اگر نمی‌دانی بگو «اطلاعات کافی ندارم»."
    )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": AI_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 500},
                },
            )
            r.raise_for_status()
            return r.json()["message"]["content"].strip()
    except Exception as e:
        logger.warning(f"تولید پاسخ ناموفق: {e}")
        return None


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


async def learn_from_conversation(messages: list[dict], chat_id: int):
    if len(messages) < 2:
        return
    for i in range(len(messages) - 1):
        curr = messages[i]
        nxt  = messages[i + 1]
        is_question = any(
            w in curr["text"]
            for w in ["چطور", "چرا", "چیه", "چی", "?", "؟", "کمک", "لطفا", "لطفاً"]
        )
        if (is_question and len(nxt["text"]) > 20
                and curr["user_id"] != nxt["user_id"]):
            await db.save_knowledge(
                question=curr["text"],
                answer=nxt["text"],
                chat_id=chat_id,
                source="conversation",
                score=0.65,
            )
