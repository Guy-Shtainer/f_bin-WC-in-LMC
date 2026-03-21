"""
pages/comparison.py
───────────────────
Side-by-side comparison of two saved simulation results.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import dash
from dash import html, dcc, callback, Input, Output, State, no_update
from dash.exceptions import PreventUpdate
import dash_mantine_components as dmc
from dash_iconify import DashIconify

_APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP not in sys.path:
    sys.path.insert(0, _APP)

from config import RESULTS_DIR, from_json_safe, to_json_safe, get_plotly_theme, SCORING_METHODS

dash.register_page(
    __name__,
    path='/comparison',
    name='Comparison',
    title='Bias Correction — Comparison',
    order=4,
    icon='tabler:arrows-diff',
)

layout = dmc.Container([
    dcc.Store(id='cmp-result-a', storage_type='memory'),
    dcc.Store(id='cmp-result-b', storage_type='memory'),

    dmc.Title('Result Comparison', order=3),
    dmc.Text('Compare two saved simulation results side-by-side.', size='sm', c='dimmed'),

    dmc.Grid([
        dmc.GridCol(dmc.Stack([
            dmc.Select(id='cmp-select-a', label='Result A', data=[], searchable=True,
                       placeholder='Select first result'),
            dmc.Button('Load A', id='cmp-load-a', variant='light', size='sm'),
        ], gap='xs'), span=6),
        dmc.GridCol(dmc.Stack([
            dmc.Select(id='cmp-select-b', label='Result B', data=[], searchable=True,
                       placeholder='Select second result'),
            dmc.Button('Load B', id='cmp-load-b', variant='light', size='sm'),
        ], gap='xs'), span=6),
    ], gutter='md', mt='md'),

    dmc.Select(id='cmp-method', label='Scoring method', mt='md',
               data=[{'value': mk, 'label': mn} for mk, mn, _, _, _ in SCORING_METHODS],
               value='ks'),

    dmc.Grid([
        dmc.GridCol(dcc.Graph(id='cmp-heatmap-a', config={'displaylogo': False}), span=6),
        dmc.GridCol(dcc.Graph(id='cmp-heatmap-b', config={'displaylogo': False}), span=6),
    ], gutter='md', mt='md'),

    dcc.Graph(id='cmp-cdf-overlay', config={'displaylogo': False}),
], fluid=True, py='md')


# ── Populate result selectors ────────────────────────────────────────────────
@callback(
    Output('cmp-select-a', 'data'),
    Output('cmp-select-b', 'data'),
    Input('url', 'pathname'),
)
def populate_result_lists(pathname):
    if not os.path.isdir(RESULTS_DIR):
        return [], []
    items = []
    for f in sorted(os.listdir(RESULTS_DIR), reverse=True):
        if f.endswith('.npz'):
            items.append({'value': os.path.join(RESULTS_DIR, f), 'label': f.replace('.npz', '')})
    return items[:50], items[:50]


# ── Load results ─────────────────────────────────────────────────────────────
@callback(Output('cmp-result-a', 'data'), Input('cmp-load-a', 'n_clicks'),
          State('cmp-select-a', 'value'), prevent_initial_call=True)
def load_a(n, path):
    if not path or not os.path.exists(path):
        raise PreventUpdate
    return to_json_safe(dict(np.load(path, allow_pickle=True)))

@callback(Output('cmp-result-b', 'data'), Input('cmp-load-b', 'n_clicks'),
          State('cmp-select-b', 'value'), prevent_initial_call=True)
def load_b(n, path):
    if not path or not os.path.exists(path):
        raise PreventUpdate
    return to_json_safe(dict(np.load(path, allow_pickle=True)))


# ── Heatmaps ─────────────────────────────────────────────────────────────────
@callback(
    Output('cmp-heatmap-a', 'figure'),
    Output('cmp-heatmap-b', 'figure'),
    Input('cmp-result-a', 'data'),
    Input('cmp-result-b', 'data'),
    Input('cmp-method', 'value'),
    State('mantine-provider', 'forceColorScheme'),
)
def update_comparison_heatmaps(data_a, data_b, method, color_scheme):
    theme = get_plotly_theme(color_scheme or 'dark')
    method_info = {mk: (mn, pk) for mk, mn, pk, _, _ in SCORING_METHODS}
    mn, pk = method_info.get(method, ('K-S', 'ks_p'))

    fig_a = _build_cmp_heatmap(data_a, pk, f'Result A — {mn}', theme)
    fig_b = _build_cmp_heatmap(data_b, pk, f'Result B — {mn}', theme)
    return fig_a, fig_b


def _build_cmp_heatmap(data, p_key, title, theme):
    if not data:
        fig = go.Figure()
        fig.add_annotation(text='No result loaded', xref='paper', yref='paper',
                           x=0.5, y=0.5, showarrow=False, font=dict(size=14, color='grey'))
        fig.update_layout(height=350, xaxis=dict(visible=False), yaxis=dict(visible=False), **theme)
        return fig

    result = from_json_safe(data)
    arr = np.array(result.get(p_key, []))
    if arr.size == 0:
        fig = go.Figure()
        fig.add_annotation(text='No data for this method', xref='paper', yref='paper',
                           x=0.5, y=0.5, showarrow=False)
        fig.update_layout(height=350, **theme)
        return fig

    while arr.ndim > 2:
        arr = np.nanmax(arr, axis=0)

    fbin_g = np.array(result.get('fbin_grid', []))
    x_g = np.array(result.get('pi_grid', result.get('sigma_grid', [])))

    fig = go.Figure(data=go.Heatmap(z=arr, x=x_g, y=fbin_g, colorscale='Viridis'))
    fig.update_layout(title=dict(text=title), height=350, **theme)
    return fig


# ── CDF overlay ──────────────────────────────────────────────────────────────
@callback(
    Output('cmp-cdf-overlay', 'figure'),
    Input('cmp-result-a', 'data'),
    Input('cmp-result-b', 'data'),
    State('mantine-provider', 'forceColorScheme'),
)
def update_cdf_overlay(data_a, data_b, color_scheme):
    theme = get_plotly_theme(color_scheme or 'dark')
    fig = go.Figure()

    for data, name, color in [(data_a, 'Result A', '#4A90D9'), (data_b, 'Result B', '#E25A53')]:
        if not data:
            continue
        obs = np.array(data.get('obs_delta_rv', []))
        if obs.size == 0:
            continue
        obs_sorted = np.sort(obs)
        cdf = np.arange(1, len(obs_sorted) + 1) / len(obs_sorted)
        fig.add_trace(go.Scatter(x=obs_sorted, y=cdf, mode='lines', name=name,
                                 line=dict(color=color, width=2)))

    fig.update_layout(title='Observed ΔRV CDF', xaxis_title='ΔRV (km/s)',
                      yaxis_title='Cumulative Fraction', height=400, **theme)
    return fig
