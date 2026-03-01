#!/bin/bash
# auto_continue.sh — Automatically resume Claude Code sessions after rate limit resets
#
# Usage:
#   ./scripts/auto_continue.sh              # Run once (resume if cooldown passed)
#   ./scripts/auto_continue.sh --daemon     # Loop forever, checking every 5 minutes
#   ./scripts/auto_continue.sh --install    # Install as a cron job (every 10 min)
#   ./scripts/auto_continue.sh --uninstall  # Remove cron job
#
# How it works:
#   1. Checks if enough time has passed since the last rate-limited session
#   2. If yes, resumes the most recent Claude session with "go on"
#   3. Uses --allowedTools to auto-approve safe read/write operations
#   4. Logs all activity to scripts/auto_continue.log
#
# IMPORTANT: This runs Claude with auto-approved tools. Review the allowedTools
# list below and adjust to your comfort level.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LOG_FILE="$PROJECT_DIR/scripts/auto_continue.log"
LAST_RUN_FILE="$PROJECT_DIR/scripts/.last_auto_run"
COOLDOWN_SECONDS=300  # 5 minutes — adjust based on your rate limit window

# Tools Claude is allowed to use without asking (safe defaults)
ALLOWED_TOOLS="Read,Glob,Grep,Write,Edit,Bash(conda run*),Bash(python*),Bash(git status*),Bash(git diff*),Bash(git log*),Bash(git add*),Bash(git commit*)"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

check_cooldown() {
    if [ ! -f "$LAST_RUN_FILE" ]; then
        return 0  # No previous run, OK to proceed
    fi
    local last_run
    last_run=$(cat "$LAST_RUN_FILE")
    local now
    now=$(date +%s)
    local elapsed=$((now - last_run))
    if [ "$elapsed" -lt "$COOLDOWN_SECONDS" ]; then
        return 1  # Still in cooldown
    fi
    return 0
}

run_once() {
    if ! check_cooldown; then
        log "Still in cooldown. Skipping."
        return 0
    fi

    log "Cooldown passed. Resuming Claude session..."

    # Record this run
    date +%s > "$LAST_RUN_FILE"

    # Resume the most recent session in this project directory
    cd "$PROJECT_DIR"
    claude -c -p "go on — continue where you left off. Check TODO.md for current tasks." \
        --allowedTools "$ALLOWED_TOOLS" \
        --output-format text \
        2>&1 | tee -a "$LOG_FILE"

    log "Session completed."
}

daemon_mode() {
    log "Starting daemon mode (checking every ${COOLDOWN_SECONDS}s)..."
    while true; do
        run_once
        sleep "$COOLDOWN_SECONDS"
    done
}

install_cron() {
    local script_path="$PROJECT_DIR/scripts/auto_continue.sh"
    local cron_line="*/10 * * * * $script_path >> $LOG_FILE 2>&1"

    # Check if already installed
    if crontab -l 2>/dev/null | grep -q "auto_continue.sh"; then
        echo "Cron job already installed. Current entry:"
        crontab -l | grep "auto_continue.sh"
        return 0
    fi

    (crontab -l 2>/dev/null; echo "$cron_line") | crontab -
    echo "Installed cron job: $cron_line"
    echo "To remove: $script_path --uninstall"
}

uninstall_cron() {
    if ! crontab -l 2>/dev/null | grep -q "auto_continue.sh"; then
        echo "No cron job found."
        return 0
    fi
    crontab -l | grep -v "auto_continue.sh" | crontab -
    echo "Cron job removed."
}

# ── Main ──────────────────────────────────────────────────────────────────────
case "${1:-}" in
    --daemon)
        daemon_mode
        ;;
    --install)
        install_cron
        ;;
    --uninstall)
        uninstall_cron
        ;;
    *)
        run_once
        ;;
esac
