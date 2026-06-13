#!/usr/bin/env bash
# ===================================================================
#   Telegram Group Manager Bot -- Interactive Installer v3.1
#   AI: Groq (primary, 14400/day free) + Gemini (optional fallback)
#   Supports: Ubuntu 20.04+ / Debian 11+
#   Bilingual: English / Finglish
# ===================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[ OK ]${NC}  $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error()   { echo -e "${RED}[FAIL]${NC}  $1"; exit 1; }
ask()     { echo -e "${CYAN}[ ?? ]${NC}  $1"; }
banner()  { echo -e "\n${BOLD}-- $1 --${NC}"; }

BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="telegram-bot"
ENV_FILE="$BOT_DIR/.env"
LOG_FILE="$BOT_DIR/install.log"

exec > >(tee -a "$LOG_FILE") 2>&1

prompt() {
    local var_name="$1" prompt_text="$2" default_val="${3:-}" secret="${4:-}"
    if [ -n "$default_val" ]; then
        ask "$prompt_text [default: $default_val]:"
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

# ===================================================================
#  Language Selection
# ===================================================================
clear
echo -e "${BOLD}${BLUE}"
echo "+====================================================+"
echo "|   Telegram Group Manager Bot -- Installer v3.1    |"
echo "|   AI: Groq (free) + Gemini (optional fallback)    |"
echo "+====================================================+"
echo -e "${NC}"
echo ""
echo "  Select installer language:"
echo ""
echo -e "    ${CYAN}1)${NC} Finglish  (Persian)"
echo -e "    ${CYAN}2)${NC} English"
echo ""
ask "Choice [1/2]:"
read -r LANG_CHOICE
[[ "$LANG_CHOICE" == "2" ]] && LANG="en" || LANG="fa"

# ===================================================================
#  String Table
# ===================================================================
if [ "$LANG" = "fa" ]; then
    S_STEP1="Marhale 1: Barresi Python"
    S_PY_INSTALL="Python 3 peyda nashod -- dar hal nasb..."
    S_PY_OK="Python %s peyda shod"
    S_PY_UPGRADE="Python %s peyda shod -- dar hal nasb Python 3.11..."
    S_PY_UPGRADE_OK="Python 3.11 nasb shod"
    S_PY_UPGRADE_FAIL="Nasb Python 3.11 namovaghagh shod. Dasti upgrade kon."

    S_STEP2="Marhale 2: Pikar-bandi Robot"
    S_TOKEN_TIP="Chetori token begirim:"
    S_TOKEN_TIP1="  1. Dar Telegram be @BotFather payam bedid"
    S_TOKEN_TIP2="  2. Dastur /newbot ra ersal konid"
    S_TOKEN_TIP3="  3. Token ra copy va inja paste konid"
    S_TOKEN_PROMPT="Token robot Telegram"
    S_TOKEN_ERR="Token robot ejbari ast!"

    S_ADMIN_TIP="Chetori ID Telegram peyda konid:"
    S_ADMIN_TIP1="  Be @userinfobot payam bedid"
    S_ADMIN_PROMPT="ID admin-ha (ba comma joda konid)"
    S_ADMIN_ERR="Haddaghal yek ID admin lazem ast!"

    S_GROQ_TIP="Groq API Key (RAIGAN -- 14400 darkhast/ruz):"
    S_GROQ_TIP1="  1. Berid be: https://console.groq.com"
    S_GROQ_TIP2="  2. Register ya login konid (raigan)"
    S_GROQ_TIP3="  3. API Keys --> Create API Key"
    S_GROQ_TIP4="  4. Key ra copy va inja paste konid"
    S_GROQ_PROMPT="Groq API Key"
    S_GROQ_ERR="Groq API Key ejbari ast!"

    S_GROQ_MODEL_TIP="Model Groq ra entekhab konid:"
    S_GROQ_M1="1) llama-3.1-8b-instant   -- saritar, pishnahad (raigan)"
    S_GROQ_M2="2) llama-3.3-70b-versatile -- keyfiyat balatr (raigan)"
    S_GROQ_M3="3) gemma2-9b-it            -- motavazen (raigan)"
    S_GROQ_MODEL_PROMPT="Shomare model"

    S_GEMINI_HEAD="Gemini API Key (EKHTIYARI -- fallback dar surat khatay Groq):"
    S_GEMINI_TIP1="  Agar mikhahid Gemini ham dasha bashid:"
    S_GEMINI_TIP2="  https://aistudio.google.com/apikey"
    S_GEMINI_PROMPT="Gemini API Key (Enter = rads kardan)"
    S_GEMINI_SKIP="Gemini rad shod -- faghat Groq estefade mishavad"
    S_GEMINI_OK="Gemini ham tanzim shod -- dar surat khatay Groq estefade mishavad"

    S_MOD_HEAD="Tanzimate modiriyat geruh:"
    S_WARN_PROMPT="Haddaksar akhtar ghabl az ban"
    S_WIN_PROMPT="Baze zamani tashkhis spam (sanie)"
    S_SPAM_PROMPT="Haddaksar payam dar baze spam"
    S_CONF_PROMPT="Haddaghal etminan AI (0.0 ta 1.0)"

    S_LANG_TIP="Zaban payam-haye robot:"
    S_LANG_1="1) Farsi"
    S_LANG_2="2) English"
    S_LANG_PROMPT="Entekhab"

    S_SUM_HEAD="Kholase tanzimate:"
    S_CONTINUE="Edame midahim? [Y/n]"
    S_ABORT="Laghv shod."

    S_STEP3="Marhale 3: Mohit majazi Python"
    S_VENV_NEW="Mohit majazi sakhte shod"
    S_VENV_EXISTS="Mohit majazi az ghabl vojud darad"
    S_DEPS_OK="Vabastegi-ha nasb shodand"

    S_STEP4="Marhale 4: Zakhire tanzimate"
    S_ENV_OK="File .env zakhire shod"

    S_STEP5="Marhale 5: Servis systemd"
    S_SVC_OK="Servis robot shoroo shod"
    S_SVC_FAIL="Servis shoroo nashod. Log barresi kon:"

    S_DONE_HEAD="Nasb tamam shod!"
    S_DONE_1="Log zende:"
    S_DONE_2="Restart:"
    S_DONE_3="Stop:"
    S_DONE_4="Virayesh .env:"
    S_DONE_5="Dar Telegram:"
    S_DONE_NOTE="Nakte: bad az virayesh .env robot ra restart konid"
else
    S_STEP1="Step 1: Python"
    S_PY_INSTALL="python3 not found -- installing..."
    S_PY_OK="Python %s found"
    S_PY_UPGRADE="Python %s found -- installing Python 3.11..."
    S_PY_UPGRADE_OK="Python 3.11 installed"
    S_PY_UPGRADE_FAIL="Failed to install Python 3.11. Please upgrade manually."

    S_STEP2="Step 2: Bot Configuration"
    S_TOKEN_TIP="How to get your bot token:"
    S_TOKEN_TIP1="  1. Message @BotFather on Telegram"
    S_TOKEN_TIP2="  2. Send: /newbot"
    S_TOKEN_TIP3="  3. Copy the token and paste it here"
    S_TOKEN_PROMPT="Telegram bot token"
    S_TOKEN_ERR="Bot token is required!"

    S_ADMIN_TIP="How to find your Telegram user ID:"
    S_ADMIN_TIP1="  Message @userinfobot -- it replies with your numeric ID"
    S_ADMIN_PROMPT="Admin Telegram ID(s) -- separate multiple with commas"
    S_ADMIN_ERR="At least one admin ID is required!"

    S_GROQ_TIP="Groq API Key (FREE -- 14,400 requests/day):"
    S_GROQ_TIP1="  1. Go to: https://console.groq.com"
    S_GROQ_TIP2="  2. Register or login (free)"
    S_GROQ_TIP3="  3. API Keys --> Create API Key"
    S_GROQ_TIP4="  4. Copy the key and paste it here"
    S_GROQ_PROMPT="Groq API Key"
    S_GROQ_ERR="Groq API Key is required!"

    S_GROQ_MODEL_TIP="Choose Groq model:"
    S_GROQ_M1="1) llama-3.1-8b-instant    -- fastest, recommended (free)"
    S_GROQ_M2="2) llama-3.3-70b-versatile -- better quality (free)"
    S_GROQ_M3="3) gemma2-9b-it             -- balanced (free)"
    S_GROQ_MODEL_PROMPT="Model choice"

    S_GEMINI_HEAD="Gemini API Key (OPTIONAL -- fallback if Groq fails):"
    S_GEMINI_TIP1="  If you want Gemini as backup:"
    S_GEMINI_TIP2="  https://aistudio.google.com/apikey"
    S_GEMINI_PROMPT="Gemini API Key (Enter = skip)"
    S_GEMINI_SKIP="Gemini skipped -- using Groq only"
    S_GEMINI_OK="Gemini configured -- will be used if Groq fails"

    S_MOD_HEAD="Moderation settings:"
    S_WARN_PROMPT="Max warnings before ban"
    S_WIN_PROMPT="Spam detection window (seconds)"
    S_SPAM_PROMPT="Max messages in spam window"
    S_CONF_PROMPT="AI confidence threshold (0.0 to 1.0)"

    S_LANG_TIP="Bot message language:"
    S_LANG_1="1) Persian / Farsi"
    S_LANG_2="2) English"
    S_LANG_PROMPT="Choice"

    S_SUM_HEAD="Configuration summary:"
    S_CONTINUE="Continue with installation? [Y/n]"
    S_ABORT="Aborted."

    S_STEP3="Step 3: Python virtual environment"
    S_VENV_NEW="Virtual environment created"
    S_VENV_EXISTS="Virtual environment already exists -- skipped"
    S_DEPS_OK="Python dependencies installed"

    S_STEP4="Step 4: Writing configuration"
    S_ENV_OK="Configuration saved to .env"

    S_STEP5="Step 5: System service"
    S_SVC_OK="Bot service started successfully"
    S_SVC_FAIL="Service failed to start. Check logs:"

    S_DONE_HEAD="Installation complete!"
    S_DONE_1="View live logs:"
    S_DONE_2="Restart bot:"
    S_DONE_3="Stop bot:"
    S_DONE_4="Edit config:"
    S_DONE_5="In Telegram (admin only):"
    S_DONE_NOTE="Note: restart the bot after editing .env manually"
fi

# ===================================================================
#  Step 1 -- Python
# ===================================================================
banner "$S_STEP1"

if ! command -v python3 &>/dev/null; then
    info "$S_PY_INSTALL"
    sudo apt-get update -q
    sudo apt-get install -y python3 python3-pip python3-venv git curl
fi

PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')

_install_python311() {
    if ! command -v add-apt-repository &>/dev/null; then
        sudo apt-get install -y software-properties-common &>/dev/null || true
    fi
    sudo add-apt-repository -y ppa:deadsnakes/ppa 2>/dev/null || true
    sudo apt-get update -q
    sudo apt-get install -y python3.11 python3.11-venv python3.11-dev curl git
    curl -sS https://bootstrap.pypa.io/get-pip.py | sudo python3.11 2>/dev/null || \
        sudo apt-get install -y python3.11-distutils 2>/dev/null || true
    if python3.11 -c 'import sys; exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
        success "$S_PY_UPGRADE_OK"; return 0
    else
        return 1
    fi
}

PY_BIN="python3"
if python3 -c 'import sys; exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
    success "$(printf "$S_PY_OK" "$PY_VER")"
else
    warn "$(printf "$S_PY_UPGRADE" "$PY_VER")"
    if _install_python311; then
        PY_BIN="python3.11"; PY_VER="3.11"
    elif command -v python3.11 &>/dev/null; then
        PY_BIN="python3.11"; PY_VER="3.11"
        success "$S_PY_UPGRADE_OK"
    else
        echo -e "${RED}[FAIL]${NC}  $S_PY_UPGRADE_FAIL" >&2; exit 1
    fi
fi

# ===================================================================
#  Step 2 -- Configuration
# ===================================================================
banner "$S_STEP2"

# Telegram Token
echo ""
echo -e "  ${YELLOW}$S_TOKEN_TIP${NC}"
echo "$S_TOKEN_TIP1"
echo "$S_TOKEN_TIP2"
echo "$S_TOKEN_TIP3"
echo ""
prompt BOT_TOKEN "$S_TOKEN_PROMPT" "" "secret"
[ -z "$BOT_TOKEN" ] && error "$S_TOKEN_ERR"

# Admin IDs
echo ""
echo -e "  ${YELLOW}$S_ADMIN_TIP${NC}"
echo "$S_ADMIN_TIP1"
echo ""
prompt ADMIN_IDS "$S_ADMIN_PROMPT" "" ""
[ -z "$ADMIN_IDS" ] && error "$S_ADMIN_ERR"
if ! echo "$ADMIN_IDS" | grep -qE '^[0-9]+(,[0-9]+)*$'; then
    error "Admin IDs must be numbers separated by commas"
fi

# Groq API Key (required)
echo ""
echo -e "  ${YELLOW}$S_GROQ_TIP${NC}"
echo "$S_GROQ_TIP1"
echo "$S_GROQ_TIP2"
echo "$S_GROQ_TIP3"
echo "$S_GROQ_TIP4"
echo ""
prompt GROQ_API_KEY "$S_GROQ_PROMPT" "" "secret"
[ -z "$GROQ_API_KEY" ] && error "$S_GROQ_ERR"

# Groq Model
echo ""
echo -e "  ${YELLOW}$S_GROQ_MODEL_TIP${NC}"
echo "    $S_GROQ_M1"
echo "    $S_GROQ_M2"
echo "    $S_GROQ_M3"
echo ""
prompt GROQ_MODEL_CHOICE "$S_GROQ_MODEL_PROMPT" "1" ""
case "$GROQ_MODEL_CHOICE" in
    1) GROQ_MODEL="llama-3.1-8b-instant"    ;;
    2) GROQ_MODEL="llama-3.3-70b-versatile" ;;
    3) GROQ_MODEL="gemma2-9b-it"            ;;
    *) GROQ_MODEL="llama-3.1-8b-instant"    ;;
