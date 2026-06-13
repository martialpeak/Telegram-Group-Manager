# 🤖 ربات هوشمند مدیریت گروه تلگرام

یک ربات پیشرفته مدیریت گروه تلگرام با هوش مصنوعی **کاملاً محلی** (بدون نیاز به API خارجی).

[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)](https://python.org)
[![python-telegram-bot](https://img.shields.io/badge/python--telegram--bot-21.6-blue)](https://python-telegram-bot.org)
[![Ollama](https://img.shields.io/badge/AI-Ollama-black?logo=ollama)](https://ollama.ai)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## ✨ قابلیت‌ها

| قابلیت | توضیح |
|---|---|
| 🧠 تحلیل هوشمند | شناسایی توهین / اسپم / درخواست با Ollama |
| 📚 پایگاه دانش | جستجوی معنایی (semantic) با embedding محلی |
| 🏅 سطح‌بندی کاربران | ۵ سطح با محدودیت‌های مستقل |
| ⬆️ ارتقاء خودکار | ساده → برنزی بعد از ۵۰ پیام |
| ⚠️ مجازات پلکانی | میوت و بن با افزایش تدریجی |
| 📋 سیستم گزارش | `/report` با اطلاع‌رسانی به ادمین‌ها |
| ⚙️ پنل تنظیمات | تنظیم کامل از داخل تلگرام |
| 🌐 دو زبانه | فارسی و انگلیسی |
| 🗳️ یادگیری جمعی | تصحیح و تأیید جمعی پاسخ‌ها |

---

## 📋 پیش‌نیازها

| مورد | نسخه حداقل | توضیح |
|---|---|---|
| سیستم‌عامل | Ubuntu 20.04 / Debian 11 | یا هر توزیع Linux مدرن |
| Python | **3.11+** | `python3 --version` |
| RAM | **4 GB** (8 GB توصیه‌شده) | برای مدل llama3 |
| فضای دیسک | **8 GB** | برای مدل‌های AI |
| اینترنت | — | فقط برای دانلود اولیه |

---

## 🚀 نصب سریع (یک دستور)

```bash
git clone https://github.com/yourusername/telegram-group-manager.git
cd telegram-group-manager
chmod +x install.sh
./install.sh
```

اسکریپت به‌صورت تعاملی همه مراحل را انجام می‌دهد.

---

## 📖 نصب دستی (گام به گام)

اگر اسکریپت خودکار کار نکرد یا می‌خواهید کنترل کامل داشته باشید:

### گام ۱ — دریافت کد

```bash
git clone https://github.com/yourusername/telegram-group-manager.git
cd telegram-group-manager
```

### گام ۲ — Python و محیط مجازی

```bash
# بررسی نسخه Python
python3 --version   # باید 3.11 یا بالاتر باشد

# ساخت محیط مجازی
python3 -m venv venv

# فعال‌سازی
source venv/bin/activate        # Linux / Mac
# یا
venv\Scripts\activate           # Windows

# نصب وابستگی‌ها
pip install --upgrade pip
pip install -r requirements.txt
```

### گام ۳ — نصب Ollama

**Linux (توصیه‌شده):**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**بررسی نصب:**
```bash
ollama --version
```

**دانلود مدل‌ها:**
```bash
# مدل اصلی (تحلیل پیام) — حدود 4.7 GB
ollama pull llama3.1

# مدل embedding (جستجوی معنایی) — حدود 274 MB
ollama pull nomic-embed-text
```

> **نکته:** اگر RAM محدود دارید، به‌جای `llama3.1` از `gemma2:2b` استفاده کنید (~1.6 GB).

### گام ۴ — ساخت توکن ربات

1. در تلگرام به **[@BotFather](https://t.me/BotFather)** پیام دهید
2. دستور `/newbot` را ارسال کنید
3. نام ربات و username بدهید
4. توکن دریافتی را کپی کنید

**پیدا کردن شناسه تلگرام:**
- به **[@userinfobot](https://t.me/userinfobot)** پیام دهید
- شناسه عددی خود را دریافت می‌کنید

### گام ۵ — پیکربندی

```bash
cp .env.example .env
nano .env
```

مقادیر ضروری را پر کنید:

```env
TELEGRAM_BOT_TOKEN=1234567890:ABC-توکن-شما-اینجا
ADMIN_IDS=123456789,987654321
BOT_LANG=fa
AI_MODEL=llama3.1
```

> ⚠️ فایل `.env` را هرگز در Git کامیت نکنید!

### گام ۶ — اجرای آزمایشی

```bash
source venv/bin/activate
python main.py
```

اگر خروجی زیر را دیدید، ربات کار می‌کند:

```
2025-01-01 12:00:00 | INFO | root — ✅ پایگاه داده آماده شد.
2025-01-01 12:00:00 | INFO | root — 🚀 ربات در حال اجرا است.
```

ربات را به گروه اضافه کنید و `/start` بزنید.

### گام ۷ — اجرای دائمی با systemd

برای اینکه ربات بعد از بسته شدن ترمینال یا ریستارت سرور هم اجرا بماند:

```bash
sudo nano /etc/systemd/system/telegram-bot.service
```

محتوای زیر را وارد کنید (مسیر را با مسیر واقعی جایگزین کنید):

```ini
[Unit]
Description=Telegram Group Manager Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/path/to/telegram-group-manager
ExecStart=/path/to/telegram-group-manager/venv/bin/python main.py
Restart=on-failure
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable telegram-bot
sudo systemctl start telegram-bot

# بررسی وضعیت
sudo systemctl status telegram-bot
```

---

## 🔧 مدیریت سرویس

```bash
# مشاهده لاگ زنده
journalctl -u telegram-bot -f

# ری‌استارت (بعد از تغییر .env)
sudo systemctl restart telegram-bot

# متوقف کردن
sudo systemctl stop telegram-bot

# وضعیت
sudo systemctl status telegram-bot
```

---

## ⚙️ تنظیمات

همه تنظیمات از دو راه قابل تغییرند:

**۱. از داخل تلگرام (توصیه‌شده):**
```
/settings
```

**۲. ویرایش مستقیم `.env` و ری‌استارت ربات**

| متغیر | پیش‌فرض | توضیح |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | توکن از @BotFather |
| `ADMIN_IDS` | — | شناسه‌های ادمین با کاما |
| `BOT_LANG` | `fa` | زبان پیام‌ها: `fa` یا `en` |
| `AI_MODEL` | `llama3.1` | مدل Ollama |
| `EMBED_MODEL` | `nomic-embed-text` | مدل embedding |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | آدرس سرور Ollama |
| `MAX_WARNINGS` | `3` | اخطار قبل از بن |
| `SPAM_TIME_WINDOW` | `60` | بازه اسپم (ثانیه) |
| `SPAM_MAX_MESSAGES` | `5` | پیام در بازه اسپم |
| `MIN_CONFIDENCE` | `0.60` | حداقل اطمینان AI |
| `LEARNING_ENABLED` | `true` | یادگیری از فیدبک |
| `LEARNING_MIN_SCORE` | `0.75` | امتیاز حداقل برای ذخیره |

---

## 📖 دستورات

### دستورات عمومی

| دستور | توضیح |
|---|---|
| `/start` | راهنما و اطلاعات سطح |
| `/myrank` | سطح و آمار شما |
| `/mystats` | آمار روزانه با نوار پیشرفت |
| `/levels` | نمایش همه سطوح |
| `/report [دلیل]` | گزارش پیام (روی پیام ریپلای بزنید) |

### دستورات ادمین

| دستور | توضیح |
|---|---|
| `/warn [دلیل]` | اخطار دستی |
| `/unwarn` | پاک کردن اخطار |
| `/warnings` | تعداد اخطارهای کاربر |
| `/mute [دقیقه]` | میوت دستی |
| `/unmute` | رفع میوت |
| `/ban [30m\|2h\|7d] [دلیل]` | بن موقت یا دائم |
| `/unban` | آنبن |
| `/setlevel <سطح>` | تغییر سطح کاربر |
| `/stats` | آمار کامل گروه |
| `/violations` | آمار تخلفات و پرتخلف‌ها |
| `/reports` | گزارش‌های در انتظر |
| `/search [متن]` | جستجو در تاریخچه |
| `/learn` | یادگیری از فیدبک‌های تأییدشده |
| `/settings` | پنل تنظیمات |

---

## 🏅 سطح‌بندی کاربران

| سطح | مدیا | لینک/روز | فوروارد/روز | سوال/روز | ارتقاء خودکار |
|---|---|---|---|---|---|
| 👤 ساده | ❌ | ۰ | ۰ | ۳ | ۵۰ پیام → برنزی |
| 🥉 برنزی | ✅ | ۵ | ۵ | ۱۰ | دستی |
| 🥈 نقره‌ای | ✅ | ۱۵ | ۱۵ | ۲۵ | دستی |
| 🥇 طلایی | ✅ | ۵۰ | ۵۰ | ۵۰ | دستی |
| 💎 الماسی | ✅ | ∞ | ∞ | ∞ | دستی |

**تغییر سطح:**
```
/setlevel bronze   — روی پیام کاربر ریپلای بزنید
```

---

## 🤖 درباره هوش مصنوعی

ربات از **Ollama** برای اجرای مدل‌های زبانی روی سرور شما استفاده می‌کند:

- **تحلیل پیام:** هر پیام را به‌عنوان `insult` / `spam` / `request` / `normal` دسته‌بندی می‌کند
- **پاسخ به سوالات:** ابتدا پایگاه دانش را جستجو می‌کند، سپس AI پاسخ می‌دهد
- **یادگیری:** کاربران می‌توانند پاسخ‌های اشتباه را تصحیح کنند — با رأی جمعی تأیید می‌شود
- **Fallback:** اگر Ollama در دسترس نبود، سیستم rule-based جایگزین می‌شود

**مدل‌های پشتیبانی‌شده:**

| مدل | RAM | کیفیت | سرعت |
|---|---|---|---|
| `llama3.1` | ~4.7 GB | ⭐⭐⭐⭐⭐ | متوسط |
| `gemma2:2b` | ~1.6 GB | ⭐⭐⭐ | سریع |
| `phi3` | ~2.3 GB | ⭐⭐⭐⭐ | سریع |
| `mistral` | ~4.1 GB | ⭐⭐⭐⭐ | متوسط |

---

## 🗂️ ساختار پروژه

```
telegram-group-manager/
├── main.py                    ← نقطه ورود
├── config.py                  ← خواندن تنظیمات از .env
├── i18n.py                    ← سیستم ترجمه فارسی/انگلیسی
├── settings_panel.py          ← پنل /settings تلگرام
├── bot/
│   ├── core/
│   │   ├── ai_analyzer.py     ← تحلیل پیام با Ollama
│   │   ├── knowledge_engine.py← جستجو و یادگیری
│   │   ├── moderation.py      ← اخطار، میوت، بن
│   │   └── user_levels.py     ← تعریف سطوح کاربری
│   ├── db/
│   │   └── database.py        ← همه عملیات SQLite
│   ├── handlers/
│   │   ├── commands.py        ← /warn /ban /stats ...
│   │   ├── messages.py        ← پردازش پیام متنی
│   │   ├── callbacks.py       ← دکمه‌های inline
│   │   └── members.py         ← ورود/خروج اعضا
│   └── utils/
│       └── helpers.py         ← توابع مشترک
├── requirements.txt
├── .env.example               ← نمونه تنظیمات
├── .gitignore
├── install.sh                 ← نصب‌کننده تعاملی
└── README.md
```

---

## 🐛 رفع مشکلات رایج

**ربات جواب نمی‌دهد:**
```bash
journalctl -u telegram-bot -n 50 --no-pager
```

**خطای `TELEGRAM_BOT_TOKEN`:**
```bash
cat .env   # بررسی توکن
sudo systemctl restart telegram-bot
```

**Ollama کار نمی‌کند:**
```bash
ollama list           # بررسی مدل‌های نصب‌شده
ollama serve          # اجرای دستی
curl http://localhost:11434/api/tags  # تست API
```

**مدل دانلود نشده:**
```bash
ollama pull llama3.1
ollama pull nomic-embed-text
```

**پیام‌ها تحلیل نمی‌شوند (fallback mode):**
- اطمینان حاصل کنید Ollama در حال اجراست
- مدل انتخابی در `.env` با `AI_MODEL` در Ollama مطابقت دارد
- `MIN_CONFIDENCE` را کاهش دهید (مثلاً `0.40`)

---

## 📄 لایسنس

MIT License — برای جزئیات [LICENSE](LICENSE) را ببینید.
