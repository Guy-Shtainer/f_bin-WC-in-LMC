"""
pages/03_ccf.py — CCF Analysis
Run cross-correlation on one star or all 25, show results and link to output plots.
"""
from __future__ import annotations
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st
import pandas as pd
import numpy as np

from shared import inject_theme, render_sidebar, get_settings_manager, get_obs_manager
import specs

st.set_page_config(page_title='CCF — WR Binary', page_icon='🔄', layout='wide')
inject_theme()
settings = render_sidebar('CCF')
sm       = get_settings_manager()

st.markdown('# 🔄 CCF Analysis')
st.markdown(
    'Cross-correlation (Zucker & Mazeh 1994 / Zucker et al. 2003) of observed spectra '
    'vs emission-line templates to extract per-epoch radial velocities.'
)

# ── CCF settings ─────────────────────────────────────────────────────────────
with st.expander('⚙️ CCF settings', expanded=True):
    ccf_cfg = settings.get('ccf', {})
    col1, col2, col3 = st.columns(3)
    vmin = col1.number_input(
        'CrossVeloMin (km/s)', value=int(ccf_cfg.get('CrossVeloMin', -2000)),
        step=100, key='ccf_vmin',
        on_change=lambda: sm.save(['ccf', 'CrossVeloMin'], value=st.session_state['ccf_vmin'])
    )
    vmax = col2.number_input(
        'CrossVeloMax (km/s)', value=int(ccf_cfg.get('CrossVeloMax', 2000)),
        step=100, key='ccf_vmax',
        on_change=lambda: sm.save(['ccf', 'CrossVeloMax'], value=st.session_state['ccf_vmax'])
    )
    fit_frac = col3.slider(
        'Fit fraction', 0.5, 1.0,
        float(ccf_cfg.get('fit_fraction_default', 0.97)), step=0.01,
        key='ccf_fit_frac',
        on_change=lambda: sm.save(['ccf', 'fit_fraction_default'], value=st.session_state['ccf_fit_frac'])
    )

    # Emission line selector
    em_lines = list(settings.get('emission_lines', {}).keys())
    primary  = settings.get('primary_line', 'C IV 5808-5812')
    default_sel = [primary] if primary in em_lines else (em_lines[:1] if em_lines else [])
    selected_lines = st.multiselect('Emission lines to run CCF on', em_lines,
                                    default=default_sel, key='ccf_lines')

# ── Target: single star or all ────────────────────────────────────────────────
st.markdown('### Run CCF')
run_mode = st.radio('Target', ['Single star', 'All 25 stars'], horizontal=True)
if run_mode == 'Single star':
    ui_cfg     = settings.get('ui', {})
    star_names = specs.star_names
    default_st = ui_cfg.get('last_star', star_names[0])
    if default_st not in star_names:
        default_st = star_names[0]
    target_star = st.selectbox('Star', star_names,
                               index=star_names.index(default_st), key='ccf_target_star')
    targets = [target_star]
else:
    targets = specs.star_names

# ── Output folder ─────────────────────────────────────────────────────────────
output_root = os.path.normpath(os.path.join(_ROOT, '..', 'output'))
st.info(f'CCF plots will be saved to `{output_root}/{{star}}/CCF/{{timestamp}}/{{line}}/`')

# ── Run button ────────────────────────────────────────────────────────────────
st.warning(
    '⚠️ The CCF runner calls the existing `CCFclass` (CCF.py) which requires '
    'the spectrum to be already loaded and normalized. '
    'This page provides a launcher interface — the actual CCF is performed via '
    'your existing `NRESClass` / `StarClass` `.run_CCF()` method. '
    'Click "Run CCF" to proceed.'
)

if st.button('▶️ Run CCF', type='primary'):
    progress = st.progress(0, text='Starting …')
    results  = []
    obs      = get_obs_manager()

    for idx, star_name in enumerate(targets):
        progress.progress((idx) / len(targets), text=f'Processing {star_name} …')
        try:
            star   = obs.load_star_instance(star_name, to_print=False)
            epochs = star.get_all_epoch_numbers()
            for ep in epochs:
                for line in selected_lines:
                    try:
                        # Use existing run_CCF method if available
                        if hasattr(star, 'run_CCF'):
                            rv, err = star.run_CCF(
                                ep, line,
                                CrossVeloMin=vmin,
                                CrossVeloMax=vmax,
                                fit_fraction=fit_frac,
                            )
                            results.append({
                                'Star': star_name,
                                'Epoch': ep,
                                'Line': line,
                                'RV (km/s)': round(float(rv), 2),
                                'Error (km/s)': round(float(err), 2),
                            })
                    except Exception as e:
                        results.append({
                            'Star': star_name,
                            'Epoch': ep,
                            'Line': line,
                            'RV (km/s)': '—',
                            'Error (km/s)': f'ERROR: {e}',
                        })
        except Exception as e:
            results.append({'Star': star_name, 'Epoch': '—', 'Line': '—',
                            'RV (km/s)': '—', 'Error (km/s)': str(e)})

    progress.progress(1.0, text='Done.')
    st.success(f'CCF complete: {len(results)} measurements.')
    if results:
        st.dataframe(pd.DataFrame(results), use_container_width=True)

# ── Show existing CCF output plots ────────────────────────────────────────────
st.markdown('---')
st.markdown('### Existing CCF plots')
if os.path.isdir(output_root):
    # collect all PNG files in output/<star>/CCF/
    png_files = []
    for star_name in specs.star_names:
        ccf_dir = os.path.join(output_root, star_name, 'CCF')
        if os.path.isdir(ccf_dir):
            for dirpath, _, fnames in os.walk(ccf_dir):
                for fn in fnames:
                    if fn.lower().endswith('.png'):
                        png_files.append(os.path.join(dirpath, fn))

    if png_files:
        star_filter = st.selectbox('Filter by star', ['All'] + specs.star_names,
                                   key='ccf_plot_star_filter')
        filtered = png_files
        if star_filter != 'All':
            filtered = [p for p in png_files if star_filter in p]

        st.write(f'{len(filtered)} plots found.')
        cols = st.columns(3)
        for i, path in enumerate(filtered[:12]):   # show first 12
            cols[i % 3].image(path, caption=os.path.relpath(path, output_root), use_column_width=True)
        if len(filtered) > 12:
            st.info(f'Showing first 12 of {len(filtered)}. Navigate output/ folder for more.')
    else:
        st.info('No CCF PNG plots found in output/ yet.')
else:
    st.info(f'Output directory not found: `{output_root}`')
