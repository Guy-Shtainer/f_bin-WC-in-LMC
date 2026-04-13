---
name: scientific-dashboard-design
description: Design guidance for scientific Streamlit+Plotly dashboards — academic themes, chart type selection, color palettes, layout patterns for spectroscopy and simulation data
user-invocable: false
---

# Scientific Data Dashboard Design Skill

## When to Apply

Use this skill for:
- Streamlit/Plotly scientific dashboard layout and styling
- Color palette selection for publication-quality plots
- Chart type selection for spectroscopic, time-series, and simulation data
- Data table design for complex multi-indexed results
- Interactive control panel layout

## Core Principles

### 1. Academic Aesthetic (Non-Negotiable)

**"Publication-ready from day one"** — Every plot should look acceptable in a peer-reviewed paper.

- White or near-white backgrounds (no dark mode for paper plots)
- Serif fonts (Times New Roman, Palatino)
- Black/dark gray axes with no gridlines (or subtle dotted)
- Ticks on outside; axis labels perpendicular to axes
- Perceptually uniform colormaps only
- Font sizes: 11-14pt labels, 9-10pt annotations

### 2. Chart Type Selection

| Data Type | Best Chart | Why | Avoid |
|-----------|-----------|-----|-------|
| Spectral flux vs wavelength | Line chart | Shows continuity; emphasis on features | Bar, Pie |
| RV measurements across epochs | Scatter + error bars | Uncertainty critical | Line connecting points |
| Distribution comparison (obs vs sim) | Histogram + CDF overlay | Semi-transparent histogram | Box plot alone |
| 2D grid (f_bin vs π) | Heatmap with contours | Both dimensions continuous | Separate subplots |
| Period distribution (Case A/B) | Histogram + log-normal overlay | Right-skewed; two-peak | Linear scale |
| Many numeric columns by star/line | Pandas table (MultiIndex) | Tabular data; grouping | Metric card grid |
| Likelihood surface | 3D surface or contour | Show optimization landscape | 2D scatter alone |
| Parameter comparison | Small multiples (subplots) | Compare side-by-side | Single aggregated view |

### 3. Color Palette

**Primary (publication-grade):**
- Observed data: **#4A90D9** (steel blue)
- Model/simulated: **#E25A53** (tomato red)
- Best-fit marker: **#DAA520** (darker gold)
- Background: **#FFFFFF** (white)
- Axes/text: **#000000** (black)
- Grid (if used): **#CCCCCC** (light gray, dotted)

**Categorical (up to 5 categories):**
- Use colorblind-safe: Okabe-Ito palette or Viridis
- Avoid red/green combinations
- Test accessibility

**Heatmaps:**
- Use: `viridis`, `cividis` (print-friendly B&W conversion)
- Avoid: Jet, Rainbow, Hot (perceptually non-uniform)

### 4. Table Design

- **MultiIndex columns** for grouped measurements (RV, Error, SNR per epoch)
- Right-align numbers; left-align text
- Include units in column headers
- Sort by primary science column (e.g., ΔRV descending)
- Alternating row shading (#F8F8F8) for readability

### 5. Layout Patterns

**Two-column (controls + results):**
```python
col_left, col_right = st.columns([0.4, 0.6], gap='medium')
with col_left:
    st.subheader('Settings')
    # controls...
with col_right:
    st.subheader('Results')
    # plot...
```

**Compact parameter controls:** Always use `st.columns()` to place related controls side-by-side.

### 6. Plotly Theme Application

```python
# ✓ Correct override:
fig.update_layout(**{**_ACADEMIC_THEME, 'title': dict(text='...')})

# ✗ WRONG (TypeError: multiple values):
fig.update_layout(**_ACADEMIC_THEME, title=...)
```

### 7. Every Plot Must Have

- Axis labels with units ("RV (km/s)", "Wavelength (Å)")
- Figure caption below (`st.caption(...)`)
- Legend if >1 dataset
- Stat box for results plots (p-value, fit params, sample size)
- Error bars where uncertainty matters

### 8. Pre-Delivery Checklist

- [ ] Academic theme applied (white bg, serif, mirrored axes, no gridlines)
- [ ] Color palette matches project standard or is colorblind-safe
- [ ] Axis labels include units
- [ ] Legend present for multi-dataset plots
- [ ] Error bars shown where uncertainty is critical
- [ ] `st.caption(...)` below every plot
- [ ] Tables use MultiIndex grouping
- [ ] Hover tooltips include units and formatting
- [ ] No emojis in scientific text
- [ ] Numerical formatting consistent (3 sig figs, aligned decimals)
- [ ] Chart type matches data type
