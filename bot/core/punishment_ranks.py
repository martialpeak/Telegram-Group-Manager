"""
سیستم رنک جریمه — مشابه سطح کاربری ولی برای مجازات‌ها
رنک‌ها: clean < warning < probation < restricted < banned
"""

from dataclasses import dataclass


@dataclass
class PunishmentRank:
    name: str
    label: str          # نام فارسی + آیکون
    tag: str            # تگ ساده
    min_violations: int # حداقل تعداد تخلفات
    max_violations: int # حداکثر تعداد تخلفات
    can_ask_bot: bool   # اجازه سوال از ربات
    can_send_link: bool # اجازه ارسال لینک
    can_forward: bool   # اجازه فوروارد
    daily_limit: int    # محدودیت روزانه (-1 = نامحدود)


# ─── رنک‌های جریمه ─────────────────────────────────────────────────────────────

PUNISHMENT_RANKS: dict[str, PunishmentRank] = {
    "clean": PunishmentRank(
        name="clean",
        label="✅ پاک",
        tag="پاک",
        min_violations=0,
        max_violations=0,
        can_ask_bot=True,
        can_send_link=True,
        can_forward=True,
        daily_limit=-1,  # نامحدود
    ),
    "warning": PunishmentRank(
        name="warning",
        label="⚠️ تحت نظر",
        tag="تحت_نظر",
        min_violations=1,
        max_violations=2,
        can_ask_bot=True,
        can_send_link=False,  # ممنوع
        can_forward=False,    # ممنوع
        daily_limit=5,
    ),
    "probation": PunishmentRank(
        name="probation",
        label="🥉 آزمایشی",
        tag="آزمایشی",
        min_violations=3,
        max_violations=5,
        can_ask_bot=True,
        can_send_link=False,
        can_forward=False,
        daily_limit=3,
    ),
    "restricted": PunishmentRank(
        name="restricted",
        label="🥈 محدود",
        tag="محدود",
        min_violations=6,
        max_violations=8,
        can_ask_bot=True,
        can_send_link=False,
        can_forward=False,
        daily_limit=1,
    ),
    "banned": PunishmentRank(
        name="banned",
        label="🥇 ممنوع",
        tag="ممنوع",
        min_violations=9,
        max_violations=999,
        can_ask_bot=False,   # حتی سوال هم ممنوع
        can_send_link=False,
        can_forward=False,
        daily_limit=0,       # کاملاً مسدود
    ),
}

RANK_ORDER = ["clean", "warning", "probation", "restricted", "banned"]


def get_rank_by_violations(violations: int) -> str:
    """محاسبه رنک جریمه بر اساس تعداد تخلفات"""
    if violations <= 0:
        return "clean"

    for rank_name in reversed(RANK_ORDER):
        rank = PUNISHMENT_RANKS[rank_name]
        if violations >= rank.min_violations:
            return rank_name

    return "clean"


def get_rank_config(rank_name: str) -> PunishmentRank | None:
    """گرفتن اطلاعات یک رنک"""
    return PUNISHMENT_RANKS.get(rank_name)


def get_rank_name(rank_name: str) -> str:
    """نام رنک جریمه"""
    rank = get_rank_config(rank_name)
    return rank.label if rank else f"⚠️ {rank_name}"


def get_rank_index(rank_name: str) -> int:
    """ایندکس رنک در لیست"""
    try:
        return RANK_ORDER.index(rank_name)
    except ValueError:
        return 0


def format_rank_info(rank_name: str) -> str:
    """نمایش اطلاعات کامل یک رنک"""
    rank = get_rank_config(rank_name)
    if not rank:
        return "⚠️ رنک نامعتبر"

    status = []
    if rank.can_ask_bot:
        status.append("✅ سوال از ربات")
    else:
        status.append("❌ سوال از ربات")

    if rank.can_send_link:
        status.append("✅ ارسال لینک")
    else:
        status.append("❌ ارسال لینک")

    if rank.can_forward:
        status.append("✅ فوروارد")
    else:
        status.append("❌ فوروارد")

    limit = "نامحدود" if rank.daily_limit == -1 else str(rank.daily_limit)

    status_text = "\n".join(status)
    return (
        f"{rank.label} <b>رنک جریمه</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"📊 تعداد تخلفات: {rank.min_violations} تا {rank.max_violations}\n"
        f"💬 محدودیت روزانه: {limit}\n\n"
        f"{status_text}"
    )


def get_all_ranks_summary() -> str:
    """خلاصه همه رنک‌ها"""
    text = "🏆 <b>رنک‌های جریمه</b>\n"
    text += "━━━━━━━━━━━━━━━━━\n\n"

    for rank_name in RANK_ORDER:
        rank = PUNISHMENT_RANKS[rank_name]
        limit = "نامحدود" if rank.daily_limit == -1 else str(rank.daily_limit)
        text += (
            f"{rank.label}\n"
            f"   📊 تخلفات: {rank.min_violations}-{rank.max_violations}\n"
            f"   💬 روزانه: {limit}\n\n"
        )

    text += "💡 <i>هر تخلف، رنک جریمه رو بالا می‌بره.</i>"
    return text
