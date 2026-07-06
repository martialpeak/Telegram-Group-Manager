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
    "تو یک متخصص ارشد فنی در حوزه VPN، شبکه، کانفیگ‌های v2ray/xray/sing-box، "
    "پروتکل‌های پروکسی (vless, vmess, trojan, shadowsocks, hysteria2, tuic, wireguard, reality) "
    "و مسائل اینترنت آزاد هستی که در یک گروه تلگرامی فارسی‌زبان به کاربران کمک می‌کنی.\n\n"
    "## روش پاسخ‌گویی (تحلیل دقیق):\n"
    "۱) قدم اول: دقیق بفهم کاربر چی می‌خواد. یکی از این‌هاست؟\n"
    "   - آموزش/راهنما (چطور یک چیزی رو انجام بده)\n"
    "   - troubleshooting (یه مشکل داره)\n"
    "   - درخواست کانفیگ/سرور\n"
    "   - سوال عمومی/توضیحی\n"
    "   - گفتگو/بحث\n"
    "۲) اگه حافظه مکالمه دادی، سوال فعلی رو به اون ربط بده. مثلاً اگه کاربر می‌گه "
    "\"اون رو چطور نصب کنم؟\" و قبلاً درباره v2ray صحبت می‌کرد، منظور v2ray است.\n"
    "۳) اگه سوال مبهمه یا اطلاعات ناقصه، اول ابهام‌زدایی کن: یا دو حالت رو پوشش بده "
    "یا یه سوال شفاف‌سازی بپرس.\n"
    "۴) پاسخ رو با دقت، جزئیات و ساختار مناسب بده.\n\n"
    "## قواعد مهم:\n"
    "- همیشه به فارسی روان، دقیق و کاربردی پاسخ بده.\n"
    "- برای سوالات فنی: مراحل واضح و ترتیب‌دار. کانفیگ/دستور/کد رو داخل بلوک کد.\n"
    "- پروتکل‌ها و پورت‌ها و تنظیمات رو با مثال‌های واقعی و قابل کپی توضیح بده.\n"
    "- اگه چند روش وجود داره، روش بهینه/امن‌تر رو اول پیشنهاد بده و دلیل بگو.\n"
    "- هرگز اطلاعات invented/ساختی نده. اگه مطمئن نیستی بگو «مطمئن نیستم».\n"
    "- پاسخ رو ساختارمند بنویس: بخش‌بندی، شماره‌گذاری، بلوک کد.\n"
    "- لحن دوستانه اما حرفه‌ای و محترمانه.\n"
    "- برای سوالات امنیتی، روش‌های امن و ضد‌شناسایی رو پیشنهاد بده.\n"
    "- هرگز وعده‌های غیرواقعی نده (مثل \"۱۰۰٪ کار می‌کنه\" یا \"هیچ‌وقت مسدود نمی‌شه\").\n"
    "- اگه سوال خارج از حوزه‌ی تخصصیه، صادقانه بگو و راهنمایی کن کجا بپرسه.\n"
    "- اگه چند بخش داری، از header‌ (مانند **۱.** یا ▶) استفاده کن.\n"
    "- مهم: روی کیفیت، دقت و صحت تمرکز کن، نه سرعت یا طول پاسخ.\n"
)

