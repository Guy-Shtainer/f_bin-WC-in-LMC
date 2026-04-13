"""
tabs/spectrum_viewer.py — Tab 1: Interactive spectrum viewer with epoch overlay,
model comparison, emission line bands, diagnostic absorption lines, zoom navigation,
and multi-line view with adjustable separation.
"""
from __future__ import annotations

import os
import tempfile

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from spectrum_helpers import (DIAGNOSTIC_LINES, LINE_COLORS,
                              render_absorption_search, render_companion_guide)
from helpers.data_loaders import (load_spectrum, load_rvs, get_mjd, load_model_file,
                                  load_anchor_wavelengths, load_interpolated_flux,
                                  get_peak_to_peak_epochs)
from helpers.model_io import MODELS_DIR, list_model_files
from shared_lite import PLOTLY_THEME, get_obs_manager

# ── Constants ────────────────────────────────────────────────────────────────
LMC_RV_KMS = 262.2
C_KMS = 299_792.458
LMC_DOPPLER_FACTOR = 1.0 + LMC_RV_KMS / C_KMS

_MODEL_COLORS = ['#7B8794', '#52B788', '#E08A4A', '#BB8FCE', '#4A90D9', '#E25A53']
_OVERLAY_COLORS = ['#E25A53', '#58D68D', '#AF7AC5', '#F5B041', '#5DADE2', '#AEB6BF']
_ZOOM_PRESETS = {
    'Full range': None,
    'C IV 5808-5812': (5750, 5870),
    'C III 5696': (5640, 5750),
    'He I 4471': (4420, 4520),
    'He I 5876': (5820, 5930),
    'He II 4686': (4630, 4740),
    'Hα 6563': (6510, 6620),
    'Hβ 4861': (4810, 4920),
    'O VI 3811-3834': (3760, 3890),
}
_LINE_ZOOM_HALFWIN = 30.0


def _correct_wave(wave_angstrom: np.ndarray, apply: bool) -> np.ndarray:
    return wave_angstrom / LMC_DOPPLER_FACTOR if apply else wave_angstrom


