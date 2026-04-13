"""
tabs/max_drv.py — Tab 2: Max ΔRV epoch comparison.
Shows the two epochs with the largest radial-velocity separation
for a selected emission line, with independent star selector.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

import specs
from helpers.data_loaders import load_spectrum, get_mjd, load_all_lines_rvs
from shared_lite import PLOTLY_THEME, get_obs_manager

# Constants
LMC_RV_KMS = 262.2
C_KMS = 299_792.458
LMC_DOPPLER_FACTOR = 1.0 + LMC_RV_KMS / C_KMS
BANDS = ['COMBINED', 'UVB', 'VIS', 'NIR']


def _correct_wave(wave_angstrom: np.ndarray, apply: bool) -> np.ndarray:
    return wave_angstrom / LMC_DOPPLER_FACTOR if apply else wave_angstrom


def render(settings: dict, sm) -> None:
    """Render the Max ΔRV tab with independent star/band selectors."""
    star_names = specs.star_names

    # ── Independent star/band selectors (persisted under ui_drv) ─────────
    drv_cfg = settings.get('ui_drv', {})

    dc1, dc2, dc3 = st.columns([2, 1, 1])
    drv_default_star = drv_cfg.get('last_star', star_names[0])
    if drv_default_star not in star_names:
        drv_default_star = star_names[0]
    drv_star = dc1.selectbox(
        'Star', star_names, index=star_names.index(drv_default_star),
        key='drv_star',
        on_change=lambda: sm.save(['ui_drv', 'last_star'], value=st.session_state['drv_star']),
    )

    drv_default_band = drv_cfg.get('last_band', 'COMBINED')
    drv_band = dc3.selectbox(
        'Band', BANDS, index=BANDS.index(drv_default_band) if drv_default_band in BANDS else 0,
        key='drv_band',
        on_change=lambda: sm.save(['ui_drv', 'last_band'], value=st.session_state['drv_band']),
    )
    drv_lmc = dc2.checkbox('LMC correction', value=True, key='drv_lmc_corr')

    obs = get_obs_manager()
    drv_star_obj = obs.load_star_instance(drv_star, to_print=False)
    drv_epochs = drv_star_obj.get_all_epoch_numbers()

    if not drv_epochs:
        st.warning(f'No epochs found for {drv_star}.')
        return

    _all_rvs = load_all_lines_rvs(drv_star)
    _lines_with_data = {ln: d for ln, d in _all_rvs.items() if len(d['epochs']) >= 2}

    if not _lines_with_data:
        st.info('No emission lines with ≥2 epochs of RV data for this star.')
        return

    _line_names = list(_lines_with_data.keys())
    _default_line = 'C IV 5808-5812'
    _default_idx = _line_names.index(_default_line) if _default_line in _line_names else 0

    drv_c1, drv_c2, drv_c3 = st.columns([2, 1, 1])
    sel_line = drv_c1.selectbox('Emission line for ΔRV', _line_names, index=_default_idx, key='drv_line')
    zoom_to_line = drv_c2.checkbox('Zoom to line region', value=True, key='drv_zoom')
    drv_offset = drv_c3.number_input('Vertical offset', value=0.0, step=0.05, key='drv_vert_offset')

    _ld = _lines_with_data[sel_line]
    _rv_arr = np.array(_ld['rv'])
    _rv_err_arr = np.array(_ld['rv_err'])
    _ep_arr = _ld['epochs']

    _idx_lo = int(np.argmin(_rv_arr))
    _idx_hi = int(np.argmax(_rv_arr))
    _ep_lo, _ep_hi = _ep_arr[_idx_lo], _ep_arr[_idx_hi]
    _rv_lo, _rv_hi = _rv_arr[_idx_lo], _rv_arr[_idx_hi]
    _err_lo, _err_hi = _rv_err_arr[_idx_lo], _rv_err_arr[_idx_hi]
    _delta_rv = abs(_rv_hi - _rv_lo)
    _mjd_lo, _mjd_hi = get_mjd(drv_star, _ep_lo), get_mjd(drv_star, _ep_hi)

    ic1, ic2, ic3 = st.columns(3)
    ic1.metric('Epoch (min RV)', f'{_ep_lo}', f'{_rv_lo:.1f} ± {_err_lo:.1f} km/s')
    ic2.metric('Epoch (max RV)', f'{_ep_hi}', f'{_rv_hi:.1f} ± {_err_hi:.1f} km/s')
    ic3.metric('ΔRV', f'{_delta_rv:.1f} km/s')

    _spec_lo = load_spectrum(drv_star, _ep_lo, drv_band)
    _spec_hi = load_spectrum(drv_star, _ep_hi, drv_band)

    if _spec_lo is not None and _spec_hi is not None:
        fig_drv = go.Figure()
        _wlo = _correct_wave(np.asarray(_spec_lo.get('wavelengths', _spec_lo.get('wave', []))) * 10.0, drv_lmc)
        _flo = np.asarray(_spec_lo.get('normalized_flux', _spec_lo.get('flux', [])))
        _whi = _correct_wave(np.asarray(_spec_hi.get('wavelengths', _spec_hi.get('wave', []))) * 10.0, drv_lmc)
        _fhi = np.asarray(_spec_hi.get('normalized_flux', _spec_hi.get('flux', []))) + drv_offset

        _mjd_lo_str = f'  MJD {_mjd_lo:.2f}' if _mjd_lo else ''
        _mjd_hi_str = f'  MJD {_mjd_hi:.2f}' if _mjd_hi else ''

        fig_drv.add_trace(go.Scatter(
            x=_wlo, y=_flo, mode='lines', line=dict(color='#4A90D9', width=1.2),
            name=f'Ep {_ep_lo}: RV={_rv_lo:.1f} km/s{_mjd_lo_str}',
            hovertemplate='%{x:.1f} Å<br>Flux: %{y:.4f}<extra>Ep ' + str(_ep_lo) + '</extra>',
        ))
        fig_drv.add_trace(go.Scatter(
            x=_whi, y=_fhi, mode='lines', line=dict(color='#E25A53', width=1.2, dash='dash'),
            name=f'Ep {_ep_hi}: RV={_rv_hi:.1f} km/s{_mjd_hi_str}',
            hovertemplate='%{x:.1f} Å<br>Flux: %{y:.4f}<extra>Ep ' + str(_ep_hi) + '</extra>',
        ))

        _em_lines = settings.get('emission_lines', {})
        _line_rng = _em_lines.get(sel_line)
        _xrange = None
        if _line_rng and isinstance(_line_rng, (list, tuple)) and len(_line_rng) == 2:
            _drv_lo_hi = _correct_wave(np.array([float(_line_rng[0]) * 10, float(_line_rng[1]) * 10]), drv_lmc)
            _lo_a, _hi_a = float(_drv_lo_hi[0]), float(_drv_lo_hi[1])
            fig_drv.add_vrect(x0=_lo_a, x1=_hi_a, fillcolor='rgba(255,215,0,0.10)',
                              line_width=0.5, line_color='#B8860B',
                              annotation_text=sel_line, annotation_position='top left',
                              annotation=dict(font_size=9, font_color='#B8860B'))
            if zoom_to_line:
                _xrange = [_lo_a - 100, _hi_a + 100]

        _layout = {
            **PLOTLY_THEME,
            'title': dict(text=f'{drv_star} — Max ΔRV: {_delta_rv:.1f} km/s ({sel_line})'),
            'xaxis': {**PLOTLY_THEME.get('xaxis', {}), 'title': 'Wavelength (Å)'},
            'yaxis': {**PLOTLY_THEME.get('yaxis', {}), 'title': 'Normalised flux'},
            'height': 450,
            'legend': {**PLOTLY_THEME.get('legend', {})},
        }
        if _xrange:
            _layout['xaxis']['range'] = _xrange
        fig_drv.add_annotation(
            text=f'ΔRV = {_delta_rv:.1f} km/s',
            xref='paper', yref='paper', x=0.98, y=0.98,
            showarrow=False, font=dict(size=12, color='#DAA520'),
            bgcolor='rgba(255,255,255,0.85)', bordercolor='#cccccc',
        )
        fig_drv.update_layout(**_layout)
        st.plotly_chart(fig_drv, use_container_width=True, theme=None)
        st.caption(
            f'Comparing epochs {_ep_lo} and {_ep_hi} — the pair with largest RV separation on {sel_line}. '
            'A large ΔRV indicates binary orbital motion; the spectral shift is visible near emission line centers.'
        )
    else:
        st.warning(f'Could not load spectra for epochs {_ep_lo} and/or {_ep_hi}.')
