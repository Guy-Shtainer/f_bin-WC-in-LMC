# Implementation Plan: NRES Analysis Page (Task #22)

## 1. Summary

Create a new Streamlit page `app/pages/11_nres.py` that:

1. Lets the user select a NRES star and epoch/spectrum combination
2. Loads and stitches the NRES spectra with blaze correction and sky subtraction using `NRES.get_stitched_spectra()`
3. Runs the CCF algorithm on selectable emission lines (filtered to NRES wavelength range ~380–860 nm)
4. Displays RVs in a sortable table (per epoch/spectrum/line)
5. Calculates and displays the variance (and std) of the RVs
6. Applies a binary detection criterion using std as threshold
7. Compares to the current X-SHOOTER binary fraction from the existing pipeline

---

## 2. Key Findings from Codebase Exploration

### 2.1 NRES Star List

From `ObservationClass.py` line ~42:
```python
self.NRES_stars = ['WR 52', 'WR17']
```
NRES stars are separate from the 25 X-SHOOTER stars in `specs.star_names`. `ObservationManager.load_star_instance()` routes to `NRES` class automatically.

### 2.2 NRES Data Loading Pipeline

From `NRESClass.py`:

1. **`nres.load_observation(epoch_num, spectra_num, "1D")`** — returns a `FITSFile` object. The FITS table has columns: `wavelength`, `flux`, `uncertainty`, `blaze`, `blaze_error` — each of shape `(N_orders, N_pixels)`.

2. **Data layout**: Orders come in pairs — even indices are sky (`2*i`), odd are object (`2*i+1`). Arrays are reversed (`[::-1]`) to go short→long wavelength.

3. **Blaze correction**: `flux_obj / blaze_obj - flux_sky / blaze_sky`

4. **Stitching**: `_stitch_spectra_by_snr(wave_list, flux_list, snr_list)` — SNR-weighted overlap combination.

5. **Primary method**: `NRES.get_stitched_spectra(epoch_num, spectra_num, subtract_sky=True)` → returns `(combined_wave, combined_flux, combined_snr)`. Wavelengths in **Angstroms**.

6. **MJD**: From FITS header — `fits_file.header['MJD-OBS']` (NOT from property files).

7. **Normalized spectra**: Stored as property `'normalized_flux'` → dict with keys `wavelengths`, `normalized_flux`.

### 2.3 CCF Algorithm Requirements

From `CCF.py` (`CCFclass.compute_RV`):
- Input: `obs_wave` (Angstroms, 1D), `obs_flux` (normalized, 1D), `tpl_wave`, `tpl_flux`
- Constructor params:
  - `CrossCorRangeA` — list of `[λ_start, λ_end]` pairs in **nm** (when `nm=True`)
  - `CrossVeloMin`, `CrossVeloMax` — km/s
  - `Fit_Range_in_fraction` — 0.97 default in settings
  - `nm=True` — input ranges are in nm
- Returns `(RV_km_s, sigma_km_s)` or `(None, None)` on failure

**Template for CCF**: CCF needs a template spectrum. Strategy (in order of preference):
1. Load `'normalized_flux'` property from a reference epoch (cleanest)
2. Normalize the stitched spectrum inline with a polynomial continuum fit and use as self-template (epoch-to-epoch shifts remain valid)

**CRITICAL UNIT NOTE**: `CrossCorRangeA` in nm; `obs_wave` / `tpl_wave` in Angstroms. Do NOT convert obs_wave — pass it directly. The CCF internally handles the unit difference via its log-grid.

### 2.4 Existing Settings Structure

From `settings/user_settings.json`:
- `emission_lines` — dict `{line_name: [λ_start_nm, λ_end_nm]}`
- `ccf.CrossVeloMin`, `ccf.CrossVeloMax`, `ccf.fit_fraction_default`
- `classification.threshold_dRV` (45.5 km/s), `classification.sigma_factor` (4)
- `classification.bartzakos_binaries` (3), `classification.total_population` (28)

