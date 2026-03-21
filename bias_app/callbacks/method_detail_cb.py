"""
callbacks/method_detail_cb.py
─────────────────────────────
Dash callbacks for the per-scoring-method detail panels:
slice controls, CDF at best-fit, corner plots, and model explorer tables.

Uses the closure-capture pattern from ``scoring_cb.py`` to register one
callback per scoring method without creating duplicate function names.
"""
from __future__ import annotations

import os
import sys

import numpy as np
from dash import callback, Input, Output, State, html, no_update
from dash.exceptions import PreventUpdate
import dash_mantine_components as dmc

_APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP not in sys.path:
    sys.path.insert(0, _APP)

from config import (
    SCORING_METHODS, from_json_safe, get_plotly_theme,
)
from components.method_figures import (
    make_method_cdf_fig,
    make_corner_fig,
    make_slice_controls,
    make_explorer_table,
)


def register_method_detail_callbacks(prefix: str) -> None:
    """Register CDF, corner, slice-control, and explorer callbacks.

    Loops over ``SCORING_METHODS`` and registers four callbacks per method
    using the closure-capture pattern (default-argument binding).
    """
    p = prefix

    for mk, mname, pk, dk, mcolor in SCORING_METHODS:
        _register_slice_controls(p, mk)
        _register_method_cdf(p, mk, mname, pk, mcolor)
        _register_corner(p, mk, mname, pk, mcolor)
        _register_explorer(p, mk, pk)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _best_fit_from_result(result: dict, p_key: str):
    """Extract best-fit (fbin, pi/x, sigma) from a result dict.

    Returns (best_fbin, best_x, best_sigma, fbin_g, x_g, p_2d) or
    raises ``PreventUpdate`` when data is missing.
    """
    p_arr = result.get(p_key)
    if p_arr is None:
        raise PreventUpdate

    arr = np.asarray(p_arr)
    fbin_g = np.asarray(result.get('fbin_grid', []))
    pi_g = np.asarray(result.get('pi_grid', []))
    sigma_g = np.asarray(result.get('sigma_grid', []))

    if fbin_g.size == 0 or pi_g.size == 0:
        raise PreventUpdate

    # Collapse to 2D for grid indexing (max over sigma/outer dims)
    arr_full = arr.copy()
    while arr.ndim > 2:
        arr = np.nanmax(arr, axis=0)

    if arr.size == 0 or not np.any(np.isfinite(arr)):
        raise PreventUpdate
    best_idx = np.unravel_index(int(np.nanargmax(arr)), arr.shape)
    best_fbin = float(fbin_g[best_idx[0]]) if best_idx[0] < len(fbin_g) else 0.0
    best_x = float(pi_g[best_idx[1]]) if best_idx[1] < len(pi_g) else 0.0

    # Best sigma: find from full array if 3D+
    best_sigma = 5.0  # default
    if sigma_g.size > 0:
        if arr_full.ndim >= 3 and arr_full.size > 0 and np.any(np.isfinite(arr_full)):
            full_best = np.unravel_index(
                int(np.nanargmax(arr_full)), arr_full.shape)
            # sigma is the first dimension for 3D arrays
            if full_best[0] < len(sigma_g):
                best_sigma = float(sigma_g[full_best[0]])
        elif sigma_g.size == 1:
            best_sigma = float(sigma_g[0])

    return best_fbin, best_x, best_sigma, fbin_g, pi_g, arr


def _x_axis_info(result: dict) -> tuple[str, str]:
    """Return (x_name, x_label) depending on the model type stored."""
    model = result.get('model', result.get('period_model', 'dsilva'))
    if model == 'langer2020':
        return 'pi', '\u03c0'
    return 'pi', '\u03c0 (period power-law index)'


# ── 1. Slice controls ───────────────────────────────────────────────────────

def _register_slice_controls(p: str, method_key: str):
    m = f'{p}-{method_key}'

    @callback(
        Output(f'{m}-slice-controls', 'children'),
        Input(f'{p}-result-store', 'data'),
        prevent_initial_call=True,
    )
    def update_slice_controls(data, _mk=method_key):
        if not data:
            raise PreventUpdate
        result = from_json_safe(data)
        return make_slice_controls(result, p, _mk)


