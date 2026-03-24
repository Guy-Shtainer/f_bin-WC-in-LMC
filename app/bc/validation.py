"""bc.validation — Core logic for parameter-recovery validation.

Task #160: Single-point recovery — generate mock ΔRVs at known (true) parameters,
run the same grid search, check if the pipeline recovers the truth.

Task #161: Batch sweep — repeat the single-point test across a coarse grid of
true parameters to map where the pipeline is reliable vs unreliable.
"""
from __future__ import annotations

import multiprocessing as mp
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from wr_bias_simulation import (
    SimulationConfig,
    BinaryParameterConfig,
    simulate_delta_rv_cadence_aware,
    multinomial_log_likelihood,
    _single_grid_task_cadence_aware,
    _init_worker,
    DEFAULT_DRV_BIN_EDGES,
)


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ValidationPoint:
    """Result of a single-point recovery test."""
    true_fbin: float
    true_pi: float
    true_sigma: float
    true_logPmax: float
    rec_fbin: float
    rec_pi: float
    rec_sigma: float
    rec_logPmax: float
    recovery_score: float          # 0 = perfect, 1 = worst
    per_param: Dict[str, dict]     # {name: {true, recovered, distance, weight}}
    likelihood_grid: np.ndarray    # 2-D (fbin × x) likelihood slice at best outer
    fbin_grid: np.ndarray
    x_grid: np.ndarray             # pi (Dsilva) or sigma (Langer)
    mock_delta_rv: np.ndarray      # the mock observations used
    seed: int


@dataclass
class BatchResult:
    """Collection of single-point results for a sweep."""
    points: List[ValidationPoint] = field(default_factory=list)
    true_fbin_vals: np.ndarray = field(default_factory=lambda: np.array([]))
    true_pi_vals: np.ndarray = field(default_factory=lambda: np.array([]))
    true_sigma_vals: np.ndarray = field(default_factory=lambda: np.array([]))
    n_total: int = 0
    n_done: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Mock observation generation
# ─────────────────────────────────────────────────────────────────────────────

def generate_mock_observations(
    true_fbin: float,
    true_pi: float,
    true_sigma: float,
    true_logPmax: float,
    cadence_library: list,
    cadence_weights: Optional[np.ndarray],
    sigma_meas: float,
    bin_cfg: BinaryParameterConfig,
    period_model: str,
    seed: int = 42,
    n_sets: int = 1,
) -> np.ndarray:
    """Generate mock ΔRV observations at the given true parameters.

    Returns an array of shape (n_stars,) — one ΔRV per star, mimicking
    what the real observations look like.
    """
    rng = np.random.default_rng(seed)

    # Override bin_cfg with the true logP_max
    mock_cfg = BinaryParameterConfig(**vars(bin_cfg))
    mock_cfg.logP_max = true_logPmax
    mock_cfg.period_model = period_model

    sim_cfg = SimulationConfig(
        n_stars=len(cadence_library),
        sigma_single=true_sigma,
        sigma_measure=sigma_meas,
        cadence_library=cadence_library,
        cadence_weights=cadence_weights,
    )

    # Run one set of the cadence-aware simulation
    result = simulate_delta_rv_cadence_aware(
        f_bin=true_fbin,
        pi=true_pi,
        sim_cfg=sim_cfg,
        bin_cfg=mock_cfg,
        rng=rng,
        n_sets=n_sets,
    )

    # Take the first set's ΔRVs (shape = n_stars)
    all_drv = result['all_delta_rv']  # shape (n_sets, n_stars)
    if all_drv.ndim == 2:
        return all_drv[0]
    return all_drv.ravel()[:len(cadence_library)]


# ─────────────────────────────────────────────────────────────────────────────
# Grid search on mock data
# ─────────────────────────────────────────────────────────────────────────────

