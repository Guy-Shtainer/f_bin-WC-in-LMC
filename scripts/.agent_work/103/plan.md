# Task #103 — RV Modeling Page Improvements (follow-up on #52)

## Overview
10 improvements to the RV Modeling page (12_rv_modeling.py), with minor changes to shared.py and app.py.

## Changes

### 1. Navigation: Move RV Modeling under NRES (shared.py)
- **File:** `app/shared.py`, line 613
- Move `st.page_link('pages/12_rv_modeling.py', label='📈 RV Modeling')` from after To-Do to right after NRES (line 607)

### 2. Dashboard: Add RV Modeling step (unchecked) (app.py)
- **File:** `app/app.py`, workflow_items list (~line 448)
- Add `('RV Modeling (threshold fitting)', False)` to the workflow status checklist

### 3. PLOTLY_THEME compliance (12_rv_modeling.py)
- Already mostly correct — all `update_layout` calls use `{**PLOTLY_THEME, ...}` pattern
- Verify new plots also follow this pattern

### 4. Residuals directly under fit plot (12_rv_modeling.py)
- Restructure panels: Fit → Residuals → Weighted PDFs → Parameter Playground → Histogram → Parameters
- Use `plotly.subplots.make_subplots` with 2 rows (3:1 height ratio) to combine fit + residuals in ONE figure (like notebook's gridspec)

### 5. Add chi_red score to fit plot (12_rv_modeling.py)
- Add annotation with χ²_red directly on the fit plot (annotation box in upper-left corner)

### 6. Fix residuals: data vs fit only (12_rv_modeling.py)
- Filter to change points only: `diffs = np.diff(f_obs, prepend=-999); mask = diffs != 0`
- Plot observed data at change points only (not all 301 threshold values)
- Residuals only at those points

### 7. Parameter playground (12_rv_modeling.py)
- New section with sliders for f_bin and σ_single
- Real-time model curve overlay on data (no re-simulation needed)
- Uses the existing binary_surv_fn and std_surv_fn from the fit

### 8. Binary ΔRV histogram (12_rv_modeling.py)
- After simulation, draw histogram of simulated binary ΔRVs
- Also classify observed stars as single/binary based on optimal threshold
- Show centered RVs for each population with model Gaussian overlay
- Following notebook Figure 2 pattern

### 9. Dsilva/Langer approach switching (12_rv_modeling.py)
- Already exists in sidebar (period_model selectbox)
- Ensure all orbital parameter presets update correctly when switching

### 10. Learn from Thesis work.ipynb
- Key patterns already incorporated:
  - Change-point filtering for observed data
  - Two-stage fitting
  - Chi_red annotation
  - Population histograms
  - Gridspec-style fit+residuals layout

## Panel Structure (new order)
1. **Combined Fit + Residuals** (subplots, 3:1 height ratio)
2. **Weighted PDF Components**
3. **Parameter Playground** (interactive sliders)
4. **Binary ΔRV Histogram** (simulated distribution)
5. **Best-Fit Parameters Table**
6. **Simulation Details** (expander, unchanged)

## Files Modified
- `app/shared.py` — navigation order
- `app/app.py` — workflow status
- `app/pages/12_rv_modeling.py` — main rewrite
