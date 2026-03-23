# Plot Style Guide

## Academic Theme (Plots page — 06_plots.py)
- White background, serif fonts (Times New Roman), black mirrored axes, outside ticks, no gridlines
- Uses `_ACADEMIC_THEME` / `_academic_fig()` / `_show()` in 06_plots.py
- Matches A&A / ApJ paper style. Interactive (zoom/pan/hover via Plotly)

## App Theme (rest of webapp)
- Centralized via `PLOTLY_THEME` dict in `app/shared.py`
- ALWAYS use `**PLOTLY_THEME` in `update_layout()` calls — never hardcode plot colors
- **CRITICAL (E018)**: `PLOTLY_THEME` contains `title`, `legend`, `xaxis`, `yaxis`, `font`. NEVER use these as keyword args alongside spread. Use: `fig.update_layout(**{**_ACADEMIC_THEME, 'title': dict(text='...')})`

## Color Assignments
- Binary stars / simulated data: tomato red (#E25A53), dashed lines
- Single stars / observed data: steel blue (#4A90D9), solid lines
- Best-fit markers: dark gold (#DAA520, star markers)
- Annotations: semi-transparent white boxes with dark text
- Contour lines on heatmaps: dark grey, dotted
- Epoch colors: HSV-spaced for spectra

## Per-Plot-Type
- Spectra: thin lines (width 1-1.5)
- Bar charts: 0.7 width, count text above
- Error bars: cap size 3-4px
- Corner plots: histograms on diagonal, scatter below, error bars on scatter, dashed threshold lines (gold)
- Heatmaps: shared `make_heatmap_fig()` utility
- Histograms: semi-transparent overlays for distribution comparisons
- Always add `st.caption(...)` below each plot

## Feedback Rule
After ANY plot feedback from user → update `memory/plot_preferences.md`

## Data Loading (spectra)
- FITS wavelengths in nm → multiply by 10.0 for Å display
- NRES exception: already in Å
- .npz `wavelengths` key also in nm
- Unified loader: `_load_spectrum()` in 06_plots.py (cleaned → normalized → raw FITS fallback)
