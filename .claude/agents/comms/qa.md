## Status: FAIL
## Round: 4

---

## Acceptance criteria check

- [✓] #1 — All 6 plots render on white bg / Times New Roman serif / black mirrored axes / **PARTIAL**: 5 of 6 plots pass. Plot #5 (`_plot_bin_occupancy`) explicitly sets `showgrid=True` on the y-axis at `bin_sensitivity_plots.py:615` for every subplot panel. Because `fig.update_yaxes(showgrid=True, row=row, col=col)` runs inside the per-scheme loop before `_layout_update` is called, and because Plotly's `update_layout(yaxis=dict(...))` only patches the first panel's axis (`yaxis`), not `yaxis2`, `yaxis3`, etc., the per-panel `showgrid=True` settings survive on all panels. Plot #5 will render with y-axis gridlines on a white background, violating criterion #1. See FAIL detail below.
- [✓] #2 — Plot #4 `vertical_spacing=0.22`, no `subplot_titles=` parameter (confirmed by grep — line 436 `make_subplots` call has no `subplot_titles` kwarg), two manual `fig.add_annotation` calls for panel titles (`bin_sensitivity_plots.py:473-484`). "Dsilva best" moved to `y=0.92 yref='y domain'` inside the panel. PASS.
- [✓] #3 — Plot #4 `st.caption` present at `bin_sensitivity.py:624-636`, begins "*1-D marginal posteriors over f_bin (top) and pi (bottom)...*", ends with "`memory/likelihood_bin_sensitivity.md §4` for pitfall details.*". Text matches briefing §Change 2 exactly. PASS.
- [✓] #4 — Plot #5 `st.caption` present at `bin_sensitivity.py:644-661`, begins "*Grey = observed per-bin counts; red = simulated counts...*", includes "Quantile binning maximises statistical power per bin" (line 652) and the 20/40/60/80 percentile instruction. Text matches briefing §Change 3 exactly. PASS.
- [✓] #5 — Source radio at `bin_sensitivity.py:189-196`: `options=['Real observations', 'Mock observations (known truth)']`, `index=0`. Exactly 2 options, default = real. PASS.
- [✓] #6 — Mock-mode block at `bin_sensitivity.py:233-264` gated on `if is_mock:`. Five widgets: `True f_bin` (0.46), `True pi` (0.0), `True sigma_single (km/s)` (15.0), `True log P_max` (5.0), `Mock RNG seed` (42). All `number_input`, no min/max constraints. Real-obs mode skips the block entirely. PASS.
- [✓] #7 — Ground-truth dict threaded through `SchemeResult.ground_truth` (scorer line 77). Truth overlays gated on `gt is not None`: gold star on plot #2 (lines 280-300), green dashed lines on plot #4 (lines 512-545), top-right annotation on plot #6 (lines 719-733). `_scheme_row` inserts `Δf_bin` and `Δπ` columns conditionally when `r.ground_truth is not None` (`bin_sensitivity.py:84-95`). PASS.
- [✓] #8 — Regression sub-checks all pass:
  - logL parity: `_logL_one_scheme` (`scorer:298-306`) is algorithmically identical to `wr_bias_simulation.multinomial_log_likelihood` (`wr_bias_simulation.py:1202-1244`) — same histogram, same `total_sim`, same `eps=1/pool.size`, same sum formula. PASS.
  - Seed formula: `int(_SEED_BASE + i)` with loop order `(i_sig, i_fb, i_pi)` at `scorer:397-410`. Matches `runners_cadence.py:82-92` (base 1234, same iteration order, `_idx += 1`). PASS.
  - E048 full-forwarding: `load_npz_context` reads all five keys (`bin_cfg`, `cadence_library`, `cadence_weights`, `period_model`, `sigma_meas`) at `scorer:100-166`. Untouched. PASS.
  - Round-3 render fix: `st.rerun(scope='app')` at `bin_sensitivity.py:507`, inside `_render_progress_fragment._poll()`, gated on `status in ('done', 'error')` and `not job.get('_main_rerun_done')`. Exactly one occurrence. PASS.

---

## Static / runtime checks

- py_compile: clean (exit 0) on all three files
- pyflakes: clean (exit 0) on all three files
- test_render.py: Passed 5 | Failed 0 | Warnings 0

---

## Intent mismatches (FAIL)

### Issue 1 — Criterion #1: Plot #5 y-axis gridlines not suppressed

**Root cause:** `app/bc/bin_sensitivity_plots.py:615` — inside `_plot_bin_occupancy`, the per-scheme loop calls:

    fig.update_yaxes(showgrid=True, gridcolor=palette['grid_color'], row=row, col=col)

This was carried over from the dark-theme era (when gridlines were desired). After the Round-4 theme swap, `_layout_update` spreads `_ACADEMIC_THEME` which sets `yaxis=dict(showgrid=False, ...)` via `update_layout`. However, `update_layout(yaxis=dict(showgrid=False))` patches only the top-level `yaxis` key (panel row=1, col=1 in Plotly's internal naming). Subplots for other row/col positions use `yaxis2`, `yaxis3`, etc., which are not patched by the top-level `yaxis` key. The `update_yaxes(showgrid=True, ...)` calls made per-panel before `_layout_update` survive, because `update_layout` does not propagate its top-level `yaxis` dict to numbered subplot axes. End result: all subplot y-axes in plot #5 display horizontal gridlines on the white paper background.

**Fix for coder (one line in one file):** In `app/bc/bin_sensitivity_plots.py`, change line 615:

    # BEFORE
    fig.update_yaxes(showgrid=True, gridcolor=palette['grid_color'],
                     row=row, col=col)

    # AFTER
    fig.update_yaxes(showgrid=False, row=row, col=col)

The `gridcolor` key is also removed since `showgrid=False` makes it irrelevant. This is the only change needed — no other files, no other functions.

---

## Test plan (after fix)

1. Re-run `conda run -n guyenv python -m py_compile app/bc/bin_sensitivity_plots.py` and `pyflakes` — must be clean.
2. Re-run `scripts/test_render.py` — must still be 5/0/0.
3. In the running webapp, navigate to Bias Correction → Bin Sensitivity → run a comparison → open the "Bin Diagnostics" sub-tab. The bar chart y-axes must show no horizontal gridlines on the white background.
4. Verify all other plots (#1-#4, #6) still have white backgrounds and no gridlines.
5. Verify mock mode: switch radio to "Mock observations (known truth)", run comparison, confirm Δf_bin/Δπ columns in summary table and truth overlays on plots #2, #4, #6.

---

Status: READY — FAIL. One-line fix required at `bin_sensitivity_plots.py:615`. All other 7 criteria and all 4 regression sub-checks pass.
