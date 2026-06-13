#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#   Telegram Group Manager Bot — Interactive Installer v2.1
#   Supports: Ubuntu 20.04+ / Debian 11+ / Raspberry Pi OS
#   Bilingual: English / Finglish
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# ── رنگ‌ها ────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[ OK ]${NC}  $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error()   { echo -e "${RED}[FAIL]${NC}  $1"; exit 1; }
ask()     { echo -e "${CYAN}[ ?? ]${NC}  $1"; }
banner()  { echo -e "\n${BOLD}── $1 ──${NC}"; }

BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="telegram-bot"
ENV_FILE="$BOT_DIR/.env"
LOG_FILE="$BOT_DIR/install.log"

# ── لاگ همه خروجی‌ها ─────────────────────────────────────────
exec > >(tee -a "$LOG_FILE") 2>&1

# ── تابع prompt ──────────────────────────────────────────────
prompt() {
    local var_name="$1" prompt_text="$2" default_val="${3:-}" secret="${4:-}"
    if [ -n "$default_val" ]; then
        ask "$prompt_text [پیش‌فرض / default: $default_val]:"
    else
        ask "$prompt_text:"
    fi
    if [ "$secret" = "secret" ]; then
        read -rs value; echo ""
    else
        read -r value
    fi
    [ -z "$value" ] && value="$default_val"
    eval "$var_name='$value'"
}

# ══════════════════════════════════════════════════════════════
#  انتخاب زبان / Language Selection
# ══════════════════════════════════════════════════════════════
clear
echo -e "${BOLD}${BLUE}"
echo "╔════════════════════════════════════════════════════╗"
echo "║    Telegram Group Manager Bot — Installer v2.1    ║"
echo "╚════════════════════════════════════════════════════╝"
echo -e "${NC}"
echo ""
echo -e "  Select installer language / زبان نصب را انتخاب کنید:"
echo ""
echo -e "    ${CYAN}1)${NC} فارسی  (Persian)"
echo -e "    ${CYAN}2)${NC} English"
echo ""
ask "انتخاب / Choice [1/2]:"
read -r LANG_CHOICE
[[ "$LANG_CHOICE" == "2" ]] && LANG="en" || LANG="fa"

