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
    _draw_measurement_noise,
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
    full_likelihood: np.ndarray    # full 3-D (sigma, fbin, pi) likelihood array
    fbin_grid: np.ndarray
    pi_grid: np.ndarray            # pi grid (Dsilva) or [0.0] (Langer)
    sigma_grid: np.ndarray         # sigma grid
    x_grid: np.ndarray             # pi (Dsilva) or sigma (Langer) — for heatmap display
    mock_delta_rv: np.ndarray      # the mock observations used
    seed: int
    logPmax_grid: np.ndarray = field(default_factory=lambda: np.array([]))


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


def _sample_delta_rv_mock(
    f_bin: float,
    pi: float,
    sigma_single: float,
    logP_max: float,
    cadence_library: list,
    sigma_meas: float,
    bin_cfg: BinaryParameterConfig,
    period_model: str,
    seed: int,
    *,
    error_model: str = 'fixed',
    error_params: tuple = (),
    sigma_meas_binary: Optional[float] = None,
    error_model_binary: Optional[str] = None,
    error_params_binary: Optional[tuple] = None,
    collect_detail: bool = False,
):
    """Core mock sampler — used by BOTH the mock generator and the Explorer's
    validation-mode CDF overlay, so the two produce byte-identical ΔRV draws
    when handed the same parameters and seed.

    *** Semantic model (2026-04-23 revision) ***: this sampler produces
    OBSERVATIONAL RVs, exactly like the Dsilva/Langer cadence grids:

        v_obs = v_signal + noise_from_chosen_distribution

    ``v_signal`` is the clean physics RV (Kepler orbit for binaries,
    ``N(0, σ_single)`` for singles — the intrinsic stellar-variability
    scatter).  The measurement noise is drawn via
    :func:`wr_bias_simulation._draw_measurement_noise` — the SAME helper
    used by the grid — so the chosen error distribution shapes the mock's
    ΔRV CDF in the same way it shapes the grid simulation CDF.

    The per-epoch error array stored alongside each mock star's RVs is the
    distribution's MEAN (``sigma_meas``) broadcast to shape ``(n_ep,)`` —
    NOT the noise realisation.  That mean is what gets saved into
    ``mock_stars.npz`` via ``validation_io._build_mock_stars_payload`` and
    consumed by downstream classification significance tests (ΔRV − 4σ > 0).

    RNG draw order MUST stay identical to ``generate_mock_observations_detail``
    because that function delegates here with ``collect_detail=True``.  The
    Explorer's validation-mode path (``_me_cdf_band`` / ``_me_cdf_band_langer``)
    calls this same function with the same args + seed, so byte-identical
    invariant with the mock holds automatically (checked by
    ``scripts/test_explorer_mock_equal.py``).

    Parameters
    ----------
    error_model : str
        ``'fixed'`` or a distribution name from
        ``wr_bias_simulation._ERR_DIST_MAP`` (case-insensitive, also accepts
        the capitalised forms the selector UI returns, e.g. ``'Log-normal'``).
    error_params : tuple
        Scipy distribution parameters (ignored when ``error_model='fixed'``).

    Returns:
        drv  : (N,) float ΔRV per star [km/s] — peak-to-peak of NOISY RVs.
        When collect_detail=True, also returns:
            is_binary     : (N,) bool
            rvs_per_star  : list[np.ndarray] — noisy per-epoch RVs
            errs_per_star : list[np.ndarray] — per-epoch σ (broadcast
                            ``sigma_meas``), same shape as rvs_per_star[k].
    """
    from wr_bias_simulation import (
        sample_logP, sample_eccentricity, sample_primary_mass,
        sample_mass_ratio, sample_inclination, compute_K1, solve_kepler,
    )

    # Binary-side error model overrides (None → fall back to single's value,
    # preserving byte-identical RNG draws for callers that pass a single
    # error model — e.g. the Explorer's validation-mode CDF overlay).
    if sigma_meas_binary is None:
        sigma_meas_binary = sigma_meas
    if error_model_binary is None:
        error_model_binary = error_model
    if error_params_binary is None:
        error_params_binary = error_params

    rng = np.random.default_rng(seed)

    mock_cfg = BinaryParameterConfig(**vars(bin_cfg))
    mock_cfg.logP_max = float(logP_max)
    mock_cfg.period_model = period_model

    v_sys = 0.0
    cadences = [np.asarray(c, dtype=float) for c in cadence_library]
    N = len(cadences)

    # Deterministic binary count (user feedback 2026-04-29): the realised
    # count must match the input f_bin exactly, not fluctuate around it.
    # n_bin = round(N · f_bin) — only WHICH stars are binary is random.
    n_bin = int(round(N * float(f_bin)))
    n_bin = max(0, min(N, n_bin))
    is_binary = np.zeros(N, dtype=bool)
    if n_bin > 0:
        _bin_idx = rng.choice(N, size=n_bin, replace=False)
        is_binary[_bin_idx] = True
    idx_bin = np.where(is_binary)[0]
    idx_single = np.where(~is_binary)[0]

    rvs_per_star: list = [np.array([], dtype=float)] * N if collect_detail \
        else None
    errs_per_star: list = [np.array([], dtype=float)] * N if collect_detail \
        else None
    delta_all = np.zeros(N, dtype=float)

    # Singles — intrinsic scatter N(0, σ_single) + measurement noise drawn
    # from the chosen distribution (Dsilva-style observational model).
    for k in idx_single:
        t_ep = cadences[k]
        n_ep = int(t_ep.size)
        if n_ep <= 0:
            continue
        v = rng.normal(loc=v_sys, scale=sigma_single, size=n_ep)
        # Add per-epoch measurement noise from the chosen distribution —
        # SAME helper the Dsilva/Langer grids use, so the mock CDF responds
        # to sigma_meas / distribution choice identically to the grid.
        noise = _draw_measurement_noise(
            error_model, error_params, sigma_meas, size=n_ep, rng=rng)
        v = v + noise
        if collect_detail:
            rvs_per_star[k] = v
            errs_per_star[k] = np.full(n_ep, sigma_meas, dtype=float)
        delta_all[k] = float(v.max() - v.min()) if n_ep >= 2 else 0.0

    # Binaries — Kepler physics + measurement noise from chosen distribution.
    if n_bin > 0:
        logP = sample_logP(size=n_bin, rng=rng, pi=pi, cfg=mock_cfg)
        if isinstance(logP, tuple):
            logP = logP[0]
        P_days = 10.0 ** logP
        e_arr = sample_eccentricity(mock_cfg, n_bin, rng)
        M1 = sample_primary_mass(mock_cfg, n_bin, rng)
        q = sample_mass_ratio(mock_cfg, n_bin, rng)
        M2 = M1 / q if mock_cfg.q_flipped else M1 * q
        i_inc = sample_inclination(n_bin, rng)
        omega = rng.uniform(0.0, 2.0 * np.pi, size=n_bin)
        T0 = rng.uniform(0.0, 2.0 * np.pi, size=n_bin)
        K1 = compute_K1(P_days=P_days, e=e_arr, M1=M1, M2=M2, i_rad=i_inc)

        for j, k in enumerate(idx_bin):
            t_ep = cadences[k]
            n_ep = int(t_ep.size)
            if n_ep <= 0:
                continue
            M_mean = T0[j] + 2.0 * np.pi * (t_ep / P_days[j])
            E = solve_kepler(M_mean, e_arr[j])
            sqrt_fac = np.sqrt((1.0 + e_arr[j]) / (1.0 - e_arr[j]))
            nu = 2.0 * np.arctan2(sqrt_fac * np.tan(E / 2.0), 1.0)
            v = v_sys + K1[j] * (
                np.cos(omega[j] + nu) + e_arr[j] * np.cos(omega[j])
            )
            # Add per-epoch measurement noise — binary-side distribution.
            noise = _draw_measurement_noise(
                error_model_binary, error_params_binary, sigma_meas_binary,
                size=n_ep, rng=rng)
            v = v + noise
            if collect_detail:
                rvs_per_star[k] = v
                errs_per_star[k] = np.full(n_ep, sigma_meas_binary, dtype=float)
            delta_all[k] = float(v.max() - v.min()) if n_ep >= 2 else 0.0

    if collect_detail:
        return delta_all, is_binary, rvs_per_star, errs_per_star
    return delta_all


