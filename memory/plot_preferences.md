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
