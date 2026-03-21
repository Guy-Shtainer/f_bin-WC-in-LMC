"""
bias_app/config.py
──────────────────
Configuration, paths, theme constants, and utility functions for the Dash bias-correction app.
"""
from __future__ import annotations

import os
import sys

import numpy as np

# ── Path setup ───────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

RESULTS_DIR = os.path.join(ROOT, 'results')
SETTINGS_PATH = os.path.join(ROOT, 'settings', 'user_settings.json')
PRESETS_DIR = os.path.join(ROOT, 'settings', 'presets')

# ── Colour constants ─────────────────────────────────────────────────────────
COLOR_BINARY = '#E25A53'
COLOR_SINGLE = '#4A90D9'
COLOR_UNKNOWN = '#8C8C8C'
COLOR_CLEANED = '#52B788'
COLOR_GOLD = '#DAA520'

# ── Scoring methods (key, display_name, p_key, D_key, color) ─────────────────
SCORING_METHODS = [
    ('ks',         'K-S (standard)',  'ks_p',       'ks_D',       '#4A90D9'),
    ('weighted',   'K-S (weighted)',  'weighted_p', 'weighted_D', '#50C878'),
    ('cvm',        'CvM (S-score)',   'cvm_p',      'cvm_D',      '#E25A53'),
    ('likelihood', 'Likelihood',      'likelihood', 'logL_raw',   '#DAA520'),
]
METHOD_COLORS = {m[0]: m[4] for m in SCORING_METHODS}

# ── Plotly themes ─────────────────────────────────────────────────────────────

def _build_axis(palette: dict) -> dict:
    return dict(
        showgrid=True, gridcolor=palette['grid_color'], gridwidth=1,
        linecolor=palette['line_color'], linewidth=1, mirror=True,
        ticks='outside', tickcolor=palette['tick_color'],
    )

_DARK_PALETTE = dict(
    plot_bg='#1e1e2e', paper_bg='#1e1e2e', font_color='#e0e0e0',
    title_color='#f0f0f0', grid_color='#3a3a4a', line_color='#aaaaaa',
    tick_color='#aaaaaa', legend_bg='rgba(30,30,46,0.9)',
    legend_border='#555555',
)

_LIGHT_PALETTE = dict(
    plot_bg='white', paper_bg='white', font_color='#333333',
    title_color='#222222', grid_color='#e0e0e0', line_color='#333333',
    tick_color='#333333', legend_bg='rgba(255,255,255,0.85)',
    legend_border='#cccccc',
)


def _build_plotly_theme(palette: dict) -> dict:
    ax = _build_axis(palette)
    return dict(
        plot_bgcolor=palette['plot_bg'],
        paper_bgcolor=palette['paper_bg'],
        font=dict(family='serif', size=13, color=palette['font_color']),
        xaxis=dict(**ax),
        yaxis=dict(**ax),
        title=dict(text='', font=dict(size=15, family='serif',
                                       color=palette['title_color'])),
        legend=dict(bgcolor=palette['legend_bg'],
                    bordercolor=palette['legend_border'], borderwidth=1),
    )


PLOTLY_THEME_DARK = _build_plotly_theme(_DARK_PALETTE)
PLOTLY_THEME_LIGHT = _build_plotly_theme(_LIGHT_PALETTE)


def get_plotly_theme(color_scheme: str = 'dark') -> dict:
    """Return the Plotly theme dict for the given DMC color scheme."""
    return PLOTLY_THEME_DARK if color_scheme == 'dark' else PLOTLY_THEME_LIGHT


# ── numpy ↔ JSON conversion (CRITICAL for dcc.Store) ─────────────────────────

def to_json_safe(obj):
    """Convert numpy types to JSON-serializable Python types (recursive)."""
    if isinstance(obj, dict):
        return {k: to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_json_safe(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


_ARRAY_KEYS = frozenset({
    'ks_p', 'ks_D', 'weighted_p', 'weighted_D',
    'cvm_p', 'cvm_D', 'logL_raw', 'cvm_S_raw',
    'fbin_grid', 'pi_grid', 'sigma_grid', 'logPmax_grid',
})


def from_json_safe(data: dict, array_keys: frozenset | None = None) -> dict:
    """Convert lists back to numpy arrays for known scoring/grid keys."""
    keys = array_keys or _ARRAY_KEYS
    result = {}
    for k, v in data.items():
        if k in keys and isinstance(v, list):
            result[k] = np.array(v)
        else:
            result[k] = v
    return result
