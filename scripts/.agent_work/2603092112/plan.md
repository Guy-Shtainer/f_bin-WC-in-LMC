# Plan: Rebuild Plots Page (06_plots.py) — X-Shooter & NRES Tabs

## Summary

Rewrite `app/pages/06_plots.py` from scratch to:
1. Fix all E018 (PLOTLY_THEME collision) bugs and hardcoded dark-theme colors in the current page.
2. Add two top-level tabs: **X-Shooter** and **NRES**.
3. Port all plots from `Plots.ipynb` (76 cells) and all plottable methods from `StarClass.py` and `NRESClass.py` to Plotly-based interactive charts.
4. Verify no other webapp pages are broken after the change.

### Related TODO Items
- **#21** (high, open): "Fix broken Plots page — implement from notebook"
- **#27** (medium, open): "Add tabs to Plots page — organize into RVs, Spectrum, RV Analysis, Emission Lines Comparison. Add cleaned/contaminated toggle"
- **#28** (medium, open): "Toggle cleaned/contaminated stars in all plots"
- **#26** (high, open): "Fix spectrum axis units to Angstrom"

---

## Current State & Bugs

### `app/pages/06_plots.py` (228 lines)
- **E018 bug on lines 76-80, 118-122**: `title=..., **PLOTLY_THEME` → `TypeError: got multiple values for keyword argument 'title'`. `PLOTLY_THEME` already contains `title`, `xaxis`, `yaxis`, `font`, `legend`.
- **Hardcoded dark colors on lines 140-141, 203-204, 216-217**: `plot_bgcolor='#1a1a2e'` etc. instead of using `PLOTLY_THEME`.
- **Deprecated Streamlit API on line 168**: `use_column_width=True` → should be `use_container_width=True`.
- **No NRES support at all**: only X-Shooter stars from `specs.star_names`.
- **Very few plots**: only 5 plots total (normalized spectra, RV vs epoch, ΔRV bar, CCF images, one heatmap).
- **Missing**: most of the 8+ ΔRV analysis plots from notebook, emission line comparisons, error spectra, 2D images, epoch consistency checks, NRES spectra, NRES SNR, etc.

---

## Proposed Structure

