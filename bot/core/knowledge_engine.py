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
from bot.utils.helpers import (
    get_persian_date_info,
    is_datetime_query,
    get_datetime_response,
    to_persian_digits,
)

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
        # gemini-1.5-flash مدل پایدار و سریع Google
        _model_name = GEMINI_MODEL if GEMINI_MODEL else "gemini-1.5-flash"
        _gemini_model = genai.GenerativeModel(_model_name)
    except Exception as e:
        logger.warning(f"Gemini init failed: {e}")

# ── System prompt برای پاسخ‌دهی (تخصصی VPN/شبکه و مشاوره هوشمند) ────────────
ANSWER_SYSTEM_PROMPT = (
    "تو یک مشاور تخصصی خرید، کارشناس فنی و دستیار هوشمند همه‌فن‌حریف در گروه تلگرامی هستی.\n"
    "در مشاوره خرید انواع کالاها (لوازم خانگی مانند جاروبرقی، تلویزیون، یخچال، کالاهای دیجیتال مثل گوشی و لپ‌تاپ)، "
    "مقایسه محصولات، شبکه و VPN و پاسخ به پرسش‌های کاربران تسلط کامل داری.\n\n"
    "## نحوه پاسخ به سوالات مشاوره و مقایسه خرید (مانند «جاروبرقی کیسه‌ای بهتره یا مخزن‌دار؟»):\n"
    "۱) تحلیل دقیق و بی‌طرفانه: مزایا و معایب هر گزینه را با دسته‌بندی و بولت‌پوینت‌های مرتب مقایسه کن (بهداشت، قدرت مکش، نگهداری، هزینه‌های جانبی، افراد دارای آلرژی و...). \n"
    "۲) ارائه نتیجه‌گیری کاربردی و شفاف: مشخص کن هر گزینه برای چه سبک زندگی و نیازهایی مناسب‌تر است.\n"
    "۳) پیشنهاد مدل‌های برتر: محبوب‌ترین برندها و مدل‌های باکیفیت موجود در بازار ایران (مثل بوش، فیلیپس، سامسونگ، پارس خزر) را نام ببر.\n"
    "۴) نگارش روان، فارسی اصیل و بدون اصطلاحات گیج‌کننده با لحنی صمیمی و در عین حال حرفه‌ای.\n"
    "۵) از قالب‌بندی مرتب با تگ‌های مجاز <b> و <i> استفاده کن. تگ‌های تودرتوی ناقص یا کدهای شکسته هرگز ننویس.\n"
    "۶) به تقویم رسمی ایران، روزهای هفته (شنبه تا جمعه)، تاریخ شمسی و میلادی و زمان کنونی مسلط هستی و به سوالات زمانی با دقت روز جاری پاسخ می‌دهی.\n"
)

