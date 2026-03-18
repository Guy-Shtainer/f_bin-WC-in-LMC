# Error Check Report

**Target files:**
- `wr_bias_simulation.py`
- `app/pages/05_bias_correction.py`

**Date:** 2026-03-16

---

## Phase 1: Static Pattern Scan

### Quick-Scan Regex Results

**`wr_bias_simulation.py`**: 0 matches -- CLEAN

**`app/pages/05_bias_correction.py`**: 22 matches for `nanargmax`/`nanargmin` (E034 pattern)

#### E034 Violations (nanargmax/nanargmin without NaN guard)

The following locations call `np.nanargmax` or `np.nanargmin` **without** a preceding `np.any(np.isfinite(...))` guard:

| Line | Code | Status |
|------|------|--------|
| 267 | `np.nanargmax(ks_p)` | PASS -- guarded by line 266 `np.any(np.isfinite(ks_p))` |
| 271 | `np.nanargmax(ks_p)` | PASS -- guarded by line 270 `np.any(np.isfinite(ks_p))` |
| 1464 | `np.nanargmin(S_vals)` | PASS -- guarded by line 1460-1462 `finite.sum() == 0` early return |
| 1467 | `np.nanargmin(S_vals)` | PASS -- guarded by line 1460-1462 |
| 1513 | `np.nanargmin(S_2d)` | PASS -- guarded by similar finite check above |
| 1516 | `np.nanargmin(S_2d)` | PASS -- guarded |
| 1580 | `np.nanargmin(S_3d)` | PASS -- guarded |
| 1584 | `np.nanargmin(S_3d)` | PASS -- guarded |
| **2834** | `np.nanargmax(ks_p_4d)` | **FAIL [E034]** -- NO finite guard before this call. If `ks_p_4d` is all-NaN, raises `ValueError`. |
| 2965 | `np.nanargmax(ks_p_4d)` | PASS -- guarded by line 2964 `_valid_mask.any()` |
| 6145 | `np.nanargmax(ks_p)` | PASS -- guarded by line 6142 `np.any(np.isfinite(ks_p))` |
| 6496 | `np.nanargmax(hm_z)` | PASS -- guarded by line 6495 `np.any(np.isfinite(hm_z))` |
| 6534 | `np.nanargmax(ks_p_arr)` | PASS -- guarded by line 6531 `np.any(np.isfinite(ks_p_arr))` |
| **6605** | `np.nanargmax(ks_p_arr)` | **WARN** -- inside `if n_sig > 1:` block but no direct finite guard. Potentially reachable if `ks_p_arr` is all-NaN. |
| 6670 | `np.nanargmax(ks_p_arr)` | PASS -- guarded by line 6666 `np.any(np.isfinite(ks_p_arr))` |
| 6900 | `np.nanargmax(_zf)` | PASS -- guarded by line 6898 `np.any(np.isfinite(_zf))` |
| 7009 | `np.nanargmax(_sl)` | PASS -- context has `continue` for non-finite cases above |
| 7054 | `np.nanargmax(ks_p_arr)` | PASS -- guarded by line 7050 `np.any(np.isfinite(ks_p_arr))` |
| **9163** | `np.nanargmax(ks_p)` | **FAIL [E034]** -- NO finite guard in comparison tab `_extract_result_info`. If loaded result is all-NaN, raises `ValueError`. |
| **9175** | `np.nanargmax(ks_p)` | **FAIL [E034]** -- same function, no guard |
| **9185** | `np.nanargmax(ks_p)` | **FAIL [E034]** -- same function, no guard |
| **9202** | `np.nanargmax(ks_p)` | **FAIL [E034]** -- same function, no guard |

### Non-Greppable Checks

- **E003 (load_property RV filter)**: Neither file calls `load_property('RVs'` or `load_property('full_RV'` -- N/A.
- **E018 (PLOTLY_THEME keyword collision)**: 37 uses of `**PLOTLY_THEME` found. All use the safe `**{**PLOTLY_THEME, 'key': ...}` dict literal pattern OR do not conflict with PLOTLY_THEME keys (e.g., `height`, `width`, `showlegend`). **PASS -- no violations.**
- **E024 (dataclass field cache check)**: No new fields added to dataclasses in current diff. N/A.
- **E025 (removed widget variable)**: No widget variables removed in current diff. N/A.

### Phase 1 Summary

**Phase 1: FAIL -- 5 E034 violations found (lines 2834, 9163, 9175, 9185, 9202)**

Fix: Add `if np.any(np.isfinite(ks_p)):` guard before each `np.nanargmax` call.

---

## Phase 2: Cache Cleanup

