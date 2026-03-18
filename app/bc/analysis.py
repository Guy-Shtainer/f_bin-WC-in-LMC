"""bc.analysis — Multi-method summary, per-method expanders, CDF comparison."""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from shared import (
    find_best_grid_point, make_heatmap_fig,
    PLOTLY_THEME, get_palette,
)

from bc.helpers import (
    SCORING_METHODS, _METHOD_COLORS, _hex_to_rgba,
    _RESULT_DIR,
)

# Re-export from split modules (external consumers import from bc.analysis)
from bc.scoring_detail import _render_cvm_analysis  # noqa: F401

_best_point = find_best_grid_point
_make_heatmap_fig = make_heatmap_fig


# ─────────────────────────────────────────────────────────────────────────────
# Multi-method summary + per-method expanders
# ─────────────────────────────────────────────────────────────────────────────

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
    p_nd: np.ndarray,
    grids: list[np.ndarray],
    grid_names: list[str],
    is_likelihood: bool = False,
) -> dict:
    """Find global best-fit and 68% HDI for each axis of a scoring array.

    Parameters
    ----------
    p_nd : ndarray
        N-dimensional scoring array (higher = better for all methods,
        since likelihood is already normalized to [0,1]).
    grids : list of 1D arrays
        Grid values for each axis, in order matching p_nd dimensions.
    grid_names : list of str
        Names for each axis (e.g. ['sigma', 'fbin', 'pi']).
    is_likelihood : bool
        True if the array is likelihood (not p-value). Affects labels only.

    Returns
    -------
    dict with keys:
        'best_idx' : tuple of int — multi-index of best point
        'best_vals' : dict[name -> float]
        'best_score' : float
        'hdi' : dict[name -> (mode, lo, hi)]
    """
    from wr_bias_simulation import compute_hdi68

    valid = np.isfinite(p_nd)
    if not np.any(valid):
        return None

    flat_best = int(np.nanargmax(p_nd))
    best_idx = np.unravel_index(flat_best, p_nd.shape)
    best_score = float(p_nd[best_idx])
    best_vals = {}
    hdi = {}

    for i, (g, name) in enumerate(zip(grids, grid_names)):
        best_vals[name] = float(g[best_idx[i]])
        # Marginalize over all other axes
        sum_axes = tuple(j for j in range(p_nd.ndim) if j != i)
        post_1d = np.nansum(p_nd, axis=sum_axes) if sum_axes else p_nd.copy()
        if post_1d.sum() > 0:
            mode, lo, hi = compute_hdi68(g, post_1d)
            hdi[name] = (float(mode), float(lo), float(hi))
        else:
            v = best_vals[name]
            hdi[name] = (v, v, v)

    return {
        'best_idx': best_idx,
        'best_vals': best_vals,
        'best_score': best_score,
        'hdi': hdi,
    }