```
06_plots.py
├── Top-level tabs: ["X-Shooter", "NRES"]
│
├── X-Shooter tab
│   ├── Sub-tabs: ["Spectra", "RV Analysis", "Emission Lines", "CCF Outputs", "Grid Results"]
│   │
│   ├── Spectra sub-tab
│   │   ├── Star/band/epoch selectors
│   │   ├── Normalized spectra (all epochs overlaid) — from notebook cells 8,10 & StarClass.plot_normalized_spectra
│   │   ├── Raw spectra viewer with toggles — from StarClass.plot_spectra:
│   │   │   ├── Toggle: Normalize (build continuum from anchor wavelengths, divide)
│   │   │   ├── Toggle: Rest frame (apply RV from 'C IV 5808-5812' to legend)
│   │   │   ├── Toggle: Log scale (mask flux ≤ 0, set yaxis_type='log')
│   │   │   ├── Toggle: Show continuum overlay (load 'interpolated_flux' property)
│   │   │   └── Toggle: Show RV emission lines (highlight regions from ccf_settings JSON)
│   │   ├── Error spectra viewer — from StarClass.plot_spectra_errors:
│   │   │   └── Load observation FITS → data['ERR'][0] → plot error vs wavelength
│   │   ├── 2D spectral image — from StarClass.plot_2D_image:
│   │   │   ├── Load via star.load_2D_observation(epoch, band) → .primary_data (2D array)
│   │   │   ├── Display as go.Heatmap with ValMin/ValMax sliders
│   │   │   └── 1D wavelength overlay from star.load_observation(epoch, band)
│   │   ├── Emission line band overlays — from cell 11 (emission_lines dict)
│   │   ├── Toggle: cleaned vs uncleaned normalized flux (#28)
│   │   ├── Epoch flux consistency scatter — from notebook cell 9:
│   │   │   ├── User selects two epochs + wavelength window (e.g. 575-595 nm → 5750-5950 Å)
│   │   │   ├── Load cleaned_normalized_flux for each epoch
│   │   │   ├── Scatter plot of flux1 vs flux2 in the window
│   │   │   └── Place in st.expander("Epoch Consistency Check")
│   │   └── Extreme RV comparison (highest vs lowest epoch overlay) — from StarClass.plot_extreme_rv_spectra / notebook cell 15
│   │
│   ├── RV Analysis sub-tab (ported from notebook cells 44-59)
│   │   ├── Toggle: show cleaned / contaminated stars (#28)
│   │   ├── Plot 1: ΔRV bar chart (all stars, sorted, with threshold line) — cell 44
│   │   ├── Plot 2: Binary Fraction vs ΔRV Threshold — cell 46/47
│   │   ├── Plot 3: Equivalent Thresholds across lines — cell 49
│   │   ├── Plot 4: Binary Fraction per emission line — cell 55
│   │   ├── Plot 5: Confidence Grading (Golden/Silver/Bronze) — cell 57
│   │   ├── Plot 6: All/Clean/Contaminated comparison — cell 59
│   │   ├── Plot 7: RV vs Epoch for selected star — existing functionality
│   │   └── Plot 8: Corner plot — cells 51, 53
│   │       └── NxN scatter/histogram matrix of ΔRV across emission lines
│   │       └── Full-width section (not hidden in expander — scientifically important)
│   │
│   ├── Emission Lines sub-tab
│   │   ├── Per-line ΔRV comparison across stars
│   │   └── Line-by-line RV table
│   │
│   ├── CCF Outputs sub-tab (preserved from current page)
│   │   └── Browse CCF plot PNGs from ../output/
│   │
│   └── Grid Results sub-tab
│       ├── K-S heatmap from latest Dsilva/Langer result
│       └── p-value slice at best π
│
├── NRES tab
│   ├── Sub-tabs: ["Spectra", "RV Analysis", "SNR & Quality"]
│   │
│   ├── Spectra sub-tab
│   │   ├── Star selector (WR 52, WR17)
│   │   ├── Normalized spectra (all epochs overlaid) — from notebook cell 22-23 & NRESClass.plot_normalized_spectra
│   │   ├── Raw spectra with blaze correction toggle — from NRESClass.plot_raw_spectra / cell 31
│   │   ├── Stitched spectra — ALWAYS use NRESClass.get_stitched_spectra3() (production version with low-blaze filtering)
│   │   │   └── Never use get_stitched_spectra() or get_stitched_spectra2() — v3 is the latest
│   │   └── Emission line band overlays
│   │
│   ├── RV Analysis sub-tab
│   │   ├── RV vs date (epoch means) — mirrors 11_nres_analysis threshold tab
│   │   ├── All individual RVs scatter
│   │   └── Sigma summary table
│   │
│   └── SNR & Quality sub-tab
│       ├── SNR vs wavelength per spectrum — from notebook cell 28
│       ├── Individual NRES orders — from notebook cells 29-30:
│       │   ├── Load raw NRES data via star.load_observation(epoch, spectra_num, '1D')
│       │   ├── data['flux'], data['blaze'], data['wavelength'] — arrays with shape [n_orders, n_pixels]
│       │   ├── np.flip() to ascending wavelength order
│       │   ├── Show blaze-corrected (flux/blaze) individual orders as overlaid traces
│       │   ├── Toggle: with/without blaze correction
│       │   └── Subset selector or "show all orders" checkbox
│       └── Blaze function visualization — from cell 30
```

---

## Files to Modify/Create

### 1. `app/pages/06_plots.py` — FULL REWRITE (~800-1200 lines)
- **Backup first**: `cp app/pages/06_plots.py Backups/06_plots.py.bak`
- Rewrite from scratch, keeping the same page config and theme injection pattern
- Structure as two top-level tabs with sub-tabs inside each

