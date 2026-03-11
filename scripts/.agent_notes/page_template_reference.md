# Streamlit Page-Building Reference

This is the definitive guide for building high-quality Streamlit pages in this project.
**Read this BEFORE implementing any webapp page.**

---

## 1. Canonical Page Boilerplate

Every page in `app/pages/` MUST start with this exact structure:

```python
"""
app/pages/NN_page_name.py — Page Title
───────────────────────────────────────
Brief description of what this page does.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st

st.set_page_config(page_title='Page Title', page_icon='📊', layout='wide')

from shared import inject_theme, render_sidebar, apply_theme, PLOTLY_THEME
# Import other shared utilities as needed (see Section 3 below)

inject_theme()
settings = render_sidebar('Page Title')
```

**CRITICAL:** Import from `shared`, NEVER from `app.shared`. Streamlit adds `app/` to sys.path.

---

## 2. Auto-Run Pattern (MANDATORY)

Pages MUST show meaningful content immediately on first load. NEVER require a button click to see initial results.

```python
# Pattern: auto-run on first visit, button for subsequent runs
run_btn = st.button('Re-run analysis')
should_run = run_btn or 'my_result_key' not in st.session_state

if should_run:
    with st.spinner('Computing...'):
        result = expensive_function(param1, param2)
    st.session_state['my_result_key'] = result

# Always display from session_state
result = st.session_state.get('my_result_key')
if result is not None:
    # ... display charts, tables, etc.
```

**Self-check:** Ask yourself: "What does the user see when this page first loads?"
If the answer is "nothing" or "a button", you have FAILED.

---

## 3. Available Shared Utilities (`app/shared.py`)

Always check these BEFORE writing custom implementations:

### Theme & Layout
- `inject_theme()` — inject CSS for custom HTML elements (call once at page top)
- `render_sidebar(page_name: str) -> dict` — standard sidebar with settings, returns settings dict
- `apply_theme(fig, **overrides)` — apply PLOTLY_THEME to a Plotly figure
- `PLOTLY_THEME: dict` — the active Plotly theme dict (dark mode aware)
- `metric_card(label, value, ...)` — single metric display card (HTML)

### Data Loading (cached)
- `cached_load_observed_delta_rvs(settings_hash(settings)) -> (ndarray, dict)` — load observed ΔRVs
- `cached_load_cadence(hash) -> (list, ndarray)` — load observation cadence (star names, MJD arrays)
- `cached_load_grid_result(model, path=None) -> dict|None` — load .npz grid results
- `cached_load_nres_rvs() -> dict` — load NRES RV measurements
- `settings_hash(settings: dict) -> str` — deterministic 12-char hash for cache keys

### Analysis
- `find_best_grid_point(ks_p_2d, fbin_vals, x_vals) -> (best_fbin, best_x, best_pval)` — find best-fit in 2D grid
- `make_heatmap_fig(ks_p_2d, fbin_vals, x_vals, ...) -> fig` — create standard heatmap with PLOTLY_THEME
- `get_obs_manager() -> ObservationManager` — singleton ObservationManager
- `get_settings_manager() -> SettingsManager` — settings file manager
- `load_run_history() -> list[dict]` — load run history from JSON
- `preload_all_data(settings)` — warm all caches at session startup

### External modules (import from project root)
- `from wr_bias_simulation import SimulationConfig, BinaryParameterConfig, run_bias_grid, simulate_delta_rv_sample` — simulation engine
- `from pipeline.load_observations import load_observed_delta_rvs, load_cadence_library` — raw data loaders
- `from plot import read_file` — universal spectrum file reader (X-SHOOTER, HERMES, etc.)

---

## 4. PLOTLY_THEME Usage (E018 — CRITICAL)

`PLOTLY_THEME` contains keys: `title`, `xaxis`, `yaxis`, `font`, `legend`, `plot_bgcolor`, `paper_bgcolor`.

**CORRECT — single dict-merge call:**
```python
fig.update_layout(**{**PLOTLY_THEME,
    'title': dict(text='My Title'),
    'xaxis': {**PLOTLY_THEME.get('xaxis', {}), 'title': 'X Label'},
    'yaxis': {**PLOTLY_THEME.get('yaxis', {}), 'title': 'Y Label'},
})
```

