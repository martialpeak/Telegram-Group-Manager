#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#   Telegram Group Manager Bot — Interactive Installer v2.1
#   Supports: Ubuntu 20.04+ / Debian 11+ / Raspberry Pi OS
#   Bilingual: English / Finglish
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# ── colors ──────────────────────────────────────────────────
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

# ── log all output ───────────────────────────────────────────
exec > >(tee -a "$LOG_FILE") 2>&1

# ── prompt helper ────────────────────────────────────────────
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

# ══════════════════════════════════════════════════════════════
#  Language Selection
# ══════════════════════════════════════════════════════════════
clear
echo -e "${BOLD}${BLUE}"
echo "+====================================================+"
echo "|   Telegram Group Manager Bot -- Installer v2.1    |"
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

# ══════════════════════════════════════════════════════════════
#  String Table
# ══════════════════════════════════════════════════════════════
if [ "$LANG" = "fa" ]; then
    S_STEP1="Marhale 1: Barresi Python"
    S_PY_INSTALL="Python 3 peyda nashod -- dar hal nasb..."
    S_PY_OK="Python %s peyda shod"
    S_PY_ERR="Python 3.11+ lazem ast (version feli: %s). Dar hal nasb Python 3.11..."
    S_PY_UPGRADE="Python %s peyda shod -- dar hal nasb Python 3.11 az deadsnakes PPA..."
    S_PY_UPGRADE_OK="Python 3.11 ba movafaghiat nasb shod"
    S_PY_UPGRADE_FAIL="Nasb Python 3.11 namovaghagh shod. Dasti upgrade kon va dobbare ejra kon."

    S_STEP2="Marhale 2: Pikar-bandi Robot"
    S_TOKEN_TIP="Chetori token begirim:"
    S_TOKEN_TIP1="  1. Dar Telegram be @BotFather payam bedid"
    S_TOKEN_TIP2="  2. Dastur /newbot ra ersal konid"
    S_TOKEN_TIP3="  3. Token daryafti ra inja vared konid"
    S_TOKEN_PROMPT="Token robot Telegram"
    S_TOKEN_ERR="Token robot ejbari ast!"

    S_ADMIN_TIP="Chetori shenase Telegram khodetono peyda konid:"
    S_ADMIN_TIP1="  Be @userinfobot payam bedid -- shenase adadi shoma ra barmigardanad"
    S_ADMIN_PROMPT="Shenase admin-ha (chand ta ba comma joda konid)"
    S_ADMIN_ERR="Haddaghal yek shenase admin lazem ast!"

    S_MODEL_TIP="Model Hush Masnoui ra entekhab konid:"
    S_MODEL_1="1) llama3.1     -- keyfiyat khob      (~4.7 GB RAM)"
    S_MODEL_2="2) gemma2:2b    -- saboktar           (~1.6 GB RAM)"
    S_MODEL_3="3) phi3         -- saritar            (~2.3 GB RAM)"
    S_MODEL_4="4) mistral      -- motavazen          (~4.1 GB RAM)"
    S_MODEL_5="5) dasti        -- khodet esm benevis"
    S_MODEL_PROMPT="Shomare model"
    S_MODEL_CUSTOM="Esm model ra vared kon (masalan llama3.1:8b)"

    S_MOD_HEAD="Tanzimate modiriyat geruh:"
    S_WARN_PROMPT="Haddaksar akhtar ghabl az ban"
    S_WIN_PROMPT="Baze zamani tashkhis spam (sanie)"
    S_SPAM_PROMPT="Haddaksar payam dar baze spam"
    S_CONF_PROMPT="Haddaghal etminan Hush Masnoui (0.0 ta 1.0)"

    S_LANG_TIP="Zaban payam-haye robot dar Telegram:"
    S_LANG_1="1) Farsi"
    S_LANG_2="2) English"
    S_LANG_PROMPT="Entekhab"

    S_SUM_HEAD="Kholase tanzimate:"
    S_CONTINUE="Edame midahim? [Y/n]"
    S_ABORT="Laghv shod."

    S_STEP3="Marhale 3: Mohit majazi Python"
    S_VENV_NEW="Mohit majazi sakhte shod"
    S_VENV_EXISTS="Mohit majazi az ghabl vojud darad -- rad shod"
    S_DEPS_OK="Vabastegi-ha nasb shodand"

    S_STEP4="Marhale 4: Zakhire file tanzimate"
    S_ENV_OK="File .env zakhire shod"

    S_STEP5="Marhale 5: Ollama (motor Hush Masnoui mahali)"
    S_OLL_INSTALL="Dar hal nasb Ollama..."
    S_OLL_OK="Ollama nasb shod"
    S_OLL_EXISTS="Ollama az ghabl nasb ast"
    S_OLL_RUNNING="Servis Ollama dar hal ejrast"
    S_OLL_START="Servis Ollama ra rahendazi mikonim..."
    S_MODEL_PULL="Dar hal download model %s (chand daghighe tool mikeshad)..."
    S_MODEL_OK="Model '%s' amadeh ast"
    S_MODEL_FAIL="Download '%s' namovaghagh bud. Dasti ejra kon: ollama pull %s"
    S_EMBED_PULL="Dar hal download model embedding..."
    S_EMBED_OK="Model embedding amadeh ast"
    S_EMBED_FAIL="Download embedding namovaghagh. Dasti ejra kon: ollama pull nomic-embed-text"

    S_STEP6="Marhale 6: Servis systemd (ejraye khodkar ba boot)"
    S_SVC_OK="Servis robot ba movafaghiat shoroo shod"
    S_SVC_FAIL="Servis shoroo nashod. Log ra barresi kon:"

    S_DONE_HEAD="Nasb tamam shod!"
    S_DONE_1="Moshahedeye log zende:"
    S_DONE_2="Restart robot:"
    S_DONE_3="Stop robot:"
    S_DONE_4="Virayesh tanzimate:"
    S_DONE_5="Dar Telegram (faghat admin):"
    S_DONE_NOTE="Nakte: bad az virayeshe dasti .env robot ra restart konid"
