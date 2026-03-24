"""bc.scoring_detail — CvM/Likelihood scoring analysis with heatmaps and fits."""
from __future__ import annotations

import os
import sys

import numpy as np
import plotly.graph_objects as go
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from shared import PLOTLY_THEME, make_heatmap_fig

from bc.fitting import (
    _parabolic_min_1d, _parabolic_min_2d, _parabolic_min_3d,
    _eval_3d_quadratic, _render_cvm_1d_plot,
)

_make_heatmap_fig = make_heatmap_fig


def _render_cvm_analysis(
    ks_D_2d: np.ndarray,
    ks_p_2d: np.ndarray,
    x_grid: np.ndarray,
    y_grid: np.ndarray,
    x_label: str = 'f_bin',
    y_label: str = 'π',
    sigma_grid: np.ndarray | None = None,
    logPmax_grid: np.ndarray | None = None,
    ks_D_3d: np.ndarray | None = None,
    ks_p_3d: np.ndarray | None = None,
    ks_S_raw_2d: np.ndarray | None = None,
    height: int = 400,
    width: int | None = None,
    prefix: str = 'cvm',
    mode: str = 'cvm',
    obs_delta_rv: np.ndarray | None = None,
    likelihood_bin_edges: np.ndarray | None = None,
    result: dict | None = None,
) -> None:
    """Render scoring analysis: heatmaps, grid exclusion, parabolic fit, 1D slices.

    Works for both CvM (mode='cvm') and Likelihood (mode='likelihood').
    Convention: x_grid = fbin (rows of z), y_grid = π/σ (cols of z).
    Display matches make_heatmap_fig: y-axis = f_bin, x-axis = π/σ.
    """
    _theme = PLOTLY_THEME
    _is_likelihood = (mode == 'likelihood')

    # Mode-dependent labels
    _stat_name = '−log L' if _is_likelihood else 'S'
    _stat_display = 'Likelihood' if _is_likelihood else 'CvM S-score'
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
    _raw_title = f'{_stat_display} — {_cbar_title} (all models)' if _is_likelihood else f'Weighted {_cbar_title} (all models)'
    fig_raw.update_layout(**{**_theme, 'title': dict(text=_raw_title),
                             'xaxis': dict(title=y_label), 'yaxis': dict(title=x_label),
                             'height': height, 'width': width})
    st.plotly_chart(fig_raw, use_container_width=(width is None))
    _raw_caption = ('Higher likelihood = better fit. Gold star marks parabolic best fit.'
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

    # Likelihood-specific: CDF comparison, per-bin stats, and explanation
    if _is_likelihood and obs_delta_rv is not None and likelihood_bin_edges is not None and result is not None:
        from bc.likelihood_viz import (
            render_likelihood_cdf, render_likelihood_stats_table,
            render_likelihood_explanation,
        )
        _pooled_sim = render_likelihood_cdf(
            obs_delta_rv, result, likelihood_bin_edges,
            prefix=prefix, theme=_theme,
        )
        if _pooled_sim is not None:
            render_likelihood_stats_table(
                obs_delta_rv, _pooled_sim, likelihood_bin_edges,
            )
        render_likelihood_explanation(obs_delta_rv, likelihood_bin_edges)

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
        f'**Parabolic best fit ({_stat_display}):** {x_label} = {best_x:.4f}, '
        f'{y_label} = {best_y:.3f}, {_cbar_title} = {best_S:.2f}')

    # Camera presets (shared by 2D and 3D surface plots)
    _cam_presets = {
        'Default': dict(eye=dict(x=1.5, y=1.5, z=1.2)),
        'Top-down': dict(eye=dict(x=0, y=0, z=2.5)),
        'Front': dict(eye=dict(x=0, y=2.5, z=0.5)),
        'Side': dict(eye=dict(x=2.5, y=0, z=0.5)),
    }

    # ── 3b. 3D surface plot of the parabolic fit ─────────────────────────
    if _fit_coeffs is not None and _fit_bounds is not None:
        st.markdown('---')
        st.markdown('#### 3D Parabolic Surface')

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
                'title': dict(text=f'2D Parabolic Fit ({_stat_display})'),
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
    # Determine which 3rd axis to use: sigma (if multi-valued) or logPmax
    _do_3d_sigma = (sigma_grid is not None and ks_D_3d is not None
                    and len(sigma_grid) > 1)
    _do_3d_logPmax = (not _do_3d_sigma and logPmax_grid is not None
                      and ks_D_3d is not None and len(logPmax_grid) > 1)
    _do_3d_fit = _do_3d_sigma or _do_3d_logPmax
    _3d_z_grid = sigma_grid if _do_3d_sigma else logPmax_grid
    _3d_z_label = 'σ_single' if _do_3d_sigma else 'logP_max'
    _3d_z_key = 'sigma' if _do_3d_sigma else 'logPmax'  # key in _interp_result
    if _do_3d_fit:
        _cam = _cam_presets.get(
            _cam_choice if '_cam_choice' in dir() else 'Default',
            dict(eye=dict(x=1.5, y=1.5, z=1.2)))

        # Build working copy with exclusion applied
        # Negate for likelihood (same as 2D: minimize -logL)
        _S3d_work = (-ks_D_3d if _is_likelihood else ks_D_3d).copy().astype(float)
        for _is3 in range(_S3d_work.shape[0]):
            _S3d_work[_is3][_exc_mask_2d] = np.nan

        # Single 3D quadratic fit over (x=fbin, y=pi/sigma, z=sigma/logPmax)
        # _S3d_work is (n_z, n_fb, n_y) → transpose to (n_fb, n_y, n_z)
        _S3d_for_fit = _S3d_work.transpose(1, 2, 0)
        _3d_bx, _3d_by, _3d_bz, _3d_bS, _3d_coeffs, _3d_bounds = \
            _parabolic_min_3d(x_grid, y_grid, _3d_z_grid, _S3d_for_fit,
                              height_factor=_h_factor, n_neighbors=max(_nn_x, _nn_y))

        st.markdown('---')
        st.markdown(f'#### 3D Quadratic Fit — {_stat_display}')
        if _3d_bx is None or _3d_by is None or _3d_bz is None:
            st.warning('3D quadratic fit did not converge.')
            _do_3d_fit = False  # skip projections
        else:
            st.success(
                f'**3D best fit ({_stat_display}):** {x_label} = {_3d_bx:.4f}, '
                f'{y_label} = {_3d_by:.3f}, {_3d_z_label} = {_3d_bz:.2f}, '
                f'{_cbar_title} = {_3d_bS:.2f}')

        if _do_3d_fit and _3d_coeffs is not None and _3d_bounds is not None:
            xb0, xb1, yb0, yb1, zb0, zb1 = _3d_bounds
            _ns3 = 50

            # 3 projections: fix one variable at best, show surface for other two
            _proj_configs = [
                (x_grid, y_grid, x_label, y_label, _3d_z_label,
                 _3d_bx, _3d_by, _3d_bz,
                 lambda xx, yy: _eval_3d_quadratic(_3d_coeffs, xx, yy, _3d_bz),
                 f'{x_label} × {y_label}  ({_3d_z_label}={_3d_bz:.2f})',
                 xb0, xb1, yb0, yb1, _S3d_work[:, :, :]),
                (x_grid, _3d_z_grid, x_label, _3d_z_label, y_label,
                 _3d_bx, _3d_bz, _3d_by,
                 lambda xx, zz: _eval_3d_quadratic(_3d_coeffs, xx, _3d_by, zz),
                 f'{x_label} × {_3d_z_label}  ({y_label}={_3d_by:.3f})',
                 xb0, xb1, zb0, zb1, None),
                (y_grid, _3d_z_grid, y_label, _3d_z_label, x_label,
                 _3d_by, _3d_bz, _3d_bx,
                 lambda yy, zz: _eval_3d_quadratic(_3d_coeffs, _3d_bx, yy, zz),
                 f'{y_label} × {_3d_z_label}  (f_bin={_3d_bx:.4f})',
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
                    # f_bin × y: need best z-axis slice from 3D data
                    _iz_best = int(np.argmin(np.abs(_3d_z_grid - _3d_bz)))
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
            'f_bin': _3d_bx, 'pi': _3d_by,
            _3d_z_key: _3d_bz, 'S': _3d_bS,
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
                           f'{y_label}={_interp_y_val:.3f}<extra>Interpolated best</extra>'),
        )
        fig_masked.add_trace(_star_trace)
        _masked_slot.plotly_chart(fig_masked, use_container_width=(width is None))
        # Also add to score heatmap
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