**CORRECT — apply_theme helper:**
```python
apply_theme(fig, title=dict(text='My Title'))
```

**WRONG — crashes at runtime with TypeError:**
```python
fig.update_layout(title='My Title', **PLOTLY_THEME)  # CRASH!
fig.update_layout(**PLOTLY_THEME, xaxis=dict(title='X'))  # CRASH!
```

---

## 5. Long Computation Patterns

### For computations 2-5 seconds:
```python
with st.spinner('Computing...'):
    result = my_function()
```

### For computations >5 seconds (use progress bar):
```python
progress = st.progress(0)
for i, item in enumerate(items):
    process(item)
    progress.progress((i + 1) / len(items))
progress.empty()
```

### For computations >30 seconds (use background thread + polling):
```python
import threading

def _run_in_background(params, progress_dict):
    """Runs in a daemon thread. Writes progress to shared dict."""
    for i, step in enumerate(steps):
        result = compute(step)
        progress_dict['progress'] = (i + 1) / len(steps)
        progress_dict['partial_result'] = result
    progress_dict['done'] = True
    progress_dict['final_result'] = result

# Launch
if run_btn:
    progress_dict = {'done': False, 'progress': 0}
    st.session_state['_bg_progress'] = progress_dict
    thread = threading.Thread(target=_run_in_background,
                              args=(params, progress_dict), daemon=True)
    thread.start()

# Poll with st.fragment
@st.fragment(run_every=3)
def poll_progress():
    pd = st.session_state.get('_bg_progress', {})
    if pd.get('done'):
        st.session_state['my_result'] = pd['final_result']
        st.rerun()
    elif pd:
        st.progress(pd.get('progress', 0))
```

See `app/pages/05_bias_correction.py` for the canonical implementation.

---

## 6. Caching Rules

```python
@st.cache_data
def my_cached_function(param1: str, param2: int) -> dict:
    """Cache based on param1 and param2."""
    return expensive_computation(param1, param2)
```

**CRITICAL (E023):** Parameters prefixed with `_` are EXCLUDED from the cache key!
```python
# WRONG — all calls return same cached result regardless of star_name:
@st.cache_data
def load_star(_star_name: str, epoch: int):
    ...

# CORRECT:
@st.cache_data
def load_star(star_name: str, epoch: int):
    ...
```

---

## 7. Top 10 Common Errors to Check

Before submitting ANY page, verify NONE of these are present:

1. **E001** — `np.trapz` → use `np.trapezoid`
2. **E002** — `numpy.bool_` with `is True` → use `bool()` or `if x:`
3. **E003** — Missing `rv[rv != 0]` filter on RV arrays
4. **E012** — `st.page_link` paths relative to entrypoint, not CWD
5. **E017** — `.applymap()` removed in pandas 2.x → use `.map()`
6. **E018** — PLOTLY_THEME kwargs collision (see Section 4 above)
7. **E019** — Data symlink `Data/` is fragile, check after git ops
8. **E023** — `@st.cache_data` underscore params excluded from key
9. Import from `shared`, never `app.shared`
10. Auto-run on first load (never require button click for initial content)

---

## 8. Quality Self-Check Checklist

Before declaring implementation complete, verify ALL of these:

- [ ] Page shows meaningful content immediately on first load (no clicks needed)
- [ ] All Plotly charts use PLOTLY_THEME correctly (E018 pattern)
- [ ] All expensive computations have spinner/progress indicators
- [ ] All data loading uses `cached_load_*` from shared.py (not custom loading)
- [ ] `inject_theme()` and `render_sidebar()` called at page top
- [ ] `@st.cache_data` params don't start with `_` unless intentionally excluded
- [ ] No imports from `app.shared` (use `from shared import ...`)
- [ ] py_compile passes: `conda run -n guyenv python -m py_compile <file>`
- [ ] COMMON_ERRORS.md patterns scanned (E001-E025)
- [ ] Every chart has `st.caption(...)` below it explaining what it shows
- [ ] Tabs work independently (no tab depends on another tab running first)
