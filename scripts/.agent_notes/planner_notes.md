# Planner Notes

Learnings about how to plan tasks for this project.

<!-- Notes will be auto-appended below this line -->

## Task #19 — 2026-03-03 (f_bin vs sigma and pi vs sigma heatmaps)

- **Always read existing helper functions before proposing new ones** — `_make_heatmap_fig` (lines 100–168 in `05_bias_correction.py`) already had a `dict(title=..., **PLOTLY_THEME)` conflict bug. The plan should have included a step to audit all pre-existing helper functions referenced as templates and flag any known-bad patterns from `COMMON_ERRORS.md`.
- **Include a "runtime conflict check" step in plans for Plotly pages** — when planning new `update_layout()` calls, explicitly list which `PLOTLY_THEME` keys overlap with any additional kwargs (`title`, `xaxis`, `yaxis`, `font`, `legend`). Require the implementer to either use a merge helper or set conflicting keys separately.
- **Marginalization axis math must be stated precisely in the plan** — the 3D array `ks_p` has shape `(n_sigma, n_fbin, n_pi)`. For f_bin vs sigma: `nansum(axis=2)` → shape `(n_sigma, n_fbin)`. For pi vs sigma: `nansum(axis=1)` → shape `(n_sigma, n_pi)`. Specify this explicitly to avoid transposition bugs.
- **Plan should specify when multi-sigma guard (`len(sigma_grid) > 1`) is needed** — new heatmaps that only make sense with a 3D result must be wrapped in this conditional; failure to include it causes an IndexError for legacy 2D results.

## Task #52 — 2026-03-11 (Statistical RV Modeling page)

- **Check `shared.py` for reusable helpers before planning new data-loading code** — `cached_load_observed_delta_rvs`, `settings_hash`, `COLOR_BINARY`, `COLOR_SINGLE`, and `PLOTLY_THEME` are all exported and should be reused. Plans should list which shared helpers to import rather than re-implementing.
- **When planning pages that combine simulation + fitting, specify the mathematical model precisely** — e.g., `f(t) = (1−f_bin)·S_single(t/σ) + f_bin·S_binary(t)` where S is the survival function. Ambiguity in the mixture formula leads to implementation bugs.
- **Plan two-stage fitting explicitly** — for curve_fit on noisy empirical data, the plan should specify: (1) initial fit on raw/unfiltered data for stable p0, (2) refined fit on filtered data with proper error weights. Skipping stage 1 often causes convergence failures.
- **Plan the UI state machine for expensive computations** — Streamlit pages need three states: (a) preview before run, (b) computation on button click, (c) display from session_state cache. The plan should describe all three states to avoid missing the preview or re-computation bugs.
