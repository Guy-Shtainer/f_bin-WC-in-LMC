"""
tabs/classification.py — Tab 3: Per-star classification workflow + summary table.
"""
from __future__ import annotations

import json
import os

import pandas as pd
import streamlit as st

import numpy as np

import specs
from helpers.data_loaders import load_rvs, get_mjd, classify_star_line
from shared_lite import ROOT, COLOR_BINARY, COLOR_SINGLE, COLOR_UNKNOWN

# ── Classification persistence ───────────────────────────────────────────────
_CLASSIFICATION_PATH = os.path.join(ROOT, 'settings', 'star_classifications.json')
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


def render(star_name: str, epochs: list, settings: dict) -> None:
    """Render the classification tab: per-star form + summary table."""
    primary_line = settings.get('primary_line', 'C IV 5808-5812')
    star_names = specs.star_names

    st.markdown(f'### Classify: **{star_name}**')

    # Show automated classification result
    cls_cfg = settings.get('classification', {})
    _auto = classify_star_line(
        star_name, primary_line,
        _threshold=cls_cfg.get('threshold_dRV', 45.5),
        _sigma_factor=cls_cfg.get('sigma_factor', 4.0),
    )
    _auto_bin = _auto['is_binary']
    _auto_drv = _auto['best_dRV']
    _auto_sig = _auto['best_sigma']
    _auto_signif = _auto_drv - 4.0 * _auto_sig if not np.isnan(_auto_sig) else float('nan')
    if _auto_bin is True:
        _auto_label = f'<span style="color:{COLOR_BINARY};font-weight:700;">Binary</span>'
    elif _auto_bin is False:
        _auto_label = f'<span style="color:{COLOR_SINGLE};font-weight:600;">Single</span>'
    else:
        _auto_label = f'<span style="color:{COLOR_UNKNOWN};">Unknown</span>'
    st.markdown(
        f'Algorithm ({primary_line}): {_auto_label} &nbsp;|&nbsp; '
        f'ΔRV = {_auto_drv:.1f} km/s &nbsp; σ = {_auto_sig:.1f} &nbsp; '
        f'ΔRV−4σ = {_auto_signif:.1f}',
        unsafe_allow_html=True,
    )

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
        placeholder='e.g., Possible He I absorption at 4471A, needs more epochs...',
    )

    btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)
    save_clicked = btn_col1.button('Save Classification', key='cls_save', type='primary')

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
    st.markdown(f'### RV Measurements — {primary_line}')
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
        df_rv['DRV (km/s)'] = (df_rv['RV (km/s)'] - mean_rv).round(2)
        st.dataframe(df_rv, use_container_width=True, hide_index=True)
    else:
        st.info('No RV data saved for this star on the primary line.')

    # ── Full classification table ────────────────────────────────────────
    st.markdown('---')
    st.markdown('## Classification Summary — All Stars')
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
    if exp_col1.button('Export classifications as CSV', key='cls_export'):
        csv_data = df_cls.to_csv(index=False)
        st.download_button(
            'Download CSV', csv_data, 'star_classifications.csv', 'text/csv', key='cls_download',
        )
    if exp_col2.button('Clear all classifications', key='cls_clear'):
        _save_classifications({})
        st.toast('All classifications cleared.')
        st.rerun()
