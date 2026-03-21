"""bc.corner_plots — N-parameter corner plots for scoring methods."""
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


def _render_corner_plot(p_nd, fbin_g, x_g, x_name, x_display_label,
                        display_name, _is_likelihood, ndim_mode,
                        result, prefix, method_key, pal, use_cw=True):
    """Render N-parameter corner plot (2×2 or 3×3 depending on sigma grid)."""
    from bc.analysis import _method_best_and_hdi

    st.divider()
    with st.expander(f'Corner Plot — {display_name}', expanded=False):
        # Build grids/names matching p_nd dimensions
        # Build grids matching p_nd dimensions.
        # logPmax and sigma are "outer" axes prepended when scanned.
        _sigma_g = np.asarray(result.get('sigma_grid', [0.0]))
        _logPmax_g = np.asarray(result.get('logPmax_grid', [0.0]))
        _has_lp = _logPmax_g.size > 1
        _has_sig = _sigma_g.size > 1

        if ndim_mode == 'dsilva':
            # Dsilva: shape is [logPmax?, sigma?, fbin, pi]
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
            # Squeeze p_nd to match grid count — remove size-1 axes
            p_nd = _squeeze_to_match(p_nd, len(_all_grids))
        elif ndim_mode == 'langer':
            # Langer: shape is [logPmax?, fbin, sigma]
            _all_grids = []
            _all_names = []
            if _has_lp:
                _all_grids.append(_logPmax_g)
                _all_names.append('logPmax')
            _all_grids.extend([fbin_g, x_g])
            _all_names.extend(['fbin', x_name])
            p_nd = _squeeze_to_match(p_nd, len(_all_grids))
        else:
            # cadence modes — build dynamically from scanned axes
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
            # For cadence_langer x_name='sigma' but sigma is already added;
            # use pi_grid as last axis only if it has >1 value (not size-1)
            if x_name == 'sigma' and 'sigma' in _all_names:
                _pi_g = np.asarray(result.get('pi_grid', [0.0]))
                # Only include pi if it has >1 value AND matches array's last dim
                if _pi_g.size > 1 and p_nd.shape[-1] == _pi_g.size:
                    _all_grids.append(_pi_g)
                    _all_names.append('pi')
                # else: skip pi — degenerate or mismatched axis, squeeze it out
            else:
                _all_grids.append(x_g)
                _all_names.append(x_name)
            p_nd = _squeeze_to_match(p_nd, len(_all_grids))

        _info = _method_best_and_hdi(p_nd, _all_grids, _all_names,
                                     is_likelihood=_is_likelihood)
        if _info is None:
            st.info('No valid data for corner plot.')
            return _info

        _hdi = _info['hdi']
        _bv = _info['best_vals']

        # Determine which axes to show: all scanned grids with >1 value
        show_axes = []  # list of (name, grid, display_label)
        show_axes.append((x_name, x_g, x_display_label))
        show_axes.append(('fbin', fbin_g, 'f_bin'))
        if 'sigma' in _all_names and x_name != 'sigma':
            _sig_idx = _all_names.index('sigma')
            if _all_grids[_sig_idx].size > 1:
                show_axes.append(('sigma', _all_grids[_sig_idx], 'σ_single (km/s)'))
        if 'logPmax' in _all_names:
            _lp_idx = _all_names.index('logPmax')
            if _all_grids[_lp_idx].size > 1:
                show_axes.append(('logPmax', _all_grids[_lp_idx], 'log₁₀(P_max / days)'))

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
                        key=f'{prefix}_{method_key}_corner')
        _param_list = ' × '.join(lbl for _, _, lbl in show_axes)
        st.caption(
            f'{n_params}-parameter corner plot for {display_name} ({_param_list}). '
            f'Diagonal: 1D posteriors with 68% HDI (blue shading) and mode (red dashed). '
            f'Off-diagonal: 2D marginalized heatmap{"s" if n_params > 2 else ""} '
            f'with 68%/95% contours and best fit (gold star).'
        )

    return _info