def _render_method_summary_section(
    result: dict,
    fbin_g: np.ndarray,
    x_g: np.ndarray,
    extra_grids: list[tuple[str, np.ndarray]] | None = None,
    prefix: str = 'ds',
    x_name: str = 'pi',
    x_label: str = 'pi',
    ndim_mode: str = 'dsilva',
) -> dict:
    """Render a comparison table of all scoring methods above the per-method details.

    Returns method_results dict mapping method_key → {best_vals, hdi, ...}.

    Parameters
    ----------
    result : dict
        Full result dictionary (must contain scoring arrays).
    fbin_g : 1D array
        f_bin grid.
    x_g : 1D array
        Second-axis grid (pi for Dsilva, sigma for Langer).
    extra_grids : list of (name, 1D-array) or None
        Additional grids to include in the analysis (e.g. sigma, logPmax
        for the Dsilva 4D case). These are prepended to the grid list.
    prefix : str
        Unique key prefix for session state.
    x_name : str
        Display name for x_g axis (e.g. 'pi', 'sigma').
    x_label : str
        Formatted label for x_g axis (e.g. 'pi', 'sigma_single').
    ndim_mode : str
        'dsilva' (4D: logPmax x sigma x fbin x pi),
        'langer' (2D: fbin x sigma),
        'cadence_dsilva' (3D: sigma x fbin x pi),
        'cadence_langer' (3D/2D: sigma x fbin x pi).
    """
    # Build ordered grid list matching array dimensions
    if ndim_mode == 'dsilva':
        # 4D: [logPmax, sigma, fbin, pi]
        sigma_g = np.asarray(result.get('sigma_grid', [0.0]))
        logPmax_g = np.asarray(result.get('logPmax_grid', [0.0]))
        grids = [logPmax_g, sigma_g, fbin_g, x_g]
        grid_names = ['logPmax', 'sigma', 'fbin', x_name]
    elif ndim_mode == 'langer':
        # 2D: [fbin, sigma]
        grids = [fbin_g, x_g]
        grid_names = ['fbin', x_name]
    elif ndim_mode == 'cadence_langer':
        # Cadence Langer: arrays are [n_sig, n_fb, n_pi=1]
        # Squeeze pi dim and transpose to [n_fb, n_sig] → treat as 2D like Langer
        grids = [fbin_g, x_g]
        grid_names = ['fbin', x_name]
    elif ndim_mode == 'cadence_dsilva':
        # 3D: [sigma, fbin, pi]
        grids = []
        grid_names = []
        if extra_grids:
            for gn, ga in extra_grids:
                grids.append(ga)
                grid_names.append(gn)
        grids.extend([fbin_g, x_g])
        grid_names.extend(['fbin', x_name])
    else:
        grids = [fbin_g, x_g]
        grid_names = ['fbin', x_name]

    rows = []
    method_results = {}

    for mk, mname, pk, dk, mcolor in SCORING_METHODS:
        p_arr = _get_method_array(result, pk)
        if p_arr is None:
            continue

        # Ensure dimensionality matches expected grids
        is_lk = (mk == 'likelihood')

        # For Dsilva 4D: ensure 4D
        if ndim_mode == 'dsilva':
            if p_arr.ndim == 2:
                p_arr = p_arr[np.newaxis, np.newaxis, ...]
            elif p_arr.ndim == 3:
                p_arr = p_arr[np.newaxis, ...]

        # For cadence Langer: squeeze pi dim and transpose to [n_fb, n_sig]
        if ndim_mode == 'cadence_langer':
            if p_arr.ndim == 3 and p_arr.shape[2] == 1:
                p_arr = p_arr[:, :, 0].T  # [n_sig, n_fb, 1] → [n_fb, n_sig]
            elif p_arr.ndim == 3:
                # Multi-pi cadence langer — shouldn't happen but handle gracefully
                p_arr = p_arr[:, :, 0].T
            while p_arr.ndim > len(grids):
                p_arr = p_arr[0]
        # For cadence Dsilva: squeeze leading dims if needed
        elif ndim_mode == 'cadence_dsilva':
            while p_arr.ndim > len(grids):
                p_arr = p_arr[0]

        info = _method_best_and_hdi(p_arr, grids, grid_names, is_likelihood=is_lk)
        if info is None:
            continue
        method_results[mk] = info

        bv = info['best_vals']
        hdi = info['hdi']

        def _fmt_hdi_cell(name, fmt='.4f'):
            if name not in hdi:
                return '--'
            mode, lo, hi = hdi[name]
            return f'{mode:{fmt}} (+{hi - mode:{fmt}} / -{mode - lo:{fmt}})'

        fb_best = f"{bv.get('fbin', 0):.4f}"
        fb_hdi = _fmt_hdi_cell('fbin', '.4f')

        x_best = f"{bv.get(x_name, 0):.3f}"
        x_hdi = _fmt_hdi_cell(x_name, '.3f')

        # Sigma columns (only if sigma is a separate grid axis, not the x-axis)
        _has_sigma_col = ('sigma' in grid_names and x_name != 'sigma')
        sig_best = ''
        sig_hdi = ''
        if _has_sigma_col:
            sig_best = f"{bv.get('sigma', 0):.2f}"
            sig_hdi = _fmt_hdi_cell('sigma', '.2f')

        score_val = f"{info['best_score']:.6f}"

        row = {
            'Method': mname,
            'Best f_bin': fb_best,
            '68% HDI f_bin': fb_hdi,
            f'Best {x_label}': x_best,
            f'68% HDI {x_label}': x_hdi,
            'Score (best)': score_val,
        }
        if _has_sigma_col:
            row['Best σ_single'] = sig_best
            row['68% HDI σ_single'] = sig_hdi
        rows.append(row)

    if not rows:
        return

    # Compute agreement column: does each method's best f_bin fall within
    # every other method's 68% HDI for f_bin?
    for i, row in enumerate(rows):
        mk_i = SCORING_METHODS[i][0]
        if mk_i not in method_results:
            row['Agreement'] = '--'
            continue
        best_fb_i = method_results[mk_i]['best_vals'].get('fbin', np.nan)
        in_all = True
        for mk_j, info_j in method_results.items():
            if mk_j == mk_i:
                continue
            lo_j = info_j['hdi'].get('fbin', (0, 0, 0))[1]
            hi_j = info_j['hdi'].get('fbin', (0, 0, 0))[2]
            if not (lo_j <= best_fb_i <= hi_j):
                in_all = False
                break
        row['Agreement'] = 'Yes' if in_all else 'No'

    st.markdown('#### Scoring Method Comparison')
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(
        'Comparison of all scoring methods. "Agreement" = does this method\'s '
        'best f_bin fall within every other method\'s 68% HDI for f_bin.'
    )

    return method_results