# ══════════════════════════════════════════════════════════════
#  جدول رشته‌ها / String Table
# ══════════════════════════════════════════════════════════════
if [ "$LANG" = "fa" ]; then
    S_STEP1="مرحله ۱: بررسی پایتون"
    S_PY_INSTALL="پایتون ۳ پیدا نشد — در حال نصب..."
    S_PY_OK="Python %s پیدا شد ✓"
    S_PY_ERR="Python 3.11+ لازم است (نسخه فعلی: %s). لطفاً Python را ارتقاء دهید."

    S_STEP2="مرحله ۲: پیکربندی ربات"
    S_TOKEN_TIP="چطور توکن بگیریم:"
    S_TOKEN_TIP1="  ۱. در تلگرام به @BotFather پیام دهید"
    S_TOKEN_TIP2="  ۲. دستور /newbot را ارسال کنید"
    S_TOKEN_TIP3="  ۳. توکن دریافتی را اینجا وارد کنید"
    S_TOKEN_PROMPT="توکن ربات تلگرام"
    S_TOKEN_ERR="توکن ربات اجباری است!"

    S_ADMIN_TIP="چطور شناسه تلگرام خود را پیدا کنید:"
    S_ADMIN_TIP1="  به @userinfobot پیام دهید — شناسه عددی شما را برمی‌گرداند"
    S_ADMIN_PROMPT="شناسه ادمین‌ها (چند تا با کاما جدا کنید)"
    S_ADMIN_ERR="حداقل یک شناسه ادمین لازم است!"

    S_MODEL_TIP="مدل هوش مصنوعی را انتخاب کنید:"
    S_MODEL_1="1) llama3.1     — کیفیت خوب      (~4.7 GB RAM)"
    S_MODEL_2="2) gemma2:2b    — سبک‌تر          (~1.6 GB RAM)"
    S_MODEL_3="3) phi3         — سریع‌تر          (~2.3 GB RAM)"
    S_MODEL_4="4) mistral      — متوازن           (~4.1 GB RAM)"
    S_MODEL_5="5) دستی         — خودت نام بنویس"
    S_MODEL_PROMPT="شماره مدل"
    S_MODEL_CUSTOM="نام مدل را وارد کن (مثلاً llama3.1:8b)"

    S_MOD_HEAD="تنظیمات مدیریت گروه:"
    S_WARN_PROMPT="حداکثر اخطار قبل از بن"
    S_WIN_PROMPT="بازه زمانی تشخیص اسپم (ثانیه)"
    S_SPAM_PROMPT="حداکثر پیام در بازه اسپم"
    S_CONF_PROMPT="حداقل اطمینان هوش مصنوعی (0.0 تا 1.0)"

    S_LANG_TIP="زبان پیام‌های ربات در تلگرام:"
    S_LANG_1="1) فارسی"
    S_LANG_2="2) English"
    S_LANG_PROMPT="انتخاب"

    S_SUM_HEAD="خلاصه تنظیمات:"
    S_CONTINUE="ادامه می‌دهیم؟ [Y/n]"
    S_ABORT="لغو شد."

    S_STEP3="مرحله ۳: محیط مجازی پایتون"
    S_VENV_NEW="محیط مجازی ساخته شد"
    S_VENV_EXISTS="محیط مجازی از قبل وجود دارد — رد شد"
    S_DEPS_OK="وابستگی‌ها نصب شدند"

    S_STEP4="مرحله ۴: ذخیره فایل تنظیمات"
    S_ENV_OK="فایل .env ذخیره شد"

    S_STEP5="مرحله ۵: Ollama (موتور هوش مصنوعی محلی)"
    S_OLL_INSTALL="در حال نصب Ollama..."
    S_OLL_OK="Ollama نصب شد"
    S_OLL_EXISTS="Ollama از قبل نصب است"
    S_OLL_RUNNING="سرویس Ollama در حال اجراست"
    S_OLL_START="سرویس Ollama را راه‌اندازی می‌کنیم..."
    S_MODEL_PULL="در حال دانلود مدل %s (چند دقیقه طول می‌کشد)..."
    S_MODEL_OK="مدل '%s' آماده است ✓"
    S_MODEL_FAIL="دانلود '%s' ناموفق بود. دستی اجرا کن: ollama pull %s"
    S_EMBED_PULL="در حال دانلود مدل embedding..."
    S_EMBED_OK="مدل embedding آماده است ✓"
    S_EMBED_FAIL="دانلود embedding ناموفق. دستی اجرا کن: ollama pull nomic-embed-text"

    S_STEP6="مرحله ۶: سرویس systemd (اجرای خودکار با بوت)"
    S_SVC_OK="سرویس ربات با موفقیت شروع شد ✓"
    S_SVC_FAIL="سرویس شروع نشد. لاگ را بررسی کن:"

    S_DONE_HEAD="نصب تمام شد! 🎉"
    S_DONE_1="مشاهده لاگ زنده:"
    S_DONE_2="ری‌استارت ربات:"
    S_DONE_3="استاپ ربات:"
    S_DONE_4="ویرایش تنظیمات:"
    S_DONE_5="در تلگرام (فقط ادمین):"
    S_DONE_NOTE="نکته: بعد از ویرایش دستی .env ربات را ری‌استارت کنید"
