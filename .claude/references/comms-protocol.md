# Comms Protocol

Single source of truth for how the orchestrator and the 7 agents coordinate through shared files in `.claude/agents/comms/`.

## Orchestrator responsibilities

**Before spawning ANY agent:**
1. Write `.claude/agents/comms/briefing.md` using `briefing.template.md` as the skeleton. Include:
   - Task (one paragraph: what, why, expected outcome)
   - Assigned agent(s) and order in the chain
   - Relevant file paths and context (code pointers, related memory files)
   - Round number (`1` for first spawn, increment on re-spawns within the same chain)

**After an agent returns:**
2. Read `.claude/agents/comms/{agent}.md` for the agent's output — do not rely solely on the inline summary the Agent tool returns
3. If chaining (e.g. designer → coder), update `briefing.md` (bump round, add context from the upstream agent's comms file) before spawning the next agent
4. If looping (e.g. QA says FAIL), re-spawn coder with the QA feedback as part of the updated briefing

## Agent responsibilities

**At start of every invocation:**
1. Read `.claude/agents/comms/briefing.md` first
2. Read upstream agents' comms files relevant to your role in the chain. See "Standard chains" below for who to read.

**At end of every invocation:**
3. Write your output to `.claude/agents/comms/{your-name}.md` with:
   - Decision / recommendation / verdict
   - Reasoning (brief — cite files/lines, memory files, acceptance criteria)
   - Follow-ups or handoffs for downstream agents
   - Status label: `READY`, `NEEDS-INPUT`, or `BLOCKED`

Each agent definition has a per-agent output format in its "Communication Protocol" section. Use that format.

## Standard chains

| Task type | Chain | Reads upstream comms |
|---|---|---|
| UI change | designer → coder → QA (loop) | coder reads designer; QA reads designer + coder |
| Chart change | plots → coder → QA | coder reads plots; QA reads plots + coder |
| Science → code | scientist → coder → QA | coder reads scientist; QA reads scientist + coder |
| Paper section | scientist → writer | writer reads scientist |
| Tooling / skill | meta-tools | — |

The coder ALWAYS has QA downstream when the change touches UI, user-facing behavior, or data display.

## Looping on QA FAIL

1. QA writes verdict FAIL to `comms/qa.md` with specific mismatches
2. Orchestrator updates `briefing.md` (round++, appends QA feedback as explicit fix instructions)
3. Orchestrator re-spawns coder
4. Coder reads the updated briefing + its own previous `comms/coder.md` + QA feedback, produces a new edit
5. QA re-spawned, reads round-N coder output, verifies
6. Continue until QA returns PASS or a max of 3 rounds (escalate to user if 3 rounds pass without PASS)

## When NOT to use the protocol

- **Trivial edits** (1-line fix, typo, config toggle) — orchestrator works inline, no agent spawn, no briefing
- **Pure research / read-only exploration** — use the general-purpose or Explore agent, no comms file writes needed
- **Emergency rollback** — fix first, document in comms after
