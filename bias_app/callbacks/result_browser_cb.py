"""
callbacks/result_browser_cb.py
──────────────────────────────
Load saved .npz result files and populate the result selector.
"""
from __future__ import annotations

import os
import sys

import numpy as np
from dash import callback, Input, Output, State, no_update
from dash.exceptions import PreventUpdate

_APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.dirname(_APP)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from config import RESULTS_DIR, to_json_safe


def register_result_browser_callbacks(prefix: str, model_filter: str = 'dsilva') -> None:
    """Register result file browser callbacks for a model page."""
    p = prefix

    @callback(
        Output(f'{p}-result-select', 'data'),
        Input(f'{p}-refresh-results-btn', 'n_clicks'),
        prevent_initial_call=False,  # populate on load
    )
    def refresh_result_list(n_clicks):
        if not os.path.isdir(RESULTS_DIR):
            return []
        items = []
        for fname in sorted(os.listdir(RESULTS_DIR), reverse=True):
            if not fname.endswith('.npz'):
                continue
            if model_filter and model_filter not in fname.lower():
                continue
            items.append({
                'value': os.path.join(RESULTS_DIR, fname),
                'label': fname.replace('.npz', ''),
            })
        return items[:50]  # limit to 50 most recent

    @callback(
        Output(f'{p}-result-store', 'data', allow_duplicate=True),
        Input(f'{p}-load-btn', 'n_clicks'),
        State(f'{p}-result-select', 'value'),
        prevent_initial_call=True,
    )
    def load_result(n_clicks, path):
        if not path or not os.path.exists(path):
            raise PreventUpdate
        data = dict(np.load(path, allow_pickle=True))
        return to_json_safe(data)
