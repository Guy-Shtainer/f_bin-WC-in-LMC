"""
bias_app/callbacks/sim_plots_cb.py
──────────────────────────────────
Dash callbacks for Simulation-tab plots (period dist, binary fraction,
orbital histograms, sigma scan, CDF comparison).

Call ``register_sim_plot_callbacks(prefix)`` once per tab prefix.
"""
from __future__ import annotations

import numpy as np
from dash import callback, Input, Output, State, html, dcc, no_update
from dash.exceptions import PreventUpdate

from config import from_json_safe, get_plotly_theme, SCORING_METHODS
from components.figures import (
    make_max_pval_fig,
    make_period_dist_fig,
    make_binary_frac_fig,
    make_orbital_hist_fig,
    make_all_methods_cdf_fig,
    _empty_fig,
)


def _method_best_simple(p_nd: np.ndarray, grids: list[np.ndarray],
                         names: list[str]) -> dict | None:
    """Lightweight argmax best-fit (no HDI)."""
    if not np.any(np.isfinite(p_nd)):
        return None
    if p_nd.size == 0 or not np.any(np.isfinite(p_nd)):
        raise PreventUpdate
    flat = int(np.nanargmax(p_nd))
    idx = np.unravel_index(flat, p_nd.shape)
    best_vals = {n: float(g[idx[i]]) for i, (g, n)
                 in enumerate(zip(grids, names))}
    return {'best_idx': idx, 'best_vals': best_vals,
            'best_score': float(p_nd[idx])}


def _build_method_results(result: dict, fbin_g: np.ndarray,
                           x_g: np.ndarray,
                           x_name: str) -> dict:
    """Build method_results dict from result scoring arrays."""
    sigma_g = np.asarray(result.get('sigma_grid', [0.0]))
    has_sigma = sigma_g.size > 1
    method_results: dict = {}
    for mk, _, p_key, _, _ in SCORING_METHODS:
        arr = result.get(p_key)
        if arr is None:
            continue
        arr = np.asarray(arr, dtype=float)
        if not np.any(np.isfinite(arr)):
            continue
        if has_sigma and arr.ndim == 3:
            grids = [sigma_g, fbin_g, x_g]
            names = ['sigma', 'fbin', x_name]
        elif arr.ndim == 2:
            grids = [fbin_g, x_g]
            names = ['fbin', x_name]
        else:
            continue
        info = _method_best_simple(arr, grids, names)
        if info is not None:
            method_results[mk] = info
    return method_results


