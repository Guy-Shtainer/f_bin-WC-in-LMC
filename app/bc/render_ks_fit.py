"""bc.render_ks_fit — K-S fitting, 1D slices, 3D surface, and corner plot.

Hardcoded for K-S scoring (no likelihood branches).
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

from shared import PLOTLY_THEME, make_heatmap_fig

_make_heatmap_fig = make_heatmap_fig


# ─────────────────────────────────────────────────────────────────────────────
# Parabolic fitting utilities (copied from bc.fitting)
# ─────────────────────────────────────────────────────────────────────────────

def _parabolic_min_1d(t_grid, S_vals, mode='height', fraction=0.1,
                      height_factor=2.0, n_neighbors=2):
    """Find sub-grid minimum via 1D parabolic fit around grid minimum.

    Parameters
    ----------
    mode : 'height', 'range', or 'neighborhood'
        'height': include points where S < S_min * height_factor
        'range': include points within fraction * total_range of minimum
        'neighborhood': include +/-n_neighbors points around the minimum
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
    where coeffs = (a, b, c, d, e, f) for S = ax^2 + by^2 + cxy + dx + ey + f
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
    # Check Hessian is positive definite -> true minimum
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

    Fits S = a*x^2 + b*y^2 + c*z^2 + d*xy + e*xz + f*yz + g*x + h*y + i*z + j
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

    # Select fitting region: points within height_factor * S_min
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

    # Design matrix: [x^2, y^2, z^2, xy, xz, yz, x, y, z, 1]
    A = np.column_stack([xf**2, yf**2, zf**2, xf*yf, xf*zf, yf*zf,
                         xf, yf, zf, np.ones_like(xf)])
    coeffs, _, _, _ = np.linalg.lstsq(A, sf, rcond=None)
    a, b, c, d_xy, e_xz, f_yz, g, h, i_c, j = coeffs

    # Solve grad S = 0: Hessian/2 * [x, y, z]^T = -[g, h, i]^T
    M = np.array([[2*a, d_xy, e_xz],
                   [d_xy, 2*b, f_yz],
                   [e_xz, f_yz, 2*c]])
    # Check Hessian is positive definite (all eigenvalues > 0) -> true minimum
    eigvals = np.linalg.eigvalsh(M)
    if not np.all(eigvals > 0):
        # Not a minimum (saddle point or maximum) -> fall back to grid minimum
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


# ─────────────────────────────────────────────────────────────────────────────
# 1D slice plot (copied from bc.fitting)
# ─────────────────────────────────────────────────────────────────────────────

def _render_ks_1d_plot(col, t_grid, S_grid, label, best_t, best_S,
                       coeffs, fit_range, caption_text, height=300,
                       log_transform=False):
    """Render a single 1D slice plot with grid points + parabolic fit."""
    _theme = PLOTLY_THEME

    def _disp(arr):
        if log_transform:
            return np.log10(np.where(arr > 0, arr, np.nan))
        return arr

    _y_title = 'log10(K-S D)' if log_transform else 'K-S D-statistic'

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
# Corner plot helpers (copied from bc.corner_plots)
# ─────────────────────────────────────────────────────────────────────────────

def _method_best_and_hdi(
    p_nd: np.ndarray, grids: list, grid_names: list,
    is_likelihood: bool = False,
) -> dict | None:
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


def _add_1d_posterior(fig, row, col, grid, post_1d, hdi_tuple, color='#4A90D9'):
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
            fill='toself', fillcolor='rgba(74,144,217,0.3)',
            line=dict(width=0), showlegend=False,
        ), row=row, col=col)

    fig.add_vline(x=mode_val, line_dash='dash',
                  line_color='#E25A53', line_width=1.5,
                  row=row, col=col)


def _add_2d_heatmap(fig, row, col, x_grid, y_grid, z_2d, best_x, best_y, pal):
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
                          labelfont=dict(size=8, color=pal['contour_label'])),
            ncontours=2, contours_start=l95, contours_end=l68,
            line=dict(color=pal['contour_color'], width=1.5, dash='dot'),
            showscale=False, hoverinfo='skip',
        ), row=row, col=col)

    # Best-fit star
    fig.add_trace(go.Scatter(
        x=[best_x], y=[best_y], mode='markers',
        marker=dict(symbol='star', size=10, color='#DAA520',
                    line=dict(color='black', width=1)),
        showlegend=False,
    ), row=row, col=col)


