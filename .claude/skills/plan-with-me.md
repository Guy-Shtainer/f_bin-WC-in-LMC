# Plan With Me

Auto-triggered skill for collaborative session planning.

## When to trigger
- At the start of any new conversation/session
- When the user says "let's plan", "what should we work on", "plan with me"
- Before starting any non-trivial implementation task (unless the user says "just do it" or similar)

## Workflow

### Step 1: Review priorities
1. Read `TODO.md` to get all open tasks with their urgent/important flags
2. Identify the Eisenhower quadrant distribution:
   - **Do First** (urgent + important) — these are the critical items
   - **Schedule** (important, not urgent) — plan these into future sessions
   - **Delegate/Urgent** (urgent, not important) — quick fixes
   - **Eliminate** (neither) — deprioritize or remove

### Step 2: Propose a session plan
1. Select 2-4 tasks for the current session based on:
   - Priority order (critical first)
   - Logical grouping (related tasks together)
   - Scope estimation (don't overload a single session)
2. For each task, briefly describe:
   - What needs to be done
   - Which files are likely involved
   - Estimated complexity (small/medium/large)
3. If a task is too large for one session, propose splitting it

### Step 3: Ask clarifying questions
Use `AskUserQuestion` to confirm:
- Does the proposed session plan look right?
- Any tasks to swap in/out?
- Any scope clarifications needed?
- Are there new tasks or priorities not in TODO.md?

### Step 4: Divide into sessions
If there are more tasks than fit in one session:
- Present a multi-session roadmap (Session 1, 2, 3...)
- Each session should have a clear theme/goal
- Critical items always come first

### Step 5: Execute
Once the user confirms, proceed with implementation using:
- TodoWrite to track progress within the session
- Commit after each logical change (git-workflow skill)
- Update TODO.md when tasks are completed (todo-manager skill)

## Key principles
- **Always ask before diving in** — the user's priorities may have changed
- **Keep sessions focused** — 2-4 tasks max per session
- **Quality over quantity** — it's better to finish 2 tasks well than rush 4
- **Surface blockers early** — if a task depends on user input or external info, ask upfront
- **End sessions cleanly** — commit all changes, update TODO.md, update DOCUMENTATION.md
