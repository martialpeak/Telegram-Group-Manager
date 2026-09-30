"""
هندلرهای Callback — فیدبک، رای‌گیری، گزارش، عمومی
"""

import html
import logging
from datetime import datetime, timedelta, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import ADMIN_IDS
import bot.db.database as db
from bot.core import moderation as mod
from bot.core.user_levels import get_config, level_label
from bot.utils.helpers import mention, build_vote_keyboard, esc
from bot.handlers.messages import get_pending_answers
from i18n import t

logger = logging.getLogger(__name__)

_MAX_FB_PER_HOUR  = 5
_VOTES_TO_CONFIRM = 2
_VOTES_TO_REJECT  = 3
_MIN_CORRECTION_LEN = 10


def _is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


# ─── callback پاسخ ادمین به سوال بی‌جواب ─────────────────────────────────────

async def on_admin_answer_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data

    if not _is_admin(query.from_user.id):
        return

    pending = get_pending_answers()

    # ── نادیده گرفتن ─────────────────────────────────────────────────────────
    if data.startswith("adm_skip_"):
        key = data[9:]
        pending.pop(key, None)
        try:
            await query.edit_message_text(
                query.message.text + "\n\n🚫 <i>نادیده گرفته شد.</i>",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    # ── پاسخ ادمین ───────────────────────────────────────────────────────────
    if data.startswith("adm_ans_"):
        key = data[8:]
        info = pending.get(key)
        if not info:
            await query.answer("این سوال دیگه فعال نیست.", show_alert=True)
            return
        context.user_data["admin_answering"] = key
        try:
            await query.edit_message_text(
                query.message.text + "\n\n✏️ <i>پاسخ خود را بنویسید:</i>",
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception:
            pass
        return


async def on_admin_answer_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دریافت متن پاسخ ادمین و ارسال به کاربر + ذخیره در دانش"""
    if not _is_admin(update.effective_user.id):
        return

    key = context.user_data.get("admin_answering")
    if not key:
        return

    answer_text = update.message.text.strip()
    if len(answer_text) < 3:
        await update.message.reply_text("❌ پاسخ خیلی کوتاهه.")
        return

    context.user_data.pop("admin_answering")
    pending = get_pending_answers()
    info    = pending.pop(key, None)

    if not info:
        await update.message.reply_text("⚠️ زمان پاسخ گذشته یا قبلاً پاسخ داده شده.")
        return

    # ذخیره در دانش
    from bot.core.knowledge_engine import _normalize_question
    from bot.db.database import save_knowledge
    norm_q  = _normalize_question(info["question"])
    store_q = norm_q if len(norm_q) >= 3 else info["question"]
    await save_knowledge(
        question=store_q,
        answer=answer_text,
        chat_id=info["chat_id"],
        source="admin_answer",
        score=0.98,
    )

    # ارسال پاسخ به کاربر در گروه
    try:
        await context.bot.send_message(
            chat_id=info["chat_id"],
            text=(
                f"✅ پاسخ سوال شما:\n\n"
                f"❓ <b>{info['question'][:200]}</b>\n\n"
                f"💬 {answer_text}"
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.warning(f"ارسال پاسخ ادمین به گروه ناموفق: {e}")

    await update.message.reply_text(
        f"✅ پاسخ ارسال و در دانش ذخیره شد.\n"
        f"سوال: <code>{info['question'][:100]}</code>",
        parse_mode="HTML",
    )


# ─── callback عمومی (rules / myrank) ─────────────────────────────────────────

async def on_general_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data  = query.data

    # ── تست کلیدهای اینلاین ────────────────────────────────────────────────
    if data == "tbtn_ok":
        await query.answer("✅ دکمه اول کار کرد!", show_alert=True)
        return
    if data == "tbtn_no":
        await query.answer("❌ دکمه دوم کار کرد!", show_alert=True)
        return
    if data == "tbtn_link":
        await query.answer("🔗 دکمه لینک کار کرد!", show_alert=True)
        return

    if data == "dt_refresh":
        await query.answer("🔄 ساعت و تاریخ بروز شد")
        from bot.utils.helpers import get_datetime_response
        txt = get_datetime_response()
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 بروزرسانی زمان", callback_data="dt_refresh")],
        ])
        try:
            await query.edit_message_text(txt, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass
        return

    if data == "rules":
        await query.answer(t("rules_text"), show_alert=True)

    elif data.startswith("myrank_"):
        try:
            uid = int(data.split("_")[1])
        except (ValueError, IndexError):
            await query.answer()
            return
        chat_id = query.message.chat_id
        level   = await db.get_user_level(uid, chat_id)
        cfg     = get_config(level)
        warns   = await db.get_warnings(uid, chat_id)
        q       = "نامحدود" if cfg.daily_queries == -1 else str(cfg.daily_queries)
        await query.answer(
            f"🏅 سطح: {level_label(level)}\n"
            f"⚠️ اخطار: {warns}/3\n"
            f"❓ سوال روزانه: {q}",
            show_alert=True,
        )

    elif data == "help_main":
        await query.answer()
        bot_username = context.bot.username
        user = query.from_user
        chat = query.message.chat
        from telegram.constants import ChatType
        is_adm = _is_admin(user.id)
        is_priv = (chat.type == ChatType.PRIVATE)

        level_val = None
        q_val = None
        rank_name = None

        if not is_priv:
            level_val = await db.get_user_level(user.id, chat.id)
            cfg = get_config(level_val)
            q_val = "نامحدود" if cfg.daily_queries == -1 else str(cfg.daily_queries)
            from bot.core.punishment_ranks import get_rank_name
            rank = await db.get_punishment_rank(user.id, chat.id)
            rank_name = get_rank_name(rank)

        from bot.handlers.commands import get_start_text, get_start_keyboard
        text = get_start_text(bot_username, user, chat.type, level_val, q_val, rank_name)
        kb = get_start_keyboard(bot_username, is_adm, is_priv, user.id)
        try:
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception as e:
            if "Message is not modified" not in str(e):
                logger.warning(f"Failed to edit message in help_main: {e}")
                try:
                    await query.edit_message_text(text, reply_markup=kb)
                except Exception:
                    pass
        return

    elif data in ("help_user", "help_admin", "help_ai"):
        await query.answer()
        from bot.handlers.commands import (
            get_help_user_text, get_help_admin_text, get_help_ai_text, get_help_keyboard
        )
        is_adm = _is_admin(query.from_user.id)
        if data == "help_user":
            txt = get_help_user_text()
            tab = "user"
        elif data == "help_admin":
            txt = get_help_admin_text()
            tab = "admin"
        else:
            txt = get_help_ai_text()
            tab = "ai"

        kb = get_help_keyboard(tab, is_adm)
        try:
            await query.edit_message_text(txt, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass
        return

    elif data.startswith("ainf_"):
        if not _is_admin(query.from_user.id):
            await query.answer("❌ فقط ادمین‌ها اجازه دارند.", show_alert=True)
            return

        parts = data.split("_")
        action = parts[1]
        try:
            target_uid = int(parts[2])
        except (IndexError, ValueError):
            await query.answer("شناسه کاربر نامعتبر است.")
            return

        chat = query.message.chat
        chat_id = chat.id

        if action == "warn":
            from bot.core import moderation as mod
            warn_count = await db.add_warning(target_uid, chat_id, "اقدام سریع از کارت اطلاعات کاربر")
            await mod.apply_warn_tag(context.bot, chat_id, target_uid, warn_count)
            await query.answer(f"⚠️ اخطار #{warn_count} برای کاربر ثبت شد.", show_alert=True)

        elif action == "mute":
            from bot.core import moderation as mod
            await mod._mute(context.bot, chat_id, target_uid, minutes=30)
            await db.add_punishment(target_uid, chat_id, "mute", 1800, "میوت ۳۰ دقیقه‌ای از کارت اینفو")
            await mod.apply_mute_tag(context.bot, chat_id, target_uid, "۳۰ دقیقه")
            await query.answer("🔇 کاربر به مدت ۳۰ دقیقه میوت شد.", show_alert=True)

        elif action == "ban":
            from bot.core import moderation as mod
            await mod._ban(context.bot, chat_id, target_uid)
            await db.add_punishment(target_uid, chat_id, "ban", -1, "بن سریع از کارت اینفو")
            await query.answer("🚫 کاربر از گروه بن شد.", show_alert=True)

        elif action == "ref":
            await query.answer("🔄 اطلاعات به‌روزرسانی شد.")

        try:
            from bot.handlers.commands import build_user_info_card
            cm = await context.bot.get_chat_member(chat_id, target_uid)
            target_name = getattr(cm.user, "full_name", str(target_uid))
            target_mention = mention(cm.user)
            text, kb = await build_user_info_card(
                context, chat, target_uid, target_name, target_mention, query.from_user.id
            )
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass
        return

    elif data.startswith("qunb_"):
        if not _is_admin(query.from_user.id):
            await query.answer("❌ فقط ادمین‌ها اجازه دارند.", show_alert=True)
            return

        try:
            target_uid = int(data[5:])
        except ValueError:
            await query.answer("شناسه نامعتبر است.")
            return

        chat = query.message.chat
        try:
            from bot.core import moderation as mod
            await mod._unban(context.bot, chat.id, target_uid)
            await db.log_action(chat.id, "unban", target_uid, str(target_uid), "آنبن سریع از لیست بن")
            await query.answer(f"✅ کاربر {target_uid} با موفقیت آنبن شد!", show_alert=True)

            bans = await db.get_recent_banned_users(chat.id, limit=8)
            if not bans:
                await query.edit_message_text("✅ <b>هیچ کاربر بن‌شده‌ای در این گروه وجود ندارد.</b>", parse_mode="HTML")
            else:
                lines = []
                unban_buttons = []
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                for i, b in enumerate(bans, 1):
                    uid = b["user_id"]
                    name = b["name"][:18]
                    date_str = b["created_at"][:16] if b.get("created_at") else ""
                    reason = b.get("reason") or "تخلف"
                    actor = f"توسط ادمین <code>{b['actor_id']}</code>" if b.get("actor_id") else "توسط سیستم/AI"
                    lines.append(f"<b>{i}. {name}</b> (<code>{uid}</code>)\n   📅 تاریخ: <code>{date_str}</code> | {actor}\n   📌 علت: <i>{reason}</i>")
                    unban_buttons.append(InlineKeyboardButton(f"🔓 آنبن: {name[:12]}", callback_data=f"qunb_{uid}"))

                cards = "\n\n".join(lines)
                text = f"🚫 <b>لیست کاربران بن‌شده اخیر در گروه:</b>\n\n<blockquote>\n{cards}\n</blockquote>\n\n💡 <i>جهت رفع مسدودیت هر کاربر، دکمه مربوطه را لمس کنید:</i>"
                rows = [unban_buttons[i:i+2] for i in range(0, len(unban_buttons), 2)]
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))
        except Exception as e:
            await query.answer(f"خطا در آنبن: {e}", show_alert=True)
        return

    elif data.startswith("prc_"):
        await query.answer()
        from bot.core.knowledge_engine import (
            _currency_api_search, _gold_api_search, _crypto_api_search,
            _product_price_search, search_price_all
        )
        import urllib.parse
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        if data == "prc_currency":
            curr = await _currency_api_search("دلار")
            if curr:
                kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🔄 بروزرسانی نرخ ارز", callback_data="prc_currency"),
                        InlineKeyboardButton("🪙 طلا و انواع سکه", callback_data="prc_gold"),
                    ],
                    [
                        InlineKeyboardButton("⚡ رمزارزها (BTC/TON)", callback_data="prc_crypto"),
                    ],
                    [
                        InlineKeyboardButton("🔙 منوی قیمت‌ها", callback_data="prc_menu"),
                        InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu_main"),
                    ]
                ])
                try:
                    await query.edit_message_text(curr, parse_mode="HTML", reply_markup=kb)
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        logger.warning(f"Error editing prc_currency: {e}")
            else:
                await query.answer("❌ در حال حاضر دریافت نرخ ارز با مشکل مواجه شد.", show_alert=True)
            return

        elif data == "prc_gold":
            gold = await _gold_api_search("طلا")
            if gold:
                kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🔄 بروزرسانی طلا و سکه", callback_data="prc_gold"),
                        InlineKeyboardButton("💵 نرخ ارز و دلار", callback_data="prc_currency"),
                    ],
                    [
                        InlineKeyboardButton("⚡ رمزارزها (BTC/TON)", callback_data="prc_crypto"),
                    ],
                    [
                        InlineKeyboardButton("🔙 منوی قیمت‌ها", callback_data="prc_menu"),
                        InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu_main"),
                    ]
                ])
                try:
                    await query.edit_message_text(gold, parse_mode="HTML", reply_markup=kb)
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        logger.warning(f"Error editing prc_gold: {e}")
            else:
                await query.answer("❌ اطلاعات طلا و سکه دریافت نشد.", show_alert=True)
            return

        elif data == "prc_crypto":
            crypto = await _crypto_api_search("crypto")
            if crypto:
                kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🔄 بروزرسانی رمزارزها", callback_data="prc_crypto"),
                        InlineKeyboardButton("💵 نرخ ارز و دلار", callback_data="prc_currency"),
                    ],
                    [
                        InlineKeyboardButton("🪙 طلا و انواع سکه", callback_data="prc_gold"),
                    ],
                    [
                        InlineKeyboardButton("🔙 منوی قیمت‌ها", callback_data="prc_menu"),
                        InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu_main"),
                    ]
                ])
                try:
                    await query.edit_message_text(crypto, parse_mode="HTML", reply_markup=kb)
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        logger.warning(f"Error editing prc_crypto: {e}")
            else:
                await query.answer("❌ ارتباط با بازار رمزارز برقرار نشد.", show_alert=True)
            return

        elif data.startswith("prc_it_"):
            raw_item = data[7:]
            try:
                item_name = urllib.parse.unquote(raw_item)
            except Exception:
                item_name = raw_item

            prod = await _product_price_search(item_name)
            if prod:
                enc = urllib.parse.quote(item_name)
                kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("🔗 مشاهده همه فروشگاه‌ها در ترب", url=prod["search_url"]),
                    ],
                    [
                        InlineKeyboardButton("🔄 بروزرسانی قیمت", callback_data=f"prc_it_{enc[:30]}"),
                    ],
                    [
                        InlineKeyboardButton("🔙 منوی قیمت‌ها", callback_data="prc_menu"),
                        InlineKeyboardButton("🏠 منوی اصلی", callback_data="menu_main"),
                    ]
                ])
                try:
                    await query.edit_message_text(prod["text"], parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
                except Exception as e:
                    if "Message is not modified" not in str(e):
                        logger.warning(f"Error editing prc_it_: {e}")
            else:
                await query.answer("❌ کالایی در ترب یافت نشد.", show_alert=True)
            return

        elif data == "prc_menu":
            res = await search_price_all("")
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("💵 نرخ ارز و دلار", callback_data="prc_currency"),
                    InlineKeyboardButton("🪙 طلا و انواع سکه", callback_data="prc_gold"),
                ],
                [
                    InlineKeyboardButton("⚡ بازار رمزارزها (BTC/TON)", callback_data="prc_crypto"),
                ],
                [
                    InlineKeyboardButton("🧹 قیمت انواع جاروبرقی", callback_data="prc_it_جاروبرقی"),
                    InlineKeyboardButton("📱 قیمت روز موبایل", callback_data="prc_it_گوشی موبایل"),
                ],
                [
                    InlineKeyboardButton("💻 قیمت لپ‌تاپ", callback_data="prc_it_لپ تاپ"),
                    InlineKeyboardButton("🎮 قیمت کنسول PS5", callback_data="prc_it_پلی استیشن 5"),
                ],
                [
                    InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="menu_main"),
                ],
            ])
            try:
                await query.edit_message_text(res["text"], parse_mode="HTML", reply_markup=kb)
            except Exception as e:
                if "Message is not modified" not in str(e):
                    logger.warning(f"Error editing prc_menu: {e}")
            return

    elif data.startswith("menu_"):
        await query.answer()
        chat = query.message.chat if query.message else None
        user = query.from_user

        if data == "menu_main":
            name = html.escape(user.first_name) if user and user.first_name else "دوست"
            text = (
                f"🤖 <b>منوی هوشمند و خدمات گروه</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👋 سلام <b>{name}</b> عزیز، به داشبورد تعاملی خوش آمدید!\n"
                f"برای دسترسی سریع و بدون اسپم، یکی از گزینه‌های زیر را انتخاب کنید:"
            )
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("💰 استعلام زنده ارز و طلا", callback_data="menu_prices"),
                    InlineKeyboardButton("⚡ بازار رمزارزها", callback_data="prc_crypto"),
                ],
                [
                    InlineKeyboardButton("🎮 آفرهای بازی رایگان", callback_data="menu_games"),
                    InlineKeyboardButton("📰 اخبار تکنولوژی و AI", callback_data="menu_news"),
                ],
                [
                    InlineKeyboardButton("🪪 شناسنامه و پروفایل من", callback_data="menu_profile"),
                    InlineKeyboardButton("⭐ محبوب‌ترین‌ها (کارما)", callback_data="menu_topkarma"),
                ],
                [
                    InlineKeyboardButton("🌤 وضعیت آب و هوا", callback_data="menu_weather"),
                    InlineKeyboardButton("🗓 تقویم و ساعت رسمی", callback_data="menu_datetime"),
                ],
                [
                    InlineKeyboardButton("🏆 فعال‌ترین‌های چت", callback_data="menu_top"),
                    InlineKeyboardButton("📜 قوانین گروه", callback_data="menu_rules"),
                ],
                [
                    InlineKeyboardButton("❓ راهنمای دستورات", callback_data="menu_help"),
                    InlineKeyboardButton("❌ بستن منو", callback_data="menu_close"),
                ]
            ])
            try:
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
            except Exception as e:
                err_str = str(e)
                if "Message is not modified" in err_str:
                    try:
                        await query.answer("شما هم‌اکنون در منوی اصلی هستید.")
                    except Exception:
                        pass
                else:
                    logger.warning(f"Failed to edit message in menu_main: {e}")
                    plain_text = (
                        "🤖 منوی هوشمند و خدمات گروه\n"
                        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                        f"👋 سلام {user.first_name if user and user.first_name else 'دوست'} عزیز، به داشبورد تعاملی خوش آمدید!\n"
                        "برای دسترسی سریع و بدون اسپم، یکی از گزینه‌های زیر را انتخاب کنید:"
                    )
                    try:
                        await query.edit_message_text(plain_text, reply_markup=kb)
                    except Exception as e2:
                        logger.warning(f"Plain text fallback in menu_main failed: {e2}")
                        try:
                            if query.message:
                                await query.message.reply_text(text, parse_mode="HTML", reply_markup=kb)
                        except Exception as e3:
                            logger.error(f"Reply fallback in menu_main failed: {e3}")
            return

        elif data == "menu_profile":
            from bot.handlers.commands import get_profile_card_data
            text, kb = await get_profile_card_data(user, chat, context)
            try:
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
            except Exception as e:
                if "Message is not modified" not in str(e):
                    logger.warning(f"Error in menu_profile: {e}")
            return

        elif data == "menu_top":
            from bot.utils.helpers import to_persian_digits
            top_users = await db.get_top_users(chat.id, limit=10) if chat else []
            rank_icons = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
            lines = [
                "🏆 <b>فعال‌ترین و برترین کاربران گروه بر اساس فعالیت:</b>",
                "━━━━━━━━━━━━━━━━━━━━━━━━\n",
                "<blockquote>",
            ]
            if top_users:
                for i, u in enumerate(top_users):
                    icon = rank_icons[i] if i < len(rank_icons) else f"#{i+1}"
                    pts_fa = to_persian_digits(f"{u['points']:,}")
                    raw_name = u["full_name"] or f"کاربر {u['user_id']}"
                    u_name = html.escape(raw_name)
                    lines.append(f"{icon} <b>{u_name}</b> — <b>{pts_fa}</b> امتیاز فعالیت")
            else:
                lines.append("هنوز فعالیتی ثبت نشده است.")
            lines.append("</blockquote>\n")
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⭐ برترین‌های کارما", callback_data="menu_topkarma"),
                    InlineKeyboardButton("🪪 پروفایل من", callback_data="menu_profile"),
                ],
                [
                    InlineKeyboardButton("🔙 بازگشت به منو", callback_data="menu_main"),
                ]
            ])
            try:
                await query.edit_message_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)
            except Exception as e:
                if "Message is not modified" not in str(e):
                    logger.warning(f"Error in menu_top: {e}")
            return

        elif data == "menu_topkarma":
            from bot.utils.helpers import to_persian_digits
            top_list = await db.get_top_karma_users(chat.id, limit=10) if chat else []
            rank_icons = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
            lines = [
                "⭐ <b>محبوب‌ترین و مفیدترین اعضای گروه (بر اساس کارما):</b>",
                "━━━━━━━━━━━━━━━━━━━━━━━━\n",
                "<blockquote>",
            ]
            if top_list:
                for i, item in enumerate(top_list):
                    icon = rank_icons[i] if i < len(rank_icons) else f"#{i+1}"
                    k_fa = to_persian_digits(str(item["karma"]))
                    raw_name = item["name"] or f"کاربر {item['user_id']}"
                    u_name = html.escape(raw_name)
                    lines.append(f"{icon} <b>{u_name}</b> — <b>{k_fa}</b> کارما ⭐")
            else:
                lines.append("هنوز امتیازی برای اعضا ثبت نشده است.")
            lines.append("</blockquote>\n")
            lines.append("💡 <i>با ریپلای تشکر و علامت (+) به پیام دیگران، به آنها کارما دهید.</i>")
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🏆 برترین‌های پیام", callback_data="menu_top"),
                    InlineKeyboardButton("🪪 پروفایل من", callback_data="menu_profile"),
                ],
                [
                    InlineKeyboardButton("🔙 بازگشت به منو", callback_data="menu_main"),
                ]
            ])
            try:
                await query.edit_message_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)
            except Exception as e:
                if "Message is not modified" not in str(e):
                    logger.warning(f"Error in menu_topkarma: {e}")
            return

        elif data == "menu_prices":
            from bot.core.knowledge_engine import search_price_all
            res = await search_price_all("")
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("💵 نرخ ارز و دلار", callback_data="prc_currency"),
                    InlineKeyboardButton("🪙 طلا و انواع سکه", callback_data="prc_gold"),
                ],
                [
                    InlineKeyboardButton("⚡ بازار رمزارزها (BTC/TON)", callback_data="prc_crypto"),
                ],
                [
                    InlineKeyboardButton("🔍 جستجوی کالا و اجناس (ترب)", callback_data="prc_menu"),
                    InlineKeyboardButton("🔙 بازگشت به منو", callback_data="menu_main"),
                ]
            ])
            try:
                await query.edit_message_text(res["text"], parse_mode="HTML", reply_markup=kb)
            except Exception as e:
                if "Message is not modified" not in str(e):
                    logger.warning(f"Error in menu_prices: {e}")
            return

        elif data == "menu_datetime":
            from bot.utils.helpers import get_datetime_response
            txt = get_datetime_response()
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🔄 بروزرسانی زمان", callback_data="dt_refresh"),
                    InlineKeyboardButton("🔙 بازگشت به منو", callback_data="menu_main"),
                ]
            ])
            try:
                await query.edit_message_text(txt, parse_mode="HTML", reply_markup=kb)
            except Exception as e:
                if "Message is not modified" not in str(e):
                    logger.warning(f"Error in menu_datetime: {e}")
            return

        elif data == "menu_rules":
            rules_text = (
                f"📜 <b>قوانین رسمی گروه:</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"<blockquote>"
                f"۱. رعایت احترام متقابل و عدم توهین یا تمسخر اعضا\n"
                f"۲. ممنوعیت ارسال هرگونه لینک و تبلیغات غیرمجاز\n"
                f"۳. عدم اسپم، فوروارد رگباری و ارسال استیکرهای نامناسب\n"
                f"۴. بحث و گفتگو در چارچوب موضوع گروه"
                f"</blockquote>\n\n"
                f"🛡️ <i>ربات دارای سیستم اخطار و تنبیه تصاعدی خودکار است.</i>"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت به منو", callback_data="menu_main")]
            ])
            try:
                await query.edit_message_text(rules_text, parse_mode="HTML", reply_markup=kb)
            except Exception as e:
                if "Message is not modified" not in str(e):
                    logger.warning(f"Error in menu_rules: {e}")
            return

        elif data == "menu_help":
            from bot.handlers.commands import get_help_user_text
            txt = get_help_user_text()
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 بازگشت به منو", callback_data="menu_main")]
            ])
            try:
                await query.edit_message_text(txt, parse_mode="HTML", reply_markup=kb)
            except Exception as e:
                if "Message is not modified" not in str(e):
                    logger.warning(f"Error in menu_help: {e}")
            return

        elif data == "menu_games":
            from bot.core.news_deals import get_free_games, format_free_games_message
            try:
                games = await get_free_games(limit=5)
                text, kb = format_free_games_message(games)
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
            except Exception as e:
                if "Message is not modified" not in str(e):
                    logger.warning(f"Error in menu_games: {e}")
            return

        elif data == "menu_news":
            from bot.core.news_deals import get_tech_news, format_tech_news_message
            try:
                news = await get_tech_news(limit=5)
                text, kb = format_tech_news_message(news)
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
            except Exception as e:
                if "Message is not modified" not in str(e):
                    logger.warning(f"Error in menu_news: {e}")
            return

        elif data == "menu_weather":
            from bot.core.weather import get_weather_info
            try:
                text, _ = await get_weather_info("تهران")
                weather_kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("📍 سراوان", callback_data="weather_ref_سراوان"),
                        InlineKeyboardButton("📍 تهران", callback_data="weather_ref_تهران"),
                        InlineKeyboardButton("📍 مشهد", callback_data="weather_ref_مشهد"),
                    ],
                    [
                        InlineKeyboardButton("📍 شیراز", callback_data="weather_ref_شیراز"),
                        InlineKeyboardButton("📍 اصفهان", callback_data="weather_ref_اصفهان"),
                        InlineKeyboardButton("📍 تبریز", callback_data="weather_ref_تبریز"),
                    ],
                    [
                        InlineKeyboardButton("📍 رشت", callback_data="weather_ref_رشت"),
                        InlineKeyboardButton("📍 اهواز", callback_data="weather_ref_اهواز"),
                        InlineKeyboardButton("📍 چابهار", callback_data="weather_ref_چابهار"),
                    ],
                    [
                        InlineKeyboardButton("🔄 بروزرسانی", callback_data="weather_ref_تهران"),
                        InlineKeyboardButton("🔙 بازگشت به منو", callback_data="menu_main"),
                    ]
                ])
                await query.edit_message_text(text, parse_mode="HTML", reply_markup=weather_kb)
            except Exception as e:
                if "Message is not modified" not in str(e):
                    logger.warning(f"Error in menu_weather: {e}")
            return

        elif data == "menu_close":
            try:
                await query.message.delete()
            except Exception:
                pass
            return

    elif data.startswith("weather_ref_"):
        await query.answer("🔄 در حال دریافت آب و هوای بروز...")
        city = data.replace("weather_ref_", "").strip()
        from bot.core.weather import get_weather_info
        try:
            text, _ = await get_weather_info(city)
            weather_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📍 سراوان", callback_data="weather_ref_سراوان"),
                    InlineKeyboardButton("📍 تهران", callback_data="weather_ref_تهران"),
                    InlineKeyboardButton("📍 مشهد", callback_data="weather_ref_مشهد"),
                ],
                [
                    InlineKeyboardButton("📍 شیراز", callback_data="weather_ref_شیراز"),
                    InlineKeyboardButton("📍 اصفهان", callback_data="weather_ref_اصفهان"),
                    InlineKeyboardButton("📍 رشت", callback_data="weather_ref_رشت"),
                ],
                [
                    InlineKeyboardButton("🔄 بروزرسانی همین شهر", callback_data=f"weather_ref_{city}"),
                    InlineKeyboardButton("🔙 بازگشت به منو", callback_data="menu_main"),
                ]
            ])
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=weather_kb)
        except Exception:
            pass
        return

    elif data.startswith("game_"):
        await query.answer("🔄 در حال دریافت آفرهای بازی...")
        from bot.core.news_deals import get_free_games, format_free_games_message
        try:
            games = await get_free_games(limit=5)
            text, kb = format_free_games_message(games)
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
        except Exception:
            pass
        return

    elif data.startswith("news_"):
        await query.answer("🔄 در حال بروزرسانی اخبار...")
        cat_key = data.replace("news_cat_", "")
        category = None if cat_key in ("all", "") else cat_key
        from bot.core.news_deals import get_tech_news, format_tech_news_message
        try:
            news = await get_tech_news(category=category, limit=5)
            text, kb = format_tech_news_message(news, category=category)
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb, disable_web_page_preview=True)
        except Exception:
            pass
        return

    elif data.startswith("prof_refresh_"):
        await query.answer("🔄 در حال بروزرسانی کارت...")
        chat = query.message.chat
        parts = data.split("_")
        target_uid = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else query.from_user.id
        try:
            target_user = query.from_user if target_uid == query.from_user.id else (await context.bot.get_chat_member(chat.id, target_uid)).user
            from bot.handlers.commands import get_profile_card_data
            text, kb = await get_profile_card_data(target_user, chat, context)
            await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            pass
        return

    else:
        await query.answer()


# ─── callback فیدبک و رای‌گیری ───────────────────────────────────────────────

async def on_feedback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query   = update.callback_query
    await query.answer()
    data    = query.data
    voter   = query.from_user
    pending = get_pending_answers()

    # ── درسته ────────────────────────────────────────────────────────────────
    if data.startswith("fb_ok_"):
        key  = data[6:]
        info = pending.pop(key, None)
        if not info:
            await query.answer("این فیدبک دیگه فعال نیست.", show_alert=True)
            return
        allowed = await db.check_feedback_rate(voter.id, info["chat_id"], _MAX_FB_PER_HOUR)
        if not allowed:
            await query.answer("⏳ خیلی زیاد فیدبک دادی! کمی صبر کن.", show_alert=True)
            return
        await db.save_feedback(
            info["user_id"], info["chat_id"],
            info["question"], info["answer"], correct=True,
        )
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("🙏 ممنون از تاییدت!")

    # ── اشتباهه ──────────────────────────────────────────────────────────────
    elif data.startswith("fb_no_"):
        key  = data[6:]
        info = pending.pop(key, None)
        if not info:
            await query.answer("این فیدبک دیگه فعال نیست.", show_alert=True)
            return
        allowed = await db.check_feedback_rate(voter.id, info["chat_id"], _MAX_FB_PER_HOUR)
        if not allowed:
            await query.answer("⏳ خیلی زیاد فیدبک دادی! کمی صبر کن.", show_alert=True)
            return
        await db.save_feedback(
            info["user_id"], info["chat_id"],
            info["question"], info["answer"], correct=False,
        )
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("📝 فیدبکت ثبت شد. ممنون!")

    # ── رای روی تصحیح ────────────────────────────────────────────────────────
    elif data.startswith("vote_up_") or data.startswith("vote_dn_"):
        is_up = data.startswith("vote_up_")
        try:
            fb_id = int(data[8:])
        except ValueError:
            return
        result = await db.vote_correction(fb_id, voter.id, 1 if is_up else -1)
        fb     = await db.get_feedback_by_id(fb_id)
        if not fb:
            return
        # امتیاز برای رای‌دهنده
        await db.add_points(voter.id, fb["chat_id"], 2)
        if result["ups"] >= _VOTES_TO_CONFIRM:
            from bot.core.knowledge_engine import _normalize_question
            norm_q = _normalize_question(fb["question"])
            store_q = norm_q if len(norm_q) >= 3 else fb["question"]
            await db.save_knowledge(
                question=store_q, answer=fb["correction"],
                chat_id=fb["chat_id"], source="community_verified", score=0.92,
            )
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(
                f"✅ تصحیح تایید و یاد گرفته شد! ({result['ups']} رای موافق)"
            )
        elif result["downs"] >= _VOTES_TO_REJECT:
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(
                f"🗑️ تصحیح رد شد. ({result['downs']} رای مخالف)"
            )
        else:
            try:
                await query.edit_message_reply_markup(
                    reply_markup=build_vote_keyboard(fb_id, result["ups"], result["downs"])
                )
            except Exception:
                pass
            label = "👍" if is_up else "👎"
            await query.answer(
                f"{label} رای ثبت شد. موافق:{result['ups']} مخالف:{result['downs']}"
            )


# ─── callback گزارش ──────────────────────────────────────────────────────────

async def on_report_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data

    if not _is_admin(query.from_user.id):
        await query.answer("❌ فقط ادمین‌ها میتونن اقدام کنن.", show_alert=True)
        return

    parts  = data.split("_")
    action = parts[1]

    # ── تأیید رد گزارش ───────────────────────────────────────────────────────
    if action == "ignore":
        report_id = int(parts[2])
        await db.update_report_status(report_id, "ignored")
        await query.edit_message_text(
            query.message.text + "\n\n✅ *نادیده گرفته شد*",
            parse_mode="HTML",
        )
        return

    try:
        report_id = int(parts[2])
        user_id   = int(parts[3])
        chat_id   = int(parts[4])
    except (IndexError, ValueError):
        await query.answer("داده نامعتبر.", show_alert=True)
        return

    await db.update_report_status(report_id, "reviewed")

    # امتیاز به گزارش‌دهنده
    reporter_id = None
    try:
        import aiosqlite
        async with aiosqlite.connect(db.DB_PATH) as _db:
            cur = await _db.execute(
                "SELECT reporter_id FROM reports WHERE id=?", (report_id,)
            )
            row = await cur.fetchone()
            if row:
                reporter_id = row[0]
    except Exception:
        pass

    if action == "warn":
        warn_count = await db.add_warning(user_id, chat_id, f"گزارش #{report_id}")
        await mod.apply_warn_tag(context.bot, chat_id, user_id, warn_count)
        result_txt = f"⚠️ اخطار #{warn_count} داده شد"
        if reporter_id:
            await db.add_points(reporter_id, chat_id, 4)

    elif action == "mute":
        minutes      = await mod._next_mute_minutes(user_id, chat_id)
        duration_lbl = mod._format_minutes(minutes)
        await mod._mute(context.bot, chat_id, user_id, minutes=minutes)
        await db.add_punishment(
            user_id, chat_id, "mute", minutes * 60, f"گزارش #{report_id}"
        )
        await mod.apply_mute_tag(context.bot, chat_id, user_id, duration_lbl)
        result_txt = f"🔇 میوت {duration_lbl}"
        if reporter_id:
            await db.add_points(reporter_id, chat_id, 4)

    elif action == "ban":
        days, label = await mod._next_ban_duration(user_id, chat_id)
        until = (
            datetime.now(tz=timezone.utc) + timedelta(days=days)
        ) if days else None
        await mod._ban(context.bot, chat_id, user_id, until_date=until)
        await db.add_punishment(
            user_id, chat_id, "ban",
            days * 86400 if days else -1,
            f"گزارش #{report_id}",
        )
        result_txt = f"🚫 بن {label}"
        if reporter_id:
            await db.add_points(reporter_id, chat_id, 4)
    else:
        return

    await query.edit_message_text(
        query.message.text + f"\n\n✅ *اقدام انجام شد: {result_txt}*",
        parse_mode="HTML",
    )


# ─── callback تأیید/رد ارتقاء سطح ───────────────────────────────────────────

async def on_upgrade_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data

    if not _is_admin(query.from_user.id):
        await query.answer("❌ فقط ادمین‌ها میتونن اقدام کنن.", show_alert=True)
        return

    if data.startswith("upg_approve_"):
        parts   = data[12:].split("_")
        try:
            user_id = int(parts[0])
            chat_id = int(parts[1])
        except (IndexError, ValueError):
            return

        pending = await db.get_upgrade_pending(user_id, chat_id)
        if not pending:
            await query.answer("درخواست ارتقاء دیگه موجود نیست.", show_alert=True)
            try:
                await query.message.delete()
            except Exception:
                pass
            return

        to_level = pending["to_level"]
        await db.set_user_level(user_id, chat_id, to_level, set_by=query.from_user.id)

        from bot.core.moderation import _set_status_tag
        from bot.core.user_levels import get_config as _get_cfg, level_label as _lv_lbl
        new_cfg = _get_cfg(to_level)
        await _set_status_tag(context.bot, chat_id, user_id, new_cfg.tag)

        # ساخت mention بدون آبجکت User — فقط ID داریم
        user_mention = f'<a href="tg://user?id={user_id}">{user_id}</a>'
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"🎉 {user_mention} به سطح {_lv_lbl(to_level)} ارتقاء پیدا کرد!",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"upgrade announce failed: {e}")

        await db.delete_upgrade_pending(user_id, chat_id)
        try:
            await query.message.delete()
        except Exception:
            pass

    elif data.startswith("upg_reject_"):
        parts   = data[11:].split("_")
        try:
            user_id = int(parts[0])
            chat_id = int(parts[1])
        except (IndexError, ValueError):
            return

        # کم کردن ۵۰ امتیاز
        try:
            current_pts = await db.get_points(user_id, chat_id)
        except Exception:
            current_pts = 0
        new_pts = await db.add_points(user_id, chat_id, -50)

        # حذف درخواست ارتقاء
        await db.delete_upgrade_pending(user_id, chat_id)

        # اعلام به کاربر
        user_mention = f'<a href="tg://user?id={user_id}">{user_id}</a>'
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ درخواست ارتقاء {user_mention} رد شد.\n"
                     f"⭐ امتیاز: {current_pts} → {new_pts} (−50)",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning(f"upgrade reject announce failed: {e}")

        try:
            await query.message.delete()
        except Exception:
            pass


# ─── callback بازبینی مدیریت (تأیید/رد تشخیص AI) ────────────────────────────

async def on_moderation_review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    pattern: rev_approve_{review_id}_{user_id}_{chat_id}_{action}
             rev_reject_{review_id}_{user_id}_{chat_id}_{action}
    """
    query = update.callback_query
    await query.answer()

    if not _is_admin(query.from_user.id):
        return

    data  = query.data
    parts = data.split("_")
    # parts[0]=rev, parts[1]=approve/reject, parts[2]=review_id,
    # parts[3]=user_id, parts[4]=chat_id, parts[5]=action
    try:
        decision  = parts[1]           # approve یا reject
        review_id = int(parts[2])
        user_id   = int(parts[3])
        chat_id   = int(parts[4])
        action    = parts[5]           # insult یا spam
    except (IndexError, ValueError):
        await query.answer("داده نامعتبر.", show_alert=True)
        return

    review = await db.get_moderation_review(review_id)
    if not review or review["status"] != "pending":
        try:
            await query.edit_message_text(
                query.message.text + "\n\n⚠️ قبلاً پردازش شده.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        return

    from bot.core.moderation import (
        apply_warn_tag, apply_mute_tag,
        _mute, _ban, _next_ban_duration, _next_mute_minutes,
        _format_minutes, _notify_user,
    )
    from config import MAX_WARNINGS as _MAX_WARNS

    if decision == "approve":
        await db.update_moderation_review(review_id, "approved")
        warn_count = await db.add_warning(user_id, chat_id, review["ai_reason"] or "تخلف")
        await db.add_points(user_id, chat_id, -5)

        if warn_count >= _MAX_WARNS:
            days, label = await _next_ban_duration(user_id, chat_id)
            from datetime import datetime, timedelta, timezone
            until = (datetime.now(tz=timezone.utc) + timedelta(days=days)) if days else None
            await _ban(context.bot, chat_id, user_id, until_date=until)
            await db.add_punishment(
                user_id, chat_id, "ban",
                days * 86400 if days else -1, action,
            )
            await db.reset_warnings(user_id, chat_id)
            result_txt = f"🚫 بن {label}"
        elif action == "spam":
            minutes      = await _next_mute_minutes(user_id, chat_id)
            duration_lbl = _format_minutes(minutes)
            await _mute(context.bot, chat_id, user_id, minutes=minutes)
            await db.add_punishment(user_id, chat_id, "mute", minutes * 60, action)
            await apply_mute_tag(context.bot, chat_id, user_id, duration_lbl)
            result_txt = f"🔇 میوت {duration_lbl} + اخطار {warn_count}"
        else:
            result_txt = f"⚠️ اخطار {warn_count}"

        await apply_warn_tag(context.bot, chat_id, user_id, warn_count)

        try:
            await _notify_user(
                context.bot, user_id,
                f"⚠️ پیام شما در گروه حذف شد.\n"
                f"اخطار: {warn_count}/{_MAX_WARNS}\n"
                f"دلیل: {review['ai_reason'] or 'تخلف'}",
            )
        except Exception:
            pass

        try:
            await query.edit_message_text(
                query.message.text + f"\n\n✅ <b>تأیید شد — {result_txt}</b>",
                parse_mode="HTML",
            )
        except Exception:
            pass

    elif decision == "reject":
        await db.update_moderation_review(review_id, "rejected")
        await db.save_false_positive(
            action=action,
            message_text=review["message_text"] or "",
            ai_reason=review["ai_reason"] or "",
        )
        try:
            await query.edit_message_text(
                query.message.text + "\n\n❌ <b>رد شد — یاد گرفته شد</b>",
                parse_mode="HTML",
            )
        except Exception:
            pass