def _render_ks_corner_plot(p_nd, fbin_g, x_g, x_name, x_display_label,
                           display_name, ndim_mode,
                           result, prefix, pal, use_cw=True):
    """Render N-parameter corner plot (2x2 or 3x3) for K-S p-values.

    Returns info dict from _method_best_and_hdi or None.
    """
    st.divider()
    with st.expander(f'Corner Plot -- {display_name}', expanded=False):
        # Build grids/names matching p_nd dimensions
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
            # cadence modes -- build dynamically from scanned axes
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
                                     is_likelihood=False)
        if _info is None:
            st.info('No valid data for corner plot.')
            return _info

        _hdi = _info['hdi']
        _bv = _info['best_vals']

        # Determine which axes to show: all scanned grids with >1 value
        show_axes = []
        show_axes.append((x_name, x_g, x_display_label))
        show_axes.append(('fbin', fbin_g, 'f_bin'))
        if 'sigma' in _all_names and x_name != 'sigma':
            _sig_idx = _all_names.index('sigma')
            if _all_grids[_sig_idx].size > 1:
                show_axes.append(('sigma', _all_grids[_sig_idx], 'sigma_single (km/s)'))
        if 'logPmax' in _all_names:
            _lp_idx = _all_names.index('logPmax')
            if _all_grids[_lp_idx].size > 1:
                show_axes.append(('logPmax', _all_grids[_lp_idx], 'log10(P_max / days)'))

        n_params = len(show_axes)
        fig_c = make_subplots(
            rows=n_params, cols=n_params,
            horizontal_spacing=0.06, vertical_spacing=0.06,
        )

        # For each diagonal: 1D posterior
        for i, (name_i, grid_i, label_i) in enumerate(show_axes):
            ax_idx = _all_names.index(name_i)
            sum_axes = tuple(j for j in range(p_nd.ndim) if j != ax_idx)
            post_1d = np.nansum(p_nd, axis=sum_axes) if sum_axes else p_nd.copy()
            hdi_i = _hdi.get(name_i, (0, 0, 0))
            _add_1d_posterior(fig_c, row=i + 1, col=i + 1,
                              grid=grid_i, post_1d=post_1d, hdi_tuple=hdi_i)

        # For each lower-triangle cell: 2D marginalized heatmap
        for j in range(n_params):
            for i in range(j):
                name_row, grid_row, label_row = show_axes[j]
                name_col, grid_col, label_col = show_axes[i]
                ax_row = _all_names.index(name_row)
                ax_col = _all_names.index(name_col)
                keep = sorted([ax_col, ax_row])
                sum_2d = tuple(k for k in range(p_nd.ndim) if k not in keep)
                p2d = np.nansum(p_nd, axis=sum_2d) if sum_2d else p_nd.copy()
                # Orient: rows=col_axis, cols=row_axis (x=col_grid, y=row_grid)
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

        # Axis labels: bottom row gets x-labels, left column gets y-labels
        for i, (_, _, label_i) in enumerate(show_axes):
            fig_c.update_xaxes(title_text=label_i, row=n_params, col=i + 1)
            if i > 0:
                fig_c.update_yaxes(title_text=show_axes[i][2], row=i + 1, col=1)

        fig_c.update_layout(**{
            **PLOTLY_THEME,
            'height': 350 * n_params // 2 + 150,
            'showlegend': False,
            'margin': dict(l=60, r=20, t=30, b=60),
        })
        st.plotly_chart(fig_c, use_container_width=True,
                        key=f'{prefix}_ks_corner')
        _param_list = ' x '.join(lbl for _, _, lbl in show_axes)
        st.caption(
            f'{n_params}-parameter corner plot for {display_name} ({_param_list}). '
            f'Diagonal: 1D posteriors with 68% HDI (blue shading) and mode (red dashed). '
            f'Off-diagonal: 2D marginalized heatmap{"s" if n_params > 2 else ""} '
            f'with 68%/95% contours and best fit (gold star).'
        )

    return _info
