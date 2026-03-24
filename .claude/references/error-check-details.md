# Error Check — Detailed Testing Patterns

## Function-Level Smoke Test Data Heuristics

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

## Edge Cases to Test
- Empty arrays: `np.array([])`
- Single element: `np.array([1.0])`
- Arrays with NaN: `np.array([1.0, np.nan, 3.0])`

## What to Skip (Do NOT Test)
- Functions requiring file I/O (FITS loading, `Data/` directory access)
- Class methods needing complex initialization (ObservationManager, Star)
- Functions that write to disk or modify state
- Private helper functions called only internally (test the public API)

## What to Prioritize
- Pure computation functions (math, statistics, array manipulation)
- Simulation functions in `wr_bias_simulation.py`
- Utility functions in `utils.py` (`robust_mean`, `robust_std`, etc.)
- Streamlit render / tab functions — call with mock obs_data, assert no exception
- Any function with a clear input/output contract

## Streamlit Render Test Template

```python
import sys; sys.path.insert(0, 'app'); sys.path.insert(0, '.')
import numpy as np
obs_data = dict(
    pal={'font_color': '#fff', 'muted_color': '#888', 'bg_color': '#000'},
    t_full=np.arange(0, 301, dtype=float),
    f_obs=np.zeros(301), raw_frac=np.zeros(301),
    sig_err=np.ones(301)*0.01,
    t_dots=np.array([0.0, 45.0]), f_dots=np.array([0.4, 0.1]),
    e_dots=np.array([0.05, 0.05]),
    change_mask=np.zeros(301, dtype=bool),
    is_sig=np.array([True, False]), p2p=np.array([60.0, 20.0]),
    p2p_err=np.array([5.0, 3.0]),
    names=['s1','s2'], n_stars=2, star_centered_rvs={},
)
from <module> import <render_func>
<render_func>(obs_data)  # should not raise
```

## Summary Report Format

Use this format — one line per check, grouped by phase:
- `✅` — checked and passed
- `❌` — checked and FAILED (needs attention)
- `⚠️` — checked with warnings (non-critical)
- `⏭️` — skipped (with reason)

List EVERY individual check. For `❌` items: include line numbers, problem, and fix inline.
Footer: `Checked: N | Passed: N | Failed: N | Warned: N | Skipped: N`
OVERALL is `❌ FAIL` if ANY check failed. `✅ PASS` only when zero failures.
