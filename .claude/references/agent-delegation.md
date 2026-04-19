# Agent Delegation Rules

When to spawn which agent. Loaded on-demand from [CLAUDE.md](../../CLAUDE.md) and [MEMORY.md](../../../.claude/projects/-Users-guyshtainer-Library-CloudStorage-OneDrive-Tel-AvivUniversity-----------Thesis-Thesis-codes/memory/MEMORY.md).

**Always write a briefing first** — see [comms-protocol.md](comms-protocol.md).

## Trigger table

| Trigger | Agent | Follow-up chain |
|---------|-------|-----------------|
| Scientific validation, binary classification, bias sim, pipeline question | `scientist` | (often → coder → QA) |
| Writing Python code >30 lines, multiprocessing, Streamlit/Dash edits | `coder` | → QA (always, when UI/user-facing) |
| UI layout / control placement / user-intent translation ("make it cleaner", "move X") | `designer` | → coder → QA |
| Designing or reviewing a Plotly chart (A&A style, contrast, accuracy) | `plots` | → coder → QA |
| Drafting / editing any file in `paper/` | `writer` | (often ← scientist review) |
| Creating / fixing / reviewing a skill or plugin | `meta-tools` | — |
| Any coder run touching UI, user-facing behavior, or data display | `qa` (auto) | (always runs after coder) |

## Hard rules

1. **QA is mandatory after coder** whenever the change touches UI, user-facing behavior, or data display. No exceptions.
2. **Designer before coder** when the user describes a UI change in intent terms ("make this cleaner", "move the controls", "I want X to feel Y").
3. **Plots before coder** when the user describes chart content or style.
4. **Designer and plots can run in parallel** when both layout AND chart styling are in scope.
5. **Trivial edits skip the chain** — 1-line fix, typo, config toggle → orchestrator does it inline.
6. **Scientist review before writer** when content in `paper/` touches results or methodology (not just prose polish).
7. **QA-FAIL loop max 3 rounds** — after 3 failed rounds, escalate to user.

## Decision flow

```
User asks for a change.
│
├─ Trivial (1 line, typo, config)?
│   └─ Do it inline. No agent spawn.
│
├─ UI change described in intent terms?
│   └─ designer → coder → QA (loop on FAIL)
│
├─ Chart change (content or style)?
│   └─ plots → coder → QA (loop on FAIL)
│
├─ Science question / pipeline / data method?
│   └─ scientist (may chain → coder → QA)
│
├─ Paper content (paper/ dir)?
│   └─ scientist review (if results touched) → writer
│
├─ Skill / plugin / tooling?
│   └─ meta-tools
│
└─ Pure code implementation (no UI intent)?
    └─ coder → QA (if user-facing) or coder alone (if pure backend)
```

## Parallel spawns

Multiple agents can run in parallel in a single orchestrator turn when they're independent:
- `designer` + `plots` together when a page redesign touches both layout and chart styling
- `scientist` + `writer` together when a paper section needs a science cross-check while the draft is being polished

Do **not** run `coder` in parallel with its upstream spec agent (designer / plots / scientist) — the coder must wait for the spec to land in comms.

## Escalation rules

- 3+ QA FAILs in a row → stop looping, summarize for the user, ask for direction
- Agent returns BLOCKED status → read their comms file, decide whether to spawn a helper agent or ask the user
- Orchestrator unsure which agent fits → ask the user with AskUserQuestion rather than guessing