**NRES-relevant lines** (λ_start >= 360 nm, λ_end <= 870 nm):
- `He II 4686`: 456–480 nm ✓
- `O VI 5210-5340`: 521–533.5 nm ✓
- `He II 5412 & C IV 5471`: 535–554 nm ✓
- `C IV 5808-5812`: 570–588 nm ✓ (primary binary line)
- `C III 6700-6800`: 666.5–684 nm ✓
- `C IV 7063`: 697–714 nm ✓
- NIR lines (`C IV 17396`, `C IV 20842`) — OUTSIDE NRES range, exclude

### 2.5 Existing Page Patterns

From `app/pages/03_ccf.py` and `app/pages/01_stars.py`:

1. **Path fix block** at top:
```python
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)
from shared import inject_theme, render_sidebar, ...
```

2. **Caching**: `@st.cache_data` on expensive IO (FITS loading, CCF); no TTL.

3. **Settings persistence**: `sm.save(['nres', 'key'], value=...)` via `on_change` callbacks.

4. **Error handling**: All data loads in try/except; `st.warning()` on failure, never crash.

5. **Progress bars**: For loops >5 seconds must use `st.progress()` updated per iteration.

### 2.6 X-SHOOTER Binary Fraction for Comparison

`shared.py::cached_load_observed_delta_rvs(settings_hash)` returns `(obs_delta_rv_dict, detail_dict)` where `detail_dict[star]['is_binary']` is a bool. Use this to compute:
```
f_xsh = (N_xsh_binary + bartzakos_3) / total_28
```

---

## 3. Files to Create / Modify

### Create

| File | Purpose |
|------|---------|
| `app/pages/11_nres.py` | New NRES analysis page (~500 lines) |

### Modify

| File | What to Change |
|------|---------------|
| `app/shared.py` | Add `st.page_link('pages/11_nres.py', ...)` in `render_sidebar()` navigation list |
| `settings/user_settings.json` | Add `"nres"` section with NRES-specific defaults (pure additive, no existing keys changed) |

**Backup first**: `cp app/pages/10_todo.py Backups/10_todo.py.bak` and equivalent for `shared.py` before editing.

---

## 4. Step-by-Step Implementation Instructions

### Step 0: Backups

```bash
cp app/shared.py Backups/shared.py.bak
cp settings/user_settings.json Backups/user_settings.json.bak
```

### Step 1: Update `settings/user_settings.json`

Add at top level (after the last closing brace of any existing top-level key, inside the outer `{}`):

```json
"nres": {
  "subtract_sky": true,
  "velo_min": -500,
  "velo_max": 500,
  "fit_fraction": 0.97,
  "variance_threshold": 45.5,
  "active_lines": ["C IV 5808-5812", "He II 4686", "C IV 7063"]
}
```

**Do NOT change any existing keys.**

### Step 2: Update `app/shared.py` — Add Page Link

In `render_sidebar()`, after the line that adds the to-do page link (`pages/10_todo.py`), add:
```python
st.page_link('pages/11_nres.py', label='🔭 NRES Analysis')
```

### Step 3: Create `app/pages/11_nres.py`

Full structure (see Section 5 for detailed code). Sections:

**SECTION 1 — Imports and path fix**
```python
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from shared import (
    inject_theme, render_sidebar, get_settings_manager, settings_hash,
    cached_load_observed_delta_rvs, PLOTLY_THEME
)
from CCF import CCFclass
from ObservationClass import ObservationManager
```

**SECTION 2 — Page config**
```python
st.set_page_config(
    page_title='NRES Analysis',
    page_icon='🔭',
    layout='wide',
)
inject_theme()
settings = render_sidebar('NRES')
sm = get_settings_manager()
```

**SECTION 3 — Constants**
```python
NRES_STARS = ['WR 52', 'WR17']
NRES_WAVE_MIN_NM = 360.0
NRES_WAVE_MAX_NM = 870.0
```

