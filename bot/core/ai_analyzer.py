"""
تحلیل پیام — Groq (primary) → Gemini (fallback) → Rule-based (آخرین راه)
"""

import json
import re
import logging
import asyncio
from typing import Optional

from config import GROQ_API_KEY, GROQ_MODEL, GEMINI_API_KEY, GEMINI_MODEL

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
        _model_name = GEMINI_MODEL if GEMINI_MODEL else "gemini-2.5-flash"
        _gemini_model = genai.GenerativeModel(_model_name)
    except Exception as e:
        logger.warning(f"Gemini init failed: {e}")

if not _groq_client and not _gemini_model:
    logger.warning("هیچ AI تنظیم نشده — فقط rule-based کار می‌کنه")

# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a Telegram group moderation AI. Analyze the message and return ONLY a JSON object, no extra text:
{
  "type": "insult" | "spam" | "request" | "normal",
  "confidence": 0.0 to 1.0,
  "reason": "brief explanation in Farsi"
}
Rules:
- insult: clear offensive language, profanity, direct personal attacks (be strict, only flag obvious cases)
- spam: unsolicited ads, suspicious links promoting external channels/products, affiliate/scam promotions (do NOT flag normal mentions of buying/selling topics in conversation)
- request: questions, help requests, information seeking
- normal: regular conversation, discussion about topics like commerce, business, daily life — even if words like buy/sell/join appear in natural context
Be conservative: when in doubt, classify as "normal". Only flag high-confidence violations."""

# ── Rule-based fallback ───────────────────────────────────────────────────────
INSULT_WORDS = [
    "احمق", "کودن", "گاو", "خر", "بیشعور", "بی‌شعور",
    "بی‌ناموس", "فاحشه", "حرومزاده", "کثیف", "گوساله", "الاغ",
    "idiot", "stupid", "fuck", "shit", "bitch", "asshole", "moron",
]
# فقط الگوهای واضح تبلیغاتی — کلمات عمومی مثل خرید/فروش حذف شدن
SPAM_WORDS = [
    "کسب درآمد", "سود تضمینی", "عضو شو و درآمد",
    "کانال تبلیغ", "لینک دعوت", "t.me/joinchat",
]
REQUEST_WORDS = [
    "لطفاً", "لطفا", "میشه", "می‌شه", "چطور", "چگونه", "کمک",
    "سوال", "بگو", "توضیح", "راهنما", "چیه", "کجاست",
    "please", "help", "how", "what",
]


async def analyze_message(text: str) -> dict:
    # ۱. Groq
    if _groq_client:
        try:
            return await _analyze_groq(text)
        except Exception as e:
            logger.warning(f"Groq analyze failed, trying Gemini: {e}")

    # ۲. Gemini fallback
    if _gemini_model:
        try:
            return await _analyze_gemini(text)
        except Exception as e:
            logger.warning(f"Gemini analyze failed, using rules: {e}")

    # ۳. Rule-based
    return _rules(text)


async def _analyze_groq(text: str) -> dict:
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: _groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": f"Message: {text}"},
            ],
            temperature=0.1,
            max_tokens=150,
            response_format={"type": "json_object"},
        )
    )
    content = response.choices[0].message.content.strip()
    return _normalize(json.loads(content))


async def _analyze_gemini(text: str) -> dict:
    import google.generativeai as genai
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: _gemini_model.generate_content(
            f"{SYSTEM_PROMPT}\n\nMessage: {text}",
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                max_output_tokens=150,
            ),
        )
    )
    content = re.sub(r"```json\s*|\s*```", "", response.text).strip()
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
            return _normalize({"type": "insult", "confidence": 0.85, "reason": f"کلمه نامناسب: {kw}"})
    for kw in SPAM_WORDS:
        if kw in t:
            return _normalize({"type": "spam", "confidence": 0.75, "reason": "محتوای تبلیغاتی"})
    for kw in REQUEST_WORDS:
        if kw in t:
            return _normalize({"type": "request", "confidence": 0.65, "reason": "درخواست کاربر"})
    return _normalize({"type": "normal", "confidence": 0.90, "reason": "پیام عادی"})


def _normalize(r: dict) -> dict:
    if r.get("type") not in {"insult", "spam", "request", "normal"}:
        r["type"] = "normal"
    r.setdefault("confidence", 0.5)
    r.setdefault("reason", "")
    r.setdefault("request_summary", None)
    r.setdefault("suggested_response", None)
    return r
