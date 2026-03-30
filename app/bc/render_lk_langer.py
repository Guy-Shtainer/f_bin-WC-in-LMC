"""bc.render_lk -- Likelihood entry point + heatmaps.

Renders the detailed analysis view when the user selects "Likelihood"
in the scoring method radio button.  Self-contained: copies all needed
helpers (no imports from render_ks.py, analysis.py, or scoring_detail.py).
"""
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

from shared import (
    find_best_grid_point, make_heatmap_fig,
    PLOTLY_THEME, get_palette,
)
# Keys hardcoded for Likelihood
_METHOD_KEY = 'likelihood'
_DISPLAY_NAME = 'Likelihood'
_P_KEY = 'likelihood'
_D_KEY = 'logL_raw'
_SCORE_LABEL = 'Normalized Likelihood'
_METHOD_COLOR = '#DAA520'


# ---------------------------------------------------------------------------
# Helper: safely retrieve scoring array
# ---------------------------------------------------------------------------

def _get_method_array(result: dict, key: str) -> np.ndarray | None:
    """Safely retrieve and convert a scoring array from result dict."""
    arr = result.get(key)
    if arr is None:
        return None
    arr = np.asarray(arr, dtype=float)
    if not np.any(np.isfinite(arr)):
        return None
    return arr


# ---------------------------------------------------------------------------
# Helper: ensure correct dimensionality
# ---------------------------------------------------------------------------

def _ensure_nd(arr: np.ndarray | None, ctx: dict) -> np.ndarray | None:
    """Pad a scoring array to the expected number of dimensions for the model."""
    if arr is None:
        return None
    if ctx['ndim_mode'] == 'dsilva':
        # Dsilva expects 4D: (logPmax, sigma, fbin, pi)
        if arr.ndim == 2:
            arr = arr[np.newaxis, np.newaxis, ...]
        elif arr.ndim == 3:
            arr = arr[np.newaxis, ...]
    return arr


# ---------------------------------------------------------------------------
# Helper: max score vs scan variable line chart
# ---------------------------------------------------------------------------

def _make_max_score_fig(
    sigma_vals: np.ndarray,
    max_scores: list[float],
    height: int = 300,
    x_label: str = 'sigma_single',
    stat_label: str = 'Likelihood',
) -> go.Figure:
    """Line chart: max score vs a scan variable."""
    best_idx = int(np.argmax(max_scores))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sigma_vals, y=max_scores,
        mode='lines+markers',
        marker=dict(size=8, color=_METHOD_COLOR),
        line=dict(color=_METHOD_COLOR, width=2),
        hovertemplate=(
            f'{x_label}=%{{x:.2f}}<br>'
            f'max {stat_label}=%{{y:.4f}}<extra></extra>'
        ),
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=[float(sigma_vals[best_idx])],
        y=[max_scores[best_idx]],
        mode='markers+text',
        marker=dict(symbol='star', size=16, color='gold',
                    line=dict(color='black', width=1)),
        text=[
            f'  {x_label}={float(sigma_vals[best_idx]):.2f}, '
            f'{stat_label}={max_scores[best_idx]:.4f}'
        ],
        textposition='middle right',
        textfont=dict(color='gold', size=11),
        showlegend=False,
    ))
    fig.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(
            text=f'Max {stat_label} vs {x_label}',
            font=dict(size=14),
        ),
        'xaxis_title': x_label,
        'yaxis_title': f'Max {stat_label}',
        'height': height,
        'margin': dict(l=60, r=20, t=50, b=50),
    })
    return fig


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_lk_tab(p: str, ctx: dict, method_results: dict) -> None:
    """Render Likelihood detailed analysis tab.

    Parameters
    ----------
    p : str
        Unique key prefix for this model tab (e.g. 'ds', 'lg', 'cd', 'cl').
    ctx : dict
        Context dict built by the calling model tab.  Must contain at minimum:
        result, fbin_g, x_g, x_name, x_label, ndim_mode, model_type.
    method_results : dict
        All methods' best-fit info (from _render_method_summary_section).
    """
    result = ctx['result']

    p_nd = _get_method_array(result, _P_KEY)
    D_nd = _get_method_array(result, _D_KEY)

    if p_nd is None:
        st.info(f'No **{_DISPLAY_NAME}** data in this result.')
        return

    # Ensure correct dimensionality
    p_nd = _ensure_nd(p_nd, ctx)
    D_nd = _ensure_nd(D_nd, ctx)

    # A3: Max likelihood vs σ/logPmax — now rendered inside D5a right panel
    # (render_lk_scoring.py handles it)

    _render_lk_expander(
        p_nd=p_nd,
        D_nd=D_nd,
        result=result,
        fbin_g=ctx['fbin_g'],
        x_g=ctx['x_g'],
        prefix=p,
        height=ctx.get('canvas_height', 520),
        width=ctx.get('canvas_width'),
        use_cw=ctx.get('use_container_width', True),
        x_label=ctx['x_label'],
        x_name=ctx['x_name'],
        x_display_label=ctx.get('x_display_label', ctx['x_label']),
        ndim_mode=ctx['ndim_mode'],
        disp_outer_slices=ctx.get('disp_outer_slices'),
        method_results=method_results,
    )


