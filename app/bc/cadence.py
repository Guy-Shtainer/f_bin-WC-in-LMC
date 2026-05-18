"""bc.cadence — Cadence-aware simulation tabs (Dsilva + Langer variants)."""
from __future__ import annotations

import dataclasses
import datetime as _dt
import os
import sys
import threading

import numpy as np
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from shared import (
    cached_load_observed_delta_rvs, cached_load_cadence,
    cached_load_grid_result, settings_hash,
)

from bc.helpers import (
    _RESULT_DIR,
    _build_descriptive_filename,
    _render_partial_table,
    _scan_result_metadata,
    _make_max_pval_fig, _make_heatmap_fig,
    build_sim_context_signature, diff_sim_contexts,
)
from bc.params import (
    _render_orbital_params_dsilva, _render_orbital_params_langer,
    _render_cadence_sigma_scan, _render_cadence_adaptive_bins,
    _render_likelihood_bin_config, _render_logPmax_scan,
)
from bc.analysis import _get_method_array  # noqa: F401 — re-export for tests
from bc.runners import _run_cadence_bg
from bc.extras import _render_error_model_selector
from bc.subtabs import render_model_subtabs
from bc.polling import _poll_cadence_job
from bc.polling_langer import _poll_cadence_job_langer


# ─────────────────────────────────────────────────────────────────────────────
# Best-model helper: find best grid point from (possibly masked) likelihood
# ─────────────────────────────────────────────────────────────────────────────

