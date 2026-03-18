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

    # ── Per-method sigma slider (when sigma has >1 values) ─────────
    _sigma_g_sl = np.asarray(result.get('sigma_grid', []))
    _has_sig_slider = (_sigma_g_sl.size > 1 and p_nd.ndim >= 3
                       and ndim_mode not in ('langer', 'cadence_langer'))
    _user_sig_idx = None
    if _has_sig_slider:
        # Determine default: best sigma index from global argmax
        _tmp_best = np.unravel_index(int(np.nanargmax(p_nd)), p_nd.shape)
        if ndim_mode == 'dsilva':
            _default_sig = int(_tmp_best[1])  # [logPmax, sigma, fbin, pi]
        else:
            _default_sig = int(_tmp_best[0])  # [sigma, fbin, pi]
        _user_sig_idx = st.select_slider(
            f'σ_single slice ({display_name})',
            options=list(range(len(_sigma_g_sl))),
            format_func=lambda i: f'{_sigma_g_sl[i]:.1f} km/s',
            value=_default_sig,
            key=f'{prefix}_{method_key}_sig_slider',
        )

    # Slice down to 2D: [fbin, x]
    if _user_sig_idx is not None:
        # User-selected sigma slice overrides disp_outer_slices
        if ndim_mode == 'dsilva' and p_nd.ndim == 4:
            _lp_s = disp_outer_slices[0] if disp_outer_slices else 0
            p_2d = p_nd[_lp_s, _user_sig_idx]
            D_2d = D_nd[_lp_s, _user_sig_idx] if D_nd is not None else None
        else:
            p_2d = p_nd[_user_sig_idx]
            D_2d = D_nd[_user_sig_idx] if D_nd is not None else None
    elif disp_outer_slices is not None and p_nd.ndim > 2:
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
        # Extract sigma grid and full ND arrays for 3D fit passthrough
        _sigma_g_fit = np.asarray(result.get('sigma_grid', []))
        _full_D_3d = None
        _full_p_3d = None
        if _sigma_g_fit.size > 1:
            _dk_key = {'cvm': 'cvm_D', 'likelihood': 'logL_raw'}[method_key]
            _pk_key = {'cvm': 'cvm_p', 'likelihood': 'likelihood'}[method_key]
            _raw_D = _get_method_array(result, _dk_key)
            _raw_p = _get_method_array(result, _pk_key)
            if _raw_D is not None:
                # Handle Dsilva 4D: [logPmax, sigma, fbin, pi] → take logPmax slice
                if ndim_mode == 'dsilva' and _raw_D.ndim == 4:
                    _lp_idx = disp_outer_slices[0] if disp_outer_slices else 0
                    _full_D_3d = _raw_D[_lp_idx]  # → [sigma, fbin, pi]
                    _full_p_3d = _raw_p[_lp_idx] if _raw_p is not None else None
                elif _raw_D.ndim == 3:
                    # Cadence modes: already [sigma, fbin, pi]
                    _full_D_3d = _raw_D
                    _full_p_3d = _raw_p
        _render_cvm_analysis(
            D_2d if D_2d is not None else p_2d,
            p_2d,
            fbin_g, x_g,
            x_label='f_bin', y_label=x_label,
            sigma_grid=_sigma_g_fit if _sigma_g_fit.size > 1 else None,
            ks_D_3d=_full_D_3d,
            ks_p_3d=_full_p_3d,
            height=height, width=width,
            prefix=f'{prefix}_{method_key}_analysis',
            mode=_mode,
            obs_delta_rv=_obs_drv,
            likelihood_bin_edges=_lk_edges,
            result=result,
        )

    # ── Score vs σ_single (all methods with multiple σ values) ──
    _sigma_g = np.asarray(result.get('sigma_grid', []))
    if _sigma_g.size > 1:
        from bc.helpers import _make_max_pval_fig, _make_min_score_fig
        # Get full ND score array for this method
        _pk = next((pk for mk, _, pk, _, _ in SCORING_METHODS if mk == method_key), None)
        _full_arr = _get_method_array(result, _pk) if _pk else None
        if _full_arr is not None:
            # Compute best score per sigma (maximize for p-value/likelihood, minimize for D-stat)
            _is_cvm = (method_key == 'cvm')
            # For CvM: use D-statistic (lower=better); for others: use p/likelihood (higher=better)
            if _is_cvm:
                _dk = next((dk for mk, _, _, dk, _ in SCORING_METHODS if mk == 'cvm'), None)
                _d_arr = _get_method_array(result, _dk)
                _score_arr = _d_arr if _d_arr is not None else _full_arr
            else:
                _score_arr = _full_arr

            # Determine sigma axis and compute per-sigma score
            _per_sig = None
            if _score_arr.ndim == 4:
                # Dsilva 4D: [logPmax, sigma, fbin, pi]
                if _is_cvm:
                    _per_sig = np.nanmin(_score_arr, axis=(0, 2, 3))
                else:
                    _per_sig = np.nanmax(_score_arr, axis=(0, 2, 3))
            elif _score_arr.ndim == 3:
                # Cadence 3D: [sigma, fbin, pi]
                if _is_cvm:
                    _per_sig = np.nanmin(_score_arr, axis=(1, 2))
                else:
                    _per_sig = np.nanmax(_score_arr, axis=(1, 2))
            elif _score_arr.ndim == 2:
                # Langer 2D: [fbin, sigma]
                if _is_cvm:
                    _per_sig = np.nanmin(_score_arr, axis=0)
                else:
                    _per_sig = np.nanmax(_score_arr, axis=0)

            if _per_sig is not None and _per_sig.size == _sigma_g.size:
                st.divider()
                _mname_sig = next((n for mk, n, _, _, _ in SCORING_METHODS if mk == method_key), method_key)
                if _is_cvm:
                    _fig_sig = _make_min_score_fig(
                        _sigma_g, list(_per_sig), height=350,
                        x_label='σ_single (km/s)', stat_label=_mname_sig)
                else:
                    _fig_sig = _make_max_pval_fig(
                        _sigma_g, list(_per_sig), height=350,
                        x_label='σ_single (km/s)', stat_label=_mname_sig)
                st.plotly_chart(_fig_sig, use_container_width=use_cw,
                                key=f'{prefix}_{method_key}_sig_profile')

    # ── Corner Plot (N-param: fbin × x × sigma if available) ───────────
    from bc.corner_plots import _render_corner_plot
    _info = _render_corner_plot(
        p_nd, fbin_g, x_g, x_name, x_display_label,
        display_name, _is_likelihood, ndim_mode,
        result, prefix, method_key, pal, use_cw,
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

                # Get best-fit params as defaults for interactive sliders
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
                    _def_fb = float(_me_bv.get('fbin', 0.5))
                    _def_x = float(_me_bv.get(x_name, 0.0))
                    _def_sig = float(_me_bv.get('sigma', result.get('sigma_meas', 5.0)))

                    # Interactive parameter sliders
                    _me_cols = st.columns(3)
                    _me_fb = _me_cols[0].slider(
                        'f_bin', 0.0, 1.0, _def_fb, 0.01,
                        key=f'{prefix}_{method_key}_me_fb')
                    _x_lo_me = float(x_g[0]) if len(x_g) > 0 else -3.0
                    _x_hi_me = float(x_g[-1]) if len(x_g) > 0 else 3.0
                    _me_x = _me_cols[1].slider(
                        x_label, _x_lo_me, _x_hi_me, min(max(_def_x, _x_lo_me), _x_hi_me), 0.01,
                        key=f'{prefix}_{method_key}_me_x')
                    _sigma_g_me = np.asarray(result.get('sigma_grid', []))
                    if _sigma_g_me.size > 1:
                        _me_sig = _me_cols[2].slider(
                            'σ_single (km/s)',
                            float(_sigma_g_me[0]), float(_sigma_g_me[-1]),
                            min(max(_def_sig, float(_sigma_g_me[0])), float(_sigma_g_me[-1])),
                            0.1, key=f'{prefix}_{method_key}_me_sig')
                    else:
                        _me_sig = _def_sig

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
