"""bc.render_lk_explorer -- Likelihood interactive exploration tools.

Model explorer (sliders + CDF + histogram + detection fraction),
re-simulation at interpolated best-fit, and CDF sanity check (cadence).
Hardcoded for Likelihood scoring -- no K-S/CvM branches.
"""
from __future__ import annotations

import os
import sys
from typing import NamedTuple, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


class CDFBandResult(NamedTuple):
    """Return type for `_me_cdf_band` / `_me_cdf_band_langer`.

    Eight named arrays: the existing (median, lo, hi, pooled) plus the
    new (mean, rank_median, rank_mean, rank_bin_frac) carried out of the
    cadence-aware simulator for per-rank CDF panel markers.

    The tuple is also unpackable as a 4-tuple via slicing; call sites
    that only want the legacy fields use attribute access (`.median`,
    `.lo`, `.hi`, `.pooled`).
    """
    median: np.ndarray
    lo: np.ndarray
    hi: np.ndarray
    pooled: np.ndarray
    mean: np.ndarray
    rank_median: np.ndarray
    rank_mean: np.ndarray
    rank_bin_frac: np.ndarray


def _binned_cdf(data: np.ndarray, bin_edges: np.ndarray) -> np.ndarray:
    """Empirical CDF at bin_edges."""
    s = np.sort(data)
    return np.searchsorted(s, bin_edges, side='right') / len(s)


def _explorer_run_grid_pipeline(
    fb: float, pi_v: float, sigma_s: float, logPmax: float,
    sigma_m: float, bin_edges: np.ndarray, lk_be: np.ndarray,
    obs_drv: np.ndarray, cad_lib, cad_wt,
    bin_cfg_dict, period_model: str,
    n_sets: int, seed: int, result: dict,
) -> dict:
    """Run the EXACT grid worker pipeline (`_single_grid_task_cadence_aware`)
    at a single (f_bin, pi, sigma, logPmax) point and return the result
    needed by the Explorer (CDF + logL + pooled drv).

    Mirrors wr_bias_simulation.py:1580-1629.  Same SimulationConfig fields,
    same BinaryParameterConfig copy, same simulate_delta_rv_cadence_aware
    call, same multinomial_log_likelihood scoring.
    """
    from wr_bias_simulation import (
        SimulationConfig, BinaryParameterConfig,
        simulate_delta_rv_cadence_aware, multinomial_log_likelihood,
    )

    # cadence_library may have been persisted as a numpy object array
    # (one entry per star, each entry a 1-D MJD array of varying length).
    # SimulationConfig.assign_times_deterministic requires a Python list
    # of np.ndarrays — coerce here.
    if cad_lib is not None and not isinstance(cad_lib, list):
        try:
            cad_lib_list = [np.asarray(_c, dtype=float) for _c in cad_lib]
        except Exception:
            cad_lib_list = list(cad_lib)
    else:
        cad_lib_list = cad_lib

    if cad_wt is not None and hasattr(cad_wt, 'tolist'):
        cad_wt_list = cad_wt.tolist()
    else:
        cad_wt_list = cad_wt

    sim_cfg_local = SimulationConfig(
        n_stars=len(cad_lib_list) if cad_lib_list is not None else 25,
        n_epochs=int(result.get('n_epochs', 6)),
        time_span=float(result.get('time_span', 3650.0)),
        sigma_single=float(sigma_s),
        sigma_measure=float(sigma_m),
        v_sys=float(result.get('v_sys', 0.0)),
        observation_times=result.get('observation_times'),
        cadence_library=cad_lib_list,
        cadence_weights=cad_wt_list,
        error_model_single=str(result.get('error_model_single', 'fixed')),
        error_params_single=tuple(result.get('error_params_single', ()) or ()),
        error_model_binary=str(result.get('error_model_binary', 'fixed')),
        error_params_binary=tuple(result.get('error_params_binary', ()) or ()),
    )

    if bin_cfg_dict is not None:
        try:
            bin_cfg_local = BinaryParameterConfig(**dict(bin_cfg_dict))
        except Exception:
            bin_cfg_local = BinaryParameterConfig()
    else:
        bin_cfg_local = BinaryParameterConfig()
    bin_cfg_local.logP_max = float(logPmax)
    bin_cfg_local.period_model = str(period_model)

    rng = np.random.default_rng(int(seed))
    sim_result = simulate_delta_rv_cadence_aware(
        f_bin=float(fb), pi=float(pi_v),
        sim_cfg=sim_cfg_local, bin_cfg=bin_cfg_local, rng=rng,
        n_sets=int(n_sets), bin_edges=bin_edges,
    )
    pooled = sim_result['all_delta_rv'].ravel()
    logL = float(multinomial_log_likelihood(obs_drv, pooled, lk_be))
    return {
        'logL': logL,
        'median_cdf': sim_result['median_cdf'],
        'lo_cdf': sim_result['lo_cdf'],
        'hi_cdf': sim_result['hi_cdf'],
        'pooled': pooled,
    }


# ---------------------------------------------------------------------------
# Cached wrapper around _explorer_run_grid_pipeline (auto-update Explorer)
# ---------------------------------------------------------------------------
# Project rule "All UI inputs persist on change" + the user's request
# (2026-04-29) to drop the Run-button gate require an inexpensive
# recompute path so dragging a slider does not trigger a redundant
# n_sets-shot simulation.  We wrap _explorer_run_grid_pipeline in
# @st.cache_data so back-and-forth slider motion is instant after the
# first compute.  The cache key is built from primitive/hashable args
# only — `result` is decomposed into its scalar/tuple ingredients so
# the cache key actually changes when (and only when) physics inputs
# change.

def _hashable_cadence_library(cad_lib):
    """Convert a cadence library (list/object-array of 1D MJD arrays)
    into a hashable nested tuple.  Returns None when input is None."""
    if cad_lib is None:
        return None
    try:
        return tuple(tuple(float(x) for x in np.asarray(arr, dtype=float).ravel())
                     for arr in cad_lib)
    except Exception:
        # Worst-case fallback: hash by repr (still hashable, deterministic
        # for the lifetime of the result dict).
        return repr(cad_lib)


def _hashable_1d(arr):
    """Convert a 1D-ish array/list to a tuple of floats.  None → None."""
    if arr is None:
        return None
    try:
        return tuple(float(x) for x in np.asarray(arr, dtype=float).ravel())
    except Exception:
        return None


@st.cache_data(show_spinner=False)
def _explorer_run_grid_pipeline_cached(
    fb: float, pi_v: float, sigma_s: float, logPmax: float,
    sigma_m: float, n_sets: int, seed: int,
    bin_edges_tuple: tuple, lk_be_tuple: tuple, obs_drv_tuple: tuple,
    cad_lib_tuple, cad_wt_tuple,
    bin_cfg_dict_tuple, period_model: str,
    n_stars: int, n_epochs: int, time_span: float, v_sys: float,
    obs_times_tuple,
    error_model_single: str, error_params_single: tuple,
    error_model_binary: str, error_params_binary: tuple,
) -> dict:
    """Cached grid-pipeline run keyed on hashable primitives.

    Reconstructs the minimum `result`-like dict that
    `_explorer_run_grid_pipeline` reads, then delegates.  This keeps the
    grid-equivalence invariant intact (same SimulationConfig fields,
    same BinaryParameterConfig copy, same simulate_delta_rv_cadence_aware
    call, same multinomial_log_likelihood scoring) — the wrapper only
    serialises arguments for the cache key.
    """
    # Reconstruct ndarrays from hashable tuples.
    bin_edges = np.asarray(bin_edges_tuple, dtype=float)
    lk_be = np.asarray(lk_be_tuple, dtype=float)
    obs_drv = np.asarray(obs_drv_tuple, dtype=float)
    if cad_lib_tuple is None:
        cad_lib = None
    elif isinstance(cad_lib_tuple, str):
        cad_lib = None  # repr fallback — degrade gracefully
    else:
        cad_lib = [np.asarray(t, dtype=float) for t in cad_lib_tuple]
    cad_wt = (list(cad_wt_tuple) if cad_wt_tuple is not None else None)

    # Build a minimal result dict carrying only the fields
    # _explorer_run_grid_pipeline reads.
    _obs_times = (None if obs_times_tuple is None
                  else list(obs_times_tuple))
    _result_min = {
        'n_epochs': int(n_epochs),
        'time_span': float(time_span),
        'v_sys': float(v_sys),
        'observation_times': _obs_times,
        'error_model_single': str(error_model_single),
        'error_params_single': tuple(error_params_single),
        'error_model_binary': str(error_model_binary),
        'error_params_binary': tuple(error_params_binary),
    }
    return _explorer_run_grid_pipeline(
        float(fb), float(pi_v), float(sigma_s), float(logPmax),
        float(sigma_m), bin_edges, lk_be, obs_drv,
        cad_lib, cad_wt,
        bin_cfg_dict_tuple, str(period_model),
        int(n_sets), int(seed), _result_min,
    )


def _run_grid_pipeline_via_cache(
    fb: float, pi_v: float, sigma_s: float, logPmax: float,
    sigma_m: float, bin_edges: np.ndarray, lk_be: np.ndarray,
    obs_drv: np.ndarray, cad_lib, cad_wt,
    bin_cfg_dict_tuple, period_model: str,
    n_sets: int, seed: int, result: dict,
) -> dict:
    """Adapter: build hashable args from a `result` dict and call the
    cached wrapper.  Use this everywhere the Explorer would have called
    `_explorer_run_grid_pipeline` directly so repeated parameter
    combinations are served from cache."""
    return _explorer_run_grid_pipeline_cached(
        float(fb), float(pi_v), float(sigma_s), float(logPmax),
        float(sigma_m), int(n_sets), int(seed),
        tuple(np.asarray(bin_edges, dtype=float).ravel().tolist()),
        tuple(np.asarray(lk_be, dtype=float).ravel().tolist()),
        tuple(np.asarray(obs_drv, dtype=float).ravel().tolist()),
        _hashable_cadence_library(cad_lib),
        _hashable_1d(cad_wt),
        bin_cfg_dict_tuple,
        str(period_model),
        int(len(cad_lib) if cad_lib is not None else
            result.get('n_stars', 25)),
        int(result.get('n_epochs', 6)),
        float(result.get('time_span', 3650.0)),
        float(result.get('v_sys', 0.0)),
        _hashable_1d(result.get('observation_times')),
        str(result.get('error_model_single', 'fixed')),
        tuple(result.get('error_params_single', ()) or ()),
        str(result.get('error_model_binary', 'fixed')),
        tuple(result.get('error_params_binary', ()) or ()),
    )


