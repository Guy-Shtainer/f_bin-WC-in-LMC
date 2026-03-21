"""
callbacks/detail_plots_cb.py
────────────────────────────
Dash callbacks for D-statistic heatmaps, 1-D slices (fbin and x-axis),
registered per scoring method using the closure-capture pattern.
"""
from __future__ import annotations

import os
import sys

import numpy as np
from dash import callback, Input, Output, State, no_update
from dash.exceptions import PreventUpdate

_APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP not in sys.path:
    sys.path.insert(0, _APP)

_ROOT = os.path.dirname(_APP)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from config import (
    SCORING_METHODS, from_json_safe, get_plotly_theme,
)
from components.detail_figures import (
    make_d_heatmap_fig,
    make_1d_slice_fig,
    make_resim_cdf_fig,
    _empty_fig,
)


# ── Shared helpers ───────────────────────────────────────────────────────────

def _extract_2d(result: dict, key: str):
    """Get array from result, collapse to 2-D (max over leading dims)."""
    raw = result.get(key)
    if raw is None:
        return None
    arr = np.asarray(raw, dtype=float)
    while arr.ndim > 2:
        arr = np.nanmax(arr, axis=0)
    return arr


def _best_indices_2d(arr_2d: np.ndarray, is_likelihood: bool):
    """Return (i_fbin, i_x) for the best point in a 2-D score array.

    For likelihood (higher-is-better) uses argmax; otherwise argmin.
    """
    if is_likelihood:
        if arr_2d.size == 0 or not np.any(np.isfinite(arr_2d)):
            raise PreventUpdate
        flat_idx = int(np.nanargmax(arr_2d))
    else:
        if arr_2d.size == 0 or not np.any(np.isfinite(arr_2d)):
            raise PreventUpdate
        flat_idx = int(np.nanargmin(arr_2d))
    return np.unravel_index(flat_idx, arr_2d.shape)


def _x_axis_info(result: dict) -> tuple[str, str]:
    """Return (x_name, x_label) depending on the model type stored."""
    model = result.get('model', result.get('period_model', 'dsilva'))
    if model == 'langer2020':
        return 'pi', '\u03c0'
    return 'pi', '\u03c0 (period power-law index)'


def _best_fit_from_p(result: dict, p_key: str):
    """Extract best-fit values from score (p-value) array.

    Returns (best_fbin, best_x, best_sigma, fbin_g, x_g) or
    raises ``PreventUpdate``.
    """
    p_arr = result.get(p_key)
    if p_arr is None:
        raise PreventUpdate
    arr = np.asarray(p_arr, dtype=float)
    fbin_g = np.asarray(result.get('fbin_grid', []))
    pi_g = np.asarray(result.get('pi_grid', []))
    sigma_g = np.asarray(result.get('sigma_grid', []))
    if fbin_g.size == 0 or pi_g.size == 0:
        raise PreventUpdate

    arr_full = arr.copy()
    while arr.ndim > 2:
        arr = np.nanmax(arr, axis=0)

    if arr.size == 0 or not np.any(np.isfinite(arr)):
        raise PreventUpdate
    best_idx = np.unravel_index(int(np.nanargmax(arr)), arr.shape)
    best_fbin = float(fbin_g[best_idx[0]]) if best_idx[0] < len(fbin_g) else 0.0
    best_x = float(pi_g[best_idx[1]]) if best_idx[1] < len(pi_g) else 0.0

    best_sigma = 5.0
    if sigma_g.size > 0:
        if arr_full.ndim >= 3 and arr_full.size > 0 and np.any(np.isfinite(arr_full)):
            full_best = np.unravel_index(
                int(np.nanargmax(arr_full)), arr_full.shape)
            if full_best[0] < len(sigma_g):
                best_sigma = float(sigma_g[full_best[0]])
        elif sigma_g.size == 1:
            best_sigma = float(sigma_g[0])

    return best_fbin, best_x, best_sigma, fbin_g, pi_g


def _try_parabolic_fit(grid_vals, scores_1d):
    """Attempt parabolic fit, return (coeffs, fit_range) or (None, None)."""
    try:
        from app.bc.fitting import _parabolic_min_1d
        _, _, coeffs, fit_range = _parabolic_min_1d(
            grid_vals, scores_1d, mode='neighborhood', n_neighbors=3)
        return coeffs, fit_range
    except Exception:
        return None, None


# ── Registration function ────────────────────────────────────────────────────

def register_detail_plot_callbacks(prefix: str) -> None:
    """Register D-heatmap, fbin-slice, and x-slice callbacks per method.

    Uses the closure-capture pattern (default-argument binding) to avoid
    duplicate function names across the loop.
    """
    p = prefix

    for mk, mname, pk, dk, mcolor in SCORING_METHODS:
        _register_d_heatmap(p, mk, mname, pk, dk, mcolor)
        _register_fbin_slice(p, mk, mname, pk, dk, mcolor)
        _register_x_slice(p, mk, mname, pk, dk, mcolor)


# ── 1. D-statistic heatmap ──────────────────────────────────────────────────