### 2. `app/shared.py` — MINOR ADDITIONS (optional)
- May need a helper function for building the ΔRV analysis DataFrame (shared between plots page and notebook logic)
- Consider adding `cached_load_drv_analysis()` to avoid duplicating notebook cell 42's data pipeline
- Lines ~540-560: consider adding to exports

### 3. `TODO.md` — UPDATE STATUS
- Set #21, #26, #27, #28 to `to-test` after implementation

---

## Step-by-Step Implementation

### Step 0: Backup
```bash
cp app/pages/06_plots.py Backups/06_plots.py.bak
```

### Step 1: Create the ΔRV Analysis Data Pipeline

The notebook cell 42 has a comprehensive data pipeline that builds a DataFrame with ΔRV per star × emission line. This is needed for most RV Analysis plots. We need to port this as a cached function.

**Add to `app/shared.py`** (or create `app/drv_analysis.py`):
```python
@st.cache_data
def cached_load_drv_analysis(settings_hash: str) -> tuple[pd.DataFrame, dict, dict, dict, list]:
    """
    Build the comprehensive ΔRV analysis DataFrame used by all RV analysis plots.
    Returns (df, ew_fail_stats, drverr_map, rv_epoch_cache, ordered_lines).
    """
```

**CRITICAL E023 NOTE**: The parameter is `settings_hash` (NO leading underscore). A leading underscore would cause Streamlit to exclude it from the cache key, returning stale data for different settings. This was a bug in the previous plan version.

This function ports the data loading from notebook cell 42:
- Reads `ccf_settings_with_global_lines.json`
- For each star × each emission line: loads RVs, computes ΔRV, EW stats
- Returns a DataFrame with columns: `Star`, `Clean`, `is_clean_bool`, `dRV | {line}` for each line, `Mean ΔRV`, `Std ΔRV`
- Plus helper dicts: `ew_fail_stats`, `drverr_map`, `rv_epoch_cache`

**Critical**: Use `get_obs_manager()` to get the singleton ObservationManager.

### Step 2: Write the X-Shooter Spectra Sub-Tab

**Imports** — add `apply_theme` to the imports from `shared`:
```python
from shared import (
    inject_theme, render_sidebar, get_settings_manager,
    cached_load_observed_delta_rvs, settings_hash,
    get_obs_manager, COLOR_BINARY, COLOR_SINGLE,
    PLOTLY_THEME, apply_theme,
)
```

**Star/band selectors** at top. Then:

1. **Normalized spectra overlay**: For selected star, load `normalized_flux` or `cleaned_normalized_flux` for all epochs in selected band. Plot with Plotly scatter traces, one per epoch, color-coded.
   - Add a toggle: "Use cleaned spectra" (defaults True) — loads `cleaned_normalized_flux` first, falls back to `normalized_flux`.
   - Emission line band overlays using `ccf_settings_with_global_lines.json` line ranges (convert nm→Å by ×10).

2. **Raw spectra viewer** (with toggles in `st.columns`):
   - **Data loading**: `star.load_observation(epoch, band)` → FITS → `data['WAVE'][0]`, `data['FLUX'][0]`
   - Toggle: **Normalize** — load `norm_anchor_wavelengths` property, build continuum interpolation, divide flux by it
   - Toggle: **Log scale** — set `yaxis_type='log'`, mask flux ≤ 0
   - Toggle: **Show continuum** — load `interpolated_flux` property, overlay as dashed line
   - Toggle: **Show RV emission lines** — load line ranges from JSON, draw `fig.add_vrect()` for each
   - Toggle: **Color by instrument** — when band='COMBINED', color trace segments by UVB/VIS/NIR wavelength ranges