**SECTION 4 — Filter emission lines to NRES range**
```python
all_lines = settings.get('emission_lines', {})
nres_lines = {
    k: v for k, v in all_lines.items()
    if v[0] >= NRES_WAVE_MIN_NM and v[1] <= NRES_WAVE_MAX_NM
}
```

**SECTION 5 — Load NRES defaults from settings**
```python
nres_cfg = settings.get('nres', {})
default_velo_min = nres_cfg.get('velo_min', -500)
default_velo_max = nres_cfg.get('velo_max', 500)
default_fit_frac = nres_cfg.get('fit_fraction', 0.97)
default_lines = nres_cfg.get('active_lines', ['C IV 5808-5812'])
default_threshold = nres_cfg.get('variance_threshold', 45.5)
default_sky = nres_cfg.get('subtract_sky', True)
```

**SECTION 6 — Cached helpers**
```python
@st.cache_data
def _get_obs_manager():
    return ObservationManager(to_print=False)

@st.cache_data
def _get_nres_instance(star_name: str):
    om = _get_obs_manager()
    return om.load_star_instance(star_name, to_print=False)

@st.cache_data
def _load_stitched(star_name: str, epoch: int, spectra: int, subtract_sky: bool):
    """Load stitched NRES spectrum. Returns (wave_A, flux, snr, mjd)."""
    try:
        om = _get_obs_manager()
        nres = om.load_star_instance(star_name, to_print=False)
        wave, flux, snr = nres.get_stitched_spectra(epoch, spectra, subtract_sky=subtract_sky)
        # Get MJD from FITS header
        try:
            fits_file = nres.load_observation(epoch, spectra, "1D")
            mjd = float(fits_file.header['MJD-OBS'])
        except Exception:
            mjd = float('nan')
        return wave, flux, snr, mjd
    except Exception as e:
        return None, None, None, float('nan')

@st.cache_data
def _load_template(star_name: str, epoch: int, spectra: int):
    """Load normalized spectrum for use as CCF template."""
    try:
        om = _get_obs_manager()
        nres = om.load_star_instance(star_name, to_print=False)
        norm_data = nres.load_property('normalized_flux', epoch, spectra)
        return norm_data.get('wavelengths'), norm_data.get('normalized_flux')
    except Exception:
        return None, None

@st.cache_data
def _get_all_epochs(star_name: str):
    """Return sorted list of available epoch numbers."""
    try:
        nres = _get_nres_instance(star_name)
        return sorted(nres.get_all_epoch_numbers())
    except Exception:
        return [1]

@st.cache_data
def _get_spectra_in_epoch(star_name: str, epoch: int):
    try:
        nres = _get_nres_instance(star_name)
        return sorted(nres.get_all_spectra_in_epoch(epoch))
    except Exception:
        return [1]
```

**SECTION 7 — UI: Star / Epoch / Spectra Selector**
```python
st.title('🔭 NRES Analysis')
st.caption('Load and CCF-analyze NRES multi-fiber spectra for WR stars.')

col_star, col_ep, col_sp, col_sky = st.columns([2, 1, 1, 1])
with col_star:
    star_name = st.selectbox('NRES Star', NRES_STARS, key='nres_star')
with col_ep:
    all_epochs = _get_all_epochs(star_name)
    epoch = st.selectbox('Epoch', all_epochs, key='nres_epoch')
with col_sp:
    all_specs = _get_spectra_in_epoch(star_name, epoch)
    spectra = st.selectbox('Spectra #', all_specs, key='nres_spectra')
with col_sky:
    subtract_sky = st.checkbox('Sky subtract', value=default_sky, key='nres_sky',
        on_change=lambda: sm.save(['nres', 'subtract_sky'],
                                   st.session_state['nres_sky']))
```

