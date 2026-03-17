"""bc.analysis — Parabolic fitting, multi-method summary, CvM analysis."""
from __future__ import annotations

import json
import os
import sys

import numpy as np
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

_best_point = find_best_grid_point
_make_heatmap_fig = make_heatmap_fig

def _parabolic_min_1d(t_grid, S_vals, mode='height', fraction=0.1,
                      height_factor=2.0, n_neighbors=2):
    """Find sub-grid minimum via 1D parabolic fit around grid minimum.

    Parameters
    ----------
    mode : 'height', 'range', or 'neighborhood'
        'height': include points where S < S_min * height_factor
        'range': include points within fraction * total_range of minimum
        'neighborhood': include ±n_neighbors points around the minimum
    Returns (best_t, best_S, coeffs, t_fit_range)
    """
    finite = np.isfinite(S_vals)
    if finite.sum() == 0:
        return None, None, None, None
    if finite.sum() < 3:
        i_min = int(np.nanargmin(S_vals))
        return float(t_grid[i_min]), float(S_vals[i_min]), None, None

    i_min = int(np.nanargmin(S_vals))
    S_min = float(S_vals[i_min])
    t_min = float(t_grid[i_min])

    if mode == 'height':
        sel = finite & (S_vals <= S_min * max(height_factor, 1.01))
    elif mode == 'neighborhood':
        lo = max(0, i_min - n_neighbors)
        hi = min(len(t_grid), i_min + n_neighbors + 1)
        sel = np.zeros_like(finite)
        sel[lo:hi] = finite[lo:hi]
    else:
        t_range = (t_grid[-1] - t_grid[0]) * fraction / 2
        sel = finite & (np.abs(t_grid - t_min) <= t_range)

    if sel.sum() < 3:
        return t_min, S_min, None, None

    t_sel = t_grid[sel]
    S_sel = S_vals[sel]
    coeffs = np.polyfit(t_sel, S_sel, 2)
    a, b, c = coeffs

    if a <= 0:  # not a minimum (concave)
        return t_min, S_min, coeffs, (t_sel.min(), t_sel.max())

    best_t = float(-b / (2 * a))
    best_S = float(a * best_t**2 + b * best_t + c)
    return best_t, best_S, coeffs, (float(t_sel.min()), float(t_sel.max()))


def _parabolic_min_2d(x_grid, y_grid, S_2d, mode='height',
                      fraction_x=0.1, fraction_y=0.1,
                      height_factor=2.0,
                      n_neighbors_x=2, n_neighbors_y=2):
    """Find sub-grid minimum via 2D parabolic (quadratic) fit.

    Returns (best_x, best_y, best_S, coeffs, fit_bounds)
    where coeffs = (a, b, c, d, e, f) for S = ax² + by² + cxy + dx + ey + f
    and fit_bounds = (x_sel_min, x_sel_max, y_sel_min, y_sel_max).
    """
    _empty = (None, None, None, None, None)
    finite = np.isfinite(S_2d)
    if finite.sum() == 0:
        return _empty
    if finite.sum() < 6:
        idx = np.unravel_index(np.nanargmin(S_2d), S_2d.shape)
        return float(x_grid[idx[0]]), float(y_grid[idx[1]]), float(S_2d[idx]), None, None

    idx = np.unravel_index(np.nanargmin(S_2d), S_2d.shape)
    S_min = float(S_2d[idx])
    x_min, y_min = float(x_grid[idx[0]]), float(y_grid[idx[1]])

    xs, ys = np.meshgrid(x_grid, y_grid, indexing='ij')
    xf, yf, zf = xs.ravel(), ys.ravel(), S_2d.ravel()
    fin = np.isfinite(zf)

    if mode == 'height':
        sel = fin & (zf <= S_min * max(height_factor, 1.01))
    elif mode == 'neighborhood':
        ix_min, iy_min = idx
        x_lo = max(0, ix_min - n_neighbors_x)
        x_hi = min(len(x_grid), ix_min + n_neighbors_x + 1)
        y_lo = max(0, iy_min - n_neighbors_y)
        y_hi = min(len(y_grid), iy_min + n_neighbors_y + 1)
        mask_2d = np.zeros_like(S_2d, dtype=bool)
        mask_2d[x_lo:x_hi, y_lo:y_hi] = True
        sel = fin & mask_2d.ravel()
    else:
        x_range = (x_grid[-1] - x_grid[0]) * fraction_x / 2
        y_range = (y_grid[-1] - y_grid[0]) * fraction_y / 2
        sel = fin & (np.abs(xf - x_min) <= x_range) & (np.abs(yf - y_min) <= y_range)

    if sel.sum() < 6:
        return x_min, y_min, S_min, None, None

    xf, yf, zf = xf[sel], yf[sel], zf[sel]
    fit_bounds = (float(xf.min()), float(xf.max()), float(yf.min()), float(yf.max()))

    A = np.column_stack([xf**2, yf**2, xf*yf, xf, yf, np.ones_like(xf)])
    coeffs, _, _, _ = np.linalg.lstsq(A, zf, rcond=None)
    a, b, c_xy, d, e, f = coeffs

    M = np.array([[2*a, c_xy], [c_xy, 2*b]])
    # Check Hessian is positive definite → true minimum
    eigvals = np.linalg.eigvalsh(M)
    if not np.all(eigvals > 0):
        return x_min, y_min, S_min, tuple(coeffs), fit_bounds
    rhs = np.array([-d, -e])
    try:
        sol = np.linalg.solve(M, rhs)
        best_x, best_y = float(sol[0]), float(sol[1])
        best_S = float(a*best_x**2 + b*best_y**2 + c_xy*best_x*best_y
                       + d*best_x + e*best_y + f)
        if best_S < 0 or best_S > S_min * 10:
            best_x, best_y, best_S = x_min, y_min, S_min
    except np.linalg.LinAlgError:
        best_x, best_y, best_S = x_min, y_min, S_min

    return best_x, best_y, best_S, tuple(coeffs), fit_bounds