PROMPT_TEMPLATE = (
    "{context}"
    "سوال کاربر: {question}\n\n"
    "پاسخ ساختاریافته، تحلیلی و راهنمای کامل به زبان فارسی:"
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
    # ۰. تقویم، تاریخ و ساعت رسمی کشور (پاسخ آنی، دقیق و بدون تاخیر)
    if is_datetime_query(question):
        dt_ans = get_datetime_response(question)
        if dt_ans:
            if user_id:
                try:
                    await db.add_conversation_message(user_id, chat_id, "user", question)
                    await db.add_conversation_message(user_id, chat_id, "assistant", dt_ans)
                except Exception:
                    pass
            return {
                "answer": dt_ans,
                "source": "calendar_clock",
                "confidence": 1.0,
            }

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

    # ۲. ساخت context غنی: تقویم زنده + تاریخچه گروه + حافظه مکالمه + پروفایل کاربر
    context_parts = []

    # ۲-۰. زمان و تقویم رسمی کنونی کشور (ایران - تهران) برای درک کامل هوش مصنوعی از امروز
    try:
        dt_info = get_persian_date_info()
        context_parts.append(
            f"📅 زمان و تقویم رسمی لحظه‌ای (ایران - تهران):\n"
            f"• روز هفته: {dt_info['weekday_name']}\n"
            f"• تاریخ خورشیدی (شمسی): {dt_info['jd']} {dt_info['month_name']} {dt_info['jy']} ({dt_info['date_fa_num']})\n"
            f"• تاریخ میلادی: {dt_info['date_g_full']}\n"
            f"• ساعت رسمی: {dt_info['time_str']}"
        )
    except Exception as e:
        logger.warning(f"Failed to append datetime info to context: {e}")

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


# ─── تشخیص نوع سوال (مشاوره/مقایسه در برابر استعلام قیمت) ─────────────────

def is_advice_or_comparison_question(question: str) -> bool:
    """
    تشخیص می‌دهد که آیا سوال کاربر یک سوال مشاوره‌ای، مقایسه‌ای یا فنی است یا نه.
    مثل: «جاروبرقی کیسه‌ای بهتره یا مخزن‌دار؟»، «چی بخرم؟»، «کدوم مدل بهتره؟»
    این سوالات حتماً باید توسط هوش مصنوعی (AI) تحلیل و پاسخ داده شوند نه با سرچ وب یا ترب!
    """
    q = question.lower().strip()
    comparison_patterns = [
        "بهتره", "کدوم", "فرق", "تفاوت", "مقایسه", "چی بخرم", "چی بگیرم",
        "پیشنهاد", "معایب", "مزایا", "نظرت", "راهنمایی", "خوبه", "چطوره", "کدومه",
        "کیسه‌ای", "مخزن‌دار", "کیسه ای", "مخزندار", "چگونه", "چطور", "علت", "دلیل",
        "نحوه", "آموزش", "توضیح", "بهترین", "ارزش خرید", "بررسی", "نظرت چیه"
    ]
    if " یا " in q:
        return True
    return any(w in q for w in comparison_patterns)


def is_explicit_price_query(question: str) -> bool:
    """
    آیا کاربر به طور مشخص استعلام نرخ و قیمت کالا یا ارز کرده است؟
    مثلاً: «قیمت جاروبرقی بوش»، «قیمت دلار»، «قیمت طلا»، «چند تومنه»
    """
    if is_advice_or_comparison_question(question):
        return False
    q = question.lower().strip()
    price_indicators = ["قیمت", "نرخ", "چند تومنه", "چندتومنه", "چنده", "استعلام قیمت"]
    return any(p in q for p in price_indicators)


def needs_web_search(question: str) -> bool:
    """
    تشخیص می‌دهد که آیا این سوال به اطلاعات لحظه‌ای (قیمت، آب‌وهوا، تاریخ) نیاز دارد یا نه.
    نکته بسیار مهم: سوالات مشاوره‌ای، مقایسه‌ای یا فنی هرگز نباید وب‌سرچ شوند و مستقیماً به هوش مصنوعی می‌روند.
    """
    # ۱. اگر سوال مقایسه‌ای، مشاوره‌ای، نظری یا فنی است -> حتماً AI پاسخ دهد
    if is_advice_or_comparison_question(question):
        return False

    q = question.lower().strip()
    if len(q) < 3:
        return False

    # ۱.۵. تاریخ، تقویم و ساعت زنده
    if is_datetime_query(q):
        return True

    # ۲. آیا استعلام صریح قیمت است؟
    if is_explicit_price_query(q):
        return True

    # ۳. آب‌وهوا
    weather_words = ["هواشناسی", "آب و هوا", "آب‌وهوا", "هوای", "دمای هوا", "باران", "برف", "weather"]
    if any(w in q for w in weather_words):
        return True

    # ۴. تاریخ و زمان زنده
    time_words = ["ساعت چند", "امروز چندمه", "تاریخ امروز", "چه روزیه"]
    if any(w in q for w in time_words):
        return True

    # ۵. اخبار و رویدادهای زنده لحظه‌ای
    live_words = ["اخبار امروز", "آخرین اخبار", "خبر فوری", "نتیجه بازی", "نتایج زنده"]
    if any(w in q for w in live_words):
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

    # ۰. تقویم، تاریخ و ساعت رسمی کشور (بدون تاخیر و با دقت کامل)
    if is_datetime_query(question):
        dt_res = get_datetime_response(question)
        if dt_res:
            logger.info("✅ Direct Persian calendar/clock returned result")
            return dt_res

    snippets = []
    logger.info(f"🔍 starting web search for: '{question[:50]}'")

    # ۰.۱. اگه سوال مربوط به هواشناسی هست، اول Weather API رو امتحان کن
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

    # ۰.۲۵. اگه سوال مربوط به طلا و سکه هست، اول از کانال قیمت بگیر
    gold_keywords_check = ["طلا", "سکه", "امامی", "بهار آزاد", "گرم طلا", "طلای 18", "طلای ۱۸"]
    if any(kw in question for kw in gold_keywords_check):
        try:
            gold_result = await _gold_api_search(question)
            if gold_result:
                logger.info("✅ Gold API returned result")
                await _cache_web_answer(question, gold_result)
                return gold_result
        except Exception as e:
            logger.warning(f"gold API search failed: {e}")

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

    # ۰.۶. استعلام قیمت رمزارزها (Binance / Crypto)
    crypto_keywords = [
        "بیت کوین", "بیتکوین", "btc", "اتریوم", "eth", "سولانا", "sol",
        "تون", "تون کوین", "ton", "دوج", "دوج کوین", "doge", "ترون", "trx",
        "ریپل", "xrp", "شیبا", "shib", "کریپتو", "ارز دیجیتال", "ارزدیجیتال", "crypto"
    ]
    if any(kw in question.lower() for kw in crypto_keywords):
        try:
            crypto_result = await _crypto_api_search(question)
            if crypto_result:
                logger.info("✅ Crypto API returned result")
                await _cache_web_answer(question, crypto_result)
                return crypto_result
        except Exception as e:
            logger.warning(f"crypto API search failed: {e}")

    # ۰.۷. استعلام قیمت کالا و محصولات بازار ایران از ترب (فقط در صورت استعلام صریح قیمت، نه سوالات مشاوره‌ای)
    if is_explicit_price_query(question):
        try:
            prod_result = await _product_price_search(question)
            if prod_result and prod_result.get("text"):
                logger.info("✅ Torob Product API returned result")
                await _cache_web_answer(question, prod_result["text"])
                return prod_result["text"]
        except Exception as e:
            logger.warning(f"product price search failed: {e}")

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
    """دریافت اطلاعات پیشرفته هواشناسی شهرهای ایران و جهان با احتمال بارش و UI زیبا"""
    try:
        from bot.core.weather import get_weather_info
        text, _ = await get_weather_info(question)
        return text
    except Exception as e:
        logger.warning(f"weather search failed: {e}")
        return None


# ─── سیستم استعلام نرخ ارز، طلا و سکه (TGJU + @ba_z1 + Wallex) ───

# کش کوتاه‌مدت برای سرعت پاسخ‌دهی و جلوگیری از فشار به سرورها (TTL: ۳ دقیقه)
_MARKET_RATES_CACHE: dict = {}
_MARKET_RATES_CACHE_TIME: float = 0.0
_MARKET_CACHE_TTL: float = 180.0

# کلمات کلیدی طلا و سکه
_GOLD_KEYWORDS = (
    "طلا", "طلای 18", "طلای ۱۸", "گرم طلا", "سکه", "سککه", "امامی",
    "بهار آزادی", "بهار ازادی", "نیم سکه", "ربع سکه", "سکه گرمی"
)


async def _read_baz1_market_rates() -> dict | None:
    """
    استعلام زنده آخرین نرخ معاملات بازار نقدی و فردایی تهران از کانال تلگرام @ba_z1
    (دلار فردایی تهران خرید/فروش/معامله، طلا ۱۸ عیار، آبشده نقدی، تتر)
    """
    import httpx
    import re

    try:
        url = "https://t.me/s/ba_z1"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": "fa,en;q=0.9",
        }
        async with httpx.AsyncClient(timeout=8, follow_redirects=True, headers=headers) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning(f"@ba_z1 scrape failed: HTTP {resp.status_code}")
                return None

            html = resp.text
            msgs = re.findall(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
            if not msgs:
                return None

            for raw in reversed(msgs):
                clean = re.sub(r'<[^>]+>', ' ', raw)
                for z in ('\u200c', '\u200b', '\u200e', '\u200f', '\ufeff'):
                    clean = clean.replace(z, '')
                for i, (ar, fa) in enumerate(zip("٠١٢٣٤٥٦٧٨٩", "۰۱۲۳۴۵۶۷۸۹")):
                    clean = clean.replace(ar, str(i)).replace(fa, str(i))

                if "دلار فردایی تهران" in clean or "#طلا_گرمی" in clean:
                    def _num(s: str | None) -> float:
                        if not s:
                            return 0.0
                        c = s.replace(",", "").replace(".", "").replace(" ", "").strip()
                        try:
                            return float(c)
                        except (ValueError, TypeError):
                            return 0.0

                    m_deal = re.search(r'(\d{2,3}[\.,\s]?\d{3})\s*معامله', clean)
                    m_buy = re.search(r'(\d{2,3}[\.,\s]?\d{3})\s*خرید', clean)
                    m_sell = re.search(r'(\d{2,3}[\.,\s]?\d{3})\s*فروش', clean)
                    m_gold = re.search(r'#طلا_گرمی\s*(\d[\d,]+)', clean)
                    m_abshodeh = re.search(r'#(?:آبشده_نقدی|آبشده_اتحادیه)\s*(\d[\d,]+)', clean)
                    m_usdt = re.search(r'#تتر\s*\[USDT\]\s*(\d[\d,]+)', clean)
                    m_time = re.search(r'\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})\]', clean)

                    deal_t = _num(m_deal.group(1)) if m_deal else 0.0
                    buy_t = _num(m_buy.group(1)) if m_buy else 0.0
                    sell_t = _num(m_sell.group(1)) if m_sell else 0.0
                    gold_t = float(m_gold.group(1).replace(",", "")) if m_gold else 0.0
                    abshodeh_t = float(m_abshodeh.group(1).replace(",", "")) if m_abshodeh else 0.0
                    usdt_t = float(m_usdt.group(1).replace(",", "")) if m_usdt else 0.0
                    time_str = m_time.group(1) if m_time else ""

                    if deal_t or buy_t or gold_t:
                        return {
                            "usd_deal": deal_t or buy_t,
                            "usd_buy": buy_t,
                            "usd_sell": sell_t,
                            "gold18": gold_t,
                            "abshodeh": abshodeh_t,
                            "usdt": usdt_t,
                            "time": time_str,
                            "channel": "@ba_z1",
                        }
    except Exception as e:
        logger.warning(f"Error fetching @ba_z1 channel rates: {e}")
    return None


async def _get_live_market_rates() -> dict:
    """
    دریافت جامع و زنده نرخ‌های ارز، طلا و سکه از ۲ مرجع معتبر و مکمل بازار:
    ۱. TGJU (شبکه اطلاع‌رسانی طلا، سکه و ارز) - منبع رسمی بازار صرافی‌ها و اتحادیه
    ۲. کانال بازار فردایی تهران (@ba_z1) - منبع زنده معاملات لحظه‌ای کف بازار تهران
    ۳. Wallex / Bitpin - صرافی‌های آنلاین برای نرخ لحظه‌ای تتر (USDT)
    ۴. تلگرام (@Price33) - پشتیبان اضطراری در صورت قطعی اینترنت
    """
    global _MARKET_RATES_CACHE, _MARKET_RATES_CACHE_TIME
    import time
    import httpx

    now = time.time()
    if _MARKET_RATES_CACHE and (now - _MARKET_RATES_CACHE_TIME < _MARKET_CACHE_TTL):
        return _MARKET_RATES_CACHE

    rates = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.tgju.org/",
    }

    # ۱. استعلام از منبع ۱: TGJU (شبکه اطلاع‌رسانی طلا، سکه و ارز تهران)
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True, headers=headers) as client:
            resp = await client.get("https://call.tgju.org/ajax.json")
            if resp.status_code == 200:
                cur = resp.json().get("current", {})

                def _parse_tgju(key: str) -> dict | None:
                    item = cur.get(key, {})
                    p_str = item.get("p")
                    if not p_str:
                        return None
                    try:
                        clean_p = str(p_str).replace(",", "").strip()
                        p_toman = float(clean_p) / 10
                        h_str = item.get("h")
                        l_str = item.get("l")
                        high_t = float(str(h_str).replace(",", "")) / 10 if h_str else p_toman
                        low_t = float(str(l_str).replace(",", "")) / 10 if l_str else p_toman
                        return {
                            "price": p_toman,
                            "price_rial": p_toman * 10,
                            "high": high_t,
                            "low": low_t,
                            "time": item.get("t", ""),
                        }
                    except (ValueError, TypeError):
                        return None

                tgju_mapping = {
                    "USD": "price_dollar_rl",
                    "EUR": "price_eur",
                    "GBP": "price_gbp",
                    "AED": "price_aed",
                    "TRY": "price_try",
                    "CNY": "price_cny",
                    "CAD": "price_cad",
                    "AUD": "price_aud",
                    "KWD": "price_kwd",
                    "IQD": "price_iqd",
                    "GOLD18": "tgju_gold_irg18",
                    "COIN_EMAMI": "sekee",
                    "COIN_HALF": "nim",
                    "COIN_QUARTER": "rob",
                    "COIN_GRAMI": "gerami",
                }
                for code, key in tgju_mapping.items():
                    val = _parse_tgju(key)
                    if not val and code == "GOLD18":
                        val = _parse_tgju("geram18")
                    if val:
                        rates[code] = val
                rates["source"] = "شبکه اطلاع‌رسانی طلا و ارز (TGJU)"
    except Exception as e:
        logger.warning(f"TGJU rate fetch failed: {e}")

    # ۲. استعلام از منبع ۲: کانال بازار فردایی تهران (@ba_z1)
    try:
        baz1_data = await _read_baz1_market_rates()
        if baz1_data:
            rates["BAZ1"] = baz1_data
            # در صورتی که TGJU دلار نداده بود، نرخ BAZ1 جایگزین اصلی شود
            if "USD" not in rates and baz1_data.get("usd_deal"):
                rates["USD"] = {
                    "price": baz1_data["usd_deal"],
                    "price_rial": baz1_data["usd_deal"] * 10,
                    "high": baz1_data.get("usd_sell", baz1_data["usd_deal"]),
                    "low": baz1_data.get("usd_buy", baz1_data["usd_deal"]),
                    "time": baz1_data.get("time", ""),
                }
            # در صورتی که TGJU طلا نداده بود
            if "GOLD18" not in rates and baz1_data.get("gold18"):
                rates["GOLD18"] = {
                    "price": baz1_data["gold18"],
                    "price_rial": baz1_data["gold18"] * 10,
                    "high": baz1_data["gold18"],
                    "low": baz1_data["gold18"],
                    "time": baz1_data.get("time", ""),
                }
    except Exception as e:
        logger.warning(f"BAZ1 channel fetch failed: {e}")

    # ۳. استعلام نرخ لحظه‌ای تتر (USDT) از صرافی‌های والکس و بیت‌پین
    try:
        async with httpx.AsyncClient(timeout=6, follow_redirects=True, headers=headers) as client:
            rw = await client.get("https://api.wallex.ir/v1/markets")
            if rw.status_code == 200:
                wd = rw.json()
                u_stats = wd.get("result", {}).get("symbols", {}).get("USDTTMN", {}).get("stats", {})
                last_w = u_stats.get("lastPrice")
                if last_w:
                    p = float(last_w)
                    rates["USDT"] = {
                        "price": p,
                        "price_rial": p * 10,
                        "high": float(u_stats.get("highPrice", p)) if u_stats.get("highPrice") else p,
                        "low": float(u_stats.get("lowPrice", p)) if u_stats.get("lowPrice") else p,
                        "time": "معاملات ۲۴ ساعته",
                    }
    except Exception as e:
        logger.warning(f"Wallex rate fetch failed: {e}")

    if "USDT" not in rates:
        # اگر والکس نبود و BAZ1 تتر داشت، از BAZ1 بردار
        if rates.get("BAZ1", {}).get("usdt"):
            u_p = rates["BAZ1"]["usdt"]
            rates["USDT"] = {
                "price": u_p,
                "price_rial": u_p * 10,
                "high": u_p,
                "low": u_p,
                "time": "بازار تهران",
            }
        else:
            try:
                async with httpx.AsyncClient(timeout=6, follow_redirects=True, headers=headers) as client:
                    rb = await client.get("https://api.bitpin.ir/v1/mkt/markets/")
                    if rb.status_code == 200:
                        for m in rb.json().get("results", []):
                            if m.get("code") in ("USDT_IRT", "usdt_irt"):
                                p = float(m.get("price"))
                                rates["USDT"] = {
                                    "price": p,
                                    "price_rial": p * 10,
                                    "high": p,
                                    "low": p,
                                    "time": "معاملات ۲۴ ساعته",
                                }
                                break
            except Exception as e:
                logger.warning(f"Bitpin rate fetch failed: {e}")

    # ۴. فال‌بک کانال تلگرام (@Price33) در صورت نبود نرخ‌های اصلی
    if not rates or "USD" not in rates:
        try:
            ch_prices = await _read_channel_currency()
            if ch_prices:
                for k, v in ch_prices.items():
                    if k not in rates:
                        p_t = v / 10
                        rates[k] = {
                            "price": p_t,
                            "price_rial": v,
                            "high": p_t,
                            "low": p_t,
                            "time": "کانال بازار ارز",
                        }
                rates["source"] = "کانال بازار ارز"
        except Exception as e:
            logger.warning(f"Channel currency fallback failed: {e}")

    if rates:
        _MARKET_RATES_CACHE = rates
        _MARKET_RATES_CACHE_TIME = now
        return rates

    return _MARKET_RATES_CACHE


