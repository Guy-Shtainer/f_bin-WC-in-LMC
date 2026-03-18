# Error Check Results for Modified Python Files

**Date:** 2026-03-16
**Files checked:** `wr_bias_simulation.py`, `app/pages/05_bias_correction.py`

## Compilation Check

| File | py_compile | Status |
|------|-----------|--------|
| `wr_bias_simulation.py` | PASS | No syntax errors |
| `app/pages/05_bias_correction.py` | PASS | No syntax errors |

## Common Error Pattern Scan (COMMON_ERRORS.md)

### Checked Patterns (all clean)

| Pattern | ID | Result |
|---------|----|--------|
| `np.trapz` (removed in numpy 2.0) | E001 | Not found |
| `numpy.bool_` identity comparison | E002 | Not found |
| `CLAUDECODE` / `allow_dangerously_skip_permissions` | E006/E010 | Not found |
| `asyncio.sleep` | E007/E016 | Not found |
| `.applymap()` (pandas 2.x removed) | E017 | Not found |
| `**PLOTLY_THEME` keyword collision | E018 | All uses correct (`**{**PLOTLY_THEME, ...}` pattern) |
| `@st.cache_data` underscore params | E023 | Not found |
| `omega`/`T0` uninitialized before `if n_bin > 0` | E033 | Fixed (pre-initialized at lines 931-932) |

### Issues Found

#### 1. POTENTIAL BUG (E034): Unguarded `np.nanargmax` in Dsilva results display

**File:** `app/pages/05_bias_correction.py`, line 2834
**Severity:** Medium (runtime crash if all-NaN grid)
**Code:**
```python
_flat_best_4d = int(np.nanargmax(ks_p_4d))
```
**Problem:** No `np.any(np.isfinite(ks_p_4d))` guard before calling `np.nanargmax`. If the result grid contains all NaN values (e.g., from a partial/failed simulation), this raises `ValueError: All-NaN slice encountered`.

**Context:** This is in the Dsilva tab results display section ("Sigma browse"). Other locations in the same file (e.g., lines 266, 6142, 6531, 6666, 7050) properly guard with `np.any(np.isfinite(...))` checks, but this one does not.

**Fix:** Add a finite-check guard:
```python
if not np.any(np.isfinite(ks_p_4d)):
    st.warning('No finite values in result grid.')
else:
    _flat_best_4d = int(np.nanargmax(ks_p_4d))
    ...
```

#### 2. POTENTIAL BUG (E034): Unguarded `np.nanargmax` in compare tab `_get_arrays()`

**File:** `app/pages/05_bias_correction.py`, lines 9163, 9175, 9185, 9202
**Severity:** Medium (runtime crash if loading empty/partial results for comparison)
**Code:**
```python
flat_idx = int(np.nanargmax(ks_p))  # lines 9163, 9175, 9185, 9202
```
**Problem:** The `_get_arrays()` function in the compare tab calls `np.nanargmax(ks_p)` without any finite-value guard. If a loaded result file has all-NaN p-values, this crashes.

**Fix:** Add a guard at the top of the section:
```python
if not np.any(np.isfinite(ks_p)):
    return info
```

#### 3. LOW RISK (E027): `np.empty` for accumulation arrays

**File:** `wr_bias_simulation.py`, lines 1553-1554, 1721-1722
**Severity:** Low (currently safe but fragile)
**Code:**
```python
ks_D = np.empty((n_sig, n_fb, n_pi), dtype=float)
ks_p = np.empty((n_sig, n_fb, n_pi), dtype=float)
```
**Note:** These are technically safe because the subsequent loop fills every cell (one result per grid task). However, `ks_S_raw` at line 1555/1723 correctly uses `np.full(..., np.nan)`. For consistency and safety against future changes (e.g., if a task fails and returns partial results), these should also use `np.full(..., np.nan)`.

## Summary

- **2 files checked**, both compile cleanly
- **2 medium-severity issues found:** unguarded `np.nanargmax` calls (E034 pattern) at 5 locations in `05_bias_correction.py` that could crash with all-NaN data
- **1 low-severity consistency issue:** `np.empty` vs `np.full(..., np.nan)` in `wr_bias_simulation.py`
- **All other COMMON_ERRORS patterns:** clean