else
    S_STEP1="Step 1: Python"
    S_PY_INSTALL="python3 not found — installing..."
    S_PY_OK="Python %s found ✓"
    S_PY_ERR="Python 3.11+ is required (found: %s). Please upgrade Python."

    S_STEP2="Step 2: Bot Configuration"
    S_TOKEN_TIP="How to get a bot token:"
    S_TOKEN_TIP1="  1. Open Telegram and message @BotFather"
    S_TOKEN_TIP2="  2. Send: /newbot"
    S_TOKEN_TIP3="  3. Copy the token and paste it here"
    S_TOKEN_PROMPT="Telegram bot token"
    S_TOKEN_ERR="Bot token is required!"

    S_ADMIN_TIP="How to find your Telegram user ID:"
    S_ADMIN_TIP1="  Message @userinfobot — it replies with your numeric ID"
    S_ADMIN_PROMPT="Admin Telegram ID(s) — separate multiple with commas"
    S_ADMIN_ERR="At least one admin ID is required!"

    S_MODEL_TIP="Choose an AI model:"
    S_MODEL_1="1) llama3.1     — good quality    (~4.7 GB RAM)"
    S_MODEL_2="2) gemma2:2b    — lightweight     (~1.6 GB RAM)"
    S_MODEL_3="3) phi3         — fast            (~2.3 GB RAM)"
    S_MODEL_4="4) mistral      — balanced        (~4.1 GB RAM)"
    S_MODEL_5="5) custom       — enter manually"
    S_MODEL_PROMPT="Model choice"
    S_MODEL_CUSTOM="Enter model name (e.g. llama3.1:8b)"

    S_MOD_HEAD="Moderation settings:"
    S_WARN_PROMPT="Max warnings before ban"
    S_WIN_PROMPT="Spam detection window (seconds)"
    S_SPAM_PROMPT="Max messages in spam window"
    S_CONF_PROMPT="AI confidence threshold (0.0 to 1.0)"

    S_LANG_TIP="Bot message language in Telegram:"
    S_LANG_1="1) Persian / Farsi"
    S_LANG_2="2) English"
    S_LANG_PROMPT="Choice"

    S_SUM_HEAD="Configuration summary:"
    S_CONTINUE="Continue with installation? [Y/n]"
    S_ABORT="Aborted."

    S_STEP3="Step 3: Python virtual environment"
    S_VENV_NEW="Virtual environment created"
    S_VENV_EXISTS="Virtual environment already exists — skipped"
    S_DEPS_OK="Python dependencies installed"

    S_STEP4="Step 4: Writing configuration file"
    S_ENV_OK="Configuration saved to .env"

    S_STEP5="Step 5: Ollama (local AI engine)"
    S_OLL_INSTALL="Installing Ollama..."
    S_OLL_OK="Ollama installed"
    S_OLL_EXISTS="Ollama already installed"
    S_OLL_RUNNING="Ollama service is running"
    S_OLL_START="Starting Ollama service..."
    S_MODEL_PULL="Pulling model: %s  (this may take several minutes)..."
    S_MODEL_OK="Model '%s' ready ✓"
    S_MODEL_FAIL="Failed to pull '%s'. Run manually: ollama pull %s"
    S_EMBED_PULL="Pulling embedding model: nomic-embed-text..."
    S_EMBED_OK="Embedding model ready ✓"
    S_EMBED_FAIL="Failed to pull embedding model. Run: ollama pull nomic-embed-text"

    S_STEP6="Step 6: System service (auto-start on boot)"
    S_SVC_OK="Bot service started successfully ✓"
    S_SVC_FAIL="Service failed to start. Check logs:"

    S_DONE_HEAD="Installation complete! 🎉"
    S_DONE_1="View live logs:"
    S_DONE_2="Restart bot:"
    S_DONE_3="Stop bot:"
    S_DONE_4="Edit config:"
    S_DONE_5="In Telegram (admin only):"
    S_DONE_NOTE="Note: restart the bot after editing .env manually"
fi

# ══════════════════════════════════════════════════════════════
#  مرحله ۱ / Step 1 — Python
# ══════════════════════════════════════════════════════════════
banner "$S_STEP1"