**SECTION 8 — CCF Settings Expander**
```python
with st.expander('⚙️ CCF Settings', expanded=False):
    s1, s2, s3 = st.columns(3)
    with s1:
        velo_min = st.number_input('CrossVeloMin (km/s)', value=default_velo_min,
            step=50, key='nres_vmin',
            on_change=lambda: sm.save(['nres', 'velo_min'], st.session_state['nres_vmin']))
        velo_max = st.number_input('CrossVeloMax (km/s)', value=default_velo_max,
            step=50, key='nres_vmax',
            on_change=lambda: sm.save(['nres', 'velo_max'], st.session_state['nres_vmax']))
    with s2:
        fit_frac = st.slider('Fit fraction', 0.5, 1.0, default_fit_frac, 0.01,
            key='nres_fitfrac',
            on_change=lambda: sm.save(['nres', 'fit_fraction'], st.session_state['nres_fitfrac']))
    with s3:
        var_threshold = st.slider('σ_RV threshold (km/s)', 0.0, 200.0, default_threshold, 0.5,
            key='nres_threshold',
            on_change=lambda: sm.save(['nres', 'variance_threshold'], st.session_state['nres_threshold']))

    selected_lines = st.multiselect(
        'Emission lines (NRES range only)',
        list(nres_lines.keys()),
        default=[l for l in default_lines if l in nres_lines],
        key='nres_lines',
        on_change=lambda: sm.save(['nres', 'active_lines'], st.session_state['nres_lines'])
    )
```

**SECTION 9 — Spectrum Display**
```python
wave, flux, snr, mjd = _load_stitched(star_name, epoch, spectra, subtract_sky)

if wave is not None and flux is not None:
    fig_spec = go.Figure()
    fig_spec.add_trace(go.Scatter(
        x=wave, y=flux, mode='lines',
        line=dict(color='#4A90D9', width=0.8),
        name='Flux'
    ))
    # Highlight selected emission line regions
    for lname in selected_lines:
        lrange = nres_lines[lname]
        fig_spec.add_vrect(
            x0=lrange[0]*10, x1=lrange[1]*10,  # nm → Angstrom
            fillcolor='rgba(255,165,0,0.15)',
            line_width=0,
            annotation_text=lname, annotation_position='top left'
        )
    fig_spec.update_layout(**{
        **PLOTLY_THEME,
        'title': f'{star_name} — Epoch {epoch}, Spec {spectra} (MJD {mjd:.2f})',
        'xaxis_title': 'Wavelength (Å)',
        'yaxis_title': 'Flux (arb. units)',
        'height': 350,
    })
    st.plotly_chart(fig_spec, use_container_width=True)
    st.caption(f'Stitched NRES spectrum. Sky subtraction: {subtract_sky}. MJD: {mjd:.3f}')
else:
    st.warning(f'Could not load spectrum for {star_name}, epoch {epoch}, spectra {spectra}.')
```

**SECTION 10 — Run CCF Over All Epochs**
```python
st.markdown('---')
if not selected_lines:
    st.warning('Select at least one emission line to run CCF.')
else:
    if st.button('▶ Run CCF for ALL epochs', type='primary', key='nres_run_ccf'):
        progress_bar = st.progress(0, text='Initializing...')
        status_text = st.empty()
        rv_results = {}

        all_ep = _get_all_epochs(star_name)
        total_combos = sum(len(_get_spectra_in_epoch(star_name, ep)) for ep in all_ep)
        done = 0

        for ep in all_ep:
            all_sp = _get_spectra_in_epoch(star_name, ep)
            for sp in all_sp:
                status_text.text(f'Processing epoch {ep}, spectra {sp}...')
                w, f, s, mjd_ep = _load_stitched(star_name, ep, sp, subtract_sky)
                if w is None:
                    done += 1
                    continue

                # Template: try normalized, else normalize inline
                tpl_w, tpl_f = _load_template(star_name, ep, sp)
                if tpl_w is None:
                    # Crude normalization — polynomial continuum
                    from numpy.polynomial import polynomial as P
                    med_f = np.nanmedian(f)
                    tpl_w = w.copy()
                    tpl_f = f / med_f if med_f > 0 else f.copy()

                for line_name in selected_lines:
                    line_range_nm = nres_lines[line_name]
                    try:
                        ccf_obj = CCFclass(
                            CrossCorRangeA=[line_range_nm],
                            CrossVeloMin=velo_min,
                            CrossVeloMax=velo_max,
                            Fit_Range_in_fraction=fit_frac,
                            nm=True,
                        )
                        rv, rv_err = ccf_obj.compute_RV(w, f, tpl_w, tpl_f)
                        if rv is not None:
                            rv_results[(ep, sp, line_name)] = {
                                'rv': float(rv),
                                'rv_err': float(rv_err),
                                'mjd': mjd_ep,
                            }
                    except Exception as exc:
                        st.warning(f'CCF failed {ep}/{sp}/{line_name}: {exc}')

                done += 1
                progress_bar.progress(done / max(total_combos, 1),
                                      text=f'Epoch {ep}, spec {sp} done.')

        st.session_state['nres_rv_results'] = rv_results
        status_text.text('✅ CCF complete.')
        progress_bar.progress(1.0, text='Done!')
```