Bash `rm` commands were denied by the sandbox. Cache cleanup could not be performed.

**Phase 2: SKIP -- sandbox restriction on file deletion**

---

## Phase 3: Functional Testing

### 3a: py_compile (baseline)

| File | Result |
|------|--------|
| `wr_bias_simulation.py` | PASS |
| `app/pages/05_bias_correction.py` | PASS |

### 3b: Import test

| File | Result |
|------|--------|
| `wr_bias_simulation.py` | PASS -- `import wr_bias_simulation` OK |
| `app/pages/05_bias_correction.py` | WARN -- Streamlit runtime warnings (expected outside `streamlit run`) |

### 3c: Function-level smoke tests

| Function | Result | Output |
|----------|--------|--------|
| `adaptive_bin_edges(obs)` | PASS | ndarray len=5 |
| `sample_inclination(100, rng)` | PASS | ndarray len=100 |
| `compute_K1(P, e, M1, M2, i)` | PASS | 102.36 km/s |
| `solve_kepler(M_arr, e)` | PASS | ndarray len=3 |
| `ks_two_sample(d1, d2)` | PASS | D=0.1900, p=0.0539 |
| `binned_cdf(data, edges)` | PASS | correct CDF values |
| `compute_hdi68(x, posterior)` | PASS | mode=0.495, lo=0.404, hi=0.596 |
| `ks_weighted_D(obs, sim, w)` | PASS | D=0.1000 |
| `cvm_weighted_score(sim, obs, var, drv, edges)` | PASS | S=2.5, p=1.0, S_raw=0.025 |
| `sample_logP_powerlaw(pi, size, logP_min, logP_max, rng)` | PASS | len=100, mean=0.98 |
| `simulate_delta_rv_sample(...)` | SKIP -- requires SimulationConfig+BinaryParameterConfig+data setup |
| `run_bias_grid(...)` | SKIP -- requires full config + observed data |
| Streamlit page functions | SKIP -- need Streamlit runtime |

**Phase 3: PASS -- 10/10 testable functions passed, 0 FAIL**

---

## Phase 4: Webapp Smoke Test

| Test | Result |
|------|--------|
| 4a: `from shared import *` | PASS |
| 4b: `import pages.05_bias_correction` | WARN (Streamlit runtime warnings, expected) |
| 4c: `from shared import PLOTLY_THEME, make_heatmap_fig` | PASS -- key exports verified |

**PLOTLY_THEME keys confirmed:** `plot_bgcolor`, `paper_bgcolor`, `font`, `xaxis`, `yaxis`, `title`, `legend`

**Phase 4: PASS (with expected Streamlit WARN)**

---

## Phase 5: Learn from Failures

All 5 failures are instances of **E034** (nanargmax/nanargmin on potentially all-NaN arrays), which is already documented in `COMMON_ERRORS.md`. No new error patterns discovered.

**Phase 5: DONE -- No new patterns discovered**

---

## Summary

```
+----------------------+--------+------------------------------------------+
| Phase                | Result | Details                                  |
+----------------------+--------+------------------------------------------+
| 1. Static patterns   | FAIL   | 5 E034 violations in 05_bias_correction  |
| 2. Cache cleanup     | SKIP   | Sandbox restriction on rm commands       |
| 3. Functional tests  | PASS   | 10/10 functions passed                   |
| 4. Webapp smoke test | PASS   | shared.py + 1 page OK (WARN expected)    |
| 5. Learning          | DONE   | No new patterns (all known E034)         |
+----------------------+--------+------------------------------------------+
| OVERALL              | FAIL   | 5 unguarded nanargmax calls              |
+----------------------+--------+------------------------------------------+
```

### Failures Detail

1. **`app/pages/05_bias_correction.py:2834`** -- `np.nanargmax(ks_p_4d)` without finite guard in Dsilva 4D sigma browse section.
   - **Fix:** Add `if np.any(np.isfinite(ks_p_4d)):` before line 2834.

2. **`app/pages/05_bias_correction.py:9163`** -- `np.nanargmax(ks_p)` without finite guard in `_extract_result_info()` comparison tab (ndim==4 branch).
   - **Fix:** Add `if not np.any(np.isfinite(ks_p)): return info` before the ndim checks.

3. **`app/pages/05_bias_correction.py:9175`** -- Same function, ndim==3 branch.

4. **`app/pages/05_bias_correction.py:9185`** -- Same function, ndim==2 branch (Dsilva).

5. **`app/pages/05_bias_correction.py:9202`** -- Same function, ndim==2 branch (Langer).

**Should I fix these issues now?**
