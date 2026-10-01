"""
موتور پیشرفته و دوگانه استخراج متن از تصویر (OCR Engine)
پشتیبانی ترکیبی از:
۱. Groq Vision (مدل‌های فوق‌سریع Qwen 3.8 27B و Llama 4 Scout)
۲. Google Gemini Vision (مدل‌های پردقت Gemini 2.0 Flash و 1.5 Flash)
۳. موتور آفلاین و محلی (Tesseract فارسی و RapidOCR ONNX)
"""

import asyncio
import base64
import html
import io
import logging
import time
from typing import Optional, Tuple

try:
    from PIL import Image, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
    Image = None
    ImageOps = None

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import GEMINI_API_KEY, GEMINI_MODEL, GROQ_API_KEY, AI_PROVIDER
try:
    from config import GROQ_VISION_MODEL
except ImportError:
    GROQ_VISION_MODEL = "qwen/qwen3.8-27b"

from bot.utils.helpers import to_persian_digits

logger = logging.getLogger(__name__)

# کش موقت تصاویر برای کلیک روی دکمه‌های اینلاین OCR (حداکثر ۱۰۰ تصویر اخیر)
_ocr_image_cache: dict[str, bytes] = {}


def cache_ocr_image(key: str, data: bytes):
    if len(_ocr_image_cache) > 100:
        try:
            _ocr_image_cache.pop(next(iter(_ocr_image_cache)))
        except Exception:
            pass
    _ocr_image_cache[key] = data


def get_cached_ocr_image(key: str) -> Optional[bytes]:
    return _ocr_image_cache.get(key)


def _detect_mime_type(data: bytes) -> str:
    """تشخیص نوع فایل تصویر بر اساس بایت‌های هدر"""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    elif data.startswith(b"GIF8"):
        return "image/gif"
    elif data.startswith(b"RIFF") and b"WEBP" in data[:16]:
        return "image/webp"
    return "image/jpeg"


# موتور محلی RapidOCR به صورت lazy load
_rapidocr_engine = None


def _get_local_engine():
    global _rapidocr_engine
    if _rapidocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _rapidocr_engine = RapidOCR()
            logger.info("✅ موتور محلی RapidOCR با موفقیت بارگذاری شد.")
        except Exception as e:
            logger.warning(f"بارگذاری RapidOCR ناموفق بود: {e}")
            _rapidocr_engine = False
    return _rapidocr_engine if _rapidocr_engine is not False else None


def preprocess_image(image_bytes: bytes, max_dimension: int = 2560) -> bytes:
    """بهینه‌سازی ابعاد، جهت (EXIF) و فرمت تصویر برای پردازش سریع و دقیق"""
    if not HAS_PIL or not Image or not ImageOps:
        return image_bytes
    try:
        img = Image.open(io.BytesIO(image_bytes))
        # تصحیح جهت چرخش بر اساس EXIF
        try:
            transposed = ImageOps.exif_transpose(img)
            if transposed is not None:
                img = transposed
        except Exception:
            pass

        # تبدیل به حالت RGB
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")

        # تغییر سایز در صورت بزرگ‌تر بودن از سقف مجاز
        w, h = img.size
        if max(w, h) > max_dimension:
            scale = max_dimension / max(w, h)
            new_size = (int(w * scale), int(h * scale))
            img = img.resize(new_size, Image.Resampling.LANCZOS)

        out_buf = io.BytesIO()
        img.save(out_buf, format="JPEG", quality=92, optimize=True)
        return out_buf.getvalue()
    except Exception as e:
        logger.warning(f"Image preprocessing warning: {e}")
        return image_bytes


# ─── ۱. موتور آفلاین و محلی (Tesseract فارسی + RapidOCR) ───────────────────

def _run_local_ocr_sync(image_bytes: bytes) -> Optional[str]:
    """تلاش برای خواندن آفلاین با اولویت Tesseract فارسی و سپس RapidOCR"""
    # ۱. اولویت Tesseract در صورت نصب در سیستم عامل (دارای دیتابیس فارسی)
    try:
        import subprocess
        proc = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", "fas+eng", "--psm", "3"],
            input=image_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
        )
        if proc.returncode == 0:
            out = proc.stdout.decode("utf-8", errors="replace").strip()
            if out and len(out) > 3:
                return out
    except Exception:
        pass

    # ۲. RapidOCR
    engine = _get_local_engine()
    if engine:
        try:
            result, elapse = engine(image_bytes)
            if result:
                lines = [item[1].strip() for item in result if item and len(item) > 1 and item[1].strip()]
                if lines:
                    return "\n".join(lines)
        except Exception as e:
            logger.warning(f"RapidOCR execution failed: {e}")

    return None


