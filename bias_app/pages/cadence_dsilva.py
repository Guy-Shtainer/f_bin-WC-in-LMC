"""Cadence-aware Dsilva model page."""
from __future__ import annotations

import dash
from dash import html, dcc
import dash_mantine_components as dmc

import sys, os
_APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP not in sys.path:
    sys.path.insert(0, _APP)

from components.param_panels import build_cadence_dsilva_params
from components.scoring_tabs import build_scoring_tabs

dash.register_page(
    __name__,
    path='/cadence-dsilva',
    name='Cadence (D)',
    title='Bias Correction — Cadence Dsilva',
    order=2,
    icon='tabler:clock-play',
)

PREFIX = 'cadence-dsilva'

layout = dmc.Container([
    dcc.Store(id=f'{PREFIX}-params-store', storage_type='local'),
    dcc.Store(id=f'{PREFIX}-result-store', storage_type='memory'),
    dcc.Store(id=f'{PREFIX}-presets-store', storage_type='local'),
    dmc.Grid([
        dmc.GridCol(build_cadence_dsilva_params(PREFIX), span=4),
        dmc.GridCol(dmc.Stack([
            dmc.Title('Cadence-Aware Dsilva', order=3),
            dmc.Text('Deterministic cadence matching + power-law periods', size='sm', c='dimmed'),
            build_scoring_tabs(PREFIX),
        ], gap='sm'), span=8),
    ], gutter='lg'),
], fluid=True, py='md')

from callbacks.ui_callbacks import register_ui_callbacks
from callbacks.scoring_cb import register_scoring_callbacks
from callbacks.persistence_cb import register_persistence_callbacks
from callbacks.result_browser_cb import register_result_browser_callbacks
from callbacks.sim_plots_cb import register_sim_plot_callbacks

register_ui_callbacks(PREFIX)
register_scoring_callbacks(PREFIX)
register_persistence_callbacks(PREFIX)
register_result_browser_callbacks(PREFIX, model_filter='cadence_dsilva')
register_sim_plot_callbacks(PREFIX)

from callbacks.simulation_cadence_cb import register_cadence_simulation_callback
register_cadence_simulation_callback(PREFIX, period_model='powerlaw')

from callbacks.method_detail_cb import register_method_detail_callbacks
register_method_detail_callbacks(PREFIX)

from callbacks.detail_plots_cb import register_detail_plot_callbacks
register_detail_plot_callbacks(PREFIX)
