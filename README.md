# 🤖 Telegram Group Manager Bot | ربات هوشمند مدیریت گروه

<div dir="rtl">

**یک ربات پیشرفته مدیریت گروه تلگرام با هوش مصنوعی ابری — Groq (primary) + Gemini (fallback)**

</div>

**An advanced Telegram group manager bot powered by cloud AI — Groq (primary) + Gemini (fallback).**

[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)](https://python.org)
[![python-telegram-bot](https://img.shields.io/badge/python--telegram--bot-21.6-blue)](https://python-telegram-bot.org)
[![Groq](https://img.shields.io/badge/AI-Groq-orange)](https://console.groq.com)
[![Gemini](https://img.shields.io/badge/AI-Gemini-blue)](https://aistudio.google.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## 🌐 Language | زبان

- [English](#english)
- [فارسی](#فارسی)

---

<a name="english"></a>
# 🇬🇧 English

## ✨ Features

| Feature | Description |
|---|---|
| 🧠 AI Analysis | Detects insult / spam / requests — Groq → Gemini → rule-based fallback |
| 📚 Knowledge Base | Cached Q&A with fuzzy similarity matching |
| 🏅 User Levels | 5 tiers with independent daily limits |
| ⬆️ Auto Upgrade | simple → bronze after 50 messages |
| ⚠️ Escalating Punishments | Progressive mute (10m→30m→3h→24h→48h) and ban steps |
| 📋 Report System | `/report` with admin PM notification + action buttons |
| ⚙️ Settings Panel | Full config from inside Telegram via `/settings` |
| 🌐 Bilingual | Persian and English support |
| 🗳️ Community Learning | Community-voted answer corrections |

## 📋 Requirements

| Item | Minimum | Notes |
|---|---|---|
| OS | Ubuntu 20.04 / Debian 11 | Any modern Linux distro |
| Python | **3.11+** | `python3 --version` |
| RAM | **512 MB** | No local AI model needed |
| Internet | Required | For Groq / Gemini API calls |
| Groq API Key | Free | 14,400 requests/day free tier |
| Gemini API Key | Free (optional) | 1,500 requests/day free tier — used as fallback |

## 🔑 Get API Keys

**Groq (primary — free):**
1. Go to [console.groq.com](https://console.groq.com)
2. Sign up and create an API key
3. Free tier: 14,400 requests/day with `llama-3.1-8b-instant`

**Gemini (fallback — optional but recommended):**
1. Go to [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Create an API key
3. Free tier: 1,500 requests/day with `gemini-2.5-flash`

> If only Groq is configured, Gemini fallback is skipped. If neither is set, the bot falls back to a rule-based engine.

## 🚀 Quick Install (one command)

```bash
git clone https://github.com/martialpeak/Telegram-Group-Manager.git
cd Telegram-Group-Manager
chmod +x install.sh
./install.sh
```

The script handles everything interactively.

## 📖 Manual Installation

### Step 1 — Clone the repository

```bash
git clone https://github.com/martialpeak/Telegram-Group-Manager.git
cd Telegram-Group-Manager
```

### Step 2 — Python virtual environment

```bash
# Check Python version (must be 3.11+)
python3 --version

# Create virtual environment
python3 -m venv venv
source venv/bin/activate        # Linux / Mac
# or
venv\Scripts\activate           # Windows

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3 — Get a bot token

1. Open Telegram and message **[@BotFather](https://t.me/BotFather)**
2. Send `/newbot`
3. Follow the steps and copy your token

**Find your Telegram user ID:**
- Message **[@userinfobot](https://t.me/userinfobot)** — it replies with your numeric ID

### Step 4 — Configure

```bash
cp .env.example .env
nano .env
```

Fill in the required values:

```env
TELEGRAM_BOT_TOKEN=your_token_here
ADMIN_IDS=123456789,987654321
BOT_LANG=en

# AI — at least one is required
GROQ_API_KEY=your_groq_key_here
GEMINI_API_KEY=your_gemini_key_here   # optional fallback
```

> ⚠️ Never commit `.env` to Git!

### Step 5 — Test run

```bash
source venv/bin/activate
python main.py
```

Expected output:
```
2025-01-01 12:00:00 | INFO | root — ✅ Database ready.
2025-01-01 12:00:00 | INFO | root — 🚀 Bot is running.
```

Add the bot to your group and send `/start`.

### Step 6 — Run as a system service (auto-start)

```bash
sudo nano /etc/systemd/system/telegram-bot.service
```

```ini
[Unit]
Description=Telegram Group Manager Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=YOUR_LINUX_USERNAME
WorkingDirectory=/path/to/Telegram-Group-Manager
ExecStart=/path/to/Telegram-Group-Manager/venv/bin/python main.py
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
sudo systemctl status telegram-bot
```

## 🔧 Service Management

```bash
journalctl -u telegram-bot -f          # live logs
sudo systemctl restart telegram-bot    # restart (after .env changes)
sudo systemctl stop telegram-bot       # stop
sudo systemctl status telegram-bot     # status
```

## ⚙️ Configuration

Change settings via `/settings` in Telegram or edit `.env` directly:

| Variable | Default | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | Token from @BotFather |
| `ADMIN_IDS` | — | Admin IDs, comma-separated |
| `BOT_LANG` | `fa` | Message language: `fa` or `en` |
| `GROQ_API_KEY` | — | Groq API key (primary AI) |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | Groq model name |
| `GEMINI_API_KEY` | — | Gemini API key (fallback AI) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model name |
| `MAX_WARNINGS` | `3` | Warnings before ban |
| `SPAM_TIME_WINDOW` | `60` | Spam detection window (seconds) |
| `SPAM_MAX_MESSAGES` | `5` | Max messages in spam window |
| `MIN_CONFIDENCE` | `0.80` | Minimum AI confidence threshold |
| `CACHE_MIN_SCORE` | `0.75` | Minimum similarity for cache hit |
| `LEARNING_ENABLED` | `true` | Enable learning from feedback |
| `LEARNING_MIN_SCORE` | `0.75` | Minimum score to store knowledge |

## 📖 Commands

### User Commands

| Command | Description |
|---|---|
| `/start` | Help and your level info |
| `/myrank` | Your level and stats |
| `/mystats` | Daily stats with progress bars |
| `/levels` | Show all user levels |
| `/report [reason]` | Report a message (reply to it) |

### Admin Commands

| Command | Description |
|---|---|
| `/warn [reason]` | Manually warn a user |
| `/unwarn` | Clear a user's warnings |
| `/warnings` | Show warning count |
| `/mute [minutes]` | Manually mute a user |
| `/unmute` | Unmute a user |
| `/ban [30m\|2h\|7d] [reason]` | Temporary or permanent ban |
| `/unban` | Unban a user |
| `/setlevel <level>` | Set user level |
| `/stats` | Full group statistics |
| `/violations` | Violation stats and top offenders |
| `/reports` | Pending user reports |
| `/search [text]` | Search message history |
| `/learn` | Process approved feedback |
| `/settings` | Bot settings panel |

## 🏅 User Levels

| Level | Media | Links/day | Forwards/day | Queries/day | Auto-upgrade |
|---|---|---|---|---|---|
| 👤 Simple | ❌ | 0 | 0 | 3 | After 50 messages → Bronze |
| 🥉 Bronze | ✅ | 5 | 5 | 10 | Manual |
| 🥈 Silver | ✅ | 15 | 15 | 25 | Manual |
| 🥇 Gold | ✅ | 50 | 50 | 50 | Manual |
| 💎 Diamond | ✅ | ∞ | ∞ | ∞ | Manual |

```
/setlevel bronze    — reply to user's message
```

## 🤖 About the AI

The bot uses a **cloud AI chain** — no local installation needed:

1. **Groq** (primary) — ultra-fast inference, free 14,400 req/day
2. **Gemini** (fallback) — activates if Groq fails or is unavailable
3. **Rule-based engine** — always available, no API needed

**What AI does:**
- **Message Analysis** — classifies each message as `insult` / `spam` / `request` / `normal`
- **Question Answering** — checks knowledge cache first, then calls AI
- **Learning** — users correct wrong answers; community voting approves them

**Supported Groq models:**

| Model | Speed | Notes |
|---|---|---|
| `llama-3.1-8b-instant` | ⚡ Very fast | Default, recommended |
| `llama-3.3-70b-versatile` | 🚀 Fast | Higher quality |
| `mixtral-8x7b-32768` | 🚀 Fast | Good for Persian |

**Supported Gemini models:**

| Model | Notes |
|---|---|
| `gemini-2.5-flash` | Default fallback, fast |
| `gemini-2.0-flash` | Stable alternative |
| `gemini-2.5-pro` | Highest quality |

## 🐛 Troubleshooting

**Bot doesn't respond:**
```bash
journalctl -u telegram-bot -n 50 --no-pager
```

**Token error:**
```bash
cat .env
sudo systemctl restart telegram-bot
```

**AI not working (falling back to rules):**
- Check `GROQ_API_KEY` is set correctly in `.env`
- Verify key at [console.groq.com](https://console.groq.com)
- Try lowering `MIN_CONFIDENCE` to `0.60`
- Check logs for `Groq analyze failed` messages

**Rate limit errors:**
- Groq free tier: 14,400 req/day — set `GEMINI_API_KEY` as fallback
- If both limits hit, rule-based engine takes over automatically

---

<a name="فارسی"></a>
# 🇮🇷 فارسی

<div dir="rtl">

## ✨ قابلیت‌ها

| قابلیت | توضیح |
|---|---|
| 🧠 تحلیل هوشمند | شناسایی توهین / اسپم / درخواست — Groq → Gemini → rule-based |
| 📚 پایگاه دانش | کش سوال-جواب با جستجوی fuzzy |
| 🏅 سطح‌بندی کاربران | ۵ سطح با محدودیت‌های مستقل |
| ⬆️ ارتقاء خودکار | ساده → برنزی بعد از ۵۰ پیام |
| ⚠️ مجازات پلکانی | میوت (۱۰m→۳۰m→۳h→۲۴h→۴۸h) و بن تدریجی |
| 📋 سیستم گزارش | `/report` با اطلاع‌رسانی به ادمین‌ها |
| ⚙️ پنل تنظیمات | تنظیم کامل از داخل تلگرام |
| 🌐 دو زبانه | پشتیبانی از فارسی و انگلیسی |
| 🗳️ یادگیری جمعی | تصحیح و تأیید جمعی پاسخ‌ها |

## 📋 پیش‌نیازها

| مورد | نسخه حداقل | توضیح |
|---|---|---|
| سیستم‌عامل | Ubuntu 20.04 / Debian 11 | هر توزیع Linux مدرن |
| Python | **3.11+** | `python3 --version` |
| RAM | **512 MB** | نیازی به مدل محلی نیست |
| اینترنت | ضروری | برای API call به Groq / Gemini |
| Groq API Key | رایگان | روزانه ۱۴،۴۰۰ درخواست رایگان |
| Gemini API Key | رایگان (اختیاری) | روزانه ۱،۵۰۰ درخواست — fallback |

## 🔑 دریافت API Key

**Groq (اصلی — رایگان):**
1. به [console.groq.com](https://console.groq.com) بروید
2. ثبت‌نام کنید و یک API key بسازید
3. مدل پیش‌فرض: `llama-3.1-8b-instant`

**Gemini (fallback — اختیاری ولی توصیه‌شده):**
1. به [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey) بروید
2. یک API key بسازید
3. مدل پیش‌فرض: `gemini-2.5-flash`

> اگر هیچ‌کدام تنظیم نشود، ربات با موتور rule-based کار می‌کند.

## 🚀 نصب سریع (یک دستور)

```bash
git clone https://github.com/martialpeak/Telegram-Group-Manager.git
cd Telegram-Group-Manager
chmod +x install.sh
./install.sh
```

اسکریپت به‌صورت تعاملی همه مراحل را انجام می‌دهد.

## 📖 نصب دستی (گام به گام)

### گام ۱ — دریافت کد

```bash
git clone https://github.com/martialpeak/Telegram-Group-Manager.git
cd Telegram-Group-Manager
```

### گام ۲ — محیط مجازی پایتون

```bash
python3 --version   # باید 3.11 یا بالاتر باشد

python3 -m venv venv
source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

### گام ۳ — ساخت توکن ربات

۱. در تلگرام به **[@BotFather](https://t.me/BotFather)** پیام دهید
۲. دستور `/newbot` را ارسال کنید
۳. توکن را کپی کنید

**پیدا کردن شناسه تلگرام:**
- به **[@userinfobot](https://t.me/userinfobot)** پیام دهید

### گام ۴ — پیکربندی

```bash
cp .env.example .env
nano .env
```

مقادیر ضروری:

```env
TELEGRAM_BOT_TOKEN=توکن-شما-اینجا
ADMIN_IDS=123456789,987654321
BOT_LANG=fa
GROQ_API_KEY=کلید-groq-شما
GEMINI_API_KEY=کلید-gemini-شما   # اختیاری
```

> ⚠️ فایل `.env` را هرگز در Git کامیت نکنید!

### گام ۵ — اجرای آزمایشی

```bash
source venv/bin/activate
python main.py
```

خروجی موردانتظار:
```
2025-01-01 12:00:00 | INFO | root — ✅ پایگاه داده آماده شد.
2025-01-01 12:00:00 | INFO | root — 🚀 ربات در حال اجرا است.
```

ربات را به گروه اضافه کنید و `/start` بزنید.

### گام ۶ — اجرای دائمی با systemd

```bash
sudo nano /etc/systemd/system/telegram-bot.service
```

```ini
[Unit]
Description=Telegram Group Manager Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=نام_کاربری_لینوکس_شما
WorkingDirectory=/مسیر/Telegram-Group-Manager
ExecStart=/مسیر/Telegram-Group-Manager/venv/bin/python main.py
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
sudo systemctl status telegram-bot
```

## 🔧 مدیریت سرویس

```bash
journalctl -u telegram-bot -f               # لاگ زنده
sudo systemctl restart telegram-bot         # ری‌استارت
sudo systemctl stop telegram-bot            # توقف
sudo systemctl status telegram-bot          # وضعیت
```

## ⚙️ تنظیمات

از داخل تلگرام: `/settings`
یا ویرایش مستقیم `.env` و ری‌استارت ربات:

| متغیر | پیش‌فرض | توضیح |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | توکن از @BotFather |
| `ADMIN_IDS` | — | شناسه ادمین‌ها با کاما |
| `BOT_LANG` | `fa` | زبان: `fa` یا `en` |
| `GROQ_API_KEY` | — | کلید API گروک (AI اصلی) |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | مدل گروک |
| `GEMINI_API_KEY` | — | کلید API جمینی (fallback) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | مدل جمینی |
| `MAX_WARNINGS` | `3` | اخطار قبل از بن |
| `SPAM_TIME_WINDOW` | `60` | بازه اسپم (ثانیه) |
| `SPAM_MAX_MESSAGES` | `5` | پیام در بازه اسپم |
| `MIN_CONFIDENCE` | `0.80` | حداقل اطمینان AI |
| `CACHE_MIN_SCORE` | `0.75` | حداقل شباهت برای cache |
| `LEARNING_ENABLED` | `true` | یادگیری از فیدبک |

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
| `/warnings` | تعداد اخطارها |
| `/mute [دقیقه]` | میوت دستی |
| `/unmute` | رفع میوت |
| `/ban [30m\|2h\|7d] [دلیل]` | بن موقت یا دائم |
| `/unban` | آنبن |
| `/setlevel <سطح>` | تغییر سطح کاربر |
| `/stats` | آمار کامل گروه |
| `/violations` | آمار تخلفات |
| `/reports` | گزارش‌های در انتظر |
| `/search [متن]` | جستجو در تاریخچه |
| `/learn` | یادگیری از فیدبک‌های تأییدشده |
| `/settings` | پنل تنظیمات |

## 🏅 سطح‌بندی کاربران

| سطح | مدیا | لینک/روز | فوروارد/روز | سوال/روز | ارتقاء |
|---|---|---|---|---|---|
| 👤 ساده | ❌ | ۰ | ۰ | ۳ | ۵۰ پیام → برنزی |
| 🥉 برنزی | ✅ | ۵ | ۵ | ۱۰ | دستی |
| 🥈 نقره‌ای | ✅ | ۱۵ | ۱۵ | ۲۵ | دستی |
| 🥇 طلایی | ✅ | ۵۰ | ۵۰ | ۵۰ | دستی |
| 💎 الماسی | ✅ | ∞ | ∞ | ∞ | دستی |

```
/setlevel bronze   — روی پیام کاربر ریپلای بزنید
```

## 🤖 درباره هوش مصنوعی

ربات از یک **زنجیره AI ابری** استفاده می‌کند — نیازی به نصب محلی نیست:

1. **Groq** (اصلی) — سریع‌ترین inference، رایگان ۱۴،۴۰۰ req/day
2. **Gemini** (fallback) — اگر Groq در دسترس نبود فعال می‌شود
3. **موتور rule-based** — همیشه در دسترس، بدون نیاز به API

**مدل‌های Groq پشتیبانی‌شده:**

| مدل | سرعت | توضیح |
|---|---|---|
| `llama-3.1-8b-instant` | ⚡ خیلی سریع | پیش‌فرض، توصیه‌شده |
| `llama-3.3-70b-versatile` | 🚀 سریع | کیفیت بالاتر |
| `mixtral-8x7b-32768` | 🚀 سریع | مناسب فارسی |

**مدل‌های Gemini پشتیبانی‌شده:**

| مدل | توضیح |
|---|---|
| `gemini-2.5-flash` | پیش‌فرض fallback، سریع |
| `gemini-2.0-flash` | جایگزین پایدار |
| `gemini-2.5-pro` | بالاترین کیفیت |

## 🐛 رفع مشکلات رایج

**ربات جواب نمی‌دهد:**
```bash
journalctl -u telegram-bot -n 50 --no-pager
```

**خطای توکن:**
```bash
cat .env
sudo systemctl restart telegram-bot
```

**AI کار نمی‌کند (rule-based فعال است):**
- `GROQ_API_KEY` را در `.env` بررسی کنید
- کلید را در [console.groq.com](https://console.groq.com) تأیید کنید
- `MIN_CONFIDENCE` را به `0.60` کاهش دهید
- در لاگ دنبال `Groq analyze failed` بگردید

**rate limit خوردید:**
- Groq: روزانه ۱۴،۴۰۰ درخواست رایگان
- برای fallback، `GEMINI_API_KEY` را هم تنظیم کنید
- در بدترین حالت، موتور rule-based فعال می‌شود

</div>

---

## 🗂️ Project Structure | ساختار پروژه

```
Telegram-Group-Manager/
├── main.py                    ← entry point
├── config.py                  ← settings from .env
├── i18n.py                    ← Persian / English translations
├── settings_panel.py          ← /settings Telegram panel
├── bot/
│   ├── core/
│   │   ├── ai_analyzer.py     ← Groq/Gemini message analysis
│   │   ├── knowledge_engine.py← cache, search & learning
│   │   ├── moderation.py      ← warn, mute, ban
│   │   └── user_levels.py     ← level definitions
│   ├── db/
│   │   └── database.py        ← SQLite operations
│   ├── handlers/
│   │   ├── commands.py        ← /warn /ban /stats ...
│   │   ├── messages.py        ← text message processing
│   │   ├── callbacks.py       ← inline button handlers
│   │   └── members.py         ← join / leave events
│   └── utils/
│       └── helpers.py         ← shared utility functions
├── requirements.txt
├── .env.example
├── install.sh                 ← interactive installer
└── README.md
```

---

## 📄 License | لایسنس

MIT License — see [LICENSE](LICENSE) for details.