async def _ocr_local(image_bytes: bytes) -> Optional[str]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run_local_ocr_sync, image_bytes)


# ─── ۲. موتور ابری Google Gemini Vision ───────────────────────────────────────

async def _ocr_gemini(image_bytes: bytes, mode: str = "full") -> Optional[str]:
    if not GEMINI_API_KEY:
        return None

    try:
        import google.generativeai as genai
    except ImportError:
        logger.warning("google.generativeai package not installed")
        return None

    genai.configure(api_key=GEMINI_API_KEY)

    prompts = {
        "full": (
            "تو یک متخصص بی‌نقص OCR متن فارسی و انگلیسی هستی. "
            "تمام متون موجود در این تصویر را با دقت ۱۰۰٪ و بدون اضافه کردن هیچ توضیح، مقدمه یا موخره‌ای، کلمه به کلمه استخراج کن. "
            "پاراگراف‌ها و سطربندی را عیناً حفظ کن. اعداد فارسی یا انگلیسی را دقیقاً همانطور که در تصویر هستند بنویس."
        ),
        "clean": (
            "تو یک ویراستار و متخصص OCR هستی. متن تصویر را با دقت بسیار بالا استخراج کرده و غلط‌های املایی، "
            "فواصل حروف و نشانه‌گذاری‌های ناقص را طبق زبان فارسی معیار تصحیح و مرتب کن. فقط متن تصحیح‌شده را برگردان."
        ),
        "receipt": (
            "این تصویر یک رسید، فاکتور یا فیش واریزی بانکی است. "
            "اطلاعات کلیدی آن را با دقت صد در صد و به صورت فرمت مرتب زیر استخراج کن:\n"
            "🧾 <b>اطلاعات تراکنش مالی:</b>\n"
            "• <b>نوع عملیات:</b> [انتقال کارت به کارت / پایا / خرید / ساتنا]\n"
            "• <b>مبلغ پرداختی:</b> [مبلغ به ریال و تومان]\n"
            "• <b>کد پیگیری / شماره ارجاع:</b> [کد]\n"
            "• <b>شماره کارت/حساب مقصد:</b> [شماره و نام صاحب حساب اگر مشخص است]\n"
            "• <b>شماره کارت مبدأ:</b> [شماره کارت]\n"
            "• <b>تاریخ و زمان:</b> [تاریخ و ساعت دقیق]\n"
            "• <b>وضعیت تراکنش:</b> [موفق / ناموفق / در حال پردازش]\n\n"
            "اگر موردی در تصویر خوانا نبود بنویس «نامشخص». فقط همین قالب را تحویل بده."
        ),
        "summary": (
            "متن موجود در این تصویر را با دقت بخوان و نکات مهم، پیام اصلی و خلاصه مفید آن را "
            "در قالب چند بند کوتاه و خوانا (Bullet Points) به زبان فارسی استخراج کن."
        ),
        "translate": (
            "متن موجود در این تصویر را استخراج کرده و آن را به زبان فارسی روان، دقیق و خوانا ترجمه کن. "
            "ابتدا ترجمه فارسی و سپس در صورت تمایل متن اصلی را بنویس."
        ),
    }

    prompt = prompts.get(mode, prompts["full"])
    mime_type = _detect_mime_type(image_bytes)

    if HAS_PIL and Image:
        try:
            content_part = Image.open(io.BytesIO(image_bytes))
        except Exception:
            content_part = {"mime_type": mime_type, "data": image_bytes}
    else:
        content_part = {"mime_type": mime_type, "data": image_bytes}

    models_to_try = [
        GEMINI_MODEL,
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-2.5-flash",
        "gemini-1.5-flash-8b",
        "gemini-1.5-pro",
    ]
    models = list(dict.fromkeys(m for m in models_to_try if m))

    loop = asyncio.get_running_loop()
    for model_name in models:
        try:
            model = genai.GenerativeModel(model_name)
            response = await loop.run_in_executor(
                None,
                lambda m=model: m.generate_content(
                    [prompt, content_part],
                    generation_config=genai.types.GenerationConfig(
                        temperature=0.1,
                        max_output_tokens=3000,
                    ),
                ),
            )
            ans = None
            if response and response.candidates:
                first_cand = response.candidates[0]
                if first_cand.content and first_cand.content.parts:
                    ans = "".join(p.text for p in first_cand.content.parts if hasattr(p, "text") and p.text).strip()
            if not ans and response:
                try:
                    ans = response.text.strip()
                except Exception:
                    pass
            if ans and len(ans) > 2:
                logger.info(f"✅ Gemini Vision OCR succeeded using model: {model_name}")
                return ans
        except Exception as e:
            logger.warning(f"Gemini Vision model '{model_name}' failed: {e}")
            continue

    return None


