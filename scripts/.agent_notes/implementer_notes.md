# Implementer Notes

Learnings about implementation patterns and pitfalls in this project.

<!-- Notes will be auto-appended below this line -->

## Task #19 — 2026-03-03 (f_bin vs sigma and pi vs sigma heatmaps)

- **NEVER do `dict(title=..., **PLOTLY_THEME)` or `fig.update_layout(title=..., **PLOTLY_THEME)`.** `PLOTLY_THEME` (in `app/shared.py`) contains `title=dict(font=...)`, which collides and raises `TypeError: multiple values for keyword argument 'title'`. The correct pattern is: `fig.update_layout(**PLOTLY_THEME)` first, then override individual keys: `fig.update_layout(title=dict(text="My Title"))`.
- **`PLOTLY_THEME` keys to watch for collision:** `title`, `xaxis`, `yaxis`, `font`, `legend`, `plot_bgcolor`, `paper_bgcolor`. Never pass any of these as explicit kwargs in the same call that unpacks `**PLOTLY_THEME`.
- **py_compile passing ≠ runtime safe** — dict-unpacking conflicts are only caught at runtime when the conflicting line is actually executed. After implementing any Plotly layout change, mentally trace what keys would be in the merged dict.
- **The `.agent_work/{task_id}/test_report_N.md` files tell the real story** — if the pipeline says a task failed, read these files directly. In this case all three test reports said PASS; the failure was a pipeline orchestration false positive. Don't assume the code is wrong just because the pipeline marked it failed.
- **`05_bias_correction.py` helper pattern for heatmaps:** Build the layout kwargs dict, but keep all PLOTLY_THEME-conflicting keys out of the initial dict. Apply them as a second `update_layout()` call. This matches how the `_make_heatmap_fig` function *should* work (even though the pre-existing version has the bug).

## Task #52 — 2026-03-11 (Statistical RV Modeling page)

- **Empirical survival function pattern:** `np.searchsorted(sorted_vals, t_arr, side="right")` → `S(t) = 1 - idx/N`. Pre-sort the sample once, then wrap with `scipy.interpolate.interp1d(t_grid, S_grid, bounds_error=False, fill_value=(1.0, 0.0))` for a smooth callable. This is much faster than recomputing `np.mean(sample > t)` at each threshold.
- **`simulate_delta_rv_sample()` requires `f_bin=1.0` when generating a pure-binary distribution** — set `sigma_single=0.0` and `sigma_measure=0.0` in `SimulationConfig` to get clean orbital ΔRVs without measurement noise. The single-star component is modeled separately.
- **`@st.cache_data` on simulation functions requires ALL varying params as arguments** — every parameter that could change (including `weight_A` for Langer) must be an explicit function argument so Streamlit's hash-based cache invalidates correctly. Burying params in a dict or session_state bypasses caching.
- **Binomial error for fraction data:** `σ = sqrt(f*(1-f)/N) + ε` (add small ε ~1e-4 to avoid zero-division at f=0 or f=1). Pass to `curve_fit(sigma=sig_err, absolute_sigma=True)` for proper weighted least-squares.
- **Use `**{**PLOTLY_THEME, 'title': dict(text='...'), 'xaxis': {**PLOTLY_THEME.get('xaxis', {}), 'title': '...'}}` for layout** — single dict-merge call that correctly overrides nested keys without E018 collision. This is now the standard pattern across all app pages.
