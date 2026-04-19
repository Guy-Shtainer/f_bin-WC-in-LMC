"""bc.render_lk_explorer -- Likelihood interactive exploration tools.

Model explorer (sliders + CDF + histogram + detection fraction),
re-simulation at interpolated best-fit, and CDF sanity check (cadence).
Hardcoded for Likelihood scoring -- no K-S/CvM branches.
"""
from __future__ import annotations

import os
import sys
from typing import Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def _binned_cdf(data: np.ndarray, bin_edges: np.ndarray) -> np.ndarray:
    """Empirical CDF at bin_edges."""
    s = np.sort(data)
    return np.searchsorted(s, bin_edges, side='right') / len(s)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from shared import PLOTLY_THEME

_METHOD_KEY = 'likelihood'
_DISPLAY_NAME = 'Likelihood'
_METHOD_COLOR = '#DAA520'


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Convert hex color to rgba string."""
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'rgba({r},{g},{b},{alpha})'


# ---------------------------------------------------------------------------
# Cached CDF band helper
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def _me_cdf_band_langer(
    fb: float, logPmax: float, sigma_s: float, sigma_m: float,
    bin_edges_tuple: tuple, n_sets: int = 50,
    _cadence_library=None, _cadence_weights=None,
    _bin_cfg_dict=None, period_model: str = 'langer2020',
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Langer-specific CDF band: uses langer2020 period model with logP_max.

    E048 fix: when _bin_cfg_dict is supplied (hashable tuple from the grid
    result), the full bin_cfg is reconstituted so the re-simulated CDF/logL
    matches the physics surface the grid scored. When _cadence_library is
    supplied, runs cadence-aware simulation (matching the grid worker).
    """
    from wr_bias_simulation import (
        simulate_delta_rv_sample, simulate_delta_rv_cadence_aware,
        SimulationConfig, BinaryParameterConfig,
    )
    _be = np.array(bin_edges_tuple)
    if _bin_cfg_dict is not None:
        try:
            _bc_d = dict(_bin_cfg_dict)
            bin_cfg = BinaryParameterConfig(**_bc_d)
        except Exception:
            bin_cfg = BinaryParameterConfig(
                period_model='langer2020', logP_max=logPmax)
    else:
        bin_cfg = BinaryParameterConfig(
            period_model='langer2020', logP_max=logPmax)
    bin_cfg.logP_max = float(logPmax)
    bin_cfg.period_model = period_model

    if _cadence_library is not None:
        cfg = SimulationConfig(
            n_stars=len(_cadence_library),
            sigma_single=sigma_s, sigma_measure=sigma_m,
            cadence_library=_cadence_library,
            cadence_weights=_cadence_weights)
        rng = np.random.default_rng(42)
        res = simulate_delta_rv_cadence_aware(
            fb, 0.0, cfg, bin_cfg, rng, n_sets=n_sets, bin_edges=_be)
        all_drv = res['all_delta_rv']
        all_cdfs = np.array(
            [_binned_cdf(all_drv[i], _be) for i in range(all_drv.shape[0])])
        pooled = all_drv.ravel()
    else:
        all_cdfs, all_drv_list = [], []
        for si in range(n_sets):
            cfg = SimulationConfig(n_stars=1000, sigma_single=sigma_s,
                                   sigma_measure=sigma_m)
            drv = simulate_delta_rv_sample(fb, 0.0, cfg, bin_cfg,
                                           np.random.default_rng(42 + si))
            all_cdfs.append(_binned_cdf(drv, _be))
            all_drv_list.append(drv)
        all_cdfs = np.array(all_cdfs)
        pooled = np.concatenate(all_drv_list)

    return (np.median(all_cdfs, axis=0),
            np.percentile(all_cdfs, 16, axis=0),
            np.percentile(all_cdfs, 84, axis=0),
            pooled)


# --- E048 helpers: reuse the Dsilva implementations ----------------------
# Kept as thin re-exports so the Langer side doesn't duplicate the
# freeze/load logic (memory rule allows duplication but there's no Dsilva
# vs Langer divergence for these utilities — they operate only on the
# result dict).
from bc.render_lk_explorer import (  # noqa: E402
    _result_bin_cfg_tuple,
    _result_period_model,
)


# ---------------------------------------------------------------------------
# Re-simulation at interpolated best-fit point
# ---------------------------------------------------------------------------