def run_validation_grid(
    mock_delta_rv: np.ndarray,
    fbin_vals: np.ndarray,
    pi_vals: np.ndarray,
    sigma_vals: np.ndarray,
    cadence_library: list,
    cadence_weights: Optional[np.ndarray],
    sigma_meas: float,
    bin_cfg: BinaryParameterConfig,
    period_model: str,
    n_sets: int = 500,
    likelihood_bin_edges: Optional[np.ndarray] = None,
    logPmax_val: float = 5.0,
    progress_callback=None,
) -> np.ndarray:
    """Run the likelihood grid search against mock observations.

    Returns likelihood array of shape (n_sigma, n_fbin, n_pi).
    """
    if likelihood_bin_edges is None:
        likelihood_bin_edges = DEFAULT_DRV_BIN_EDGES

    n_sig = len(sigma_vals)
    n_fb = len(fbin_vals)
    n_pi = len(pi_vals)

    # Build task list
    _cfg = BinaryParameterConfig(**vars(bin_cfg))
    _cfg.logP_max = logPmax_val
    _cfg.period_model = period_model

    tasks = []
    seed_base = 1234
    for i_s, sigma in enumerate(sigma_vals):
        for i_f, fb in enumerate(fbin_vals):
            for i_p, pi_val in enumerate(pi_vals):
                tasks.append((
                    fb, pi_val, sigma, _cfg, period_model,
                    seed_base + i_s * n_fb * n_pi + i_f * n_pi + i_p,
                    n_sets,
                ))

    # Initialize worker pool
    n_proc = max(1, (os.cpu_count() or 2) - 1)
    initargs = (
        cadence_library, cadence_weights, mock_delta_rv,
        len(cadence_library), float(sigma_meas),
        6, 3650.0, None, 0.0, None,
        n_sets,
        likelihood_bin_edges,
    )

    lk_arr = np.full((n_sig, n_fb, n_pi), np.nan)

    with mp.Pool(n_proc, initializer=_init_worker, initargs=initargs) as pool:
        total = len(tasks)
        for i, res in enumerate(pool.imap_unordered(
                _single_grid_task_cadence_aware, tasks)):
            fb, pi_val, sigma, logL, _, _, _ = res
            i_s = int(np.argmin(np.abs(sigma_vals - sigma)))
            i_f = int(np.argmin(np.abs(fbin_vals - fb)))
            i_p = int(np.argmin(np.abs(pi_vals - pi_val)))
            lk_arr[i_s, i_f, i_p] = logL
            if progress_callback and (i + 1) % max(1, total // 50) == 0:
                progress_callback((i + 1) / total)

    if progress_callback:
        progress_callback(1.0)

    return lk_arr


# ─────────────────────────────────────────────────────────────────────────────
# Recovery scoring
# ─────────────────────────────────────────────────────────────────────────────

def compute_recovery_score(
    true_params: Dict[str, float],
    rec_params: Dict[str, float],
    grid_sizes: Dict[str, int],
) -> Tuple[float, Dict[str, dict]]:
    """Compute weighted normalized distance between true and recovered params.

    For each parameter:
        distance_i = |recovered - true| / parameter_range
        weight_i   = grid_points_i / total_grid_points

    Overall score = Σ weight_i * distance_i  (0 = perfect, 1 = worst).

    Returns (overall_score, per_param_dict).
    """
    # Parameter ranges (physically meaningful)
    param_ranges = {
        'fbin':     (0.0, 1.0),
        'pi':       (-3.0, 3.0),
        'sigma':    (0.0, 50.0),
        'logPmax':  (0.0, 6.0),
    }

    per_param = {}
    total_weight = 0.0
    weighted_sum = 0.0

    for name in true_params:
        t = true_params[name]
        r = rec_params.get(name, t)
        lo, hi = param_ranges.get(name, (0.0, 1.0))
        rng = hi - lo if hi > lo else 1.0
        dist = abs(r - t) / rng
        weight = grid_sizes.get(name, 1)
        per_param[name] = {
            'true': t,
            'recovered': r,
            'abs_error': abs(r - t),
            'distance': dist,
            'weight': weight,
        }
        total_weight += weight
        weighted_sum += weight * dist

    overall = weighted_sum / max(total_weight, 1e-12)
    return overall, per_param


def extract_best_fit(
    lk_arr: np.ndarray,
    fbin_vals: np.ndarray,
    pi_vals: np.ndarray,
    sigma_vals: np.ndarray,
) -> Dict[str, float]:
    """Extract best-fit parameters from a likelihood grid."""
    if not np.any(np.isfinite(lk_arr)):
        return {'fbin': np.nan, 'pi': np.nan, 'sigma': np.nan}

    flat_idx = int(np.nanargmax(lk_arr))  # guarded by isfinite check above
    n_sig, n_fb, n_pi = lk_arr.shape
    i_s = flat_idx // (n_fb * n_pi)
    i_f = (flat_idx // n_pi) % n_fb
    i_p = flat_idx % n_pi

    return {
        'fbin': float(fbin_vals[i_f]),
        'pi': float(pi_vals[i_p]),
        'sigma': float(sigma_vals[i_s]),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Single-point validation (combines all steps)
# ─────────────────────────────────────────────────────────────────────────────

def run_single_validation(
    true_fbin: float,
    true_pi: float,
    true_sigma: float,
    true_logPmax: float,
    fbin_grid: np.ndarray,
    pi_grid: np.ndarray,
    sigma_grid: np.ndarray,
    cadence_library: list,
    cadence_weights: Optional[np.ndarray],
    sigma_meas: float,
    bin_cfg: BinaryParameterConfig,
    period_model: str,
    seed: int = 42,
    n_sets: int = 500,
    likelihood_bin_edges: Optional[np.ndarray] = None,
    progress_callback=None,
) -> ValidationPoint:
    """Full single-point validation: mock → grid search → score."""
    # 1. Generate mock observations
    mock_drv = generate_mock_observations(
        true_fbin=true_fbin,
        true_pi=true_pi,
        true_sigma=true_sigma,
        true_logPmax=true_logPmax,
        cadence_library=cadence_library,
        cadence_weights=cadence_weights,
        sigma_meas=sigma_meas,
        bin_cfg=bin_cfg,
        period_model=period_model,
        seed=seed,
    )

    # 2. Run grid search
    lk_arr = run_validation_grid(
        mock_delta_rv=mock_drv,
        fbin_vals=fbin_grid,
        pi_vals=pi_grid,
        sigma_vals=sigma_grid,
        cadence_library=cadence_library,
        cadence_weights=cadence_weights,
        sigma_meas=sigma_meas,
        bin_cfg=bin_cfg,
        period_model=period_model,
        n_sets=n_sets,
        likelihood_bin_edges=likelihood_bin_edges,
        logPmax_val=true_logPmax,
        progress_callback=progress_callback,
    )

    # 3. Extract best fit
    rec = extract_best_fit(lk_arr, fbin_grid, pi_grid, sigma_grid)

    # 4. Score recovery
    true_params = {'fbin': true_fbin, 'pi': true_pi, 'sigma': true_sigma}
    grid_sizes = {
        'fbin': len(fbin_grid),
        'pi': len(pi_grid),
        'sigma': len(sigma_grid),
    }
    # For Langer (pi is not scanned), remove pi from scoring
    if len(pi_grid) <= 1:
        true_params.pop('pi', None)
        rec.pop('pi', None)
        grid_sizes.pop('pi', None)

    score, per_param = compute_recovery_score(true_params, rec, grid_sizes)

    # 5. Build 2D slice for heatmap display (at best sigma)
    best_sig_idx = 0
    if lk_arr.shape[0] > 1 and np.any(np.isfinite(lk_arr)):
        sig_max = [float(np.nanmax(lk_arr[s]))
                   if np.any(np.isfinite(lk_arr[s])) else -np.inf
                   for s in range(lk_arr.shape[0])]
        best_sig_idx = int(np.argmax(sig_max))
    lk_2d = lk_arr[best_sig_idx]  # shape (n_fbin, n_pi)

    return ValidationPoint(
        true_fbin=true_fbin,
        true_pi=true_pi,
        true_sigma=true_sigma,
        true_logPmax=true_logPmax,
        rec_fbin=rec.get('fbin', np.nan),
        rec_pi=rec.get('pi', np.nan),
        rec_sigma=rec.get('sigma', np.nan),
        rec_logPmax=true_logPmax,  # not scanned
        recovery_score=score,
        per_param=per_param,
        likelihood_grid=lk_2d,
        fbin_grid=fbin_grid,
        x_grid=pi_grid if len(pi_grid) > 1 else sigma_grid,
        mock_delta_rv=mock_drv,
        seed=seed,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Batch sweep (Task #161)
# ─────────────────────────────────────────────────────────────────────────────

def run_batch_validation(
    true_fbin_vals: np.ndarray,
    true_pi_vals: np.ndarray,
    true_sigma_vals: np.ndarray,
    true_logPmax: float,
    fbin_grid: np.ndarray,
    pi_grid: np.ndarray,
    sigma_grid: np.ndarray,
    cadence_library: list,
    cadence_weights: Optional[np.ndarray],
    sigma_meas: float,
    bin_cfg: BinaryParameterConfig,
    period_model: str,
    seed_base: int = 100,
    n_sets: int = 500,
    likelihood_bin_edges: Optional[np.ndarray] = None,
    progress_dict: Optional[dict] = None,
) -> BatchResult:
    """Run validation at every combination of (true_fbin, true_pi, true_sigma).

    Parameters
    ----------
    progress_dict : optional dict
        If provided, updated with 'n_done', 'n_total', 'current_point' keys
        for live UI polling.
    """
    n_fb = len(true_fbin_vals)
    n_pi = len(true_pi_vals)
    n_sig = len(true_sigma_vals)
    n_total = n_fb * n_pi * n_sig

    batch = BatchResult(
        true_fbin_vals=true_fbin_vals,
        true_pi_vals=true_pi_vals,
        true_sigma_vals=true_sigma_vals,
        n_total=n_total,
    )
    if progress_dict is not None:
        progress_dict['n_total'] = n_total
        progress_dict['n_done'] = 0

    idx = 0
    for i_f, tf in enumerate(true_fbin_vals):
        for i_p, tp in enumerate(true_pi_vals):
            for i_s, ts in enumerate(true_sigma_vals):
                seed = seed_base + idx * 1000

                if progress_dict is not None:
                    progress_dict['current_point'] = (
                        f'f_bin={tf:.2f}, pi={tp:.1f}, sigma={ts:.1f}')

                vp = run_single_validation(
                    true_fbin=tf,
                    true_pi=tp,
                    true_sigma=ts,
                    true_logPmax=true_logPmax,
                    fbin_grid=fbin_grid,
                    pi_grid=pi_grid,
                    sigma_grid=sigma_grid,
                    cadence_library=cadence_library,
                    cadence_weights=cadence_weights,
                    sigma_meas=sigma_meas,
                    bin_cfg=bin_cfg,
                    period_model=period_model,
                    seed=seed,
                    n_sets=n_sets,
                    likelihood_bin_edges=likelihood_bin_edges,
                )
                batch.points.append(vp)
                idx += 1
                batch.n_done = idx

                if progress_dict is not None:
                    progress_dict['n_done'] = idx

    return batch


def batch_to_recovery_heatmap(
    batch: BatchResult,
    is_dsilva: bool = True,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Convert batch results to a 2D heatmap of recovery scores.

    For Dsilva: (true_fbin × true_pi), marginalized over sigma.
    For Langer: (true_fbin × true_sigma).

    Returns (scores_2d, y_vals, x_vals).
    """
    fbin_vals = batch.true_fbin_vals
    n_fb = len(fbin_vals)

    if is_dsilva:
        pi_vals = batch.true_pi_vals
        sigma_vals = batch.true_sigma_vals
        n_pi = len(pi_vals)
        n_sig = len(sigma_vals)
        # Scores indexed as [i_f, i_p, i_s] in iteration order
        scores_3d = np.full((n_fb, n_pi, n_sig), np.nan)
        idx = 0
        for i_f in range(n_fb):
            for i_p in range(n_pi):
                for i_s in range(n_sig):
                    if idx < len(batch.points):
                        scores_3d[i_f, i_p, i_s] = batch.points[idx].recovery_score
                    idx += 1
        # Marginalize over sigma (mean)
        scores_2d = np.nanmean(scores_3d, axis=2)  # (n_fb, n_pi)
        return scores_2d, fbin_vals, pi_vals
    else:
        sigma_vals = batch.true_sigma_vals
        pi_vals = batch.true_pi_vals
        n_pi = len(pi_vals)
        n_sig = len(sigma_vals)
        scores_3d = np.full((n_fb, n_pi, n_sig), np.nan)
        idx = 0
        for i_f in range(n_fb):
            for i_p in range(n_pi):
                for i_s in range(n_sig):
                    if idx < len(batch.points):
                        scores_3d[i_f, i_p, i_s] = batch.points[idx].recovery_score
                    idx += 1
        # Marginalize over pi (only 1 value for Langer anyway)
        scores_2d = np.nanmean(scores_3d, axis=1)  # (n_fb, n_sig)
        return scores_2d, fbin_vals, sigma_vals
