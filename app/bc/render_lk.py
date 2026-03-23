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
    x_label: str = 'pi',
    x_name: str = 'pi',
    x_display_label: str = 'pi (period power-law index)',
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
    if _has_sig_slider:
        _tmp_best = np.unravel_index(int(np.nanargmax(p_nd)), p_nd.shape)
        if ndim_mode == 'dsilva':
            _default_sig = int(_tmp_best[1])  # [logPmax, sigma, fbin, pi]
        else:
            _default_sig = int(_tmp_best[0])  # [sigma, fbin, pi]
        _user_sig_idx = st.select_slider(
            f'sigma_single slice ({_DISPLAY_NAME})',
            options=list(range(len(_sigma_g_sl))),
            format_func=lambda i: f'{_sigma_g_sl[i]:.1f} km/s',
            value=_default_sig,
            key=f'{prefix}_{_METHOD_KEY}_sig_slider',
        )

    # -- logPmax slider (any mode with logPmax scan) ---------------
    _logPmax_g_sl = np.asarray(result.get('logPmax_grid', []))
    _user_lp_idx = None
    if (_logPmax_g_sl.size > 1
            and p_nd.ndim >= 3):
        _tmp_best_lp = np.unravel_index(int(np.nanargmax(p_nd)), p_nd.shape)
        _default_lp = int(_tmp_best_lp[0])
        _user_lp_idx = st.select_slider(
            f'logP_max slice ({_DISPLAY_NAME})',
            options=list(range(len(_logPmax_g_sl))),
            format_func=lambda i: f'{_logPmax_g_sl[i]:.2f}',
            value=_default_lp,
            key=f'{prefix}_{_METHOD_KEY}_lp_slider',
        )

    # -- Slice down to 2D: [fbin, x] ------------------------------
    if _user_lp_idx is not None:
        p_2d = p_nd[_user_lp_idx]
        D_2d = D_nd[_user_lp_idx] if D_nd is not None else None
    elif _user_sig_idx is not None:
        if ndim_mode == 'dsilva' and p_nd.ndim == 4:
            _lp_s = disp_outer_slices[0] if disp_outer_slices else 0
            p_2d = p_nd[_lp_s, _user_sig_idx]
            D_2d = D_nd[_lp_s, _user_sig_idx] if D_nd is not None else None
        else:
            p_2d = p_nd[_user_sig_idx]
            D_2d = D_nd[_user_sig_idx] if D_nd is not None else None
    elif disp_outer_slices is not None and p_nd.ndim > 2:
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

    # For cadence_langer: sliced p_2d may be [sigma, fbin] -> transpose
    if (ndim_mode == 'cadence_langer'
            and p_2d.ndim == 2
            and p_2d.shape[0] != len(fbin_g)
            and p_2d.shape[1] == len(fbin_g)):
        p_2d = p_2d.T
        if D_2d is not None:
            D_2d = D_2d.T

    # -- Global best across all dimensions -------------------------
    valid = np.isfinite(p_nd)
    if not np.any(valid):
        st.warning(f'No valid data for {_DISPLAY_NAME}.')
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
    if ndim_mode == 'dsilva':
        g_fb = float(fbin_g[global_best_idx[2]])
        g_x = float(x_g[global_best_idx[3]])
    elif ndim_mode == 'cadence_dsilva':
        g_fb = float(fbin_g[global_best_idx[-2]])
        g_x = float(x_g[global_best_idx[-1]])
    elif ndim_mode == 'cadence_langer':
        if p_nd.ndim == 3:
            g_fb = float(fbin_g[global_best_idx[2]])
            g_x = float(x_g[global_best_idx[1]])
        else:
            g_fb = float(fbin_g[global_best_idx[0]])
            g_x = float(x_g[global_best_idx[1]])
    else:
        g_fb = float(fbin_g[global_best_idx[0]])
        g_x = float(x_g[global_best_idx[1]])

    # -- D1: Primary heatmap --------------------------------------
    fig_hm = make_heatmap_fig(
        p_2d, fbin_g, x_g,
        title=f'{_DISPLAY_NAME} -- {_SCORE_LABEL}',
        show_d=False,
        height=height, width=width,
        x_label=x_display_label,
        x_name=x_name,
        scoring_label=_DISPLAY_NAME,
        colorbar_title_override='Normalized Likelihood',
    )
    st.plotly_chart(fig_hm, use_container_width=use_cw,
                    key=f'{prefix}_{_METHOD_KEY}_hm')

    # -- D2-D3: REMOVED (covered by A3 σ×logPmax heatmap upgrade) --

    # -- D4: Best-fit metrics -------------------------------------
    _is_2d_mode = ndim_mode in ('langer', 'cadence_langer') or p_nd.ndim <= 2
    if _is_2d_mode:
        st.metric(
            label=f'Best fit ({_DISPLAY_NAME})',
            value=f'f_bin={g_fb:.4f}, {x_label}={g_x:.3f}',
            delta=f'{_SCORE_LABEL} = {global_best_score:.6f}',
            delta_color='off',
        )
    else:
        mc1, mc2 = st.columns(2)
        mc1.metric(
            label=f'Current slice best ({_DISPLAY_NAME})',
            value=f'f_bin={slice_best_fb:.4f}, {x_label}={slice_best_x:.3f}',
            delta=f'{_SCORE_LABEL} = {slice_best_score:.6f}',
            delta_color='off',
        )
        mc2.metric(
            label=f'Global best ({_DISPLAY_NAME})',
            value=f'f_bin={g_fb:.4f}, {x_label}={g_x:.3f}',
            delta=f'{_SCORE_LABEL} = {global_best_score:.6f}',
            delta_color='off',
        )

    # -- Likelihood scoring detail ---------------------------------
    _sigma_g_fit = np.asarray(result.get('sigma_grid', []))
    _logPmax_g_fit = np.asarray(result.get('logPmax_grid', []))
    _full_D_3d = None
    _full_p_3d = None
    _raw_D = _get_method_array(result, _D_KEY)
    _raw_p = _get_method_array(result, _P_KEY)

    if _sigma_g_fit.size > 1 and _raw_D is not None:
        if ndim_mode == 'dsilva' and _raw_D.ndim == 4:
            _lp_idx = disp_outer_slices[0] if disp_outer_slices else 0
            _full_D_3d = _raw_D[_lp_idx]
            _full_p_3d = _raw_p[_lp_idx] if _raw_p is not None else None
        elif _raw_D.ndim == 3:
            _full_D_3d = _raw_D
            _full_p_3d = _raw_p
    elif _logPmax_g_fit.size > 1 and _raw_D is not None:
        if _raw_D.ndim >= 3:
            if _raw_D.ndim == 4:
                _sig_idx = (
                    disp_outer_slices[1]
                    if (disp_outer_slices and len(disp_outer_slices) > 1)
                    else 0
                )
                _full_D_3d = _raw_D[:, _sig_idx, :, :]
                _full_p_3d = (
                    _raw_p[:, _sig_idx, :, :]
                    if _raw_p is not None else None
                )
            else:
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
        from bc.render_lk_scoring import render_lk_scoring_detail
        render_lk_scoring_detail(
            lk_D_2d=D_2d if D_2d is not None else p_2d,
            lk_p_2d=p_2d,
            x_grid=fbin_g,
            y_grid=x_g,
            x_label='f_bin',
            y_label=x_label,
            sigma_grid=_sigma_g_fit if _sigma_g_fit.size > 1 else None,
            logPmax_grid=(
                _logPmax_g_fit
                if (_logPmax_g_fit.size > 1 and _sigma_g_fit.size <= 1)
                else None
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
        from bc.render_lk_fit import _render_lk_corner_plot
        _info = _render_lk_corner_plot(
            p_nd, fbin_g, x_g, x_name, x_display_label,
            ndim_mode,
            result, prefix, pal, use_cw,
        )
    except ImportError:
        _info = None

    # -- Per-method best-fit summary table -------------------------
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

        _interp_key = f'{prefix}_interp'
        _interp = st.session_state.get(_interp_key)

        _sum_rows = []
        _row_fb = {
            'Parameter': 'f_bin',
            'Best (grid)': f"{_bv_s.get('fbin', 0):.4f}",
            'Mode +/- HDI68': _fmt_hdi_s('fbin', '.4f'),
        }
        if _interp and 'f_bin' in _interp:
            _row_fb['Interpolated'] = f"{_interp['f_bin']:.4f}"
        _sum_rows.append(_row_fb)

        if x_name in _bv_s:
            _row_x = {
                'Parameter': x_label,
                'Best (grid)': f"{_bv_s[x_name]:.3f}",
                'Mode +/- HDI68': _fmt_hdi_s(x_name, '.3f'),
            }
            if _interp:
                _iv = _interp.get('pi', _interp.get('sigma',
                      _interp.get('y_val')))
                _row_x['Interpolated'] = (
                    f'{_iv:.3f}' if _iv is not None else '--'
                )
            _sum_rows.append(_row_x)

        if 'sigma' in _bv_s and x_name != 'sigma':
            _row_sig = {
                'Parameter': 'sigma_single (km/s)',
                'Best (grid)': f"{_bv_s['sigma']:.2f}",
                'Mode +/- HDI68': _fmt_hdi_s('sigma', '.2f'),
            }
            if _interp and 'sigma' in _interp:
                _row_sig['Interpolated'] = f"{_interp['sigma']:.2f}"
            _sum_rows.append(_row_sig)

        if 'logPmax' in _bv_s:
            _row_lp = {
                'Parameter': 'logP_max',
                'Best (grid)': f"{_bv_s['logPmax']:.2f}",
                'Mode +/- HDI68': _fmt_hdi_s('logPmax', '.2f'),
            }
            if _interp and 'logPmax' in _interp:
                _row_lp['Interpolated'] = f"{_interp['logPmax']:.2f}"
            _sum_rows.append(_row_lp)

        _row_score = {
            'Parameter': _SCORE_LABEL,
            'Best (grid)': f"{_info['best_score']:.6f}",
            'Mode +/- HDI68': '--',
        }
        if _interp and 'S' in _interp:
            _row_score['Interpolated'] = f"{_interp['S']:.6f}"
        _sum_rows.append(_row_score)

        st.table(pd.DataFrame(_sum_rows))

        # -- D16: Re-simulate at interpolated best-fit ----------------
        if _interp is not None:
            try:
                from bc.render_lk_explorer import _render_lk_resim_interp
                _render_lk_resim_interp(
                    _interp, result, x_label,
                    pfx=f'{prefix}_{_METHOD_KEY}',
                )
            except ImportError:
                pass

    # -- Model Explorer --------------------------------------------
    _obs_drv_me = result.get('obs_delta_rv')
    if _obs_drv_me is not None and _info is not None:
        st.divider()
        with st.expander(f'Model Explorer -- {_DISPLAY_NAME}', expanded=False):
            try:
                from bc.render_lk_explorer import _render_lk_model_explorer
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
                from bc.render_lk_explorer import _render_lk_cdf_sanity_check
                _render_lk_cdf_sanity_check(
                    _bv.get('fbin', 0.5),
                    _bv.get(x_name, 0.0),
                    _bv.get('sigma', float(result.get('sigma_meas', 5.0))),
                    np.asarray(_osc), _pm, result, {},
                    f'{prefix}_{_METHOD_KEY}',
                )
            except Exception:
                pass
