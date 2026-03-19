# Implementation Plan: Add Missing Notebook Plots to Webapp Plots Page

## Context

The Thesis work.ipynb and Plots.ipynb notebooks contain ~25 publication-quality plots.
The webapp's Plots page (`app/plots/`) has ~15 of these. This plan adds the missing ones
and restructures the Plots page to stay under the 800-line file limit.

`xshooter.py` is already at **825 lines** (over limit) and must be split before adding anything.

---

## Pre-Phase: Discovery (2 rounds — MANDATORY before any coding)

Before implementing ANYTHING, you MUST do 2 full rounds of independent discovery to find
plots/features missing from the webapp that this plan may have overlooked.

### Discovery Round 1:
1. **Read the entire `Thesis work.ipynb` notebook** — go cell by cell. For EVERY plot or
   visualization, check if the webapp has an equivalent. Don't just match by name — look at
   the actual data shown, axes, interactivity, and adjustable parameters.
2. **Read `Plots.ipynb`** — same process. This has publication-quality figures.
3. **Read ALL webapp plot files**: `app/plots/*.py`, `app/bc/sim_plots.py`, and any other
   pages with plots (`app/pages/02_spectrum.py`, `app/pages/12_rv_modeling.py`, etc.)
4. **Write a discovery report** listing:
   - Everything I (the original planner) identified (the 9 items in the Gap Analysis below)
   - Any NEW gaps you found that I missed
   - Any adjustability differences (notebook has controls the webapp doesn't)
   - Any data processing steps in the notebook that feed plots but aren't in the webapp

### Discovery Round 2:
1. **Re-read the notebooks with fresh eyes**, focusing on:
   - Widget controls / `ipywidgets` that provide interactivity (sliders, dropdowns, toggles)
   - Data transformations that happen between cells (aggregation, filtering, sorting)
   - Subplot layouts and multi-panel figures that might be collapsed into single panels in the webapp
   - Color schemes, annotations, text boxes, legends that are more detailed in notebooks
2. **Cross-reference** your Round 1 findings with the Gap Analysis table below
3. **Update the Gap Analysis table** in this plan file with any new items you found
4. **Only after both discovery rounds** proceed to Step 0 and the implementation phases

If you find additional missing plots, add them to the implementation plan (new Phase 2 entries)
with the same level of detail as the existing ones. Assign them to appropriate tab files.

---

## Step 0: Skills Reference (pre-installed)

Three skill sets have been pre-installed to `.claude/skills/` before this task was created:

1. **Streamlit Agent Skills** (`developing-with-streamlit/`) — official Streamlit team skills
   covering dashboard layouts, themes, dataframes, performance, custom components (16 sub-skills)
2. **UI/UX Pro Max** (`ui-ux-pro-max/`) — 50+ UI styles, 161 color palettes, 57 font pairings,
   25 chart types, 99 UX guidelines
3. **Scientific Dashboard Design** (`scientific-dashboard-design/`) — custom skill for academic
   Plotly charts, color palettes, chart type selection, layout patterns

Read these skills during Discovery Round 2 and reference their patterns when building new tabs.
Do NOT re-install — they are already available.

---

## Gap Analysis: Notebook vs Webapp

| # | Plot | Notebook | Webapp | Status |
|---|------|----------|--------|--------|
| 1 | ΔRV vs Line Wavelength scatter (per-star, log-Y) | Cell 58 | -- | **MISSING** |
| 2 | f_bin vs Threshold with piecewise 2-segment fit + elbow + residuals | Plots.ipynb G2 | Has curve, NO fit/elbow/residuals | **PARTIAL** |
| 3 | Equivalent Thresholds Across Lines | Plots.ipynb G3 | -- | **MISSING** |
| 4 | Agreement Ranking (correlation-weighted line scores) | Plots.ipynb G5 | -- | **MISSING** |
| 5 | Interactive Dashboard with epoch strips + sorting | Cells 63-72 | Simple bar chart only | **PARTIAL** |
| 6 | SNR Requirements on Template Spectrum | Cell 93 | -- | **MISSING** |
| 7 | f_bin(t) Survival Function (P(ΔRV > t) curves) | Cell 84 | -- | **MISSING** |
| 8 | PDF Intersection / Threshold Optimization | Cell 86 | -- | **MISSING** |
| 9 | Normalized Flux with Anchor Points | Cell 34 | Has spectra, NO anchors | **PARTIAL** |
| 10 | Normalized spectra (all epochs) | Cell 34 | Yes | OK |
| 11 | ΔRV bar chart sorted | Cells 60, G1 | Yes | OK |
| 12 | f_bin per emission line | Plots.ipynb G6 | Yes | OK |
| 13 | Confidence grading (Gold/Silver/Bronze) | Plots.ipynb G7 | Yes | OK |
| 14 | Clean vs Contaminated comparison | Plots.ipynb G8 | Yes | OK |
| 15 | RV vs Epoch per star | Cell 77 | Yes | OK |
| 16 | Corner plot (ΔRV correlation matrix) | Plots.ipynb G4 | Yes | OK |
| 17 | Raw spectra / 2D image / error spectrum | Various | Yes | OK |
| 18 | Grid Results heatmap + CDF | bias_simulation.ipynb | Yes | OK |

**Missing adjustability in existing plots:**
- Bar chart: no sorting controls (notebook has sort-by-any-line + asc/desc)
- f_bin curve: no "filter changes only" toggle, no "exclude contaminated" toggle
- No per-epoch RV heatmap/strip visualization

---

## Phase 1: Split `xshooter.py` (prerequisite)

Split the 825-line monolith into sub-tab modules:

| File | Content | Est. lines |
|------|---------|------------|
| `xshooter.py` | Thin orchestrator: create tabs, call renderers | ~50 |
| `tab_spectra.py` | Spectra sub-tab (lines 41-333) | ~300 |
| `tab_rv_analysis.py` | Existing RV plots + new #4 (agreement) | ~500 |
| `tab_emission_lines.py` | Emission Lines sub-tab + new #1 (scatter) | ~200 |
| `tab_ccf.py` | CCF Outputs sub-tab | ~50 |
| `tab_grid.py` | Grid Results sub-tab | ~100 |

New files for new sub-tabs:

| File | Content | Est. lines |
|------|---------|------------|
| `tab_threshold.py` | **NEW** sub-tab: plots #2 (piecewise), #3 (equiv), #7 (survival), #8 (PDF) | ~500 |
| `tab_dashboard.py` | **NEW** sub-tab: plot #5 (interactive epoch-strip dashboard) | ~400 |
| `tab_diagnostics.py` | **NEW** sub-tab: plots #6 (SNR), #9 (anchor points) | ~250 |
| `compute.py` | Pure computation functions (no Streamlit) | ~300 |

Sub-tab order after restructure:
```
Spectra | RV Analysis | Emission Lines | Threshold Analysis | Dashboard | Diagnostics | CCF Outputs | Grid Results
```

---

## Phase 2: New Plots (implementation order)

### 2a. Plot #1 — ΔRV vs Line Wavelength Scatter → `tab_emission_lines.py`

- X: central wavelength per line (Å), Y: ΔRV per star (log scale)
- Points colored by star (Plotly discrete colors)
- Binary fraction % annotated above each line column
- Configurable threshold line
- **Data:** `cached_load_drv_analysis()` + `_get_emission_lines()` (both exist)

### 2b. Plot #4 — Agreement Ranking → `tab_rv_analysis.py`

- Pairwise Pearson r between `dRV | {line}` columns, weighted by n_pairs/25
- Bar chart sorted by agreement score
- Optional overlay: best correlation partner per line
- **New function in `compute.py`:** `compute_agreement_scores(df, ordered_lines)`

### 2c. Plot #2 — Enhanced f_bin vs Threshold → `tab_threshold.py`

- 2-segment piecewise linear fit with elbow detection
- Residual panel below (chi²/DoF)
- Wilson score confidence intervals (use existing `_wilson_score_interval` from `data.py`)
- Toggles: "Filter changes only", "Exclude contaminated"
- **New function in `compute.py`:** `fit_two_segment_linear(x, y, y_err)` → elbow, slopes, chi²
- **Reuse:** `_is_significant_binary()` from `analysis.py`, `_wilson_score_interval()` from `data.py`

### 2d. Plot #3 — Equivalent Thresholds → `tab_threshold.py`

- For each line, find threshold t* where f_bin(t*) = f_bin(CIV, 45.5)
- Bar chart: X = line name, Y = equivalent threshold (km/s)
- **New function in `compute.py`:** `find_equiv_thresholds(frac_data, ref_line, ref_threshold)`

### 2e. Plot #7 — Survival Function → `tab_threshold.py`

- P(ΔRV > t) for single vs binary populations (Gaussian noise model)
- Mixed curve: f_obs(t) = (1-f)·P_s(t) + f·P_b(t)
- Configurable σ_single, σ_binary, f_bin, n_epochs
- **New in `compute.py`:** `compute_survival_curve(thresholds, sigma, n_epochs)` using numerical integration
- Cache with `@st.cache_data` (CPU-intensive first run)

### 2f. Plot #8 — PDF Intersection → `tab_threshold.py`

- Numerical derivative of survival → PDFs
- Weighted PDFs: (1-f)·pdf_single, f·pdf_binary
- Shaded region where binary dominates
- Optimal threshold at intersection
- Recovery curve: f_rec = (f_obs - S_single) / (S_binary - S_single)
- Depends on Plot #7

### 2g. Plot #5 — Interactive Dashboard → `tab_dashboard.py`

- DataFrame: rows = stars, columns = emission lines, cells = ΔRV (colored)
- Per-epoch RV heatmap alongside: X = epoch, Y = star, Z = RV (diverging colorscale)
- Sort controls: selectbox for sort column, radio asc/desc
- Toggle: gradient coloring vs binary red/blue
- **Data:** `rv_epoch_cache` from `cached_load_drv_analysis()`
- **Plotly approach:** `go.Heatmap` for epoch strips, `st.dataframe` with Styler for table

### 2h. Plot #6 — SNR Requirements → `tab_diagnostics.py`

- Template spectrum with shaded emission line regions
- Annotations: "SNR ≥ X for σ(RV) < 3 km/s"
- Requires pre-computed SNR vs σ(RV) data → graceful fallback if unavailable

### 2i. Plot #9 — Anchor Points on Normalized Flux → `tab_diagnostics.py`

- Raw + normalized flux overlaid
- Vertical lines at normalization anchor wavelengths
- **Data:** `_load_spectrum()` + `_load_raw_spec()` (both exist)

---

## Phase 3: Enhanced Adjustability for Existing Plots

Add to existing RV Analysis plots (in `tab_rv_analysis.py`):

1. **Bar chart sorting:** selectbox for sort column (any line), radio asc/desc
2. **f_bin curve toggles:** "Filter changes only" checkbox, embedded in threshold tab

---

## Key Files to Modify/Create

**Modify:**
- `app/plots/xshooter.py` — gut to thin orchestrator (~50 lines)
- `app/plots/analysis.py` — no changes needed
- `app/plots/data.py` — may add template spectrum loader

**Create:**
- `app/plots/tab_spectra.py` — extracted from xshooter.py
- `app/plots/tab_rv_analysis.py` — extracted + agreement ranking
- `app/plots/tab_emission_lines.py` — extracted + wavelength scatter
- `app/plots/tab_ccf.py` — extracted
- `app/plots/tab_grid.py` — extracted
- `app/plots/tab_threshold.py` — NEW: piecewise fit, equiv thresholds, survival, PDF
- `app/plots/tab_dashboard.py` — NEW: interactive epoch-strip dashboard
- `app/plots/tab_diagnostics.py` — NEW: SNR requirements, anchor points
- `app/plots/compute.py` — NEW: pure computation functions

**Reusable existing utilities:**
- `_academic_fig()`, `_show()`, `_epoch_colors()`, `_add_emission_bands()` from `app/plots/theme.py`
- `cached_load_drv_analysis()`, `_is_significant_binary()` from `app/plots/analysis.py`
- `_get_emission_lines()`, `_wilson_score_interval()` from `app/plots/data.py`
- `COLOR_BINARY`, `COLOR_SINGLE`, `make_heatmap_fig` from `app/shared.py`

---

## Implementation Order

1. **Split xshooter.py** → 5 sub-tab files + thin orchestrator
2. **Verify** existing functionality works identically (`python -m py_compile` + integration test)
3. **Create `compute.py`** with agreement scores, piecewise fit, equiv thresholds, survival functions
4. **Add plots** in order: #1 → #4 → #2 → #3 → #7 → #8 → #5 → #6 → #9
5. **Add sorting controls** to bar chart
6. **Test** each addition: `test_bc_imports.py` + `py_compile` + manual webapp check

---

## Verification (per phase)

After each phase:
1. `conda run -n guyenv python error-check-workspace/test_bc_imports.py`
2. `conda run -n guyenv python -m py_compile app/plots/{new_file}.py`
3. Verify all existing plots still work (no regression)
4. Check `wc -l` on all new files — none should exceed 800
5. Scan all modified files against `COMMON_ERRORS.md` patterns

---

## MANDATORY: 3-Round Iterative Improvement Protocol

After completing ALL phases above, you MUST execute 3 full rounds of review-and-improve.
Each round is a complete pass over everything you built. Do NOT skip any round.

### Round 1: Functional Review
1. **Re-read every new file** you created (`tab_*.py`, `compute.py`, `tab_dashboard.py`, `tab_threshold.py`, `tab_diagnostics.py`)
2. **Compare each plot** to its notebook source (read the notebook cells listed in the Gap Analysis table)
3. For each plot, verify:
   - Does it show the SAME data as the notebook version?
   - Does it have ALL the adjustable parameters the notebook has?
   - Are colors, labels, axes correct?
   - Does it use `_academic_fig()` + `_show()` from `theme.py`?
4. **Fix any discrepancies** found
5. **Run full error check:**
   ```bash
   conda run -n guyenv python error-check-workspace/test_bc_imports.py
   conda run -n guyenv python -m py_compile app/plots/tab_spectra.py
   conda run -n guyenv python -m py_compile app/plots/tab_rv_analysis.py
   conda run -n guyenv python -m py_compile app/plots/tab_emission_lines.py
   conda run -n guyenv python -m py_compile app/plots/tab_ccf.py
   conda run -n guyenv python -m py_compile app/plots/tab_grid.py
   conda run -n guyenv python -m py_compile app/plots/tab_threshold.py
   conda run -n guyenv python -m py_compile app/plots/tab_dashboard.py
   conda run -n guyenv python -m py_compile app/plots/tab_diagnostics.py
   conda run -n guyenv python -m py_compile app/plots/compute.py
   conda run -n guyenv python -m py_compile app/plots/xshooter.py
   conda run -n guyenv python -m py_compile app/plots/page.py
   ```
6. **Check file sizes:** `wc -l app/plots/*.py` — NONE over 800 lines
7. **Log what you fixed** in this round

### Round 2: Quality & Design Review
1. **Read the Streamlit Agent Skills** in `.claude/skills/developing-with-streamlit/`
2. **Read the Scientific Dashboard Design skill** in `.claude/skills/scientific-dashboard-design/`
3. **Review each tab's UI layout** against Streamlit best practices:
   - Are controls in compact `st.columns()` layouts? (user preference)
   - Are progress bars shown for >5s computations?
   - Do all plots have `st.caption(...)` below them?
   - Are Plotly hover texts informative?
   - Is the academic theme applied consistently?
4. **Check for COMMON_ERRORS.md patterns** (E001-E023) in ALL new files:
   ```bash
   conda run -n guyenv python -c "
   import re, glob
   patterns = [
       (r'np\.trapz\b', 'E001: use np.trapezoid'),
       (r'\.applymap\b', 'E017: use .map()'),
       (r'if\s+\w+\s*:', 'E018: check numpy truth value'),
       (r'PLOTLY_THEME.*title.*=', 'E018: dict spread conflict'),
   ]
   for f in glob.glob('app/plots/tab_*.py') + glob.glob('app/plots/compute.py'):
       txt = open(f).read()
       for pat, msg in patterns:
           for m in re.finditer(pat, txt):
               print(f'{f}:{msg} at pos {m.start()}')
   "
   ```
5. **Fix any issues** found
6. **Re-run full error check** (same as Round 1 step 5)
7. **Log what you fixed** in this round

### Round 3: Final Verification & Polish
1. **Import every new module** to catch missing imports:
   ```bash
   conda run -n guyenv python -c "
   import sys; sys.path.insert(0, 'app')
   from plots.tab_spectra import render_spectra_subtab
   from plots.tab_rv_analysis import render_rv_analysis_subtab
   from plots.tab_emission_lines import render_emission_lines_subtab
   from plots.tab_ccf import render_ccf_subtab
   from plots.tab_grid import render_grid_subtab
   from plots.tab_threshold import render_threshold_subtab
   from plots.tab_dashboard import render_dashboard_subtab
   from plots.tab_diagnostics import render_diagnostics_subtab
   from plots.compute import compute_agreement_scores, fit_two_segment_linear, find_equiv_thresholds, compute_survival_curve
   from plots.xshooter import render_xshooter_tab
   print('ALL IMPORTS OK')
   "
   ```
2. **Call every render function** with mock data to catch runtime errors:
   ```bash
   conda run -n guyenv python -c "
   import sys; sys.path.insert(0, 'app')
   import streamlit as st
   from plots.xshooter import render_xshooter_tab
   from shared import get_settings_manager
   settings = get_settings_manager().load()
   sm = get_settings_manager()
   try:
       render_xshooter_tab(settings, sm)
       print('RENDER OK — no exceptions')
   except Exception as e:
       print(f'RENDER FAILED: {e}')
       raise
   "
   ```
3. **Final file size check:** `wc -l app/plots/*.py`
4. **Diff check** — verify `xshooter.py` is now ~50 lines (thin orchestrator):
   ```bash
   wc -l app/plots/xshooter.py  # should be ~50, not 825
   ```
5. **Verify the sub-tab order** in the new `xshooter.py`:
   ```
   Spectra | RV Analysis | Emission Lines | Threshold Analysis | Dashboard | Diagnostics | CCF Outputs | Grid Results
   ```
6. **Commit all changes** with descriptive message
7. **Update GIT_LOG.md**
8. **Set TODO #150 status to `to-test`**

---

## MANDATORY: Error Check Protocol (3 passes)

Run this FULL error check sequence 3 separate times (once after each improvement round).
Each pass must complete with ZERO errors before proceeding.

### Error Check Pass (run 3 times):
```bash
# 1. Delete all .pyc caches
find app/plots/ -name '__pycache__' -exec rm -rf {} + 2>/dev/null; true

# 2. py_compile every new file
for f in app/plots/tab_*.py app/plots/compute.py app/plots/xshooter.py app/plots/page.py; do
    echo "Checking $f..."
    conda run -n guyenv python -m py_compile "$f" && echo "  OK" || echo "  FAILED"
done

# 3. Integration test
conda run -n guyenv python error-check-workspace/test_bc_imports.py

# 4. Import test
conda run -n guyenv python -c "
import sys; sys.path.insert(0, 'app')
from plots.xshooter import render_xshooter_tab
from plots.page import render_plots_page
print('PASS')
"

# 5. COMMON_ERRORS scan
conda run -n guyenv python -c "
import subprocess
result = subprocess.run(['grep', '-rn', '-E',
    'np\.trapz|\.applymap|asyncio\.sleep|from app\.shared',
    'app/plots/'], capture_output=True, text=True)
if result.stdout.strip():
    print('COMMON ERRORS FOUND:')
    print(result.stdout)
    exit(1)
else:
    print('No common errors found')
"

# 6. File size check
echo "=== File sizes ==="
wc -l app/plots/*.py
echo "Any file over 800 lines is a FAILURE"
```

If ANY check fails in a pass, fix the issue and restart that pass from step 1.
All 3 passes must complete cleanly.
