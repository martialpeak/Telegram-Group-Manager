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
    "تو یک دستیار هوشمند فارسی‌زبان هستی که در یک گروه تلگرامی به کاربران کمک می‌کنی.\n"
    "تخصص اصلی: VPN، شبکه، کانفیگ‌های v2ray/xray/sing-box، پروتکل‌های پروکسی.\n"
    "ولی به همه سوالات عمومی هم پاسخ میدی (قیمت ارز، هواشناسی، اخبار، ورزش، و...).\n\n"
    "## قواعد پاسخ‌گویی:\n"
    "۱) اول نیت کاربر رو دقیق بفهم.\n"
    "۲) پاسخ رو کوتاه، دقیق و کاربردی بده (کمتر از ۱۰ خط مگه لازم باشه).\n"
    "۳) همیشه به فارسی روان و طبیعی پاسخ بده.\n"
    "۴) اگه اطلاعات لحظه‌ای می‌خواد (قیمت، هوا، اخبار) بگو از منابع آنلاین چک کنه.\n"
    "۵) اگه مطمئن نیستی، صادقانه بگو.\n"
    "۶) لحن دوستانه اما حرفه‌ای.\n"
    "۷) هرگز اطلاعات ساختگی نده.\n"
)

PROMPT_TEMPLATE = (
    "{context}"
    "سوال کاربر: {question}\n\n"
    "به این سوال کوتاه و دقیق پاسخ بده:"
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
        loop = asyncio.get_running_loop()
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


# ─── تولید پاسخ عمومی (برای خلاصه‌سازی وب) ────────────────────────────────

async def _generate_groq_general(prompt: str) -> Optional[str]:
    """تولید پاسخ با Groq برای سوالات عمومی (نه VPN)"""
    if not _groq_client:
        return None
    general_system = (
        "تو یک دستیار هوشمند فارسی‌زبان هستی که به سوالات کاربران پاسخ میدی. "
        "به فارسی روان و دقیق پاسخ بده. اگه مطمئن نیستی، صادقانه بگو."
    )
    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: _groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": general_system},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=3500,
                top_p=0.9,
            )
        )
        answer = response.choices[0].message.content.strip()
        return answer if answer and len(answer) > 5 else None
    except Exception as e:
        logger.warning(f"Groq general answer failed: {e}")
        return None


