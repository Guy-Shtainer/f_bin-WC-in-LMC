"""bc.render_shared — ALL shared graphs rendered BEFORE the scoring method radio selector.

Self-contained module: does NOT import from analysis.py, sim_plots.py, or subtabs.py.
Contains copied implementations of every function needed for the shared section.
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from shared import make_heatmap_fig, find_best_grid_point, PLOTLY_THEME, get_palette
from bc.helpers import SCORING_METHODS, _METHOD_COLORS, _RESULT_DIR, smooth_pooled_cdf


def _binned_cdf(data: np.ndarray, bin_edges: np.ndarray) -> np.ndarray:
    """Empirical CDF at bin_edges."""
    sorted_data = np.sort(data)
    return np.searchsorted(sorted_data, bin_edges, side='right') / len(sorted_data)

# Shared colors
_CLR_DETECTED = '#E25A53'
_CLR_MISSED   = '#F5A623'
_CLR_ALL      = '#52B788'
_CLR_OBS      = '#4A90D9'
_CLR_CASE_A   = '#4A90D9'
_CLR_CASE_B   = '#F5A623'

# ── Helpers ──────────────────────────────────────────────────────────────────

def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Convert hex color to rgba string for Plotly shading."""
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'rgba({r},{g},{b},{alpha})'

def _make_max_pval_fig(
    sigma_vals: np.ndarray, max_pvals: list[float],
    height: int = 300, x_label: str = '\u03c3_single', stat_label: str = 'K-S',
) -> go.Figure:
    """Line chart: max score vs a scan variable."""
    best_idx = int(np.argmax(max_pvals))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sigma_vals, y=max_pvals, mode='lines+markers',
        marker=dict(size=8, color='#4A90D9'),
        line=dict(color='#4A90D9', width=2),
        hovertemplate=f'{x_label}=%{{x:.2f}}<br>max {stat_label}=%{{y:.4f}}<extra></extra>',
        showlegend=False))
    fig.add_trace(go.Scatter(
        x=[float(sigma_vals[best_idx])], y=[max_pvals[best_idx]],
        mode='markers+text',
        marker=dict(symbol='star', size=16, color='#DAA520',
                    line=dict(color='black', width=1)),
        text=[f'  {x_label}={float(sigma_vals[best_idx]):.2f}, {stat_label}={max_pvals[best_idx]:.4f}'],
        textposition='middle right', textfont=dict(color='#DAA520', size=11),
        showlegend=False))
    fig.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(text=f'Max {stat_label} vs {x_label}', font=dict(size=14)),
        'xaxis_title': x_label, 'yaxis_title': f'Max {stat_label}',
        'height': height, 'margin': dict(l=60, r=20, t=50, b=50),
    })
    # A&A override: white bg + serif (WCAG-safe goldenrod star marker above).
    try:
        from bc.render_validation import _AA_OVERRIDES
        fig.update_layout(**_AA_OVERRIDES)
        fig.update_xaxes(**_AA_OVERRIDES['xaxis'])
        fig.update_yaxes(**_AA_OVERRIDES['yaxis'])
    except Exception:
        pass
    return fig

