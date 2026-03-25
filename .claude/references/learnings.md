# Learnings — Active Rules

Rules are ordered by recency (most recently triggered/added at top).
Rules are NEVER deleted — only archived when the underlying code/pattern is verified gone.

## Active Rules

### Agent Architecture
- **Pipeline constraints ≠ Claude intelligence**: When the agent fails, check if the pipeline is blocking it before blaming the model. Rigid verify→fix loops, scoped prompts, and false-positive gates make the agent "stupid" — not the model. The user wants "let Claude be Claude." (last_triggered: 2026-03-24)
- **Pin-point fixes vs systemic issues**: When the user describes a systemic problem, don't propose a narrow fix. Listen for the broader pattern they're describing. E.g., "why is the agent dumb" → the issue is the pipeline architecture, not one Hebrew path bug. (last_triggered: 2026-03-24)

### Context & Memory
- **Never claim code is fixed without reading it**: User caught me claiming A7 was updated 4 times when it wasn't — `model_type='cadence_dsilva'` didn't match `'dsilva'` so the old code path ran. Always verify the ACTUAL call path, not just the edited function. (last_triggered: 2026-03-25)
- **Reverse-audit: read code → compare to MD, not MD → trust memory**: When verifying, read the actual code fresh and describe what it does NOW, then compare. Don't just re-read the MD comments and claim they match. (last_triggered: 2026-03-25)
- **Never ignore user commands**: When user says "search online for X" or "do Y", do it. Don't skip or substitute your own approach. (last_triggered: 2026-03-25)
- **Update GRAPHS_PER_METHOD.md + FEATURES.md with EVERY code change**: These are the regression checklists. Comments can only be removed after user review approves the graph. (last_triggered: 2026-03-25)
- **Verify current app state, don't trust stale memory**: Before writing about app features (tabs, scoring methods, UI), check the actual code. Memory entries about app state decay fast. (last_triggered: 2026-03-23)
- **Keep code comments minimal**: Don't bloat code files with descriptions. `# WORKING — do not change this code` is sufficient. Put context about what code does in reference files, not inline comments. (last_triggered: 2026-03-23)
- **Don't trim upstream skills**: Skill files from Anthropic's GitHub (daymade-skill-creator, anthropic-skill-creator) are not ours to trim. At most update from upstream. (last_triggered: 2026-03-23)

### Data & Debugging
- **DATA BEFORE DISPLAY**: Read raw data/state before fixing any display bug. Don't assume format. (last_triggered: 2026-03-22)
- **Root cause first**: State "bug is at file:line because X" before editing. No edits until identified. (last_triggered: 2026-03-22)
- **One file only**: If bug is in one file, edit only that file. Second file needs user justification. (last_triggered: 2026-03-22)
- **After 2 failed attempts → different approach**: Stop varying the same knob. Step back or ask user. (last_triggered: 2026-03-18)
- **Grep all downstream consumers**: After any fix, trace all consumers of changed function/variable. Especially when removing a function from a shared module (e.g., `binned_cdf` removal broke 5+ files). (last_triggered: 2026-03-23)
- **`# WORKING` flags**: Place `# WORKING — do not change this code` above verified working code. Never modify flagged code unless user explicitly asks. If you need to understand what flagged code does, check `.claude/references/working-code-map.md` instead of guessing. (last_triggered: 2026-03-22)

### Testing
- **Run /error-check immediately after edits**: Don't summarize or mark tasks done until /error-check has run. It's part of the task, not a follow-up step. User had to remind multiple times. (last_triggered: 2026-03-25)
- **py_compile is NOT sufficient**: Must run pyflakes (catches NameError/undefined vars) + `scripts/test_render.py` (loads real .npz, mocks Streamlit, calls render functions). User caught 3 runtime errors that py_compile missed. (last_triggered: 2026-03-25)
- **Real tests, not just py_compile**: edit → delete .pyc → functional test → py_compile. (last_triggered: 2026-03-22)
- **Test Streamlit renders**: Call render functions with mock `obs_data` in bare mode. Only Exceptions are failures. (last_triggered: 2026-03-18)
- **Parameter verification**: New functions replicating existing computations must receive IDENTICAL params. (last_triggered: 2026-03-15)

### User Interaction
- **Graph review: match rendering order**: When walking user through graphs/plots, present them in exact top-to-bottom rendering order. User corrected twice when order was wrong — they need positional context to give accurate feedback. (last_triggered: 2026-03-24)
- **Questions ≠ requests**: When user asks "can I do X?" or "does X work?", ANSWER the question first. Don't start implementing. Only code when explicitly asked. (last_triggered: 2026-03-23)
- **Align before non-trivial changes**: If confidence < 90%, ASK. User repeating = misunderstanding. (last_triggered: 2026-03-22)
- **Ask before refactoring**: Don't touch "improvable" code near the bug. Mention it, let user decide. (last_triggered: 2026-03-22)

### UI/Webapp
- **Replicate across both cadence tabs**: Cadence Dsilva and Cadence Langer must have identical features. (last_triggered: 2026-03-18)
- **Compact side-by-side layouts**: Group min/max, μ/σ pairs in 2-column; 3-column for grid scans; sliders full-width. (last_triggered: 2026-03-15)
- **File size limit 800 lines**: Pre-plan splitting. Thin-wrapper pattern for pages. Check `wc -l` before adding. (last_triggered: 2026-03-18)
- **4σ significance in playground**: f(T) curve must apply ΔRV − 4σ > 0, not just ΔRV > threshold. (last_triggered: 2026-03-18)

### Streamlit Quirks
- **st.caption() truncates** in narrow columns → `st.markdown(unsafe_allow_html=True)` with `<span>`
- **st.markdown() strips `<script>`** → `st.components.v1.html()` for JS
- **st.session_state.pop() doesn't clear widgets** → form version counter `_v{N}` suffix
- **`@st.cache_data` underscore params (E023)** → `_`-prefixed params excluded from cache key
- **Bulk transforms** → Python regex script, not repeated Edit calls

### Error Documentation
- **After fixing ANY runtime error** → immediately add to `COMMON_ERRORS.md` with ID, grep pattern, fix. (last_triggered: 2026-03-23)

## Archived Rules
(Rules moved here only when underlying code/pattern is verified gone)

_None yet._
