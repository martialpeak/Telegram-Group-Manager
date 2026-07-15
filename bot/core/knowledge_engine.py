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

# کلماتی که نشون می‌ده سوال به اطلاعات لحظه‌ای/واقعی نیاز داره
# (AI نمی‌تونه جواب بده، حتماً باید سرچ بشه)
_REALTIME_PATTERNS = [
    # آب‌وهوا
    "هواشناسی", "آب و هوا", "آب‌وهوا", "دمای هوا", "طقس", "باران", "برف",
    "weather",
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
    weather_keywords = ["هواشناسی", "آب و هوا", "دما", "باران", "برف", "آفتابی", "ابری", "دمای", "天气"]
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
    currency_keywords = ["دلار", "تتر", "usdt", "یورو", "پوند", "لیر", "درهم", "یوان", "ین", "ارز", "نرخ ارز", "قیمت"]
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

    # ۲-ب. اگه DDG کار نکرد (احتمالاً فیلتر)، Google search رو امتحان کن
    if not snippets:
        try:
            google_snippets = await _google_search(question, WEB_SEARCH_MAX_RESULTS)
            snippets.extend(google_snippets)
            logger.info(f"Google: {len(google_snippets)} snippets")
        except Exception as e:
            logger.warning(f"google search failed: {e}")

    # ۲-ج. اگه Google هم کار نکرد، Wikipedia API رو امتحان کن
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


# ─── Currency API (قیمت لحظه‌ای ارز) ─────────────────────────────────────────

# ─── Weather API ────────────────────────────────────────────────────────────

async def _weather_search(question: str) -> str | None:
    """دریافت اطلاعات هواشناسی از wttr.in"""
    import httpx
    import re as _re_w

    # استخراج نام شهر
    city_map = {
        "تهران": "Tehran", "مشهد": "Mashhad", "اصفهان": "Isfahan",
        "شیراز": "Shiraz", "تبریز": "Tabriz", "اهواز": "Ahvaz",
        "کرمان": "Kerman", "قم": "Qom", "کرج": "Karaj",
        "زنجان": "Zanjan", "اردبیل": "Ardabil", "یزد": "Yazd",
        "بوشهر": "Bushehr", "چابهار": "Chabahar", "بندرعباس": "Bandar-Abbas",
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
                # گرفتن قیمت USDT از CoinGecko (دلاری)
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
                
                # گرفتن نرخ آزاد دلار (بازار)
                try:
                    fm_resp = await client.get(
                        "https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/usd.json",
                    )
                    if fm_resp.status_code == 200:
                        fm_data = fm_resp.json()
                        free_market_irr = fm_data.get("usd", {}).get("irr", usd_to_irr)
                    else:
                        free_market_irr = usd_to_irr
                except Exception:
                    free_market_irr = usd_to_irr
                
                # قیمت تقریبی بازار (نرخ آزاد + حاشیه بازار ایران)
                # به دلیل تحریم‌ها و محدودیت‌های ارزی، قیمت بازار ~35% بالاتر از نرخ آزاد بین‌المللی است
                MARKET_PREMIUM = 1.35
                market_irr = free_market_irr * MARKET_PREMIUM * usdt_usd
                market_toman = market_irr / 10
                
                result = (
                    f"💰 قیمت {target_name} ({target_symbol})\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"💵 قیمت جهانی:\n"
                    f"   1 USDT = {usdt_usd:.4f} USD\n\n"
                    f"📊 قیمت بازار (تقریبی):\n"
                    f"   {market_irr:,.0f} ریال\n"
                    f"   ({market_toman:,.0f} تومان)\n\n"
                    f"🏦 نرخ رسمی (بانک مرکزی):\n"
                    f"   {usd_to_irr:,.0f} ریال ({usd_to_irr/10:,.0f} تومان)\n\n"
                    f"📅 تاریخ: {date}\n"
                    f"📊 منبع: CoinGecko + Currency API\n\n"
                    f"⚠️ قیمت تقریبی است. برای قیمت دقیق، صرافی‌ها رو چک کنید."
                )
                return result
            else:
                # ارز رسمی
                target_to_usd = rates.get(target_code, 1)
                target_to_irr = usd_to_irr / target_to_usd if target_code != "USD" else usd_to_irr
                
                toman = target_to_irr / 10
                eur_to_irr = usd_to_irr / rates.get("EUR", 1)
                gbp_to_irr = usd_to_irr / rates.get("GBP", 1)
                
                result = (
                    f"💰 قیمت {target_name} ({target_symbol})\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                    f"💵 نرخ رسمی:\n"
                    f"   {target_to_irr:,.0f} ریال\n"
                    f"   ({toman:,.0f} تومان)\n\n"
                    f"📊 سایر ارزها:\n"
                    f"   💵 دلار: {usd_to_irr:,.0f} ریال\n"
                    f"   💶 یورو: {eur_to_irr:,.0f} ریال\n"
                    f"   💷 پوند: {gbp_to_irr:,.0f} ریال\n\n"
                    f"📅 تاریخ: {date}\n"
                    f"📊 منبع: Exchange Rate API\n\n"
                    f"💡 نرخ بازار آزاد ممکنه متفاوت باشه."
                )
                return result
    except Exception as e:
        logger.warning(f"currency API failed: {e}")
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

async def _google_search(query: str, max_results: int = 3) -> list[str]:
    """استخراج snippet از Google Search"""
    import httpx
    import re as _re
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        async with httpx.AsyncClient(timeout=15, headers=headers, follow_redirects=True) as client:
            resp = await client.get(
                "https://www.google.com/search",
                params={"q": query, "hl": "fa", "num": max_results},
            )
            logger.info(f"Google search: HTTP {resp.status_code}")
            if resp.status_code != 200:
                return []
            snippets = []
            # Multiple regex patterns for different Google layouts
            patterns = [
                r'<div[^>]*class="BNeawe[^"]*"[^>]*>(.*?)</div>',
                r'<div[^>]*class="[^"]*VwiC3b[^"]*"[^>]*>(.*?)</div>',
                r'<span[^>]*class="[^"]*aCOpRe[^"]*"[^>]*>(.*?)</span>',
                r'<div[^>]*data-sncf="[^"]*"[^>]*>(.*?)</div>',
            ]
            for pattern in patterns:
                if snippets:
                    break
                matches = _re.findall(pattern, resp.text, _re.DOTALL)
                for m in matches[:max_results]:
                    clean = _re.sub(r"<[^>]+>", "", m).strip()
                    if clean and len(clean) > 30 and not clean.startswith("http"):
                        snippets.append(clean[:300])
            # final fallback
            if not snippets:
                matches = _re.findall(
                    r'<span[^>]*>(.*?)</span>',
                    resp.text,
                    _re.DOTALL,
                )
                for m in matches[:max_results * 3]:
                    clean = _re.sub(r"<[^>]+>", "", m).strip()
                    if clean and len(clean) > 50 and not clean.startswith("http"):
                        snippets.append(clean[:300])
            return snippets[:max_results]
    except Exception as e:
        logger.warning(f"Google search failed: {e}")
        return []


# ─── Bing Search (وقتی DDG و Google فیلترن) ──────────────────────────────────

async def _bing_search(query: str, max_results: int = 3) -> list[str]:
    """استخراج snippet از Bing Search"""
    import httpx
    import re as _re
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        async with httpx.AsyncClient(timeout=15, headers=headers, follow_redirects=True) as client:
            resp = await client.get(
                "https://www.bing.com/search",
                params={"q": query, "count": max_results},
            )
            logger.info(f"Bing search: HTTP {resp.status_code}")
            if resp.status_code != 200:
                return []
            snippets = []
            matches = _re.findall(
                r'<p[^>]*>(.*?)</p>',
                resp.text,
                _re.DOTALL,
            )
            for m in matches[:max_results * 2]:
                clean = _re.sub(r"<[^>]+>", "", m).strip()
                if clean and len(clean) > 50 and not clean.startswith("http"):
                    snippets.append(clean[:300])
            if not snippets:
                matches = _re.findall(
                    r'<div[^>]*class="[^"]*b_caption[^"]*"[^>]*>(.*?)</div>',
                    resp.text,
                    _re.DOTALL,
                )
                for m in matches[:max_results]:
                    clean = _re.sub(r"<[^>]+>", "", m).strip()
                    if clean and len(clean) > 30:
                        snippets.append(clean[:300])
            return snippets[:max_results]
    except Exception as e:
        logger.warning(f"Bing search failed: {e}")
        return []


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
        try:
            answer = await _generate_groq_general(prompt)
            if answer:
                return "🌐 (بر اساس جست‌وجو در وب)\n\n" + answer
        except Exception as e:
            logger.warning(f"Groq summarize failed: {e}")
    # fallback Gemini
    if _gemini_model:
        try:
            answer = await _generate_gemini_general(prompt)
            if answer:
                return "🌐 (بر اساس جست‌وجو در وب)\n\n" + answer
        except Exception as e:
            logger.warning(f"Gemini summarize failed: {e}")
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
