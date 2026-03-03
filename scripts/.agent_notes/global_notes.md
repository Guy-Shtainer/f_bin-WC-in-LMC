# Global Agent Notes

These notes are prepended to ALL agent roles. Add general project learnings here.

<!-- Notes will be auto-appended below this line -->

## Task #19 — 2026-03-03 (f_bin vs sigma and pi vs sigma heatmaps)

- **`PLOTLY_THEME` contains a `title` key** — never use `dict(title=..., **PLOTLY_THEME)` or `fig.update_layout(title=..., **PLOTLY_THEME)`. Python raises `TypeError: multiple values for keyword argument 'title'`. Instead: set title separately after the layout call, e.g. `fig.update_layout(**PLOTLY_THEME); fig.update_layout(title=...)`.
- **Syntax tests (py_compile) do NOT catch runtime TypeErrors** — the bias correction page compiled cleanly but crashes at runtime when Plotly tries to merge conflicting `title=` kwargs. Always also check for dict-unpacking conflicts involving `PLOTLY_THEME` keys (`title`, `xaxis`, `yaxis`, `font`, `legend`).
- **Pipeline verdict parsing may produce false positives** — the overnight agent marked the task `test_failed` even though all three test reports returned PASS. When reviewing a failed task, always read the actual `test_report_N.md` files in `.agent_work/` before assuming the code is broken.
- **Copying pre-existing code patterns can silently propagate bugs** — Task #19 faithfully mirrored `_make_heatmap_fig` (pre-existing), which already had the `title` dict conflict. Before using an existing function as a template, verify it is itself bug-free.