def register_sim_plot_callbacks(prefix: str) -> None:
    """Register five Dash callbacks for simulation-result plots."""
    p = prefix

    # ── 1. CDF comparison ────────────────────────────────────────────────
    @callback(
        Output(f'{p}-sim-cdf', 'figure'),
        Input(f'{p}-result-store', 'data'),
        State('mantine-provider', 'forceColorScheme'),
    )
    def update_sim_cdf(data, color_scheme):
        if not data:
            raise PreventUpdate
        theme = get_plotly_theme(color_scheme or 'dark')
        result = from_json_safe(data)
        fbin_g = np.asarray(result.get('fbin_grid', []))
        x_g = np.asarray(result.get('pi_grid', []))
        x_name = result.get('x_name', 'pi')
        x_label = result.get('x_label', 'pi')
        if fbin_g.size == 0 or x_g.size == 0:
            return _empty_fig('No grid data', theme)
        mr = _build_method_results(result, fbin_g, x_g, x_name)
        return make_all_methods_cdf_fig(result, mr, fbin_g, x_g, theme,
                                        x_name=x_name, x_label=x_label)

    # ── 2. Sigma scan chart ──────────────────────────────────────────────
    @callback(
        Output(f'{p}-sigma-scan-chart-container', 'children'),
        Input(f'{p}-result-store', 'data'),
        State('mantine-provider', 'forceColorScheme'),
    )
    def update_sigma_scan(data, color_scheme):
        if not data:
            raise PreventUpdate
        theme = get_plotly_theme(color_scheme or 'dark')
        result = from_json_safe(data)
        sigma_g = np.asarray(result.get('sigma_grid', []))
        if sigma_g.size <= 1:
            return html.Div()
        # Compute max p-value per sigma slice from ks_p
        ks_p = result.get('ks_p')
        if ks_p is None:
            return html.Div()
        ks_p = np.asarray(ks_p, dtype=float)
        if ks_p.ndim != 3:
            return html.Div()
        max_pvals = [float(np.nanmax(ks_p[i])) for i in range(ks_p.shape[0])]
        fig = make_max_pval_fig(sigma_g, max_pvals, theme)
        return dcc.Graph(figure=fig, style={'width': '100%'})

    # ── 3. Period distribution ───────────────────────────────────────────
    @callback(
        Output(f'{p}-period-dist', 'figure'),
        Input(f'{p}-result-store', 'data'),
        State('mantine-provider', 'forceColorScheme'),
    )
    def update_period_dist(data, color_scheme):
        if not data:
            raise PreventUpdate
        theme = get_plotly_theme(color_scheme or 'dark')
        result = from_json_safe(data)
        gap_sim = result.get('gap_sim')
        if gap_sim is None or 'P_days' not in gap_sim:
            return _empty_fig('No simulation data for period distribution',
                              theme, height=400)
        gap_sim = {k: np.asarray(v) for k, v in gap_sim.items()
                   if isinstance(v, (list, np.ndarray))}
        det = np.asarray(result.get('bin_detected_mask', []), dtype=bool)
        mis = np.asarray(result.get('bin_missed_mask', []), dtype=bool)
        logP_min = float(result.get('logP_min', 0.15))
        logP_max = float(result.get('logP_max', 4.0))
        return make_period_dist_fig(gap_sim, det, mis, logP_min, logP_max,
                                    theme)

    # ── 4. Binary fraction vs threshold ──────────────────────────────────
    @callback(
        Output(f'{p}-binary-frac', 'figure'),
        Input(f'{p}-result-store', 'data'),
        State('mantine-provider', 'forceColorScheme'),
    )
    def update_binary_frac(data, color_scheme):
        if not data:
            raise PreventUpdate
        theme = get_plotly_theme(color_scheme or 'dark')
        result = from_json_safe(data)
        gap_sim = result.get('gap_sim')
        if gap_sim is None or 'delta_rv' not in gap_sim:
            return _empty_fig('No simulation data for binary fraction',
                              theme, height=400)
        drv = np.asarray(gap_sim['delta_rv'])
        is_bin = np.asarray(gap_sim.get('is_binary', []), dtype=bool)
        fbin_intr = float(result.get('intrinsic_fbin', 0.5))
        thresh = float(result.get('thresh_dRV', 45.5))
        obs_fbin = float(result.get('observed_fbin', 0.0))
        return make_binary_frac_fig(drv, is_bin, fbin_intr, obs_fbin,
                                    thresh, theme)

    # ── 5. Orbital histograms ────────────────────────────────────────────
    @callback(
        Output(f'{p}-orbital-hist', 'figure'),
        Input(f'{p}-result-store', 'data'),
        State('mantine-provider', 'forceColorScheme'),
    )
    def update_orbital_hist(data, color_scheme):
        if not data:
            raise PreventUpdate
        theme = get_plotly_theme(color_scheme or 'dark')
        result = from_json_safe(data)
        gap_sim = result.get('gap_sim')
        if gap_sim is None or 'P_days' not in gap_sim:
            return _empty_fig('No simulation data for orbital histograms',
                              theme, height=850)
        gap_sim = {k: np.asarray(v) for k, v in gap_sim.items()
                   if isinstance(v, (list, np.ndarray))}
        det = np.asarray(result.get('bin_detected_mask', []), dtype=bool)
        mis = np.asarray(result.get('bin_missed_mask', []), dtype=bool)
        return make_orbital_hist_fig(gap_sim, det, mis, theme)
