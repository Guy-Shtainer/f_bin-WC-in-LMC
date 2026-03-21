#!/bin/bash
# launch-dash-builder.sh — Autonomous Dash feature builder (2-day loop)
#
# Usage:
#   bash scripts/launch-dash-builder.sh              # run all remaining batches
#   bash scripts/launch-dash-builder.sh 5             # start from batch 5
#   bash scripts/launch-dash-builder.sh --status      # show progress and exit
#
# To monitor:  tmux attach -t dash-builder
# To detach:   Ctrl-B d
# To pause:    touch .claude/dash-builder-pause  (resumes when file is removed)
# To stop:     tmux kill-session -t dash-builder
#
# WARNING: Keep Mac on a desk with airflow, plugged in. Lid closed is fine.

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SESSION_NAME="dash-builder"
LOG_DIR="$PROJECT_DIR/.claude/dash-builder-logs"
PAUSE_FILE="$PROJECT_DIR/.claude/dash-builder-pause"
FEATURES_FILE="$PROJECT_DIR/bias_app/FEATURES.md"

MAX_HOURS=48
BATCH_TIMEOUT=2400
RATE_LIMIT_SLEEP=3600
MAX_CONSECUTIVE_FAILS=3
COOLDOWN=15

START_BATCH="${1:-next}"

# ── Dependency checks ──────────────────────────────────────────────────────
command -v tmux >/dev/null 2>&1 || { echo "Error: tmux not installed. Run: brew install tmux"; exit 1; }
command -v caffeinate >/dev/null 2>&1 || { echo "Error: caffeinate not found"; exit 1; }
command -v claude >/dev/null 2>&1 || { echo "Error: claude CLI not found"; exit 1; }

# ── Status check ───────────────────────────────────────────────────────────
if [ "$START_BATCH" = "--status" ]; then
    if [ -f "$FEATURES_FILE" ]; then
        DONE=$(grep -c '\- \[x\]' "$FEATURES_FILE" 2>/dev/null || echo 0)
        PARTIAL=$(grep -c '\- \[~\]' "$FEATURES_FILE" 2>/dev/null || echo 0)
        TODO=$(grep -c '\- \[ \]' "$FEATURES_FILE" 2>/dev/null || echo 0)
        TOTAL=$((DONE + PARTIAL + TODO))
        echo "FEATURES.md progress: $DONE/$TOTAL done, $PARTIAL partial, $TODO remaining"
    fi
    if [ -f "$LOG_DIR/master.log" ]; then
        echo ""
        echo "Last 10 log entries:"
        tail -10 "$LOG_DIR/master.log"
    fi
    exit 0
fi

# ── Prevent duplicate sessions ─────────────────────────────────────────────
tmux has-session -t "$SESSION_NAME" 2>/dev/null && {
    echo "Session '$SESSION_NAME' already running."
    echo "  Monitor: tmux attach -t $SESSION_NAME"
    echo "  Stop:    tmux kill-session -t $SESSION_NAME"
    exit 1
}

# ── Build the runner script ────────────────────────────────────────────────
# Two-part heredoc: first part UNQUOTED (expands config vars with Hebrew path),
# second part QUOTED (preserves $BATCH_NUM etc. for runtime)
mkdir -p "$LOG_DIR"

RUNNER=$(mktemp /tmp/dash-builder-runner.XXXXXX.sh)

# Part 1: config variables (expanded NOW by the outer shell)
cat > "$RUNNER" <<CONFIG_EOF
#!/bin/bash
set -uo pipefail
PROJECT_DIR="$PROJECT_DIR"
LOG_DIR="$LOG_DIR"
PAUSE_FILE="$PAUSE_FILE"
FEATURES_FILE="$FEATURES_FILE"
MAX_HOURS=$MAX_HOURS
BATCH_TIMEOUT=$BATCH_TIMEOUT
RATE_LIMIT_SLEEP=$RATE_LIMIT_SLEEP
MAX_CONSECUTIVE_FAILS=$MAX_CONSECUTIVE_FAILS
COOLDOWN=$COOLDOWN
START_BATCH="$START_BATCH"
CONFIG_EOF

# Part 2: script body (preserved literally — runtime variables like $BATCH_NUM stay)
cat >> "$RUNNER" <<'BODY_EOF'

cd "$PROJECT_DIR" || exit 1

BATCH_NUM=1
CONSECUTIVE_FAILURES=0
START_TIME=$(date +%s)
TOTAL_COMPLETED=0

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_DIR/master.log"
}

log "=== Dash Builder started ==="
log "Project: $PROJECT_DIR"
log "Max runtime: ${MAX_HOURS}h | Batch timeout: ${BATCH_TIMEOUT}s"

