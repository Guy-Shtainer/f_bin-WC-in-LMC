# Scripts

## Overnight Agent (`overnight_agent.py`)

Autonomous agent that works on your low-priority TODO tasks while you sleep.

### Quick Start

```bash
# Before bed — one command, that's it:
conda run -n guyenv python scripts/overnight_agent.py
```

It will:
- Tag your current code as a safe rollback point (`pre-agent-{timestamp}`)
- Pick tasks from the "Eliminate" quadrant (not urgent + not important)
- Run Claude on each task, auto-accepting all tool calls
- Create a git branch per task (`agent/{id}-{slug}`)
- Sleep on rate limits, wake up and continue automatically
- Keep your Mac awake via `caffeinate`
- Ctrl+C to stop anytime

### When You Wake Up

```bash
# 1. Check what it did
cat scripts/agent_log.md

# 2. Open the webapp — tasks are marked "TO TEST" with green badges
conda run -n guyenv streamlit run app/app.py

# 3. Don't like everything? Undo ALL agent work:
git reset --hard pre-agent-20260301-2345    # use the tag from agent_log.md

# 4. Want to keep some changes but undo others?
#    Each task is on its own branch — cherry-pick what you want:
git log --oneline --all | grep AGENT        # see all agent commits
git cherry-pick <commit-hash>               # pick the ones you like
```

### Options

```bash
# Work on "Delegate" tasks (urgent but not important) instead
conda run -n guyenv python scripts/overnight_agent.py --quadrant delegate

# Work on "Schedule" tasks (important but not urgent) — opt-in only
conda run -n guyenv python scripts/overnight_agent.py --quadrant schedule

# Preview what it would do without actually doing it
conda run -n guyenv python scripts/overnight_agent.py --dry-run

# Stop after 3 tasks
conda run -n guyenv python scripts/overnight_agent.py --max-tasks 3

# Run in background (detached from terminal)
conda run -n guyenv python scripts/overnight_agent.py --daemon

# Stop a background daemon
conda run -n guyenv python scripts/overnight_agent.py --stop
```

### Safety

- **Never touches "Do First" tasks** (urgent + important) — those always need you
- **Git checkpoint** before anything — one command to undo everything
- **Each task on its own branch** — cherry-pick what you like, discard the rest
- **All commits prefixed with `[AGENT]`** — easy to spot in git log
- **Tasks marked "to-test"** — you verify before they become "done"
- **agent_log.md** — full record of what was done, with rollback commands

### Quadrant Priority Order

| Quadrant | Urgent? | Important? | Agent works on it? |
|----------|---------|------------|-------------------|
| Eliminate | No | No | Yes (default) |
| Delegate | Yes | No | Yes (with `--quadrant delegate`) |
| Schedule | No | Yes | Only if you opt in (`--quadrant schedule`) |
| Do First | Yes | Yes | **NEVER** — always needs human |

---

## Auto-Continue (`auto_continue.sh`)

Simple "poke" script — just sends "go on" to resume a paused Claude session.
Much simpler than the overnight agent. Use this if you just want a quick nudge.

```bash
./scripts/auto_continue.sh           # Run once
./scripts/auto_continue.sh --daemon  # Loop every 5 min
./scripts/auto_continue.sh --install # Add as cron job
```
