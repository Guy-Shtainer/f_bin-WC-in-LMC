## Status: done

### Task
Add a user-facing `Std band bins` number_input above the CDF and f_bin-vs-threshold panels in the mock_inspector_app, controlling the x-resolution of the 16-84% percentile band on both panels via `smooth_pooled_cdf`'s `n_fine` parameter.

### Files edited
- `mock_inspector_app/app.py` — 528 → 544 lines (+16)
  - Added `'insp_band_bins': 500` to `DEFAULTS` dict.
  - Added a 3-column layout with the `Std band bins` `number_input` (no min/max, step=50, persisted via `_save_widget` on change) just above `cdf_col, fbin_col = st.columns([1, 1])`.
  - Wired `n_band_bins=int(st.session_state.insp_band_bins)` into both `make_drv_cdf_overlay_figure(...)` and `make_fbin_vs_threshold_overlay_figure(...)` calls.
- `mock_inspector_app/inspector.py` — 988 → 998 lines (+10)
  - `make_drv_cdf_overlay_figure(...)`: added `n_band_bins: int = 500` kwarg; forwards to a new `n_band_bins` kwarg on the internal `_add_smoothed_cdf_traces(...)` helper, which itself forwards to `smooth_pooled_cdf(..., n_fine=int(n_band_bins))`.
  - `make_fbin_vs_threshold_overlay_figure(...)`: added `n_band_bins: int = 500` kwarg; replaced the hardcoded `n_fine=2000` inside `_add_fbin_band_and_median(...)` with `n_fine=int(n_band_bins)` (closure captures the outer kwarg).
  - Updated the corresponding code comment ("`n_fine=2000` gives the band the tight small bins" → "x-resolution of the band is `n_band_bins` (default 500, user-tunable)").

### Verification (conda guyenv, real cadence data)
Verification script from spec ran clean:
```
n_band_bins=100:  CDF band lo n_pts=100,  fbin band lo n_pts=100
n_band_bins=500:  CDF band lo n_pts=500,  fbin band lo n_pts=500
n_band_bins=2000: CDF band lo n_pts=2000, fbin band lo n_pts=2000
n_band_bins=5000: CDF band lo n_pts=5000, fbin band lo n_pts=5000
default kwarg:    fbin band lo n_pts=500   (expect 500)              PASS
fbin Mock median n_pts: 12500 (expect ~12500 from pooled, NOT n_band_bins)  PASS
ALL_PASS
```

Static checks: `pyflakes` clean on both files, `py_compile` OK, AST parse OK.

### UI placement
The `Std band bins` `number_input` sits in the LEFT third of a `[1, 3, 1]` column row, immediately above the `[CDF panel | f_bin panel]` row that opens with `cdf_col, fbin_col = st.columns([1, 1])`. A `st.markdown('---')` separator sits just above the control row to visually detach it from the n_binaries summary caption that precedes it. Two empty spacer columns sit to the right of the control so the input doesn't stretch full-width.

### Confirmations
- `Run`, `Add single run`, `Clear single runs` are untouched — the buttons row sits in the upper "Control region" `st.container()` and was not edited. Their handler logic at the bottom of the controls block is unchanged.
- `smooth_pooled_cdf(..., n_fine=int(n_band_bins))` is invoked from BOTH `_add_smoothed_cdf_traces` (CDF panel) and `_add_fbin_band_and_median` (f_bin panel). One control, both panels.
- f_bin Mock median trace still uses the pooled-sorted x positions (`sorted_pool` from `smooth_pooled_cdf`), giving ~`n_iter * n_stars` points (~12,500 for the 500x25 default) — NOT downsampled to `n_band_bins`. Only the band itself uses `n_band_bins`. Verified above (`fbin Mock median n_pts: 12500`).
- Trace counts unchanged: with no single runs, CDF has 6 traces (Mock band x2 + Mock median + Explorer band x2 + Explorer median) and f_bin has 6 (same shape); single-run overlays add the existing N step lines + 2 dot traces on top, exactly as before.
- `insp_band_bins` persists via the existing `_save_widget` callback pattern, written through `SettingsManager.save(...)` to `mock_inspector_app/settings.json` on every change. Default `500` is read from `DEFAULTS` if the key is absent.
- No min/max constraints on the `number_input` (per project rule).

### Notes
- `Std band bins` only re-renders the two panels — clicking it does NOT trigger pipeline recomputation (it isn't in `_params_hash()`). The cached `result_mock` / `result_exp` arrays are reused; only the band is redrawn. This is the intended behaviour — the simulation arrays don't depend on band resolution.
- The internal helper `_add_smoothed_cdf_traces` now has a `n_band_bins` kwarg with default 500, so any other in-process caller (none currently) is fully backward-compatible.