async def _generate_gemini_general(prompt: str) -> Optional[str]:
    """تولید پاسخ با Gemini برای سوالات عمومی (نه VPN)"""
    if not _gemini_model:
        return None
    general_system = (
        "تو یک دستیار هوشمند فارسی‌زبان هستی که به سوالات کاربران پاسخ میدی. "
        "به فارسی روان و دقیق پاسخ بده. اگه مطمئن نیستی، صادقانه بگو."
    )
    import google.generativeai as genai
    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: _gemini_model.generate_content(
                f"{general_system}\n\n{prompt}",
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
        logger.warning(f"Gemini general answer failed: {e}")
        return None


# ─── تولید پاسخ با Gemini ────────────────────────────────────────────────────

async def _generate_gemini(question: str, context: str) -> Optional[str]:
    if not _gemini_model:
        return None
    import google.generativeai as genai
    prompt = PROMPT_TEMPLATE.format(context=context, question=question)
    try:
        loop = asyncio.get_running_loop()
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
    # ۱. Cache — پایگاه دانش (فقط برای سوالات غیرلحظه‌ای)
    is_realtime = needs_web_search(question)
    if not is_realtime:
        cached = await _search_knowledge(question, chat_id)
        if cached:
            await db.increment_use(cached["id"])
            if user_id:
                await db.add_conversation_message(user_id, chat_id, "user", question)
                await db.add_conversation_message(user_id, chat_id, "assistant", cached["answer"])
            return {
                "answer": cached["answer"],
                "source": "knowledge_base",
                "confidence": cached["score"],
            }
    else:
        logger.info(f"⏭️ سوال لحظه‌ای تشخیص داده شد → رد شدن از کش: '{question[:50]}'")

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

    # ── تعیین منبع پاسخ: auto / ai / web ──────────────────────────────────
    from config import ANSWER_MODE
    use_web_first = False
    if ANSWER_MODE == "web":
        use_web_first = True
    elif ANSWER_MODE == "auto":
        # سوالات اطلاعاتی/لحظه‌ای → اول سرچ وب
        if needs_web_search(question):
            use_web_first = True
            logger.info(f"🔍 سوال اطلاعاتی تشخیص داده شد → سرچ وب اول: '{question[:50]}'")

    answer = None
    source = "none"

    # ۳-الف. سرچ وب (اگه اولویت باهاشه)
    if use_web_first:
        try:
            from config import WEB_SEARCH_ENABLED
            if WEB_SEARCH_ENABLED:
                web_answer = await search_web_fallback(question)
                if web_answer:
                    answer = web_answer
                    source = "web_search"
        except Exception as e:
            logger.warning(f"web search failed: {e}")

    # ۳-ب. AI (اگه سرچ وب جواب نداشت یا اولویت با AI بود)
    if not answer:
        answer = await _generate_groq(question, context)
        source = "groq" if answer else "none"

    # ۴. Gemini (fallback نهایی)
    if not answer:
        logger.info("Groq unavailable, trying Gemini...")
        answer = await _generate_gemini(question, context)
        source = "gemini" if answer else "none"

    # ۴-ب. fallback آخر: سرچ وب (اگه AI هم جواب نداشت)
    if not answer and ANSWER_MODE != "ai":
        try:
            from config import WEB_SEARCH_ENABLED
            if WEB_SEARCH_ENABLED:
                web_answer = await search_web_fallback(question)
                if web_answer:
                    answer = web_answer
                    source = "web_search"
        except Exception as e:
            logger.warning(f"web search fallback failed: {e}")

    # ۵. ذخیره در cache (فقط برای پاسخ‌های AI، نه وب سرچ)
    if answer and source not in ("web_search",):
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
    elif answer:
        logger.info(f"Answer via {source} (not cached - web search)")

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

# کلماتی که نشون می‌ده سوال به اطلاعات لحظه‌ای/واقعی نیاز داره
# (AI نمی‌تونه جواب بده، حتماً باید سرچ بشه)
_REALTIME_PATTERNS = [
    # آب‌وهوا
    "هواشناسی", "آب و هوا", "آب‌وهوا", "هوای", "دمای هوا", "طقس", "باران", "برف",
    "weather", "دما", "آفتابی", "ابری", "مه", "طوفان", "رگبار",
    # قیمت‌ها
    "قیمت دلار", "دلار", "یورو", "قیمت طلا", "طلا", "نرخ ارز", "بورس",
    "شاخص بورس", "قیمت سکه", "دلار آزاد", "قیمت بنزین",
    "تتر", "usdt", "قیمت تتر", "قیمت ارز", "نرخ دلار",
    # زمان/تاریخ
    "ساعت چند", "امروز چندمه", "تاریخ امروز", "چه روزیه",
    "چند روز تا", "چند روز مانده",
    # اخبار/رویدادهای جاری
    "خبر", "اخبار", "آخرین", "تازه‌ترین", "الان چه", "امروز چه",
    "news", "latest", "today",
    # وضعیت لحظه‌ای
    "وضعیت", "لحظه", "الان", "همین الان", "در حال حاضر",
    # نتایج زنده
    "نتیجه", "بازی", "مسابقه", "نتایج",
    # افراد/سوالات آنلاین
    "چه کسی", "کیست", "بیوگرافی", "ویکی‌پدیا",
    # تبدیل‌ها
    "چقدر است", "چند تومن", "چند ریال",
]


def needs_web_search(question: str) -> bool:
    """
    تشخیص می‌ده که آیا این سوال نیاز به سرچ در وب داره یا نه.
    سوالاتی مثل هواشناسی، قیمت، اخبار، اطلاعات لحظه‌ای.
    """
    q = question.lower().strip()
    if len(q) < 3:
        return False
    # الگوهای مشخص
    for pattern in _REALTIME_PATTERNS:
        if pattern in q:
            return True
    # اگه سوال خیلی کوتاه نیست و شامل کلمات کلیدی فنی نیست، احتمالاً به وب نیاز داره
    # (فقط برای سوالات انگلیسی یا فارسی که ظاهراً اطلاعات عمومی می‌خوان)
    if len(q.split()) > 3:
        # بررسی اینکه آیا سوال مربوط به VPN/شبکه هست یا نه
        vpn_keywords = ["v2ray", "xray", "sing-box", "vless", "vmess", "trojan", "shadowsocks",
                       "hysteria", "tuic", "wireguard", "reality", "کانفیگ", "پروکسی", "سرور",
                       "VPN", "فیلترشکن", "روت"]
        has_vpn_keyword = any(kw.lower() in q for kw in vpn_keywords)
        if not has_vpn_keyword:
            # اگه مربوط به VPN نیست، احتمالاً به وب نیاز داره
            return True
    return False


async def search_web_fallback(question: str) -> str | None:
    """
    وقتی AI جوابی نداشت، در وب سرچ می‌کنه و خلاصه‌ای برمی‌گردونه.
    روش: DuckDuckgo → Google → Wikipedia → خلاصه با AI.
    """
    import httpx
    import re as _re
    from config import WEB_SEARCH_MAX_RESULTS

    snippets = []
    logger.info(f"🔍 starting web search for: '{question[:50]}'")

    # ۰. اگه سوال مربوط به هواشناسی هست، اول Weather API رو امتحان کن
    weather_keywords = ["هواشناسی", "آب و هوا", "هوای", "آب‌وهوا", "دما", "باران", "برف", "آفتابی", "ابری", "دمای", "天气", "weather", "هوا"]
    if any(kw in question for kw in weather_keywords):
        try:
            weather_result = await _weather_search(question)
            if weather_result:
                logger.info("✅ Weather API returned result")
                await _cache_web_answer(question, weather_result)
                return weather_result
        except Exception as e:
            logger.warning(f"weather API search failed: {e}")

    # ۰.۵. اگه سوال مربوط به قیمت ارز هست، اول API مستقیم رو امتحان کن
    currency_keywords = ["دلار", "تتر", "usdt", "یورو", "پوند", "لیر", "درهم", "یوان", "ین ژاپن", "ارز", "نرخ ارز", "قیمت دلار", "قیمت یورو", "قیمت پوند", "قیمت لیر", "قیمت تتر", "نرخ دلار", "نرخ یورو"]
    is_currency = any(kw in question for kw in currency_keywords)
    logger.info(f"💰 currency check: question='{question[:30]}', is_currency={is_currency}")
    if is_currency:
        try:
            logger.info("💰 calling _currency_api_search...")
            currency_result = await _currency_api_search(question)
            logger.info(f"💰 currency_result type: {type(currency_result)}, value: {str(currency_result)[:100]}")
            if currency_result:
                logger.info("✅ Currency API returned result")
                await _cache_web_answer(question, currency_result)
                return currency_result
            else:
                logger.warning("💰 Currency API returned None")
        except Exception as e:
            logger.warning(f"currency API search failed: {e}")
            import traceback
            logger.warning(f"currency API traceback: {traceback.format_exc()}")

    # ۱. DuckDuckGo Instant Answer API
    try:
        async with httpx.AsyncClient(timeout=15) as client:
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
                    snippets.append({"title": "", "url": t.get("FirstURL", ""), "snippet": t["Text"][:250]})
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

    # ۲-ب. Brave Search (کار می‌کنه از المان)
    if not snippets:
        try:
            brave_results = await _brave_search(question, WEB_SEARCH_MAX_RESULTS)
            snippets.extend(brave_results)
            logger.info(f"Brave: {len(brave_results)} results")
        except Exception as e:
            logger.warning(f"brave search failed: {e}")

    # ۲-ج. Startpage (کار می‌کنه از المان)
    if not snippets:
        try:
            startpage_results = await _startpage_search(question, WEB_SEARCH_MAX_RESULTS)
            snippets.extend(startpage_results)
            logger.info(f"Startpage: {len(startpage_results)} results")
        except Exception as e:
            logger.warning(f"startpage search failed: {e}")

    # ۲-د. Google (ممکنه فیلتر باشه)
    if not snippets:
        try:
            google_results = await _google_search(question, WEB_SEARCH_MAX_RESULTS)
            snippets.extend(google_results)
            logger.info(f"Google: {len(google_results)} results")
        except Exception as e:
            logger.warning(f"google search failed: {e}")

    # ۲-ه. Bing (ممکنه فیلتر باشه)
    if not snippets:
        try:
            bing_results = await _bing_search(question, WEB_SEARCH_MAX_RESULTS)
            snippets.extend(bing_results)
            logger.info(f"Bing: {len(bing_results)} results")
        except Exception as e:
            logger.warning(f"bing search failed: {e}")

    # ۲-و. Wikipedia API
    if not snippets:
        try:
            wiki_snippets = await _wikipedia_search(question, WEB_SEARCH_MAX_RESULTS)
            for s in wiki_snippets:
                snippets.append({"title": "", "url": "", "snippet": s})
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

    # ۴. fallback: فقط snippet‌ها و لینک‌ها رو نشون بده
    text = "🔍 یافته‌های مرتبط از وب:\n\n"
    for s in snippets[:5]:
        if isinstance(s, dict):
            title = s.get("title", "")
            url = s.get("url", "")
            snippet = s.get("snippet", "")
            if title:
                text += f"📌 {title}\n"
            if url:
                text += f"🔗 {url}\n"
            if snippet:
                text += f"{snippet}\n\n"
        else:
            text += f"{s}\n\n"
    await _cache_web_answer(question, text)
    return text


# ─── Currency API (قیمت لحظه‌ای ارز) ─────────────────────────────────────────

# ─── Weather API ────────────────────────────────────────────────────────────

async def _weather_search(question: str) -> str | None:
    """دریافت اطلاعات هواشناسی از wttr.in"""
    import httpx
    import re as _re_w

    # استخراج نام شهر
    city_map = {
        # استان تهران
        "تهران": "Tehran", "کرج": "Karaj", "ری": "Rey",
        # استان خراسان
        "مشهد": "Mashhad", "نیشابور": "Nishapur", "بیرجند": "Birjand",
        "بجنورد": "Bojnurd", "درگز": "Dargaz", "قاین": "Qaen",
        "تربت حیدریه": "Torbat-e Heydarieh", "سبزوار": "Sabzevar",
        "فریمان": "Fariman", "خلیل‌آباد": "Khalilabad",
        # استان اصفهان
        "اصفهان": "Isfahan", "کاشان": "Kashan", "نائین": "Nain",
        "خمینی‌شهر": "Khomeini-Shahr", "نجف‌آباد": "Najafabad",
        "فولادشهر": "Fooladshahr", "ورزنه": "Varzaneh",
        # استان فارس
        "شیراز": "Shiraz", "جهرم": "Jahrom", "فسا": "Fasa",
        "مرودشت": "Marvdasht", "لار": "Lar", "کازرون": "Kazerun",
        "نی‌ریز": "Neyriz", "استهبان": "Esbieh", "ممسنی": "Mamasani",
        # استان آذربایجان شرقی
        "تبریز": "Tabriz", "مراغه": "Maragheh", "میانه": "Mianeh",
        "اهر": "Ahar", "شبستر": "Shabestar", "بستان‌آباد": "Bostanabad",
        "اهر": "Ahar", "هشترود": "Hashtrud",
        # استان آذربایجان غربی
        "ارومیه": "Urmia", "خوی": "Khoy", "میاندوآب": "Miandoab",
        "بوکان": "Bukan", "سلماس": "Salmas", "پیرانشهر": "Piranshahr",
        "نقده": "Naqadeh", "ماکو": "Maku", "تکاب": "Takab",
        # استان خوزستان
        "اهواز": "Ahvaz", "آبادان": "Abadan", "خرمشهر": "Khorramshahr",
        "دزفول": "Dezful", "سوسنگرد": "Susangerd", "ماهشهر": "Mahshahr",
        "بندرامام خمینی": "Bandar Imam Khomeini", "بهبهان": "Behbahan",
        "ایذه": "Izeh", "رامهرمز": "Ramhormoz",
        # استان کرمان
        "کرمان": "Kerman", "رفسنجان": "Rafsanjan", " بم": "Bam",
        "جیرفت": "Jiroft", "سیرجان": "Sirjan", "بافت": "Bafq",
        "زرند": "Zarand", "کهنوج": "Kahnuj",
        # استان مازندران
        "ساری": "Sari", "بابل": "Babol", "آمل": "Amol",
        "قائم‌شهر": "Qaemshahr", "نور": "Nur", "چالوس": "Chalus",
        "رامسر": "Ramsar", "تنکابن": "Tonekabon", "نکا": "Neka",
        "بهشهر": "Behshahr", "سوادکوه": "Savadkuh",
        # استان گیلان
        "رشت": "Rasht", "لاهیجان": "Lahijan", "انزلی": "Anzali",
        "تالش": "Talesh", "آستارا": "Astara", "رودبار": "Rudbar",
        "صومعه‌سرا": "Someh-Sara", "فومن": "Fuman", "ماسال": "Masal",
        # استان کردستان
        "سنندج": "Sanandaj", "مهاباد": "Mahabad", "بانه": "Baneh",
        "سقندیس": "Saqqez", "مریوان": "Marivan", "قروه": "Qorveh",
        "دیواندره": "Divandarreh", "بیجار": "Bijar",
        # استان همدان
        "همدان": "Hamadan", "ملایر": "Malayer", "نهاوند": "Nahavand",
        "تویسرکان": "Toysarkan", "اسدآباد": "Asadabad",
        # استان مرکزی
        "اراک": "Arak", "ساوه": "Saveh", "خمین": "Khomeyn",
        "دلیجان": "Delijan", "تفرش": "Tafresh", "آشتیان": "Ashtian",
        # استان قم
        "قم": "Qom",
        # استان قزوین
        "قزوین": "Qazvin", "البرز": "Alborz", "تاکستان": "Takestan",
        # استان گلستان
        "گرگان": "Gorgan", "گنبد کاووس": "Gonbad-Kavus", "آزادشهر": "Azadshahr",
        "کلاله": "Kalaleh", "مینودشت": "Minoodasht",
        # استان لرستان
        "خرم‌آباد": "Khorramabad", "بروجرد": "Borujerd", "دورود": "Dorud",
        "الیگودرز": "Aligudarz", "کوهدشت": "Kuhdasht",
        # استان هرمزگان
        "بندرعباس": "Bandar-Abbas", "میناب": "Minab", "رودان": "Rudan",
        "جاسک": "Jask", "حاجی‌آباد": "Hajiabad",
        # استان سیستان و بلوچستان
        "زاهدان": "Zahedan", "چابهار": "Chabahar", "زابل": "Zabol",
        "ایرانشهر": "IranShahr", "خاش": "Khash",
        # استان کرمانشاه
        "کرمانشاه": "Kermanshah", "اسلام‌آباد غرب": "Islamabad Gharb",
        "سنقر": "Sanghor", "هرسین": "Harsin", "پاوه": "Paveh",
        "جوانرود": "Javanrud", "قصر شیرین": "Qasr-e Shirin",
        # استان اردبیل
        "اردبیل": "Ardabil", "پارس‌آباد": "Parsabad", "خلخال": "Khalkhal",
        "گرمی": "Germi",
        # استان بوشهر
        "بوشهر": "Bushehr", "برازجان": "Borazjan", "گناوه": "Ganaveh",
        "دیر": "Dayer",
        # استان یزد
        "یزد": "Yazd", "اردکان": "Ardakan", "میبد": "Meybod",
        "تفت": "Taft", "بافق": "Bafq", "ابرکوه": "Abarkuh",
        # استان ایلام
        "ایلام": "Ilam", "دهلران": "Dehloran", "آبدانان": "Abdanan",
        "مهران": "Mehran",
    }

    city_en = None
    for fa, en in city_map.items():
        if fa in question:
            city_en = en
            break

    # اگه شهر فارسی پیدا نشد، انگلیسی رو چک کن
    if not city_en:
        words = question.split()
        for word in words:
            if word.isascii() and len(word) > 3:
                city_en = word
                break

    if not city_en:
        city_en = "Tehran"  # default

    # Persian city mapping
    city_fa = {v: k for k, v in city_map.items()}.get(city_en, city_en)

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://wttr.in/{city_en}?format=j1",
                headers={"User-Agent": "TelegramBot/1.0"},
            )
            logger.info(f"Weather API: HTTP {resp.status_code} for {city_en}")
            if resp.status_code == 200:
                data = resp.json()
                current = data.get("current_condition", [{}])[0]
                weather_desc = current.get("lang_fa", [{}])
                if isinstance(weather_desc, list) and weather_desc:
                    desc = weather_desc[0].get("value", "")
                else:
                    desc = current.get("weatherDesc", [{}])[0].get("value", "")

                temp_c = current.get("temp_C", "?")
                feels_like = current.get("FeelsLikeC", "?")
                humidity = current.get("humidity", "?")
                wind_speed = current.get("windspeedKmph", "?")
                wind_dir = current.get("winddir16Point", "")
                visibility = current.get("visibility", "?")
                uv = current.get("uvIndex", "?")

                # پیش‌بینی ۳ روز
                forecast_lines = []
                for day in data.get("weather", [])[:3]:
                    date = day.get("date", "")
                    max_temp = day.get("maxtempC", "?")
                    min_temp = day.get("mintempC", "?")
                    avg = day.get("hourly", [{}])
                    if avg:
                        chance_rain = avg[len(avg)//2].get("chanceofrain", "0")
                    else:
                        chance_rain = "0"
                    forecast_lines.append(f"   📅 {date}: {min_temp}° تا {max_temp}° (بارندگی {chance_rain}%)")

                forecast_text = "\n".join(forecast_lines) if forecast_lines else ""

                result = (
                    f"🌤 هواشناسی {city_fa}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"🌡 دما: {temp_c}°C (احساس: {feels_like}°C)\n"
                    f"☁ وضعیت: {desc}\n"
                    f"💧 رطوبت: {humidity}%\n"
                    f"💨 باد: {wind_speed} km/h {wind_dir}\n"
                    f"👁 دید: {visibility} km\n"
                    f"☀ UV Index: {uv}\n\n"
                    f"📊 پیش‌بینی:\n{forecast_text}"
                )
                return result
    except Exception as e:
        logger.warning(f"weather API failed: {e}")

    return None


# ─── Currency API ───────────────────────────────────────────────────────────

async def _currency_api_search(query: str) -> str | None:
    """دریافت قیمت ارز از API مستقیم"""
    import httpx
    q = query.lower()
    
    # تشخیص نوع ارز
    currency_map = {
        "دلار": ("USD", "دلار آمریکا", "$"),
        "یورو": ("EUR", "یورو", "€"),
        "پوند": ("GBP", "پوند انگلیس", "£"),
        "لیر": ("TRY", "لیر ترکیه", "₺"),
        "درهم": ("AED", "درهم امارات", "د.إ"),
        "یوان": ("CNY", "یوان چین", "¥"),
        "ین": ("JPY", "ین ژاپن", "¥"),
        "کرون": ("SEK", "کرون سوئد", "kr"),
        "وون": ("KRW", "وون کره", "₩"),
    }
    
    # کریپتو: تتر/USDT
    is_crypto = "تتر" in q or "usdt" in q
    
    target_code = None
    target_name = None
    target_symbol = ""
    for keyword, (code, name, symbol) in currency_map.items():
        if keyword in q:
            target_code = code
            target_name = name
            target_symbol = symbol
            break
    
    if is_crypto:
        target_name = "تتر (USDT)"
        target_symbol = "₮"
    
    if not target_code and not is_crypto:
        target_code = "USD"
        target_name = "دلار آمریکا"
        target_symbol = "$"
    
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            # گرفتن نرخ USD به IRR
            resp = await client.get("https://open.er-api.com/v6/latest/USD")
            logger.info(f"Currency API: HTTP {resp.status_code}")
            if resp.status_code != 200:
                return None
            data = resp.json()
            rates = data.get("rates", {})
            usd_to_irr = rates.get("IRR")
            
            if not usd_to_irr:
                logger.warning("IRR not found in API response")
                return None
            
            raw_date = data.get("time_last_update_utc", "نامشخص")
            date = raw_date[:16] if len(raw_date) > 16 else raw_date
            
            if is_crypto:
                # اول از کانال تلگرام قیمت بگیر
                channel_prices = await _read_channel_currency()
                
                if channel_prices and "USDT" in channel_prices:
                    market_price = channel_prices["USDT"]
                    market_toman = market_price / 10
                    logger.info(f"💰 Using channel price for USDT: {market_price} IRR")
                else:
                    # fallback به CoinGecko
                    try:
                        cg_resp = await client.get(
                            "https://api.coingecko.com/api/v3/simple/price",
                            params={"ids": "tether", "vs_currencies": "usd"},
                        )
                        if cg_resp.status_code == 200:
                            cg_data = cg_resp.json()
                            usdt_usd = cg_data.get("tether", {}).get("usd", 1.0)
                        else:
                            usdt_usd = 1.0
                    except Exception:
                        usdt_usd = 1.0
                    market_price = usd_to_irr * usdt_usd
                    market_toman = market_price / 10
                
                # سایر ارزها از کانال
                usd_price = channel_prices.get("USD", 0) / 10 if channel_prices and "USD" in channel_prices else usd_to_irr / 10
                eur_price = channel_prices.get("EUR", 0) / 10 if channel_prices and "EUR" in channel_prices else 0
                gbp_price = channel_prices.get("GBP", 0) / 10 if channel_prices and "GBP" in channel_prices else 0
                
                other_lines = []
                if usd_price > 0: other_lines.append(f"   💵 دلار: {usd_price:,.0f} تومان")
                if eur_price > 0: other_lines.append(f"   💶 یورو: {eur_price:,.0f} تومان")
                if gbp_price > 0: other_lines.append(f"   💷 پوند: {gbp_price:,.0f} تومان")
                other_prices = "\n".join(other_lines)
                
                source = "📊 منبع: @Price33" if channel_prices else "📊 منبع: CoinGecko"
                
                result = (
                    f"💰 قیمت تتر (USDT)\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"📊 قیمت بازار:\n"
                    f"   {market_toman:,.0f} تومان\n"
                    f"   ({market_price:,.0f} ریال)\n\n"
                    f"📊 سایر ارزها:\n"
                    f"{other_prices}\n\n"
                    f"📅 {date}\n"
                    f"{source}"
                )
                return result
            else:
                # ارز رسمی - قیمت بازار از کانال @Price33
                target_to_usd = rates.get(target_code, 1)
                target_to_irr_official = usd_to_irr / target_to_usd if target_code != "USD" else usd_to_irr
                
                # اول از کانال تلگرام قیمت بگیر
                channel_prices = await _read_channel_currency()
                
                if channel_prices and target_code in channel_prices:
                    # قیمت مستقیم از کانال (تبدیل شده به ریال)
                    market_price = channel_prices[target_code]
                    market_toman = market_price / 10
                    logger.info(f"💰 Using Telegram channel price for {target_code}: {market_price} IRR")
                else:
                    # fallback به API بین‌المللی
                    market_price = usd_to_irr / target_to_usd if target_code != "USD" else usd_to_irr
                    market_toman = market_price / 10
                    logger.info(f"💰 Fallback to API for {target_code}: {market_price} IRR")
                
                # سایر ارزها از کانال
                eur_price = channel_prices.get("EUR", 0) / 10 if channel_prices and "EUR" in channel_prices else 0
                gbp_price = channel_prices.get("GBP", 0) / 10 if channel_prices and "GBP" in channel_prices else 0
                try_price = channel_prices.get("TRY", 0) / 10 if channel_prices and "TRY" in channel_prices else 0
                usdt_price = channel_prices.get("USDT", 0) / 10 if channel_prices and "USDT" in channel_prices else 0
                
                # فرمت قیمت‌ها
                price_lines = []
                if eur_price > 0: price_lines.append(f"   💶 یورو: {eur_price:,.0f} تومان")
                if gbp_price > 0: price_lines.append(f"   💷 پوند: {gbp_price:,.0f} تومان")
                if try_price > 0: price_lines.append(f"   💴 لیر: {try_price:,.0f} تومان")
                if usdt_price > 0: price_lines.append(f"   💵 تتر: {usdt_price:,.0f} تومان")
                other_prices = "\n".join(price_lines)
                
                source = "📊 منبع: @Price33" if channel_prices else f"📊 منبع: Exchange Rate API"
                
                result = (
                    f"💰 قیمت {target_name} ({target_symbol})\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"📊 قیمت بازار:\n"
                    f"   {market_toman:,.0f} تومان\n"
                    f"   ({market_price:,.0f} ریال)\n\n"
                    f"🏦 نرخ رسمی:\n"
                    f"   {target_to_irr_official/10:,.0f} تومان\n\n"
                    f"📊 سایر ارزها:\n"
                    f"{other_prices}\n\n"
                    f"📅 {date}\n"
                    f"{source}"
                )
                return result
    except Exception as e:
        logger.warning(f"currency API failed: {e}")
        import traceback
        logger.warning(f"traceback: {traceback.format_exc()}")
    
    return None


# ─── خواندن قیمت ارز از کانال تلگرام (@Price33) ────────────────────────────

async def _read_channel_currency(channel_username: str = "Price33") -> dict | None:
    """خواندن آخرین قیمت ارز از کانال تلگرام با اسکرپر وب"""
    import httpx
    import re
    
    try:
        url = f"https://t.me/s/{channel_username}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"Channel scrape failed: HTTP {resp.status_code}")
                return None
            
            html = resp.text
            
            # پیدا کردن آخرین پیام
            messages = re.findall(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
            if not messages:
                logger.warning("No messages found in channel")
                return None
            
            last_msg = messages[-1]  # آخرین پیام
            
            # تبدیل اعداد عربی/فارسی به انگلیسی
            arabic_nums = "٠١٢٣٤٥٦٧٨٩"
            persian_nums = "۰۱۲۳۴۵۶۷۸۹"
            for i, (ar, fa) in enumerate(zip(arabic_nums, persian_nums)):
                last_msg = last_msg.replace(ar, str(i)).replace(fa, str(i))
            
            # حذف HTML tags
            last_msg = re.sub(r'<[^>]+>', '', last_msg)
            
            # الگوهای استخراج قیمت (تومان)
            # فرمت: يورو : 214,000 یا دلار آمريکا : 187,300
            patterns = [
                (r"(?:يورو|یورو)[:\s]*(\d[\d,]+)", "EUR"),
                (r"(?:دلار|دلار آمريکا|دلار آمریکا)[:\s]*(\d[\d,]+)", "USD"),
                (r"(?:تتر|USDT)[:\s]*(\d[\d,]+)", "USDT"),
                (r"(?:پوند|پوند انگليس|پوند انگلیس)[:\s]*(\d[\d,]+)", "GBP"),
                (r"(?:درهم|درهم امارات)[:\s]*(\d[\d,]+)", "AED"),
                (r"(?:يوآن|یوان|يوآن چين|یوان چین)[:\s]*(\d[\d,]+)", "CNY"),
                (r"(?:لير|لير ترکيه|لیر ترکیه)[:\s]*(\d[\d,]+)", "TRY"),
                (r"(?:دینار|دینار کویت)[:\s]*(\d[\d,]+)", "KWD"),
            ]
            
            prices = {}
            for pattern, code in patterns:
                match = re.search(pattern, last_msg)
                if match:
                    price_str = match.group(1).replace(",", "")
                    try:
                        # قیمت به تومان است، ضرب در 10 برای ریال
                        prices[code] = int(price_str) * 10
                        logger.info(f"💰 Channel price: {code} = {prices[code]} IRR")
                    except ValueError:
                        pass
            
            if prices:
                logger.info(f"✅ Loaded {len(prices)} prices from @{channel_username}")
            else:
                logger.warning(f"No prices found in channel message: {last_msg[:200]}")
            
            return prices if prices else None
    except Exception as e:
        logger.warning(f"channel currency read failed: {e}")
        import traceback
        logger.warning(f"traceback: {traceback.format_exc()}")
    return None


# ─── Yandex Search (در ایران کار می‌کنه) ─────────────────────────────────────

async def _yandex_search(query: str, max_results: int = 3) -> list[str]:
    """استخراج snippet از Yandex Search"""
    import httpx
    import re as _re
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        async with httpx.AsyncClient(timeout=15, headers=headers, follow_redirects=True) as client:
            resp = await client.get(
                "https://yandex.com/search/",
                params={"text": query, "lr": "10393"},
            )
            logger.info(f"Yandex search: HTTP {resp.status_code}")
            if resp.status_code != 200:
                return []
            snippets = []
            # Yandex organic results
            matches = _re.findall(
                r'<div[^>]*class="[^"]*organic[^"]*"[^>]*>(.*?)</div>',
                resp.text,
                _re.DOTALL,
            )
            for m in matches[:max_results * 2]:
                clean = _re.sub(r"<[^>]+>", "", m).strip()
                if clean and len(clean) > 40:
                    snippets.append(clean[:300])
            # fallback: h3 titles
            if not snippets:
                matches = _re.findall(
                    r'<h3[^>]*>(.*?)</h3>',
                    resp.text,
                    _re.DOTALL,
                )
                for m in matches[:max_results]:
                    clean = _re.sub(r"<[^>]+>", "", m).strip()
                    if clean and len(clean) > 10:
                        snippets.append(clean[:300])
            # fallback: snippet divs
            if not snippets:
                matches = _re.findall(
                    r'<div[^>]*class="[^"]*TextContainer[^"]*"[^>]*>(.*?)</div>',
                    resp.text,
                    _re.DOTALL,
                )
                for m in matches[:max_results]:
                    clean = _re.sub(r"<[^>]+>", "", m).strip()
                    if clean and len(clean) > 30:
                        snippets.append(clean[:300])
            return snippets[:max_results]
    except Exception as e:
        logger.warning(f"Yandex search failed: {e}")
        return []


# ─── Google Search (وقتی DDG فیلتره) ──────────────────────────────────────────

async def _google_search(query: str, max_results: int = 5) -> list[dict]:
    """استخراج snippet + URL از Google Search"""
    import httpx
    import re as _re
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    results = []
    try:
        async with httpx.AsyncClient(timeout=15, headers=headers, follow_redirects=True) as client:
            resp = await client.get(
                "https://www.google.com/search",
                params={"q": query, "hl": "fa", "num": max_results},
            )
            logger.info(f"Google search: HTTP {resp.status_code}")
            if resp.status_code != 200:
                return []
            
            html = resp.text
            
            # استخراج لینک‌ها و عنوان‌ها
            # الگوی اصلی: <a href="/url?q=URL...">TITLE</a>
            link_pattern = r'<a[^>]*href="/url\?q=([^&"]+)[^"]*"[^>]*>(.*?)</a>'
            links = _re.findall(link_pattern, html, _re.DOTALL)
            
            # الگوی snippets
            snippet_patterns = [
                r'<div[^>]*class="[^"]*VwiC3b[^"]*"[^>]*>(.*?)</div>',
                r'<div[^>]*class="[^"]*BNeawe[^"]*"[^>]*>(.*?)</div>',
                r'<span[^>]*class="[^"]*aCOpRe[^"]*"[^>]*>(.*?)</span>',
            ]
            
            # ترکیب لینک‌ها و snippets
            for url, title in links[:max_results * 2]:
                if not url.startswith("http"):
                    continue
                title_clean = _re.sub(r"<[^>]+>", "", title).strip()
                if not title_clean or len(title_clean) < 5:
                    continue
                
                # پیدا کردن snippet مرتبط
                snippet = ""
                for pattern in snippet_patterns:
                    match = _re.search(pattern, html)
                    if match:
                        snippet = _re.sub(r"<[^>]+>", "", match.group(1)).strip()
                        if snippet and len(snippet) > 20:
                            break
                
                if title_clean:
                    results.append({
                        "title": title_clean[:100],
                        "url": url[:200],
                        "snippet": snippet[:300] if snippet else ""
                    })
                    if len(results) >= max_results:
                        break
            
            logger.info(f"Google: {len(results)} results with URLs")
    except Exception as e:
        logger.warning(f"Google search failed: {e}")
    return results


# ─── Bing Search (وقتی DDG و Google فیلترن) ──────────────────────────────────

async def _bing_search(query: str, max_results: int = 5) -> list[dict]:
    """استخراج snippet + URL از Bing Search"""
    import httpx
    import re as _re
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    results = []
    try:
        async with httpx.AsyncClient(timeout=15, headers=headers, follow_redirects=True) as client:
            resp = await client.get(
                "https://www.bing.com/search",
                params={"q": query, "count": max_results},
            )
            logger.info(f"Bing search: HTTP {resp.status_code}")
            if resp.status_code != 200:
                return []
            
            html = resp.text
            
            # استخراج لینک‌ها و snippets
            # Bing: <li class="b_algo"> <h2><a href="URL">TITLE</a></h2> <p>SNIPPET</p>
            pattern = r'<li class="b_algo">\s*<h2><a href="([^"]+)"[^>]*>(.*?)</a></h2>\s*(?:<p>(.*?)</p>)?'
            matches = _re.findall(pattern, html, _re.DOTALL)
            
            for url, title, snippet in matches[:max_results]:
                title_clean = _re.sub(r"<[^>]+>", "", title).strip()
                snippet_clean = _re.sub(r"<[^>]+>", "", snippet).strip() if snippet else ""
                if title_clean:
                    results.append({
                        "title": title_clean[:100],
                        "url": url[:200],
                        "snippet": snippet_clean[:300]
                    })
            
            logger.info(f"Bing: {len(results)} results with URLs")
    except Exception as e:
        logger.warning(f"Bing search failed: {e}")
    return results


async def _ddg_html_search(query: str, max_results: int = 5) -> list[dict]:
    """استخراج snippet + URL از DuckDuckGo HTML"""
    import httpx
    import re as _re
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    results = []
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        resp = await client.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
        )
    
    html = resp.text
    
    # استخراج لینک‌ها و snippets
    # DDG: <a class="result__a" href="URL">TITLE</a> <a class="result__snippet">SNIPPET</a>
    link_pattern = r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
    snippet_pattern = r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>'
    
    links = _re.findall(link_pattern, html, _re.DOTALL)
    snippets_raw = _re.findall(snippet_pattern, html, _re.DOTALL)
    
    for i, (url, title) in enumerate(links[:max_results]):
        title_clean = _re.sub(r"<[^>]+>", "", title).strip()
        snippet_clean = ""
        if i < len(snippets_raw):
            snippet_clean = _re.sub(r"<[^>]+>", "", snippets_raw[i]).strip()
        
        if title_clean:
            results.append({
                "title": title_clean[:100],
                "url": url[:200],
                "snippet": snippet_clean[:300]
            })
    
    logger.info(f"DDG HTML: {len(results)} results with URLs")
    return results


# ─── Brave Search ─────────────────────────────────────────────────────────────

async def _brave_search(query: str, max_results: int = 5) -> list[dict]:
    """استخراج نتایج از Brave Search"""
    import httpx
    import re as _re
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    results = []
    try:
        async with httpx.AsyncClient(timeout=15, headers=headers, follow_redirects=True) as client:
            resp = await client.get(
                "https://search.brave.com/search",
                params={"q": query},
            )
            logger.info(f"Brave search: HTTP {resp.status_code}")
            if resp.status_code != 200:
                return []
            
            html = resp.text
            
            # Brave: <div class="snippet"> <a class="result-header" href="URL">TITLE</a> <p class="snippet-description">SNIPPET</p>
            pattern = r'<div[^>]*class="[^"]*snippet[^"]*"[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*class="[^"]*result-header[^"]*"[^>]*>(.*?)</a>.*?<p[^>]*class="[^"]*snippet-description[^"]*"[^>]*>(.*?)</p>'
            matches = _re.findall(pattern, html, _re.DOTALL)
            
            for url, title, snippet in matches[:max_results]:
                title_clean = _re.sub(r"<[^>]+>", "", title).strip()
                snippet_clean = _re.sub(r"<[^>]+>", "", snippet).strip()
                if title_clean:
                    results.append({
                        "title": title_clean[:100],
                        "url": url[:200],
                        "snippet": snippet_clean[:300]
                    })
            
            logger.info(f"Brave: {len(results)} results")
    except Exception as e:
        logger.warning(f"Brave search failed: {e}")
    return results


# ─── Startpage Search ─────────────────────────────────────────────────────────

async def _startpage_search(query: str, max_results: int = 5) -> list[dict]:
    """استخراج نتایج از Startpage"""
    import httpx
    import re as _re
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    results = []
    try:
        async with httpx.AsyncClient(timeout=15, headers=headers, follow_redirects=True) as client:
            resp = await client.get(
                "https://www.startpage.com/do/dsearch",
                params={"query": query, "cat": "web"},
            )
            logger.info(f"Startpage search: HTTP {resp.status_code}")
            if resp.status_code != 200:
                return []
            
            html = resp.text
            
            # Startpage: <a class="w-gl__result-url" href="URL">TITLE</a>
            pattern = r'<a[^>]*class="[^"]*w-gl__result-url[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
            matches = _re.findall(pattern, html, _re.DOTALL)
            
            for url, title in matches[:max_results]:
                title_clean = _re.sub(r"<[^>]+>", "", title).strip()
                if title_clean and url.startswith("http"):
                    results.append({
                        "title": title_clean[:100],
                        "url": url[:200],
                        "snippet": ""
                    })
            
            logger.info(f"Startpage: {len(results)} results")
    except Exception as e:
        logger.warning(f"Startpage search failed: {e}")
    return results


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


async def _summarize_snippets(question: str, snippets: list[dict]) -> str | None:
    """استفاده از AI برای خلاصه‌سازی نتایج وب به جواب واحد با لینک"""
    # ساخت context با لینک‌ها
    context_parts = []
    urls = []
    for i, s in enumerate(snippets):
        if isinstance(s, dict):
            title = s.get("title", "")
            url = s.get("url", "")
            snippet = s.get("snippet", "")
            context_parts.append(f"[{i+1}] {title}\n{snippet}")
            if url:
                urls.append(f"🔗 {title}: {url}")
        else:
            context_parts.append(f"[{i+1}] {s}")
    
    context = "\n\n".join(context_parts)
    urls_text = "\n".join(urls[:5]) if urls else ""
    
    prompt = (
        f"بر اساس این نتایج جست‌وجو، به سوال زیر پاسخ بده:\n\n"
        f"سوال: {question}\n\n"
        f"نتایج جست‌وجو:\n{context}\n\n"
        "پاسخ رو به فارسی و بر اساس این اطلاعات بنویس. "
        "اگه اطلاعات کافی نیست، صادقانه بگو. "
        "لینک‌های مرتبط رو در انتهای پاسخ قرار بده."
    )
    
    answer = None
    # اول Groq
    if _groq_client:
        try:
            answer = await _generate_groq_general(prompt)
        except Exception as e:
            logger.warning(f"Groq summarize failed: {e}")
    # fallback Gemini
    if not answer and _gemini_model:
        try:
            answer = await _generate_gemini_general(prompt)
        except Exception as e:
            logger.warning(f"Gemini summarize failed: {e}")
    
    if answer:
        result = "🌐 (بر اساس جست‌وجو در وب)\n\n" + answer
        if urls_text:
            result += f"\n\n📌 لینک‌های مرتبط:\n{urls_text}"
        return result
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
