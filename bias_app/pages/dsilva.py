"""
pages/dsilva.py
───────────────
Dsilva power-law period model page.
Layout: left sidebar (params) + right area (nested scoring tabs).
"""
from __future__ import annotations

import dash
from dash import html, dcc, callback, Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate
import dash_mantine_components as dmc

import sys, os
_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.dirname(_HERE)
if _APP not in sys.path:
    sys.path.insert(0, _APP)

from components.param_panels import build_dsilva_params
from components.scoring_tabs import build_scoring_tabs

# ── Register page ────────────────────────────────────────────────────────────
dash.register_page(
    __name__,
    path='/',
    name='Dsilva',
    title='Bias Correction — Dsilva',
    order=0,
    icon='tabler:chart-dots-3',
    redirect_from=['/dsilva'],
)

PREFIX = 'dsilva'

# ── Layout ───────────────────────────────────────────────────────────────────
layout = dmc.Container([
    # Per-page stores
    dcc.Store(id=f'{PREFIX}-params-store', storage_type='local'),
    dcc.Store(id=f'{PREFIX}-result-store', storage_type='memory'),
    dcc.Store(id=f'{PREFIX}-presets-store', storage_type='local'),

    # Two-column grid: params (left) + results (right)
    dmc.Grid([
        dmc.GridCol(
            build_dsilva_params(PREFIX),
            span=4,
        ),
        dmc.GridCol(
            dmc.Stack([
                dmc.Title('Dsilva Model', order=3),
                dmc.Text('Power-law period distribution: p(logP) ∝ (logP)^π', size='sm', c='dimmed'),
                build_scoring_tabs(PREFIX),
            ], gap='sm'),
            span=8,
        ),
    ], gutter='lg'),
], fluid=True, py='md')


# ── Callbacks ────────────────────────────────────────────────────────────────
# These are imported from callbacks/ modules. Register them here so Dash
# discovers them when this page module loads.

from callbacks.ui_callbacks import register_ui_callbacks
from callbacks.scoring_cb import register_scoring_callbacks
from callbacks.simulation_cb import register_simulation_callback
from callbacks.persistence_cb import register_persistence_callbacks
from callbacks.result_browser_cb import register_result_browser_callbacks
from callbacks.sim_plots_cb import register_sim_plot_callbacks

register_ui_callbacks(PREFIX)
register_scoring_callbacks(PREFIX)
register_simulation_callback(PREFIX)
register_persistence_callbacks(PREFIX)
register_result_browser_callbacks(PREFIX, model_filter='dsilva')
register_sim_plot_callbacks(PREFIX)

from callbacks.method_detail_cb import register_method_detail_callbacks
register_method_detail_callbacks(PREFIX)

from callbacks.detail_plots_cb import register_detail_plot_callbacks
register_detail_plot_callbacks(PREFIX)