def _render_lk_resim_interp(interp, result, x_label, pfx):
    """Re-simulate CDF at interpolated best-fit point for Likelihood scoring."""
    st.markdown('#### Re-simulate at Interpolated Point')
    c1, c2, c3 = st.columns([0.3, 0.3, 0.4])
    ns = c1.number_input('N_sets', 100, 50000, 1000, step=100,
                         key=f'{pfx}_lk_resim_n')
    if not c2.button('Re-simulate', key=f'{pfx}_lk_resim_btn',
                     type='primary'):
        return
    try:
        from wr_bias_simulation import (
            DEFAULT_DRV_BIN_EDGES,
            multinomial_log_likelihood,
        )
        fb = float(interp.get('f_bin', 0.5))
        _lp_resim = float(interp.get('logPmax',
                          interp.get('y_val', 3.5)))
        sig = float(interp.get('sigma', result.get('sigma_meas', 5.0)))
        be = (np.asarray(result['bin_edges'])
              if 'bin_edges' in result else DEFAULT_DRV_BIN_EDGES)
        lk_be = (np.asarray(result['likelihood_bin_edges'])
                 if 'likelihood_bin_edges' in result else be)
        # E048: thread full physics config.
        _bc_tuple_l = _result_bin_cfg_tuple(result)
        _pm_l = _result_period_model(result, default='langer2020')
        _cad_lib_l = result.get('cadence_library')
        _cad_wt_l = result.get('cadence_weights')
        med_c, lo_c, hi_c, pooled = _me_cdf_band_langer(
            fb, _lp_resim, sig, float(result.get('sigma_meas', 3.0)),
            tuple(be.tolist()), n_sets=int(ns),
            _cadence_library=_cad_lib_l, _cadence_weights=_cad_wt_l,
            _bin_cfg_dict=_bc_tuple_l, period_model=_pm_l,
        )
        obs = np.asarray(result.get('obs_delta_rv', []))
        rx = np.concatenate([[0.0], be])

        # Compute likelihood score
        logL = multinomial_log_likelihood(obs, pooled, lk_be)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=be, y=_binned_cdf(obs, be), mode='lines',
            name='Observed',
            line=dict(color='#4A90D9', width=2.5, shape='hv')))
        _hi_y = np.concatenate([[0.0], hi_c])
        _lo_y = np.concatenate([[0.0], lo_c])
        fig.add_trace(go.Scatter(
            x=rx, y=_lo_y, mode='lines',
            line=dict(color='rgba(0,0,0,0)', shape='hv'),
            showlegend=False, hoverinfo='skip'))
        fig.add_trace(go.Scatter(
            x=rx, y=_hi_y, mode='lines',
            line=dict(color='rgba(0,0,0,0)', shape='hv'),
            fill='tonexty',
            fillcolor=_hex_to_rgba(_METHOD_COLOR, 0.2),
            showlegend=False, hoverinfo='skip'))
        fig.add_trace(go.Scatter(
            x=rx, y=np.concatenate([[0.0], med_c]),
            mode='lines', name='Simulated (interp)',
            line=dict(color=_METHOD_COLOR, width=2.5, dash='dash',
                      shape='hv')))
        fig.update_layout(**{
            **PLOTLY_THEME, 'height': 380,
            'title': dict(
                text=f'Re-sim: f_bin={fb:.4f}, {x_label}={xv:.3f}',
                font=dict(size=14)),
            'xaxis_title': 'DeltaRV (km/s)',
            'yaxis_title': 'Cumulative fraction',
        })
        st.plotly_chart(fig, use_container_width=True,
                        key=f'{pfx}_lk_resim_cdf')
        c3.metric('ln L (interp)', f"{logL:.3f}")
    except Exception as err:
        st.error(f'Re-simulation failed: {err}')


# ---------------------------------------------------------------------------
# CDF Sanity Check (cadence tabs only)
# ---------------------------------------------------------------------------