def _explorer_seed_for_cell(
    result: dict, sigma_g: np.ndarray, fbin_g: np.ndarray, pi_g: np.ndarray,
    logPmax_g: np.ndarray,
    me_sig: float, me_fb: float, me_pi: float, me_logPmax: float,
    seed_base: int = 1234,
) -> int:
    """Reproduce the grid worker's seed for the cell nearest the slider tuple.

    Mirrors `_build_tasks_for_slice` in app/bc/runners_cadence.py:96-106 for
    the multi-logPmax case, and `run_bias_grid_cadence_aware` in
    wr_bias_simulation.py:1672-1683 for the single-logPmax case.

    Loop nesting (outer→inner):  logPmax → sigma → fbin → pi.

    seed = seed_base
            + i_lp * (n_sig * n_fb * n_pi)
            + i_sig * (n_fb * n_pi)
            + i_fb  *  n_pi
            + i_pi
    """
    sigma_g = np.asarray(sigma_g) if sigma_g is not None else np.array([])
    fbin_g = np.asarray(fbin_g) if fbin_g is not None else np.array([])
    pi_g = np.asarray(pi_g) if pi_g is not None else np.array([])
    logPmax_g = (np.asarray(logPmax_g) if logPmax_g is not None
                 else np.array([]))

    n_sig = max(int(sigma_g.size), 1)
    n_fb = max(int(fbin_g.size), 1)
    n_pi = max(int(pi_g.size), 1)

    i_sig = (int(np.argmin(np.abs(sigma_g - me_sig)))
             if sigma_g.size > 0 else 0)
    i_fb = (int(np.argmin(np.abs(fbin_g - me_fb)))
            if fbin_g.size > 0 else 0)
    i_pi = (int(np.argmin(np.abs(pi_g - me_pi)))
            if pi_g.size > 0 else 0)
    i_lp = (int(np.argmin(np.abs(logPmax_g - me_logPmax)))
            if logPmax_g.size > 1 else 0)

    return int(seed_base
               + i_lp * (n_sig * n_fb * n_pi)
               + i_sig * (n_fb * n_pi)
               + i_fb * n_pi
               + i_pi)

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
def _me_cdf_band(
    fb: float, x_val: float, sigma_s: float, sigma_m: float,
    bin_edges_tuple: tuple, logPmax: float = 5.0, n_sets: int = 50,
    _cadence_library=None, _cadence_weights=None,
    _bin_cfg_dict=None, period_model: str = 'powerlaw',
) -> CDFBandResult:
    """Run *n_sets* simulations and return a `CDFBandResult` with 8 fields.

    When _cadence_library is provided, uses cadence-aware simulation
    (matching the grid runner). Otherwise falls back to basic simulation.

    Parameters
    ----------
    _bin_cfg_dict : tuple of (key, value) pairs OR None
        Hashable (via the tuple form) full bin_cfg contents. When provided,
        a BinaryParameterConfig is rebuilt from it and `logP_max` +
        `period_model` are overridden per the other args. When None, falls
        back to the legacy behaviour (BinaryParameterConfig with just
        logP_max set). This mirrors the grid worker exactly — see E048.
    period_model : str
        'powerlaw' or 'langer2020'. Explicitly propagated to bin_cfg so the
        period distribution used here matches the one scored by the grid.

    Note (2026-04-29): the previous validation_mode branch (mock-replay
    sampler with seed reuse) was removed.  The Explorer now drives all
    scoring through the Run button + `_explorer_run_grid_pipeline`, which
    matches the grid worker bit-for-bit.  The cached helper here is only
    consumed by the legacy re-sim and CDF-sanity-check paths.
    """
    from wr_bias_simulation import (
        simulate_delta_rv_sample, simulate_delta_rv_cadence_aware,
        SimulationConfig, BinaryParameterConfig,
    )
    _be = np.array(bin_edges_tuple)
    # Rebuild bin_cfg from the FULL dict when available. Fall back to the
    # legacy (logP_max only) path for old .npz files that don't carry the
    # bin_cfg payload.
    if _bin_cfg_dict is not None:
        try:
            _bc_d = dict(_bin_cfg_dict)
            bin_cfg = BinaryParameterConfig(**_bc_d)
        except Exception:
            bin_cfg = BinaryParameterConfig(logP_max=logPmax)
    else:
        bin_cfg = BinaryParameterConfig(logP_max=logPmax)
    # Explorer slider (logPmax) always wins over the stored value.
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
            fb, x_val, cfg, bin_cfg, rng, n_sets=n_sets, bin_edges=_be)
        all_drv = res['all_delta_rv']
        all_cdfs = np.array(
            [_binned_cdf(all_drv[i], _be) for i in range(all_drv.shape[0])])
        pooled = all_drv.ravel()
        mean_cdf_arr  = res['mean_cdf']
        rank_median   = res['per_rank_median_drv']
        rank_mean     = res['per_rank_mean_drv']
        rank_bin_frac = res['per_rank_binary_fraction']
    else:
        all_cdfs, all_drv = [], []
        for si in range(n_sets):
            cfg = SimulationConfig(n_stars=1000, sigma_single=sigma_s,
                                   sigma_measure=sigma_m)
            drv = simulate_delta_rv_sample(fb, x_val, cfg, bin_cfg,
                                           np.random.default_rng(42 + si))
            all_cdfs.append(_binned_cdf(drv, _be))
            all_drv.append(drv)
        all_cdfs = np.array(all_cdfs)
        pooled = np.concatenate(all_drv)
        # No per-rank info available — pooled across stars.  Empty rank
        # arrays cause the renderer to skip the per-rank gradient markers.
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


def _bin_cfg_dict_as_hashable(bc_dict):
    """Convert a bin_cfg dict (possibly with nested dict/list/tuple values)
    into a hashable nested-tuple form suitable as a cache key.

    Returns None when bc_dict is None/empty. Falls back to repr-string
    for anything exotic.
    """
    if not bc_dict:
        return None

    def _freeze(v):
        if isinstance(v, dict):
            return tuple(sorted(
                (k, _freeze(vv)) for k, vv in v.items()))
        if isinstance(v, (list, tuple)):
            return tuple(_freeze(vv) for vv in v)
        if isinstance(v, np.ndarray):
            return tuple(v.tolist())
        try:
            hash(v)
            return v
        except TypeError:
            return repr(v)

    try:
        return tuple(sorted((str(k), _freeze(v)) for k, v in bc_dict.items()))
    except Exception:
        return None


def _result_bin_cfg_tuple(result):
    """Pull bin_cfg dict from result and return hashable tuple form."""
    _raw = result.get('bin_cfg') if result is not None else None
    if _raw is None:
        return None
    # .npz → np.array(dict, dtype=object) .item() recovers the dict. If the
    # caller already unwrapped it (common on load), pass through.
    if hasattr(_raw, 'item') and getattr(_raw, 'ndim', 1) == 0:
        try:
            _raw = _raw.item()
        except Exception:
            pass
    if not isinstance(_raw, dict):
        return None
    return _bin_cfg_dict_as_hashable(_raw)


