# 🤖 Telegram Group Manager Bot | ربات هوشمند مدیریت گروه

<div dir="rtl">

**یک ربات پیشرفته مدیریت گروه تلگرام با هوش مصنوعی کاملاً محلی — بدون نیاز به API خارجی.**

</div>

**An advanced Telegram group manager bot powered by fully local AI — no external API required.**

[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)](https://python.org)
[![python-telegram-bot](https://img.shields.io/badge/python--telegram--bot-21.6-blue)](https://python-telegram-bot.org)
[![Ollama](https://img.shields.io/badge/AI-Ollama-black)](https://ollama.ai)
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
| 🧠 AI Analysis | Detects insult / spam / requests using local Ollama |
| 📚 Knowledge Base | Semantic search with local embeddings |
| 🏅 User Levels | 5 tiers with independent permissions |
| ⬆️ Auto Upgrade | simple → bronze after 50 messages |
| ⚠️ Escalating Punishments | Progressive mute and ban steps |
| 📋 Report System | `/report` with admin notification |
| ⚙️ Settings Panel | Full config from inside Telegram |
| 🌐 Bilingual | Persian and English support |
| 🗳️ Community Learning | Community-voted answer corrections |

## 📋 Requirements

| Item | Minimum | Notes |
|---|---|---|
| OS | Ubuntu 20.04 / Debian 11 | Any modern Linux distro |
| Python | **3.11+** | `python3 --version` |
| RAM | **4 GB** (8 GB recommended) | For llama3.1 model |
| Disk | **8 GB** | For AI models |
| Internet | — | Only for initial download |

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

### Step 3 — Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh

# Download AI models
ollama pull llama3.1           # ~4.7 GB — main analysis model
ollama pull nomic-embed-text   # ~274 MB — semantic search model
```

> **Low RAM?** Use `gemma2:2b` (~1.6 GB) instead of `llama3.1`.

### Step 4 — Get a bot token

1. Open Telegram and message **[@BotFather](https://t.me/BotFather)**
2. Send `/newbot`
3. Follow the steps and copy your token

**Find your Telegram user ID:**
- Message **[@userinfobot](https://t.me/userinfobot)** — it replies with your numeric ID

### Step 5 — Configure

```bash
cp .env.example .env
nano .env
```

Fill in the required values:

```env
TELEGRAM_BOT_TOKEN=your_token_here
ADMIN_IDS=123456789,987654321
BOT_LANG=en
AI_MODEL=llama3.1
```

> ⚠️ Never commit `.env` to Git!

### Step 6 — Test run

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

### Step 7 — Run as a system service (auto-start)

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
| `AI_MODEL` | `llama3.1` | Ollama model name |
| `EMBED_MODEL` | `nomic-embed-text` | Embedding model |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server address |
| `MAX_WARNINGS` | `3` | Warnings before ban |
| `SPAM_TIME_WINDOW` | `60` | Spam detection window (seconds) |
| `SPAM_MAX_MESSAGES` | `5` | Max messages in spam window |
| `MIN_CONFIDENCE` | `0.60` | Minimum AI confidence threshold |
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

The bot uses **Ollama** to run language models locally on your server:

- **Message Analysis** — classifies each message as `insult` / `spam` / `request` / `normal`
- **Question Answering** — searches knowledge base first, then generates AI response
- **Learning** — users correct wrong answers; community voting approves them
- **Fallback** — rule-based engine activates if Ollama is unavailable

**Supported models:**

| Model | RAM | Quality | Speed |
|---|---|---|---|
| `llama3.1` | ~4.7 GB | ⭐⭐⭐⭐⭐ | Medium |
| `gemma2:2b` | ~1.6 GB | ⭐⭐⭐ | Fast |
| `phi3` | ~2.3 GB | ⭐⭐⭐⭐ | Fast |
| `mistral` | ~4.1 GB | ⭐⭐⭐⭐ | Medium |

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

**Ollama not working:**
```bash
ollama list
curl http://localhost:11434/api/tags
ollama serve   # manual start
```

**Model not downloaded:**
```bash
ollama pull llama3.1
ollama pull nomic-embed-text
```

**Messages not analyzed (fallback mode active):**
- Make sure Ollama is running
- Check `AI_MODEL` in `.env` matches the pulled model name
- Try lowering `MIN_CONFIDENCE` to `0.40`

---

<a name="فارسی"></a>
# 🇮🇷 فارسی

<div dir="rtl">

## ✨ قابلیت‌ها

| قابلیت | توضیح |
|---|---|
| 🧠 تحلیل هوشمند | شناسایی توهین / اسپم / درخواست با Ollama محلی |
| 📚 پایگاه دانش | جستجوی معنایی با embedding محلی |
| 🏅 سطح‌بندی کاربران | ۵ سطح با محدودیت‌های مستقل |
| ⬆️ ارتقاء خودکار | ساده → برنزی بعد از ۵۰ پیام |
| ⚠️ مجازات پلکانی | میوت و بن با افزایش تدریجی |
| 📋 سیستم گزارش | `/report` با اطلاع‌رسانی به ادمین‌ها |
| ⚙️ پنل تنظیمات | تنظیم کامل از داخل تلگرام |
| 🌐 دو زبانه | پشتیبانی از فارسی و انگلیسی |
| 🗳️ یادگیری جمعی | تصحیح و تأیید جمعی پاسخ‌ها |

## 📋 پیش‌نیازها

| مورد | نسخه حداقل | توضیح |
|---|---|---|
| سیستم‌عامل | Ubuntu 20.04 / Debian 11 | هر توزیع Linux مدرن |
| Python | **3.11+** | `python3 --version` |
| RAM | **4 GB** (8 GB توصیه‌شده) | برای مدل llama3.1 |
| فضای دیسک | **8 GB** | برای مدل‌های AI |
| اینترنت | — | فقط برای دانلود اولیه |

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
# بررسی نسخه Python (باید 3.11 یا بالاتر باشد)
python3 --version

# ساخت محیط مجازی
python3 -m venv venv
source venv/bin/activate

# نصب وابستگی‌ها
pip install --upgrade pip
pip install -r requirements.txt
```

### گام ۳ — نصب Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh

# دانلود مدل‌ها
ollama pull llama3.1           # ~4.7 GB — مدل اصلی
ollama pull nomic-embed-text   # ~274 MB — جستجوی معنایی
```

> **RAM کم دارید؟** به‌جای `llama3.1` از `gemma2:2b` (~1.6 GB) استفاده کنید.

### گام ۴ — ساخت توکن ربات

۱. در تلگرام به **[@BotFather](https://t.me/BotFather)** پیام دهید
۲. دستور `/newbot` را ارسال کنید
۳. مراحل را دنبال کنید و توکن را کپی کنید

**پیدا کردن شناسه تلگرام:**
- به **[@userinfobot](https://t.me/userinfobot)** پیام دهید

### گام ۵ — پیکربندی

```bash
cp .env.example .env
nano .env
```

مقادیر ضروری:

```env
TELEGRAM_BOT_TOKEN=توکن-شما-اینجا
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

خروجی موردانتظار:
```
2025-01-01 12:00:00 | INFO | root — ✅ پایگاه داده آماده شد.
2025-01-01 12:00:00 | INFO | root — 🚀 ربات در حال اجرا است.
```

ربات را به گروه اضافه کنید و `/start` بزنید.

### گام ۷ — اجرای دائمی با systemd

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
| `AI_MODEL` | `llama3.1` | مدل Ollama |
| `EMBED_MODEL` | `nomic-embed-text` | مدل embedding |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | آدرس سرور Ollama |
| `MAX_WARNINGS` | `3` | اخطار قبل از بن |
| `SPAM_TIME_WINDOW` | `60` | بازه اسپم (ثانیه) |
| `SPAM_MAX_MESSAGES` | `5` | پیام در بازه اسپم |
| `MIN_CONFIDENCE` | `0.60` | حداقل اطمینان AI |
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

| مدل | RAM | کیفیت | سرعت |
|---|---|---|---|
| `llama3.1` | ~4.7 GB | ⭐⭐⭐⭐⭐ | متوسط |
| `gemma2:2b` | ~1.6 GB | ⭐⭐⭐ | سریع |
| `phi3` | ~2.3 GB | ⭐⭐⭐⭐ | سریع |
| `mistral` | ~4.1 GB | ⭐⭐⭐⭐ | متوسط |

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

**Ollama کار نمی‌کند:**
```bash
ollama list
curl http://localhost:11434/api/tags
ollama serve
```

**مدل دانلود نشده:**
```bash
ollama pull llama3.1
ollama pull nomic-embed-text
```

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
│   │   ├── ai_analyzer.py     ← Ollama message analysis
│   │   ├── knowledge_engine.py← search & learning
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
