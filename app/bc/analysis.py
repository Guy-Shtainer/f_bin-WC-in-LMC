"""bc.analysis — Multi-method summary, per-method expanders, CDF comparison."""
from __future__ import annotations

import json
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

from shared import (
    find_best_grid_point, make_heatmap_fig,
    PLOTLY_THEME, get_palette,
)

from bc.helpers import (
    SCORING_METHODS, _METHOD_COLORS, _hex_to_rgba,
    _RESULT_DIR,
)

from typing import Tuple

# Re-export from split modules (external consumers import from bc.analysis)
from bc.scoring_detail import _render_cvm_analysis  # noqa: F401

_best_point = find_best_grid_point
_make_heatmap_fig = make_heatmap_fig


def _binned_cdf(data: np.ndarray, bin_edges: np.ndarray) -> np.ndarray:
    """Empirical CDF evaluated at bin_edges: fraction of data <= x."""
    sorted_data = np.sort(data)
    return np.searchsorted(sorted_data, bin_edges, side='right') / len(sorted_data)


# ─────────────────────────────────────────────────────────────────────────────
# Multi-method summary + per-method expanders
# ─────────────────────────────────────────────────────────────────────────────

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
    p_nd: np.ndarray,
    grids: list[np.ndarray],
    grid_names: list[str],
    is_likelihood: bool = False,
) -> dict:
    """Find global best-fit and 68% HDI for each axis of a scoring array.

    Parameters
    ----------
    p_nd : ndarray
        N-dimensional scoring array (higher = better for all methods,
        since likelihood is already normalized to [0,1]).
    grids : list of 1D arrays
        Grid values for each axis, in order matching p_nd dimensions.
    grid_names : list of str
        Names for each axis (e.g. ['sigma', 'fbin', 'pi']).
    is_likelihood : bool
        True if the array is likelihood (not p-value). Affects labels only.

    Returns
    -------
    dict with keys:
        'best_idx' : tuple of int — multi-index of best point
        'best_vals' : dict[name -> float]
        'best_score' : float
        'hdi' : dict[name -> (mode, lo, hi)]
    """
    from wr_bias_simulation import compute_hdi68

    valid = np.isfinite(p_nd)
    if not np.any(valid):
        return None

    # E040: validate grid count matches array dimensions
    if len(grids) != p_nd.ndim:
        return None

    flat_best = int(np.nanargmax(p_nd))
    best_idx = np.unravel_index(flat_best, p_nd.shape)
    best_score = float(p_nd[best_idx])
    best_vals = {}
    hdi = {}

    for i, (g, name) in enumerate(zip(grids, grid_names)):
        # E040: skip if grid size doesn't match array dimension
        if i >= p_nd.ndim or len(g) != p_nd.shape[i]:
            best_vals[name] = float('nan')
            hdi[name] = (float('nan'), float('nan'), float('nan'))
            continue
        best_vals[name] = float(g[best_idx[i]])
        # Marginalize over all other axes
        sum_axes = tuple(j for j in range(p_nd.ndim) if j != i)
        post_1d = np.nansum(p_nd, axis=sum_axes) if sum_axes else p_nd.copy()
        if post_1d.sum() > 0:
            mode, lo, hi = compute_hdi68(g, post_1d)
            hdi[name] = (float(mode), float(lo), float(hi))
        else:
            v = best_vals[name]
            hdi[name] = (v, v, v)

    return {
        'best_idx': best_idx,
        'best_vals': best_vals,
        'best_score': best_score,
        'hdi': hdi,
    }


def _render_method_summary_section(
    result: dict,
    fbin_g: np.ndarray,
    x_g: np.ndarray,
    extra_grids: list[tuple[str, np.ndarray]] | None = None,
    prefix: str = 'ds',
    x_name: str = 'pi',
    x_label: str = 'pi',
    ndim_mode: str = 'dsilva',
) -> dict:
    """Render a comparison table of all scoring methods above the per-method details.

    Returns method_results dict mapping method_key → {best_vals, hdi, ...}.

    Parameters
    ----------
    result : dict
        Full result dictionary (must contain scoring arrays).
    fbin_g : 1D array
        f_bin grid.
    x_g : 1D array
        Second-axis grid (pi for Dsilva, sigma for Langer).
    extra_grids : list of (name, 1D-array) or None
        Additional grids to include in the analysis (e.g. sigma, logPmax
        for the Dsilva 4D case). These are prepended to the grid list.
    prefix : str
        Unique key prefix for session state.
    x_name : str
        Display name for x_g axis (e.g. 'pi', 'sigma').
    x_label : str
        Formatted label for x_g axis (e.g. 'pi', 'sigma_single').
    ndim_mode : str
        'dsilva' (4D: logPmax x sigma x fbin x pi),
        'langer' (2D: fbin x sigma),
        'cadence_dsilva' (3D: sigma x fbin x pi),
        'cadence_langer' (3D/2D: sigma x fbin x pi).
    """
    # Build ordered grid list matching array dimensions
    if ndim_mode == 'dsilva':
        # 4D: [logPmax, sigma, fbin, pi]
        sigma_g = np.asarray(result.get('sigma_grid', [0.0]))
        logPmax_g = np.asarray(result.get('logPmax_grid', [0.0]))
        grids = [logPmax_g, sigma_g, fbin_g, x_g]
        grid_names = ['logPmax', 'sigma', 'fbin', x_name]
    elif ndim_mode == 'langer':
        # 2D: [fbin, sigma]
        grids = [fbin_g, x_g]
        grid_names = ['fbin', x_name]
    elif ndim_mode == 'cadence_langer':
        # Cadence Langer: arrays are [logPmax?, n_sig, n_fb, n_pi=1]
        # Build grids dynamically based on scanned axes
        _sigma_g_cl = np.asarray(result.get('sigma_grid', [0.0]))
        _logPmax_g_cl = np.asarray(result.get('logPmax_grid', [0.0]))
        grids = []
        grid_names = []
        if _logPmax_g_cl.size > 1:
            grids.append(_logPmax_g_cl)
            grid_names.append('logPmax')
        if _sigma_g_cl.size > 1:
            grids.append(_sigma_g_cl)
            grid_names.append('sigma')
        grids.append(fbin_g)
        grid_names.append('fbin')
        if x_name not in grid_names:
            grids.append(x_g)
            grid_names.append(x_name)
    elif ndim_mode == 'cadence_dsilva':
        # 3D: [sigma, fbin, pi]
        grids = []
        grid_names = []
        if extra_grids:
            for gn, ga in extra_grids:
                grids.append(ga)
                grid_names.append(gn)
        grids.extend([fbin_g, x_g])
        grid_names.extend(['fbin', x_name])
    else:
        grids = [fbin_g, x_g]
        grid_names = ['fbin', x_name]

    rows = []
    method_results = {}

    for mk, mname, pk, dk, mcolor in SCORING_METHODS:
        p_arr = _get_method_array(result, pk)
        if p_arr is None:
            continue

        # Ensure dimensionality matches expected grids
        is_lk = (mk == 'likelihood')

        # For Dsilva 4D: ensure 4D
        if ndim_mode == 'dsilva':
            if p_arr.ndim == 2:
                p_arr = p_arr[np.newaxis, np.newaxis, ...]
            elif p_arr.ndim == 3:
                p_arr = p_arr[np.newaxis, ...]

        # For cadence Langer: squeeze pi dim (last, always size 1)
        if ndim_mode == 'cadence_langer':
            # Remove trailing pi=1 dimension
            if p_arr.ndim >= 3 and p_arr.shape[-1] == 1:
                p_arr = p_arr[..., 0]
            # 2D [n_sig, n_fb] → transpose to [n_fb, n_sig] to match grids
            if p_arr.ndim == 2:
                p_arr = p_arr.T
            # 3D [logPmax, n_sig, n_fb] → keep as-is (grids already ordered)
            # Safety: squeeze remaining size-1 dims
            while p_arr.ndim > len(grids):
                squeezed = False
                for _ax in range(p_arr.ndim):
                    if p_arr.shape[_ax] == 1:
                        p_arr = np.squeeze(p_arr, axis=_ax)
                        squeezed = True
                        break
                if not squeezed:
                    break
        # For cadence Dsilva: squeeze leading dims if needed
        elif ndim_mode == 'cadence_dsilva':
            while p_arr.ndim > len(grids):
                p_arr = p_arr[0]

        info = _method_best_and_hdi(p_arr, grids, grid_names, is_likelihood=is_lk)
        if info is None:
            continue
        method_results[mk] = info

        bv = info['best_vals']
        hdi = info['hdi']

        def _fmt_hdi_cell(name, fmt='.4f'):
            if name not in hdi:
                return '--'
            mode, lo, hi = hdi[name]
            return f'{mode:{fmt}} (+{hi - mode:{fmt}} / -{mode - lo:{fmt}})'

        fb_best = f"{bv.get('fbin', 0):.4f}"
        fb_hdi = _fmt_hdi_cell('fbin', '.4f')

        x_best = f"{bv.get(x_name, 0):.3f}"
        x_hdi = _fmt_hdi_cell(x_name, '.3f')

        # Sigma columns (only if sigma is a separate grid axis, not the x-axis)
        _has_sigma_col = ('sigma' in grid_names and x_name != 'sigma')
        sig_best = ''
        sig_hdi = ''
        if _has_sigma_col:
            sig_best = f"{bv.get('sigma', 0):.2f}"
            sig_hdi = _fmt_hdi_cell('sigma', '.2f')

        score_val = f"{info['best_score']:.6f}"

        row = {
            'Method': mname,
            'Best f_bin': fb_best,
            '68% HDI f_bin': fb_hdi,
            f'Best {x_label}': x_best,
            f'68% HDI {x_label}': x_hdi,
            'Score (best)': score_val,
        }
        if _has_sigma_col:
            row['Best σ_single'] = sig_best
            row['68% HDI σ_single'] = sig_hdi
        rows.append(row)

    if not rows:
        return

    # Compute agreement column: does each method's best f_bin fall within
    # every other method's 68% HDI for f_bin?
    for i, row in enumerate(rows):
        mk_i = SCORING_METHODS[i][0]
        if mk_i not in method_results:
            row['Agreement'] = '--'
            continue
        best_fb_i = method_results[mk_i]['best_vals'].get('fbin', np.nan)
        in_all = True
        for mk_j, info_j in method_results.items():
            if mk_j == mk_i:
                continue
            lo_j = info_j['hdi'].get('fbin', (0, 0, 0))[1]
            hi_j = info_j['hdi'].get('fbin', (0, 0, 0))[2]
            if not (lo_j <= best_fb_i <= hi_j):
                in_all = False
                break
        row['Agreement'] = 'Yes' if in_all else 'No'

    st.markdown('#### Scoring Method Comparison')
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(
        'Comparison of all scoring methods. "Agreement" = does this method\'s '
        'best f_bin fall within every other method\'s 68% HDI for f_bin.'
    )

    return method_results


