# Error Check Results: utils.py

**Date:** 2026-03-16
**Target file:** `utils.py`
**Skill used:** `/error-check`

---

## Phase 1: Static Pattern Scan — PASS

### Quick-Scan Regex
Ran combined grep pattern from COMMON_ERRORS.md against `utils.py`:
```
grep -n -E 'np\.trapz\b|\.bool_\b.*is (True|False)|\.int_\b|\.float_\b|\.complex_\b|\.object_\b|\.str_\b|CLAUDECODE|allow_dangerously_skip_permissions|\.replace\(second=.*\.second\s*\+|nanargmax|nanargmin' utils.py
```
**Result: 0 matches.**

### Non-Greppable Checks
| Check | Applicable? | Result |
|-------|------------|--------|
| E003 (zero-filter on RV) | No — no `load_property` calls | N/A |
| E018 (PLOTLY_THEME collision) | No — no Plotly usage | N/A |
| E024 (dataclass field vs cache) | No — no dataclasses | N/A |
| E025 (removed widget refs) | No — no Streamlit widgets | N/A |

**Phase 1: PASS — 0 matches in 1 file**

---

## Phase 2: Cache Cleanup — DONE

Found and removed 2 stale `.pyc` files:
- `__pycache__/utils.cpython-312.pyc`
- `__pycache__/utils.cpython-314.pyc`

**Phase 2: Cleaned 2 .pyc files**

---

## Phase 3: Functional Testing — PASS

### 3a: py_compile
```
conda run -n guyenv python -m py_compile utils.py
```
**Result: PASS** (zero output, no syntax errors)

### 3b: Import test
```
conda run -n guyenv python -c "import utils; print('OK')"
```
**Result: PASS** — module imports cleanly

### 3c: Function-level smoke tests

#### robust_mean
| Test case | Input | Result | Status |
|-----------|-------|--------|--------|
| With outlier | `[1, 2, 3, 100, 4]`, sigma=3 | 22.0000 | PASS |
| Clean data | `[1, 2, 3, 4, 5]`, sigma=3 | 3.0000 | PASS |
| Single element | `[42]`, sigma=3 | 42.0000 | PASS |
| NaN input | `[1, NaN, 3]`, sigma=3 | nan (RuntimeWarning) | PASS (no crash) |
| Empty array | `[]`, sigma=3 | nan (RuntimeWarning) | PASS (no crash) |

#### double_robust_mean
| Test case | Input | Result | Status |
|-----------|-------|--------|--------|
| With outlier | `[1, 2, 3, 100, 4]`, sigma=3 | 22.0000 | PASS |
| Clean data | `[1, 2, 3, 4, 5]`, sigma=3 | 3.0000 | PASS |
| Single element | `[42]`, sigma=3 | 42.0000 | PASS |

#### robust_std
| Test case | Input | Result | Status |
|-----------|-------|--------|--------|
| With outlier | `[1, 2, 3, 100, 4]`, sigma=3 | 39.0128 | PASS |
| Clean data | `[1, 2, 3, 4, 5]`, sigma=3 | 1.4142 | PASS |
| Single element | `[42]`, sigma=3 | 0.0000 | PASS |
| NaN input | `[1, NaN, 3]`, sigma=3 | nan (RuntimeWarning) | PASS (no crash) |

**Phase 3: PASS — 3/3 functions passed (11/11 test cases)**

---

## Phase 4: Webapp Smoke Test — SKIP

`utils.py` is not under `app/`. Phase 4 skipped per skill instructions.

---

## Phase 5: Learn from Failures — No new patterns

No failures in any phase. No new error patterns to add to `COMMON_ERRORS.md`.

**Phase 5: No new patterns discovered**

---

## Summary

```
+----------------------+--------+--------------------------------+
| Phase                | Result | Details                        |
+----------------------+--------+--------------------------------+
| 1. Static patterns   | PASS   | 0 matches in 1 file            |
| 2. Cache cleanup     | DONE   | Cleaned 2 .pyc files           |
| 3. Functional tests  | PASS   | 3/3 functions passed           |
| 4. Webapp smoke test | SKIP   | Not an app/ file               |
| 5. Learning          | DONE   | No new patterns                |
+----------------------+--------+--------------------------------+
| OVERALL              | PASS   |                                |
+----------------------+--------+--------------------------------+
```

### Notes
- The file has a duplicate `import numpy as np` on line 45 (harmless but redundant).
- NaN and empty-array edge cases produce `nan` with RuntimeWarnings rather than raising exceptions. This is standard numpy behavior and acceptable for the project's use case.
- The `robust_mean` with outlier `[1, 2, 3, 100, 4]` returns 22.0 because the outlier (100) is within 3-sigma of the mean (22.0, std=39.01), so no clipping occurs. This is correct behavior -- the sigma threshold would need to be tighter to clip 100 from this small dataset.
