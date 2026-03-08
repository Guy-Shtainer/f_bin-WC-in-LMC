---
name: todo-manager
description: Maintain the project TODO.md file — add, update, and complete tasks. This skill triggers whenever tasks are discussed, completed, deferred, or when new work items arise from conversations with the user or their thesis advisor (Tomer). Also trigger when the user says "add to the to-do list", "mark as done", "what's left to do", mentions pending work, or when Claude identifies follow-up tasks after completing a coding change. Proactively add tasks when they come up in conversation.
---

# To-Do Manager

Maintain `TODO.md` at the project root. This file is both human-readable (visible
in VS Code) and parsed by the webapp (`app/pages/10_todo.py`).

## File Format

```markdown
# Project To-Do List

## Open Tasks
| ID | Title | Description | Priority | Tags | Status | Added by | Suggested by | Date added | Urgent | Important | Notes |
|----|-------|-------------|----------|------|--------|----------|-------------|------------|--------|-----------|-------|

## Done
| ID | Title | Description | Priority | Tags | Status | Added by | Suggested by | Date added | Urgent | Important | Date done | Notes |
|----|-------|-------------|----------|------|--------|----------|-------------|------------|--------|-----------|-----------|-------|

## Deleted
| ID | Title | Date deleted | Notes |
|----|-------|-------------|-------|
```

## Adding a Task

- Assign the next sequential ID (read existing IDs from Open, Done, AND Deleted to find the max)
- Set `Status` to `open` (or `in-progress` if starting immediately)
- `Added by`: who is writing it now (Claude, Guy, etc.)
- `Suggested by`: who originally proposed it (Tomer, Guy, Claude, etc.)
- `Priority`: `critical`, `high`, `medium`, or `low`
- `Tags`: comma-separated labels (e.g., `bias-correction`, `webapp`, `paper`, `bug`)
- `Date added`: full datetime — `datetime.now().isoformat(timespec='seconds')` (e.g., `2026-03-08T18:18:44`)
- `Urgent`: `Y` or `N` (Eisenhower matrix)
- `Important`: `Y` or `N` (Eisenhower matrix)
- Priority is auto-derived: urgent+important=critical, important=high, urgent=medium, neither=low
- `Notes`: initially empty; used for modification timestamps, decline feedback, etc.

## Status Workflow

```
open → in-progress → to-test → done
```

**CRITICAL RULES:**
- When Claude finishes implementing a task, set status to `to-test` — **NEVER** to `done`
- Only the USER can confirm tasks and move them to the Done section (via the webapp UI)
- Update the task description to briefly summarize what was implemented
- If the user declines a to-test task, it goes back to `open` with `declined` tag and feedback in Notes

## Completing a Task (to-test)

1. Change `Status` from `open`/`in-progress` to `to-test` in the Open Tasks table
2. Update `Description` with a brief summary of what was done
3. Do NOT move to Done — the user confirms via the webapp

## Deleting a Task

- Deleted tasks go to the `## Deleted` section (4 columns: ID, Title, Date deleted, Notes)
- They can be restored to Open or permanently deleted via the webapp

## Proactive Behavior

- When the user or Tomer mentions something that should be done → add it
- When Claude identifies a follow-up after finishing a task → add it
- After implementing any feature/fix → update the task status to `to-test`
- Preserve insertion order in the file — UI sort handles display ordering

## Notes

- The webapp page `app/pages/10_todo.py` reads and writes this same file
- Keep descriptions concise (one sentence)
- Use consistent tag names across items
- The Notes column tracks: `[Modified TIMESTAMP]`, `[DECLINED TIMESTAMP] reason`
