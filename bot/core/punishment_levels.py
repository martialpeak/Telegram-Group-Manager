"""
سیستم لول جریمه — مجازات ۸ مرحله‌ای
هر لول شامل: عنوان، توضیح، مدت، کاهش امتیاز، آیکون
"""

from dataclasses import dataclass


@dataclass
class PunishmentLevel:
    level: int
    name: str          # نام فارسی
    icon: str          # آیکون
    description: str   # توضیح
    duration_minutes: int | None  # None = دائمی
    points_penalty: int           # کاهش امتیاز
    is_temporary: bool            # آیا موقتیه؟
    auto_upgrade_after: int       # بعد از چند بار تکرار ارتقا پیدا می‌کنه


# ─── ۸ لول جریمه ─────────────────────────────────────────────────────────────

PUNISHMENT_LEVELS = {
    1: PunishmentLevel(
        level=1,
        name="اخطار شفاهی",
        icon="⚠️",
        description="اخطار بدون محدودیت — فقط اطلاع‌رسانی",
        duration_minutes=None,
        points_penalty=2,
        is_temporary=False,
        auto_upgrade_after=2,  # بعد از ۲ بار → لول ۲
    ),
    2: PunishmentLevel(
        level=2,
        name="محدودیت موقت",
        icon="🔒",
        description="ممنوعیت ارسال لینک و فوروارد به مدت ۱ ساعت",
        duration_minutes=60,
        points_penalty=5,
        is_temporary=True,
        auto_upgrade_after=3,  # بعد از ۳ بار → لول ۳
    ),
    3: PunishmentLevel(
        level=3,
        name="میوت کوتاه",
        icon="🔇",
        description="سکوت ۱۰ دقیقه‌ای",
        duration_minutes=10,
        points_penalty=8,
        is_temporary=True,
        auto_upgrade_after=3,  # بعد از ۳ بار → لول ۴
    ),
    4: PunishmentLevel(
        level=4,
        name="میوت متوسط",
        icon="🔇",
        description="سکوت ۳۰ دقیقه‌ای",
        duration_minutes=30,
        points_penalty=12,
        is_temporary=True,
        auto_upgrade_after=2,  # بعد از ۲ بار → لول ۵
    ),
    5: PunishmentLevel(
        level=5,
        name="میوت طولانی",
        icon="🔕",
        description="سکوت ۳ ساعته",
        duration_minutes=180,
        points_penalty=18,
        is_temporary=True,
        auto_upgrade_after=2,  # بعد از ۲ بار → لول ۶
    ),
    6: PunishmentLevel(
        level=6,
        name="اخراج موقت",
        icon="🚪",
        description="اخراج از گروه به مدت ۲۴ ساعت",
        duration_minutes=1440,
        points_penalty=25,
        is_temporary=True,
        auto_upgrade_after=2,  # بعد از ۲ بار → لول ۷
    ),
    7: PunishmentLevel(
        level=7,
        name="بن موقت",
        icon="🚫",
        description="بن ۳ روزه",
        duration_minutes=4320,
        points_penalty=35,
        is_temporary=True,
        auto_upgrade_after=2,  # بعد از ۲ بار → لول ۸
    ),
    8: PunishmentLevel(
        level=8,
        name="بن دائم",
        icon="⛔",
        description="حذف دائم از گروه",
        duration_minutes=None,
        points_penalty=50,
        is_temporary=False,
        auto_upgrade_after=999,  # حداکثر لول
    ),
}


def get_punishment_level(level: int) -> PunishmentLevel | None:
    """گرفتن اطلاعات یک لول جریمه"""
    return PUNISHMENT_LEVELS.get(level)


def get_next_punishment_level(current_violations: int) -> int:
    """محاسبه لول جریمه بر اساس تعداد تخلفات"""
    if current_violations <= 0:
        return 1

    total = 0
    for level in sorted(PUNISHMENT_LEVELS.keys()):
        pl = PUNISHMENT_LEVELS[level]
        total += pl.auto_upgrade_after
        if current_violations < total:
            return level

    return 8  # حداکثر لول


def get_punishment_duration(level: int) -> int | None:
    """مدت مجازات بر اساس لول (دقیقه)"""
    pl = get_punishment_level(level)
    return pl.duration_minutes if pl else None


def get_punishment_points(level: int) -> int:
    """کاهش امتیاز بر اساس لول"""
    pl = get_punishment_level(level)
    return pl.points_penalty if pl else 5


def get_level_name(level: int) -> str:
    """نام لول جریمه"""
    pl = get_punishment_level(level)
    return f"{pl.icon} {pl.name}" if pl else f"⚠️ لول {level}"


def get_level_icon(level: int) -> str:
    """آیکون لول جریمه"""
    pl = get_punishment_level(level)
    return pl.icon if pl else "⚠️"


def format_punishment_info(level: int) -> str:
    """نمایش اطلاعات کامل یک لول جریمه"""
    pl = get_punishment_level(level)
    if not pl:
        return "⚠️ لول نامعتبر"

    duration = "دائمی" if pl.duration_minutes is None else f"{pl.duration_minutes} دقیقه"
    return (
        f"{pl.icon} <b>لول {pl.level}: {pl.name}</b>\n"
        f"📝 {pl.description}\n"
        f"⏱️ مدت: {duration}\n"
        f"⭐ کاهش امتیاز: {pl.points_penalty}"
    )
