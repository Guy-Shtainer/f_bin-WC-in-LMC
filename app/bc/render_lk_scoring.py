"""bc.render_lk_scoring -- Likelihood scoring detail heatmaps.

Renders the Likelihood-specific scoring analysis: grid exclusion,
scoring heatmaps (raw logL, normalized likelihood), likelihood CDF,
per-bin stats table, explanation, fit mode selector, parabolic fitting,
3D surface, 1D slices, and interpolated best-fit.

Convention: logL is always negative (higher = better). We find the maximum.

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
    _render_likelihood_explanation,
)

_make_heatmap_fig = make_heatmap_fig

# Likelihood-specific constants
_STAT_NAME = 'log L'
_STAT_DISPLAY = 'Likelihood'
_SCORE_NAME = 'Normalized Likelihood'
_METHOD_COLOR = '#DAA520'


# ---------------------------------------------------------------------------
# Helper: compute pooled sim data for E6 stats table (E5 CDF removed)
# ---------------------------------------------------------------------------

def _compute_pooled_sim(obs_delta_rv: np.ndarray, result: dict) -> np.ndarray | None:
    """Simulate at best-fit and return pooled ΔRV array for the stats table."""
    from wr_bias_simulation import (
        simulate_delta_rv_sample, SimulationConfig, BinaryParameterConfig,
    )
    _lk_p = result.get('likelihood')
    if _lk_p is None:
        return None
    _lk_p = np.asarray(_lk_p, dtype=float)
    if not np.any(np.isfinite(_lk_p)):
        return None

    flat_best = int(np.nanargmax(_lk_p))
    best_idx = np.unravel_index(flat_best, _lk_p.shape)
    fbin_g = np.asarray(result.get('fbin_grid', [0.5]))
    x_g = np.asarray(result.get('pi_grid', result.get('sigma_grid', [0.0])))
    sigma_g = np.asarray(result.get('sigma_grid', [5.0]))

    if _lk_p.ndim == 4:
        fb, pi_v, sig_v = float(fbin_g[best_idx[2]]), float(x_g[best_idx[3]]), float(sigma_g[best_idx[1]])
    elif _lk_p.ndim == 3:
        fb, pi_v, sig_v = float(fbin_g[best_idx[1]]), float(x_g[best_idx[2]]), float(sigma_g[best_idx[0]])
    else:
        fb, pi_v = float(fbin_g[best_idx[0]]), float(x_g[best_idx[1]])
        sig_v = float(sigma_g[0]) if sigma_g.size else 5.0

    obs_drv = np.abs(np.asarray(obs_delta_rv))
    sim_cfg = SimulationConfig(
        n_stars=len(obs_drv),
        sigma_single=sig_v,
        sigma_measure=float(result.get('sigma_meas', 3.0)),
    )
    bin_cfg = BinaryParameterConfig()
    all_sim = []
    for seed_i in range(100):
        rng = np.random.default_rng(42 + seed_i)
        all_sim.append(simulate_delta_rv_sample(
            f_bin=fb, pi=pi_v, sim_cfg=sim_cfg, bin_cfg=bin_cfg, rng=rng))
    return np.concatenate(all_sim)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

# WORKING — do not change this code (D5a: Raw logL Heatmap, D9: 1D Slices, D10: 3D Surface)
def render_lk_scoring_detail(
    lk_D_2d: np.ndarray,
    lk_p_2d: np.ndarray,
    x_grid: np.ndarray,
    y_grid: np.ndarray,
    x_label: str = 'f_bin',
    y_label: str = 'π',
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

    # -- D6: Log scale toggle REMOVED (heatmaps moved to top) ------
    _cbar_title = _STAT_NAME

    def _to_display(S_arr):
        """Pass-through (linear scale)."""
        return S_arr

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
    # logL_raw is negative (higher = better) — display as-is, find maximum.
    _S_work = lk_D_2d.copy().astype(float)
    _S_work[_exc_mask_2d] = np.nan
    _p_work = lk_p_2d.copy().astype(float)
    _p_work[_exc_mask_2d] = np.nan

    # -- D5a: REMOVED — heatmap moved to top (H3 in cadence.py) -----
    st.markdown('#### Likelihood Analysis')

    # D5a right panel (σ×logP) MOVED to top heatmaps in cadence.py

    # -- D5b, D5c: REMOVED (user review 2026-03-23) ----------------

    # -- E5 CDF: REMOVED. E6 stats table: MOVED to render_shared.py (under CDF).
    # E7 methodology explainer kept here.
    if obs_delta_rv is not None and likelihood_bin_edges is not None and result is not None:
        _render_likelihood_explanation(obs_delta_rv, likelihood_bin_edges)

    # -- NO S_raw heatmap (K-S only) -------------------------------
    # Skipped intentionally for Likelihood.

    # -- 3D Parabolic Surface + Fit Controls -------------------------
    st.markdown('---')
    st.markdown('#### 3D Parabolic Surface & Interpolation')
    _fc1, _fc2, _fc3 = st.columns([0.2, 0.4, 0.4])
    _fit_mode = _fc1.radio(
        'Fit selection',
        ['Height-based', 'Range-based', 'Neighborhood'],
        index=1,  # Default to Range-based
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
    _frac_x = _frac_y = 0.2
    _nn_x = _nn_y = _nn_1d = 2

    if _mode == 'height':
        _h_factor = _fc2.number_input(
            '2D fit: S > S_max x', min_value=1.01, max_value=1000.0,
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
            value=0.20, step=0.01, key=f'{prefix}_frac_x')
        _frac_y = _fc3.number_input(
            f'{y_label} fraction', min_value=0.01, max_value=1.0,
            value=0.20, step=0.01, key=f'{prefix}_frac_y')

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
        find_max=True,
    )

    # D5a heatmap removed — gold star no longer needed on it

    st.success(
        f'**Parabolic best fit (max likelihood):** {x_label} = {best_x:.4f}, '
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
            name='Maximum',
            hovertemplate=_3d_hover + '<extra>Maximum</extra>',
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

    # -- 1D slices -------------------------------------------------
    i_x_best = int(np.argmin(np.abs(x_grid - best_x)))
    i_y_best = int(np.argmin(np.abs(y_grid - best_y)))

    S_x_slice = _S_work[:, i_y_best]
    S_y_slice = _S_work[i_x_best, :]

    _, _, cx, frx = _parabolic_min_1d(
        x_grid, S_x_slice, mode=_mode, fraction=_frac_x,
        height_factor=_h_factor_x, n_neighbors=_nn_x,
        find_max=True,
    )
    _, _, cy, fry = _parabolic_min_1d(
        y_grid, S_y_slice, mode=_mode, fraction=_frac_y,
        height_factor=_h_factor_y, n_neighbors=_nn_y,
        find_max=True,
    )
    bx = best_x
    bS_x = best_S if best_S is not None else float(np.nanmax(S_x_slice))
    by = best_y
    bS_y = best_S if best_S is not None else float(np.nanmax(S_y_slice))

    # Compute sigma best-fit if 3D (for interp result), but don't render σ slice
    bsig = None
    if (sigma_grid is not None and lk_D_3d is not None
            and len(sigma_grid) > 1):
        S_sig_slice = lk_D_3d[:, i_x_best, i_y_best].astype(float)
        bsig, _, _, _ = _parabolic_min_1d(
            sigma_grid, S_sig_slice, mode=_mode,
            fraction=_frac_x,
            height_factor=_h_factor_x, n_neighbors=_nn_1d,
            find_max=True,
        )

    # Only f_bin and π slices (2-column layout)
    sc1, sc2 = st.columns(2)
    _render_cvm_1d_plot(
        sc1, x_grid, S_x_slice, x_label, bx, bS_x, cx, frx,
        f'Slice at {y_label}={y_grid[i_y_best]:.3f}', height=300,
        log_transform=False,
    )
    _render_cvm_1d_plot(
        sc2, y_grid, S_y_slice, y_label, by, bS_y, cy, fry,
        f'Slice at {x_label}={x_grid[i_x_best]:.4f}', height=300,
        log_transform=False,
    )

    # Caption: which σ and logP produced this slice
    _slice_parts = []
    if sigma_grid is not None and sigma_grid.size > 1:
        _sig_at = sigma_grid[int(np.argmin(np.abs(sigma_grid - (bsig if bsig is not None else sigma_grid[0]))))]
        _slice_parts.append(f'σ_single = {_sig_at:.1f} km/s')
    if logPmax_grid is not None and logPmax_grid.size > 1:
        _slice_parts.append('logP_max = (from slider above)')
    if _slice_parts:
        st.caption(f'1D slices at: {", ".join(_slice_parts)}')

    # -- Store unified fit results ---------------------------------
    _interp_result = {'f_bin': best_x, 'y_val': best_y, 'S': best_S}
    if bsig is not None:
        _interp_result['sigma'] = bsig
    st.session_state[f'{prefix}_interp'] = _interp_result

    # D5a heatmap removed — interpolated star no longer rendered on it

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
