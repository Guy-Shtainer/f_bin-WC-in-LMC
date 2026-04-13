"""
shared_lite.py — Lightweight shared utilities for the standalone Spectrum app.
Extracts only what the Spectrum page needs from app/shared.py.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

import streamlit as st

# ── Path setup ───────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Add app/ to path so we can import spectrum_helpers
_APP_DIR = os.path.join(ROOT, 'app')
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

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


def inject_theme() -> None:
    """Inject CSS for dark Streamlit app, but Plotly plots stay academic/white."""
    st.session_state['_dark_mode'] = True
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
.metric-card {
    background: #f8f8f8; border-radius: 10px; padding: 16px 20px;
    text-align: center; border: 1px solid #cccccc;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}
.metric-card .label { font-size: 0.82rem; color: #555555; text-transform: uppercase; letter-spacing: 0.05em; }
.metric-card .value { font-size: 2rem; font-weight: 700; color: #000000; margin-top: 4px; }
.metric-card .sub { font-size: 0.78rem; color: #666666; margin-top: 2px; }
.status-chip-binary { color: #E25A53; font-weight: 600; }
.status-chip-single { color: #4A90D9; }
.status-chip-unknown { color: #8C8C8C; }
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