else
    S_STEP1="Step 1: Python"
    S_PY_INSTALL="python3 not found -- installing..."
    S_PY_OK="Python %s found"
    S_PY_ERR="Python 3.11+ is required (found: %s). Attempting to install Python 3.11..."
    S_PY_UPGRADE="Python %s found -- installing Python 3.11 from deadsnakes PPA..."
    S_PY_UPGRADE_OK="Python 3.11 installed successfully"
    S_PY_UPGRADE_FAIL="Failed to install Python 3.11. Please upgrade manually and re-run."

    S_STEP2="Step 2: Bot Configuration"
    S_TOKEN_TIP="How to get a bot token:"
    S_TOKEN_TIP1="  1. Open Telegram and message @BotFather"
    S_TOKEN_TIP2="  2. Send: /newbot"
    S_TOKEN_TIP3="  3. Copy the token and paste it here"
    S_TOKEN_PROMPT="Telegram bot token"
    S_TOKEN_ERR="Bot token is required!"

    S_ADMIN_TIP="How to find your Telegram user ID:"
    S_ADMIN_TIP1="  Message @userinfobot -- it replies with your numeric ID"
    S_ADMIN_PROMPT="Admin Telegram ID(s) -- separate multiple with commas"
    S_ADMIN_ERR="At least one admin ID is required!"

    S_MODEL_TIP="Choose an AI model:"
    S_MODEL_1="1) llama3.1     -- good quality    (~4.7 GB RAM)"
    S_MODEL_2="2) gemma2:2b    -- lightweight     (~1.6 GB RAM)"
    S_MODEL_3="3) phi3         -- fast            (~2.3 GB RAM)"
    S_MODEL_4="4) mistral      -- balanced        (~4.1 GB RAM)"
    S_MODEL_5="5) custom       -- enter manually"
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
    S_VENV_EXISTS="Virtual environment already exists -- skipped"
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
    S_MODEL_OK="Model '%s' ready"
    S_MODEL_FAIL="Failed to pull '%s'. Run manually: ollama pull %s"
    S_EMBED_PULL="Pulling embedding model: nomic-embed-text..."
    S_EMBED_OK="Embedding model ready"
    S_EMBED_FAIL="Failed to pull embedding model. Run: ollama pull nomic-embed-text"

    S_STEP6="Step 6: System service (auto-start on boot)"
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

# ══════════════════════════════════════════════════════════════
#  Step 1 — Python
# ══════════════════════════════════════════════════════════════
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
        success "$S_PY_UPGRADE_OK"
        return 0
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
        PY_BIN="python3.11"
        PY_VER="3.11"
    else
        if command -v python3.11 &>/dev/null && \
           python3.11 -c 'import sys; exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
            PY_BIN="python3.11"
            PY_VER="3.11"
            success "$S_PY_UPGRADE_OK"
        else
            echo -e "${RED}[FAIL]${NC}  $S_PY_UPGRADE_FAIL" >&2
            exit 1
        fi
    fi
fi