esac

# Gemini API Key (optional fallback)
echo ""
echo -e "  ${CYAN}$S_GEMINI_HEAD${NC}"
echo "$S_GEMINI_TIP1"
echo "$S_GEMINI_TIP2"
echo ""
prompt GEMINI_API_KEY "$S_GEMINI_PROMPT" "" "secret"
if [ -z "$GEMINI_API_KEY" ]; then
    warn "$S_GEMINI_SKIP"
    GEMINI_MODEL="gemini-2.5-flash"
else
    success "$S_GEMINI_OK"
    GEMINI_MODEL="gemini-2.5-flash"
fi

# Moderation settings
echo ""
echo -e "  ${YELLOW}$S_MOD_HEAD${NC}"
prompt MAX_WARNINGS "$S_WARN_PROMPT" "3"    ""
prompt SPAM_WINDOW  "$S_WIN_PROMPT"  "60"   ""
prompt SPAM_MAX     "$S_SPAM_PROMPT" "5"    ""
prompt MIN_CONF     "$S_CONF_PROMPT" "0.60" ""

[[ "$MAX_WARNINGS" =~ ^[0-9]+$ ]] || error "Max warnings must be a positive integer"
[[ "$SPAM_WINDOW"  =~ ^[0-9]+$ ]] || error "Spam window must be a positive integer"
[[ "$SPAM_MAX"     =~ ^[0-9]+$ ]] || error "Spam max must be a positive integer"
"$PY_BIN" -c "v=float('$MIN_CONF'); exit(0 if 0.0<=v<=1.0 else 1)" 2>/dev/null \
    || error "AI confidence must be between 0.0 and 1.0"