3. **Error spectra viewer** (in `st.expander("Error Spectrum")`):
   - Data: `star.load_observation(epoch, band)` → `data['ERR'][0]`
   - Plot error vs wavelength as a line chart
   - Simple but important for data quality assessment

4. **2D spectral image** (in `st.expander("2D Spectral Image")`):
   - Data: `star.load_2D_observation(epoch, band)` → `.primary_data` (2D numpy array)
   - Display as `go.Heatmap(z=image_data, x=wavelengths, colorscale='Viridis')`
   - Add `ValMin`/`ValMax` sliders for display range control
   - Note: wavelengths from `star.load_observation(epoch, band)` → `data['WAVE'][0]` for x-axis

5. **Epoch flux consistency scatter** (in `st.expander("Epoch Consistency Check")`):
   - User selects two epochs (selectbox) + wavelength window (two number_inputs in Å, default 5750–5950)
   - Load `cleaned_normalized_flux` for each epoch
   - Window the flux arrays to the selected range
   - Scatter plot: flux_epoch1 vs flux_epoch2
   - Ported from notebook cell 9

6. **Extreme RV comparison**: For selected star, find the epochs with max and min RV (from primary line `C IV 5808-5812`), overlay those two spectra. Highlight the emission line region.

**Data loading**: Use `@st.cache_data` functions, following the pattern in `02_spectrum.py`.

**CRITICAL THEME PATTERN**: Use `apply_theme()` from shared.py for ALL figure styling:
```python
apply_theme(fig, title=dict(text='My Title'), height=480,
            xaxis_title='Wavelength (Å)', yaxis_title='Normalised flux')
```
This is the project's canonical way to apply PLOTLY_THEME with overrides. It internally does `fig.update_layout(**{**PLOTLY_THEME, **overrides})`, which safely merges all keys. **NEVER** use `fig.update_layout(title=..., **PLOTLY_THEME)` — that triggers E018.

### Step 3: Write the X-Shooter RV Analysis Sub-Tab

Port the following plots from the notebook, converting matplotlib → Plotly:

#### Plot 1: ΔRV Bar Chart (cell 44)
- Bar chart of |ΔRV| per star, sorted descending
- Color: binary (red) vs single (blue) based on threshold
- Horizontal dashed line at threshold (45.5 km/s)
- Use `cached_load_observed_delta_rvs()` for data
- Add clean/contaminated toggle
- Apply theme: `apply_theme(fig, title=dict(text='Peak-to-Peak ΔRV'), height=380)`

#### Plot 2: Binary Fraction vs Threshold (cells 46-47)
- X-axis: ΔRV threshold range (10–400 km/s)
- Y-axis: observed binary fraction
- Show: per-line curves with different colors
- Highlight the current threshold (45.5) with vertical line
- Data: from the ΔRV analysis DataFrame, compute fraction above each threshold for each line

#### Plot 3: Equivalent Thresholds (cell 49)
- Line plot showing the threshold per emission line that yields the same f_bin as CIV at 20 km/s
- X-axis: emission line names, Y-axis: threshold value

#### Plot 4: Binary Fraction per Line (cell 55)
- Bar chart showing binary fraction for each emission line at the fixed threshold

#### Plot 5: Confidence Grading (cell 57)
- Stacked bar or grouped display: Golden/Silver/Bronze classification
- Shows how many lines agree on each star's classification

#### Plot 6: Clean vs Contaminated (cell 59)
- Side-by-side or stacked bar: binary/single counts for all, clean-only, contaminated-only

#### Plot 7: RV vs Epoch (existing)
- Per-star RV time series with error bars (already exists, just fix E018 bug and use `apply_theme()`)

#### Plot 8: Corner Plot (cells 51, 53)
- NxN scatter/histogram matrix of ΔRV across emission lines
- Scientific importance: shows pairwise correlation between lines → validates which lines agree
- Full-width display (not hidden in expander), with option to filter lines
- For N emission lines: create subplot grid N×N, diagonal=histogram, off-diagonal=scatter
- Use `plotly.subplots.make_subplots()` for the grid layout

