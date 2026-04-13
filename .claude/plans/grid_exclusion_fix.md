# Fix Grid Exclusion for sigma_single and logPmax

**Created**: 2026-04-03 | **Status**: Planned, not implemented

## Context

Grid exclusion in bias correction cadence tabs only works for the 2D inner axes (fbin×pi for Dsilva, fbin×sigma for Langer). Two bugs:

1. **Sigma (Dsilva)**: The multiselect widget exists in `helpers.py:159` but the return value is **discarded** — never captured to a variable. Even if captured, no code builds or applies a 1D mask from it.
2. **LogPmax (both)**: No UI widget exists at all. No exclusion possible.

Array layouts:
| Tab | No logPmax scan | With logPmax scan |
|-----|----------------|-------------------|
| Dsilva | `[sigma, fbin, pi]` 3D | `[logPmax, sigma, fbin, pi]` 4D |
| Langer | `[sigma, fbin]` 2D | `[logPmax, sigma, fbin]` 3D |

The 2D mask from `render_grid_exclusion()` covers the last 2 dims and is applied via `arr[..., mask]=np.nan`, which broadcasts correctly. The outer dims (sigma, logPmax) are never masked.

Only 2 callers of `render_grid_exclusion()`, both in `cadence.py`.

---

## Approach A (Recommended): Return a dict instead of bare ndarray

Change `render_grid_exclusion()` to return a dict with all masks:

```python
return {
    'mask_2d': _exc_mask_2d,        # (n_x, n_y) — always present
    'sig_1d': _sig_exc_1d or None,  # (n_sig,) — only if sigma_grid provided
    'lp_1d': _lp_exc_1d or None,    # (n_lp,) — only if logPmax_grid provided
}
```

**Pros**: Explicit data flow, no hidden session_state coupling, easy to reason about.
**Cons**: Both callers need updating (trivial — just unpack the dict). Session_state still needed for downstream scoring renderers that read `{prefix}_exc_mask_2d`.

### Changes

#### `app/bc/helpers.py` — `render_grid_exclusion()` (lines 99-196)

1. Add param: `logPmax_grid: np.ndarray | None = None`
2. Compute `_has_logPmax = logPmax_grid is not None and len(logPmax_grid) > 1`
3. Column count: `_n_exc_cols = 2 + int(_has_sigma) + int(_has_logPmax)`
4. **Capture** sigma multiselect return (line 159 → `_exc_sig_vals = _exc_ax_cols[idx].multiselect(...)`)
5. **Add** logPmax multiselect when `_has_logPmax`
6. Build 1D masks:
   - `_sig_exc_1d = np.array([float(v) in set(_exc_sig_vals) for v in sigma_grid])` if `_has_sigma`
   - `_lp_exc_1d = np.array([float(v) in set(_exc_lp_vals) for v in logPmax_grid])` if `_has_logPmax`
7. Still store `_exc_mask_2d` in session_state (downstream scoring needs it)
8. Return dict instead of ndarray

#### `app/bc/cadence.py` — Dsilva block (lines 647-668)

```python
_exc = render_grid_exclusion(
    f'{p}_likelihood_analysis', fbin_grid, pi_grid,
    'f_bin', 'π', sigma_grid=sigma_grid, logPmax_grid=logPmax_grid,
)
_exc_2d = _exc['mask_2d']
_sig_exc = _exc.get('sig_1d')
_lp_exc = _exc.get('lp_1d')

_any_exc = ((_exc_2d is not None and _exc_2d.any())
            or (_sig_exc is not None and _sig_exc.any())
            or (_lp_exc is not None and _lp_exc.any()))

if _any_exc:
    _masked_result = dict(result)
    for key in ('logL_raw', 'likelihood'):
        if key not in result:
            continue
        _arr = np.asarray(result[key], dtype=float).copy()
        if _exc_2d is not None and _exc_2d.any():
            _arr[..., _exc_2d] = np.nan           # last 2 dims
        if _sig_exc is not None and _sig_exc.any():
            if _arr.ndim == 3:                     # [sigma, fbin, pi]
                _arr[_sig_exc] = np.nan
            elif _arr.ndim == 4:                   # [logPmax, sigma, fbin, pi]
                _arr[:, _sig_exc] = np.nan
        if _lp_exc is not None and _lp_exc.any():
            if _arr.ndim == 4:                     # [logPmax, ...]
                _arr[_lp_exc] = np.nan
        _masked_result[key] = _arr
    model_ctx['result'] = _masked_result
```