PROMPT_TEMPLATE = (
    "{context}"
    "سوال کاربر: {question}\n\n"
    "به این سوال به‌طور کامل، دقیق و تخصصی پاسخ بده. "
    "اول نیت کاربر رو تحلیل کن، بعد پاسخ بده:"
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
                temperature=0.3,   # کمی بالاتر = پاسخ طبیعی‌تر ولی هنوز دقیق
                max_tokens=3500,   # پاسخ‌های کامل و تخصصی
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
                    temperature=0.3,
                    max_output_tokens=3500,
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

async def answer_question(
    question: str, chat_id: int, user_id: int = 0
) -> dict:
    # ۱. Cache — پایگاه دانش
    cached = await _search_knowledge(question, chat_id)
    if cached:
        await db.increment_use(cached["id"])
        # حتی cache شده رو تو حافظه مکالمه ثبت کن
        if user_id:
            await db.add_conversation_message(user_id, chat_id, "user", question)
            await db.add_conversation_message(user_id, chat_id, "assistant", cached["answer"])
        return {
            "answer": cached["answer"],
            "source": "knowledge_base",
            "confidence": cached["score"],
        }

    # ۲. ساخت context غنی: تاریخچه گروه + حافظه مکالمه + پروفایل کاربر
    context_parts = []

    # ۲-الف. پروفایل کاربر — برای شخصی‌سازی
    if user_id:
        try:
            profile = await db.get_user_profile(user_id, chat_id)
            if profile and profile.get("full_name"):
                context_parts.append(f"کاربر سوال‌کننده: {profile['full_name']}")
        except Exception:
            pass

    # ۲-ب. حافظه مکالمه اخیر همین کاربر — برای ادامه گفت‌وگو
    if user_id:
        try:
            mem = await db.get_conversation_history(user_id, chat_id, limit=4)
            if mem:
                mem_lines = []
                for m in mem:
                    role = "کاربر" if m["role"] == "user" else "ربات"
                    mem_lines.append(f"{role}: {m['content']}")
                context_parts.append(
                    "گفت‌وگوی اخیر این کاربر با ربات (برای ادامه مکالمه):\n"
                    + "\n".join(mem_lines)
                )
        except Exception:
            pass

    # ۲-ج. تاریخچه مرتبط گروه
    history = await _search_history(question, chat_id)
    if history:
        lines = "\n".join(f"- {m['name']}: {m['text']}" for m in history[:5])
        context_parts.append(
            "اطلاعات مرتبط از تاریخچه گروه (می‌تونی برای غنی‌تر کردن پاسخ ازشون استفاده کنی):\n"
            + lines
        )

    context = ""
    if context_parts:
        context = "\n\n" + "\n\n".join(context_parts) + "\n\n"

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

    # ۶. ثبت در حافظه مکالمه
    if user_id and answer:
        try:
            await db.add_conversation_message(user_id, chat_id, "user", question)
            await db.add_conversation_message(user_id, chat_id, "assistant", answer)
        except Exception:
            pass

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


# ─── همگام‌سازی از کانال‌های آموزشی ────────────────────────────────────────────

async def sync_training_channels(limit_per_channel: int = 100) -> int:
    """
    مطالب کانال‌های آموزشی تنظیم‌شده رو می‌خونه و به پایگاه دانش اضافه می‌کنه.
    از scraping نسخه‌ی وب کانال (t.me/s/) استفاده می‌کنه — بدون نیاز به API.
    فقط کانال‌های public (با یوزرنیم) کار می‌کنن.
    """
    from config import TRAINING_CHANNELS
    if not TRAINING_CHANNELS:
        return 0

    from bot.core.channel_reader import read_channel_messages
    total = 0
    for channel in TRAINING_CHANNELS:
        try:
            messages = await read_channel_messages(channel, limit=limit_per_channel)
            if not messages:
                logger.warning(
                    f"📚 کانال {channel}: پیامی استخراج نشد "
                    f"(شما کانال public نیست یا فیلتره)"
                )
                continue
            count = 0
            for msg in messages:
                text = msg["text"]
                # فقط مطالب آموزشی (طولانی) رو ذخیره کن
                if len(text) < 50:
                    continue
                # title از خط اول بگیر (یا ۸۰ کاراکتر اول)
                first_line = text.split("\n")[0][:80].strip()
                if not first_line:
                    first_line = text[:80].strip()
                # ذخیره به‌عنوان knowledge
                await db.save_knowledge(
                    question=first_line,
                    answer=text,
                    chat_id=0,  # global برای همه گروه‌ها
                    source=f"channel:{channel}",
                    score=0.85,
                )
                count += 1
            total += count
            logger.info(f"📚 از {channel}: {count} مطلب ذخیره شد")
        except Exception as e:
            logger.warning(f"sync {channel} failed: {e}")
    return total


# ─── سرچ در وب (fallback) ─────────────────────────────────────────────────────

async def search_web_fallback(question: str) -> str | None:
    """
    وقتی AI جوابی نداشت، در وب سرچ می‌کنه و خلاصه‌ای برمی‌گردونه.
    روش: DuckDuckgo Instant Answer → اگر نبود، HTML results → خلاصه با AI.
    """
    import httpx
    import re as _re
    from config import WEB_SEARCH_MAX_RESULTS

    snippets = []
    logger.info(f"🔍 starting web search for: '{question[:50]}'")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # ۱. DuckDuckGo Instant Answer API
            resp = await client.get(
                "https://api.duckduckgo.com/",
                params={
                    "q": question,
                    "format": "json",
                    "no_html": "1",
                    "skip_disambig": "1",
                },
            )
            logger.info(f"DDG instant answer: HTTP {resp.status_code}")
            data = resp.json()
            abstract = data.get("AbstractText") or data.get("Abstract")
            if abstract and len(abstract) > 30:
                source = data.get("AbstractURL", "")
                result = abstract
                if source:
                    result += f"\n\n📚 منبع: {source}"
                await _cache_web_answer(question, result)
                logger.info("✅ DDG instant answer found")
                return result
            # related topics
            for t in (data.get("RelatedTopics") or [])[:WEB_SEARCH_MAX_RESULTS]:
                if isinstance(t, dict) and t.get("Text"):
                    snippets.append(t["Text"][:250])
            logger.info(f"DDG: {len(snippets)} related snippets")
    except Exception as e:
        logger.warning(f"duckduckgo instant answer failed: {e}")

    # ۲. اگه Instant Answer چیزی نداشت، HTML results رو امتحان کن
    if not snippets:
        try:
            ddg_html = await _ddg_html_search(question, WEB_SEARCH_MAX_RESULTS)
            snippets.extend(ddg_html)
            logger.info(f"DDG HTML: {len(ddg_html)} snippets")
        except Exception as e:
            logger.warning(f"ddg html search failed: {e}")

    # ۲-ب. اگه DDG کار نکرد (احتمالاً فیلتر)، Wikipedia API رو امتحان کن
    if not snippets:
        try:
            wiki_snippets = await _wikipedia_search(question, WEB_SEARCH_MAX_RESULTS)
            snippets.extend(wiki_snippets)
            logger.info(f"Wikipedia: {len(wiki_snippets)} snippets")
        except Exception as e:
            logger.warning(f"wikipedia search failed: {e}")

    if not snippets:
        logger.warning("❌ web search: no snippets found at all")
        return None

    # ۳. اگه AI در دسترسه، snippet‌ها رو خلاصه کن
    summary = await _summarize_snippets(question, snippets)
    if summary:
        await _cache_web_answer(question, summary)
        return summary

    # ۴. fallback: فقط snippet‌ها رو بچسبون
    text = "🔍 یافته‌های مرتبط از وب:\n\n" + "\n\n".join(snippets)
    await _cache_web_answer(question, text)
    return text


async def _ddg_html_search(query: str, max_results: int = 3) -> list[str]:
    """استخراج snippet از صفحه HTML DuckDuckGo"""
    import httpx
    import re as _re
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        resp = await client.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
        )
    # snippet‌ها داخل تگ a class="result__a" و div class="result__snippet"
    snippets = []
    matches = _re.findall(
        r'class="result__snippet"[^>]*>(.*?)</a>',
        resp.text,
        _re.DOTALL,
    )
    for m in matches[:max_results]:
        # حذف تگ‌های HTML
        clean = _re.sub(r"<[^>]+>", "", m).strip()
        if clean and len(clean) > 20:
            snippets.append(clean[:300])
    return snippets


