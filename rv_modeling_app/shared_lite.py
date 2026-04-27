"""
shared_lite.py — Lightweight shared utilities for the standalone RV Modeling app.
Extracts only what rv_modeling needs from app/shared.py.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any

import numpy as np
import streamlit as st

# ── Path setup ───────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from ObservationClass import ObservationManager as _OM

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────
_SETTINGS_PATH = os.path.join(ROOT, 'settings', 'user_settings.json')

# ─────────────────────────────────────────────────────────────────────────────
# Colour constants
# ─────────────────────────────────────────────────────────────────────────────
COLOR_BINARY  = '#E25A53'
COLOR_SINGLE  = '#4A90D9'
COLOR_UNKNOWN = '#8C8C8C'
COLOR_CLEANED = '#52B788'

# ─────────────────────────────────────────────────────────────────────────────
# Theme — matplotlib/academic style (white bg, serif, black axes, no gridlines)
# ─────────────────────────────────────────────────────────────────────────────
_ACADEMIC_AXIS = dict(
    showgrid=False,
    linecolor='black', linewidth=1, mirror=True,
    ticks='outside', tickcolor='black',
    tickfont=dict(family='Times New Roman, serif', size=12, color='black'),
    title=dict(font=dict(family='Times New Roman, serif', size=13, color='black')),
)

PLOTLY_THEME: dict = dict(
    plot_bgcolor='white',
    paper_bgcolor='white',
    font=dict(family='Times New Roman, serif', size=13, color='black'),
    xaxis=dict(**_ACADEMIC_AXIS),
    yaxis=dict(**_ACADEMIC_AXIS),
    title=dict(text='', font=dict(size=15, family='Times New Roman, serif', color='black')),
    legend=dict(
        bgcolor='rgba(255,255,255,0.85)',
        bordercolor='#cccccc', borderwidth=1,
    ),
)

# Academic-style palette returned by get_palette() — keys consumed by rv_modeling/tabs
_ACADEMIC_PALETTE = dict(
    plot_bg='white', paper_bg='white', font_color='black', title_color='black',
    grid_color='#e0e0e0', line_color='black', tick_color='black',
    legend_bg='rgba(255,255,255,0.85)', legend_border='#cccccc',
    app_bg='#ffffff', sidebar_bg='#f5f5f5', heading_color='black',
    card_bg='#ffffff', card_border='#d0d0d0', card_shadow='rgba(0,0,0,0.08)',
    label_color='#555555', value_color='black', sub_color='#666666',
    muted_color='#777777',
    annotation_bg='rgba(255,255,255,0.9)', annotation_border='#cccccc',
    annotation_font='black',
    tag_bg='#e8f0fe', tag_fg='#1a4a80',
    contour_color='#555555', contour_label='black',
)


def get_palette() -> dict:
    """Return academic/white palette dict for use in page code."""
    return _ACADEMIC_PALETTE


def inject_theme() -> None:
    """Inject CSS for Streamlit; Plotly plots stay academic/white."""
    PLOTLY_THEME.clear()
    PLOTLY_THEME.update(dict(
        plot_bgcolor='white',
        paper_bgcolor='white',
        font=dict(family='Times New Roman, serif', size=13, color='black'),
        xaxis=dict(**_ACADEMIC_AXIS),
        yaxis=dict(**_ACADEMIC_AXIS),
        title=dict(text='', font=dict(size=15, family='Times New Roman, serif', color='black')),
        legend=dict(
            bgcolor='rgba(255,255,255,0.85)',
            bordercolor='#cccccc', borderwidth=1,
        ),
    ))
    st.markdown("""
<style>
h1, h2, h3 { font-family: serif; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# SettingsManager
# ─────────────────────────────────────────────────────────────────────────────
class SettingsManager:
    def load(self) -> dict:
        if '_settings' not in st.session_state:
            st.session_state['_settings'] = self._read_disk()
        return st.session_state['_settings']

    def save(self, keys: list[str] | str, value: Any) -> None:
        settings = self.load()
        if isinstance(keys, str):
            keys = [keys]
        d = settings
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value
        self._write_disk(settings)

    def reload(self) -> dict:
        if '_settings' in st.session_state:
            del st.session_state['_settings']
        return self.load()

    @staticmethod
    def _read_disk() -> dict:
        if os.path.exists(_SETTINGS_PATH):
            with open(_SETTINGS_PATH) as f:
                return json.load(f)
        return {}

    @staticmethod
    def _write_disk(settings: dict) -> None:
        os.makedirs(os.path.dirname(_SETTINGS_PATH), exist_ok=True)
        with open(_SETTINGS_PATH, 'w') as f:
            json.dump(settings, f, indent=2, default=str)


@st.cache_resource
def get_settings_manager() -> SettingsManager:
    return SettingsManager()


# ─────────────────────────────────────────────────────────────────────────────
# ObservationManager singleton
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_obs_manager() -> _OM:
    return _OM(
        data_dir=os.path.join(ROOT, 'Data/'),
        backup_dir=os.path.join(ROOT, 'Backups/'),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Cached data loaders (mirror app/shared.py)
# ─────────────────────────────────────────────────────────────────────────────
def settings_hash(settings: dict) -> str:
    """Hash classification-relevant keys only."""
    relevant = {
        'primary_line':   settings.get('primary_line'),
        'classification': settings.get('classification'),
    }
    return hashlib.sha256(
        json.dumps(relevant, sort_keys=True, default=str).encode()
    ).hexdigest()[:12]


@st.cache_data
def cached_load_observed_delta_rvs(settings_hash: str) -> tuple[np.ndarray, dict]:
    from pipeline.load_observations import load_observed_delta_rvs
    sm = get_settings_manager()
    return load_observed_delta_rvs(sm.load(), get_obs_manager())


@st.cache_data
def cached_load_cadence(_hash: str) -> tuple[list, np.ndarray]:
    from pipeline.load_observations import load_cadence_library
    return load_cadence_library(get_obs_manager())


def render_sidebar(page_name: str = '') -> dict:
    """Minimal sidebar for standalone — returns current settings dict."""
    sm = get_settings_manager()
    settings = sm.load()
    with st.sidebar:
        if page_name:
            st.markdown(f'## {page_name}')
            st.divider()
        if st.button('Clear cache', key='_sidebar_clear_cache_lite'):
            st.cache_data.clear()
            st.success('Cache cleared.')
    return settings
