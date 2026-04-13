"""
spectrum_app/app.py — Standalone Spectrum Browser
Entry point with star/epoch/band selectors, binary classification banner,
and tab dispatch to spectrum_viewer, max_drv, and classification tabs.
State persistence via SettingsManager under 'ui_spectrum' namespace.
"""
from __future__ import annotations

import os
import sys

# ── Path setup ───────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# Add app/ for spectrum_helpers imports
_APP_DIR = os.path.join(_ROOT, 'app')
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

import numpy as np
import streamlit as st

import specs
from shared_lite import (inject_theme, get_settings_manager, get_obs_manager,
                         COLOR_BINARY, COLOR_SINGLE, COLOR_UNKNOWN, COLOR_CLEANED)
from helpers.data_loaders import classify_star_line, is_star_cleaned, get_peak_to_peak_epochs
from tabs import spectrum_viewer, max_drv, classification

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title='Spectrum Browser', page_icon='📊', layout='wide')
inject_theme()
sm = get_settings_manager()
settings = sm.load()

primary_line = settings.get('primary_line', 'C IV 5808-5812')
cls_cfg = settings.get('classification', {})

# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('## Spectrum Browser')
    st.divider()
    st.caption(f'Primary line: {primary_line}')
    st.caption(f'Binary threshold: {cls_cfg.get("threshold_dRV", 45.5):.1f} km/s')
    st.divider()
    with st.expander('App settings'):
        if st.button('Clear cache', key='_sidebar_clear_cache'):
            st.cache_data.clear()
            st.success('Cache cleared.')

# ── Star / Epoch / Band selectors ────────────────────────────────────────────
st.markdown('# Spectrum Browser')

ui_cfg = settings.get('ui', {})
star_names = specs.star_names
BANDS = ['COMBINED', 'UVB', 'VIS', 'NIR']

col1, col2, col3, col4 = st.columns([2.5, 1, 1, 1])

default_star = ui_cfg.get('last_star', star_names[0])
if default_star not in star_names:
    default_star = star_names[0]
star_name = col1.selectbox(
    'Star', star_names, index=star_names.index(default_star),
    key='spec_star',
    on_change=lambda: sm.save(['ui', 'last_star'], value=st.session_state['spec_star']),
)

default_band = ui_cfg.get('last_band', 'COMBINED')
band = col3.selectbox(
    'Band', BANDS, index=BANDS.index(default_band) if default_band in BANDS else 0,
    key='spec_band',
    on_change=lambda: sm.save(['ui', 'last_band'], value=st.session_state['spec_band']),
)
apply_lmc = col4.checkbox('LMC correction', value=True, key='spec_lmc_corr')

obs = get_obs_manager()
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
    on_change=lambda: sm.save(['ui', 'last_epoch'], value=st.session_state['spec_epoch']),
)

# ── Star info banner: binary classification + cleaning status ────────────────
_cls_thresh = cls_cfg.get('threshold_dRV', 45.5)
_cls_sigma = cls_cfg.get('sigma_factor', 4.0)

_cls = classify_star_line(star_name, primary_line, _threshold=_cls_thresh, _sigma_factor=_cls_sigma)
_pk = get_peak_to_peak_epochs(star_name, primary_line)
_cleaned = is_star_cleaned(star_name)

_is_bin = _cls['is_binary']
_drv = _cls['best_dRV']
_sig = _cls['best_sigma']
_signif = _drv - 4.0 * _sig if not np.isnan(_sig) else float('nan')

if _is_bin is True:
    _stat = f'<span style="color:{COLOR_BINARY};font-weight:700;">Binary</span>'
elif _is_bin is False:
    _stat = f'<span style="color:{COLOR_SINGLE};font-weight:600;">Single</span>'
else:
    _stat = f'<span style="color:{COLOR_UNKNOWN};">Unknown</span>'
_clean = (f'<span style="color:{COLOR_CLEANED};font-weight:600;">Cleaned</span>'
          if _cleaned else f'<span style="color:{COLOR_UNKNOWN};">Not cleaned</span>')

_pk_str = ''
if _pk is not None:
    _pk_str = (f'&nbsp;|&nbsp; Peak-to-peak: Ep {_pk["ep_lo"]} ↔ Ep {_pk["ep_hi"]} '
               f'(ΔRV = {_pk["delta_rv"]:.1f}) ')
st.markdown(
    f'{_stat} &nbsp;|&nbsp; '
    f'dRV = {_drv:.1f} km/s &nbsp; sigma = {_sig:.1f} &nbsp; '
    f'dRV-4sigma = {_signif:.1f} &nbsp;|&nbsp; '
    f'{_clean} {_pk_str}&nbsp;|&nbsp; '
    f'<span style="color:#8C8C8C;font-size:0.85rem;">{_cls["n_epochs"]} epochs</span>',
    unsafe_allow_html=True,
)

# ── Tab dispatch ─────────────────────────────────────────────────────────────
tab_spectrum, tab_drv, tab_classify = st.tabs([
    'Spectrum', 'Max ΔRV', 'Classification',
])

with tab_spectrum:
    spectrum_viewer.render(star_name, epoch, band, apply_lmc, epochs, settings, sm)

with tab_drv:
    max_drv.render(settings, sm)

with tab_classify:
    classification.render(star_name, epochs, settings)