if ! command -v python3 &>/dev/null; then
    info "$S_PY_INSTALL"
    sudo apt-get update -q
    sudo apt-get install -y python3 python3-pip python3-venv git curl
fi

PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if python3 -c 'import sys; exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
    success "$(printf "$S_PY_OK" "$PY_VER")"
else
    error "$(printf "$S_PY_ERR" "$PY_VER")"
fi

# ══════════════════════════════════════════════════════════════
#  مرحله ۲ / Step 2 — پیکربندی
# ══════════════════════════════════════════════════════════════
banner "$S_STEP2"

# ── توکن ────────────────────────────────────────────────────
echo ""
echo -e "  ${YELLOW}$S_TOKEN_TIP${NC}"
echo "$S_TOKEN_TIP1"
echo "$S_TOKEN_TIP2"
echo "$S_TOKEN_TIP3"
echo ""
prompt BOT_TOKEN "$S_TOKEN_PROMPT" "" "secret"
[ -z "$BOT_TOKEN" ] && error "$S_TOKEN_ERR"

# ── ادمین ────────────────────────────────────────────────────
echo ""
echo -e "  ${YELLOW}$S_ADMIN_TIP${NC}"
echo "$S_ADMIN_TIP1"
echo ""
prompt ADMIN_IDS "$S_ADMIN_PROMPT" "" ""
[ -z "$ADMIN_IDS" ] && error "$S_ADMIN_ERR"

# اعتبارسنجی: فقط اعداد و کاما
if ! echo "$ADMIN_IDS" | grep -qE '^[0-9]+(,[0-9]+)*$'; then
    error "Admin IDs must be numbers separated by commas (e.g. 123456789,987654321)"
fi

# ── مدل AI ──────────────────────────────────────────────────
echo ""
echo -e "  ${YELLOW}$S_MODEL_TIP${NC}"
echo "    $S_MODEL_1"
echo "    $S_MODEL_2"
echo "    $S_MODEL_3"
echo "    $S_MODEL_4"
echo "    $S_MODEL_5"
echo ""
prompt MODEL_CHOICE "$S_MODEL_PROMPT" "1" ""
case "$MODEL_CHOICE" in
    1) AI_MODEL="llama3.1"  ;;
    2) AI_MODEL="gemma2:2b" ;;
    3) AI_MODEL="phi3"      ;;
    4) AI_MODEL="mistral"   ;;
    5) prompt AI_MODEL "$S_MODEL_CUSTOM" "llama3.1" "" ;;
    *) AI_MODEL="$MODEL_CHOICE" ;;   # عدد دیگری = نام مدل مستقیم
esac

# ── تنظیمات مدیریت ──────────────────────────────────────────
echo ""
echo -e "  ${YELLOW}$S_MOD_HEAD${NC}"
prompt MAX_WARNINGS "$S_WARN_PROMPT" "3"    ""
prompt SPAM_WINDOW  "$S_WIN_PROMPT"  "60"   ""
prompt SPAM_MAX     "$S_SPAM_PROMPT" "5"    ""
prompt MIN_CONF     "$S_CONF_PROMPT" "0.60" ""

# اعتبارسنجی مقادیر عددی
[[ "$MAX_WARNINGS" =~ ^[0-9]+$ ]] || error "Max warnings must be a positive integer"
[[ "$SPAM_WINDOW"  =~ ^[0-9]+$ ]] || error "Spam window must be a positive integer"
[[ "$SPAM_MAX"     =~ ^[0-9]+$ ]] || error "Spam max must be a positive integer"
python3 -c "v=float('$MIN_CONF'); exit(0 if 0.0<=v<=1.0 else 1)" 2>/dev/null \
    || error "AI confidence must be between 0.0 and 1.0"