### Step 4: Write the X-Shooter Emission Lines Sub-Tab

- Table showing per-star, per-line ΔRV values (from the analysis DataFrame)
- Color-coded: green if passes binary criterion, grey otherwise
- Optionally: corner plot matrix as a heatmap of pairwise line correlations (simplified version of notebook cell 51)

### Step 5: Write the X-Shooter CCF Outputs Sub-Tab

Preserve existing functionality:
- Browse CCF PNG files from `../output/{star}/CCF/`
- Filter by star
- Fix `use_column_width` → `use_container_width`

### Step 6: Write the X-Shooter Grid Results Sub-Tab

Preserve existing functionality:
- Load Dsilva/Langer result from `results/` directory
- Show K-S p-value heatmap with contours and best-fit star
- p-value slice at best π
- Fix all PLOTLY_THEME collision bugs — use `apply_theme()` throughout
- Use `make_heatmap_fig()` from shared.py instead of duplicating heatmap code

### Step 7: Write the NRES Spectra Sub-Tab

For NRES stars (WR 52, WR17):

**NOTE on NRESClass stubs**: `NRESClass.plot_spectra()` and `NRESClass.plot_spectra_errors()` are **empty placeholder methods** (`pass`). These will NOT be ported — they have no functionality. All NRES data must be loaded via `load_property()`, `load_observation()`, and `get_stitched_spectra3()`.

1. **Star/epoch/spectra selectors**: Use `NRESClass.get_all_epoch_numbers()` and `get_all_spectra_in_epoch()`

2. **Normalized spectra overlay**: Load `clean_normalized_flux` or `normalized_flux` for all epoch-spectra combos. Plot with Plotly.
   - Data access: `star.load_property('clean_normalized_flux', epoch, spectra_num)`
   - Returns dict with `wavelengths` and `normalized_flux` arrays

3. **Raw spectra with blaze correction**: Load raw observation data via `star.load_observation(epoch, spectra_num, '1D')`, extract `flux`, `blaze`, `wavelength` arrays. Plot flux/blaze if blaze correction toggled on.
   - Toggle: blaze correction on/off, sky subtraction on/off

4. **Stitched spectra**: **ALWAYS use `NRESClass.get_stitched_spectra3()`** — this is the production version with low-blaze filtering. Never use `get_stitched_spectra()` (v1) or `get_stitched_spectra2()` (v2).

### Step 8: Write the NRES RV Analysis Sub-Tab

- Reuse data from the NRES analysis page (`11_nres_analysis.py`)
- Load saved RV properties using `_load_existing_rvs()` pattern
- Show RV vs date plot (epoch means with error bars)
- Show individual RV scatter
- Show sigma summary table

### Step 9: Write the NRES SNR & Quality Sub-Tab

1. **SNR vs wavelength** for selected star/epoch/spectra (from notebook cell 28):
   - Data: `wave, flux, snr = star.get_stitched_spectra3(epoch, spectra_num)`
   - Plot the `snr` array vs `wave`

2. **Individual NRES orders** (from notebook cells 29-30):
   - Load raw NRES data: `data = star.load_observation(epoch, spectra_num, '1D').data`
   - Extract arrays: `flux = np.flip(data['flux'])`, `blaze = np.flip(data['blaze'])`, `wave = np.flip(data['wavelength'])`
   - These are 2D arrays: `[n_orders, n_pixels]` — NRES has ~67 fiber pairs → multiple orders
   - Display individual orders (odd indices = object, even = sky for most stars):
     - Plot `wave[order_idx]` vs `flux[order_idx]/blaze[order_idx]` (blaze-corrected) for selected orders
     - Or plot without blaze correction: just `flux[order_idx]`
   - Toggle: with/without blaze correction
   - Order selector (multiselect or slider range)
   - **WR17 special case**: epochs 2 & 3 have reversed sky/object pairing (handled by get_stitched_spectra3 internally, but manual order plots need awareness)

