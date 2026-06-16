"""
سیستم سطح‌بندی کاربران
سطوح: simple < bronze < silver < gold < diamond
"""

from dataclasses import dataclass


@dataclass
class LevelConfig:
    name:              str
    label:             str    # نام فارسی + آیکون — برای نمایش در چت
    tag:               str    # تگ ساده بدون emoji — برای setChatMemberTag
    can_media:         bool   # ارسال عکس/ویدئو/فایل
    can_links:         bool   # ارسال لینک
    can_forward:       bool   # فوروارد پیام
    daily_queries:     int    # سوال روزانه از ربات  (-1 = نامحدود)
    daily_links:       int    # لینک روزانه          (-1 = نامحدود، 0 = ممنوع)
    daily_forwards:    int    # فوروارد روزانه        (-1 = نامحدود، 0 = ممنوع)
    daily_stickers:    int    # گیف/استیکر/انیمیشن روزانه (-1=نامحدود, 0=ممنوع)
    auto_upgrade_msgs: int | None = None  # آستانه ارتقاء خودکار


LEVELS: dict[str, LevelConfig] = {
    "simple": LevelConfig(
        name="simple",
        label="👤 ساده",
        tag="ساده",
        can_media=False,
        can_links=False,
        can_forward=False,
        daily_queries=3,
        daily_links=0,
        daily_forwards=0,
        daily_stickers=0,
        auto_upgrade_msgs=50,
    ),
    "bronze": LevelConfig(
        name="bronze",
        label="🥉 برنزی",
        tag="برنزی",
        can_media=True,
        can_links=True,
        can_forward=True,
        daily_queries=10,
        daily_links=5,
        daily_forwards=5,
        daily_stickers=10,
        auto_upgrade_msgs=None,
    ),
    "silver": LevelConfig(
        name="silver",
        label="🥈 نقره‌ای",
        tag="نقره‌ای",
        can_media=True,
        can_links=True,
        can_forward=True,
        daily_queries=25,
        daily_links=15,
        daily_forwards=15,
        daily_stickers=30,
        auto_upgrade_msgs=None,
    ),
    "gold": LevelConfig(
        name="gold",
        label="🥇 طلایی",
        tag="طلایی",
        can_media=True,
        can_links=True,
        can_forward=True,
        daily_queries=50,
        daily_links=50,
        daily_forwards=50,
        daily_stickers=-1,
        auto_upgrade_msgs=None,
    ),
    "diamond": LevelConfig(
        name="diamond",
        label="💎 الماسی",
        tag="الماسی",
        can_media=True,
        can_links=True,
        can_forward=True,
        daily_queries=-1,
        daily_links=-1,
        daily_forwards=-1,
        daily_stickers=-1,
        auto_upgrade_msgs=None,
    ),
}

LEVEL_ORDER = ["simple", "bronze", "silver", "gold", "diamond"]
AUTO_UPGRADE_MAX = "bronze"


def _load_overrides():
    """بارگذاری تنظیمات سطوح از .env در صورت وجود"""
    import os
    try:
        from dotenv import dotenv_values
        # از __file__ مسیر مطلق بگیر و سه سطح بالاتر برو
        base = os.path.dirname(os.path.abspath(__file__))
        env_path = os.path.join(base, "..", "..", ".env")
        env_path = os.path.normpath(env_path)
        vals = dotenv_values(env_path)
        for level in LEVEL_ORDER:
            cfg = LEVELS[level]
            prefix = f"LEVEL_{level.upper()}_"
            for key, val in vals.items():
                if not key.startswith(prefix):
                    continue
                field = key[len(prefix):].lower()
                try:
                    if field == "queries":
                        cfg.daily_queries  = int(val)
                    elif field == "links":
                        cfg.daily_links    = int(val)
                    elif field == "forwards":
                        cfg.daily_forwards = int(val)
                    elif field == "stickers":
                        cfg.daily_stickers = int(val)
                    elif field == "media":
                        cfg.can_media      = val.lower() == "true"
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass


# بارگذاری override ها هنگام import
_load_overrides()


def get_config(level: str) -> LevelConfig:
    return LEVELS.get(level, LEVELS["simple"])


def level_label(level: str) -> str:
    return get_config(level).label


def is_valid_level(level: str) -> bool:
    return level in LEVELS


def next_auto_level(current: str) -> str | None:
    idx     = LEVEL_ORDER.index(current) if current in LEVEL_ORDER else 0
    max_idx = LEVEL_ORDER.index(AUTO_UPGRADE_MAX)
    if idx < max_idx:
        return LEVEL_ORDER[idx + 1]
    return None


def level_summary() -> str:
    lines = ["📋 *سطوح کاربری:*\n"]
    for lv in LEVEL_ORDER:
        c  = LEVELS[lv]
        q  = "نامحدود" if c.daily_queries  == -1 else str(c.daily_queries)
        lk = "ممنوع"   if c.daily_links    ==  0 else ("نامحدود" if c.daily_links    == -1 else str(c.daily_links))
        fw = "ممنوع"   if c.daily_forwards ==  0 else ("نامحدود" if c.daily_forwards == -1 else str(c.daily_forwards))
        media = "✅" if c.can_media else "❌"
        up    = f" | ارتقاء خودکار: {c.auto_upgrade_msgs} پیام" if c.auto_upgrade_msgs else ""
        lines.append(
            f"{c.label}\n"
            f"  مدیا:{media}  لینک/روز:{lk}  فوروارد/روز:{fw}  سوال/روز:{q}{up}\n"
        )
    return "\n".join(lines)
