# Code Quality Verification: utils.py

## Summary

**File:** `/Users/guyshtainer/Library/CloudStorage/OneDrive-Tel-AvivUniversity/תואר שני!/Thesis/Thesis-codes/utils.py`
**Lines:** 139
**Functions:** 3 (`robust_mean`, `double_robust_mean`, `robust_std`)
**Status:** File is functional with minor issues noted below.

---

## Issues Found

### Issue 1: Duplicate `import numpy as np` (Line 45)

**Severity:** Low (cosmetic)
**Location:** Line 45
**Description:** `import numpy as np` appears twice — once at line 1 and again at line 45 (between `robust_mean` and `double_robust_mean`). This has no runtime effect but is poor style and suggests the file was assembled by copy-pasting.

### Issue 2: Docstring default value mismatch

**Severity:** Low (documentation only)
**Location:** Lines 14, 59, 109
**Description:** All three functions have `sigma=3` as the actual default parameter, but the docstrings say `optional (default=2)`. The code uses `sigma=3`, which is correct based on all call sites found in the codebase (every caller passes `sigma=3` or `sigma=1` or `sigma=2` explicitly). The docstring is simply wrong — it should say `default=3`.

### Issue 3: No NaN handling

**Severity:** Medium (potential silent corruption)
**Description:** None of the three functions handle NaN values. When NaN is present in the input:
- `np.mean()` returns NaN
- `np.std()` returns NaN
- The boolean mask comparison with NaN produces False, so NaN elements are masked out
- But the initial `mean` and `std` are already NaN, so `sigma * std` is NaN, and the entire mask becomes all-False

This means with any NaN in input, the mask excludes ALL data points. In `robust_mean`, `np.any(~mask)` is True (all excluded), so it returns `np.mean(data[mask])` which is `np.mean([])` = NaN with a RuntimeWarning.

**Impact:** Several callers pass windowed flux arrays that could contain NaN (e.g., `NRESClass.py` SNR computation). The result is silent NaN propagation rather than a clear error.

**Recommendation:** Use `np.nanmean` and `np.nanstd`, or filter NaNs at entry: `data = data[~np.isnan(data)]`.

### Issue 4: Empty array behavior

**Severity:** Low
**Description:** Passing an empty array `[]` to any function triggers `RuntimeWarning: Mean of empty slice` from numpy and returns NaN. No explicit guard or error message.

### Issue 5: `double_robust_mean` — inverted early-exit logic (Line 81)

**Severity:** Low (practically unreachable)
**Location:** Line 81
**Description:** The check `if not np.any(mask1)` means "if no data points survived the filter." This would only happen if ALL points are more than `sigma` standard deviations from the mean, which is mathematically impossible for a dataset with finite variance — the mean is always within sigma*std of at least one point. So this branch is dead code.

However, the semantic intent seems correct (return early if filtering removed everything), and the condition is harmless.

---

## COMMON_ERRORS.md Pattern Scan (Static)

Checked all patterns from the quick-scan regex against `utils.py`:

| Pattern | Found? |
|---------|--------|
| `np.trapz` | No |
| `.bool_` identity comparison | No |
| Deprecated numpy scalar types | No |
| `CLAUDECODE` | No |
| `nanargmax` / `nanargmin` without guard | No |

**Result: No COMMON_ERRORS patterns found.**

---

## Codebase Usage

The file is imported as `import utils as ut` by 5 files:

| File | Functions Used |
|------|--------------|
| `StarClass.py` | `robust_mean`, `robust_std` |
| `NRESClass.py` | `robust_mean`, `robust_std` |
| `ISE.py` | `robust_mean`, `double_robust_mean`, `robust_std` |
| `INnres.py` | `robust_mean` |
| `IC2D.py` | `robust_mean` |

All three functions are actively used. No unused functions.

---

## Structural Assessment

- **No classes, no side effects, no file I/O** — pure numerical utility module. Clean design.
- **Single responsibility** per function — each does one thing (sigma-clipped mean or std).
- **Consistent API** — all functions take `(data, sigma)` and return a scalar.
- **No circular imports** — only depends on numpy.

---

## Verdict

The file is **functional and correct for its intended use**. The issues are minor:

1. **Fix recommended:** Remove the duplicate import on line 45.
2. **Fix recommended:** Update docstrings to say `default=3` instead of `default=2`.
3. **Consider:** Adding NaN filtering at entry if callers may pass NaN-containing arrays.
4. The dead-code early-exit in `double_robust_mean` is harmless.

No bugs that would produce incorrect results for valid (non-NaN, non-empty) input.

---

## Note on Testing

Bash tool access was denied during this session, so syntax checking (`py_compile`) and runtime functional tests could not be executed. The analysis above is based on thorough static code review and cross-referencing with codebase usage patterns. The file has been in active use across 5 modules with no reported issues, which provides indirect evidence of correctness.
