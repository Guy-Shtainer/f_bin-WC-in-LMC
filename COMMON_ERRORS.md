# Common Errors & Known Pitfalls

This file documents recurring bugs and deprecated patterns found in this project.
**Claude checks these patterns automatically before and after writing code.**

## Quick-Scan Regex

Combined grep pattern for all known bad patterns (copy-paste ready):

```bash
grep -rn -E 'np\.trapz\b|\.bool_\b.*is (True|False)|\.int_\b|\.float_\b|\.complex_\b|\.object_\b|\.str_\b|asyncio\.sleep|CLAUDECODE|allow_dangerously_skip_permissions|\.replace\(second=.*\.second\s*\+' --include='*.py' .
```

---

## Numpy Deprecations (numpy 2.x)

### E001 — `np.trapz` removed in numpy 2.0

| | |
|---|---|
| **Bad** | `np.trapz(y, x)` |
| **Fix** | `np.trapezoid(y, x)` |
| **Grep** | `np\.trapz\b` |
| **Why** | `numpy.trapz` was deprecated in 1.25 and removed in 2.0. Renamed to `numpy.trapezoid`. |
| **Found in** | `wr_bias_simulation.py`, `app/pages/05_bias_correction.py`, `CCF.py`, `CCF-old.py` |

### E002 — `numpy.bool_` identity comparison

| | |
|---|---|
| **Bad** | `if result is True:` (where `result` is `numpy.bool_`) |
| **Fix** | `if bool(result):` or `if result:` |
| **Grep** | `\.bool_\b.*is (True\|False)` |
| **Why** | `numpy.bool_(True) is True` evaluates to `False` because they are different objects. Always cast with `bool()` before using `is` comparisons. |
| **Found in** | Various files comparing numpy array element results |

---

## Data Handling

### E003 — Missing zero-filter on RV arrays

| | |
|---|---|
| **Bad** | Using raw RV arrays directly from `.npz` property files |
| **Fix** | `rv = rv[rv != 0]` before any analysis |
| **Grep** | *(not greppable — requires manual attention)* |
| **Why** | Missing/unavailable epochs are stored as `0.0` in the RV property arrays. Using them without filtering corrupts ΔRV calculations. |
| **Found in** | `pipeline/load_observations.py`, any code loading `full_RV` properties |

---

## Streamlit

### E004 — Duplicate widget keys in `st.empty()` slots

| | |
|---|---|
| **Bad** | Calling `slot.plotly_chart(..., key='same_key')` twice in one script run |
| **Fix** | Guard with `if not run_btn:` or use different keys for live vs display rendering |
| **Grep** | *(not greppable — requires manual attention)* |
| **Why** | Streamlit raises `StreamlitDuplicateElementKey` when two widgets in the same run share a key. `st.empty()` slots reused during live updates and post-run display can trigger this. |
| **Found in** | `app/pages/05_bias_correction.py` (heatmap slot) |

---

## Shell & Environment

### E005 — Hebrew/Unicode paths fail in shell `cd`

