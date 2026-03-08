"""
pages/01_stars.py — Star Overview
Sortable/filterable table, live threshold re-classification, link to spectrum page.
"""
from __future__ import annotations
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from shared import (
    inject_theme, render_sidebar, get_settings_manager,
    cached_load_observed_delta_rvs, settings_hash,
    COLOR_BINARY, COLOR_SINGLE, COLOR_UNKNOWN,
    PLOTLY_THEME,
)
import specs

st.set_page_config(page_title='Stars — WR Binary', page_icon='⭐', layout='wide')
inject_theme()
settings = render_sidebar('Stars')
sm = get_settings_manager()

st.markdown('# ⭐ Star Overview')

# ── Live threshold controls ───────────────────────────────────────────────────
with st.expander('⚙️ Classification settings', expanded=False):
    cls_cfg = settings.get('classification', {})
    col1, col2 = st.columns(2)
    threshold = col1.slider(
        'ΔRV threshold (km/s)', 10.0, 200.0,
        float(cls_cfg.get('threshold_dRV', 45.5)), step=0.5,
        key='stars_threshold',
        on_change=lambda: sm.save(['classification', 'threshold_dRV'],
                                   value=st.session_state['stars_threshold']))
    sigma_factor = col2.slider(
        'Sigma factor', 1.0, 10.0,
        float(cls_cfg.get('sigma_factor', 4.0)), step=0.1,
        key='stars_sigma_factor',
        on_change=lambda: sm.save(['classification', 'sigma_factor'],
                                   value=st.session_state['stars_sigma_factor']))

# ── Load data ─────────────────────────────────────────────────────────────────
sh = settings_hash(settings)
with st.spinner('Loading classifications …'):
    try:
        obs_delta_rv, detail = cached_load_observed_delta_rvs(sh)
    except Exception as e:
        st.error(f'Could not load data: {e}')
        st.stop()

cls_cfg   = settings.get('classification', {})
bartzakos = cls_cfg.get('bartzakos_binaries', 3)
total_pop = cls_cfg.get('total_population', 28)

# ── Build table ───────────────────────────────────────────────────────────────
rows = []
for star_name in specs.star_names:
    d      = detail.get(star_name, {})
    is_bin = d.get('is_binary')
    drv    = d.get('best_dRV', 0.0)
    sigma  = d.get('best_sigma', float('nan'))
    sig_val = drv / sigma if (sigma and sigma > 0 and not np.isnan(sigma)) else float('nan')
    n_ep   = len(d.get('rv', []))

    # live reclassification using current slider values
    if n_ep >= 2:
        live_bin = bool(drv > threshold and (drv - sigma_factor * (sigma or 0)) > 0)
    else:
        live_bin = None

    if live_bin is True:
        status = '✓ BINARY'
    elif live_bin is None:
        status = '? NO DATA'
    else:
        status = '✗ single'

    rows.append({
        'Star': star_name,
        'Status': status,
        'ΔRV (km/s)': round(drv, 1),
        'Σ (km/s)': round(float(sigma), 1) if not (np.isnan(sigma) if isinstance(sigma, float) else False) else float('nan'),
        'Sig. (σ)': round(sig_val, 1) if not np.isnan(sig_val) else float('nan'),
        'Epochs': n_ep,
        '_is_binary': live_bin,
    })

df = pd.DataFrame(rows)
n_bin = sum(1 for r in rows if r['_is_binary'] is True)
n_unk = sum(1 for r in rows if r['_is_binary'] is None)

# ── Filter widget ─────────────────────────────────────────────────────────────
filter_opt = st.radio('Show', ['All', 'Binary only', 'Single only', 'No data'],
                      horizontal=True, key='stars_filter')
fmap = {'Binary only': True, 'Single only': False, 'No data': None}
if filter_opt != 'All':
    df = df[df['_is_binary'] == fmap[filter_opt]]

display_df = df.drop(columns=['_is_binary'])

def _style_status(val):
    if 'BINARY' in str(val):
        return f'color: {COLOR_BINARY}; font-weight: 600'
    if 'single' in str(val):
        return f'color: {COLOR_SINGLE}'
    return f'color: {COLOR_UNKNOWN}'

styled = (
    display_df.style
    .map(_style_status, subset=['Status'])
    .format({'ΔRV (km/s)': '{:.1f}', 'Σ (km/s)': lambda x: f'{x:.1f}' if not (isinstance(x, float) and np.isnan(x)) else '—',
             'Sig. (σ)': lambda x: f'{x:.1f}' if not (isinstance(x, float) and np.isnan(x)) else '—'})
)
st.dataframe(styled, use_container_width=True, height=520)

# ── Summary ───────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)
c1.metric('Binary (live)', n_bin)
c2.metric('Single (live)', len(specs.star_names) - n_bin - n_unk)
c3.metric('No data', n_unk)
c4.metric('Obs. fraction', f'{(n_bin+bartzakos)/total_pop*100:.1f}%',
          f'({n_bin}+{bartzakos})/{total_pop}')

# ── ΔRV bar chart ─────────────────────────────────────────────────────────────
st.markdown('### ΔRV per star')
full_rows = [r for r in rows if r['Epochs'] >= 2]
if full_rows:
    names = [r['Star'] for r in full_rows]
    drvs  = [r['ΔRV (km/s)'] for r in full_rows]
    colors = [COLOR_BINARY if r['_is_binary'] else COLOR_SINGLE for r in full_rows]

    fig = go.Figure(go.Bar(x=names, y=drvs, marker_color=colors, name='ΔRV'))
    fig.add_hline(y=threshold, line_dash='dash', line_color='gold',
                  annotation_text=f'Threshold {threshold:.1f} km/s')
    fig.update_layout(
        xaxis_title='Star', yaxis_title='ΔRV (km/s)',
        **PLOTLY_THEME, height=420,
        xaxis_tickangle=-45,
    )
    st.plotly_chart(fig, use_container_width=True)