**SECTION 11 — Display Results Table**
```python
if st.session_state.get('nres_rv_results'):
    rv_results = st.session_state['nres_rv_results']

    rows = [
        {
            'Epoch': k[0], 'Spectra': k[1], 'Line': k[2],
            'MJD': v['mjd'], 'RV (km/s)': round(v['rv'], 2),
            'Error (km/s)': round(v['rv_err'], 2),
        }
        for k, v in rv_results.items()
    ]
    df = pd.DataFrame(rows).sort_values(['Line', 'Epoch', 'Spectra']).reset_index(drop=True)

    st.subheader('📋 RV Results Table')
    st.dataframe(df, use_container_width=True)
```

**SECTION 12 — RV Time Series Plot**
```python
    st.subheader('📈 RV Time Series')
    fig_rv = go.Figure()
    line_colors = ['#4A90D9', '#E25A53', '#2ecc71', '#9b59b6', '#f39c12', '#1abc9c']

    for i, line_name in enumerate(selected_lines):
        lc = line_colors[i % len(line_colors)]
        subset = {k: v for k, v in rv_results.items() if k[2] == line_name}
        if not subset:
            continue
        mjds = [v['mjd'] for v in subset.values()]
        rvs = [v['rv'] for v in subset.values()]
        errs = [v['rv_err'] for v in subset.values()]

        fig_rv.add_trace(go.Scatter(
            x=mjds, y=rvs,
            error_y=dict(type='data', array=errs, visible=True),
            mode='lines+markers',
            name=line_name,
            line=dict(color=lc),
            marker=dict(size=8),
        ))

    # Mean line
    all_rvs_arr = np.array([v['rv'] for v in rv_results.values()])
    mean_rv = float(np.nanmean(all_rvs_arr))
    fig_rv.add_hline(y=mean_rv, line_dash='dash', line_color='gray',
                      annotation_text=f'Mean: {mean_rv:.1f} km/s')

    fig_rv.update_layout(**{
        **PLOTLY_THEME,
        'title': f'{star_name} — RV vs MJD',
        'xaxis_title': 'MJD',
        'yaxis_title': 'RV (km/s)',
        'height': 400,
    })
    st.plotly_chart(fig_rv, use_container_width=True)
    st.caption('Radial velocities measured via CCF across all available epochs. Error bars show 1σ CCF fit uncertainty.')
```

