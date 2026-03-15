---
description: "Execute the next agent task from queue or TODO.md"
argument-hint: "[task_id | 'next' | 'freeform: description']"
---

# Automated Task Execution Pipeline

You are an autonomous agent executing tasks from a queue. Follow each phase precisely.
Write status updates to `.claude/agent-status.json` at every phase transition.

## Phase 0: Read Task

Read `.claude/agent-task.json`. If it exists and has a non-empty `queue` array, pop the first
task ID from the queue. Look up that task in `TODO.md` (Open Tasks table) to get its title and
description.

If no `.claude/agent-task.json` exists, check `$ARGUMENTS`:
- A number (e.g., `42`) → load that task ID from TODO.md
- `next` → pick the first `open` task from TODO.md sorted by priority (critical > high > medium > low)
- `freeform: <text>` → use the text as the task description (no TODO.md lookup)
- Empty / no args → output `<promise>ALL_DONE</promise>` and stop

Write initial status:
```
Use the Write tool to create .claude/agent-status.json with:
{
  "phase": "starting",
  "task_id": <id or "freeform">,
  "title": "<title>",
  "started_at": "<ISO timestamp>",
  "log": [{"time": "<HH:MM:SS>", "msg": "Starting task #<id>: <title>"}],
  "completed_tasks": <read from previous status file if exists>,
  "error": null
}
```

## Phase 1: Explore

Update status: `"phase": "explore"`

Launch an **Explore** subagent with this prompt:
> Read CLAUDE.md, COMMON_ERRORS.md, and any files relevant to this task.
> Task #{id}: {title}
> Description: {description}
> Find: (1) which files need to be modified, (2) existing patterns/utilities to reuse,
> (3) any gotchas from COMMON_ERRORS.md that apply, (4) related code that could break.
> Be thorough — read the actual files, don't guess.

Save the explore output for the next phase.

## Phase 2: Plan

Update status: `"phase": "plan"`

Launch a **Plan** subagent with this prompt:
> Based on the exploration results below, design an implementation plan.
> Task: {title} — {description}
> Exploration findings: {explore_output}
>
> Create a step-by-step plan: which files to edit, what changes to make,
> what to test. Follow CLAUDE.md conventions. Be specific — include line
> numbers and function names. Identify risks and how to mitigate them.

Save the plan output.

## Phase 3: Implement

Update status: `"phase": "implement"`

Execute the plan directly. For each file you modify:
1. Read the file first (never edit blind)
2. Make the changes using Edit tool
3. Run `conda run -n guyenv python -m py_compile <file>` immediately after
4. If py_compile fails, fix the error before moving on

Log each file modified in the status file.

**CRITICAL RULES:**
- Follow ALL rules in CLAUDE.md (error checking, import conventions, etc.)
- After EVERY .py file edit, scan for COMMON_ERRORS patterns
- Never break existing functionality — if unsure, read more code first
- Use `@st.cache_data` with no expiry for expensive computations in Streamlit
- Wavelengths: FITS files are nm, display in Angstrom (multiply by 10)
- Use `PLOTLY_THEME` from shared.py for plots (never hardcode colors)

## Phase 4: Quality Check

Update status: `"phase": "quality_check"`

For ALL modified .py files:
1. `conda run -n guyenv python -m py_compile <file>` — must pass
2. Read COMMON_ERRORS.md, extract the Quick-Scan Regex, grep each modified file
3. Check for any obvious issues: missing imports, undefined variables, broken logic

If any check fails:
- Fix the issue
- Re-run all checks
- Maximum 2 fix attempts. If still failing after 2 retries:
  - Run `git checkout -- .` to revert ALL uncommitted changes
  - Log the failure in status: `"error": "Quality check failed after 2 retries: <details>"`
  - Skip to Phase 6 (do NOT commit broken code)

## Phase 5: Commit

Update status: `"phase": "commit"`

1. Verify the Data symlink exists: `ls -la Data` — if missing, restore with `ln -s ../Data Data`
2. `git add` ONLY the specific files you changed (NEVER `git add -A`)
3. Commit with a descriptive message + Co-Authored-By trailer
4. If the task came from TODO.md, update the task's Status column to `to-test`
   (use Edit tool on TODO.md, find the row by task ID, change `open` → `to-test`)
5. If TODO.md was modified, `git add TODO.md` and commit separately

Log the commit hash in the status file.

## Phase 6: Next or Done

Update status: `"phase": "idle"` with the completed task added to `completed_tasks` array.

Check `.claude/agent-task.json`:
- If `queue` still has task IDs: the file was already updated in Phase 0 (you popped one).
  Output: `<promise>NEXT</promise>`
- If `queue` is empty or file doesn't exist:
  Output: `<promise>ALL_DONE</promise>`

## Error Recovery

If at ANY point something goes catastrophically wrong:
1. Run `git checkout -- .` to revert all uncommitted changes
2. Verify Data symlink: `ls -la Data` → if broken: `ln -s ../Data Data`
3. Update status with error details
4. If there are more tasks in queue → output `<promise>NEXT</promise>` (skip this task, try next)
5. If no more tasks → output `<promise>ALL_DONE</promise>`

NEVER leave the repo in a broken state. Either commit working code or revert everything.
