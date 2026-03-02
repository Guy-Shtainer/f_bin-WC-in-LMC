"""
pages/04_classification.py — Live Classification Explorer
Adjust threshold and sigma_factor; table re-classifies in real time.
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
import plotly.graph_objects as go
import streamlit as st

from shared import (
    inject_theme, render_sidebar, get_settings_manager,
    cached_load_observed_delta_rvs, settings_hash,
    COLOR_BINARY, COLOR_SINGLE, COLOR_UNKNOWN,
    PLOTLY_THEME,
)
import specs

st.set_page_config(page_title='Classification — WR Binary', page_icon='🎯', layout='wide')
inject_theme()
settings = render_sidebar('Classification')
sm = get_settings_manager()

st.markdown('# 🎯 Live Binary Classification')

# ── Controls ─────────────────────────────────────────────────────────────────
cls_cfg = settings.get('classification', {})
bartzakos = cls_cfg.get('bartzakos_binaries', 3)
total_pop = cls_cfg.get('total_population',  28)

col1, col2 = st.columns(2)
threshold = col1.slider(
    'ΔRV threshold (km/s)', 10.0, 200.0,
    float(cls_cfg.get('threshold_dRV', 45.5)), step=0.5,
    key='cls_threshold',
    on_change=lambda: sm.save(['classification', 'threshold_dRV'],
                               value=st.session_state['cls_threshold'])
)
sigma_factor = col2.slider(
    'Sigma factor', 1.0, 10.0,
    float(cls_cfg.get('sigma_factor', 4.0)), step=0.1,
    key='cls_sigma',
    on_change=lambda: sm.save(['classification', 'sigma_factor'],
                               value=st.session_state['cls_sigma'])
)
st.caption(
    f'Binary criteria: ΔRV > {threshold:.1f} km/s  **AND**  '
    f'ΔRV − {sigma_factor:.1f}·σ > 0'
)
st.info(
    f'Note: {bartzakos} additional confirmed binaries from Bartzakos (2001) '
    f'are always added.  Total population = {total_pop} WC stars in LMC.'
)

# ── Load data ─────────────────────────────────────────────────────────────────
sh = settings_hash(settings)
with st.spinner('Loading data …'):
    try:
        obs_delta_rv, detail = cached_load_observed_delta_rvs(sh)
    except Exception as e:
        st.error(str(e))
        st.stop()

# ── Classify with live sliders ────────────────────────────────────────────────
rows = []
for star_name in specs.star_names:
    d     = detail.get(star_name, {})
    drv   = d.get('best_dRV', 0.0)
    sigma = d.get('best_sigma', float('nan'))
    n_ep  = len(d.get('rv', []))

    if n_ep >= 2:
        sigma_val = float(sigma) if sigma and not math.isnan(sigma) else 0.0
        live_bin  = bool(drv > threshold and (drv - sigma_factor * sigma_val) > 0)
    else:
        live_bin = None

    rows.append({
        'Star': star_name,
        'ΔRV (km/s)': round(drv, 1),
        'σ (km/s)':  round(float(sigma), 1) if sigma and not math.isnan(sigma) else '—',
        'Significance': round(drv / sigma, 1) if (sigma and not math.isnan(sigma) and sigma > 0) else '—',
        'Status': ('✓ BINARY' if live_bin is True else ('? NO DATA' if live_bin is None else '✗ single')),
        'Epochs': n_ep,
        '_bin': live_bin,
    })

n_bin = sum(1 for r in rows if r['_bin'] is True)
obs_frac = (n_bin + bartzakos) / total_pop

# ── Summary metrics ───────────────────────────────────────────────────────────
c1, c2, c3 = st.columns(3)
c1.metric('Detected binaries', n_bin)
c2.metric('Observed fraction', f'{obs_frac*100:.1f}%',
          f'({n_bin}+{bartzakos})/{total_pop}')
c3.metric('Binary fraction threshold', f'{threshold:.1f} km/s')

# ── Table ─────────────────────────────────────────────────────────────────────
df = pd.DataFrame(rows).drop(columns=['_bin'])

def _style_row(row):
    if 'BINARY' in row['Status']:
        return [f'color: {COLOR_BINARY}; font-weight: 600'] * len(row)
    if 'single' in row['Status']:
        return [f'color: {COLOR_SINGLE}'] * len(row)
    return [f'color: {COLOR_UNKNOWN}'] * len(row)

styled = df.style.apply(_style_row, axis=1)
st.dataframe(styled, use_container_width=True, height=500)

# ── Histogram ─────────────────────────────────────────────────────────────────
st.markdown('### ΔRV distribution')
drvs_valid = [r['ΔRV (km/s)'] for r in rows if r['Epochs'] >= 2]
bins = np.linspace(0, max(drvs_valid) + 20, 30) if drvs_valid else np.linspace(0, 200, 30)

fig = go.Figure()
bin_vals = [v for v in drvs_valid if v > threshold]
sing_vals = [v for v in drvs_valid if v <= threshold]

fig.add_trace(go.Histogram(x=sing_vals, xbins=dict(start=bins[0], end=bins[-1],
              size=float(bins[1]-bins[0])), marker_color=COLOR_SINGLE,
              name='Single', opacity=0.75))
fig.add_trace(go.Histogram(x=bin_vals, xbins=dict(start=bins[0], end=bins[-1],
              size=float(bins[1]-bins[0])), marker_color=COLOR_BINARY,
              name='Binary', opacity=0.75))
fig.add_vline(x=threshold, line_dash='dash', line_color='gold',
              annotation_text=f'Threshold {threshold:.1f} km/s',
              annotation_position='top right')
fig.update_layout(
    barmode='overlay',
    xaxis_title='ΔRV (km/s)', yaxis_title='Count',
    **PLOTLY_THEME, height=380,
)
st.plotly_chart(fig, use_container_width=True)

# ── Binary fraction vs threshold curve ───────────────────────────────────────
st.markdown('### Binary fraction vs threshold')
thresholds = np.linspace(10, 200, 191)
fracs = []
for th in thresholds:
    n = sum(1 for r in rows if r['Epochs'] >= 2 and r['ΔRV (km/s)'] > th)
    fracs.append((n + bartzakos) / total_pop * 100)

fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=thresholds, y=fracs, mode='lines',
                          line=dict(color='#4A90D9', width=2), name='Obs. fraction'))
fig2.add_vline(x=threshold, line_dash='dash', line_color='gold',
               annotation_text=f'Current: {threshold:.1f} km/s',
               annotation_position='top right')
fig2.update_layout(
    xaxis_title='ΔRV threshold (km/s)', yaxis_title='Binary fraction (%)',
    **PLOTLY_THEME, height=350,
)
st.plotly_chart(fig2, use_container_width=True)