def _render_all_methods_cdf(
    result: dict,
    method_results: dict,
    fbin_g: np.ndarray,
    x_g: np.ndarray,
    prefix: str,
    x_name: str = 'pi',
    x_label: str = 'pi',
) -> None:
    """CDF comparison: observed vs best-fit model from each scoring method."""
    obs_drv = result.get('obs_delta_rv')
    if obs_drv is None or len(method_results) < 1:
        return
    try:
        from wr_bias_simulation import (
            binned_cdf, DEFAULT_DRV_BIN_EDGES,
            simulate_delta_rv_sample, SimulationConfig, BinaryParameterConfig,
        )
    except ImportError:
        return

    _be = result.get('bin_edges')
    if _be is None:
        _be = DEFAULT_DRV_BIN_EDGES
    else:
        _be = np.asarray(_be)
    obs_drv = np.asarray(obs_drv)
    _n_obs_stars = len(obs_drv)
    obs_cdf = binned_cdf(obs_drv, _be)
    _obs_x = np.concatenate([[0.0], _be])
    _obs_y = np.concatenate([[0.0], obs_cdf])

    fig_cdf = go.Figure()
    fig_cdf.add_trace(go.Scatter(
        x=_obs_x, y=_obs_y,
        mode='lines', name='Observed',
        line=dict(color='black', width=2.5),
    ))

    _n_cdf_sets = 100
    for mk, info in method_results.items():
        bv = info['best_vals']
        fb = bv.get('fbin', 0.5)
        pi_v = bv.get(x_name, 0.0)
        sig_v = bv.get('sigma', 5.0)
        _mcolor = next((c for k, _, _, _, c in SCORING_METHODS if k == mk), '#888888')
        _mname = next((n for k, n, _, _, _ in SCORING_METHODS if k == mk), mk)
        try:
            _all_cdfs = []
            for _seed_i in range(_n_cdf_sets):
                sim_cfg = SimulationConfig(
                    n_stars=_n_obs_stars,
                    sigma_single=float(sig_v),
                    sigma_measure=float(result.get('sigma_meas', 3.0)),
                )
                bin_cfg = BinaryParameterConfig()
                rng = np.random.default_rng(42 + _seed_i)
                sim_drv = simulate_delta_rv_sample(
                    f_bin=float(fb), pi=float(pi_v),
                    sim_cfg=sim_cfg, bin_cfg=bin_cfg, rng=rng)
                _all_cdfs.append(binned_cdf(sim_drv, _be))
            _all_cdfs = np.array(_all_cdfs)
            _median_cdf = np.median(_all_cdfs, axis=0)
            _lo_cdf = np.percentile(_all_cdfs, 16, axis=0)
            _hi_cdf = np.percentile(_all_cdfs, 84, axis=0)

            _med_x = np.concatenate([[0.0], _be])
            _med_y = np.concatenate([[0.0], _median_cdf])
            _lo_y = np.concatenate([[0.0], _lo_cdf])
            _hi_y = np.concatenate([[0.0], _hi_cdf])

            _lbl = f'{_mname} (f_bin={fb:.3f}'
            if x_name in bv:
                _lbl += f', {x_label}={bv[x_name]:.2f}'
            _lbl += ')'

            _fill_color = _hex_to_rgba(_mcolor, 0.2)
            fig_cdf.add_trace(go.Scatter(
                x=np.concatenate([_med_x, _med_x[::-1]]),
                y=np.concatenate([_hi_y, _lo_y[::-1]]),
                fill='toself', fillcolor=_fill_color,
                line=dict(color='rgba(0,0,0,0)'),
                showlegend=False, hoverinfo='skip',
            ))
            fig_cdf.add_trace(go.Scatter(
                x=_med_x, y=_med_y,
                mode='lines', name=_lbl,
                line=dict(color=_mcolor, width=2, dash='dash'),
            ))
        except Exception:
            pass

    fig_cdf.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(text='CDF Comparison: Observed vs Best-Fit Models', font=dict(size=14)),
        'xaxis_title': 'ΔRV (km/s)',
        'yaxis_title': 'Cumulative Fraction',
        'height': 400,
        'legend': dict(x=0.55, y=0.05),
    })
    st.plotly_chart(fig_cdf, use_container_width=True,
                    key=f'{prefix}_cdf_comparison')
    st.caption(
        f'Observed ΔRV CDF (solid black) vs simulated CDFs at each '
        f'method\'s best-fit parameters (dashed, median of {_n_cdf_sets} draws). '
        f'Shaded bands show 16th-84th percentile range. N_stars={_n_obs_stars}.'
    )


