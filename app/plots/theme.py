"""plots/theme.py — Academic white theme for Plotly (A&A / ApJ paper style)."""
from __future__ import annotations

import colorsys

import plotly.graph_objects as go
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# Academic white theme
# ─────────────────────────────────────────────────────────────────────────────
_ACADEMIC_THEME = dict(
    plot_bgcolor='white',
    paper_bgcolor='white',
    font=dict(family='Times New Roman, serif', size=13, color='black'),
    xaxis=dict(
        showgrid=False, linecolor='black', linewidth=1.2, mirror=True,
        ticks='outside', tickcolor='black', tickwidth=1,
        tickfont=dict(size=11), title_font=dict(size=13),
        zeroline=False,
    ),
    yaxis=dict(
        showgrid=False, linecolor='black', linewidth=1.2, mirror=True,
        ticks='outside', tickcolor='black', tickwidth=1,
        tickfont=dict(size=11), title_font=dict(size=13),
        zeroline=False,
    ),
    title=dict(font=dict(size=15, family='Times New Roman, serif', color='black')),
    legend=dict(
        bgcolor='rgba(255,255,255,0)', bordercolor='black', borderwidth=0.5,
        font=dict(size=10, color='black'),
    ),
    margin=dict(l=60, r=20, t=50, b=50),
)


def _academic_fig(**overrides) -> go.Figure:
    """Create a Plotly figure with academic white theme."""
    fig = go.Figure()
    fig.update_layout(**{**_ACADEMIC_THEME, **overrides})
    return fig


def _show(fig, caption=None, **kwargs):
    """Display Plotly figure + optional caption."""
    st.plotly_chart(fig, width='stretch', theme=None, **kwargs)
    if caption:
        st.caption(caption)


def _epoch_colors(n: int) -> list:
    """Generate n distinct hue-spaced colors as hex strings."""
    return [
        '#' + ''.join(f'{int(c * 255):02x}'
                       for c in colorsys.hsv_to_rgb(i / max(n, 1), 0.7, 0.8))
        for i in range(n)
    ]


_EMISSION_BAND_COLORS = [
    'rgba(255,100,100,0.12)', 'rgba(100,100,255,0.12)',
    'rgba(100,255,100,0.12)', 'rgba(255,200,100,0.12)',
    'rgba(200,100,255,0.12)', 'rgba(100,255,255,0.12)',
    'rgba(255,150,200,0.12)', 'rgba(200,200,100,0.12)',
    'rgba(150,100,100,0.12)', 'rgba(100,200,150,0.12)',
    'rgba(150,150,255,0.12)',
]


def _add_emission_bands(fig, lines_dict: dict):
    """Add semi-transparent vertical bands for emission lines on a Plotly figure."""
    for i, (name, rng) in enumerate(lines_dict.items()):
        lam_min = rng[0] * 10.0  # nm → Å
        lam_max = rng[1] * 10.0
        color = _EMISSION_BAND_COLORS[i % len(_EMISSION_BAND_COLORS)]
        fig.add_vrect(
            x0=lam_min, x1=lam_max,
            fillcolor=color, line_width=0, layer='below',
            annotation_text=name, annotation_position='top left',
            annotation_font=dict(size=7, color='#333333'),
        )