while true; do

    # Check 2-day timeout
    ELAPSED_H=$(( ($(date +%s) - START_TIME) / 3600 ))
    if [ "$ELAPSED_H" -ge "$MAX_HOURS" ]; then
        log "=== ${MAX_HOURS}-hour limit reached. Stopping. ==="
        break
    fi

    # Check pause file
    while [ -f "$PAUSE_FILE" ]; do
        log "PAUSED. Remove $PAUSE_FILE to resume."
        sleep 60
    done

    # Check if any features remain
    REMAINING=$(grep -c '\- \[ \]' "$FEATURES_FILE" 2>/dev/null || echo 0)
    if [ "$REMAINING" -eq 0 ]; then
        log "=== ALL FEATURES COMPLETE! ==="
        break
    fi

    TIMESTAMP=$(date +%Y%m%d-%H%M%S)
    BATCH_LOG="$LOG_DIR/batch_${BATCH_NUM}_${TIMESTAMP}.log"

    log "--- Batch $BATCH_NUM starting ($REMAINING features remaining, ${ELAPSED_H}h elapsed) ---"

    # First iteration uses START_BATCH arg, rest use "next"
    if [ "$START_BATCH" != "next" ] && [ "$BATCH_NUM" -eq 1 ]; then
        BATCH_ARG="$START_BATCH"
    else
        BATCH_ARG="next"
    fi

    timeout "$BATCH_TIMEOUT" claude \
        --dangerously-skip-permissions \
        "/build-dash $BATCH_ARG" \
        > "$BATCH_LOG" 2>&1

    EXIT_CODE=$?

    case $EXIT_CODE in
        0)
            NEW_REMAINING=$(grep -c '\- \[ \]' "$FEATURES_FILE" 2>/dev/null || echo 0)
            COMPLETED_THIS=$((REMAINING - NEW_REMAINING))
            TOTAL_COMPLETED=$((TOTAL_COMPLETED + COMPLETED_THIS))
            log "Batch $BATCH_NUM DONE (+${COMPLETED_THIS} features, ${TOTAL_COMPLETED} total)"
            CONSECUTIVE_FAILURES=0
            BATCH_NUM=$((BATCH_NUM + 1))
            sleep "$COOLDOWN"
            ;;

        124)
            log "Batch $BATCH_NUM TIMEOUT (${BATCH_TIMEOUT}s)"
            CONSECUTIVE_FAILURES=$((CONSECUTIVE_FAILURES + 1))
            ;;

        *)
            if grep -qi 'rate.limit\|429\|too.many.requests\|overloaded\|capacity' "$BATCH_LOG" 2>/dev/null; then
                CONSECUTIVE_FAILURES=$((CONSECUTIVE_FAILURES + 1))

                if [ "$CONSECUTIVE_FAILURES" -ge 6 ]; then
                    SLEEP_SECS=$(python3 -c "
import datetime
now = datetime.datetime.now()
days = (6 - now.weekday()) % 7
if days == 0 and now.hour >= 11:
    days = 7
target = (now + datetime.timedelta(days=days)).replace(hour=11, minute=0, second=0)
print(int((target - now).total_seconds()))
" 2>/dev/null || echo 86400)
                    log "WEEKLY LIMIT HIT. Sleeping ${SLEEP_SECS}s until Sunday 11 AM"
                    sleep "$SLEEP_SECS"
                    CONSECUTIVE_FAILURES=0
                else
                    log "RATE LIMITED (attempt $CONSECUTIVE_FAILURES/6). Sleeping ${RATE_LIMIT_SLEEP}s..."
                    sleep "$RATE_LIMIT_SLEEP"
                fi
            else
                log "Batch $BATCH_NUM FAILED (exit $EXIT_CODE). See $BATCH_LOG"
                CONSECUTIVE_FAILURES=$((CONSECUTIVE_FAILURES + 1))
            fi
            ;;
    esac

    if [ "$CONSECUTIVE_FAILURES" -ge "$MAX_CONSECUTIVE_FAILS" ]; then
        log "Skipping batch $BATCH_NUM after $MAX_CONSECUTIVE_FAILS consecutive failures"
        BATCH_NUM=$((BATCH_NUM + 1))
        CONSECUTIVE_FAILURES=0
        sleep "$COOLDOWN"
    fi

done

ELAPSED_TOTAL=$(( ($(date +%s) - START_TIME) / 60 ))
FINAL_DONE=$(grep -c '\- \[x\]' "$FEATURES_FILE" 2>/dev/null || echo 0)
FINAL_TODO=$(grep -c '\- \[ \]' "$FEATURES_FILE" 2>/dev/null || echo 0)

log "=== Session complete ==="
log "Duration: ${ELAPSED_TOTAL} minutes"
log "Features done: ${FINAL_DONE}, remaining: ${FINAL_TODO}"
log "This session: $TOTAL_COMPLETED features across $((BATCH_NUM - 1)) batches"

echo ""
echo "Dash Builder finished. Press Enter to close."
read
BODY_EOF

chmod +x "$RUNNER"

# ── Launch in tmux with caffeinate ─────────────────────────────────────────
tmux new-session -d -s "$SESSION_NAME" "caffeinate -s '$RUNNER'"

echo "Dash Builder launched!"
echo ""
echo "  Session:  $SESSION_NAME"
echo "  Monitor:  tmux attach -t $SESSION_NAME"
echo "  Pause:    touch .claude/dash-builder-pause"
echo "  Resume:   rm .claude/dash-builder-pause"
echo "  Stop:     tmux kill-session -t $SESSION_NAME"
echo "  Status:   bash scripts/launch-dash-builder.sh --status"
echo "  Logs:     $LOG_DIR/master.log"
echo ""
echo "Caffeinate prevents sleep (AC power required for lid-closed mode)."
