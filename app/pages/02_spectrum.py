"""
pages/02_spectrum.py — Spectrum Browser
Interactive Plotly spectrum viewer with epoch overlay, diagnostic line markers,
model spectrum comparison, absorption line search, and per-star classification.
Organised into three tabs: Spectrum, Max ΔRV (independent star), Classification.
"""
from __future__ import annotations
import os, sys, json
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import numpy as np
import plotly.graph_objects as go
import streamlit as st
import pandas as pd

from shared import inject_theme, render_sidebar, get_settings_manager, get_obs_manager, PLOTLY_THEME
from spectrum_helpers import DIAGNOSTIC_LINES, LINE_COLORS, render_absorption_search
import specs

# LMC systemic velocity correction (non-relativistic Doppler)
LMC_RV_KMS = 262.2
C_KMS = 299_792.458
LMC_DOPPLER_FACTOR = 1.0 + LMC_RV_KMS / C_KMS


def _correct_wave(wave_angstrom: np.ndarray, apply: bool) -> np.ndarray:
    """Divide wavelengths by LMC Doppler factor to shift from observed to rest frame."""
    return wave_angstrom / LMC_DOPPLER_FACTOR if apply else wave_angstrom


st.set_page_config(page_title='Spectrum — WR Binary', page_icon='📊', layout='wide')
inject_theme()
settings = render_sidebar('Spectrum')
sm = get_settings_manager()

# ─────────────────────────────────────────────────────────────────────────────
# Classification persistence
# ─────────────────────────────────────────────────────────────────────────────
_CLASSIFICATION_PATH = os.path.join(_ROOT, 'settings', 'star_classifications.json')
_CLASS_TYPES = ['Unknown', 'Single', 'SB1', 'SB2', 'SB2?', 'Composite']
_CONFIDENCE_LEVELS = ['Low', 'Medium', 'High']