# Bot language
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

# Summary
echo ""
echo -e "${GREEN}+------------------------------------------------------+${NC}"
echo -e "${GREEN}|  $S_SUM_HEAD${NC}"
echo -e "${GREEN}+------------------------------------------------------+${NC}"
printf "${GREEN}|${NC}  Token          : %s...\n"  "${BOT_TOKEN:0:15}"
printf "${GREEN}|${NC}  Admin IDs      : %s\n"     "$ADMIN_IDS"
printf "${GREEN}|${NC}  Groq Model     : %s\n"     "$GROQ_MODEL"
printf "${GREEN}|${NC}  Groq Key       : %s...\n"  "${GROQ_API_KEY:0:8}"
printf "${GREEN}|${NC}  Gemini Key     : %s\n"     "${GEMINI_API_KEY:+set}${GEMINI_API_KEY:-not set}"
printf "${GREEN}|${NC}  Max Warnings   : %s\n"     "$MAX_WARNINGS"
printf "${GREEN}|${NC}  Spam Window    : %s sec\n" "$SPAM_WINDOW"
printf "${GREEN}|${NC}  Spam Limit     : %s msg\n" "$SPAM_MAX"
printf "${GREEN}|${NC}  Bot Language   : %s\n"     "$BOT_LANG"
echo -e "${GREEN}+------------------------------------------------------+${NC}"
echo ""
ask "$S_CONTINUE"
read -r CONFIRM
[[ "${CONFIRM:-Y}" =~ ^[Nn] ]] && { echo "$S_ABORT"; exit 0; }