# ── 2. CDF at method's best-fit ─────────────────────────────────────────────

def _register_method_cdf(
    p: str, method_key: str, display_name: str, p_key: str, method_color: str,
):
    m = f'{p}-{method_key}'

    @callback(
        Output(f'{m}-cdf', 'figure'),
        Input(f'{p}-result-store', 'data'),
        State('mantine-provider', 'forceColorScheme'),
        prevent_initial_call=True,
    )
    def update_method_cdf(
        data, color_scheme,
        _mk=method_key, _mn=display_name, _pk=p_key, _mc=method_color,
    ):
        if not data:
            raise PreventUpdate

        result = from_json_safe(data)
        theme = get_plotly_theme(color_scheme or 'dark')

        obs_drv = np.asarray(result.get('obs_delta_rv', []))
        if obs_drv.size == 0:
            from components.method_figures import _empty_fig
            return _empty_fig('No observed \u0394RV data', theme)

        try:
            best_fbin, best_x, best_sigma, _, _, _ = _best_fit_from_result(
                result, _pk)
        except PreventUpdate:
            from components.method_figures import _empty_fig
            return _empty_fig(f'No {_mn} data', theme)

        return make_method_cdf_fig(
            obs_delta_rv=obs_drv,
            best_fbin=best_fbin,
            best_pi=best_x,
            best_sigma=best_sigma,
            theme=theme,
            n_draws=50,
            method_color=_mc,
            method_name=_mn,
            result_meta=result,
        )


# ── 3. Corner plot ──────────────────────────────────────────────────────────

def _register_corner(
    p: str, method_key: str, display_name: str, p_key: str, method_color: str,
):
    m = f'{p}-{method_key}'

    @callback(
        Output(f'{m}-corner', 'figure'),
        Input(f'{p}-result-store', 'data'),
        State('mantine-provider', 'forceColorScheme'),
        prevent_initial_call=True,
    )
    def update_corner(
        data, color_scheme,
        _mk=method_key, _mn=display_name, _pk=p_key, _mc=method_color,
    ):
        if not data:
            raise PreventUpdate

        result = from_json_safe(data)
        theme = get_plotly_theme(color_scheme or 'dark')

        try:
            _, _, _, fbin_g, x_g, p_2d = _best_fit_from_result(result, _pk)
        except PreventUpdate:
            from components.method_figures import _empty_fig
            return _empty_fig(f'No {_mn} data for corner plot', theme)

        x_name, x_label = _x_axis_info(result)

        return make_corner_fig(
            p_nd=p_2d,
            fbin_g=fbin_g,
            x_g=x_g,
            x_name=x_name,
            x_label=x_label,
            method_key=_mk,
            method_color=_mc,
            theme=theme,
        )


# ── 4. Model explorer table ─────────────────────────────────────────────────

def _register_explorer(p: str, method_key: str, p_key: str):
    m = f'{p}-{method_key}'

    @callback(
        Output(f'{m}-explorer', 'children'),
        Input(f'{p}-result-store', 'data'),
        prevent_initial_call=True,
    )
    def update_explorer(data, _mk=method_key, _pk=p_key):
        if not data:
            raise PreventUpdate

        result = from_json_safe(data)
        p_arr = result.get(_pk)
        if p_arr is None:
            return dmc.Text(f'No {_mk} data available.', c='dimmed')

        fbin_g = np.asarray(result.get('fbin_grid', []))
        x_g = np.asarray(result.get('pi_grid', []))
        if fbin_g.size == 0 or x_g.size == 0:
            return dmc.Text('Grid data missing.', c='dimmed')

        _, x_label = _x_axis_info(result)

        return make_explorer_table(
            result_data=result,
            method_key=_mk,
            p_key=_pk,
            fbin_g=fbin_g,
            x_g=x_g,
            x_label=x_label,
            top_n=5,
        )
