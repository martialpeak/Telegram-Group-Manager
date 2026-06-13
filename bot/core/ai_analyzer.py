"""
تحلیل پیام با Gemini API — شناسایی توهین / اسپم / درخواست
"""

import json
import re
import logging
import google.generativeai as genai
from config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

# ── راه‌اندازی Gemini ─────────────────────────────────────────────────────────
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    _model = genai.GenerativeModel(GEMINI_MODEL)
else:
    _model = None
    logger.warning("GEMINI_API_KEY تنظیم نشده — فقط rule-based کار می‌کنه")

SYSTEM_PROMPT = """تو سیستم هوشمند مدیریت گروه تلگرام هستی. پیام‌های کاربران را تحلیل کن.

دقیقاً یک JSON برگردان، بدون هیچ متن اضافه:
{
  "type": "insult" | "spam" | "request" | "normal",
  "confidence": عدد 0 تا 1,
  "reason": "توضیح کوتاه فارسی"
}

قوانین:
- insult: فحش، ناسزا، توهین به فرد/قوم/مذهب/جنسیت
- spam: تبلیغ، لینک مشکوک، پیام تکراری، دعوت به کانال
- request: سوال، درخواست کمک، خواستن اطلاعات
- normal: مکالمه عادی"""

# ── Rule-based fallback ───────────────────────────────────────────────────────
INSULT_WORDS = [
    "احمق", "کودن", "گاو", "خر", "بیشعور", "بی‌شعور",
    "بی‌ناموس", "فاحشه", "حرومزاده", "کثیف", "گوساله", "الاغ",
    "idiot", "stupid", "fuck", "shit", "bitch", "asshole", "moron",
]
SPAM_WORDS = [
    "تبلیغ", "خرید", "فروش", "کسب درآمد", "ارز دیجیتال",
    "سود تضمینی", "عضو شو", "join", "t.me/",
]
REQUEST_WORDS = [
    "لطفاً", "لطفا", "میشه", "می‌شه", "چطور", "چگونه", "کمک",
    "سوال", "بگو", "توضیح", "راهنما", "چیه", "کجاست",
    "please", "help", "how", "what",
]


async def analyze_message(text: str) -> dict:
    if _model:
        try:
            return await _gemini(text)
        except Exception as e:
            logger.warning(f"Gemini fallback: {e}")
    return _rules(text)


async def _gemini(text: str) -> dict:
    import asyncio
    prompt = f"{SYSTEM_PROMPT}\n\nپیام: {text}"
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: _model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                max_output_tokens=200,
            ),
        )
    )
    content = response.text.strip()
    # پاک کردن markdown code block اگه بود
    content = re.sub(r"```json\s*|\s*```", "", content).strip()
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