def _parabolic_min_3d(x_grid, y_grid, z_grid, S_3d,
                      height_factor=2.0, n_neighbors=2):
    """Find sub-grid minimum via 3D quadratic fit over (x, y, z).

    Fits S = a·x² + b·y² + c·z² + d·xy + e·xz + f·yz + g·x + h·y + i·z + j
    (10 coefficients).

    Returns (best_x, best_y, best_z, best_S, coeffs_10, fit_bounds_6)
    where fit_bounds_6 = (x_min, x_max, y_min, y_max, z_min, z_max).
    """
    _empty_3d = (None, None, None, None, None, None)
    finite = np.isfinite(S_3d)
    if finite.sum() == 0:
        return _empty_3d
    if finite.sum() < 10:
        idx = np.unravel_index(np.nanargmin(S_3d), S_3d.shape)
        return (float(x_grid[idx[0]]), float(y_grid[idx[1]]), float(z_grid[idx[2]]),
                float(S_3d[idx]), None, None)

    idx = np.unravel_index(np.nanargmin(S_3d), S_3d.shape)
    S_min = float(S_3d[idx])
    x_min = float(x_grid[idx[0]])
    y_min = float(y_grid[idx[1]])
    z_min = float(z_grid[idx[2]])

    xs, ys, zs = np.meshgrid(x_grid, y_grid, z_grid, indexing='ij')
    xf, yf, zf, sf = xs.ravel(), ys.ravel(), zs.ravel(), S_3d.ravel()
    fin = np.isfinite(sf)

    # Select fitting region: points within height_factor × S_min
    sel = fin & (sf <= S_min * max(height_factor, 1.01))

    if sel.sum() < 10:
        # Fallback: neighborhood
        ix, iy, iz = idx
        n = n_neighbors
        mask_3d = np.zeros_like(S_3d, dtype=bool)
        mask_3d[max(0, ix-n):min(len(x_grid), ix+n+1),
                max(0, iy-n):min(len(y_grid), iy+n+1),
                max(0, iz-n):min(len(z_grid), iz+n+1)] = True
        sel = fin & mask_3d.ravel()

    if sel.sum() < 10:
        return x_min, y_min, z_min, S_min, None, None

    xf, yf, zf, sf = xf[sel], yf[sel], zf[sel], sf[sel]
    fit_bounds = (float(xf.min()), float(xf.max()),
                  float(yf.min()), float(yf.max()),
                  float(zf.min()), float(zf.max()))

    # Design matrix: [x², y², z², xy, xz, yz, x, y, z, 1]
    A = np.column_stack([xf**2, yf**2, zf**2, xf*yf, xf*zf, yf*zf,
                         xf, yf, zf, np.ones_like(xf)])
    coeffs, _, _, _ = np.linalg.lstsq(A, sf, rcond=None)
    a, b, c, d_xy, e_xz, f_yz, g, h, i_c, j = coeffs

    # Solve ∇S = 0: Hessian/2 · [x, y, z]ᵀ = -[g, h, i]ᵀ
    M = np.array([[2*a, d_xy, e_xz],
                   [d_xy, 2*b, f_yz],
                   [e_xz, f_yz, 2*c]])
    # Check Hessian is positive definite (all eigenvalues > 0) → true minimum
    eigvals = np.linalg.eigvalsh(M)
    if not np.all(eigvals > 0):
        # Not a minimum (saddle point or maximum) → fall back to grid minimum
        return x_min, y_min, z_min, S_min, tuple(coeffs), fit_bounds
    rhs = np.array([-g, -h, -i_c])
    try:
        sol = np.linalg.solve(M, rhs)
        bx, by, bz = float(sol[0]), float(sol[1]), float(sol[2])
        bS = float(a*bx**2 + b*by**2 + c*bz**2 + d_xy*bx*by + e_xz*bx*bz
                    + f_yz*by*bz + g*bx + h*by + i_c*bz + j)
        if bS < 0 or bS > S_min * 10:
            bx, by, bz, bS = x_min, y_min, z_min, S_min
    except np.linalg.LinAlgError:
        bx, by, bz, bS = x_min, y_min, z_min, S_min

    return bx, by, bz, bS, tuple(coeffs), fit_bounds


def _eval_3d_quadratic(coeffs_10, x, y, z):
    """Evaluate 3D quadratic at given coordinates."""
    a, b, c, d, e, f, g, h, i, j = coeffs_10
    return (a*x**2 + b*y**2 + c*z**2 + d*x*y + e*x*z + f*y*z
            + g*x + h*y + i*z + j)