async def _gold_api_search(query: str) -> str | None:
    """استعلام دقیق قیمت طلا و سکه از ۲ منبع (TGJU رسمی + کانال بازار فردایی @ba_z1)"""
    q = query.lower()
    if not any(k in q for k in _GOLD_KEYWORDS):
        return None

    rates = await _get_live_market_rates()
    if not rates:
        return None

    gold18 = rates.get("GOLD18", {}).get("price", 0)
    gold18_rial = rates.get("GOLD18", {}).get("price_rial", 0)
    baz1 = rates.get("BAZ1", {})
    gold18_baz1 = baz1.get("gold18", 0)
    abshodeh_baz1 = baz1.get("abshodeh", 0)

    sekee = rates.get("COIN_EMAMI", {}).get("price", 0)
    nim = rates.get("COIN_HALF", {}).get("price", 0)
    rob = rates.get("COIN_QUARTER", {}).get("price", 0)
    gerami = rates.get("COIN_GRAMI", {}).get("price", 0)
    usd = baz1.get("usd_deal") or rates.get("USD", {}).get("price", 0)
    usdt = rates.get("USDT", {}).get("price", 0) or baz1.get("usdt", 0)

    if not gold18 and not gold18_baz1 and not sekee:
        return None

    from bot.utils.helpers import get_persian_date_info
    date_info = get_persian_date_info()

    lines = [
        "🏅 <b>قیمت روز طلا و انواع سکه در بازار تهران:</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━\n",
    ]

    # بخش طلای ۱۸ عیار و آبشده (مقایسه دو منبع در صورت وجود هر دو)
    if gold18 or gold18_baz1 or abshodeh_baz1:
        if gold18 and gold18_baz1:
            lines.append("🥇 <b>طلای ۱۸ عیار (هر گرم) — مقایسه ۲ منبع:</b>")
            lines.append("<blockquote>")
            g_tgju_fa = to_persian_digits(f"{gold18:,.0f}")
            gr_tgju_fa = to_persian_digits(f"{gold18_rial:,.0f}")
            lines.append(f"🏛 <b>نرخ اتحادیه (TGJU):</b> <b>{g_tgju_fa}</b> تومان  <code>({gr_tgju_fa} ریال)</code>")
            g_baz1_fa = to_persian_digits(f"{gold18_baz1:,.0f}")
            lines.append(f"⛳️ <b>معاملات بازار تهران (@ba_z1):</b> <b>{g_baz1_fa}</b> تومان")
            if abshodeh_baz1:
                ab_fa = to_persian_digits(f"{abshodeh_baz1:,.0f}")
                lines.append(f"💧 <b>آبشده نقدی (هر مثقال):</b> <b>{ab_fa}</b> تومان")
            lines.append("</blockquote>\n")
        elif gold18:
            lines.append("<blockquote>")
            g_fa = to_persian_digits(f"{gold18:,.0f}")
            gr_fa = to_persian_digits(f"{gold18_rial:,.0f}")
            lines.append(f"🥇 <b>طلای ۱۸ عیار (هر گرم):</b>\n   <b>{g_fa}</b> تومان  <code>({gr_fa} ریال)</code>")
            lines.append("</blockquote>\n")
        elif gold18_baz1:
            lines.append("<blockquote>")
            gb_fa = to_persian_digits(f"{gold18_baz1:,.0f}")
            lines.append(f"🥇 <b>طلای ۱۸ عیار (معاملات بازار تهران):</b>\n   <b>{gb_fa}</b> تومان")
            if abshodeh_baz1:
                ab_fa = to_persian_digits(f"{abshodeh_baz1:,.0f}")
                lines.append(f"💧 <b>آبشده نقدی:</b> <b>{ab_fa}</b> تومان")
            lines.append("</blockquote>\n")

    # بخش انواع سکه
    if sekee or nim or rob or gerami:
        lines.append("🪙 <b>قیمت انواع سکه (مرجع رسمی TGJU):</b>")
        lines.append("<blockquote>")
        if sekee:
            s_fa = to_persian_digits(f"{sekee:,.0f}")
            lines.append(f"🪙 <b>سکه تمام طرح جدید (امامی):</b> <b>{s_fa}</b> تومان")
        if nim:
            n_fa = to_persian_digits(f"{nim:,.0f}")
            lines.append(f"🪙 <b>نیم سکه بهار آزادی:</b> <b>{n_fa}</b> تومان")
        if rob:
            r_fa = to_persian_digits(f"{rob:,.0f}")
            lines.append(f"🪙 <b>ربع سکه بهار آزادی:</b> <b>{r_fa}</b> تومان")
        if gerami:
            gm_fa = to_persian_digits(f"{gerami:,.0f}")
            lines.append(f"🪙 <b>سکه گرمی:</b> <b>{gm_fa}</b> تومان")
        lines.append("</blockquote>\n")

    indicators = []
    if usd:
        u_fa = to_persian_digits(f"{usd:,.0f}")
        indicators.append(f"💵 دلار آزاد: <b>{u_fa}</b> تومان")
    if usdt:
        ut_fa = to_persian_digits(f"{usdt:,.0f}")
        indicators.append(f"⚡ تتر: <b>{ut_fa}</b> تومان")
    if indicators:
        lines.append("📊 <b>شاخص ارز مرتبط:</b>")
        lines.append("   " + " | ".join(indicators) + "\n")

    t_fa = to_persian_digits(date_info["time_str"])
    lines.append(f"🗓 <i>تاریخ: {date_info['date_fa_full']} — ساعت {t_fa}</i>")

    sources = []
    if gold18 or sekee:
        sources.append("TGJU رسمی")
    if gold18_baz1 or abshodeh_baz1:
        sources.append("کانال بازار تهران (@ba_z1)")
    source_str = " + ".join(sources) if sources else "TGJU و بازار آزاد"
    lines.append(f"🌐 <i>منابع: {source_str}</i>")

    return "\n".join(lines)