def _render_all_methods_cdf(
    result: dict,
    method_results: dict,
    fbin_g: np.ndarray,
    x_g: np.ndarray,
    prefix: str,
    x_name: str = 'pi',
    x_label: str = 'pi',
) -> None:
    """CDF comparison: observed vs best-fit model from each scoring method.

    NOTE (2026-04-28): this function is currently DEAD code — `subtabs.py`
    line ~90 has the call commented out as redundant with E5.  It is
    maintained here for parity with the active `render_shared.py` /
    `render_shared_langer.py` panels in case it gets re-enabled.  The
    Round-5 dual-overlay convention (BLACK obs + RED grid + PURPLE
    marginal) is mirrored below.
    """
    obs_drv = result.get('obs_delta_rv')
    if obs_drv is None or len(method_results) < 1:
        return
    try:
        from wr_bias_simulation import (
            DEFAULT_DRV_BIN_EDGES,
            simulate_delta_rv_sample, SimulationConfig, BinaryParameterConfig,
        )
    except ImportError:
        return

    _be = result.get('bin_edges')
    if _be is None:
        _be = DEFAULT_DRV_BIN_EDGES
    else:
        _be = np.asarray(_be)
    obs_drv = np.asarray(obs_drv)
    _n_obs_stars = len(obs_drv)

    # Conditional label for Validation flow (mock observations vs real obs).
    from bc.helpers import _obs_label
    _obs_name = _obs_label(result)

    # CDF style constants — single source of truth in render_validation.
    # Observation = BLACK step (NO markers on the line itself — coloured
    # truth-coded dots overlay separately when validation truth is
    # available).  Grid best-fit = dashed RED step; marginal best-fit =
    # dashed PURPLE step.  Round-5 user-locked global convention.
    from bc.render_validation import (
        _CDF_OBS_COLOR, _CDF_FIT_COLOR, _CDF_FIT_MARG_COLOR,
        _CLR_SINGLE, _CLR_BINARY,
    )

    # Round-5: observation curve uses the SORTED-RAW empirical step (NOT
    # the binned CDF) so per-star truth dots align exactly with the line.
    _obs_finite = obs_drv[np.isfinite(obs_drv) & (obs_drv > 0)]
    _n_obs_finite = int(_obs_finite.size)
    fig_cdf = go.Figure()
    if _n_obs_finite > 0:
        _sort_idx = np.argsort(_obs_finite)
        _drv_sorted = _obs_finite[_sort_idx]
        _cdf_vals = (np.arange(_n_obs_finite) + 1) / _n_obs_finite
        fig_cdf.add_trace(go.Scatter(
            x=_drv_sorted, y=_cdf_vals,
            mode='lines', name=_obs_name,
            line=dict(color=_CDF_OBS_COLOR, width=2.5, shape='hv'),
        ))
    else:
        _drv_sorted = np.array([])
        _cdf_vals = np.array([])

    # Per-star truth-coded markers (validation flow only).  Each star sits
    # at its own ΔRV on the empirical CDF (rank+1)/N — same source array
    # as the line above, so dot positions match the step exactly.
    # Outside the validation flow `_is_bin` is None and the dots are
    # silently omitted so this code path stays a no-op for real obs.
    from bc.validation_io import load_per_star_truth
    _is_bin = load_per_star_truth(result)
    if (_is_bin is not None and len(_is_bin) == len(obs_drv)
            and _n_obs_finite > 0):
        _is_bin_full = np.asarray(_is_bin, dtype=bool)
        _finite_mask = np.isfinite(obs_drv) & (obs_drv > 0)
        _is_bin_finite = _is_bin_full[_finite_mask]
        if _is_bin_finite.size == _n_obs_finite:
            _is_bin_sorted = _is_bin_finite[_sort_idx]
        else:
            _is_bin_sorted = np.zeros(_n_obs_finite, dtype=bool)
        _single_mask = ~_is_bin_sorted
        if np.any(_single_mask):
            fig_cdf.add_trace(go.Scatter(
                x=_drv_sorted[_single_mask], y=_cdf_vals[_single_mask],
                mode='markers',
                marker=dict(color=_CLR_SINGLE, size=8,
                            line=dict(color='black', width=0.6)),
                name=f'Single ({int(_single_mask.sum())})',
                hovertemplate='single · ΔRV=%{x:.1f} km/s<extra></extra>',
            ))
        if np.any(_is_bin_sorted):
            fig_cdf.add_trace(go.Scatter(
                x=_drv_sorted[_is_bin_sorted], y=_cdf_vals[_is_bin_sorted],
                mode='markers',
                marker=dict(color=_CLR_BINARY, size=8,
                            line=dict(color='black', width=0.6)),
                name=f'Binary ({int(_is_bin_sorted.sum())})',
                hovertemplate='binary · ΔRV=%{x:.1f} km/s<extra></extra>',
            ))

    # Bug 1 fix: prefer the stored best-fit CDF band (populated during the
    # grid run at runners_cadence.py:550) over re-simulating from scratch.
    # The stored arrays correspond to the global likelihood argmax — i.e.
    # the single method we have in SCORING_METHODS.
    _stored_med = result.get('best_median_cdf')
    _stored_lo = result.get('best_lo_cdf')
    _stored_hi = result.get('best_hi_cdf')
    _have_stored = (
        _stored_med is not None and _stored_lo is not None
        and _stored_hi is not None
        and np.asarray(_stored_med).size == len(_be)
    )

    _n_cdf_sets = 100

    # Round-5: per-method visual separation via decreasing band opacity;
    # line colors stay globally red (grid) / purple (marginal).
    _band_alphas_a = [0.18, 0.12, 0.08]

    def _resim_cdf_a(fb_, pi_, sig_):
        """Back-compat re-sim using the simple sampler (not cadence-aware).

        Mirrors the original loop body and is kept inside this dead-code
        function so behaviour at the grid argmax stays identical.
        """
        _all_cdfs = []
        for _seed_i in range(_n_cdf_sets):
            sim_cfg = SimulationConfig(
                n_stars=_n_obs_stars,
                sigma_single=float(sig_),
                sigma_measure=float(result.get('sigma_meas', 3.0)),
            )
            bin_cfg = BinaryParameterConfig()
            rng = np.random.default_rng(42 + _seed_i)
            sim_drv = simulate_delta_rv_sample(
                f_bin=float(fb_), pi=float(pi_),
                sim_cfg=sim_cfg, bin_cfg=bin_cfg, rng=rng)
            _all_cdfs.append(_binned_cdf(sim_drv, _be))
        _all_cdfs = np.array(_all_cdfs)
        return (np.median(_all_cdfs, axis=0),
                np.percentile(_all_cdfs, 16, axis=0),
                np.percentile(_all_cdfs, 84, axis=0))

    def _add_overlay_a(_median_cdf, _lo_cdf, _hi_cdf, color, alpha,
                       lgroup, label):
        _med_x = np.concatenate([[0.0], _be])
        _med_y = np.concatenate([[0.0], _median_cdf])
        _lo_y = np.concatenate([[0.0], _lo_cdf])
        _hi_y = np.concatenate([[0.0], _hi_cdf])
        _fill_color = _hex_to_rgba(color, alpha)
        fig_cdf.add_trace(go.Scatter(
            x=np.concatenate([_med_x, _med_x[::-1]]),
            y=np.concatenate([_hi_y, _lo_y[::-1]]),
            fill='toself', fillcolor=_fill_color,
            line=dict(color='rgba(0,0,0,0)', shape='hv'),
            legendgroup=lgroup, showlegend=False, hoverinfo='skip',
        ))
        fig_cdf.add_trace(go.Scatter(
            x=_med_x, y=_med_y,
            mode='lines', name=label, legendgroup=lgroup,
            line=dict(color=color, width=2, dash='dash', shape='hv'),
        ))

    for _mi_a, (mk, info) in enumerate(method_results.items()):
        bv = info['best_vals']
        hdi = info.get('hdi', {})
        _mname = next((n for k, n, _, _, _ in SCORING_METHODS if k == mk), mk)
        _alpha_a = _band_alphas_a[_mi_a % len(_band_alphas_a)]

        # ── GRID best-fit (joint argmax) ─────────────────────────────────
        fb_g = float(bv.get('fbin', 0.5))
        pi_g = float(bv.get(x_name, 0.0))
        sig_g = float(bv.get('sigma', 5.0))
        try:
            if _have_stored and mk == 'likelihood':
                _median_cdf = np.asarray(_stored_med, dtype=float)
                _lo_cdf = np.asarray(_stored_lo, dtype=float)
                _hi_cdf = np.asarray(_stored_hi, dtype=float)
            else:
                _median_cdf, _lo_cdf, _hi_cdf = _resim_cdf_a(fb_g, pi_g, sig_g)

            _lbl_g = f'{_mname} grid (f_bin={fb_g:.3f}'
            if x_name in bv:
                _lbl_g += f', {x_label}={bv[x_name]:.2f}'
            _lbl_g += ')'
            _sat = float(_median_cdf[-1]) if len(_median_cdf) else 1.0
            if _sat < 0.98:
                _lbl_g += f' [≤{_be[-1]:.0f} km/s: {_sat:.0%}]'
            _add_overlay_a(_median_cdf, _lo_cdf, _hi_cdf,
                           _CDF_FIT_COLOR, _alpha_a,
                           f'{mk}_grid', _lbl_g)
        except Exception:
            pass

        # ── MARGINAL best-fit (1-D posterior modes) ──────────────────────
        # hdi[name][0] = mode of the 1-D marginal posterior — same
        # canonical _method_best_and_hdi path Round-5 used for honest
        # joint-argmax + marginal-peak reporting.
        def _marg_or_grid_a(name: str, fallback):
            t = hdi.get(name)
            if t is None or not np.isfinite(t[0]):
                return fallback
            return float(t[0])

        fb_m = _marg_or_grid_a('fbin', fb_g)
        pi_m = _marg_or_grid_a(x_name, pi_g)
        sig_m = _marg_or_grid_a('sigma', sig_g)
        if (fb_m != fb_g) or (pi_m != pi_g) or (sig_m != sig_g):
            try:
                _med_m, _lo_m, _hi_m = _resim_cdf_a(fb_m, pi_m, sig_m)
                _lbl_m = f'{_mname} marginal (f_bin={fb_m:.3f}'
                if x_name in bv:
                    _lbl_m += f', {x_label}={pi_m:.2f}'
                _lbl_m += ')'
                _sat_m = float(_med_m[-1]) if len(_med_m) else 1.0
                if _sat_m < 0.98:
                    _lbl_m += f' [≤{_be[-1]:.0f} km/s: {_sat_m:.0%}]'
                _add_overlay_a(_med_m, _lo_m, _hi_m,
                               _CDF_FIT_MARG_COLOR, _alpha_a,
                               f'{mk}_marg', _lbl_m)
            except Exception:
                pass

    fig_cdf.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(text=f'CDF Comparison: {_obs_name} vs Best-Fit Models',
                      font=dict(size=14)),
        'xaxis_title': 'ΔRV (km/s)',
        'yaxis_title': 'Cumulative Fraction',
        'height': 400,
        'legend': dict(x=0.55, y=0.05),
    })
    # A&A journal theme (white bg, black serif text) — see feedback_aa_journal_style
    from bc.render_validation import _AA_OVERRIDES
    fig_cdf.update_layout(**_AA_OVERRIDES)
    fig_cdf.update_xaxes(**_AA_OVERRIDES['xaxis'])
    fig_cdf.update_yaxes(**_AA_OVERRIDES['yaxis'])
    st.plotly_chart(fig_cdf, use_container_width=True,
                    key=f'{prefix}_cdf_comparison')
    _src_desc = ('stored best-fit CDF band from the grid run'
                 if _have_stored else
                 f'median of {_n_cdf_sets} fresh draws')
    st.caption(
        f'{_obs_name} ΔRV CDF (black) vs simulated CDFs at each method\'s '
        f'grid-argmax (red dashed) and marginal-posterior peak '
        f'(purple dashed) best-fit parameters ({_src_desc}). '
        f'Bands = 16-84 percentile range. N_stars={_n_obs_stars}.  When '
        f'the simulated CDF saturates below 1 at the rightmost bin '
        f'(≤{float(_be[-1]):.0f} km/s), the remaining probability mass '
        f'lies at higher ΔRV — see the percentage shown in the legend label.'
    )