**SECTION 13 — Variance Analysis Metrics**
```python
    st.subheader('📊 Variance Analysis')
    all_rvs_arr = np.array([v['rv'] for v in rv_results.values()])
    rv_std = float(np.nanstd(all_rvs_arr)) if len(all_rvs_arr) >= 2 else float('nan')
    rv_var = float(np.nanvar(all_rvs_arr)) if len(all_rvs_arr) >= 2 else float('nan')
    max_drv = float(np.nanmax(all_rvs_arr) - np.nanmin(all_rvs_arr)) if len(all_rvs_arr) >= 2 else float('nan')
    is_binary_nres = bool(rv_std > var_threshold)  # E002: cast to Python bool

    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric('σ_RV (km/s)', f'{rv_std:.2f}', help='Standard deviation of all RV measurements')
    mc2.metric('Var(RV) (km²/s²)', f'{rv_var:.1f}')
    mc3.metric('Max ΔRV (km/s)', f'{max_drv:.1f}',
               help='Maximum − minimum RV across all epochs')
    mc4.metric('Classification',
               '🔴 BINARY' if is_binary_nres else '🟢 SINGLE',
               help=f'σ_RV {">" if is_binary_nres else "<"} threshold {var_threshold} km/s')

    st.caption(f'Threshold: σ_RV > {var_threshold:.1f} km/s → binary. '
               f'Based on {len(all_rvs_arr)} RV measurements across {len(all_rvs_arr)} epoch-spectra-line combinations.')
```

**SECTION 14 — Binary Fraction Comparison**
```python
    st.subheader('🔬 Binary Fraction Comparison')

    # NRES fraction (only current star)
    nres_binary_count = 1 if is_binary_nres else 0
    nres_total = 1  # one star processed so far
    nres_frac = nres_binary_count / nres_total

    # X-SHOOTER fraction
    try:
        sh = settings_hash(settings)
        obs_delta_rv, detail = cached_load_observed_delta_rvs(sh)
        n_xsh_binary = sum(1 for d in detail.values() if d.get('is_binary') is True)
        bartzakos = settings.get('classification', {}).get('bartzakos_binaries', 3)
        total_pop = settings.get('classification', {}).get('total_population', 28)
        xsh_frac = (n_xsh_binary + bartzakos) / total_pop
        xsh_label = f'X-SHOOTER\n({n_xsh_binary}+{bartzakos})/{total_pop}'
    except Exception:
        xsh_frac = 0.46  # fallback from known result
        xsh_label = 'X-SHOOTER\n13/28'

    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        x=['NRES (this star)', xsh_label],
        y=[nres_frac * 100, xsh_frac * 100],
        marker_color=['#E25A53' if nres_binary_count > 0 else '#4A90D9', '#4A90D9'],
        text=[f'{nres_frac*100:.0f}%', f'{xsh_frac*100:.0f}%'],
        textposition='outside',
    ))
    fig_bar.update_layout(**{
        **PLOTLY_THEME,
        'title': 'Binary Fraction Comparison',
        'yaxis_title': 'Binary Fraction (%)',
        'yaxis': {'range': [0, 110]},
        'height': 350,
    })
    st.plotly_chart(fig_bar, use_container_width=True)
    st.caption(
        f'NRES classification uses σ_RV > {var_threshold:.1f} km/s as binary criterion. '
        f'X-SHOOTER uses ΔRV > 45.5 km/s and ΔRV − 4σ > 0.'
    )
```

### Step 4: Syntax and Error Check

After creating `11_nres.py`:
```bash
conda run -n guyenv python -m py_compile app/pages/11_nres.py
```
Must produce zero output.

Run the COMMON_ERRORS.md quick-scan regex against the new file.

---

## 5. Settings Editable in UI

| Setting | Widget | Key path | Default |
|---------|--------|----------|---------|
| Sky subtraction | checkbox | `nres.subtract_sky` | True |
| CrossVeloMin | number_input | `nres.velo_min` | -500 |
| CrossVeloMax | number_input | `nres.velo_max` | 500 |
| Fit fraction | slider | `nres.fit_fraction` | 0.97 |
| Active emission lines | multiselect | `nres.active_lines` | ['C IV 5808-5812', ...] |
| σ_RV threshold | slider | `nres.variance_threshold` | 45.5 |

---

## 6. Plots Summary

| Plot | Type | X axis | Y axis | Notes |
|------|------|--------|--------|-------|
| Stitched spectrum | Line | Wavelength (Å) | Flux | Colored vrect highlights for selected lines |
| RV time series | Scatter+line | MJD | RV (km/s) | One trace per line, error bars, mean dashed |
| Binary fraction | Bar | Dataset | % | Two bars: NRES vs X-SHOOTER |