def _render_cvm_1d_plot(col, t_grid, S_grid, label, best_t, best_S,
                        coeffs, fit_range, caption_text, height=300,
                        log_transform=False):
    """Render a single 1D slice plot with grid points + parabolic fit."""
    import plotly.graph_objects as go
    _theme = PLOTLY_THEME

    def _disp(arr):
        if log_transform:
            return np.log10(np.where(arr > 0, arr, np.nan))
        return arr

    _y_title = 'log₁₀(S)' if log_transform else 'S'

    fig = go.Figure()
    # All grid points
    fig.add_trace(go.Scatter(
        x=t_grid, y=_disp(S_grid), mode='markers',
        marker=dict(color='#4A90D9', size=6), name='Grid points'))

    # Parabolic fit curve (only in the fit region)
    if coeffs is not None and fit_range is not None:
        t_fine = np.linspace(fit_range[0], fit_range[1], 200)
        S_fit = np.polyval(coeffs, t_fine)
        fig.add_trace(go.Scatter(
            x=t_fine, y=_disp(S_fit), mode='lines',
            line=dict(color='#E25A53', width=2), name='Parabolic fit'))

    # Gold star at minimum
    fig.add_trace(go.Scatter(
        x=[best_t], y=[float(_disp(np.array([best_S]))[0])], mode='markers',
        marker=dict(symbol='star', size=14, color='#DAA520',
                    line=dict(width=1, color='black')),
        name='Minimum'))

    fig.update_layout(**{**_theme, 'title': dict(text=f'{_y_title} vs {label}'),
                         'xaxis': dict(title=label), 'yaxis': dict(title=_y_title),
                         'height': height, 'showlegend': False})
    col.plotly_chart(fig, use_container_width=True)
    col.caption(caption_text)


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
) -> None:
    """Render a comparison table of all scoring methods above the per-method details.

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

        score_val = f"{info['best_score']:.6f}"

        rows.append({
            'Method': mname,
            f'Best f_bin': fb_best,
            '68% HDI f_bin': fb_hdi,
            f'Best {x_label}': x_best,
            f'68% HDI {x_label}': x_hdi,
            'Score (best)': score_val,
        })

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

    # ── CDF comparison plot: observed vs best-fit model from each method ──
    obs_drv = result.get('obs_delta_rv')
    if obs_drv is not None and len(method_results) >= 2:
        try:
            from wr_bias_simulation import (
                binned_cdf, DEFAULT_DRV_BIN_EDGES,
                simulate_delta_rv_sample, SimulationConfig, BinaryParameterConfig,
            )
            _be = result.get('bin_edges')
            if _be is None:
                _be = DEFAULT_DRV_BIN_EDGES
            else:
                _be = np.asarray(_be)
            obs_drv = np.asarray(obs_drv)
            _n_obs_stars = len(obs_drv)
            obs_cdf = binned_cdf(obs_drv, _be)
            # Prepend (0, 0) so the CDF starts at the origin
            _obs_x = np.concatenate([[0.0], _be])
            _obs_y = np.concatenate([[0.0], obs_cdf])

            fig_cdf = go.Figure()
            fig_cdf.add_trace(go.Scatter(
                x=_obs_x, y=_obs_y,
                mode='lines', name='Observed',
                line=dict(color='black', width=2.5),
            ))

            _n_cdf_sets = 100  # Number of MC draws for confidence band

            # For each method, simulate at best-fit params and overlay CDF
            # with 16th/84th percentile confidence bands
            for mk, info in method_results.items():
                bv = info['best_vals']
                fb = bv.get('fbin', 0.5)
                pi_v = bv.get(x_name, 0.0)
                sig_v = bv.get('sigma', 5.0)
                _mcolor = next((c for k, _, _, _, c in SCORING_METHODS if k == mk), '#888888')
                _mname = next((n for k, n, _, _, _ in SCORING_METHODS if k == mk), mk)
                try:
                    # Simulate n_cdf_sets draws to get median + confidence band
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
                    _all_cdfs = np.array(_all_cdfs)  # (n_sets, n_bins)
                    _median_cdf = np.median(_all_cdfs, axis=0)
                    _lo_cdf = np.percentile(_all_cdfs, 16, axis=0)
                    _hi_cdf = np.percentile(_all_cdfs, 84, axis=0)

                    # Prepend (0, 0) to all CDF traces
                    _med_x = np.concatenate([[0.0], _be])
                    _med_y = np.concatenate([[0.0], _median_cdf])
                    _lo_y = np.concatenate([[0.0], _lo_cdf])
                    _hi_y = np.concatenate([[0.0], _hi_cdf])

                    _lbl = f'{_mname} (f_bin={fb:.3f}'
                    if x_name in bv:
                        _lbl += f', {x_label}={bv[x_name]:.2f}'
                    _lbl += ')'

                    # Confidence band (shaded region between 16th and 84th)
                    _fill_color = _hex_to_rgba(_mcolor, 0.2)
                    fig_cdf.add_trace(go.Scatter(
                        x=np.concatenate([_med_x, _med_x[::-1]]),
                        y=np.concatenate([_hi_y, _lo_y[::-1]]),
                        fill='toself', fillcolor=_fill_color,
                        line=dict(color='rgba(0,0,0,0)'),
                        showlegend=False,
                        hoverinfo='skip',
                    ))
                    # Median line
                    fig_cdf.add_trace(go.Scatter(
                        x=_med_x, y=_med_y,
                        mode='lines', name=_lbl,
                        line=dict(color=_mcolor, width=2, dash='dash'),
                    ))
                except Exception:
                    pass  # Skip if simulation fails for this method

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
        except ImportError:
            pass  # wr_bias_simulation not available



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
    """
    _is_likelihood = (method_key == 'likelihood')
    _theme = PLOTLY_THEME

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

    score_label = 'Likelihood' if _is_likelihood else 'p-value'

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


