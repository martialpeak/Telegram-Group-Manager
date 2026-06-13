#!/usr/bin/env bash
# ===================================================================
#   Telegram Group Manager Bot -- Update Script
#   Usage: ./update.sh
#   Pulls latest code from GitHub, updates deps, restarts service
# ===================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $1"; }
success() { echo -e "${GREEN}[ OK ]${NC}  $1"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $1"; }
error()   { echo -e "${RED}[FAIL]${NC}  $1"; exit 1; }

BOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="telegram-bot"
ENV_FILE="$BOT_DIR/.env"
VENV_PYTHON="$BOT_DIR/venv/bin/python"
VENV_PIP="$BOT_DIR/venv/bin/pip"

echo -e "\n${BOLD}${BLUE}+====================================================+${NC}"
echo -e "${BOLD}${BLUE}|   Telegram Group Manager Bot -- Update             |${NC}"
echo -e "${BOLD}${BLUE}+====================================================+${NC}\n"

# ── بررسی پیش‌نیازها ─────────────────────────────────────────────
[ -f "$ENV_FILE" ]      || error ".env not found. Run install.sh first."
[ -d "$BOT_DIR/venv" ]  || error "venv not found. Run install.sh first."
[ -d "$BOT_DIR/.git" ]  || error "Not a git repository."

# ── نسخه فعلی ────────────────────────────────────────────────────
CURRENT_COMMIT=$(git -C "$BOT_DIR" rev-parse --short HEAD 2>/dev/null || echo "unknown")
info "Current version: $CURRENT_COMMIT"

# ── بک‌آپ .env ───────────────────────────────────────────────────
info "Backing up .env ..."
cp "$ENV_FILE" "${ENV_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
success ".env backed up"

# ── git pull ─────────────────────────────────────────────────────
info "Fetching latest code from GitHub ..."
git -C "$BOT_DIR" fetch origin

LOCAL=$(git -C "$BOT_DIR" rev-parse HEAD)
REMOTE=$(git -C "$BOT_DIR" rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    success "Already up to date. No changes."
    NEW_COMMIT="$CURRENT_COMMIT"
    NEEDS_RESTART=false
else
    git -C "$BOT_DIR" pull --ff-only origin main
    NEW_COMMIT=$(git -C "$BOT_DIR" rev-parse --short HEAD)
    success "Code updated: $CURRENT_COMMIT → $NEW_COMMIT"
    NEEDS_RESTART=true

    # نمایش تغییرات
    echo ""
    echo -e "  ${CYAN}Changes:${NC}"
    git -C "$BOT_DIR" log --oneline "${CURRENT_COMMIT}..HEAD" | sed 's/^/    /'
    echo ""
fi

# ── آپدیت dependencies ───────────────────────────────────────────
info "Checking dependencies ..."
REQS_HASH_OLD=$(md5sum "$BOT_DIR/requirements.txt" 2>/dev/null | cut -d' ' -f1 || echo "")
# اگه requirements.txt تغییر کرده، نصب مجدد
if [ "$NEEDS_RESTART" = true ] || \
   [ ! -f "$BOT_DIR/.reqs_hash" ] || \
   [ "$(cat "$BOT_DIR/.reqs_hash" 2>/dev/null)" != "$REQS_HASH_OLD" ]; then
    info "Installing/updating Python packages ..."
    "$VENV_PIP" install --quiet --upgrade pip wheel
    "$VENV_PIP" install --quiet -r "$BOT_DIR/requirements.txt"
    md5sum "$BOT_DIR/requirements.txt" | cut -d' ' -f1 > "$BOT_DIR/.reqs_hash"
    success "Dependencies updated"
else
    success "Dependencies unchanged — skipped"
fi

# ── ری‌استارت سرویس ──────────────────────────────────────────────
if systemctl is-enabled --quiet "$SERVICE_NAME" 2>/dev/null; then
    info "Restarting $SERVICE_NAME ..."
    sudo systemctl restart "$SERVICE_NAME"
    sleep 3
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        success "Service restarted successfully"
    else
        error "Service failed to start! Check logs:\n  journalctl -u $SERVICE_NAME -n 50 --no-pager"
    fi
else
    warn "Service '$SERVICE_NAME' not found in systemd."
    warn "Start manually: source $BOT_DIR/venv/bin/activate && python $BOT_DIR/main.py"
fi

# ── خلاصه ────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}+====================================================+${NC}"
echo -e "${GREEN}|   Update complete!                                 |${NC}"
echo -e "${GREEN}+====================================================+${NC}"
echo ""
echo -e "  ${CYAN}Version:${NC}       $CURRENT_COMMIT → $NEW_COMMIT"
echo -e "  ${CYAN}Live logs:${NC}     journalctl -u ${SERVICE_NAME} -f"
echo -e "  ${CYAN}Status:${NC}        sudo systemctl status ${SERVICE_NAME}"
echo -e "  ${CYAN}Config:${NC}        nano ${ENV_FILE}"
echo ""
