"""
pages/rv_errors.py
──────────────────
RV error model configuration: choose distribution type and parameters,
see live preview of the PDF.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

import dash
from dash import html, dcc, callback, Input, Output, State
from dash.exceptions import PreventUpdate
import dash_mantine_components as dmc
from dash_iconify import DashIconify

import sys, os
_APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP not in sys.path:
    sys.path.insert(0, _APP)

from config import get_plotly_theme

dash.register_page(
    __name__,
    path='/rv-errors',
    name='RV Errors',
    title='Bias Correction — RV Errors',
    order=5,
    icon='tabler:chart-candle',
)

_DIST_OPTIONS = [
    {'value': 'fixed', 'label': 'Fixed (constant σ)'},
    {'value': 'normal', 'label': 'Normal'},
    {'value': 'lognormal', 'label': 'Log-Normal'},
    {'value': 'gamma', 'label': 'Gamma'},
    {'value': 'weibull', 'label': 'Weibull'},
    {'value': 'uniform', 'label': 'Uniform'},
]

layout = dmc.Container([
    dcc.Store(id='rve-params-store', storage_type='local'),
    dmc.Title('RV Error Model', order=3),
    dmc.Text('Configure measurement error distributions for single and binary stars.', size='sm', c='dimmed'),

    dmc.Grid([
        # Single stars
        dmc.GridCol(dmc.Paper(dmc.Stack([
            dmc.Title('Single Stars', order=5),
            dmc.Select(id='rve-type-single', label='Distribution', data=_DIST_OPTIONS, value='fixed'),
            dmc.NumberInput(id='rve-sigma-single', label='σ_measure (km/s)', value=1.622,
                            min=0.01, max=100.0, step=0.1, decimalScale=3),
            dmc.NumberInput(id='rve-param1-single', label='Param 1 (shape/mean)', value=1.0,
                            min=0.001, max=100.0, step=0.1),
            dmc.NumberInput(id='rve-param2-single', label='Param 2 (scale/std)', value=0.5,
                            min=0.001, max=100.0, step=0.1),
        ], gap='sm'), shadow='sm', p='md', withBorder=True), span=6),

        # Binary stars
        dmc.GridCol(dmc.Paper(dmc.Stack([
            dmc.Title('Binary Stars', order=5),
            dmc.Select(id='rve-type-binary', label='Distribution', data=_DIST_OPTIONS, value='fixed'),
            dmc.NumberInput(id='rve-sigma-binary', label='σ_measure (km/s)', value=1.622,
                            min=0.01, max=100.0, step=0.1, decimalScale=3),
            dmc.NumberInput(id='rve-param1-binary', label='Param 1 (shape/mean)', value=1.0,
                            min=0.001, max=100.0, step=0.1),
            dmc.NumberInput(id='rve-param2-binary', label='Param 2 (scale/std)', value=0.5,
                            min=0.001, max=100.0, step=0.1),
        ], gap='sm'), shadow='sm', p='md', withBorder=True), span=6),
    ], gutter='md', mt='md'),

    dcc.Graph(id='rve-preview', config={'displaylogo': False}),
], fluid=True, py='md')


@callback(
    Output('rve-preview', 'figure'),
    Input('rve-type-single', 'value'),
    Input('rve-sigma-single', 'value'),
    Input('rve-param1-single', 'value'),
    Input('rve-param2-single', 'value'),
    Input('rve-type-binary', 'value'),
    Input('rve-sigma-binary', 'value'),
    Input('rve-param1-binary', 'value'),
    Input('rve-param2-binary', 'value'),
    State('mantine-provider', 'forceColorScheme'),
)
def update_error_preview(t_s, sig_s, p1_s, p2_s, t_b, sig_b, p1_b, p2_b, color_scheme):
    theme = get_plotly_theme(color_scheme or 'dark')
    fig = go.Figure()
    x = np.linspace(0.01, 20.0, 500)

    for dist_type, sigma, p1, p2, name, color in [
        (t_s, sig_s, p1_s, p2_s, 'Single', '#4A90D9'),
        (t_b, sig_b, p1_b, p2_b, 'Binary', '#E25A53'),
    ]:
        pdf = _compute_pdf(x, dist_type or 'fixed', sigma or 1.0, p1 or 1.0, p2 or 0.5)
        fig.add_trace(go.Scatter(x=x, y=pdf, mode='lines', name=name,
                                 line=dict(color=color, width=2)))

    fig.update_layout(title='Error Distribution Preview',
                      xaxis_title='σ_measure (km/s)', yaxis_title='PDF',
                      height=400, **theme)
    return fig


def _compute_pdf(x, dist_type, sigma, p1, p2):
    """Compute PDF values for the given distribution."""
    from scipy import stats
    if dist_type == 'fixed':
        pdf = np.zeros_like(x)
        idx = np.argmin(np.abs(x - sigma))
        pdf[max(0, idx - 2):idx + 3] = 1.0
        return pdf / (np.sum(pdf) * (x[1] - x[0]) + 1e-10)
    elif dist_type == 'normal':
        return stats.norm.pdf(x, loc=p1, scale=p2)
    elif dist_type == 'lognormal':
        return stats.lognorm.pdf(x, s=p2, scale=np.exp(p1))
    elif dist_type == 'gamma':
        return stats.gamma.pdf(x, a=p1, scale=p2)
    elif dist_type == 'weibull':
        return stats.weibull_min.pdf(x, c=p1, scale=p2)
    elif dist_type == 'uniform':
        return stats.uniform.pdf(x, loc=p1, scale=p2 - p1)
    return np.zeros_like(x)