# ── زبان ────────────────────────────────────────────────────
echo ""
echo -e "  ${YELLOW}$S_LANG_TIP${NC}"
echo "    $S_LANG_1"
echo "    $S_LANG_2"
echo ""
prompt BOT_LANG_CHOICE "$S_LANG_PROMPT" "1" ""
case "$BOT_LANG_CHOICE" in
    2) BOT_LANG="en" ;;
    *) BOT_LANG="fa" ;;
esac

# ── خلاصه ───────────────────────────────────────────────────
echo ""
echo -e "${GREEN}┌──────────────────────────────────────────────────────┐${NC}"
echo -e "${GREEN}│  ${BOLD}$S_SUM_HEAD${NC}${GREEN}$(printf ' %.0s' {1..60} | head -c $((53-${#S_SUM_HEAD})))│${NC}"
echo -e "${GREEN}├──────────────────────────────────────────────────────┤${NC}"
printf "${GREEN}│${NC}  Token          : %s...\n"  "${BOT_TOKEN:0:15}"
printf "${GREEN}│${NC}  Admin IDs      : %s\n"     "$ADMIN_IDS"
printf "${GREEN}│${NC}  AI Model       : %s\n"     "$AI_MODEL"
printf "${GREEN}│${NC}  Max Warnings   : %s\n"     "$MAX_WARNINGS"
printf "${GREEN}│${NC}  Spam Window    : %s sec\n" "$SPAM_WINDOW"
printf "${GREEN}│${NC}  Spam Limit     : %s msg\n" "$SPAM_MAX"
printf "${GREEN}│${NC}  AI Confidence  : %s\n"     "$MIN_CONF"
printf "${GREEN}│${NC}  Bot Language   : %s\n"     "$BOT_LANG"
echo -e "${GREEN}└──────────────────────────────────────────────────────┘${NC}"
echo ""
ask "$S_CONTINUE"
read -r CONFIRM
[[ "${CONFIRM:-Y}" =~ ^[Nn] ]] && { echo "$S_ABORT"; exit 0; }

# ══════════════════════════════════════════════════════════════
#  مرحله ۳ / Step 3 — محیط مجازی پایتون
# ══════════════════════════════════════════════════════════════
banner "$S_STEP3"

if [ ! -d "$BOT_DIR/venv" ]; then
    python3 -m venv "$BOT_DIR/venv"
    success "$S_VENV_NEW"
else
    warn "$S_VENV_EXISTS"
fi

source "$BOT_DIR/venv/bin/activate"
pip install --quiet --upgrade pip wheel
pip install --quiet -r "$BOT_DIR/requirements.txt"
success "$S_DEPS_OK"

# ══════════════════════════════════════════════════════════════
#  مرحله ۴ / Step 4 — ذخیره .env
# ══════════════════════════════════════════════════════════════
banner "$S_STEP4"

# اگه .env قبلی وجود داره backup بگیر
if [ -f "$ENV_FILE" ]; then
    cp "$ENV_FILE" "${ENV_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
    warn "Existing .env backed up"
fi

cat > "$ENV_FILE" <<EOF
# Generated by install.sh — $(date '+%Y-%m-%d %H:%M:%S')
# DO NOT commit this file to git!

# ── تلگرام ──────────────────────────────────────────
TELEGRAM_BOT_TOKEN=${BOT_TOKEN}
ADMIN_IDS=${ADMIN_IDS}
BOT_LANG=${BOT_LANG}

# ── هوش مصنوعی ──────────────────────────────────────
AI_MODEL=${AI_MODEL}
EMBED_MODEL=nomic-embed-text
OLLAMA_BASE_URL=http://localhost:11434

# ── مدیریت گروه ─────────────────────────────────────
MAX_WARNINGS=${MAX_WARNINGS}
SPAM_TIME_WINDOW=${SPAM_WINDOW}
SPAM_MAX_MESSAGES=${SPAM_MAX}
MIN_CONFIDENCE=${MIN_CONF}

# ── یادگیری ─────────────────────────────────────────
LEARNING_ENABLED=true
LEARNING_MIN_SCORE=0.75
SEARCH_TOP_K=5
EOF

