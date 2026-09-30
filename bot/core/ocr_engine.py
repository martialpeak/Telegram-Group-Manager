"""
موتور پیشرفته و دوگانه استخراج متن از تصویر (OCR Engine)
پشتیبانی ترکیبی از:
۱. Google Gemini 1.5 Flash Vision (دقت ۹۹٪، تشخیص دست‌نویس، تصحیح خودکار، استخراج فاکتور)
۲. Groq Llama 3.2 Vision (سرعت رعدآسا)
۳. RapidOCR ONNX (موتور آفلاین و محلی بدون نیاز به کلید API یا اینترنت بین‌الملل)
"""

import asyncio
import base64
import html
import io
import logging
import time
from typing import Optional, Tuple

from PIL import Image, ImageOps
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config import GEMINI_API_KEY, GEMINI_MODEL, GROQ_API_KEY
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
    try:
        img = Image.open(io.BytesIO(image_bytes))
        # تصحیح جهت چرخش بر اساس EXIF
        img = ImageOps.exif_transpose(img)

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


# ─── ۱. موتور محلی RapidOCR (آفلاین) ────────────────────────────────────────

def _run_rapidocr_sync(image_bytes: bytes) -> Optional[str]:
    engine = _get_local_engine()
    if not engine:
        return None
    try:
        result, elapse = engine(image_bytes)
        if not result:
            return None

        # تجمیع متن خطوط استخراج‌شده
        lines = [item[1].strip() for item in result if item and len(item) > 1 and item[1].strip()]
        return "\n".join(lines) if lines else None
    except Exception as e:
        logger.warning(f"RapidOCR execution failed: {e}")
        return None


async def _ocr_rapidocr(image_bytes: bytes) -> Optional[str]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _run_rapidocr_sync, image_bytes)


# ─── ۲. موتور ابری Google Gemini 1.5 Flash Vision ────────────────────────────

async def _ocr_gemini(image_bytes: bytes, mode: str = "full") -> Optional[str]:
    if not GEMINI_API_KEY:
        return None

    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)

    model_name = GEMINI_MODEL or "gemini-1.5-flash"
    model = genai.GenerativeModel(model_name)

    prompts = {
        "full": (
            "تو یک دستیار پیشرفته و بی‌نقص OCR متن فارسی و انگلیسی هستی. "
            "تمام متون موجود در این تصویر را با دقت ۱۰۰٪ و بدون اضافه کردن هیچ توضیح، مقدمه یا موخره‌ای، کلمه به کلمه استخراج کن. "
            "پاراگراف‌ها و سطربندی را عیناً حفظ کن. اعداد فارسی یا انگلیسی را دقیقاً همانطور که در تصویر هستند بنویس."
        ),
        "clean": (
            "تو یک ویراستار و متخصص OCR هستی. متن تصویر را با دقت بسیار بالا استخراج کرده و غلط‌های املایی، "
            "فواصل حروف و نشانه‌گذاری‌های ناقص را طبق زبان فارسی معیار تصحیح و مرتب کن. فقط متن تصحیح‌شده را برگردان."
        ),
        "receipt": (
            "این تصویر یک رسید، فاکتور یا فیش واریزی بانکی است. "
            "لطفاً اطلاعات کلیدی آن را با دقت صد در صد و به صورت فرمت مرتب زیر استخراج کن:\n"
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

    try:
        pil_img = Image.open(io.BytesIO(image_bytes))
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: model.generate_content(
                [prompt, pil_img],
                generation_config=genai.types.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=3000,
                ),
            )
        )
        ans = response.text.strip() if response and response.text else None
        return ans
    except Exception as e:
        logger.warning(f"Gemini Vision OCR failed: {e}")
        return None


# ─── ۳. موتور ابری Groq Vision (Llama-3.2) ──────────────────────────────────

