"""
pages/langer.py
───────────────
Langer 2020 two-component period model page.
Differs from Dsilva: σ on x-axis (not π), period distribution selectors, q preset.
"""
from __future__ import annotations

import dash
from dash import html, dcc
import dash_mantine_components as dmc

import sys, os
_APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP not in sys.path:
    sys.path.insert(0, _APP)

from components.param_panels import build_langer_params
from components.scoring_tabs import build_scoring_tabs

dash.register_page(
    __name__,
    path='/langer',
    name='Langer',
    title='Bias Correction — Langer',
    order=1,
    icon='tabler:chart-histogram',
)

PREFIX = 'langer'

layout = dmc.Container([
    dcc.Store(id=f'{PREFIX}-params-store', storage_type='local'),
    dcc.Store(id=f'{PREFIX}-result-store', storage_type='memory'),
    dcc.Store(id=f'{PREFIX}-presets-store', storage_type='local'),
    dmc.Grid([
        dmc.GridCol(build_langer_params(PREFIX), span=4),
        dmc.GridCol(dmc.Stack([
            dmc.Title('Langer Model', order=3),
            dmc.Text('Langer et al. 2020: two-component (Case A + B) period distribution', size='sm', c='dimmed'),
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
register_result_browser_callbacks(PREFIX, model_filter='langer')
register_sim_plot_callbacks(PREFIX)

from callbacks.simulation_langer_cb import register_langer_simulation_callback
from callbacks.ui_callbacks import register_langer_preset_callbacks
register_langer_simulation_callback(PREFIX)
register_langer_preset_callbacks(PREFIX)

from callbacks.method_detail_cb import register_method_detail_callbacks
register_method_detail_callbacks(PREFIX)

from callbacks.detail_plots_cb import register_detail_plot_callbacks
register_detail_plot_callbacks(PREFIX)
