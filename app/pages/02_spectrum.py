"""
pages/02_spectrum.py — Spectrum Browser
Interactive Plotly spectrum viewer with epoch overlay and RV annotations.
"""
from __future__ import annotations
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from shared import inject_theme, render_sidebar, get_settings_manager, get_obs_manager, PLOTLY_THEME
import specs

st.set_page_config(page_title='Spectrum — WR Binary', page_icon='📊', layout='wide')
inject_theme()
settings = render_sidebar('Spectrum')
sm = get_settings_manager()

st.markdown('# 📊 Spectrum Browser')

# ── Star / epoch / band selectors ────────────────────────────────────────────
ui_cfg = settings.get('ui', {})
col1, col2, col3 = st.columns([2, 1, 1])

star_names   = specs.star_names
default_star = ui_cfg.get('last_star', star_names[0])
if default_star not in star_names:
    default_star = star_names[0]

star_name = col1.selectbox(
    'Star', star_names, index=star_names.index(default_star),
    key='spec_star',
    on_change=lambda: sm.save(['ui', 'last_star'], value=st.session_state['spec_star'])
)

BANDS = ['COMBINED', 'UVB', 'VIS', 'NIR']
default_band = ui_cfg.get('last_band', 'COMBINED')
band = col3.selectbox(
    'Band', BANDS, index=BANDS.index(default_band) if default_band in BANDS else 0,
    key='spec_band',
    on_change=lambda: sm.save(['ui', 'last_band'], value=st.session_state['spec_band'])
)

# ── Load star ─────────────────────────────────────────────────────────────────
@st.cache_data
def _get_epochs(star_name: str) -> list[int]:
    obs  = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    return star.get_all_epoch_numbers()

obs  = get_obs_manager()
star = obs.load_star_instance(star_name, to_print=False)
epochs = star.get_all_epoch_numbers()

if not epochs:
    st.warning(f'No epochs found for {star_name}.')
    st.stop()

default_ep = ui_cfg.get('last_epoch', epochs[0])
if default_ep not in epochs:
    default_ep = epochs[0]

epoch = col2.selectbox(
    'Epoch', epochs, index=epochs.index(default_ep),
    key='spec_epoch',
    on_change=lambda: sm.save(['ui', 'last_epoch'], value=st.session_state['spec_epoch'])
)

# ── Load spectrum ─────────────────────────────────────────────────────────────
@st.cache_data
def _load_spectrum(star_name: str, epoch: int, band: str):
    obs  = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    data = star.load_property('normalized_flux', epoch, band)
    if data is None:
        # fallback: try cleaned_normalized_flux
        data = star.load_property('cleaned_normalized_flux', epoch, band)
    return data

@st.cache_data
def _load_rvs(star_name: str, epoch: int):
    obs  = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    return star.load_property('RVs', epoch, 'COMBINED')

@st.cache_data
def _get_mjd(star_name: str, epoch: int) -> float | None:
    obs  = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    for b in ['NIR', 'VIS', 'UVB']:
        try:
            fit = star.load_observation(epoch, band=b)
            return float(fit.header['MJD-OBS'])
        except Exception:
            pass
    return None

data   = _load_spectrum(star_name, epoch, band)
rv_prop = _load_rvs(star_name, epoch)
mjd    = _get_mjd(star_name, epoch)

# ── Overlay second epoch ─────────────────────────────────────────────────────
overlay_ep = st.checkbox('Overlay another epoch for comparison')
overlay_data = None
if overlay_ep and len(epochs) > 1:
    other_eps = [e for e in epochs if e != epoch]
    ep2 = st.selectbox('Overlay epoch', other_eps, key='spec_overlay_ep')
    overlay_data = _load_spectrum(star_name, ep2, band)

# ── Plot ─────────────────────────────────────────────────────────────────────
fig = go.Figure()

if data is not None:
    wave = np.asarray(data.get('wavelengths', data.get('wave', [])))
    flux = np.asarray(data.get('normalized_flux', data.get('flux', [])))
    if len(wave) > 0:
        mjd_str = f'  MJD {mjd:.2f}' if mjd else ''
        fig.add_trace(go.Scatter(
            x=wave, y=flux, mode='lines',
            line=dict(color='#4A90D9', width=1.2),
            name=f'Epoch {epoch}{mjd_str}',
        ))
else:
    st.info(f'No normalized spectrum for {star_name} epoch {epoch} band {band}.')

if overlay_data is not None:
    w2 = np.asarray(overlay_data.get('wavelengths', overlay_data.get('wave', [])))
    f2 = np.asarray(overlay_data.get('normalized_flux', overlay_data.get('flux', [])))
    if len(w2) > 0:
        mjd2 = _get_mjd(star_name, ep2)
        mjd_str2 = f'  MJD {mjd2:.2f}' if mjd2 else ''
        fig.add_trace(go.Scatter(
            x=w2, y=f2, mode='lines',
            line=dict(color='#E25A53', width=1.0, dash='dot'),
            name=f'Epoch {ep2}{mjd_str2}',
        ))

# ── Emission line overlays ────────────────────────────────────────────────────
em_lines = settings.get('emission_lines', {})
show_lines = st.checkbox('Show emission line bands', value=True, key='spec_show_lines')
if show_lines and em_lines and data is not None:
    for line_name, rng in em_lines.items():
        if isinstance(rng, (list, tuple)) and len(rng) == 2:
            lo, hi = float(rng[0]) * 10, float(rng[1]) * 10   # nm → Å
            fig.add_vrect(x0=lo, x1=hi,
                          fillcolor='rgba(255,215,0,0.08)',
                          line_width=0.5, line_color='gold',
                          annotation_text=line_name, annotation_position='top left',
                          annotation=dict(font_size=9, font_color='gold'))

# ── RV annotation ─────────────────────────────────────────────────────────────
primary_line = settings.get('primary_line', 'C IV 5808-5812')
if rv_prop and primary_line in rv_prop:
    entry = rv_prop[primary_line]
    if hasattr(entry, 'item'):
        entry = entry.item()
    rv_val  = entry.get('full_RV',     None)
    err_val = entry.get('full_RV_err', None)
    if rv_val is not None:
        st.info(f'RV ({primary_line}): **{rv_val:.1f} ± {err_val:.1f} km/s**  (epoch {epoch})')

fig.update_layout(
    xaxis_title='Wavelength (Å)', yaxis_title='Normalised flux',
    title=f'{star_name}  —  Epoch {epoch}  —  {band}',
    **PLOTLY_THEME, height=500,
    legend=dict(bgcolor='rgba(255,255,255,0.85)'),
)
st.plotly_chart(fig, use_container_width=True)

# ── RV table for this star (all epochs, primary line) ─────────────────────────
st.markdown('### RV measurements (primary line)')
rv_rows = []
for ep in epochs:
    rv_p = _load_rvs(star_name, ep)
    if rv_p and primary_line in rv_p:
        entry = rv_p[primary_line]
        if hasattr(entry, 'item'):
            entry = entry.item()
        rv_rows.append({
            'Epoch': ep,
            'RV (km/s)': round(float(entry.get('full_RV', 0)), 2),
            'Error (km/s)': round(float(entry.get('full_RV_err', 0)), 2),
            'MJD': _get_mjd(star_name, ep) or '—',
        })

if rv_rows:
    import pandas as pd
    st.dataframe(pd.DataFrame(rv_rows), use_container_width=True)
else:
    st.info('No RV data saved for this star on the primary line.')