async def _ocr_groq(image_bytes: bytes, mode: str = "full") -> Optional[str]:
    if not GROQ_API_KEY:
        return None

    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY)

    b64_img = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:image/jpeg;base64,{b64_img}"

    sys_prompt = "You are an expert Persian and English OCR transcription engine. Transcribe all text accurately without commentary."
    user_prompt = "Extract all text from this image accurately. Preserve formatting and paragraphs. Do not add intro or outro."

    if mode == "receipt":
        user_prompt = "Extract all financial receipt details from this image in Persian (Amount, Tracking ID, Card numbers, Date/Time)."
    elif mode == "summary":
        user_prompt = "Summarize the key information and text from this image in bullet points in Persian."
    elif mode == "translate":
        user_prompt = "Extract the text from this image and translate it to fluent Persian."

    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None,
            lambda: client.chat.completions.create(
                model="llama-3.2-11b-vision-preview",
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    },
                ],
                temperature=0.1,
                max_tokens=2500,
            )
        )
        ans = response.choices[0].message.content.strip()
        return ans if ans and len(ans) > 2 else None
    except Exception as e:
        logger.warning(f"Groq Vision OCR failed: {e}")
        return None


# ─── ۴. تابع جامع استخراج متن (پایپ‌لاین هوشمند دوگانه) ─────────────────────

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
            provider_title = "🤖 هوش مصنوعی پیشرفته (Gemini Vision)"

    # ۲. درخواست اختصاصی Groq
    elif provider == "groq":
        text_result = await _ocr_groq(clean_bytes, mode=mode)
        if text_result:
            used_provider = "groq"
            provider_title = "⚡ هوش مصنوعی پرسرعت (Groq Vision)"

    # ۳. درخواست اختصاصی موتور محلی
    elif provider == "local":
        text_result = await _ocr_rapidocr(clean_bytes)
        if text_result:
            used_provider = "local"
            provider_title = "💻 موتور آفلاین و محلی (RapidOCR)"

    # ۴. حالت خودکار (Auto Hybrid Fallback Pipeline)
    else:
        # اولویت ۱: Gemini 1.5 Flash Vision (بالاترین کیفیت)
        if GEMINI_API_KEY:
            text_result = await _ocr_gemini(clean_bytes, mode=mode)
            if text_result:
                used_provider = "gemini"
                provider_title = "🤖 هوش مصنوعی پیشرفته (Gemini Vision)"

        # اولویت ۲: Groq Vision (در صورت بروز مشکل در جمینای)
        if not text_result and GROQ_API_KEY:
            text_result = await _ocr_groq(clean_bytes, mode=mode)
            if text_result:
                used_provider = "groq"
                provider_title = "⚡ هوش مصنوعی پرسرعت (Groq Vision)"

        # اولویت ۳: موتور محلی و آفلاین RapidOCR
        if not text_result:
            text_result = await _ocr_rapidocr(clean_bytes)
            if text_result:
                used_provider = "local"
                provider_title = "💻 موتور آفلاین و محلی (RapidOCR)"

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
        return {
            "success": False,
            "text": "❌ هیچ متنی در این تصویر شناسایی نشد یا تصویر ناخوانا است.",
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
            InlineKeyboardButton("💻 موتور آفلاین محلی", callback_data=f"ocr_p_local_{f_short}"),
            InlineKeyboardButton("🤖 موتور هوش مصنوعی", callback_data=f"ocr_p_gemini_{f_short}"),
        ],
        [
            InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="menu_main"),
        ]
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

    text_content = result.get("text", "")

    # اگر حالت رسید نیست، داخل blockquote برای خوانایی بهتر قرار گیرد
    lines = [
        f"🔍 <b>نتیجه خواندن تصویر ({mode_fa})</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━\n",
    ]

    if mode == "receipt":
        lines.append(text_content)
    else:
        # پاکسازی کدهای نمایشی
        lines.append("<blockquote>")
        lines.append(html.escape(text_content))
        lines.append("</blockquote>")

    lines.append("\n━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"⚙️ <b>موتور:</b> {prov_fa} | ⏱ <b>زمان پردازش:</b> {sec_fa} ثانیه")
    lines.append("👇 <i>برای تغییر نوع پردازش یا موتور، از کلیدهای زیر استفاده کنید:</i>")

    return "\n".join(lines)
