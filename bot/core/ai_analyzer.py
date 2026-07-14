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

# ── System prompt (بهبود‌یافته — دقیق‌تر با few-shot) ─────────────────────────
SYSTEM_PROMPT = """You are a precise Telegram group moderation AI for a Persian-language group focused on VPN, networking, and tech discussions.

Your job: classify ONE message into exactly one category. Think step by step, then output JSON.

## CATEGORIES

**insult** — A DIRECT, explicit personal attack using clearly offensive/profane words aimed AT a specific person.
  - Requires: profanity/slur + target + hostile intent.
  - Examples that ARE insults: "بشین کسده", "کیر خور", "کونی", "مادرقه", "motherfucker", "you're a retard"
  - Confidence must be ≥ 0.90 to flag.

**spam** — Unsolicited PROMOTION of an external channel, bot, service, or money-making scheme, with intent to drive traffic AWAY from this group.
  - Requires ALL: external promotion + referral/invite link + copy-paste ad style.
  - Examples that ARE spam: "کانال ما رو دنبال کنید t.me/xxx", "سود تضمینی روزانه ۵۰ هزار تومان", "عضو شو و درآمد کسب کن"
  - Confidence must be ≥ 0.92 to flag.

**request** — A genuine question or explicit help request FROM the user, directed at the bot or group.

**normal** — EVERYTHING else. This is the default and most common.

## CRITICAL — NEVER FLAG as spam or insult:
- Any VPN/proxy config: vless://, vmess://, ss://, trojan://, tuic://, hysteria://, hysteria2://, hy2://, wireguard://, naive://, brook://, snell://, ssconf://, or base64 config strings
- Subscription links, server addresses, IP:port, technical networking configs
- Discussing prices, buying, selling, trading ("فروش", "خرید", "قیمت", "چند میدهی")
- Asking about product availability, recommendations, reviews
- Sharing news, tutorials, screenshots, logs
- Frustration, venting, mild complaints, sarcasm, memes, jokes, emojis
- Debates, disagreements, strong opinions (without profanity at a person)
- Persian slang or informal language that is NOT profanity
- Code snippets, command-line output, error messages

## REASONING RULES
1. When unsure between two categories, ALWAYS pick the less severe (normal > request > spam/insult).
2. An insult needs a TARGET (a person). General cursing about a situation is normal.
3. A message with a VPN config link is NEVER spam, even if it looks promotional.
4. Consider the conversation context provided — if others are calmly discussing and this message continues the thread, it's likely normal.
5. Sarcasm and dark humor are normal unless they contain explicit slurs.

## OUTPUT FORMAT
Return ONLY a JSON object, no markdown, no explanation outside JSON:
{"type": "insult|spam|request|normal", "confidence": 0.0-1.0, "reason": "دلیل کوتاه به فارسی"}

## EXAMPLES
Message: "این کانفیگ خرابه دیگه، چرا وصل نمیشه؟"
→ {"type": "normal", "confidence": 0.95, "reason": "شکایت از کانفیگ، نه توهین"}

Message: "vless://eyJhZGQiLCIxLjIuMy40In0= @"
→ {"type": "normal", "confidence": 0.98, "reason": "کانفیگ VPN، اسپم نیست"}

Message: "بیا عضو کانال ما شو و روزی ۱۰۰ تومان درآمد داشته باش t.me/joinchat/ABC"
→ {"type": "spam", "confidence": 0.97, "reason": "تبلیغ کانال خارجی با وعده درآمد"}

Message: "مگه خری هستی؟ کیر亦是"
→ {"type": "insult", "confidence": 0.92, "reason": "توهین مستقیم با الفاظ رکیک"}

Message: "ببخشید، قیمت این سرویس چنده؟"
→ {"type": "normal", "confidence": 0.93, "reason": "پرسش درباره قیمت، گفتگوی تجاری"}

Message: "الان چطور میتونم کانفیگ vless بسازم؟"
→ {"type": "request", "confidence": 0.90, "reason": "سوال فنی کاربر"}

## PREVIOUSLY MISCLASSIFIED MESSAGES (do NOT flag similar):
{false_positives}
"""

# ── Rule-based fallback ───────────────────────────────────────────────────────
INSULT_WORDS = [
    "بی‌ناموس", "بی ناموس", "فاحشه", "حرومزاده", "حرامزاده",
    "کسده", "کس ده", "کونی", "کون ده", "مادرقه", "مادر قه",
    "جق", "کیرخور", "کیر خور", "خارکسه",
    "fuck you", "motherfucker", "son of a bitch", "asshole", "retard",
]
# فقط الگوهای واضح تبلیغاتی — کلمات عمومی مثل خرید/فروش حذف شدن
SPAM_WORDS = [
    "کسب درآمد", "سود تضمینی", "عضو شو و درآمد",
    "کانال تبلیغ", "لینک دعوت", "t.me/joinchat",
    "درآمد آنلاین", "پروژه پولساز",
]
REQUEST_WORDS = [
    "لطفاً", "لطفا", "میشه", "می‌شه", "چطور", "چگونه", "کمک",
    "سوال", "بگو", "توضیح", "راهنما", "چیه", "کجاست",
    "please", "help", "how", "what",
]

