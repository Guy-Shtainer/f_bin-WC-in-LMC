# Implementer Notes

Learnings about implementation patterns and pitfalls in this project.

<!-- Notes will be auto-appended below this line -->

## Task #19 — 2026-03-03 (f_bin vs sigma and pi vs sigma heatmaps)

- **NEVER do `dict(title=..., **PLOTLY_THEME)` or `fig.update_layout(title=..., **PLOTLY_THEME)`.** `PLOTLY_THEME` (in `app/shared.py`) contains `title=dict(font=...)`, which collides and raises `TypeError: multiple values for keyword argument 'title'`. The correct pattern is: `fig.update_layout(**PLOTLY_THEME)` first, then override individual keys: `fig.update_layout(title=dict(text="My Title"))`.
- **`PLOTLY_THEME` keys to watch for collision:** `title`, `xaxis`, `yaxis`, `font`, `legend`, `plot_bgcolor`, `paper_bgcolor`. Never pass any of these as explicit kwargs in the same call that unpacks `**PLOTLY_THEME`.
- **py_compile passing ≠ runtime safe** — dict-unpacking conflicts are only caught at runtime when the conflicting line is actually executed. After implementing any Plotly layout change, mentally trace what keys would be in the merged dict.
- **The `.agent_work/{task_id}/test_report_N.md` files tell the real story** — if the pipeline says a task failed, read these files directly. In this case all three test reports said PASS; the failure was a pipeline orchestration false positive. Don't assume the code is wrong just because the pipeline marked it failed.
- **`05_bias_correction.py` helper pattern for heatmaps:** Build the layout kwargs dict, but keep all PLOTLY_THEME-conflicting keys out of the initial dict. Apply them as a second `update_layout()` call. This matches how the `_make_heatmap_fig` function *should* work (even though the pre-existing version has the bug).
