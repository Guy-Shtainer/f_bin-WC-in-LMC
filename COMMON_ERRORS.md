# Common Errors & Known Pitfalls

This file documents recurring bugs and deprecated patterns found in this project.
**Claude checks these patterns automatically before and after writing code.**

## Quick-Scan Regex

Combined grep pattern for all known bad patterns (copy-paste ready):

```bash
grep -rn -E 'np\.trapz\b|\.bool_\b.*is (True|False)|\.int_\b|\.float_\b|\.complex_\b|\.object_\b|\.str_\b|CLAUDECODE|allow_dangerously_skip_permissions|\.replace\(second=.*\.second\s*\+|nanargmax|nanargmin|\\big[lr]?\b|\\Big[lr]?\b|ax\.text\(.*wrap=True|fig\.text\(.*wrap=True' --include='*.py' .
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

### E005 — Hebrew/Unicode paths fail in shell commands

| | |
|---|---|
| **Bad** | `cd "/path/with/תואר שני!/..."` or `sys.path.insert(0, '/path/with/תואר שני!/...')` built via string interpolation in subprocess/shell |
| **Fix** | (1) Never `cd` into Hebrew paths — use absolute paths or inherit cwd. (2) In Python subprocesses, pass `cwd=` kwarg to `subprocess.run()` instead of shell `cd`. (3) For `sys.path.insert`, use `Path(__file__).resolve().parent` instead of string literals. (4) When building shell commands as strings, use `shlex.quote()` and test with the actual Hebrew path. |
| **Grep** | *(not greppable — requires manual attention)* |
| **Why** | zsh/bash mishandle multi-byte Hebrew characters (`תואר שני!`) in paths — truncation, encoding corruption, or silent failure. This is especially bad when paths are interpolated into shell command strings (e.g., `f"cd '{path}' && python -c ..."`) where the Hebrew gets truncated mid-character. The overnight agent's verify step hits this: it builds a `sys.path.insert(0, '...')` command string that gets cut off at the Hebrew portion, causing false "IMPORT ERROR" failures even when the code is correct. |
| **Found in** | Bash tool calls, agent v2 verify harness (`scripts/agent_v2/`), `overnight_agent_v1.py` test commands |
| **Impact** | Agent tasks #160 and #161 both failed verification due to this false positive — the code was fine but the test harness couldn't handle the path. |

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
| **Bad** | `fig.update_layout(title=dict(...), **PLOTLY_THEME)` or `dict(title=..., **PLOTLY_THEME)` or `fig.update_layout(**PLOTLY_THEME, **_AA_OVERRIDES)` (dual-spread variant — both dicts have `plot_bgcolor`/`xaxis`/etc.) |
| **Fix** | `fig.update_layout(**{**PLOTLY_THEME, 'title': dict(...)})` (dict literal with override). Dual-spread: `_merged = {**PLOTLY_THEME, **_AA_OVERRIDES}; _merged['title'] = ...; fig.update_layout(**_merged)` — last-wins merge resolves duplicates. |
| **Grep** | *(not reliably greppable — requires manual attention)* |
| **Why** | `PLOTLY_THEME` contains `title`, `legend`, `xaxis`, `yaxis`, `font`, `plot_bgcolor`, `paper_bgcolor` keys. Python raises `TypeError: got multiple values for keyword argument` whenever the same key appears in two `**dict_unpack` operations or in a `**spread` plus an explicit kwarg in the same call (`dict()`, `update_layout()`, etc.). Dict-literal merge syntax `{**base, **override}` resolves duplicates by last-wins. |
| **Colliding keys** | `title`, `legend`, `yaxis`, `xaxis`, `font`, `plot_bgcolor`, `paper_bgcolor` |
| **Found in** | `app/pages/05_bias_correction.py` (10 sites); `scripts/plot_validation_summary.py` (dual-spread variant, 2026-05-20) |

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

### E030 — `dict.get()` returns `None` when key exists with `None` value

| | |
|---|---|
| **Bad** | `_be = g.get('bin_edges', DEFAULT_DRV_BIN_EDGES)` — returns `None` when `g['bin_edges']` is `None` |
| **Fix** | `_be = g.get('bin_edges') or DEFAULT_DRV_BIN_EDGES` |
| **Grep** | `g\.get\(.*,\s*DEFAULT` |
| **Why** | `dict.get(key, default)` only uses the default when the key is **missing**, not when the value is `None`. Use `or` to fall back on `None` values. |
| **Found in** | `wr_bias_simulation.py` — `_single_grid_task_lite` CvM branch |

### E031 — `dict(**unpacked, key=val)` fails when unpacked dict already contains `key`

| | |
|---|---|
| **Bad** | `dict(**result.items(), timestamp=np.array(...))` — crashes if `result` already has `'timestamp'` |
| **Fix** | Filter out conflicting keys: `{**{k: v for k, v in result.items() if k not in ('timestamp',)}, 'timestamp': ...}` |
| **Grep** | `dict\(\s*\*\*` |
| **Why** | Python raises `TypeError: got multiple values for keyword argument`. When unpacking a dict into `dict()`, any explicit keyword that also exists in the unpacked dict causes a collision. |
| **Found in** | `app/pages/05_bias_correction.py` — cadence save result handler |

### E032 — Hardcoded Streamlit widget keys in reusable functions

| | |
|---|---|
| **Bad** | `st.radio(..., key='cvm_fit_mode')` in a function called from multiple tabs |
| **Fix** | Accept a `prefix` parameter and use `key=f'{prefix}_fit_mode'` |
| **Grep** | `key='cvm_` |
| **Why** | Streamlit requires globally unique widget keys. A function called from multiple tabs/columns will create duplicate keys, crashing with `StreamlitDuplicateElementKey`. Always parameterize keys with a tab/context prefix. |
| **Found in** | `app/pages/05_bias_correction.py` — `_render_cvm_analysis()` |

### E033 — Variable defined inside `if n_bin > 0` used in return dict outside the block

| | |
|---|---|
| **Bad** | `omega` assigned inside `if n_bin > 0:` but used in `return {'omega': omega}` outside |
| **Fix** | Initialize `omega = np.array([])` before the `if` block |
| **Grep** | — (not greppable, requires control-flow analysis) |
| **Why** | When `n_bin == 0` (no binaries drawn), the variable is never assigned, causing `UnboundLocalError`. Always initialize variables before conditional blocks that assign them. |
| **Found in** | `wr_bias_simulation.py` — `simulate_with_params()` (`omega`, `T0`) |

### E034 — `np.nanargmax`/`np.nanargmin` on all-NaN array raises ValueError

| | |
|---|---|
| **Bad** | `np.nanargmax(arr)` or `np.nanargmin(arr)` without checking for finite values |
| **Fix** | `if np.any(np.isfinite(arr)): idx = np.nanargmax(arr)` |
| **Grep** | `nanargmax\|nanargmin` (then verify a finite-check guard exists nearby) |
| **Why** | `np.nanargmax` / `np.nanargmin` raise `ValueError: All-NaN slice encountered` when the input has no finite values. This happens when exclusion masks set all grid points to NaN, or when loading partial/empty results. Always guard with `np.any(np.isfinite(arr))` before calling. |
| **Found in** | `app/pages/05_bias_correction.py` — `_render_cadence_results()` (5 locations), `_parabolic_min_1d/2d/3d` |

### E035 — New function missing parameters from original code path (silent wrong results)

| | |
|---|---|
| **Bad** | `SimulationConfig(n_stars=25, sigma_measure=1.6)` — missing `cadence_library`, `cadence_weights`, `n_epochs`, `time_span` |
| **Fix** | Copy ALL parameters from the original code path: `SimulationConfig(n_stars=..., sigma_measure=..., cadence_library=..., cadence_weights=..., n_epochs=..., time_span=...)` |
| **Grep** | `SimulationConfig(` (then verify all fields are passed) |
| **Why** | When creating a new function that re-does a computation from an existing code path, missing parameters silently use defaults. The `resimulate_at_point()` function ran non-cadence simulations for a week because `cadence_library` was missing from its `SimulationConfig` — producing wrong p-values that looked plausible. Always LIST every parameter the original uses and verify each one is passed. |
| **Found in** | `app/pages/05_bias_correction.py` — re-simulation block; `wr_bias_simulation.py` — `resimulate_at_point()` |

### E036 — Parabolic extremum without Hessian positive-definite check

| | |
|---|---|
| **Bad** | Solve ∇S=0 and accept the result without checking if it's a minimum |
| **Fix** | Check `np.all(np.linalg.eigvalsh(Hessian) > 0)` before accepting; fall back to grid min if not positive definite |
| **Grep** | `np.linalg.solve` near `parabolic_min` (then verify Hessian eigenvalue check exists) |
| **Why** | Solving ∇S=0 finds ANY extremum — minimum, maximum, or saddle point. Without checking the Hessian is positive definite (all eigenvalues > 0), the code may return a maximum, making the "best-fit" the worst point on the grid. |
| **Found in** | `app/pages/05_bias_correction.py` — `_parabolic_min_2d()`, `_parabolic_min_3d()` |

### E037 — Python `or` on numpy arrays raises ValueError

| | |
|---|---|
| **Bad** | `result = arr_or_none or default_array` (where `arr_or_none` might be a numpy array) |
| **Fix** | `result = arr_or_none if arr_or_none is not None else default_array` |
| **Grep** | `.get(` followed by `or ` followed by another `.get(` or array name (manual check) |
| **Why** | Python's `or` evaluates truthiness of the left operand. For numpy arrays with >1 element, `bool(array)` raises `ValueError: The truth value of an array with more than one element is ambiguous`. This happens when `dict.get()` returns a numpy array (truthy) and you chain with `or`. Use explicit `is None` checks instead. |
| **Found in** | `wr_bias_simulation.py` — likelihood bin edges fallback chain |

### E038 — `st.session_state[widget_key] = value` after widget is instantiated

| | |
|---|---|
| **Bad** | `st.slider(..., key="my_key")` then later `st.session_state["my_key"] = new_val` |
| **Fix** | Store in an internal key (`_bestfit_my_key`) **before** the widget renders, then use `st.slider(..., value=st.session_state.get("_bestfit_my_key", default), key="my_key")` |
| **Grep** | *(not reliably greppable — requires flow analysis)* |
| **Why** | Streamlit raises `StreamlitAPIException: st.session_state.X cannot be modified after the widget with key X is instantiated`. Once a widget with a given key has rendered in a script run, its session_state entry is locked. To update defaults after computation, use a separate internal key and read it as the widget's `value` parameter. |
| **Found in** | `app/pages/12_rv_modeling.py` — playground sliders updated after fitting |

---

### E039 — Squeezing ND arrays with `arr[0]` removes wrong axis

| | |
|---|---|
| **Bad** | `while arr.ndim > target: arr = arr[0]` — always removes axis 0 regardless of which axis has size 1 |
| **Fix** | Find the first size-1 axis and `np.squeeze(arr, axis=ax)` it. Only fall back to `arr[0]` if no size-1 axis exists. Use `_squeeze_to_match(arr, target_ndim)` from `bc.corner_plots`. |
| **Why** | When logP_max (axis 0) and sigma (axis 1) are grid axes, but sigma has only 1 value, `arr[0]` removes the logP_max axis instead of the trivial sigma axis. This causes grid/array dimension mismatches downstream (e.g., `compute_hdi68` gets arrays of incompatible shapes). |
| **Found in** | `app/bc/corner_plots.py` — recurring bug with 4D arrays where only some outer axes are scanned |

---

### E040 — Grid/array dimension mismatch in `_method_best_and_hdi`

| | |
|---|---|
| **Bad** | Building `grids = [fbin_g, x_g]` (2 grids) for a 3D or 4D scoring array, then passing to `_method_best_and_hdi` which zips grids with `p_nd.shape` — axis indices don't match |
| **Fix** | (1) Build grids dynamically based on which axes were actually scanned (`sigma_grid.size > 1`, `logPmax_grid.size > 1`). (2) Add a guard: `if len(grids) != p_nd.ndim: return None`. (3) Per-axis check: `if len(g) != p_nd.shape[i]: skip`. |
| **Grep** | `_method_best_and_hdi` |
| **Why** | Cadence Langer with logPmax scanning produces 4D arrays `[logPmax, sigma, fbin, pi=1]` but the `cadence_langer` branch only built 2D grids `[fbin, sigma]`. The `while p_arr.ndim > len(grids): p_arr = p_arr[0]` hack silently sliced away the wrong leading dims, causing `compute_hdi68` to receive incompatible shapes (e.g., grid of 8 values vs marginalized array of 0 values). |
| **Found in** | `app/bc/analysis.py` — `_render_method_summary_section` cadence_langer branch + `_method_best_and_hdi` |

---

### E041 — Heatmap colorbar label must match scoring method

| | |
|---|---|
| **Bad** | `scoring_label='Likelihood'` → colorbar renders "Likelihood p-value" (via shared.py appending " p-value") |
| **Fix** | Pass `colorbar_title_override='Likelihood'` for likelihood method, `'CvM S-score'` for CvM. Only K-S methods should say "p-value". |
| **Grep** | `scoring_label=` in `_make_heatmap_fig` calls |
| **Why** | `shared.py:make_heatmap_fig` appends " p-value" to ALL non-D scoring labels. Likelihood is not a p-value. User flagged this >10 times. |
| **Found in** | `app/bc/analysis.py` — `_render_method_expander` heatmap call |

---

### E042 — Function call passes extra positional argument after refactor

| | |
|---|---|
| **Bad** | `_render_lk_corner_plot(p_nd, fbin_g, x_g, x_name, x_display_label, _DISPLAY_NAME, ndim_mode, result, prefix, pal, use_cw)` — 11 args for a function that takes 10 |
| **Fix** | Remove the extra arg (`_DISPLAY_NAME` was left over from when KS/Likelihood shared a common call pattern with a `display_name` param). Always verify arg count matches function signature after splitting/refactoring. |
| **Grep** | N/A (not machine-detectable — caught at runtime as `TypeError: ... takes from N to M positional arguments but M+1 were given`) |
| **Why** | When duplicating a function call for a new render file (e.g., splitting KS and Likelihood into separate files), extra arguments from the original generic call may be left in. The code compiles fine (`py_compile` passes) because the error is only raised at call time. |
| **Found in** | `app/bc/render_lk.py` — call to `_render_lk_corner_plot()` had `_DISPLAY_NAME` as an extra arg |
| **Prevention** | After any refactor that changes function signatures: (1) grep all callers, (2) count positional args vs function def, (3) test the actual code path (not just import). |

### E043 — `np.argmax` on array with NaN returns index 0

| | |
|---|---|
| **Bad** | `np.argmax(arr)` when `arr` may contain NaN |
| **Fix** | `np.nanargmax(arr)` (+ guard `np.any(np.isfinite(arr))` for all-NaN case) |
| **Grep** | `np\.argmax\b` (check context — only bad if array may have NaN) |
| **Why** | `np.argmax` treats NaN as greater than any finite value in C-level comparisons, returning the first NaN element (index 0). `np.nanargmax` skips NaN but raises `ValueError` on all-NaN. |
| **Found in** | `app/shared.py` — `find_best_grid_point` placed gold star at (0,0) after grid exclusion NaN'd the array |

### E044 — `dict.get(key, default)` returns None when key exists with value None

| | |
|---|---|
| **Bad** | `float(result.get('sigma_meas', 3.0))` when `result['sigma_meas'] = None` |
| **Fix** | `float(result.get('sigma_meas') or 3.0)` — the `or` catches both missing key AND None value |
| **Grep** | N/A (not machine-detectable — depends on runtime dict contents) |
| **Why** | `dict.get(key, default)` only uses `default` when the key is ABSENT. If the key exists with value `None`, `get()` returns `None`. `float(None)` → `TypeError`. |
| **Found in** | `app/bc/render_shared.py` — CDF model trace silently crashed inside `try/except: pass` because `sigma_meas` was `None` in result dict |

### E045 — `st.slider` with float bounds quantises value to implicit step `(max-min)/100`

| | |
|---|---|
| **Bad** | `col.slider(label, min_val, max_val, key=k)` with float min/max and no explicit `step` — Streamlit defaults to `step = (max-min)/100`, so any value written to `st.session_state[k]` gets rounded to the nearest tick on render and overwrites the session_state with the rounded value |
| **Fix** | Either: (a) pass `step=<small_value>` explicitly to `st.slider(...)` matching the grid spacing, OR (b) when precision matters (e.g. seed-reuse simulation), keep an off-widget reference to the exact float and use that for downstream computation, treating the slider as display-only |
| **Grep** | `st\.slider\(` (then verify `step=` appears in the call OR a downstream override exists) |
| **Why** | For float types `st.slider(label, mn, mx, key=k)` without `step` defaults `step = (max - min) / 100`. The widget reads `st.session_state[k]` as its initial value, snaps to the nearest tick, and writes back. So even if you set `session_state[k] = 0.151428` as the default, the function returns `0.15`. The number_input widget below has independent `step` and may NOT round, so `slider` and `number_input` can disagree on the same logical control. Especially dangerous when the slider value is fed into a deterministic-seeded simulation: tiny float differences amplify into noticeable score divergence. |
| **Found in** | `app/bc/render_lk_explorer.py` — Reset-to-best button set sliders to joint-argmax grid coordinates, but slider quantised them, so Explorer's recomputed logL diverged from stored Global best by ~0.04 even at the "same" cell. Workaround: detect first render after Reset via `_last_rc` tracker, then override `me_*` with exact `_bf_*` floats post-widget-render, before passing to the simulation |

---

## Adding New Errors

When you encounter a new recurring error, add it here with:
1. An **ID** (E005, E006, ...) and descriptive title
2. The **bad** and **fix** code patterns
3. A **grep regex** if the pattern is machine-detectable
4. **Why** it happens
5. **Where** it was found
6. Update the **Quick-Scan Regex** at the top if a new greppable pattern was added

### E043 — `result['settings']` is a JSON string, not a dict

| | |
|---|---|
| **Bad** | `result.get('settings', {}).get('sigma_factor', 4.0)` |
| **Fix** | `json.loads(str(result.get('settings', '{}'))).get('sigma_factor', 4.0)` |
| **Grep** | `result\.get\('settings'.*\.get\(` |
| **Why** | `runners_cadence.py` stores settings via `json.dumps()`. When loaded from `.npz`, it becomes a numpy string array. Calling `.get()` on it raises `AttributeError: 'numpy.ndarray' object has no attribute 'get'`. |
| **Found in** | `app/bc/render_lk_explorer.py`, `app/bc/render_lk_explorer_langer.py` (2026-03-31) |

---

### E044 — `'COL' in fit.data` fails on astropy `FITS_rec`

| | |
|---|---|
| **Bad** | `'ERR' in fit.data` |
| **Fix** | `'ERR' in fit.data.dtype.names` |
| **Grep** | `in fit\.data\b` or `in .*\.data\b` (manual check needed) |
| **Why** | Astropy `FITS_rec` (structured array) doesn't support `str in FITS_rec` — raises `TypeError: Cannot compare structured or void to non-void arrays`. The `in` operator tries element-wise comparison, not column-name lookup. Use `.dtype.names` to check column existence. |
| **Found in** | `app/plots/data.py` (2026-04-06) |

### E045 — `st.slider` with `min_value == max_value` on single-value grid

| | |
|---|---|
| **Bad** | `st.slider('range', min_value=lo, max_value=hi, ...)` when `lo == hi` |
| **Fix** | Guard: `if lo >= hi: return lo, hi` — show static text instead of slider |
| **Grep** | `\.slider\(` (manual check: ensure grid can't be single-value) |
| **Why** | Streamlit requires `min_value < max_value`. When a grid axis has one value (e.g., fixed σ_single=7.5 in Langer model), `lo == hi` and the slider raises `StreamlitAPIException`. |
| **Found in** | `app/bc/helpers.py:_make_range_slider` (2026-04-19) |

### E046 — `st.button` inside conditional block: click dropped on rerun

| | |
|---|---|
| **Bad** | Button rendered only when a one-shot session_state flag is set, then popped on first rerun. After click the condition is False → button isn't re-instantiated at its key → Streamlit drops the click → handler never fires. |
| **Fix** | Before `st.stop()` in the "wait for click" branch, **re-arm** the session_state flag(s) that gated the outer `if`. Next rerun re-enters the block, re-renders the button at the same key, and the click is captured. In the click-handler branches, clear the re-armed flags to avoid an infinite loop. |
| **Grep** | *(not greppable — structural pattern)* |
| **Why** | Streamlit's button click is only consumed on the *next* rerun, and only if the widget is re-instantiated at the same key. If the outer `if` goes False because a flag was popped on the previous rerun, the button is gone and the click is silently discarded. Classic symptom: "nothing happens when I click the button." |
| **Found in** | `app/bc/cadence.py` — resume-flow sim-context mismatch guard (2026-04-19). The `_auto_resume` / `_resume_from` flags are popped at the top of `_cadence_run_and_results`, so the mismatch buttons ("Start fresh" / "Cancel") were unreachable until the block re-armed both before `st.stop()`. |
| **Prevention** | When rendering a button inside a one-shot-triggered block: either (1) re-arm the flags before `st.stop()` so the next rerun repaints the buttons, or (2) store button state explicitly in session_state from an `on_click` callback. |

### E047 — Plotly `fill='toself'` band + `shape='hv'` step line mismatch

| | |
|---|---|
| **Bad** | Percentile band drawn as a closed `fill='toself'` polygon (linear-interp edges) while the median/central line overlaid with `line=dict(..., shape='hv')`. Between two X points, the step line stays flat at y_{i-1} while the band's polygon edge slopes diagonally to (x_i, y_i). Median visually escapes the band even though `lo[i] ≤ med[i] ≤ hi[i]` is mathematically guaranteed. |
| **Fix** | Replace single polygon with **two `shape='hv'` traces** + `fill='tonexty'`:<br>```python<br>go.Scatter(x=X, y=lo, mode='lines',<br>    line=dict(color='rgba(0,0,0,0)', shape='hv'), showlegend=False, hoverinfo='skip')<br>go.Scatter(x=X, y=hi, mode='lines',<br>    line=dict(color='rgba(0,0,0,0)', shape='hv'),<br>    fill='tonexty', fillcolor=..., showlegend=False, hoverinfo='skip')<br>```<br>The lo-trace MUST be added IMMEDIATELY before the hi-trace (`tonexty` targets the previous trace). |
| **Grep** | `fill=.toself` combined with nearby `shape=.hv` (manual inspection — false positives for 2D confidence regions where no step line is overlaid) |
| **Why** | Plotly `shape='hv'` on `fill='toself'` with a forward-then-reverse closed path has undefined behavior (the backward leg's step direction is ambiguous). The two-trace `fill='tonexty'` pattern is the standard Plotly idiom for stepped uncertainty bands. |
| **Found in** | Bias correction page CDF plots (2026-04-19): `app/bc/render_shared.py:_render_all_methods_cdf`, `app/bc/render_shared_langer.py:_render_all_methods_cdf`, `app/bc/render_lk_explorer.py:_render_lk_resim_interp`, `app/bc/render_lk_explorer_langer.py:_render_lk_resim_interp`. Also present in the dead copies at `app/bc/analysis.py:460-465, 1101-1108`. |
| **Prevention** | Whenever a central line uses `shape='hv'` (empirical CDFs, step histograms), the surrounding uncertainty band must use the same step shape. Check by zooming: if median visibly dips outside band near bin-edge transitions, you have this bug. |

### E050 — `@st.cache_data` invoked from a background `threading.Thread`

| | |
|---|---|
| **Symptom** | Background worker thread freezes silently after completing heavy work. Progress UI advances to the last step (e.g. "cell N/N"), then CPU drops to zero and the run never finishes. No traceback, no error. |
| **Bad** | A `threading.Thread` runner calls a function decorated with `@st.cache_data` (or `@st.cache_resource`). Streamlit's cache assumes a `ScriptRunContext` on the calling thread. Without one, the cache-store step at the END of the call can deadlock on internal locks shared with the main ScriptRunner thread (especially when a `@st.fragment(run_every=1)` poller is touching cached state on the main thread). |
| **Fix** | Bypass the cache on the bg-thread path — call the uncached inner function directly. Keep the cached wrapper only for main-thread callers. Add a NOTE comment above the cached wrapper: `# NOT safe to call from a background thread — no ScriptRunContext → deadlocks on cache locks.` |
| **Grep** | Any `@st.cache_data`-decorated function called inside a `threading.Thread` target or any `_bg` / `_worker` function body. Pattern: `grep -nE '^(def |    ).*_bg\(\|_worker\(' app/` then check what cached helpers those call. |
| **Why** | `st.cache_data` internally uses `threading.RLock` to serialize writes, and the key computation pulls from `ScriptRunContext`. A non-ScriptRunner thread has no context, so `st.runtime.scriptrunner.get_script_run_ctx()` returns `None`; the cache falls back to a shared global, but its write path still takes locks that the main thread may hold while polling state. The signature is distinctive: the progress callback (which writes directly to a shared dict, bypassing the cache) reports 100% completion, then everything stalls. |
| **Found in** | `app/bc/bin_sensitivity_scorer.py:_run_all_schemes_bg` called `rescore_scheme_cached` (decorated) per-scheme; third scheme hung at "9900/9900" with zero CPU. Fixed 2026-04-23 by calling `rescore_scheme` directly from the bg runner. |
| **Prevention** | Any function invoked from a `threading.Thread` must be cache-free. If you want result caching across runs, persist to disk via your own IO layer (e.g. `np.savez` in a sidecar folder) — do NOT reach for `@st.cache_data`. |

### E049 — Plotly subplot inconsistency from scoped axis updates

| | |
|---|---|
| **Symptom** | In a `make_subplots` figure, some subplots have frames, ticks, or gridlines that differ from others — random-looking inconsistency across panels of the same canvas. |
| **Root cause** | `fig.update_xaxes(range=..., row=N)` without `col=` applies to the ENTIRE row only. Other rows fall back to auto-range / inherited defaults. Same for `col=M` without `row=`. |
| **Fix** | Either pass both `row` and `col` (targets one subplot), or pass neither (targets all subplots — this is almost always what you want for styling). Use the `_apply_aa_axes(fig)` helper in `app/bc/bin_sensitivity_plots.py` as the canonical pattern: unscoped `fig.update_xaxes(...)` + `fig.update_yaxes(...)` after all traces are added. |
| **Where it bit us** | `_plot_cdf_faceted` in `app/bc/bin_sensitivity_plots.py` was calling `fig.update_yaxes(range=[0, 1.05], col=1)` — only left column got the range lock, right column auto-ranged, giving the "some panels have horizontal gridlines, some don't" appearance. Fixed 2026-04-23 Session 5. |
| **Grep** | Any `update_xaxes`/`update_yaxes` call with only `row=` or only `col=` (single-dimension scoping) in a subplot module. |
| **Prevention** | Any `update_xaxes`/`update_yaxes` call in a subplot module must explicitly state whether it targets one subplot (both `row` AND `col`) or all (neither). Single-dimension scoping is a bug in almost all cases. |

### E048 — Re-sim helper builds fresh `BinaryParameterConfig` — silent physics-config drift between grid scoring and CDF/score display

| | |
|---|---|
| **Bad** | A cached re-sim helper that takes `fb, pi, sigma, logPmax, …` and internally does `bin_cfg = BinaryParameterConfig(logP_max=logPmax)`. Every other field (`logP_min`, `e_model`, `q_model`, `mass_primary_model`, `period_model`, …) silently reverts to module defaults, so the recomputed CDF/logL lives on a different physical surface than the one the grid worker scored. Symptoms: top-of-page CDF flatlines at 0.5 from ~27 → ~320 km/s; Model-Explorer "Global best logL" disagrees with the heatmap's `logL_raw[best_idx]`; user can manually find a higher-scoring point in the explorer that isn't actually higher on the real grid surface. |
| **Fix** | (1) Accept the full bin_cfg as a parameter (as a hashable dict/tuple) + an explicit `period_model` string. Rebuild `BinaryParameterConfig(**bin_cfg_dict)` inside the helper, then override only `logP_max` (slider) and `period_model` (explicit arg). (2) Persist `bin_cfg` (as `vars(bin_cfg)` dict), `period_model`, and `cadence_weights` into the grid runner's `result` dict so downstream callers have everything they need. (3) All call sites pull from `result.get('bin_cfg'/'period_model'/'cadence_weights')` and pass through. (4) Keep a legacy fallback (`_bin_cfg_dict is None` → `BinaryParameterConfig()`) so old .npz files still load, with an `st.info()` notice. |
| **Grep** | `BinaryParameterConfig\(logP_max=` (legitimate only inside `_me_cdf_band`/`_me_cdf_band_langer` as the legacy fallback). Any OTHER hit in a helper that also computes a CDF or logL is suspect. |
| **Why** | `BinaryParameterConfig` is a dataclass with ~10 knobs — logP bounds, eccentricity model/max, primary-mass model/range, q model/range, Langer mixture params, `period_model`. Building a fresh one with just `logP_max=…` silently reverts the other 9 knobs to module defaults, which almost never match the user's run. The bug is especially nasty because it's cadence-silent (cadence_library was already threaded) and only shows up as a "the algorithm is wrong" complaint from the user — they see the explorer's re-sim disagree with the heatmap without any error message. |
| **Found in** | `app/bc/render_lk_explorer.py:_me_cdf_band` (line 48) + 3 call sites; `app/bc/render_lk_explorer_langer.py:_me_cdf_band_langer` (line 48) + 4 call sites; `app/bc/render_shared.py:_render_all_methods_cdf` (line 284); `app/bc/render_shared_langer.py:_render_all_methods_cdf` (line 296); `app/bc/runners_cadence.py:480-496` (result dict — persist bin_cfg/period_model/cadence_weights). Fixed 2026-04-19. **Recurrence 2026-05-10**: same pattern at `app/bc/render_validation.py:351-357` — UI mock generator built fresh `BinaryParameterConfig(logP_min, logP_max, period_model, e_model, e_max)` (only 5 fields), leaving `q_range` at default `(0.1, 2.0)` while the grid worker used `(0.1, 4.0)` from the orbital-params widget. Caused 0.05–0.09 systematic CDF offset between mock and Explorer dashed line; algorithm best-fit drifted from truth by 3.4 logL. Fix: build base bin_cfg from `settings['grid_cadence_*']['orbital']` (same source `cadence.py` reads), then `dataclasses.replace(...)` for truth-specific fields. |
| **Prevention** | When adding a new re-sim helper (CDF, logL, detection fraction, …), the input contract is: take either the full `bin_cfg` object OR its `vars(...)` dict. Never accept a subset like "(fb, pi, sigma, logPmax)" and synthesize a fresh `BinaryParameterConfig` from it. If the helper is `@st.cache_data`, pass the dict as a hashable tuple and prefix with `_` to skip the cache key (the underlying parameters already differentiate the call). Store every physics-affecting knob in the runner's result dict so downstream code never has to guess. See rule "Result-dict completeness contract" in `.claude/references/learnings.md`. |

### E051 — Runner-mode tag passed as `period_model` value

| | |
|---|---|
| **Bad** | `_pm = 'dsilva' if ndim_mode == 'cadence_dsilva' else 'langer'` then `period_model=_pm` passed to `_sample_delta_rv_mock` / `BinaryParameterConfig`. Inside the sampler, `sample_logP` raises `ValueError(f"Unknown period_model: {cfg.period_model}")` because it accepts only `'powerlaw'` and `'langer2020'`. |
| **Fix** | Translate at the boundary: `_pm = 'powerlaw' if ndim_mode == 'cadence_dsilva' else 'langer2020'`. The pattern in `render_validation.py:57` is correct: `period_model = 'powerlaw' if is_dsilva else 'langer2020'`. |
| **Grep** | `period_model\s*=\s*['\"]dsilva['\"]\|period_model\s*=\s*['\"]langer['\"]` |
| **Why** | The codebase has TWO namespaces with similar-looking strings: (a) runner-mode tags (`'dsilva'`, `'langer'`, `'cadence_dsilva'`, `'cadence_langer'`) used as `result['type']` and `ndim_mode`; (b) period-distribution model names (`'powerlaw'`, `'langer2020'`) used in `BinaryParameterConfig.period_model` and consumed by `sample_logP`. The two namespaces overlap in surface form but not in accepted values. Type checking can't catch this — both are `str`. The bug only surfaces when the sampler is reached with the wrong tag. |
| **Found in** | `app/bc/render_lk_explorer.py:1357`, `app/bc/render_lk.py:549`, `app/bc/render_lk_explorer_langer.py:1062` — all three callers of `_render_lk_cdf_sanity_check` after Sprint 4's switch from `simulate_delta_rv_sample` (which accepted both forms via different dispatch) to the canonical `_sample_delta_rv_mock`. Fixed 2026-04-28. |
| **Prevention** | When threading a string through a chain of helpers, write down which namespace each function expects in its docstring. If a function accepts `period_model` as a parameter, its docstring should say "must be one of `'powerlaw'`, `'langer2020'`". Translate at the data-source boundary (where the runner-mode tag is decided), not at every consumer. The `_result_period_model(result, default='powerlaw')` helper in `render_lk_explorer.py:205` is the correct centralised translator — extend it to handle the runner-mode tag form too, so callers don't have to translate manually. |

### E052 — `\bigl` / `\bigr` (and other `\big` family) crash matplotlib mathtext

| | |
|---|---|
| **Bad** | `r"$x = \bigl[\,u\,(b^{\pi+1}-a^{\pi+1}) + a^{\pi+1}\,\bigr]^{1/(\pi+1)}$"` — raises `ParseFatalException: Unknown symbol: \bigl, found '\'` on `pdf.savefig` / draw |
| **Fix** | Use plain `[`, `]` (mathtext auto-sizes nothing, but the rendered text still reads cleanly). For genuine bracket scaling use `\left[ \ldots \right]` which mathtext does support. |
| **Grep** | `\\\\big[lr]?\b\|\\\\Big[lr]?\b\|\\\\bigg[lr]?\b\|\\\\Bigg[lr]?\b` |
| **Why** | matplotlib's mathtext parser implements a subset of LaTeX. The `\big`/`\Big`/`\bigg`/`\Bigg` and `\bigl`/`\bigr`/etc. delimiter-sizing macros are NOT in that subset. They fail with a `ParseFatalException` at draw time, not at parse time, so the error only surfaces when the figure is actually rendered (e.g. inside a `PdfPages` writeout). The `pdftoppm`-style preview happens to work too late to help. Fallback options that DO work: bare `[`, `]`, `\left[ … \right]`, or pre-rendered TeX via `text.usetex=True` (heavyweight). |
| **Found in** | `scripts/make_powerlaw_explainer.py:152` (initial draft, fixed 2026-05-07). Crash was: `ValueError: \nx \;=\; \bigl[\,u\,(b^{\pi+1}-a^{\pi+1}) + a^{\pi+1}\,\bigr]^{1/(\pi+1)}\n        ^\nParseFatalException: Unknown symbol: \bigl`. |
| **Prevention** | When writing matplotlib `$...$` mathtext, treat the LaTeX subset as: greek, sub/super, fractions, roots, `\sum`/`\int`/`\prod`, accents, `\mathrm`/`\mathbf`/`\mathtt`/`\mathcal`, `\cdot`, `\propto`, `\sim`, `\to`, `\Longrightarrow`, `\bullet`, spacing (`\,`, `\;`, `\quad`). Anything more exotic (`\bigl`, `\boldsymbol`, `\substack`, `\overset`, `\xrightarrow`, …) is likely unsupported. Test by rendering one figure to PDF + `pdftoppm` BEFORE building all six pages. |

---

### E053 — `ax.text(..., wrap=True)` corrupts `$math$` segments

| | |
|---|---|
| **Bad** | `ax.text(0.0, 0.85, "Right: $\\pi=-1$ — $p(\\log P)\\propto 1/\\log P$, so the histogram …", ha="left", va="top", fontsize=11, wrap=True)` — renders the math segments as literal `$\pi=-1$` / `$p(\log P)\propto 1/\log P$` characters in the PDF |
| **Fix** | Pre-wrap the string at safe word boundaries (treating each `$...$` as one atomic unit), join with `\n`, and pass to `ax.text` with `linespacing=1.5` instead of `wrap=True`. Helper that splits while preserving math: `_wrap_preserving_math(s, width)` in `scripts/make_powerlaw_explainer.py`. |
| **Grep** | `ax\.text\(.*wrap=True\|fig\.text\(.*wrap=True` |
| **Why** | matplotlib's `wrap=True` post-processes the text by re-flowing on whitespace at draw time. It does NOT understand `$...$` as atomic — if a `$math$` span happens to span a wrap point, the wrapper inserts a newline mid-formula and mathtext silently fails on each fragment, falling back to literal `$…$` rendering. The bug is layout-dependent: short text with one inline `$x$` works fine, longer captions with multiple math segments break unpredictably. Visual inspection is the only way to catch it. |
| **Found in** | `scripts/make_powerlaw_explainer.py` page-6 caption (initial draft, fixed 2026-05-07). All math in the caption rendered as literal `$\pi=-1$ — $p(\log P)\propto 1/\log P$, …`. |
| **Prevention** | Avoid `wrap=True` for any caption that mixes prose with math. Pre-wrap into lines yourself, or use `fig.text()` inside a known-width axes and let the line-by-line layout do the wrapping. When in doubt, always rasterise the PDF with `pdftoppm` and visually inspect each page before declaring success — multipage PDFs with captions are the highest-risk case. |

---

### E054 — Validation lane persists metadata to disk but not to the in-memory `result` dict

| | |
|---|---|
| **Bad** | Inside the validation/mock-backend branch of a background runner: `result['is_validation'] = True; _vio.save_validation_result(result, _validation_mock, _validation_truth, …)` — the disk save absorbs the four `true_*` truth fields via `_validation_truth`, but the in-memory `result` returned to the UI keeps only `is_validation` and is missing `true_fbin / true_pi / true_sigma / true_logPmax`. |
| **Fix** | After flagging `result['is_validation'] = True`, also attach the truth fields locally: `for k in ('true_fbin','true_pi','true_sigma','true_logPmax'): result[k] = float(_validation_truth.get(k, np.nan))`. Now the in-memory dict the UI consumes has the same shape the disk save persists. |
| **Grep** | *(not greppable cleanly — context-dependent; look for `save_validation_result(` callers that pass `_validation_truth` separately but never write the `true_*` keys onto `result`)* |
| **Why** | The disk save handler accepts truth as a separate argument and merges it into the persisted blob via `validation_io.save_validation_result`. The in-memory dict goes back to the UI untouched. Fresh validation runs therefore differ from disk reloads: corner_plots._truth_for() reads `result['true_fbin']` etc. directly, returns None on fresh runs (key missing), and the green dashed truth lines vanish — but they reappear after the user reloads the same .npz because the disk path filled the keys. The disk vs memory shape divergence is invisible until a consumer specifically asks for the missing field. |
| **Found in** | `app/bc/runners_cadence.py` `_run_cadence_bg` mock-backend branch (~L672), fixed 2026-05-18. Symptom: corner-plot green truth line missing on fresh validation runs but present after disk reload. |
| **Prevention** | When a background-runner branch persists state to disk via a sibling helper that accepts metadata as a separate argument, mirror those metadata writes onto the in-memory `result` dict before `job['result'] = result; job['status'] = 'done'`. Disk and memory should have the SAME shape — every consumer downstream sees only the in-memory dict; only the on-disk format is for reload. Cross-check by listing all consumers that read `result[KEY]` and confirming every KEY they read is set by the in-memory branch, not just the disk-save branch. |