# ===================================================================
#  Step 3 -- Python virtual environment
# ===================================================================
banner "$S_STEP3"

if [ ! -d "$BOT_DIR/venv" ]; then
    "$PY_BIN" -m venv "$BOT_DIR/venv"
    success "$S_VENV_NEW"
else
    warn "$S_VENV_EXISTS"
fi

source "$BOT_DIR/venv/bin/activate"
pip install --quiet --upgrade pip wheel
pip install --quiet -r "$BOT_DIR/requirements.txt"
success "$S_DEPS_OK"

# ===================================================================
#  Step 4 -- Write .env
# ===================================================================
banner "$S_STEP4"

if [ -f "$ENV_FILE" ]; then
    cp "$ENV_FILE" "${ENV_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
    warn "Existing .env backed up"
fi

cat > "$ENV_FILE" <<EOF
# Generated by install.sh -- $(date '+%Y-%m-%d %H:%M:%S')
# DO NOT commit this file to git!

# Telegram
TELEGRAM_BOT_TOKEN=${BOT_TOKEN}
ADMIN_IDS=${ADMIN_IDS}
BOT_LANG=${BOT_LANG}

# Groq AI (primary -- 14400 req/day free)
GROQ_API_KEY=${GROQ_API_KEY}
GROQ_MODEL=${GROQ_MODEL}