def _render_resim_interp(interp, result, mk, score_label, x_label, pfx, sm):
    """Re-simulate CDF at interpolated best-fit point."""
    st.markdown('#### Re-simulate at Interpolated Point')
    c1, c2, c3 = st.columns([0.3, 0.3, 0.4])
    ns = c1.number_input('N_sets', 100, 50000, 1000, step=100, key=f'{pfx}_{mk}_resim_n')
    if not c2.button('Re-simulate', key=f'{pfx}_{mk}_resim_btn', type='primary'):
        return
    try:
        from wr_bias_simulation import DEFAULT_DRV_BIN_EDGES
        # CDF style constants — single source of truth in render_validation.
        from bc.render_validation import _CDF_OBS_COLOR
        fb = float(interp.get('f_bin', 0.5))
        xv = float(interp.get('pi', interp.get('sigma', interp.get('y_val', 0.0))))
        sig = float(interp.get('sigma', result.get('sigma_meas', 5.0)))
        be = np.asarray(result['bin_edges']) if 'bin_edges' in result else DEFAULT_DRV_BIN_EDGES
        med_c, lo_c, hi_c, _ = _me_cdf_band(
            fb, xv, sig, float(result.get('sigma_meas', 3.0)),
            tuple(be.tolist()), n_sets=int(ns))
        obs = np.asarray(result.get('obs_delta_rv', []))
        rx = np.concatenate([[0.0], be])
        mc = next((c for k, _, _, _, c in sm if k == mk), '#E25A53')
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=be, y=_binned_cdf(obs, be), mode='lines',
            name='Observed', line=dict(color=_CDF_OBS_COLOR, width=2.5, shape='hv')))
        _hi_y = np.concatenate([[0.0], hi_c])
        _lo_y = np.concatenate([[0.0], lo_c])
        fig.add_trace(go.Scatter(x=np.concatenate([rx, rx[::-1]]),
            y=np.concatenate([_hi_y, _lo_y[::-1]]), fill='toself',
            fillcolor=_hex_to_rgba(mc, 0.2), line=dict(color='rgba(0,0,0,0)'),
            showlegend=False, hoverinfo='skip'))
        fig.add_trace(go.Scatter(x=rx, y=np.concatenate([[0.0], med_c]),
            mode='lines', name='Simulated (interp)',
            line=dict(color=mc, width=2.5, dash='dash', shape='hv')))
        fig.update_layout(**{**PLOTLY_THEME, 'height': 380,
            'title': dict(text=f'Re-sim: f_bin={fb:.4f}, {x_label}={xv:.3f}',
                          font=dict(size=14)),
            'xaxis_title': 'ΔRV (km/s)', 'yaxis_title': 'Cumulative fraction'})
        st.plotly_chart(fig, use_container_width=True, key=f'{pfx}_{mk}_resim_cdf')
        c3.metric(f'{score_label} (interp)', f"{interp.get('S', 0):.6f}")
    except Exception as err:
        st.error(f'Re-simulation failed: {err}')


