"""bc.render_lk_scoring -- Likelihood scoring detail heatmaps.

Renders the Likelihood-specific scoring analysis: log toggle, grid exclusion,
scoring heatmaps (raw -logL, masked, normalized likelihood), likelihood CDF,
per-bin stats table, explanation, fit mode selector, parabolic fitting,
3D surface, 1D slices, and interpolated best-fit.

Self-contained: all needed code is copied here (no imports from
render_ks_scoring.py, analysis.py, or scoring_detail.py).
"""
from __future__ import annotations

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

from shared import PLOTLY_THEME, make_heatmap_fig

from bc.render_lk_fit import (
    _parabolic_min_1d, _parabolic_min_2d, _parabolic_min_3d,
    _eval_3d_quadratic, _render_cvm_1d_plot,
    _render_likelihood_cdf, _render_likelihood_stats_table,
    _render_likelihood_explanation,
)

_make_heatmap_fig = make_heatmap_fig

# Likelihood-specific constants
_STAT_NAME = '-log L'
_STAT_DISPLAY = 'Likelihood'
_SCORE_NAME = 'Normalized Likelihood'
_METHOD_COLOR = '#DAA520'


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_lk_scoring_detail(
    lk_D_2d: np.ndarray,
    lk_p_2d: np.ndarray,
    x_grid: np.ndarray,
    y_grid: np.ndarray,
    x_label: str = 'f_bin',
    y_label: str = 'pi',
    sigma_grid: np.ndarray | None = None,
    logPmax_grid: np.ndarray | None = None,
    lk_D_3d: np.ndarray | None = None,
    lk_p_3d: np.ndarray | None = None,
    height: int = 400,
    width: int | None = None,
    prefix: str = 'lk',
    obs_delta_rv: np.ndarray | None = None,
    likelihood_bin_edges: np.ndarray | None = None,
    result: dict | None = None,
) -> tuple:
    """Render Likelihood scoring detail.  Returns (fit_coeffs, fit_info).

    Convention: x_grid = fbin (rows of z), y_grid = pi/sigma (cols of z).
    Display matches make_heatmap_fig: y-axis = f_bin, x-axis = pi/sigma.
    """
    _theme = PLOTLY_THEME

    # -- D6: Log scale toggle --------------------------------------
    _log_label = f'Log10({_STAT_NAME}) scale'
    _use_log = st.checkbox(_log_label, value=False, key=f'{prefix}_log_s')

    def _to_display(S_arr):
        """Transform S values for display (log or linear)."""
        if _use_log:
            return np.log10(np.where(S_arr > 0, S_arr, np.nan))
        return S_arr

    _cbar_title = f'log10({_STAT_NAME})' if _use_log else _STAT_NAME
    _z_hover = _cbar_title

    # -- D7: Grid range exclusion (above heatmaps) ----------------
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

        # Per-axis value exclusion
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
        _exc_sig_vals: list = []
        if _has_sigma:
            _sig_vals_list = [float(v) for v in sigma_grid]
            _exc_sig_vals = _exc_ax_cols[2].multiselect(
                'Exclude sigma_single values', options=_sig_vals_list,
                default=[], key=f'{prefix}_exc_sig_vals')

    # Build exclusion mask (True = EXCLUDED)
    if len(x_grid) >= 5:
        _x_exc = (x_grid < _x_min_exc) | (x_grid > _x_max_exc)
    else:
        _x_inc_set = set(
            [float(v) for v in (_x_sel if '_x_sel' in dir() else _x_vals)]
        )
        _x_exc = np.array([float(v) not in _x_inc_set for v in x_grid])
    if len(y_grid) >= 5:
        _y_exc = (y_grid < _y_min_exc) | (y_grid > _y_max_exc)
    else:
        _y_inc_set = set(
            [float(v) for v in (_y_sel if '_y_sel' in dir() else _y_vals)]
        )
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
        st.info(
            f'Excluding **{_n_excluded}** / {_exc_mask_2d.size} '
            f'grid points from fitting'
        )

    # Apply exclusion -- working copies for fitting AND display
    # For likelihood: logL_raw is negative (higher = better), negate
    # to get -logL (positive, lower = better) -- consistent with minimization.
    _S_work = -lk_D_2d.copy().astype(float)
    _S_work[_exc_mask_2d] = np.nan
    _p_work = lk_p_2d.copy().astype(float)
    _p_work[_exc_mask_2d] = np.nan

    # -- D5a: Raw -logL heatmap (LEFT) + σ×logPmax max-L (RIGHT) ---
    st.markdown('#### Likelihood Analysis')

    _has_right_panel = (sigma_grid is not None and logPmax_grid is not None
                        and sigma_grid.size > 1 and logPmax_grid.size > 1
                        and lk_p_3d is not None)
    _has_1d_right = (not _has_right_panel
                     and ((sigma_grid is not None and sigma_grid.size > 1)
                          or (logPmax_grid is not None and logPmax_grid.size > 1))
                     and lk_p_3d is not None)

    if _has_right_panel or _has_1d_right:
        _d5_left, _d5_right = st.columns(2)
    else:
        _d5_left = st.container()

    with _d5_left:
        fig_raw = go.Figure(go.Heatmap(
            z=_to_display(_S_work), x=y_grid, y=x_grid,
            colorscale='Viridis_r', colorbar=dict(title=_cbar_title),
            hovertemplate=(
                f'{y_label}: %{{x:.3f}}<br>'
                f'{x_label}: %{{y:.3f}}<br>'
                f'{_z_hover}: %{{z:.2f}}<extra></extra>'
            ),
        ))
        _raw_title = f'{_STAT_DISPLAY} -- {_cbar_title} (f_bin × {y_label})'
        fig_raw.update_layout(**{
            **_theme,
            'title': dict(text=_raw_title),
            'xaxis': dict(title=y_label),
            'yaxis': dict(title=x_label),
            'height': height,
            'width': width,
        })
        st.plotly_chart(fig_raw, use_container_width=True)
        st.caption('Lower −log L = better fit. All models shown.')

    if _has_right_panel:
        with _d5_right:
            # 2D heatmap: max likelihood per (σ, logPmax)
            _lk_full = lk_p_3d
            if _lk_full.ndim == 4:
                _sig_lp_max = np.nanmax(_lk_full, axis=(2, 3))  # → [logPmax, sigma]
            elif _lk_full.ndim == 3:
                _sig_lp_max = np.nanmax(_lk_full, axis=2)
            else:
                _sig_lp_max = _lk_full
            _fig_right = _make_heatmap_fig(
                _sig_lp_max, logPmax_grid, sigma_grid,
                title='Max Likelihood (σ × logP_max)',
                show_d=False, height=height,
                x_label='σ_single (km/s)',
                y_label='log₁₀(P_max / days)',
                x_name='σ',
                scoring_label='Likelihood',
                colorbar_title_override='Max Likelihood',
            )
            st.plotly_chart(_fig_right, use_container_width=True,
                            key=f'{prefix}_d5a_sig_lp')
            st.caption('Max likelihood across f_bin × π at each (σ, logP_max).')
    elif _has_1d_right:
        with _d5_right:
            # 1D profile for whichever extra axis exists
            _lk_full = lk_p_3d
            if sigma_grid is not None and sigma_grid.size > 1:
                _ax_g = sigma_grid
                _ax_label = 'σ_single (km/s)'
                if _lk_full.ndim == 3:
                    _max_1d = [float(np.nanmax(_lk_full[i]))
                               if np.any(np.isfinite(_lk_full[i])) else 0.0
                               for i in range(_ax_g.size)]
                else:
                    _max_1d = [0.0] * _ax_g.size
            else:
                _ax_g = logPmax_grid
                _ax_label = 'logP_max'
                if _lk_full.ndim >= 3:
                    _max_1d = [float(np.nanmax(_lk_full[i]))
                               if np.any(np.isfinite(_lk_full[i])) else 0.0
                               for i in range(_ax_g.size)]
                else:
                    _max_1d = [0.0] * _ax_g.size
            from bc.helpers import _make_max_pval_fig as _mpf
            st.plotly_chart(
                _mpf(_ax_g, _max_1d, height=height,
                     x_label=_ax_label, stat_label='Likelihood'),
                use_container_width=True,
                key=f'{prefix}_d5a_1d_right')

    # -- D5b, D5c: REMOVED (user review 2026-03-23) ----------------

    # -- Likelihood CDF, per-bin stats, and explanation ------------
    if obs_delta_rv is not None and likelihood_bin_edges is not None and result is not None:
        _pooled_sim = _render_likelihood_cdf(
            obs_delta_rv, result, likelihood_bin_edges,
            prefix=prefix, theme=_theme,
        )
        if _pooled_sim is not None:
            _render_likelihood_stats_table(
                obs_delta_rv, _pooled_sim, likelihood_bin_edges,
            )
        _render_likelihood_explanation(obs_delta_rv, likelihood_bin_edges)

    # -- NO S_raw heatmap (K-S only) -------------------------------
    # Skipped intentionally for Likelihood.

    # -- Fit selection controls (per-axis) -------------------------
    _fc1, _fc2, _fc3 = st.columns([0.2, 0.4, 0.4])
    _fit_mode = _fc1.radio(
        'Fit selection',
        ['Height-based', 'Range-based', 'Neighborhood'],
        horizontal=True, key=f'{prefix}_fit_mode',
    )
    _mode = (
        'height' if _fit_mode == 'Height-based'
        else 'neighborhood' if _fit_mode == 'Neighborhood'
        else 'range'
    )

    # Defaults for unused params
    _h_factor = 2.0
    _h_factor_x = _h_factor_y = 2.0
    _frac_x = _frac_y = 0.1
    _nn_x = _nn_y = _nn_1d = 2

    if _mode == 'height':
        _h_factor = _fc2.number_input(
            '2D fit: S < S_min x', min_value=1.01, max_value=1000.0,
            value=2.0, step=0.5, key=f'{prefix}_h_factor')
        _h1, _h2 = st.columns(2)
        _h_factor_x = _h1.number_input(
            f'{x_label} slice factor', min_value=1.01, max_value=1000.0,
            value=2.0, step=0.5, key=f'{prefix}_h_factor_x')
        _h_factor_y = _h2.number_input(
            f'{y_label} slice factor', min_value=1.01, max_value=1000.0,
            value=2.0, step=0.5, key=f'{prefix}_h_factor_y')
    elif _mode == 'neighborhood':
        _max_nn_x = max(1, len(x_grid) // 2)
        _max_nn_y = max(1, len(y_grid) // 2)
        _nn_x = _fc2.number_input(
            f'+/- {x_label} neighbors', min_value=1,
            max_value=_max_nn_x,
            value=min(2, _max_nn_x), step=1,
            key=f'{prefix}_nn_x')
        _nn_y = _fc3.number_input(
            f'+/- {y_label} neighbors', min_value=1,
            max_value=_max_nn_y,
            value=min(2, _max_nn_y), step=1,
            key=f'{prefix}_nn_y')
        _nn_1d = max(_nn_x, _nn_y)
    else:
        _frac_x = _fc2.number_input(
            f'{x_label} fraction', min_value=0.01, max_value=1.0,
            value=0.10, step=0.01, key=f'{prefix}_frac_x')
        _frac_y = _fc3.number_input(
            f'{y_label} fraction', min_value=0.01, max_value=1.0,
            value=0.10, step=0.01, key=f'{prefix}_frac_y')

    # -- Parabolic interpolation -----------------------------------
    if not np.any(np.isfinite(_S_work)):
        st.warning(
            'All grid points are excluded -- cannot fit. '
            'Adjust exclusion settings.'
        )
        st.session_state[f'{prefix}_exc_mask_2d'] = _exc_mask_2d
        st.session_state[f'{prefix}_exc_x_mask_1d'] = _x_exc
        st.session_state[f'{prefix}_exc_y_mask_1d'] = _y_exc
        st.session_state[f'{prefix}_stored_exc_sig_vals'] = (
            list(_exc_sig_vals) if _has_sigma else []
        )
        st.session_state[f'{prefix}_exc_x_val_set'] = set(
            float(x_grid[i]) for i, v in enumerate(_x_exc) if v
        )
        st.session_state[f'{prefix}_exc_y_val_set'] = set(
            float(y_grid[i]) for i, v in enumerate(_y_exc) if v
        )
        return (_exc_mask_2d,)

    best_x, best_y, best_S, _fit_coeffs, _fit_bounds = _parabolic_min_2d(
        x_grid, y_grid, _S_work,
        mode=_mode, fraction_x=_frac_x, fraction_y=_frac_y,
        height_factor=_h_factor,
        n_neighbors_x=_nn_x, n_neighbors_y=_nn_y,
    )

    # Add gold star to masked heatmap (axes swapped: x=y_grid, y=x_grid)
    fig_masked.add_trace(go.Scatter(
        x=[best_y], y=[best_x], mode='markers',
        marker=dict(symbol='star', size=16, color=_METHOD_COLOR,
                    line=dict(width=1, color='black')),
        name='Best fit (parabolic)',
        hovertemplate=(
            f'{x_label}={best_x:.4f}<br>'
            f'{y_label}={best_y:.3f}<br>'
            f'{_STAT_NAME}={best_S:.2f}<extra></extra>'
        ),
    ))
    _masked_slot.plotly_chart(fig_masked, use_container_width=(width is None))

    st.success(
        f'**Parabolic minimum ({_STAT_DISPLAY}):** {x_label} = {best_x:.4f}, '
        f'{y_label} = {best_y:.3f}, {_cbar_title} = {best_S:.2f}'
    )

    # Camera presets for 3D plots
    _cam_presets = {
        'Default': dict(eye=dict(x=1.5, y=1.5, z=1.2)),
        'Top-down': dict(eye=dict(x=0, y=0, z=2.5)),
        'Front': dict(eye=dict(x=0, y=2.5, z=0.5)),
        'Side': dict(eye=dict(x=2.5, y=0, z=0.5)),
    }

    # -- 3D surface plot of the parabolic fit ----------------------
    if _fit_coeffs is not None and _fit_bounds is not None:
        st.markdown('---')
        st.markdown('#### 3D Parabolic Surface')

        _cam_choice = st.radio(
            'Camera', list(_cam_presets.keys()),
            horizontal=True, key=f'{prefix}_cam_3d',
        )

        a, b, c_xy, d, e, f = _fit_coeffs
        xb0, xb1, yb0, yb1 = _fit_bounds
        _n_surf = 50
        _x_surf = np.linspace(xb0, xb1, _n_surf)
        _y_surf = np.linspace(yb0, yb1, _n_surf)
        _Xs, _Ys = np.meshgrid(_x_surf, _y_surf, indexing='ij')
        _Zs = (a * _Xs**2 + b * _Ys**2 + c_xy * _Xs * _Ys
                + d * _Xs + e * _Ys + f)

        # Grid data points in the fit region
        _xg, _yg = np.meshgrid(x_grid, y_grid, indexing='ij')
        _xgf, _ygf, _zgf = _xg.ravel(), _yg.ravel(), _S_work.ravel()
        _in_bounds = (
            np.isfinite(_zgf)
            & (_xgf >= xb0) & (_xgf <= xb1)
            & (_ygf >= yb0) & (_ygf <= yb1)
        )

        _Zs_disp = _to_display(_Zs)
        _zgf_disp = _to_display(_zgf)
        _bestS_disp = float(_to_display(np.array([best_S]))[0])

        _3d_hover = (
            f'{y_label}: %{{x:.3f}}<br>'
            f'{x_label}: %{{y:.3f}}<br>'
            f'{_cbar_title}: %{{z:.2f}}'
        )

        fig_3d = go.Figure()
        fig_3d.add_trace(go.Surface(
            x=_y_surf, y=_x_surf, z=_Zs_disp,
            colorscale='Viridis_r', opacity=0.7,
            colorbar=dict(title=f'{_cbar_title} (fit)', x=1.05),
            name='Parabolic fit',
            hovertemplate=_3d_hover + '<extra>Parabolic fit</extra>',
        ))
        if _in_bounds.sum() > 0:
            fig_3d.add_trace(go.Scatter3d(
                x=_ygf[_in_bounds], y=_xgf[_in_bounds],
                z=_zgf_disp[_in_bounds],
                mode='markers',
                marker=dict(size=3, color='#4A90D9'),
                name='Grid points',
                hovertemplate=_3d_hover + '<extra>Grid points</extra>',
            ))
        fig_3d.add_trace(go.Scatter3d(
            x=[best_y], y=[best_x], z=[_bestS_disp],
            mode='markers',
            marker=dict(size=8, color=_METHOD_COLOR, symbol='diamond'),
            name='Minimum',
            hovertemplate=_3d_hover + '<extra>Minimum</extra>',
        ))
        fig_3d.update_layout(**{
            **_theme,
            'title': dict(text=f'2D Parabolic Fit ({_STAT_DISPLAY})'),
            'scene': dict(
                xaxis_title=y_label,
                yaxis_title=x_label,
                zaxis_title=_cbar_title,
                dragmode='orbit',
            ),
            'scene_camera': _cam_presets[_cam_choice],
            'legend': dict(
                x=0.01, y=0.99, xanchor='left', yanchor='top',
                bgcolor='rgba(0,0,0,0.5)', bordercolor='gray',
                borderwidth=1, font=dict(size=11),
            ),
            'height': 500,
        })
        st.plotly_chart(fig_3d, use_container_width=True,
                        key=f'{prefix}_3d_fbpi')

    # -- 3D quadratic fit + projected surfaces (3-axis grids) ------
    _do_3d_sigma = (
        sigma_grid is not None
        and lk_D_3d is not None
        and len(sigma_grid) > 1
    )
    _do_3d_logPmax = (
        not _do_3d_sigma
        and logPmax_grid is not None
        and lk_D_3d is not None
        and len(logPmax_grid) > 1
    )
    _do_3d_fit = _do_3d_sigma or _do_3d_logPmax
    _3d_z_grid = sigma_grid if _do_3d_sigma else logPmax_grid
    _3d_z_label = 'sigma_single' if _do_3d_sigma else 'logP_max'
    _3d_z_key = 'sigma' if _do_3d_sigma else 'logPmax'
    _3d_bx = _3d_by = _3d_bz = _3d_bS = None
    _3d_coeffs = _3d_bounds = None

    if _do_3d_fit:
        _cam = _cam_presets.get(
            _cam_choice if '_cam_choice' in dir() else 'Default',
            dict(eye=dict(x=1.5, y=1.5, z=1.2)),
        )

        # Build working copy with exclusion applied
        # Negate for likelihood (minimize -logL)
        _S3d_work = (-lk_D_3d).copy().astype(float)
        for _is3 in range(_S3d_work.shape[0]):
            _S3d_work[_is3][_exc_mask_2d] = np.nan

        # Single 3D quadratic fit over (x=fbin, y=pi/sigma, z=sigma/logPmax)
        _S3d_for_fit = _S3d_work.transpose(1, 2, 0)
        (_3d_bx, _3d_by, _3d_bz, _3d_bS,
         _3d_coeffs, _3d_bounds) = _parabolic_min_3d(
            x_grid, y_grid, _3d_z_grid, _S3d_for_fit,
            height_factor=_h_factor,
            n_neighbors=max(_nn_x, _nn_y),
        )

        st.markdown('---')
        st.markdown(f'#### 3D Quadratic Fit -- {_STAT_DISPLAY}')
        if _3d_bx is None or _3d_by is None or _3d_bz is None:
            st.warning('3D quadratic fit did not converge.')
            _do_3d_fit = False
        else:
            st.success(
                f'**3D minimum ({_STAT_DISPLAY}):** {x_label} = {_3d_bx:.4f}, '
                f'{y_label} = {_3d_by:.3f}, '
                f'{_3d_z_label} = {_3d_bz:.2f}, '
                f'{_cbar_title} = {_3d_bS:.2f}'
            )

        # 3D projected surfaces
        if _do_3d_fit and _3d_coeffs is not None and _3d_bounds is not None:
            xb0, xb1, yb0, yb1, zb0, zb1 = _3d_bounds
            _ns3 = 50

            _proj_configs = [
                (x_grid, y_grid, x_label, y_label, _3d_z_label,
                 _3d_bx, _3d_by, _3d_bz,
                 lambda xx, yy: _eval_3d_quadratic(
                     _3d_coeffs, xx, yy, _3d_bz),
                 f'{x_label} x {y_label}  ({_3d_z_label}={_3d_bz:.2f})',
                 xb0, xb1, yb0, yb1, _S3d_work[:, :, :]),
                (x_grid, _3d_z_grid, x_label, _3d_z_label, y_label,
                 _3d_bx, _3d_bz, _3d_by,
                 lambda xx, zz: _eval_3d_quadratic(
                     _3d_coeffs, xx, _3d_by, zz),
                 f'{x_label} x {_3d_z_label}  ({y_label}={_3d_by:.3f})',
                 xb0, xb1, zb0, zb1, None),
                (y_grid, _3d_z_grid, y_label, _3d_z_label, x_label,
                 _3d_by, _3d_bz, _3d_bx,
                 lambda yy, zz: _eval_3d_quadratic(
                     _3d_coeffs, _3d_bx, yy, zz),
                 f'{y_label} x {_3d_z_label}  (f_bin={_3d_bx:.4f})',
                 yb0, yb1, zb0, zb1, None),
            ]

            for _ip, (_gA, _gB, _lA, _lB, _lC, _bA, _bB, _bC,
                       _eval_fn, _ttl,
                       _ab0, _ab1, _bb0, _bb1, _) in enumerate(
                           _proj_configs):
                _xp = np.linspace(_ab0, _ab1, _ns3)
                _yp = np.linspace(_bb0, _bb1, _ns3)
                _Xp, _Yp = np.meshgrid(_xp, _yp, indexing='ij')
                _Zp = _eval_fn(_Xp, _Yp)

                # Grid data in fit region
                if _ip == 0:
                    _iz_best = int(
                        np.argmin(np.abs(_3d_z_grid - _3d_bz)))
                    _sl_data = _S3d_work[_iz_best]
                elif _ip == 1:
                    _iy_best = int(
                        np.argmin(np.abs(y_grid - _3d_by)))
                    _sl_data = _S3d_work[:, :, _iy_best].T
                else:
                    _ix_best = int(
                        np.argmin(np.abs(x_grid - _3d_bx)))
                    _sl_data = _S3d_work[:, _ix_best, :].T

                _xg3, _yg3 = np.meshgrid(_gA, _gB, indexing='ij')
                _xgf3 = _xg3.ravel()
                _ygf3 = _yg3.ravel()
                _zgf3 = _sl_data.ravel()
                _ib3 = (
                    np.isfinite(_zgf3)
                    & (_xgf3 >= _ab0) & (_xgf3 <= _ab1)
                    & (_ygf3 >= _bb0) & (_ygf3 <= _bb1)
                )

                _Zpd = _to_display(_Zp)
                _zgf3d = _to_display(_zgf3)
                _bSd = float(_to_display(np.array([_3d_bS]))[0])

                _hov3 = (
                    f'{_lB}: %{{x:.3f}}<br>'
                    f'{_lA}: %{{y:.3f}}<br>'
                    f'{_cbar_title}: %{{z:.2f}}'
                )

                fig_proj = go.Figure()
                fig_proj.add_trace(go.Surface(
                    x=_yp, y=_xp, z=_Zpd,
                    colorscale='Viridis_r', opacity=0.7,
                    colorbar=dict(
                        title=f'{_cbar_title} (3D fit)', x=1.05),
                    name='3D quadratic projection',
                    hovertemplate=(
                        _hov3 + '<extra>3D fit projection</extra>'),
                ))
                if _ib3.sum() > 0:
                    fig_proj.add_trace(go.Scatter3d(
                        x=_ygf3[_ib3], y=_xgf3[_ib3],
                        z=_zgf3d[_ib3],
                        mode='markers',
                        marker=dict(size=3, color='#4A90D9'),
                        name='Grid points',
                        hovertemplate=(
                            _hov3 + '<extra>Grid points</extra>'),
                    ))
                fig_proj.add_trace(go.Scatter3d(
                    x=[_bB], y=[_bA], z=[_bSd],
                    mode='markers',
                    marker=dict(
                        size=8, color=_METHOD_COLOR, symbol='diamond'),
                    name='3D Minimum',
                    hovertemplate=(
                        _hov3 + '<extra>3D Minimum</extra>'),
                ))
                fig_proj.update_layout(**{
                    **_theme,
                    'title': dict(
                        text=f'3D Fit Projection: {_ttl}'),
                    'scene': dict(
                        xaxis_title=_lB,
                        yaxis_title=_lA,
                        zaxis_title=_cbar_title,
                        dragmode='orbit',
                    ),
                    'scene_camera': _cam,
                    'legend': dict(
                        x=0.01, y=0.99, xanchor='left',
                        yanchor='top',
                        bgcolor='rgba(0,0,0,0.5)',
                        bordercolor='gray',
                        borderwidth=1, font=dict(size=11),
                    ),
                    'height': 500,
                })
                st.plotly_chart(
                    fig_proj, use_container_width=True,
                    key=f'{prefix}_3d_proj_{_ip}',
                )

    # -- 4D quadratic fit (optional, when BOTH σ AND logPmax scanned) -
    _has_both_outer = (
        sigma_grid is not None and logPmax_grid is not None
        and sigma_grid.size > 1 and logPmax_grid.size > 1
        and lk_D_3d is not None
    )
    if _has_both_outer:
        _do_4d = st.checkbox(
            'Enable full 4D quadratic fit (f_bin × π × σ × logPmax)',
            value=False, key=f'{prefix}_4d_fit_toggle')
        if _do_4d:
            from bc.fitting import _parabolic_min_4d
            # lk_D_3d shape: [logPmax, sigma, fbin, pi] → negate for minimization
            _S4d = (-lk_D_3d).copy().astype(float)
            # Apply exclusion mask per outer slice
            for _i0 in range(_S4d.shape[0]):
                for _i1 in range(_S4d.shape[1]):
                    _S4d[_i0, _i1][_exc_mask_2d] = np.nan
            # Reorder to [fbin, pi, sigma, logPmax] for fit
            _S4d_fit = _S4d.transpose(2, 3, 1, 0)
            (_4d_bfb, _4d_bpi, _4d_bsig, _4d_blp, _4d_bS,
             _4d_coeffs, _4d_bounds) = _parabolic_min_4d(
                x_grid, y_grid, sigma_grid, logPmax_grid,
                _S4d_fit,
                height_factor=_h_factor,
                n_neighbors=max(_nn_x, _nn_y),
            )
            st.markdown('---')
            st.markdown(f'#### 4D Quadratic Fit -- {_STAT_DISPLAY}')
            if _4d_bfb is not None:
                st.success(
                    f'**4D minimum:** f_bin = {_4d_bfb:.4f}, '
                    f'{y_label} = {_4d_bpi:.3f}, '
                    f'σ_single = {_4d_bsig:.2f} km/s, '
                    f'logP_max = {_4d_blp:.2f}, '
                    f'{_cbar_title} = {_4d_bS:.2f}'
                )
                # Store interpolated result in session_state
                st.session_state[f'{prefix}_interp'] = {
                    'f_bin': _4d_bfb,
                    y_label: _4d_bpi,
                    'sigma': _4d_bsig,
                    'logPmax': _4d_blp,
                    'S': _4d_bS,
                }
            else:
                st.warning('4D quadratic fit did not converge.')

    # -- 1D slices -------------------------------------------------
    i_x_best = int(np.argmin(np.abs(x_grid - best_x)))
    i_y_best = int(np.argmin(np.abs(y_grid - best_y)))

    S_x_slice = _S_work[:, i_y_best]
    S_y_slice = _S_work[i_x_best, :]

    _, _, cx, frx = _parabolic_min_1d(
        x_grid, S_x_slice, mode=_mode, fraction=_frac_x,
        height_factor=_h_factor_x, n_neighbors=_nn_x,
    )
    _, _, cy, fry = _parabolic_min_1d(
        y_grid, S_y_slice, mode=_mode, fraction=_frac_y,
        height_factor=_h_factor_y, n_neighbors=_nn_y,
    )
    bx = best_x
    bS_x = best_S if best_S is not None else float(np.nanmin(S_x_slice))
    by = best_y
    bS_y = best_S if best_S is not None else float(np.nanmin(S_y_slice))

    # Check if we have a 3D grid (sigma scan)
    do_3d = (
        sigma_grid is not None
        and lk_D_3d is not None
        and len(sigma_grid) > 1
    )
    if do_3d:
        # Negate for likelihood
        _lk_D_3d_neg = (-lk_D_3d).astype(float)
        S_sig_slice = _lk_D_3d_neg[:, i_x_best, i_y_best]
        _, _, csig, frsig = _parabolic_min_1d(
            sigma_grid, S_sig_slice, mode=_mode, fraction=_frac_x,
            height_factor=_h_factor_x, n_neighbors=_nn_1d,
        )
        if _3d_bz is not None:
            bsig = _3d_bz
            bS_sig = (
                _3d_bS if _3d_bS is not None
                else float(np.nanmin(S_sig_slice))
            )
        else:
            bsig, bS_sig, _, _ = _parabolic_min_1d(
                sigma_grid, S_sig_slice, mode=_mode,
                fraction=_frac_x,
                height_factor=_h_factor_x, n_neighbors=_nn_1d,
            )
        sc1, sc2, sc3 = st.columns(3)
        _render_cvm_1d_plot(
            sc1, x_grid, S_x_slice, x_label, bx, bS_x, cx, frx,
            f'Slice at {y_label}={y_grid[i_y_best]:.3f}', height=300,
            log_transform=_use_log,
        )
        _render_cvm_1d_plot(
            sc2, y_grid, S_y_slice, y_label, by, bS_y, cy, fry,
            f'Slice at {x_label}={x_grid[i_x_best]:.4f}', height=300,
            log_transform=_use_log,
        )
        _render_cvm_1d_plot(
            sc3, sigma_grid, S_sig_slice, 'sigma_single',
            bsig, bS_sig, csig, frsig,
            (f'Slice at {x_label}={x_grid[i_x_best]:.4f}, '
             f'{y_label}={y_grid[i_y_best]:.3f}'),
            height=300, log_transform=_use_log,
        )
        st.info(f'**sigma_single (parabolic):** {bsig:.2f} km/s')
    else:
        bsig = None
        sc1, sc2 = st.columns(2)
        _render_cvm_1d_plot(
            sc1, x_grid, S_x_slice, x_label, bx, bS_x, cx, frx,
            f'Slice at {y_label}={y_grid[i_y_best]:.3f}', height=300,
            log_transform=_use_log,
        )
        _render_cvm_1d_plot(
            sc2, y_grid, S_y_slice, y_label, by, bS_y, cy, fry,
            f'Slice at {x_label}={x_grid[i_x_best]:.4f}', height=300,
            log_transform=_use_log,
        )

    # -- Store unified fit results ---------------------------------
    _interp_result = {'f_bin': best_x, 'y_val': best_y, 'S': best_S}
    if do_3d and _3d_bx is not None:
        _interp_result = {
            'f_bin': _3d_bx, 'pi': _3d_by,
            _3d_z_key: _3d_bz, 'S': _3d_bS,
        }
    elif bsig is not None:
        _interp_result['sigma'] = bsig
    st.session_state[f'{prefix}_interp'] = _interp_result

    # Add green star for interpolated point on masked heatmap
    _interp_fb_val = _interp_result.get('f_bin', best_x)
    _interp_y_val = _interp_result.get(
        'pi', _interp_result.get(
            'sigma', _interp_result.get('y_val', best_y)))
    if _interp_fb_val is not None and _interp_y_val is not None:
        _star_trace = go.Scatter(
            x=[_interp_y_val], y=[_interp_fb_val], mode='markers',
            marker=dict(symbol='star', size=14, color='#00CC66',
                        line=dict(width=1, color='black')),
            name='Interpolated',
            hovertemplate=(
                f'{x_label}={_interp_fb_val:.4f}<br>'
                f'{y_label}={_interp_y_val:.3f}'
                f'<extra>Interpolated best</extra>'
            ),
        )
        fig_masked.add_trace(_star_trace)
        _masked_slot.plotly_chart(
            fig_masked, use_container_width=(width is None))
        _fig_pval.add_trace(_star_trace)
        _pval_slot.plotly_chart(
            _fig_pval, use_container_width=(width is None))

    # Store exclusion masks in session_state for downstream sections
    st.session_state[f'{prefix}_exc_mask_2d'] = _exc_mask_2d
    st.session_state[f'{prefix}_exc_x_mask_1d'] = _x_exc
    st.session_state[f'{prefix}_exc_y_mask_1d'] = _y_exc
    st.session_state[f'{prefix}_stored_exc_sig_vals'] = (
        list(_exc_sig_vals) if _has_sigma else []
    )
    st.session_state[f'{prefix}_exc_x_val_set'] = set(
        float(x_grid[i]) for i, v in enumerate(_x_exc) if v
    )
    st.session_state[f'{prefix}_exc_y_val_set'] = set(
        float(y_grid[i]) for i, v in enumerate(_y_exc) if v
    )

    return (_fit_coeffs, _interp_result)
