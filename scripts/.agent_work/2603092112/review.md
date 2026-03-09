# Review: Plan for Rebuild Plots Page (06_plots.py)

## What's Correct

1. **Accurate bug identification in current file**: The plan correctly identifies all E018 bugs (lines 76-80, 118-122 with `title=..., **PLOTLY_THEME`), hardcoded dark colors (lines 140-141, 203-204, 216-217), and the deprecated `use_column_width` on line 168. These are real and confirmed.

2. **Correct two-tab structure**: The user explicitly asked for X-Shooter and NRES tabs. The plan delivers this with appropriate sub-tabs for each.

3. **Correct data access patterns**: The plan's reference section accurately reflects how to load data:
   - StarClass: `load_property(property_name, epoch_num, band)` — verified correct
   - NRESClass: `load_property(property_name, epoch_num, spectra_num, data_type='1D', to_print=True)` — verified correct
   - MJD from FITS headers, not RV property dict — matches CLAUDE.md convention
   - `get_obs_manager()` returns cached `ObservationManager` singleton — verified

4. **PLOTLY_THEME keys correctly identified**: The plan lists `title`, `legend`, `xaxis`, `yaxis`, `font` as colliding keys — confirmed from `_build_plotly_theme()` in shared.py (lines 92-105).

5. **Correct NRES star names**: `'WR 52'` and `'WR17'` match `ObservationManager.NRES_stars`.

6. **Risk 8 (matplotlib methods)**: Correctly identifies that `plot_*` methods in StarClass/NRESClass use matplotlib internally and cannot be called in Streamlit — data must be loaded via `load_property()` / `load_observation()` and Plotly figures built manually.

7. **Good risk analysis overall**: Risks 1-8 are well-identified with appropriate mitigations.

8. **Backup step**: Plan correctly calls for `cp app/pages/06_plots.py Backups/06_plots.py.bak` per CLAUDE.md convention.

9. **TODO items correctly identified**: #21, #26, #27, #28 are all relevant plot-page tasks.

10. **Verification checklist is comprehensive**: Includes py_compile, COMMON_ERRORS scan, per-subtab testing, and all-pages regression check.

---

## What Needs Fixing

### CRITICAL — E023 Violation in Plan's Own Code

**Step 1** defines:
```python
@st.cache_data
def cached_load_drv_analysis(_settings_hash: str) -> tuple[...]:
```

The parameter `_settings_hash` starts with underscore. Per E023, Streamlit **excludes** underscore-prefixed parameters from the cache key. This means every call — regardless of what settings hash is passed — would return the same cached result. The plan's own text even says "NOT starting with underscore — see E023" in the same paragraph, directly contradicting the code shown. This would cause stale/incorrect data across different settings configurations.

### CRITICAL — Plan Ignores `apply_theme()` Helper

`shared.py` (lines 113-117) already provides:
```python
def apply_theme(fig, **overrides):
    """Apply scientific Plotly theme to *fig*, with optional overrides."""
    merged = {**PLOTLY_THEME, **overrides}
    fig.update_layout(**merged)
    return fig
```

This is the **safe, canonical way** to apply PLOTLY_THEME with overrides, and it's already in shared.py. The plan instead tells the implementer to use `fig.update_layout(**{**PLOTLY_THEME, 'title': dict(text='...')})` everywhere — a verbose, error-prone pattern when a one-liner already exists. Using `apply_theme(fig, title=dict(text='...'), height=480)` is both safer and cleaner.

### HIGH — Incomplete Coverage of StarClass Plot Methods

The user explicitly said: *"make sure all the plots I can make from my Plots notebook, and in the StarClass and NRESClass are plottable as well."*

The plan is missing Plotly equivalents for these StarClass methods:

| Method | What It Does | Plan Coverage |
|--------|-------------|---------------|
| `plot_spectra(normalize=False, log=True, add_continuum=True, add_RV_emission_lines=True)` | Raw spectra with continuum model overlay, emission line annotations, log scale, rest-frame toggle | Only "Raw spectra viewer (optional, per epoch)" — missing all the toggle detail |
| `plot_spectra_errors()` | Error spectrum per epoch/band | **Not mentioned at all** |
| `plot_2D_image(epoch_num, band)` | 2D FITS spectral image visualization | **Not mentioned at all** |
| `preview_snr_stitch_cleaned_normalized()` | SNR and stitching quality preview across bands | **Not mentioned at all** |

### HIGH — Incomplete Coverage of Notebook Plots

Several notebook plots are missing from the plan:

| Notebook Cell | Description | Plan Coverage |
|--------------|-------------|---------------|
| Cell 10 | Epoch-to-epoch flux consistency scatter plot (scatter of flux1 vs flux2 in a wavelength window) | **Missing** |
| Cell 19 | Before/after normalization comparison (old vs new flux overlay) | **Missing** |
| Cell 21 | SNR/stitch preview via `preview_snr_stitch_cleaned_normalized()` | **Missing** |
| Cell 30-31 | Individual NRES spectral orders (16 orders) with blaze correction — important for understanding data quality | **Missing** (plan has "Raw spectra with blaze correction" but not per-order view) |
| Cell 37 Plot 4 | Corner plot (NxN scatter/histogram matrix of ΔRV across emission lines) | Listed as "optional expander" — should be more prominently covered given scientific importance |

### MEDIUM — NRESClass Empty Placeholder Methods

The plan lists `plot_spectra` and `plot_spectra_errors` for NRESClass as things to port, but these are **empty placeholder methods** (`def plot_spectra(self, *args, **kwargs): pass`). The plan should note these are no-ops and skip them rather than implying they have functionality to port.

### MINOR — `get_stitched_spectra3` vs Earlier Versions

NRESClass has three versions: `get_stitched_spectra()`, `get_stitched_spectra2()`, and `get_stitched_spectra3()`. The plan mentions `get_stitched_spectra3()` which is correct (it's the latest with `remove_low_blaze=True`), but should explicitly note to **always use v3** and never the older versions.

### MINOR — Missing `apply_theme` from Imports

The plan's Step 1 imports section doesn't mention importing `apply_theme` from `shared`. Since it should be used throughout (see critical fix above), it must be added to the import list.

---

## Corrections Required

### 1. Fix E023 violation (CRITICAL)
Change the function signature in Step 1 from:
```python
def cached_load_drv_analysis(_settings_hash: str) -> tuple[...]:
```
to:
```python
def cached_load_drv_analysis(settings_hash: str) -> tuple[...]:
```
(Remove the leading underscore.)

### 2. Use `apply_theme()` throughout (CRITICAL)
Replace all instances of the pattern:
```python
fig.update_layout(**{**PLOTLY_THEME, 'title': dict(text='...'), 'height': 400})
```
with:
```python
apply_theme(fig, title=dict(text='...'), height=400)
```
Add `apply_theme` to the imports from `shared`. This eliminates the E018 risk entirely.

### 3. Add missing StarClass plot types to X-Shooter Spectra sub-tab (HIGH)
Add to the Spectra sub-tab plan:
- **Raw spectra viewer** with toggles: normalize, Rest_frame, log scale, add_continuum overlay, add_RV_emission_lines. Load data via `star.load_observation()` → get raw flux/wave, then build Plotly figure with toggleable overlays using `st.checkbox`.
- **Error spectra viewer**: Load error arrays from FITS and plot as line chart.
- **2D spectral image**: Load 2D FITS data via `star.load_observation()` → access `.data` attribute → display as Plotly heatmap (`go.Heatmap`). Toggles: ValMin/ValMax sliders, normalization.
- **SNR/stitch quality viewer**: Load cleaned normalized flux and SNR bounds, plot quality metrics across wavelength.

### 4. Add missing notebook plots (HIGH)
- **Epoch flux consistency scatter** (Cell 10): Under X-Shooter Spectra, add an expander "Epoch Consistency Check" — user selects two epochs + wavelength window → scatter plot of flux1 vs flux2.
- **Per-order NRES view** (Cells 30-31): Under NRES SNR & Quality sub-tab, add "Individual Orders" section — load raw NRES data, show 16 orders overlaid with/without blaze correction.

### 5. Remove NRESClass placeholder methods from scope
Note explicitly that `NRESClass.plot_spectra()` and `NRESClass.plot_spectra_errors()` are empty stubs and will not be ported.

### 6. Add `apply_theme` to shared.py imports
In the plan's import section, add:
```python
from shared import (
    inject_theme, render_sidebar, get_settings_manager,
    cached_load_observed_delta_rvs, settings_hash,
    get_obs_manager, COLOR_BINARY, COLOR_SINGLE,
    PLOTLY_THEME, apply_theme,  # <-- add apply_theme
)
```

---

## Verdict

The plan is solid architecturally — the two-tab structure, sub-tabs, data access patterns, risk analysis, and verification checklist are all well done. However, the E023 bug in the plan's own code would cause a runtime data caching defect, and the plan misses the existing `apply_theme()` helper which is the project's canonical way to avoid E018. Additionally, the user explicitly requested coverage of all notebook and class plots, and several are missing.

**REJECTED** — The E023 parameter naming bug is a silent data corruption issue that would be difficult to debug at runtime. The incomplete plot coverage does not satisfy the user's explicit request. Apply the corrections above and resubmit.