def render(star_name: str, epoch: int, band: str, apply_lmc: bool,
           epochs: list, settings: dict, sm) -> None:
    """Render the full Spectrum Viewer tab."""
    render_companion_guide()
    data = load_spectrum(star_name, epoch, band)
    rv_prop = load_rvs(star_name, epoch)
    mjd = get_mjd(star_name, epoch)
    primary_line = settings.get('primary_line', 'C IV 5808-5812')

    # ── Overlay options (inline, not collapsed) ──────────────────────────
    model_specs: list[dict] = []
    opt_col1, opt_col2 = st.columns(2)
    show_all_epochs = opt_col1.checkbox('Show all epochs', value=True, key='spec_show_all_epochs')
    show_only_pk = opt_col1.checkbox('Show only peak-to-peak epochs', value=False, key='spec_show_only_pk')
    if show_all_epochs:
        overlay_eps = [e for e in epochs if e != epoch]
    else:
        overlay_eps = opt_col1.multiselect(
            'Overlay epochs', [e for e in epochs if e != epoch], key='spec_overlay_eps',
        )
    if show_only_pk:
        pk = get_peak_to_peak_epochs(star_name, primary_line)
        if pk is not None:
            pk_eps = [pk['ep_lo'], pk['ep_hi']]
            overlay_eps = [e for e in pk_eps if e != epoch]
        else:
            st.caption('No peak-to-peak pair available (needs ≥2 epochs of RV data).')
    vert_offset = 0.0
    if overlay_eps:
        vert_offset = opt_col1.number_input(
            'Vertical offset between epochs', value=0.0, step=0.05, key='spec_vert_offset',
        )

    show_model = opt_col2.checkbox('Overlay model spectrum', key='spec_model_toggle')

    if show_model:
        available_models = list_model_files()
        if available_models:
            selected_models = st.multiselect(
                'Select model spectra from library', available_models, key='spec_model_files',
            )
            for fname in selected_models:
                mw, mf = load_model_file(os.path.join(MODELS_DIR, fname))
                if mw is not None:
                    model_specs.append({'wave': mw, 'flux': mf, 'name': fname})
                else:
                    st.warning(f'Could not load {fname}')
        else:
            st.info(f'Model library folder not found: `{MODELS_DIR}`')

        uploaded = st.file_uploader(
            'Or upload a custom model (.dat, .txt, .fits, .gz)',
            type=['dat', 'txt', 'fits', 'gz', 'ascii', 'nspec'], key='spec_model_file',
        )
        if uploaded is not None:
            suffix = '.' + uploaded.name.split('.')[-1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(uploaded.getvalue())
                tmp_path = tmp.name
            try:
                mw, mf = load_model_file(tmp_path)
                if mw is not None:
                    model_specs.append({'wave': mw, 'flux': mf, 'name': uploaded.name})
                else:
                    st.error('Could not parse uploaded model file.')
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        if model_specs:
            st.markdown('**Scale / Offset:**')
            for i, ms in enumerate(model_specs):
                c1, c2, c3 = st.columns([3, 1, 1])
                c1.caption(ms['name'])
                sc = c2.number_input('Scale', value=1.0, step=0.05, key=f'mscale_{i}')
                off = c3.number_input('Offset', value=0.0, step=0.01, key=f'moff_{i}')
                ms['flux'] = ms['flux'] * sc + off

        st.caption(
            'OB companion models: download from '
            '[TLUSTY OSTAR/BSTAR](http://tlusty.oca.eu/Tlusty2002/tlusty-frames-cloudy.html) '
            'or [POLLUX](https://pollux.oreme.org/). Upload downloaded files above.'
        )

    # ── Line overlay controls (inline, defaults ON) ──────────────────────
    line_col1, line_col2 = st.columns(2)
    show_em_lines = line_col1.checkbox('Show emission line bands', value=True, key='spec_show_lines')
    show_diag_lines = line_col2.checkbox('Show diagnostic absorption lines', value=True, key='spec_show_diag')

    all_groups = list(DIAGNOSTIC_LINES.keys())
    selected_groups = []
    if show_diag_lines:
        selected_groups = st.multiselect(
            'Select line groups to display', all_groups, default=all_groups, key='spec_diag_groups',
        )

    # ── Zoom navigation ──────────────────────────────────────────────────
    st.divider()
    if 'spec_zoom_history' not in st.session_state:
        st.session_state['spec_zoom_history'] = []
        st.session_state['spec_zoom_idx'] = -1

    def _push_zoom(xr, yr=None):
        _h = st.session_state['spec_zoom_history']
        _i = st.session_state['spec_zoom_idx']
        _h = _h[:_i + 1] if _i >= 0 else []
        _h.append((xr, yr))
        st.session_state['spec_zoom_history'] = _h
        st.session_state['spec_zoom_idx'] = len(_h) - 1

    def _unpack(entry):
        """History entries may be (xr, yr) tuples or legacy plain xr tuples."""
        if entry is None:
            return None, None
        if isinstance(entry, tuple) and len(entry) == 2 and (
            entry[1] is None or (isinstance(entry[1], (tuple, list)) and len(entry[1]) == 2)
        ):
            return entry[0], entry[1]
        return entry, None

    zn_c1, zn_c2, zn_c3, zn_c4 = st.columns([1, 1, 1, 2])
    _go_back = zn_c1.button('◀ Back', key='spec_zoom_back')
    _go_fwd = zn_c2.button('▶ Forward', key='spec_zoom_fwd')
    _go_home = zn_c3.button('⟲ Home', key='spec_zoom_home')
    _preset = zn_c4.selectbox(
        'Jump to region', list(_ZOOM_PRESETS.keys()), index=0, key='spec_zoom_preset',
    )

    _hist = st.session_state['spec_zoom_history']
    _idx = st.session_state['spec_zoom_idx']
    _xrange = None
    _yrange = None

    if _go_back and _idx > 0:
        st.session_state['spec_zoom_idx'] = _idx - 1
        _xrange, _yrange = _unpack(_hist[_idx - 1])
    elif _go_fwd and _idx < len(_hist) - 1:
        st.session_state['spec_zoom_idx'] = _idx + 1
        _xrange, _yrange = _unpack(_hist[_idx + 1])
    elif _go_home:
        _xrange = None
        _yrange = None
        st.session_state['spec_zoom_idx'] = -1
    elif _preset != 'Full range':
        _xrange = _ZOOM_PRESETS[_preset]
        if _xrange is not None:
            _push_zoom(_xrange, None)
    else:
        if _idx >= 0 and _idx < len(_hist):
            _xrange, _yrange = _unpack(_hist[_idx])

    # ── Build spectrum figure ────────────────────────────────────────────
    fig = go.Figure()
    wave = np.array([])
    flux = np.array([])

    if data is not None:
        if data.get('_raw'):
            st.warning(f'Showing raw (unnormalized) spectrum for {star_name} epoch {epoch} band {band}.')
        wave = np.asarray(data.get('wavelengths', data.get('wave', [])))
        flux = np.asarray(data.get('normalized_flux', data.get('flux', [])))
        if len(wave) > 0:
            wave = _correct_wave(wave * 10.0, apply_lmc)
            mjd_str = f'  MJD {mjd:.2f}' if mjd else ''
            fig.add_trace(go.Scatter(
                x=wave, y=flux, mode='lines', line=dict(color='#4A90D9', width=1.2),
                name=f'Epoch {epoch}{mjd_str}',
                hovertemplate='%{x:.1f} Å<br>Flux: %{y:.4f}<extra>Epoch ' + str(epoch) + '</extra>',
            ))
    else:
        st.info(f'No spectrum found for {star_name} epoch {epoch} band {band}.')

    for oi, ov_ep in enumerate(overlay_eps):
        ov_data = load_spectrum(star_name, ov_ep, band)
        if ov_data is not None:
            w2 = np.asarray(ov_data.get('wavelengths', ov_data.get('wave', [])))
            f2 = np.asarray(ov_data.get('normalized_flux', ov_data.get('flux', [])))
            if len(w2) > 0:
                w2 = _correct_wave(w2 * 10.0, apply_lmc)
                f2 = f2 + vert_offset * (oi + 1)
                mjd2 = get_mjd(star_name, ov_ep)
                mjd_str2 = f'  MJD {mjd2:.2f}' if mjd2 else ''
                off_str = f'  +{vert_offset * (oi + 1):.2f}' if vert_offset > 0 else ''
                fig.add_trace(go.Scatter(
                    x=w2, y=f2, mode='lines',
                    line=dict(color=_OVERLAY_COLORS[oi % len(_OVERLAY_COLORS)], width=1.0, dash='dot'),
                    name=f'Epoch {ov_ep}{mjd_str2}{off_str}',
                ))

    for i, ms in enumerate(model_specs):
        color = _MODEL_COLORS[i % len(_MODEL_COLORS)]
        fig.add_trace(go.Scatter(
            x=ms['wave'], y=ms['flux'], mode='lines',
            line=dict(color=color, width=1.0, dash='dash'), name=f'Model: {ms["name"]}',
        ))

    em_lines = settings.get('emission_lines', {})
    if show_em_lines and em_lines and data is not None:
        for line_name, rng in em_lines.items():
            if isinstance(rng, (list, tuple)) and len(rng) == 2:
                _lo_hi = _correct_wave(np.array([float(rng[0]) * 10, float(rng[1]) * 10]), apply_lmc)
                lo, hi = float(_lo_hi[0]), float(_lo_hi[1])
                fig.add_vrect(x0=lo, x1=hi, fillcolor='rgba(255,215,0,0.08)',
                              line_width=0.5, line_color='#B8860B',
                              annotation_text=line_name, annotation_position='top left',
                              annotation=dict(font_size=10, font_color='#B8860B'))

    if show_diag_lines and selected_groups and data is not None and len(wave) > 0:
        wmin, wmax = float(wave.min()), float(wave.max())
        for group_name in selected_groups:
            for linfo in DIAGNOSTIC_LINES.get(group_name, []):
                w = linfo['wave']
                if w < wmin or w > wmax:
                    continue
                color = LINE_COLORS.get(linfo['element'], '#AEB6BF')
                dash_style = 'dash' if linfo['type'] == 'abs' else 'dot'
                fig.add_vline(
                    x=w, line_width=1, line_dash=dash_style, line_color=color, opacity=0.7,
                    annotation_text=linfo['name'],
                    annotation=dict(font_size=11, font_color=color, textangle=-90, yanchor='bottom'),
                    annotation_position='top',
                )

    if rv_prop and primary_line in rv_prop:
        entry = rv_prop[primary_line]
        if hasattr(entry, 'item'):
            entry = entry.item()
        rv_val = entry.get('full_RV', None)
        err_val = entry.get('full_RV_err', None)
        if rv_val is not None:
            st.info(f'RV ({primary_line}): **{rv_val:.1f} ± {err_val:.1f} km/s**  (epoch {epoch})')

    _xaxis_cfg = {**PLOTLY_THEME.get('xaxis', {}), 'title': 'Wavelength (Å)'}
    if _xrange is not None:
        _xaxis_cfg['range'] = list(_xrange)
    _yaxis_cfg = {**PLOTLY_THEME.get('yaxis', {}), 'title': 'Normalized flux'}
    if _yrange is not None:
        _yaxis_cfg['range'] = list(_yrange)
    fig.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(text=f'{star_name}  —  Epoch {epoch}  —  {band}'),
        'xaxis': _xaxis_cfg,
        'yaxis': _yaxis_cfg,
        'height': 550,
    })
    st.plotly_chart(fig, use_container_width=True, theme=None)
    st.caption(
        'Normalized flux vs. wavelength for the selected epoch. '
        'Overlay epochs and model spectra to identify companion signatures.'
    )

    if show_diag_lines and selected_groups:
        legend_items = []
        for group_name in selected_groups:
            lines_in_group = DIAGNOSTIC_LINES.get(group_name, [])
            if lines_in_group:
                elem = lines_in_group[0]['element']
                color = LINE_COLORS.get(elem, '#AEB6BF')
                line_type = lines_in_group[0]['type']
                style = '- - -' if line_type == 'abs' else '· · ·'
                legend_items.append(
                    f'<span style="color:{color}; font-weight:600">{style} {group_name}</span>'
                )
        if legend_items:
            st.markdown(' &nbsp;|&nbsp; '.join(legend_items), unsafe_allow_html=True)

        st.markdown('**Quick-zoom to diagnostic line:**')
        _groups_with_lines = [(g, DIAGNOSTIC_LINES.get(g, [])) for g in selected_groups
                              if DIAGNOSTIC_LINES.get(g, [])]
        _GROUPS_PER_ROW = 4
        for _row_start in range(0, len(_groups_with_lines), _GROUPS_PER_ROW):
            _row_groups = _groups_with_lines[_row_start:_row_start + _GROUPS_PER_ROW]
            _cols = st.columns(len(_row_groups))
            for _gi, (group_name, lines_in_group) in enumerate(_row_groups):
                with _cols[_gi]:
                    st.caption(group_name)
                    for linfo in lines_in_group:
                        if st.button(
                            linfo['name'],
                            key=f"spec_zoom_line_{group_name}_{linfo['name']}",
                            use_container_width=True,
                        ):
                            _c = float(linfo['wave'])
                            _new_xr = (_c - _LINE_ZOOM_HALFWIN, _c + _LINE_ZOOM_HALFWIN)
                            _elem = linfo.get('element', '')
                            if _elem in ('ISM', 'Telluric'):
                                _new_yr = (0.0, 1.2)
                            elif linfo.get('type') == 'abs':
                                _new_yr = (0.5, 1.3)
                            else:
                                _upper = 2.0
                                if len(wave) > 0 and len(flux) > 0:
                                    _mask = (wave >= _new_xr[0]) & (wave <= _new_xr[1])
                                    if np.any(_mask):
                                        _local_max = float(np.nanmax(flux[_mask]))
                                        _upper = max(2.0, _local_max * 1.1)
                                _new_yr = (0.5, _upper)
                            _push_zoom(_new_xr, _new_yr)
                            st.rerun()

    # ── Unnormalized spectrum (COMBINED) ─────────────────────────────────
    st.divider()
    st.markdown('### Unnormalized Spectrum (COMBINED)')
    _obs = get_obs_manager()
    _star = _obs.load_star_instance(star_name, to_print=False)
    _raw_fig = go.Figure()
    _has_raw = False
    try:
        _fit = _star.load_observation(epoch, band='COMBINED')
        if _fit is not None and _fit.data is not None:
            _raw_w = np.asarray(_fit.data['WAVE'][0], dtype=float) * 10.0  # nm -> Å
            _raw_f = np.asarray(_fit.data['FLUX'][0], dtype=float)
            _raw_w = _correct_wave(_raw_w, apply_lmc)
            _raw_fig.add_trace(go.Scatter(
                x=_raw_w, y=_raw_f, mode='lines', line=dict(color='#1f77b4', width=1.0),
                name=f'Epoch {epoch} (raw)',
                hovertemplate='%{x:.1f} Å<br>Flux: %{y:.2f}<extra></extra>',
            ))
            _has_raw = True
    except Exception:
        pass

    if _has_raw:
        _anch_col1, _anch_col2 = st.columns(2)
        show_anchors = _anch_col1.checkbox('Show anchor points', value=False, key='spec_show_anchors')
        show_interp = _anch_col2.checkbox('Show interpolation curve', value=False, key='spec_show_interp')

        if show_anchors:
            _anchors_nm = load_anchor_wavelengths(star_name, epoch, 'COMBINED')
            if _anchors_nm is not None:
                _anch_arr = np.asarray(_anchors_nm, dtype=float).ravel()
                _anch_a = _correct_wave(_anch_arr * 10.0, apply_lmc)
                _anch_flux = np.interp(_anch_a, _raw_w, _raw_f)
                _raw_fig.add_trace(go.Scatter(
                    x=_anch_a, y=_anch_flux, mode='markers',
                    marker=dict(color='#d62728', size=8, symbol='circle'),
                    name='Anchor points',
                    hovertemplate='%{x:.1f} Å<br>Flux: %{y:.2f}<extra>Anchor</extra>',
                ))

        if show_interp:
            _interp_data = load_interpolated_flux(star_name, epoch, 'COMBINED')
            if _interp_data is not None:
                _int_w = np.asarray(_interp_data['wavelengths'], dtype=float) * 10.0
                _int_f = np.asarray(_interp_data['interpolated_flux'], dtype=float)
                _int_w = _correct_wave(_int_w, apply_lmc)
                _raw_fig.add_trace(go.Scatter(
                    x=_int_w, y=_int_f, mode='lines',
                    line=dict(color='#d62728', width=1.5, dash='dash'),
                    name='Continuum (ISE)',
                    hovertemplate='%{x:.1f} Å<br>Continuum: %{y:.2f}<extra>ISE interp</extra>',
                ))

        if show_em_lines and em_lines:
            for _ln, rng in em_lines.items():
                if isinstance(rng, (list, tuple)) and len(rng) == 2:
                    _lo_hi = _correct_wave(np.array([float(rng[0]) * 10, float(rng[1]) * 10]), apply_lmc)
                    _raw_fig.add_vrect(x0=float(_lo_hi[0]), x1=float(_lo_hi[1]),
                                       fillcolor='rgba(184,134,11,0.08)',
                                       line_width=0.5, line_color='#B8860B',
                                       annotation_text=_ln, annotation_position='top left',
                                       annotation=dict(font_size=10, font_color='#B8860B'))
        if show_diag_lines and selected_groups and len(_raw_w) > 0:
            _wmin, _wmax = float(_raw_w.min()), float(_raw_w.max())
            for group_name in selected_groups:
                for linfo in DIAGNOSTIC_LINES.get(group_name, []):
                    w = linfo['wave']
                    if w < _wmin or w > _wmax:
                        continue
                    _c = LINE_COLORS.get(linfo['element'], '#666666')
                    _ds = 'dash' if linfo['type'] == 'abs' else 'dot'
                    _raw_fig.add_vline(
                        x=w, line_width=1, line_dash=_ds, line_color=_c, opacity=0.7,
                        annotation_text=linfo['name'],
                        annotation=dict(font_size=11, font_color=_c, textangle=-90, yanchor='bottom'),
                        annotation_position='top',
                    )
        _raw_fig.update_layout(**{
            **PLOTLY_THEME,
            'title': dict(text=f'{star_name} — Epoch {epoch} — COMBINED (unnormalized)'),
            'xaxis': {**PLOTLY_THEME.get('xaxis', {}), 'title': 'Wavelength (Å)'},
            'yaxis': {**PLOTLY_THEME.get('yaxis', {}), 'title': 'Flux (counts)'},
            'height': 450,
        })
        st.plotly_chart(_raw_fig, use_container_width=True, theme=None)
        st.caption('Unnormalized flux from the raw FITS file. Line annotations match the main spectrum above.')
    else:
        st.info('No raw FITS spectrum available for COMBINED band.')

    # ── Absorption Line Search ───────────────────────────────────────────
    render_absorption_search(
        star_name=star_name, band=band, epochs=epochs,
        load_spectrum_fn=load_spectrum, get_mjd_fn=get_mjd,
        plotly_theme=PLOTLY_THEME,
        lmc_doppler_factor=LMC_DOPPLER_FACTOR if apply_lmc else 1.0,
    )