def _result_period_model(result, default='powerlaw'):
    """Read period_model from result, tolerating missing / numpy-string values."""
    if result is None:
        return default
    _pm = result.get('period_model', default)
    if _pm is None:
        return default
    # Handle 0-d numpy array
    if hasattr(_pm, 'item') and getattr(_pm, 'ndim', 1) == 0:
        try:
            _pm = _pm.item()
        except Exception:
            pass
    _pm = str(_pm)
    if _pm in ('powerlaw', 'langer2020'):
        return _pm
    return default


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
        xv = float(interp.get('pi', interp.get('sigma',
                   interp.get('y_val', 0.0))))
        sig = float(interp.get('sigma', result.get('sigma_meas', 5.0)))
        be = (np.asarray(result['bin_edges'])
              if 'bin_edges' in result else DEFAULT_DRV_BIN_EDGES)
        lk_be = (np.asarray(result['likelihood_bin_edges'])
                 if 'likelihood_bin_edges' in result else be)
        _lpm = float(interp.get('logPmax', 5.0))
        _lp_g_ri = np.asarray(result.get('logPmax_grid', []))
        if _lp_g_ri.size >= 1:
            _lpm = float(interp.get('logPmax', float(_lp_g_ri[0])))
        # E048: pass full bin_cfg + period_model + cadence_weights so the
        # re-simulated CDF/logL sits on the exact surface the grid scored.
        _bc_tuple = _result_bin_cfg_tuple(result)
        _pm_resim = _result_period_model(result, default='powerlaw')
        _cad_lib_resim = result.get('cadence_library')
        _cad_wt_resim = result.get('cadence_weights')
        _b = _me_cdf_band(
            fb, xv, sig, float(result.get('sigma_meas', 3.0)),
            tuple(be.tolist()), logPmax=_lpm, n_sets=int(ns),
            _cadence_library=_cad_lib_resim,
            _cadence_weights=_cad_wt_resim,
            _bin_cfg_dict=_bc_tuple,
            period_model=_pm_resim,
        )
        med_c, lo_c, hi_c, pooled = _b.median, _b.lo, _b.hi, _b.pooled
        obs = np.asarray(result.get('obs_delta_rv', []))
        rx = np.concatenate([[0.0], be])

        # Compute likelihood score
        logL = multinomial_log_likelihood(obs, pooled, lk_be)

        # Round-5 (2026-04-28): also re-simulate at the MARGINAL-best
        # tuple (read off ``result['analysis_marginal_best']`` if cached
        # by `_method_best_and_hdi`, else fall back to a quick recomputation
        # from the likelihood grid).  Plotted in PURPLE.
        marg_med = marg_lo = marg_hi = None
        try:
            from bc.analysis import _method_best_and_hdi
            _lk_arr = np.asarray(result.get('likelihood', []))
            _fbg = np.asarray(result.get('fbin_grid', []))
            _pig = np.asarray(result.get('pi_grid', []))
            _sgg = np.asarray(result.get('sigma_grid', []))
            _lpg = np.asarray(result.get('logPmax_grid', []))
            _grids_m = []
            _names_m = []
            if _lpg.size > 1:
                _grids_m.append(_lpg)
                _names_m.append('logPmax')
            if _sgg.size > 1:
                _grids_m.append(_sgg)
                _names_m.append('sigma')
            if _fbg.size > 0:
                _grids_m.append(_fbg)
                _names_m.append('fbin')
            if _pig.size > 0:
                _grids_m.append(_pig)
                _names_m.append('pi')
            # Squeeze lk to match grids
            _lk_sq = _lk_arr.copy() if _lk_arr is not None else None
            while (_lk_sq is not None and _lk_sq.ndim > len(_grids_m)
                   and _lk_sq.shape[0] == 1):
                _lk_sq = _lk_sq[0]
            if (_lk_sq is not None and _lk_sq.ndim == len(_grids_m)
                    and _lk_sq.size > 0):
                _info_m = _method_best_and_hdi(
                    _lk_sq, _grids_m, _names_m, is_likelihood=True)
                if _info_m is not None:
                    _hdi_m = _info_m.get('hdi', {})
                    _m_fb = float(_hdi_m.get('fbin', (fb,))[0])
                    _m_pi = float(_hdi_m.get('pi', (xv,))[0])
                    _m_sig = float(_hdi_m.get('sigma', (sig,))[0])
                    _m_lpm = float(_hdi_m.get('logPmax', (_lpm,))[0])
                    _params_differ_rs = (
                        (not np.isclose(_m_fb, fb, atol=1e-6))
                        or (not np.isclose(_m_pi, xv, atol=1e-6))
                        or (not np.isclose(_m_sig, sig, atol=1e-6))
                        or (not np.isclose(_m_lpm, _lpm, atol=1e-6))
                    )
                    if _params_differ_rs:
                        _bm = _me_cdf_band(
                            _m_fb, _m_pi, _m_sig,
                            float(result.get('sigma_meas', 3.0)),
                            tuple(be.tolist()), logPmax=_m_lpm,
                            n_sets=int(ns),
                            _cadence_library=_cad_lib_resim,
                            _cadence_weights=_cad_wt_resim,
                            _bin_cfg_dict=_bc_tuple,
                            period_model=_pm_resim,
                        )
                        marg_med, marg_lo, marg_hi, _marg_pooled = (
                            _bm.median, _bm.lo, _bm.hi, _bm.pooled)
        except Exception:
            marg_med = marg_lo = marg_hi = None

        # CDF style constants — keep all CDF panels consistent.
        from bc.render_validation import (
            _CDF_OBS_COLOR, _CDF_FIT_COLOR, _CDF_FIT_MARG_COLOR,
            _CLR_SINGLE, _CLR_BINARY,
        )
        fig = go.Figure()

        # Mock observation: TRUE empirical step (sorted ΔRV) so dots align.
        _obs_arr_rs = np.asarray(obs, dtype=float)
        _obs_finite_rs = _obs_arr_rs[np.isfinite(_obs_arr_rs)]
        _n_obs_rs = int(_obs_finite_rs.size)
        if _n_obs_rs > 0:
            _obs_sort_rs = np.argsort(_obs_finite_rs)
            _obs_sorted_rs = _obs_finite_rs[_obs_sort_rs]
            _obs_cdf_rs = (np.arange(_n_obs_rs) + 1) / _n_obs_rs
            fig.add_trace(go.Scatter(
                x=_obs_sorted_rs, y=_obs_cdf_rs, mode='lines',
                name='Mock observation',
                line=dict(color=_CDF_OBS_COLOR, width=2.5, shape='hv')))
        else:
            _obs_sort_rs = None
            _obs_sorted_rs = None
            _obs_cdf_rs = None

        # Per-star truth-coded markers — paired with the SAME sort that
        # built the obs step, so dots sit ON the curve.
        from bc.validation_io import load_per_star_truth
        _is_bin = load_per_star_truth(result)
        if (_is_bin is not None and _obs_sorted_rs is not None
                and len(_is_bin) == len(obs)):
            _is_bin_full_rs = np.asarray(_is_bin, dtype=bool)
            _finite_mask_rs = np.isfinite(_obs_arr_rs)
            if _is_bin_full_rs.size == _obs_arr_rs.size:
                _is_bin_finite_rs = _is_bin_full_rs[_finite_mask_rs]
                _is_bin_sorted_rs = _is_bin_finite_rs[_obs_sort_rs]
            else:
                _is_bin_sorted_rs = np.zeros(_n_obs_rs, dtype=bool)
            _single_mask_rs = ~_is_bin_sorted_rs
            if np.any(_single_mask_rs):
                fig.add_trace(go.Scatter(
                    x=_obs_sorted_rs[_single_mask_rs],
                    y=_obs_cdf_rs[_single_mask_rs],
                    mode='markers',
                    marker=dict(color=_CLR_SINGLE, size=8,
                                line=dict(color='black', width=0.6)),
                    name=f'Single ({int(_single_mask_rs.sum())})',
                    hovertemplate='single · ΔRV=%{x:.1f} km/s<extra></extra>',
                ))
            if np.any(_is_bin_sorted_rs):
                fig.add_trace(go.Scatter(
                    x=_obs_sorted_rs[_is_bin_sorted_rs],
                    y=_obs_cdf_rs[_is_bin_sorted_rs],
                    mode='markers',
                    marker=dict(color=_CLR_BINARY, size=8,
                                line=dict(color='black', width=0.6)),
                    name=f'Binary ({int(_is_bin_sorted_rs.sum())})',
                    hovertemplate='binary · ΔRV=%{x:.1f} km/s<extra></extra>',
                ))

        # GRID best-fit: 16/84 band + median
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

        # MARGINAL best-fit: 16/84 band + median (purple)
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

        _title_rs = f'Re-sim: Grid f_bin={fb:.4f}'
        if marg_med is not None:
            _title_rs += f', Marginal f_bin={_m_fb:.4f}'
        else:
            _title_rs += f', {x_label}={xv:.3f}'
        fig.update_layout(**{
            **PLOTLY_THEME, 'height': 380,
            'title': dict(text=_title_rs, font=dict(size=14)),
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
                                x_name: str = 'pi') -> None:
    """Render CDF draws vs observed with an expected 16/84 band.

    Round-5 (2026-04-28) rewrite:
      - Replace the binned obs CDF (``_binned_cdf(obs, bin_edges)``) with the
        TRUE empirical step at sorted ΔRV values, so the per-star dots sit
        EXACTLY on the black curve (the previous binned step landed at fixed
        bin edges, while the dots landed at each star's ΔRV — they appeared
        to "fly" off the step).
      - Optionally accept ``marg_params`` and overlay a SECOND set of draws
        + 16/84 band + bold median in PURPLE.  The grid set stays in RED.
      - Each best-fit shows: all N_draw faint dashed draws + a bold median
        + a translucent 16/84 shadow band.

    Stage D (2026-04-23) rewrite (kept):
      - configurable ``n_draw`` via an inline number_input (default 500),
      - 16/84 percentile band from ``_n_band`` draws at n_draw stars,
      - canonical mock sampler so overlays line up with the Explorer.
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

    # Inline control for per-draw sample size
    _n_draw_key = f'{p_prefix}_cdf_sanity_n'
    if _n_draw_key not in st.session_state:
        st.session_state[_n_draw_key] = 500
    _n_draw = int(st.number_input(
        'Stars per draw (n_draw)',
        min_value=25, max_value=5000, step=25,
        key=_n_draw_key,
        help=('How many simulated stars per CDF draw.  Higher n_draw = '
              'smoother curves + tighter 16/84 band.  The caption describes '
              'exactly what is plotted.')
    ))

    # Bug 2 fix: rebuild bin_cfg from the result so the canonical sampler
    # sees the SAME physics config the grid did (E048).
    _bcfg_dict = result.get('bin_cfg', {}) or {}
    bcfg = (BinaryParameterConfig(**_bcfg_dict)
            if _bcfg_dict else BinaryParameterConfig())

    # Bug 2 fix: pull the joint argmax from the result so the 5 draws use
    # the SAME (f_bin, π, σ, logP_max) tuple the rest of the Validation
    # Explorer is wired to (memory/feedback_honest_labels.md).  Best-fit
    # callers pass the joint argmax via best_fbin / best_x / sigma_single
    # already; here we additionally need logP_max since the legacy
    # sampler ignored it.
    _eff_logPmax = float(result.get('argmax_logPmax',
                                    _bcfg_dict.get('logP_max', 5.0)))
    if not np.isfinite(_eff_logPmax):
        _eff_logPmax = float(_bcfg_dict.get('logP_max', 5.0))

    _sigma_meas = float(result.get('sigma_meas', 1.622))

    # Bug 2 fix: derive validation context (error_model / error_params /
    # validation seed) from session_state when this Explorer is rendered
    # from the Validation tab.  page_prefix is the page-level prefix
    # (e.g. 'bc_val_dsilva') under which the mock generator stashed the
    # 8-tuple at f'{page_prefix}_val_mock_params'.  Outside the validation
    # flow we get an empty mock-params tuple and fall back to
    # 'fixed' / () — exactly what the legacy code assumed implicitly.
    _pp = page_prefix
    if _pp is None and isinstance(p_prefix, str):
        # Fallback: strip the trailing '_<method_key>' the call site appended.
        # Method keys today are always 'likelihood'; this is the same
        # heuristic used by other re-sim helpers in this module.
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

    # The sanity-check needs a DIFFERENT rng per draw, so we don't reuse
    # the validation seed (that one matches the mock byte-for-byte).
    # Seeds 1000+i (band) and 42..(42+n_draw) (draws) are inherited from
    # the 2026-04-23 rewrite for backward visual continuity.

    def _draw_one(fb_v: float, x_v: float, sig_v: float,
                  seed_int: int, n_stars: int) -> np.ndarray:
        """Single CDF draw via the canonical mock sampler.  ``fb_v / x_v /
        sig_v`` allow swapping in the marginal-best tuple at call time."""
        # _sample_delta_rv_mock takes a cadence_library — we want
        # n_stars samples, but the library has 25 entries.  Tile or
        # slice as appropriate so the per-draw sample count matches the
        # n_draw the user picked.
        cad = list(cadence_library)
        if n_stars <= len(cad):
            cad = cad[:n_stars]
        else:
            # Repeat the cadence library cyclically to reach n_stars.
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

    # ── x-grid for empirical step CDFs ────────────────────────────────
    # Use a fine grid so the simulated CDFs and obs CDF share the same
    # x-axis.  Range = max(bin_edges, max(obs_delta_rv)) so the obs
    # rightmost step and the sim tail are both captured.
    _obs_max = float(np.nanmax(obs_delta_rv)) if len(obs_delta_rv) else 0.0
    _be_max = float(np.nanmax(_bin_edges[np.isfinite(_bin_edges)])) if len(_bin_edges) else 0.0
    _x_max_sc = max(_obs_max, _be_max, 1.0) * 1.05
    _x_grid = np.linspace(0.0, _x_max_sc, 400)

    def _ecdf_on_grid(sample: np.ndarray, grid: np.ndarray) -> np.ndarray:
        """Empirical CDF of a sample evaluated at ``grid``.  Equivalent to
        a step at sorted(sample) values but resampled onto a uniform x-axis
        for traces that need to share x-coords (the 16/84 band needs all
        traces on the same grid, otherwise ``np.percentile`` mixes apples
        and oranges)."""
        s = np.asarray(sample, dtype=float)
        s = s[np.isfinite(s)]
        if s.size == 0:
            return np.zeros_like(grid)
        ss = np.sort(s)
        return np.searchsorted(ss, grid, side='right').astype(float) / s.size

    # ── 1. Generate draws for GRID and MARGINAL best-fit tuples ─────────
    _n_band = 50

    def _draws_and_band(fb_v, x_v, sig_v, seed_offset):
        """Run n_draw draws + n_band band draws, return median, lo, hi,
        plus the n_draw individual CDFs (faint overlay)."""
        # Faint individual draws — we plot all of them at alpha 0.3.
        # Seeds offset by ``seed_offset`` so grid and marginal draws use
        # different RNG streams.
        _draw_seeds = list(range(42 + seed_offset, 42 + seed_offset + 5))
        _draw_cdfs = []
        for s_ in _draw_seeds:
            try:
                drv_d = _draw_one(fb_v, x_v, sig_v, s_, _n_draw)
                _draw_cdfs.append(_ecdf_on_grid(drv_d, _x_grid))
            except Exception:
                continue
        # 16/84 band from many draws
        _band_cdfs = []
        for _i in range(_n_band):
            try:
                drv_b = _draw_one(
                    fb_v, x_v, sig_v, 1000 + seed_offset + _i, _n_draw)
                _band_cdfs.append(_ecdf_on_grid(drv_b, _x_grid))
            except Exception:
                continue
        if len(_band_cdfs) >= 5:
            arr = np.asarray(_band_cdfs)
            _med = np.median(arr, axis=0)
            _lo = np.percentile(arr, 16, axis=0)
            _hi = np.percentile(arr, 84, axis=0)
        else:
            _med = _lo = _hi = None
        return _med, _lo, _hi, _draw_cdfs

    # GRID best-fit tuple (red)
    grid_med, grid_lo, grid_hi, grid_draws = _draws_and_band(
        float(best_fbin), float(best_x), float(sigma_single),
        seed_offset=0,
    )

    # MARGINAL best-fit tuple (purple) — only when caller provided one
    # AND it differs from the grid tuple.  The grid sanity-check still
    # works as a single-color overlay when ``marg_params is None``.
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

    # CDF style constants — keep observation/sim styles consistent across
    # all CDF panels.  See render_validation._CDF_OBS_COLOR.
    from bc.render_validation import (
        _CDF_OBS_COLOR, _CDF_FIT_COLOR, _CDF_FIT_MARG_COLOR,
    )

    fig = go.Figure()

    # ── 2. GRID 16/84 band (plotted FIRST so traces sit on top) ─────────
    if grid_med is not None:
        fig.add_trace(go.Scatter(
            x=_x_grid, y=grid_lo, mode='lines',
            line=dict(color='rgba(0,0,0,0)', shape='hv'),
            showlegend=False, hoverinfo='skip',
        ))
        fig.add_trace(go.Scatter(
            x=_x_grid, y=grid_hi, mode='lines',
            line=dict(color='rgba(0,0,0,0)', shape='hv'),
            fill='tonexty',
            fillcolor=_hex_to_rgba(_CDF_FIT_COLOR, 0.16),
            name='Grid best-fit 16/84',
        ))

    # ── 3. GRID faint individual draws (one legend entry only) ──────────
    for _i, _gd in enumerate(grid_draws):
        fig.add_trace(go.Scatter(
            x=_x_grid, y=_gd,
            mode='lines',
            line=dict(color=_CDF_FIT_COLOR, width=1.0,
                      dash='dash', shape='hv'),
            opacity=0.30,
            name='Grid best-fit draws' if _i == 0 else None,
            showlegend=(_i == 0),
            hoverinfo='skip',
        ))

    # ── 4. GRID median (BOLD red dashed) ────────────────────────────────
    if grid_med is not None:
        fig.add_trace(go.Scatter(
            x=_x_grid, y=grid_med, mode='lines',
            line=dict(color=_CDF_FIT_COLOR, width=2.5,
                      dash='dash', shape='hv'),
            name='Grid best-fit (median)',
        ))

    # ── 5. MARGINAL band + draws + median (purple) ──────────────────────
    if _have_marg and marg_med is not None:
        fig.add_trace(go.Scatter(
            x=_x_grid, y=marg_lo, mode='lines',
            line=dict(color='rgba(0,0,0,0)', shape='hv'),
            showlegend=False, hoverinfo='skip',
        ))
        fig.add_trace(go.Scatter(
            x=_x_grid, y=marg_hi, mode='lines',
            line=dict(color='rgba(0,0,0,0)', shape='hv'),
            fill='tonexty',
            fillcolor=_hex_to_rgba(_CDF_FIT_MARG_COLOR, 0.16),
            name='Marginal best-fit 16/84',
        ))
        for _i, _md in enumerate(marg_draws):
            fig.add_trace(go.Scatter(
                x=_x_grid, y=_md,
                mode='lines',
                line=dict(color=_CDF_FIT_MARG_COLOR, width=1.0,
                          dash='dash', shape='hv'),
                opacity=0.30,
                name='Marginal best-fit draws' if _i == 0 else None,
                showlegend=(_i == 0),
                hoverinfo='skip',
            ))
        fig.add_trace(go.Scatter(
            x=_x_grid, y=marg_med, mode='lines',
            line=dict(color=_CDF_FIT_MARG_COLOR, width=2.5,
                      dash='dash', shape='hv'),
            name='Marginal best-fit (median)',
        ))

    # ── 6. Observed / Mock CDF — TRUE empirical step (NOT binned) ───────
    # Round-5 (2026-04-28): the previous implementation used
    # ``_binned_cdf(obs_delta_rv, _bin_edges)`` which placed y-values at
    # FIXED bin-edge x-positions, while the per-star dots landed at each
    # star's ΔRV — so dots appeared OFF the black step.  Fix: build the
    # empirical step from sorted ΔRV values directly, so dots and step
    # come from the same data and the dots sit ON the curve.
    from bc.helpers import _obs_label as _obs_label_sc
    _obs_name_sc = _obs_label_sc(result)
    _obs_arr = np.asarray(obs_delta_rv, dtype=float)
    _obs_finite = _obs_arr[np.isfinite(_obs_arr)]
    _n_obs = int(_obs_finite.size)
    if _n_obs > 0:
        _obs_sort_idx = np.argsort(_obs_finite)
        _obs_sorted = _obs_finite[_obs_sort_idx]
        _obs_cdf_y = (np.arange(_n_obs) + 1) / _n_obs
        fig.add_trace(go.Scatter(
            x=_obs_sorted, y=_obs_cdf_y,
            mode='lines', name='Mock observation',
            line=dict(color=_CDF_OBS_COLOR, width=2.5, shape='hv'),
            hovertemplate='ΔRV=%{x:.1f} km/s<br>CDF=%{y:.3f}<extra></extra>',
        ))

    # ── 7. Per-star truth-coded markers (validation flow only) ──────────
    # Markers sit at each star's ΔRV on the empirical CDF (rank+1)/N —
    # NOW exactly aligned with the black step (same source data).  Silently
    # skipped outside the validation flow (no mock_stars file).
    from bc.validation_io import load_per_star_truth
    from bc.render_validation import _CLR_SINGLE, _CLR_BINARY
    _is_bin = load_per_star_truth(result)
    if (_is_bin is not None and _n_obs > 0
            and len(_is_bin) == len(obs_delta_rv)):
        # Apply the SAME sort that built the obs CDF.  ``_obs_sort_idx``
        # indexes into ``_obs_finite`` which (when no NaNs) is the same as
        # the original ``obs_delta_rv``.  When NaNs are present we fall
        # back to argsorting the truth array against the original obs
        # array.  This is the dot-positioning fix the brief flagged.
        _is_bin_full = np.asarray(_is_bin, dtype=bool)
        if _is_bin_full.size == _obs_arr.size:
            _finite_mask = np.isfinite(_obs_arr)
            _is_bin_finite = _is_bin_full[_finite_mask]
            _is_bin_sorted = _is_bin_finite[_obs_sort_idx]
        else:
            _is_bin_sorted = np.zeros(_n_obs, dtype=bool)
        _single_mask = ~_is_bin_sorted
        if np.any(_single_mask):
            fig.add_trace(go.Scatter(
                x=_obs_sorted[_single_mask], y=_obs_cdf_y[_single_mask],
                mode='markers',
                marker=dict(color=_CLR_SINGLE, size=8,
                            line=dict(color='black', width=0.6)),
                name=f'Single ({int(_single_mask.sum())})',
                hovertemplate='single · ΔRV=%{x:.1f} km/s<extra></extra>',
            ))
        if np.any(_is_bin_sorted):
            fig.add_trace(go.Scatter(
                x=_obs_sorted[_is_bin_sorted], y=_obs_cdf_y[_is_bin_sorted],
                mode='markers',
                marker=dict(color=_CLR_BINARY, size=8,
                            line=dict(color='black', width=0.6)),
                name=f'Binary ({int(_is_bin_sorted.sum())})',
                hovertemplate='binary · ΔRV=%{x:.1f} km/s<extra></extra>',
            ))

    _title_parts = [f'CDF Sanity Check (Grid f_bin={best_fbin:.3f}']
    if _have_marg:
        _title_parts[0] += (
            f', Marginal f_bin={float(marg_params["f_bin"]):.3f}'
        )
    _title_parts[0] += f', N_draw={_n_draw})'
    fig.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(text=_title_parts[0], font=dict(size=14)),
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
    _caption = (
        f'5 faint individual draws (N={_n_draw} stars each) + median (bold) '
        f'+ 16/84 percentile band (from {_n_band} draws) for the **grid** '
        '(red) best-fit'
    )
    if _have_marg:
        _caption += ' and the **marginal** (purple) best-fit'
    _caption += (
        f'.  Black step = {_obs_name_sc.lower()} empirical CDF.  '
        'If the black curve sits inside the band across the full ΔRV range '
        'the best-fit reproduces the data within expected Monte-Carlo '
        'variation.'
    )
    st.caption(_caption)


# ---------------------------------------------------------------------------
# Model Explorer -- interactive grid browser
# ---------------------------------------------------------------------------

# WORKING — do not change this code (D17: Model Explorer)
def _render_lk_model_explorer(
    result: dict, display_name: str,
    fbin_g: np.ndarray, x_g: np.ndarray, x_name: str, x_label: str,
    prefix: str, info: dict | None,
    p_nd: np.ndarray,
) -> None:
    """Interactive Likelihood model explorer: sliders -> CDF + score + histogram + det frac."""
    try:
        from wr_bias_simulation import (
            simulate_with_params,
            SimulationConfig, BinaryParameterConfig,
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

    # ──────────────────────────────────────────────────────────────────
    # Slider defaults from joint argmax of logL_raw (Reset-to-best fix)
    # ──────────────────────────────────────────────────────────────────
    # The marginalised best from `_method_best_and_hdi` (used elsewhere
    # for HDI68 summaries) is a 2D-projected argmax that disagrees with
    # the joint argmax of the full N-D logL_raw cube.  For the Explorer
    # sliders + Reset button we want the joint argmax so that landing on
    # the Reset target reproduces the displayed "Global best logL".
    #
    # We also need the actual GRID-fixed values for non-scanned axes
    # (σ when sigma_grid.size==1, logP_max when logPmax_grid.size==1) —
    # NOT sigma_meas (measurement noise constant).
    _seed_base_me = int(result.get('seed_base', 1234))
    _sigma_g_seed = np.asarray(result.get('sigma_grid', []))
    _fbin_g_seed = np.asarray(result.get('fbin_grid', []))
    _pi_g_seed = np.asarray(result.get('pi_grid', []))
    _logPmax_g_seed = np.asarray(result.get('logPmax_grid', []))

    # Recover bin_cfg dict so we can pull the fixed logP_max when
    # logPmax_grid is size 1 / empty.
    _bc_tuple_for_default = _result_bin_cfg_tuple(result)
    _bc_dict_for_default = (
        dict(_bc_tuple_for_default) if _bc_tuple_for_default is not None
        else (result.get('bin_cfg') if isinstance(result.get('bin_cfg'), dict) else {})
    )

    # Safe fallbacks BEFORE ndim dispatch — guarantees all four _bf_*
    # are defined for Case D (2D, neither σ nor logP_max scanned).
    _bf_fb_v = float(bv.get('fbin', 0.5))
    _bf_pi_v = float(bv.get(x_name, 0.0))
    if _sigma_g_seed.size >= 1:
        _bf_sig_v = float(_sigma_g_seed[0])
    else:
        _bf_sig_v = float(result.get('sigma_meas', 5.0))
    if _logPmax_g_seed.size >= 1:
        _bf_lp_v = float(_logPmax_g_seed[0])
    else:
        _bf_lp_v = float(_bc_dict_for_default.get('logP_max', 5.0))

    _logL_raw_arr = (np.asarray(result.get('logL_raw'), dtype=float)
                     if result.get('logL_raw') is not None else None)
    _logL_best = float('nan')
    if _logL_raw_arr is not None and _logL_raw_arr.size > 0:
        try:
            _flat_best = int(np.nanargmax(_logL_raw_arr))
            _best_idx = np.unravel_index(_flat_best, _logL_raw_arr.shape)
            _logL_best = float(_logL_raw_arr[_best_idx])
            # Layout matches runner: [logPmax?, sigma?, fbin, pi]
            _ndim = _logL_raw_arr.ndim
            if _ndim == 4:
                _bf_lp_v = float(_logPmax_g_seed[_best_idx[0]])
                _bf_sig_v = float(_sigma_g_seed[_best_idx[1]])
                _bf_fb_v = float(_fbin_g_seed[_best_idx[2]])
                _bf_pi_v = float(_pi_g_seed[_best_idx[3]])
            elif _ndim == 3:
                _bf_sig_v = float(_sigma_g_seed[_best_idx[0]])
                _bf_fb_v = float(_fbin_g_seed[_best_idx[1]])
                _bf_pi_v = float(_pi_g_seed[_best_idx[2]])
            elif _ndim == 2:
                _bf_fb_v = float(_fbin_g_seed[_best_idx[0]])
                _bf_pi_v = float(_pi_g_seed[_best_idx[1]])
        except Exception:
            pass

    # Slider defaults — joint argmax of logL_raw (Bug A fix).
    def_fb = float(_bf_fb_v)
    def_x = float(_bf_pi_v)
    def_sig = float(_bf_sig_v)
    _bf_logPmax = float(_bf_lp_v)

    # Reset counter — slider keys include counter so reset forces new widgets
    _reset_key = f'{prefix}_lk_me_reset_count'
    _rc = st.session_state.get(_reset_key, 0)

    # Detect first render after Reset (or first page load) so we can
    # bypass the slider's implicit-step quantisation for the simulation
    # call.  See the override block below for the full rationale.
    _last_rc_key = f'{prefix}_lk_me_last_rc'
    _last_rc = st.session_state.get(_last_rc_key, None)
    _just_reset = (_last_rc != _rc)
    st.session_state[_last_rc_key] = _rc

    # Caption + Reset button.  Two columns now — the Run button gate was
    # removed (2026-04-29) so logL + CDF + heatmaps + histogram +
    # detection-fraction recompute on every slider/number_input change
    # via @st.cache_data on _explorer_run_grid_pipeline_cached.
    _lp_g = np.asarray(result.get('logPmax_grid', []))
    # _best_score (marginal best from _method_best_and_hdi) was previously
    # shown in the caption, but the caption now reports the joint-argmax
    # _logL_best from logL_raw to stay consistent with the Reset target
    # and the "Global best logL" metric card.  me_info itself is still
    # consumed elsewhere on the page for the marginalised HDI68 summary.
    _reset_col1, _reset_col2 = st.columns([0.75, 0.25])
    with _reset_col1:
        # Show joint-argmax for scanned axes, "(fixed)" for non-scanned.
        _best_parts = [f'f_bin={_bf_fb_v:.3f}', f'{x_label}={_bf_pi_v:.3f}']

        _sig_g_pre = np.asarray(result.get('sigma_grid', []))
        if _sig_g_pre.size > 1:
            _best_parts.append(f'σ_single={_bf_sig_v:.2f}')
        elif _sig_g_pre.size == 1:
            _best_parts.append(f'σ_single={float(_sig_g_pre[0]):.2f} (fixed)')

        _lp_g_pre = np.asarray(result.get('logPmax_grid', []))
        if _lp_g_pre.size > 1:
            _best_parts.append(f'logP_max={_bf_lp_v:.2f}')
        elif _lp_g_pre.size == 1:
            _best_parts.append(f'logP_max={float(_lp_g_pre[0]):.2f} (fixed)')

        st.caption(f'Best-fit model: {", ".join(_best_parts)}  |  logL = {_logL_best:.4f}')
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
    lk_be = _render_me_lk_be(prefix, '_lk', _sm_me, _sim_lk_be)

    # Sliders + synced number inputs for precise control.  n_sets gets
    # its own (rightmost) column — see step 2 of the 2026-04-29
    # auto-update spec.  Extend _ncols by 1 for the n_sets number_input.
    sig_g = np.asarray(result.get('sigma_grid', []))
    _ncols = (4 if _lp_g.size > 1 else 3) + 1

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

    me_fb = _synced_slider_input(
        cols[0], f'f_bin  (best: {def_fb:.3f})',
        0.0, 1.0, def_fb, 0.001, '%.4f', f'{prefix}_lk_me_fb')

    x_lo, x_hi = (float(x_g[0]) if len(x_g) else -3.0,
                   float(x_g[-1]) if len(x_g) else 3.0)
    if x_lo < x_hi:
        me_x = _synced_slider_input(
            cols[1], f'{x_label}  (best: {def_x:.3f})',
            x_lo, x_hi, min(max(def_x, x_lo), x_hi), 0.001, '%.4f',
            f'{prefix}_lk_me_x')
    else:
        me_x = def_x

    if sig_g.size > 1:
        me_sig = _synced_slider_input(
            cols[2], f'σ_single  (best: {def_sig:.1f})',
            float(sig_g[0]), float(sig_g[-1]),
            min(max(def_sig, float(sig_g[0])), float(sig_g[-1])),
            0.1, '%.2f', f'{prefix}_lk_me_sig')
    else:
        # Bug B fix: use the grid-fixed value, NOT sigma_meas.
        me_sig = (float(sig_g[0]) if sig_g.size == 1
                  else float(result.get('sigma_meas', 5.0)))

    me_logPmax = None
    if _lp_g.size > 1:
        _dlp = float(_bf_lp_v)
        _c = cols[3] if sig_g.size > 1 else cols[2]
        me_logPmax = _synced_slider_input(
            _c, f'logP_max  (best: {_dlp:.2f})',
            float(_lp_g[0]), float(_lp_g[-1]),
            min(max(_dlp, float(_lp_g[0])), float(_lp_g[-1])),
            0.01, '%.3f', f'{prefix}_lk_me_logPmax')

    # Resolve effective logP_max for simulation.  Bug B fix: when
    # logP_max isn't scanned use the grid's fixed value (size==1) or
    # the bin_cfg value, NOT a hardcoded 5.0 fallback.
    if me_logPmax is not None:
        _eff_logPmax = float(me_logPmax)
    elif _lp_g.size == 1:
        _eff_logPmax = float(_lp_g[0])
    else:
        _eff_logPmax = float(_bc_dict_for_default.get('logP_max', 5.0))

    # Bypass slider quantisation on Reset.  Streamlit's float slider quantises
    # its session_state value to an implicit step (≈ (max-min)/100), so even
    # when we write the exact _bf_* float as the default, the slider returns
    # a rounded version that does NOT reproduce the grid's stored logL.
    # On the first render after Reset (and on first page load), force the
    # simulation to receive the exact joint-argmax floats.  Subsequent renders
    # pass the user's slider value through untouched — no auto-snap.
    if _just_reset and _logL_raw_arr is not None and _logL_raw_arr.size > 0:
        me_fb = float(_bf_fb_v)
        me_x = float(_bf_pi_v)
        if sig_g.size > 1:
            me_sig = float(_bf_sig_v)
        if _lp_g.size > 1:
            me_logPmax = float(_bf_lp_v)
            _eff_logPmax = me_logPmax

    # n_sets number_input (2026-04-29): user-tunable simulation count.
    # Default mirrors what the grid worker actually used so the Explorer
    # score lands on the SAME number stored in logL_raw at that cell.
    # Persist on every change per project rule "All UI inputs persist
    # on change" (see _render_cadence_adaptive_bins, params.py:442).
    _ns_default_raw = result.get('grid_n_sets', result.get('n_sets', 1000))
    if _ns_default_raw is None:
        _ns_default_raw = 1000
    _ns_default = int(_ns_default_raw)
    _ns_key = f'{prefix}_lk_me_n_sets'
    if _ns_key not in st.session_state:
        # Seed from settings_manager if a previously-saved value exists.
        try:
            from shared import get_settings_manager as _gsm_lk
            _sm_lk = _gsm_lk()
            _saved = _sm_lk.load().get('lk_explorer', {}).get('n_sets')
            if _saved is not None:
                st.session_state[_ns_key] = int(_saved)
            else:
                st.session_state[_ns_key] = _ns_default
        except Exception:
            st.session_state[_ns_key] = _ns_default

    def _persist_n_sets():
        try:
            from shared import get_settings_manager as _gsm_lk2
            _gsm_lk2().save(['lk_explorer', 'n_sets'],
                            value=int(st.session_state[_ns_key]))
        except Exception:
            pass

    # Place the n_sets input in the rightmost slider column.  No
    # `value=` arg — Streamlit pulls the initial value from
    # st.session_state[_ns_key] (seeded above from settings or default).
    _ns_col = cols[-1]
    _ns_col.number_input(
        'n_sets',
        min_value=1, step=100, format='%d',
        key=_ns_key, on_change=_persist_n_sets,
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
    _cad_lib = result.get('cadence_library')
    _cad_wt = result.get('cadence_weights')
    # E048: full physics config so the explorer's re-sim matches the grid.
    _bc_tuple_me = _result_bin_cfg_tuple(result)
    _pm_me = _result_period_model(result, default='powerlaw')

    # ──────────────────────────────────────────────────────────────────
    # Auto-recompute (2026-04-29): the Run-button gate was removed —
    # logL + CDF + heatmaps + histogram + detection-fraction now refresh
    # on every slider/number_input change.  The grid pipeline call goes
    # through @st.cache_data, so back-and-forth slider motion is instant
    # after the first compute at each cell.  Numerical equivalence with
    # the grid is preserved bit-for-bit (same simulate_delta_rv_cadence_aware
    # + multinomial_log_likelihood, deterministic seed_base+idx_cell seed).
    # ──────────────────────────────────────────────────────────────────

    # Build the seed for THIS cell exactly the way the grid worker did.
    # Note: _seed_base_me, _sigma_g_seed, _fbin_g_seed, _pi_g_seed,
    # _logPmax_g_seed, _logL_raw_arr, _logL_best, and the joint-argmax
    # _bf_* values were all resolved earlier (above the slider block) so
    # they could feed the slider defaults / Reset target.
    _cell_seed = _explorer_seed_for_cell(
        result, _sigma_g_seed, _fbin_g_seed, _pi_g_seed, _logPmax_g_seed,
        me_sig, me_fb, me_x, _eff_logPmax, seed_base=_seed_base_me,
    )

    # Rebuild the best-fit seed for the optional best-fit-CDF overlay
    # using the joint-argmax coords already computed above.
    _bf_seed = _seed_base_me  # fallback
    if _logL_raw_arr is not None and _logL_raw_arr.size > 0:
        try:
            _bf_seed = _explorer_seed_for_cell(
                result, _sigma_g_seed, _fbin_g_seed, _pi_g_seed,
                _logPmax_g_seed,
                _bf_sig_v, _bf_fb_v, _bf_pi_v, _bf_lp_v,
                seed_base=_seed_base_me,
            )
        except Exception:
            _bf_seed = _seed_base_me

    # Auto-recompute on every change.  The cached wrapper makes back-
    # and-forth slider motion instant after the first compute at each
    # (params, n_sets) cell.  Spinner is shown only while the actual
    # simulation runs (cache hits return immediately).
    try:
        with st.spinner('Computing logL…'):
            _run_payload = _run_grid_pipeline_via_cache(
                me_fb, me_x, me_sig, _eff_logPmax,
                sigma_m, be, lk_be, obs_drv, _cad_lib, _cad_wt,
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

    # ── D17: Score metric cards (logL) ──
    mc1, mc2 = st.columns(2)
    if _have_run:
        mc1.metric(
            label='Current (Explorer)',
            value=f'f_bin={me_fb:.3f}, {x_label}={me_x:.2f}',
            delta=f'logL = {_logL:.4f}',
            delta_color='off',
        )
    else:
        mc1.metric(
            label='Current (Explorer)',
            value=f'f_bin={me_fb:.3f}, {x_label}={me_x:.2f}',
            delta='—',
            delta_color='off',
        )
    if np.isfinite(_logL_best):
        mc2.metric(
            label='Global best',
            value=f'f_bin={def_fb:.3f}, {x_label}={def_x:.2f}',
            delta=f'logL = {_logL_best:.4f}',
            delta_color='off',
        )
    else:
        mc2.metric(
            label='Global best',
            value=f'f_bin={def_fb:.3f}, {x_label}={def_x:.2f}',
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

    # Best-fit overlay (algorithm's best vs explorer's current).  Lazily
    # computed via the SAME grid pipeline at the algorithm's best-fit
    # cell, then cached for the duration of the session.
    _show_bestfit = st.checkbox('Compare with algorithm best-fit',
                                value=False, key=f'{prefix}_lk_me_cmp_best')
    _bf_med = None
    _bf_pooled = None
    if _show_bestfit and info is not None and _have_run:
        _bf_bv = info.get('best_vals', {})
        _bf_fb = float(_bf_bv.get('fbin', def_fb))
        _bf_x = float(_bf_bv.get(x_name, def_x))
        _bf_sig = float(_bf_bv.get('sigma', def_sig))
        _bf_lp = float(_bf_bv.get('logPmax', _bf_logPmax))
        # Routed through the same cached wrapper — first hit runs the
        # simulation, all subsequent slider movements are instant.
        try:
            with st.spinner('Computing best-fit CDF…'):
                _bf_payload = _run_grid_pipeline_via_cache(
                    _bf_fb, _bf_x, _bf_sig, _bf_lp,
                    sigma_m, be, lk_be, obs_drv, _cad_lib, _cad_wt,
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
    # CDF style constants — observation = teal step (NO markers on the
    # line itself; coloured truth-coded dots overlay separately when the
    # validation truth is available).  Current explorer trace and global
    # best-fit overlay both render in dashed red so all 5 CDFs share the
    # same look (best-fit is dotted to distinguish it from the live trace).
    from bc.render_validation import (
        _CDF_OBS_COLOR, _CDF_FIT_COLOR, _CLR_SINGLE, _CLR_BINARY,
    )

    # Snapshot store (session-only) — feature: Saved attempts.
    _snap_key = f'{prefix}_lk_me_snapshots'
    st.session_state.setdefault(_snap_key, [])

    fig_cdf = go.Figure()
    fig_cdf.add_trace(go.Scatter(
        x=be, y=obs_cdf, mode='lines', name=_obs_name_me,
        line=dict(color=_CDF_OBS_COLOR, width=2.5, shape='hv'),
    ))

    # Per-star truth-coded markers (validation flow only).  Skipped
    # silently when load_per_star_truth returns None (real-obs flow).
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
    # Bin diagnostics depend on the pooled sim data — only when a Run
    # has produced it.
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

    # All downstream panels (heatmaps + histogram + detection fraction)
    # depend on either the green-dot at the slider position or the
    # freshly simulated pooled ΔRV array.  In auto-recompute mode the
    # only path here is when the simulation itself failed — surface the
    # warning above and bail.
    if not _have_run:
        st.info('Adjust the sliders to retry — see warning above for the '
                'recompute failure.')
        return

    # ── D17: Explorer heatmaps (2×2) with green dot ──
    _sig_g_hm = np.asarray(result.get('sigma_grid', []))
    _lp_g_hm = np.asarray(result.get('logPmax_grid', []))
    _has_multi_sig = _sig_g_hm.size > 1
    _has_multi_lp = _lp_g_hm.size > 1
    _can_show_fbpi = (p_nd.ndim >= 2)
    _can_show_siglp = (_has_multi_sig and _has_multi_lp)
    if _can_show_fbpi:
        from bc.helpers import _make_heatmap_fig as _mkhm

        # Find current slider indices
        _me_sig_idx = int(np.argmin(np.abs(_sig_g_hm - me_sig))) if _has_multi_sig else 0
        _me_lp_idx = (int(np.argmin(np.abs(_lp_g_hm - me_logPmax)))
                      if me_logPmax is not None and _has_multi_lp else 0)

        # Slice normalized likelihood at current σ/logP → 2D (fbin × pi)
        if p_nd.ndim == 4:
            _norm_fbpi = p_nd[_me_lp_idx, _me_sig_idx]
        elif p_nd.ndim == 3:
            # 3D: leading axis is logP (if scanned) or sigma (if scanned)
            if _has_multi_lp:
                _norm_fbpi = p_nd[_me_lp_idx]
            elif _has_multi_sig:
                _norm_fbpi = p_nd[_me_sig_idx]
            else:
                _norm_fbpi = p_nd[0]
        else:
            _norm_fbpi = p_nd

        # Secondary 2D heatmap: σ × logP (only when both scanned)
        _norm_siglp = None
        if _can_show_siglp and p_nd.ndim == 4:
            _norm_siglp = np.nanmax(p_nd, axis=(2, 3))

        # 1D profile when only one extra axis is scanned
        _norm_1d_vals = None
        _norm_1d_grid = None
        _norm_1d_label = None
        _norm_1d_dot = None
        if not _can_show_siglp:
            if _has_multi_lp:
                _norm_1d_grid = _lp_g_hm
                _norm_1d_label = 'log₁₀(P_max)'
                _norm_1d_dot = _eff_logPmax
                if p_nd.ndim == 4:
                    # 4D [logP, sigma, fbin, pi] — slice at sigma, max over fbin×pi
                    _norm_1d_vals = np.array([
                        float(np.nanmax(p_nd[i, _me_sig_idx]))
                        if np.any(np.isfinite(p_nd[i, _me_sig_idx])) else 0.0
                        for i in range(_lp_g_hm.size)])
                elif p_nd.ndim == 3:
                    _norm_1d_vals = np.array([
                        float(np.nanmax(p_nd[i])) if np.any(np.isfinite(p_nd[i])) else 0.0
                        for i in range(_lp_g_hm.size)])
            elif _has_multi_sig:
                _norm_1d_grid = _sig_g_hm
                _norm_1d_label = 'σ_single (km/s)'
                _norm_1d_dot = me_sig
                if p_nd.ndim == 3:
                    _norm_1d_vals = np.array([
                        float(np.nanmax(p_nd[i])) if np.any(np.isfinite(p_nd[i])) else 0.0
                        for i in range(_sig_g_hm.size)])

        # Unnormalized logL
        _logL_raw = result.get('logL_raw')
        _unnorm_fbpi = _unnorm_siglp = None
        _unnorm_1d_vals = None
        if _logL_raw is not None:
            _lr = np.asarray(_logL_raw, dtype=float)
            if _lr.ndim == 4:
                _unnorm_fbpi = _lr[_me_lp_idx, _me_sig_idx]
                if _can_show_siglp:
                    _unnorm_siglp = np.nanmax(_lr, axis=(2, 3))
                elif _norm_1d_grid is not None and _has_multi_lp:
                    _unnorm_1d_vals = np.array([
                        float(np.nanmax(_lr[i, _me_sig_idx]))
                        if np.any(np.isfinite(_lr[i, _me_sig_idx])) else np.nan
                        for i in range(_norm_1d_grid.size)])
            elif _lr.ndim == 3:
                if _has_multi_lp:
                    _unnorm_fbpi = _lr[_me_lp_idx]
                elif _has_multi_sig:
                    _unnorm_fbpi = _lr[_me_sig_idx]
                else:
                    _unnorm_fbpi = _lr[0]
                # 1D unnormalized profile
                if _norm_1d_grid is not None:
                    _unnorm_1d_vals = np.array([
                        float(np.nanmax(_lr[i])) if np.any(np.isfinite(_lr[i])) else np.nan
                        for i in range(_norm_1d_grid.size)])
            elif _lr.ndim == 2:
                _unnorm_fbpi = _lr

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
            _fig1 = _mkhm(_norm_fbpi, fbin_g, x_g,
                           title='Normalized Likelihood (f<sub>bin</sub> × π)',
                           show_d=False, height=350,
                           x_label=x_label, x_name=x_name,
                           scoring_label='Likelihood',
                           colorbar_title_override='Norm. L')
            _green_dot(_fig1, me_x, me_fb)
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
            elif _norm_1d_vals is not None:
                _fig2 = go.Figure()
                _fig2.add_trace(go.Scatter(
                    x=_norm_1d_grid, y=_norm_1d_vals, mode='lines+markers',
                    line=dict(color=_METHOD_COLOR, width=2),
                    name='Max Norm. L'))
                if _norm_1d_dot is not None:
                    _dot_idx = int(np.argmin(np.abs(_norm_1d_grid - _norm_1d_dot)))
                    _green_dot(_fig2, float(_norm_1d_grid[_dot_idx]),
                               float(_norm_1d_vals[_dot_idx]))
                _fig2.update_layout(**{
                    **PLOTLY_THEME, 'height': 350,
                    'title': dict(text=f'Max Norm. Likelihood vs {_norm_1d_label}',
                                  font=dict(size=14)),
                    'xaxis_title': _norm_1d_label,
                    'yaxis_title': 'Max Norm. Likelihood',
                })
                # User authorised 2026-04-28: A&A theme override applied inside WORKING block
                try:
                    from bc.render_validation import _AA_OVERRIDES
                    _fig2.update_layout(**_AA_OVERRIDES)
                    _fig2.update_xaxes(**_AA_OVERRIDES['xaxis'])
                    _fig2.update_yaxes(**_AA_OVERRIDES['yaxis'])
                except Exception:
                    pass
                st.plotly_chart(_fig2, use_container_width=True,
                                key=f'{prefix}_lk_me_hm_norm_siglp')

        _hm_r2c1, _hm_r2c2 = st.columns(2)
        with _hm_r2c1:
            if _unnorm_fbpi is not None:
                _fig3 = _mkhm(_unnorm_fbpi, fbin_g, x_g,
                               title='log L (f<sub>bin</sub> × π)',
                               show_d=False, height=350,
                               x_label=x_label, x_name=x_name,
                               scoring_label='log L',
                               colorbar_title_override='log L')
                _green_dot(_fig3, me_x, me_fb)
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
            elif _unnorm_1d_vals is not None:
                _fig4 = go.Figure()
                _fig4.add_trace(go.Scatter(
                    x=_norm_1d_grid, y=_unnorm_1d_vals, mode='lines+markers',
                    line=dict(color=_METHOD_COLOR, width=2),
                    name='Max log L'))
                if _norm_1d_dot is not None:
                    _dot_idx = int(np.argmin(np.abs(_norm_1d_grid - _norm_1d_dot)))
                    _green_dot(_fig4, float(_norm_1d_grid[_dot_idx]),
                               float(_unnorm_1d_vals[_dot_idx]))
                _fig4.update_layout(**{
                    **PLOTLY_THEME, 'height': 350,
                    'title': dict(text=f'Max log L vs {_norm_1d_label}',
                                  font=dict(size=14)),
                    'xaxis_title': _norm_1d_label,
                    'yaxis_title': 'Max log L',
                })
                # User authorised 2026-04-28: A&A theme override applied inside WORKING block
                try:
                    from bc.render_validation import _AA_OVERRIDES
                    _fig4.update_layout(**_AA_OVERRIDES)
                    _fig4.update_xaxes(**_AA_OVERRIDES['xaxis'])
                    _fig4.update_yaxes(**_AA_OVERRIDES['yaxis'])
                except Exception:
                    pass
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
        'legend': dict(x=0.65, y=0.95),
    })
    # User authorised 2026-04-28: A&A theme override applied inside WORKING block
    # (D17 Histogram overlay)
    try:
        from bc.render_validation import _AA_OVERRIDES
        fig_hist.update_layout(**_AA_OVERRIDES)
        fig_hist.update_xaxes(**_AA_OVERRIDES['xaxis'])
        fig_hist.update_yaxes(**_AA_OVERRIDES['yaxis'])
    except Exception:
        pass
    st.plotly_chart(fig_hist, use_container_width=True,
                    key=f'{prefix}_lk_me_hist')

    # ── WORKING — do not change this code (D17j: Binary Fraction vs Threshold) ──
    from shared import get_palette as _gp
    _pal = _gp()
    _CLR_DETECTED = '#E25A53'
    _CLR_MISSED = '#F5A623'
    _CLR_OBS = '#4A90D9'
    thresh_dRV = float(result.get('thresh_dRV', 45.5))
    _nsigma = 4.0
    # Simulate at current explorer params to get is_binary + sigma_p2p
    _det_sim_cfg = SimulationConfig(
        n_stars=10000, sigma_single=me_sig, sigma_measure=sigma_m,
        cadence_library=_cad_lib, cadence_weights=_cad_wt)
    _det_bin_cfg = BinaryParameterConfig(logP_max=_eff_logPmax)
    _det_gap = simulate_with_params(
        me_fb, me_x, _det_sim_cfg, _det_bin_cfg,
        np.random.default_rng(42))
    gap_drv = np.asarray(_det_gap['delta_rv'])
    gap_is_bin = np.asarray(_det_gap['is_binary'], dtype=bool)
    sigma_p2p = np.asarray(_det_gap.get('sigma_p2p', np.zeros(len(gap_drv))))
    n_sim = len(gap_drv)
    thresh_arr = np.linspace(0, float(np.max(gap_drv) * 1.05), 200)
    # Significance mask: ΔRV - nsigma * σ_p2p > 0
    if sigma_p2p is not None:
        sig_mask = (gap_drv - _nsigma * sigma_p2p) > 0
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
    intrinsic_fbin = float(gap_is_bin.mean())
    _idx_bin = np.where(gap_is_bin)[0]
    _bin_drv = gap_drv[_idx_bin]
    _bin_sigma = sigma_p2p[_idx_bin]
    _bin_det = (_bin_drv > thresh_dRV) & ((_bin_drv - _nsigma * _bin_sigma) > 0)
    total_bin = int(gap_is_bin.sum())
    detected_bin_count = int(_bin_det.sum())
    missed_count = total_bin - detected_bin_count
    observed_fbin = float(np.sum((gap_drv > thresh_dRV) & sig_mask)) / n_sim

    fig_det = go.Figure()
    fig_det.add_trace(go.Scatter(
        x=thresh_arr, y=missed_bin_curve,
        fill='tozeroy', fillcolor='rgba(242,166,35,0.25)',
        line=dict(width=0), mode='lines', name='Missed binaries', showlegend=True))
    if np.any(false_pos_curve > 0):
        fig_det.add_trace(go.Scatter(
            x=thresh_arr, y=false_pos_curve,
            fill='tozeroy', fillcolor='rgba(74,144,217,0.25)',
            line=dict(width=0), mode='lines', name='Singles above threshold', showlegend=True))
    fig_det.add_trace(go.Scatter(
        x=thresh_arr, y=fbin_curve, mode='lines',
        name='Simulated f_bin(threshold)', line=dict(color=_CLR_OBS, width=2.5)))
    # Real observed binary fraction curve (step/stairs)
    # Bartzakos correction: 3 confirmed binaries excluded from sample → +3 numerator, /28 denominator
    if obs_drv is not None and len(obs_drv) > 0:
        _obs_drv_s = np.sort(np.asarray(obs_drv))
        _n_bartz = 3
        _total_pop = len(_obs_drv_s) + _n_bartz
        _obs_sig_floor = _nsigma * float(sigma_p2p[0]) if len(sigma_p2p) > 0 else 0.0
        _obs_fbin_curve = np.array(
            [float(np.sum((_obs_drv_s > t) & (_obs_drv_s > _obs_sig_floor)) + _n_bartz) / _total_pop
             for t in _obs_drv_s])
        fig_det.add_trace(go.Scatter(
            x=_obs_drv_s, y=_obs_fbin_curve, mode='lines',
            name='Observed f_bin(threshold)',
            line=dict(color='white', width=2.5, shape='hv')))
    fig_det.add_hline(y=intrinsic_fbin, line_dash='dot', line_color=_CLR_DETECTED,
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
        fig_det.add_vline(x=_real_thresh, line_dash='dot', line_color='#00CC66',
                          line_width=2, annotation_text=f'Real threshold \u2248 {_real_thresh:.0f} km/s',
                          annotation_position='bottom right',
                          annotation_font=dict(size=10, color='#00CC66'))
    fig_det.add_vline(x=thresh_dRV, line_dash='dash', line_color=_CLR_MISSED,
                      line_width=2, annotation_text=f'Threshold = {thresh_dRV} km/s',
                      annotation_position='top right',
                      annotation_font=dict(size=11, color=_CLR_MISSED))
    fig_det.add_trace(go.Scatter(
        x=[thresh_dRV], y=[observed_fbin], mode='markers+text',
        marker=dict(size=14, color='white', symbol='diamond',
                    line=dict(width=2, color='black')),
        text=[f'{observed_fbin:.1%}'], textposition='top left',
        textfont=dict(size=12, color='#333333'),
        name=f'Simulated @ {thresh_dRV} km/s', showlegend=True))
    gap_pct = intrinsic_fbin - observed_fbin
    fig_det.add_annotation(
        x=thresh_dRV + 15, y=(intrinsic_fbin + observed_fbin) / 2,
        text=f'Gap: {gap_pct:.1%}<br>({missed_count} missed / {total_bin} binaries)',
        showarrow=False, font=dict(size=11, color=_CLR_MISSED),
        bgcolor=_pal['annotation_bg'], bordercolor=_CLR_MISSED,
        borderwidth=1, borderpad=4)
    fig_det.add_annotation(
        x=thresh_dRV, y=intrinsic_fbin, ax=thresh_dRV, ay=observed_fbin,
        xref='x', yref='y', axref='x', ayref='y',
        showarrow=True, arrowhead=3, arrowwidth=2, arrowcolor=_CLR_MISSED)
    # Best-fit overlay (same pattern as CDF)
    if _show_bestfit and info is not None:
        _bf_bv2 = info.get('best_vals', {})
        _bf_fb2 = float(_bf_bv2.get('fbin', 0.5))
        _bf_x2 = float(_bf_bv2.get(x_name, 0.0))
        _bf_sig2 = float(_bf_bv2.get('sigma', me_sig))
        _bf_lp2 = float(_bf_bv2.get('logPmax', _eff_logPmax))
        _bf_sim2 = SimulationConfig(
            n_stars=10000, sigma_single=_bf_sig2,
            sigma_measure=sigma_m,
            cadence_library=_cad_lib, cadence_weights=_cad_wt)
        _bf_bcfg2 = BinaryParameterConfig(logP_max=_bf_lp2)
        _bf_gap2 = simulate_with_params(
            _bf_fb2, _bf_x2, _bf_sim2, _bf_bcfg2,
            np.random.default_rng(42))
        _bf_drv2 = np.asarray(_bf_gap2['delta_rv'])
        _bf_sp2 = np.asarray(_bf_gap2.get('sigma_p2p', np.zeros(len(_bf_drv2))))
        _bf_n2 = len(_bf_drv2)
        _bf_sig_m2 = (_bf_drv2 - _nsigma * _bf_sp2) > 0
        _bf_fbin_c2 = np.array([float(np.sum((_bf_drv2 > t) & _bf_sig_m2)) / _bf_n2
                                for t in thresh_arr])
        fig_det.add_trace(go.Scatter(
            x=thresh_arr, y=_bf_fbin_c2, mode='lines',
            name='Best-fit (algorithm)',
            line=dict(color=_CLR_DETECTED, width=2, dash='dot')))
    fig_det.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(text='Binary Fraction vs \u0394RV Threshold', font=dict(size=14)),
        'xaxis_title': '\u0394RV threshold (km/s)', 'yaxis_title': 'Fraction of sample',
        'height': 400, 'margin': dict(l=60, r=80, t=50, b=50),
        'showlegend': True, 'legend': dict(x=0.55, y=0.95, font=dict(size=10)),
        'yaxis': dict(range=[0, min(1.0, intrinsic_fbin * 1.5)]),
    })
    # User authorised 2026-04-28: A&A theme override applied inside WORKING block
    # (D17j Binary Fraction vs Threshold).  Note: deferred white traces
    # (observed-fbin curve, diamond marker) intentionally NOT touched.
    try:
        from bc.render_validation import _AA_OVERRIDES
        fig_det.update_layout(**_AA_OVERRIDES)
        fig_det.update_xaxes(**_AA_OVERRIDES['xaxis'])
        # Preserve the existing yaxis range while adding A&A styling
        _aa_y = dict(_AA_OVERRIDES['yaxis'])
        _aa_y['range'] = [0, min(1.0, intrinsic_fbin * 1.5)]
        fig_det.update_yaxes(**_aa_y)
    except Exception:
        pass
    st.plotly_chart(fig_det, use_container_width=True,
                    key=f'{prefix}_lk_me_det')
    st.caption(
        f'Binary fraction as a function of \u0394RV threshold (Explorer). '
        f'Blue curve = fraction classified as binary. Dashed red line = '
        f'intrinsic f_bin = {intrinsic_fbin:.1%}. At threshold '
        f'({thresh_dRV} km/s), observed fraction = '
        f'{observed_fbin:.1%} \u2014 gap of {gap_pct:.1%} due to '
        f'{missed_count} undetectable binaries. '
        f'Amber = missed binaries; blue = singles above threshold.')

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
        # Round-5 (2026-04-28): also pass the MARGINAL-best param tuple
        # so the sanity-check overlays a second (purple) draw set.
        # ``info['hdi'][name]`` is (mode, lo, hi) where mode IS the marginal
        # max (peak of the 1-D marginal posterior).
        _hdi_dict = info.get('hdi', {}) if info is not None else {}
        def _marg_or(default, name):
            t = _hdi_dict.get(name)
            try:
                m = float(t[0]) if t is not None else float('nan')
            except (TypeError, ValueError, IndexError):
                m = float('nan')
            return m if np.isfinite(m) else default
        _grid_fb = float(_bv.get('fbin', 0.5))
        _grid_x = float(_bv.get(x_name, 0.0))
        _grid_sig = float(_bv.get('sigma',
                                  float(result.get('sigma_meas', 5.0))))
        _marg_dict = {
            'f_bin': _marg_or(_grid_fb, 'fbin'),
            x_name: _marg_or(_grid_x, x_name),
            'sigma': _marg_or(_grid_sig, 'sigma'),
        }
        # Bug 1e fix (2026-04-28): translate the runner-mode tag into the
        # actual `period_model` string accepted by `sample_logP`
        # (powerlaw / langer2020).  Previously this passed 'dsilva' /
        # 'langer' which raised "Unknown period_model" inside the mock
        # sampler.  Mirror the translation in render_validation.py:57.
        _stored_pm = str(result.get('period_model', 'powerlaw')).lower()
        if _stored_pm in ('langer', 'langer2020'):
            _pm = 'langer2020'
        else:
            _pm = 'powerlaw'
        try:
            _render_lk_cdf_sanity_check(
                _grid_fb, _grid_x, _grid_sig,
                np.asarray(obs_delta_rv), _pm, result,
                f'{p}_{method_key}', page_prefix=p,
                marg_params=_marg_dict, x_name=x_name)
        except Exception as _sanity_err:
            # Phase-6 debug (2026-04-28): surface sanity-check failures so
            # downstream "missing graph" reports have a visible cause.
            st.warning(f'CDF sanity check failed: {_sanity_err}')