def _load_classifications() -> dict:
    if os.path.exists(_CLASSIFICATION_PATH):
        try:
            with open(_CLASSIFICATION_PATH, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save_classifications(data: dict) -> None:
    os.makedirs(os.path.dirname(_CLASSIFICATION_PATH), exist_ok=True)
    with open(_CLASSIFICATION_PATH, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# Page header + shared star/epoch/band selectors (above tabs)
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('# 📊 Spectrum Browser')

ui_cfg = settings.get('ui', {})
star_names = specs.star_names
BANDS = ['COMBINED', 'UVB', 'VIS', 'NIR']

col1, col2, col3 = st.columns([2, 1, 1])

default_star = ui_cfg.get('last_star', star_names[0])
if default_star not in star_names:
    default_star = star_names[0]
star_name = col1.selectbox(
    'Star', star_names, index=star_names.index(default_star),
    key='spec_star',
    on_change=lambda: sm.save(['ui', 'last_star'], value=st.session_state['spec_star'])
)

default_band = ui_cfg.get('last_band', 'COMBINED')
band = col3.selectbox(
    'Band', BANDS, index=BANDS.index(default_band) if default_band in BANDS else 0,
    key='spec_band',
    on_change=lambda: sm.save(['ui', 'last_band'], value=st.session_state['spec_band'])
)
apply_lmc = col3.checkbox('LMC redshift correction', value=True, key='spec_lmc_corr')

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
    on_change=lambda: sm.save(['ui', 'last_epoch'], value=st.session_state['spec_epoch'])
)

primary_line = settings.get('primary_line', 'C IV 5808-5812')

# ─────────────────────────────────────────────────────────────────────────────
# Cached data loaders (shared across tabs)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data
def load_spectrum(star_name: str, epoch: int, band: str):
    obs = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    data = star.load_property('normalized_flux', epoch, band)
    if data is None:
        data = star.load_property('cleaned_normalized_flux', epoch, band)
    return data

@st.cache_data
def load_rvs(star_name: str, epoch: int):
    obs = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    return star.load_property('RVs', epoch, 'COMBINED')

@st.cache_data
def get_mjd(star_name: str, epoch: int) -> float | None:
    obs = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    for b in ['NIR', 'VIS', 'UVB']:
        try:
            fit = star.load_observation(epoch, band=b)
            return float(fit.header['MJD-OBS'])
        except Exception:
            pass
    return None

@st.cache_data
def _load_model_file(path: str):
    try:
        _mod_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if _mod_root not in sys.path:
            sys.path.insert(0, _mod_root)
        from plot import read_file
        mw, mf = read_file(path)
        return np.asarray(mw), np.asarray(mf)
    except Exception:
        return None, None

@st.cache_data
def _load_all_lines_rvs(star_name: str) -> dict:
    from pipeline.load_observations import load_star_rvs_all_lines
    return load_star_rvs_all_lines(star_name, obs=get_obs_manager())

_MODEL_COLORS = ['#AEB6BF', '#82E0AA', '#F0B27A', '#BB8FCE', '#85C1E9', '#F1948A']
_MODELS_DIR = os.path.join(_ROOT, 'Data', 'Models_for_Guy')
_OVERLAY_COLORS = ['#E25A53', '#58D68D', '#AF7AC5', '#F5B041', '#5DADE2', '#AEB6BF']


# ═══════════════════════════════════════════════════════════════════════════
# TAB 1: SPECTRUM VIEWER
# ═══════════════════════════════════════════════════════════════════════════
def _render_spectrum_tab(star_name, epoch, band, apply_lmc, epochs):
    data = load_spectrum(star_name, epoch, band)
    rv_prop = load_rvs(star_name, epoch)
    mjd = get_mjd(star_name, epoch)

    # ── Overlay options ──────────────────────────────────────────────────
    opt_col1, opt_col2 = st.columns(2)
    show_all_epochs = opt_col1.checkbox('Show all epochs', key='spec_show_all_epochs')
    if show_all_epochs:
        overlay_eps = [e for e in epochs if e != epoch]
    else:
        overlay_eps = opt_col1.multiselect(
            'Overlay epochs', [e for e in epochs if e != epoch], key='spec_overlay_eps',
        )
    vert_offset = 0.0
    if overlay_eps:
        vert_offset = opt_col1.slider(
            'Vertical offset between epochs', 0.0, 2.0, 0.0, 0.05, key='spec_vert_offset',
        )

    show_model = opt_col2.checkbox('Overlay model spectrum', key='spec_model_toggle')
    model_specs: list[dict] = []

    if show_model:
        with st.expander('Model overlay settings', expanded=True):
            if os.path.isdir(_MODELS_DIR):
                available_models = sorted(
                    f for f in os.listdir(_MODELS_DIR)
                    if os.path.isfile(os.path.join(_MODELS_DIR, f)) and not f.startswith('.')
                )
                selected_models = st.multiselect(
                    'Select model spectra from library', available_models, key='spec_model_files',
                )
                for fname in selected_models:
                    mw, mf = _load_model_file(os.path.join(_MODELS_DIR, fname))
                    if mw is not None:
                        model_specs.append({'wave': mw, 'flux': mf, 'name': fname})
                    else:
                        st.warning(f'Could not load {fname}')
            else:
                st.info(f'Model library folder not found: `{_MODELS_DIR}`')

            uploaded = st.file_uploader(
                'Or upload a custom model (.dat, .txt, .fits, .gz)',
                type=['dat', 'txt', 'fits', 'gz', 'ascii', 'nspec'], key='spec_model_file',
            )
            if uploaded is not None:
                import tempfile
                suffix = '.' + uploaded.name.split('.')[-1]
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(uploaded.getvalue())
                    tmp_path = tmp.name
                try:
                    mw, mf = _load_model_file(tmp_path)
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
                    sc = c2.slider('Scale', 0.1, 3.0, 1.0, 0.05, key=f'mscale_{i}')
                    off = c3.slider('Offset', -1.0, 1.0, 0.0, 0.01, key=f'moff_{i}')
                    ms['flux'] = ms['flux'] * sc + off

            st.caption(
                'OB companion models: download from '
                '[TLUSTY OSTAR/BSTAR](http://tlusty.oca.eu/Tlusty2002/tlusty-frames-cloudy.html) '
                'or [POLLUX](https://pollux.oreme.org/). Upload downloaded files above.'
            )

    # ── Line overlay controls ────────────────────────────────────────────
    line_col1, line_col2 = st.columns(2)
    show_em_lines = line_col1.checkbox('Show emission line bands', value=True, key='spec_show_lines')
    show_diag_lines = line_col2.checkbox('Show diagnostic absorption lines', value=False, key='spec_show_diag')

    selected_groups = []
    if show_diag_lines:
        all_groups = list(DIAGNOSTIC_LINES.keys())
        selected_groups = st.multiselect(
            'Select line groups to display', all_groups, default=all_groups[:4], key='spec_diag_groups',
        )

    # ── Build spectrum figure ────────────────────────────────────────────
    fig = go.Figure()
    wave = np.array([])

    if data is not None:
        wave = np.asarray(data.get('wavelengths', data.get('wave', [])))
        flux = np.asarray(data.get('normalized_flux', data.get('flux', [])))
        if len(wave) > 0:
            wave = _correct_wave(wave * 10.0, apply_lmc)
            mjd_str = f'  MJD {mjd:.2f}' if mjd else ''
            fig.add_trace(go.Scatter(
                x=wave, y=flux, mode='lines', line=dict(color='#4A90D9', width=1.2),
                name=f'Epoch {epoch}{mjd_str}',
            ))
    else:
        st.info(f'No normalized spectrum for {star_name} epoch {epoch} band {band}.')

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
                              line_width=0.5, line_color='gold',
                              annotation_text=line_name, annotation_position='top left',
                              annotation=dict(font_size=9, font_color='gold'))

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
                    annotation=dict(font_size=8, font_color=color, textangle=-90, yanchor='bottom'),
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

    fig.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(text=f'{star_name}  —  Epoch {epoch}  —  {band}'),
        'xaxis': {**PLOTLY_THEME.get('xaxis', {}), 'title': 'Wavelength (Å)'},
        'yaxis': {**PLOTLY_THEME.get('yaxis', {}), 'title': 'Normalised flux'},
        'height': 550,
        'legend': {**PLOTLY_THEME.get('legend', {}), 'bgcolor': 'rgba(30,30,46,0.85)'},
    })
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        'Normalized flux vs. wavelength for the selected epoch. '
        'Overlay epochs and model spectra to identify companion signatures. '
        'Emission bumps and absorption dips encode WR wind physics and any companion contribution.'
    )
    st.caption('Zoom with scroll, pan with drag. Dashed lines = absorption, dotted = emission.')

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

    # ── Absorption Line Search ───────────────────────────────────────────
    render_absorption_search(
        star_name=star_name, band=band, epochs=epochs,
        load_spectrum_fn=load_spectrum, get_mjd_fn=get_mjd,
        plotly_theme=PLOTLY_THEME,
        lmc_doppler_factor=LMC_DOPPLER_FACTOR if apply_lmc else 1.0,
    )