# ─── ۳. موتور ابری Groq Vision ───────────────────────────────────────────────

async def _ocr_groq(image_bytes: bytes, mode: str = "full") -> Optional[str]:
    if not GROQ_API_KEY:
        return None

    try:
        from groq import Groq
    except ImportError:
        logger.warning("groq library not installed")
        return None

    client = Groq(api_key=GROQ_API_KEY)

    b64_img = base64.b64encode(image_bytes).decode("utf-8")
    mime_type = _detect_mime_type(image_bytes)
    data_url = f"data:{mime_type};base64,{b64_img}"

    sys_instruction = "You are an expert Persian and English OCR transcription engine. Transcribe all text accurately without commentary."
    if mode == "receipt":
        user_prompt = (
            f"{sys_instruction}\n\n"
            "این تصویر یک رسید، فاکتور یا فیش واریزی بانکی است. "
            "اطلاعات کلیدی آن را با دقت صد در صد و به صورت فرمت مرتب زیر استخراج کن:\n"
            "🧾 <b>اطلاعات تراکنش مالی:</b>\n"
            "• <b>نوع عملیات:</b> [انتقال کارت به کارت / پایا / خرید / ساتنا]\n"
            "• <b>مبلغ پرداختی:</b> [مبلغ به ریال و تومان]\n"
            "• <b>کد پیگیری / شماره ارجاع:</b> [کد]\n"
            "• <b>شماره کارت/حساب مقصد:</b> [شماره و نام صاحب حساب اگر مشخص است]\n"
            "• <b>شماره کارت مبدأ:</b> [شماره کارت]\n"
            "• <b>تاریخ و زمان:</b> [تاریخ و ساعت دقیق]\n"
            "• <b>وضعیت تراکنش:</b> [موفق / ناموفق / در حال پردازش]\n\n"
            "اگر موردی در تصویر خوانا نبود بنویس «نامشخص». فقط همین قالب را تحویل بده."
        )
    elif mode == "summary":
        user_prompt = (
            f"{sys_instruction}\n\n"
            "متن موجود در این تصویر را با دقت بخوان و نکات مهم، پیام اصلی و خلاصه مفید آن را "
            "در قالب چند بند کوتاه و خوانا (Bullet Points) به زبان فارسی استخراج کن."
        )
    elif mode == "translate":
        user_prompt = (
            f"{sys_instruction}\n\n"
            "متن موجود در این تصویر را استخراج کرده و آن را به زبان فارسی روان، دقیق و خوانا ترجمه کن. "
            "ابتدا ترجمه فارسی و سپس در صورت تمایل متن اصلی را بنویس."
        )
    elif mode == "clean":
        user_prompt = (
            f"{sys_instruction}\n\n"
            "متن تصویر را با دقت بسیار بالا استخراج کرده و غلط‌های املایی، "
            "فواصل حروف و نشانه‌گذاری‌های ناقص را طبق زبان فارسی معیار تصحیح و مرتب کن. فقط متن تصحیح‌شده را برگردان."
        )
    else:
        user_prompt = (
            f"{sys_instruction}\n\n"
            "تمام متون موجود در این تصویر (فارسی و انگلیسی) را با دقت ۱۰۰٪ و کلمه به کلمه استخراج کن. "
            "پاراگراف‌ها و سطربندی را عیناً حفظ کن. اعداد فارسی یا انگلیسی را دقیقاً همانطور که در تصویر هستند بنویس. "
            "هیچ متن اضافه، مقدمه یا سلام ننویس."
        )

    models_to_try = [
        GROQ_VISION_MODEL,
        "qwen/qwen3.8-27b",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "llama-3.2-11b-vision-preview",
        "llama-3.2-90b-vision-preview",
    ]
    models = list(dict.fromkeys(m for m in models_to_try if m))

    loop = asyncio.get_running_loop()
    for model_name in models:
        try:
            response = await loop.run_in_executor(
                None,
                lambda m=model_name: client.chat.completions.create(
                    model=m,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": user_prompt},
                                {"type": "image_url", "image_url": {"url": data_url}},
                            ],
                        },
                    ],
                    temperature=0.1,
                    max_completion_tokens=3000,
                ),
            )
            if response and response.choices and response.choices[0].message:
                ans = response.choices[0].message.content.strip()
                if ans and len(ans) > 2:
                    logger.info(f"✅ Groq Vision OCR succeeded using model: {model_name}")
                    return ans
        except Exception as e:
            logger.warning(f"Groq Vision model '{model_name}' failed: {e}")
            continue

    return None