def _render_cvm_analysis(
    ks_D_2d: np.ndarray,
    ks_p_2d: np.ndarray,
    x_grid: np.ndarray,
    y_grid: np.ndarray,
    x_label: str = 'f_bin',
    y_label: str = 'π',
    sigma_grid: np.ndarray | None = None,
    ks_D_3d: np.ndarray | None = None,
    ks_p_3d: np.ndarray | None = None,
    ks_S_raw_2d: np.ndarray | None = None,
    height: int = 400,
    width: int | None = None,
    prefix: str = 'cvm',
    mode: str = 'cvm',
    obs_delta_rv: np.ndarray | None = None,
    likelihood_bin_edges: np.ndarray | None = None,
) -> None:
    """Render scoring analysis: heatmaps, grid exclusion, parabolic fit, 1D slices.

    Works for both CvM (mode='cvm') and Likelihood (mode='likelihood').
    Convention: x_grid = fbin (rows of z), y_grid = π/σ (cols of z).
    Display matches make_heatmap_fig: y-axis = f_bin, x-axis = π/σ.
    """
    import plotly.graph_objects as go

    _theme = PLOTLY_THEME
    _is_likelihood = (mode == 'likelihood')

    # Mode-dependent labels
    _stat_name = '-logL' if _is_likelihood else 'S'
    _score_name = 'Likelihood' if _is_likelihood else 'p-value'

    # ── 0. Log scale toggle ─────────────────────────────────────────────
    _log_label = f'Log₁₀({_stat_name}) scale'
    _use_log = st.checkbox(_log_label, value=False, key=f'{prefix}_log_s')

    def _to_display(S_arr):
        """Transform S values for display (log or linear)."""
        if _use_log:
            return np.log10(np.where(S_arr > 0, S_arr, np.nan))
        return S_arr

    _cbar_title = f'log₁₀({_stat_name})' if _use_log else _stat_name
    _z_hover = _cbar_title

    # ── 0b. Grid range exclusion (above heatmaps) ────────────────────────
    with st.expander('Grid Range Exclusion', expanded=False):
        _x_vals = [float(v) for v in x_grid]
        _y_vals = [float(v) for v in y_grid]

        # Range sliders
        _exc_c1, _exc_c2 = st.columns(2)
        if len(x_grid) >= 5:
            _x_min_exc = _exc_c1.slider(
                f'{x_label} min', min_value=_x_vals[0], max_value=_x_vals[-1],
                value=_x_vals[0], key=f'{prefix}_exc_xmin')
            _x_max_exc = _exc_c1.slider(
                f'{x_label} max', min_value=_x_vals[0], max_value=_x_vals[-1],
                value=_x_vals[-1], key=f'{prefix}_exc_xmax')
        else:
            _x_sel = _exc_c1.multiselect(
                f'{x_label} values to include', options=_x_vals,
                default=_x_vals, key=f'{prefix}_exc_xsel')
            _x_min_exc = min(_x_sel) if _x_sel else _x_vals[0]
            _x_max_exc = max(_x_sel) if _x_sel else _x_vals[-1]

        if len(y_grid) >= 5:
            _y_min_exc = _exc_c2.slider(
                f'{y_label} min', min_value=_y_vals[0], max_value=_y_vals[-1],
                value=_y_vals[0], key=f'{prefix}_exc_ymin')
            _y_max_exc = _exc_c2.slider(
                f'{y_label} max', min_value=_y_vals[0], max_value=_y_vals[-1],
                value=_y_vals[-1], key=f'{prefix}_exc_ymax')
        else:
            _y_sel = _exc_c2.multiselect(
                f'{y_label} values to include', options=_y_vals,
                default=_y_vals, key=f'{prefix}_exc_ysel')
            _y_min_exc = min(_y_sel) if _y_sel else _y_vals[0]
            _y_max_exc = max(_y_sel) if _y_sel else _y_vals[-1]

        # Per-axis value exclusion (separate dropdown per axis)
        st.markdown('**Exclude specific values per axis:**')
        _has_sigma = (sigma_grid is not None and len(sigma_grid) > 1)
        _n_exc_cols = 3 if _has_sigma else 2
        _exc_ax_cols = st.columns(_n_exc_cols)
        _exc_x_vals = _exc_ax_cols[0].multiselect(
            f'Exclude {x_label} values', options=_x_vals,
            default=[], key=f'{prefix}_exc_x_vals')
        _exc_y_vals = _exc_ax_cols[1].multiselect(
            f'Exclude {y_label} values', options=_y_vals,
            default=[], key=f'{prefix}_exc_y_vals')
        _exc_sig_vals = []
        if _has_sigma:
            _sig_vals_list = [float(v) for v in sigma_grid]
            _exc_sig_vals = _exc_ax_cols[2].multiselect(
                'Exclude σ_single values', options=_sig_vals_list,
                default=[], key=f'{prefix}_exc_sig_vals')

    # Build exclusion mask (True = EXCLUDED)
    if len(x_grid) >= 5:
        _x_exc = (x_grid < _x_min_exc) | (x_grid > _x_max_exc)
    else:
        _x_inc_set = set([float(v) for v in (_x_sel if '_x_sel' in dir() else _x_vals)])
        _x_exc = np.array([float(v) not in _x_inc_set for v in x_grid])
    if len(y_grid) >= 5:
        _y_exc = (y_grid < _y_min_exc) | (y_grid > _y_max_exc)
    else:
        _y_inc_set = set([float(v) for v in (_y_sel if '_y_sel' in dir() else _y_vals)])
        _y_exc = np.array([float(v) not in _y_inc_set for v in y_grid])

    # Per-axis value exclusion
    _exc_x_set = set(_exc_x_vals)
    _exc_y_set = set(_exc_y_vals)
    for ix, xv in enumerate(x_grid):
        if float(xv) in _exc_x_set:
            _x_exc[ix] = True
    for iy, yv in enumerate(y_grid):
        if float(yv) in _exc_y_set:
            _y_exc[iy] = True

    _exc_mask_2d = _x_exc[:, None] | _y_exc[None, :]

    _n_excluded = int(_exc_mask_2d.sum())
    if _n_excluded > 0:
        st.info(f'Excluding **{_n_excluded}** / {_exc_mask_2d.size} grid points from fitting')

    # Apply exclusion — working copies for fitting AND display
    # For likelihood mode, logL_raw is negative (higher = better), so negate
    # to get -logL (positive, lower = better) — consistent with CvM minimization.
    if _is_likelihood:
        _S_work = -ks_D_2d.copy().astype(float)
    else:
        _S_work = ks_D_2d.copy().astype(float)
    _S_work[_exc_mask_2d] = np.nan
    _p_work = ks_p_2d.copy().astype(float)
    _p_work[_exc_mask_2d] = np.nan

    # ── 1. Heatmaps stacked vertically (full-width) ───────────────
    _section_title = 'Likelihood Analysis' if _is_likelihood else 'CvM S-score Analysis'
    st.markdown(f'#### {_section_title}')

    # Raw statistic (uses _S_work so excluded points show as white)
    fig_raw = go.Figure(go.Heatmap(
        z=_to_display(_S_work), x=y_grid, y=x_grid,
        colorscale='Viridis_r', colorbar=dict(title=_cbar_title),
        hovertemplate=f'{y_label}: %{{x:.3f}}<br>{x_label}: %{{y:.3f}}<br>{_z_hover}: %{{z:.2f}}<extra></extra>',
    ))
    _raw_title = f'{_cbar_title} (all models)' if _is_likelihood else f'Weighted {_cbar_title} (all models)'
    fig_raw.update_layout(**{**_theme, 'title': dict(text=_raw_title),
                             'xaxis': dict(title=y_label), 'yaxis': dict(title=x_label),
                             'height': height, 'width': width})
    st.plotly_chart(fig_raw, use_container_width=(width is None))
    _raw_caption = ('Lower -logL = better fit. All models shown.'
                    if _is_likelihood else 'Lower S = better fit. All models shown.')
    st.caption(_raw_caption)

    # Score-masked statistic
    S_masked = _S_work.copy()
    if _is_likelihood:
        # For likelihood: mask where L < 5% of max (implausible models)
        _L_max = np.nanmax(_p_work)
        p_mask = _p_work < (0.05 * _L_max) if _L_max > 0 else np.ones_like(_p_work, dtype=bool)
    else:
        p_mask = (_p_work < 0.05) | (_p_work > 0.95)
    S_masked[p_mask] = np.nan
    _masked_title = (f'{_cbar_title} (L ≥ 5% of max)' if _is_likelihood
                     else f'{_cbar_title} (p ∈ [0.05, 0.95])')
    fig_masked = go.Figure(go.Heatmap(
        z=_to_display(S_masked), x=y_grid, y=x_grid,
        colorscale='Viridis_r', colorbar=dict(title=_cbar_title),
        hovertemplate=f'{y_label}: %{{x:.3f}}<br>{x_label}: %{{y:.3f}}<br>{_z_hover}: %{{z:.2f}}<extra></extra>',
    ))
    fig_masked.update_layout(**{**_theme, 'title': dict(text=_masked_title),
                                'xaxis': dict(title=y_label), 'yaxis': dict(title=x_label),
                                'height': height, 'width': width})
    _masked_slot = st.empty()  # placeholder — will re-render after adding gold star
    _masked_slot.plotly_chart(fig_masked, use_container_width=(width is None))
    _masked_caption = ('White = models with L < 5% of max (implausible).'
                       if _is_likelihood
                       else 'White = models outside p ∈ [0.05, 0.95] (implausible).')
    st.caption(_masked_caption)

    # Score heatmap — standard style (uses _p_work for exclusion)
    _score_title = 'Normalized Likelihood' if _is_likelihood else 'Empirical p-value'
    _scoring_lbl = 'L' if _is_likelihood else 'CvM'
    _fig_pval = _make_heatmap_fig(
        _p_work, x_grid, y_grid,
        title=_score_title,
        show_d=False, height=height, width=width,
        x_label=y_label, x_name=y_label,
        scoring_label=_scoring_lbl,
    )
    _pval_slot = st.empty()
    _pval_slot.plotly_chart(_fig_pval, use_container_width=(width is None))
    _score_caption = ('Higher = better fit. Normalized so max = 1.'
                      if _is_likelihood
                      else 'Fraction of simulated sets with S ≥ S_obs.')
    st.caption(_score_caption)

    # Binned bar chart (likelihood-specific: observed vs simulated bin counts)
    if _is_likelihood and obs_delta_rv is not None and likelihood_bin_edges is not None:
        _lk_edges = np.asarray(likelihood_bin_edges)
        _n_obs_bins = np.histogram(np.abs(obs_delta_rv), bins=_lk_edges)[0]
        _bin_labels = []
        for _bi in range(len(_lk_edges) - 1):
            lo = _lk_edges[_bi]
            hi = _lk_edges[_bi + 1]
            if np.isinf(hi):
                _bin_labels.append(f'[{lo:.0f}, ∞)')
            else:
                _bin_labels.append(f'[{lo:.0f}, {hi:.0f})')
        _fig_bar = go.Figure()
        _fig_bar.add_trace(go.Bar(
            x=_bin_labels, y=_n_obs_bins,
            name='Observed', marker_color='#4A90D9',
            text=_n_obs_bins, textposition='auto',
        ))
        _fig_bar.update_layout(**{**_theme,
            'title': dict(text='Observed ΔRV Bin Counts (Multinomial Likelihood)'),
            'xaxis': dict(title='ΔRV bin (km/s)'),
            'yaxis': dict(title='Count'),
            'height': 350})
        st.plotly_chart(_fig_bar, use_container_width=(width is None))
        st.caption('Multinomial likelihood compares these observed bin counts '
                   'to simulated bin probabilities at each grid point.')

    # S_raw (unweighted) heatmap — CvM only, cross-model comparable
    if not _is_likelihood and ks_S_raw_2d is not None and np.any(np.isfinite(ks_S_raw_2d)):
        _Sraw_work = ks_S_raw_2d
        fig_sraw = go.Figure(go.Heatmap(
            z=_to_display(_Sraw_work), x=y_grid, y=x_grid,
            colorscale='Viridis_r',
            colorbar=dict(title='log₁₀(S_raw)' if _use_log else 'S_raw'),
            hovertemplate=(f'{y_label}: %{{x:.3f}}<br>{x_label}: %{{y:.3f}}'
                           f'<br>S_raw: %{{z:.4f}}<extra></extra>'),
        ))
        fig_sraw.update_layout(**{**_theme,
            'title': dict(text='S_raw (unweighted, cross-model comparable)'),
            'xaxis': dict(title=y_label), 'yaxis': dict(title=x_label),
            'height': height, 'width': width})
        st.plotly_chart(fig_sraw, use_container_width=(width is None))
        st.caption('Lower S_raw = better fit. Directly comparable between Dsilva and Langer models.')

    # ── 2. Fit selection controls (per-axis) ─────────────────────────────
    _fc1, _fc2, _fc3 = st.columns([0.2, 0.4, 0.4])
    _fit_mode = _fc1.radio('Fit selection', ['Height-based', 'Range-based', 'Neighborhood'],
                           horizontal=True, key=f'{prefix}_fit_mode')
    _mode = ('height' if _fit_mode == 'Height-based'
             else 'neighborhood' if _fit_mode == 'Neighborhood'
             else 'range')

    # Defaults for unused params
    _h_factor = 2.0
    _h_factor_x = _h_factor_y = 2.0
    _frac_x = _frac_y = 0.1
    _nn_x = _nn_y = _nn_1d = 2

    if _mode == 'height':
        _h_factor = _fc2.number_input(
            '2D fit: S < S_min ×', min_value=1.1, max_value=1000.0, value=2.0,
            step=0.5, key=f'{prefix}_h_factor')
        _h1, _h2 = st.columns(2)
        _h_factor_x = _h1.number_input(
            f'{x_label} slice factor', min_value=1.1, max_value=1000.0,
            value=2.0, step=0.5, key=f'{prefix}_h_factor_x')
        _h_factor_y = _h2.number_input(
            f'{y_label} slice factor', min_value=1.1, max_value=1000.0,
            value=2.0, step=0.5, key=f'{prefix}_h_factor_y')
    elif _mode == 'neighborhood':
        _max_nn_x = max(1, len(x_grid) // 2)
        _max_nn_y = max(1, len(y_grid) // 2)
        _nn_x = _fc2.number_input(
            f'± {x_label} neighbors', min_value=1, max_value=_max_nn_x,
            value=min(2, _max_nn_x), step=1, key=f'{prefix}_nn_x')
        _nn_y = _fc3.number_input(
            f'± {y_label} neighbors', min_value=1, max_value=_max_nn_y,
            value=min(2, _max_nn_y), step=1, key=f'{prefix}_nn_y')
        _nn_1d = max(_nn_x, _nn_y)
    else:
        _frac_x = _fc2.number_input(
            f'{x_label} fraction', min_value=0.01, max_value=1.0, value=0.10,
            step=0.01, key=f'{prefix}_frac_x')
        _frac_y = _fc3.number_input(
            f'{y_label} fraction', min_value=0.01, max_value=1.0, value=0.10,
            step=0.01, key=f'{prefix}_frac_y')

    # ── 3. Parabolic interpolation ────────────────────────────────────────
    if not np.any(np.isfinite(_S_work)):
        st.warning('All grid points are excluded — cannot fit. Adjust exclusion settings.')
        # Store exclusion info before returning
        st.session_state[f'{prefix}_exc_mask_2d'] = _exc_mask_2d
        st.session_state[f'{prefix}_exc_x_mask_1d'] = _x_exc
        st.session_state[f'{prefix}_exc_y_mask_1d'] = _y_exc
        st.session_state[f'{prefix}_stored_exc_sig_vals'] = list(_exc_sig_vals) if _has_sigma else []
        st.session_state[f'{prefix}_exc_x_val_set'] = set(float(x_grid[i]) for i, v in enumerate(_x_exc) if v)
        st.session_state[f'{prefix}_exc_y_val_set'] = set(float(y_grid[i]) for i, v in enumerate(_y_exc) if v)
        return _exc_mask_2d

    best_x, best_y, best_S, _fit_coeffs, _fit_bounds = _parabolic_min_2d(
        x_grid, y_grid, _S_work,
        mode=_mode, fraction_x=_frac_x, fraction_y=_frac_y,
        height_factor=_h_factor,
        n_neighbors_x=_nn_x, n_neighbors_y=_nn_y)

    # Add gold star to masked heatmap (axes swapped: x=y_grid, y=x_grid)
    fig_masked.add_trace(go.Scatter(
        x=[best_y], y=[best_x], mode='markers',
        marker=dict(symbol='star', size=16, color='#DAA520',
                    line=dict(width=1, color='black')),
        name='Best fit (parabolic)',
        hovertemplate=(f'{x_label}={best_x:.4f}<br>{y_label}={best_y:.3f}'
                       f'<br>S={best_S:.2f}<extra></extra>'),
    ))
    _masked_slot.plotly_chart(fig_masked, use_container_width=(width is None))

    st.success(
        f'**Parabolic minimum:** {x_label} = {best_x:.4f}, '
        f'{y_label} = {best_y:.3f}, {_stat_name} = {best_S:.2f}')

    # ── 3b. 3D surface plot of the parabolic fit ─────────────────────────
    if _fit_coeffs is not None and _fit_bounds is not None:
        st.markdown('---')
        st.markdown('#### 3D Parabolic Surface')

        # Camera presets
        _cam_presets = {
            'Default': dict(eye=dict(x=1.5, y=1.5, z=1.2)),
            'Top-down': dict(eye=dict(x=0, y=0, z=2.5)),
            'Front': dict(eye=dict(x=0, y=2.5, z=0.5)),
            'Side': dict(eye=dict(x=2.5, y=0, z=0.5)),
        }
        _cam_choice = st.radio('Camera', list(_cam_presets.keys()),
                               horizontal=True, key=f'{prefix}_cam_3d')

        if True:  # block scope (replaces old expander indentation)
            a, b, c_xy, d, e, f = _fit_coeffs
            xb0, xb1, yb0, yb1 = _fit_bounds
            # Evaluate paraboloid on fine grid
            _n_surf = 50
            _x_surf = np.linspace(xb0, xb1, _n_surf)
            _y_surf = np.linspace(yb0, yb1, _n_surf)
            _Xs, _Ys = np.meshgrid(_x_surf, _y_surf, indexing='ij')
            _Zs = (a * _Xs**2 + b * _Ys**2 + c_xy * _Xs * _Ys
                    + d * _Xs + e * _Ys + f)

            # Grid data points in the fit region (use _S_work for exclusion)
            _xg, _yg = np.meshgrid(x_grid, y_grid, indexing='ij')
            _xgf, _ygf, _zgf = _xg.ravel(), _yg.ravel(), _S_work.ravel()
            _in_bounds = (np.isfinite(_zgf)
                          & (_xgf >= xb0) & (_xgf <= xb1)
                          & (_ygf >= yb0) & (_ygf <= yb1))

            # Display values: apply log transform if active
            _Zs_disp = _to_display(_Zs)
            _zgf_disp = _to_display(_zgf)
            _bestS_disp = float(_to_display(np.array([best_S]))[0])

            _3d_hover = (f'{y_label}: %{{x:.3f}}<br>{x_label}: %{{y:.3f}}<br>'
                         f'{_cbar_title}: %{{z:.2f}}')

            fig_3d = go.Figure()
            # Paraboloid surface (axes swapped for display: x=y_label, y=x_label)
            fig_3d.add_trace(go.Surface(
                x=_y_surf, y=_x_surf, z=_Zs_disp,
                colorscale='Viridis_r', opacity=0.7,
                colorbar=dict(title=f'{_cbar_title} (fit)', x=1.05),
                name='Parabolic fit',
                hovertemplate=_3d_hover + '<extra>Parabolic fit</extra>'))
            # Grid data points
            if _in_bounds.sum() > 0:
                fig_3d.add_trace(go.Scatter3d(
                    x=_ygf[_in_bounds], y=_xgf[_in_bounds], z=_zgf_disp[_in_bounds],
                    mode='markers',
                    marker=dict(size=3, color='#4A90D9'),
                    name='Grid points',
                    hovertemplate=_3d_hover + '<extra>Grid points</extra>'))
            # Gold star minimum
            fig_3d.add_trace(go.Scatter3d(
                x=[best_y], y=[best_x], z=[_bestS_disp],
                mode='markers',
                marker=dict(size=8, color='#DAA520', symbol='diamond'),
                name='Minimum',
                hovertemplate=_3d_hover + '<extra>Minimum</extra>'))
            fig_3d.update_layout(**{
                **_theme,
                'title': dict(text=f'2D Parabolic Fit ({_cbar_title})'),
                'scene': dict(
                    xaxis_title=y_label,
                    yaxis_title=x_label,
                    zaxis_title=_cbar_title,
                    dragmode='orbit',
                ),
                'scene_camera': _cam_presets[_cam_choice],
                'legend': dict(x=0.01, y=0.99, xanchor='left', yanchor='top',
                               bgcolor='rgba(0,0,0,0.5)', bordercolor='gray',
                               borderwidth=1, font=dict(size=11)),
                'height': 500,
            })
            st.plotly_chart(fig_3d, use_container_width=True,
                           key=f'{prefix}_3d_fbpi')

    # ── 3c. 3D quadratic fit + projected surfaces (3-axis grids) ────────
    _do_3d_fit = (sigma_grid is not None and ks_D_3d is not None
                  and len(sigma_grid) > 1)
    if _do_3d_fit:
        _cam = _cam_presets.get(
            _cam_choice if '_cam_choice' in dir() else 'Default',
            dict(eye=dict(x=1.5, y=1.5, z=1.2)))

        # Build working copy with exclusion applied
        # Negate for likelihood (same as 2D: minimize -logL)
        _S3d_work = (-ks_D_3d if _is_likelihood else ks_D_3d).copy().astype(float)
        for _is3 in range(_S3d_work.shape[0]):
            _S3d_work[_is3][_exc_mask_2d] = np.nan

        # Single 3D quadratic fit over (x=fbin, y=pi, z=sigma)
        # _S3d_work is (n_sig, n_fb, n_pi) → transpose to (n_fb, n_pi, n_sig)
        _S3d_for_fit = _S3d_work.transpose(1, 2, 0)
        _3d_bx, _3d_by, _3d_bz, _3d_bS, _3d_coeffs, _3d_bounds = \
            _parabolic_min_3d(x_grid, y_grid, sigma_grid, _S3d_for_fit,
                              height_factor=_h_factor, n_neighbors=max(_nn_x, _nn_y))

        st.markdown('---')
        st.markdown('#### 3D Quadratic Fit (all axes)')
        st.success(
            f'**3D minimum:** {x_label} = {_3d_bx:.4f}, '
            f'{y_label} = {_3d_by:.3f}, σ_single = {_3d_bz:.2f} km/s, '
            f'{_stat_name} = {_3d_bS:.2f}')

        if _3d_coeffs is not None and _3d_bounds is not None:
            xb0, xb1, yb0, yb1, zb0, zb1 = _3d_bounds
            _ns3 = 50

            # 3 projections: fix one variable at best, show surface for other two
            _proj_configs = [
                (x_grid, y_grid, x_label, y_label, 'σ_single',
                 _3d_bx, _3d_by, _3d_bz,
                 lambda xx, yy: _eval_3d_quadratic(_3d_coeffs, xx, yy, _3d_bz),
                 f'{x_label} × {y_label}  (σ={_3d_bz:.1f})',
                 xb0, xb1, yb0, yb1, _S3d_work[:, :, :]),
                (x_grid, sigma_grid, x_label, 'σ_single', y_label,
                 _3d_bx, _3d_bz, _3d_by,
                 lambda xx, zz: _eval_3d_quadratic(_3d_coeffs, xx, _3d_by, zz),
                 f'{x_label} × σ  (π={_3d_by:.3f})',
                 xb0, xb1, zb0, zb1, None),
                (y_grid, sigma_grid, y_label, 'σ_single', x_label,
                 _3d_by, _3d_bz, _3d_bx,
                 lambda yy, zz: _eval_3d_quadratic(_3d_coeffs, _3d_bx, yy, zz),
                 f'{y_label} × σ  (f_bin={_3d_bx:.4f})',
                 yb0, yb1, zb0, zb1, None),
            ]

            for _ip, (_gA, _gB, _lA, _lB, _lC, _bA, _bB, _bC, _eval_fn,
                       _ttl, _ab0, _ab1, _bb0, _bb1, _) in enumerate(_proj_configs):
                _xp = np.linspace(_ab0, _ab1, _ns3)
                _yp = np.linspace(_bb0, _bb1, _ns3)
                _Xp, _Yp = np.meshgrid(_xp, _yp, indexing='ij')
                _Zp = _eval_fn(_Xp, _Yp)

                # Grid data in fit region
                if _ip == 0:
                    # f_bin × pi: need best sigma slice from 3D data
                    _iz_best = int(np.argmin(np.abs(sigma_grid - _3d_bz)))
                    _sl_data = _S3d_work[_iz_best]  # (n_fb, n_pi)
                elif _ip == 1:
                    # f_bin × sigma: fix pi at best
                    _iy_best = int(np.argmin(np.abs(y_grid - _3d_by)))
                    _sl_data = _S3d_work[:, :, _iy_best].T  # (n_sig, n_fb) → (n_fb, n_sig)
                else:
                    # pi × sigma: fix fbin at best
                    _ix_best = int(np.argmin(np.abs(x_grid - _3d_bx)))
                    _sl_data = _S3d_work[:, _ix_best, :].T  # (n_sig, n_pi) → (n_pi, n_sig)

                _xg3, _yg3 = np.meshgrid(_gA, _gB, indexing='ij')
                _xgf3, _ygf3, _zgf3 = _xg3.ravel(), _yg3.ravel(), _sl_data.ravel()
                _ib3 = (np.isfinite(_zgf3)
                        & (_xgf3 >= _ab0) & (_xgf3 <= _ab1)
                        & (_ygf3 >= _bb0) & (_ygf3 <= _bb1))

                _Zpd = _to_display(_Zp)
                _zgf3d = _to_display(_zgf3)
                _bSd = float(_to_display(np.array([_3d_bS]))[0])

                _hov3 = (f'{_lB}: %{{x:.3f}}<br>{_lA}: %{{y:.3f}}<br>'
                         f'{_cbar_title}: %{{z:.2f}}')

                fig_proj = go.Figure()
                fig_proj.add_trace(go.Surface(
                    x=_yp, y=_xp, z=_Zpd,
                    colorscale='Viridis_r', opacity=0.7,
                    colorbar=dict(title=f'{_cbar_title} (3D fit)', x=1.05),
                    name='3D quadratic projection',
                    hovertemplate=_hov3 + '<extra>3D fit projection</extra>'))
                if _ib3.sum() > 0:
                    fig_proj.add_trace(go.Scatter3d(
                        x=_ygf3[_ib3], y=_xgf3[_ib3], z=_zgf3d[_ib3],
                        mode='markers',
                        marker=dict(size=3, color='#4A90D9'),
                        name='Grid points',
                        hovertemplate=_hov3 + '<extra>Grid points</extra>'))
                fig_proj.add_trace(go.Scatter3d(
                    x=[_bB], y=[_bA], z=[_bSd],
                    mode='markers',
                    marker=dict(size=8, color='#DAA520', symbol='diamond'),
                    name='3D Minimum',
                    hovertemplate=_hov3 + '<extra>3D Minimum</extra>'))
                fig_proj.update_layout(**{
                    **_theme,
                    'title': dict(text=f'3D Fit Projection: {_ttl}'),
                    'scene': dict(
                        xaxis_title=_lB,
                        yaxis_title=_lA,
                        zaxis_title=_cbar_title,
                        dragmode='orbit',
                    ),
                    'scene_camera': _cam,
                    'legend': dict(x=0.01, y=0.99, xanchor='left', yanchor='top',
                                   bgcolor='rgba(0,0,0,0.5)', bordercolor='gray',
                                   borderwidth=1, font=dict(size=11)),
                    'height': 500,
                })
                st.plotly_chart(fig_proj, use_container_width=True,
                               key=f'{prefix}_3d_proj_{_ip}')

    # ── 4. 1D slices (gold stars from unified 2D/3D fit, not independent 1D fits)
    i_x_best = int(np.argmin(np.abs(x_grid - best_x)))
    i_y_best = int(np.argmin(np.abs(y_grid - best_y)))

    # 1D slices through the best-fit point for visualization
    S_x_slice = _S_work[:, i_y_best]
    S_y_slice = _S_work[i_x_best, :]

    # Gold star positions come from the 2D/3D fit — we just need the parabolic
    # curve coefficients for drawing the fit line on the 1D plots
    _, _, cx, frx = _parabolic_min_1d(
        x_grid, S_x_slice, mode=_mode, fraction=_frac_x,
        height_factor=_h_factor_x, n_neighbors=_nn_x)
    _, _, cy, fry = _parabolic_min_1d(
        y_grid, S_y_slice, mode=_mode, fraction=_frac_y,
        height_factor=_h_factor_y, n_neighbors=_nn_y)
    # Override gold star position with the unified fit result
    bx = best_x
    bS_x = best_S if best_S is not None else float(np.nanmin(S_x_slice))
    by = best_y
    bS_y = best_S if best_S is not None else float(np.nanmin(S_y_slice))

    # Check if we have a 3D grid (sigma scan)
    do_3d = (sigma_grid is not None and ks_D_3d is not None and len(sigma_grid) > 1)
    if do_3d:
        S_sig_slice = ks_D_3d[:, i_x_best, i_y_best]
        _, _, csig, frsig = _parabolic_min_1d(
            sigma_grid, S_sig_slice, mode=_mode, fraction=_frac_x,
            height_factor=_h_factor_x, n_neighbors=_nn_1d)
        # Use 3D fit result for sigma gold star if available
        if '_3d_bz' in dir() and _3d_bz is not None:
            bsig = _3d_bz
            bS_sig = _3d_bS if _3d_bS is not None else float(np.nanmin(S_sig_slice))
        else:
            bsig, bS_sig, _, _ = _parabolic_min_1d(
                sigma_grid, S_sig_slice, mode=_mode, fraction=_frac_x,
                height_factor=_h_factor_x, n_neighbors=_nn_1d)
        sc1, sc2, sc3 = st.columns(3)
        _render_cvm_1d_plot(sc1, x_grid, S_x_slice, x_label, bx, bS_x, cx, frx,
                            f'Slice at {y_label}={y_grid[i_y_best]:.3f}', height=300,
                            log_transform=_use_log)
        _render_cvm_1d_plot(sc2, y_grid, S_y_slice, y_label, by, bS_y, cy, fry,
                            f'Slice at {x_label}={x_grid[i_x_best]:.4f}', height=300,
                            log_transform=_use_log)
        _render_cvm_1d_plot(sc3, sigma_grid, S_sig_slice, 'σ_single', bsig, bS_sig, csig, frsig,
                            f'Slice at {x_label}={x_grid[i_x_best]:.4f}, {y_label}={y_grid[i_y_best]:.3f}',
                            height=300, log_transform=_use_log)
        st.info(f'**σ_single (parabolic):** {bsig:.2f} km/s')
    else:
        bsig = None
        sc1, sc2 = st.columns(2)
        _render_cvm_1d_plot(sc1, x_grid, S_x_slice, x_label, bx, bS_x, cx, frx,
                            f'Slice at {y_label}={y_grid[i_y_best]:.3f}', height=300,
                            log_transform=_use_log)
        _render_cvm_1d_plot(sc2, y_grid, S_y_slice, y_label, by, bS_y, cy, fry,
                            f'Slice at {x_label}={x_grid[i_x_best]:.4f}', height=300,
                            log_transform=_use_log)

    # ── Store unified fit results for summary table + re-simulation ──
    _interp_result = {'f_bin': best_x, 'y_val': best_y, 'S': best_S}
    if do_3d and '_3d_bx' in dir() and _3d_bx is not None:
        _interp_result = {
            'f_bin': _3d_bx, 'pi': _3d_by, 'sigma': _3d_bz, 'S': _3d_bS
        }
    elif bsig is not None:
        _interp_result['sigma'] = bsig
    st.session_state[f'{prefix}_interp'] = _interp_result

    # Add green star for interpolated point on masked heatmap (distinct from gold grid-best)
    _interp_fb_val = _interp_result.get('f_bin', best_x)
    _interp_y_val = _interp_result.get('pi', _interp_result.get('sigma',
                     _interp_result.get('y_val', best_y)))
    if _interp_fb_val is not None and _interp_y_val is not None:
        _star_trace = go.Scatter(
            x=[_interp_y_val], y=[_interp_fb_val], mode='markers',
            marker=dict(symbol='star', size=14, color='#00CC66',
                        line=dict(width=1, color='black')),
            name='Interpolated',
            hovertemplate=(f'{x_label}={_interp_fb_val:.4f}<br>'
                           f'{y_label}={_interp_y_val:.3f}<extra></extra>'),
        )
        fig_masked.add_trace(_star_trace)
        _masked_slot.plotly_chart(fig_masked, use_container_width=(width is None))
        # Also add to p-value heatmap
        _fig_pval.add_trace(_star_trace)
        _pval_slot.plotly_chart(_fig_pval, use_container_width=(width is None))

    # Store exclusion masks in session_state for downstream sections
    st.session_state[f'{prefix}_exc_mask_2d'] = _exc_mask_2d
    st.session_state[f'{prefix}_exc_x_mask_1d'] = _x_exc      # 1D bool per x-axis point
    st.session_state[f'{prefix}_exc_y_mask_1d'] = _y_exc      # 1D bool per y-axis point
    st.session_state[f'{prefix}_stored_exc_sig_vals'] = list(_exc_sig_vals) if _has_sigma else []
    # Store excluded VALUE SETS so downstream sections with different grid sizes
    # can rebuild their own masks (cadence grids may differ from CvM grids)
    st.session_state[f'{prefix}_exc_x_val_set'] = set(float(x_grid[i]) for i, v in enumerate(_x_exc) if v)
    st.session_state[f'{prefix}_exc_y_val_set'] = set(float(y_grid[i]) for i, v in enumerate(_y_exc) if v)
    return _exc_mask_2d


