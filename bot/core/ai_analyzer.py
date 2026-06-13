"""
تحلیل پیام با Ollama — شناسایی توهین / اسپم / درخواست
"""

import json
import re
import logging
import httpx
from config import OLLAMA_BASE_URL, AI_MODEL

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """تو سیستم هوشمند مدیریت گروه تلگرام هستی. پیام‌های کاربران را تحلیل کن.

دقیقاً یک JSON برگردان، بدون هیچ متن اضافه:
{
  "type": "insult" | "spam" | "request" | "normal",
  "confidence": عدد 0 تا 1,
  "reason": "توضیح کوتاه فارسی",
  "request_summary": "خلاصه درخواست یا null",
  "suggested_response": "پاسخ پیشنهادی یا null"
}

قوانین:
- insult: فحش، ناسزا، توهین به فرد/قوم/مذهب/جنسیت
- spam: تبلیغ، لینک مشکوک، پیام تکراری، دعوت به کانال
- request: سوال، درخواست کمک، خواستن اطلاعات
- normal: مکالمه عادی"""

INSULT_WORDS = [
    "احمق", "کودن", "گاو", "خر", "بیشعور", "بی‌شعور", "مادر", "ننه",
    "بی‌ناموس", "فاحشه", "حرومزاده", "کثیف", "لاشخور", "نره غول",
    "گوساله", "الاغ",
    "idiot", "stupid", "fuck", "shit", "bitch", "asshole", "moron", "dumb",
]
SPAM_WORDS = [
    "تبلیغ", "خرید", "فروش", "درآمد", "پول", "کسب درآمد", "ارز دیجیتال",
    "سود تضمینی", "عضو شو", "join", "t.me/", "http://", "https://",
]
REQUEST_WORDS = [
    "لطفاً", "لطفا", "میشه", "می‌شه", "چطور", "چگونه", "کمک", "سوال",
    "بگو", "توضیح", "راهنما", "چیه", "کجاست", "چی هست",
    "please", "help", "how", "what",
]


async def analyze_message(text: str) -> dict:
    try:
        return await _ollama(text)
    except Exception as e:
        logger.warning(f"Ollama fallback: {e}")
        return _rules(text)


async def _ollama(text: str) -> dict:
    payload = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"پیام: {text}"},
        ],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1, "num_predict": 300},
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload)
        r.raise_for_status()
    content = r.json()["message"]["content"].strip()
    try:
        result = json.loads(content)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", content, re.DOTALL)
        result = json.loads(m.group()) if m else {}
    return _normalize(result)


def _rules(text: str) -> dict:
    t = text.lower()
    for kw in INSULT_WORDS:
        if kw in t:
            return _normalize({
                "type": "insult", "confidence": 0.85,
                "reason": f"کلمه نامناسب: «{kw}»",
            })
    for kw in SPAM_WORDS:
        if kw in t:
            return _normalize({"type": "spam", "confidence": 0.75, "reason": "محتوای تبلیغاتی"})
    for kw in REQUEST_WORDS:
        if kw in t:
            return _normalize({
                "type": "request", "confidence": 0.65,
                "reason": "درخواست کاربر",
                "request_summary": text[:120],
                "suggested_response": "لطفاً با ادمین‌های گروه در ارتباط باشید.",
            })
    return _normalize({"type": "normal", "confidence": 0.90, "reason": "پیام عادی"})


def _normalize(r: dict) -> dict:
    if r.get("type") not in {"insult", "spam", "request", "normal"}:
        r["type"] = "normal"
    r.setdefault("confidence", 0.5)
    r.setdefault("reason", "")
    r.setdefault("request_summary", None)
    r.setdefault("suggested_response", None)
    return r
