"""bc.render_shared — ALL shared graphs rendered BEFORE the scoring method radio selector.

Self-contained module: does NOT import from analysis.py, sim_plots.py, or subtabs.py.
Contains copied implementations of every function needed for the shared section.
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from shared import make_heatmap_fig, find_best_grid_point, PLOTLY_THEME, get_palette
from bc.helpers import SCORING_METHODS, _METHOD_COLORS, _RESULT_DIR


def _binned_cdf(data: np.ndarray, bin_edges: np.ndarray) -> np.ndarray:
    """Empirical CDF at bin_edges."""
    sorted_data = np.sort(data)
    return np.searchsorted(sorted_data, bin_edges, side='right') / len(sorted_data)

# Shared colors
_CLR_DETECTED = '#E25A53'
_CLR_MISSED   = '#F5A623'
_CLR_ALL      = '#52B788'
_CLR_OBS      = '#4A90D9'
_CLR_CASE_A   = '#4A90D9'
_CLR_CASE_B   = '#F5A623'

# ── Helpers ──────────────────────────────────────────────────────────────────

def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Convert hex color to rgba string for Plotly shading."""
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'rgba({r},{g},{b},{alpha})'

def _make_max_pval_fig(
    sigma_vals: np.ndarray, max_pvals: list[float],
    height: int = 300, x_label: str = '\u03c3_single', stat_label: str = 'K-S',
) -> go.Figure:
    """Line chart: max score vs a scan variable."""
    best_idx = int(np.argmax(max_pvals))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sigma_vals, y=max_pvals, mode='lines+markers',
        marker=dict(size=8, color='#4A90D9'),
        line=dict(color='#4A90D9', width=2),
        hovertemplate=f'{x_label}=%{{x:.2f}}<br>max {stat_label}=%{{y:.4f}}<extra></extra>',
        showlegend=False))
    fig.add_trace(go.Scatter(
        x=[float(sigma_vals[best_idx])], y=[max_pvals[best_idx]],
        mode='markers+text',
        marker=dict(symbol='star', size=16, color='gold',
                    line=dict(color='black', width=1)),
        text=[f'  {x_label}={float(sigma_vals[best_idx]):.2f}, {stat_label}={max_pvals[best_idx]:.4f}'],
        textposition='middle right', textfont=dict(color='gold', size=11),
        showlegend=False))
    fig.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(text=f'Max {stat_label} vs {x_label}', font=dict(size=14)),
        'xaxis_title': x_label, 'yaxis_title': f'Max {stat_label}',
        'height': height, 'margin': dict(l=60, r=20, t=50, b=50),
    })
    return fig

