"""
pages/05_bias_correction.py — Bias Correction (Dsilva / Langer 2020 grid search)

Features:
  - Two-column layout: grid/orbital params left, sigma scan + live heatmap right
  - Single persistent multiprocessing Pool — no per-f_bin overhead
  - Heatmap fills in live row-by-row via imap_unordered + throttled render
  - Sigma scan mode: run N sigma values -> max-p line chart + browse slider + animated 4D + 3D stacked
  - Smart partial cache reuse: unchanged f_bin rows reused from prior result
  - All BinaryParameterConfig orbital params exposed and editable
  - User-controllable canvas dimensions (height / width in px)
"""
from __future__ import annotations

import os
import sys
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from shared import inject_theme, render_sidebar, get_settings_manager

from bc import (
    _render_cadence_dsilva_tab,
    _render_cadence_langer_tab,
    _render_rv_errors_tab,
    _render_compare_tab,
    _render_validation_tab,
    _render_bin_sensitivity_tab,
)

st.set_page_config(
    page_title='Bias Correction \u2014 WR Binary',
    page_icon='\u26a1',
    layout='wide',
)
inject_theme()
settings = render_sidebar('Bias Correction')
sm = get_settings_manager()

st.markdown('# \u26a1 Bias Correction')
st.caption(
    'Monte-Carlo K-S grid search over (f_bin, \u03c0) to find the intrinsic binary fraction '
    'and period-distribution power-law index that best reproduce the observed \u0394RV distribution.'
)

# \u2500\u2500\u2500\u2500\u2500\u2500\u2500 Canvas size (page-level)
with st.expander('\U0001f5bc\ufe0f Canvas size', expanded=False):
    _cs_c1, _cs_c2, _ = st.columns([0.2, 0.2, 0.6])
    canvas_height = _cs_c1.number_input(
        'Height (px)', 200, 2000, 520, 20, key='bc_canvas_height')
    canvas_width = _cs_c2.number_input(
        'Width (px, 0 = auto)', 0, 3000, 0, 50, key='bc_canvas_width')

_ch = int(canvas_height)
_cw = int(canvas_width) if int(canvas_width) > 0 else None
_use_cw = (_cw is None)

# \u2500\u2500\u2500\u2500\u2500\u2500\u2500 Dynamic tab management
if 'bc_tabs' not in st.session_state:
    st.session_state['bc_tabs'] = [
        {'type': 'cadence_dsilva', 'name': 'Cadence (Dsilva)', 'prefix': 'cad'},
        {'type': 'cadence_langer', 'name': 'Cadence (Langer)', 'prefix': 'cal'},
        {'type': 'bin_sensitivity', 'name': 'Bin Sensitivity', 'prefix': 'bsn'},
        {'type': 'rv_errors', 'name': 'RV Errors', 'prefix': 'rve'},
        {'type': 'compare', 'name': 'Compare', 'prefix': 'cmp'},
        {'type': 'validation', 'name': 'Validation', 'prefix': 'val'},
    ]

# "+" button to add new tabs
_tab_mgmt_cols = st.columns([0.85, 0.15])
with _tab_mgmt_cols[1]:
    with st.popover('\u2795 Add tab'):
        _add_type = st.radio(
            'Tab type',
            ['Cadence (Dsilva)', 'Cadence (Langer)', 'Bin Sensitivity',
             'RV Errors', 'Compare', 'Validation'],
            key='_bc_add_tab_type',
        )
        _add_name = st.text_input('Tab name (optional)', key='_bc_add_tab_name')
        _add_col1, _add_col2 = st.columns(2)
        if _add_col1.button('Add', key='_bc_add_tab_btn', type='primary'):
            _idx = len(st.session_state['bc_tabs'])
            _type_map = {'cadence (dsilva)': 'cadence_dsilva',
                         'cadence (langer)': 'cadence_langer',
                         'bin sensitivity': 'bin_sensitivity',
                         'rv errors': 'rv_errors',
                         'compare': 'compare',
                         'validation': 'validation'}
            _type_lower = _type_map.get(_add_type.lower(), _add_type.lower())
            _pfx = f'{_type_lower[:3]}{_idx}'
            st.session_state['bc_tabs'].append({
                'type': _type_lower,
                'name': _add_name or f'{_add_type} {_idx}',
                'prefix': _pfx,
            })
            st.rerun()

        if len(st.session_state['bc_tabs']) > 4:
            if _add_col2.button('Remove last', key='_bc_rm_tab_btn'):
                st.session_state['bc_tabs'].pop()
                st.rerun()

# Create dynamic tabs
_tab_names = [t['name'] for t in st.session_state['bc_tabs']]
_tab_widgets = st.tabs(_tab_names)

for _tw, _ti in zip(_tab_widgets, st.session_state['bc_tabs']):
    with _tw:
        if _ti['type'] == 'cadence_dsilva':
            _render_cadence_dsilva_tab(_ti['prefix'], settings, sm)
        elif _ti['type'] == 'cadence_langer':
            _render_cadence_langer_tab(_ti['prefix'], settings, sm)
        elif _ti['type'] == 'bin_sensitivity':
            _render_bin_sensitivity_tab(_ti['prefix'], settings, sm)
        elif _ti['type'] == 'rv_errors':
            _render_rv_errors_tab(_ti['prefix'], settings, sm)
        elif _ti['type'] == 'compare':
            _render_compare_tab(_ti['prefix'])
        elif _ti['type'] == 'validation':
            _render_validation_tab(_ti['prefix'], settings, sm)

# NOTE: Live polling is handled by @st.fragment(run_every=3) inside each tab\'s
# rendering function. No global auto-refresh needed (avoids full-page flicker).