def _render_method_expander(
    method_key: str,
    display_name: str,
    p_nd: np.ndarray,
    D_nd: np.ndarray | None,
    result: dict,
    fbin_g: np.ndarray,
    x_g: np.ndarray,
    prefix: str,
    height: int = 520,
    width: int | None = None,
    use_cw: bool = True,
    x_label: str = 'pi',
    x_name: str = 'pi',
    x_display_label: str = 'pi (period power-law index)',
    ndim_mode: str = 'dsilva',
    disp_outer_slices: tuple[int, ...] | None = None,
    method_results: dict | None = None,
) -> None:
    """Render one scoring method's detail panel inside an expander.

    Shows: heatmap of the 2D (fbin x x) slice, best-fit metrics,
    and calls _render_cvm_analysis with the appropriate mode.

    Parameters
    ----------
    p_nd : ndarray
        Full N-dimensional scoring array (p-value or likelihood).
    D_nd : ndarray or None
        Full N-dimensional D-statistic array.
    disp_outer_slices : tuple of int or None
        Indices for outer dimensions to select the 2D slice to display.
        For Dsilva 4D: (logPmax_idx, sigma_idx).
        For cadence 3D: (sigma_idx,).
        For Langer 2D: None (already 2D).
    method_results : dict or None
        All methods' best-fit info (from _render_method_summary_section).
        Used to render CDF comparison inside K-S expander.
    """
    _is_likelihood = (method_key == 'likelihood')
    _theme = PLOTLY_THEME
    pal = get_palette()

    # Slice down to 2D: [fbin, x]
    if disp_outer_slices is not None and p_nd.ndim > 2:
        p_2d = p_nd[disp_outer_slices]
        D_2d = D_nd[disp_outer_slices] if D_nd is not None else None
    else:
        p_2d = p_nd
        D_2d = D_nd

    # Ensure 2D
    while p_2d.ndim > 2:
        p_2d = p_2d[0]
        if D_2d is not None:
            D_2d = D_2d[0]

    # Global best across all dimensions
    valid = np.isfinite(p_nd)
    if not np.any(valid):
        st.warning(f'No valid data for {display_name}.')
        return

    flat_best = int(np.nanargmax(p_nd))
    global_best_idx = np.unravel_index(flat_best, p_nd.shape)
    global_best_score = float(p_nd[global_best_idx])

    # Slice best
    slice_valid = np.isfinite(p_2d)
    if np.any(slice_valid):
        flat_slice_best = int(np.nanargmax(p_2d))
        slice_best_idx = np.unravel_index(flat_slice_best, p_2d.shape)
        slice_best_fb = float(fbin_g[slice_best_idx[0]])
        slice_best_x = float(x_g[slice_best_idx[1]])
        slice_best_score = float(p_2d[slice_best_idx])
    else:
        slice_best_fb = slice_best_x = slice_best_score = float('nan')

    # Determine global best fbin and x values
    # For Dsilva 4D: axes are [logPmax, sigma, fbin, pi]
    if ndim_mode == 'dsilva':
        g_fb = float(fbin_g[global_best_idx[2]])
        g_x = float(x_g[global_best_idx[3]])
    elif ndim_mode in ('cadence_dsilva', 'cadence_langer'):
        # 3D: [sigma, fbin, pi] or [sigma, fbin, sigma]
        g_fb = float(fbin_g[global_best_idx[-2]])
        g_x = float(x_g[global_best_idx[-1]])
    else:
        # 2D: [fbin, x]
        g_fb = float(fbin_g[global_best_idx[0]])
        g_x = float(x_g[global_best_idx[1]])

    if _is_likelihood:
        score_label = 'Likelihood'
    elif method_key == 'cvm':
        score_label = 'CvM S-score'
    else:
        score_label = 'p-value'

    # ── Heatmap ──────────────────────────────────────────────────
    show_d = not _is_likelihood
    fig_hm = _make_heatmap_fig(
        p_2d, fbin_g, x_g,
        title=f'{display_name} — {score_label}',
        show_d=show_d,
        ks_d_2d=D_2d if show_d else None,
        height=height, width=width,
        x_label=x_display_label,
        x_name=x_name,
        scoring_label=display_name,
    )
    st.plotly_chart(fig_hm, use_container_width=use_cw,
                    key=f'{prefix}_{method_key}_hm')

    # ── Slice vs Global metrics ──────────────────────────────────
    # For 2D arrays (Langer, cadence_langer) the slice IS the global — show
    # a single "Best fit" card instead of the redundant slice-vs-global pair.
    _is_2d_mode = ndim_mode in ('langer', 'cadence_langer') or p_nd.ndim <= 2
    if _is_2d_mode:
        st.metric(
            label=f'Best fit ({display_name})',
            value=f'f_bin={g_fb:.4f}, {x_label}={g_x:.3f}',
            delta=f'{score_label} = {global_best_score:.6f}',
            delta_color='off',
        )
    else:
        mc1, mc2 = st.columns(2)
        mc1.metric(
            label=f'Current slice best ({display_name})',
            value=f'f_bin={slice_best_fb:.4f}, {x_label}={slice_best_x:.3f}',
            delta=f'{score_label} = {slice_best_score:.6f}',
            delta_color='off',
        )
        mc2.metric(
            label=f'Global best ({display_name})',
            value=f'f_bin={g_fb:.4f}, {x_label}={g_x:.3f}',
            delta=f'{score_label} = {global_best_score:.6f}',
            delta_color='off',
        )

    # ── Scoring analysis (reuse _render_cvm_analysis) ────────────
    _obs_drv = result.get('obs_delta_rv')
    _lk_edges = result.get('likelihood_bin_edges')
    if method_key in ('cvm', 'likelihood'):
        _mode = method_key
        _render_cvm_analysis(
            D_2d if D_2d is not None else p_2d,
            p_2d,
            fbin_g, x_g,
            x_label='f_bin', y_label=x_label,
            height=height, width=width,
            prefix=f'{prefix}_{method_key}_analysis',
            mode=_mode,
            obs_delta_rv=_obs_drv,
            likelihood_bin_edges=_lk_edges,
            result=result,
        )

    # ── Likelihood vs σ_single (only for likelihood with multiple σ values) ──
    if method_key == 'likelihood':
        _sigma_g = np.asarray(result.get('sigma_grid', []))
        _lk_full = result.get('likelihood')
        if _lk_full is not None and _sigma_g.size > 1:
            _lk_full = np.asarray(_lk_full, dtype=float)
            # Compute max likelihood per σ_single (marginalize over f_bin, π, logPmax)
            if _lk_full.ndim == 4:
                # [logPmax, sigma, fbin, pi] → max over logPmax, fbin, pi
                _max_per_sig = np.nanmax(_lk_full, axis=(0, 2, 3))
            elif _lk_full.ndim == 3:
                # [sigma, fbin, pi] → max over fbin, pi
                _max_per_sig = np.nanmax(_lk_full, axis=(1, 2))
            elif _lk_full.ndim == 2:
                # Langer: [fbin, sigma] → max over fbin
                _max_per_sig = np.nanmax(_lk_full, axis=0)
            else:
                _max_per_sig = None

            if _max_per_sig is not None and _max_per_sig.size == _sigma_g.size:
                st.divider()
                _best_sig_idx = int(np.nanargmax(_max_per_sig))
                _fig_sig = go.Figure()
                _fig_sig.add_trace(go.Scatter(
                    x=_sigma_g, y=_max_per_sig,
                    mode='lines+markers', name='Max Likelihood',
                    line=dict(color='#4A90D9', width=2),
                    marker=dict(size=6),
                ))
                _fig_sig.add_trace(go.Scatter(
                    x=[float(_sigma_g[_best_sig_idx])],
                    y=[float(_max_per_sig[_best_sig_idx])],
                    mode='markers', name='Best σ_single',
                    marker=dict(symbol='star', size=16, color='#DAA520'),
                ))
                _fig_sig.update_layout(**{
                    **PLOTLY_THEME,
                    'title': dict(
                        text='Max Likelihood vs σ_single',
                        font=dict(size=14),
                    ),
                    'xaxis_title': 'σ_single (km/s)',
                    'yaxis_title': 'Max Normalized Likelihood',
                    'height': 380,
                    'legend': dict(x=0.7, y=0.95),
                })
                st.plotly_chart(_fig_sig, use_container_width=use_cw,
                                key=f'{prefix}_{method_key}_sig_profile')
                st.caption(
                    f'Best σ_single = {_sigma_g[_best_sig_idx]:.1f} km/s '
                    f'(max L = {_max_per_sig[_best_sig_idx]:.4f}). '
                    f'Shows the maximum globally-normalized likelihood at each '
                    f'σ_single value (maximized over f_bin and π).'
                )

    # ── Corner Plot (2-param: fbin x x) ─────────────────────────────
    st.divider()
    with st.expander(f'Corner Plot — {display_name}', expanded=False):
        from plotly.subplots import make_subplots as _ms
        from wr_bias_simulation import compute_hdi68

        # Build grids/names matching p_nd dimensions
        if ndim_mode == 'dsilva':
            _sigma_g = np.asarray(result.get('sigma_grid', [0.0]))
            _logPmax_g = np.asarray(result.get('logPmax_grid', [0.0]))
            _all_grids = [_logPmax_g, _sigma_g, fbin_g, x_g]
            _all_names = ['logPmax', 'sigma', 'fbin', x_name]
        elif ndim_mode == 'langer':
            _all_grids = [fbin_g, x_g]
            _all_names = ['fbin', x_name]
        else:
            # cadence modes — build from p_nd shape
            _all_grids = []
            _all_names = []
            _sig_g_c = np.asarray(result.get('sigma_grid', [0.0]))
            if p_nd.ndim >= 3 and _sig_g_c.size > 1:
                _all_grids.append(_sig_g_c)
                _all_names.append('sigma')
            _all_grids.extend([fbin_g, x_g])
            _all_names.extend(['fbin', x_name])

        _info = _method_best_and_hdi(p_nd, _all_grids, _all_names,
                                     is_likelihood=_is_likelihood)
        if _info is not None:
            _hdi = _info['hdi']
            _bv = _info['best_vals']
            _fb_mode, _fb_lo, _fb_hi = _hdi.get('fbin', (0, 0, 0))
            _x_mode, _x_lo, _x_hi = _hdi.get(x_name, (0, 0, 0))

            # Marginalize to 1D posteriors
            _fb_ax = _all_names.index('fbin')
            _x_ax = _all_names.index(x_name)
            _sum_fb = tuple(j for j in range(p_nd.ndim) if j != _fb_ax)
            _sum_x = tuple(j for j in range(p_nd.ndim) if j != _x_ax)
            _post_fb = np.nansum(p_nd, axis=_sum_fb) if _sum_fb else p_nd.copy()
            _post_x = np.nansum(p_nd, axis=_sum_x) if _sum_x else p_nd.copy()

            # Marginalize to 2D (fbin x x)
            _keep = sorted([_fb_ax, _x_ax])
            _sum_2d = tuple(j for j in range(p_nd.ndim) if j not in _keep)
            _p2d_marg = np.nansum(p_nd, axis=_sum_2d) if _sum_2d else p_nd.copy()
            # Orient: rows=fbin, cols=x
            if _fb_ax == _keep[0]:
                _z_corner = _p2d_marg
            else:
                _z_corner = _p2d_marg.T

            fig_c = _ms(rows=2, cols=2, horizontal_spacing=0.08,
                        vertical_spacing=0.08)

            # [0,0] f_bin posterior
            _norm_fb = float(np.trapezoid(_post_fb, fbin_g))
            _pn_fb = _post_fb / _norm_fb if _norm_fb > 0 else _post_fb
            fig_c.add_trace(go.Scatter(
                x=fbin_g, y=_pn_fb, mode='lines',
                line=dict(color='#4A90D9', width=2), showlegend=False,
            ), row=1, col=1)
            _m_fb = (fbin_g >= _fb_lo) & (fbin_g <= _fb_hi)
            if np.any(_m_fb):
                _xh = fbin_g[_m_fb]
                _yh = _pn_fb[_m_fb]
                fig_c.add_trace(go.Scatter(
                    x=np.concatenate([_xh, _xh[::-1]]),
                    y=np.concatenate([_yh, np.zeros(len(_yh))]),
                    fill='toself', fillcolor='rgba(74,144,217,0.3)',
                    line=dict(width=0), showlegend=False,
                ), row=1, col=1)
            fig_c.add_vline(x=_fb_mode, line_dash='dash',
                            line_color='#E25A53', line_width=1.5,
                            row=1, col=1)

            # [1,1] x posterior
            _norm_x = float(np.trapezoid(_post_x, x_g))
            _pn_x = _post_x / _norm_x if _norm_x > 0 else _post_x
            fig_c.add_trace(go.Scatter(
                x=x_g, y=_pn_x, mode='lines',
                line=dict(color='#4A90D9', width=2), showlegend=False,
            ), row=2, col=2)
            _m_x = (x_g >= _x_lo) & (x_g <= _x_hi)
            if np.any(_m_x):
                _xh2 = x_g[_m_x]
                _yh2 = _pn_x[_m_x]
                fig_c.add_trace(go.Scatter(
                    x=np.concatenate([_xh2, _xh2[::-1]]),
                    y=np.concatenate([_yh2, np.zeros(len(_yh2))]),
                    fill='toself', fillcolor='rgba(74,144,217,0.3)',
                    line=dict(width=0), showlegend=False,
                ), row=2, col=2)
            fig_c.add_vline(x=_x_mode, line_dash='dash',
                            line_color='#E25A53', line_width=1.5,
                            row=2, col=2)

            # [1,0] 2D heatmap — x-axis=fbin (col 1), y-axis=x (row 2)
            _z_max = float(np.nanmax(_z_corner)) if np.any(np.isfinite(_z_corner)) else 1.0
            fig_c.add_trace(go.Heatmap(
                x=fbin_g, y=x_g, z=_z_corner.T,
                colorscale='RdBu_r', zmin=0, zmax=_z_max,
                zsmooth='best', showscale=False,
            ), row=2, col=1)
            # Contour overlay
            _zf = _z_corner.ravel()
            _zp = _zf[_zf > 0]
            if len(_zp) > 2:
                _zs = np.sort(_zp)[::-1]
                _zcs = np.cumsum(_zs)
                _zcs = _zcs / _zcs[-1]
                _i68 = np.searchsorted(_zcs, 0.68)
                _i95 = np.searchsorted(_zcs, 0.95)
                _l68 = float(_zs[min(_i68, len(_zs) - 1)])
                _l95 = float(_zs[min(_i95, len(_zs) - 1)])
                fig_c.add_trace(go.Contour(
                    x=fbin_g, y=x_g, z=_z_corner.T,
                    contours=dict(coloring='none', showlabels=True,
                                  labelfont=dict(size=8, color=pal['contour_label'])),
                    ncontours=2, contours_start=_l95, contours_end=_l68,
                    line=dict(color=pal['contour_color'], width=1.5, dash='dot'),
                    showscale=False, hoverinfo='skip',
                ), row=2, col=1)
            # Best-fit star
            fig_c.add_trace(go.Scatter(
                x=[_bv.get('fbin', 0)], y=[_bv.get(x_name, 0)],
                mode='markers',
                marker=dict(symbol='star', size=10, color='#DAA520',
                            line=dict(color='black', width=1)),
                showlegend=False,
            ), row=2, col=1)

            # Hide upper-right cell
            fig_c.update_xaxes(visible=False, row=1, col=2)
            fig_c.update_yaxes(visible=False, row=1, col=2)
            # Axis labels — corner plot: col 1 = fbin, row 2 = x
            fig_c.update_xaxes(title_text='f_bin', row=1, col=1)
            fig_c.update_xaxes(title_text='f_bin', row=2, col=1)
            fig_c.update_xaxes(title_text=x_display_label, row=2, col=2)
            fig_c.update_yaxes(title_text=x_display_label, row=2, col=1)

            fig_c.update_layout(**{
                **PLOTLY_THEME,
                'height': 500, 'showlegend': False,
                'margin': dict(l=60, r=20, t=30, b=60),
            })
            st.plotly_chart(fig_c, use_container_width=True,
                            key=f'{prefix}_{method_key}_corner')
            st.caption(
                f'2-parameter corner plot for {display_name}. '
                f'Diagonal: 1D posteriors with 68% HDI (blue shading) and mode (red dashed). '
                f'Off-diagonal: 2D marginalized heatmap with 68%/95% contours and best fit (gold star).'
            )
        else:
            st.info('No valid data for corner plot.')

    # ── All-methods CDF comparison (K-S expander only) ──────────────
    if method_key == 'ks' and method_results:
        st.divider()
        with st.expander('CDF Comparison — All Scoring Methods', expanded=False):
            _render_all_methods_cdf(
                result, method_results, fbin_g, x_g,
                prefix=f'{prefix}_{method_key}',
                x_name=x_name, x_label=x_label,
            )

    # ── Model Explorer (best-fit CDF, histogram, detection fraction) ──
    _obs_drv_me = result.get('obs_delta_rv')
    if _obs_drv_me is not None:
        st.divider()
        with st.expander(f'Model Explorer — {display_name}', expanded=False):
            try:
                from wr_bias_simulation import (
                    simulate_delta_rv_sample, SimulationConfig,
                    BinaryParameterConfig, binned_cdf, DEFAULT_DRV_BIN_EDGES,
                )

                # Get best-fit params from global argmax
                _me_info = _info  # reuse from corner plot section
                if _me_info is None:
                    _me_info = _method_best_and_hdi(
                        p_nd,
                        _all_grids if '_all_grids' in dir() else [fbin_g, x_g],
                        _all_names if '_all_names' in dir() else ['fbin', x_name],
                        is_likelihood=_is_likelihood,
                    )
                if _me_info is not None:
                    _me_bv = _me_info['best_vals']
                    _me_fb = float(_me_bv.get('fbin', 0.5))
                    _me_x = float(_me_bv.get(x_name, 0.0))
                    _me_sig = float(_me_bv.get('sigma', result.get('sigma_meas', 5.0)))

                    _obs_drv_arr = np.asarray(_obs_drv_me)
                    _be = result.get('bin_edges')
                    if _be is None:
                        _be = DEFAULT_DRV_BIN_EDGES
                    else:
                        _be = np.asarray(_be)

                    # Simulate at best-fit
                    _sim_cfg_me = SimulationConfig(
                        n_stars=1000,
                        sigma_single=_me_sig,
                        sigma_measure=float(result.get('sigma_meas', 3.0)),
                    )
                    _bin_cfg_me = BinaryParameterConfig()
                    _rng_me = np.random.default_rng(42)
                    _sim_drv = simulate_delta_rv_sample(
                        _me_fb, _me_x, _sim_cfg_me, _bin_cfg_me, _rng_me)

                    # 1) CDF comparison
                    _obs_cdf = binned_cdf(_obs_drv_arr, _be)
                    _sim_cdf = binned_cdf(_sim_drv, _be)

                    fig_me_cdf = go.Figure()
                    fig_me_cdf.add_trace(go.Scatter(
                        x=_be, y=_obs_cdf, mode='lines', name='Observed',
                        line=dict(color='#4A90D9', width=2.5, shape='hv'),
                    ))
                    fig_me_cdf.add_trace(go.Scatter(
                        x=_be, y=_sim_cdf, mode='lines', name='Simulated',
                        line=dict(color='#E25A53', width=2.5, dash='dash', shape='hv'),
                    ))
                    fig_me_cdf.update_layout(**{
                        **PLOTLY_THEME,
                        'title': dict(
                            text=f'CDF at best fit (f_bin={_me_fb:.3f}, {x_label}={_me_x:.2f})',
                            font=dict(size=14)),
                        'xaxis_title': 'DeltaRV (km/s)',
                        'yaxis_title': 'Cumulative fraction',
                        'height': 380,
                        'legend': dict(x=0.6, y=0.15),
                    })
                    st.plotly_chart(fig_me_cdf, use_container_width=True,
                                    key=f'{prefix}_{method_key}_me_cdf')

                    # 2) DeltaRV histogram overlay
                    fig_me_hist = go.Figure()
                    fig_me_hist.add_trace(go.Histogram(
                        x=_obs_drv_arr, nbinsx=30,
                        histnorm='probability density',
                        name='Observed', marker_color='#4A90D9', opacity=0.6,
                    ))
                    fig_me_hist.add_trace(go.Histogram(
                        x=_sim_drv, nbinsx=30,
                        histnorm='probability density',
                        name='Simulated', marker_color='#E25A53', opacity=0.5,
                    ))
                    fig_me_hist.update_layout(**{
                        **PLOTLY_THEME,
                        'barmode': 'overlay',
                        'title': dict(text='DeltaRV Distribution', font=dict(size=14)),
                        'xaxis_title': 'DeltaRV (km/s)',
                        'yaxis_title': 'Probability density',
                        'height': 380,
                        'legend': dict(x=0.65, y=0.95),
                    })
                    st.plotly_chart(fig_me_hist, use_container_width=True,
                                    key=f'{prefix}_{method_key}_me_hist')

                    # 3) Detection fraction vs threshold
                    _max_drv = max(float(np.max(_obs_drv_arr)),
                                   float(np.max(_sim_drv)))
                    _thresholds = np.linspace(0, _max_drv * 1.1, 100)
                    _frac_obs = np.array([(_obs_drv_arr > T).mean() for T in _thresholds])
                    _frac_sim = np.array([(_sim_drv > T).mean() for T in _thresholds])

                    fig_me_det = go.Figure()
                    fig_me_det.add_trace(go.Scatter(
                        x=_thresholds, y=_frac_obs, mode='lines', name='Observed',
                        line=dict(color='#4A90D9', width=2.5),
                    ))
                    fig_me_det.add_trace(go.Scatter(
                        x=_thresholds, y=_frac_sim, mode='lines', name='Simulated',
                        line=dict(color='#E25A53', width=2.5, dash='dash'),
                    ))
                    _thresh_dRV = float(result.get('thresh_dRV', 45.5))
                    fig_me_det.add_vline(
                        x=_thresh_dRV, line_dash='dot',
                        line_color='#DAA520', line_width=1.5,
                        annotation_text=f'Threshold={_thresh_dRV:.0f}',
                        annotation_position='top right',
                        annotation_font_color='#DAA520',
                    )
                    fig_me_det.update_layout(**{
                        **PLOTLY_THEME,
                        'title': dict(
                            text=f'Detection Fraction (f_bin={_me_fb:.3f}, {x_label}={_me_x:.2f})',
                            font=dict(size=14)),
                        'xaxis_title': 'DeltaRV threshold (km/s)',
                        'yaxis_title': 'Fraction above threshold',
                        'height': 380,
                        'yaxis': dict(range=[0, 1.05]),
                        'legend': dict(x=0.65, y=0.95),
                    })
                    st.plotly_chart(fig_me_det, use_container_width=True,
                                    key=f'{prefix}_{method_key}_me_det')

                    st.caption(
                        f'Best-fit model explorer for {display_name}. '
                        f'Top: binned CDF comparison. Middle: DeltaRV histogram overlay. '
                        f'Bottom: detection fraction vs threshold (gold line = classification cutoff).'
                    )
                else:
                    st.info('Could not determine best-fit parameters.')
            except ImportError:
                st.info('wr_bias_simulation not available for model explorer.')
