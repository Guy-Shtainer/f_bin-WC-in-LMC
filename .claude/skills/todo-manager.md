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
| ID | Title | Description | Priority | Tags | Status | Added by | Suggested by | Date added |
|----|-------|-------------|----------|------|--------|----------|-------------|------------|

## Done
| ID | Title | Date done |
|----|-------|-----------|
```

## Adding a Task

- Assign the next sequential ID (read existing IDs to find the max)
- Set `Status` to `open` (or `in-progress` if starting immediately)
- `Added by`: who is writing it now (Claude, Guy, etc.)
- `Suggested by`: who originally proposed it (Tomer, Guy, Claude, etc.)
- `Priority`: `critical`, `high`, `medium`, or `low`
- `Tags`: comma-separated labels (e.g., `bias-correction`, `webapp`, `paper`, `bugfix`)
- `Date added`: today's date in ISO format (YYYY-MM-DD)

## Completing a Task

1. Remove the row from the "Open Tasks" table
2. Add it to the "Done" table with today's date as `Date done`
3. Keep Done items sorted by date (newest first)

## Proactive Behavior

- When the user or Tomer mentions something that should be done → add it
- When Claude identifies a follow-up after finishing a task → add it
- When a task is clearly completed → move it to Done
- Sort Open tasks by priority (critical first, then high, medium, low)

## Notes

- The webapp page `app/pages/10_todo.py` reads and writes this same file
- Keep descriptions concise (one sentence)
- Use consistent tag names across items
