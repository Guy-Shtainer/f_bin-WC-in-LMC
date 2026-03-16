---
description: "Comprehensive 5-phase code verification: static analysis, cache cleanup, functional testing, webapp smoke test, and auto-learning new error patterns"
argument-hint: "[file1.py file2.py ...] or empty for auto-detect from git diff"
---

# Error Check — Comprehensive Code Verification

Run all 5 phases in order. Report a summary table at the end.

## Input: Which Files to Check

If `$ARGUMENTS` is provided, treat each space-separated token as a file path → `TARGET_FILES`.

If `$ARGUMENTS` is empty, auto-detect modified `.py` files:

```bash
{ git diff --name-only HEAD -- '*.py'; git diff --name-only --cached HEAD -- '*.py'; } | sort -u
```

If no `.py` files are modified, report "No modified Python files found" and stop.

---

## Phase 1: Static Pattern Scan

Catch known bad patterns before they reach runtime.

1. Read `COMMON_ERRORS.md` and extract the **Quick-Scan Regex** (the combined `grep -rn -E` command near the top).

2. Run it against each file in `TARGET_FILES`:
   ```bash
   grep -n -E '<quick_scan_pattern>' <file>
   ```

3. For each match, identify the error ID by comparing the matched sub-pattern against individual entries in COMMON_ERRORS.md. Report:
   ```
   FAIL [E0XX] file.py:LINE — <matched text> — Fix: <fix from COMMON_ERRORS.md>
   ```

4. Also perform these **non-greppable checks** by reading each file:
   - **E003**: If the file calls `load_property('RVs'` or `load_property('full_RV'`, verify a `!= 0` filter exists nearby.
   - **E018**: If the file uses `**PLOTLY_THEME` or `**_ACADEMIC_THEME`, verify it is NOT inside a function call with `title=`, `legend=`, `xaxis=`, or `yaxis=` as explicit kwargs in the same call.
   - **E024**: If the file adds a new field to a dataclass, check that all cache/hash/reuse functions also include that field.
   - **E025**: If the file removes a widget variable definition, verify no downstream references remain.

5. Report total: `Phase 1: PASS — 0 matches` or `Phase 1: FAIL — N matches found`.

---

## Phase 2: Cache Cleanup

Prevent stale `.pyc` from masking import errors.

For each file in `TARGET_FILES`:

```bash
module=$(basename "<file>" .py)
dir=$(dirname "<file>")
rm -f "${dir}/__pycache__/${module}.cpython-"*.pyc 2>/dev/null
```

Also clean root `__pycache__` if the file is in the project root:
```bash
rm -f "__pycache__/${module}.cpython-"*.pyc 2>/dev/null
```

Report: `Phase 2: Cleaned N .pyc files` or `Phase 2: No stale caches found`.

---

## Phase 3: Functional Testing

This is the most important phase — verify code actually runs, not just compiles.

### 3a: py_compile (baseline)

```bash
conda run -n guyenv python -m py_compile <file>
```

If this fails → `FAIL` for this file. Do NOT proceed to 3b/3c for it.

### 3b: Import test

**Root modules** (`utils.py`, `CCF.py`, `specs.py`, `wr_bias_simulation.py`, etc.):
```bash
conda run -n guyenv python -c "import <module_name>; print('OK')"
```

