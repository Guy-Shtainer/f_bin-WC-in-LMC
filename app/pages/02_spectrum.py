"""
pages/02_spectrum.py — Spectrum Browser
Interactive Plotly spectrum viewer with epoch overlay, diagnostic line markers,
model spectrum comparison, and per-star classification workflow.
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
import specs

st.set_page_config(page_title='Spectrum — WR Binary', page_icon='📊', layout='wide')
inject_theme()
settings = render_sidebar('Spectrum')
sm = get_settings_manager()

# ─────────────────────────────────────────────────────────────────────────────
# Constants: diagnostic spectral lines (wavelength in Ångströms)
# ─────────────────────────────────────────────────────────────────────────────
# Each entry: { 'name': str, 'wave': float (Å), 'element': str, 'type': 'abs'|'em' }
DIAGNOSTIC_LINES: dict[str, list[dict]] = {
    'Hydrogen (Balmer)': [
        {'name': 'Hα',  'wave': 6562.8, 'element': 'H', 'type': 'abs'},
        {'name': 'Hβ',  'wave': 4861.3, 'element': 'H', 'type': 'abs'},
        {'name': 'Hγ',  'wave': 4340.5, 'element': 'H', 'type': 'abs'},
        {'name': 'Hδ',  'wave': 4101.7, 'element': 'H', 'type': 'abs'},
        {'name': 'Hε',  'wave': 3970.1, 'element': 'H', 'type': 'abs'},
    ],
    'He I (OB companion)': [
        {'name': 'He I 4026', 'wave': 4026.2, 'element': 'He I', 'type': 'abs'},
        {'name': 'He I 4388', 'wave': 4387.9, 'element': 'He I', 'type': 'abs'},
        {'name': 'He I 4471', 'wave': 4471.5, 'element': 'He I', 'type': 'abs'},
        {'name': 'He I 4922', 'wave': 4921.9, 'element': 'He I', 'type': 'abs'},
        {'name': 'He I 5876', 'wave': 5875.6, 'element': 'He I', 'type': 'abs'},
        {'name': 'He I 6678', 'wave': 6678.2, 'element': 'He I', 'type': 'abs'},
    ],
    'He II (hot companion)': [
        {'name': 'He II 4200', 'wave': 4199.8, 'element': 'He II', 'type': 'abs'},
        {'name': 'He II 4542', 'wave': 4541.6, 'element': 'He II', 'type': 'abs'},
        {'name': 'He II 4686', 'wave': 4685.7, 'element': 'He II', 'type': 'em'},
        {'name': 'He II 5412', 'wave': 5411.5, 'element': 'He II', 'type': 'abs'},
    ],
    'Carbon (WC diagnostic)': [
        {'name': 'C III 5696', 'wave': 5696.0, 'element': 'C', 'type': 'em'},
        {'name': 'C IV 5801', 'wave': 5801.3, 'element': 'C', 'type': 'em'},
        {'name': 'C IV 5812', 'wave': 5811.9, 'element': 'C', 'type': 'em'},
    ],
    'Nitrogen (WN diagnostic)': [
        {'name': 'N III 4634', 'wave': 4634.1, 'element': 'N', 'type': 'em'},
        {'name': 'N III 4641', 'wave': 4640.6, 'element': 'N', 'type': 'em'},
        {'name': 'N IV 4058', 'wave': 4057.8, 'element': 'N', 'type': 'em'},
        {'name': 'N V 4604',  'wave': 4603.7, 'element': 'N', 'type': 'em'},
        {'name': 'N V 4620',  'wave': 4619.9, 'element': 'N', 'type': 'em'},
    ],
    'Interstellar / Other': [
        {'name': 'Na I D1', 'wave': 5895.9, 'element': 'Na', 'type': 'abs'},
        {'name': 'Na I D2', 'wave': 5889.9, 'element': 'Na', 'type': 'abs'},
        {'name': 'DIB 4430', 'wave': 4430.0, 'element': 'DIB', 'type': 'abs'},
        {'name': 'DIB 5780', 'wave': 5780.5, 'element': 'DIB', 'type': 'abs'},
        {'name': 'DIB 5797', 'wave': 5797.1, 'element': 'DIB', 'type': 'abs'},
    ],
}

# Color mapping for element groups
_LINE_COLORS = {
    'H':     '#5DADE2',   # light blue
    'He I':  '#48C9B0',   # teal / cyan
    'He II': '#AF7AC5',   # purple
    'C':     '#F5B041',   # orange
    'N':     '#58D68D',   # green
    'Na':    '#AEB6BF',   # grey
    'DIB':   '#AEB6BF',   # grey
}

# ─────────────────────────────────────────────────────────────────────────────
# Classification persistence
# ─────────────────────────────────────────────────────────────────────────────
_CLASSIFICATION_PATH = os.path.join(_ROOT, 'settings', 'star_classifications.json')
_CLASS_TYPES = ['Unknown', 'Single', 'SB1', 'SB2', 'SB2?', 'Composite']
_CONFIDENCE_LEVELS = ['Low', 'Medium', 'High']


def _load_classifications() -> dict:
    """Load per-star classification metadata from disk."""
    if os.path.exists(_CLASSIFICATION_PATH):
        try:
            with open(_CLASSIFICATION_PATH, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def _save_classifications(data: dict) -> None:
    """Persist per-star classification metadata to disk."""
    os.makedirs(os.path.dirname(_CLASSIFICATION_PATH), exist_ok=True)
    with open(_CLASSIFICATION_PATH, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# Page header
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('# 📊 Spectrum Browser')
st.caption('Interactive spectrum viewer with diagnostic line markers, model overlay, and classification workflow.')

# ── Star / epoch / band selectors ──────────────────────────────────────────
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

# ── Load star ────────────────────────────────────────────────────────────────
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

# ── Cached data loaders ─────────────────────────────────────────────────────
@st.cache_data
def load_spectrum(star_name: str, epoch: int, band: str):
    obs  = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    data = star.load_property('normalized_flux', epoch, band)
    if data is None:
        data = star.load_property('cleaned_normalized_flux', epoch, band)
    return data

@st.cache_data
def load_rvs(star_name: str, epoch: int):
    obs  = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    return star.load_property('RVs', epoch, 'COMBINED')

@st.cache_data
def get_mjd(star_name: str, epoch: int) -> float | None:
    obs  = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    for b in ['NIR', 'VIS', 'UVB']:
        try:
            fit = star.load_observation(epoch, band=b)
            return float(fit.header['MJD-OBS'])
        except Exception:
            pass
    return None

data    = load_spectrum(star_name, epoch, band)
rv_prop = load_rvs(star_name, epoch)
mjd     = get_mjd(star_name, epoch)

# ── Overlay options ──────────────────────────────────────────────────────────
opt_col1, opt_col2 = st.columns(2)

# Overlay second epoch
overlay_ep = opt_col1.checkbox('Overlay another epoch', key='spec_overlay_toggle')
overlay_data = None
ep2 = None
if overlay_ep and len(epochs) > 1:
    other_eps = [e for e in epochs if e != epoch]
    ep2 = opt_col1.selectbox('Overlay epoch', other_eps, key='spec_overlay_ep')
    overlay_data = load_spectrum(star_name, ep2, band)

# Model spectrum overlay
show_model = opt_col2.checkbox('Overlay model spectrum', key='spec_model_toggle')
model_wave = None
model_flux = None
if show_model:
    uploaded = opt_col2.file_uploader(
        'Upload model spectrum (.dat, .txt, .fits, .gz)',
        type=['dat', 'txt', 'fits', 'gz', 'ascii', 'nspec'],
        key='spec_model_file',
    )
    if uploaded is not None:
        import tempfile
        # Save uploaded file temporarily and parse it
        suffix = '.' + uploaded.name.split('.')[-1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = tmp.name
        try:
            sys.path.insert(0, _ROOT)
            from plot import read_file
            mw, mf = read_file(tmp_path)
            model_wave = np.asarray(mw)
            model_flux = np.asarray(mf)
        except Exception as e:
            opt_col2.error(f'Could not parse model file: {e}')
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        if model_wave is not None:
            # Scale / offset controls
            m_sc_col1, m_sc_col2 = opt_col2.columns(2)
            model_scale  = m_sc_col1.slider('Scale', 0.1, 3.0, 1.0, 0.05, key='model_scale')
            model_offset = m_sc_col2.slider('Offset', -1.0, 1.0, 0.0, 0.01, key='model_offset')
            model_flux = model_flux * model_scale + model_offset

# ── Line overlay controls ────────────────────────────────────────────────────
line_col1, line_col2 = st.columns(2)
show_em_lines = line_col1.checkbox('Show emission line bands', value=True, key='spec_show_lines')
show_diag_lines = line_col2.checkbox('Show diagnostic absorption lines', value=False, key='spec_show_diag')

selected_groups = []
if show_diag_lines:
    all_groups = list(DIAGNOSTIC_LINES.keys())
    selected_groups = st.multiselect(
        'Select line groups to display',
        all_groups, default=all_groups[:3],  # H, He I, He II by default
        key='spec_diag_groups',
    )

# ── Build spectrum figure ────────────────────────────────────────────────────
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

# Overlay second epoch
if overlay_data is not None:
    w2 = np.asarray(overlay_data.get('wavelengths', overlay_data.get('wave', [])))
    f2 = np.asarray(overlay_data.get('normalized_flux', overlay_data.get('flux', [])))
    if len(w2) > 0:
        mjd2 = get_mjd(star_name, ep2)
        mjd_str2 = f'  MJD {mjd2:.2f}' if mjd2 else ''
        fig.add_trace(go.Scatter(
            x=w2, y=f2, mode='lines',
            line=dict(color='#E25A53', width=1.0, dash='dot'),
            name=f'Epoch {ep2}{mjd_str2}',
        ))

# Overlay model spectrum
if model_wave is not None and model_flux is not None:
    fig.add_trace(go.Scatter(
        x=model_wave, y=model_flux, mode='lines',
        line=dict(color='#AEB6BF', width=1.0, dash='dash'),
        name='Model spectrum',
    ))

# ── Emission line band overlays ──────────────────────────────────────────────
em_lines = settings.get('emission_lines', {})
if show_em_lines and em_lines and data is not None:
    for line_name, rng in em_lines.items():
        if isinstance(rng, (list, tuple)) and len(rng) == 2:
            lo, hi = float(rng[0]) * 10, float(rng[1]) * 10   # nm → Å
            fig.add_vrect(x0=lo, x1=hi,
                          fillcolor='rgba(255,215,0,0.08)',
                          line_width=0.5, line_color='gold',
                          annotation_text=line_name, annotation_position='top left',
                          annotation=dict(font_size=9, font_color='gold'))

# ── Diagnostic absorption/emission line markers ─────────────────────────────
if show_diag_lines and selected_groups and data is not None:
    wave_arr = np.asarray(data.get('wavelengths', data.get('wave', [])))
    if len(wave_arr) > 0:
        wmin, wmax = float(wave_arr.min()), float(wave_arr.max())
        for group_name in selected_groups:
            lines_in_group = DIAGNOSTIC_LINES.get(group_name, [])
            for linfo in lines_in_group:
                w = linfo['wave']
                if w < wmin or w > wmax:
                    continue
                color = _LINE_COLORS.get(linfo['element'], '#AEB6BF')
                dash_style = 'dash' if linfo['type'] == 'abs' else 'dot'
                fig.add_vline(
                    x=w, line_width=1, line_dash=dash_style,
                    line_color=color, opacity=0.7,
                    annotation_text=linfo['name'],
                    annotation=dict(
                        font_size=8, font_color=color,
                        textangle=-90, yanchor='bottom',
                    ),
                    annotation_position='top',
                )

# ── RV annotation ────────────────────────────────────────────────────────────
primary_line = settings.get('primary_line', 'C IV 5808-5812')
if rv_prop and primary_line in rv_prop:
    entry = rv_prop[primary_line]
    if hasattr(entry, 'item'):
        entry = entry.item()
    rv_val  = entry.get('full_RV',     None)
    err_val = entry.get('full_RV_err', None)
    if rv_val is not None:
        st.info(f'RV ({primary_line}): **{rv_val:.1f} ± {err_val:.1f} km/s**  (epoch {epoch})')

# ── Layout — CRITICAL: use dict merge, never title=... alongside **PLOTLY_THEME ──
fig.update_layout(**{
    **PLOTLY_THEME,
    'title': dict(text=f'{star_name}  —  Epoch {epoch}  —  {band}'),
    'xaxis': {**PLOTLY_THEME.get('xaxis', {}), 'title': 'Wavelength (Å)'},
    'yaxis': {**PLOTLY_THEME.get('yaxis', {}), 'title': 'Normalised flux'},
    'height': 550,
    'legend': {**PLOTLY_THEME.get('legend', {}), 'bgcolor': 'rgba(30,30,46,0.85)'},
})
st.plotly_chart(fig, use_container_width=True)
st.caption('Spectrum viewer — zoom with scroll, pan with drag. Dashed lines = absorption features, dotted = emission features.')

# ── Diagnostic line legend (if shown) ────────────────────────────────────────
if show_diag_lines and selected_groups:
    legend_items = []
    for group_name in selected_groups:
        lines_in_group = DIAGNOSTIC_LINES.get(group_name, [])
        if lines_in_group:
            elem = lines_in_group[0]['element']
            color = _LINE_COLORS.get(elem, '#AEB6BF')
            line_type = lines_in_group[0]['type']
            style = '- - -' if line_type == 'abs' else '· · ·'
            legend_items.append(
                f'<span style="color:{color}; font-weight:600">{style} {group_name}</span>'
            )
    if legend_items:
        st.markdown(' &nbsp;|&nbsp; '.join(legend_items), unsafe_allow_html=True)

# ═══════════════════════════════════════════════════════════════════════════
# CLASSIFICATION WORKFLOW
# ═══════════════════════════════════════════════════════════════════════════
st.markdown('---')
st.markdown('## 🎯 Star Classification')

classifications = _load_classifications()
current_class = classifications.get(star_name, {})

# ── Quick classification for current star ────────────────────────────────────
st.markdown(f'### Classify: **{star_name}**')

cls_col1, cls_col2, cls_col3 = st.columns([1, 1, 2])

current_type = current_class.get('type', 'Unknown')
current_conf = current_class.get('confidence', 'Low')
current_notes = current_class.get('notes', '')

new_type = cls_col1.selectbox(
    'Classification',
    _CLASS_TYPES,
    index=_CLASS_TYPES.index(current_type) if current_type in _CLASS_TYPES else 0,
    key='cls_type',
)
new_conf = cls_col2.selectbox(
    'Confidence',
    _CONFIDENCE_LEVELS,
    index=_CONFIDENCE_LEVELS.index(current_conf) if current_conf in _CONFIDENCE_LEVELS else 0,
    key='cls_conf',
)
new_notes = cls_col3.text_input(
    'Notes (spectroscopic observations)',
    value=current_notes,
    key='cls_notes',
    placeholder='e.g., Possible He I absorption at 4471Å, needs more epochs...',
)

btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)
save_clicked = btn_col1.button('💾 Save Classification', key='cls_save', type='primary')

# Quick-set buttons
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
        'type': new_type,
        'confidence': new_conf,
        'notes': new_notes,
    }
    _save_classifications(classifications)
    st.toast(f'Classification saved for {star_name}: {new_type} ({new_conf})')
    st.rerun()

# Show current status badge
if current_type != 'Unknown':
    badge_colors = {
        'SB1': '#E25A53', 'SB2': '#E25A53', 'SB2?': '#F5B041',
        'Single': '#4A90D9', 'Composite': '#AF7AC5', 'Unknown': '#8C8C8C',
    }
    badge_color = badge_colors.get(current_type, '#8C8C8C')
    st.markdown(
        f'Current: <span style="background:{badge_color}; color:white; padding:2px 10px; '
        f'border-radius:4px; font-weight:600">{current_type}</span> '
        f'(confidence: {current_conf})'
        + (f' — <em>{current_notes}</em>' if current_notes else ''),
        unsafe_allow_html=True,
    )

# ── RV measurements table ───────────────────────────────────────────────────
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
    st.dataframe(pd.DataFrame(rv_rows), use_container_width=True, hide_index=True)
else:
    st.info('No RV data saved for this star on the primary line.')

# ═══════════════════════════════════════════════════════════════════════════
# FULL CLASSIFICATION TABLE (all stars)
# ═══════════════════════════════════════════════════════════════════════════
st.markdown('---')
st.markdown('## 📋 Classification Summary — All Stars')
st.caption('Overview of spectroscopic classifications for all 25 WR stars. '
           'Use the quick classify panel above to update individual stars.')

# Build table data
classifications = _load_classifications()  # Re-read in case just saved
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

# Summary metrics
type_counts = df_cls['Type'].value_counts()
summary_parts = []
for t in _CLASS_TYPES:
    count = type_counts.get(t, 0)
    if count > 0:
        summary_parts.append(f'**{t}**: {count}')
if summary_parts:
    st.markdown(' · '.join(summary_parts))

# Styled table — highlight current star, color-code types
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

# ── Export classification data ───────────────────────────────────────────────
exp_col1, exp_col2 = st.columns(2)
if exp_col1.button('📥 Export classifications as CSV', key='cls_export'):
    csv_data = df_cls.to_csv(index=False)
    st.download_button(
        'Download CSV', csv_data, 'star_classifications.csv', 'text/csv',
        key='cls_download',
    )

if exp_col2.button('🗑️ Clear all classifications', key='cls_clear'):
    _save_classifications({})
    st.toast('All classifications cleared.')
    st.rerun()