def _safe_mask(arr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Apply boolean mask, returning empty array if source is empty."""
    return arr[mask] if arr.size > 0 else np.array([])

# ── From analysis.py ─────────────────────────────────────────────────────────

def _get_method_array(result: dict, key: str) -> np.ndarray | None:
    """Safely retrieve and convert a scoring array from result dict."""
    arr = result.get(key)
    if arr is None:
        return None
    arr = np.asarray(arr, dtype=float)
    if not np.any(np.isfinite(arr)):
        return None
    return arr

def _method_best_and_hdi(
    p_nd: np.ndarray, grids: list[np.ndarray],
    grid_names: list[str], is_likelihood: bool = False,
) -> dict:
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

# WORKING — do not change this code (A1: Summary Table)
def _render_method_summary_section(
    result: dict, fbin_g: np.ndarray, x_g: np.ndarray,
    extra_grids: list[tuple[str, np.ndarray]] | None = None,
    prefix: str = 'ds', x_name: str = 'pi',
    x_label: str = 'π', ndim_mode: str = 'dsilva',
) -> dict:
    """Render a comparison table of all scoring methods.
    Returns method_results dict mapping method_key -> {best_vals, hdi, ...}.
    """
    # Build ordered grid list matching array dimensions
    if ndim_mode == 'dsilva':
        sigma_g = np.asarray(result.get('sigma_grid', [0.0]))
        logPmax_g = np.asarray(result.get('logPmax_grid', [0.0]))
        grids = [logPmax_g, sigma_g, fbin_g, x_g]
        grid_names = ['logPmax', 'sigma', 'fbin', x_name]
    elif ndim_mode == 'langer':
        grids, grid_names = [fbin_g, x_g], ['fbin', x_name]
    elif ndim_mode == 'cadence_langer':
        _sigma_g_cl = np.asarray(result.get('sigma_grid', [0.0]))
        _logPmax_g_cl = np.asarray(result.get('logPmax_grid', [0.0]))
        grids, grid_names = [], []
        if _logPmax_g_cl.size > 1:
            grids.append(_logPmax_g_cl); grid_names.append('logPmax')
        if _sigma_g_cl.size > 1:
            grids.append(_sigma_g_cl); grid_names.append('sigma')
        grids.append(fbin_g); grid_names.append('fbin')
        if x_name not in grid_names:
            grids.append(x_g); grid_names.append(x_name)
    elif ndim_mode == 'cadence_dsilva':
        grids, grid_names = [], []
        if extra_grids:
            for gn, ga in extra_grids:
                grids.append(ga); grid_names.append(gn)
        grids.extend([fbin_g, x_g]); grid_names.extend(['fbin', x_name])
    else:
        grids, grid_names = [fbin_g, x_g], ['fbin', x_name]

    rows, method_results = [], {}
    for mk, mname, pk, dk, mcolor in SCORING_METHODS:
        p_arr = _get_method_array(result, pk)
        if p_arr is None:
            continue
        is_lk = (mk == 'likelihood')
        if ndim_mode == 'dsilva':
            if p_arr.ndim == 2:
                p_arr = p_arr[np.newaxis, np.newaxis, ...]
            elif p_arr.ndim == 3:
                p_arr = p_arr[np.newaxis, ...]
        if ndim_mode == 'cadence_langer':
            if p_arr.ndim >= 3 and p_arr.shape[-1] == 1:
                p_arr = p_arr[..., 0]
            if p_arr.ndim == 2:
                p_arr = p_arr.T
            while p_arr.ndim > len(grids):
                squeezed = False
                for _ax in range(p_arr.ndim):
                    if p_arr.shape[_ax] == 1:
                        p_arr = np.squeeze(p_arr, axis=_ax); squeezed = True; break
                if not squeezed:
                    break
        elif ndim_mode == 'cadence_dsilva':
            # Bug 1c fix (2026-04-28): the previous `p_arr[0]` blindly
            # dropped axis 0 (logPmax), so when only logPmax is scanned
            # (sigma=1, logPmax>1) the wrong axis was squeezed and the
            # 'logPmax' grid_name became attached to the (size-1) sigma
            # axis → best_vals['logPmax']=NaN → CDF re-simulated at NaN
            # logP_max → flat ~0.12 line.  Mirror the cadence_langer
            # pattern: squeeze only size-1 axes.
            while p_arr.ndim > len(grids):
                squeezed = False
                for _ax in range(p_arr.ndim):
                    if p_arr.shape[_ax] == 1:
                        p_arr = np.squeeze(p_arr, axis=_ax)
                        squeezed = True
                        break
                if not squeezed:
                    # Fallback to old behaviour to avoid infinite loop
                    # if no size-1 axis exists (shouldn't happen with
                    # the runner's 4-D layout, but be defensive).
                    p_arr = p_arr[0]

        info = _method_best_and_hdi(p_arr, grids, grid_names, is_likelihood=is_lk)
        if info is None:
            continue
        method_results[mk] = info
        bv, hdi = info['best_vals'], info['hdi']

        def _fmt_hdi_cell(name, fmt='.4f'):
            if name not in hdi:
                return '--'
            mode, lo, hi = hdi[name]
            return f'{mode:{fmt}} (+{hi - mode:{fmt}} / -{mode - lo:{fmt}})'

        _has_sigma_col = ('sigma' in grid_names and x_name != 'sigma')
        row = {
            'Method': mname,
            'Best f_bin': f"{bv.get('fbin', 0):.4f}",
            '68% HDI f_bin': _fmt_hdi_cell('fbin', '.4f'),
            f'Best {x_label}': f"{bv.get(x_name, 0):.3f}",
            f'68% HDI {x_label}': _fmt_hdi_cell(x_name, '.3f'),
        }
        if _has_sigma_col:
            row['Best σ_single'] = f"{bv.get('sigma', 0):.2f}"
            row['68% HDI σ_single'] = _fmt_hdi_cell('sigma', '.2f')
        _has_logPmax_col = ('logPmax' in grid_names)
        if _has_logPmax_col:
            row['Best logP_max'] = f"{bv.get('logPmax', 0):.2f}"
            row['68% HDI logP_max'] = _fmt_hdi_cell('logPmax', '.2f')
        # Interpolated results (from parabolic fit)
        _interp = st.session_state.get(f'{prefix}_{mk}_analysis_interp')
        if _interp is not None:
            row['Interp f_bin'] = f"{_interp.get('f_bin', 0):.4f}"
            if x_name in _interp or x_label in _interp:
                _ix = _interp.get(x_name, _interp.get(x_label, 0))
                row[f'Interp {x_label}'] = f"{_ix:.3f}"
        # Raw logL score (rightmost column) — NOT normalized
        _raw_logL = result.get('logL_raw')
        if _raw_logL is not None:
            _raw_arr = np.asarray(_raw_logL, dtype=float)
            if np.any(np.isfinite(_raw_arr)):
                row['ln L (raw)'] = f"{float(np.nanmax(_raw_arr)):.2f}"
            else:
                row['ln L (raw)'] = '--'
        else:
            row['ln L (raw)'] = f"{info['best_score']:.6f}"
        rows.append(row)

    if not rows:
        return method_results

    st.markdown('#### Summary Table')
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(
        'Best-fit parameters and 68% HDI from likelihood scoring.')
    return method_results

# UPDATED 2026-04-19: CDF aligned with Model Explorer (cadence-aware + shape='hv').
def _render_all_methods_cdf(
    result: dict, method_results: dict,
    fbin_g: np.ndarray, x_g: np.ndarray, prefix: str,
    x_name: str = 'pi', x_label: str = 'π',
    bin_cfg=None,
) -> None:
    """CDF comparison: observed vs best-fit model from each scoring method."""
    obs_drv = result.get('obs_delta_rv')
    if obs_drv is None or len(method_results) < 1:
        return
    try:
        from wr_bias_simulation import DEFAULT_DRV_BIN_EDGES, BinaryParameterConfig
    except ImportError:
        return
    from bc.render_lk_explorer import (
        _me_cdf_band, _result_bin_cfg_tuple, _result_period_model,
    )
    # Round-5 CDF style constants (cross-file SSOT in render_validation).
    from bc.render_validation import (
        _CDF_OBS_COLOR, _CDF_FIT_COLOR, _CDF_FIT_MARG_COLOR,
        _CLR_SINGLE, _CLR_BINARY,
    )
    from bc.validation_io import load_per_star_truth

    _base_bin_cfg = bin_cfg if bin_cfg is not None else BinaryParameterConfig()
    _be = result.get('bin_edges')
    _be = DEFAULT_DRV_BIN_EDGES if _be is None else np.asarray(_be)
    obs_drv = np.asarray(obs_drv)

    # Conditional "Mock Observation" label in validation flow.
    from bc.helpers import _obs_label as _obs_label_sh
    _obs_name_sh = _obs_label_sh(result)

    # Round-5 CDF: BLACK sorted-raw step (NOT the binned CDF) so per-star
    # truth dots overlay precisely on the curve.  Mock vs real distinction
    # is communicated via the legend label and the dot overlay below.
    _obs_finite = obs_drv[np.isfinite(obs_drv) & (obs_drv > 0)]
    _n_obs_stars = int(_obs_finite.size)
    fig_cdf = go.Figure()
    if _n_obs_stars > 0:
        _sort_idx = np.argsort(_obs_finite)
        _drv_sorted = _obs_finite[_sort_idx]
        _cdf_y = (np.arange(_n_obs_stars) + 1) / _n_obs_stars
        fig_cdf.add_trace(go.Scatter(
            x=_drv_sorted, y=_cdf_y, mode='lines', name=_obs_name_sh,
            line=dict(color=_CDF_OBS_COLOR, width=2.5, shape='hv')))

        # Per-star truth-coded markers (validation flow only).  Outside the
        # validation flow load_per_star_truth returns None and the dots are
        # silently omitted — the panel is shared between mock and real obs.
        _is_bin = load_per_star_truth(result)
        # Re-sort the boolean mask to match _drv_sorted order.  Tolerate
        # arrays that came from a different filter (e.g. include zero-RV
        # stars) by aligning on the same finite/positive subset.
        if _is_bin is not None:
            _is_bin_full = np.asarray(_is_bin, dtype=bool)
            if _is_bin_full.size == obs_drv.size:
                _finite_mask = np.isfinite(obs_drv) & (obs_drv > 0)
                _is_bin_finite = _is_bin_full[_finite_mask]
                if _is_bin_finite.size == _n_obs_stars:
                    _is_bin_sorted = _is_bin_finite[_sort_idx]
                    _single_mask = ~_is_bin_sorted
                    _n_single = int(_single_mask.sum())
                    _n_binary = int(_is_bin_sorted.sum())
                    if np.any(_single_mask):
                        fig_cdf.add_trace(go.Scatter(
                            x=_drv_sorted[_single_mask],
                            y=_cdf_y[_single_mask],
                            mode='markers',
                            marker=dict(color=_CLR_SINGLE, size=8,
                                        line=dict(color='black', width=0.6)),
                            name=f'Single ({_n_single})',
                            hovertemplate='single · ΔRV=%{x:.1f} km/s<extra></extra>',
                        ))
                    if np.any(_is_bin_sorted):
                        fig_cdf.add_trace(go.Scatter(
                            x=_drv_sorted[_is_bin_sorted],
                            y=_cdf_y[_is_bin_sorted],
                            mode='markers',
                            marker=dict(color=_CLR_BINARY, size=8,
                                        line=dict(color='black', width=0.6)),
                            name=f'Binary ({_n_binary})',
                            hovertemplate='binary · ΔRV=%{x:.1f} km/s<extra></extra>',
                        ))

        # Real-obs fallback: when the validation truth helper returned
        # None, pull binary classification from the observation loader
        # so dots also work for the real WR sample.  Silent skip on any
        # failure to avoid breaking the shared panel for legacy results.
        if _is_bin is None and _n_obs_stars > 0:
            try:
                from shared import (
                    settings_hash,
                    cached_load_observed_delta_rvs,
                    get_settings_manager,
                )
                _settings_raw = result.get('settings')
                # `np.savez` round-trips dicts as 0-d numpy object arrays;
                # unwrap before settings_hash, which expects a real dict.
                if isinstance(_settings_raw, np.ndarray):
                    try:
                        _settings_raw = _settings_raw.item()
                    except Exception:
                        _settings_raw = None
                if not isinstance(_settings_raw, dict):
                    _settings_obj = get_settings_manager().load()
                else:
                    _settings_obj = _settings_raw
                _sh = settings_hash(_settings_obj)
                _obs_drv_full, _obs_detail = cached_load_observed_delta_rvs(_sh)
                _names_in_order = list(_obs_detail.keys())
                _isbin_full = np.array([
                    bool(_obs_detail[n].get('is_binary'))
                    if _obs_detail[n].get('is_binary') is not None else False
                    for n in _names_in_order
                ], dtype=bool)
                _sigma_full = np.array([
                    float(_obs_detail[n].get('best_sigma') or 0.0)
                    for n in _names_in_order
                ], dtype=float)
                if _isbin_full.size == obs_drv.size:
                    _finite_mask_ro = np.isfinite(obs_drv) & (obs_drv > 0)
                    _isbin_finite = _isbin_full[_finite_mask_ro]
                    _sigma_finite = _sigma_full[_finite_mask_ro]
                    if _isbin_finite.size == _n_obs_stars:
                        _isbin_sorted_ro = _isbin_finite[_sort_idx]
                        _sigma_sorted_ro = _sigma_finite[_sort_idx]
                        for _mask, _color, _label in [
                            (~_isbin_sorted_ro, _CLR_SINGLE, 'single'),
                            (_isbin_sorted_ro,  _CLR_BINARY, 'binary'),
                        ]:
                            if bool(np.any(_mask)):
                                _hover = [
                                    f'ΔRV = {d:.1f} km/s, σ = {s:.1f}, {_label}'
                                    for d, s in zip(_drv_sorted[_mask],
                                                    _sigma_sorted_ro[_mask])
                                ]
                                fig_cdf.add_trace(go.Scatter(
                                    x=_drv_sorted[_mask],
                                    y=_cdf_y[_mask],
                                    mode='markers',
                                    marker=dict(color=_color, size=8,
                                                line=dict(color='black',
                                                          width=0.6)),
                                    name=f'{_label.title()} ({int(_mask.sum())})',
                                    hovertext=_hover, hoverinfo='text',
                                ))
                    else:
                        st.warning(
                            f"Real-obs truth dots skipped: filter "
                            f"mismatch (isbin_finite={_isbin_finite.size} "
                            f"vs n_obs_stars={_n_obs_stars}).")
                else:
                    st.warning(
                        f"Real-obs truth dots skipped: size mismatch "
                        f"(isbin_full={_isbin_full.size} vs "
                        f"obs_drv={obs_drv.size}).")
            except Exception as _ro_exc:
                import traceback as _tb
                st.warning(
                    f"Real-obs truth-dot fallback raised:\n```\n"
                    f"{_tb.format_exc()}\n```")

    # E048: pull full physics config so the top CDF uses the SAME surface the
    # grid scored. Fall back to `bin_cfg` passed in from model_ctx, then to
    # module defaults (legacy .npz files).
    _bc_tuple_shared = _result_bin_cfg_tuple(result)
    if _bc_tuple_shared is None and bin_cfg is not None:
        try:
            from bc.render_lk_explorer import _bin_cfg_dict_as_hashable
            _bc_tuple_shared = _bin_cfg_dict_as_hashable(dict(vars(bin_cfg)))
        except Exception:
            _bc_tuple_shared = None
    _pm_shared = _result_period_model(result, default='powerlaw')
    if _bc_tuple_shared is None and result.get('bin_cfg') is None:
        st.info(
            'Legacy result — this .npz has no stored bin_cfg/period_model; '
            'CDFs are re-simulated with the orbital defaults from '
            '`BinaryParameterConfig()`. Rerun the simulation for a guaranteed '
            'match with the grid\'s stored logL_raw.')

    _n_sets = int(result.get('n_sets', 50))
    if result.get('cadence_library') is None:
        st.warning('Cadence library not stored in this result — CDF uses non-cadence-aware fallback (legacy .npz).')

    # Round-5 dual overlay: GRID best (red dashed step) + MARGINAL best
    # (purple dashed step) for every method.  Method identity is communicated
    # via the legend label, NOT the line color (user-locked global red/purple
    # convention).  Per-method band opacity decreases so multiple methods
    # don't paint over each other into an opaque blob.
    _band_opacities = [0.18, 0.12, 0.08]

    def _format_label(prefix: str, vals: dict) -> str:
        _lbl = f'{prefix} (f<sub>bin</sub>={vals.get("fbin", float("nan")):.3f}'
        if x_name in vals and np.isfinite(vals[x_name]):
            _lbl += f', π={vals[x_name]:.2f}' if x_name == 'pi' else f', {x_label}={vals[x_name]:.2f}'
        if 'sigma' in vals and np.isfinite(vals['sigma']) and vals['sigma'] != 0:
            _lbl += f', σ={vals["sigma"]:.1f}'
        if ('logPmax' in vals and np.isfinite(vals['logPmax'])
                and vals['logPmax'] != 0):
            _lbl += f', logP<sub>max</sub>={vals["logPmax"]:.2f}'
        _lbl += ')'
        return _lbl

    # ── Per-rank gradient markers helpers ──────────────────────────────
    def _gradient_color(frac: float) -> str:
        """Linear RGB interp from _CLR_SINGLE (red, frac=0) to
        _CLR_BINARY (green, frac=1).  Used to color per-rank dots by
        the simulated binary fraction at that rank.
        """
        def _hex_to_rgb(h):
            h = h.lstrip('#')
            return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))
        r0, g0, b0 = _hex_to_rgb(_CLR_SINGLE)
        r1, g1, b1 = _hex_to_rgb(_CLR_BINARY)
        f = max(0.0, min(1.0, float(frac)))
        r = int(round(r0 + (r1 - r0) * f))
        g = int(round(g0 + (g1 - g0) * f))
        b = int(round(b0 + (b1 - b0) * f))
        return f'rgb({r},{g},{b})'

    # Track whether the shared colorbar has been emitted yet (single
    # colorbar across all method-blocks; subsequent traces inherit the
    # same colorscale silently).
    _colorbar_shown = {'flag': False}

    def _add_rank_markers(rank_drv, rank_bin_frac, lgroup,
                          step_x=None, step_y=None,
                          symbol='circle'):
        """Per-rank markers colored by simulated binary fraction (red→green).

        When *step_x* and *step_y* are provided, snap each marker's y to
        the hv-step's value at that x so they ride exactly on the line.
        *symbol* picks the marker shape ('square' for median-line ranks,
        'triangle-up' for mean-line ranks).

        Empty rank arrays (non-cadence-aware fallback) silently skip.
        """
        if (rank_drv is None or len(rank_drv) == 0
                or rank_bin_frac is None or len(rank_bin_frac) == 0):
            return
        rank_drv_arr = np.asarray(rank_drv, dtype=float)
        n = int(rank_drv_arr.size)
        if step_x is not None and step_y is not None:
            _sx = np.asarray(step_x)
            _sy = np.asarray(step_y)
            _idx = np.searchsorted(_sx, rank_drv_arr, side='right') - 1
            _idx = np.clip(_idx, 0, _sy.size - 1)
            y_vals = _sy[_idx]
        else:
            y_vals = (np.arange(n) + 1) / n
        bf_arr = np.asarray(rank_bin_frac, dtype=float)
        hover = [f'rank {k+1}/{n} · binary fraction = {bf_arr[k]:.0%}'
                 for k in range(n)]
        _show_cbar = not _colorbar_shown['flag']
        _marker = dict(
            symbol=symbol,
            color=bf_arr, size=8,
            colorscale=[[0.0, _CLR_SINGLE], [1.0, _CLR_BINARY]],
            cmin=0.0, cmax=1.0,
            line=dict(color='black', width=0.4),
            showscale=_show_cbar,
        )
        if _show_cbar:
            _marker['colorbar'] = dict(
                title=dict(text='MC binary<br>fraction',
                           font=dict(size=11)),
                tickvals=[0.0, 0.5, 1.0],
                ticktext=['0% single', '50%', '100% binary'],
                len=0.6, thickness=12, x=1.02, y=0.5,
            )
            _colorbar_shown['flag'] = True
        fig_cdf.add_trace(go.Scatter(
            x=rank_drv_arr, y=y_vals, mode='markers',
            marker=_marker,
            legendgroup=lgroup, showlegend=False,
            hovertext=hover, hoverinfo='text',
        ))

    # ── logL helpers for legend suffix ──────────────────────────────────
    def _logL_at_grid_cell(vals: dict) -> float:
        """Stored exact logL at the nearest grid cell to *vals*.

        Reads `result['logL_raw']` (3-D or 4-D) and indexes by the
        nearest sigma/fbin/x_name/logPmax grid cell.
        """
        raw = result.get('logL_raw')
        if raw is None or not np.size(raw):
            return float('nan')
        raw = np.asarray(raw)
        sg = np.asarray(result.get('sigma_grid', []))
        fg = np.asarray(result.get('fbin_grid', []))
        pg = np.asarray(result.get('pi_grid', []))
        lpg = np.asarray(result.get('logPmax_grid', []))

        def _nearest(g, v):
            if g.size == 0:
                return None
            return int(np.argmin(np.abs(g - v)))

        i_sig = _nearest(sg, vals.get('sigma', 0.0))
        i_fb  = _nearest(fg, vals.get('fbin', 0.0))
        i_pi  = _nearest(pg, vals.get(x_name, 0.0))
        i_lp  = _nearest(lpg, vals.get('logPmax', 0.0)) if lpg.size > 0 else None
        try:
            if raw.ndim == 4 and i_lp is not None:
                return float(raw[i_lp, i_sig, i_fb, i_pi])
            if raw.ndim == 3:
                return float(raw[i_sig, i_fb, i_pi])
        except Exception:
            return float('nan')
        return float('nan')

    def _logL_exact_pooled(pooled) -> float:
        """Exact logL for a marginal point: re-score pooled draws against
        the same likelihood bins the grid used."""
        if pooled is None or len(pooled) == 0:
            return float('nan')
        try:
            from wr_bias_simulation import (
                multinomial_log_likelihood, DSILVA_LIKELIHOOD_BINS,
            )
            _lk_be = result.get('likelihood_bin_edges')
            if _lk_be is None:
                _lk_be = DSILVA_LIKELIHOOD_BINS
            return float(multinomial_log_likelihood(
                np.asarray(obs_drv), np.asarray(pooled), np.asarray(_lk_be)))
        except Exception:
            return float('nan')

    def _logL_suffix(val: float) -> str:
        return f' · logL = {val:.1f}' if np.isfinite(val) else ''

    for _mi, (mk, info) in enumerate(method_results.items()):
        bv = info['best_vals']
        hdi = info.get('hdi', {})
        _mname = next((n for k, n, _, _, _ in SCORING_METHODS if k == mk), mk)
        _band_alpha = _band_opacities[_mi % len(_band_opacities)]

        # Marginal-best params: hdi[name][0] = mode of the 1-D marginal
        # posterior (vs best_vals = joint argmax).  Same canonical path as
        # Round-5 (render_validation.py:_method_best_and_hdi).
        def _marg_or_grid(name: str, fallback):
            t = hdi.get(name)
            if t is None or not np.isfinite(t[0]):
                return fallback
            return float(t[0])

        try:
            _cad_lib = result.get('cadence_library')
            _cad_wt  = result.get('cadence_weights')
            sigma_m  = float(result.get('sigma_meas') or 3.0)

            # ── GRID best-fit (joint argmax) ────────────────────────────
            fb_g  = float(bv.get('fbin', 0.5))
            pi_g  = float(bv.get(x_name, 0.0))
            sig_g = float(bv.get('sigma', 5.0))
            lp_g  = float(bv.get('logPmax', _base_bin_cfg.logP_max))
            _band_g = _me_cdf_band(
                fb_g, pi_g, sig_g, sigma_m,
                tuple(_be.tolist()), logPmax=lp_g, n_sets=_n_sets,
                _cadence_library=_cad_lib, _cadence_weights=_cad_wt,
                _bin_cfg_dict=_bc_tuple_shared, period_model=_pm_shared,
            )
            _grid_vals = {'fbin': fb_g, x_name: pi_g, 'sigma': sig_g,
                          'logPmax': lp_g}
            # Smooth: empirical CDF of pooled ΔRVs (n_sets × n_stars samples)
            # for the dashed line; band = 16-84 percentile of per-draw CDFs
            # at a fine 500-point x-grid.  Bypasses the coarse visualization
            # bin grid (unrelated to the multinomial likelihood bins).
            _scdf_g = smooth_pooled_cdf(_band_g.pooled, _n_sets)
            if _scdf_g is not None:
                _sp_g, _yp_g, _xf_g, _lof_g, _hif_g = _scdf_g
                fig_cdf.add_trace(go.Scatter(
                    x=_xf_g, y=_lof_g, mode='lines',
                    line=dict(color='rgba(0,0,0,0)'),
                    legendgroup=f'{mk}_grid', showlegend=False,
                    hoverinfo='skip'))
                fig_cdf.add_trace(go.Scatter(
                    x=_xf_g, y=_hif_g, mode='lines',
                    line=dict(color='rgba(0,0,0,0)'),
                    fill='tonexty',
                    fillcolor=_hex_to_rgba(_CDF_FIT_COLOR, _band_alpha),
                    legendgroup=f'{mk}_grid', showlegend=False,
                    hoverinfo='skip'))
                fig_cdf.add_trace(go.Scatter(
                    x=_sp_g, y=_yp_g, mode='lines',
                    line=dict(color=_CDF_FIT_COLOR, width=2, dash='dash'),
                    legendgroup=f'{mk}_grid', showlegend=True,
                    name=_format_label(f'{_mname} grid', _grid_vals)
                         + _logL_suffix(_logL_at_grid_cell(_grid_vals)),
                    hovertemplate='grid median<extra></extra>',
                ))

                # Per-rank markers — squares snap to the smooth line.
                _add_rank_markers(_band_g.rank_median,
                                  _band_g.rank_bin_frac, f'{mk}_grid',
                                  step_x=_sp_g, step_y=_yp_g,
                                  symbol='square')

            # ── MARGINAL best-fit (1-D posterior modes) ─────────────────
            fb_m  = _marg_or_grid('fbin', fb_g)
            pi_m  = _marg_or_grid(x_name, pi_g)
            sig_m = _marg_or_grid('sigma', sig_g)
            lp_m  = _marg_or_grid('logPmax', lp_g)
            # Skip the marginal overlay only if every coordinate matches
            # the grid argmax bit-for-bit (then the trace is redundant).
            _coords_differ = (
                fb_m != fb_g or pi_m != pi_g
                or sig_m != sig_g or lp_m != lp_g
            )
            if _coords_differ:
                _band_m = _me_cdf_band(
                    fb_m, pi_m, sig_m, sigma_m,
                    tuple(_be.tolist()), logPmax=lp_m, n_sets=_n_sets,
                    _cadence_library=_cad_lib, _cadence_weights=_cad_wt,
                    _bin_cfg_dict=_bc_tuple_shared, period_model=_pm_shared,
                )
                _marg_vals = {'fbin': fb_m, x_name: pi_m, 'sigma': sig_m,
                              'logPmax': lp_m}
                # Smooth empirical CDF + 500-point band (same recipe as grid).
                _scdf_m = smooth_pooled_cdf(_band_m.pooled, _n_sets)
                if _scdf_m is not None:
                    _sp_m, _yp_m, _xf_m, _lof_m, _hif_m = _scdf_m
                    fig_cdf.add_trace(go.Scatter(
                        x=_xf_m, y=_lof_m, mode='lines',
                        line=dict(color='rgba(0,0,0,0)'),
                        legendgroup=f'{mk}_marg', showlegend=False,
                        hoverinfo='skip'))
                    fig_cdf.add_trace(go.Scatter(
                        x=_xf_m, y=_hif_m, mode='lines',
                        line=dict(color='rgba(0,0,0,0)'),
                        fill='tonexty',
                        fillcolor=_hex_to_rgba(_CDF_FIT_MARG_COLOR, _band_alpha),
                        legendgroup=f'{mk}_marg', showlegend=False,
                        hoverinfo='skip'))
                    fig_cdf.add_trace(go.Scatter(
                        x=_sp_m, y=_yp_m, mode='lines',
                        line=dict(color=_CDF_FIT_MARG_COLOR, width=2,
                                  dash='dash'),
                        legendgroup=f'{mk}_marg', showlegend=True,
                        name=_format_label(f'{_mname} marginal', _marg_vals)
                             + _logL_suffix(_logL_exact_pooled(_band_m.pooled)),
                        hovertemplate='marginal median<extra></extra>',
                    ))

                    # Per-rank markers — squares snap to the smooth line.
                    _add_rank_markers(_band_m.rank_median,
                                      _band_m.rank_bin_frac, f'{mk}_marg',
                                      step_x=_sp_m, step_y=_yp_m,
                                      symbol='square')
        except Exception as _cdf_exc:
            import traceback as _tb
            st.error(f"CDF panel exception for method '{mk}':\n```\n{_tb.format_exc()}\n```")

    # Phantom legend entries — make the marker-shape convention explicit
    # ('observation = circle', 'median rank = square').  Each is a single
    # off-canvas point so it shows up only in the legend and contributes
    # nothing to the chart area.
    fig_cdf.add_trace(go.Scatter(
        x=[None], y=[None], mode='markers',
        marker=dict(symbol='circle', color='black', size=8,
                    line=dict(color='black', width=0.6)),
        name='Observation (circle)', showlegend=True, hoverinfo='skip',
    ))
    fig_cdf.add_trace(go.Scatter(
        x=[None], y=[None], mode='markers',
        marker=dict(symbol='square', color='gray', size=8,
                    line=dict(color='black', width=0.4)),
        name='Median rank (square)', showlegend=True, hoverinfo='skip',
    ))

    # Show likelihood bins toggle
    _show_bins = st.checkbox('Show likelihood bins', value=False,
                             key=f'{prefix}_cdf_show_bins')
    if _show_bins:
        _lk_be = result.get('likelihood_bin_edges')
        if _lk_be is None:
            try:
                from wr_bias_simulation import DSILVA_LIKELIHOOD_BINS
                _lk_be = DSILVA_LIKELIHOOD_BINS
            except ImportError:
                _lk_be = np.array([0.0, 45.5, 250.0, 650.0])
        _lk_be = np.asarray(_lk_be)
        for _edge in _lk_be:
            if np.isfinite(_edge) and _edge > 0:
                fig_cdf.add_vline(
                    x=_edge, line_dash='dash', line_color='rgba(200,200,200,0.8)',
                    line_width=1.5)

    fig_cdf.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(text=f'CDF Comparison: {_obs_name_sh} vs Best-Fit Models',
                      font=dict(size=14)),
        'xaxis_title': 'ΔRV (km/s)', 'yaxis_title': 'Cumulative Fraction',
        'height': 600, 'legend': dict(x=0.55, y=0.05),
        'margin': dict(r=40),
    })
    # A&A override: white bg + serif.
    try:
        from bc.render_validation import _AA_OVERRIDES
        fig_cdf.update_layout(**_AA_OVERRIDES)
        fig_cdf.update_xaxes(**_AA_OVERRIDES['xaxis'])
        fig_cdf.update_yaxes(**_AA_OVERRIDES['yaxis'])
    except Exception:
        pass
    st.plotly_chart(fig_cdf, use_container_width=True, key=f'{prefix}_cdf_comparison')
    st.caption(
        f"{_obs_name_sh} ΔRV CDF (black) vs simulated best-fit CDFs: "
        f"red dashed = grid-argmax best-fit (empirical CDF of all pooled "
        f"simulated ΔRVs across {_n_sets} MC draws); purple dashed = "
        f"marginal-posterior-peak best-fit (same construction). Per-rank "
        f"dots ride those lines, colored by the simulated binary fraction "
        f"at each rank (red = 0% binary, green = 100% binary). "
        f"Shaded band = 16-84 percentile envelope of per-draw CDFs at a "
        f"500-point fine x-grid. "
        f"Cadence-aware when `cadence_library` is available.")

# ── From subtabs.py ──────────────────────────────────────────────────────────

# WORKING — do not change this code (extra_grids: only axes with >1 value)
def _build_extra_grids(ctx: dict) -> list[tuple[str, np.ndarray]] | None:
    """Build the extra_grids list for multi-dim models.

    Order must match array dimension order: (logPmax, sigma, fbin, pi).
    logPmax first (axis 0), then sigma (axis 1).
    """
    ndim = ctx['ndim_mode']
    extras: list[tuple[str, np.ndarray]] = []
    # logPmax FIRST (axis 0 in 4D array) — only if actual grid search (>1 value)
    if ctx.get('logPmax_g') is not None and ndim in ('dsilva', 'cadence_dsilva'):
        _lpg = ctx['logPmax_g']
        if len(_lpg) > 1:
            extras.append(('logPmax', _lpg))
    # sigma SECOND (axis 1 in 4D array) — only if actual grid search (>1 value)
    if ctx.get('sigma_g') is not None and ndim in ('dsilva', 'cadence_dsilva'):
        _sg = ctx['sigma_g']
        if len(_sg) > 1:
            extras.append(('sigma', _sg))
    return extras if extras else None

# WORKING — do not change this code (A3: Max Likelihood vs σ/logPmax)
def render_sigma_scan_chart(ctx: dict) -> None:
    """Show max -logL vs σ/logPmax: 1D line or 2D heatmap depending on grids.

    - σ only → 1D line (σ on x)
    - logPmax only → 1D line (logPmax on x)
    - Both σ AND logPmax → 2D heatmap (σ × logPmax, max over f_bin × π)

    Uses unnormalized logL_raw (falling back to normalized likelihood).
    """
    result = ctx['result']
    sigma_g = np.asarray(result.get('sigma_grid', []))
    logPmax_g = np.asarray(result.get('logPmax_grid', []))
    # Prefer unnormalized logL_raw; fall back to normalized likelihood
    lk = np.asarray(result.get('logL_raw', result.get('likelihood', [])))
    if lk.size == 0:
        return

    _has_sig = sigma_g.size > 1
    _has_lp = logPmax_g.size > 1
    _pfx = ctx.get('_prefix', 'sim')

    if not _has_sig and not _has_lp:
        return

    def _max_per_axis(arr, axis_sizes, keep_axes):
        """Compute max over all axes EXCEPT keep_axes."""
        reduce_axes = tuple(i for i in range(arr.ndim) if i not in keep_axes)
        if not reduce_axes:
            return arr
        return np.nanmax(arr, axis=reduce_axes)

    if _has_sig and _has_lp:
        # BOTH grids: 2D heatmap (σ × logPmax, max over f_bin × π)
        # lk shape: [logPmax, sigma, fbin, pi] (4D) or similar
        if lk.ndim == 4:
            hm_2d = np.nanmax(lk, axis=(2, 3))  # → [logPmax, sigma]
        elif lk.ndim == 3:
            hm_2d = np.nanmax(lk, axis=2)  # → [logPmax or sigma, sigma or fbin]
        else:
            return
        fig_hm = make_heatmap_fig(
            hm_2d, logPmax_g, sigma_g,
            title='Max Norm. Likelihood (σ_single × logP_max)',
            show_d=False, height=450,
            x_label='σ_single (km/s)',
            y_label='log₁₀(P_max / days)',
            x_name='σ',
            scoring_label='Likelihood',
            colorbar_title_override='Max Likelihood',
        )
        st.plotly_chart(fig_hm, use_container_width=True,
                        key=f'{_pfx}_sig_lp_heatmap')
        st.caption('Max likelihood across f_bin × π at each (σ_single, logP_max) point.')

    elif _has_sig:
        # σ only: 1D line chart
        if lk.ndim == 4:
            max_vals = [float(np.nanmax(lk[:, i_s, :, :]))
                        if np.any(np.isfinite(lk[:, i_s, :, :])) else 0.0
                        for i_s in range(sigma_g.size)]
        elif lk.ndim == 3:
            max_vals = [float(np.nanmax(lk[i_s]))
                        if np.any(np.isfinite(lk[i_s])) else 0.0
                        for i_s in range(sigma_g.size)]
        elif lk.ndim == 2:
            max_vals = [float(np.nanmax(lk[:, i_s]))
                        if np.any(np.isfinite(lk[:, i_s])) else 0.0
                        for i_s in range(sigma_g.size)]
        else:
            return
        fig = _make_max_pval_fig(sigma_g, max_vals, height=450,
                                 x_label='σ_single (km/s)',
                                 stat_label='Likelihood')
        st.plotly_chart(fig, use_container_width=True,
                        key=f'{_pfx}_sig_scan')

    elif _has_lp:
        # logPmax only: 1D line chart
        if lk.ndim == 4:
            max_vals = [float(np.nanmax(lk[i_lp]))
                        if np.any(np.isfinite(lk[i_lp])) else 0.0
                        for i_lp in range(logPmax_g.size)]
        elif lk.ndim == 3:
            max_vals = [float(np.nanmax(lk[i_lp]))
                        if np.any(np.isfinite(lk[i_lp])) else 0.0
                        for i_lp in range(logPmax_g.size)]
        else:
            return
        fig = _make_max_pval_fig(logPmax_g, max_vals, height=450,
                                 x_label='log₁₀(P_max / days)',
                                 stat_label='Likelihood')
        st.plotly_chart(fig, use_container_width=True,
                        key=f'{_pfx}_lp_scan')

# ── From sim_plots.py ────────────────────────────────────────────────────────

# WORKING — do not change this code (A5: Binary Fraction vs ΔRV Threshold)
def render_binary_fraction_vs_threshold(p, gap_drv, gap_is_bin, intrinsic_fbin,
                                        observed_fbin, thresh_dRV, missed_count,
                                        total_bin, detected_bin_count, pal,
                                        model_label='', obs_delta_rv=None,
                                        sigma_p2p=None, nsigma=4.0):
    """Binary fraction vs deltaRV threshold with gap annotation."""
    st.markdown('### Simulated Binary Fraction vs Threshold')
    n_sim = len(gap_drv)
    # X-axis max: full data range so the home button zooms all the way out.
    # Include obs_delta_rv so the observed step curve never clips.
    _obs_max = float(np.max(obs_delta_rv)) if (obs_delta_rv is not None and len(obs_delta_rv) > 0) else 0.0
    x_max = max(float(np.max(gap_drv)) * 1.05, _obs_max * 1.15)
    thresh_arr = np.linspace(0, x_max, 200)
    # Significance mask: ΔRV - nsigma * σ_p2p > 0
    if sigma_p2p is not None:
        sig_mask = (gap_drv - nsigma * sigma_p2p) > 0
    else:
        sig_mask = np.ones(n_sim, dtype=bool)
    bin_sig = sig_mask[gap_is_bin]
    sin_sig = sig_mask[~gap_is_bin]
    fbin_curve = np.array([float(np.sum((gap_drv > t) & sig_mask)) / n_sim
                           for t in thresh_arr])
    bin_drv_all = gap_drv[gap_is_bin]
    sin_drv_all = gap_drv[~gap_is_bin]
    missed_bin_curve = np.array(
        [float(np.sum((bin_drv_all <= t) | ~bin_sig)) / n_sim
         for t in thresh_arr])
    false_pos_curve = np.array(
        [float(np.sum((sin_drv_all > t) & sin_sig)) / n_sim
         for t in thresh_arr])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=thresh_arr, y=missed_bin_curve,
        fill='tozeroy', fillcolor='rgba(242,166,35,0.25)',
        line=dict(width=0), mode='lines', name='Missed binaries', showlegend=True))
    if np.any(false_pos_curve > 0):
        fig.add_trace(go.Scatter(
            x=thresh_arr, y=false_pos_curve,
            fill='tozeroy', fillcolor='rgba(74,144,217,0.25)',
            line=dict(width=0), mode='lines', name='Singles above threshold', showlegend=True))
    fig.add_trace(go.Scatter(
        x=thresh_arr, y=fbin_curve, mode='lines',
        name='Simulated f_bin(threshold)', line=dict(color=_CLR_OBS, width=2.5)))
    # Real observed binary fraction curve (step/stairs)
    # Bartzakos correction: 3 confirmed binaries excluded from sample → +3 numerator, /28 denominator
    if obs_delta_rv is not None and len(obs_delta_rv) > 0:
        _obs_drv = np.sort(np.asarray(obs_delta_rv))
        _n_bartz = 3
        _total_pop = len(_obs_drv) + _n_bartz
        # Apply same significance floor as simulated curve
        _obs_sig_floor = nsigma * float(sigma_p2p[0]) if (sigma_p2p is not None and len(sigma_p2p) > 0) else 0.0
        _obs_fbin_curve = np.array(
            [float(np.sum((_obs_drv > t) & (_obs_drv > _obs_sig_floor)) + _n_bartz) / _total_pop
             for t in _obs_drv])
        fig.add_trace(go.Scatter(
            x=_obs_drv, y=_obs_fbin_curve, mode='lines',
            name='Observed f_bin(threshold)',
            line=dict(color='#000000', width=2.5, shape='hv')))
    fig.add_hline(y=intrinsic_fbin, line_dash='dot', line_color=_CLR_DETECTED,
                  line_width=2, annotation_text=f'Intrinsic f_bin = {intrinsic_fbin:.1%}',
                  annotation_position='top left',
                  annotation_font=dict(size=11, color=_CLR_DETECTED))
    # "Real threshold" — where intrinsic f_bin crosses observed fraction curve
    _crossings = np.where(np.diff(np.sign(fbin_curve - intrinsic_fbin)))[0]
    if len(_crossings) > 0:
        _ci = _crossings[0]
        _real_thresh = np.interp(intrinsic_fbin,
                                 [fbin_curve[_ci + 1], fbin_curve[_ci]],
                                 [thresh_arr[_ci + 1], thresh_arr[_ci]])
        fig.add_vline(x=_real_thresh, line_dash='dot', line_color='#00CC66',
                      line_width=2, annotation_text=f'Real threshold ≈ {_real_thresh:.0f} km/s',
                      annotation_position='bottom right',
                      annotation_font=dict(size=10, color='#00CC66'))
    fig.add_vline(x=thresh_dRV, line_dash='dash', line_color=_CLR_MISSED,
                  line_width=2, annotation_text=f'Threshold = {thresh_dRV} km/s',
                  annotation_position='top right',
                  annotation_font=dict(size=11, color=_CLR_MISSED))
    fig.add_trace(go.Scatter(
        x=[thresh_dRV], y=[observed_fbin], mode='markers+text',
        marker=dict(size=14, color='#DAA520', symbol='diamond',
                    line=dict(width=2, color='black')),
        text=[f'{observed_fbin:.1%}'], textposition='top left',
        textfont=dict(size=12, color='#000000'),
        name=f'Simulated @ {thresh_dRV} km/s', showlegend=True))
    gap_pct = intrinsic_fbin - observed_fbin
    fig.add_annotation(
        x=thresh_dRV + 15, y=(intrinsic_fbin + observed_fbin) / 2,
        text=f'Gap: {gap_pct:.1%}<br>({missed_count} missed / {total_bin} binaries)',
        showarrow=False, font=dict(size=11, color=_CLR_MISSED),
        bgcolor='rgba(255,255,255,0.9)', bordercolor=_CLR_MISSED,
        borderwidth=1, borderpad=4)
    fig.add_annotation(
        x=thresh_dRV, y=intrinsic_fbin, ax=thresh_dRV, ay=observed_fbin,
        xref='x', yref='y', axref='x', ayref='y',
        showarrow=True, arrowhead=3, arrowwidth=2, arrowcolor=_CLR_MISSED)
    fig.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(text='Binary Fraction vs \u0394RV Threshold', font=dict(size=14)),
        'xaxis_title': '\u0394RV threshold (km/s)', 'yaxis_title': 'Fraction of sample',
        'height': 400, 'margin': dict(l=60, r=80, t=50, b=50),
        'showlegend': True, 'legend': dict(x=0.55, y=0.95, font=dict(size=10)),
        'xaxis': dict(range=[0.0, float(x_max)]),
        'yaxis': dict(range=[0.0, 1.0]),
    })
    # A&A override: force white bg + serif on paper-worthy plots.
    # Keep at the END so it overrides the PLOTLY_THEME (dark) defaults
    # spread at the top of update_layout. See render_validation.py:353.
    # 2026-04-23: Guy asked 5+ times for A&A; shipping dark had been the
    # recurring regression. Deferred import breaks any circular risk.
    try:
        from bc.render_validation import _AA_OVERRIDES
        fig.update_layout(**_AA_OVERRIDES)
        # _AA_OVERRIDES clobbers xaxis/yaxis → re-apply our ranges AFTER.
        fig.update_xaxes(range=[0.0, float(x_max)], **_AA_OVERRIDES['xaxis'])
        fig.update_yaxes(range=[0.0, 1.0], **_AA_OVERRIDES['yaxis'])
    except Exception:
        pass
    st.plotly_chart(fig, use_container_width=True, key=f'{p}_gap_chart')
    sfx = f' ({model_label})' if model_label else ''
    st.caption(
        f'Observed binary fraction as a function of \u0394RV threshold{sfx}. '
        f'The blue curve shows the fraction of stars classified as '
        f'binary at each threshold. The dashed red line is the '
        f'intrinsic f_bin = {intrinsic_fbin:.1%}. At our threshold '
        f'({thresh_dRV} km/s), the observed fraction is '
        f'{observed_fbin:.1%} \u2014 a gap of {gap_pct:.1%} due to '
        f'{missed_count} undetectable binaries. '
        f'Amber shading shows missed binaries; blue shading shows '
        f'singles scattered above each threshold.')

# WORKING — do not change this code (A6: Orbital Histograms)
def render_orbital_histograms(p, gap_sim, bin_detected_mask, bin_missed_mask,
                              ana_fbin, ana_x_val, x_label, thresh_dRV,
                              detected_bin_count, missed_count, has_case_AB=False,
                              sigma_single=None, logP_max_val=None):
    """9-panel orbital parameter histograms (detected vs missed)."""
    st.markdown('---')
    st.markdown('### Binary Orbital Properties')
    # Subtitle with best-fit model parameters
    _parts = []
    if ana_fbin is not None:
        _parts.append(f'f_bin = {ana_fbin:.3f}')
    if ana_x_val is not None:
        _parts.append(f'{x_label} = {ana_x_val:.2f}')
    if sigma_single is not None:
        _parts.append(f'σ_single = {sigma_single:.1f} km/s')
    if logP_max_val is not None:
        _parts.append(f'logP_max = {logP_max_val:.2f}')
    if _parts:
        st.caption(f'Best-fit model: {", ".join(_parts)}')
    mb_opts = ['Compare detected vs missed', 'Detected binaries only',
               'Missed binaries only', 'All binaries (combined)']
    if has_case_AB and gap_sim.get('case_A_mask') is not None:
        mb_opts.append('Case A vs Case B')
    mb_view = st.radio('Show populations', mb_opts, horizontal=True, key=f'{p}_mb_view')

    P_det = _safe_mask(gap_sim['P_days'], bin_detected_mask)
    P_mis = _safe_mask(gap_sim['P_days'], bin_missed_mask)
    e_det = _safe_mask(gap_sim['e'], bin_detected_mask)
    e_mis = _safe_mask(gap_sim['e'], bin_missed_mask)
    q_det = _safe_mask(gap_sim['q'], bin_detected_mask)
    q_mis = _safe_mask(gap_sim['q'], bin_missed_mask)
    K1_det = _safe_mask(gap_sim['K1'], bin_detected_mask)
    K1_mis = _safe_mask(gap_sim['K1'], bin_missed_mask)
    M1_det = _safe_mask(gap_sim['M1'], bin_detected_mask)
    M1_mis = _safe_mask(gap_sim['M1'], bin_missed_mask)
    i_det = np.degrees(_safe_mask(gap_sim['i_rad'], bin_detected_mask))
    i_mis = np.degrees(_safe_mask(gap_sim['i_rad'], bin_missed_mask))
    has_omega = 'omega' in gap_sim
    if has_omega:
        omega_det = np.degrees(_safe_mask(gap_sim['omega'], bin_detected_mask))
        omega_mis = np.degrees(_safe_mask(gap_sim['omega'], bin_missed_mask))
        T0_det = _safe_mask(gap_sim['T0'], bin_detected_mask)
        T0_mis = _safe_mask(gap_sim['T0'], bin_missed_mask)
    else:
        omega_det = omega_mis = T0_det = T0_mis = np.array([])
    M2_det = q_det * M1_det if q_det.size > 0 and M1_det.size > 0 else np.array([])
    M2_mis = q_mis * M1_mis if q_mis.size > 0 and M1_mis.size > 0 else np.array([])
    P_all = gap_sim['P_days']; e_all = gap_sim['e']; q_all = gap_sim['q']
    K1_all = gap_sim['K1']; M1_all = gap_sim['M1']
    i_all = np.degrees(gap_sim['i_rad'])
    omega_all = np.degrees(gap_sim['omega']) if has_omega else np.array([])
    T0_all = gap_sim['T0'] if has_omega else np.array([])
    M2_all = q_all * M1_all if q_all.size > 0 else np.array([])

    xlabs = ['log\u2081\u2080(P / days)', 'e', 'q = M\u2082/M\u2081',
             'K\u2081 (km/s)', 'M\u2081 (M\u2299)', 'M\u2082 (M\u2299)',
             'i (degrees)', '\u03c9 (degrees)', 'T\u2080 (rad)']
    NC, NR, NBINS = 3, 3, 30
    fig_mb = make_subplots(rows=NR, cols=NC,
                           horizontal_spacing=0.08, vertical_spacing=0.10)
    def _pos(idx):
        return (idx // NC + 1, idx % NC + 1)
    def _add_hist(row, col, data, name, color, show_legend):
        if data.size == 0:
            return
        d_min, d_max = float(data.min()), float(data.max())
        bsz = (d_max - d_min) / NBINS if d_max > d_min else 1.0
        fig_mb.add_trace(go.Histogram(
            x=data, xbins=dict(start=d_min, end=d_max + bsz * 0.01, size=bsz),
            histnorm='probability density', name=name, marker_color=color,
            opacity=0.6, legendgroup=name, showlegend=show_legend,
        ), row=row, col=col)
    def _logP(arr):
        return np.log10(arr) if arr.size > 0 else arr

    if mb_view == 'All binaries (combined)':
        ds = [_logP(P_all), e_all, q_all, K1_all, M1_all, M2_all,
              i_all, omega_all, T0_all]
        for pi, d in enumerate(ds):
            _add_hist(*_pos(pi), d, 'All binaries', _CLR_ALL, pi == 0)
    elif mb_view == 'Case A vs Case B':
        cA = gap_sim['case_A_mask']; cB = ~cA
        for mask, lbl, clr in [(cA, f'Case A ({int(cA.sum())})', _CLR_CASE_A),
                                (cB, f'Case B ({int(cB.sum())})', _CLR_CASE_B)]:
            ds = [_logP(_safe_mask(gap_sim['P_days'], mask)),
                  _safe_mask(gap_sim['e'], mask),
                  _safe_mask(gap_sim['q'], mask),
                  _safe_mask(gap_sim['K1'], mask),
                  _safe_mask(gap_sim['M1'], mask),
                  _safe_mask(gap_sim['q'], mask) * _safe_mask(gap_sim['M1'], mask),
                  np.degrees(_safe_mask(gap_sim['i_rad'], mask)),
                  np.degrees(_safe_mask(gap_sim.get('omega', np.array([])), mask)) if has_omega else np.array([]),
                  _safe_mask(gap_sim.get('T0', np.array([])), mask) if has_omega else np.array([])]
            for pi, d in enumerate(ds):
                _add_hist(*_pos(pi), d, lbl, clr, pi == 0)
    else:
        det_ds = [_logP(P_det), e_det, q_det, K1_det, M1_det, M2_det,
                  i_det, omega_det, T0_det]
        mis_ds = [_logP(P_mis), e_mis, q_mis, K1_mis, M1_mis, M2_mis,
                  i_mis, omega_mis, T0_mis]
        if mb_view in ('Compare detected vs missed', 'Detected binaries only'):
            for pi, d in enumerate(det_ds):
                _add_hist(*_pos(pi), d, 'Detected', _CLR_DETECTED, pi == 0)
        if mb_view in ('Compare detected vs missed', 'Missed binaries only'):
            for pi, d in enumerate(mis_ds):
                _add_hist(*_pos(pi), d, 'Missed', _CLR_MISSED, pi == 0)

    fig_mb.update_layout(**{
        **PLOTLY_THEME, 'barmode': 'overlay', 'height': 850,
        'margin': dict(l=40, r=20, t=40, b=60),
        'legend': dict(orientation='h', yanchor='bottom', y=1.04,
                       xanchor='center', x=0.5),
    })
    for pi in range(9):
        r, c = _pos(pi)
        fig_mb.update_xaxes(title_text=xlabs[pi], showgrid=False, row=r, col=c)
        fig_mb.update_yaxes(showgrid=False, row=r, col=c)
    for ri in range(1, NR + 1):
        fig_mb.update_yaxes(title_text='Prob. density', row=ri, col=1)
    # A&A override: white bg + serif across every subplot.
    try:
        from bc.render_validation import _AA_OVERRIDES
        fig_mb.update_layout(
            plot_bgcolor=_AA_OVERRIDES['plot_bgcolor'],
            paper_bgcolor=_AA_OVERRIDES['paper_bgcolor'],
            font=_AA_OVERRIDES['font'],
            legend=_AA_OVERRIDES['legend'],
            hoverlabel=_AA_OVERRIDES['hoverlabel'],
        )
        fig_mb.update_xaxes(**_AA_OVERRIDES['xaxis'])
        fig_mb.update_yaxes(**_AA_OVERRIDES['yaxis'])
    except Exception:
        pass
    st.plotly_chart(fig_mb, use_container_width=True, key=f'{p}_missed_binaries')
    _cap_parts = []
    if ana_fbin is not None:
        _cap_parts.append(f'f_bin={ana_fbin:.3f}')
    if ana_x_val is not None:
        _cap_parts.append(f'{x_label}={ana_x_val:.2f}')
    _cap_model = ', '.join(_cap_parts) if _cap_parts else 'best-fit'
    st.caption(
        f'Orbital parameter distributions of simulated binaries at the '
        f'best-fit model ({_cap_model}). '
        f'**Detected** (red): {detected_bin_count} binaries with '
        f'\u0394RV > {thresh_dRV} km/s. '
        f'**Missed** (amber): {missed_count} binaries below threshold. '
        f'Use "All binaries" to view the full population as a sanity check '
        f'that input distributions match expectations.')

# WORKING — do not change this code (A7: Methodology Equations)
def render_methodology_equations(model_type):
    """Methodology expander with equations."""
    if model_type not in ('dsilva', 'cadence_dsilva'):
        from bc.helpers import _render_methodology_expander
        _render_methodology_expander(model_type)
        return
    st.markdown('---')
    with st.expander('Simulation methodology & equations', expanded=False):
        st.markdown(
            '**Simulation overview** \u2014 for each grid point '
            '(f_bin, \u03c0, \u03c3_single):\n\n'
            '1. **Draw N systems** (default 3,000). Each system is binary '
            'with probability f_bin, or single with probability 1 \u2212 f_bin.\n\n'
            '2. **Assign observation cadences.** Each simulated system is '
            'assigned the observation cadence (MJD sequence) of one of the '
            '25 sample stars.\n\n'
            '3. **Single stars:** draw RV at each epoch from '
            'N(v_sys, \u03c3_total) where \u03c3_total = '
            '\u221a(\u03c3_single\u00b2 + \u03c3_measure\u00b2). '
            'Compute \u0394RV = max(v) \u2212 min(v).\n\n'
            '4. **Binary stars:** sample orbital parameters:\n'
            '   - Period P from power-law p(log P) \u221d (log P)^\u03c0\n'
            '   - Eccentricity e ~ U[0, e_max]\n'
            '   - Primary mass M\u2081, mass ratio q = M\u2082/M\u2081\n'
            '   - Inclination i from sin(i) distribution\n'
            '   - \u03c9 ~ U[0, 2\u03c0], T\u2080 ~ U[0, 2\u03c0]\n\n'
            '5. **Compute the RV semi-amplitude K\u2081:**')
        st.latex(r'K_1 = \left(\frac{2\pi G}{P}\right)^{1/3}'
                 r'\frac{M_2 \sin i}{(M_1 + M_2)^{2/3}}'
                 r'\frac{1}{\sqrt{1 - e^2}}')
        st.markdown('6. **Solve Kepler\'s equation** via Newton-Raphson:')
        st.latex(r'E - e \sin E = M, \quad M = T_0 + \frac{2\pi t}{P}')
        st.markdown('7. **True anomaly** \u03bd from E:')
        st.latex(r'\tan\frac{\nu}{2} = \sqrt{\frac{1+e}{1-e}} \, \tan\frac{E}{2}')
        st.markdown('8. **Radial velocity curve:**')
        st.latex(r'v(t) = v_{\rm sys} + K_1 \left[\cos(\omega + \nu) + e\cos\omega\right]')
        st.markdown(
            'Then \u0394RV = max(v) \u2212 min(v) over observed epochs.\n\n'
            '9. **Score** via multinomial log-likelihood. The observed and '
            'simulated \u0394RV distributions are binned, and the likelihood is:')
        st.latex(r'\ln L = \sum_{i} n_i \ln(p_i)')
        st.markdown(
            'where n_i is the observed count in bin i and p_i is the simulated '
            'fraction. Higher likelihood = better match.\n\n'
            '10. **Binary detection criteria** (both required):')
        st.latex(r'\Delta\mathrm{RV} > 45.5 \; \mathrm{km/s}'
                 r'\quad \text{and} \quad'
                 r'\Delta\mathrm{RV} - 4\sigma > 0')
        st.markdown(
            'where \u03c3 is the combined measurement error of the epoch pair.\n\n'
            '**Uncertainties** on model parameters (f_bin, \u03c0, \u03c3_single, '
            'logP_max) are derived from the 16th and 84th percentile of the '
            'marginalized likelihood in the corner plots.')

# ── Analysis plots helper ────────────────────────────────────────────────────

def _render_analysis_plots(p: str, ctx: dict, gap_sim: dict, method_results: dict) -> None:
    """Render period distribution, binary fraction, and orbital histograms."""
    pal = get_palette()
    thresh_dRV = ctx.get('thresh_dRV', 45.5)
    has_case_AB = ctx.get('has_case_AB', False)
    gap_drv = np.asarray(gap_sim.get('delta_rv', []))
    gap_is_bin = np.asarray(gap_sim.get('is_binary', []), dtype=bool)
    if gap_drv.size == 0:
        return
    # Significance criterion: σ_p2p from simulate_with_params
    _raw_sp = gap_sim.get('sigma_p2p')
    sigma_p2p = np.asarray(_raw_sp) if _raw_sp is not None else None
    nsigma = float(ctx.get('classification', {}).get('sigma_factor', 4.0))

    idx_bin = gap_sim.get('idx_bin')
    if idx_bin is None:
        idx_bin = np.where(gap_is_bin)[0]
    bin_drv = gap_drv[idx_bin] if idx_bin.size > 0 else np.array([])
    bin_sigma = sigma_p2p[idx_bin] if (sigma_p2p is not None and idx_bin.size > 0) else None
    # Dual criterion: ΔRV > threshold AND ΔRV − nsigma·σ_p2p > 0
    if bin_sigma is not None:
        bin_detected_mask = (bin_drv > thresh_dRV) & ((bin_drv - nsigma * bin_sigma) > 0)
    else:
        bin_detected_mask = bin_drv > thresh_dRV
    bin_missed_mask = ~bin_detected_mask

    ana_fbin, ana_x_val, ana_sigma, ana_logPmax = None, None, None, None
    for mk, _, _, _, _ in SCORING_METHODS:
        mr = method_results.get(mk)
        if mr and 'best_vals' in mr:
            bv = mr['best_vals']
            ana_fbin = bv.get('fbin')
            ana_x_val = bv.get(ctx['x_name'])
            ana_sigma = bv.get('sigma')
            ana_logPmax = bv.get('logPmax')
            break
    intrinsic_fbin = float(gap_is_bin.mean()) if gap_is_bin.size > 0 else 0.5
    x_label = ctx['x_label']
    logP_min, logP_max = ctx.get('logP_min', 0.15), ctx.get('logP_max', 4.0)
    total_bin = int(np.sum(gap_is_bin))
    detected_bin_count = int(np.sum(bin_detected_mask))
    missed_count = int(np.sum(bin_missed_mask))
    # observed_fbin uses same dual criterion on ALL stars
    if sigma_p2p is not None:
        _all_sig_mask = (gap_drv - nsigma * sigma_p2p) > 0
        observed_fbin = float(np.sum((gap_drv > thresh_dRV) & _all_sig_mask)) / max(len(gap_drv), 1)
    else:
        observed_fbin = detected_bin_count / max(len(gap_drv), 1)

    render_binary_fraction_vs_threshold(
        p, gap_drv, gap_is_bin, intrinsic_fbin, observed_fbin, thresh_dRV,
        missed_count, total_bin, detected_bin_count, pal,
        model_label=ctx['model_type'],
        obs_delta_rv=ctx.get('obs_delta_rv'),
        sigma_p2p=sigma_p2p, nsigma=nsigma)
    render_orbital_histograms(
        p, gap_sim, bin_detected_mask, bin_missed_mask,
        ana_fbin, ana_x_val, x_label, thresh_dRV,
        detected_bin_count, missed_count, has_case_AB=has_case_AB,
        sigma_single=ana_sigma, logP_max_val=ana_logPmax)

# ── Public entry point ───────────────────────────────────────────────────────

def render_shared_section(p: str, model_ctx: dict) -> dict:
    """Render shared graphs (summary table, CDF, sim plots) before radio selector.

    Returns method_results dict for use by scoring method tabs.
    """
    result = model_ctx.get('result')
    if result is None:
        st.info('Run a simulation or load a saved result to see analysis.')
        return {}

    extra_grids = _build_extra_grids(model_ctx)
    method_results = _render_method_summary_section(
        result, model_ctx['fbin_g'], model_ctx['x_g'],
        extra_grids=extra_grids, prefix=p,
        x_name=model_ctx['x_name'], x_label=model_ctx['x_label'],
        ndim_mode=model_ctx['ndim_mode'])
    if method_results is None:
        method_results = {}

    _render_all_methods_cdf(
        result, method_results, model_ctx['fbin_g'], model_ctx['x_g'],
        prefix=p, x_name=model_ctx['x_name'], x_label=model_ctx['x_label'],
        bin_cfg=model_ctx.get('bin_cfg'))

    # E6: Per-bin breakdown table (directly under CDF)
    _obs_drv_e6 = result.get('obs_delta_rv')
    if _obs_drv_e6 is not None:
        _lk_be_e6 = result.get('likelihood_bin_edges')
        if _lk_be_e6 is None:
            try:
                from wr_bias_simulation import DSILVA_LIKELIHOOD_BINS
                _lk_be_e6 = DSILVA_LIKELIHOOD_BINS
            except ImportError:
                _lk_be_e6 = None
        if _lk_be_e6 is not None:
            try:
                from bc.render_lk_scoring import _compute_pooled_sim
                from bc.render_lk_fit import _render_likelihood_stats_table
                _pooled_e6 = _compute_pooled_sim(np.asarray(_obs_drv_e6), result)
                if _pooled_e6 is not None:
                    _render_likelihood_stats_table(
                        np.asarray(_obs_drv_e6), _pooled_e6, np.asarray(_lk_be_e6))
            except ImportError:
                pass

    # A3 sigma/logPmax chart: moved to Likelihood Analysis section (render_lk.py)

    gap_sim = model_ctx.get('gap_sim')
    if gap_sim is not None:
        _render_analysis_plots(p, model_ctx, gap_sim, method_results)

    render_methodology_equations(model_ctx['model_type'])
    return method_results