3. **Blaze function visualization** (from cell 30):
   - Plot blaze arrays for each order to show the instrument response
   - Useful for understanding data quality and order overlap regions

### Step 10: Fix Axis Units (#26)

Ensure all wavelength axes are labeled "Wavelength (Å)" and data is in Angstrom.
- X-Shooter data: the `wavelengths` key in normalized_flux properties is already in Å
- X-Shooter raw FITS: `data['WAVE'][0]` is in **nm** — multiply by 10 to get Å
- NRES data: `wavelength` arrays are in Å
- Verify by checking units in the property dicts
- Add "Wavelength (Å)" as the x-axis label on all spectrum plots

### Step 11: Test & Verify

1. `python -m py_compile app/pages/06_plots.py` — must succeed
2. Run COMMON_ERRORS quick-scan regex against the file — especially:
   - E018: `grep -nE 'title\s*=.*\*\*PLOTLY|update_layout\(.*title.*\*\*PLOTLY'`
   - E023: `grep -nE 'def\s+\w+\(.*_\w+.*:.*str'` in `@st.cache_data` functions
   - E020: no bare `make_heatmap_fig()` without `title=`
3. Launch webapp: `conda run -n guyenv streamlit run app/app.py`
4. Test each sub-tab loads without errors
5. Verify other pages still work: 01_stars, 02_spectrum, 03_ccf, 04_classification, 05_bias_correction, 07_tables, 08_results, 09_settings, 10_todo, 11_nres_analysis

### Step 12: Update TODO.md

Set tasks #21, #26, #27, #28 to `to-test`.

---

## Risks & Mitigations

### Risk 1: E018 — PLOTLY_THEME keyword collision
**Mitigation**: Always use `apply_theme(fig, title=dict(text='...'), height=480)` from shared.py. This helper merges `PLOTLY_THEME` with overrides safely via `fig.update_layout(**{**PLOTLY_THEME, **overrides})`. NEVER use `fig.update_layout(title=..., **PLOTLY_THEME)`.

### Risk 2: NRES data availability
The NRES stars (WR 52, WR17) may not have all properties saved. The code must handle missing data gracefully with `st.info()` messages.
**Mitigation**: Always check `if data is None:` before attempting to access dict keys.

### Risk 3: E023 — `@st.cache_data` underscore parameter exclusion
**Mitigation**: Never prefix cache-relevant parameters with `_`. Use full names like `settings_hash`, `star_name`, not `_settings_hash`, `_star_name`. Leading underscore causes Streamlit to silently exclude the parameter from cache key computation.

### Risk 4: Large data loading time
The ΔRV analysis data pipeline loads RVs for all 25 stars × 11 emission lines.
**Mitigation**: Use `@st.cache_data` aggressively. Cache the analysis DataFrame with a settings hash key. Show `st.spinner()` during first load.

### Risk 5: File size / complexity
A full port of all notebook plots could result in 1500+ lines.
**Mitigation**:
- Use helper functions extracted into the top of the file
- Limit initial scope to the most useful plots; add more incrementally
- Use `st.expander()` for less-used plots to keep the page clean

### Risk 6: Notebook helper functions are complex
The notebook's `get_star_classification_data()`, `build_masked_df()`, `calculate_equivalent_thresholds()` etc. are 200+ lines of data processing.
**Mitigation**: Port only the essential data pipeline. The key outputs needed are:
1. `df` — the ΔRV analysis DataFrame
2. `ew_fail_stats` — for filtering low-quality lines
3. `drverr_map` — for binary significance calculation
4. `ordered_lines` — the emission line list
5. `rv_epoch_cache` — for per-star RV time series

### Risk 7: Breaking other pages
**Mitigation**: Only modify `06_plots.py`. Any additions to `shared.py` are purely additive (new functions). Run all other pages to verify no regressions.