# WORKING — do not change this code (D18: CDF Sanity Check)
def _render_lk_cdf_sanity_check(best_fbin, best_x, sigma_single,
                                obs_delta_rv, period_model, result,
                                p_prefix: str) -> None:
    """Render 5 random CDF draws vs observed for cadence sanity check.

    Generates 5 independent sets of 25 simulated stars at the best-fit
    parameters, overlaid on the observed CDF.
    """
    from wr_bias_simulation import (
        simulate_delta_rv_sample, SimulationConfig, BinaryParameterConfig,
        DEFAULT_DRV_BIN_EDGES,
    )

    cadence_library = result.get('cadence_library')
    if cadence_library is None:
        return

    _bin_edges = DEFAULT_DRV_BIN_EDGES
    obs_cdf_b = _binned_cdf(obs_delta_rv, _bin_edges)

    st.markdown('### CDF Sanity Check')
    st.caption(
        '5 random draws of 25 simulated stars at the best-fit parameters, '
        'compared to the observed CDF. Each draw uses different random seeds '
        'but identical cadence assignments.'
    )

    # Build configs from result metadata
    _bcfg_dict = result.get('bin_cfg', {})
    bcfg = (BinaryParameterConfig(**_bcfg_dict)
            if _bcfg_dict else BinaryParameterConfig())
    sim_cfg = SimulationConfig(
        n_stars=25,
        sigma_single=float(sigma_single),
        sigma_measure=float(result.get('sigma_meas', 1.622)),
    )

    fig = go.Figure()

    # Observed CDF
    fig.add_trace(go.Scatter(
        x=_bin_edges, y=obs_cdf_b,
        mode='lines', name='Observed',
        line=dict(color='white', width=3, shape='hv'),
    ))

    # 5 random draws
    _draw_colors = ['#E25A53', '#50C878', '#9B59B6', '#F39C12', '#1ABC9C']
    for i, seed in enumerate([42, 43, 44, 45, 46]):
        rng = np.random.default_rng(seed)
        try:
            drv = simulate_delta_rv_sample(
                f_bin=best_fbin,
                pi=best_x,
                sim_cfg=sim_cfg,
                bin_cfg=bcfg,
                rng=rng,
            )
            sim_cdf = _binned_cdf(drv, _bin_edges)
            fig.add_trace(go.Scatter(
                x=_bin_edges, y=sim_cdf,
                mode='lines', name=f'Draw {i+1} (seed={seed})',
                line=dict(color=_draw_colors[i], width=1.5,
                          dash='dash', shape='hv'),
                opacity=0.7,
            ))
        except Exception as e:
            st.warning(f'Draw {i+1} failed: {e}')

    fig.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(
            text=(f'CDF Sanity Check  (f_bin={best_fbin:.3f}, '
                  f'25 stars x 5 draws)'),
            font=dict(size=14)),
        'xaxis_title': 'DeltaRV (km/s)',
        'yaxis_title': 'Cumulative fraction',
        'height': 420,
        'legend': dict(x=0.55, y=0.35, font=dict(size=10)),
    })
    st.plotly_chart(fig, use_container_width=True,
                    key=f'{p_prefix}_cdf_sanity')


# ---------------------------------------------------------------------------
# Model Explorer -- interactive grid browser
# ---------------------------------------------------------------------------