# ══════════════════════════════════════════════════════════════
#  Step 2 — Configuration
# ══════════════════════════════════════════════════════════════
banner "$S_STEP2"

echo ""
echo -e "  ${YELLOW}$S_TOKEN_TIP${NC}"
echo "$S_TOKEN_TIP1"
echo "$S_TOKEN_TIP2"
echo "$S_TOKEN_TIP3"
echo ""
prompt BOT_TOKEN "$S_TOKEN_PROMPT" "" "secret"
[ -z "$BOT_TOKEN" ] && error "$S_TOKEN_ERR"

echo ""
echo -e "  ${YELLOW}$S_ADMIN_TIP${NC}"
echo "$S_ADMIN_TIP1"
echo ""
prompt ADMIN_IDS "$S_ADMIN_PROMPT" "" ""
[ -z "$ADMIN_IDS" ] && error "$S_ADMIN_ERR"

if ! echo "$ADMIN_IDS" | grep -qE '^[0-9]+(,[0-9]+)*$'; then
    error "Admin IDs must be numbers separated by commas (e.g. 123456789,987654321)"
fi

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
    *) AI_MODEL="$MODEL_CHOICE" ;;
esac

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

echo ""
echo -e "${GREEN}+------------------------------------------------------+${NC}"
echo -e "${GREEN}|  ${BOLD}$S_SUM_HEAD${NC}${GREEN}"
echo -e "${GREEN}+------------------------------------------------------+${NC}"
printf "${GREEN}|${NC}  Token          : %s...\n"  "${BOT_TOKEN:0:15}"
printf "${GREEN}|${NC}  Admin IDs      : %s\n"     "$ADMIN_IDS"
printf "${GREEN}|${NC}  AI Model       : %s\n"     "$AI_MODEL"
printf "${GREEN}|${NC}  Max Warnings   : %s\n"     "$MAX_WARNINGS"
printf "${GREEN}|${NC}  Spam Window    : %s sec\n" "$SPAM_WINDOW"
printf "${GREEN}|${NC}  Spam Limit     : %s msg\n" "$SPAM_MAX"
printf "${GREEN}|${NC}  AI Confidence  : %s\n"     "$MIN_CONF"
printf "${GREEN}|${NC}  Bot Language   : %s\n"     "$BOT_LANG"
echo -e "${GREEN}+------------------------------------------------------+${NC}"
echo ""
ask "$S_CONTINUE"
read -r CONFIRM
[[ "${CONFIRM:-Y}" =~ ^[Nn] ]] && { echo "$S_ABORT"; exit 0; }

# ══════════════════════════════════════════════════════════════
#  Step 3 — Python virtual environment
# ══════════════════════════════════════════════════════════════
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

# ══════════════════════════════════════════════════════════════
#  Step 4 — Write .env
# ══════════════════════════════════════════════════════════════
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

# AI
AI_MODEL=${AI_MODEL}
EMBED_MODEL=nomic-embed-text
OLLAMA_BASE_URL=http://localhost:11434

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

# ══════════════════════════════════════════════════════════════
#  Step 5 — Ollama
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

echo ""
info "$(printf "$S_MODEL_PULL" "$AI_MODEL")"
if ollama pull "$AI_MODEL"; then
    success "$(printf "$S_MODEL_OK" "$AI_MODEL")"
else
    warn "$(printf "$S_MODEL_FAIL" "$AI_MODEL" "$AI_MODEL")"
fi

echo ""
info "$S_EMBED_PULL"
if ollama pull nomic-embed-text; then
    success "$S_EMBED_OK"
else
    warn "$S_EMBED_FAIL"
fi

# ══════════════════════════════════════════════════════════════
#  Step 6 — systemd service
# ══════════════════════════════════════════════════════════════
banner "$S_STEP6"

CURRENT_USER=$(whoami)
VENV_PYTHON="$BOT_DIR/venv/bin/python"

sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null <<UNIT
[Unit]
Description=Telegram Group Manager Bot
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
#  Done
# ══════════════════════════════════════════════════════════════
echo ""
echo -e "${GREEN}+======================================================+${NC}"
echo -e "${GREEN}|   ${BOLD}$S_DONE_HEAD${NC}"
echo -e "${GREEN}+======================================================+${NC}"
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
echo    "    /settings  -- change settings from Telegram"
echo    "    /stats     -- group statistics"
echo    "    /reports   -- pending reports"
echo ""
echo -e "${YELLOW}  $S_DONE_NOTE${NC}"
echo ""
echo "  Install log: ${LOG_FILE}"
echo ""
