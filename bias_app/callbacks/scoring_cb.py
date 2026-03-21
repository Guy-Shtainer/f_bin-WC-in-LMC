"""
callbacks/scoring_cb.py
───────────────────────
Callbacks that render scoring method figures when result data arrives.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import plotly.graph_objects as go
from dash import callback, Input, Output, State, html, no_update
from dash.exceptions import PreventUpdate
import dash_mantine_components as dmc

_APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP not in sys.path:
    sys.path.insert(0, _APP)

from config import (
    SCORING_METHODS, METHOD_COLORS, COLOR_GOLD, COLOR_BINARY, COLOR_SINGLE,
    from_json_safe, get_plotly_theme,
)


def register_scoring_callbacks(prefix: str) -> None:
    """Register scoring analysis callbacks for a model page."""
    p = prefix

    # ── Method summary (Simulation tab) ──────────────────────────────────
    @callback(
        Output(f'{p}-method-summary', 'children'),
        Input(f'{p}-result-store', 'data'),
        State('mantine-provider', 'forceColorScheme'),
    )
    def update_method_summary(data, color_scheme):
        if not data:
            return dmc.Text('Run a simulation or load a saved result.', c='dimmed')

        result = from_json_safe(data)
        rows = []
        for mk, mname, pk, dk, mcolor in SCORING_METHODS:
            p_arr = result.get(pk)
            if p_arr is None:
                continue
            if isinstance(p_arr, list):
                p_arr = np.array(p_arr)
            if p_arr.size == 0 or not np.any(np.isfinite(p_arr)):
                continue
            best_idx = np.unravel_index(int(np.nanargmax(p_arr)), p_arr.shape)
            fbin_g = np.array(result.get('fbin_grid', []))
            pi_g = np.array(result.get('pi_grid', []))
            best_fbin = fbin_g[best_idx[-2]] if len(fbin_g) > 0 else 0
            best_pi = pi_g[best_idx[-1]] if len(pi_g) > 0 else 0
            best_val = float(np.nanmax(p_arr))
            rows.append([mname, f'{best_fbin:.3f}', f'{best_pi:.2f}', f'{best_val:.4f}'])

        if not rows:
            return dmc.Text('No scoring data available.', c='dimmed')

        return dmc.Table(
            data={
                'head': ['Method', 'Best f_bin', 'Best π', 'Best Score'],
                'body': rows,
            },
            striped=True,
            highlightOnHover=True,
            withTableBorder=True,
            withColumnBorders=True,
        )

    # ── Per-method heatmaps ──────────────────────────────────────────────
    for mk, mname, pk, dk, mcolor in SCORING_METHODS:
        _register_method_heatmap(p, mk, mname, pk)

    # NOTE: Simulation CDF callback is in sim_plots_cb.py (registered separately)


def _register_method_heatmap(p: str, method_key: str, display_name: str, p_key: str):
    """Register heatmap callback for one scoring method."""
    m = f'{p}-{method_key}'

    @callback(
        Output(f'{m}-heatmap', 'figure'),
        Output(f'{m}-best-fit', 'children'),
        Input(f'{p}-result-store', 'data'),
        State('mantine-provider', 'forceColorScheme'),
        prevent_initial_call=True,
    )
    def update_heatmap(data, color_scheme, _mk=method_key, _mn=display_name, _pk=p_key):
        if not data:
            raise PreventUpdate

        result = from_json_safe(data)
        p_arr = result.get(_pk)
        if p_arr is None:
            fig = _build_empty_figure(f'No {_mn} data', color_scheme)
            return fig, dmc.Text(f'No {_mn} data available.', c='dimmed')

        fbin_g = result.get('fbin_grid', [])
        pi_g = result.get('pi_grid', [])
        theme = get_plotly_theme(color_scheme)

        # Handle multi-dimensional (take max over outer dims for display)
        arr = np.array(p_arr)
        while arr.ndim > 2:
            arr = np.nanmax(arr, axis=0)

        fig = _build_heatmap(arr, fbin_g, pi_g, _mn, theme)

        # Best-fit text
        if arr.size == 0 or not np.any(np.isfinite(arr)):
            raise PreventUpdate
        best_idx = np.unravel_index(int(np.nanargmax(arr)), arr.shape)
        best_fbin = fbin_g[best_idx[0]] if len(fbin_g) > best_idx[0] else 0
        best_pi = pi_g[best_idx[1]] if len(pi_g) > best_idx[1] else 0
        best_val = float(np.nanmax(arr))

        best_fit = dmc.Group([
            dmc.Text(f'{_mn}', fw=600),
            dmc.Text(f'Best: f_bin = {best_fbin:.3f}, π = {best_pi:.2f}, '
                     f'score = {best_val:.4f}', size='sm'),
        ], gap='md')

        return fig, best_fit


def _build_heatmap(z, y_vals, x_vals, title, theme):
    """Build a Plotly heatmap figure."""
    y_arr = np.array(y_vals)
    x_arr = np.array(x_vals)
    z_arr = np.array(z)

    fig = go.Figure(data=go.Heatmap(
        z=z_arr,
        x=x_arr,
        y=y_arr,
        colorscale='Viridis',
        colorbar=dict(title=title),
        hovertemplate='π: %{x:.2f}<br>f_bin: %{y:.3f}<br>Score: %{z:.4f}<extra></extra>',
    ))

    # Best-fit gold star marker
    if z_arr.size > 0 and np.any(np.isfinite(z_arr)):
        best_idx = np.unravel_index(int(np.nanargmax(z_arr)), z_arr.shape)
        fig.add_trace(go.Scatter(
            x=[x_arr[best_idx[1]]],
            y=[y_arr[best_idx[0]]],
            mode='markers',
            marker=dict(symbol='star', size=15, color=COLOR_GOLD,
                        line=dict(color='black', width=1)),
            name='Best fit',
            showlegend=False,
        ))

    fig.update_layout(
        title=dict(text=title),
        xaxis_title='π (period power-law index)',
        yaxis_title='f_bin (binary fraction)',
        **theme,
    )
    return fig


def _build_empty_figure(message, color_scheme='dark'):
    """Return an empty Plotly figure with a centered message."""
    theme = get_plotly_theme(color_scheme or 'dark')
    fig = go.Figure()
    fig.add_annotation(
        text=message, xref='paper', yref='paper', x=0.5, y=0.5,
        showarrow=False, font=dict(size=16, color='grey'),
    )
    fig.update_layout(
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        height=300, **theme,
    )
    return fig