def _register_d_heatmap(
    p: str, method_key: str, display_name: str,
    p_key: str, d_key: str, method_color: str,
):
    m = f'{p}-{method_key}'

    @callback(
        Output(f'{m}-d-heatmap', 'figure'),
        Input(f'{p}-result-store', 'data'),
        State('mantine-provider', 'forceColorScheme'),
        prevent_initial_call=True,
    )
    def update_d_heatmap(
        data, color_scheme,
        _mk=method_key, _mn=display_name, _pk=p_key,
        _dk=d_key, _mc=method_color,
    ):
        if not data:
            raise PreventUpdate

        result = from_json_safe(data)
        theme = get_plotly_theme(color_scheme or 'dark')

        D_2d = _extract_2d(result, _dk)
        if D_2d is None or D_2d.size == 0:
            return _empty_fig(f'No {_mn} D-stat data', theme)

        fbin_g = np.asarray(result.get('fbin_grid', []))
        pi_g = np.asarray(result.get('pi_grid', []))
        if fbin_g.size == 0 or pi_g.size == 0:
            return _empty_fig('Grid data missing', theme)

        _, x_label = _x_axis_info(result)

        return make_d_heatmap_fig(
            D_2d=D_2d,
            fbin_g=fbin_g,
            x_g=pi_g,
            method_name=_mn,
            method_color=_mc,
            theme=theme,
            x_label=x_label,
        )


# ── 2. f_bin 1-D slice ──────────────────────────────────────────────────────

def _register_fbin_slice(
    p: str, method_key: str, display_name: str,
    p_key: str, d_key: str, method_color: str,
):
    m = f'{p}-{method_key}'

    @callback(
        Output(f'{m}-fbin-slice', 'figure'),
        Input(f'{p}-result-store', 'data'),
        State('mantine-provider', 'forceColorScheme'),
        prevent_initial_call=True,
    )
    def update_fbin_slice(
        data, color_scheme,
        _mk=method_key, _mn=display_name, _pk=p_key,
        _dk=d_key, _mc=method_color,
    ):
        if not data:
            raise PreventUpdate

        result = from_json_safe(data)
        theme = get_plotly_theme(color_scheme or 'dark')

        try:
            best_fbin, best_x, _, fbin_g, pi_g = _best_fit_from_p(
                result, _pk)
        except PreventUpdate:
            return _empty_fig(f'No {_mn} data for fbin slice', theme)

        # Use p-value array for slicing (higher is better)
        p_2d = _extract_2d(result, _pk)
        if p_2d is None:
            return _empty_fig(f'No {_mn} score data', theme)

        # Slice along fbin axis at best x index
        best_x_idx = int(np.argmin(np.abs(pi_g - best_x)))
        fbin_scores = p_2d[:, best_x_idx]

        coeffs, fit_range = _try_parabolic_fit(fbin_g, -fbin_scores)

        return make_1d_slice_fig(
            grid_vals=fbin_g,
            scores_1d=fbin_scores,
            axis_label='f_bin',
            best_val=best_fbin,
            theme=theme,
            method_color=_mc,
            score_label=f'{_mn} score',
            fit_coeffs=None if coeffs is None else -coeffs,
            fit_range=fit_range,
        )


# ── 3. x-axis 1-D slice ─────────────────────────────────────────────────────

def _register_x_slice(
    p: str, method_key: str, display_name: str,
    p_key: str, d_key: str, method_color: str,
):
    m = f'{p}-{method_key}'

    @callback(
        Output(f'{m}-x-slice', 'figure'),
        Input(f'{p}-result-store', 'data'),
        State('mantine-provider', 'forceColorScheme'),
        prevent_initial_call=True,
    )
    def update_x_slice(
        data, color_scheme,
        _mk=method_key, _mn=display_name, _pk=p_key,
        _dk=d_key, _mc=method_color,
    ):
        if not data:
            raise PreventUpdate

        result = from_json_safe(data)
        theme = get_plotly_theme(color_scheme or 'dark')

        try:
            best_fbin, best_x, _, fbin_g, pi_g = _best_fit_from_p(
                result, _pk)
        except PreventUpdate:
            _, x_label = _x_axis_info(result)
            return _empty_fig(f'No {_mn} data for {x_label} slice', theme)

        _, x_label = _x_axis_info(result)

        p_2d = _extract_2d(result, _pk)
        if p_2d is None:
            return _empty_fig(f'No {_mn} score data', theme)

        # Slice along x axis at best fbin index
        best_fb_idx = int(np.argmin(np.abs(fbin_g - best_fbin)))
        x_scores = p_2d[best_fb_idx, :]

        coeffs, fit_range = _try_parabolic_fit(pi_g, -x_scores)

        return make_1d_slice_fig(
            grid_vals=pi_g,
            scores_1d=x_scores,
            axis_label=x_label,
            best_val=best_x,
            theme=theme,
            method_color=_mc,
            score_label=f'{_mn} score',
            fit_coeffs=None if coeffs is None else -coeffs,
            fit_range=fit_range,
        )
