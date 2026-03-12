# Task #53: Model RV Measurement Errors from Observations for Bias Correction

## Plan

### Overview
Add an empirical error model to the bias correction simulation that samples per-epoch RV measurement errors from a fitted distribution (log-normal, gamma, or normal) instead of using a fixed `sigma_measure`. Also fix the critical bug where `sigma_measure` is never actually applied in the simulation functions.

### Shared Utilities Used
- `cached_load_observed_delta_rvs(settings_hash)` — to collect all rv_err arrays
- `settings_hash(settings)` — for cache key
- `PLOTLY_THEME` + `apply_theme(fig)` — for any new charts
- `render_sidebar()`, `inject_theme()` — page boilerplate
- `get_settings_manager()` — for saving error_model setting

### Structural Template
Existing `05_bias_correction.py` — adding to both Dsilva and Langer tabs.

### COMMON_ERRORS Patterns
- **E018**: PLOTLY_THEME collision — use `apply_theme()` for new charts
- **E024**: Audit cache reuse functions when adding new config fields
- **E023**: No underscore-prefixed cache params

---

## Step 1: Fix sigma_measure Bug in wr_bias_simulation.py

The `simulate_delta_rv_sample()`, `simulate_delta_rv_cadence_aware()`, and `simulate_with_params()` functions never apply `sigma_measure` noise. Fix by adding measurement noise:

### In `simulate_delta_rv_sample()`:
- **Singles** (around line 668-678): Add measurement noise in quadrature:
  ```python
  scale = math.sqrt(sim_cfg.sigma_single**2 + sim_cfg.sigma_measure**2)
  ```
  OR add separate per-epoch noise draws.

- **Binaries** (around line 728-733): After computing orbital RV, add per-epoch measurement noise:
  ```python
  v += rng.normal(loc=0.0, scale=sim_cfg.sigma_measure, size=v.shape)
  ```

### In `simulate_delta_rv_cadence_aware()`:
- Same pattern for singles and binaries.

### In `simulate_with_params()`:
- Same pattern for singles and binaries.

## Step 2: Add error_model to SimulationConfig

Add new field to `SimulationConfig`:
```python
error_model: str = "fixed"  # "fixed" or "empirical"
error_dist_params: Optional[Dict[str, float]] = field(default=None)
# e.g., {"dist": "lognormal", "mu": ..., "sigma": ...}
```

Modify the simulation functions to check `sim_cfg.error_model`:
- If "fixed": use `sim_cfg.sigma_measure` as before (now actually applied)
- If "empirical": sample per-epoch sigma from the fitted distribution, then apply per-epoch noise

## Step 3: Add Distribution Fitting Function to wr_bias_simulation.py

New function `fit_rv_error_distribution(rv_errors: np.ndarray) -> dict`:
- Try log-normal, gamma, and normal fits using scipy.stats
- Compute AIC/BIC for each
- Return dict with best fit params, distribution name, and comparison table

## Step 4: Add UI Toggle in 05_bias_correction.py

In both Dsilva and Langer tabs, near the `sigma_measure` widget:
- Add `st.radio("Error Model", ["Fixed σ_measure", "Empirical (fitted distribution)"])`
- When "Empirical" is selected:
  - Show fitted distribution info (type, params, AIC/BIC comparison)
  - Show histogram of observed errors with fitted overlay
  - Hide the manual σ_measure input
- When "Fixed" is selected:
  - Show the existing σ_measure number_input

Pass `error_model` and `error_dist_params` through to SimulationConfig.

## Step 5: Auto-fit on Page Load

On first load, automatically:
1. Collect all rv_err from `cached_load_observed_delta_rvs()`
2. Fit distributions
3. Cache results in `st.session_state`
4. Display summary

---

## Pre-Implementation Validation

### What does the user see when this page first loads?
The page already shows content on load (existing behavior unchanged). The new error model radio button defaults to "Fixed σ_measure" (current behavior). If the user switches to "Empirical", the distribution fit results and histogram appear immediately (auto-computed from cached data, no button needed).

### Which cached_load_* functions am I using?
- `cached_load_observed_delta_rvs(settings_hash(...))` — existing function in shared.py

### How am I using PLOTLY_THEME?
- `apply_theme(fig)` for the new error distribution histogram chart

### Cache reuse audit (E024):
- `_find_reusable_fbin()` already checks `sigma_measure` in `stable_cfg` → need to also check `error_model`
- `_find_reusable_fbin_langer()` → same
- The config hash in `.npz` files → need to include `error_model` field

---

## Files Modified
1. `wr_bias_simulation.py` — SimulationConfig fields, fix sigma_measure application, add error sampling, add distribution fitting function
2. `app/pages/05_bias_correction.py` — UI toggle, distribution display, pass error_model through to simulation
3. `settings/user_settings.json` — add simulation.error_model default

## Testing
- py_compile all modified files
- Verify sigma_measure is now actually applied in all 3 simulation functions
- Verify empirical error sampling works
- Regression: all project files still compile