def generate_mock_observations_detail(
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
    *,
    error_model: str = 'fixed',
    error_params: tuple = (),
    sigma_meas_binary: Optional[float] = None,
    error_model_binary: Optional[str] = None,
    error_params_binary: Optional[tuple] = None,
) -> dict:
    """Cadence-aware mock generation returning per-star detail.

    Produces one set (n_sets=1) and exposes the ground-truth binarity
    flag plus per-epoch (noisy) RVs AND per-epoch error σ for every mock
    star, so the validation UI can show a labelled CDF / binary-fraction
    plot and a star table, and classification significance tests can
    consume the errors.

    The RVs include measurement noise drawn from the chosen error
    distribution — identical observational model to the Dsilva/Langer
    cadence grids.  See docstring of :func:`_sample_delta_rv_mock`.

    Parameters
    ----------
    error_model : str
        Distribution type for the per-epoch measurement-noise draw.
        ``'fixed'`` → ``N(0, sigma_meas)``.  Otherwise a scipy distribution
        name (e.g. ``'Log-normal'``) consumed by
        :func:`wr_bias_simulation._draw_measurement_noise`.
    error_params : tuple
        Scipy distribution parameters (ignored for ``'fixed'``).

    Returns a dict with keys:
      delta_rv       : (N,)  peak-to-peak ΔRV of noisy RVs [km/s]
      is_binary      : (N,)  bool ground-truth binarity
      rvs_per_star   : list of ndarray — per-epoch NOISY RV per star [km/s]
      errs_per_star  : list of ndarray — per-epoch σ (broadcast
                       ``sigma_meas``) per star [km/s], same shape as
                       rvs_per_star[k].
      n_epochs       : (N,)  int number of epochs per star
      rv_min, rv_max : (N,)  min/max (noisy) RV per star [km/s]
      seed           : int   random seed used

    Note: cadence_weights is accepted for signature compatibility with
    generate_mock_observations but is NOT used — the mock uses the full
    cadence_library one-star-per-cadence by construction.
    """
    delta_all, is_binary, rvs_per_star, errs_per_star = _sample_delta_rv_mock(
        f_bin=true_fbin,
        pi=true_pi,
        sigma_single=true_sigma,
        logP_max=true_logPmax,
        cadence_library=cadence_library,
        sigma_meas=sigma_meas,
        bin_cfg=bin_cfg,
        period_model=period_model,
        seed=int(seed),
        error_model=error_model,
        error_params=tuple(error_params),
        sigma_meas_binary=sigma_meas_binary,
        error_model_binary=error_model_binary,
        error_params_binary=(tuple(error_params_binary)
                             if error_params_binary is not None else None),
        collect_detail=True,
    )

    n_epochs = np.array([r.size for r in rvs_per_star], dtype=int)
    rv_min = np.array(
        [float(r.min()) if r.size > 0 else np.nan for r in rvs_per_star])
    rv_max = np.array(
        [float(r.max()) if r.size > 0 else np.nan for r in rvs_per_star])

    return {
        'delta_rv': delta_all,
        'is_binary': is_binary,
        'rvs_per_star': rvs_per_star,
        'errs_per_star': errs_per_star,
        'n_epochs': n_epochs,
        'rv_min': rv_min,
        'rv_max': rv_max,
        'seed': int(seed),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap uncertainty band for the mock preview
# ─────────────────────────────────────────────────────────────────────────────

def bootstrap_mock_cdf_band(
    *,
    f_bin: float,
    pi: float,
    sigma_single: float,
    logP_max: float,
    cadence_library: list,
    sigma_meas: float,
    bin_cfg: BinaryParameterConfig,
    period_model: str,
    error_model: str = 'fixed',
    error_params: tuple = (),
    n_boot: int = 50,
    seed_base: int = 1000,
    cdf_x_grid: Optional[np.ndarray] = None,
    threshold_grid: Optional[np.ndarray] = None,
) -> Dict[str, np.ndarray]:
    """Bootstrap a 16/84 uncertainty band for the mock-preview CDF and
    binary-fraction-vs-threshold curves.

    Runs ``n_boot`` independent draws of :func:`_sample_delta_rv_mock` with
    seeds ``seed_base + 1, seed_base + 2, …, seed_base + n_boot`` — same
    physics parameters as the deterministic mock, only the seed varies.
    The deterministic mock realisation itself is produced by the caller
    (with the user-set seed) and is NOT recomputed here.

    Returned percentiles per x grid:

    - ``cdf_16``, ``cdf_84`` — only present when ``cdf_x_grid`` is provided.
      Empirical CDF ``mean(drv <= x)`` evaluated at each x in the grid, then
      16/84-th percentile across bootstraps.
    - ``fbin_16``, ``fbin_84`` — only present when ``threshold_grid`` is
      provided.  ``mean(drv > t)`` evaluated at each t, 16/84-th percentile.

    Parameters mirror :func:`_sample_delta_rv_mock` so the bootstrap shares
    the EXACT same sampler used by both the mock generator and the Explorer's
    validation-mode CDF overlay (cross-figure consistency, see
    ``render_lk_explorer._render_lk_cdf_sanity_check``).
    """
    cdf_lo = cdf_hi = None
    fbin_lo = fbin_hi = None

    if cdf_x_grid is None and threshold_grid is None:
        return {}

    cdf_xg = (np.asarray(cdf_x_grid, dtype=float)
              if cdf_x_grid is not None else None)
    th_g = (np.asarray(threshold_grid, dtype=float)
            if threshold_grid is not None else None)

    cdfs = []
    fbins = []
    for i in range(int(n_boot)):
        try:
            drv_b = _sample_delta_rv_mock(
                f_bin=float(f_bin),
                pi=float(pi),
                sigma_single=float(sigma_single),
                logP_max=float(logP_max),
                cadence_library=cadence_library,
                sigma_meas=float(sigma_meas),
                bin_cfg=bin_cfg,
                period_model=str(period_model),
                seed=int(seed_base) + 1 + i,
                error_model=str(error_model),
                error_params=tuple(error_params),
                collect_detail=False,
            )
        except Exception:
            continue
        drv_b = np.asarray(drv_b, dtype=float)
        if drv_b.size == 0:
            continue
        if cdf_xg is not None:
            # Empirical CDF at each x grid point: mean(drv <= x).
            # searchsorted on a sorted array gives the same answer in O(log N).
            srt = np.sort(drv_b)
            cdfs.append(
                np.searchsorted(srt, cdf_xg, side='right') / float(srt.size)
            )
        if th_g is not None:
            # Survival fraction at each threshold: mean(drv > t).
            srt = np.sort(drv_b) if cdf_xg is None else srt
            n = float(srt.size)
            # mean(drv > t) = 1 - mean(drv <= t)
            fbins.append(
                1.0 - np.searchsorted(srt, th_g, side='right') / n
            )

    out: Dict[str, np.ndarray] = {}
    if cdf_xg is not None and len(cdfs) >= 2:
        arr = np.asarray(cdfs)
        out['cdf_16'] = np.percentile(arr, 16, axis=0)
        out['cdf_84'] = np.percentile(arr, 84, axis=0)
    if th_g is not None and len(fbins) >= 2:
        arr = np.asarray(fbins)
        out['fbin_16'] = np.percentile(arr, 16, axis=0)
        out['fbin_84'] = np.percentile(arr, 84, axis=0)
    out['n_boot_used'] = np.array(
        [len(cdfs) if cdf_xg is not None else len(fbins)], dtype=int)
    return out


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
    logPmax_vals: Optional[np.ndarray] = None,
) -> Dict[str, float]:
    """Extract best-fit parameters from a likelihood grid (3-D or 4-D)."""
    if not np.any(np.isfinite(lk_arr)):
        result = {'fbin': np.nan, 'pi': np.nan, 'sigma': np.nan}
        if logPmax_vals is not None and len(logPmax_vals) > 1:
            result['logPmax'] = np.nan
        return result

    flat_idx = int(np.nanargmax(lk_arr))  # guarded by isfinite check above

    if lk_arr.ndim == 4 and logPmax_vals is not None and len(logPmax_vals) > 1:
        n_lp, n_sig, n_fb, n_pi = lk_arr.shape
        i_lp = flat_idx // (n_sig * n_fb * n_pi)
        rem = flat_idx % (n_sig * n_fb * n_pi)
        i_s = rem // (n_fb * n_pi)
        i_f = (rem // n_pi) % n_fb
        i_p = rem % n_pi
        return {
            'fbin': float(fbin_vals[i_f]),
            'pi': float(pi_vals[i_p]),
            'sigma': float(sigma_vals[i_s]),
            'logPmax': float(logPmax_vals[i_lp]),
        }

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
        full_likelihood=lk_arr,
        fbin_grid=fbin_grid,
        pi_grid=pi_grid,
        sigma_grid=sigma_grid,
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