def _render_method_expander(
    method_key: str,
    display_name: str,
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
    """Render one scoring method's detail panel inside an expander.

    Shows: heatmap of the 2D (fbin x x) slice, best-fit metrics,
    and calls _render_cvm_analysis with the appropriate mode.

    Parameters
    ----------
    p_nd : ndarray
        Full N-dimensional scoring array (p-value or likelihood).
    D_nd : ndarray or None
        Full N-dimensional D-statistic array.
    disp_outer_slices : tuple of int or None
        Indices for outer dimensions to select the 2D slice to display.
        For Dsilva 4D: (logPmax_idx, sigma_idx).
        For cadence 3D: (sigma_idx,).
        For Langer 2D: None (already 2D).
    method_results : dict or None
        All methods' best-fit info (from _render_method_summary_section).
        Used to render CDF comparison inside K-S expander.
    """
    _is_likelihood = (method_key == 'likelihood')
    _theme = PLOTLY_THEME
    pal = get_palette()

    # ── Squeeze trailing pi=1 dimension for cadence_langer ─────────
    if ndim_mode == 'cadence_langer' and p_nd.ndim >= 3 and p_nd.shape[-1] == 1:
        p_nd = p_nd[..., 0]
        if D_nd is not None:
            D_nd = D_nd[..., 0]

    # ── Per-method sigma slider (when sigma has >1 values) ─────────
    _sigma_g_sl = np.asarray(result.get('sigma_grid', []))
    _has_sig_slider = (_sigma_g_sl.size > 1 and p_nd.ndim >= 3
                       and ndim_mode not in ('langer', 'cadence_langer'))
    _user_sig_idx = None
    if _has_sig_slider:
        # Determine default: best sigma index from global argmax
        _tmp_best = np.unravel_index(int(np.nanargmax(p_nd)), p_nd.shape)
        if ndim_mode == 'dsilva':
            _default_sig = int(_tmp_best[1])  # [logPmax, sigma, fbin, pi]
        else:
            _default_sig = int(_tmp_best[0])  # [sigma, fbin, pi]
        _user_sig_idx = st.select_slider(
            f'σ_single slice ({display_name})',
            options=list(range(len(_sigma_g_sl))),
            format_func=lambda i: f'{_sigma_g_sl[i]:.1f} km/s',
            value=_default_sig,
            key=f'{prefix}_{method_key}_sig_slider',
        )

    # ── logPmax slider for cadence_langer with logPmax scan ──────
    _logPmax_g_sl = np.asarray(result.get('logPmax_grid', []))
    _user_lp_idx = None
    if (_logPmax_g_sl.size > 1 and p_nd.ndim >= 3
            and ndim_mode == 'cadence_langer'):
        _tmp_best_lp = np.unravel_index(int(np.nanargmax(p_nd)), p_nd.shape)
        _default_lp = int(_tmp_best_lp[0])  # [logPmax, sigma, fbin]
        _user_lp_idx = st.select_slider(
            f'logP_max slice ({display_name})',
            options=list(range(len(_logPmax_g_sl))),
            format_func=lambda i: f'{_logPmax_g_sl[i]:.2f}',
            value=_default_lp,
            key=f'{prefix}_{method_key}_lp_slider',
        )

    # Slice down to 2D: [fbin, x]
    if _user_lp_idx is not None:
        # cadence_langer logPmax slider: slice axis 0 → [sigma, fbin]
        p_2d = p_nd[_user_lp_idx]
        D_2d = D_nd[_user_lp_idx] if D_nd is not None else None
    elif _user_sig_idx is not None:
        # User-selected sigma slice overrides disp_outer_slices
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

    # For cadence_langer: sliced p_2d may be [sigma, fbin] → transpose to [fbin, sigma]
    if (ndim_mode == 'cadence_langer'
            and p_2d.ndim == 2
            and p_2d.shape[0] != len(fbin_g)
            and p_2d.shape[1] == len(fbin_g)):
        p_2d = p_2d.T
        if D_2d is not None:
            D_2d = D_2d.T

    # Global best across all dimensions
    valid = np.isfinite(p_nd)
    if not np.any(valid):
        st.warning(f'No valid data for {display_name}.')
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
    # For Dsilva 4D: axes are [logPmax, sigma, fbin, pi]
    if ndim_mode == 'dsilva':
        g_fb = float(fbin_g[global_best_idx[2]])
        g_x = float(x_g[global_best_idx[3]])
    elif ndim_mode == 'cadence_dsilva':
        # cadence_dsilva 3D: [sigma, fbin, pi]
        g_fb = float(fbin_g[global_best_idx[-2]])
        g_x = float(x_g[global_best_idx[-1]])
    elif ndim_mode == 'cadence_langer':
        # cadence_langer after pi squeeze: 3D [logPmax, sigma, fbin] or 2D [fbin, sigma]
        if p_nd.ndim == 3:
            g_fb = float(fbin_g[global_best_idx[2]])   # fbin is axis 2
            g_x = float(x_g[global_best_idx[1]])       # sigma is axis 1
        else:
            g_fb = float(fbin_g[global_best_idx[0]])
            g_x = float(x_g[global_best_idx[1]])
    else:
        # 2D: [fbin, x]
        g_fb = float(fbin_g[global_best_idx[0]])
        g_x = float(x_g[global_best_idx[1]])

    if _is_likelihood:
        score_label = 'Likelihood'
    elif method_key == 'cvm':
        score_label = 'CvM S-score'
    else:
        score_label = 'p-value'

    # ── Heatmap ──────────────────────────────────────────────────
    show_d = not _is_likelihood
    fig_hm = _make_heatmap_fig(
        p_2d, fbin_g, x_g,
        title=f'{display_name} — {score_label}',
        show_d=show_d,
        ks_d_2d=D_2d if show_d else None,
        height=height, width=width,
        x_label=x_display_label,
        x_name=x_name,
        scoring_label=display_name,
        colorbar_title_override=score_label if _is_likelihood else None,
    )
    st.plotly_chart(fig_hm, use_container_width=use_cw,
                    key=f'{prefix}_{method_key}_hm')

    # ── Extra heatmaps for multi-axis models ─────────────────────
    _logPmax_g_extra = np.asarray(result.get('logPmax_grid', []))
    _sigma_g_extra = np.asarray(result.get('sigma_grid', []))
    if _logPmax_g_extra.size > 1 and _sigma_g_extra.size > 1 and p_nd.ndim >= 3:
        # Marginalize to show additional 2D views
        # p_nd axes for cadence_langer after pi squeeze: [logPmax, sigma, fbin]
        _ec1, _ec2 = st.columns(2)
        with _ec1:
            # f_bin vs logPmax (max over sigma axis=1)
            _fb_lp = np.nanmax(p_nd, axis=(1, 3)) if p_nd.ndim == 4 else np.nanmax(p_nd, axis=1)  # [logPmax, fbin]
            _fb_lp_fig = _make_heatmap_fig(
                _fb_lp.T, fbin_g, _logPmax_g_extra,
                title=f'{display_name} — f_bin × logP_max (max over σ)',
                show_d=False, height=400,
                x_label='log₁₀(P_max / days)', x_name='logP_max',
                scoring_label=display_name,
                colorbar_title_override=score_label if _is_likelihood else None,
            )
            st.plotly_chart(_fb_lp_fig, use_container_width=True,
                            key=f'{prefix}_{method_key}_hm_fb_lp')
        with _ec2:
            # σ vs logPmax (max over fbin axis=2)
            _sig_lp = np.nanmax(p_nd, axis=(2, 3)) if p_nd.ndim == 4 else np.nanmax(p_nd, axis=2)  # [logPmax, sigma]
            _sig_lp_fig = _make_heatmap_fig(
                _sig_lp.T, _sigma_g_extra, _logPmax_g_extra,
                title=f'{display_name} — σ × logP_max (max over f_bin)',
                show_d=False, height=400,
                x_label='log₁₀(P_max / days)', x_name='logP_max',
                y_label='σ_single (km/s)',
                scoring_label=display_name,
                colorbar_title_override=score_label if _is_likelihood else None,
            )
            st.plotly_chart(_sig_lp_fig, use_container_width=True,
                            key=f'{prefix}_{method_key}_hm_sig_lp')

    # ── Slice vs Global metrics ──────────────────────────────────
    # For 2D arrays (Langer, cadence_langer) the slice IS the global — show
    # a single "Best fit" card instead of the redundant slice-vs-global pair.
    _is_2d_mode = ndim_mode in ('langer', 'cadence_langer') or p_nd.ndim <= 2
    if _is_2d_mode:
        st.metric(
            label=f'Best fit ({display_name})',
            value=f'f_bin={g_fb:.4f}, {x_label}={g_x:.3f}',
            delta=f'{score_label} = {global_best_score:.6f}',
            delta_color='off',
        )
    else:
        mc1, mc2 = st.columns(2)
        mc1.metric(
            label=f'Current slice best ({display_name})',
            value=f'f_bin={slice_best_fb:.4f}, {x_label}={slice_best_x:.3f}',
            delta=f'{score_label} = {slice_best_score:.6f}',
            delta_color='off',
        )
        mc2.metric(
            label=f'Global best ({display_name})',
            value=f'f_bin={g_fb:.4f}, {x_label}={g_x:.3f}',
            delta=f'{score_label} = {global_best_score:.6f}',
            delta_color='off',
        )

    # ── Scoring analysis (reuse _render_cvm_analysis) ────────────
    _obs_drv = result.get('obs_delta_rv')
    _lk_edges = result.get('likelihood_bin_edges')
    if method_key in ('cvm', 'likelihood'):
        _mode = method_key
        # Extract sigma/logPmax grids and full ND arrays for 3D fit passthrough
        _sigma_g_fit = np.asarray(result.get('sigma_grid', []))
        _logPmax_g_fit = np.asarray(result.get('logPmax_grid', []))
        _full_D_3d = None
        _full_p_3d = None
        _dk_key = {'cvm': 'cvm_D', 'likelihood': 'logL_raw'}[method_key]
        _pk_key = {'cvm': 'cvm_p', 'likelihood': 'likelihood'}[method_key]
        _raw_D = _get_method_array(result, _dk_key)
        _raw_p = _get_method_array(result, _pk_key)

        if _sigma_g_fit.size > 1 and _raw_D is not None:
            # sigma is the 3rd fit axis
            if ndim_mode == 'dsilva' and _raw_D.ndim == 4:
                _lp_idx = disp_outer_slices[0] if disp_outer_slices else 0
                _full_D_3d = _raw_D[_lp_idx]  # → [sigma, fbin, pi]
                _full_p_3d = _raw_p[_lp_idx] if _raw_p is not None else None
            elif _raw_D.ndim == 3:
                _full_D_3d = _raw_D
                _full_p_3d = _raw_p
        elif _logPmax_g_fit.size > 1 and _raw_D is not None:
            # logPmax is the 3rd fit axis (sigma is single)
            if _raw_D.ndim >= 3:
                # Take sigma slice if needed
                if _raw_D.ndim == 4:
                    _sig_idx = disp_outer_slices[1] if (disp_outer_slices and len(disp_outer_slices) > 1) else 0
                    _full_D_3d = _raw_D[:, _sig_idx, :, :]  # → [logPmax, fbin, pi]
                    _full_p_3d = _raw_p[:, _sig_idx, :, :] if _raw_p is not None else None
                else:
                    _full_D_3d = _raw_D
                    _full_p_3d = _raw_p

        _render_cvm_analysis(
            D_2d if D_2d is not None else p_2d,
            p_2d,
            fbin_g, x_g,
            x_label='f_bin', y_label=x_label,
            sigma_grid=_sigma_g_fit if _sigma_g_fit.size > 1 else None,
            logPmax_grid=_logPmax_g_fit if (_logPmax_g_fit.size > 1 and _sigma_g_fit.size <= 1) else None,
            ks_D_3d=_full_D_3d,
            ks_p_3d=_full_p_3d,
            height=height, width=width,
            prefix=f'{prefix}_{method_key}_analysis',
            mode=_mode,
            obs_delta_rv=_obs_drv,
            likelihood_bin_edges=_lk_edges,
            result=result,
        )

    # ── Score vs σ_single (all methods with multiple σ values) ──
    _sigma_g = np.asarray(result.get('sigma_grid', []))
    if _sigma_g.size > 1:
        from bc.helpers import _make_max_pval_fig, _make_min_score_fig
        # Get full ND score array for this method
        _pk = next((pk for mk, _, pk, _, _ in SCORING_METHODS if mk == method_key), None)
        _full_arr = _get_method_array(result, _pk) if _pk else None
        if _full_arr is not None:
            # Compute best score per sigma (maximize for p-value/likelihood, minimize for D-stat)
            _is_cvm = (method_key == 'cvm')
            # For CvM: use D-statistic (lower=better); for others: use p/likelihood (higher=better)
            if _is_cvm:
                _dk = next((dk for mk, _, _, dk, _ in SCORING_METHODS if mk == 'cvm'), None)
                _d_arr = _get_method_array(result, _dk)
                _score_arr = _d_arr if _d_arr is not None else _full_arr
            else:
                _score_arr = _full_arr

            # Determine sigma axis and compute per-sigma score
            _per_sig = None
            if _score_arr.ndim == 4:
                # Dsilva 4D: [logPmax, sigma, fbin, pi]
                if _is_cvm:
                    _per_sig = np.nanmin(_score_arr, axis=(0, 2, 3))
                else:
                    _per_sig = np.nanmax(_score_arr, axis=(0, 2, 3))
            elif _score_arr.ndim == 3:
                # Cadence 3D: [sigma, fbin, pi]
                if _is_cvm:
                    _per_sig = np.nanmin(_score_arr, axis=(1, 2))
                else:
                    _per_sig = np.nanmax(_score_arr, axis=(1, 2))
            elif _score_arr.ndim == 2:
                # Langer 2D: [fbin, sigma]
                if _is_cvm:
                    _per_sig = np.nanmin(_score_arr, axis=0)
                else:
                    _per_sig = np.nanmax(_score_arr, axis=0)

            if _per_sig is not None and _per_sig.size == _sigma_g.size:
                st.divider()
                _mname_sig = next((n for mk, n, _, _, _ in SCORING_METHODS if mk == method_key), method_key)
                if _is_cvm:
                    _fig_sig = _make_min_score_fig(
                        _sigma_g, list(_per_sig), height=350,
                        x_label='σ_single (km/s)', stat_label=_mname_sig)
                else:
                    _fig_sig = _make_max_pval_fig(
                        _sigma_g, list(_per_sig), height=350,
                        x_label='σ_single (km/s)', stat_label=_mname_sig)
                st.plotly_chart(_fig_sig, use_container_width=use_cw,
                                key=f'{prefix}_{method_key}_sig_profile')

    # ── Score vs logP_max (all methods with multiple logPmax values) ──
    _logPmax_g = np.asarray(result.get('logPmax_grid', []))
    if _logPmax_g.size > 1:
        from bc.helpers import _make_max_pval_fig, _make_min_score_fig
        _pk_lp = next((pk for mk, _, pk, _, _ in SCORING_METHODS if mk == method_key), None)
        _full_lp = _get_method_array(result, _pk_lp) if _pk_lp else None
        if _full_lp is not None:
            _is_cvm_lp = (method_key == 'cvm')
            if _is_cvm_lp:
                _dk_lp = next((dk for mk, _, _, dk, _ in SCORING_METHODS if mk == 'cvm'), None)
                _d_lp = _get_method_array(result, _dk_lp)
                _score_lp = _d_lp if _d_lp is not None else _full_lp
            else:
                _score_lp = _full_lp

            # logPmax is always axis 0 when present
            _other_axes = tuple(range(1, _score_lp.ndim))
            if _other_axes:
                if _is_cvm_lp:
                    _per_lp = np.nanmin(_score_lp, axis=_other_axes)
                else:
                    _per_lp = np.nanmax(_score_lp, axis=_other_axes)

                if _per_lp.size == _logPmax_g.size:
                    st.divider()
                    _mname_lp = next((n for mk, n, _, _, _ in SCORING_METHODS
                                      if mk == method_key), method_key)
                    if _is_cvm_lp:
                        _fig_lp = _make_min_score_fig(
                            _logPmax_g, list(_per_lp), height=350,
                            x_label='logP_max', stat_label=_mname_lp)
                    else:
                        _fig_lp = _make_max_pval_fig(
                            _logPmax_g, list(_per_lp), height=350,
                            x_label='logP_max', stat_label=_mname_lp)
                    st.plotly_chart(_fig_lp, use_container_width=use_cw,
                                    key=f'{prefix}_{method_key}_logPmax_profile')

    # ── Corner Plot (N-param: fbin × x × sigma × logPmax if available) ──
    from bc.corner_plots import _render_corner_plot
    _info = _render_corner_plot(
        p_nd, fbin_g, x_g, x_name, x_display_label,
        display_name, _is_likelihood, ndim_mode,
        result, prefix, method_key, pal, use_cw,
    )

    # ── Per-method best-fit summary table ─────────────────────────────
    if _info is not None:
        st.divider()
        st.markdown(f'#### Best-fit Summary — {display_name}')
        _bv_s = _info['best_vals']
        _hdi_s = _info['hdi']

        def _fmt_hdi_s(name, fmt='.3f'):
            if name not in _hdi_s:
                return '—'
            m, lo, hi = _hdi_s[name]
            return f'{m:{fmt}} +{hi - m:{fmt}} / −{m - lo:{fmt}}'

        # Check for interpolated best-fit from parabolic/neighborhood fit
        _interp_key = f'{prefix}_interp'
        _interp = st.session_state.get(_interp_key)

        _sum_rows = []
        _row_fb = {'Parameter': 'f_bin',
                   'Best (grid)': f"{_bv_s.get('fbin', 0):.4f}",
                   'Mode ± HDI68': _fmt_hdi_s('fbin', '.4f')}
        if _interp and 'f_bin' in _interp:
            _row_fb['Interpolated'] = f"{_interp['f_bin']:.4f}"
        _sum_rows.append(_row_fb)

        if x_name in _bv_s:
            _row_x = {'Parameter': x_label,
                      'Best (grid)': f"{_bv_s[x_name]:.3f}",
                      'Mode ± HDI68': _fmt_hdi_s(x_name, '.3f')}
            if _interp:
                _iv = _interp.get('pi', _interp.get('sigma',
                      _interp.get('y_val')))
                _row_x['Interpolated'] = f'{_iv:.3f}' if _iv is not None else '—'
            _sum_rows.append(_row_x)

        if 'sigma' in _bv_s and x_name != 'sigma':
            _row_sig = {'Parameter': 'σ_single (km/s)',
                        'Best (grid)': f"{_bv_s['sigma']:.2f}",
                        'Mode ± HDI68': _fmt_hdi_s('sigma', '.2f')}
            if _interp and 'sigma' in _interp:
                _row_sig['Interpolated'] = f"{_interp['sigma']:.2f}"
            _sum_rows.append(_row_sig)

        if 'logPmax' in _bv_s:
            _row_lp = {'Parameter': 'logP_max',
                       'Best (grid)': f"{_bv_s['logPmax']:.2f}",
                       'Mode ± HDI68': _fmt_hdi_s('logPmax', '.2f')}
            if _interp and 'logPmax' in _interp:
                _row_lp['Interpolated'] = f"{_interp['logPmax']:.2f}"
            _sum_rows.append(_row_lp)

        _row_score = {'Parameter': score_label,
                      'Best (grid)': f"{_info['best_score']:.6f}",
                      'Mode ± HDI68': '—'}
        if _interp and 'S' in _interp:
            _row_score['Interpolated'] = f"{_interp['S']:.6f}"
        _sum_rows.append(_row_score)

        st.table(pd.DataFrame(_sum_rows))

        # ── Re-simulate at interpolated point ─────────────────────────
        _interp = st.session_state.get(f'{prefix}_interp')
        if _interp is not None:
            _render_resim_interp(
                _interp, result, method_key, score_label, x_label,
                prefix, SCORING_METHODS)

    # ── Model Explorer (best-fit CDF, histogram, detection fraction) ──
    _obs_drv_me = result.get('obs_delta_rv')
    if _obs_drv_me is not None:
        st.divider()
        with st.expander(f'Model Explorer — {display_name}', expanded=False):
            _render_model_explorer(
                result, method_key, display_name, score_label,
                fbin_g, x_g, x_name, x_label, prefix, _info,
                _is_likelihood, p_nd,
            )

    # ── CDF sanity check (cadence tabs) ───────────────────────────────
    if ndim_mode in ('cadence_dsilva', 'cadence_langer') and _info is not None:
        _osc = result.get('obs_delta_rv')
        if _osc is not None:
            _bv = _info['best_vals']
            _pm = 'dsilva' if ndim_mode == 'cadence_dsilva' else 'langer'
            try:
                from bc.helpers import _render_cdf_sanity_check
                _render_cdf_sanity_check(
                    _bv.get('fbin', 0.5), _bv.get(x_name, 0.0),
                    _bv.get('sigma', float(result.get('sigma_meas', 5.0))),
                    np.asarray(_osc), _pm, result, {}, f'{prefix}_{method_key}')
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Model Explorer — extracted from _render_method_expander for readability
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _me_cdf_band(
    fb: float, x_val: float, sigma_s: float, sigma_m: float,
    bin_edges_tuple: tuple, n_sets: int = 50,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Run *n_sets* simulations and return (median_cdf, lo_cdf, hi_cdf, pooled_drv)."""
    from wr_bias_simulation import (
        simulate_delta_rv_sample, SimulationConfig,
        BinaryParameterConfig,
    )
    _be = np.array(bin_edges_tuple)
    all_cdfs, all_drv = [], []
    for si in range(n_sets):
        cfg = SimulationConfig(n_stars=1000, sigma_single=sigma_s, sigma_measure=sigma_m)
        drv = simulate_delta_rv_sample(fb, x_val, cfg, BinaryParameterConfig(),
                                       np.random.default_rng(42 + si))
        all_cdfs.append(_binned_cdf(drv, _be))
        all_drv.append(drv)
    all_cdfs = np.array(all_cdfs)
    return (np.median(all_cdfs, axis=0),
            np.percentile(all_cdfs, 16, axis=0),
            np.percentile(all_cdfs, 84, axis=0),
            np.concatenate(all_drv))


def _render_model_explorer(
    result: dict, method_key: str, display_name: str, score_label: str,
    fbin_g: np.ndarray, x_g: np.ndarray, x_name: str, x_label: str,
    prefix: str, _info: dict | None,
    _is_likelihood: bool, p_nd: np.ndarray,
) -> None:
    """Interactive model explorer: sliders → CDF (with error band) + score + histogram + det frac."""
    try:
        from wr_bias_simulation import (
            simulate_delta_rv_sample, SimulationConfig,
            BinaryParameterConfig, DEFAULT_DRV_BIN_EDGES,
            multinomial_log_likelihood,
        )
    except ImportError:
        st.info('wr_bias_simulation not available for model explorer.')
        return

    # Best-fit defaults for sliders
    me_info = _info
    if me_info is None:
        me_info = _method_best_and_hdi(
            p_nd,
            [fbin_g, x_g], ['fbin', x_name],
            is_likelihood=_is_likelihood,
        )
    if me_info is None:
        st.info('Could not determine best-fit parameters.')
        return

    bv = me_info['best_vals']
    def_fb = float(bv.get('fbin', 0.5))
    def_x = float(bv.get(x_name, 0.0))
    def_sig = float(bv.get('sigma', result.get('sigma_meas', 5.0)))

    # Sliders — add logPmax column when grid has >1 value
    _lp_g = np.asarray(result.get('logPmax_grid', []))
    _ncols = 4 if _lp_g.size > 1 else 3
    cols = st.columns(_ncols)
    me_fb = cols[0].slider('f_bin', 0.0, 1.0, def_fb, 0.01,
                           key=f'{prefix}_{method_key}_me_fb')
    x_lo, x_hi = (float(x_g[0]) if len(x_g) else -3.0,
                   float(x_g[-1]) if len(x_g) else 3.0)
    me_x = cols[1].slider(x_label, x_lo, x_hi,
                          min(max(def_x, x_lo), x_hi), 0.01,
                          key=f'{prefix}_{method_key}_me_x')
    sig_g = np.asarray(result.get('sigma_grid', []))
    if sig_g.size > 1:
        me_sig = cols[2].slider(
            'σ_single (km/s)', float(sig_g[0]), float(sig_g[-1]),
            min(max(def_sig, float(sig_g[0])), float(sig_g[-1])),
            0.1, key=f'{prefix}_{method_key}_me_sig')
    else:
        me_sig = def_sig
    me_logPmax = None
    if _lp_g.size > 1:
        _dlp = float(bv.get('logPmax', float(_lp_g[0])))
        _c = cols[3] if sig_g.size > 1 else cols[2]
        me_logPmax = _c.slider(
            'logP_max', float(_lp_g[0]), float(_lp_g[-1]),
            min(max(_dlp, float(_lp_g[0])), float(_lp_g[-1])),
            0.1, key=f'{prefix}_{method_key}_me_logPmax')

    obs_drv = np.asarray(result.get('obs_delta_rv'))
    be = result.get('bin_edges')
    be = np.asarray(be) if be is not None else DEFAULT_DRV_BIN_EDGES
    sigma_m = float(result.get('sigma_meas', 3.0))

    # Likelihood-specific bin edges
    lk_be = result.get('likelihood_bin_edges')
    if lk_be is not None:
        lk_be = np.asarray(lk_be)

    # Multi-seed CDF band (cached)
    med_cdf, lo_cdf, hi_cdf, pooled_drv = _me_cdf_band(
        me_fb, me_x, me_sig, sigma_m, tuple(be.tolist()), n_sets=50)

    # ── Score metric ────────────────────────────────────────────
    _use_be = lk_be if lk_be is not None else be
    _logL = multinomial_log_likelihood(obs_drv, pooled_drv, _use_be)
    _score_val = f'{_logL:.2f}'

    sc1, sc2 = st.columns([0.35, 0.65])
    sc1.metric(score_label, _score_val)
    sc2.caption(f'f_bin={me_fb:.3f}, {x_label}={me_x:.2f}, σ_single={me_sig:.1f} km/s')

    # ── CDF with error shadow ──────────────────────────────────
    obs_cdf = _binned_cdf(obs_drv, be)
    med_x = np.concatenate([[0.0], be])
    med_y = np.concatenate([[0.0], med_cdf])
    lo_y = np.concatenate([[0.0], lo_cdf])
    hi_y = np.concatenate([[0.0], hi_cdf])

    mcolor = next((c for k, _, _, _, c in SCORING_METHODS if k == method_key), '#E25A53')

    # Conditional "Mock Observation" label in validation flow
    from bc.helpers import _obs_label as _obs_label_me
    _obs_name_me = _obs_label_me(result)

    # CDF style constants — single source of truth (Phase 6 finishing pass)
    from bc.render_validation import _CDF_OBS_COLOR, _CDF_FIT_COLOR

    fig_cdf = go.Figure()
    fig_cdf.add_trace(go.Scatter(
        x=be, y=obs_cdf, mode='lines', name=_obs_name_me,
        line=dict(color=_CDF_OBS_COLOR, width=2.5, shape='hv'),
    ))
    # Error band (legendgroup links shadow to line for toggle)
    fig_cdf.add_trace(go.Scatter(
        x=np.concatenate([med_x, med_x[::-1]]),
        y=np.concatenate([hi_y, lo_y[::-1]]),
        fill='toself', fillcolor=_hex_to_rgba(mcolor, 0.2),
        line=dict(color='rgba(0,0,0,0)'),
        legendgroup='sim', showlegend=False, hoverinfo='skip',
    ))
    fig_cdf.add_trace(go.Scatter(
        x=med_x, y=med_y, mode='lines', name='Simulated (median)',
        legendgroup='sim',
        line=dict(color=mcolor, width=2.5, dash='dash', shape='hv'),
    ))
    fig_cdf.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(
            text=f'CDF — {score_label}={_score_val}',
            font=dict(size=14)),
        'xaxis_title': 'ΔRV (km/s)',
        'yaxis_title': 'Cumulative fraction',
        'height': 380,
        'legend': dict(x=0.6, y=0.15),
    })
    # ── Bin overlay toggle ──────────────────────────────────────
    _show_bins_me = st.checkbox('Show bin edges on CDF', value=False,
                                key=f'{prefix}_{method_key}_me_show_bins')
    if _show_bins_me:
        _alt = ['rgba(100,100,100,0.08)', 'rgba(100,100,100,0.15)']
        for _bi in range(len(be) - 1):
            fig_cdf.add_vrect(x0=float(be[_bi]), x1=float(be[_bi + 1]),
                              fillcolor=_alt[_bi % 2], layer='below', line_width=0)
        for _ei in range(len(be)):
            fig_cdf.add_vline(x=float(be[_ei]), line=dict(color='grey', width=1, dash='dot'))
    st.plotly_chart(fig_cdf, use_container_width=True,
                    key=f'{prefix}_{method_key}_me_cdf')
    if _show_bins_me:
        _no, _ns = np.histogram(obs_drv, bins=be)[0], np.histogram(pooled_drv, bins=be)[0]
        _sf = _ns / max(_ns.sum(), 1)
        _br = [{'Bin': f'{be[i]:.0f}–{be[i+1]:.0f}', 'N_obs': int(_no[i]),
                'N_sim': int(_ns[i]), 'Sim frac': f'{_sf[i]:.3f}'}
               for i in range(len(be) - 1)]
        st.dataframe(pd.DataFrame(_br), use_container_width=True, hide_index=True)

    # ── Histogram overlay ──────────────────────────────────────
    sim_drv_single = pooled_drv[:1000]  # use first seed for histogram
    fig_hist = go.Figure()
    fig_hist.add_trace(go.Histogram(
        x=obs_drv, nbinsx=30, histnorm='probability density',
        name=_obs_name_me, marker_color=_CDF_OBS_COLOR, opacity=0.6,
    ))
    fig_hist.add_trace(go.Histogram(
        x=sim_drv_single, nbinsx=30, histnorm='probability density',
        name='Simulated', marker_color=_CDF_FIT_COLOR, opacity=0.5,
    ))
    fig_hist.update_layout(**{
        **PLOTLY_THEME,
        'barmode': 'overlay',
        'title': dict(text='ΔRV Distribution', font=dict(size=14)),
        'xaxis_title': 'ΔRV (km/s)',
        'yaxis_title': 'Probability density',
        'height': 380,
        'legend': dict(x=0.65, y=0.95),
    })
    st.plotly_chart(fig_hist, use_container_width=True,
                    key=f'{prefix}_{method_key}_me_hist')

    # ── Detection fraction vs threshold ────────────────────────
    max_drv = max(float(np.max(obs_drv)), float(np.max(sim_drv_single)))
    thresholds = np.linspace(0, max_drv * 1.1, 100)
    frac_obs = np.array([(obs_drv > T).mean() for T in thresholds])
    frac_sim = np.array([(sim_drv_single > T).mean() for T in thresholds])

    fig_det = go.Figure()
    fig_det.add_trace(go.Scatter(
        x=thresholds, y=frac_obs, mode='lines', name=_obs_name_me,
        line=dict(color=_CDF_OBS_COLOR, width=2.5),
    ))
    fig_det.add_trace(go.Scatter(
        x=thresholds, y=frac_sim, mode='lines', name='Simulated',
        line=dict(color=_CDF_FIT_COLOR, width=2.5, dash='dash'),
    ))
    thresh_dRV = float(result.get('thresh_dRV', 45.5))
    fig_det.add_vline(
        x=thresh_dRV, line_dash='dot', line_color='#DAA520', line_width=1.5,
        annotation_text=f'Threshold={thresh_dRV:.0f}',
        annotation_position='top right',
        annotation_font_color='#DAA520',
    )
    fig_det.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(
            text=f'Detection Fraction (f_bin={me_fb:.3f}, {x_label}={me_x:.2f})',
            font=dict(size=14)),
        'xaxis_title': 'ΔRV threshold (km/s)',
        'yaxis_title': 'Fraction above threshold',
        'height': 380,
        'yaxis': dict(range=[0, 1.05]),
        'legend': dict(x=0.65, y=0.95),
    })
    st.plotly_chart(fig_det, use_container_width=True,
                    key=f'{prefix}_{method_key}_me_det')

    st.caption(
        f'Model explorer for {display_name}. '
        f'CDF shows median ± 68% band from 50 simulations. '
        f'{score_label} computed from pooled simulated data.'
    )
