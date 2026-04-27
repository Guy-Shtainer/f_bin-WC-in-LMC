---
name: plot_preferences
description: Accumulated plot style preferences from user feedback — colors, themes, interactions. Auto-updated after any plot feedback.
type: feedback
---

## Themes
- **Plots page (06_plots.py):** White academic Plotly theme (`_ACADEMIC_THEME`). White bg, serif fonts (Times New Roman), black mirrored axes, no gridlines, outside ticks. Matches A&A/ApJ paper style.
- **Rest of app:** Use `PLOTLY_THEME` dict from `shared.py` — always `**PLOTLY_THEME` in `update_layout()`, never hardcode colors.
- **CRITICAL (E018):** Never pass `title`, `legend`, `xaxis`, `yaxis`, `font` as kwargs alongside theme spread — use dict literal override: `fig.update_layout(**{**THEME, 'title': dict(text='...')})`

## Colors
- Gold star markers for best-fit points (darker gold #DAA520 for readability on white)
- Observed data: solid lines in steel blue (#4A90D9)
- Simulated/model data: dashed lines in tomato red (#E25A53)
- Scoring method colors defined in `SCORING_METHODS` in `bc/helpers.py`

## Annotations & Overlays
- Annotations with key statistics: semi-transparent white boxes with dark text
- Contour lines on heatmaps (dark grey, dotted)
- Semi-transparent histogram overlays for distribution comparisons

## Interactive Behavior
- **CDF legend toggle must hide shadows:** When toggling a CDF line off via Plotly legend, its error shadow (fill band) must also disappear. Use `legendgroup` to link the line trace and its fill trace so they toggle together. Set `showlegend=False` on the fill trace.
  **Why:** Shadow without its line is confusing and clutters the plot.
  **How to apply:** Every CDF plot with error bands — assign matching `legendgroup` to line + fill, only show legend on the line trace.

## Data Presentation
- Tables over metric cards for tabular data — structured tables with grouped columns (MultiIndex by epoch). Metric cards OK for single summary values only.

## Bin-Sensitivity sub-tab (2026-04-20)
- **Plot #6 (bin-edge geometry) — STRONGLY APPROVED.** User feedback: "I really liked the first graph!" This is the horizontal strip-plot showing each scheme's bin edges stacked on the observed ΔRV rug, with threshold + max-observed vlines. Keep the stacked-row layout, the rug at top, and the scheme-family color coding. Default view for the Bin Sensitivity tab.
- **Bin-Sensitivity plots are A&A paper-ready by default** — all 6 plots use `_academic_fig()` from `app/plots/theme.py` (white bg, Times New Roman serif, black mirrored axes, no gridlines). User wants paper-ready style without per-figure toggles.
- **Plot #4 (marginal posteriors) — caption required.** Explains what the plot means, flags ε-floor artifacts from multi-modal curves. Caption text lives in `app/bc/bin_sensitivity.py` under the plot.
- **Plot #5 (bin diagnostics) — caption required.** Explains obs-vs-sim-height interpretation (within-bin = fit quality) vs quantile binning (across-bin equal heights = methodological choice, not cherry-picking).

## 2026-04-23 — 7th-strike A&A failures on Bin Sensitivity tab

Triggered by: Bin Sensitivity tab under Bias Correction showed white-on-white text (invisible CDF observed line, invisible diagnostic annotations) AND subplot inconsistency (first CDF panel had a frame, others didn't; 3 panels had horizontal gridlines, 3 didn't).

**Root cause of inconsistency:** `fig.update_xaxes(range=..., row=N)` without a `col=` argument applies to the ENTIRE row only (Plotly semantics). Other panels fell back to auto-range. This is how "random-looking" inconsistency shows up across subplots.

**Mandatory rules for every future plot handoff:**
1. `_ACADEMIC_THEME` only — never `PLOTLY_THEME` on a paper-ready plot.
2. Use the `_apply_aa_axes(fig)` helper (unscoped `update_xaxes`/`update_yaxes`) to force identical style across ALL subplots.
3. Never pass only `row=` or only `col=` to `update_xaxes`/`update_yaxes`. Either both, or neither (applies to all). Scoping by only one dimension is the main source of "some subplots look different" bugs.
4. Ban-list on white-bg plots: `'white'`, `'#FFFFFF'`, `'gold'`, `'#FFD700'`, `font_color` (dark-theme), anything grey ≤ #555555 for primary data. WCAG 4.5:1 required.
5. Observed ΔRV CDF color: `#2CA6A4` (teal). Simulated: `#E25A53`. Truth marker: `#DAA520`. Reference line: `#2E2E2E`. No exceptions.
6. Legend font size ≥ 12 for static A&A figures; ≥ 14 for subplot grids (≥3 subplots) where legend must be scannable.
7. Subplot titles risk collision with mirrored top frames — always add `yshift = 8-12` to subplot-title annotations.
8. Grep-before-handoff checklist: `grep -nE "'white'|'#FFFFFF'|'gold'|'#FFD700'|showgrid=True"` must return zero in any A&A figure module.

Any future white-on-white failure is a blocker, not a warning.

## 2026-04-23 — Readable text size rule (applies to every chart)

All text in charts must be large enough to read without zooming in.

**Minimums** (apply on top of `_ACADEMIC_THEME`):
- Axis tick labels: ≥ 12 pt
- Axis titles: ≥ 14 pt
- Subplot titles: ≥ 14 pt
- Legend text: ≥ 12 pt (≥ 14 pt on grids of ≥3 subplots)
- In-plot annotations / bar labels / tick labels on categorical axes: ≥ 12 pt
- Figure-level title: ≥ 16 pt

**Why:** user reported Bin Diagnostic tab text was unreadable. Scientific dashboards are viewed at normal browser zoom on a laptop screen; defaults from Plotly themes aimed at print are too small.

**How to apply:** after `fig.update_layout(**_ACADEMIC_THEME)` (or equivalent), set font-size overrides on `xaxis.tickfont.size`, `xaxis.title.font.size`, `yaxis.tickfont.size`, `yaxis.title.font.size`, `legend.font.size`, and on every `fig.add_annotation(..., font=dict(size=...))`. For subplot grids, loop `update_xaxes`/`update_yaxes` unscoped (no `row=`/`col=`) to set every subplot's tick font at once.

This rule applies to every plot in the app, not just Bin Sensitivity. The `plots` agent must enforce it on every future plot handoff.
