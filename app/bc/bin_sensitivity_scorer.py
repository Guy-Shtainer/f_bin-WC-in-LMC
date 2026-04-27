"""bc.bin_sensitivity_scorer — Re-scoring engine for the Bin-Sensitivity sub-tab.

Loads a cadence-Dsilva .npz result, re-simulates every grid cell using the ORIGINAL
seed formula (matching ``app/bc/runners_cadence.py:82-92`` — the source of truth),
then re-scores every cell under one or more ΔRV-bin schemes and returns a frozen
:class:`SchemeResult` dataclass that every plot in ``bin_sensitivity_plots.py`` reads.

Backward compatibility (learnings.md E048): if the .npz lacks ``bin_cfg`` /
``cadence_library`` / ``period_model`` / ``cadence_weights`` / ``sigma_meas``, we fall
back to :class:`BinaryParameterConfig` defaults (reconstructed from the ``settings``
JSON when available), ``period_model='powerlaw'``, ``cadence_weights=None``, and
``seed_base=1234``. The caller surfaces one ``st.info()`` about the legacy fallback.
"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import sys
import traceback as _tb
from dataclasses import dataclass, field
from typing import Optional, Callable

import numpy as np
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bc.bin_schemes import scheme_label as _scheme_label
# NOTE: wr_bias_simulation imports are deferred inside functions to avoid
# importing heavy modules at Streamlit page startup.


# Default bin-edge array for the simulation's internal ΔRV CDF (not the likelihood bins).
_DEFAULT_SIM_BIN_EDGES: np.ndarray = np.arange(0.0, 360.0, 10.0)

# Seed formula mirrored from runners_cadence.py (source of truth — read-only).
_SEED_BASE: int = 1234


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass — the single schema every plot reads
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SchemeResult:
    """Frozen per-scheme result. Every plot function reads only from this object."""
    scheme: str                     # e.g. "equal_width_10"
    family: str                     # e.g. "equal_width"
    edges: np.ndarray               # bin edges (n_bins+1,)
    n_bins: int
    n_eff_bins: int                 # non-empty bins in observed
    best_fbin: float
    best_pi: float
    hdi68_fbin: tuple               # (lo, hi)
    hdi68_pi: tuple                 # (lo, hi)
    logL_max: float                 # raw logL at best cell (within-scheme only)
    aic: float                      # 2*n_eff_bins - 2*logL_max
    ks_D: float                     # K-S statistic at best cell vs obs CDF
    ks_p: float
    logL_map: np.ndarray            # (n_fb, n_pi) marginalized over sigma
    marginal_fbin: np.ndarray
    marginal_pi: np.ndarray
    sim_cdf_median: np.ndarray      # at best cell
    sim_cdf_q16: np.ndarray
    sim_cdf_q84: np.ndarray
    cdf_x: np.ndarray               # shared ΔRV grid for sim_cdf arrays
    n_obs_per_bin: np.ndarray
    n_sim_per_bin: np.ndarray       # at best cell, pooled
    status: str                     # "OK" / "WARN" / "FAIL"
    status_reasons: tuple = field(default_factory=tuple)
    # Mock-mode-only: {'f_bin', 'pi', 'sigma', 'logPmax'} when the caller
    # injects synthetic observations. ``None`` in real-obs mode.
    ground_truth: Optional[dict] = None


# ─────────────────────────────────────────────────────────────────────────────
# .npz loading & config reconstruction
# ─────────────────────────────────────────────────────────────────────────────

def _unwrap(v):
    """Unwrap a 0-D object ndarray to its Python value."""
    if isinstance(v, np.ndarray) and v.dtype == object and v.ndim == 0:
        return v.item()
    return v


def load_npz_context(npz_path: str) -> dict:
    """Load the minimal context from a .npz needed to re-simulate the grid.

    Returns a dict with keys:
      fbin_grid, pi_grid, sigma_grid, logPmax_grid (may be length-1),
      n_sets, obs_delta_rv, logL_raw,
      bin_cfg_dict, cadence_library, cadence_weights, period_model,
      sigma_meas, sim_bin_edges, likelihood_bin_edges (original),
      is_legacy (bool — True when bin_cfg is not persisted).
    """
    d = dict(np.load(npz_path, allow_pickle=True))
    fbin_grid = np.asarray(d['fbin_grid'], dtype=float)
    pi_grid = np.asarray(d['pi_grid'], dtype=float)
    sigma_grid = np.asarray(d['sigma_grid'], dtype=float)
    logPmax_grid = np.asarray(d.get('logPmax_grid', np.array([5.0])), dtype=float)
    obs_delta_rv = np.asarray(d['obs_delta_rv'], dtype=float)
    logL_raw = np.asarray(d['logL_raw'], dtype=float)
    n_sets = int(_unwrap(d.get('n_sets', 1000)))

    sim_bin_edges = np.asarray(d.get('bin_edges', _DEFAULT_SIM_BIN_EDGES), dtype=float)
    _lbe = d.get('likelihood_bin_edges')
    if _lbe is not None:
        try:
            likelihood_bin_edges = np.asarray(_unwrap(_lbe), dtype=float)
        except Exception:
            likelihood_bin_edges = None
    else:
        likelihood_bin_edges = None

    # Orbital config
    _bin_cfg_raw = _unwrap(d.get('bin_cfg'))
    is_legacy = _bin_cfg_raw is None or not isinstance(_bin_cfg_raw, dict)
    if is_legacy:
        bin_cfg_dict = _bin_cfg_from_settings_json(_unwrap(d.get('settings')))
    else:
        bin_cfg_dict = dict(_bin_cfg_raw)

    period_model = _unwrap(d.get('period_model'))
    if period_model is None:
        # Legacy: read from settings JSON if available
        _s = _unwrap(d.get('settings'))
        try:
            period_model = json.loads(str(_s)).get('period_model', 'powerlaw')
        except Exception:
            period_model = 'powerlaw'

    _cw = d.get('cadence_weights')
    if _cw is not None:
        _cw = _unwrap(_cw)
        if _cw is None or (isinstance(_cw, np.ndarray) and _cw.size == 0):
            cadence_weights = None
        else:
            cadence_weights = np.asarray(_cw, dtype=float)
    else:
        cadence_weights = None

    _cl = d.get('cadence_library')
    if _cl is not None:
        _cl = _unwrap(_cl)
        if _cl is None:
            cadence_library = None
        else:
            try:
                cadence_library = [np.asarray(x, dtype=float) for x in _cl]
            except Exception:
                cadence_library = None
    else:
        cadence_library = None

    _sm = _unwrap(d.get('sigma_meas'))
    if _sm is None:
        try:
            _sm = json.loads(str(_unwrap(d.get('settings')))).get('sigma_measure', 1.5)
        except Exception:
            _sm = 1.5
    sigma_meas = float(_sm)

    return {
        'fbin_grid': fbin_grid,
        'pi_grid': pi_grid,
        'sigma_grid': sigma_grid,
        'logPmax_grid': logPmax_grid,
        'obs_delta_rv': obs_delta_rv,
        'logL_raw': logL_raw,
        'n_sets': n_sets,
        'sim_bin_edges': sim_bin_edges,
        'likelihood_bin_edges': likelihood_bin_edges,
        'bin_cfg_dict': bin_cfg_dict,
        'period_model': str(period_model),
        'cadence_weights': cadence_weights,
        'cadence_library': cadence_library,
        'sigma_meas': sigma_meas,
        'is_legacy': is_legacy,
    }


def _bin_cfg_from_settings_json(settings_str) -> dict:
    """Reconstruct a BinaryParameterConfig-compatible dict from the 'settings' JSON."""
    out: dict = {}
    try:
        s = json.loads(str(settings_str))
    except Exception:
        return out
    # Map settings keys to BinaryParameterConfig kwargs
    if 'logP_min' in s:
        out['logP_min'] = float(s['logP_min'])
    if 'logP_max' in s:
        out['logP_max'] = float(s['logP_max'])
    out['period_model'] = s.get('period_model', 'powerlaw')
    out['e_model'] = s.get('e_model', 'flat')
    if 'e_max' in s:
        out['e_max'] = float(s['e_max'])
    out['mass_primary_model'] = s.get('mass_primary_model', 'fixed')
    if 'mass_primary_fixed' in s:
        out['mass_primary_fixed'] = float(s['mass_primary_fixed'])
    out['q_model'] = s.get('q_model', 'flat')
    if 'q_min' in s and 'q_max' in s:
        out['q_range'] = (float(s['q_min']), float(s['q_max']))
    if 'q_flipped' in s:
        out['q_flipped'] = bool(s['q_flipped'])
    return out


def _make_bin_cfg(bin_cfg_dict: dict, period_model: str, logP_max_override=None):
    """Materialize a BinaryParameterConfig from a stored dict + logP_max override."""
    from wr_bias_simulation import BinaryParameterConfig
    d = dict(bin_cfg_dict or {})
    if logP_max_override is not None:
        d['logP_max'] = float(logP_max_override)
    d.setdefault('period_model', period_model)
    # Strip any unknown keys that BinaryParameterConfig doesn't accept.
    allowed = {
        'logP_min', 'logP_max', 'period_model', 'langer_period_params',
        'e_model', 'e_max',
        'mass_primary_model', 'mass_primary_fixed', 'mass_primary_range',
        'q_model', 'q_range', 'langer_q_mu', 'langer_q_sigma', 'q_flipped',
    }
    d_clean = {k: v for k, v in d.items() if k in allowed}
    # q_range must be a tuple, not a list (BinaryParameterConfig dataclass field)
    if 'q_range' in d_clean and not isinstance(d_clean['q_range'], tuple):
        try:
            d_clean['q_range'] = tuple(d_clean['q_range'])
        except Exception:
            d_clean.pop('q_range')
    if 'mass_primary_range' in d_clean and not isinstance(d_clean['mass_primary_range'], tuple):
        try:
            d_clean['mass_primary_range'] = tuple(d_clean['mass_primary_range'])
        except Exception:
            d_clean.pop('mass_primary_range')
    return BinaryParameterConfig(**d_clean)


# ─────────────────────────────────────────────────────────────────────────────
# Per-cell re-simulation worker (module-level so mp.Pool can pickle it)
# ─────────────────────────────────────────────────────────────────────────────

def _resim_cell(args):
    """Re-simulate one (i_sig, i_fb, i_pi) cell and return its pooled ΔRV sample.

    args = (f_bin, pi_val, sigma_single, seed, n_sets, period_model,
            bin_cfg_dict, sim_bin_edges)
    """
    (f_bin, pi_val, sigma_single, seed, n_sets, period_model,
     bin_cfg_dict, sim_bin_edges) = args
    from wr_bias_simulation import (
        simulate_delta_rv_cadence_aware, SimulationConfig,
    )
    g = _WORKER_GLOBALS
    bin_cfg = _make_bin_cfg(bin_cfg_dict, period_model)
    sim_cfg = SimulationConfig(
        n_stars=len(g['cadence_library']),
        n_epochs=6, time_span=3650.0,
        sigma_single=float(sigma_single),
        sigma_measure=float(g['sigma_meas']),
        v_sys=0.0,
        observation_times=None,
        cadence_library=g['cadence_library'],
        cadence_weights=g['cadence_weights'],
    )
    rng = np.random.default_rng(int(seed))
    out = simulate_delta_rv_cadence_aware(
        f_bin=float(f_bin), pi=float(pi_val),
        sim_cfg=sim_cfg, bin_cfg=bin_cfg, rng=rng,
        n_sets=int(n_sets),
        bin_edges=sim_bin_edges,
    )
    # Pool ΔRV across all (n_sets × n_stars) draws.
    return out['all_delta_rv'].ravel()


# Shared between worker processes (populated by _init_resim_worker).
_WORKER_GLOBALS: dict = {}


def _init_resim_worker(cadence_library, cadence_weights, sigma_meas):
    global _WORKER_GLOBALS
    _WORKER_GLOBALS = dict(
        cadence_library=cadence_library,
        cadence_weights=cadence_weights,
        sigma_meas=float(sigma_meas),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Core re-scoring function — cached per (npz_path, edges_tuple)
# ─────────────────────────────────────────────────────────────────────────────

def _logL_one_scheme(obs: np.ndarray, pool: np.ndarray, edges: np.ndarray) -> float:
    """Binned multinomial logL (matches wr_bias_simulation.multinomial_log_likelihood)."""
    n_obs = np.histogram(obs, bins=edges)[0]
    n_sim = np.histogram(pool, bins=edges)[0]
    total_sim = max(int(n_sim.sum()), 1)
    p_bins = n_sim.astype(float) / total_sim
    eps = 1.0 / max(pool.size, 1)
    p_bins = np.maximum(p_bins, eps)
    return float(np.sum(n_obs * np.log(p_bins)))


def _ks_stat(obs: np.ndarray, pool: np.ndarray) -> tuple[float, float]:
    """Scipy K-S statistic; safe fallback if scipy missing."""
    try:
        from scipy.stats import ks_2samp
        res = ks_2samp(obs, pool)
        return float(res.statistic), float(res.pvalue)
    except Exception:
        # Manual K-S
        x = np.sort(np.concatenate([obs, pool]))
        cdf_o = np.searchsorted(np.sort(obs), x, side='right') / obs.size
        cdf_s = np.searchsorted(np.sort(pool), x, side='right') / max(pool.size, 1)
        return float(np.max(np.abs(cdf_o - cdf_s))), float('nan')


def _hdi68_safe(x_vals: np.ndarray, posterior_1d: np.ndarray) -> tuple[float, float, float]:
    """Compute 68% HDI. Returns (mode, lo, hi). Safe on degenerate posteriors."""
    from wr_bias_simulation import compute_hdi68
    x = np.asarray(x_vals, dtype=float)
    p = np.asarray(posterior_1d, dtype=float)
    if not np.any(np.isfinite(p)) or p.sum() <= 0:
        return float(x[0]), float(x[0]), float(x[-1])
    try:
        return compute_hdi68(x, p)
    except Exception:
        return float(x[np.argmax(p)]), float(x[0]), float(x[-1])


def rescore_scheme(
    npz_path: str,
    family: str,
    n_bins: int,
    edges: np.ndarray,
    ctx: Optional[dict] = None,
    progress_cb: Optional[Callable[[int, int, str], None]] = None,
    n_proc: Optional[int] = None,
    scheme_name: Optional[str] = None,
    obs_override: Optional[np.ndarray] = None,
    ground_truth: Optional[dict] = None,
) -> SchemeResult:
    """Re-score a single scheme against the cached ΔRV pools of a saved .npz.

    If *ctx* is None we call :func:`load_npz_context` for it. A progress callback
    receives ``(completed_cells, total_cells, label)`` updates.

    When ``scheme_name`` is provided it overrides the auto-generated
    ``_scheme_label(family, n_bins)`` label — used by the manual scheme-list
    UI so that user-provided names (e.g. "shifted") surface verbatim in plots
    and the summary table.

    NOTE: This function is cache-wrapped by :func:`rescore_scheme_cached` below —
    which is what renderers should call.
    """
    ctx = ctx or load_npz_context(npz_path)
    fbin_grid = ctx['fbin_grid']
    pi_grid = ctx['pi_grid']
    sigma_grid = ctx['sigma_grid']
    # Mock-mode override: when callers supply `obs_override`, use that synthetic
    # ΔRV sample in place of the .npz-loaded observed array. The scoring loop
    # (histogram + multinomial logL) is identical — only the target array changes.
    obs = (np.asarray(obs_override, dtype=float)
           if obs_override is not None else ctx['obs_delta_rv'])
    n_sets = int(ctx['n_sets'])
    period_model = str(ctx['period_model'])
    bin_cfg_dict = dict(ctx['bin_cfg_dict'])
    cad_lib = ctx['cadence_library']
    cad_wts = ctx['cadence_weights']
    sigma_meas = float(ctx['sigma_meas'])
    sim_bin_edges = ctx['sim_bin_edges']

    if cad_lib is None:
        # Legacy .npz lacks cadence_library — fall back to the live loader.
        from shared import cached_load_cadence, settings_hash, get_settings_manager
        _sh = settings_hash(get_settings_manager().load())
        cad_lib, _cw_default = cached_load_cadence(_sh)
        if cad_wts is None:
            cad_wts = _cw_default

    n_fb = int(fbin_grid.size)
    n_pi = int(pi_grid.size)

    edges_arr = np.asarray(edges, dtype=float)
    scheme_name = str(scheme_name) if scheme_name else _scheme_label(family, n_bins)

    # Build task list with the ORIGINAL seed formula: base=1234, order (sigma, fb, pi).
    # Matches app/bc/runners_cadence.py:82-92. i_lp is 0 when no logPmax scan was done
    # for the scheme-sensitivity re-scoring (we collapse the logP dimension to its
    # maximum-likelihood slice — same convention as the main tab's marginals).
    tasks = []
    i = 0
    for i_sig, sigma in enumerate(sigma_grid):
        for i_fb, fb in enumerate(fbin_grid):
            for i_pi, pi_val in enumerate(pi_grid):
                tasks.append((
                    float(fb), float(pi_val), float(sigma),
                    int(_SEED_BASE + i),
                    int(n_sets),
                    period_model,
                    bin_cfg_dict,
                    sim_bin_edges,
                    i_sig, i_fb, i_pi,  # indices for storage (stripped before MP)
                ))
                i += 1

    # Collapse sigma dimension: pick the best sigma by original logL_raw first so
    # that re-sim only has to scan (n_fb × n_pi). This matches the runner's
    # "best cell" behaviour — the σ dimension in the original grid is nuisance-
    # marginalised, and for a binning sensitivity we compare the (f_bin, π) surface.
    logL_raw = ctx['logL_raw']
    if logL_raw.ndim == 4:
        # (logPmax, sigma, fb, pi) → max over logPmax, then pick best sigma slice
        _l3 = np.nanmax(logL_raw, axis=0)
    else:
        _l3 = logL_raw
    # Use the sigma slice with the highest original likelihood maximum.
    if _l3.ndim == 3:
        _lmax_per_sig = np.nanmax(_l3, axis=(1, 2))
        if np.any(np.isfinite(_lmax_per_sig)):
            best_sig_idx = int(np.nanargmax(_lmax_per_sig))
        else:
            best_sig_idx = 0
    else:
        # 2D (n_fb, n_pi) — single sigma
        best_sig_idx = 0

    # Filter tasks to only the best_sig_idx slice to bound computation.
    tasks_slice = [t for t in tasks if t[8] == best_sig_idx]
    total_work = len(tasks_slice)

    # Strip storage indices before sending to the pool
    mp_tasks = [t[:8] for t in tasks_slice]

    # Parallel re-simulation
    logL_map = np.full((n_fb, n_pi), np.nan, dtype=float)
    best = {
        'logL': -np.inf, 'i_fb': 0, 'i_pi': 0,
        'pool': None,
    }

    use_mp = bool(n_proc is None or int(n_proc) > 1)
    if use_mp:
        _np = max(1, (os.cpu_count() or 2) - 1) if n_proc is None else int(n_proc)
    else:
        _np = 1

    def _handle(pool_arr, t):
        logL_val = _logL_one_scheme(obs, pool_arr, edges_arr)
        _i_fb = t[9]
        _i_pi = t[10]
        logL_map[_i_fb, _i_pi] = logL_val
        if logL_val > best['logL']:
            best['logL'] = logL_val
            best['i_fb'] = _i_fb
            best['i_pi'] = _i_pi
            best['pool'] = pool_arr

    completed = 0
    if _np > 1 and total_work > 1:
        with mp.Pool(
            processes=_np,
            initializer=_init_resim_worker,
            initargs=(cad_lib, cad_wts, sigma_meas),
        ) as pool:
            results_iter = pool.imap(
                _resim_cell,
                mp_tasks,
                chunksize=max(1, total_work // (_np * 8) or 1),
            )
            for tsk, pool_arr in zip(tasks_slice, results_iter):
                _handle(pool_arr, tsk)
                completed += 1
                if progress_cb is not None and (completed % 25 == 0 or completed == total_work):
                    try:
                        progress_cb(completed, total_work, scheme_name)
                    except Exception:
                        pass
    else:
        # Serial path — inline init
        _init_resim_worker(cad_lib, cad_wts, sigma_meas)
        for tsk in tasks_slice:
            pool_arr = _resim_cell(tsk[:8])
            _handle(pool_arr, tsk)
            completed += 1
            if progress_cb is not None and (completed % 25 == 0 or completed == total_work):
                try:
                    progress_cb(completed, total_work, scheme_name)
                except Exception:
                    pass

    # Best cell
    best_i_fb = int(best['i_fb'])
    best_i_pi = int(best['i_pi'])
    best_pool = best['pool'] if best['pool'] is not None else np.zeros(1)
    best_logL = float(best['logL']) if np.isfinite(best['logL']) else float(np.nanmax(logL_map))
    best_fbin = float(fbin_grid[best_i_fb])
    best_pi = float(pi_grid[best_i_pi])

    # Marginals (softmax in logL space → unit-area posterior in x)
    _L_for_post = np.where(np.isnan(logL_map), -np.inf, logL_map)
    _L_max = np.nanmax(_L_for_post) if np.any(np.isfinite(_L_for_post)) else 0.0
    lk = np.exp(_L_for_post - _L_max) if np.isfinite(_L_max) else np.zeros_like(logL_map)
    marg_fbin = np.sum(lk, axis=1)
    marg_pi = np.sum(lk, axis=0)
    # Normalise to unit area (trapezoid)
    _a_fb = float(np.trapezoid(marg_fbin, fbin_grid)) if marg_fbin.sum() > 0 else 0.0
    _a_pi = float(np.trapezoid(marg_pi, pi_grid)) if marg_pi.sum() > 0 else 0.0
    if _a_fb > 0:
        marg_fbin = marg_fbin / _a_fb
    if _a_pi > 0:
        marg_pi = marg_pi / _a_pi

    # HDI68
    _m_fb, lo_fb, hi_fb = _hdi68_safe(fbin_grid, marg_fbin)
    _m_pi, lo_pi, hi_pi = _hdi68_safe(pi_grid, marg_pi)

    # K-S at best cell (bin-free cross-check)
    ks_D, ks_p = _ks_stat(obs, best_pool)

    # Observed & simulated bin counts at best cell
    n_obs_per_bin = np.histogram(obs, bins=edges_arr)[0].astype(int)
    n_sim_per_bin = np.histogram(best_pool, bins=edges_arr)[0].astype(int)
    n_eff_bins = int(np.sum(n_obs_per_bin > 0))
    n_bins_total = int(max(edges_arr.size - 1, 1))

    # Simulated CDF envelope at best cell — pooled over n_sets (median ± 1σ)
    _n_stars_per_set = int(len(cad_lib)) if cad_lib is not None else int(obs.size)
    cdf_x = sim_bin_edges
    sim_cdf_median, sim_cdf_q16, sim_cdf_q84 = _cdf_percentiles_from_pool(
        best_pool, n_stars_per_set=_n_stars_per_set, bin_edges=sim_bin_edges,
    )

    # AIC — cross-scheme-comparable metric. Uses n_eff_bins per scientist.md #4.
    aic = float(2.0 * n_eff_bins - 2.0 * best_logL)

    # Pitfall detection (see briefing §Pitfall flagging, memory §4)
    status, reasons = _detect_pitfalls(
        n_obs_per_bin=n_obs_per_bin,
        n_sim_per_bin=n_sim_per_bin,
        edges=edges_arr,
        max_obs=float(obs.max() if obs.size > 0 else 0.0),
        best_pool_size=int(best_pool.size),
        logL_max=best_logL,
    )

    return SchemeResult(
        scheme=scheme_name,
        family=family,
        edges=edges_arr,
        n_bins=n_bins_total,
        n_eff_bins=n_eff_bins,
        best_fbin=best_fbin,
        best_pi=best_pi,
        hdi68_fbin=(float(lo_fb), float(hi_fb)),
        hdi68_pi=(float(lo_pi), float(hi_pi)),
        logL_max=best_logL,
        aic=aic,
        ks_D=float(ks_D),
        ks_p=float(ks_p),
        logL_map=logL_map.astype(float),
        marginal_fbin=marg_fbin.astype(float),
        marginal_pi=marg_pi.astype(float),
        sim_cdf_median=sim_cdf_median,
        sim_cdf_q16=sim_cdf_q16,
        sim_cdf_q84=sim_cdf_q84,
        cdf_x=cdf_x,
        n_obs_per_bin=n_obs_per_bin,
        n_sim_per_bin=n_sim_per_bin,
        status=status,
        status_reasons=tuple(reasons),
        ground_truth=(dict(ground_truth) if ground_truth is not None else None),
    )


def _cdf_percentiles_from_pool(
    pool: np.ndarray,
    n_stars_per_set: int,
    bin_edges: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Reconstruct the (median, q16, q84) CDF envelope from a pooled ΔRV sample.

    Assumes ``pool`` is shaped as ``(n_sets × n_stars_per_set)`` rows pooled
    into a 1-D array. We reshape back into rows, build each set's CDF on the
    *same* ``bin_edges`` grid used by the original grid run, and take
    percentiles across sets.
    """
    if n_stars_per_set <= 0 or pool.size < n_stars_per_set:
        cdf = np.searchsorted(np.sort(pool), bin_edges, side='right') / max(pool.size, 1)
        return cdf.astype(float), cdf.astype(float), cdf.astype(float)
    n_sets = int(pool.size // n_stars_per_set)
    grid = pool[: n_sets * n_stars_per_set].reshape(n_sets, n_stars_per_set)
    cdfs = np.empty((n_sets, bin_edges.size), dtype=float)
    for s in range(n_sets):
        row = np.sort(grid[s])
        cdfs[s] = np.searchsorted(row, bin_edges, side='right') / float(n_stars_per_set)
    return (
        np.median(cdfs, axis=0),
        np.percentile(cdfs, 16, axis=0),
        np.percentile(cdfs, 84, axis=0),
    )


def _detect_pitfalls(
    n_obs_per_bin: np.ndarray,
    n_sim_per_bin: np.ndarray,
    edges: np.ndarray,
    max_obs: float,
    best_pool_size: int,
    logL_max: float,
) -> tuple[str, list[str]]:
    """Detect pitfalls P1-P5 (see briefing §Pitfall flagging, memory §4).

    Returns (status_code, reasons). Status is 'FAIL' > 'WARN' > 'OK'.
    """
    reasons: list[str] = []
    worst = 'OK'

    n_bins = int(n_obs_per_bin.size)
    n_empty = int(np.sum(n_obs_per_bin == 0))
    n_nonempty = int(n_bins - n_empty)

    # P1: >50% of bins empty in observed
    if n_bins > 0 and (n_empty / n_bins) > 0.5:
        reasons.append('P1')
        worst = 'WARN'

    # P2: any bin above max_obs (wasted bin)
    if edges.size >= 2 and np.any(edges[:-1] > max_obs):
        reasons.append('P2')
        if worst == 'OK':
            worst = 'WARN'

    # P3: ε-floor limited — the "smallest p_i" is at floor
    eps = 1.0 / max(best_pool_size, 1)
    # If any n_obs>0 bin has n_sim==0, its p_i is at the ε floor; if that bin
    # dominates logL (|n_obs * ln(eps)| near |logL_max|), flag FAIL.
    if n_empty < n_bins and eps > 0:
        floor_contrib = -np.sum(
            np.where((n_sim_per_bin == 0) & (n_obs_per_bin > 0),
                     n_obs_per_bin, 0)
        ) * np.log(eps)
        if abs(logL_max) > 0 and floor_contrib > 0:
            # If floor accounts for >90% of |logL|, scheme is floor-limited
            if floor_contrib > 0.9 * abs(logL_max):
                reasons.append('P3')
                worst = 'FAIL'

    # P4: HDI68 width edge-flip sensitivity — we need a perturbation scan; skip here
    # (it is a per-scheme meta-diagnostic; deferring to a future sub-pass).
    # NOTE: left un-implemented in this file; not blocking.

    # P5: small-N multinomial (n_obs ∈ {1}) in >50% of non-empty bins
    if n_nonempty > 0:
        small = int(np.sum((n_obs_per_bin > 0) & (n_obs_per_bin < 2)))
        if (small / n_nonempty) > 0.5:
            reasons.append('P5')
            if worst == 'OK':
                worst = 'WARN'

    return worst, reasons


# ─────────────────────────────────────────────────────────────────────────────
# Streamlit cache wrapper
# ─────────────────────────────────────────────────────────────────────────────

# NOTE: Not called from the bg thread — Streamlit cache is not thread-safe
# without a ScriptRunContext. The bg runner uses `rescore_scheme` directly.
@st.cache_data(show_spinner=False)
def rescore_scheme_cached(
    npz_path: str,
    family: str,
    n_bins: int,
    edges_tuple: tuple,
    scheme_name: Optional[str] = None,
    _progress_cb: Optional[Callable] = None,
    _n_proc: Optional[int] = None,
) -> SchemeResult:
    """Streamlit-cached wrapper around :func:`rescore_scheme`.

    Cache key = (npz_path, family, n_bins, edges_tuple, scheme_name). The
    ``scheme_name`` override is included in the cache key so two manual
    schemes with identical edges but different names don't collide.
    ``_progress_cb`` and ``_n_proc`` are excluded from the cache key via
    the underscore prefix.
    """
    edges = np.array(edges_tuple, dtype=float)
    return rescore_scheme(
        npz_path=npz_path,
        family=family,
        n_bins=int(n_bins),
        edges=edges,
        progress_cb=_progress_cb,
        n_proc=_n_proc,
        scheme_name=scheme_name,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Background runner — drives one scheme at a time through the pool
# ─────────────────────────────────────────────────────────────────────────────

def _run_all_schemes_bg(job: dict, params: dict) -> None:
    """Worker thread: iterates ``params['schemes']`` (list of (name, edges) pairs)
    and re-scores each one sequentially, streaming progress into ``job``.

    params keys:
      npz_path      : str
      schemes       : list[tuple[str, np.ndarray]]   (name, edges)
      n_proc        : int | None
      obs_override  : np.ndarray | None  — mock-mode synthetic observations
      ground_truth  : dict | None        — mock-mode truth params attached to every result
    """
    try:
        npz_path = params['npz_path']
        schemes = params['schemes']
        n_proc = params.get('n_proc')
        obs_override = params.get('obs_override')
        ground_truth = params.get('ground_truth')

        ctx = load_npz_context(npz_path)
        # When mock observations are supplied, the rug/summary should reflect
        # the synthetic sample — overwrite the ctx snapshot shown to the UI.
        _obs_for_ui = (np.asarray(obs_override, dtype=float)
                       if obs_override is not None else ctx['obs_delta_rv'])
        job['ctx'] = {
            'fbin_grid': ctx['fbin_grid'],
            'pi_grid': ctx['pi_grid'],
            'obs_delta_rv': _obs_for_ui,
            'is_legacy': bool(ctx['is_legacy']),
        }

        total = max(len(schemes), 1)
        results: dict[str, SchemeResult] = {}

        for i, (name, edges) in enumerate(schemes):
            if job.get('cancel'):
                job['status'] = 'cancelled'
                return
            edges_arr = np.asarray(edges, dtype=float)
            n_bins_int = int(max(edges_arr.size - 1, 1))

            def _cb(done: int, tot: int, label: str, _i=i, _t=total):
                job['progress_cell_done'] = int(done)
                job['progress_cell_total'] = int(tot)
                job['progress_scheme'] = label
                job['progress_pct'] = (_i + (done / max(tot, 1))) / _t

            try:
                if obs_override is not None:
                    # Mock mode bypasses the Streamlit cache — each run uses a
                    # fresh synthetic sample (seed can change) so caching by
                    # (npz_path, family, n_bins, edges) alone would collide.
                    r = rescore_scheme(
                        npz_path=npz_path,
                        family='manual',
                        n_bins=n_bins_int,
                        edges=edges_arr,
                        ctx=ctx,
                        progress_cb=_cb,
                        n_proc=n_proc,
                        scheme_name=str(name),
                        obs_override=obs_override,
                        ground_truth=ground_truth,
                    )
                else:
                    # Call rescore_scheme directly — @st.cache_data is not
                    # safe to invoke from a background thread (no
                    # ScriptRunContext → can deadlock on cache locks when
                    # writing the result at the end of the call). The auto-
                    # save layer (bin_sensitivity_storage.save_bin_sensitivity_run)
                    # plus the in-session job dict provide result persistence.
                    r = rescore_scheme(
                        npz_path=npz_path,
                        family='manual',
                        n_bins=n_bins_int,
                        edges=edges_arr,
                        ctx=ctx,
                        progress_cb=_cb,
                        n_proc=n_proc,
                        scheme_name=str(name),
                    )
                results[str(name)] = r
            except Exception as exc:
                job.setdefault('errors', []).append(
                    f'{name}: rescore failed: {exc}\n{_tb.format_exc()}')

            job['progress_pct'] = (i + 1) / total
            job['progress_scheme'] = str(name)
            job['results_snapshot'] = dict(results)

        job['results'] = results
        job['status'] = 'done'
    except Exception:
        job['status'] = 'error'
        job['error_trace'] = _tb.format_exc()