#### `app/bc/cadence.py` — Langer block (lines 913-933)

Same pattern but sigma is the y-axis (already in 2D mask), so only logPmax 1D mask is new:

```python
_exc = render_grid_exclusion(
    f'{p}_likelihood_analysis', fbin_grid, sigma_grid,
    'f_bin', 'σ_single', sigma_grid=None, logPmax_grid=logPmax_grid,
)
_exc_2d = _exc['mask_2d']
_lp_exc = _exc.get('lp_1d')

_any_exc = ((_exc_2d is not None and _exc_2d.any())
            or (_lp_exc is not None and _lp_exc.any()))

if _any_exc:
    _masked_result = dict(result)
    for key in ('logL_raw', 'likelihood'):
        if key not in result:
            continue
        _arr = np.asarray(result[key], dtype=float).copy()
        if _exc_2d is not None and _exc_2d.any():
            _arr[..., _exc_2d] = np.nan
        if _lp_exc is not None and _lp_exc.any():
            if _arr.ndim >= 3:                     # [logPmax, sigma, fbin] or [logPmax, sigma, fbin, pi]
                _arr[_lp_exc] = np.nan
        _masked_result[key] = _arr
    model_ctx['result'] = _masked_result
```

---

## Approach B: Keep returning 2D mask, communicate extras via session_state

Keep the function signature and return type unchanged. Store 1D masks in session_state, read them in cadence.py.

**Pros**: Zero change to return type, backward compatible if more callers added later.
**Cons**: Hidden coupling via session_state key naming convention, harder to debug.

### Changes

#### `app/bc/helpers.py` — same widget additions as Approach A, but:
- Return `_exc_mask_2d` (unchanged)
- Store `st.session_state[f'{prefix}_exc_sig_1d'] = _sig_exc_1d`
- Store `st.session_state[f'{prefix}_exc_lp_1d'] = _lp_exc_1d`

#### `app/bc/cadence.py` — read from session_state:
```python
_sig_exc = st.session_state.get(f'{p}_likelihood_analysis_exc_sig_1d')
_lp_exc = st.session_state.get(f'{p}_likelihood_analysis_exc_lp_1d')
```
Rest of masking logic identical to Approach A.

---

## Downstream Impact — None Required

`render_lk_scoring.py` and `render_lk_scoring_langer.py` read `{prefix}_exc_mask_2d` from session_state and apply it to already-sliced 2D arrays. They do NOT need changes — sigma/logPmax exclusion happens upstream in `cadence.py` before the arrays get sliced to 2D.

## Files to Modify

| File | Lines | What |
|------|-------|------|
| `app/bc/helpers.py` | 99-196 | Add logPmax param, capture sigma, add logPmax widget, return dict |
| `app/bc/cadence.py` | 647-668 | Dsilva: unpack dict, apply sigma+logPmax 1D masks |
| `app/bc/cadence.py` | 913-933 | Langer: unpack dict, apply logPmax 1D mask |

## Verification

1. `/error-check` (pyflakes + render test)
2. Run app → Cadence Dsilva with sigma scan → verify sigma multiselect excludes grid slices
3. Run app → Cadence Dsilva with logPmax scan → verify logPmax multiselect appears and works
4. Run app → Cadence Langer with logPmax scan → verify logPmax exclusion works
5. Verify parabolic fit + heatmaps update after exclusion
6. Verify that exclusion with no values selected changes nothing (no regression)
