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

# Re-export `CDFBandResult` so callers of either Explorer twin have a
# single canonical type to import.
from bc.render_lk_explorer import CDFBandResult  # noqa: E402


@st.cache_data(show_spinner=False)
def _me_cdf_band_langer(
    fb: float, logPmax: float, sigma_s: float, sigma_m: float,
    bin_edges_tuple: tuple, n_sets: int = 50,
    _cadence_library=None, _cadence_weights=None,
    _bin_cfg_dict=None, period_model: str = 'langer2020',
) -> CDFBandResult:
    """Langer-specific CDF band: uses langer2020 period model with logP_max.

    E048 fix: when _bin_cfg_dict is supplied (hashable tuple from the grid
    result), the full bin_cfg is reconstituted so the re-simulated CDF/logL
    matches the physics surface the grid scored. When _cadence_library is
    supplied, runs cadence-aware simulation (matching the grid worker).

    Note (2026-04-29): the previous validation_mode branch (mock-replay
    sampler with seed reuse) was removed.  The Explorer now drives all
    scoring through the Run button + grid pipeline (parity with Dsilva).
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
        mean_cdf_arr  = res['mean_cdf']
        rank_median   = res['per_rank_median_drv']
        rank_mean     = res['per_rank_mean_drv']
        rank_bin_frac = res['per_rank_binary_fraction']
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
        mean_cdf_arr  = np.mean(all_cdfs, axis=0)
        rank_median   = np.array([], dtype=float)
        rank_mean     = np.array([], dtype=float)
        rank_bin_frac = np.array([], dtype=float)

    return CDFBandResult(
        median=np.median(all_cdfs, axis=0),
        lo=np.percentile(all_cdfs, 16, axis=0),
        hi=np.percentile(all_cdfs, 84, axis=0),
        pooled=pooled,
        mean=mean_cdf_arr,
        rank_median=rank_median,
        rank_mean=rank_mean,
        rank_bin_frac=rank_bin_frac,
    )


# --- E048 helpers: reuse the Dsilva implementations ----------------------
# Kept as thin re-exports so the Langer side doesn't duplicate the
# freeze/load logic (memory rule allows duplication but there's no Dsilva
# vs Langer divergence for these utilities — they operate only on the
# result dict).  Run-button helpers (2026-04-29) are also shared across
# the two Explorer twins.
from bc.render_lk_explorer import (  # noqa: E402
    _result_bin_cfg_tuple,
    _result_period_model,
    _explorer_seed_for_cell,
    _run_grid_pipeline_via_cache,
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
        _b = _me_cdf_band_langer(
            fb, _lp_resim, sig, float(result.get('sigma_meas', 3.0)),
            tuple(be.tolist()), n_sets=int(ns),
            _cadence_library=_cad_lib_l, _cadence_weights=_cad_wt_l,
            _bin_cfg_dict=_bc_tuple_l, period_model=_pm_l,
        )
        med_c, lo_c, hi_c, pooled = _b.median, _b.lo, _b.hi, _b.pooled
        obs = np.asarray(result.get('obs_delta_rv', []))
        rx = np.concatenate([[0.0], be])

        # Compute likelihood score
        logL = multinomial_log_likelihood(obs, pooled, lk_be)

        # Round-5 (2026-04-28): also re-simulate at the MARGINAL-best
        # tuple so the panel shows BOTH grid and marginal best-fits side
        # by side.  Langer's marginal is over (f_bin, sigma, logPmax)
        # — the pi axis is not scanned in Langer mode.
        marg_med = marg_lo = marg_hi = None
        _m_fb = _m_sig = _m_lpm = None
        try:
            from bc.analysis import _method_best_and_hdi
            _lk_arr_l = np.asarray(result.get('likelihood', []))
            _fbg_l = np.asarray(result.get('fbin_grid', []))
            _sgg_l = np.asarray(result.get('sigma_grid', []))
            _lpg_l = np.asarray(result.get('logPmax_grid', []))
            _grids_ml = []
            _names_ml = []
            if _lpg_l.size > 1:
                _grids_ml.append(_lpg_l)
                _names_ml.append('logPmax')
            if _sgg_l.size > 1:
                _grids_ml.append(_sgg_l)
                _names_ml.append('sigma')
            if _fbg_l.size > 0:
                _grids_ml.append(_fbg_l)
                _names_ml.append('fbin')
            _lk_sq_l = _lk_arr_l.copy() if _lk_arr_l is not None else None
            while (_lk_sq_l is not None and _lk_sq_l.ndim > len(_grids_ml)
                   and _lk_sq_l.shape[-1] == 1):
                _lk_sq_l = _lk_sq_l.squeeze(axis=-1)
            while (_lk_sq_l is not None and _lk_sq_l.ndim > len(_grids_ml)
                   and _lk_sq_l.shape[0] == 1):
                _lk_sq_l = _lk_sq_l[0]
            if (_lk_sq_l is not None and _lk_sq_l.ndim == len(_grids_ml)
                    and _lk_sq_l.size > 0):
                _info_ml = _method_best_and_hdi(
                    _lk_sq_l, _grids_ml, _names_ml, is_likelihood=True)
                if _info_ml is not None:
                    _hdi_ml = _info_ml.get('hdi', {})
                    _m_fb = float(_hdi_ml.get('fbin', (fb,))[0])
                    _m_sig = float(_hdi_ml.get('sigma', (sig,))[0])
                    _m_lpm = float(_hdi_ml.get('logPmax',
                                               (_lp_resim,))[0])
                    _diff_l = (
                        (not np.isclose(_m_fb, fb, atol=1e-6))
                        or (not np.isclose(_m_sig, sig, atol=1e-6))
                        or (not np.isclose(_m_lpm, _lp_resim, atol=1e-6))
                    )
                    if _diff_l:
                        _bm = _me_cdf_band_langer(
                            _m_fb, _m_lpm, _m_sig,
                            float(result.get('sigma_meas', 3.0)),
                            tuple(be.tolist()), n_sets=int(ns),
                            _cadence_library=_cad_lib_l,
                            _cadence_weights=_cad_wt_l,
                            _bin_cfg_dict=_bc_tuple_l,
                            period_model=_pm_l,
                        )
                        marg_med, marg_lo, marg_hi = _bm.median, _bm.lo, _bm.hi
        except Exception:
            marg_med = marg_lo = marg_hi = None

        from bc.render_validation import (
            _CDF_OBS_COLOR, _CDF_FIT_COLOR, _CDF_FIT_MARG_COLOR,
            _CLR_SINGLE, _CLR_BINARY,
        )
        fig = go.Figure()

        # Mock observation: TRUE empirical step.
        _obs_arr_rl = np.asarray(obs, dtype=float)
        _obs_finite_rl = _obs_arr_rl[np.isfinite(_obs_arr_rl)]
        _n_obs_rl = int(_obs_finite_rl.size)
        if _n_obs_rl > 0:
            _obs_sort_rl = np.argsort(_obs_finite_rl)
            _obs_sorted_rl = _obs_finite_rl[_obs_sort_rl]
            _obs_cdf_rl = (np.arange(_n_obs_rl) + 1) / _n_obs_rl
            fig.add_trace(go.Scatter(
                x=_obs_sorted_rl, y=_obs_cdf_rl, mode='lines',
                name='Mock observation',
                line=dict(color=_CDF_OBS_COLOR, width=2.5, shape='hv')))
        else:
            _obs_sort_rl = None
            _obs_sorted_rl = None
            _obs_cdf_rl = None

        # Per-star markers
        from bc.validation_io import load_per_star_truth
        _is_bin = load_per_star_truth(result)
        if (_is_bin is not None and _obs_sorted_rl is not None
                and len(_is_bin) == len(obs)):
            _is_bin_full_rl = np.asarray(_is_bin, dtype=bool)
            _finite_mask_rl = np.isfinite(_obs_arr_rl)
            if _is_bin_full_rl.size == _obs_arr_rl.size:
                _is_bin_finite_rl = _is_bin_full_rl[_finite_mask_rl]
                _is_bin_sorted_rl = _is_bin_finite_rl[_obs_sort_rl]
            else:
                _is_bin_sorted_rl = np.zeros(_n_obs_rl, dtype=bool)
            _single_mask_rl = ~_is_bin_sorted_rl
            if np.any(_single_mask_rl):
                fig.add_trace(go.Scatter(
                    x=_obs_sorted_rl[_single_mask_rl],
                    y=_obs_cdf_rl[_single_mask_rl],
                    mode='markers',
                    marker=dict(color=_CLR_SINGLE, size=8,
                                line=dict(color='black', width=0.6)),
                    name=f'Single ({int(_single_mask_rl.sum())})',
                    hovertemplate='single · ΔRV=%{x:.1f} km/s<extra></extra>',
                ))
            if np.any(_is_bin_sorted_rl):
                fig.add_trace(go.Scatter(
                    x=_obs_sorted_rl[_is_bin_sorted_rl],
                    y=_obs_cdf_rl[_is_bin_sorted_rl],
                    mode='markers',
                    marker=dict(color=_CLR_BINARY, size=8,
                                line=dict(color='black', width=0.6)),
                    name=f'Binary ({int(_is_bin_sorted_rl.sum())})',
                    hovertemplate='binary · ΔRV=%{x:.1f} km/s<extra></extra>',
                ))

        # GRID best-fit: 16/84 + median
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
            fillcolor=_hex_to_rgba(_CDF_FIT_COLOR, 0.18),
            name='Grid best-fit 16/84', hoverinfo='skip'))
        fig.add_trace(go.Scatter(
            x=rx, y=np.concatenate([[0.0], med_c]),
            mode='lines', name='Grid best-fit (median)',
            line=dict(color=_CDF_FIT_COLOR, width=2.5, dash='dash',
                      shape='hv')))

        # MARGINAL best-fit: 16/84 + median (purple)
        if marg_med is not None:
            _hi_y_m = np.concatenate([[0.0], marg_hi])
            _lo_y_m = np.concatenate([[0.0], marg_lo])
            fig.add_trace(go.Scatter(
                x=rx, y=_lo_y_m, mode='lines',
                line=dict(color='rgba(0,0,0,0)', shape='hv'),
                showlegend=False, hoverinfo='skip'))
            fig.add_trace(go.Scatter(
                x=rx, y=_hi_y_m, mode='lines',
                line=dict(color='rgba(0,0,0,0)', shape='hv'),
                fill='tonexty',
                fillcolor=_hex_to_rgba(_CDF_FIT_MARG_COLOR, 0.18),
                name='Marginal best-fit 16/84', hoverinfo='skip'))
            fig.add_trace(go.Scatter(
                x=rx, y=np.concatenate([[0.0], marg_med]),
                mode='lines', name='Marginal best-fit (median)',
                line=dict(color=_CDF_FIT_MARG_COLOR, width=2.5,
                          dash='dash', shape='hv')))

        # Bug fix (2026-04-23): `xv` was undefined here — copy/paste leftover
        # from the Dsilva twin where xv=pi.  Langer has no pi; the scanned
        # x-axis IS sigma (x_label='σ_single (km/s)'), so substitute `sig`.
        _title_rl = (f'Re-sim: Grid f_bin={fb:.4f}, {x_label}={sig:.3f}, '
                     f'logP_max={_lp_resim:.3f}')
        if marg_med is not None and _m_fb is not None:
            _title_rl += f'  | Marginal f_bin={_m_fb:.4f}'
        fig.update_layout(**{
            **PLOTLY_THEME, 'height': 380,
            'title': dict(text=_title_rl, font=dict(size=14)),
            'xaxis_title': 'ΔRV (km/s)',
            'yaxis_title': 'Cumulative fraction',
        })
        # A&A journal theme (white bg, black serif text)
        from bc.render_validation import _AA_OVERRIDES
        fig.update_layout(**_AA_OVERRIDES)
        fig.update_xaxes(**_AA_OVERRIDES['xaxis'])
        fig.update_yaxes(**_AA_OVERRIDES['yaxis'])
        st.plotly_chart(fig, use_container_width=True,
                        key=f'{pfx}_lk_resim_cdf')
        c3.metric('ln L (interp)', f"{logL:.3f}")
    except Exception as err:
        st.error(f'Re-simulation failed: {err}')


# ---------------------------------------------------------------------------
# CDF Sanity Check (cadence tabs only)
# ---------------------------------------------------------------------------

def _render_lk_cdf_sanity_check(best_fbin, best_x, sigma_single,
                                obs_delta_rv, period_model, result,
                                p_prefix: str,
                                page_prefix: 'str | None' = None,
                                marg_params: dict | None = None,
                                x_name: str = 'sigma') -> None:
    """Langer twin of the Dsilva sanity-check.

    Round-5 (2026-04-28) parity with ``render_lk_explorer.py``:
      - True empirical step for the obs CDF (so per-star dots align).
      - Optional marginal-best overlay (purple) when ``marg_params`` is
        provided and differs from the grid tuple.
      - All N_draw faint dashed draws + bold median + 16/84 shadow for
        each best-fit colour.
    """
    from wr_bias_simulation import (
        BinaryParameterConfig, DEFAULT_DRV_BIN_EDGES,
    )
    from bc.validation import _sample_delta_rv_mock

    cadence_library = result.get('cadence_library')
    if cadence_library is None:
        return

    _bin_edges = DEFAULT_DRV_BIN_EDGES

    st.markdown('### CDF Sanity Check')

    _n_draw_key = f'{p_prefix}_cdf_sanity_n'
    if _n_draw_key not in st.session_state:
        st.session_state[_n_draw_key] = 500
    _n_draw = int(st.number_input(
        'Stars per draw (n_draw)',
        min_value=25, max_value=5000, step=25,
        key=_n_draw_key,
        help=('How many simulated stars per CDF draw.  Higher n_draw = '
              'smoother curves + tighter 16/84 band.')
    ))

    _bcfg_dict = result.get('bin_cfg', {}) or {}
    bcfg = (BinaryParameterConfig(**_bcfg_dict)
            if _bcfg_dict else BinaryParameterConfig())

    # Bug 2 fix: pull joint argmax for logP_max, derive validation context.
    _eff_logPmax = float(result.get('argmax_logPmax',
                                    _bcfg_dict.get('logP_max', 5.0)))
    if not np.isfinite(_eff_logPmax):
        _eff_logPmax = float(_bcfg_dict.get('logP_max', 5.0))
    _sigma_meas = float(result.get('sigma_meas', 1.622))

    _pp = page_prefix
    if _pp is None and isinstance(p_prefix, str):
        if p_prefix.endswith('_likelihood'):
            _pp = p_prefix[:-len('_likelihood')]
        else:
            _pp = p_prefix
    _val_truth = (st.session_state.get(f'{_pp}_val_mock_params')
                  if _pp else None)
    _validation_mode = (_val_truth is not None
                        and len(_val_truth) >= 5)
    if _validation_mode:
        _val_err_model = (str(_val_truth[6])
                          if len(_val_truth) >= 8 else 'fixed')
        _val_err_params = (tuple(_val_truth[7])
                           if len(_val_truth) >= 8 else ())
    else:
        _val_err_model = 'fixed'
        _val_err_params = ()

    def _draw_one(fb_v: float, x_v: float, sig_v: float,
                  seed_int: int, n_stars: int) -> np.ndarray:
        cad = list(cadence_library)
        if n_stars <= len(cad):
            cad = cad[:n_stars]
        else:
            reps = (n_stars + len(cad) - 1) // len(cad)
            cad = (cad * reps)[:n_stars]
        drv = _sample_delta_rv_mock(
            f_bin=float(fb_v),
            pi=float(x_v),
            sigma_single=float(sig_v),
            logP_max=float(_eff_logPmax),
            cadence_library=cad,
            sigma_meas=float(_sigma_meas),
            bin_cfg=bcfg,
            period_model=str(period_model),
            seed=int(seed_int),
            error_model=str(_val_err_model),
            error_params=tuple(_val_err_params),
            collect_detail=False,
        )
        return np.asarray(drv, dtype=float)

    # Empirical-step grid (shared by all simulated CDFs + the obs step).
    _obs_max_l = float(np.nanmax(obs_delta_rv)) if len(obs_delta_rv) else 0.0
    _be_max_l = float(np.nanmax(_bin_edges[np.isfinite(_bin_edges)])) if len(_bin_edges) else 0.0
    _x_max_sc_l = max(_obs_max_l, _be_max_l, 1.0) * 1.05
    _x_grid_l = np.linspace(0.0, _x_max_sc_l, 400)

    def _ecdf_on_grid(sample: np.ndarray, grid: np.ndarray) -> np.ndarray:
        s = np.asarray(sample, dtype=float)
        s = s[np.isfinite(s)]
        if s.size == 0:
            return np.zeros_like(grid)
        ss = np.sort(s)
        return np.searchsorted(ss, grid, side='right').astype(float) / s.size

    _n_band = 50

    def _draws_and_band(fb_v, x_v, sig_v, seed_offset):
        _draw_seeds = list(range(42 + seed_offset, 42 + seed_offset + 5))
        _draw_cdfs = []
        for s_ in _draw_seeds:
            try:
                drv_d = _draw_one(fb_v, x_v, sig_v, s_, _n_draw)
                _draw_cdfs.append(_ecdf_on_grid(drv_d, _x_grid_l))
            except Exception:
                continue
        _band_cdfs = []
        for _i in range(_n_band):
            try:
                drv_b = _draw_one(
                    fb_v, x_v, sig_v, 1000 + seed_offset + _i, _n_draw)
                _band_cdfs.append(_ecdf_on_grid(drv_b, _x_grid_l))
            except Exception:
                continue
        if len(_band_cdfs) >= 5:
            arr = np.asarray(_band_cdfs)
            return (np.median(arr, axis=0),
                    np.percentile(arr, 16, axis=0),
                    np.percentile(arr, 84, axis=0),
                    _draw_cdfs)
        return None, None, None, _draw_cdfs

    grid_med, grid_lo, grid_hi, grid_draws = _draws_and_band(
        float(best_fbin), float(best_x), float(sigma_single),
        seed_offset=0,
    )

    _have_marg = False
    marg_med = marg_lo = marg_hi = None
    marg_draws: list = []
    if marg_params is not None:
        _m_fb = float(marg_params.get('f_bin', best_fbin))
        _m_x = float(marg_params.get(x_name, best_x))
        _m_sig = float(marg_params.get('sigma', sigma_single))
        _params_differ = (
            (not np.isclose(_m_fb, float(best_fbin), atol=1e-6))
            or (not np.isclose(_m_x, float(best_x), atol=1e-6))
            or (not np.isclose(_m_sig, float(sigma_single), atol=1e-6))
        )
        if _params_differ:
            _have_marg = True
            marg_med, marg_lo, marg_hi, marg_draws = _draws_and_band(
                _m_fb, _m_x, _m_sig, seed_offset=500,
            )

    # CDF style constants — single source of truth.
    from bc.render_validation import (
        _CDF_OBS_COLOR, _CDF_FIT_COLOR, _CDF_FIT_MARG_COLOR,
        _CLR_SINGLE, _CLR_BINARY,
    )

    fig = go.Figure()

    # Grid 16/84 band
    if grid_med is not None:
        fig.add_trace(go.Scatter(
            x=_x_grid_l, y=grid_lo, mode='lines',
            line=dict(color='rgba(0,0,0,0)', shape='hv'),
            showlegend=False, hoverinfo='skip',
        ))
        fig.add_trace(go.Scatter(
            x=_x_grid_l, y=grid_hi, mode='lines',
            line=dict(color='rgba(0,0,0,0)', shape='hv'),
            fill='tonexty',
            fillcolor=_hex_to_rgba(_CDF_FIT_COLOR, 0.16),
            name='Grid best-fit 16/84',
        ))

    # Grid faint draws
    for _i, _gd in enumerate(grid_draws):
        fig.add_trace(go.Scatter(
            x=_x_grid_l, y=_gd,
            mode='lines',
            line=dict(color=_CDF_FIT_COLOR, width=1.0,
                      dash='dash', shape='hv'),
            opacity=0.30,
            name='Grid best-fit draws' if _i == 0 else None,
            showlegend=(_i == 0),
            hoverinfo='skip',
        ))

    # Grid median
    if grid_med is not None:
        fig.add_trace(go.Scatter(
            x=_x_grid_l, y=grid_med, mode='lines',
            line=dict(color=_CDF_FIT_COLOR, width=2.5,
                      dash='dash', shape='hv'),
            name='Grid best-fit (median)',
        ))

    # Marginal band + draws + median
    if _have_marg and marg_med is not None:
        fig.add_trace(go.Scatter(
            x=_x_grid_l, y=marg_lo, mode='lines',
            line=dict(color='rgba(0,0,0,0)', shape='hv'),
            showlegend=False, hoverinfo='skip',
        ))
        fig.add_trace(go.Scatter(
            x=_x_grid_l, y=marg_hi, mode='lines',
            line=dict(color='rgba(0,0,0,0)', shape='hv'),
            fill='tonexty',
            fillcolor=_hex_to_rgba(_CDF_FIT_MARG_COLOR, 0.16),
            name='Marginal best-fit 16/84',
        ))
        for _i, _md in enumerate(marg_draws):
            fig.add_trace(go.Scatter(
                x=_x_grid_l, y=_md,
                mode='lines',
                line=dict(color=_CDF_FIT_MARG_COLOR, width=1.0,
                          dash='dash', shape='hv'),
                opacity=0.30,
                name='Marginal best-fit draws' if _i == 0 else None,
                showlegend=(_i == 0),
                hoverinfo='skip',
            ))
        fig.add_trace(go.Scatter(
            x=_x_grid_l, y=marg_med, mode='lines',
            line=dict(color=_CDF_FIT_MARG_COLOR, width=2.5,
                      dash='dash', shape='hv'),
            name='Marginal best-fit (median)',
        ))

    # Mock observation: TRUE empirical step (NOT binned) so per-star
    # dots align exactly with the curve.  See Round-5 fix in the Dsilva
    # twin (render_lk_explorer.py) for the full rationale.
    from bc.helpers import _obs_label as _obs_label_sc
    _obs_name_sc = _obs_label_sc(result)
    _obs_arr_l = np.asarray(obs_delta_rv, dtype=float)
    _obs_finite_l = _obs_arr_l[np.isfinite(_obs_arr_l)]
    _n_obs_l = int(_obs_finite_l.size)
    if _n_obs_l > 0:
        _obs_sort_l = np.argsort(_obs_finite_l)
        _obs_sorted_l = _obs_finite_l[_obs_sort_l]
        _obs_cdf_l = (np.arange(_n_obs_l) + 1) / _n_obs_l
        fig.add_trace(go.Scatter(
            x=_obs_sorted_l, y=_obs_cdf_l,
            mode='lines', name='Mock observation',
            line=dict(color=_CDF_OBS_COLOR, width=2.5, shape='hv'),
        ))
    else:
        _obs_sorted_l = None

    # Per-star markers — paired with the SAME sort that built the obs step.
    from bc.validation_io import load_per_star_truth
    _is_bin = load_per_star_truth(result)
    if (_is_bin is not None and _obs_sorted_l is not None
            and len(_is_bin) == len(obs_delta_rv)):
        _is_bin_full_l = np.asarray(_is_bin, dtype=bool)
        if _is_bin_full_l.size == _obs_arr_l.size:
            _finite_mask_l = np.isfinite(_obs_arr_l)
            _is_bin_finite_l = _is_bin_full_l[_finite_mask_l]
            _is_bin_sorted_l = _is_bin_finite_l[_obs_sort_l]
        else:
            _is_bin_sorted_l = np.zeros(_n_obs_l, dtype=bool)
        _single_mask_l = ~_is_bin_sorted_l
        if np.any(_single_mask_l):
            fig.add_trace(go.Scatter(
                x=_obs_sorted_l[_single_mask_l],
                y=_obs_cdf_l[_single_mask_l],
                mode='markers',
                marker=dict(color=_CLR_SINGLE, size=8,
                            line=dict(color='black', width=0.6)),
                name=f'Single ({int(_single_mask_l.sum())})',
                hovertemplate='single · ΔRV=%{x:.1f} km/s<extra></extra>',
            ))
        if np.any(_is_bin_sorted_l):
            fig.add_trace(go.Scatter(
                x=_obs_sorted_l[_is_bin_sorted_l],
                y=_obs_cdf_l[_is_bin_sorted_l],
                mode='markers',
                marker=dict(color=_CLR_BINARY, size=8,
                            line=dict(color='black', width=0.6)),
                name=f'Binary ({int(_is_bin_sorted_l.sum())})',
                hovertemplate='binary · ΔRV=%{x:.1f} km/s<extra></extra>',
            ))

    _title_l = f'CDF Sanity Check (Grid f_bin={best_fbin:.3f}'
    if _have_marg:
        _title_l += f', Marginal f_bin={float(marg_params["f_bin"]):.3f}'
    _title_l += f', N_draw={_n_draw})'
    fig.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(text=_title_l, font=dict(size=14)),
        'xaxis_title': 'ΔRV (km/s)',
        'yaxis_title': 'Cumulative fraction',
        'height': 460,
        'legend': dict(x=0.55, y=0.35, font=dict(size=9)),
    })
    # A&A journal theme (white bg, black serif text)
    from bc.render_validation import _AA_OVERRIDES
    fig.update_layout(**_AA_OVERRIDES)
    fig.update_xaxes(**_AA_OVERRIDES['xaxis'])
    fig.update_yaxes(**_AA_OVERRIDES['yaxis'])
    st.plotly_chart(fig, use_container_width=True,
                    key=f'{p_prefix}_cdf_sanity')
    _caption_l = (
        f'5 faint individual draws (N={_n_draw} stars each) + median (bold) '
        f'+ 16/84 percentile band (from {_n_band} draws) for the **grid** '
        '(red) best-fit'
    )
    if _have_marg:
        _caption_l += ' and the **marginal** (purple) best-fit'
    _caption_l += f'.  Black step = {_obs_name_sc.lower()} empirical CDF.'
    st.caption(_caption_l)


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
            DEFAULT_DRV_BIN_EDGES,
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

    # Caption + Reset button.  Two columns now — the Run button gate
    # was removed (2026-04-29) so logL + CDF + heatmaps + histogram +
    # detection-fraction recompute on every slider/number_input change
    # via @st.cache_data on _explorer_run_grid_pipeline_cached.
    _best_score = me_info.get('best_score', 0)
    _reset_col1, _reset_col2 = st.columns([0.75, 0.25])
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

    # ──────────────────────────────────────────────────────────────────
    # Explorer-only likelihood bin editor (always visible, session-tunable).
    # Persists to a SEPARATE settings namespace
    # (`explorer_likelihood_bin_config`) so the simulation's saved
    # `likelihood_bin_config` is never overwritten.  Defaults pre-populate
    # from the loaded simulation's `result['likelihood_bin_edges']`.
    # ──────────────────────────────────────────────────────────────────
    st.markdown('**Likelihood bins (Explorer)**')
    try:
        from wr_bias_simulation import DSILVA_LIKELIHOOD_BINS as _DSILVA_LK_BINS
    except ImportError:
        _DSILVA_LK_BINS = np.array([0.0, 50.0, 250.0, 650.0, np.inf])
    _sim_lk_be = (np.asarray(result.get('likelihood_bin_edges'), dtype=float)
                  if result.get('likelihood_bin_edges') is not None
                  else _DSILVA_LK_BINS)
    try:
        from shared import get_settings_manager as _gsm_me
        _sm_me = _gsm_me()
    except Exception:
        _sm_me = None
    from bc.params import _render_explorer_lk_bin_config as _render_me_lk_be
    lk_be = _render_me_lk_be(prefix, '_lk_langer', _sm_me, _sim_lk_be)

    # Sliders + synced number inputs for precise control.  Extend by 1
    # for the n_sets number_input on the right (2026-04-29 spec).
    sig_g = np.asarray(result.get('sigma_grid', []))
    _ncols = 1 + (1 if sig_g.size > 1 else 0) + (1 if _lp_g.size > 1 else 0) + 1

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

    # n_sets number_input (2026-04-29) — Langer twin.  Default mirrors
    # what the grid worker actually used so the Explorer score lands on
    # the same number stored in logL_raw at that cell.  Persisted on
    # change per project rule "All UI inputs persist on change".
    _ns_default_raw = result.get('grid_n_sets', result.get('n_sets', 1000))
    if _ns_default_raw is None:
        _ns_default_raw = 1000
    _ns_default = int(_ns_default_raw)
    _ns_key = f'{prefix}_lk_me_n_sets'
    if _ns_key not in st.session_state:
        try:
            from shared import get_settings_manager as _gsm_ll
            _saved = _gsm_ll().load().get('lk_explorer_langer', {}).get(
                'n_sets')
            if _saved is not None:
                st.session_state[_ns_key] = int(_saved)
            else:
                st.session_state[_ns_key] = _ns_default
        except Exception:
            st.session_state[_ns_key] = _ns_default

    def _persist_n_sets_l():
        try:
            from shared import get_settings_manager as _gsm_ll2
            _gsm_ll2().save(['lk_explorer_langer', 'n_sets'],
                            value=int(st.session_state[_ns_key]))
        except Exception:
            pass

    # Place n_sets input in the rightmost slider column.  Initial value
    # is read from session_state[_ns_key] (seeded above).
    cols[-1].number_input(
        'n_sets',
        min_value=1, step=100, format='%d',
        key=_ns_key, on_change=_persist_n_sets_l,
        help='Number of simulations per Explorer recompute.  Default '
             'matches the grid worker\'s n_sets so the Explorer logL '
             'matches the grid\'s stored logL_raw at the same cell.',
    )
    _n_sets_me = int(st.session_state[_ns_key])

    obs_drv = np.asarray(result.get('obs_delta_rv'))
    be = result.get('bin_edges')
    be = np.asarray(be) if be is not None else DEFAULT_DRV_BIN_EDGES
    # NB: `lk_be` is supplied by the Explorer-only bin editor above; do NOT
    # overwrite from `result['likelihood_bin_edges']` here.
    sigma_m = float(result.get('sigma_meas', 3.0))
    # E048: full physics config + cadence library for grid-matching re-sim.
    _cad_lib_me = result.get('cadence_library')
    _cad_wt_me = result.get('cadence_weights')
    _bc_tuple_me = _result_bin_cfg_tuple(result)
    _pm_me = _result_period_model(result, default='langer2020')

    _lp_for_sim = me_logPmax if me_logPmax is not None else def_logPmax

    # ──────────────────────────────────────────────────────────────────
    # Auto-recompute (2026-04-29) — Langer twin parity with Dsilva.
    # Run button removed; cached wrapper makes back-and-forth slider
    # motion instant.  Numerical equivalence with the grid is preserved
    # bit-for-bit (same simulate_delta_rv_cadence_aware +
    # multinomial_log_likelihood, deterministic seed_base+idx_cell seed).
    # ──────────────────────────────────────────────────────────────────

    _sigma_g_seed = np.asarray(result.get('sigma_grid', []))
    _fbin_g_seed = np.asarray(result.get('fbin_grid', []))
    _pi_g_seed = np.asarray(result.get('pi_grid', []))
    _logPmax_g_seed = np.asarray(result.get('logPmax_grid', []))
    _seed_base_me = int(result.get('seed_base', 1234))
    _cell_seed = _explorer_seed_for_cell(
        result, _sigma_g_seed, _fbin_g_seed, _pi_g_seed, _logPmax_g_seed,
        me_sig, me_fb, 0.0, _lp_for_sim, seed_base=_seed_base_me,
    )

    # Global best logL — direct lookup from stored grid array.
    _logL_raw_arr = (np.asarray(result.get('logL_raw'), dtype=float)
                     if result.get('logL_raw') is not None else None)
    _logL_best = float('nan')
    _bf_seed = _seed_base_me
    _bf_sig_v = def_sig
    _bf_fb_v = def_fb
    _bf_lp_v = def_logPmax
    _bf_pi_v = 0.0
    if _logL_raw_arr is not None and _logL_raw_arr.size > 0:
        try:
            _flat_best = int(np.nanargmax(_logL_raw_arr))
            _best_idx = np.unravel_index(_flat_best, _logL_raw_arr.shape)
            _logL_best = float(_logL_raw_arr[_best_idx])
            _ndim = _logL_raw_arr.ndim
            if _ndim == 4:
                _bf_lp_v = float(_logPmax_g_seed[_best_idx[0]])
                _bf_sig_v = float(_sigma_g_seed[_best_idx[1]])
                _bf_fb_v = float(_fbin_g_seed[_best_idx[2]])
                _bf_pi_v = float(_pi_g_seed[_best_idx[3]]) if _pi_g_seed.size > 0 else 0.0
            elif _ndim == 3:
                _bf_sig_v = float(_sigma_g_seed[_best_idx[0]])
                _bf_fb_v = float(_fbin_g_seed[_best_idx[1]])
                _bf_pi_v = float(_pi_g_seed[_best_idx[2]]) if _pi_g_seed.size > 0 else 0.0
            elif _ndim == 2:
                _bf_fb_v = float(_fbin_g_seed[_best_idx[0]])
                _bf_pi_v = float(_pi_g_seed[_best_idx[1]]) if _pi_g_seed.size > 0 else 0.0
            _bf_seed = _explorer_seed_for_cell(
                result, _sigma_g_seed, _fbin_g_seed, _pi_g_seed,
                _logPmax_g_seed,
                _bf_sig_v, _bf_fb_v, _bf_pi_v, _bf_lp_v,
                seed_base=_seed_base_me,
            )
        except Exception:
            _bf_seed = _seed_base_me

    # Auto-recompute on every change.  Cached wrapper makes back-and-
    # forth slider motion instant after the first compute.
    try:
        with st.spinner('Computing logL…'):
            _run_payload = _run_grid_pipeline_via_cache(
                me_fb, 0.0, me_sig, _lp_for_sim,
                sigma_m, be, lk_be, obs_drv, _cad_lib_me, _cad_wt_me,
                _bc_tuple_me, _pm_me, _n_sets_me, _cell_seed, result,
            )
        _have_run = True
        _logL = float(_run_payload['logL'])
        med_cdf = np.asarray(_run_payload['median_cdf'])
        pooled_drv = np.asarray(_run_payload['pooled'])
    except Exception as _err:
        st.warning(f'Explorer recompute failed: {_err}')
        _have_run = False
        _logL = None
        med_cdf = None
        pooled_drv = None

    mc1, mc2 = st.columns(2)
    _cur_parts = [f'f_bin={me_fb:.3f}']
    _best_parts_mc = [f'f_bin={def_fb:.3f}']
    if me_logPmax is not None:
        _cur_parts.append(f'logP={me_logPmax:.2f}')
        _best_parts_mc.append(f'logP={def_logPmax:.2f}')
    if sig_g.size > 1:
        _cur_parts.append(f'σ={me_sig:.1f}')
        _best_parts_mc.append(f'σ={def_sig:.1f}')
    if _have_run:
        mc1.metric(
            label='Current (Explorer)',
            value=', '.join(_cur_parts),
            delta=f'logL = {_logL:.4f}',
            delta_color='off',
        )
    else:
        mc1.metric(
            label='Current (Explorer)',
            value=', '.join(_cur_parts),
            delta='—',
            delta_color='off',
        )
    if np.isfinite(_logL_best):
        mc2.metric(
            label='Global best',
            value=', '.join(_best_parts_mc),
            delta=f'logL = {_logL_best:.4f}',
            delta_color='off',
        )
    else:
        mc2.metric(
            label='Global best',
            value=', '.join(_best_parts_mc),
            delta='—',
            delta_color='off',
        )

    # -- CDF with error shadow + optional best-fit overlay --------
    obs_cdf = _binned_cdf(obs_drv, be)
    if med_cdf is not None:
        # Append (pooled_max, 1.0) so the step CDF visibly reaches 1.0.
        # Every simulated star is ≤ pooled_max by construction, so the
        # empirical CDF at pooled_max is 1.0 in every set, hence the
        # per-set median is also 1.0.
        if pooled_drv is not None and len(pooled_drv):
            _pooled_max = float(np.nanmax(pooled_drv))
        else:
            _pooled_max = float(be[-1])
        med_x = np.concatenate([[0.0], be, [_pooled_max]])
        med_y = np.concatenate([[0.0], med_cdf, [1.0]])
    else:
        med_x = np.array([])
        med_y = np.array([])

    # Best-fit overlay — lazily computed via grid pipeline + cached.
    _show_bestfit = st.checkbox('Compare with algorithm best-fit',
                                value=False, key=f'{prefix}_lk_me_cmp_best')
    _bf_med = None
    _bf_pooled = None
    if _show_bestfit and info is not None and _have_run:
        _bf_bv = info.get('best_vals', {})
        _bf_fb = float(_bf_bv.get('fbin', _bf_fb_v))
        _bf_sig = float(_bf_bv.get('sigma', _bf_sig_v))
        _bf_lp = float(_bf_bv.get('logPmax', _bf_lp_v))
        try:
            with st.spinner('Computing best-fit CDF…'):
                _bf_payload = _run_grid_pipeline_via_cache(
                    _bf_fb, 0.0, _bf_sig, _bf_lp,
                    sigma_m, be, lk_be, obs_drv, _cad_lib_me, _cad_wt_me,
                    _bc_tuple_me, _pm_me, _n_sets_me, _bf_seed, result,
                )
            _bf_med = np.asarray(_bf_payload['median_cdf'])
            _bf_pooled = np.asarray(_bf_payload['pooled'])
        except Exception:
            _bf_med = None
            _bf_pooled = None

    # Conditional "Mock Observation" label in the Validation flow.
    from bc.helpers import _obs_label as _obs_label_me, smooth_pooled_cdf
    _obs_name_me = _obs_label_me(result)

    # CDF style constants — single source of truth (Phase 6 finishing pass).
    from bc.render_validation import (
        _CDF_OBS_COLOR, _CDF_FIT_COLOR, _CLR_SINGLE, _CLR_BINARY,
    )

    # Snapshot store (session-only) — feature: Saved attempts (Langer).
    _snap_key = f'{prefix}_lk_me_langer_snapshots'
    st.session_state.setdefault(_snap_key, [])

    fig_cdf = go.Figure()
    fig_cdf.add_trace(go.Scatter(
        x=be, y=obs_cdf, mode='lines', name=_obs_name_me,
        line=dict(color=_CDF_OBS_COLOR, width=2.5, shape='hv'),
    ))

    # Per-star truth-coded markers (validation flow only).  Markers sit at
    # each star's ΔRV on the empirical CDF (rank+1)/N — not the binned y.
    # Silently skipped outside the validation flow.
    from bc.validation_io import load_per_star_truth
    _is_bin = load_per_star_truth(result)
    if _is_bin is not None and len(_is_bin) == len(obs_drv):
        _sort_idx = np.argsort(np.asarray(obs_drv))
        _drv_sorted = np.asarray(obs_drv)[_sort_idx]
        _is_bin_sorted = np.asarray(_is_bin)[_sort_idx]
        _cdf_vals = (np.arange(len(_drv_sorted)) + 1) / max(len(_drv_sorted), 1)
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

    # Explorer current — smooth pooled CDF + 16/84 band.
    if _have_run:
        _scdf_cur = smooth_pooled_cdf(pooled_drv, _n_sets_me)
        if _scdf_cur is not None:
            _sp, _yp, _xf, _lo, _hi = _scdf_cur
            fig_cdf.add_trace(go.Scatter(
                x=_xf, y=_lo, mode='lines',
                line=dict(color='rgba(0,0,0,0)'),
                legendgroup='cur', showlegend=False, hoverinfo='skip',
            ))
            fig_cdf.add_trace(go.Scatter(
                x=_xf, y=_hi, mode='lines',
                line=dict(color='rgba(0,0,0,0)'),
                fill='tonexty',
                fillcolor=_hex_to_rgba(_CDF_FIT_COLOR, 0.20),
                legendgroup='cur', showlegend=False, hoverinfo='skip',
            ))
            fig_cdf.add_trace(go.Scatter(
                x=_sp, y=_yp, mode='lines', name='Explorer (current)',
                line=dict(color=_CDF_FIT_COLOR, width=2, dash='dash'),
                legendgroup='cur',
            ))
        else:
            # Fallback: empty pool — keep step CDF.
            fig_cdf.add_trace(go.Scatter(
                x=med_x, y=med_y, mode='lines', name='Explorer (current)',
                line=dict(color=_CDF_FIT_COLOR, width=2, dash='dash',
                          shape='hv'),
            ))
    # Best-fit overlay — smooth pooled CDF + 16/84 band.
    if _bf_med is not None:
        _scdf_bf = None
        if _bf_pooled is not None and len(_bf_pooled):
            _scdf_bf = smooth_pooled_cdf(_bf_pooled, _n_sets_me)
        if _scdf_bf is not None:
            _sp_b, _yp_b, _xf_b, _lo_b, _hi_b = _scdf_bf
            fig_cdf.add_trace(go.Scatter(
                x=_xf_b, y=_lo_b, mode='lines',
                line=dict(color='rgba(0,0,0,0)'),
                legendgroup='bf', showlegend=False, hoverinfo='skip',
            ))
            fig_cdf.add_trace(go.Scatter(
                x=_xf_b, y=_hi_b, mode='lines',
                line=dict(color='rgba(0,0,0,0)'),
                fill='tonexty',
                fillcolor=_hex_to_rgba(_CDF_FIT_COLOR, 0.12),
                legendgroup='bf', showlegend=False, hoverinfo='skip',
            ))
            fig_cdf.add_trace(go.Scatter(
                x=_sp_b, y=_yp_b, mode='lines', name='Best-fit (algorithm)',
                line=dict(color=_CDF_FIT_COLOR, width=2, dash='dot'),
                legendgroup='bf',
            ))
        else:
            # Fallback: empty pool — keep step CDF.
            if _bf_pooled is not None and len(_bf_pooled):
                _bf_pooled_max = float(np.nanmax(_bf_pooled))
            else:
                _bf_pooled_max = float(be[-1])
            _bf_x_arr = np.concatenate([[0.0], be, [_bf_pooled_max]])
            _bf_y_arr = np.concatenate([[0.0], _bf_med, [1.0]])
            fig_cdf.add_trace(go.Scatter(
                x=_bf_x_arr, y=_bf_y_arr,
                mode='lines', name='Best-fit (algorithm)',
                line=dict(color=_CDF_FIT_COLOR, width=2, dash='dot', shape='hv'),
            ))
    # Saved-attempt overlays — smooth CDF + 16/84 band per snapshot.
    for _snap in st.session_state[_snap_key]:
        _sc = _snap['color']
        _smooth = _snap.get('smooth_cdf')
        if _smooth is not None:
            _sp, _yp, _xf, _lo, _hi = (np.asarray(a) for a in _smooth)
            # Lower band edge (invisible).
            fig_cdf.add_trace(go.Scatter(
                x=_xf, y=_lo, mode='lines',
                line=dict(color='rgba(0,0,0,0)'),
                legendgroup=f"snap_{_snap['id']}",
                showlegend=False, hoverinfo='skip',
            ))
            # Upper band edge + fill between this and previous trace.
            fig_cdf.add_trace(go.Scatter(
                x=_xf, y=_hi, mode='lines',
                line=dict(color='rgba(0,0,0,0)'),
                fill='tonexty',
                fillcolor=_hex_to_rgba(_sc, 0.18),
                legendgroup=f"snap_{_snap['id']}",
                showlegend=False, hoverinfo='skip',
            ))
            # Median dashed line.
            fig_cdf.add_trace(go.Scatter(
                x=_sp, y=_yp, mode='lines',
                name=f"Save #{_snap['id']} · logL={_snap['logL']:.2f}",
                line=dict(color=_sc, width=2, dash='dash'),
                legendgroup=f"snap_{_snap['id']}",
            ))
        else:
            # Fallback for legacy snapshots without smooth_cdf (or empty pool).
            _smedian = np.asarray(_snap['median_cdf'])
            _spm = float(_snap['pooled_max'])
            _smx = np.concatenate([[0.0], be, [_spm]])
            _smy = np.concatenate([[0.0], _smedian, [1.0]])
            fig_cdf.add_trace(go.Scatter(
                x=_smx, y=_smy, mode='lines',
                name=f"Save #{_snap['id']} · logL={_snap['logL']:.2f}",
                line=dict(color=_sc, width=2, dash='dash', shape='hv'),
                legendgroup=f"snap_{_snap['id']}",
            ))

    # x-range: let plotly autofocus from the data extents.  The trace
    # extension above guarantees the Explorer / best-fit step CDFs reach
    # (pooled_max, 1.0) so the natural data range covers all curves and
    # the rightmost point of any trace at CDF=1.0 is the auto right-edge.
    if _have_run:
        _cdf_title = f'CDF -- logL = {_logL:.3f}'
    else:
        _cdf_title = 'CDF — recompute failed'
    fig_cdf.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(text=_cdf_title, font=dict(size=14)),
        'xaxis_title': 'ΔRV (km/s)',
        'yaxis_title': 'Cumulative fraction',
        'height': 380,
        'margin': dict(l=60, r=30, t=40, b=50),
        'legend': dict(x=0.6, y=0.15),
    })
    # A&A journal theme (white bg, black serif text) — see feedback_aa_journal_style
    from bc.render_validation import _AA_OVERRIDES
    fig_cdf.update_layout(**_AA_OVERRIDES)
    fig_cdf.update_xaxes(**_AA_OVERRIDES['xaxis'])
    fig_cdf.update_yaxes(**_AA_OVERRIDES['yaxis'])
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
        # Snapshot bin-edge overlays — one set of vlines per saved attempt.
        for _snap in st.session_state[_snap_key]:
            _sc = _snap['color']
            for _ei in _snap['lk_be']:
                if np.isfinite(_ei):
                    fig_cdf.add_vline(
                        x=float(_ei),
                        line=dict(color=_sc, width=1, dash='dot'))
    st.plotly_chart(fig_cdf, use_container_width=True,
                    key=f'{prefix}_lk_me_cdf')

    # ── Saved attempts table (session-only) ──────────────────────────
    from bc.helpers import _SNAPSHOT_PALETTE
    _t_c1, _t_c2, _t_c3 = st.columns([0.7, 0.15, 0.15])
    _t_c1.markdown(
        f'### Saved attempts ({len(st.session_state[_snap_key])})')
    if _t_c2.button('💾 Save', key=f'{prefix}_lk_me_snap_save',
                    disabled=(not _have_run)):
        _existing_ids = [s['id'] for s in st.session_state[_snap_key]]
        _new_id = (max(_existing_ids) + 1) if _existing_ids else 1
        _new_color = _SNAPSHOT_PALETTE[(_new_id - 1) % len(_SNAPSHOT_PALETTE)]
        # pooled_max used for trace right edge (mirrors current trace logic).
        if pooled_drv is not None and len(pooled_drv):
            _snap_pmax = float(np.nanmax(pooled_drv))
        else:
            _snap_pmax = float(be[-1])
        _snap = {
            'id': int(_new_id),
            'color': _new_color,
            'lk_be': tuple(float(_e) for _e in np.asarray(lk_be, dtype=float)),
            'f_bin': float(me_fb),
            'x': float(me_x),
            'sigma': float(me_sig),
            'logPmax': (float(me_logPmax)
                        if me_logPmax is not None else None),
            'n_sets': int(_n_sets_me),
            'logL': float(_logL),
            'median_cdf': tuple(float(v) for v in np.asarray(med_cdf, dtype=float)),
            'pooled_max': float(_snap_pmax),
        }
        # Replicate the live Explorer's smooth-CDF rendering for this snapshot.
        # smooth_pooled_cdf returns (_sp, _yp, _xf, _lo, _hi) or None for empty pool.
        _smooth = smooth_pooled_cdf(pooled_drv, _n_sets_me)
        if _smooth is not None:
            _sp, _yp, _xf, _lo, _hi = _smooth
            _snap['smooth_cdf'] = (
                tuple(float(v) for v in np.asarray(_sp, dtype=float)),
                tuple(float(v) for v in np.asarray(_yp, dtype=float)),
                tuple(float(v) for v in np.asarray(_xf, dtype=float)),
                tuple(float(v) for v in np.asarray(_lo, dtype=float)),
                tuple(float(v) for v in np.asarray(_hi, dtype=float)),
            )
        else:
            _snap['smooth_cdf'] = None
        st.session_state[_snap_key].append(_snap)
        st.rerun()
    if _t_c3.button('🧹 Clear all', key=f'{prefix}_lk_me_snap_clear',
                    disabled=(not st.session_state[_snap_key])):
        st.session_state[_snap_key] = []
        st.rerun()

    if st.session_state[_snap_key]:
        # Header row
        _h = st.columns([0.04, 0.20, 0.10, 0.10, 0.10, 0.10, 0.10, 0.06])
        _h[0].caption('')
        _h[1].caption('lk bin edges')
        _h[2].caption('f_bin')
        _h[3].caption(x_label)
        _h[4].caption('σ_single')
        _h[5].caption('logP_max')
        _h[6].caption('logL')
        _h[7].caption('')
        _best_logL_snap = max(
            (float(s['logL']) for s in st.session_state[_snap_key]),
            default=float('-inf'))
        for _snap in list(st.session_state[_snap_key]):
            _r = st.columns([0.04, 0.20, 0.10, 0.10, 0.10, 0.10, 0.10, 0.06])
            _r[0].markdown(
                f'<div style="background:{_snap["color"]}; width:20px; '
                'height:20px; border-radius:3px;"></div>',
                unsafe_allow_html=True)
            _edges_lbl = ', '.join(
                f'{_e:g}' if np.isfinite(_e) else '∞' for _e in _snap['lk_be'])
            _r[1].markdown(f'`{_edges_lbl}`')
            _r[2].write(f'{_snap["f_bin"]:.3f}')
            _r[3].write(f'{_snap["x"]:.3f}')
            _r[4].write(f'{_snap["sigma"]:.2f}')
            _r[5].write(f'{_snap["logPmax"]:.2f}'
                        if _snap['logPmax'] is not None else '—')
            _is_best = (float(_snap['logL']) >= _best_logL_snap - 1e-12)
            _logL_txt = f'{_snap["logL"]:.4f}'
            if _is_best:
                _r[6].markdown(f'**{_logL_txt}**')
            else:
                _r[6].write(_logL_txt)
            if _r[7].button(
                    '✕',
                    key=f'{prefix}_lk_me_snap_del_{_snap["id"]}'):
                st.session_state[_snap_key] = [
                    s for s in st.session_state[_snap_key]
                    if s['id'] != _snap['id']]
                st.rerun()
    if _show_bins_me and _have_run and pooled_drv is not None:
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

    # Heatmaps + histogram + detection-fraction panels all need either
    # the green-dot at the slider position or the freshly simulated
    # pooled ΔRV — only path here is when auto-recompute failed.
    if not _have_run:
        st.info('Adjust the sliders to retry — see warning above for the '
                'recompute failure.')
        return

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
    # (User explicitly authorised CDF colour-constant migration 2026-04-28)
    sim_drv_single = pooled_drv[:1000]
    fig_hist = go.Figure()
    fig_hist.add_trace(go.Histogram(
        x=obs_drv, nbinsx=30, histnorm='probability density',
        name=_obs_name_me, marker_color=_CDF_OBS_COLOR, opacity=0.6,
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
    # User authorised 2026-04-28: A&A theme override applied inside WORKING block
    # (Langer twin — D17 Histogram overlay)
    try:
        from bc.render_validation import _AA_OVERRIDES
        fig_hist.update_layout(**_AA_OVERRIDES)
        fig_hist.update_xaxes(**_AA_OVERRIDES['xaxis'])
        fig_hist.update_yaxes(**_AA_OVERRIDES['yaxis'])
    except Exception:
        pass
    st.plotly_chart(fig_hist, use_container_width=True,
                    key=f'{prefix}_lk_me_hist')

    # ── WORKING — do not change this code · D17: Detection fraction vs threshold ──
    # (User explicitly authorised CDF colour-constant migration 2026-04-28)
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
        x=thresholds, y=frac_obs, mode='lines', name=_obs_name_me,
        line=dict(color=_CDF_OBS_COLOR, width=2.5),
    ))
    fig_det.add_trace(go.Scatter(
        x=thresholds, y=frac_sim, mode='lines', name='Simulated',
        line=dict(color=_CDF_FIT_COLOR, width=2.5, dash='dash'),
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
    # User authorised 2026-04-28: A&A theme override applied inside WORKING block
    # (Langer twin — D17j Detection Fraction)
    try:
        from bc.render_validation import _AA_OVERRIDES
        fig_det.update_layout(**_AA_OVERRIDES)
        fig_det.update_xaxes(**_AA_OVERRIDES['xaxis'])
        _aa_y = dict(_AA_OVERRIDES['yaxis'])
        _aa_y['range'] = [0, 1.05]
        fig_det.update_yaxes(**_aa_y)
    except Exception:
        pass
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
        # Round-5 (2026-04-28): pass marginal-best alongside the joint
        # argmax so the sanity-check overlays a second (purple) draw set.
        _hdi_dict_l = info.get('hdi', {}) if info is not None else {}
        def _marg_or_l(default, name):
            t = _hdi_dict_l.get(name)
            try:
                m = float(t[0]) if t is not None else float('nan')
            except (TypeError, ValueError, IndexError):
                m = float('nan')
            return m if np.isfinite(m) else default
        _grid_fb_l = float(_bv.get('fbin', 0.5))
        _grid_x_l = float(_bv.get(x_name, 0.0))
        _grid_sig_l = float(_bv.get('sigma',
                                    float(result.get('sigma_meas', 5.0))))
        _marg_dict_l = {
            'f_bin': _marg_or_l(_grid_fb_l, 'fbin'),
            x_name: _marg_or_l(_grid_x_l, x_name),
            'sigma': _marg_or_l(_grid_sig_l, 'sigma'),
        }
        # Bug 1e fix (2026-04-28): translate the runner-mode tag into
        # the actual `period_model` string accepted by `sample_logP`
        # (powerlaw / langer2020).  Previously this passed 'dsilva' /
        # 'langer' which raised "Unknown period_model" inside the mock
        # sampler.  Mirror the translation in render_validation.py:57.
        _stored_pm = str(result.get('period_model', 'langer2020')).lower()
        if _stored_pm in ('powerlaw', 'dsilva'):
            _pm = 'powerlaw'
        else:
            _pm = 'langer2020'
        try:
            _render_lk_cdf_sanity_check(
                _grid_fb_l, _grid_x_l, _grid_sig_l,
                np.asarray(obs_delta_rv), _pm, result,
                f'{p}_{method_key}', page_prefix=p,
                marg_params=_marg_dict_l, x_name=x_name)
        except Exception:
            pass