# ═══════════════════════════════════════════════════════════════════════════
# TAB 2: MAX ΔRV EPOCH COMPARISON (independent star selector)
# ═══════════════════════════════════════════════════════════════════════════
def _render_drv_tab(settings, sm):
    st.caption(
        'Displays the two epochs with the largest radial-velocity separation for the selected emission line. '
        'A large Delta-RV indicates binary orbital motion; the spectral shift is visible near emission line centers.'
    )

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

    # Load this tab's star
    drv_star_obj = obs.load_star_instance(drv_star, to_print=False)
    drv_epochs = drv_star_obj.get_all_epoch_numbers()

    if not drv_epochs:
        st.warning(f'No epochs found for {drv_star}.')
        return

    _all_rvs = _load_all_lines_rvs(drv_star)
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
    drv_offset = drv_c3.slider('Vertical offset', 0.0, 2.0, 0.0, 0.05, key='drv_vert_offset')

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
        ))
        fig_drv.add_trace(go.Scatter(
            x=_whi, y=_fhi, mode='lines', line=dict(color='#E25A53', width=1.2, dash='dash'),
            name=f'Ep {_ep_hi}: RV={_rv_hi:.1f} km/s{_mjd_hi_str}',
        ))

        _em_lines = settings.get('emission_lines', {})
        _line_rng = _em_lines.get(sel_line)
        _xrange = None
        if _line_rng and isinstance(_line_rng, (list, tuple)) and len(_line_rng) == 2:
            _drv_lo_hi = _correct_wave(np.array([float(_line_rng[0]) * 10, float(_line_rng[1]) * 10]), drv_lmc)
            _lo_a, _hi_a = float(_drv_lo_hi[0]), float(_drv_lo_hi[1])
            fig_drv.add_vrect(x0=_lo_a, x1=_hi_a, fillcolor='rgba(255,215,0,0.10)',
                              line_width=0.5, line_color='gold',
                              annotation_text=sel_line, annotation_position='top left',
                              annotation=dict(font_size=9, font_color='gold'))
            if zoom_to_line:
                _xrange = [_lo_a - 100, _hi_a + 100]

        _layout = {
            **PLOTLY_THEME,
            'title': dict(text=f'{drv_star} — Max ΔRV: {_delta_rv:.1f} km/s ({sel_line})'),
            'xaxis': {**PLOTLY_THEME.get('xaxis', {}), 'title': 'Wavelength (Å)'},
            'yaxis': {**PLOTLY_THEME.get('yaxis', {}), 'title': 'Normalised flux'},
            'height': 450,
            'legend': {**PLOTLY_THEME.get('legend', {}), 'bgcolor': 'rgba(30,30,46,0.85)'},
        }
        if _xrange:
            _layout['xaxis']['range'] = _xrange
        fig_drv.update_layout(**_layout)
        st.plotly_chart(fig_drv, use_container_width=True)
        st.caption(f'Comparing epochs {_ep_lo} and {_ep_hi} — the pair with largest RV separation on {sel_line}.')
    else:
        st.warning(f'Could not load spectra for epochs {_ep_lo} and/or {_ep_hi}.')