chmod 600 "$ENV_FILE"
success "$S_ENV_OK"

# ══════════════════════════════════════════════════════════════
#  مرحله ۵ / Step 5 — Ollama
# ══════════════════════════════════════════════════════════════
banner "$S_STEP5"

if ! command -v ollama &>/dev/null; then
    info "$S_OLL_INSTALL"
    curl -fsSL https://ollama.com/install.sh | sh
    success "$S_OLL_OK"
else
    OLLAMA_VER=$(ollama --version 2>/dev/null | head -1 || echo "unknown")
    success "$S_OLL_EXISTS ($OLLAMA_VER)"
fi

# اطمینان از اجرای سرویس Ollama
if ! pgrep -x ollama &>/dev/null; then
    info "$S_OLL_START"
    if systemctl is-enabled ollama &>/dev/null 2>&1; then
        sudo systemctl start ollama
    else
        ollama serve &>/dev/null &
        sleep 3
    fi
fi
success "$S_OLL_RUNNING"

# دانلود مدل اصلی
echo ""
info "$(printf "$S_MODEL_PULL" "$AI_MODEL")"
if ollama pull "$AI_MODEL"; then
    success "$(printf "$S_MODEL_OK" "$AI_MODEL")"
else
    warn "$(printf "$S_MODEL_FAIL" "$AI_MODEL" "$AI_MODEL")"
fi

# دانلود مدل embedding
echo ""
info "$S_EMBED_PULL"
if ollama pull nomic-embed-text; then
    success "$S_EMBED_OK"
else
    warn "$S_EMBED_FAIL"
fi

# ══════════════════════════════════════════════════════════════
#  مرحله ۶ / Step 6 — systemd service
# ══════════════════════════════════════════════════════════════
banner "$S_STEP6"

CURRENT_USER=$(whoami)
VENV_PYTHON="$BOT_DIR/venv/bin/python"

sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null <<UNIT
[Unit]
Description=Telegram Group Manager Bot
Documentation=https://github.com/yourusername/telegram-group-manager
After=network-online.target ollama.service
Wants=network-online.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${BOT_DIR}
ExecStart=${VENV_PYTHON} ${BOT_DIR}/main.py
Restart=on-failure
RestartSec=10
StartLimitInterval=60
StartLimitBurst=3
StandardOutput=journal
StandardError=journal
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"
sleep 3

if systemctl is-active --quiet "${SERVICE_NAME}"; then
    success "$S_SVC_OK"
else
    warn "$S_SVC_FAIL"
    echo ""
    echo "    journalctl -u ${SERVICE_NAME} -n 50 --no-pager"
    echo ""
fi

# ══════════════════════════════════════════════════════════════
#  پایان / Done
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   ${BOLD}$S_DONE_HEAD${NC}${GREEN}$(printf ' %.0s' {1..60} | head -c $((52-${#S_DONE_HEAD})))║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${CYAN}$S_DONE_1${NC}"
echo    "    journalctl -u ${SERVICE_NAME} -f"
echo ""
echo -e "  ${CYAN}$S_DONE_2${NC}"
echo    "    sudo systemctl restart ${SERVICE_NAME}"
echo ""
echo -e "  ${CYAN}$S_DONE_3${NC}"
echo    "    sudo systemctl stop ${SERVICE_NAME}"
echo ""
echo -e "  ${CYAN}$S_DONE_4${NC}"
echo    "    nano ${ENV_FILE}"
echo ""
echo -e "  ${CYAN}$S_DONE_5${NC}"
echo    "    /settings  — تغییر تنظیمات از داخل تلگرام"
echo    "    /stats     — آمار گروه"
echo    "    /reports   — گزارش‌های در انتظر"
echo ""
echo -e "${YELLOW}  ⚠  $S_DONE_NOTE${NC}"
echo ""
echo -e "  📄 Install log saved to: ${LOG_FILE}"
echo ""