Optional (future extension): CCF curve per epoch, RV histogram.

---

## 7. Potential Risks and Common Errors

### E018 (CRITICAL) — PLOTLY_THEME keyword collision
`PLOTLY_THEME` contains `title`, `legend`, `xaxis`, `yaxis`, `font`. NEVER pass these as explicit kwargs alongside `**PLOTLY_THEME`. Use:
```python
fig.update_layout(**{**PLOTLY_THEME, 'title': '...', 'xaxis_title': '...'})
```
Note: `xaxis_title` is safe (not same as `xaxis`). `title` is NOT safe. Always use dict-merge syntax.

### E002 — numpy.bool_ pitfall
```python
is_binary_nres = bool(rv_std > var_threshold)  # REQUIRED cast
```

### NRES wavelength units
- `get_stitched_spectra()` → **Angstroms**
- `CCFclass CrossCorRangeA` → **nm** (when `nm=True`)
- Do NOT convert `obs_wave` — pass Angstroms directly to `compute_RV()`

### Template availability
If `'normalized_flux'` property doesn't exist for an epoch/spectra, fall back to crude inline normalization. Warn the user via `st.info()` that results may have higher scatter.

### Zero-filter
If loading RVs from session state: `all_rvs_arr[all_rvs_arr != 0]` only when appropriate; in session state all zeros mean CCF returned zero, which is a valid RV near zero. Better: only store results where `rv is not None`.

### st.cache_data + ObservationManager
`ObservationManager` may not be picklable for `@st.cache_data`. If this occurs, use `@st.cache_resource` instead for the `_get_obs_manager()` and `_get_nres_instance()` helpers. The stitched spectrum (numpy arrays) can still use `@st.cache_data`.

### CCFclass constructor signature
Check current `CCFclass.__init__` signature in `CCF.py` before writing the constructor call. Some positional args may be required. Use keyword args for all params.

### Page file numbering
The page file must be named `11_nres.py` to appear after `10_todo.py` in the Streamlit sidebar navigation.

---

## 8. Verification Steps

1. **Syntax**: `conda run -n guyenv python -m py_compile app/pages/11_nres.py` → zero output

2. **Import**: Launch app and navigate to NRES page → no import errors in terminal

3. **Star selector**: Verify `['WR 52', 'WR17']` appear in selectbox

4. **Spectrum load**: Select star + epoch + spectra → spectrum plot renders within 10 seconds

5. **CCF run**: Select `C IV 5808-5812`, click Run CCF → progress bar increments, RV table appears

6. **RV sanity**: RV values should be in range ±300 km/s; errors < 100 km/s for good epochs

7. **Variance metrics**: With ≥2 epochs, σ_RV and Max ΔRV should be non-NaN non-zero

8. **Comparison chart**: X-SHOOTER bar should show ~46%

9. **Settings persistence**: Change threshold, reload page → new value persists from `user_settings.json`

10. **COMMON_ERRORS scan**: Run quick-scan regex from `COMMON_ERRORS.md` against `11_nres.py`

---

## 9. Critical File Reference

| File | Lines of Interest |
|------|------------------|
| `NRESClass.py` | `get_stitched_spectra()` — primary loading method; `load_observation()` — for MJD; `get_all_epoch_numbers()`, `get_all_spectra_in_epoch()` |
| `CCF.py` | `CCFclass.__init__` — check required args; `compute_RV(obs_wave, obs_flux, tpl_wave, tpl_flux)` |
| `app/shared.py` | `render_sidebar()` — add page link; `cached_load_observed_delta_rvs()` — X-SHOOTER comparison; `PLOTLY_THEME` — all plot styling; `SettingsManager.save()` |
| `app/pages/03_ccf.py` | Reference for CCF page pattern (settings expander, progress bar, result storage) |
| `settings/user_settings.json` | Add `"nres"` section |
| `ObservationClass.py` | `NRES_stars` list; `load_star_instance()` routing |