async def _wikipedia_search(query: str, max_results: int = 3) -> list[str]:
    """سرچ در Wikipedia API (fa و en)"""
    import httpx
    snippets = []
    # اول فارسی
    for lang in ["fa", "en"]:
        if len(snippets) >= max_results:
            break
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # opensearch
                resp = await client.get(
                    f"https://{lang}.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "list": "search",
                        "srsearch": query,
                        "format": "json",
                        "srlimit": max_results,
                    },
                )
                data = resp.json()
                items = data.get("query", {}).get("search", [])
                for item in items:
                    # حذف تگ‌های HTML از snippet
                    import re as _re
                    snippet = _re.sub(r"<[^>]+>", "", item.get("snippet", ""))
                    if snippet and len(snippet) > 20:
                        title = item.get("title", "")
                        snippets.append(f"{title}: {snippet[:250]}")
        except Exception as e:
            logger.warning(f"wikipedia {lang} search failed: {e}")
    return snippets


async def _summarize_snippets(question: str, snippets: list[str]) -> str | None:
    """استفاده از AI برای خلاصه‌سازی نتایج وب به جواب واحد"""
    context = "\n\n".join(f"[{i+1}] {s}" for i, s in enumerate(snippets))
    prompt = (
        f"بر اساس این نتایج جست‌وجو، به سوال زیر پاسخ بده:\n\n"
        f"سوال: {question}\n\n"
        f"نتایج جست‌وجو:\n{context}\n\n"
        "پاسخ رو به فارسی و بر اساس این اطلاعات بنویس. "
        "اگه اطلاعات کافی نیست، صادقانه بگو. "
        "منابع رو در انتهای پاسخ ذکر کن."
    )
    # اول Groq
    if _groq_client:
        answer = await _generate_groq(prompt, "")
        if answer:
            return "🌐 (بر اساس جست‌وجو در وب)\n\n" + answer
    # fallback Gemini
    if _gemini_model:
        answer = await _generate_gemini(prompt, "")
        if answer:
            return "🌐 (بر اساس جست‌وجو در وب)\n\n" + answer
    return None


async def _cache_web_answer(question: str, answer: str):
    """ذخیره جواب وب در پایگاه دانش برای دفعه بعد"""
    try:
        normalized = _normalize_question(question)
        store_q = normalized if len(normalized) >= 3 else question
        await db.save_knowledge(
            question=store_q, answer=answer,
            chat_id=0,  # global برای همه گروه‌ها
            source="web_search", score=0.7,
        )
    except Exception:
        pass