def _find_best_model(
    lk_arr: np.ndarray,
    fbin_grid: np.ndarray,
    pi_grid: np.ndarray,
    sigma_grid: np.ndarray,
    logPmax_grid: np.ndarray,
    is_dsilva: bool,
    prefix: str,
) -> dict | None:
    """Return best-fit model parameters from a (possibly masked) likelihood.

    Returns ``{'f_bin', 'pi', 'sigma_single', 'logP_max'}`` or *None* when
    no finite values exist.  For axes that are not grid-searched (size ≤ 1)
    the single grid value (== the hard-coded parameter) is used.
    """
    if not np.any(np.isfinite(lk_arr)):
        return None

    _flat = int(np.nanargmax(lk_arr))
    _shape = lk_arr.shape

    if lk_arr.ndim == 4:
        _lp_idx = _flat // (_shape[1] * _shape[2] * _shape[3])
        _rem = _flat % (_shape[1] * _shape[2] * _shape[3])
        _sig_idx = _rem // (_shape[2] * _shape[3])
        _fb_idx = (_rem // _shape[3]) % _shape[2]
        _pi_idx = _rem % _shape[3]
    elif lk_arr.ndim == 3:
        _lp_idx = 0
        _sig_idx = _flat // (_shape[1] * _shape[2])
        _fb_idx = (_flat // _shape[2]) % _shape[1]
        _pi_idx = _flat % _shape[2]
    else:
        _lp_idx = 0
        _sig_idx = 0
        _fb_idx = _flat // _shape[1]
        _pi_idx = _flat % _shape[1]

    return {
        'f_bin': float(fbin_grid[_fb_idx]),
        'pi': float(pi_grid[_pi_idx]) if is_dsilva else 0.0,
        'sigma_single': float(sigma_grid[_sig_idx]),
        'logP_max': (
            float(logPmax_grid[_lp_idx]) if len(logPmax_grid) > 0
            else float(st.session_state.get(f'{prefix}_logP_max', 5.0))
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Top 4 heatmaps (above analysis, live during runs, persistent after)
# ─────────────────────────────────────────────────────────────────────────────

def _render_top_heatmaps(p, result, fbin_g, pi_g, sigma_g, logPmax_g,
                         lk_arr, best_lp_idx, is_dsilva, height, use_cw):
    """Render 2×2 grid of heatmaps at top of results.

    Row 1: Normalized likelihood (f_bin×π | σ×logP)
    Row 2: Unnormalized -logL    (f_bin×π | σ×logP)
    """
    import plotly.graph_objects as go

    _has_sig = sigma_g.size > 1
    _has_lp = logPmax_g.size > 1
    _has_multi = _has_sig or _has_lp

    # Find best-fit indices
    if not np.any(np.isfinite(lk_arr)):
        return
    _bf = np.unravel_index(int(np.nanargmax(lk_arr)), lk_arr.shape)

    # Best-fit 2D slice (normalized)
    if lk_arr.ndim == 4:
        _norm_fbpi = lk_arr[_bf[0], _bf[1]]  # [fbin, pi]
    elif lk_arr.ndim == 3:
        _norm_fbpi = lk_arr[_bf[0]]
    else:
        _norm_fbpi = lk_arr

    # Max normalized over f_bin×π → σ×logP (2D heatmap or 1D profile)
    _norm_siglp = None      # 2D: both σ and logP scanned
    _norm_1d_vals = None     # 1D fallback: only σ or only logP scanned
    _norm_1d_grid = None
    _norm_1d_label = None
    if _has_sig and _has_lp and lk_arr.ndim == 4:
        _norm_siglp = np.nanmax(lk_arr, axis=(2, 3))  # [logP, sigma]
    elif _has_sig:
        # σ only → 1D line
        _norm_1d_grid = sigma_g
        _norm_1d_label = 'σ_single (km/s)'
        if lk_arr.ndim == 4:
            _norm_1d_vals = [float(np.nanmax(lk_arr[:, i_s, :, :]))
                            if np.any(np.isfinite(lk_arr[:, i_s, :, :])) else 0.0
                            for i_s in range(sigma_g.size)]
        elif lk_arr.ndim == 3:
            _norm_1d_vals = [float(np.nanmax(lk_arr[i_s]))
                            if np.any(np.isfinite(lk_arr[i_s])) else 0.0
                            for i_s in range(sigma_g.size)]
    elif _has_lp:
        # logP only → 1D line
        _norm_1d_grid = logPmax_g
        _norm_1d_label = 'log₁₀(P_max)'
        if lk_arr.ndim == 4:
            _norm_1d_vals = [float(np.nanmax(lk_arr[i_lp]))
                            if np.any(np.isfinite(lk_arr[i_lp])) else 0.0
                            for i_lp in range(logPmax_g.size)]
        elif lk_arr.ndim == 3:
            _norm_1d_vals = [float(np.nanmax(lk_arr[i_lp]))
                            if np.any(np.isfinite(lk_arr[i_lp])) else 0.0
                            for i_lp in range(logPmax_g.size)]

    # Unnormalized logL (raw, negative values)
    _logL_raw = result.get('logL_raw')
    _unnorm_fbpi = _unnorm_siglp = None
    _unnorm_1d_vals = None
    _unnorm_1d_grid = None
    _unnorm_1d_label = None
    if _logL_raw is not None:
        _lr = np.asarray(_logL_raw, dtype=float)
        if _lr.ndim == 4:
            _unnorm_fbpi = _lr[_bf[0], _bf[1]]
            if _has_sig and _has_lp:
                _unnorm_siglp = np.nanmax(_lr, axis=(2, 3))
            elif _has_sig:
                _unnorm_1d_grid = sigma_g
                _unnorm_1d_label = 'σ_single (km/s)'
                _unnorm_1d_vals = [float(np.nanmax(_lr[:, i_s, :, :]))
                                   if np.any(np.isfinite(_lr[:, i_s, :, :])) else 0.0
                                   for i_s in range(sigma_g.size)]
            elif _has_lp:
                _unnorm_1d_grid = logPmax_g
                _unnorm_1d_label = 'log₁₀(P_max)'
                _unnorm_1d_vals = [float(np.nanmax(_lr[i_lp]))
                                   if np.any(np.isfinite(_lr[i_lp])) else 0.0
                                   for i_lp in range(logPmax_g.size)]
        elif _lr.ndim == 3:
            _unnorm_fbpi = _lr[_bf[0]]
            if _has_sig:
                _unnorm_1d_grid = sigma_g
                _unnorm_1d_label = 'σ_single (km/s)'
                _unnorm_1d_vals = [float(np.nanmax(_lr[i_s]))
                                   if np.any(np.isfinite(_lr[i_s])) else 0.0
                                   for i_s in range(sigma_g.size)]
            elif _has_lp:
                _unnorm_1d_grid = logPmax_g
                _unnorm_1d_label = 'log₁₀(P_max)'
                _unnorm_1d_vals = [float(np.nanmax(_lr[i_lp]))
                                   if np.any(np.isfinite(_lr[i_lp])) else 0.0
                                   for i_lp in range(logPmax_g.size)]

    x_g = pi_g if is_dsilva else sigma_g
    x_label = 'π' if is_dsilva else 'σ_single (km/s)'

    # Best-fit values for caption
    _bf_fb = float(fbin_g[_bf[-2]] if lk_arr.ndim >= 2 else fbin_g[0])
    _bf_x = float(x_g[_bf[-1]] if lk_arr.ndim >= 2 else x_g[0])
    _bf_parts = [f'f_bin={_bf_fb:.3f}', f'{x_label}={_bf_x:.2f}']
    if _has_sig:
        _si = _bf[1] if lk_arr.ndim == 4 else (_bf[0] if lk_arr.ndim == 3 else 0)
        _bf_parts.append(f'σ={float(sigma_g[_si]):.1f}')
    if _has_lp:
        _bf_parts.append(f'logP_max={float(logPmax_g[_bf[0]]):.2f}')
    st.caption(f'Best-fit: {", ".join(_bf_parts)}')

    # Row 1: Normalized
    _r1c1, _r1c2 = st.columns(2)
    with _r1c1:
        # WORKING — do not change this code (H1: Normalized Likelihood f_bin×π)
        _fig1 = _make_heatmap_fig(
            _norm_fbpi, fbin_g, x_g,
            title='Normalized Likelihood (f<sub>bin</sub> × π)',
            show_d=False, height=height,
            x_label=x_label, x_name='pi' if is_dsilva else 'sigma',
            scoring_label='Likelihood',
            colorbar_title_override='Norm. Likelihood',
        )
        st.plotly_chart(_fig1, use_container_width=use_cw,
                        key=f'{p}_top_norm_fbpi')
    with _r1c2:
        # WORKING — do not change this code (H2: Max Norm. Likelihood σ×logP / 1D fallback)
        if _norm_siglp is not None:
            _fig2 = _make_heatmap_fig(
                _norm_siglp, logPmax_g, sigma_g,
                title='Max Norm. Likelihood (σ × logP_max)',
                show_d=False, height=height,
                x_label='σ_single (km/s)',
                y_label='log₁₀(P_max)',
                x_name='σ', y_name='log₁₀(P_max)',
                scoring_label='Likelihood',
                colorbar_title_override='Max Norm. L',
            )
            st.plotly_chart(_fig2, use_container_width=use_cw,
                            key=f'{p}_top_norm_siglp')
        elif _norm_1d_vals is not None:
            _fig2 = _make_max_pval_fig(
                _norm_1d_grid, _norm_1d_vals, height=height,
                x_label=_norm_1d_label, stat_label='Norm. Likelihood',
            )
            st.plotly_chart(_fig2, use_container_width=use_cw,
                            key=f'{p}_top_norm_1d')

    # Row 2: Unnormalized logL (raw, negative values — higher = better)
    if _unnorm_fbpi is not None:
        _r2c1, _r2c2 = st.columns(2)
        with _r2c1:
            # WORKING — do not change this code (H3: log L f_bin×π)
            _fig3 = _make_heatmap_fig(
                _unnorm_fbpi, fbin_g, x_g,
                title='log L (f<sub>bin</sub> × π)',
                show_d=False, height=height,
                x_label=x_label, x_name='pi' if is_dsilva else 'sigma',
                scoring_label='log L',
                colorbar_title_override='log L',
            )
            st.plotly_chart(_fig3, use_container_width=use_cw,
                            key=f'{p}_top_unnorm_fbpi')
        with _r2c2:
            # WORKING — do not change this code (H4: Max log L σ×logP / 1D fallback)
            if _unnorm_siglp is not None:
                _fig4 = _make_heatmap_fig(
                    _unnorm_siglp, logPmax_g, sigma_g,
                    title='Max log L (σ × logP_max)',
                    show_d=False, height=height,
                    x_label='σ_single (km/s)',
                    y_label='log₁₀(P_max)',
                    x_name='σ', y_name='log₁₀(P_max)',
                    scoring_label='log L',
                    colorbar_title_override='Max log L',
                )
                st.plotly_chart(_fig4, use_container_width=use_cw,
                                key=f'{p}_top_unnorm_siglp')
            elif _unnorm_1d_vals is not None:
                _fig4 = _make_max_pval_fig(
                    _unnorm_1d_grid, _unnorm_1d_vals, height=height,
                    x_label=_unnorm_1d_label, stat_label='log L',
                )
                st.plotly_chart(_fig4, use_container_width=use_cw,
                                key=f'{p}_top_unnorm_1d')


# ─────────────────────────────────────────────────────────────────────────────
# WORKING — do not change this code (H1-H4 Langer: top heatmaps + live updates)
# ─────────────────────────────────────────────────────────────────────────────

def _render_top_heatmaps_langer(p, result, fbin_g, pi_g, sigma_g, logPmax_g,
                                lk_arr, best_lp_idx, is_dsilva, height, use_cw):
    """Render top heatmaps — Langer-specific version.

    Array layout: [logPmax, sigma, fbin, pi=1] (4D) or [sigma, fbin, pi=1] (3D).
    Primary axes = f_bin × logP_max.  σ is secondary.

    Grid combos:
      f_bin only          → 1D f_bin profile (left), nothing (right)
      f_bin × σ           → heatmap f_bin × σ (left), nothing (right)
      f_bin × logP        → heatmap f_bin × logP (left), nothing (right)
      f_bin × σ × logP    → heatmap f_bin × logP at best σ (left), 1D σ (right)
    """
    if not np.any(np.isfinite(lk_arr)):
        return

    _has_sig = sigma_g.size > 1
    _has_lp = logPmax_g.size > 1
    _bf = np.unravel_index(int(np.nanargmax(lk_arr)), lk_arr.shape)

    # ── Helper: extract left heatmap and right 1D from an ND array ────
    def _extract_left_right(arr):
        """Return (left_2d, left_y_grid, left_y_label, right_1d_vals, right_grid, right_label).

        left_2d: [fbin, y_axis] heatmap data.  y_axis = logP or σ.
        right: 1D profile of the secondary axis (only when 3 grids).
        """
        if arr is None or not np.any(np.isfinite(arr)):
            return None, None, None, None, None, None

        if _has_sig and _has_lp:
            # 3 grids → left = f_bin × logP (at best σ), right = 1D σ
            if arr.ndim == 4:
                # [logP, sigma, fbin, pi=1]
                _best_sig = int(_bf[1])
                _slice = arr[:, _best_sig, :, 0]  # [logP, fbin]
                _left = _slice.T  # [fbin, logP]
                # 1D σ: max over logP×fbin×pi for each σ
                _r1d = [float(np.nanmax(arr[:, s, :, :]))
                        if np.any(np.isfinite(arr[:, s, :, :])) else np.nan
                        for s in range(sigma_g.size)]
            else:
                return None, None, None, None, None, None
            return (_left, logPmax_g, 'log₁₀(P_max)',
                    _r1d, sigma_g, 'σ_single (km/s)')

        elif _has_lp:
            # 2 grids: f_bin × logP (σ constant)
            if arr.ndim == 4:
                # [logP, sigma=1, fbin, pi=1] → squeeze σ and pi
                _left = arr[:, 0, :, 0].T  # [fbin, logP]
            elif arr.ndim == 3:
                # [logP, fbin, pi=1] — shouldn't happen for Langer but handle
                _left = arr[:, :, 0].T if arr.shape[-1] == 1 else arr[:, :].T
            else:
                return None, None, None, None, None, None
            return _left, logPmax_g, 'log₁₀(P_max)', None, None, None

        elif _has_sig:
            # 2 grids: f_bin × σ (logP constant)
            if arr.ndim == 3:
                # [sigma, fbin, pi=1]
                _left = arr[:, :, 0].T  # [fbin, sigma]
            elif arr.ndim == 4:
                # [logP=1, sigma, fbin, pi=1]
                _left = arr[0, :, :, 0].T  # [fbin, sigma]
            else:
                return None, None, None, None, None, None
            return _left, sigma_g, 'σ_single (km/s)', None, None, None

        else:
            # 1 grid: f_bin only → 1D profile
            # Squeeze to 1D
            _flat = arr.ravel()
            if _flat.size == fbin_g.size:
                return None, None, None, _flat.tolist(), fbin_g, 'f_bin'
            return None, None, None, None, None, None

    # ── Extract for normalized likelihood ─────────────────────────────
    _n_left, _n_y_g, _n_y_lbl, _n_r1d, _n_r_g, _n_r_lbl = \
        _extract_left_right(lk_arr)

    # ── Extract for unnormalized logL ─────────────────────────────────
    _logL_raw = result.get('logL_raw')
    _u_arr = np.asarray(_logL_raw, dtype=float) if _logL_raw is not None else None
    _u_left, _u_y_g, _u_y_lbl, _u_r1d, _u_r_g, _u_r_lbl = \
        _extract_left_right(_u_arr)

    # ── Best-fit caption (only scanned params) ────────────────────────
    _bf_parts = []
    # f_bin is always scanned
    _bf_fb_idx = _bf[-2] if lk_arr.ndim >= 2 else 0
    _bf_parts.append(f'f_bin={float(fbin_g[_bf_fb_idx]):.3f}')
    if _has_lp:
        _bf_parts.append(f'logP_max={float(logPmax_g[_bf[0]]):.2f}')
    if _has_sig:
        _si = _bf[1] if lk_arr.ndim == 4 else _bf[0]
        _bf_parts.append(f'σ_single={float(sigma_g[_si]):.1f} km/s')
    elif sigma_g.size == 1:
        _bf_parts.append(f'σ_single={float(sigma_g[0]):.1f} km/s (constant)')
    st.caption(f'Best-fit: {", ".join(_bf_parts)}')

    # ── Row 1: Normalized likelihood ──────────────────────────────────
    _r1c1, _r1c2 = st.columns(2)
    with _r1c1:
        if _n_left is not None:
            _title_y = _n_y_lbl.replace('σ_single (km/s)', 'σ_single').replace('log₁₀(P_max)', 'logP_max')
            _fig1 = _make_heatmap_fig(
                _n_left, fbin_g, _n_y_g,
                title=f'Normalized Likelihood (f_bin × {_title_y})',
                show_d=False, height=height,
                x_label=_n_y_lbl, x_name='logPmax' if _n_y_lbl.startswith('log') else 'sigma',
                scoring_label='Likelihood',
                colorbar_title_override='Norm. Likelihood',
            )
            st.plotly_chart(_fig1, use_container_width=use_cw,
                            key=f'{p}_top_norm_fbpi')
        elif _n_r1d is not None and _n_r_lbl == 'f_bin':
            # f_bin only → 1D profile
            _fig1 = _make_max_pval_fig(
                _n_r_g, _n_r1d, height=height,
                x_label='f_bin', stat_label='Norm. Likelihood',
            )
            st.plotly_chart(_fig1, use_container_width=use_cw,
                            key=f'{p}_top_norm_1d')
    with _r1c2:
        if _n_r1d is not None and _n_r_lbl != 'f_bin':
            _fig2 = _make_max_pval_fig(
                _n_r_g, _n_r1d, height=height,
                x_label=_n_r_lbl, stat_label='Norm. Likelihood',
            )
            st.plotly_chart(_fig2, use_container_width=use_cw,
                            key=f'{p}_top_norm_1d')

    # ── Row 2: Unnormalized logL ──────────────────────────────────────
    if _u_left is not None or (_u_r1d is not None and _u_r_lbl == 'f_bin'):
        _r2c1, _r2c2 = st.columns(2)
        with _r2c1:
            if _u_left is not None:
                _title_y = _u_y_lbl.replace('σ_single (km/s)', 'σ_single').replace('log₁₀(P_max)', 'logP_max')
                _fig3 = _make_heatmap_fig(
                    _u_left, fbin_g, _u_y_g,
                    title=f'log L (f_bin × {_title_y})',
                    show_d=False, height=height,
                    x_label=_u_y_lbl, x_name='logPmax' if _u_y_lbl.startswith('log') else 'sigma',
                    scoring_label='log L',
                    colorbar_title_override='log L',
                )
                st.plotly_chart(_fig3, use_container_width=use_cw,
                                key=f'{p}_top_unnorm_fbpi')
            elif _u_r1d is not None and _u_r_lbl == 'f_bin':
                _fig3 = _make_max_pval_fig(
                    _u_r_g, _u_r1d, height=height,
                    x_label='f_bin', stat_label='log L',
                )
                st.plotly_chart(_fig3, use_container_width=use_cw,
                                key=f'{p}_top_unnorm_1d')
        with _r2c2:
            if _u_r1d is not None and _u_r_lbl != 'f_bin':
                _fig4 = _make_max_pval_fig(
                    _u_r_g, _u_r1d, height=height,
                    x_label=_u_r_lbl, stat_label='log L',
                )
                st.plotly_chart(_fig4, use_container_width=use_cw,
                                key=f'{p}_top_unnorm_1d')


# ─────────────────────────────────────────────────────────────────────────────
# Result display: build model_ctx + delegate to subtabs
# ─────────────────────────────────────────────────────────────────────────────

def _render_cadence_results(p: str, _is_dsilva: bool, bin_cfg=None,
                            settings: dict = None,
                            obs_override: 'np.ndarray | None' = None) -> None:
    """Shared right-column results display for both cadence tabs."""
    _ch = int(st.session_state.get('bc_canvas_height', 520))
    _cw_raw = int(st.session_state.get('bc_canvas_width', 0))
    _cw = _cw_raw if _cw_raw > 0 else None
    _use_cw = (_cw is None)

    # Poll job status; only proceed to analysis on 'done'
    status = _poll_cadence_job(p)
    if status != 'done':
        return

    # For Langer: clear final live heatmaps — H1-H4 already show everything,
    # the separate live heatmap rendered by polling is redundant and shows π.
    if not _is_dsilva:
        for _lk in ('_final_live_heatmaps', '_final_live_sigma_1d',
                     '_final_live_logPmax_1d', '_final_live_sigma_logPmax_2d'):
            st.session_state.pop(f'{p}{_lk}', None)

    result = st.session_state.get(f'{p}_result')
    if result is None or result.get('likelihood') is None:
        st.warning('No results found.')
        return

    # ── Extract grids ─────────────────────────────────────────────────────
    fbin_grid = np.asarray(result['fbin_grid'])
    pi_grid = np.asarray(result['pi_grid'])
    sigma_grid = np.asarray(result['sigma_grid'])
    logPmax_grid = np.asarray(result.get('logPmax_grid', []))
    _has_logPmax_scan = len(logPmax_grid) > 1
    lk_arr = np.asarray(result['likelihood'])

    n_sig = len(sigma_grid)
    _is_langer_sigma = (not _is_dsilva) and n_sig > 1

    # ── Grid Range Exclusion (folded, above heatmaps) ──────────────────
    from bc.helpers import render_grid_exclusion
    _exc_mask = render_grid_exclusion(
        f'{p}_likelihood_analysis', fbin_grid,
        pi_grid if _is_dsilva else sigma_grid,
        'f_bin', '\u03c0' if _is_dsilva else '\u03c3_single',
        sigma_grid=sigma_grid if _is_dsilva else None,
        logPmax_grid=logPmax_grid if _has_logPmax_scan else None,
        ndim=lk_arr.ndim,
    )

    # ── Apply exclusion to likelihood for best-fit computation ────────────
    _has_exclusion = _exc_mask is not None and bool(_exc_mask.any())
    if _has_exclusion:
        _effective_lk = lk_arr.copy().astype(float)
        _effective_lk[_exc_mask] = np.nan
    else:
        _effective_lk = lk_arr

    # ── Determine x-axis and ndim_mode ────────────────────────────────────
    if _is_langer_sigma:
        _cad_ndim_mode = 'cadence_langer'
        _cad_x_g = np.asarray(sigma_grid)
        _cad_x_name = 'sigma'
        _cad_x_label = 'sigma_single'
        _cad_x_disp = 'sigma_single (km/s)'
    elif _is_dsilva:
        _cad_ndim_mode = 'cadence_dsilva'
        _cad_x_g = np.asarray(pi_grid)
        _cad_x_name = 'pi'
        _cad_x_label = '\u03c0'
        _cad_x_disp = '\u03c0 (period power-law index)'
    else:
        _cad_ndim_mode = 'cadence_langer'
        _cad_x_g = np.asarray(sigma_grid)
        _cad_x_name = 'sigma'
        _cad_x_label = 'sigma_single'
        _cad_x_disp = 'sigma_single (km/s)'

    # ── Find best model from effective (exclusion-masked) likelihood ──────
    best_model = _find_best_model(
        _effective_lk, fbin_grid, pi_grid, sigma_grid, logPmax_grid,
        _is_dsilva, p,
    )
    if best_model is None:
        st.warning('No finite likelihood values in grid \u2014 cannot run analysis.')
        return

    best_fbin_v = best_model['f_bin']
    best_pi_v = best_model['pi']
    best_sigma_v = best_model['sigma_single']
    ana_logPmax = best_model['logP_max']

    # ── Outer slice selection for heatmap display ─────────────────────────
    _cad_lp_idx = 0
    if _has_logPmax_scan and _effective_lk.ndim == 4:
        if np.any(np.isfinite(_effective_lk)):
            _hm_bf = np.unravel_index(
                int(np.nanargmax(_effective_lk)), _effective_lk.shape)
            _cad_lp_idx = _hm_bf[0]

    _lk_for_slice = _effective_lk
    if _has_logPmax_scan and _lk_for_slice.ndim == 4:
        _lk_for_slice = _lk_for_slice[_cad_lp_idx]

    _cad_outer_list = []
    if _has_logPmax_scan:
        _cad_outer_list.append(_cad_lp_idx)
    if n_sig > 1:
        _cad_best_s = 0
        if np.any(np.isfinite(_lk_for_slice)):
            _lkmax_list = [float(np.nanmax(_lk_for_slice[s]))
                           for s in range(n_sig)]
            _cad_best_s = int(np.argmax(_lkmax_list))
        _cad_outer_list.append(_cad_best_s)
    elif _lk_for_slice.ndim == 3 and not _has_logPmax_scan:
        _cad_outer_list.append(0)
    _cad_outer = tuple(_cad_outer_list) if _cad_outer_list else None

    # ── Load observed data ────────────────────────────────────────────────
    _settings = settings or {}
    cls = _settings.get('classification', {})
    thresh_dRV = float(cls.get('threshold_dRV', 45.5))
    sh_analysis = settings_hash(_settings) if _settings else ''
    if obs_override is not None:
        obs_drv_analysis = obs_override
        obs_detail = None
        try:
            cadence_list_a, cadence_weights_a = cached_load_cadence(sh_analysis)
        except Exception:
            cadence_list_a = cadence_weights_a = None
        _has_obs = True
    else:
        try:
            obs_drv_analysis, obs_detail = cached_load_observed_delta_rvs(sh_analysis)
            cadence_list_a, cadence_weights_a = cached_load_cadence(sh_analysis)
            _has_obs = True
        except Exception:
            obs_drv_analysis = obs_detail = cadence_list_a = cadence_weights_a = None
            _has_obs = False

    # ── Compute gap_sim at best-fit for analysis plots ────────────────────
    gap_sim = None
    _bin_cfg_explore = None
    if _has_obs:
        from wr_bias_simulation import (
            SimulationConfig, BinaryParameterConfig, simulate_with_params,
        )
        if bin_cfg is not None:
            _bin_cfg_explore = bin_cfg
        else:
            _d_period_model = 'powerlaw' if _is_dsilva else 'langer2020'
            _bin_cfg_explore = BinaryParameterConfig(
                logP_min=float(st.session_state.get(f'{p}_logP_min', 0.15)),
                logP_max=float(st.session_state.get(f'{p}_logP_max', 5.0)),
                period_model=_d_period_model,
                e_model=str(st.session_state.get(f'{p}_e_model', 'flat')),
                e_max=float(st.session_state.get(f'{p}_e_max', 0.9)),
                mass_primary_model=str(
                    st.session_state.get(f'{p}_mass_model', 'fixed')),
                mass_primary_fixed=float(
                    st.session_state.get(f'{p}_mass_fixed', 10.0)),
                q_model=str(st.session_state.get(f'{p}_q_model', 'flat')),
                q_range=(float(st.session_state.get(f'{p}_q_min', 0.1)),
                         float(st.session_state.get(f'{p}_q_max', 2.0))),
                langer_q_mu=float(
                    st.session_state.get(f'{p}_lq_mu', 0.7)),
                langer_q_sigma=float(
                    st.session_state.get(f'{p}_lq_sig', 0.2)),
            )

        # Override logP_max with best-fit value when grid search is active
        if len(logPmax_grid) > 1:
            _bin_cfg_explore.logP_max = ana_logPmax

        _d_sigma_meas = float(
            st.session_state.get(f'{p}_sigma_meas', 1.622))
        _sim_cfg_gap = SimulationConfig(
            n_stars=10000,
            sigma_single=best_sigma_v,
            sigma_measure=_d_sigma_meas,
            cadence_library=cadence_list_a,
            cadence_weights=cadence_weights_a,
        )
        _gap_fp = (best_fbin_v, best_pi_v, best_sigma_v,
                   ana_logPmax, lk_arr.shape)
        if (st.session_state.get(f'{p}_gap_fingerprint') != _gap_fp
                or f'{p}_gap_sim' not in st.session_state):
            rng_diag = np.random.default_rng(42)
            st.session_state[f'{p}_gap_sim'] = simulate_with_params(
                best_fbin_v, best_pi_v,
                _sim_cfg_gap, _bin_cfg_explore, rng_diag,
            )
            st.session_state[f'{p}_gap_fingerprint'] = _gap_fp
            st.session_state.pop(f'{p}_sim_drv', None)
        gap_sim = st.session_state[f'{p}_gap_sim']

    # ── Inject missing keys into result (backward compat for old .npz) ───
    if 'obs_delta_rv' not in result and obs_drv_analysis is not None:
        result['obs_delta_rv'] = obs_drv_analysis
    if 'sigma_meas' not in result:
        result['sigma_meas'] = float(
            st.session_state.get(f'{p}_sigma_meas', 1.622))
    if 'cadence_library' not in result and cadence_list_a is not None:
        result['cadence_library'] = cadence_list_a

    # ── Apply exclusion mask to result for downstream scoring / display ───
    if _has_exclusion:
        _hm_result = dict(result)
        if 'logL_raw' in result:
            _lr_m = np.asarray(result['logL_raw'], dtype=float).copy()
            _lr_m[_exc_mask] = np.nan
            _hm_result['logL_raw'] = _lr_m
        _hm_result['likelihood'] = _effective_lk
    else:
        _hm_result = result

    # ── Build model_ctx and delegate to subtabs ───────────────────────────
    _model_type = 'cadence_dsilva' if _is_dsilva else 'cadence_langer'
    _period_model = 'powerlaw' if _is_dsilva else 'langer2020'

    model_ctx = {
        'model_type': _model_type,
        'ndim_mode': _cad_ndim_mode,
        'x_name': _cad_x_name,
        'x_label': _cad_x_label,
        'x_display_label': _cad_x_disp,
        'period_model': _period_model,
        'has_case_AB': not _is_dsilva,
        'result': _hm_result,
        'fbin_g': fbin_grid,
        'x_g': _cad_x_g,
        'sigma_g': np.asarray(sigma_grid),
        'logPmax_g': logPmax_grid if len(logPmax_grid) > 0 else np.array(
            [float(st.session_state.get(f'{p}_logP_max', 5.0))]),
        'gap_sim': gap_sim,
        'best_model': best_model,
        'obs_delta_rv': obs_drv_analysis,
        'obs_detail': obs_detail,
        'cadence_list': cadence_list_a,
        'cadence_weights': cadence_weights_a,
        'n_stars_sim': 10000,
        'sigma_meas': float(
            st.session_state.get(f'{p}_sigma_meas', 1.622)),
        'bin_cfg': _bin_cfg_explore,
        'logP_min': float(st.session_state.get(f'{p}_logP_min', 0.15)),
        'logP_max': ana_logPmax,
        'thresh_dRV': thresh_dRV,
        'canvas_height': _ch,
        'canvas_width': _cw,
        'use_container_width': _use_cw,
        'disp_outer_slices': _cad_outer,
        'settings': _settings,
        'classification': cls,
    }

    # ── 4 heatmaps at top (live during run, persist after) ──────────────
    _hm_lp_idx = _cad_lp_idx
    if _is_dsilva:
        _render_top_heatmaps(p, _hm_result, fbin_grid, pi_grid, sigma_grid,
                             logPmax_grid, _effective_lk, _hm_lp_idx,
                             _is_dsilva, _ch, _use_cw)
    else:
        _render_top_heatmaps_langer(p, _hm_result, fbin_grid, pi_grid,
                                    sigma_grid, logPmax_grid, _effective_lk,
                                    _hm_lp_idx, _is_dsilva, _ch, _use_cw)

    render_model_subtabs(p, model_ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Langer-specific results display (duplicate of _render_cadence_results)
# Uses _poll_cadence_job_langer which has no f_bin×π heatmap rendering.
# ─────────────────────────────────────────────────────────────────────────────

def _render_cadence_results_langer(p: str, _is_dsilva: bool, bin_cfg=None,
                                   settings: dict = None,
                                   obs_override: 'np.ndarray | None' = None) -> None:
    """Langer-specific right-column results display.

    Same as _render_cadence_results but uses _poll_cadence_job_langer
    (no f_bin×π heatmaps). H1-H4 handle all heatmap display.
    """
    _ch = int(st.session_state.get('bc_canvas_height', 520))
    _cw_raw = int(st.session_state.get('bc_canvas_width', 0))
    _cw = _cw_raw if _cw_raw > 0 else None
    _use_cw = (_cw is None)

    # Poll job status — Langer version (no f_bin×π heatmaps)
    status = _poll_cadence_job_langer(p)
    if status != 'done':
        return

    result = st.session_state.get(f'{p}_result')
    if result is None or result.get('likelihood') is None:
        st.warning('No results found.')
        return

    # ── Extract grids ─────────────────────────────────────────────────────
    fbin_grid = np.asarray(result['fbin_grid'])
    pi_grid = np.asarray(result['pi_grid'])
    sigma_grid = np.asarray(result['sigma_grid'])
    logPmax_grid = np.asarray(result.get('logPmax_grid', []))
    _has_logPmax_scan = len(logPmax_grid) > 1
    lk_arr = np.asarray(result['likelihood'])

    n_sig = len(sigma_grid)
    _is_langer_sigma = (not _is_dsilva) and n_sig > 1

    # ── Grid Range Exclusion (folded, above heatmaps) ──────────────────
    from bc.helpers import render_grid_exclusion
    _exc_mask = render_grid_exclusion(
        f'{p}_likelihood_analysis', fbin_grid,
        sigma_grid,
        'f_bin', '\u03c3_single',
        sigma_grid=None,
        logPmax_grid=logPmax_grid if _has_logPmax_scan else None,
        ndim=lk_arr.ndim,
    )

    # ── Apply exclusion to likelihood for best-fit computation ────────────
    _has_exclusion = _exc_mask is not None and bool(_exc_mask.any())
    if _has_exclusion:
        _effective_lk = lk_arr.copy().astype(float)
        _effective_lk[_exc_mask] = np.nan
    else:
        _effective_lk = lk_arr

    # ── Determine x-axis and ndim_mode ────────────────────────────────────
    if _is_langer_sigma:
        _cad_ndim_mode = 'cadence_langer'
        _cad_x_g = np.asarray(sigma_grid)
        _cad_x_name = 'sigma'
        _cad_x_label = 'sigma_single'
        _cad_x_disp = 'sigma_single (km/s)'
    else:
        _cad_ndim_mode = 'cadence_langer'
        _cad_x_g = np.asarray(sigma_grid)
        _cad_x_name = 'sigma'
        _cad_x_label = 'sigma_single'
        _cad_x_disp = 'sigma_single (km/s)'

    # ── Find best model from effective (exclusion-masked) likelihood ──────
    best_model = _find_best_model(
        _effective_lk, fbin_grid, pi_grid, sigma_grid, logPmax_grid,
        _is_dsilva, p,
    )
    if best_model is None:
        st.warning('No finite likelihood values in grid \u2014 cannot run analysis.')
        return

    best_fbin_v = best_model['f_bin']
    best_pi_v = best_model['pi']
    best_sigma_v = best_model['sigma_single']
    ana_logPmax = best_model['logP_max']

    # ── Outer slice selection for heatmap display ─────────────────────────
    _cad_lp_idx = 0
    if _has_logPmax_scan and _effective_lk.ndim == 4:
        if np.any(np.isfinite(_effective_lk)):
            _hm_bf = np.unravel_index(
                int(np.nanargmax(_effective_lk)), _effective_lk.shape)
            _cad_lp_idx = _hm_bf[0]

    _lk_for_slice = _effective_lk
    if _has_logPmax_scan and _lk_for_slice.ndim == 4:
        _lk_for_slice = _lk_for_slice[_cad_lp_idx]

    _cad_outer_list = []
    if _has_logPmax_scan:
        _cad_outer_list.append(_cad_lp_idx)
    if n_sig > 1:
        _cad_best_s = 0
        if np.any(np.isfinite(_lk_for_slice)):
            _lkmax_list = [float(np.nanmax(_lk_for_slice[s]))
                           for s in range(n_sig)]
            _cad_best_s = int(np.argmax(_lkmax_list))
        _cad_outer_list.append(_cad_best_s)
    elif _lk_for_slice.ndim == 3 and not _has_logPmax_scan:
        _cad_outer_list.append(0)
    _cad_outer = tuple(_cad_outer_list) if _cad_outer_list else None

    # ── Load observed data ────────────────────────────────────────────────
    _settings = settings or {}
    cls = _settings.get('classification', {})
    thresh_dRV = float(cls.get('threshold_dRV', 45.5))
    sh_analysis = settings_hash(_settings) if _settings else ''
    if obs_override is not None:
        obs_drv_analysis = obs_override
        obs_detail = None
        try:
            cadence_list_a, cadence_weights_a = cached_load_cadence(sh_analysis)
        except Exception:
            cadence_list_a = cadence_weights_a = None
        _has_obs = True
    else:
        try:
            obs_drv_analysis, obs_detail = cached_load_observed_delta_rvs(sh_analysis)
            cadence_list_a, cadence_weights_a = cached_load_cadence(sh_analysis)
            _has_obs = True
        except Exception:
            obs_drv_analysis = obs_detail = cadence_list_a = cadence_weights_a = None
            _has_obs = False

    # ── Compute gap_sim at best-fit for analysis plots ────────────────────
    gap_sim = None
    _bin_cfg_explore = None
    if _has_obs:
        from wr_bias_simulation import (
            SimulationConfig, BinaryParameterConfig, simulate_with_params,
        )
        if bin_cfg is not None:
            _bin_cfg_explore = bin_cfg
        else:
            _bin_cfg_explore = BinaryParameterConfig(
                logP_min=float(st.session_state.get(f'{p}_logP_min', 0.15)),
                logP_max=float(st.session_state.get(f'{p}_logP_max', 5.0)),
                period_model='langer2020',
                e_model=str(st.session_state.get(f'{p}_e_model', 'flat')),
                e_max=float(st.session_state.get(f'{p}_e_max', 0.9)),
                mass_primary_model=str(
                    st.session_state.get(f'{p}_mass_model', 'fixed')),
                mass_primary_fixed=float(
                    st.session_state.get(f'{p}_mass_fixed', 10.0)),
                q_model=str(st.session_state.get(f'{p}_q_model', 'flat')),
                q_range=(float(st.session_state.get(f'{p}_q_min', 0.1)),
                         float(st.session_state.get(f'{p}_q_max', 2.0))),
                langer_q_mu=float(
                    st.session_state.get(f'{p}_lq_mu', 0.7)),
                langer_q_sigma=float(
                    st.session_state.get(f'{p}_lq_sig', 0.2)),
            )

        # Override logP_max with best-fit value when grid search is active
        if len(logPmax_grid) > 1:
            _bin_cfg_explore.logP_max = ana_logPmax

        _d_sigma_meas = float(
            st.session_state.get(f'{p}_sigma_meas', 1.622))
        _sim_cfg_gap = SimulationConfig(
            n_stars=10000,
            sigma_single=best_sigma_v,
            sigma_measure=_d_sigma_meas,
            cadence_library=cadence_list_a,
            cadence_weights=cadence_weights_a,
        )
        _gap_fp = (best_fbin_v, best_pi_v, best_sigma_v,
                   ana_logPmax, lk_arr.shape)
        if (st.session_state.get(f'{p}_gap_fingerprint') != _gap_fp
                or f'{p}_gap_sim' not in st.session_state):
            rng_diag = np.random.default_rng(42)
            st.session_state[f'{p}_gap_sim'] = simulate_with_params(
                best_fbin_v, best_pi_v,
                _sim_cfg_gap, _bin_cfg_explore, rng_diag,
            )
            st.session_state[f'{p}_gap_fingerprint'] = _gap_fp
            st.session_state.pop(f'{p}_sim_drv', None)
        gap_sim = st.session_state[f'{p}_gap_sim']

    # ── Inject missing keys into result (backward compat for old .npz) ───
    if 'obs_delta_rv' not in result and obs_drv_analysis is not None:
        result['obs_delta_rv'] = obs_drv_analysis
    if 'sigma_meas' not in result:
        result['sigma_meas'] = float(
            st.session_state.get(f'{p}_sigma_meas', 1.622))
    if 'cadence_library' not in result and cadence_list_a is not None:
        result['cadence_library'] = cadence_list_a

    # ── Apply exclusion mask to result for downstream scoring / display ───
    if _has_exclusion:
        _hm_result = dict(result)
        if 'logL_raw' in result:
            _lr_m = np.asarray(result['logL_raw'], dtype=float).copy()
            _lr_m[_exc_mask] = np.nan
            _hm_result['logL_raw'] = _lr_m
        _hm_result['likelihood'] = _effective_lk
    else:
        _hm_result = result

    # ── Build model_ctx and delegate to subtabs ───────────────────────────
    model_ctx = {
        'model_type': 'cadence_langer',
        'ndim_mode': _cad_ndim_mode,
        'x_name': _cad_x_name,
        'x_label': _cad_x_label,
        'x_display_label': _cad_x_disp,
        'period_model': 'langer2020',
        'has_case_AB': True,
        'result': _hm_result,
        'fbin_g': fbin_grid,
        'x_g': _cad_x_g,
        'sigma_g': np.asarray(sigma_grid),
        'logPmax_g': logPmax_grid if len(logPmax_grid) > 0 else np.array(
            [float(st.session_state.get(f'{p}_logP_max', 5.0))]),
        'gap_sim': gap_sim,
        'best_model': best_model,
        'obs_delta_rv': obs_drv_analysis,
        'obs_detail': obs_detail,
        'cadence_list': cadence_list_a,
        'cadence_weights': cadence_weights_a,
        'n_stars_sim': 10000,
        'sigma_meas': float(
            st.session_state.get(f'{p}_sigma_meas', 1.622)),
        'bin_cfg': _bin_cfg_explore,
        'logP_min': float(st.session_state.get(f'{p}_logP_min', 0.15)),
        'logP_max': ana_logPmax,
        'thresh_dRV': thresh_dRV,
        'canvas_height': _ch,
        'canvas_width': _cw,
        'use_container_width': _use_cw,
        'disp_outer_slices': _cad_outer,
        'settings': _settings,
        'classification': cls,
    }

    # ── H1-H4 heatmaps (Langer-specific) ──────────────────────────────
    _hm_lp_idx = _cad_lp_idx
    _render_top_heatmaps_langer(p, _hm_result, fbin_grid, pi_grid, sigma_grid,
                                logPmax_grid, _effective_lk, _hm_lp_idx,
                                _is_dsilva, _ch, _use_cw)

    render_model_subtabs(p, model_ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Run + load/save logic (shared by both cadence variants)
# ─────────────────────────────────────────────────────────────────────────────

def _cadence_run_and_results(p: str, _is_dsilva: bool, _period_model: str,
                              fb_min, fb_max, fb_steps,
                              pi_min, pi_max, pi_steps,
                              n_sets, sigma_vals, _bin_cfg,
                              _sigma_meas, settings, sm,
                              err_info: dict = None,
                              logPmax_scan_vals: np.ndarray = None,
                              obs_override: 'np.ndarray | None' = None) -> None:
    """Shared action buttons + right column for cadence tabs."""
    _cad_tag = 'cadence_dsilva' if _is_dsilva else 'cadence_langer'

    # K-S bin edges (user-configurable or adaptive)
    _use_adaptive = bool(st.session_state.get(f'{p}_adaptive_bins', True))
    if _use_adaptive:
        from wr_bias_simulation import adaptive_bin_edges as _abe, DEFAULT_DRV_BIN_EDGES
        if obs_override is not None:
            _obs_drv_bins = obs_override
        else:
            try:
                _sh_bins = settings_hash(settings) if 'settings' in dir() else ''
                _obs_drv_bins, _ = cached_load_observed_delta_rvs(_sh_bins)
            except Exception:
                _obs_drv_bins = None
        if _obs_drv_bins is not None and len(_obs_drv_bins) > 0:
            _cad_bin_edges = _abe(_obs_drv_bins, min_gap=1.0)
        else:
            _cad_bin_edges = DEFAULT_DRV_BIN_EDGES
    else:
        from bc.params import _auto_drv_max
        _drv_bin_width = float(
            st.session_state.get(f'{p}_drv_bin_width', 5.0))
        if obs_override is not None:
            _obs_drv_bins = obs_override
        else:
            try:
                _sh_bins = settings_hash(settings)
                _obs_drv_bins, _ = cached_load_observed_delta_rvs(_sh_bins)
            except Exception:
                _obs_drv_bins = None
        _drv_max = _auto_drv_max(_obs_drv_bins, _drv_bin_width)
        _cad_bin_edges = np.arange(0.0, _drv_max, _drv_bin_width)

    # ── Load saved results ────────────────────────────────────────────────
    _cad_meta = _scan_result_metadata(_cad_tag)
    if _cad_meta is not None and len(_cad_meta) > 0:
        with st.expander(
                f'\U0001f4c2 Load saved result ({len(_cad_meta)})',
                expanded=True):
            _cad_disp = _cad_meta.drop(columns=['_path'], errors='ignore')
            _cad_sel = st.dataframe(
                _cad_disp, use_container_width=True,
                selection_mode='single-row', on_select='rerun',
                key=f'{p}_load_table',
            )
            _cad_sel_rows = (
                _cad_sel.selection.rows if _cad_sel.selection else [])
            if _cad_sel_rows:
                _cad_idx = _cad_sel_rows[0]
                _cad_sel_path = _cad_meta.iloc[_cad_idx]['_path']
                if st.session_state.get(f'{p}_loaded_path') != _cad_sel_path:
                    _cad_loaded = dict(np.load(
                        _cad_sel_path, allow_pickle=True))
                    # Backward compat: compute likelihood from logL_raw if missing
                    if 'likelihood' not in _cad_loaded and 'logL_raw' in _cad_loaded:
                        _logL = np.asarray(_cad_loaded['logL_raw'], dtype=float)
                        _logL_max = np.nanmax(_logL)
                        if np.isfinite(_logL_max):
                            _cad_loaded['likelihood'] = np.exp(_logL - _logL_max)
                        else:
                            _cad_loaded['likelihood'] = np.zeros_like(_logL)
                    # Default likelihood_bin_edges if missing
                    if 'likelihood_bin_edges' not in _cad_loaded:
                        from wr_bias_simulation import DSILVA_LIKELIHOOD_BINS
                        _cad_loaded['likelihood_bin_edges'] = DSILVA_LIKELIHOOD_BINS
                    st.session_state[f'{p}_result'] = _cad_loaded
                    st.session_state[f'{p}_loaded_path'] = _cad_sel_path
                    st.toast(
                        f"Loaded: {_cad_meta.iloc[_cad_idx]['File']}")
                    st.rerun()
                if st.button(
                        '\U0001f5d1\ufe0f Delete this result',
                        key=f'{p}_del_full'):
                    os.remove(_cad_sel_path)
                    _scan_result_metadata.clear()
                    st.session_state.pop(f'{p}_loaded_path', None)
                    st.session_state.pop(f'{p}_result', None)
                    st.toast(
                        f"Deleted: {_cad_meta.iloc[_cad_idx]['File']}")
                    st.rerun()
    else:
        st.caption('No saved results yet.')

    # ── Partial results table ─────────────────────────────────────────────
    _render_partial_table(p, _cad_tag, st)

    # Workers
    _n_proc = os.cpu_count() - 1

    # Likelihood bin edges.  If a saved result is currently loaded (e.g.
    # on the validation tab after a Load click), pass its likelihood
    # bin edges through so the widget can re-seed when the one-shot
    # `f'{p}_is_loaded_result'` flag is set.
    _default_lk_be = None
    _loaded_result = st.session_state.get(f'{p}_result')
    if _loaded_result is not None:
        _default_lk_be = _loaded_result.get('likelihood_bin_edges')
    _lk_bin_edges = _render_likelihood_bin_config(
        p, sm=sm, default_bin_edges=_default_lk_be)

    # Action buttons
    _a1, _a2, _a3, _a4 = st.columns(4)
    _run_btn = _a1.button(
        '\u25b6\ufe0f Run', key=f'{p}_run_btn', type='primary')
    _save_clicked = _a2.button(
        '\U0001f4be Save result', key=f'{p}_save_btn')
    # ── WORKING — do not change this code · cancel-save-resume ──
    _cancel_btn = _a3.button(
        '\u23f9 Cancel', key=f'{p}_cancel_btn')
    _cancel_save_btn = _a4.button(
        '\U0001f4be Cancel & Save', key=f'{p}_cancel_save_btn')

    if _save_clicked:
        _cad_cur_res = st.session_state.get(f'{p}_result')
        if _cad_cur_res is not None:
            _cad_save_kw = {
                **{k: v for k, v in _cad_cur_res.items()
                   if k not in ('timestamp', 'config_hash')},
                'config_hash': np.array('manual_save'),
                'timestamp': np.array(_dt.datetime.now().isoformat()),
            }
            _cad_desc = _build_descriptive_filename(
                _cad_tag,
                float(fb_min), float(fb_max), int(fb_steps),
                float(sigma_vals[0]) if len(sigma_vals) > 0 else 1.0,
                float(sigma_vals[-1]) if len(sigma_vals) > 0 else 15.0,
                len(sigma_vals),
                int(n_sets), np.array(sigma_vals),
                0.5, 3.5, x_label='sig',
            )
            _cad_save_path = os.path.join(_RESULT_DIR, _cad_desc)
            os.makedirs(_RESULT_DIR, exist_ok=True)
            np.savez(_cad_save_path, **_cad_save_kw)
            cached_load_grid_result.clear()
            _scan_result_metadata.clear()
            st.toast(f'Saved: {_cad_desc}')
            st.success(f'Result saved as `{_cad_desc}`.')
        else:
            st.warning('No result to save. Run first.')

    # ── WORKING — do not change this code · cancel-save-resume ──
    if _cancel_btn and f'{p}_job' in st.session_state:
        st.session_state[f'{p}_job']['cancel'] = True
        st.session_state[f'{p}_job']['cancel_mode'] = 'discard'
    if _cancel_save_btn and f'{p}_job' in st.session_state:
        st.session_state[f'{p}_job']['cancel'] = True
        st.session_state[f'{p}_job']['cancel_mode'] = 'save'

    # ── WORKING — do not change this code · cancel-save-resume ──
    _cad_auto_resume = st.session_state.pop(f'{p}_auto_resume', False)
    _job_running = (f'{p}_job' in st.session_state
                    and st.session_state[f'{p}_job'].get('status')
                    == 'running')
    if _run_btn and _job_running:
        st.warning(
            'A simulation is already running. Cancel or wait before '
            'starting a new run.')
    # ── WORKING — do not change this code · cancel-save-resume ──
    if (_run_btn or _cad_auto_resume) and not _job_running:
        _sh = settings_hash(settings)
        if obs_override is not None:
            obs_drv = obs_override
            obs_det = None
        else:
            obs_drv, obs_det = cached_load_observed_delta_rvs(_sh)
        cad_list, cad_wts = cached_load_cadence(_sh)

        fbin_vals = np.linspace(fb_min, fb_max, fb_steps).tolist()
        pi_v = (np.linspace(pi_min, pi_max, pi_steps).tolist()
                if _is_dsilva else [0.0])

        _cad_stable_cfg = {
            'n_stars_sim': len(cad_list),
            'sigma_measure': float(_sigma_meas),
            'logP_min': float(_bin_cfg.logP_min),
            'logP_max': float(_bin_cfg.logP_max),
            'period_model': _period_model,
            'e_model': str(_bin_cfg.e_model),
            'e_max': float(_bin_cfg.e_max),
            'mass_primary_model': str(_bin_cfg.mass_primary_model),
            'mass_primary_fixed': float(_bin_cfg.mass_primary_fixed),
            'q_model': str(_bin_cfg.q_model),
            'q_min': float(_bin_cfg.q_range[0]),
            'q_max': float(_bin_cfg.q_range[1]),
            'q_flipped': bool(getattr(_bin_cfg, 'q_flipped', False)),
            'primary_line': settings.get(
                'primary_line', 'C IV 5808-5812'),
            'threshold_dRV': settings.get(
                'classification', {}).get('threshold_dRV', 45.5),
            'sigma_factor': settings.get(
                'classification', {}).get('sigma_factor', 4.0),
            'adaptive_bins': _use_adaptive,
            'n_sets': n_sets,
        }
        if not _is_dsilva:
            _cad_stable_cfg['langer_period_params'] = getattr(
                _bin_cfg, 'langer_period_params', {})

        job = {
            'status': 'running',
            'progress_pct': 0.0,
            'progress_text': 'Starting...',
            'live_heatmaps': None,
            'live_status': '',
            '_last_hm': 0,
        }
        st.session_state[f'{p}_job'] = job

        params = {
            'cadence_list': cad_list, 'cadence_weights': cad_wts,
            'obs_delta_rv': obs_drv,
            'n_proc': _n_proc,
            'fbin_vals': fbin_vals, 'pi_vals': pi_v,
            'sigma_vals': sigma_vals,
            'n_sets': n_sets,
            'period_model': _period_model,
            'bin_cfg': _bin_cfg,
            'sigma_meas': _sigma_meas,
            'bin_edges': _cad_bin_edges,
            'adaptive_bins': _use_adaptive,
            'drv_bin_width': float(
                st.session_state.get(f'{p}_drv_bin_width', 5.0)),
            'drv_max': float(
                st.session_state.get(f'{p}_drv_max', 360.0)),
            'likelihood_bin_edges': _lk_bin_edges,
            'error_model_single': (err_info or {}).get(
                'type_single', 'fixed'),
            'error_params_single': (err_info or {}).get(
                'params_single', ()),
            'error_model_binary': (err_info or {}).get(
                'type_binary', 'fixed'),
            'error_params_binary': (err_info or {}).get(
                'params_binary', ()),
            'logPmax_scan_vals': (
                logPmax_scan_vals if logPmax_scan_vals is not None
                else np.array([_bin_cfg.logP_max])),
            'stable_cfg': _cad_stable_cfg,
            'save_params': {
                'mode': 'cadence_aware',
                'period_model': _period_model,
                'n_sets': n_sets,
                'adaptive_bins': _use_adaptive,
            },
        }

        # ── Validation-lane injection (added 2026-04-23) ──
        # render_validation.py stashes per-prefix validation context in
        # session_state before delegating here so cadence-run params
        # get routed to mock_results/ instead of results/. No-op for
        # non-validation runs. See app/bc/validation_io.py.
        if st.session_state.get(f'{p}_val_save_backend') == 'mock_results':
            params['save_backend'] = 'mock_results'
            params['is_validation'] = True
            params['validation_truth'] = st.session_state.get(
                f'{p}_val_truth_dict')
            params['validation_mock_detail'] = st.session_state.get(
                f'{p}_val_mock_detail')

        # ── WORKING — do not change this code · cancel-save-resume ──
        # Check for partial resume
        _cad_resume_path = st.session_state.pop(
            f'{p}_resume_from', None)
        # Sim-context guard outcome: 'ok', 'mismatch', 'legacy', 'fresh', or None
        _sim_ctx_status = None
        _sim_ctx_diffs: list[str] = []
        if _cad_resume_path and os.path.exists(_cad_resume_path):
            _cad_ptl = None
            try:
                _cad_ptl = np.load(
                    _cad_resume_path, allow_pickle=True)
                # Load likelihood arrays from checkpoint
                params['prefilled_logL_raw'] = np.asarray(
                    _cad_ptl['logL_raw']) if 'logL_raw' in _cad_ptl else None
                # Backward compat: old checkpoints may have ks_p but no logL_raw
                if params['prefilled_logL_raw'] is None and 'ks_p' in _cad_ptl:
                    params['prefilled_logL_raw'] = None  # skip old-format checkpoints
                # Override grid params from checkpoint
                params['fbin_vals'] = (
                    _cad_ptl['fbin_grid'].tolist())
                params['pi_vals'] = (
                    _cad_ptl['pi_grid'].tolist())
                params['sigma_vals'] = (
                    _cad_ptl['sigma_grid'].tolist())
                if 'logPmax_grid' in _cad_ptl:
                    params['logPmax_scan_vals'] = np.asarray(
                        _cad_ptl['logPmax_grid'])
                if 'n_sets' in _cad_ptl:
                    params['n_sets'] = int(_cad_ptl['n_sets'])
                if 'drv_bin_width' in _cad_ptl:
                    params['drv_bin_width'] = float(
                        _cad_ptl['drv_bin_width'])
                if 'drv_max' in _cad_ptl:
                    params['drv_max'] = float(
                        _cad_ptl['drv_max'])
                if 'adaptive_bins' in _cad_ptl:
                    params['adaptive_bins'] = bool(
                        _cad_ptl['adaptive_bins'])
                # Progress info
                _pf = params.get('prefilled_logL_raw')
                _n_pre = int(np.count_nonzero(~np.isnan(_pf))) if _pf is not None else 0
                _n_tot = _pf.size if _pf is not None else 1
                params['resume_from_path'] = _cad_resume_path
                st.info(
                    f'\u267b\ufe0f Resuming from checkpoint '
                    f'({_n_pre}/{_n_tot} cells, '
                    f'{_n_pre / _n_tot * 100:.0f}%).')

                # ── Simulation-context drift guard ─────────────────
                # Compare the checkpoint's sim_context against the live one.
                # On mismatch, refuse to mix incompatible cells.
                import json as _json
                _ckpt_sim_ctx_raw = (
                    _cad_ptl['sim_context']
                    if 'sim_context' in _cad_ptl.files else None)
                if _ckpt_sim_ctx_raw is None:
                    _sim_ctx_status = 'legacy'
                else:
                    try:
                        _ckpt_sim_ctx = _json.loads(
                            str(np.asarray(_ckpt_sim_ctx_raw).item()))
                    except Exception:
                        _ckpt_sim_ctx = None

                    if _ckpt_sim_ctx is None:
                        _sim_ctx_status = 'legacy'
                    else:
                        _live_sim_ctx = build_sim_context_signature(
                            stable_cfg=_cad_stable_cfg,
                            bin_cfg=_bin_cfg,
                            sigma_meas=_sigma_meas,
                            period_model=_period_model,
                            bin_edges=_cad_bin_edges,
                            likelihood_bin_edges=_lk_bin_edges,
                            error_model_single=(err_info or {}).get(
                                'type_single', 'fixed'),
                            error_params_single=(err_info or {}).get(
                                'params_single', ()),
                            error_model_binary=(err_info or {}).get(
                                'type_binary', 'fixed'),
                            error_params_binary=(err_info or {}).get(
                                'params_binary', ()),
                            cadence_list=cad_list,
                            cadence_weights=cad_wts,
                            obs_delta_rv=obs_drv,
                        )
                        _sim_ctx_diffs = diff_sim_contexts(
                            _ckpt_sim_ctx, _live_sim_ctx)
                        _sim_ctx_status = (
                            'ok' if not _sim_ctx_diffs else 'mismatch')
            except Exception as e:
                st.warning(
                    f'\u26a0\ufe0f Failed to load checkpoint: {e}')
            finally:
                if _cad_ptl is not None:
                    try:
                        _cad_ptl.close()
                    except Exception:
                        pass

        # Surface the sim-context guard result before starting the thread.
        if _sim_ctx_status == 'legacy':
            st.warning(
                '\u26a0\ufe0f Old checkpoint without sim-context signature '
                '\u2014 cannot verify safety. Resuming may produce a '
                'discontinuous heatmap. Use Resume on this checkpoint at '
                'your own risk.')
        elif _sim_ctx_status == 'mismatch':
            _diff_text = '\n'.join(_sim_ctx_diffs) if _sim_ctx_diffs else (
                '  (no field-level diff available)')
            st.error(
                '\u26a0\ufe0f **Cannot resume:** simulation context drifted '
                'since checkpoint was saved.\n\n'
                'The following parameter(s) changed:\n\n'
                f'```\n{_diff_text}\n```\n\n'
                'Resuming would mix cells computed with different parameters '
                'and bias the likelihood. Either restore the original config '
                'and try again, or click "Start fresh" to discard the '
                'checkpoint cells and recompute the full grid with the '
                'current config.')
            _bcol1, _bcol2 = st.columns(2)
            _start_fresh = _bcol1.button(
                '\u25b6\ufe0f Start fresh with current config',
                key=f'{p}_simctx_fresh', type='primary')
            _cancel_resume = _bcol2.button(
                '\u274c Cancel',
                key=f'{p}_simctx_cancel')

            if _start_fresh:
                # Discard checkpoint cells and fall through to thread start
                # with a fresh sim. Clear any re-armed signals from a prior
                # pass so we don't loop on the next rerun.
                st.session_state.pop(f'{p}_auto_resume', None)
                st.session_state.pop(f'{p}_resume_from', None)
                params['prefilled_logL_raw'] = None
                params.pop('resume_from_path', None)
                st.info('\u25b6\ufe0f Starting fresh with current config '
                        '(checkpoint cells discarded).')
                # IMPORTANT: do NOT st.stop() — fall through to thread start.
            elif _cancel_resume:
                # User explicitly cancelled. Clear the run trigger entirely.
                st.session_state.pop(f'{p}_auto_resume', None)
                st.session_state.pop(f'{p}_resume_from', None)
                st.session_state.pop(f'{p}_job', None)
                st.info('Resume cancelled. The checkpoint file is untouched.')
                st.stop()
            else:
                # No button clicked yet: re-arm so the next rerun (triggered
                # by the user clicking a button) re-enters this block,
                # re-renders the buttons at the same keys, and captures the
                # click on that rerun.
                st.session_state[f'{p}_auto_resume'] = True
                st.session_state[f'{p}_resume_from'] = _cad_resume_path
                st.session_state.pop(f'{p}_job', None)
                st.stop()

        t = threading.Thread(
            target=_run_cadence_bg, args=(job, params), daemon=True)
        t.start()
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Cadence Dsilva tab
# ─────────────────────────────────────────────────────────────────────────────

def _render_cadence_dsilva_tab(p: str, settings: dict, sm,
                               obs_override: 'np.ndarray | None' = None,
                               n_sets_override: 'int | None' = None) -> None:
    """Render Cadence-Aware simulation tab (Dsilva / power-law)."""
    _is_dsilva = True
    _period_model = 'powerlaw'
    _sec = 'grid_cadence_dsilva'

    gcfg = settings.get(_sec, {})
    orb = gcfg.get('orbital', {})
    simcfg = settings.get('simulation', {})

    _defaults = {
        f'{p}_fb_min':      float(gcfg.get('fbin_min', 0.0)),
        f'{p}_fb_max':      float(gcfg.get('fbin_max', 1.0)),
        f'{p}_fb_steps':    int(gcfg.get('fbin_steps', 100)),
        f'{p}_pi_min':      float(gcfg.get('pi_min', -3.0)),
        f'{p}_pi_max':      float(gcfg.get('pi_max', 3.0)),
        f'{p}_pi_steps':    int(gcfg.get('pi_steps', 60)),
        f'{p}_n_sets':      int(gcfg.get('n_sets', 10000)),
        f'{p}_scan_sigma':  bool(gcfg.get('scan_sigma', False)),
        f'{p}_sigma_single': float(gcfg.get('sigma_single',
            float(settings.get('grid', {}).get('sigma_single', 15.0)))),
        f'{p}_sig_min':     float(gcfg.get('sigma_min', 5.0)),
        f'{p}_sig_max':     float(gcfg.get('sigma_max', 30.0)),
        f'{p}_sig_steps':   int(gcfg.get('sigma_steps', 10)),
        f'{p}_logP_min':    float(orb.get('logP_min', 0.15)),
        f'{p}_logP_max':    float(orb.get('logP_max', 5.0)),
        f'{p}_scan_logPmax':       bool(gcfg.get('scan_logPmax', False)),
        f'{p}_logPmax_scan_min':   float(gcfg.get('logPmax_scan_min', 1.0)),
        f'{p}_logPmax_scan_max':   float(gcfg.get('logPmax_scan_max', 6.0)),
        f'{p}_logPmax_scan_steps': int(gcfg.get('logPmax_scan_steps', 15)),
        f'{p}_e_max':       float(orb.get('e_max', 0.9)),
        f'{p}_mass_fixed':  float(orb.get('mass_primary_fixed', 10.0)),
        f'{p}_q_min':       float(orb.get('q_range', [0.1, 2.0])[0]),
        f'{p}_q_max':       float(orb.get('q_range', [0.1, 2.0])[1]),
        f'{p}_lq_mu':       float(orb.get('langer_q_mu', 0.7)),
        f'{p}_lq_sig':      float(orb.get('langer_q_sigma', 0.2)),
        f'{p}_sigma_meas':  float(simcfg.get('sigma_measure', 1.622)),
        f'{p}_drv_bin_width': float(gcfg.get('drv_bin_width', 5.0)),
        f'{p}_drv_max':       float(gcfg.get('drv_max', 360.0)),
        f'{p}_adaptive_bins': bool(gcfg.get('adaptive_bins', True)),
    }
    if n_sets_override is not None and f'{p}_n_sets' not in st.session_state:
        _defaults[f'{p}_n_sets'] = int(n_sets_override)
    for _k, _v in _defaults.items():
        if _k not in st.session_state:
            st.session_state[_k] = _v

    left_col, right_col = st.columns([0.30, 0.70])

    with left_col:
        st.markdown('#### Cadence-Aware \u2014 Dsilva (power-law)')

        with st.expander('Grid parameters', expanded=True):
            _c1, _c2, _c3 = st.columns(3)
            fb_min = _c1.number_input('f_bin min', 0.0, 1.0,
                float(gcfg.get('fbin_min', 0.0)), 0.01, key=f'{p}_fb_min',
                on_change=lambda: sm.save([_sec, 'fbin_min'],
                    value=st.session_state[f'{p}_fb_min']))
            fb_max = _c2.number_input('f_bin max', 0.0, 1.0,
                float(gcfg.get('fbin_max', 1.0)), 0.01, key=f'{p}_fb_max',
                on_change=lambda: sm.save([_sec, 'fbin_max'],
                    value=st.session_state[f'{p}_fb_max']))
            fb_steps = _c3.number_input('steps', 5, 500,
                int(gcfg.get('fbin_steps', 100)), 5, key=f'{p}_fb_steps',
                on_change=lambda: sm.save([_sec, 'fbin_steps'],
                    value=st.session_state[f'{p}_fb_steps']))

            _c4, _c5, _c6 = st.columns(3)
            pi_min = _c4.number_input('\u03c0 min', -5.0, 5.0,
                float(gcfg.get('pi_min', -3.0)), 0.1, key=f'{p}_pi_min',
                on_change=lambda: sm.save([_sec, 'pi_min'],
                    value=st.session_state[f'{p}_pi_min']))
            pi_max = _c5.number_input('\u03c0 max', -5.0, 5.0,
                float(gcfg.get('pi_max', 3.0)), 0.1, key=f'{p}_pi_max',
                on_change=lambda: sm.save([_sec, 'pi_max'],
                    value=st.session_state[f'{p}_pi_max']))
            pi_steps = _c6.number_input('\u03c0 steps', 5, 500,
                int(gcfg.get('pi_steps', 60)), 5, key=f'{p}_pi_steps',
                on_change=lambda: sm.save([_sec, 'pi_steps'],
                    value=st.session_state[f'{p}_pi_steps']))

        with st.expander('Cadence-aware settings', expanded=True):
            n_sets = st.number_input('N_sets', 100, 100000,
                int(gcfg.get('n_sets', 10000)), 100, key=f'{p}_n_sets',
                on_change=lambda: sm.save([_sec, 'n_sets'],
                    value=st.session_state[f'{p}_n_sets']))
            _use_adaptive, _cad_bin_edges_d, drv_bin_width, drv_max = \
                _render_cadence_adaptive_bins(p, _sec, sm, gcfg, settings)
            _cad_err_info = _render_error_model_selector(
                p, gcfg, sm, 'grid_cadence_dsilva')
            _sigma_meas = _cad_err_info['sigma_measure']

        with st.expander('Sigma scan', expanded=False):
            sigma_vals = _render_cadence_sigma_scan(
                p, _sec, sm, gcfg, settings)

    with right_col:
        with st.expander(
                '\U0001f527 Orbital parameters (Kepler)', expanded=False):
            _orb_vals = _render_orbital_params_dsilva(
                p, _sec, sm, orb, gcfg)

        from wr_bias_simulation import BinaryParameterConfig
        _bin_cfg = BinaryParameterConfig(
            logP_min=_orb_vals['logP_min'],
            logP_max=_orb_vals['logP_max'],
            period_model='powerlaw',
            e_model=_orb_vals['e_model'], e_max=_orb_vals['e_max'],
            mass_primary_model=_orb_vals['mass_model'],
            mass_primary_fixed=_orb_vals['mass_fixed'],
            mass_primary_range=tuple(_orb_vals['mass_range']),
            q_model=_orb_vals['q_model'],
            q_range=(_orb_vals['q_min'], _orb_vals['q_max']),
            langer_q_mu=_orb_vals['lq_mu'],
            langer_q_sigma=_orb_vals['lq_sig'],
        )

        with st.expander(
                '\U0001f39a\ufe0f logP_max scan', expanded=False):
            _cd_logPmax_vals = _render_logPmax_scan(
                p, 'grid_cadence_dsilva', sm, default_logP_max=5.0)

        # Apply fixed-value (or first scan value) override to bin_cfg so the
        # logP_max actually used for simulating binary stars matches the
        # value typed in the scan expander when the scan is OFF.
        _bin_cfg = dataclasses.replace(
            _bin_cfg, logP_max=float(_cd_logPmax_vals[0]))

        _cadence_run_and_results(
            p, _is_dsilva, _period_model,
            fb_min, fb_max, fb_steps,
            pi_min, pi_max, pi_steps,
            n_sets, sigma_vals, _bin_cfg, _sigma_meas,
            settings, sm, err_info=_cad_err_info,
            logPmax_scan_vals=_cd_logPmax_vals,
            obs_override=obs_override)

    _render_cadence_results(p, _is_dsilva, _bin_cfg, settings=settings,
                            obs_override=obs_override)


# ─────────────────────────────────────────────────────────────────────────────
# Cadence Langer tab
# ─────────────────────────────────────────────────────────────────────────────

def _render_cadence_langer_tab(p: str, settings: dict, sm,
                               obs_override: 'np.ndarray | None' = None,
                               n_sets_override: 'int | None' = None) -> None:
    """Render Cadence-Aware simulation tab (Langer 2020)."""
    _is_dsilva = False
    _period_model = 'langer2020'
    _sec = 'grid_cadence_langer'

    lg_cfg = settings.get(_sec, {})
    lg_pp = lg_cfg.get('langer_period_params', {})
    simcfg = settings.get('simulation', {})

    _defaults = {
        f'{p}_fb_min':      float(lg_cfg.get('fbin_min', 0.0)),
        f'{p}_fb_max':      float(lg_cfg.get('fbin_max', 1.0)),
        f'{p}_fb_steps':    int(lg_cfg.get('fbin_steps', 100)),
        f'{p}_n_sets':      int(lg_cfg.get('n_sets', 10000)),
        f'{p}_scan_sigma':  bool(lg_cfg.get('scan_sigma', False)),
        f'{p}_sigma_single': float(lg_cfg.get('sigma_single',
            float(settings.get('grid', {}).get('sigma_single', 15.0)))),
        f'{p}_sig_min':     float(lg_cfg.get('sigma_min', 5.0)),
        f'{p}_sig_max':     float(lg_cfg.get('sigma_max', 30.0)),
        f'{p}_sig_steps':   int(lg_cfg.get('sigma_steps', 10)),
        f'{p}_sigma_meas':  float(lg_cfg.get('sigma_meas',
            float(simcfg.get('sigma_measure', 1.622)))),
        f'{p}_dist_A':      str(lg_pp.get('dist_A', 'empirical')),
        f'{p}_mu_A':        float(lg_pp.get('mu_A', 1.0)),
        f'{p}_sigma_A':     float(lg_pp.get('sigma_A', 0.12)),
        f'{p}_dist_B':      str(lg_pp.get('dist_B', 'empirical')),
        f'{p}_mu_B':        float(lg_pp.get('mu_B', 2.1)),
        f'{p}_sigma_B':     float(lg_pp.get('sigma_B', 0.2)),
        f'{p}_weight_A':    float(lg_pp.get('weight_A', 0.08)),
        f'{p}_logP_min':    float(lg_cfg.get('logP_min', 0.5)),
        f'{p}_logP_max':    float(lg_cfg.get('logP_max', 3.5)),
        f'{p}_scan_logPmax':       bool(lg_cfg.get('scan_logPmax', False)),
        f'{p}_logPmax_scan_min':   float(
            lg_cfg.get('logPmax_scan_min', 1.0)),
        f'{p}_logPmax_scan_max':   float(
            lg_cfg.get('logPmax_scan_max', 6.0)),
        f'{p}_logPmax_scan_steps': int(
            lg_cfg.get('logPmax_scan_steps', 15)),
        f'{p}_mass_fixed':  float(
            lg_cfg.get('mass_primary_fixed', 10.0)),
        f'{p}_q_min':       float(
            lg_cfg.get('q_range', [0.25, 1.65])[0]),
        f'{p}_q_max':       float(
            lg_cfg.get('q_range', [0.25, 1.65])[1]),
        f'{p}_lq_mu':       float(lg_cfg.get('langer_q_mu', 0.67)),
        f'{p}_lq_sig':      float(lg_cfg.get('langer_q_sigma', 0.39)),
        f'{p}_q_flipped':   bool(lg_cfg.get('q_flipped', False)),
        f'{p}_drv_bin_width': float(lg_cfg.get('drv_bin_width', 5.0)),
        f'{p}_drv_max':       float(lg_cfg.get('drv_max', 360.0)),
        f'{p}_adaptive_bins': bool(lg_cfg.get('adaptive_bins', True)),
    }
    if n_sets_override is not None and f'{p}_n_sets' not in st.session_state:
        _defaults[f'{p}_n_sets'] = int(n_sets_override)
    for _k, _v in _defaults.items():
        if _k not in st.session_state:
            st.session_state[_k] = _v

    left_col, right_col = st.columns([0.30, 0.70])

    with left_col:
        st.markdown('#### Cadence-Aware \u2014 Langer 2020')

        with st.expander('Grid parameters', expanded=True):
            _c1, _c2, _c3 = st.columns(3)
            fb_min = _c1.number_input('f_bin min', 0.0, 1.0,
                float(lg_cfg.get('fbin_min', 0.0)), 0.01,
                key=f'{p}_fb_min',
                on_change=lambda: sm.save([_sec, 'fbin_min'],
                    value=st.session_state[f'{p}_fb_min']))
            fb_max = _c2.number_input('f_bin max', 0.0, 1.0,
                float(lg_cfg.get('fbin_max', 1.0)), 0.01,
                key=f'{p}_fb_max',
                on_change=lambda: sm.save([_sec, 'fbin_max'],
                    value=st.session_state[f'{p}_fb_max']))
            fb_steps = _c3.number_input('steps', 5, 500,
                int(lg_cfg.get('fbin_steps', 100)), 5,
                key=f'{p}_fb_steps',
                on_change=lambda: sm.save([_sec, 'fbin_steps'],
                    value=st.session_state[f'{p}_fb_steps']))

        with st.expander('Cadence-aware settings', expanded=True):
            n_sets = st.number_input('N_sets', 100, 100000,
                int(lg_cfg.get('n_sets', 10000)), 100,
                key=f'{p}_n_sets',
                on_change=lambda: sm.save([_sec, 'n_sets'],
                    value=st.session_state[f'{p}_n_sets']))
            _use_adaptive, _cad_bin_edges_l, drv_bin_width, drv_max = \
                _render_cadence_adaptive_bins(
                    p, _sec, sm, lg_cfg, settings)
            _cl_err_info = _render_error_model_selector(
                p, lg_cfg, sm, 'grid_cadence_langer')
            _sigma_meas = _cl_err_info['sigma_measure']

        with st.expander('Sigma scan', expanded=False):
            sigma_vals = _render_cadence_sigma_scan(
                p, _sec, sm, lg_cfg, settings)

    with right_col:
        with st.expander(
                '\U0001f527 Orbital parameters (Langer 2020)',
                expanded=False):
            _cl_orb = _render_orbital_params_langer(
                p, _sec, sm, lg_pp, lg_cfg)

            from wr_bias_simulation import BinaryParameterConfig
            _period_params = {
                'dist_A': _cl_orb['dist_A'],
                'mu_A': _cl_orb['mu_A'],
                'sigma_A': _cl_orb['sigma_A'],
                'dist_B': _cl_orb['dist_B'],
                'mu_B': _cl_orb['mu_B'],
                'sigma_B': _cl_orb['sigma_B'],
                'weight_A': _cl_orb['weight_A'],
            }
            _bin_cfg = BinaryParameterConfig(
                logP_min=_cl_orb['logP_min'],
                logP_max=_cl_orb['logP_max'],
                period_model='langer2020',
                langer_period_params=_period_params,
                e_model='zero', e_max=0.0,
                mass_primary_model=_cl_orb['mass_model'],
                mass_primary_fixed=_cl_orb['mass_fixed'],
                mass_primary_range=tuple(_cl_orb['mass_range']),
                q_model=_cl_orb['q_model'],
                q_range=(_cl_orb['q_min'], _cl_orb['q_max']),
                langer_q_mu=_cl_orb['lq_mu'],
                langer_q_sigma=_cl_orb['lq_sig'],
                q_flipped=_cl_orb['q_flipped'],
            )

        with st.expander(
                '\U0001f39a\ufe0f logP_max scan', expanded=False):
            _cl_logPmax_vals = _render_logPmax_scan(
                p, 'grid_cadence_langer', sm, default_logP_max=3.5)

        # Apply fixed-value (or first scan value) override to bin_cfg so the
        # logP_max actually used for simulating binary stars matches the
        # value typed in the scan expander when the scan is OFF.
        _bin_cfg = dataclasses.replace(
            _bin_cfg, logP_max=float(_cl_logPmax_vals[0]))

        pi_min, pi_max, pi_steps = 0.0, 0.0, 1
        _cadence_run_and_results(
            p, _is_dsilva, _period_model,
            fb_min, fb_max, fb_steps,
            pi_min, pi_max, pi_steps,
            n_sets, sigma_vals, _bin_cfg, _sigma_meas,
            settings, sm, err_info=_cl_err_info,
            logPmax_scan_vals=_cl_logPmax_vals,
            obs_override=obs_override)

    _render_cadence_results_langer(p, _is_dsilva, _bin_cfg, settings=settings,
                                   obs_override=obs_override)