async def _currency_api_search(query: str) -> str | None:
    """استعلام دقیق نرخ روز دلار، تتر، یورو و ارزهای بازار از ۲ منبع معتبر (TGJU + کانال @ba_z1)"""
    q = query.lower()

    currency_defs = {
        "دلار": ("USD", "دلار آمریکا (بازار آزاد)", "$", "💵"),
        "تتر": ("USDT", "تتر (USDT / دلار دیجیتال)", "₮", "⚡"),
        "usdt": ("USDT", "تتر (USDT / دلار دیجیتال)", "₮", "⚡"),
        "یورو": ("EUR", "یورو اروپا", "€", "💶"),
        "پوند": ("GBP", "پوند انگلیس", "£", "💷"),
        "درهم": ("AED", "درهم امارات", "د.إ", "🇦🇪"),
        "لیر": ("TRY", "لیر ترکیه", "₺", "🇹🇷"),
        "یوان": ("CNY", "یوان چین", "¥", "🇨🇳"),
        "کانادا": ("CAD", "دلار کانادا", "C$", "🇨🇦"),
        "استرالیا": ("AUD", "دلار استرالیا", "A$", "🇦🇺"),
        "دینار کویت": ("KWD", "دینار کویت", "KWD", "🇰🇼"),
        "دینار عراق": ("IQD", "دینار عراق", "IQD", "🇮🇶"),
    }

    target_code = None
    target_name = None
    target_symbol = ""
    target_icon = "💵"

    for keyword, (code, name, symbol, icon) in currency_defs.items():
        if keyword in q:
            target_code = code
            target_name = name
            target_symbol = symbol
            target_icon = icon
            break

    # پیش‌فرض در صورت گفتن «ارز» یا «قیمت ارز»: دلار آمریکا
    if not target_code:
        target_code = "USD"
        target_name = "دلار آمریکا (بازار آزاد)"
        target_symbol = "$"
        target_icon = "💵"

    rates = await _get_live_market_rates()
    if not rates:
        return None

    target_data = rates.get(target_code)
    baz1 = rates.get("BAZ1", {})

    if not target_data and target_code == "USD" and baz1.get("usd_deal"):
        target_data = {
            "price": baz1["usd_deal"],
            "price_rial": baz1["usd_deal"] * 10,
            "high": baz1.get("usd_sell", baz1["usd_deal"]),
            "low": baz1.get("usd_buy", baz1["usd_deal"]),
        }

    if not target_data and target_code == "USD":
        target_data = rates.get("USDT")

    if not target_data:
        return None

    price_toman = target_data["price"]
    price_rial = target_data.get("price_rial", price_toman * 10)
    high_toman = target_data.get("high", price_toman)
    low_toman = target_data.get("low", price_toman)

    from bot.utils.helpers import get_persian_date_info
    date_info = get_persian_date_info()

    p_fa = to_persian_digits(f"{price_toman:,.0f}")
    r_fa = to_persian_digits(f"{price_rial:,.0f}")

    lines = []

    # حالت ۱: استعلام دلار آمریکا (نمایش ۲ منبع بازار به همراه تتر)
    if target_code == "USD":
        b_deal = baz1.get("usd_deal", 0)
        b_buy = baz1.get("usd_buy", 0)
        b_sell = baz1.get("usd_sell", 0)

        if b_deal and price_toman:
            # هر دو منبع موجود هستند -> مقایسه ۲ منبع
            lines.append("💵 <b>قیمت روز دلار آمریکا (مقایسه ۲ مرجع معتبر بازار):</b>")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━\n")
            lines.append("<blockquote>")
            lines.append(f"🏛 <b>منبع ۱: شبکه طلا و ارز (TGJU - رسمی):</b>\n   نرخ صرافی‌ها: <b>{p_fa}</b> تومان  <code>({r_fa} ریال)</code>\n")
            bd_fa = to_persian_digits(f"{b_deal:,.0f}")
            lines.append(f"⛳️ <b>منبع ۲: بازار فردایی تهران (@ba_z1):</b>\n   نرخ معامله: <b>{bd_fa}</b> تومان")
            if b_buy and b_sell:
                bb_fa = to_persian_digits(f"{b_buy:,.0f}")
                bs_fa = to_persian_digits(f"{b_sell:,.0f}")
                lines.append(f"   خرید: {bb_fa} | فروش: {bs_fa} تومان")
            lines.append("</blockquote>\n")
        elif b_deal:
            # فقط منبع بازار فردایی
            bd_fa = to_persian_digits(f"{b_deal:,.0f}")
            lines.append("💵 <b>قیمت روز دلار آمریکا (بازار فردایی تهران):</b>")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━\n")
            lines.append("<blockquote>")
            lines.append(f"⛳️ <b>نرخ معامله:</b> <b>{bd_fa}</b> تومان\n")
            if b_buy and b_sell:
                bb_fa = to_persian_digits(f"{b_buy:,.0f}")
                bs_fa = to_persian_digits(f"{b_sell:,.0f}")
                lines.append(f"🔹 خرید: {bb_fa} تومان | ⭕️ فروش: {bs_fa} تومان")
            lines.append("</blockquote>\n")
        else:
            # فقط منبع TGJU
            lines.append("💵 <b>قیمت روز دلار آمریکا (بازار آزاد):</b>")
            lines.append("━━━━━━━━━━━━━━━━━━━━━━━━\n")
            lines.append("<blockquote>")
            lines.append(f"📊 <b>نرخ معامله در بازار:</b>\n   <b>{p_fa}</b> تومان  <code>({r_fa} ریال)</code>")
            if high_toman and low_toman and high_toman != low_toman:
                h_fa = to_persian_digits(f"{high_toman:,.0f}")
                l_fa = to_persian_digits(f"{low_toman:,.0f}")
                lines.append(f"\n📈 دامنه نوسان: کف {l_fa} | سقف {h_fa} تومان")
            lines.append("</blockquote>\n")

        # اضافه کردن شاخص تتر آنلاین
        if "USDT" in rates:
            usdt_p = rates["USDT"]["price"]
            ut_fa = to_persian_digits(f"{usdt_p:,.0f}")
            lines.append(f"⚡ <b>دلار دیجیتال (تتر USDT):</b>\n   <b>{ut_fa}</b> تومان <i>(صرافی‌های آنلاین / والکس)</i>\n")

    # حالت ۲: استعلام تتر (USDT)
    elif target_code == "USDT":
        lines.append(f"{target_icon} <b>قیمت روز {target_name}:</b>")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━\n")
        lines.append("<blockquote>")
        lines.append(f"⚡ <b>نرخ آنلاین صرافی‌ها:</b>\n   <b>{p_fa}</b> تومان  <code>({r_fa} ریال)</code>\n")
        if baz1.get("usdt"):
            bu_fa = to_persian_digits(f"{baz1['usdt']:,.0f}")
            lines.append(f"⛳️ <b>نرخ تتر در بازار تهران (@ba_z1):</b>\n   <b>{bu_fa}</b> تومان")
        lines.append("</blockquote>\n")

        # مقایسه با اسکناس
        usd_p = baz1.get("usd_deal") or rates.get("USD", {}).get("price", 0)
        if usd_p:
            u_fa = to_persian_digits(f"{usd_p:,.0f}")
            lines.append(f"💵 <b>دلار اسکناس (بازار فردوسی/تهران):</b>\n   <b>{u_fa}</b> تومان\n")

    # حالت ۳: سایر ارزها (یورو، پوند، درهم و...)
    else:
        lines.append(f"{target_icon} <b>قیمت روز {target_name}:</b>")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━\n")
        lines.append("<blockquote>")
        lines.append(f"📊 <b>نرخ معامله در بازار:</b>\n   <b>{p_fa}</b> تومان  <code>({r_fa} ریال)</code>\n")
        if high_toman and low_toman and high_toman != low_toman:
            h_fa = to_persian_digits(f"{high_toman:,.0f}")
            l_fa = to_persian_digits(f"{low_toman:,.0f}")
            lines.append(f"📈 <b>دامنه نوسان امروز:</b>\n   کف: {l_fa} | سقف: {h_fa} تومان")
        lines.append("</blockquote>\n")

    # سایر ارزهای مهم بازار
    other_items = []
    other_codes = [c for c in ["USD", "USDT", "EUR", "AED", "GBP", "TRY"] if c != target_code][:4]
    code_labels = {
        "USD": ("💵 دلار", "تومان"),
        "USDT": ("⚡ تتر", "تومان"),
        "EUR": ("💶 یورو", "تومان"),
        "AED": ("🇦🇪 درهم", "تومان"),
        "GBP": ("💷 پوند", "تومان"),
        "TRY": ("🇹🇷 لیر", "تومان"),
    }
    for c in other_codes:
        p = 0
        if c == "USD" and baz1.get("usd_deal"):
            p = baz1["usd_deal"]
        elif c in rates:
            p = rates[c]["price"]
        if p:
            p_formatted = to_persian_digits(f"{p:,.0f}")
            lbl, cur_unit = code_labels.get(c, (c, "تومان"))
            other_items.append(f"   {lbl}: <b>{p_formatted}</b> {cur_unit}")

    if other_items:
        lines.append("📊 <b>سایر شاخص‌های مهم بازار:</b>")
        lines.extend(other_items)
        lines.append("")

    t_fa = to_persian_digits(date_info["time_str"])
    lines.append(f"🗓 <i>تاریخ: {date_info['date_fa_full']} — ساعت {t_fa}</i>")

    sources = []
    if "USD" in rates or "EUR" in rates:
        sources.append("TGJU رسمی")
    if baz1:
        sources.append("کانال بازار فردایی (@ba_z1)")
    if "USDT" in rates:
        sources.append("والکس")
    source_str = " + ".join(sources) if sources else "TGJU و بازار آزاد"
    lines.append(f"🌐 <i>منابع: {source_str}</i>")

    return "\n".join(lines)