### Risk 8: NRESClass/StarClass matplotlib methods
The `plot_*` methods in `StarClass.py` and `NRESClass.py` use `matplotlib.pyplot` which doesn't work in Streamlit. We must NOT call these methods directly. Instead, we load the raw data using `load_property()`, `load_observation()`, `get_stitched_spectra3()` etc. and build Plotly figures ourselves.
**Mitigation**: Only use data-loading methods, never call `plot_*` methods. Additionally: `NRESClass.plot_spectra()` and `NRESClass.plot_spectra_errors()` are **empty stubs** (just `pass`) — skip them entirely.

### Risk 9: `preview_snr_stitch_cleaned_normalized()` does not exist in StarClass
This method is called in notebook cell 20 but does NOT exist in `StarClass.py` (grep confirms no match). It was likely deleted or never implemented.
**Mitigation**: Skip this specific plot. If SNR quality visualization is needed, use the normalized flux comparison approach (load cleaned vs. original, overlay) rather than calling a non-existent method.

---

## Data Access Patterns (Reference)

### X-Shooter (StarClass)
```python
obs = get_obs_manager()
star = obs.load_star_instance(star_name, to_print=False)  # returns Star object
epochs = star.get_all_epoch_numbers()  # [1, 2, 3, ...]
bands = ['COMBINED', 'UVB', 'VIS', 'NIR']

# Normalized spectrum
data = star.load_property('normalized_flux', epoch, band)
# or
data = star.load_property('cleaned_normalized_flux', epoch, band)
# data = {'wavelengths': np.array, 'normalized_flux': np.array}

# Raw spectrum from FITS
fit = star.load_observation(epoch, band)
wave_nm = fit.data['WAVE'][0]     # nanometers!
flux    = fit.data['FLUX'][0]
err     = fit.data['ERR'][0]
wave_A  = wave_nm * 10            # convert to Angstrom

# 2D image
fit_2d = star.load_2D_observation(epoch, band)
image_data = fit_2d.primary_data   # 2D numpy array

# Continuum model
interp = star.load_property('interpolated_flux', epoch, band)

# Normalization anchor points
anchors = star.load_property('norm_anchor_wavelengths', epoch, 'COMBINED')

# Backup comparison
old_data = star.load_property('cleaned_normalized_flux', epoch, band, from_backup=True)

# RVs per emission line
rv_prop = star.load_property('RVs', epoch, 'COMBINED')
# rv_prop = {'C IV 5808-5812': {'full_RV': float, 'full_RV_err': float}, ...}

# MJD
fit = star.load_observation(epoch, band='VIS')
mjd = float(fit.header['MJD-OBS'])
```

### NRES (NRESClass)
```python
obs = get_obs_manager()
star = obs.load_star_instance('WR 52', to_print=False)  # returns NRES object
epochs = star.get_all_epoch_numbers()
spectra = star.get_all_spectra_in_epoch(epoch)

# Normalized spectrum
data = star.load_property('clean_normalized_flux', epoch, spectra_num, to_print=False)
# or
data = star.load_property('normalized_flux', epoch, spectra_num, to_print=False)
# data = {'wavelengths': np.array, 'normalized_flux': np.array}

# Stitched spectra (ALWAYS use v3 — production version with low-blaze filtering)
wave, flux, snr = star.get_stitched_spectra3(epoch, spectra_num)

# Raw NRES orders (for individual order viewing)
fit = star.load_observation(epoch, spectra_num, '1D')
flux_arr = np.flip(fit.data['flux'])        # shape: [n_orders, n_pixels]
blaze_arr = np.flip(fit.data['blaze'])       # shape: [n_orders, n_pixels]
wave_arr = np.flip(fit.data['wavelength'])   # shape: [n_orders, n_pixels]
# Odd indices = object, even = sky (EXCEPT WR17 epochs 2&3: reversed)
# Blaze-corrected: flux_arr[i] / blaze_arr[i]

# Combined flux with SNR
combined = star.load_property('combined_flux', epoch, spectra_num)
# combined = {'wavelength': np.array, 'flux': np.array, 'SNR': np.array}

# RVs
rv_prop = star.load_property('RVs', epoch, spectra_num, to_print=False)

# MJD from FITS header
fit = star.load_observation(epoch, spectra_num, '1D')
mjd = float(fit.header['MJD-OBS'])  # or DATE-OBS
```