**app/pages/*.py files** (need sys.path setup):
```bash
conda run -n guyenv python -c "
import sys; sys.path.insert(0, 'app')
import importlib; importlib.import_module('pages.<module_name>')
print('OK')
"
```
If the error contains `streamlit` or `StreamlitAPIException` → mark as `WARN` (expected outside Streamlit runtime), not `FAIL`.

**pipeline/*.py files**:
```bash
conda run -n guyenv python -c "
import sys, os
sys.path.insert(0, os.path.abspath('.'))
import importlib; importlib.import_module('pipeline.<module_name>')
print('OK')
"
```

### 3c: Function-level smoke tests (the key improvement)

For each file in `TARGET_FILES`:

1. Read the file and identify **functions and methods** that were modified. Use `git diff <file>` to see which functions changed.

2. For each modified function, read its signature (params, type hints, defaults) and generate a short test.

3. Use these **domain-specific test data heuristics** to create realistic inputs:

   | Parameter pattern | Test data |
   |---|---|
   | `wave`, `wavelength`, `lambda` | `np.linspace(400, 700, 100)` (nm) |
   | `flux`, `spectrum` | `np.random.normal(1.0, 0.1, 100)` |
   | `rv`, `velocity` | `np.array([15.2, -23.4, 8.7])` (km/s) |
   | `mjd`, `time` | `np.array([59000.0, 59001.5, 59010.3])` |
   | `star_name` | `'BAT99 49'` |
   | `epoch` | `1` |
   | `band` | `'COMBINED'` |
   | `sigma` | `3.0` |
   | `f_bin`, `fbin` | `0.5` |
   | `n_stars`, `N` | `100` |
   | `data` (generic array) | `np.array([1.0, 2.0, 3.0, 100.0, 4.0])` |
   | `rng` | `np.random.default_rng(42)` |

4. Run the test:
   ```bash
   conda run -n guyenv python -c "
   import numpy as np
   from <module> import <function>
   result = <function>(<test_args>)
   assert result is not None, 'returned None unexpectedly'
   print(f'OK: {type(result).__name__}')
   "
   ```

5. Also test **edge cases** where appropriate:
   - Empty arrays: `np.array([])`
   - Single element: `np.array([1.0])`
   - Arrays with NaN: `np.array([1.0, np.nan, 3.0])`

**What to skip (do NOT test):**
- Functions that require file I/O (FITS loading, `Data/` directory access)
- Streamlit page-level functions (need the runtime)
- Class methods where the class needs complex initialization (ObservationManager, Star)
- Functions that write to disk or modify state
- Private helper functions called only internally (test the public API instead)

**What to prioritize:**
- Pure computation functions (math, statistics, array manipulation)
- Simulation functions in `wr_bias_simulation.py`
- Utility functions in `utils.py` (`robust_mean`, `robust_std`, etc.)
- Any function with a clear input→output contract

Report: `PASS`, `FAIL (error message)`, or `SKIP (reason)` for each function.

---

## Phase 4: Webapp Smoke Test

Run ONLY if any file in `TARGET_FILES` is under `app/`.

### 4a: Shared module import
```bash
conda run -n guyenv python -c "
import sys; sys.path.insert(0, 'app')
from shared import *
print('OK: shared.py imports clean')
"
```

### 4b: Modified page imports

For each modified `app/pages/*.py` file:
```bash
conda run -n guyenv python -c "
import sys; sys.path.insert(0, 'app')
try:
    import importlib
    mod = importlib.import_module('pages.<module_name>')
    print('OK')
except Exception as e:
    if 'streamlit' in str(type(e).__module__).lower() or 'Streamlit' in str(e):
        print(f'WARN: Streamlit runtime error (expected): {type(e).__name__}')
    else:
        print(f'FAIL: {e}')
        raise
"
```

### 4c: Cross-import check (if shared.py was modified)

If `app/shared.py` is in `TARGET_FILES`, verify key exports still exist:
```bash
conda run -n guyenv python -c "
import sys; sys.path.insert(0, 'app')
from shared import PLOTLY_THEME, make_heatmap_fig
print('OK: key exports verified')
"
```

Report: `PASS` / `WARN` / `FAIL` for each step.

---

## Phase 5: Learn from Failures

Review all `FAIL` results from Phases 1–4.

For each failure:

1. **Known pattern?** Check if it matches an existing E001–E034+ entry. If yes, it was already reported — skip.

2. **New recurring pattern?** A pattern qualifies if:
   - It could happen again in other files (not a one-off typo)
   - It has a clear bad → fix pair
   - It can be described as a general rule

3. **If yes — add to COMMON_ERRORS.md:**
   - Read the file to find the current highest E-number
   - Assign the next number (E035, E036, etc.)
   - Add the full entry: `### EXXX — title`, Bad, Fix, Grep (if possible), Why, Found in
   - If a grep regex exists, update the **Quick-Scan Regex** at the top of COMMON_ERRORS.md

4. Report: `Phase 5: Added EXXX to COMMON_ERRORS.md` or `Phase 5: No new patterns discovered`.

---

## Summary Report — Full Checklist

After all phases, print a **complete checklist** of every individual check performed.
The user wants to see exactly what was checked vs skipped so they can decide what to
trust and what to verify themselves.

Use this format — one line per check, grouped by phase. Every check gets a status icon:

- `✅` — checked and passed
- `❌` — checked and FAILED (needs attention)
- `⚠️` — checked with warnings (non-critical)
- `⏭️` — skipped (with reason)

```
═══════════════════════════════════════════════════════════════
  ERROR CHECK — FULL CHECKLIST
  Files: wr_bias_simulation.py, app/pages/05_bias_correction.py
═══════════════════════════════════════════════════════════════

Phase 1: Static Pattern Scan
  ✅ Quick-Scan Regex on wr_bias_simulation.py — 0 matches
  ❌ Quick-Scan Regex on 05_bias_correction.py — 5 E034 matches
     → Lines 2834, 9163, 9175, 9185, 9202: nanargmax without isfinite guard
     → Fix: Add `if np.any(np.isfinite(arr)):` before each call
  ✅ E003 (RV zero-filter) — N/A, no load_property calls
  ✅ E018 (PLOTLY_THEME collision) — 37 usages checked, all safe
  ✅ E024 (dataclass cache sync) — no new fields added
  ✅ E025 (removed widget refs) — no widgets removed

Phase 2: Cache Cleanup
  ✅ Deleted __pycache__/wr_bias_simulation.cpython-314.pyc
  ✅ Deleted app/pages/__pycache__/05_bias_correction.cpython-313.pyc
  ✅ Deleted app/pages/__pycache__/05_bias_correction.cpython-314.pyc

Phase 3: Functional Testing
  ✅ py_compile wr_bias_simulation.py — OK
  ✅ py_compile 05_bias_correction.py — OK
  ✅ import wr_bias_simulation — OK
  ⚠️ import pages.05_bias_correction — Streamlit warnings (expected)
  ✅ adaptive_bin_edges([1,5,10,50,100,200]) — ndarray, 4 bins
  ✅ sample_inclination(100, rng) — ndarray, len=100
  ✅ compute_K1(P=5, e=0.1, M1=20, M2=10, i=1.2) — 102.4 km/s
  ✅ solve_kepler([0.5, 1.0, 2.0], 0.3) — ndarray, len=3
  ✅ ks_two_sample(d1, d2) — D=0.19, p=0.054
  ⏭️ simulate_delta_rv_sample — needs SimulationConfig + data
  ⏭️ run_bias_grid — needs full config + observed data
  ⏭️ _render_dsilva_tab — Streamlit page function
  ⏭️ _render_langer_tab — Streamlit page function

Phase 4: Webapp Smoke Test
  ✅ from shared import * — OK
  ⚠️ import pages.05_bias_correction — Streamlit warnings (expected)
  ✅ PLOTLY_THEME, make_heatmap_fig exports — verified

Phase 5: Learning
  ✅ All failures match existing E034 — no new patterns

═══════════════════════════════════════════════════════════════
  OVERALL: ❌ FAIL — 5 issues need attention (see Phase 1)
  Checked: 18 items | Passed: 15 | Failed: 1 | Warned: 2 | Skipped: 4
═══════════════════════════════════════════════════════════════
```

**Key rules for the checklist:**
- List EVERY individual check — do not collapse or summarize. The user wants the full picture.
- For `❌` items: include the line numbers, the problem, and the fix — all inline.
- For `⏭️` items: always say WHY it was skipped (e.g., "needs Streamlit runtime", "requires file I/O").
- The footer counts give the user a quick read: how many things were checked vs skipped.
- **OVERALL** is `❌ FAIL` if ANY check failed. `✅ PASS` only when zero failures.

If any check failed, end with: "Should I fix these issues now?"
