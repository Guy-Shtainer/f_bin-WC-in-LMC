"""bc.render_lk_fit -- Likelihood fitting utilities and corner plot.

Currently a placeholder: the likelihood corner plot is rendered via the
shared bc.corner_plots module (called from render_lk.py).  This file
provides a ready-to-use render_lk_fitting() entry point for future
fitting features, plus an own copy of the corner plot code.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from shared import PLOTLY_THEME

_METHOD_COLOR = '#DAA520'
_DISPLAY_NAME = 'Likelihood'


# ---------------------------------------------------------------------------
# Parabolic fitting utilities (own copy for Likelihood, independent of K-S)
# ---------------------------------------------------------------------------

def _parabolic_min_1d(t_grid, S_vals, mode='height', fraction=0.1,
                      height_factor=2.0, n_neighbors=2, find_max=False):
    """Find sub-grid extremum via 1D parabolic fit.

    When find_max=True, finds the maximum (for logL); otherwise the minimum.
    """
    finite = np.isfinite(S_vals)
    if finite.sum() == 0:
        return None, None, None, None
    _argopt = np.nanargmax if find_max else np.nanargmin
    if finite.sum() < 3:
        i_opt = int(_argopt(S_vals))
        return float(t_grid[i_opt]), float(S_vals[i_opt]), None, None
    i_opt = int(_argopt(S_vals))
    S_opt = float(S_vals[i_opt])
    t_opt = float(t_grid[i_opt])
    if mode == 'height':
        if find_max:
            # logL is negative; select points within a factor of the best
            sel = finite & (S_vals >= S_opt * max(height_factor, 1.01))
        else:
            sel = finite & (S_vals <= S_opt * max(height_factor, 1.01))
    elif mode == 'neighborhood':
        lo = max(0, i_opt - n_neighbors)
        hi = min(len(t_grid), i_opt + n_neighbors + 1)
        sel = np.zeros_like(finite)
        sel[lo:hi] = finite[lo:hi]
    else:
        t_range = (t_grid[-1] - t_grid[0]) * fraction / 2
        sel = finite & (np.abs(t_grid - t_opt) <= t_range)
    if sel.sum() < 3:
        return t_opt, S_opt, None, None
    t_sel = t_grid[sel]
    S_sel = S_vals[sel]
    coeffs = np.polyfit(t_sel, S_sel, 2)
    a, b, c = coeffs
    # For max: need downward parabola (a < 0); for min: upward (a > 0)
    if find_max:
        if a >= 0:
            return t_opt, S_opt, coeffs, (t_sel.min(), t_sel.max())
    else:
        if a <= 0:
            return t_opt, S_opt, coeffs, (t_sel.min(), t_sel.max())
    best_t = float(-b / (2 * a))
    best_S = float(a * best_t**2 + b * best_t + c)
    return best_t, best_S, coeffs, (float(t_sel.min()), float(t_sel.max()))


def _parabolic_min_2d(x_grid, y_grid, S_2d, mode='height',
                      fraction_x=0.1, fraction_y=0.1,
                      height_factor=2.0,
                      n_neighbors_x=2, n_neighbors_y=2,
                      find_max=False):
    """Find sub-grid extremum via 2D parabolic (quadratic) fit.

    When find_max=True, finds the maximum (for logL); otherwise the minimum.
    """
    _empty = (None, None, None, None, None)
    finite = np.isfinite(S_2d)
    if finite.sum() == 0:
        return _empty
    _argopt = np.nanargmax if find_max else np.nanargmin
    if finite.sum() < 6:
        idx = np.unravel_index(_argopt(S_2d), S_2d.shape)
        return float(x_grid[idx[0]]), float(y_grid[idx[1]]), float(S_2d[idx]), None, None
    idx = np.unravel_index(_argopt(S_2d), S_2d.shape)
    S_opt = float(S_2d[idx])
    x_opt, y_opt = float(x_grid[idx[0]]), float(y_grid[idx[1]])
    xs, ys = np.meshgrid(x_grid, y_grid, indexing='ij')
    xf, yf, zf = xs.ravel(), ys.ravel(), S_2d.ravel()
    fin = np.isfinite(zf)
    if mode == 'height':
        if find_max:
            sel = fin & (zf >= S_opt * max(height_factor, 1.01))
        else:
            sel = fin & (zf <= S_opt * max(height_factor, 1.01))
    elif mode == 'neighborhood':
        ix_opt, iy_opt = idx
        mask_2d = np.zeros_like(S_2d, dtype=bool)
        mask_2d[max(0, ix_opt - n_neighbors_x):min(len(x_grid), ix_opt + n_neighbors_x + 1),
                max(0, iy_opt - n_neighbors_y):min(len(y_grid), iy_opt + n_neighbors_y + 1)] = True
        sel = fin & mask_2d.ravel()
    else:
        x_range = (x_grid[-1] - x_grid[0]) * fraction_x / 2
        y_range = (y_grid[-1] - y_grid[0]) * fraction_y / 2
        sel = fin & (np.abs(xf - x_opt) <= x_range) & (np.abs(yf - y_opt) <= y_range)
    if sel.sum() < 6:
        return x_opt, y_opt, S_opt, None, None
    xf, yf, zf = xf[sel], yf[sel], zf[sel]
    fit_bounds = (float(xf.min()), float(xf.max()), float(yf.min()), float(yf.max()))
    A = np.column_stack([xf**2, yf**2, xf*yf, xf, yf, np.ones_like(xf)])
    coeffs, _, _, _ = np.linalg.lstsq(A, zf, rcond=None)
    a, b, c_xy, d, e, f = coeffs
    M = np.array([[2*a, c_xy], [c_xy, 2*b]])
    eigvals = np.linalg.eigvalsh(M)
    # For max: need negative-definite Hessian; for min: positive-definite
    if find_max:
        if not np.all(eigvals < 0):
            return x_opt, y_opt, S_opt, tuple(coeffs), fit_bounds
    else:
        if not np.all(eigvals > 0):
            return x_opt, y_opt, S_opt, tuple(coeffs), fit_bounds
    rhs = np.array([-d, -e])
    try:
        sol = np.linalg.solve(M, rhs)
        best_x, best_y = float(sol[0]), float(sol[1])
        best_S = float(a*best_x**2 + b*best_y**2 + c_xy*best_x*best_y
                       + d*best_x + e*best_y + f)
        # Sanity: for max, result should be near S_opt (negative logL)
        if find_max:
            if best_S > 0 or best_S < S_opt * 10:
                best_x, best_y, best_S = x_opt, y_opt, S_opt
        else:
            if best_S < 0 or best_S > S_opt * 10:
                best_x, best_y, best_S = x_opt, y_opt, S_opt
    except np.linalg.LinAlgError:
        best_x, best_y, best_S = x_opt, y_opt, S_opt
    return best_x, best_y, best_S, tuple(coeffs), fit_bounds


def _parabolic_min_3d(x_grid, y_grid, z_grid, S_3d,
                      height_factor=2.0, n_neighbors=2, find_max=False):
    """Find sub-grid extremum via 3D quadratic fit over (x, y, z).

    When find_max=True, finds the maximum (for logL); otherwise the minimum.
    """
    _empty_3d = (None, None, None, None, None, None)
    finite = np.isfinite(S_3d)
    if finite.sum() == 0:
        return _empty_3d
    _argopt = np.nanargmax if find_max else np.nanargmin
    if finite.sum() < 10:
        idx = np.unravel_index(_argopt(S_3d), S_3d.shape)
        return (float(x_grid[idx[0]]), float(y_grid[idx[1]]), float(z_grid[idx[2]]),
                float(S_3d[idx]), None, None)
    idx = np.unravel_index(_argopt(S_3d), S_3d.shape)
    S_opt = float(S_3d[idx])
    x_opt, y_opt, z_opt = float(x_grid[idx[0]]), float(y_grid[idx[1]]), float(z_grid[idx[2]])
    xs, ys, zs = np.meshgrid(x_grid, y_grid, z_grid, indexing='ij')
    xf, yf, zf, sf = xs.ravel(), ys.ravel(), zs.ravel(), S_3d.ravel()
    fin = np.isfinite(sf)
    if find_max:
        sel = fin & (sf >= S_opt * max(height_factor, 1.01))
    else:
        sel = fin & (sf <= S_opt * max(height_factor, 1.01))
    if sel.sum() < 10:
        ix, iy, iz = idx
        n = n_neighbors
        mask_3d = np.zeros_like(S_3d, dtype=bool)
        mask_3d[max(0, ix-n):min(len(x_grid), ix+n+1),
                max(0, iy-n):min(len(y_grid), iy+n+1),
                max(0, iz-n):min(len(z_grid), iz+n+1)] = True
        sel = fin & mask_3d.ravel()
    if sel.sum() < 10:
        return x_opt, y_opt, z_opt, S_opt, None, None
    xf, yf, zf, sf = xf[sel], yf[sel], zf[sel], sf[sel]
    fit_bounds = (float(xf.min()), float(xf.max()),
                  float(yf.min()), float(yf.max()),
                  float(zf.min()), float(zf.max()))
    A = np.column_stack([xf**2, yf**2, zf**2, xf*yf, xf*zf, yf*zf,
                         xf, yf, zf, np.ones_like(xf)])
    coeffs, _, _, _ = np.linalg.lstsq(A, sf, rcond=None)
    a, b, c, d_xy, e_xz, f_yz, g, h, i_c, j = coeffs
    M = np.array([[2*a, d_xy, e_xz], [d_xy, 2*b, f_yz], [e_xz, f_yz, 2*c]])
    eigvals = np.linalg.eigvalsh(M)
    if find_max:
        if not np.all(eigvals < 0):
            return x_opt, y_opt, z_opt, S_opt, tuple(coeffs), fit_bounds
    else:
        if not np.all(eigvals > 0):
            return x_opt, y_opt, z_opt, S_opt, tuple(coeffs), fit_bounds
    rhs = np.array([-g, -h, -i_c])
    try:
        sol = np.linalg.solve(M, rhs)
        bx, by, bz = float(sol[0]), float(sol[1]), float(sol[2])
        bS = float(a*bx**2 + b*by**2 + c*bz**2 + d_xy*bx*by + e_xz*bx*bz
                    + f_yz*by*bz + g*bx + h*by + i_c*bz + j)
        if find_max:
            if bS > 0 or bS < S_opt * 10:
                bx, by, bz, bS = x_opt, y_opt, z_opt, S_opt
        else:
            if bS < 0 or bS > S_opt * 10:
                bx, by, bz, bS = x_opt, y_opt, z_opt, S_opt
    except np.linalg.LinAlgError:
        bx, by, bz, bS = x_opt, y_opt, z_opt, S_opt
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
    _theme = PLOTLY_THEME

    def _disp(arr):
        if log_transform:
            return np.log10(np.where(arr > 0, arr, np.nan))
        return arr

    _y_title = 'log10(-log L)' if log_transform else '-log L'
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=t_grid, y=_disp(S_grid), mode='markers',
        marker=dict(color='#DAA520', size=6), name='Grid points'))
    if coeffs is not None and fit_range is not None:
        t_fine = np.linspace(fit_range[0], fit_range[1], 200)
        S_fit = np.polyval(coeffs, t_fine)
        fig.add_trace(go.Scatter(
            x=t_fine, y=_disp(S_fit), mode='lines',
            line=dict(color='#E25A53', width=2), name='Parabolic fit'))
    fig.add_trace(go.Scatter(
        x=[best_t], y=[float(_disp(np.array([best_S]))[0])], mode='markers',
        marker=dict(symbol='star', size=14, color='#00CC66',
                    line=dict(width=1, color='black')),
        name='Minimum'))
    fig.update_layout(**{**_theme, 'title': dict(text=f'{_y_title} vs {label}'),
                         'xaxis': dict(title=label), 'yaxis': dict(title=_y_title),
                         'height': height, 'showlegend': False})
    col.plotly_chart(fig, use_container_width=True)
    col.caption(caption_text)


# ---------------------------------------------------------------------------
# Corner plot helpers (own copy, independent of bc.corner_plots)
# ---------------------------------------------------------------------------

def _squeeze_to_match(arr: np.ndarray, target_ndim: int) -> np.ndarray:
    """Squeeze array to target_ndim by removing size-1 axes first, then slicing."""
    while arr.ndim > target_ndim:
        squeezed = False
        for ax in range(arr.ndim):
            if arr.shape[ax] == 1:
                arr = np.squeeze(arr, axis=ax)
                squeezed = True
                break
        if not squeezed:
            arr = arr[0]
    return arr


def _add_1d_posterior(fig, row, col, grid, post_1d, hdi_tuple,
                      color=_METHOD_COLOR):
    """Add 1D posterior trace with HDI shading + mode line to a subplot cell."""
    mode_val, lo, hi = hdi_tuple
    norm = float(np.trapezoid(post_1d, grid))
    pn = post_1d / norm if norm > 0 else post_1d

    fig.add_trace(go.Scatter(
        x=grid, y=pn, mode='lines',
        line=dict(color=color, width=2), showlegend=False,
    ), row=row, col=col)

    # HDI shading
    mask = (grid >= lo) & (grid <= hi)
    if np.any(mask):
        xh = grid[mask]
        yh = pn[mask]
        fig.add_trace(go.Scatter(
            x=np.concatenate([xh, xh[::-1]]),
            y=np.concatenate([yh, np.zeros(len(yh))]),
            fill='toself', fillcolor='rgba(218,165,32,0.3)',
            line=dict(width=0), showlegend=False,
        ), row=row, col=col)

    fig.add_vline(x=mode_val, line_dash='dash',
                  line_color='#E25A53', line_width=1.5,
                  row=row, col=col)


def _add_2d_heatmap(fig, row, col, x_grid, y_grid, z_2d,
                     best_x, best_y, pal):
    """Add 2D marginalized heatmap with contours + best-fit star."""
    z_max = float(np.nanmax(z_2d)) if np.any(np.isfinite(z_2d)) else 1.0
    fig.add_trace(go.Heatmap(
        x=x_grid, y=y_grid, z=z_2d.T,
        colorscale='RdBu_r', zmin=0, zmax=z_max,
        zsmooth='best', showscale=False,
    ), row=row, col=col)

    # Contour overlay (68% / 95%)
    zf = z_2d.ravel()
    zp = zf[zf > 0]
    if len(zp) > 2:
        zs = np.sort(zp)[::-1]
        zcs = np.cumsum(zs)
        zcs = zcs / zcs[-1]
        i68 = np.searchsorted(zcs, 0.68)
        i95 = np.searchsorted(zcs, 0.95)
        l68 = float(zs[min(i68, len(zs) - 1)])
        l95 = float(zs[min(i95, len(zs) - 1)])
        fig.add_trace(go.Contour(
            x=x_grid, y=y_grid, z=z_2d.T,
            contours=dict(coloring='none', showlabels=True,
                          labelfont=dict(size=8,
                                        color=pal.get('contour_label', '#333'))),
            ncontours=2, contours_start=l95, contours_end=l68,
            line=dict(color=pal.get('contour_color', 'grey'),
                      width=1.5, dash='dot'),
            showscale=False, hoverinfo='skip',
        ), row=row, col=col)

    # Best-fit star
    fig.add_trace(go.Scatter(
        x=[best_x], y=[best_y], mode='markers',
        marker=dict(symbol='star', size=10, color=_METHOD_COLOR,
                    line=dict(color='black', width=1)),
        showlegend=False,
    ), row=row, col=col)


# WORKING — do not change this code (D14: Corner Plot)
def _render_lk_corner_plot(p_nd, fbin_g, x_g, x_name, x_display_label,
                           ndim_mode, result, prefix, pal, use_cw=True):
    """Render N-parameter corner plot for Likelihood scoring."""
    from bc.analysis import _method_best_and_hdi

    st.divider()
    with st.expander(f'Corner Plot -- {_DISPLAY_NAME}', expanded=False):
        # Build grids matching p_nd dimensions
        _sigma_g = np.asarray(result.get('sigma_grid', [0.0]))
        _logPmax_g = np.asarray(result.get('logPmax_grid', [0.0]))
        _has_lp = _logPmax_g.size > 1
        _has_sig = _sigma_g.size > 1

        if ndim_mode == 'dsilva':
            _all_grids = []
            _all_names = []
            if _has_lp:
                _all_grids.append(_logPmax_g)
                _all_names.append('logPmax')
            if _has_sig:
                _all_grids.append(_sigma_g)
                _all_names.append('sigma')
            _all_grids.extend([fbin_g, x_g])
            _all_names.extend(['fbin', x_name])
            p_nd = _squeeze_to_match(p_nd, len(_all_grids))
        elif ndim_mode == 'langer':
            _all_grids = []
            _all_names = []
            if _has_lp:
                _all_grids.append(_logPmax_g)
                _all_names.append('logPmax')
            _all_grids.extend([fbin_g, x_g])
            _all_names.extend(['fbin', x_name])
            p_nd = _squeeze_to_match(p_nd, len(_all_grids))
        else:
            _all_grids = []
            _all_names = []
            if _has_lp:
                _all_grids.append(_logPmax_g)
                _all_names.append('logPmax')
            if _has_sig:
                _all_grids.append(_sigma_g)
                _all_names.append('sigma')
            _all_grids.append(fbin_g)
            _all_names.append('fbin')
            if x_name == 'sigma' and 'sigma' in _all_names:
                _pi_g = np.asarray(result.get('pi_grid', [0.0]))
                if _pi_g.size > 1 and p_nd.shape[-1] == _pi_g.size:
                    _all_grids.append(_pi_g)
                    _all_names.append('pi')
            else:
                _all_grids.append(x_g)
                _all_names.append(x_name)
            p_nd = _squeeze_to_match(p_nd, len(_all_grids))

        _info = _method_best_and_hdi(p_nd, _all_grids, _all_names,
                                     is_likelihood=True)
        if _info is None:
            st.info('No valid data for corner plot.')
            return _info

        _hdi = _info['hdi']
        _bv = _info['best_vals']

        # Determine which axes to show
        show_axes = []
        show_axes.append((x_name, x_g, x_display_label))
        show_axes.append(('fbin', fbin_g, 'f_bin'))
        if 'sigma' in _all_names and x_name != 'sigma':
            _sig_idx = _all_names.index('sigma')
            if _all_grids[_sig_idx].size > 1:
                show_axes.append(('sigma', _all_grids[_sig_idx],
                                  'sigma_single (km/s)'))
        if 'logPmax' in _all_names:
            _lp_idx = _all_names.index('logPmax')
            if _all_grids[_lp_idx].size > 1:
                show_axes.append(('logPmax', _all_grids[_lp_idx],
                                  'log10(P_max / days)'))

        n_params = len(show_axes)
        fig_c = make_subplots(
            rows=n_params, cols=n_params,
            horizontal_spacing=0.06, vertical_spacing=0.06,
        )

        # Diagonal: 1D posteriors
        for i, (name_i, grid_i, _label_i) in enumerate(show_axes):
            ax_idx = _all_names.index(name_i)
            sum_axes = tuple(j for j in range(p_nd.ndim) if j != ax_idx)
            post_1d = (np.nansum(p_nd, axis=sum_axes)
                       if sum_axes else p_nd.copy())
            hdi_i = _hdi.get(name_i, (0, 0, 0))
            _add_1d_posterior(fig_c, row=i + 1, col=i + 1,
                              grid=grid_i, post_1d=post_1d,
                              hdi_tuple=hdi_i)

        # Lower-triangle: 2D marginalized heatmaps
        for j in range(n_params):
            for i in range(j):
                name_row, grid_row, _label_row = show_axes[j]
                name_col, grid_col, _label_col = show_axes[i]
                ax_row = _all_names.index(name_row)
                ax_col = _all_names.index(name_col)
                keep = sorted([ax_col, ax_row])
                sum_2d = tuple(k for k in range(p_nd.ndim) if k not in keep)
                p2d = (np.nansum(p_nd, axis=sum_2d)
                       if sum_2d else p_nd.copy())
                if ax_col == keep[0]:
                    z_2d = p2d
                else:
                    z_2d = p2d.T
                _add_2d_heatmap(fig_c, row=j + 1, col=i + 1,
                                x_grid=grid_col, y_grid=grid_row,
                                z_2d=z_2d,
                                best_x=_bv.get(name_col, 0),
                                best_y=_bv.get(name_row, 0),
                                pal=pal)

        # Hide upper-triangle cells
        for j in range(n_params):
            for i in range(j + 1, n_params):
                fig_c.update_xaxes(visible=False, row=j + 1, col=i + 1)
                fig_c.update_yaxes(visible=False, row=j + 1, col=i + 1)

        # Axis labels
        for i, (_, _, label_i) in enumerate(show_axes):
            fig_c.update_xaxes(title_text=label_i, row=n_params, col=i + 1)
            if i > 0:
                fig_c.update_yaxes(title_text=show_axes[i][2],
                                   row=i + 1, col=1)

        fig_c.update_layout(**{
            **PLOTLY_THEME,
            'height': 350 * n_params // 2 + 150,
            'showlegend': False,
            'margin': dict(l=60, r=20, t=30, b=60),
        })
        st.plotly_chart(fig_c, use_container_width=True,
                        key=f'{prefix}_{_DISPLAY_NAME.lower()}_corner')
        _param_list = ' x '.join(lbl for _, _, lbl in show_axes)
        st.caption(
            f'{n_params}-parameter corner plot for {_DISPLAY_NAME} '
            f'({_param_list}). '
            f'Diagonal: 1D posteriors with 68% HDI (gold shading) and '
            f'mode (red dashed). '
            f'Off-diagonal: 2D marginalized heatmap'
            f'{"s" if n_params > 2 else ""} '
            f'with 68%/95% contours and best fit (gold star). '
            f'Note: the gold star marks the joint maximum (argmax of the '
            f'full N-D likelihood), which may differ from the marginal '
            f'mode shown on each diagonal.'
        )

    return _info


# ---------------------------------------------------------------------------
# Public entry point (placeholder for future fitting features)
# ---------------------------------------------------------------------------

def render_lk_fitting(
    result: dict | None = None,
    prefix: str = 'lk_fit',
    **kwargs,
) -> None:
    """Placeholder for future likelihood fitting features.

    Currently does nothing.  Reserved for:
    - MCMC sampling around the likelihood surface
    - Profile likelihood confidence intervals
    - Bayesian evidence estimation
    """
    pass


# ---------------------------------------------------------------------------
# Likelihood CDF with bin overlay (E5)
# ---------------------------------------------------------------------------

def _render_likelihood_cdf(
    obs_delta_rv: np.ndarray,
    result: dict,
    bin_edges: np.ndarray,
    prefix: str,
    theme: dict,
) -> np.ndarray | None:
    """CDF comparison (observed vs simulated at best-fit) with optional bin overlay.

    Returns the simulated delta-RV array (for reuse in stats table), or None on failure.
    """
    from wr_bias_simulation import (
        DEFAULT_DRV_BIN_EDGES,
        simulate_delta_rv_sample, SimulationConfig, BinaryParameterConfig,
        multinomial_log_likelihood,
    )

    def _bcdf(data, edges):
        s = np.sort(data)
        return np.searchsorted(s, edges, side='right') / len(s)

    obs_drv = np.abs(np.asarray(obs_delta_rv))
    lk_edges = np.asarray(bin_edges)
    fine_edges = DEFAULT_DRV_BIN_EDGES

    _lk_p = result.get('likelihood')
    if _lk_p is None:
        st.info('No likelihood data available for CDF.')
        return None

    _lk_p = np.asarray(_lk_p, dtype=float)
    if not np.any(np.isfinite(_lk_p)):
        st.info('No finite likelihood values.')
        return None

    flat_best = int(np.nanargmax(_lk_p))
    best_idx = np.unravel_index(flat_best, _lk_p.shape)

    fbin_g = np.asarray(result.get('fbin_grid', [0.5]))
    x_g = np.asarray(result.get('pi_grid', result.get('sigma_grid', [0.0])))
    sigma_g = np.asarray(result.get('sigma_grid', [5.0]))

    if _lk_p.ndim == 4:
        fb = float(fbin_g[best_idx[2]])
        pi_v = float(x_g[best_idx[3]])
        sig_v = float(sigma_g[best_idx[1]])
    elif _lk_p.ndim == 3:
        fb = float(fbin_g[best_idx[1]])
        pi_v = float(x_g[best_idx[2]])
        sig_v = float(sigma_g[best_idx[0]])
    else:
        fb = float(fbin_g[best_idx[0]])
        pi_v = float(x_g[best_idx[1]])
        sig_v = float(sigma_g[0]) if sigma_g.size else 5.0

    n_obs_stars = len(obs_drv)
    n_cdf_sets = 100

    sim_cfg = SimulationConfig(
        n_stars=n_obs_stars,
        sigma_single=sig_v,
        sigma_measure=float(result.get('sigma_meas', 3.0)),
    )
    bin_cfg = BinaryParameterConfig()

    all_cdfs, all_sim_drv = [], []
    for seed_i in range(n_cdf_sets):
        rng = np.random.default_rng(42 + seed_i)
        sim_drv = simulate_delta_rv_sample(
            f_bin=fb, pi=pi_v,
            sim_cfg=sim_cfg, bin_cfg=bin_cfg, rng=rng)
        all_cdfs.append(_bcdf(sim_drv, fine_edges))
        all_sim_drv.append(sim_drv)

    all_cdfs_arr = np.array(all_cdfs)
    pooled_sim = np.concatenate(all_sim_drv)
    median_cdf = np.median(all_cdfs_arr, axis=0)
    lo_cdf = np.percentile(all_cdfs_arr, 16, axis=0)
    hi_cdf = np.percentile(all_cdfs_arr, 84, axis=0)
    obs_cdf = _bcdf(obs_drv, fine_edges)
    logL = multinomial_log_likelihood(obs_drv, pooled_sim, lk_edges)

    obs_x = np.concatenate([[0.0], fine_edges])
    obs_y = np.concatenate([[0.0], obs_cdf])
    med_x = np.concatenate([[0.0], fine_edges])
    med_y = np.concatenate([[0.0], median_cdf])
    lo_y = np.concatenate([[0.0], lo_cdf])
    hi_y = np.concatenate([[0.0], hi_cdf])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=obs_x, y=obs_y, mode='lines', name='Observed',
        line=dict(color='#4A90D9', width=2.5)))
    fig.add_trace(go.Scatter(
        x=np.concatenate([med_x, med_x[::-1]]),
        y=np.concatenate([hi_y, lo_y[::-1]]),
        fill='toself', fillcolor='rgba(218, 165, 32, 0.2)',
        line=dict(color='rgba(0,0,0,0)'),
        legendgroup='sim_lk', showlegend=False, hoverinfo='skip'))
    fig.add_trace(go.Scatter(
        x=med_x, y=med_y, mode='lines',
        name=f'Simulated (f_bin={fb:.3f}, pi={pi_v:.2f}, sigma={sig_v:.1f})',
        legendgroup='sim_lk',
        line=dict(color='#DAA520', width=2.5, dash='dash')))

    show_bins = st.checkbox('Show likelihood bins on CDF', value=False,
                            key=f'{prefix}_lk_cdf_show_bins')
    if show_bins:
        _colors = ['rgba(100,100,100,0.08)', 'rgba(100,100,100,0.15)']
        for bi in range(len(lk_edges) - 1):
            lo_e = lk_edges[bi]
            hi_e = min(lk_edges[bi + 1], fine_edges[-1] + 20)
            fig.add_vrect(x0=lo_e, x1=hi_e, fillcolor=_colors[bi % 2],
                          layer='below', line_width=0)
            fig.add_vline(x=lo_e, line=dict(color='grey', width=1, dash='dot'))
            mid = (lo_e + min(hi_e, fine_edges[-1])) / 2
            fig.add_annotation(x=mid, y=1.02, yref='paper',
                               text=f'Bin {bi+1}', showarrow=False,
                               font=dict(size=10, color='grey'))

    fig.update_layout(**{
        **theme,
        'title': dict(text='CDF Comparison -- Likelihood Best-Fit', font=dict(size=14)),
        'xaxis_title': 'DeltaRV (km/s)', 'yaxis_title': 'Cumulative Fraction',
        'height': 420, 'legend': dict(x=0.45, y=0.15),
        'annotations': fig.layout.annotations + (dict(
            x=0.98, y=0.95, xref='paper', yref='paper',
            text=f'ln L = {logL:.2f}', showarrow=False,
            font=dict(size=12), bgcolor='rgba(255,255,255,0.8)',
            borderpad=6, xanchor='right'),),
    })
    st.plotly_chart(fig, use_container_width=True, key=f'{prefix}_lk_cdf')
    st.caption(
        f'Observed DeltaRV CDF (solid blue) vs simulated at best-fit likelihood '
        f'parameters (dashed gold, median of {n_cdf_sets} draws). '
        f'Shaded band = 16th-84th percentile.')
    return pooled_sim


# ---------------------------------------------------------------------------
# Per-bin likelihood breakdown table (E6)
# ---------------------------------------------------------------------------

# WORKING — do not change this code (E6: Per-Bin Breakdown Table)
def _render_likelihood_stats_table(
    obs_delta_rv: np.ndarray,
    sim_delta_rv_pooled: np.ndarray,
    bin_edges: np.ndarray,
) -> None:
    """Per-bin breakdown table: n_obs, n_sim, p_i, contribution to ln L."""
    import pandas as pd
    obs_drv = np.abs(np.asarray(obs_delta_rv))
    sim_drv = np.asarray(sim_delta_rv_pooled)
    edges = np.asarray(bin_edges)
    n_obs = np.histogram(obs_drv, bins=edges)[0]
    n_sim = np.histogram(sim_drv, bins=edges)[0]
    total_sim = max(int(n_sim.sum()), 1)
    p_bins = n_sim.astype(float) / total_sim
    eps = 1.0 / max(sim_drv.size, 1)
    p_safe = np.maximum(p_bins, eps)
    contributions = n_obs * np.log(p_safe)
    rows = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        label = f'[{lo:.0f}, inf)' if np.isinf(hi) else f'[{lo:.0f}, {hi:.0f})'
        rows.append({
            'Bin': label, 'n_obs': int(n_obs[i]), 'n_sim': int(n_sim[i]),
            'p_i': f'{p_safe[i]:.4f}', 'ln(p_i)': f'{np.log(p_safe[i]):.3f}',
            'n_i * ln(p_i)': f'{contributions[i]:.3f}',
        })
    total_logL = float(np.sum(contributions))
    rows.append({
        'Bin': 'Total', 'n_obs': int(n_obs.sum()), 'n_sim': int(n_sim.sum()),
        'p_i': '--', 'ln(p_i)': '--', 'n_i * ln(p_i)': f'{total_logL:.3f}',
    })
    st.markdown('#### Per-Bin Likelihood Breakdown')
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(f'Observed counts (n_obs) vs simulated bin probabilities (p_i) at best-fit. '
               f'Total ln L = {total_logL:.3f}.')


# ---------------------------------------------------------------------------
# Likelihood explanation (E7)
# ---------------------------------------------------------------------------

# WORKING — do not change this code (E7: LaTeX Methodology Explainer)
def _render_likelihood_explanation(
    obs_delta_rv: np.ndarray,
    bin_edges: np.ndarray,
) -> None:
    """Expandable explanation of multinomial likelihood with worked example."""
    obs_drv = np.abs(np.asarray(obs_delta_rv))
    edges = np.asarray(bin_edges)
    n_obs = np.histogram(obs_drv, bins=edges)[0]
    with st.expander('How is the likelihood calculated?', expanded=False):
        st.markdown('##### 1. Raw Log-Likelihood')
        st.markdown(
            'The multinomial log-likelihood (Dsilva et al. 2023, S4.2) bins the '
            'observed DeltaRV values into **coarse categories** and compares the '
            'observed bin counts to the simulated bin probabilities:')
        st.latex(r'\ln \mathcal{L} = \sum_{i=1}^{k} n_i \cdot \ln(p_i)')
        st.markdown(
            'where **n_i** = number of observed stars in bin *i*, and '
            '**p_i** = fraction of simulated DeltaRV values falling in bin *i*.')
        st.markdown('**Worked example** (using your observed data):')
        bin_labels = []
        for i in range(len(edges) - 1):
            lo, hi = edges[i], edges[i + 1]
            bin_labels.append(f'[{lo:.0f}, inf)' if np.isinf(hi) else f'[{lo:.0f}, {hi:.0f})')
        example_p = np.array([0.60, 0.25, 0.10, 0.05])[:len(n_obs)]
        example_p = example_p / example_p.sum()
        ex_rows = []
        ex_total = 0.0
        for i in range(len(n_obs)):
            ni = int(n_obs[i])
            pi = example_p[i]
            contrib = ni * np.log(pi) if ni > 0 else 0.0
            ex_total += contrib
            ex_rows.append(f'| {bin_labels[i]} | {ni} | {pi:.2f} | {np.log(pi):.3f} | {contrib:.3f} |')
        header = '| Bin | n_i | p_i (example) | ln(p_i) | n_i * ln(p_i) |'
        sep = '|-----|-----|---------------|---------|---------------|'
        st.markdown('\n'.join([header, sep] + ex_rows))
        st.markdown(f'**Total: ln L = {ex_total:.3f}**')
        st.caption('These p_i values are illustrative. The actual p_i comes from '
                    "simulating at each grid point's (f_bin, pi, sigma) parameters.")
        st.markdown('##### 2. Normalization to [0, 1]')
        st.markdown(
            'The raw ln L is computed at **every grid point**. To compare them, we normalize:')
        st.latex(r'\mathcal{L}_{\mathrm{norm}} = \exp\!\bigl(\ln \mathcal{L} - \ln \mathcal{L}_{\max}\bigr)')
        st.markdown(
            "- Find the **maximum** ln L across the entire grid\n"
            "- Subtract it from every grid point's ln L, then exponentiate\n"
            '- Result: best-fit gets **L_norm = 1.0**, all others < 1')
        st.markdown('##### 3. Bad Example (uniform model)')
        st.markdown(
            'What if the model predicts **equal probability** for every bin? '
            'This is the worst-case scenario — a model that has no structure:')
        bad_p = np.ones(len(n_obs)) / len(n_obs)
        bad_rows = []
        bad_total = 0.0
        for i in range(len(n_obs)):
            ni = int(n_obs[i])
            pi = bad_p[i]
            contrib = ni * np.log(pi) if ni > 0 else 0.0
            bad_total += contrib
            bad_rows.append(f'| {bin_labels[i]} | {ni} | {pi:.2f} | {np.log(pi):.3f} | {contrib:.3f} |')
        st.markdown('\n'.join([header, sep] + bad_rows))
        st.markdown(f'**Total: ln L = {bad_total:.3f}**  (worse than the good example: {ex_total:.3f})')
        st.caption(
            'The uniform model penalizes bins where many stars are observed '
            'because p_i is small. A good model concentrates probability in '
            'bins that actually contain stars.')
        st.markdown('##### 4. Why Do Many Points Show L ~ 1?')
        st.markdown(
            f'With only **{len(n_obs)} coarse bins**, many parameter '
            'combinations produce nearly identical bin probabilities. '
            'The likelihood surface is "flat" — it lacks the discriminating '
            'power of the K-S method which uses fine 10 km/s bins.')