# پروتکل‌های VPN — برای rule-based: کانفیگ رو اسپم نشمار
_VPN_CONFIG_RE = re.compile(
    r"(vless|vmess|ss|shadowsocks|trojan|tuic|hysteria2?|hy2|"
    r"wireguard|naive|brook|snell|ssconf)://",
    re.IGNORECASE,
)


async def analyze_message(text: str, chat_id: int = 0) -> dict:
    # ۱. جمع‌آوری context از false positives
    fp_insult = await _get_fp_context("insult")
    fp_spam   = await _get_fp_context("spam")
    false_positives = (fp_insult + ("\n" if fp_insult and fp_spam else "") + fp_spam) \
        or "هیچ موردی ثبت نشده."

    # ۲. تاریخچه گفتگوی اخیر گروه — برای درک context
    conversation_context = await _get_conversation_context(chat_id)

    # ۳. Groq
    if _groq_client:
        try:
            return await _analyze_groq(
                text, false_positives=false_positives,
                conversation_context=conversation_context,
            )
        except Exception as e:
            logger.warning(f"Groq analyze failed, trying Gemini: {e}")

    # ۴. Gemini fallback
    if _gemini_model:
        try:
            return await _analyze_gemini(
                text, false_positives=false_positives,
                conversation_context=conversation_context,
            )
        except Exception as e:
            logger.warning(f"Gemini analyze failed, using rules: {e}")

    # ۵. Rule-based
    return _rules(text)


async def _get_fp_context(action: str) -> str:
    """آخرین ۵ false positive رو از DB بخون و به prompt اضافه کن"""
    try:
        import bot.db.database as db_module
        fps = await db_module.get_recent_false_positives(action, limit=5)
        if not fps:
            return ""
        examples = "\n".join(
            f'- "{fp["message_text"][:120]}" (نباید {action} باشه)'
            for fp in fps
        )
        return f"خطاهای قبلی در تشخیص {action}:\n{examples}"
    except Exception:
        return ""


async def _get_conversation_context(chat_id: int) -> str:
    """
    آخرین چند پیام گروه رو به‌عنوان context به AI می‌ده تا بفهمه
    در چه فضایی پیام داده شده (مثلاً بحث فنی یا دعوا).
    """
    if not chat_id:
        return ""
    try:
        import bot.db.database as db_module
        recent = await db_module.get_recent_messages(chat_id, limit=6)
        if not recent:
            return ""
        lines = []
        for m in recent[-6:]:
            name = (m.get("name") or "ناشناس")[:20]
            txt = (m.get("text") or "")[:150]
            lines.append(f"{name}: {txt}")
        return "متن گفت‌وگوی اخیر این گروه (برای درک فضای بحث):\n" + "\n".join(lines)
    except Exception:
        return ""


async def _analyze_groq(
    text: str, false_positives: str = "", conversation_context: str = ""
) -> dict:
    prompt = SYSTEM_PROMPT.format(false_positives=false_positives)
    user_content = f"Message to classify: {text}"
    if conversation_context:
        user_content += f"\n\n---\n{conversation_context}"
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None,
        lambda: _groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user",   "content": user_content},
            ],
            temperature=0.1,
            max_tokens=300,
            response_format={"type": "json_object"},
        )
    )
    content = response.choices[0].message.content.strip()
    return _normalize(json.loads(content))


async def _analyze_gemini(
    text: str, false_positives: str = "", conversation_context: str = ""
) -> dict:
    import google.generativeai as genai
    prompt = SYSTEM_PROMPT.format(false_positives=false_positives)
    user_content = f"Message to classify: {text}"
    if conversation_context:
        user_content += f"\n\n---\n{conversation_context}"
    loop = asyncio.get_running_loop()
    response = await loop.run_in_executor(
        None,
        lambda: _gemini_model.generate_content(
            f"{prompt}\n\n{user_content}",
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                max_output_tokens=300,
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
    # کانفیگ VPN هرگز اسپم/توهین نیست
    is_vpn = bool(_VPN_CONFIG_RE.search(text))
    for kw in INSULT_WORDS:
        if kw in t:
            return _normalize({"type": "insult", "confidence": 0.85, "reason": f"کلمه نامناسب: {kw}"})
    if not is_vpn:
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
