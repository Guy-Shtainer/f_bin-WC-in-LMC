# Common Errors & Known Pitfalls

This file documents recurring bugs and deprecated patterns found in this project.
**Claude checks these patterns automatically before and after writing code.**

## Quick-Scan Regex

Combined grep pattern for all known bad patterns (copy-paste ready):

```bash
grep -rn -E 'np\.trapz\b|\.bool_\b.*is (True|False)|\.int_\b|\.float_\b|\.complex_\b|\.object_\b|\.str_\b|CLAUDECODE|allow_dangerously_skip_permissions|\.replace\(second=.*\.second\s*\+' --include='*.py' .
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

### E016 — `asyncio.sleep` cancelled by SDK cancel scope

| | |
|---|---|
| **Bad** | `await asyncio.sleep(seconds)` after SDK `query()` generator cleanup |
| **Fix** | Use `time.sleep()` (blocking) via `_blocking_sleep()` helper instead |
| **Grep** | `asyncio\.sleep` (in scripts/ — verify not near SDK generator usage) |
| **Why** | `claude-agent-sdk` uses anyio cancel scopes internally. When a `query()` generator is partially consumed (e.g., bail on rate limit) and `aclose()`d, the scope cleanup runs in a background task and can cancel `asyncio.sleep()` futures in other tasks, raising `CancelledError` and crashing the process. `time.sleep()` is a blocking OS call, immune to asyncio cancellation. |
| **Found in** | `scripts/overnight_agent.py` (`run_agent_with_retry` — sleep between retries) |

---

## Plotly / Theme

### E018 — `**PLOTLY_THEME` keyword collision in function calls

| | |
|---|---|
| **Bad** | `fig.update_layout(title=dict(...), **PLOTLY_THEME)` or `dict(title=..., **PLOTLY_THEME)` |
| **Fix** | `fig.update_layout(**{**PLOTLY_THEME, 'title': dict(...)})` (dict literal with override) |
| **Grep** | *(not reliably greppable — requires manual attention)* |
| **Why** | `PLOTLY_THEME` contains `title`, `legend`, `xaxis`, `yaxis`, `font` keys. Python raises `TypeError: got multiple values for keyword argument` when the same key appears both as an explicit kwarg AND inside `**dict_unpack` in any function call (`dict()`, `update_layout()`, etc.). Dict literal syntax `{**base, 'key': override}` allows later keys to override earlier ones. |
| **Colliding keys** | `title`, `legend`, `yaxis`, `xaxis`, `font` |
| **Found in** | `app/pages/05_bias_correction.py` (10 sites) |

---

### E019 — Data symlink destroyed by git operations

| | |
|---|---|
| **Bad** | `Data/` symlink missing after git checkout/stash/branch switch |
| **Fix** | `ln -s ../Data Data` from project root |
| **Grep** | *(not greppable — check after git operations)* |
| **Why** | Git does not preserve symlinks reliably across branch switches and stash operations. The `Data/` symlink points to `../Data` and must be restored manually when missing. |
| **Found in** | Project root — causes "Could not load star data" on home page |

---

### E020 — `make_heatmap_fig()` missing required `title` argument

| | |
|---|---|
| **Bad** | `_make_heatmap_fig(z, fbin, x_vals, x_label='π', height=400)` |
| **Fix** | `_make_heatmap_fig(z, fbin, x_vals, title='My title', x_label='π', height=400)` |
| **Grep** | `_make_heatmap_fig(` (manual check — verify `title=` is always 4th arg) |
| **Why** | `make_heatmap_fig` in `shared.py` has `title: str` as a required positional parameter (4th). Omitting it causes `TypeError: missing 1 required positional argument: 'title'`. Easy to miss because all other params have defaults. |
| **Found in** | `app/pages/05_bias_correction.py` — compare tab `_render_compare_tab()` |

---

### E021 — Dict comprehension variable shadows function parameter

| | |
|---|---|
| **Bad** | `def func(p): paths = {n: p for n, p in items}` |
| **Fix** | `def func(p): paths = {n: fp for n, fp in items}` |
| **Grep** | *(not reliably greppable — code review pattern)* |
| **Why** | Python dict/list comprehension variables leak into (Python 2) or shadow (Python 3) the enclosing scope. If a function parameter is named `p` and a comprehension uses `p` as an iteration variable, the function parameter is shadowed within the comprehension. All subsequent uses of `p` in the function still refer to the parameter, but code inside the same expression sees the loop variable. This caused the compare tab to completely break — `f'{p}_sel_a'` keys used the file path string instead of the prefix. |
| **Found in** | `app/pages/05_bias_correction.py` — `_render_compare_tab()` line 3788 |

### E022 — `multiprocessing.Pool` can't pickle functions in Streamlit pages

| | |
|---|---|
| **Bad** | Defining `def worker(args): ...` in `app/pages/*.py` and passing it to `multiprocessing.Pool.map()` |
| **Fix** | Move worker functions to a separate importable module (e.g. `app/nres_ccf_worker.py`) and `from nres_ccf_worker import worker` in the page |
| **Grep** | `multiprocessing\.Pool` (check if file is under `app/pages/`) |
| **Why** | Streamlit pages run as `__main__`, not as their module name. `multiprocessing.Pool` pickles function references by module path — `__main__.worker` can't be found by the child process. `ThreadPoolExecutor` avoids this (threads share the same process/namespace), but for CPU-bound work like `double_ccf`, true multiprocessing via Pool is needed. The solution is always to put Pool worker functions in a separate importable `.py` file. |
| **Found in** | `app/pages/11_nres_analysis.py` — `_process_single_line`, `_save_single_plot` (moved to `app/nres_ccf_worker.py`) |

---

### E023 — `@st.cache_data` ignores underscore-prefixed parameters from cache key

| | |
|---|---|
| **Bad** | `@st.cache_data` + `def func(_star_name, epoch):` — `_star_name` is excluded from cache key, so `func('WR 52', 1)` and `func('WR17', 1)` return the same cached result |
| **Fix** | Remove the leading underscore: `def func(star_name, epoch):` |
| **Grep** | `@st.cache_data` then `def.*\(_[a-z]` (parameter starting with `_` in a cached function) |
| **Why** | Streamlit treats parameters prefixed with `_` as "unhashable" and excludes them from the cache key. This is documented Streamlit behavior intended for unhashable objects like DB connections, but if used on a regular string/int parameter, all distinct values collapse to the same cache entry. |
| **Found in** | `app/pages/11_nres_analysis.py` — `_load_star_epochs(_star_name)`, `_load_normalized_flux(_star_name)`, `_get_mjd(_star_name)` all returned WR 52's data for WR17 too |

---

### E024 — Cache/reuse check missing newly added config fields

| | |
|---|---|
| **Bad** | Adding `q_flipped: bool` to `BinaryParameterConfig` but not including it in `_find_reusable_fbin_langer()` parameter comparison |
| **Fix** | Whenever a new field is added to a config dataclass, audit ALL cache/reuse/hash functions that compare configs |
| **Grep** | *(not greppable — requires code review discipline)* |
| **Why** | Cache reuse functions compare a subset of config fields to decide if a previous result can be reloaded. When new fields are added to the config (e.g., `q_flipped`, `q_preset`, `langer_period_params`), the cache check silently returns stale results computed with different parameter values. This caused false cache hits when switching between q presets or Case A/B weights in the Langer model. |
| **Found in** | `_find_reusable_fbin_langer()` in `wr_bias_simulation.py` — was missing checks for `q_preset`, `q_flipped`, and `langer_period_params` |

### E025 — UI variable removed but still referenced downstream

| | |
|---|---|
| **Bad** | Removing a UI widget (e.g., `lg_weight_A = st.slider(...)`) but leaving downstream references (`float(lg_weight_A)` in save_params, filename building, etc.) |
| **Fix** | Before removing any UI variable, grep for ALL occurrences of that variable name in the file. Fix or remove every reference. |
| **Grep** | *(not greppable — requires discipline: grep for the variable name before deleting its definition)* |
| **Why** | When refactoring UI controls (e.g., replacing presets with direct inputs), it's easy to remove the widget definition but miss downstream code that reads the variable for config saving, descriptive filenames, or display. Results in `NameError` at runtime. |
| **Found in** | `app/pages/05_bias_correction.py` — `lg_weight_A` removed from period UI but still referenced in `save_params` dict and case-tag filename logic |

---

### E026 — `st.rerun(scope='app')` inside polling fragment causes full-page flicker

| | |
|---|---|
| **Bad** | `@st.fragment(run_every=3)` → `st.rerun(scope='app')` to refresh live display |
| **Fix** | Put the live display elements (progress, heatmap, status) **inside** a `@st.fragment(run_every=3)` that renders them directly. Only use `st.rerun(scope='app')` once when the job completes to transition to the done state. |
| **Grep** | `st.rerun(scope='app')` inside any `run_every` fragment (manual check) |
| **Why** | `st.rerun(scope='app')` reruns the *entire page* from top to bottom, clearing all `st.empty()` slots and recreating them. The gap between clear and re-populate causes visible flicker (elements go dark for ~100ms). Fragment-scoped re-renders only update the fragment's content. |
| **Found in** | `app/pages/05_bias_correction.py` — global `_auto_refresh` fragment at page bottom |

---

### E027 — `np.empty()` for accumulation arrays leaves garbage in uncomputed cells

| | |
|---|---|
| **Bad** | `ks_p = np.empty((n_sig, n_fb, n_pi), dtype=float)` |
| **Fix** | `ks_p = np.full((n_sig, n_fb, n_pi), np.nan)` |
| **Grep** | `np\.empty\(` (check if used for accumulation arrays where NaN sentinel is needed) |
| **Why** | `np.empty` fills with uninitialized memory (arbitrary floats). When computing `max()` or `argmax()` on partially-filled arrays, garbage values in uncomputed cells produce wrong results. Always use `np.full(..., np.nan)` for arrays that accumulate results incrementally. |
| **Found in** | `app/pages/05_bias_correction.py` — `_run_cadence_bg()` line ~4380 |

---

### E028 — Variable defined in UI section used before that section renders

| | |
|---|---|
| **Bad** | `logPmax_scan_vals = np.array([float(logP_max_val)])` (when `logP_max_val` is defined in an expander that renders later) |
| **Fix** | `logPmax_scan_vals = np.array([float(st.session_state[f'{p}_logP_max'])])` (read from session_state which is pre-initialized) |
| **Grep** | N/A — requires manual review when moving UI sections between columns |
| **Why** | When reorganizing Streamlit layouts (e.g., moving an expander from left to right column), variables defined inside widgets may be referenced earlier in the render order than where they're now defined. Session state defaults are pre-initialized and always available. |
| **Found in** | `app/pages/05_bias_correction.py` — `_render_dsilva_tab()` line ~1488, after moving orbital params expander to right column |

---

### E029 — Rebuilding config objects from session_state instead of passing constructed ones

| | |
|---|---|
| **Bad** | `bin_cfg = BinaryParameterConfig(e_model=st.session_state.get('e_model', 'flat'), ...)` inside a results renderer |
| **Fix** | Pass the already-constructed `bin_cfg` object from the tab UI as a function parameter |
| **Grep** | *(not greppable — requires code review: check if config objects are rebuilt downstream instead of passed)* |
| **Why** | When a config dataclass has many fields (e.g., `BinaryParameterConfig` with `langer_period_params`, `q_flipped`, `e_model`, etc.), rebuilding it from `session_state` in a different function risks using wrong default values or wrong session_state key names. The tab UI already constructs the correct config — pass it through rather than reconstructing. Similar to E024 (missing fields in cache checks) but applies to runtime config construction, not cache validation. |
| **Found in** | `app/pages/05_bias_correction.py` — `_render_cadence_results()` was rebuilding `BinaryParameterConfig` with `e_model='flat'` (wrong for Langer which uses `'zero'`), missing `langer_period_params` entirely |

---

## Adding New Errors

When you encounter a new recurring error, add it here with:
1. An **ID** (E005, E006, ...) and descriptive title
2. The **bad** and **fix** code patterns
3. A **grep regex** if the pattern is machine-detectable
4. **Why** it happens
5. **Where** it was found
6. Update the **Quick-Scan Regex** at the top if a new greppable pattern was added
