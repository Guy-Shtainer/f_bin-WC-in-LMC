# Coder — Three small cleanups on top of TODO 187 sprint (2026-04-23)

## Status: done

## Scope
Three independent cleanups requested after TODO 187 (Validation tab 6-bug
fix) was merged:

1. **Corner plot vline** — switch diagonal "best" vline from marginal
   mode to joint argmax.
2. **Langer resim bug** — fix undefined `xv` in f-string title at
   `app/bc/render_lk_explorer_langer.py:230`.
3. **Skipped** — grid↔Explorer reproducibility (per user).

No commit.

---

## Task 1 — Corner-plot diagonal vline: marginal mode → joint argmax

**File:** `app/bc/corner_plots.py`

### Change 1: `_add_1d_posterior` signature
Added a new `joint_argmax=None` kwarg (back-compat default).  The local
name `mode_val` was renamed to `_marg_mode` (underscore-prefixed to
signal "fallback only") and is now only consulted if the caller did not
pass a `joint_argmax` — i.e. old `.npz` files that lack `argmax_*` keys
still render.

### Change 2: vline source
The `fig.add_vline(x=...)` now uses `_vline_x = joint_argmax if joint_argmax is not None else _marg_mode`.

### Change 3: vline annotation
Added `annotation_text='Joint argmax'` (+ position `'top right'`, colour
`#E25A53`, size 9) so the red dashed line is self-labelling on every
diagonal panel.  Previously no annotation text was attached.

### Change 4: call site (`_render_corner_plot`)
Before calling `_add_1d_posterior` for each diagonal, the parameter
name (`fbin` / `pi` / `sigma` / `logPmax`) is mapped to the
corresponding `result['argmax_*']` key via a local dict:

```python
_argmax_keys = {
    'fbin': 'argmax_fbin',
    'pi': 'argmax_pi',
    'sigma': 'argmax_sigma',
    'logPmax': 'argmax_logPmax',
}
```

The value is pulled with safe conversion (`float(...)` + `np.isfinite`
guard inside a `try/except TypeError, ValueError`).  If the key is
absent (old `.npz`) or non-finite the code passes `None`, which
triggers the back-compat marginal-mode fallback in `_add_1d_posterior`.

### Change 5: caption
The `st.caption` below the corner plot now reads:
> *Diagonal: 1D marginal posteriors with 68% HDI (blue shading) and
> Joint argmax (red dashed — the parameter value at the N-D global
> logL maximum, not the marginal mode).  Off-diagonal: 2D marginalized
> heatmap(s) with 68%/95% contours and Joint argmax (gold star).*

(Previously said "mode (red dashed)" and "best fit (gold star)".)

### Exact diff
Full diff captured via `git diff app/bc/corner_plots.py` — 40 insertions,
6 deletions, all localised to `_add_1d_posterior` and
`_render_corner_plot`.  No other function in the file was touched.

### 2D gold-star left alone
The 2D heatmap's gold-star uses `_bv = _info['best_vals']` from
`_method_best_and_hdi`, which is already `nanargmax(p_nd)` — i.e. the
joint argmax OVER THE SQUEEZED corner-plot array.  For 2D/3D corner
plots this matches the true N-D joint argmax; for 4D corner plots with
a marginalised axis it's the joint argmax of the projected surface,
which is the correct thing to plot on a 2D slice.  User's brief
explicitly called out "the diagonal 1D panels" so I left the star
alone.

---

## Task 2 — Undefined `xv` at `render_lk_explorer_langer.py:230`

**File:** `app/bc/render_lk_explorer_langer.py`

### Diagnosis
The function `_render_lk_resim_interp` (lines 164-239) was clearly
copy-pasted from the Dsilva twin (`render_lk_explorer.py:228-305`)
where `xv = float(interp.get('pi', interp.get('sigma',
interp.get('y_val', 0.0))))` is set on line 243.  In the Langer port
the equivalent line is `_lp_resim = float(interp.get('logPmax',
interp.get('y_val', 3.5)))` (line 179-180) — the variable was renamed
`xv → _lp_resim` in the body but the f-string title on line 230 was
missed.

### Which variable is `x_label`?
Searched `runners_cadence.py:372` for the Langer path — `x_label` is
set to `'σ_single (km/s)'` and `x_name` is `'σ'`.  So the Langer
x-axis IS sigma, not π.  The variable in scope at line 230 that holds
the interpolated sigma is `sig` (line 181:
`sig = float(interp.get('sigma', result.get('sigma_meas', 5.0)))`).

### Fix
Substituted `sig` for `xv` and added `logP_max={_lp_resim:.3f}` to the
title so the user sees the full Langer parameter triple (`f_bin`,
`σ_single`, `logP_max`):

```python
text=(f'Re-sim: f_bin={fb:.4f}, {x_label}={sig:.3f}, '
      f'logP_max={_lp_resim:.3f}'),
```

Added a comment explaining the origin of the bug.

---

## Task 3 — Skipped per user instruction
No edits.

---

## Verification results

### Pyflakes
- `app/bc/corner_plots.py` — **clean** (no warnings).
- `app/bc/render_lk_explorer_langer.py` — 5 warnings remain, ALL
  pre-existing (verified by running pyflakes on
  `git show HEAD:app/bc/render_lk_explorer_langer.py`, which reported
  6 warnings including `undefined name 'xv'` at line 189).  My edit
  removed the `xv` warning and introduced none.  The 5 surviving
  warnings (`simulate_delta_rv_sample`/`SimulationConfig`/
  `BinaryParameterConfig` unused imports, `def_x`/`me_x`/`_me_lp_idx`
  unused locals) are outside the scope of these three cleanups.

### Runtime tests (all four PASS)
- `scripts/test_render.py` — **5 passed, 0 failed, 0 warnings**.
- `scripts/test_explorer_mock_equal.py` — both fixed-σ and log-normal
  cases report `max diff = 0.00e+00`; regression guard confirms
  σ_meas affects ΔRV.
- `scripts/test_explorer_mock_equal_langer.py` — same two cases for
  the Langer model; both `max diff = 0.00e+00`; σ_meas regression
  guard passes.
- `scripts/test_grid_vs_explorer_score.py` — grid logL = −13.429,
  explorer logL = −13.531, |diff| = 0.103 within sampling tolerance.

---

## Ambiguity / open questions
None.  Both tasks were surgical; no working code outside the two
target functions was touched.

## Files modified
- `/Users/guyshtainer/Library/CloudStorage/OneDrive-Tel-AvivUniversity/תואר שני!/Thesis/Thesis-codes/app/bc/corner_plots.py`
- `/Users/guyshtainer/Library/CloudStorage/OneDrive-Tel-AvivUniversity/תואר שני!/Thesis/Thesis-codes/app/bc/render_lk_explorer_langer.py`