def _safe_mask(arr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Apply boolean mask, returning empty array if source is empty."""
    return arr[mask] if arr.size > 0 else np.array([])

# ── From analysis.py ─────────────────────────────────────────────────────────

def _get_method_array(result: dict, key: str) -> np.ndarray | None:
    """Safely retrieve and convert a scoring array from result dict."""
    arr = result.get(key)
    if arr is None:
        return None
    arr = np.asarray(arr, dtype=float)
    if not np.any(np.isfinite(arr)):
        return None
    return arr

def _method_best_and_hdi(
    p_nd: np.ndarray, grids: list[np.ndarray],
    grid_names: list[str], is_likelihood: bool = False,
) -> dict:
    """Find global best-fit and 68% HDI for each axis of a scoring array."""
    from wr_bias_simulation import compute_hdi68
    valid = np.isfinite(p_nd)
    if not np.any(valid):
        return None
    if len(grids) != p_nd.ndim:
        return None
    flat_best = int(np.nanargmax(p_nd))
    best_idx = np.unravel_index(flat_best, p_nd.shape)
    best_score = float(p_nd[best_idx])
    best_vals, hdi = {}, {}
    for i, (g, name) in enumerate(zip(grids, grid_names)):
        if i >= p_nd.ndim or len(g) != p_nd.shape[i]:
            best_vals[name] = float('nan')
            hdi[name] = (float('nan'), float('nan'), float('nan'))
            continue
        best_vals[name] = float(g[best_idx[i]])
        sum_axes = tuple(j for j in range(p_nd.ndim) if j != i)
        post_1d = np.nansum(p_nd, axis=sum_axes) if sum_axes else p_nd.copy()
        if post_1d.sum() > 0:
            mode, lo, hi = compute_hdi68(g, post_1d)
            hdi[name] = (float(mode), float(lo), float(hi))
        else:
            v = best_vals[name]
            hdi[name] = (v, v, v)
    return {'best_idx': best_idx, 'best_vals': best_vals,
            'best_score': best_score, 'hdi': hdi}

# WORKING — do not change this code (A1: Summary Table — Langer version, approved 2026-03-30)
def _render_method_summary_section(
    result: dict, fbin_g: np.ndarray, x_g: np.ndarray,
    extra_grids: list[tuple[str, np.ndarray]] | None = None,
    prefix: str = 'ds', x_name: str = 'pi',
    x_label: str = 'π', ndim_mode: str = 'dsilva',
) -> dict:
    """Render a comparison table of all scoring methods.
    Returns method_results dict mapping method_key -> {best_vals, hdi, ...}.
    """
    # Build ordered grid list matching array dimensions
    if ndim_mode == 'dsilva':
        sigma_g = np.asarray(result.get('sigma_grid', [0.0]))
        logPmax_g = np.asarray(result.get('logPmax_grid', [0.0]))
        grids = [logPmax_g, sigma_g, fbin_g, x_g]
        grid_names = ['logPmax', 'sigma', 'fbin', x_name]
    elif ndim_mode == 'langer':
        grids, grid_names = [fbin_g, x_g], ['fbin', x_name]
    elif ndim_mode == 'cadence_langer':
        _sigma_g_cl = np.asarray(result.get('sigma_grid', [0.0]))
        _logPmax_g_cl = np.asarray(result.get('logPmax_grid', [0.0]))
        _has_sig_cl = _sigma_g_cl.size > 1
        _has_lp_cl = _logPmax_g_cl.size > 1
        # Grids built per-method after squeeze (see cadence_langer block below)
        grids, grid_names = [fbin_g], ['fbin']  # placeholder, rebuilt per-method
    elif ndim_mode == 'cadence_dsilva':
        grids, grid_names = [], []
        if extra_grids:
            for gn, ga in extra_grids:
                grids.append(ga); grid_names.append(gn)
        grids.extend([fbin_g, x_g]); grid_names.extend(['fbin', x_name])
    else:
        grids, grid_names = [fbin_g, x_g], ['fbin', x_name]

    rows, method_results = [], {}
    for mk, mname, pk, dk, mcolor in SCORING_METHODS:
        p_arr = _get_method_array(result, pk)
        if p_arr is None:
            continue
        is_lk = (mk == 'likelihood')
        if ndim_mode == 'dsilva':
            if p_arr.ndim == 2:
                p_arr = p_arr[np.newaxis, np.newaxis, ...]
            elif p_arr.ndim == 3:
                p_arr = p_arr[np.newaxis, ...]
        if ndim_mode == 'cadence_langer':
            # Squeeze pi (always size 1 for Langer)
            if p_arr.ndim >= 2 and p_arr.shape[-1] == 1:
                p_arr = p_arr[..., 0]
            # Explicit grid matching per combo
            # Runner order: [logPmax, sigma, fbin, pi] → after pi squeeze: [logPmax?, sigma?, fbin]
            if _has_lp_cl and _has_sig_cl:
                # [logP, sigma, fbin]
                grids = [_logPmax_g_cl, _sigma_g_cl, fbin_g]
                grid_names = ['logPmax', 'sigma', 'fbin']
            elif _has_lp_cl:
                # [logP, sigma=1, fbin] → squeeze sigma
                if p_arr.ndim == 3 and p_arr.shape[1] == 1:
                    p_arr = p_arr[:, 0, :]
                grids = [_logPmax_g_cl, fbin_g]
                grid_names = ['logPmax', 'fbin']
            elif _has_sig_cl:
                # [sigma, fbin]
                grids = [_sigma_g_cl, fbin_g]
                grid_names = ['sigma', 'fbin']
            else:
                # [sigma=1, fbin] → squeeze sigma
                if p_arr.ndim == 2 and p_arr.shape[0] == 1:
                    p_arr = p_arr[0]
                grids = [fbin_g]
                grid_names = ['fbin']
        elif ndim_mode == 'cadence_dsilva':
            while p_arr.ndim > len(grids):
                p_arr = p_arr[0]

        info = _method_best_and_hdi(p_arr, grids, grid_names, is_likelihood=is_lk)
        if info is None:
            continue
        method_results[mk] = info
        bv, hdi = info['best_vals'], info['hdi']

        def _fmt_hdi_cell(name, fmt='.4f'):
            if name not in hdi:
                return '--'
            mode, lo, hi = hdi[name]
            return f'{mode:{fmt}} (+{hi - mode:{fmt}} / -{mode - lo:{fmt}})'

        _has_sigma_col = ('sigma' in grid_names and x_name != 'sigma')
        row = {
            'Method': mname,
            'Best f_bin': f"{bv.get('fbin', 0):.4f}",
            '68% HDI f_bin': _fmt_hdi_cell('fbin', '.4f'),
        }
        # x-axis column: skip if x_name is sigma but sigma is constant
        if x_name in grid_names:
            row[f'Best {x_label}'] = f"{bv.get(x_name, 0):.3f}"
            row[f'68% HDI {x_label}'] = _fmt_hdi_cell(x_name, '.3f')
        if _has_sigma_col:
            row['Best σ_single'] = f"{bv.get('sigma', 0):.2f}"
            row['68% HDI σ_single'] = _fmt_hdi_cell('sigma', '.2f')
        # Show constant σ_single when not scanned
        if (ndim_mode == 'cadence_langer'
                and not _has_sigma_col
                and x_name not in grid_names
                and _sigma_g_cl.size == 1):
            row['Best σ_single'] = f"{float(_sigma_g_cl[0]):.2f} (constant)"
            row['68% HDI σ_single'] = '—'
        _has_logPmax_col = ('logPmax' in grid_names)
        if _has_logPmax_col:
            row['Best logP_max'] = f"{bv.get('logPmax', 0):.2f}"
            row['68% HDI logP_max'] = _fmt_hdi_cell('logPmax', '.2f')
        # Interpolated results (from parabolic fit)
        _interp = st.session_state.get(f'{prefix}_{mk}_analysis_interp')
        if _interp is not None:
            row['Interp f_bin'] = f"{_interp.get('f_bin', 0):.4f}"
            if x_name in _interp or x_label in _interp:
                _ix = _interp.get(x_name, _interp.get(x_label, 0))
                row[f'Interp {x_label}'] = f"{_ix:.3f}"
        # Raw logL score (rightmost column) — NOT normalized
        _raw_logL = result.get('logL_raw')
        if _raw_logL is not None:
            _raw_arr = np.asarray(_raw_logL, dtype=float)
            if np.any(np.isfinite(_raw_arr)):
                row['ln L (raw)'] = f"{float(np.nanmax(_raw_arr)):.2f}"
            else:
                row['ln L (raw)'] = '--'
        else:
            row['ln L (raw)'] = f"{info['best_score']:.6f}"
        rows.append(row)

    if not rows:
        return method_results

    st.markdown('#### Summary Table')
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(
        'Best-fit parameters and 68% HDI from likelihood scoring.')
    return method_results

# WORKING — do not change this code (A2: CDF Comparison — Langer version, approved 2026-03-30)
def _render_all_methods_cdf(
    result: dict, method_results: dict,
    fbin_g: np.ndarray, x_g: np.ndarray, prefix: str,
    x_name: str = 'pi', x_label: str = 'π',
) -> None:
    """CDF comparison: observed vs best-fit model from each scoring method."""
    obs_drv = result.get('obs_delta_rv')
    if obs_drv is None or len(method_results) < 1:
        return
    try:
        from wr_bias_simulation import (
            DEFAULT_DRV_BIN_EDGES,
            simulate_delta_rv_sample, SimulationConfig, BinaryParameterConfig,
        )
    except ImportError:
        return
    _be = result.get('bin_edges')
    _be = DEFAULT_DRV_BIN_EDGES if _be is None else np.asarray(_be)
    obs_drv = np.asarray(obs_drv)
    _n_obs = len(obs_drv)
    obs_cdf = _binned_cdf(obs_drv, _be)
    _obs_x = np.concatenate([[0.0], _be])
    _obs_y = np.concatenate([[0.0], obs_cdf])

    fig_cdf = go.Figure()
    fig_cdf.add_trace(go.Scatter(
        x=_obs_x, y=_obs_y, mode='lines', name='Observed',
        line=dict(color='lightblue', width=2.5, shape='hv')))

    _n_cdf_sets = 100
    for mk, info in method_results.items():
        bv = info['best_vals']
        fb, pi_v = bv.get('fbin', 0.5), bv.get(x_name, 0.0)
        sig_v = bv.get('sigma', 5.0)
        _mcolor = next((c for k, _, _, _, c in SCORING_METHODS if k == mk), '#888888')
        _mname = next((n for k, n, _, _, _ in SCORING_METHODS if k == mk), mk)
        try:
            _all_cdfs = []
            for _seed_i in range(_n_cdf_sets):
                sim_cfg = SimulationConfig(
                    n_stars=_n_obs, sigma_single=float(sig_v),
                    sigma_measure=float(result.get('sigma_meas', 3.0)))
                rng = np.random.default_rng(42 + _seed_i)
                sim_drv = simulate_delta_rv_sample(
                    f_bin=float(fb), pi=float(pi_v),
                    sim_cfg=sim_cfg, bin_cfg=BinaryParameterConfig(), rng=rng)
                _all_cdfs.append(_binned_cdf(sim_drv, _be))
            _all_cdfs = np.array(_all_cdfs)
            _med = np.median(_all_cdfs, axis=0)
            _lo = np.percentile(_all_cdfs, 16, axis=0)
            _hi = np.percentile(_all_cdfs, 84, axis=0)
            _mx = np.concatenate([[0.0], _be])
            _my = np.concatenate([[0.0], _med])
            _loy = np.concatenate([[0.0], _lo])
            _hiy = np.concatenate([[0.0], _hi])
            _lbl = f'{_mname} (f<sub>bin</sub>={fb:.3f}'
            if x_name in bv:
                _lbl += f', π={bv[x_name]:.2f}' if x_name == 'pi' else f', {x_label}={bv[x_name]:.2f}'
            if 'sigma' in bv and bv['sigma'] != 0:
                _lbl += f', σ={bv["sigma"]:.1f}'
            if 'logPmax' in bv and bv['logPmax'] != 0:
                _lbl += f', logP<sub>max</sub>={bv["logPmax"]:.2f}'
            _lbl += ')'
            fig_cdf.add_trace(go.Scatter(
                x=np.concatenate([_mx, _mx[::-1]]),
                y=np.concatenate([_hiy, _loy[::-1]]),
                fill='toself', fillcolor=_hex_to_rgba(_mcolor, 0.2),
                line=dict(color='rgba(0,0,0,0)'),
                legendgroup=mk, showlegend=False, hoverinfo='skip'))
            fig_cdf.add_trace(go.Scatter(
                x=_mx, y=_my, mode='lines', name=_lbl,
                legendgroup=mk, line=dict(color=_mcolor, width=2, dash='dash')))
        except Exception:
            pass

    # Show likelihood bins toggle
    _show_bins = st.checkbox('Show likelihood bins', value=False,
                             key=f'{prefix}_cdf_show_bins')
    if _show_bins:
        _lk_be = result.get('likelihood_bin_edges')
        if _lk_be is None:
            try:
                from wr_bias_simulation import DSILVA_LIKELIHOOD_BINS
                _lk_be = DSILVA_LIKELIHOOD_BINS
            except ImportError:
                _lk_be = np.array([0.0, 45.5, 250.0, 650.0])
        _lk_be = np.asarray(_lk_be)
        for _edge in _lk_be:
            if np.isfinite(_edge) and _edge > 0:
                fig_cdf.add_vline(
                    x=_edge, line_dash='dash', line_color='rgba(200,200,200,0.8)',
                    line_width=1.5)

    fig_cdf.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(text='CDF Comparison: Observed vs Best-Fit Models', font=dict(size=14)),
        'xaxis_title': 'ΔRV (km/s)', 'yaxis_title': 'Cumulative Fraction',
        'height': 400, 'legend': dict(x=0.55, y=0.05),
        'margin': dict(r=40),
    })
    st.plotly_chart(fig_cdf, use_container_width=True, key=f'{prefix}_cdf_comparison')
    st.caption(
        f'Observed ΔRV CDF (solid white) vs simulated CDFs at each '
        f'method\'s best-fit parameters (dashed, median of {_n_cdf_sets} draws). '
        f'Shaded bands show 16th-84th percentile range. N_stars={_n_obs}.')

# ── From subtabs.py ──────────────────────────────────────────────────────────

def _build_extra_grids(ctx: dict) -> list[tuple[str, np.ndarray]] | None:
    """Build the extra_grids list for multi-dim models.

    Order must match array dimension order: (logPmax, sigma, fbin, pi).
    logPmax first (axis 0), then sigma (axis 1).
    """
    ndim = ctx['ndim_mode']
    extras: list[tuple[str, np.ndarray]] = []
    # logPmax FIRST (axis 0 in 4D array)
    if ctx.get('logPmax_g') is not None and ndim in ('dsilva', 'cadence_dsilva'):
        extras.append(('logPmax', ctx['logPmax_g']))
    # sigma SECOND (axis 1 in 4D array)
    if ctx.get('sigma_g') is not None and ndim in ('dsilva', 'cadence_dsilva'):
        extras.append(('sigma', ctx['sigma_g']))
    return extras if extras else None

# WORKING — do not change this code (A3: Max Likelihood vs σ/logPmax)
def render_sigma_scan_chart(ctx: dict) -> None:
    """Show max -logL vs σ/logPmax: 1D line or 2D heatmap depending on grids.

    - σ only → 1D line (σ on x)
    - logPmax only → 1D line (logPmax on x)
    - Both σ AND logPmax → 2D heatmap (σ × logPmax, max over f_bin × π)

    Uses unnormalized logL_raw (falling back to normalized likelihood).
    """
    result = ctx['result']
    sigma_g = np.asarray(result.get('sigma_grid', []))
    logPmax_g = np.asarray(result.get('logPmax_grid', []))
    # Prefer unnormalized logL_raw; fall back to normalized likelihood
    lk = np.asarray(result.get('logL_raw', result.get('likelihood', [])))
    if lk.size == 0:
        return

    _has_sig = sigma_g.size > 1
    _has_lp = logPmax_g.size > 1
    _pfx = ctx.get('_prefix', 'sim')

    if not _has_sig and not _has_lp:
        return

    def _max_per_axis(arr, axis_sizes, keep_axes):
        """Compute max over all axes EXCEPT keep_axes."""
        reduce_axes = tuple(i for i in range(arr.ndim) if i not in keep_axes)
        if not reduce_axes:
            return arr
        return np.nanmax(arr, axis=reduce_axes)

    if _has_sig and _has_lp:
        # BOTH grids: 2D heatmap (σ × logPmax, max over f_bin × π)
        # lk shape: [logPmax, sigma, fbin, pi] (4D) or similar
        if lk.ndim == 4:
            hm_2d = np.nanmax(lk, axis=(2, 3))  # → [logPmax, sigma]
        elif lk.ndim == 3:
            hm_2d = np.nanmax(lk, axis=2)  # → [logPmax or sigma, sigma or fbin]
        else:
            return
        fig_hm = make_heatmap_fig(
            hm_2d, logPmax_g, sigma_g,
            title='Max Norm. Likelihood (σ_single × logP_max)',
            show_d=False, height=450,
            x_label='σ_single (km/s)',
            y_label='log₁₀(P_max / days)',
            x_name='σ',
            scoring_label='Likelihood',
            colorbar_title_override='Max Likelihood',
        )
        st.plotly_chart(fig_hm, use_container_width=True,
                        key=f'{_pfx}_sig_lp_heatmap')
        st.caption('Max likelihood across f_bin × π at each (σ_single, logP_max) point.')

    elif _has_sig:
        # σ only: 1D line chart
        if lk.ndim == 4:
            max_vals = [float(np.nanmax(lk[:, i_s, :, :]))
                        if np.any(np.isfinite(lk[:, i_s, :, :])) else 0.0
                        for i_s in range(sigma_g.size)]
        elif lk.ndim == 3:
            max_vals = [float(np.nanmax(lk[i_s]))
                        if np.any(np.isfinite(lk[i_s])) else 0.0
                        for i_s in range(sigma_g.size)]
        elif lk.ndim == 2:
            max_vals = [float(np.nanmax(lk[:, i_s]))
                        if np.any(np.isfinite(lk[:, i_s])) else 0.0
                        for i_s in range(sigma_g.size)]
        else:
            return
        fig = _make_max_pval_fig(sigma_g, max_vals, height=450,
                                 x_label='σ_single (km/s)',
                                 stat_label='Likelihood')
        st.plotly_chart(fig, use_container_width=True,
                        key=f'{_pfx}_sig_scan')

    elif _has_lp:
        # logPmax only: 1D line chart
        if lk.ndim == 4:
            max_vals = [float(np.nanmax(lk[i_lp]))
                        if np.any(np.isfinite(lk[i_lp])) else 0.0
                        for i_lp in range(logPmax_g.size)]
        elif lk.ndim == 3:
            max_vals = [float(np.nanmax(lk[i_lp]))
                        if np.any(np.isfinite(lk[i_lp])) else 0.0
                        for i_lp in range(logPmax_g.size)]
        else:
            return
        fig = _make_max_pval_fig(logPmax_g, max_vals, height=450,
                                 x_label='log₁₀(P_max / days)',
                                 stat_label='Likelihood')
        st.plotly_chart(fig, use_container_width=True,
                        key=f'{_pfx}_lp_scan')

# ── From sim_plots.py ────────────────────────────────────────────────────────

# WORKING — do not change this code (A5: Binary Fraction vs ΔRV Threshold — Langer version, approved 2026-03-30)
def render_binary_fraction_vs_threshold(p, gap_drv, gap_is_bin, intrinsic_fbin,
                                        observed_fbin, thresh_dRV, missed_count,
                                        total_bin, detected_bin_count, pal,
                                        model_label='', obs_delta_rv=None):
    """Binary fraction vs deltaRV threshold with gap annotation (Langer version).

    Shows both simulated curve (from gap_sim) and real observed curve (from obs_delta_rv).
    """
    st.markdown('### Binary Fraction vs Threshold')
    n_sim = len(gap_drv)
    thresh_arr = np.linspace(0, float(np.max(gap_drv) * 1.05), 200)
    fbin_curve = np.array([float(np.sum(gap_drv > t)) / n_sim for t in thresh_arr])
    bin_drv_all = gap_drv[gap_is_bin]
    sin_drv_all = gap_drv[~gap_is_bin]
    missed_bin_curve = np.array(
        [float(np.sum(bin_drv_all <= t)) / n_sim for t in thresh_arr])
    false_pos_curve = np.array(
        [float(np.sum(sin_drv_all > t)) / n_sim for t in thresh_arr])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=thresh_arr, y=missed_bin_curve,
        fill='tozeroy', fillcolor='rgba(242,166,35,0.25)',
        line=dict(width=0), mode='lines', name='Missed binaries', showlegend=True))
    if np.any(false_pos_curve > 0):
        fig.add_trace(go.Scatter(
            x=thresh_arr, y=false_pos_curve,
            fill='tozeroy', fillcolor='rgba(74,144,217,0.25)',
            line=dict(width=0), mode='lines', name='Singles above threshold', showlegend=True))
    fig.add_trace(go.Scatter(
        x=thresh_arr, y=fbin_curve, mode='lines',
        name='Simulated f_bin(threshold)', line=dict(color=_CLR_OBS, width=2.5)))
    # Real observed binary fraction curve (step/stairs)
    if obs_delta_rv is not None and len(obs_delta_rv) > 0:
        _obs_drv = np.sort(np.asarray(obs_delta_rv))
        _obs_fbin_curve = np.array(
            [float(np.sum(_obs_drv > t)) / len(_obs_drv) for t in _obs_drv])
        fig.add_trace(go.Scatter(
            x=_obs_drv, y=_obs_fbin_curve, mode='lines',
            name='Observed f_bin(threshold)',
            line=dict(color='white', width=2.5, shape='hv')))
    fig.add_hline(y=intrinsic_fbin, line_dash='dot', line_color=_CLR_DETECTED,
                  line_width=2, annotation_text=f'Intrinsic f_bin = {intrinsic_fbin:.1%}',
                  annotation_position='top left',
                  annotation_font=dict(size=11, color=_CLR_DETECTED))
    # "Real threshold" — where intrinsic f_bin crosses simulated fraction curve
    _crossings = np.where(np.diff(np.sign(fbin_curve - intrinsic_fbin)))[0]
    if len(_crossings) > 0:
        _ci = _crossings[0]
        _real_thresh = np.interp(intrinsic_fbin,
                                 [fbin_curve[_ci + 1], fbin_curve[_ci]],
                                 [thresh_arr[_ci + 1], thresh_arr[_ci]])
        fig.add_vline(x=_real_thresh, line_dash='dot', line_color='#00CC66',
                      line_width=2, annotation_text=f'Real threshold ≈ {_real_thresh:.0f} km/s',
                      annotation_position='bottom right',
                      annotation_font=dict(size=10, color='#00CC66'))
    fig.add_vline(x=thresh_dRV, line_dash='dash', line_color=_CLR_MISSED,
                  line_width=2, annotation_text=f'Threshold = {thresh_dRV} km/s',
                  annotation_position='top right',
                  annotation_font=dict(size=11, color=_CLR_MISSED))
    fig.add_trace(go.Scatter(
        x=[thresh_dRV], y=[observed_fbin], mode='markers+text',
        marker=dict(size=14, color='white', symbol='diamond',
                    line=dict(width=2, color='black')),
        text=[f'{observed_fbin:.1%}'], textposition='top left',
        textfont=dict(size=12, color='#333333'),
        name=f'Simulated @ {thresh_dRV} km/s', showlegend=True))
    gap_pct = intrinsic_fbin - observed_fbin
    fig.add_annotation(
        x=thresh_dRV + 15, y=(intrinsic_fbin + observed_fbin) / 2,
        text=f'Gap: {gap_pct:.1%}<br>({missed_count} missed / {total_bin} binaries)',
        showarrow=False, font=dict(size=11, color=_CLR_MISSED),
        bgcolor=pal['annotation_bg'], bordercolor=_CLR_MISSED,
        borderwidth=1, borderpad=4)
    fig.add_annotation(
        x=thresh_dRV, y=intrinsic_fbin, ax=thresh_dRV, ay=observed_fbin,
        xref='x', yref='y', axref='x', ayref='y',
        showarrow=True, arrowhead=3, arrowwidth=2, arrowcolor=_CLR_MISSED)
    fig.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(text='Binary Fraction vs \u0394RV Threshold', font=dict(size=14)),
        'xaxis_title': '\u0394RV threshold (km/s)', 'yaxis_title': 'Fraction of sample',
        'height': 400, 'margin': dict(l=60, r=80, t=50, b=50),
        'showlegend': True, 'legend': dict(x=0.55, y=0.95, font=dict(size=10)),
        'yaxis': dict(range=[0, min(1.0, intrinsic_fbin * 1.5)]),
    })
    st.plotly_chart(fig, use_container_width=True, key=f'{p}_gap_chart')
    sfx = f' ({model_label})' if model_label else ''
    st.caption(
        f'Binary fraction as a function of \u0394RV threshold{sfx}. '
        f'The blue curve shows the simulated fraction at the best-fit model. '
        f'The white step curve shows the real observed fraction from {len(obs_delta_rv) if obs_delta_rv is not None else 0} stars. '
        f'The dashed red line is the '
        f'intrinsic f_bin = {intrinsic_fbin:.1%}. At our threshold '
        f'({thresh_dRV} km/s), the simulated fraction is '
        f'{observed_fbin:.1%} \u2014 a gap of {gap_pct:.1%} due to '
        f'{missed_count} undetectable binaries. '
        f'Amber shading shows missed binaries; blue shading shows '
        f'singles scattered above each threshold.')

# WORKING — do not change this code (A6: Orbital Histograms — Langer version, approved 2026-03-30)
def render_orbital_histograms(p, gap_sim, bin_detected_mask, bin_missed_mask,
                              ana_fbin, ana_x_val, x_label, thresh_dRV,
                              detected_bin_count, missed_count, has_case_AB=False,
                              sigma_single=None, logP_max_val=None):
    """9-panel orbital parameter histograms (detected vs missed)."""
    st.markdown('---')
    st.markdown('### Binary Orbital Properties')
    # Subtitle with best-fit model parameters
    _parts = []
    if ana_fbin is not None:
        _parts.append(f'f_bin = {ana_fbin:.3f}')
    if ana_x_val is not None:
        _parts.append(f'{x_label} = {ana_x_val:.2f}')
    if sigma_single is not None:
        _parts.append(f'σ_single = {sigma_single:.1f} km/s')
    if logP_max_val is not None:
        _parts.append(f'logP_max = {logP_max_val:.2f}')
    if _parts:
        st.caption(f'Best-fit model: {", ".join(_parts)}')
    mb_opts = ['Compare detected vs missed', 'Detected binaries only',
               'Missed binaries only', 'All binaries (combined)']
    if has_case_AB and gap_sim.get('case_A_mask') is not None:
        mb_opts.append('Case A vs Case B')
    mb_view = st.radio('Show populations', mb_opts, horizontal=True, key=f'{p}_mb_view')

    P_det = _safe_mask(gap_sim['P_days'], bin_detected_mask)
    P_mis = _safe_mask(gap_sim['P_days'], bin_missed_mask)
    e_det = _safe_mask(gap_sim['e'], bin_detected_mask)
    e_mis = _safe_mask(gap_sim['e'], bin_missed_mask)
    q_det = _safe_mask(gap_sim['q'], bin_detected_mask)
    q_mis = _safe_mask(gap_sim['q'], bin_missed_mask)
    K1_det = _safe_mask(gap_sim['K1'], bin_detected_mask)
    K1_mis = _safe_mask(gap_sim['K1'], bin_missed_mask)
    M1_det = _safe_mask(gap_sim['M1'], bin_detected_mask)
    M1_mis = _safe_mask(gap_sim['M1'], bin_missed_mask)
    i_det = np.degrees(_safe_mask(gap_sim['i_rad'], bin_detected_mask))
    i_mis = np.degrees(_safe_mask(gap_sim['i_rad'], bin_missed_mask))
    has_omega = 'omega' in gap_sim
    if has_omega:
        omega_det = np.degrees(_safe_mask(gap_sim['omega'], bin_detected_mask))
        omega_mis = np.degrees(_safe_mask(gap_sim['omega'], bin_missed_mask))
        T0_det = _safe_mask(gap_sim['T0'], bin_detected_mask)
        T0_mis = _safe_mask(gap_sim['T0'], bin_missed_mask)
    else:
        omega_det = omega_mis = T0_det = T0_mis = np.array([])
    M2_det = q_det * M1_det if q_det.size > 0 and M1_det.size > 0 else np.array([])
    M2_mis = q_mis * M1_mis if q_mis.size > 0 and M1_mis.size > 0 else np.array([])
    P_all = gap_sim['P_days']; e_all = gap_sim['e']; q_all = gap_sim['q']
    K1_all = gap_sim['K1']; M1_all = gap_sim['M1']
    i_all = np.degrees(gap_sim['i_rad'])
    omega_all = np.degrees(gap_sim['omega']) if has_omega else np.array([])
    T0_all = gap_sim['T0'] if has_omega else np.array([])
    M2_all = q_all * M1_all if q_all.size > 0 else np.array([])

    xlabs = ['log\u2081\u2080(P / days)', 'e', 'q = M\u2082/M\u2081',
             'K\u2081 (km/s)', 'M\u2081 (M\u2299)', 'M\u2082 (M\u2299)',
             'i (degrees)', '\u03c9 (degrees)', 'T\u2080 (rad)']
    NC, NR, NBINS = 3, 3, 30
    fig_mb = make_subplots(rows=NR, cols=NC,
                           horizontal_spacing=0.08, vertical_spacing=0.10)
    def _pos(idx):
        return (idx // NC + 1, idx % NC + 1)
    def _add_hist(row, col, data, name, color, show_legend):
        if data.size == 0:
            return
        d_min, d_max = float(data.min()), float(data.max())
        if d_max == d_min:
            # Constant parameter — vertical line instead of fake histogram
            fig_mb.add_trace(go.Scatter(
                x=[d_min, d_min], y=[0, 1], mode='lines',
                line=dict(color=color, width=3),
                name=name, legendgroup=name, showlegend=show_legend,
            ), row=row, col=col)
            return
        bsz = (d_max - d_min) / NBINS
        fig_mb.add_trace(go.Histogram(
            x=data, xbins=dict(start=d_min, end=d_max + bsz * 0.01, size=bsz),
            histnorm='probability density', name=name, marker_color=color,
            opacity=0.6, legendgroup=name, showlegend=show_legend,
        ), row=row, col=col)
    def _logP(arr):
        return np.log10(arr) if arr.size > 0 else arr

    if mb_view == 'All binaries (combined)':
        ds = [_logP(P_all), e_all, q_all, K1_all, M1_all, M2_all,
              i_all, omega_all, T0_all]
        for pi, d in enumerate(ds):
            _add_hist(*_pos(pi), d, 'All binaries', _CLR_ALL, pi == 0)
    elif mb_view == 'Case A vs Case B':
        cA = gap_sim['case_A_mask']; cB = ~cA
        for mask, lbl, clr in [(cA, f'Case A ({int(cA.sum())})', _CLR_CASE_A),
                                (cB, f'Case B ({int(cB.sum())})', _CLR_CASE_B)]:
            ds = [_logP(_safe_mask(gap_sim['P_days'], mask)),
                  _safe_mask(gap_sim['e'], mask),
                  _safe_mask(gap_sim['q'], mask),
                  _safe_mask(gap_sim['K1'], mask),
                  _safe_mask(gap_sim['M1'], mask),
                  _safe_mask(gap_sim['q'], mask) * _safe_mask(gap_sim['M1'], mask),
                  np.degrees(_safe_mask(gap_sim['i_rad'], mask)),
                  np.degrees(_safe_mask(gap_sim.get('omega', np.array([])), mask)) if has_omega else np.array([]),
                  _safe_mask(gap_sim.get('T0', np.array([])), mask) if has_omega else np.array([])]
            for pi, d in enumerate(ds):
                _add_hist(*_pos(pi), d, lbl, clr, pi == 0)
    else:
        det_ds = [_logP(P_det), e_det, q_det, K1_det, M1_det, M2_det,
                  i_det, omega_det, T0_det]
        mis_ds = [_logP(P_mis), e_mis, q_mis, K1_mis, M1_mis, M2_mis,
                  i_mis, omega_mis, T0_mis]
        if mb_view in ('Compare detected vs missed', 'Detected binaries only'):
            for pi, d in enumerate(det_ds):
                _add_hist(*_pos(pi), d, 'Detected', _CLR_DETECTED, pi == 0)
        if mb_view in ('Compare detected vs missed', 'Missed binaries only'):
            for pi, d in enumerate(mis_ds):
                _add_hist(*_pos(pi), d, 'Missed', _CLR_MISSED, pi == 0)

    fig_mb.update_layout(**{
        **PLOTLY_THEME, 'barmode': 'overlay', 'height': 850,
        'margin': dict(l=40, r=20, t=40, b=60),
        'legend': dict(orientation='h', yanchor='bottom', y=1.04,
                       xanchor='center', x=0.5),
    })
    for pi in range(9):
        r, c = _pos(pi)
        fig_mb.update_xaxes(title_text=xlabs[pi], showgrid=False, row=r, col=c)
        fig_mb.update_yaxes(showgrid=False, row=r, col=c)
    for ri in range(1, NR + 1):
        fig_mb.update_yaxes(title_text='Prob. density', row=ri, col=1)
    st.plotly_chart(fig_mb, use_container_width=True, key=f'{p}_missed_binaries')
    _cap_parts = [f'f_bin={ana_fbin:.3f}' if ana_fbin is not None else 'f_bin=?']
    if ana_x_val is not None:
        _cap_parts.append(f'{x_label}={ana_x_val:.2f}')
    if sigma_single is not None:
        _cap_parts.append(f'σ_single={sigma_single:.1f} km/s')
    if logP_max_val is not None:
        _cap_parts.append(f'logP_max={logP_max_val:.2f}')
    st.caption(
        f'Orbital parameter distributions of simulated binaries at the '
        f'best-fit model ({", ".join(_cap_parts)}). '
        f'**Detected** (red): {detected_bin_count} binaries with '
        f'\u0394RV > {thresh_dRV} km/s. '
        f'**Missed** (amber): {missed_count} binaries below threshold. '
        f'Use "All binaries" to view the full population as a sanity check '
        f'that input distributions match expectations.')

# WORKING — do not change this code (A7: Methodology Equations — Langer version, approved 2026-03-30)
def render_methodology_equations(model_type):
    """Langer-specific methodology expander with equations."""
    st.markdown('---')
    with st.expander('Simulation methodology & equations (Langer 2020)', expanded=False):
        st.markdown(
            '**Langer 2020 period model** \u2014 uses physically motivated orbital '
            'parameter distributions from binary population synthesis '
            '(Langer et al. 2020, A&A 638, A39).\n\n'
            '**Cadence-aware simulation** \u2014 each simulated star preserves the '
            '**exact observation timestamps** from the real survey.\n\n'
            '---\n\n'
            '**For each grid point** (f_bin, and optionally log\u2081\u2080P_max, '
            '\u03c3_single):\n\n'
            '1. **Draw N systems.** Each of N_sets iterations generates a '
            'complete set of 25 simulated stars. Each star is assigned the '
            '**exact MJD sequence** of a randomly chosen real star. '
            'Each system is binary with probability f_bin, '
            'or single with probability 1 \u2212 f_bin.\n\n'
            '2. **Single stars:** draw RV at each epoch from '
            'N(v_sys, \u03c3_single). Then add per-epoch measurement noise '
            'drawn separately from the error model (\u03c3_measure). '
            'Compute \u0394RV = max(v) \u2212 min(v).\n\n'
            '3. **Binary stars \u2014 period distribution:**\n'
            '   Two-component mixture of Case A (short-period) and Case B '
            '(long-period) mass transfer channels:')
        st.latex(r'p(\log_{10} P) = w_A \cdot \mathcal{N}(\mu_A, \sigma_A) '
                 r'+ (1 - w_A) \cdot \mathrm{LogNormal}(\mu_B, \sigma_B)')
        st.markdown(
            '   - **Case A:** Gaussian in log\u2081\u2080P with \u03bc_A and \u03c3_A\n'
            '   - **Case B:** Log-normal in log\u2081\u2080P with mode \u03bc_B and '
            'width \u03c3_B\n'
            '   - **Mixture weight:** w_A for Case A, (1 \u2212 w_A) for Case B\n\n'
            '4. **Mass ratio q = M\u2082/M\u2081:** sampled from a Gaussian '
            'centered on \u03bc_q with width \u03c3_q '
            '(based on Langer+2020 Fig. 4, BH companion masses).\n\n'
            '5. **Eccentricity e = 0** (post-RLOF circularization).\n\n'
            '6. **Compute the RV semi-amplitude K\u2081:**')
        st.latex(r'K_1 = \left(\frac{2\pi G}{P}\right)^{1/3}'
                 r'\frac{M_2 \sin i}{(M_1 + M_2)^{2/3}}'
                 r'\frac{1}{\sqrt{1 - e^2}}')
        st.markdown('7. **Solve Kepler\'s equation** via Newton-Raphson:')
        st.latex(r'E - e \sin E = M, \quad M = T_0 + \frac{2\pi t}{P}')
        st.markdown('8. **True anomaly** \u03bd from E:')
        st.latex(r'\tan\frac{\nu}{2} = \sqrt{\frac{1+e}{1-e}} \, \tan\frac{E}{2}')
        st.markdown('9. **Radial velocity curve:**')
        st.latex(r'v(t) = v_{\rm sys} + K_1 \left[\cos(\omega + \nu) + e\cos\omega\right]')
        st.markdown(
            'Then \u0394RV = max(v) \u2212 min(v) over observed epochs.\n\n'
            '10. **Score** via multinomial log-likelihood. The observed and '
            'simulated \u0394RV distributions are binned, and the likelihood is:')
        st.latex(r'\ln L = \sum_{i} n_i \ln(p_i)')
        st.markdown(
            'where n_i is the observed count in bin i and p_i is the simulated '
            'fraction. Higher likelihood = better match.\n\n'
            '11. **Binary detection criteria** (both required):')
        st.latex(r'\Delta\mathrm{RV} > 45.5 \; \mathrm{km/s}'
                 r'\quad \text{and} \quad'
                 r'\Delta\mathrm{RV} - 4\sigma > 0')
        st.markdown(
            'where \u03c3 is the measurement error of the epoch pair.\n\n'
            '**Uncertainties** on model parameters (f_bin, \u03c3_single, '
            'logP_max) are derived from the 16th and 84th percentile of the '
            'marginalized likelihood in the corner plots.')

# ── Analysis plots helper ────────────────────────────────────────────────────

def _render_analysis_plots(p: str, ctx: dict, gap_sim: dict, method_results: dict) -> None:
    """Render period distribution, binary fraction, and orbital histograms."""
    pal = get_palette()
    thresh_dRV = ctx.get('thresh_dRV', 45.5)
    has_case_AB = ctx.get('has_case_AB', False)
    gap_drv = np.asarray(gap_sim.get('delta_rv', []))
    gap_is_bin = np.asarray(gap_sim.get('is_binary', []), dtype=bool)
    if gap_drv.size == 0:
        return
    idx_bin = gap_sim.get('idx_bin')
    if idx_bin is None:
        idx_bin = np.where(gap_is_bin)[0]
    bin_drv = gap_drv[idx_bin] if idx_bin.size > 0 else np.array([])
    bin_detected_mask = bin_drv > thresh_dRV
    bin_missed_mask = ~bin_detected_mask

    ana_fbin, ana_x_val, ana_sigma, ana_logPmax = None, None, None, None
    for mk, _, _, _, _ in SCORING_METHODS:
        mr = method_results.get(mk)
        if mr and 'best_vals' in mr:
            bv = mr['best_vals']
            ana_fbin = bv.get('fbin')
            ana_x_val = bv.get(ctx['x_name'])
            ana_sigma = bv.get('sigma')
            ana_logPmax = bv.get('logPmax')
            # Fallback: if x_name is sigma but wasn't scanned, use constant
            if ana_x_val is None and ctx['x_name'] == 'sigma':
                _sig_g_fb = np.asarray(ctx.get('result', {}).get('sigma_grid', [0.0]))
                if _sig_g_fb.size == 1:
                    ana_x_val = float(_sig_g_fb[0])
            break
    intrinsic_fbin = float(gap_is_bin.mean()) if gap_is_bin.size > 0 else 0.5
    x_label = ctx['x_label']
    logP_min, logP_max = ctx.get('logP_min', 0.15), ctx.get('logP_max', 4.0)
    total_bin = int(np.sum(gap_is_bin))
    detected_bin_count = int(np.sum(bin_detected_mask))
    missed_count = int(np.sum(bin_missed_mask))
    observed_fbin = detected_bin_count / max(len(gap_drv), 1)

    render_binary_fraction_vs_threshold(
        p, gap_drv, gap_is_bin, intrinsic_fbin, observed_fbin, thresh_dRV,
        missed_count, total_bin, detected_bin_count, pal,
        model_label=ctx['model_type'],
        obs_delta_rv=ctx.get('obs_delta_rv'))
    render_orbital_histograms(
        p, gap_sim, bin_detected_mask, bin_missed_mask,
        ana_fbin, ana_x_val, x_label, thresh_dRV,
        detected_bin_count, missed_count, has_case_AB=has_case_AB,
        sigma_single=ana_sigma, logP_max_val=ana_logPmax)

# ── Public entry point ───────────────────────────────────────────────────────

def render_shared_section(p: str, model_ctx: dict) -> dict:
    """Render shared graphs (summary table, CDF, sim plots) before radio selector.

    Returns method_results dict for use by scoring method tabs.
    """
    result = model_ctx.get('result')
    if result is None:
        st.info('Run a simulation or load a saved result to see analysis.')
        return {}

    extra_grids = _build_extra_grids(model_ctx)
    method_results = _render_method_summary_section(
        result, model_ctx['fbin_g'], model_ctx['x_g'],
        extra_grids=extra_grids, prefix=p,
        x_name=model_ctx['x_name'], x_label=model_ctx['x_label'],
        ndim_mode=model_ctx['ndim_mode'])
    if method_results is None:
        method_results = {}

    _render_all_methods_cdf(
        result, method_results, model_ctx['fbin_g'], model_ctx['x_g'],
        prefix=p, x_name=model_ctx['x_name'], x_label=model_ctx['x_label'])

    # E6: Per-bin breakdown table (directly under CDF)
    _obs_drv_e6 = result.get('obs_delta_rv')
    if _obs_drv_e6 is not None:
        _lk_be_e6 = result.get('likelihood_bin_edges')
        if _lk_be_e6 is None:
            try:
                from wr_bias_simulation import DSILVA_LIKELIHOOD_BINS
                _lk_be_e6 = DSILVA_LIKELIHOOD_BINS
            except ImportError:
                _lk_be_e6 = None
        if _lk_be_e6 is not None:
            try:
                from bc.render_lk_scoring_langer import _compute_pooled_sim
                from bc.render_lk_fit_langer import _render_likelihood_stats_table
                _pooled_e6 = _compute_pooled_sim(np.asarray(_obs_drv_e6), result)
                if _pooled_e6 is not None:
                    _render_likelihood_stats_table(
                        np.asarray(_obs_drv_e6), _pooled_e6, np.asarray(_lk_be_e6))
            except ImportError:
                pass

    # A3 sigma/logPmax chart: moved to Likelihood Analysis section (render_lk.py)

    gap_sim = model_ctx.get('gap_sim')
    if gap_sim is not None:
        _render_analysis_plots(p, model_ctx, gap_sim, method_results)

    render_methodology_equations(model_ctx['model_type'])
    return method_results
