"""bc.fitting — Parabolic fitting utilities and 1D slice plots."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go

import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from shared import PLOTLY_THEME


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
    import streamlit as st
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
