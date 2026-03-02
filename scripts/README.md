# Scripts

## Overnight Agent (`overnight_agent.py`)

Multi-agent overnight supervisor. Uses a pipeline of specialized Claude agents
(planner, reviewer, implementer, tester, regression checker) per task.

### Architecture

```
Supervisor (pure Python orchestrator)
    │
    ├── picks task from TODO.md
    ├── creates git branch
    │
    ▼ Per-task pipeline:
    Planner ──▶ Reviewer ──▶ Implementer ──▶ Tester ──▶ Regression
                                              │
                                         If FAIL:
                                    Fix Planner ──▶ Fix Implementer
                                         (max 2 retries)
```

Each agent is a separate `query()` call with a specialized system prompt.
Git is ONLY touched by the supervisor — agents never run git commands.
Agent artifacts are saved to `scripts/.agent_work/{task_id}/`.

### Quick Start

```bash
# Before bed — one command:
conda run -n guyenv python scripts/overnight_agent.py

# Preview what it would do:
conda run -n guyenv python scripts/overnight_agent.py --dry-run

# Check status while running:
conda run -n guyenv python scripts/overnight_agent.py --status

# Stop and review branches interactively:
conda run -n guyenv python scripts/overnight_agent.py --stop
```

### Options

```bash
# Work on ALL quadrants (eliminate → delegate → schedule, in order)
conda run -n guyenv python scripts/overnight_agent.py --quadrant all

# Work on specific quadrant
conda run -n guyenv python scripts/overnight_agent.py --quadrant delegate
conda run -n guyenv python scripts/overnight_agent.py --quadrant schedule

# Include "Do First" tasks (urgent + important) — requires explicit opt-in
conda run -n guyenv python scripts/overnight_agent.py --quadrant all --include-critical

# Free-form task (skip TODO.md)
conda run -n guyenv python scripts/overnight_agent.py --task "Draft the Introduction section"

# Stop after 3 tasks
conda run -n guyenv python scripts/overnight_agent.py --max-tasks 3

# Run in background (detached from terminal)
conda run -n guyenv python scripts/overnight_agent.py --daemon

# Stop a background daemon + review branches
conda run -n guyenv python scripts/overnight_agent.py --stop

# Show current status
conda run -n guyenv python scripts/overnight_agent.py --status
```

### When You Wake Up

```bash
# 1. Check status
conda run -n guyenv python scripts/overnight_agent.py --status

# 2. Stop and review each branch interactively
conda run -n guyenv python scripts/overnight_agent.py --stop
# Shows diff, test results, asks: [K]eep / [M]erge / [D]iscard

# 3. Or check the log directly
cat scripts/agent_log.md

# 4. Nuclear undo — reset ALL agent work:
git reset --hard pre-agent-20260301-2345    # use tag from agent_log.md
```

### Safety

- **Branches never auto-merged** — you review via `--stop` first
- **Git checkpoint** before anything — one command to undo everything
- **Each task on its own branch** — keep, merge, or discard individually
- **Multi-agent pipeline** — plan is reviewed before implementation
- **Tests + regression** — automated checks before marking done
- **All commits prefixed with `[AGENT]`** — easy to spot in git log
- **"Do First" tasks require `--include-critical`** — never touched by default

### Pipeline Stages

| Stage | Agent | What it does | Timeout |
|-------|-------|-------------|---------|
| 1 | Planner | Reads codebase, writes implementation plan | 10 min |
| 2 | Reviewer | Checks plan against CLAUDE.md, approves/rejects | 5 min |
| 3 | Implementer | Executes the plan, writes code | 15 min |
| 4 | Tester | Runs py_compile, checks COMMON_ERRORS.md patterns | 5 min |
| 5 | Regression | Checks existing files still compile | 5 min |
| Fix | Fix Planner + Fix Implementer | Diagnose and fix test failures (max 2 cycles) | 5+10 min |

### File Structure

```
scripts/
├── overnight_agent.py      # Supervisor (this file)
├── agent_prompts.py        # System prompts for each agent role
├── agent_log.md            # Human-readable log
├── .agent_work/            # Per-task artifacts
│   └── {task_id}/
│       ├── plan.md
│       ├── review.md
│       ├── test_report_1.md
│       ├── regression.md
│       └── fix_plan_1.md (if needed)
├── .agent_state.json       # Supervisor state (crash recovery)
└── .agent.pid              # Daemon PID
```

---

## Auto-Continue (`auto_continue.sh`)

Simple "poke" script — sends "go on" to resume a paused Claude session.

```bash
./scripts/auto_continue.sh           # Run once
./scripts/auto_continue.sh --daemon  # Loop every 5 min
./scripts/auto_continue.sh --install # Add as cron job
```