# ---------------------------------------------------------------------------
# Likelihood expander -- primary heatmap + extra heatmaps + metrics + profiles
# ---------------------------------------------------------------------------

# WORKING — do not change this code (D1: Primary Heatmap, D4: Metric Cards)
def _render_lk_expander(
    p_nd: np.ndarray,
    D_nd: np.ndarray | None,
    result: dict,
    fbin_g: np.ndarray,
    x_g: np.ndarray,
    prefix: str,
    height: int = 520,
    width: int | None = None,
    use_cw: bool = True,
    x_label: str = 'π',
    x_name: str = 'pi',
    x_display_label: str = 'π (period power-law index)',
    ndim_mode: str = 'dsilva',
    disp_outer_slices: tuple[int, ...] | None = None,
    method_results: dict | None = None,
) -> None:
    """Render Likelihood detail panel.

    Shows: D1 primary heatmap, D2-D3 extra heatmaps (multi-axis),
    D4 best-fit metrics, D12 sigma profile, D13 logPmax profile.
    Calls out to render_lk_scoring_detail for scoring analysis.
    """
    _theme = PLOTLY_THEME
    pal = get_palette()

    # -- Squeeze trailing pi=1 dimension for cadence_langer --------
    if ndim_mode == 'cadence_langer' and p_nd.ndim >= 3 and p_nd.shape[-1] == 1:
        p_nd = p_nd[..., 0]
        if D_nd is not None:
            D_nd = D_nd[..., 0]

    # -- Per-method sigma slider (when sigma has >1 values) --------
    _sigma_g_sl = np.asarray(result.get('sigma_grid', []))
    _has_sig_slider = (
        _sigma_g_sl.size > 1
        and p_nd.ndim >= 3
        and ndim_mode not in ('langer', 'cadence_langer')
    )
    _user_sig_idx = None
    _default_sig = 0
    _default_lp = 0
    _logPmax_g_sl = np.asarray(result.get('logPmax_grid', []))
    _has_lp_slider = (_logPmax_g_sl.size > 1 and p_nd.ndim >= 3)

    # Compute best indices for both sliders
    _tmp_best_global = np.unravel_index(int(np.nanargmax(p_nd)), p_nd.shape)
    if _has_sig_slider:
        if ndim_mode == 'dsilva':
            _default_sig = int(_tmp_best_global[1])
        else:
            _default_sig = int(_tmp_best_global[0])
    if _has_lp_slider:
        _default_lp = int(_tmp_best_global[0])

    # -- Top sliders REMOVED — D1 always shows best-fit slice ------
    # Sliders moved to Model Explorer (render_lk_explorer.py)
    _user_sig_idx = _default_sig if _has_sig_slider else None
    _user_lp_idx = _default_lp if _has_lp_slider else None

    # D1 caption/cards REMOVED — heatmaps moved to top (_render_top_heatmaps)

    # -- Langer: explicit 2D slicing based on actual scanned axes ----
    # Array after pi squeeze: [logP?, sigma?, fbin]
    # Primary axis = f_bin. Secondary = logP_max (preferred) or σ.
    _sigma_g_fit = np.asarray(result.get('sigma_grid', []))
    _logPmax_g_fit = np.asarray(result.get('logPmax_grid', []))
    _has_lp_fit = _logPmax_g_fit.size > 1
    _has_sig_fit = _sigma_g_fit.size > 1

    # Get raw logL for D_2d (the interpolation uses raw logL, not normalized)
    _raw_D = _get_method_array(result, _D_KEY)
    _raw_p = _get_method_array(result, _P_KEY)
    # Squeeze pi from D_nd same as p_nd
    D_nd = _raw_D
    if D_nd is not None and ndim_mode == 'cadence_langer' and D_nd.ndim >= 3 and D_nd.shape[-1] == 1:
        D_nd = D_nd[..., 0]

    # Helper to apply same slicing to both p_nd and D_nd
    def _slice_2d(arr):
        """Slice ND array to 2D [fbin, y_axis] for Langer."""
        if arr is None:
            return None
        if _has_lp_fit and _has_sig_fit:
            _best_sig = disp_outer_slices[-1] if disp_outer_slices else 0
            if arr.ndim == 3:
                s = arr[:, _best_sig, :] if arr.shape[1] == _sigma_g_fit.size else arr[_best_sig]
            else:
                s = arr
        elif _has_lp_fit:
            if arr.ndim == 3 and arr.shape[1] == 1:
                s = arr[:, 0, :]
            elif arr.ndim == 2:
                s = arr
            else:
                s = arr
                while s.ndim > 2:
                    for ax in range(s.ndim):
                        if s.shape[ax] == 1:
                            s = np.squeeze(s, axis=ax); break
                    else:
                        s = s[0]
        elif _has_sig_fit:
            if arr.ndim > 2:
                s = arr
                while s.ndim > 2:
                    for ax in range(s.ndim):
                        if s.shape[ax] == 1:
                            s = np.squeeze(s, axis=ax); break
                    else:
                        s = s[0]
            else:
                s = arr
        else:
            return arr.ravel()[:len(fbin_g)] if arr.size >= len(fbin_g) else arr.ravel()
        if s.ndim == 2 and s.shape[0] != len(fbin_g):
            s = s.T
        return s

    p_2d = _slice_2d(p_nd)
    D_2d = _slice_2d(D_nd)

    # Determine secondary axis
    if _has_lp_fit:
        _y_grid_actual = _logPmax_g_fit
        _y_label_actual = 'log₁₀(P_max)'
    elif _has_sig_fit:
        _y_grid_actual = _sigma_g_fit
        _y_label_actual = 'σ_single (km/s)'
    else:
        _y_grid_actual = None
        _y_label_actual = None

    # Ensure 2D for 2-grid cases
    if _y_grid_actual is not None and p_2d.ndim != 2:
        while p_2d.ndim > 2:
            p_2d = p_2d[0]
        if D_2d is not None:
            while D_2d.ndim > 2:
                D_2d = D_2d[0]

    valid = np.isfinite(p_nd)
    if not np.any(valid):
        st.warning(f'No valid data for {_DISPLAY_NAME}.')
        return

    # -- Build 3D arrays for sigma interpolation (when 3 grids) ----
    _full_D_3d = None
    _full_p_3d = None

    if _has_sig_fit and _has_lp_fit and _raw_D is not None:
        if _raw_D.ndim >= 3:
            _full_D_3d = _raw_D
            _full_p_3d = _raw_p
    elif _has_sig_fit and _raw_D is not None:
        if _raw_D.ndim >= 3:
            _full_D_3d = _raw_D
            _full_p_3d = _raw_p

    # Likelihood bin edges for CDF / stats
    _lk_bin_edges = result.get('likelihood_bin_edges')
    if _lk_bin_edges is None:
        try:
            from wr_bias_simulation import DSILVA_LIKELIHOOD_BINS
            _lk_bin_edges = DSILVA_LIKELIHOOD_BINS
        except ImportError:
            _lk_bin_edges = np.array([0.0, 45.5, 250.0, 650.0, np.inf])
    _lk_bin_edges = np.asarray(_lk_bin_edges)

    try:
        from bc.render_lk_scoring_langer import render_lk_scoring_detail
        render_lk_scoring_detail(
            lk_D_2d=D_2d if D_2d is not None else p_2d,
            lk_p_2d=p_2d,
            x_grid=fbin_g,
            y_grid=_y_grid_actual,
            x_label='f_bin',
            y_label=_y_label_actual,
            sigma_grid=_sigma_g_fit if _sigma_g_fit.size > 1 else None,
            logPmax_grid=(
                _logPmax_g_fit if _logPmax_g_fit.size > 1 else None
            ),
            lk_D_3d=_full_D_3d,
            lk_p_3d=_full_p_3d,
            height=height,
            width=width,
            prefix=f'{prefix}_{_METHOD_KEY}_analysis',
            obs_delta_rv=result.get('obs_delta_rv'),
            likelihood_bin_edges=_lk_bin_edges,
            result=result,
        )
    except ImportError:
        st.warning('render_lk_scoring module not available.')

    # -- D12, D13: REMOVED (covered by A3 σ/logPmax upgrade) ------

    # -- Corner plot -----------------------------------------------
    try:
        from bc.render_lk_fit_langer import _render_lk_corner_plot
        _info = _render_lk_corner_plot(
            p_nd, fbin_g, x_g, x_name, x_display_label,
            ndim_mode,
            result, prefix, pal, use_cw,
        )
    except ImportError:
        _info = None

    # ── D15: Summary table + cadence-aware re-sim (fixed 2026-03-30, pending user approval) ──
    if _info is not None:
        import pandas as pd
        st.divider()
        st.markdown(f'#### Best-fit Summary -- {_DISPLAY_NAME}')
        _bv_s = _info['best_vals']
        _hdi_s = _info['hdi']

        def _fmt_hdi_s(name, fmt='.3f'):
            if name not in _hdi_s:
                return '--'
            m, lo, hi = _hdi_s[name]
            return f'{m:{fmt}} +{hi - m:{fmt}} / -{m - lo:{fmt}}'

        _interp_key = f'{prefix}_{_METHOD_KEY}_analysis_interp'
        _interp = st.session_state.get(_interp_key)

        # N_sets for re-sim (changing + Enter auto-triggers re-sim)
        _n_sets_resim = st.number_input(
            'N_sets for re-simulation at interpolated best-fit',
            min_value=100, max_value=50000, value=1000, step=100,
            key=f'{prefix}_{_METHOD_KEY}_n_sets_resim',
        )

        # Auto re-sim at interpolated point using cadence-aware simulation
        _resim_score = None
        if _interp is not None:
            try:
                from wr_bias_simulation import (
                    simulate_delta_rv_cadence_aware, SimulationConfig,
                    BinaryParameterConfig, multinomial_log_likelihood,
                    DEFAULT_DRV_BIN_EDGES,
                )
                _rs_fb = float(_interp.get('f_bin', 0.5))
                _rs_xv = float(_interp.get('y_val', 0.0))
                _rs_sig = float(_bv_s.get('sigma',
                                result.get('sigma_meas', 5.0)))
                _rs_sigma_meas = float(result.get('sigma_meas', 3.0))
                _cadence_lib = result.get('cadence_library')
                _rs_be = (np.asarray(result['bin_edges'])
                          if 'bin_edges' in result else DEFAULT_DRV_BIN_EDGES)
                _rs_lk_be = (np.asarray(result['likelihood_bin_edges'])
                             if 'likelihood_bin_edges' in result else _rs_be)
                _rs_sim_cfg = SimulationConfig(
                    n_stars=len(_cadence_lib),
                    sigma_single=_rs_sig,
                    sigma_measure=_rs_sigma_meas,
                    cadence_library=_cadence_lib,
                    cadence_weights=result.get('cadence_weights'),
                )
                _rs_period = result.get('period_model', 'powerlaw')
                _rs_bin_cfg = BinaryParameterConfig(
                    period_model=_rs_period)
                _rs_result = simulate_delta_rv_cadence_aware(
                    _rs_fb, _rs_xv, _rs_sim_cfg, _rs_bin_cfg,
                    np.random.default_rng(42),
                    n_sets=int(_n_sets_resim),
                    bin_edges=_rs_be,
                )
                _rs_pooled = _rs_result['all_delta_rv'].ravel()
                _rs_obs = np.asarray(result.get('obs_delta_rv', []))
                _resim_score = float(multinomial_log_likelihood(
                    _rs_obs, _rs_pooled, _rs_lk_be))
            except Exception:
                _resim_score = None

        _sum_rows = []
        _row_fb = {
            'Parameter': 'f_bin',
            'Best (grid)': f"{_bv_s.get('fbin', 0):.4f}",
            'Mode ± HDI68': _fmt_hdi_s('fbin', '.4f'),
        }
        if _interp and 'f_bin' in _interp:
            _row_fb['Interpolated'] = f"{_interp['f_bin']:.4f}"
            _row_fb['Re-sim'] = f"{_interp['f_bin']:.4f}"
        _sum_rows.append(_row_fb)

        if x_name in _bv_s:
            _row_x = {
                'Parameter': 'π' if x_name == 'pi' else x_label,
                'Best (grid)': f"{_bv_s[x_name]:.3f}",
                'Mode ± HDI68': _fmt_hdi_s(x_name, '.3f'),
            }
            if _interp:
                _iv = _interp.get('y_val')
                _row_x['Interpolated'] = (
                    f'{_iv:.3f}' if _iv is not None else '--'
                )
                _row_x['Re-sim'] = _row_x['Interpolated']
            _sum_rows.append(_row_x)
        elif x_name == 'sigma':
            # σ_single was constant (not scanned) — show fixed value
            _const_sig = np.asarray(result.get('sigma_grid', [0.0]))
            _csv = float(_const_sig[0]) if _const_sig.size > 0 else 0.0
            _sum_rows.append({
                'Parameter': 'σ_single (km/s)',
                'Best (grid)': f'{_csv:.2f} (constant)',
                'Mode ± HDI68': '--',
            })

        if 'sigma' in _bv_s and x_name != 'sigma':
            _row_sig = {
                'Parameter': 'σ_single (km/s)',
                'Best (grid)': f"{_bv_s['sigma']:.2f}",
                'Mode ± HDI68': _fmt_hdi_s('sigma', '.2f'),
            }
            _row_sig['Re-sim'] = f"{_bv_s['sigma']:.2f} (grid)"
            _sum_rows.append(_row_sig)

        if 'logPmax' in _bv_s:
            _row_lp = {
                'Parameter': 'log₁₀(P_max)',
                'Best (grid)': f"{_bv_s['logPmax']:.2f}",
                'Mode ± HDI68': _fmt_hdi_s('logPmax', '.2f'),
            }
            _row_lp['Re-sim'] = f"{_bv_s['logPmax']:.2f} (grid)"
            _sum_rows.append(_row_lp)

        # Normalized likelihood row
        _logL_raw_arr = result.get('logL_raw')
        _row_score = {
            'Parameter': _SCORE_LABEL,
            'Best (grid)': f"{_info['best_score']:.6f}",
            'Mode ± HDI68': '--',
        }
        if _interp and 'S' in _interp and _logL_raw_arr is not None:
            _lr_max = float(np.nanmax(np.asarray(_logL_raw_arr, dtype=float)))
            _norm_interp = float(np.exp(_interp['S'] - _lr_max))
            _row_score['Interpolated'] = f"{_norm_interp:.6f} *"
        _sum_rows.append(_row_score)

        # Raw logL row (grid best + interpolated + re-sim)
        _row_logL = {
            'Parameter': 'Likelihood (logL)',
            'Best (grid)': '--',
            'Mode ± HDI68': '--',
        }
        if _logL_raw_arr is not None:
            _lr = np.asarray(_logL_raw_arr, dtype=float)
            _bf_idx = np.unravel_index(
                int(np.nanargmax(_lr)), _lr.shape)
            _row_logL['Best (grid)'] = f"{float(_lr[_bf_idx]):.4f}"
        if _interp and 'S' in _interp:
            _row_logL['Interpolated'] = f"{_interp['S']:.4f}"
        if _resim_score is not None:
            _row_logL['Re-sim'] = f"{_resim_score:.4f}"
        _sum_rows.append(_row_logL)

        _df = pd.DataFrame(_sum_rows)
        _df.index = range(1, len(_df) + 1)
        st.table(_df)
        if _interp and 'S' in _interp:
            st.caption('\\* Normalized from interpolated logL using grid normalization: exp(logL_interp − logL_max)')

    # -- Model Explorer --------------------------------------------
    _obs_drv_me = result.get('obs_delta_rv')
    if _obs_drv_me is not None and _info is not None:
        st.divider()
        with st.expander(f'Model Explorer -- {_DISPLAY_NAME}', expanded=False):
            try:
                from bc.render_lk_explorer_langer import _render_lk_model_explorer
                _render_lk_model_explorer(
                    result, _DISPLAY_NAME,
                    fbin_g, x_g, x_name, x_label,
                    prefix, _info, p_nd,
                )
            except ImportError:
                st.info('Likelihood model explorer not available.')

    # -- CDF sanity check (cadence tabs) ---------------------------
    if ndim_mode in ('cadence_dsilva', 'cadence_langer') and _info is not None:
        _osc = result.get('obs_delta_rv')
        if _osc is not None:
            _bv = _info['best_vals']
            _pm = 'dsilva' if ndim_mode == 'cadence_dsilva' else 'langer'
            try:
                from bc.render_lk_explorer_langer import _render_lk_cdf_sanity_check
                _render_lk_cdf_sanity_check(
                    _bv.get('fbin', 0.5),
                    _bv.get(x_name, 0.0),
                    _bv.get('sigma', float(result.get('sigma_meas', 5.0))),
                    np.asarray(_osc), _pm, result,
                    f'{prefix}_{_METHOD_KEY}',
                )
            except Exception:
                pass