# Gemini AI (optional fallback)
GEMINI_API_KEY=${GEMINI_API_KEY}
GEMINI_MODEL=${GEMINI_MODEL}

# Cache
CACHE_MIN_SCORE=0.75
CACHE_TTL_HOURS=24

# Moderation
MAX_WARNINGS=${MAX_WARNINGS}
SPAM_TIME_WINDOW=${SPAM_WINDOW}
SPAM_MAX_MESSAGES=${SPAM_MAX}
MIN_CONFIDENCE=${MIN_CONF}

# Learning
LEARNING_ENABLED=true
LEARNING_MIN_SCORE=0.75
SEARCH_TOP_K=5
EOF

chmod 600 "$ENV_FILE"
success "$S_ENV_OK"

# ===================================================================
#  Step 5 -- systemd service
# ===================================================================
banner "$S_STEP5"

CURRENT_USER=$(whoami)
VENV_PYTHON="$BOT_DIR/venv/bin/python"

sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null <<UNIT
[Unit]
Description=Telegram Group Manager Bot
After=network-online.target
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
    echo "    journalctl -u ${SERVICE_NAME} -n 50 --no-pager"
fi

# ===================================================================
#  Done
# ===================================================================
echo ""
echo -e "${GREEN}+======================================================+${NC}"
echo -e "${GREEN}|   ${BOLD}$S_DONE_HEAD${NC}"
echo -e "${GREEN}+======================================================+${NC}"
echo ""
echo -e "  ${CYAN}$S_DONE_1${NC}  journalctl -u ${SERVICE_NAME} -f"
echo -e "  ${CYAN}$S_DONE_2${NC}  sudo systemctl restart ${SERVICE_NAME}"
echo -e "  ${CYAN}$S_DONE_3${NC}  sudo systemctl stop ${SERVICE_NAME}"
echo -e "  ${CYAN}$S_DONE_4${NC}  nano ${ENV_FILE}"
echo ""
echo -e "  ${CYAN}$S_DONE_5${NC}"
echo    "    /settings -- change settings from Telegram"
echo    "    /stats    -- group statistics"
echo ""
echo -e "${YELLOW}  $S_DONE_NOTE${NC}"
echo ""
echo "  Install log: ${LOG_FILE}"
echo ""
