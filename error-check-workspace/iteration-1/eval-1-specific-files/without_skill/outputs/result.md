# Code Quality Verification Report

## Files Analyzed
1. `/Users/guyshtainer/Library/CloudStorage/OneDrive-Tel-AvivUniversity/תואר שני!/Thesis/Thesis-codes/wr_bias_simulation.py` (2559 lines)
2. `/Users/guyshtainer/Library/CloudStorage/OneDrive-Tel-AvivUniversity/תואר שני!/Thesis/Thesis-codes/app/pages/05_bias_correction.py` (9731 lines)

## Compilation Check
Both files pass `python -m py_compile` with zero errors.

---

## COMMON_ERRORS.md Pattern Scan

| Pattern | wr_bias_simulation.py | 05_bias_correction.py |
|---------|----------------------|----------------------|
| E001 `np.trapz` | CLEAN | CLEAN |
| E002 `numpy.bool_ is True/False` | CLEAN | CLEAN |
| E017 `.applymap()` | N/A | CLEAN |
| E027 `np.empty()` for accum | See findings below | CLEAN |
| E034 `nanargmax/nanargmin` guards | CLEAN | See findings below |
| `asyncio.sleep` | CLEAN | CLEAN |

---

## Issues Found

### CRITICAL: `_render_cdf_sanity_check()` uses wrong API for `simulate_delta_rv_sample`

**File:** `app/pages/05_bias_correction.py`, lines 765-774
**Severity:** HIGH (function is silently broken)

The function `simulate_delta_rv_sample` has signature:
```python
def simulate_delta_rv_sample(f_bin, pi, sim_cfg, bin_cfg, rng):
```

But the call at line 765 uses completely wrong keyword arguments:
```python
drv = simulate_delta_rv_sample(
    n_stars=25,
    f_bin=best_fbin,
    sigma_single=sigma_single,
    sigma_measure=float(result.get('sigma_meas', 1.622)),
    binary_config=bcfg,        # wrong param name (should be bin_cfg)
    rng_seed=seed,             # wrong (should be rng=np.random.default_rng(seed))
    period_model=period_model, # not a param
    cadence_library=cadence_library,  # should be via SimulationConfig
)
```

This always raises `TypeError` at runtime. The error is silently swallowed by the `try/except` at lines 764/783. The CDF Sanity Check feature (5 random draws overlaid on observed) never actually renders any simulated draws.

**Fix required:** Rewrite the call to construct a `SimulationConfig` and `BinaryParameterConfig`, then call with the correct positional/keyword arguments.

---

### MEDIUM: `np.empty()` used for result arrays in `run_bias_grid` and `run_bias_grid_cadence_aware`

**File:** `wr_bias_simulation.py`, lines 1553-1554 and 1721-1722

```python
ks_D = np.empty((n_sig, n_fb, n_pi), dtype=float)
ks_p = np.empty((n_sig, n_fb, n_pi), dtype=float)
```

These arrays are populated by iterating over a `results` list that should contain one entry per cell. If the results list is complete, the arrays are fully populated and this is safe. However, `np.full(..., np.nan)` would be safer against partial failures (e.g., if a worker crashes). The cadence background runner (`_run_cadence_bg`, line 5905) correctly uses `np.full(..., np.nan)`.

**Risk:** Low in practice (the loop is deterministic), but inconsistent with project conventions.

---

### LOW: `nanargmax`/`nanargmin` calls without finite-value guards

**File:** `app/pages/05_bias_correction.py`

Most `nanargmax`/`nanargmin` calls have proper guards (`np.any(np.isfinite(...))`), but several locations lack them:

- **Line 2834:** `_flat_best_4d = int(np.nanargmax(ks_p_4d))` - No guard. If all values are NaN, this raises `ValueError`. However, this code path is only reached after a completed grid run, so it's unlikely to hit all-NaN in practice.

- **Lines 9161-9202:** Multiple `np.nanargmax(ks_p)` calls in the compare tab's result parsing. These are inside a `try/except` block that catches all exceptions, so the error is handled, but silently.

- **Lines 6532-6534, 7054:** Similar unguarded calls, but context makes all-NaN unlikely.

**Risk:** Low. Most are either in try/except blocks or in code paths where data is guaranteed to have finite values.

---

### LOW: Duplicate imports in `wr_bias_simulation.py`

**File:** `wr_bias_simulation.py`, lines 44-45 and 89-91

```python
# First occurrence (line 44-45):
from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Tuple, List

# Second occurrence (line 89-91):
from dataclasses import dataclass, field
from typing import Optional, List
import numpy as np
```

`dataclass`, `field`, `Optional`, `List`, and `numpy` are imported twice. This is harmless but untidy.

---

### INFO: `np.empty()` usage analysis in `wr_bias_simulation.py`

All `np.empty()` occurrences reviewed:

| Line | Context | Safe? |
|------|---------|-------|
| 408 | `logP = np.empty(size)` in `sample_logP_langer2020` | YES - immediately filled by mask_A/mask_B branches that cover all elements |
| 857 | `all_cdfs = np.empty(...)` in `simulate_delta_rv_cadence_aware` | YES - immediately filled in loop |
| 1201 | `all_cdfs = np.empty(...)` in `cvm_weighted_score` | YES - immediately filled in loop |
| 1409 | `all_drv = np.empty(...)` in `_single_grid_task_lite` | YES - immediately filled in loop |
| 1553-1554 | `ks_D/ks_p = np.empty(...)` in `run_bias_grid` | MEDIUM RISK - see finding above |
| 1721-1722 | `ks_D/ks_p = np.empty(...)` in `run_bias_grid_cadence_aware` | MEDIUM RISK - see finding above |
| 1925, 1931 | `all_drv/all_cdfs` in `resimulate_at_point` | YES - immediately filled in loop |
| 2201, 2206 | `np.empty(0)` (zero-size arrays) | YES - sentinel values |

---

## Summary

| Severity | Count | Description |
|----------|-------|-------------|
| CRITICAL | 1 | `_render_cdf_sanity_check` uses completely wrong API for `simulate_delta_rv_sample` (always silently fails) |
| MEDIUM | 1 | `np.empty()` instead of `np.full(..., np.nan)` in two grid runner functions |
| LOW | 2 | Unguarded `nanargmax` calls (mitigated by try/except); duplicate imports |

Both files compile cleanly and the core simulation engine (`wr_bias_simulation.py`) has no functional bugs in its public API. The main Streamlit page (`05_bias_correction.py`) is functional for its primary workflows (Dsilva, Langer, Cadence grid searches), but the CDF Sanity Check feature is completely non-functional due to an API mismatch that predates the current `simulate_delta_rv_sample` signature.