# ─── ۴. تابع جامع استخراج متن (پایپ‌لاین هوشمند چندگانه) ────────────────────

async def extract_text_from_image(
    image_bytes: bytes,
    mode: str = "full",
    provider: str = "auto",
) -> dict:
    """
    استخراج هوشمند متن از تصویر با انتخاب یا فال‌بک خودکار بین موتورها:
    mode: 'full' | 'clean' | 'receipt' | 'summary' | 'translate'
    provider: 'auto' | 'gemini' | 'groq' | 'local'
    """
    start_time = time.time()
    clean_bytes = preprocess_image(image_bytes)

    text_result = None
    used_provider = None
    provider_title = None

    # ۱. درخواست اختصاصی Gemini
    if provider == "gemini":
        text_result = await _ocr_gemini(clean_bytes, mode=mode)
        if text_result:
            used_provider = "gemini"
            provider_title = "🤖 هوش مصنوعی (Gemini Vision)"

    # ۲. درخواست اختصاصی Groq
    elif provider == "groq":
        text_result = await _ocr_groq(clean_bytes, mode=mode)
        if text_result:
            used_provider = "groq"
            provider_title = "⚡ هوش مصنوعی (Groq Vision)"

    # ۳. درخواست اختصاصی موتور محلی
    elif provider == "local":
        text_result = await _ocr_local(clean_bytes)
        if text_result:
            used_provider = "local"
            provider_title = "💻 موتور آفلاین و محلی"

    # ۴. حالت خودکار (Auto Hybrid Fallback Pipeline)
    else:
        # تعیین اولویت بر اساس AI_PROVIDER تعریف‌شده در .env
        is_groq_primary = (AI_PROVIDER or "groq").lower() == "groq"

        primary = ("groq", _ocr_groq, "⚡ هوش مصنوعی (Groq Vision)") if is_groq_primary else ("gemini", _ocr_gemini, "🤖 هوش مصنوعی (Gemini Vision)")
        secondary = ("gemini", _ocr_gemini, "🤖 هوش مصنوعی (Gemini Vision)") if is_groq_primary else ("groq", _ocr_groq, "⚡ هوش مصنوعی (Groq Vision)")

        # تلاش اول: موتور هوش مصنوعی اصلی
        p_name, p_func, p_title = primary
        if (GROQ_API_KEY if p_name == "groq" else GEMINI_API_KEY):
            text_result = await p_func(clean_bytes, mode=mode)
            if text_result:
                used_provider = p_name
                provider_title = p_title

        # تلاش دوم: موتور هوش مصنوعی جایگزین
        if not text_result:
            s_name, s_func, s_title = secondary
            if (GROQ_API_KEY if s_name == "groq" else GEMINI_API_KEY):
                text_result = await s_func(clean_bytes, mode=mode)
                if text_result:
                    used_provider = s_name
                    provider_title = s_title

        # تلاش سوم: موتور محلی
        if not text_result:
            text_result = await _ocr_local(clean_bytes)
            if text_result:
                used_provider = "local"
                provider_title = "💻 موتور آفلاین و محلی"

    elapsed = round(time.time() - start_time, 2)

    if text_result:
        return {
            "success": True,
            "text": text_result,
            "provider": used_provider,
            "provider_title": provider_title,
            "mode": mode,
            "elapsed_seconds": elapsed,
        }
    else:
        if not GROQ_API_KEY and not GEMINI_API_KEY:
            fail_msg = (
                "❌ <b>کلید API هوش مصنوعی تنظیم نشده است!</b>\n\n"
                "برای فعال‌سازی استخراج متن (OCR)، لطفاً در فایل <code>.env</code> سرور، حداقل یکی از مقادیر زیر را وارد کنید:\n"
                "• <code>GROQ_API_KEY</code> (رایگان از console.groq.com)\n"
                "• <code>GEMINI_API_KEY</code> (رایگان از aistudio.google.com)"
            )
        else:
            fail_msg = (
                "❌ هیچ متنی در این تصویر شناسایی نشد یا تصویر ناخوانا است.\n\n"
                "💡 <b>پیشنهاد:</b>\n"
                "• مطمئن شوید تصویر دارای متن خوانا و وضوح کافی است.\n"
                "• می‌توانید با کلیدهای زیر مجدداً پردازش را امتحان فرمایید."
            )

        return {
            "success": False,
            "text": fail_msg,
            "provider": "none",
            "provider_title": "ناموفق",
            "mode": mode,
            "elapsed_seconds": elapsed,
        }