---

## apply_theme() Usage Reference

The `apply_theme()` function in `shared.py` (lines 113-117) is the canonical way to style all Plotly figures:

```python
def apply_theme(fig, **overrides):
    """Apply scientific Plotly theme to *fig*, with optional overrides."""
    merged = {**PLOTLY_THEME, **overrides}
    fig.update_layout(**merged)
    return fig
```

**Usage examples throughout the page:**
```python
# Simple case — just title and height
apply_theme(fig, title=dict(text='My Plot Title'), height=480)

# With axis labels
apply_theme(fig, title=dict(text='Spectra'), height=480,
            xaxis_title='Wavelength (Å)', yaxis_title='Flux')

# With log axis
apply_theme(fig, title=dict(text='Raw Spectrum (log)'), height=480,
            yaxis_type='log', xaxis_title='Wavelength (Å)')

# With custom margins
apply_theme(fig, title=dict(text='2D Image'), height=500,
            margin=dict(l=60, r=20, t=50, b=50))
```

**NEVER do this** (E018):
```python
fig.update_layout(title='...', **PLOTLY_THEME)  # TypeError!
fig.update_layout(title=dict(text='...'), **PLOTLY_THEME)  # TypeError!
```

---

## Verification Checklist

- [ ] `python -m py_compile app/pages/06_plots.py` passes
- [ ] Quick-scan regex shows no E018 or other known errors
- [ ] X-Shooter > Spectra: normalized spectra overlay renders for any star
- [ ] X-Shooter > Spectra: emission line bands toggle works
- [ ] X-Shooter > Spectra: clean/uncleaned toggle works
- [ ] X-Shooter > Spectra: raw spectra viewer with all toggles (normalize, log, continuum, emission lines)
- [ ] X-Shooter > Spectra: error spectrum viewer renders
- [ ] X-Shooter > Spectra: 2D spectral image renders (if 2D data available)
- [ ] X-Shooter > Spectra: epoch consistency scatter works (select 2 epochs + wavelength window)
- [ ] X-Shooter > RV Analysis: ΔRV bar chart renders for all 25 stars
- [ ] X-Shooter > RV Analysis: binary fraction vs threshold curve renders
- [ ] X-Shooter > RV Analysis: RV vs epoch works for selected star
- [ ] X-Shooter > RV Analysis: corner plot renders
- [ ] X-Shooter > Emission Lines: per-line table renders
- [ ] X-Shooter > CCF Outputs: image browser works
- [ ] X-Shooter > Grid Results: heatmap renders from saved results
- [ ] NRES > Spectra: normalized spectra overlay for WR 52 / WR17
- [ ] NRES > Spectra: stitched spectra using get_stitched_spectra3()
- [ ] NRES > RV Analysis: RV vs date if data available
- [ ] NRES > SNR: SNR vs wavelength renders
- [ ] NRES > SNR: individual order viewer works (with/without blaze correction)
- [ ] All other pages (01-05, 07-11) still load without errors
- [ ] No hardcoded colors (grep for `#1a1a2e`, `#e0e0e0`)
- [ ] All wavelength axes labeled "Wavelength (Å)"
- [ ] All `apply_theme()` calls — no raw `**PLOTLY_THEME` in `update_layout()` calls
- [ ] No `@st.cache_data` parameters starting with `_` that should differentiate cache entries
- [ ] TODO.md updated with #21, #26, #27, #28 set to `to-test`
