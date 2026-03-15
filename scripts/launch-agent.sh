#!/bin/bash
# launch-agent.sh — Start the agent loop in tmux with sleep prevention
#
# Usage:
#   bash scripts/launch-agent.sh                    # default: 20 iterations
#   bash scripts/launch-agent.sh 50                 # custom max iterations
#   bash scripts/launch-agent.sh 50 "freeform: Fix the login bug"  # with args
#
# To monitor:  tmux attach -t agent
# To detach:   Ctrl-B d
# To stop:     tmux kill-session -t agent
# To rollback: git reset --hard pre-agent-rewrite && ln -sf ../Data Data
#
# WARNING: Do NOT put your Mac in a bag while this runs — it needs airflow!
#          Leave it on a desk, plugged in, lid closed is fine.

set -euo pipefail

MAX_ITER="${1:-20}"
TASK_ARGS="${2:-}"
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SESSION_NAME="agent"

# Check dependencies
command -v tmux >/dev/null 2>&1 || { echo "Error: tmux not installed. Run: brew install tmux"; exit 1; }
command -v caffeinate >/dev/null 2>&1 || { echo "Error: caffeinate not found (should be built into macOS)"; exit 1; }
command -v claude >/dev/null 2>&1 || { echo "Error: claude CLI not found"; exit 1; }

# Kill existing session if running
tmux has-session -t "$SESSION_NAME" 2>/dev/null && {
    echo "Agent session already running. Kill it first: tmux kill-session -t $SESSION_NAME"
    exit 1
}

echo "Starting agent loop..."
echo "  Max iterations: $MAX_ITER"
echo "  Project: $PROJECT_DIR"
echo "  Task args: ${TASK_ARGS:-'(from queue or TODO.md)'}"
echo ""
echo "Launching in tmux session '$SESSION_NAME'..."
echo "  Monitor:  tmux attach -t $SESSION_NAME"
echo "  Stop:     tmux kill-session -t $SESSION_NAME"
echo ""

# Build the claude command
if [ -n "$TASK_ARGS" ]; then
    CLAUDE_CMD="cd '$PROJECT_DIR' && claude --dangerously-skip-permissions '/ralph-loop \"/run-task $TASK_ARGS\" --max-iterations $MAX_ITER --completion-promise ALL_DONE'"
else
    CLAUDE_CMD="cd '$PROJECT_DIR' && claude --dangerously-skip-permissions '/ralph-loop \"/run-task\" --max-iterations $MAX_ITER --completion-promise ALL_DONE'"
fi

# Start tmux session with caffeinate wrapping
# caffeinate -s: prevent sleep while on AC power
# caffeinate -i: prevent idle sleep (works on battery too but drains faster)
tmux new-session -d -s "$SESSION_NAME" "caffeinate -s bash -c '$CLAUDE_CMD; echo; echo Agent loop finished. Press enter to close.; read'"

echo "Agent launched! Session: $SESSION_NAME"
echo "Caffeinate is preventing sleep (AC power required for lid-closed mode)."