# ─── خواندن قیمت ارز از کانال تلگرام (@Price33) به عنوان پشتیبان ────────────

async def _read_channel_currency(channel_username: str = "Price33") -> dict | None:
    """خواندن آخرین قیمت ارز از کانال تلگرام با اسکرپر وب به عنوان فال‌بک"""
    import httpx
    import re

    try:
        url = f"https://t.me/s/{channel_username}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"Channel scrape failed: HTTP {resp.status_code}")
                return None

            html = resp.text
            messages = re.findall(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', html, re.DOTALL)
            if not messages:
                logger.warning("No messages found in channel")
                return None

            last_msg = messages[-1]

            # تبدیل اعداد عربی/فارسی به انگلیسی
            arabic_nums = "٠١٢٣٤٥٦٧٨٩"
            persian_nums = "۰۱۲۳۴۵۶۷۸۹"
            for i, (ar, fa) in enumerate(zip(arabic_nums, persian_nums)):
                last_msg = last_msg.replace(ar, str(i)).replace(fa, str(i))

            last_msg = re.sub(r'<[^>]+>', '', last_msg)

            patterns = [
                (r"(?:يورو|یورو)[:\s]*(\d[\d,]+)", "EUR"),
                (r"(?:دلار|دلار آمريکا|دلار آمریکا)[:\s]*(\d[\d,]+)", "USD"),
                (r"(?:تتر|USDT)[:\s]*(\d[\d,]+)", "USDT"),
                (r"(?:پوند|پوند انگليس|پوند انگلیس)[:\s]*(\d[\d,]+)", "GBP"),
                (r"(?:درهم|درهم امارات)[:\s]*(\d[\d,]+)", "AED"),
                (r"(?:يوآن|یوان|يوآن چين|یوان چین)[:\s]*(\d[\d,]+)", "CNY"),
                (r"(?:لير|لير ترکيه|لیر ترکیه)[:\s]*(\d[\d,]+)", "TRY"),
                (r"(?:دینار|دینار کویت)[:\s]*(\d[\d,]+)", "KWD"),
                (r"طلا[يی]\s*۱۸\s*ع[يی]ار\s*هر\s*گرم\s*[:：]?\s*(\d[\d,]+)", "GOLD18"),
                (r"طلا[يی]\s*18\s*ع[يی]ار\s*هر\s*گرم\s*[:：]?\s*(\d[\d,]+)", "GOLD18"),
                (r"سکه\s*امام[يی]\s*[:：]?\s*(\d[\d,]+)", "COIN_EMAMI"),
                (r"سکه\s*امامی\s*[:：]?\s*(\d[\d,]+)", "COIN_EMAMI"),
                (r"سکه\s*بهار\s*ازاد[يی]\s*[:：]?\s*(\d[\d,]+)", "COIN_BAHAR"),
                (r"سکه\s*بهار\s*آزاد[يی]\s*[:：]?\s*(\d[\d,]+)", "COIN_BAHAR"),
                (r"نیم\s*سکه\s*[:：]?\s*(\d[\d,]+)", "COIN_HALF"),
                (r"ربع\s*سکه\s*[:：]?\s*(\d[\d,]+)", "COIN_QUARTER"),
                (r"سکه\s*گرم[يی]\s*[:：]?\s*(\d[\d,]+)", "COIN_GRAMI"),
            ]

            prices = {}
            for pattern, code in patterns:
                match = re.search(pattern, last_msg)
                if match:
                    price_str = match.group(1).replace(",", "")
                    try:
                        prices[code] = int(price_str) * 10
                    except ValueError:
                        pass

            return prices if prices else None
    except Exception as e:
        logger.warning(f"channel currency read failed: {e}")
    return None


# ─── استعلام قیمت کالا از ترب (Torob API) ───────────────────────────────────

def _clean_product_query(query: str) -> str:
    """پاکسازی عبارت جستجوی کالا و حذف کلمات اضافه"""
    import re
    q = query.strip()
    q = re.sub(r"^/(price|gheymat|gheimat|نرخ|قیمت)\s*", "", q, flags=re.IGNORECASE)
    stopwords = [
        "قیمت", "چنده", "چند", "نرخ", "چند تومنه", "چندتومنه", "چقدره", "چقدر است",
        "استعلام", "لطفا", "لطفاً", "میخوام", "می‌خوام", "سایت", "ترب", "دیجیکالا",
        "دیجی کالا", "امروز", "الان", "بازار", "جدید", "آخرین"
    ]
    for _ in range(2):
        for w in stopwords:
            q = re.sub(r"(^|\s)" + re.escape(w) + r"(\s|$)", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q or query.strip()


async def _product_price_search(query: str) -> dict | None:
    """
    استعلام هوشمند قیمت کالا (جاروبرقی، موبایل، لپ‌تاپ، لوازم خانگی و...) از ترب
    """
    import httpx
    import urllib.parse

    clean_q = _clean_product_query(query)
    if len(clean_q) < 2:
        return None

    enc = urllib.parse.quote(clean_q)
    url = f"https://api.torob.com/v4/base-product/search/?sort=popularity&page=0&size=4&q={enc}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        async with httpx.AsyncClient(timeout=10, headers=headers, follow_redirects=True) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                logger.warning(f"Torob search failed: HTTP {resp.status_code}")
                return None

            data = resp.json()
            results = data.get("results", [])
            if not results:
                return None

            import html as _html

            safe_q = _html.escape(clean_q)
            lines = [
                f"🛍️ <b>استعلام قیمت در بازار (ترب): {safe_q}</b>",
                "━━━━━━━━━━━━━━━━━━━━━━━━",
                ""
            ]

            products = []
            for i, item in enumerate(results[:4], 1):
                raw_name = item.get("name1") or item.get("name2") or clean_q
                raw_price = item.get("price_text") or (f"{item['price']:,} تومان" if item.get("price") else "نامشخص")
                raw_shop = item.get("shop_text") or "فروشگاه‌های معتبر"
                item_url = "https://torob.com" + item.get("web_client_absolute_url", "")

                safe_name = _html.escape(str(raw_name))
                safe_price = _html.escape(str(raw_price))
                safe_shop = _html.escape(str(raw_shop))
                safe_url = _html.escape(str(item_url))

                lines.append(f"<b>{i}. {safe_name}</b>")
                lines.append(f"💰 قیمت: <b>{safe_price}</b>")
                lines.append(f"🏪 فروشگاه‌ها: <i>{safe_shop}</i>")
                lines.append(f"🔗 <a href=\"{safe_url}\">مشاهده و خرید در ترب</a>\n")

                products.append({
                    "name": raw_name,
                    "price_text": raw_price,
                    "shop": raw_shop,
                    "url": item_url,
                })

            lines.append("💡 <i>قیمت‌ها لحظه‌ای و استخراج‌شده از بین معتبرترین فروشگاه‌های آنلاین کشور هستند.</i>")
            search_web_url = f"https://torob.com/search/?query={enc}"

            return {
                "text": "\n".join(lines),
                "products": products,
                "query": clean_q,
                "search_url": search_web_url,
            }
    except Exception as e:
        logger.warning(f"Torob product search error: {e}")
        return None


# ─── استعلام قیمت رمزارزها (Binance API) ────────────────────────────────────

_CRYPTO_MAP = {
    "بیت کوین": "BTC", "بیتکوین": "BTC", "btc": "BTC", "bitcoin": "BTC",
    "اتریوم": "ETH", "eth": "ETH", "ethereum": "ETH",
    "سولانا": "SOL", "sol": "SOL", "solana": "SOL",
    "تون": "TON", "تون کوین": "TON", "ton": "TON", "toncoin": "TON",
    "دوج": "DOGE", "دوج کوین": "DOGE", "doge": "DOGE", "dogecoin": "DOGE",
    "ترون": "TRX", "trx": "TRX", "tron": "TRX",
    "ریپل": "XRP", "xrp": "XRP", "ripple": "XRP",
    "شیبا": "SHIB", "shib": "SHIB", "shiba": "SHIB",
    "بایننس کوین": "BNB", "bnb": "BNB",
    "کاردانو": "ADA", "ada": "ADA", "cardano": "ADA",
    "نات کوین": "NOT", "not": "NOT",
    "پپه": "PEPE", "pepe": "PEPE",
}

_CRYPTO_NAMES = {
    "BTC": "بیت‌کوین (BTC)",
    "ETH": "اتریوم (ETH)",
    "SOL": "سولانا (SOL)",
    "TON": "تون‌کوین (TON)",
    "DOGE": "دوج‌کوین (DOGE)",
    "TRX": "ترون (TRX)",
    "XRP": "ریپل (XRP)",
    "SHIB": "شیبا اینو (SHIB)",
    "BNB": "بایننس کوین (BNB)",
    "ADA": "کاردانو (ADA)",
    "NOT": "نات کوین (NOT)",
    "PEPE": "پپه (PEPE)",
}

async def _crypto_api_search(query: str) -> str | None:
    """
    دریافت قیمت لحظه‌ای رمزارزها از بایننس به دلار و محاسبه معادل تومانی
    """
    import httpx
    import json
    q = query.lower().strip()

    target_sym = None
    for kw, sym in _CRYPTO_MAP.items():
        if kw in q:
            target_sym = sym
            break

    if target_sym:
        symbols = [f"{target_sym}USDT"]
    else:
        if not any(w in q for w in ["کریپتو", "ارز دیجیتال", "ارزدیجیتال", "crypto"]):
            return None
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "TONUSDT", "DOGEUSDT", "TRXUSDT", "XRPUSDT"]

    try:
        usdt_toman = 0
        try:
            channel_prices = await _read_channel_currency()
            if channel_prices and "USDT" in channel_prices:
                usdt_toman = channel_prices["USDT"] / 10
            elif channel_prices and "USD" in channel_prices:
                usdt_toman = channel_prices["USD"] / 10
        except Exception:
            pass

        async with httpx.AsyncClient(timeout=8, headers={"User-Agent": "Mozilla/5.0"}) as client:
            sym_param = json.dumps(symbols, separators=(',', ':'))
            resp = await client.get(
                "https://api.binance.com/api/v3/ticker/24hr",
                params={"symbols": sym_param},
            )
            if resp.status_code != 200:
                logger.warning(f"Binance API status: {resp.status_code}")
                return None

            items = resp.json()
            if not items:
                return None

            lines = [
                "🪙 <b>قیمت لحظه‌ای بازار ارزهای دیجیتال (Crypto):</b>",
                "━━━━━━━━━━━━━━━━━━━━━━━━",
                ""
            ]

            for it in items:
                raw_sym = it.get("symbol", "").replace("USDT", "")
                name = _CRYPTO_NAMES.get(raw_sym, raw_sym)
                price = float(it.get("lastPrice", 0))
                change = float(it.get("priceChangePercent", 0))
                high = float(it.get("highPrice", 0))
                low = float(it.get("lowPrice", 0))

                arrow = "🟢" if change >= 0 else "🔴"
                sign = "+" if change >= 0 else ""

                price_str = f"${price:,.4f}" if price < 1 else f"${price:,.2f}"

                toman_str = ""
                if usdt_toman > 0:
                    toman_val = price * usdt_toman
                    if toman_val >= 1000:
                        toman_str = f" ┃ 🇮🇷 ~<code>{toman_val:,.0f} تومان</code>"
                    else:
                        toman_str = f" ┃ 🇮🇷 ~<code>{toman_val:,.1f} تومان</code>"

                lines.append(f"{arrow} <b>{name}</b>")
                lines.append(f"   💵 قیمت جهانی: <b>{price_str}</b>{toman_str}")
                lines.append(f"   📊 تغییر ۲۴ ساعت: <code>{sign}{change:.2f}%</code> (کف: {low:,.2f} | سقف: {high:,.2f})\n")

            if usdt_toman > 0:
                lines.append(f"💵 <i>نرخ مبنای تتر: {usdt_toman:,.0f} تومان</i>")
            lines.append("📅 <i>اطلاعات زنده از صرافی بین‌المللی بایننس</i>")

            return "\n".join(lines)
    except Exception as e:
        logger.warning(f"Crypto API search failed: {e}")
        return None


# ─── موتور جامع استعلام قیمت (کالا، طلا، ارز، کریپتو) ────────────────────────

async def search_price_all(query: str) -> dict:
    """
    موتور جامع استعلام قیمت:
    تشخیص هوشمند نوع استعلام (کالا/محصول، طلا و سکه، ارز، رمزارز)
    """
    raw_q = query.strip()
    clean_q = _clean_product_query(raw_q)
    lower_q = raw_q.lower()

    # ۱. اگر خالی باشد -> منوی اصلی
    if not clean_q or len(clean_q) < 2:
        return {
            "type": "empty",
            "text": (
                "🏷️ <b>مرکز هوشمند استعلام قیمت و نرخ لحظه‌ای</b>\n\n"
                "<blockquote>\n"
                "💡 برای دریافت سریع‌ترین قیمت‌ها، نام محصول، رمزارز یا ارز را بعد از دستور بنویسید:\n\n"
                "🛍️ <b>کالاها و محصولات (ترب و فروشگاه‌های آنلاین):</b>\n"
                "• <code>/price جاروبرقی بوش</code>\n"
                "• <code>/price آیفون 15</code>\n"
                "• <code>/price پلی استیشن 5</code>\n"
                "• <code>/price لپ‌تاپ ایسوس</code>\n\n"
                "🪙 <b>رمزارزها، طلا و ارزها:</b>\n"
                "• <code>/price دلار</code> یا <code>/price تتر</code>\n"
                "• <code>/price طلا</code> یا <code>/price سکه</code>\n"
                "• <code>/price بیت کوین</code> یا <code>/price ton</code>\n"
                "</blockquote>\n\n"
                "👇 <i>یا یکی از گزینه‌های آماده زیر را لمس کنید:</i>"
            ),
        }

    # ۱.۵. اگر سوال مشاوره‌ای یا مقایسه‌ای است (مثل: «جاروبرقی کیسه‌ای بهتره یا مخزن‌دار؟») -> پاسخ با هوش مصنوعی
    if is_advice_or_comparison_question(raw_q):
        ai_resp = await answer_question(raw_q, chat_id=0)
        return {
            "type": "advice",
            "text": ai_resp.get("answer", ""),
            "query": raw_q,
        }

    # ۲. چک رمزارزها
    is_crypto = any(k in lower_q for k in _CRYPTO_MAP.keys()) or any(w in lower_q for w in ["کریپتو", "ارز دیجیتال", "ارزدیجیتال", "crypto"])
    if is_crypto:
        crypto_res = await _crypto_api_search(raw_q)
        if crypto_res:
            return {"type": "crypto", "text": crypto_res, "query": raw_q}

    # ۳. چک طلا و سکه
    is_gold = any(k in raw_q for k in _GOLD_KEYWORDS)
    if is_gold:
        gold_res = await _gold_api_search(raw_q)
        if gold_res:
            return {"type": "gold", "text": gold_res, "query": raw_q}

    # ۴. چک ارزهای رسمی و آزاد (دلار، یورو، پوند و...)
    currency_keywords = ["دلار", "تتر", "usdt", "یورو", "پوند", "لیر", "درهم", "یوان", "ین", "ارز", "نرخ ارز"]
    if any(k in lower_q for k in currency_keywords):
        curr_res = await _currency_api_search(raw_q)
        if curr_res:
            return {"type": "currency", "text": curr_res, "query": raw_q}

    # ۵. استعلام کالا و محصولات بازار از ترب (جاروبرقی، گوشی، لپ‌تاپ و...)
    prod_res = await _product_price_search(raw_q)
    if prod_res:
        return {
            "type": "product",
            "text": prod_res["text"],
            "products": prod_res["products"],
            "query": prod_res["query"],
            "search_url": prod_res["search_url"],
        }

    # ۶. تلاش نهایی با موتور جست‌وجوی وب
    web_res = await search_web_fallback(f"قیمت {clean_q}")
    if web_res:
        return {"type": "web", "text": web_res, "query": raw_q}

    return {
        "type": "none",
        "text": f"❌ متأسفانه قیمت یا اطلاعاتی برای «<b>{clean_q}</b>» یافت نشد.\nلطفاً نام دقیق‌تر برند یا مدل کالا را وارد کنید.",
        "query": raw_q,
    }


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

# ─── Rate limiter برای جستجو ─────────────────────────────────────────────────

import time as _time
_last_search_time = 0.0
_SEARCH_MIN_INTERVAL = 2.0  # حداقل ۲ ثانیه بین هر درخواست جستجو

async def _rate_limit_search():
    """جلوگیری از rate limit شدن"""
    global _last_search_time
    now = _time.time()
    elapsed = now - _last_search_time
    if elapsed < _SEARCH_MIN_INTERVAL:
        await asyncio.sleep(_SEARCH_MIN_INTERVAL - elapsed)
    _last_search_time = _time.time()


async def _brave_search(query: str, max_results: int = 5) -> list[dict]:
    """استخراج نتایج از Brave Search"""
    import httpx
    import re as _re
    await _rate_limit_search()
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
            
            # Brave: استخراج همه لینک‌های خارجی
            a_tags = _re.findall(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', html, _re.DOTALL)
            
            for href, text in a_tags:
                text_clean = _re.sub(r"<[^>]+>", "", text).strip()
                if (text_clean and len(text_clean) > 15 
                    and href.startswith("http") 
                    and "brave.com" not in href
                    and "youtube.com" not in href
                    and "facebook.com" not in href
                    and "twitter.com" not in href):
                    results.append({
                        "title": text_clean[:100],
                        "url": href[:200],
                        "snippet": ""
                    })
                    if len(results) >= max_results:
                        break
            
            logger.info(f"Brave: {len(results)} results")
    except Exception as e:
        logger.warning(f"Brave search failed: {e}")
    return results


# ─── Startpage Search ─────────────────────────────────────────────────────────

async def _startpage_search(query: str, max_results: int = 5) -> list[dict]:
    """استخراج نتایج از Startpage"""
    import httpx
    import re as _re
    await _rate_limit_search()
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
            
            # اگه CAPTCHA اومد، رد شو
            if "captcha" in resp.text.lower() or resp.status_code == 303:
                logger.info("Startpage: CAPTCHA detected, skipping")
                return []
            
            if resp.status_code != 200:
                return []
            
            html = resp.text
            
            # استخراج همه لینک‌های خارجی
            a_tags = _re.findall(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', html, _re.DOTALL)
            
            for href, text in a_tags:
                text_clean = _re.sub(r"<[^>]+>", "", text).strip()
                if (text_clean and len(text_clean) > 15 
                    and href.startswith("http") 
                    and "startpage.com" not in href
                    and "google.com" not in href):
                    results.append({
                        "title": text_clean[:100],
                        "url": href[:200],
                        "snippet": ""
                    })
                    if len(results) >= max_results:
                        break
            
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
