"""
callbacks/ui_callbacks.py
─────────────────────────
UI toggle callbacks: show/hide conditional parameter sections.
Called from each page module to register page-specific callbacks.
"""
from __future__ import annotations

from dash import callback, Input, Output, State


def register_ui_callbacks(prefix: str) -> None:
    """Register UI toggle callbacks for a model page with given prefix."""
    p = prefix

    # ── Sigma scan: toggle between single value and range ────────────────
    @callback(
        Output(f'{p}-sigma-single-container', 'style'),
        Output(f'{p}-sigma-range-container', 'style'),
        Input(f'{p}-scan-sigma', 'checked'),
    )
    def toggle_sigma_scan(checked):
        if checked:
            return {'display': 'none'}, {'display': 'block'}
        return {'display': 'block'}, {'display': 'none'}

    # ── logP_max scan: toggle range visibility ───────────────────────────
    @callback(
        Output(f'{p}-logpmax-range-container', 'style'),
        Input(f'{p}-scan-logpmax', 'checked'),
    )
    def toggle_logpmax_scan(checked):
        return {'display': 'block'} if checked else {'display': 'none'}

    # ── Eccentricity model: show/hide e_max ──────────────────────────────
    @callback(
        Output(f'{p}-emax-container', 'style'),
        Input(f'{p}-e-model', 'value'),
    )
    def toggle_emax(model):
        return {'display': 'block'} if model == 'flat' else {'display': 'none'}

    # ── Mass model: toggle fixed vs range ────────────────────────────────
    @callback(
        Output(f'{p}-mass-fixed-container', 'style'),
        Output(f'{p}-mass-range-container', 'style'),
        Input(f'{p}-mass-model', 'value'),
    )
    def toggle_mass_model(model):
        if model == 'fixed':
            return {'display': 'block'}, {'display': 'none'}
        return {'display': 'none'}, {'display': 'block'}

    # ── q model: show/hide Langer params ─────────────────────────────────
    @callback(
        Output(f'{p}-q-langer-container', 'style'),
        Input(f'{p}-q-model', 'value'),
    )
    def toggle_q_langer(model):
        return {'display': 'block'} if model == 'langer' else {'display': 'none'}


def register_langer_preset_callbacks(prefix: str) -> None:
    """Register Langer Case A/B/Both preset button callbacks."""
    from dash.exceptions import PreventUpdate
    p = prefix

    @callback(
        Output(f'{p}-weight-A', 'value', allow_duplicate=True),
        Input(f'{p}-preset-caseA', 'n_clicks'),
        prevent_initial_call=True,
    )
    def preset_case_a(n):
        if not n:
            raise PreventUpdate
        return 1.0

    @callback(
        Output(f'{p}-weight-A', 'value', allow_duplicate=True),
        Input(f'{p}-preset-caseB', 'n_clicks'),
        prevent_initial_call=True,
    )
    def preset_case_b(n):
        if not n:
            raise PreventUpdate
        return 0.0

    @callback(
        Output(f'{p}-weight-A', 'value', allow_duplicate=True),
        Input(f'{p}-preset-both', 'n_clicks'),
        prevent_initial_call=True,
    )
    def preset_both(n):
        if not n:
            raise PreventUpdate
        return 0.08