# ─── ۵. کیبورد تعاملی نتایج OCR ──────────────────────────────────────────────

def build_ocr_keyboard(file_id: str, current_mode: str = "full", current_prov: str = "auto") -> InlineKeyboardMarkup:
    """ساخت کیبورد شیشه‌ای زیبا برای عملیات مختلف روی عکس"""
    f_short = file_id[-20:] if len(file_id) > 20 else file_id

    rows = [
        [
            InlineKeyboardButton("🧾 تحلیل فیش / رسید", callback_data=f"ocr_m_receipt_{f_short}"),
            InlineKeyboardButton("🌐 ترجمه فارسی", callback_data=f"ocr_m_translate_{f_short}"),
        ],
        [
            InlineKeyboardButton("💡 خلاصه‌سازی محتوا", callback_data=f"ocr_m_summary_{f_short}"),
            InlineKeyboardButton("📝 متن کامل چاپی", callback_data=f"ocr_m_full_{f_short}"),
        ],
        [
            InlineKeyboardButton("✨ ویرایش و تصحیح", callback_data=f"ocr_m_clean_{f_short}"),
            InlineKeyboardButton("⚡ اسکن مجدد هوشمند", callback_data=f"ocr_p_auto_{f_short}"),
        ],
        [
            InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="menu_main"),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def format_ocr_response(result: dict, mode: str = "full") -> str:
    """قالب‌بندی حرفه‌ای و تمیز تلگرام برای نمایش نتایج OCR"""
    mode_labels = {
        "full": "استخراج کامل متن",
        "clean": "متن ویرایش‌شده و تمیز",
        "receipt": "تحلیل فیش و رسید بانکی",
        "summary": "خلاصه نکات کلیدی",
        "translate": "ترجمه متن تصویر",
    }
    mode_fa = mode_labels.get(mode, "استخراج متن")
    prov_fa = result.get("provider_title", "موتور هوشمند")
    sec_fa = to_persian_digits(str(result.get("elapsed_seconds", "0")))
    success = result.get("success", False)

    text_content = result.get("text", "")

    lines = [
        f"🔍 <b>نتیجه پردازش تصویر ({mode_fa})</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━\n",
    ]

    if not success:
        lines.append(text_content)
    elif mode == "receipt":
        lines.append(text_content)
    else:
        lines.append("<blockquote>")
        lines.append(html.escape(text_content))
        lines.append("</blockquote>")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"⚙️ <b>موتور:</b> {prov_fa} | ⏱ <b>زمان:</b> {sec_fa} ثانیه")
    lines.append("👇 <i>برای تغییر نوع پردازش، از کلیدهای زیر استفاده کنید:</i>")

    return "\n".join(lines)