# ═══════════════════════════════════════════════════════════════════════════
# TAB 3: CLASSIFICATION WORKFLOW
# ═══════════════════════════════════════════════════════════════════════════
def _render_classification_tab(star_name, epochs):
    st.markdown(f'### Classify: **{star_name}**')

    classifications = _load_classifications()
    current_class = classifications.get(star_name, {})
    current_type = current_class.get('type', 'Unknown')
    current_conf = current_class.get('confidence', 'Low')
    current_notes = current_class.get('notes', '')

    # Badge above form
    if current_type != 'Unknown':
        _badge_colors = {
            'SB1': '#E25A53', 'SB2': '#E25A53', 'SB2?': '#F5B041',
            'Single': '#4A90D9', 'Composite': '#AF7AC5', 'Unknown': '#8C8C8C',
        }
        _badge_color = _badge_colors.get(current_type, '#8C8C8C')
        st.markdown(
            f'Current: <span style="background:{_badge_color}; color:white; padding:2px 10px; '
            f'border-radius:4px; font-weight:600">{current_type}</span> '
            f'(confidence: {current_conf})'
            + (f' — <em>{current_notes}</em>' if current_notes else ''),
            unsafe_allow_html=True,
        )

    cls_col1, cls_col2, cls_col3 = st.columns([1, 1, 2])
    new_type = cls_col1.selectbox(
        'Classification', _CLASS_TYPES,
        index=_CLASS_TYPES.index(current_type) if current_type in _CLASS_TYPES else 0,
        key='cls_type',
    )
    new_conf = cls_col2.selectbox(
        'Confidence', _CONFIDENCE_LEVELS,
        index=_CONFIDENCE_LEVELS.index(current_conf) if current_conf in _CONFIDENCE_LEVELS else 0,
        key='cls_conf',
    )
    new_notes = cls_col3.text_input(
        'Notes (spectroscopic observations)', value=current_notes, key='cls_notes',
        placeholder='e.g., Possible He I absorption at 4471Å, needs more epochs...',
    )

    btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)
    save_clicked = btn_col1.button('💾 Save Classification', key='cls_save', type='primary')

    if btn_col2.button('Mark SB2', key='cls_quick_sb2'):
        st.session_state['cls_type'] = 'SB2'
        st.session_state['cls_conf'] = 'Medium'
        st.rerun()
    if btn_col3.button('Mark Single', key='cls_quick_single'):
        st.session_state['cls_type'] = 'Single'
        st.session_state['cls_conf'] = 'Medium'
        st.rerun()
    if btn_col4.button('Mark SB1', key='cls_quick_sb1'):
        st.session_state['cls_type'] = 'SB1'
        st.session_state['cls_conf'] = 'Medium'
        st.rerun()

    if save_clicked:
        classifications[star_name] = {
            'type': new_type, 'confidence': new_conf, 'notes': new_notes,
        }
        _save_classifications(classifications)
        st.toast(f'Classification saved for {star_name}: {new_type} ({new_conf})')
        st.rerun()

    # ── RV measurements table ────────────────────────────────────────────
    st.markdown('### RV Measurements (primary line)')
    rv_rows = []
    for ep in epochs:
        rv_p = load_rvs(star_name, ep)
        if rv_p and primary_line in rv_p:
            entry = rv_p[primary_line]
            if hasattr(entry, 'item'):
                entry = entry.item()
            rv_rows.append({
                'Epoch': ep,
                'RV (km/s)': round(float(entry.get('full_RV', 0)), 2),
                'Error (km/s)': round(float(entry.get('full_RV_err', 0)), 2),
                'MJD': get_mjd(star_name, ep) or '—',
            })

    if rv_rows:
        df_rv = pd.DataFrame(rv_rows)
        mean_rv = df_rv['RV (km/s)'].mean()
        df_rv['ΔRV (km/s)'] = (df_rv['RV (km/s)'] - mean_rv).round(2)
        st.dataframe(df_rv, use_container_width=True, hide_index=True)
    else:
        st.info('No RV data saved for this star on the primary line.')

    # ── Full classification table ────────────────────────────────────────
    st.markdown('---')
    st.markdown('## 📋 Classification Summary — All Stars')
    st.caption('Overview of spectroscopic classifications for all 25 WR stars.')

    classifications = _load_classifications()
    table_rows = []
    for sn in star_names:
        cls = classifications.get(sn, {})
        table_rows.append({
            'Star': sn,
            'Type': cls.get('type', 'Unknown'),
            'Confidence': cls.get('confidence', 'Low'),
            'Notes': cls.get('notes', ''),
        })

    df_cls = pd.DataFrame(table_rows)

    type_counts = df_cls['Type'].value_counts()
    summary_parts = []
    for t in _CLASS_TYPES:
        count = type_counts.get(t, 0)
        if count > 0:
            summary_parts.append(f'**{t}**: {count}')
    if summary_parts:
        st.markdown(' · '.join(summary_parts))

    filter_types = st.multiselect('Filter by type', _CLASS_TYPES, default=_CLASS_TYPES, key='cls_filter_types')
    df_cls = df_cls[df_cls['Type'].isin(filter_types)]

    def _style_type(val):
        colors = {
            'SB1': 'background-color: rgba(226,90,83,0.25)',
            'SB2': 'background-color: rgba(226,90,83,0.35)',
            'SB2?': 'background-color: rgba(245,176,65,0.25)',
            'Single': 'background-color: rgba(74,144,217,0.25)',
            'Composite': 'background-color: rgba(175,122,197,0.25)',
        }
        return colors.get(val, '')

    styled = df_cls.style.map(_style_type, subset=['Type'])
    st.dataframe(styled, use_container_width=True, hide_index=True, height=400)

    exp_col1, exp_col2 = st.columns(2)
    if exp_col1.button('📥 Export classifications as CSV', key='cls_export'):
        csv_data = df_cls.to_csv(index=False)
        st.download_button(
            'Download CSV', csv_data, 'star_classifications.csv', 'text/csv', key='cls_download',
        )
    if exp_col2.button('🗑️ Clear all classifications', key='cls_clear'):
        _save_classifications({})
        st.toast('All classifications cleared.')
        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# TAB DISPATCH
# ═══════════════════════════════════════════════════════════════════════════
tab_spectrum, tab_drv, tab_classify = st.tabs([
    'Spectrum', 'Max ΔRV', 'Classification',
])

with tab_spectrum:
    _render_spectrum_tab(star_name, epoch, band, apply_lmc, epochs)

with tab_drv:
    _render_drv_tab(settings, sm)

with tab_classify:
    _render_classification_tab(star_name, epochs)
