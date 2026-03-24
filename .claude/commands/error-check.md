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

3. Use **domain-specific test data heuristics** from `.claude/references/error-check-details.md` to create realistic inputs.

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

5. Also test edge cases and Streamlit render functions. See `.claude/references/error-check-details.md` for edge cases, skip/prioritize rules, and the render test template.

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
See `.claude/references/error-check-details.md` for the report format template (status icons, rules).

**Key rules:** List EVERY check (no collapsing). `❌` items include line numbers + fix inline. `⏭️` items include skip reason. Footer: `Checked: N | Passed: N | Failed: N | Warned: N | Skipped: N`. OVERALL = `❌ FAIL` if ANY failed.

If any check failed, end with: "Should I fix these issues now?"