# D17: Model Explorer (fixed 2026-03-30, pending user approval)
def _render_lk_model_explorer(
    result: dict, display_name: str,
    fbin_g: np.ndarray, x_g: np.ndarray, x_name: str, x_label: str,
    prefix: str, info: dict | None,
    p_nd: np.ndarray,
) -> None:
    """Interactive Likelihood model explorer: sliders -> CDF + score + histogram + det frac."""
    try:
        from wr_bias_simulation import (
            simulate_delta_rv_sample, SimulationConfig,
            BinaryParameterConfig, DEFAULT_DRV_BIN_EDGES,
            multinomial_log_likelihood,
        )
    except ImportError:
        st.info('wr_bias_simulation not available for model explorer.')
        return

    from bc.analysis import _method_best_and_hdi

    # Best-fit defaults for sliders
    me_info = info
    if me_info is None:
        me_info = _method_best_and_hdi(
            p_nd,
            [fbin_g, x_g], ['fbin', x_name],
            is_likelihood=True,
        )
    if me_info is None:
        st.info('Could not determine best-fit parameters.')
        return

    bv = me_info['best_vals']
    def_fb = float(bv.get('fbin', 0.5))
    # Sigma may be constant (not in bv) — fall back to grid value
    _sig_const = np.asarray(result.get('sigma_grid', [5.0]))
    def_sig = float(bv.get('sigma',
                    float(_sig_const[0]) if _sig_const.size > 0
                    else result.get('sigma_meas', 5.0)))
    _lp_g = np.asarray(result.get('logPmax_grid', []))
    def_logPmax = float(bv.get('logPmax',
                        float(_lp_g[0]) if _lp_g.size > 0 else 3.5))
    # x_name='sigma' for Langer — fall back to constant sigma value
    def_x = float(bv.get(x_name, def_sig))

    # Reset counter — slider keys include counter so reset forces new widgets
    _reset_key = f'{prefix}_lk_me_reset_count'
    _rc = st.session_state.get(_reset_key, 0)

    # Reset button + best-fit labels
    _best_score = me_info.get('best_score', 0)
    _reset_col1, _reset_col2 = st.columns([0.7, 0.3])
    with _reset_col1:
        _best_parts = [f'f_bin={def_fb:.3f}']
        if _lp_g.size > 1:
            _best_parts.append(f'logP_max={def_logPmax:.2f}')
        _sig_g_pre = np.asarray(result.get('sigma_grid', []))
        if _sig_g_pre.size > 1:
            _best_parts.append(f'σ={def_sig:.1f}')
        else:
            _best_parts.append(f'σ={def_sig:.1f} (constant)')
        st.caption(f'Best-fit model: {", ".join(_best_parts)}  |  Score: {_best_score:.4f}')
    with _reset_col2:
        if st.button('🟢 Reset to best', key=f'{prefix}_lk_me_reset'):
            st.session_state[_reset_key] = _rc + 1
            st.rerun()

    # Sliders + synced number inputs for precise control
    sig_g = np.asarray(result.get('sigma_grid', []))
    _ncols = 1 + (1 if sig_g.size > 1 else 0) + (1 if _lp_g.size > 1 else 0)

    def _synced_slider_input(col, label, mn, mx, default, step, fmt, key_base):
        """Slider + number_input with bidirectional sync."""
        _k_sl = f'{key_base}_{_rc}_sl'
        _k_ni = f'{key_base}_{_rc}_ni'
        if _k_sl not in st.session_state:
            st.session_state[_k_sl] = default
        if _k_ni not in st.session_state:
            st.session_state[_k_ni] = default

        def _sync_from_slider():
            v = min(max(float(st.session_state[_k_sl]), mn), mx)
            st.session_state[_k_sl] = v
            st.session_state[_k_ni] = v

        def _sync_from_input():
            v = min(max(float(st.session_state[_k_ni]), mn), mx)
            st.session_state[_k_sl] = v
            st.session_state[_k_ni] = v

        col.slider(label, mn, mx, key=_k_sl, on_change=_sync_from_slider)
        col.number_input('exact', min_value=mn, max_value=mx,
                         step=step, format=fmt, key=_k_ni,
                         label_visibility='collapsed',
                         on_change=_sync_from_input)
        return float(st.session_state[_k_sl])

    cols = st.columns(_ncols)
    _col_idx = 0

    me_fb = _synced_slider_input(
        cols[_col_idx], f'f_bin  (best: {def_fb:.3f})',
        0.0, 1.0, def_fb, 0.001, '%.4f', f'{prefix}_lk_me_fb')
    _col_idx += 1

    # For Langer: x_g IS sigma — use a single σ slider (not both x and σ)
    if sig_g.size > 1:
        me_sig = _synced_slider_input(
            cols[_col_idx], f'σ_single  (best: {def_sig:.1f})',
            float(sig_g[0]), float(sig_g[-1]),
            min(max(def_sig, float(sig_g[0])), float(sig_g[-1])),
            0.1, '%.2f', f'{prefix}_lk_me_sig')
        _col_idx += 1
    else:
        me_sig = def_sig
    me_x = me_sig  # x_name='sigma' for Langer — keep in sync

    me_logPmax = None
    if _lp_g.size > 1:
        _dlp = float(bv.get('logPmax', def_logPmax))
        me_logPmax = _synced_slider_input(
            cols[_col_idx], f'logP_max  (best: {_dlp:.2f})',
            float(_lp_g[0]), float(_lp_g[-1]),
            min(max(_dlp, float(_lp_g[0])), float(_lp_g[-1])),
            0.01, '%.3f', f'{prefix}_lk_me_logPmax')

    obs_drv = np.asarray(result.get('obs_delta_rv'))
    be = result.get('bin_edges')
    be = np.asarray(be) if be is not None else DEFAULT_DRV_BIN_EDGES
    lk_be = result.get('likelihood_bin_edges')
    lk_be = np.asarray(lk_be) if lk_be is not None else be
    sigma_m = float(result.get('sigma_meas', 3.0))
    # E048: full physics config + cadence library for grid-matching re-sim.
    _cad_lib_me = result.get('cadence_library')
    _cad_wt_me = result.get('cadence_weights')
    _bc_tuple_me = _result_bin_cfg_tuple(result)
    _pm_me = _result_period_model(result, default='langer2020')
    _n_sets_me = int(result.get('n_sets', 50))

    # Multi-seed CDF band (cached) — Langer: uses langer2020 period model
    _lp_for_sim = me_logPmax if me_logPmax is not None else def_logPmax
    med_cdf, lo_cdf, hi_cdf, pooled_drv = _me_cdf_band_langer(
        me_fb, _lp_for_sim, me_sig, sigma_m, tuple(be.tolist()),
        n_sets=_n_sets_me,
        _cadence_library=_cad_lib_me, _cadence_weights=_cad_wt_me,
        _bin_cfg_dict=_bc_tuple_me, period_model=_pm_me)

    # ── D17: Score metric cards (logL) ──
    _logL = multinomial_log_likelihood(obs_drv, pooled_drv, lk_be)
    # Compute logL for the global best-fit
    _bf_med, _, _, _bf_pooled = _me_cdf_band_langer(
        def_fb, def_logPmax, def_sig, sigma_m, tuple(be.tolist()),
        n_sets=_n_sets_me,
        _cadence_library=_cad_lib_me, _cadence_weights=_cad_wt_me,
        _bin_cfg_dict=_bc_tuple_me, period_model=_pm_me)
    _logL_best = multinomial_log_likelihood(obs_drv, _bf_pooled, lk_be)

    mc1, mc2 = st.columns(2)
    _cur_parts = [f'f_bin={me_fb:.3f}']
    _best_parts_mc = [f'f_bin={def_fb:.3f}']
    if me_logPmax is not None:
        _cur_parts.append(f'logP={me_logPmax:.2f}')
        _best_parts_mc.append(f'logP={def_logPmax:.2f}')
    if sig_g.size > 1:
        _cur_parts.append(f'σ={me_sig:.1f}')
        _best_parts_mc.append(f'σ={def_sig:.1f}')
    mc1.metric(
        label='Current (Explorer)',
        value=', '.join(_cur_parts),
        delta=f'logL = {_logL:.4f}',
        delta_color='off',
    )
    mc2.metric(
        label='Global best',
        value=', '.join(_best_parts_mc),
        delta=f'logL = {_logL_best:.4f}',
        delta_color='off',
    )

    # -- CDF with error shadow + optional best-fit overlay --------
    obs_cdf = _binned_cdf(obs_drv, be)
    med_x = np.concatenate([[0.0], be])
    med_y = np.concatenate([[0.0], med_cdf])

    # Best-fit overlay (algorithm's best vs explorer's current)
    _show_bestfit = st.checkbox('Compare with algorithm best-fit',
                                value=False, key=f'{prefix}_lk_me_cmp_best')
    _bf_med = None
    if _show_bestfit and info is not None:
        _bf_bv = info.get('best_vals', {})
        _bf_fb = float(_bf_bv.get('fbin', 0.5))
        _bf_sig = float(_bf_bv.get('sigma', def_sig))
        _bf_lp = float(_bf_bv.get('logPmax', def_logPmax))
        _bf_med, _bf_lo, _bf_hi, _ = _me_cdf_band_langer(
            _bf_fb, _bf_lp, _bf_sig, sigma_m,
            tuple(be.tolist()), n_sets=_n_sets_me,
            _cadence_library=_cad_lib_me, _cadence_weights=_cad_wt_me,
            _bin_cfg_dict=_bc_tuple_me, period_model=_pm_me)

    fig_cdf = go.Figure()
    fig_cdf.add_trace(go.Scatter(
        x=be, y=obs_cdf, mode='lines', name='Observed',
        line=dict(color='white', width=2.5, shape='hv'),
    ))
    # Explorer median CDF (no error band)
    fig_cdf.add_trace(go.Scatter(
        x=med_x, y=med_y, mode='lines', name='Explorer (current)',
        line=dict(color=_METHOD_COLOR, width=2, dash='dash',
                  shape='hv'),
    ))
    # Best-fit overlay
    if _bf_med is not None:
        _bf_x_arr = np.concatenate([[0.0], be])
        _bf_y_arr = np.concatenate([[0.0], _bf_med])
        fig_cdf.add_trace(go.Scatter(
            x=_bf_x_arr, y=_bf_y_arr,
            mode='lines', name='Best-fit (algorithm)',
            line=dict(color='#E25A53', width=2, dash='dot', shape='hv'),
        ))
    # Full x-range: cover all observed data + bin edges
    _xmax_cdf = float(np.nanmax(obs_drv)) if len(obs_drv) else 1.0
    _be_finite = be[np.isfinite(be)]
    if len(_be_finite):
        _xmax_cdf = max(_xmax_cdf, float(np.max(_be_finite)))
    fig_cdf.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(
            text=f'CDF -- logL = {_logL:.3f}',
            font=dict(size=14)),
        'xaxis_title': 'ΔRV (km/s)',
        'xaxis_range': [0, _xmax_cdf * 1.05],
        'yaxis_title': 'Cumulative fraction',
        'height': 380,
        'margin': dict(l=60, r=30, t=40, b=50),
        'legend': dict(x=0.6, y=0.15),
    })
    # -- Bin overlay toggle (uses likelihood bins, not CDF bins) ----
    _show_bins_me = st.checkbox('Show likelihood bin edges on CDF', value=False,
                                key=f'{prefix}_lk_me_show_bins')
    if _show_bins_me:
        _alt = ['rgba(100,100,100,0.08)', 'rgba(100,100,100,0.15)']
        _lk_be_finite = lk_be[np.isfinite(lk_be)]
        for _bi in range(len(lk_be) - 1):
            _x0 = float(lk_be[_bi]) if np.isfinite(lk_be[_bi]) else 0.0
            _x1 = float(lk_be[_bi + 1]) if np.isfinite(lk_be[_bi + 1]) else float(np.nanmax(obs_drv) * 1.1)
            fig_cdf.add_vrect(
                x0=_x0, x1=_x1,
                fillcolor=_alt[_bi % 2], layer='below', line_width=0)
        for _ei in _lk_be_finite:
            fig_cdf.add_vline(
                x=float(_ei),
                line=dict(color='grey', width=1, dash='dot'))
    st.plotly_chart(fig_cdf, use_container_width=True,
                    key=f'{prefix}_lk_me_cdf')
    if _show_bins_me:
        _no = np.histogram(obs_drv, bins=lk_be)[0]
        _ns = np.histogram(pooled_drv, bins=lk_be)[0]
        _sf = _ns / max(_ns.sum(), 1)
        _br = [{'Bin': f'{lk_be[i]:.0f}–{lk_be[i+1]:.0f}' if np.isfinite(lk_be[i+1]) else f'{lk_be[i]:.0f}–∞',
                'N_obs': int(_no[i]),
                'N_sim': int(_ns[i]),
                'Sim frac': f'{_sf[i]:.3f}'}
               for i in range(len(lk_be) - 1)]
        st.dataframe(pd.DataFrame(_br), use_container_width=True,
                     hide_index=True)

    # ── D17: 4 heatmaps (2×2) with green dot — Langer version ──
    # For Langer: primary heatmap = f_bin × logP_max, secondary = σ×logP
    _sig_g_hm = np.asarray(result.get('sigma_grid', []))
    _lp_g_hm = np.asarray(result.get('logPmax_grid', []))
    _has_4hm = (_sig_g_hm.size > 1 and _lp_g_hm.size > 1 and p_nd.ndim >= 3)
    if _has_4hm:
        from bc.helpers import _make_heatmap_fig as _mkhm

        # Find current slider indices
        _me_sig_idx = int(np.argmin(np.abs(_sig_g_hm - me_sig)))
        _me_lp_idx = int(np.argmin(np.abs(_lp_g_hm - me_logPmax))) if me_logPmax is not None else 0

        # Slice to f_bin × logP_max at current σ
        # Langer array layout: [logPmax, sigma, fbin, pi=1] (4D) or [sigma, fbin, pi=1] (3D)
        if p_nd.ndim == 4:
            # [logP, sigma, fbin, pi] → slice at current σ → [logP, fbin, pi]
            _slice_at_sig = p_nd[:, _me_sig_idx, :, :]
            # Squeeze pi=1 → [logP, fbin]
            if _slice_at_sig.shape[-1] == 1:
                _slice_at_sig = _slice_at_sig[..., 0]
            _norm_fb_lp = _slice_at_sig.T  # → [fbin, logP] for heatmap
            _norm_siglp = np.nanmax(p_nd, axis=(2, 3))  # [logP, sigma]
        elif p_nd.ndim == 3:
            # [sigma, fbin, pi] → slice at current σ → [fbin, pi]
            _slice_at_sig = p_nd[_me_sig_idx]
            if _slice_at_sig.shape[-1] == 1:
                _slice_at_sig = _slice_at_sig[..., 0]
            # Only fbin left — can't make f_bin×logP heatmap
            _norm_fb_lp = None
            _norm_siglp = None
        else:
            _norm_fb_lp = None
            _norm_siglp = None

        # Unnormalized logL — same slicing
        _logL_raw = result.get('logL_raw')
        _unnorm_fb_lp = _unnorm_siglp = None
        if _logL_raw is not None:
            _lr = np.asarray(_logL_raw, dtype=float)
            if _lr.ndim == 4:
                _lr_slice = _lr[:, _me_sig_idx, :, :]
                if _lr_slice.shape[-1] == 1:
                    _lr_slice = _lr_slice[..., 0]
                _unnorm_fb_lp = _lr_slice.T
                _unnorm_siglp = np.nanmax(_lr, axis=(2, 3))
            elif _lr.ndim == 3:
                _unnorm_fb_lp = None
                _unnorm_siglp = None

        def _green_dot(fig, x_val, y_val):
            fig.add_trace(go.Scatter(
                x=[x_val], y=[y_val], mode='markers',
                marker=dict(symbol='circle', size=12, color='#00CC66',
                            line=dict(width=2, color='black')),
                name='Current', showlegend=False,
            ))

        st.markdown('#### Heatmaps at Current Explorer Position')
        _hm_r1c1, _hm_r1c2 = st.columns(2)
        with _hm_r1c1:
            if _norm_fb_lp is not None:
                _fig1 = _mkhm(_norm_fb_lp, fbin_g, _lp_g_hm,
                               title='Normalized Likelihood (f_bin × logP_max)',
                               show_d=False, height=350,
                               x_label='log₁₀(P_max)', x_name='logPmax',
                               scoring_label='Likelihood',
                               colorbar_title_override='Norm. L')
                _green_dot(_fig1, me_logPmax if me_logPmax else _lp_g_hm[0], me_fb)
                st.plotly_chart(_fig1, use_container_width=True,
                                key=f'{prefix}_lk_me_hm_norm_fbpi')
        with _hm_r1c2:
            if _norm_siglp is not None:
                _fig2 = _mkhm(_norm_siglp, _lp_g_hm, _sig_g_hm,
                               title='Max Norm. Likelihood (σ × logP)',
                               show_d=False, height=350,
                               x_label='σ_single (km/s)',
                               y_label='log₁₀(P_max)',
                               x_name='σ', y_name='log₁₀(P_max)',
                               scoring_label='Likelihood',
                               colorbar_title_override='Max Norm. L')
                _green_dot(_fig2, me_sig, me_logPmax if me_logPmax else _lp_g_hm[0])
                st.plotly_chart(_fig2, use_container_width=True,
                                key=f'{prefix}_lk_me_hm_norm_siglp')

        _hm_r2c1, _hm_r2c2 = st.columns(2)
        with _hm_r2c1:
            if _unnorm_fb_lp is not None:
                _fig3 = _mkhm(_unnorm_fb_lp, fbin_g, _lp_g_hm,
                               title='log L (f_bin × logP_max)',
                               show_d=False, height=350,
                               x_label='log₁₀(P_max)', x_name='logPmax',
                               scoring_label='log L',
                               colorbar_title_override='log L')
                _green_dot(_fig3, me_logPmax if me_logPmax else _lp_g_hm[0], me_fb)
                st.plotly_chart(_fig3, use_container_width=True,
                                key=f'{prefix}_lk_me_hm_unnorm_fbpi')
        with _hm_r2c2:
            if _unnorm_siglp is not None:
                _fig4 = _mkhm(_unnorm_siglp, _lp_g_hm, _sig_g_hm,
                               title='Max log L (σ × logP)',
                               show_d=False, height=350,
                               x_label='σ_single (km/s)',
                               y_label='log₁₀(P_max)',
                               x_name='σ', y_name='log₁₀(P_max)',
                               scoring_label='log L',
                               colorbar_title_override='Max log L')
                _green_dot(_fig4, me_sig, me_logPmax if me_logPmax else _lp_g_hm[0])
                st.plotly_chart(_fig4, use_container_width=True,
                                key=f'{prefix}_lk_me_hm_unnorm_siglp')

    # ── WORKING — do not change this code · D17: Histogram overlay ──
    sim_drv_single = pooled_drv[:1000]
    fig_hist = go.Figure()
    fig_hist.add_trace(go.Histogram(
        x=obs_drv, nbinsx=30, histnorm='probability density',
        name='Observed', marker_color='#4A90D9', opacity=0.6,
    ))
    fig_hist.add_trace(go.Histogram(
        x=sim_drv_single, nbinsx=30, histnorm='probability density',
        name='Simulated', marker_color=_METHOD_COLOR, opacity=0.5,
    ))
    fig_hist.update_layout(**{
        **PLOTLY_THEME,
        'barmode': 'overlay',
        'title': dict(text='DeltaRV Distribution', font=dict(size=14)),
        'xaxis_title': 'DeltaRV (km/s)',
        'yaxis_title': 'Probability density',
        'height': 380,
        'margin': dict(l=60, r=30, t=40, b=50),
        'legend': dict(x=0.65, y=0.95),
    })
    st.plotly_chart(fig_hist, use_container_width=True,
                    key=f'{prefix}_lk_me_hist')

    # ── WORKING — do not change this code · D17: Detection fraction vs threshold ──
    max_drv = max(float(np.max(obs_drv)),
                  float(np.max(sim_drv_single)))
    thresholds = np.linspace(0, max_drv * 1.1, 100)
    # Significance criterion: ΔRV − nsigma·σ_p2p > 0 (sqrt(2)·σ_m for fixed model)
    try:
        import json as _json
        _sett = _json.loads(str(result.get('settings', '{}')))
        _nsigma = float(_sett.get('sigma_factor', 4.0))
    except Exception:
        _nsigma = 4.0
    _sig_p2p_const = np.sqrt(2.0) * sigma_m
    _sig_floor = _nsigma * _sig_p2p_const
    # Bartzakos correction: 3 confirmed binaries excluded from sample → +3 numerator, /28 denominator
    _n_bartz = 3
    _total_pop = len(obs_drv) + _n_bartz
    frac_obs = np.array([(float(np.sum((obs_drv > T) & (obs_drv > _sig_floor))) + _n_bartz) / _total_pop
                         for T in thresholds])
    frac_sim = np.array([((sim_drv_single > T) & (sim_drv_single > _sig_floor)).mean()
                         for T in thresholds])

    fig_det = go.Figure()
    fig_det.add_trace(go.Scatter(
        x=thresholds, y=frac_obs, mode='lines', name='Observed',
        line=dict(color='#4A90D9', width=2.5),
    ))
    fig_det.add_trace(go.Scatter(
        x=thresholds, y=frac_sim, mode='lines', name='Simulated',
        line=dict(color=_METHOD_COLOR, width=2.5, dash='dash'),
    ))
    thresh_dRV = float(result.get('thresh_dRV', 45.5))
    fig_det.add_vline(
        x=thresh_dRV, line_dash='dot', line_color='#E25A53',
        line_width=1.5,
        annotation_text=f'Threshold={thresh_dRV:.0f}',
        annotation_position='top right',
        annotation_font_color='#E25A53',
    )
    _det_parts = [f'f_bin={me_fb:.3f}']
    if me_logPmax is not None:
        _det_parts.append(f'logP={me_logPmax:.2f}')
    fig_det.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(
            text=f'Detection Fraction ({", ".join(_det_parts)})',
            font=dict(size=14)),
        'xaxis_title': 'DeltaRV threshold (km/s)',
        'yaxis_title': 'Fraction above threshold',
        'height': 380,
        'margin': dict(l=60, r=30, t=40, b=50),
        'yaxis': dict(range=[0, 1.05]),
        'legend': dict(x=0.65, y=0.95),
    })
    st.plotly_chart(fig_det, use_container_width=True,
                    key=f'{prefix}_lk_me_det')

    st.caption(
        f'Likelihood model explorer for {display_name}. '
        f'CDF shows median +/- 68% band from 50 simulations. '
        f'ln L computed from pooled simulated data.'
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def render_lk_explorer(
    p: str, result: dict,
    fbin_g, x_g, x_label, x_name,
    method_key='likelihood', display_name='Likelihood',
    best_fb=None, best_x=None, best_sig=None,
    obs_delta_rv=None, cadence_library=None,
    height=400, width=None,
) -> None:
    """Render Likelihood model explorer, re-sim CDF, and CDF sanity check.

    Parameters
    ----------
    p : str
        Key prefix for session state.
    result : dict
        Full result dictionary.
    fbin_g, x_g : 1D arrays
        Grid values for f_bin and second axis.
    x_label, x_name : str
        Display label and internal name for the x-axis.
    method_key : str
        Scoring method key (always 'likelihood' for this module).
    display_name : str
        Display name for the method.
    best_fb, best_x, best_sig : float or None
        Best-fit values to use as slider defaults.
    obs_delta_rv : array or None
        Observed delta-RV values.
    cadence_library : dict or None
        Cadence library for cadence-aware sanity checks.
    height : int
        Plot height.
    width : int or None
        Plot width.
    """
    fbin_g = np.asarray(fbin_g)
    x_g = np.asarray(x_g)

    # Get likelihood array for info computation
    lk_p = result.get('likelihood')
    if lk_p is not None:
        p_nd = np.asarray(lk_p, dtype=float)
    else:
        st.info('No Likelihood data available.')
        return

    # Compute info for default slider values
    from bc.analysis import _method_best_and_hdi
    _grids = [fbin_g, x_g]
    _names = ['fbin', x_name]
    _sigma_g = np.asarray(result.get('sigma_grid', [0.0]))
    _logPmax_g = np.asarray(result.get('logPmax_grid', [0.0]))
    if _logPmax_g.size > 1:
        _grids.insert(0, _logPmax_g)
        _names.insert(0, 'logPmax')
    if _sigma_g.size > 1:
        _grids.insert(0 if _logPmax_g.size <= 1 else 1, _sigma_g)
        _names.insert(0 if _logPmax_g.size <= 1 else 1, 'sigma')

    # Squeeze p_nd to match grids
    while p_nd.ndim > len(_grids):
        squeezed = False
        for ax in range(p_nd.ndim):
            if p_nd.shape[ax] == 1:
                p_nd = np.squeeze(p_nd, axis=ax)
                squeezed = True
                break
        if not squeezed:
            p_nd = p_nd[0]

    info = _method_best_and_hdi(p_nd, _grids, _names, is_likelihood=True)

    # Override info best values if caller provided explicit ones
    if info is not None and (best_fb is not None or best_x is not None
                             or best_sig is not None):
        bv = dict(info['best_vals'])
        if best_fb is not None:
            bv['fbin'] = best_fb
        if best_x is not None:
            bv[x_name] = best_x
        if best_sig is not None:
            bv['sigma'] = best_sig
        info = dict(info)
        info['best_vals'] = bv

    # -- Model Explorer -------------------------------------------
    obs_drv_me = result.get('obs_delta_rv')
    if obs_drv_me is not None:
        st.divider()
        with st.expander(f'Model Explorer -- {display_name}',
                         expanded=False):
            _render_lk_model_explorer(
                result, display_name,
                fbin_g, x_g, x_name, x_label,
                p, info, p_nd,
            )

    # -- Re-simulate at interpolated point ------------------------
    _interp = st.session_state.get(f'{p}_interp')
    if _interp is not None:
        _render_lk_resim_interp(_interp, result, x_label, p)

    # -- CDF Sanity Check (cadence tabs) --------------------------
    _cadence_lib = cadence_library or result.get('cadence_library')
    if _cadence_lib is not None and obs_delta_rv is not None:
        _bv = info['best_vals'] if info is not None else {}
        _pm = 'dsilva'
        if result.get('period_model') == 'langer':
            _pm = 'langer'
        try:
            _render_lk_cdf_sanity_check(
                _bv.get('fbin', 0.5), _bv.get(x_name, 0.0),
                _bv.get('sigma', float(result.get('sigma_meas', 5.0))),
                np.asarray(obs_delta_rv), _pm, result,
                f'{p}_{method_key}')
        except Exception:
            pass
