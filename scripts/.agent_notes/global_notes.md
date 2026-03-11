# Global Agent Notes

These notes are prepended to ALL agent roles. Add general project learnings here.

<!-- Notes will be auto-appended below this line -->

## Task #19 — 2026-03-03 (f_bin vs sigma and pi vs sigma heatmaps)

- **`PLOTLY_THEME` contains a `title` key** — never use `dict(title=..., **PLOTLY_THEME)` or `fig.update_layout(title=..., **PLOTLY_THEME)`. Python raises `TypeError: multiple values for keyword argument 'title'`. Instead: set title separately after the layout call, e.g. `fig.update_layout(**PLOTLY_THEME); fig.update_layout(title=...)`.
- **Syntax tests (py_compile) do NOT catch runtime TypeErrors** — the bias correction page compiled cleanly but crashes at runtime when Plotly tries to merge conflicting `title=` kwargs. Always also check for dict-unpacking conflicts involving `PLOTLY_THEME` keys (`title`, `xaxis`, `yaxis`, `font`, `legend`).
- **Pipeline verdict parsing may produce false positives** — the overnight agent marked the task `test_failed` even though all three test reports returned PASS. When reviewing a failed task, always read the actual `test_report_N.md` files in `.agent_work/` before assuming the code is broken.
- **Copying pre-existing code patterns can silently propagate bugs** — Task #19 faithfully mirrored `_make_heatmap_fig` (pre-existing), which already had the `title` dict conflict. Before using an existing function as a template, verify it is itself bug-free.

## Task #52 — 2026-03-11 (Statistical RV Modeling page)

- **`shared.py` exports are the canonical data-loading interface** — use `cached_load_observed_delta_rvs(settings_hash(...))` for observed ΔRVs rather than re-implementing data loading. Always check `shared.py` for existing cached helpers before writing new ones.
- **`wr_bias_simulation.py` exposes `simulate_delta_rv_sample()`** — this function generates empirical binary ΔRV distributions from Monte-Carlo orbital simulations. It accepts `f_bin`, `pi`, `SimulationConfig`, and `BinaryParameterConfig`, making it reusable for any page that needs simulated binary ΔRVs (not just bias correction).
- **PLOTLY_THEME dict-merge pattern is settled** — use `fig.update_layout(**{**PLOTLY_THEME, 'title': dict(text='...'), 'xaxis': {**PLOTLY_THEME.get('xaxis', {}), 'title': '...'}})`. This avoids E018 collisions while keeping a single `update_layout` call.
- **Two-stage `curve_fit` improves convergence** — fit raw (unfiltered) data first for stable initial guesses, then re-fit significance-filtered data with binomial error weights (`sigma=sig_err, absolute_sigma=True`). This pattern is robust for noisy fraction-vs-threshold curves.
- **Session state for expensive results** — store computation outputs in `st.session_state["key"]` so they survive Streamlit reruns without re-computation. Check `if "key" not in st.session_state` to show a preview state before the user clicks "Run".