| | |
|---|---|
| **Bad** | `cd "/path/with/תואר שני!/..."` in zsh |
| **Fix** | Use relative paths, or let the shell inherit cwd (don't `cd` at all) |
| **Grep** | *(not greppable — requires manual attention)* |
| **Why** | zsh and bash mishandle multi-byte Hebrew characters in paths, especially when escaped. The `cd` command silently corrupts the path encoding. |
| **Found in** | Bash tool calls during agent debugging |

### E006 — CLAUDECODE env var blocks nested Claude sessions

| | |
|---|---|
| **Bad** | Running `claude-agent-sdk` `query()` from within a Claude Code session |
| **Fix** | `os.environ.pop('CLAUDECODE', None)` before calling `query()` |
| **Grep** | `CLAUDECODE` |
| **Why** | Claude Code sets a `CLAUDECODE` environment variable. The Agent SDK detects this and refuses to launch a nested session. Removing the var before the SDK call allows it to proceed. |
| **Found in** | `scripts/overnight_agent.py` (`run_task`) |

---

## Async / Concurrency

### E007 — `asyncio.sleep` inside anyio cancel scope

| | |
|---|---|
| **Bad** | `await asyncio.sleep(N)` inside an async generator from `claude-agent-sdk` |
| **Fix** | `await loop.run_in_executor(None, time.sleep, N)` |
| **Grep** | `asyncio\.sleep` |
| **Why** | The `claude-agent-sdk` uses `anyio` internally with cancel scopes. `asyncio.sleep()` is not compatible with anyio cancel scopes — when the generator is garbage-collected, the cancel scope fires and kills the sleep, raising `CancelledError`. Using a synchronous `time.sleep` in an executor avoids the cancel scope entirely. |
| **Found in** | `scripts/overnight_agent.py` (rate limit handler) |

### E008 — Git checkout fails with dirty working tree

| | |
|---|---|
| **Bad** | `git checkout <branch>` when tracked files have uncommitted changes |
| **Fix** | `git stash --include-untracked` before checkout, `git stash pop` after |
| **Grep** | *(not greppable — requires manual attention)* |
| **Why** | Git refuses to switch branches if it would overwrite uncommitted changes to tracked files. In the overnight agent, `agent_log.md` is continuously written by `log()`, making the working tree always dirty during task execution. |
| **Found in** | `scripts/overnight_agent.py` (`git_create_branch`, `git_back_to_main`) |

### E009 — Async generator not properly closed

| | |
|---|---|
| **Bad** | Breaking out of `async for msg in query(...)` without cleanup |
| **Fix** | Wrap in try/finally, call `await gen.aclose()` catching `RuntimeError` |
| **Grep** | *(not greppable — requires manual attention)* |
| **Why** | Breaking out of an `async for` loop does not automatically close the async generator in all Python versions. The generator may hold open connections (to Claude Code subprocess) that cause errors on garbage collection. Explicit `aclose()` ensures clean shutdown. |
| **Found in** | `scripts/overnight_agent.py` (`run_task`) |

---

### E010 — `allow_dangerously_skip_permissions` not a valid kwarg

| | |
|---|---|
| **Bad** | `ClaudeAgentOptions(allow_dangerously_skip_permissions=True, ...)` |
| **Fix** | Just use `permission_mode='bypassPermissions'` — no extra flag needed |
| **Grep** | `allow_dangerously_skip_permissions` |
| **Why** | The `claude-agent-sdk` `ClaudeAgentOptions` does not accept this parameter. The `permission_mode='bypassPermissions'` alone is sufficient. |
| **Found in** | `scripts/overnight_agent.py` |

---

### E011 — `--status` only detects daemon-mode agents

| | |
|---|---|
| **Bad** | Checking only `.agent.pid` file for running agent detection |
| **Fix** | Also check `.agent_state.json` recency (updated_at within last 5 min) |
| **Grep** | *(not greppable)* |
| **Why** | When the agent runs in foreground (not daemon), no PID file is created. The `--status` command returned "not running" even during active foreground runs. |
| **Found in** | `scripts/overnight_agent.py` |

---

### E012 — Streamlit `st.page_link()` path resolution

| | |
|---|---|
| **Bad** | `st.page_link('agent_app/app.py', label='Dashboard')` — prefixed with subdir |
| **Fix** | `st.page_link('app.py', label='Dashboard')` — bare path relative to entrypoint directory |
| **Grep** | *(not reliably greppable — depends on directory structure)* |
| **Why** | `st.page_link()` resolves paths relative to the **entrypoint file's parent directory**, NOT the CWD. When running `streamlit run agent_app/app.py`, a bare `'app.py'` resolves to `agent_app/app.py` (correct). Prefixing with `'agent_app/app.py'` resolves to `agent_app/agent_app/app.py` (double-nested, crashes). This matches `app/shared.py` which also uses bare paths. Note: the original bare-path error was caused by files not existing on disk (they were on a different git branch), not a path resolution issue. |
| **Found in** | `agent_app/shared.py` (`render_sidebar`) |

---

### E013 — Agent branch file loss after branch switch

| | |
|---|---|
| **Bad** | Creating new files only on agent feature branches, never committing to main |
| **Fix** | Always commit shared infrastructure (webapp, settings, configs) to main first before running agents. Or recover with `git checkout <commit> -- <path>` |
| **Grep** | *(not greppable — requires workflow awareness)* |
| **Why** | The overnight agent creates feature branches for each task. When the supervisor switches between branches or back to main, files created on a feature branch disappear from the working tree. The `__pycache__/` dirs survive (they're in `.gitignore`) as ghost evidence the files once existed. |
| **Found in** | `agent_app/` — all files lost after agent branch switches |

---

### E014 — Rate limit `resume_at` timestamp overflow

| | |
|---|---|
| **Bad** | `datetime.now().replace(second=datetime.now().second + sleep_time)` |
| **Fix** | `(datetime.now() + timedelta(seconds=sleep_time)).isoformat()` |
| **Grep** | `\.replace\(second=.*\.second\s*\+` |
| **Why** | `datetime.replace(second=N)` requires N in 0–59. When `second + sleep_time > 59`, it raises `ValueError`. Use `timedelta` addition instead. |
| **Found in** | `scripts/overnight_agent.py` (`run_agent_with_retry`) |

---

## Adding New Errors

When you encounter a new recurring error, add it here with:
1. An **ID** (E005, E006, ...) and descriptive title
2. The **bad** and **fix** code patterns
3. A **grep regex** if the pattern is machine-detectable
4. **Why** it happens
5. **Where** it was found
6. Update the **Quick-Scan Regex** at the top if a new greppable pattern was added
