"""
pages/07_tables.py — Tables
ΔRV Dashboard × all emission lines, observation metadata, barycentric velocities.
"""
from __future__ import annotations
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import math
import numpy as np
import pandas as pd
import streamlit as st

from shared import (
    inject_theme, render_sidebar, get_settings_manager,
    get_obs_manager, COLOR_BINARY, COLOR_SINGLE, COLOR_UNKNOWN,
)
import specs

st.set_page_config(page_title='Tables — WR Binary', page_icon='📋', layout='wide')
inject_theme()
settings = render_sidebar('Tables')
sm = get_settings_manager()

st.markdown('# 📋 Data Tables')

tab_drv, tab_meta, tab_bary = st.tabs(
    ['ΔRV Dashboard', 'Observation Metadata', 'Barycentric Velocity']
)

# ─────────────────────────────────────────────────────────────────────────────
# ΔRV Dashboard
# ─────────────────────────────────────────────────────────────────────────────
with tab_drv:
    st.markdown('### ΔRV per star × emission line')
    st.caption('Max peak-to-peak ΔRV from saved RV measurements.  '
               'Red = exceeds current threshold (binary candidate).')

    cls_cfg   = settings.get('classification', {})
    threshold = st.slider('ΔRV threshold (km/s)', 10.0, 200.0,
                          float(cls_cfg.get('threshold_dRV', 45.5)), 0.5,
                          key='tbl_threshold',
                          on_change=lambda: sm.save(['classification', 'threshold_dRV'],
                                                     value=st.session_state['tbl_threshold']))

    @st.cache_data
    def _load_all_rvs() -> dict:
        """Load all RV measurements for all stars, all lines."""
        from pipeline.load_observations import load_star_rvs_all_lines
        obs   = get_obs_manager()
        data  = {}
        for sn in specs.star_names:
            try:
                data[sn] = load_star_rvs_all_lines(sn, obs)
            except Exception:
                data[sn] = {}
        return data

    with st.spinner('Loading all RV measurements …'):
        all_rv_data = _load_all_rvs()

    # Get all unique line names
    all_lines = sorted({line for star_data in all_rv_data.values() for line in star_data.keys()})

    if not all_lines:
        st.info('No RV data found in the data directory.')
    else:
        rows = []
        for sn in specs.star_names:
            row = {'Star': sn}
            for line in all_lines:
                ld = all_rv_data.get(sn, {}).get(line)
                if ld and len(ld['rv']) >= 2:
                    rvs = np.array(ld['rv'])
                    row[line] = round(float(np.max(rvs) - np.min(rvs)), 1)
                else:
                    row[line] = None
            rows.append(row)

        df = pd.DataFrame(rows)

        def _color_cell(val):
            if val is None or (isinstance(val, float) and math.isnan(val)):
                return 'color: #8C8C8C'
            if isinstance(val, (int, float)) and val > threshold:
                return f'color: {COLOR_BINARY}; font-weight: 600'
            return f'color: {COLOR_SINGLE}'

        # Apply styling to all line columns
        line_cols = [c for c in df.columns if c != 'Star']
        styled = df.style.applymap(_color_cell, subset=line_cols)

        # Format: show — for None
        fmt = {c: lambda x: f'{x:.1f}' if isinstance(x, (int, float)) and not math.isnan(x) else '—'
               for c in line_cols}
        styled = styled.format(fmt)

        st.dataframe(styled, use_container_width=True, height=600)

        # Download
        csv = df.to_csv(index=False)
        st.download_button('📥 Download CSV', csv, 'drv_dashboard.csv', 'text/csv')

        bartzakos = cls_cfg.get('bartzakos_binaries', 3)
        total_pop = cls_cfg.get('total_population', 28)
        primary   = settings.get('primary_line', 'C IV 5808-5812')
        if primary in line_cols:
            n_bin = sum(1 for r in rows
                        if isinstance(r.get(primary), (int, float)) and r[primary] > threshold)
            st.markdown(
                f'**{primary}**: {n_bin} binary candidates  →  '
                f'({n_bin}+{bartzakos})/{total_pop} = **{(n_bin+bartzakos)/total_pop*100:.1f}%**'
            )

# ─────────────────────────────────────────────────────────────────────────────
# Observation Metadata
# ─────────────────────────────────────────────────────────────────────────────
with tab_meta:
    st.markdown('### Observation metadata (MJD, instrument, epochs)')

    @st.cache_data
    def _load_metadata() -> pd.DataFrame:
        obs   = get_obs_manager()
        rows  = []
        for sn in specs.star_names:
            try:
                star   = obs.load_star_instance(sn, to_print=False)
                epochs = star.get_all_epoch_numbers()
                for ep in epochs:
                    mjd = None
                    for bd in ['NIR', 'VIS', 'UVB']:
                        try:
                            fit = star.load_observation(ep, band=bd)
                            mjd = float(fit.header['MJD-OBS'])
                            break
                        except Exception:
                            pass
                    rows.append({
                        'Star': sn,
                        'Epoch': ep,
                        'MJD': round(mjd, 4) if mjd else '—',
                    })
            except Exception as e:
                rows.append({'Star': sn, 'Epoch': '—', 'MJD': str(e)})
        return pd.DataFrame(rows)

    with st.spinner('Loading metadata …'):
        meta_df = _load_metadata()

    st.dataframe(meta_df, use_container_width=True, height=500)
    csv2 = meta_df.to_csv(index=False)
    st.download_button('📥 Download CSV', csv2, 'observation_metadata.csv', 'text/csv')

# ─────────────────────────────────────────────────────────────────────────────
# Barycentric Velocity
# ─────────────────────────────────────────────────────────────────────────────
with tab_bary:
    st.markdown('### Barycentric velocity per epoch (wide format)')
    st.caption('Loaded from FITS headers (HIERARCH ESO QC BARY CORR or similar key).')

    @st.cache_data
    def _load_bary() -> pd.DataFrame:
        obs   = get_obs_manager()
        rows  = {}
        all_eps: set = set()
        for sn in specs.star_names:
            rows[sn] = {}
            try:
                star   = obs.load_star_instance(sn, to_print=False)
                epochs = star.get_all_epoch_numbers()
                for ep in epochs:
                    all_eps.add(ep)
                    for bd in ['NIR', 'VIS', 'UVB']:
                        try:
                            fit = star.load_observation(ep, band=bd)
                            hdr = fit.header
                            # Try various FITS keys for barycentric correction
                            for key in ['HIERARCH ESO QC BARY CORR', 'BARY_CORR',
                                        'BARYCORR', 'VHELIO', 'VBARY']:
                                if key in hdr:
                                    rows[sn][ep] = round(float(hdr[key]), 3)
                                    break
                            break
                        except Exception:
                            pass
            except Exception:
                pass
        eps = sorted(all_eps)
        table = {'Star': list(rows.keys())}
        for ep in eps:
            table[f'Ep {ep}'] = [rows[sn].get(ep, '—') for sn in rows.keys()]
        return pd.DataFrame(table)

    with st.spinner('Loading barycentric velocities …'):
        bary_df = _load_bary()

    st.dataframe(bary_df, use_container_width=True, height=500)
    csv3 = bary_df.to_csv(index=False)
    st.download_button('📥 Download CSV', csv3, 'barycentric_velocity.csv', 'text/csv')
