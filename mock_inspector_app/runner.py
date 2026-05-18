"""mock_inspector_app/runner.py — Detail wrappers around the two pipelines.

Re-implements the orbital-parameter sampling LOOP from
`wr_bias_simulation.simulate_delta_rv_cadence_aware` and from
`app/bc/validation._sample_delta_rv_mock`, capturing the per-binary draws
(logP, e, q, cos i, omega, T0/phase) into return arrays so the inspector
UI can histogram them.

Both wrappers preserve the EXACT inner-sampler call order of their
respective production paths, so:

- Mock Data wrapper      ↔  validation._sample_delta_rv_mock
                            (binary-index method = rng.choice)
- Model Explorer wrapper ↔  wr_bias_simulation.simulate_delta_rv_cadence_aware
                            (binary-index method = rng.permutation[:n_bin])

Per-iteration RNG seeds are derived from `seed_base` so each iteration is
independent but reproducible (seed_i = seed_base + i).

Project rule (CLAUDE.md): we do NOT modify the production code — the
sampling loop is duplicated here verbatim, with the addition of capture
arrays.  This is an acceptable cost (no false data, byte-identical RNG
behaviour to production) and is documented in __init__.py.
"""
from __future__ import annotations

import os
import sys
from typing import Optional

import numpy as np

# Sibling-import setup: the project root + app/ go on sys.path so we can
# import the production samplers without modifying them.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
_APP_ROOT = os.path.join(_PROJECT_ROOT, 'app')
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

from wr_bias_simulation import (  # noqa: E402
    BinaryParameterConfig,
    sample_logP,
    sample_eccentricity,
    sample_primary_mass,
    sample_mass_ratio,
    sample_inclination,
    compute_K1,
    solve_kepler,
    _draw_measurement_noise,
)


# ─────────────────────────────────────────────────────────────────────────────
# Cadence loader (no Streamlit dependency)
# ─────────────────────────────────────────────────────────────────────────────

_CADENCE_CACHE: tuple[list[np.ndarray], np.ndarray] | None = None


def load_cadence_library_uncached() -> tuple[list[np.ndarray], np.ndarray]:
    """Load the 25-star cadence library from the project's standard source.

    Mirrors `app.shared.cached_load_cadence` minus the @st.cache_data
    decorator so this function works outside a Streamlit context (e.g. for
    `python -c "from mock_inspector_app import runner"`).  Once loaded, the
    library is memoised at module level for the lifetime of the process.
    """
    global _CADENCE_CACHE
    if _CADENCE_CACHE is not None:
        return _CADENCE_CACHE
    from pipeline.load_observations import load_cadence_library  # noqa: WPS433
    cad, w = load_cadence_library()
    _CADENCE_CACHE = (cad, w)
    return _CADENCE_CACHE


# ─────────────────────────────────────────────────────────────────────────────
# Build the BinaryParameterConfig used by the comparison.
# ─────────────────────────────────────────────────────────────────────────────

def _build_bin_cfg(true_logPmax: float) -> BinaryParameterConfig:
    """Construct a BinaryParameterConfig matching the Validation tab's
    Dsilva mock recipe: power-law period, flat eccentricity in [0, 0.9],
    fixed primary mass, flat mass ratio.  See render_validation.py:351-357.
    """
    return BinaryParameterConfig(
        logP_min=0.15,
        logP_max=float(true_logPmax),
        period_model='powerlaw',
        e_model='flat',
        e_max=0.9,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Schema documentation (used by both pipelines)
# ─────────────────────────────────────────────────────────────────────────────
#
# Every detail dict has the SAME keys (ragged in the binary axis because
# n_binaries can differ across iterations only if f_bin × N is non-integer
# in different ways — but we use n_bin = round(N · f_bin) deterministically,
# so every iteration has EXACTLY the same n_binaries.  Therefore the binary
# arrays are stored as 2-D numpy arrays of shape (n_iter, n_binaries) for
# easy histogramming).
#
# Keys:
#   delta_rv             : (n_iter, n_stars)        peak-to-peak ΔRV [km/s]
#   logP                 : (n_iter, n_binaries)     log10(P/days)
#   P_days               : (n_iter, n_binaries)     orbital period [days] = 10**logP
#   e                    : (n_iter, n_binaries)     eccentricity in [0, e_max]
#   q                    : (n_iter, n_binaries)     mass ratio M2/M1
#   M1                   : (n_iter, n_binaries)     primary mass [M_sun]
#   M2                   : (n_iter, n_binaries)     secondary mass [M_sun]
#   K1                   : (n_iter, n_binaries)     RV semi-amplitude [km/s]
#   cosi                 : (n_iter, n_binaries)     cos(inclination) in [0, 1]
#   i_rad                : (n_iter, n_binaries)     inclination [rad]
#   omega                : (n_iter, n_binaries)     argument of periastron [rad]
#   T0                   : (n_iter, n_binaries)     phase angle [rad] in [0, 2π]
#   phase                : (n_iter, n_binaries)     T0 / (2π), in [0, 1]
#   is_binary            : (n_iter, n_stars)        bool ground-truth
#   n_binaries_per_iter  : (n_iter,)                int (constant by construction)
#   binary_index_method  : str                      'rng.choice' / 'rng.permutation'
#   pipeline_label       : str                      'Mock Data' / 'Model Explorer'


# ─────────────────────────────────────────────────────────────────────────────
# Mock Data path  — uses rng.choice(N, n_bin, replace=False)
#                   (mirrors validation._sample_delta_rv_mock)
# ─────────────────────────────────────────────────────────────────────────────

def _run_mock_one_iter(
    *,
    seed: int,
    cadences: list[np.ndarray],
    f_bin: float,
    pi: float,
    sigma_single: float,
    sigma_meas: float,
    bin_cfg: BinaryParameterConfig,
    error_model: str,
    error_params: tuple,
) -> dict:
    """Single-iteration Mock Data sampler.  RNG draw order MUST match
    `validation._sample_delta_rv_mock` (`collect_detail=False` branch) for
    byte-identical reproducibility.
    """
    rng = np.random.default_rng(int(seed))

    N = len(cadences)
    n_bin = int(round(N * float(f_bin)))
    n_bin = max(0, min(N, n_bin))

    is_binary = np.zeros(N, dtype=bool)
    if n_bin > 0:
        # MOCK PATH: rng.choice without replacement.  This is the FIRST RNG
        # draw — every subsequent sampler call inherits the resulting state.
        _bin_idx = rng.choice(N, size=n_bin, replace=False)
        is_binary[_bin_idx] = True
    idx_bin = np.where(is_binary)[0]
    idx_single = np.where(~is_binary)[0]

    delta_all = np.zeros(N, dtype=float)

    # --- Singles: per-star draws (matches the for-loop in validation.py) ---
    for k in idx_single:
        t_ep = cadences[k]
        n_ep = int(t_ep.size)
        if n_ep <= 0:
            continue
        v = rng.normal(loc=0.0, scale=sigma_single, size=n_ep)
        noise = _draw_measurement_noise(
            error_model, error_params, sigma_meas, size=n_ep, rng=rng)
        v = v + noise
        delta_all[k] = float(v.max() - v.min()) if n_ep >= 2 else 0.0

    # --- Binaries: vectorised orbital draws, then per-binary Kepler loop ---
    if n_bin > 0:
        logP = sample_logP(size=n_bin, rng=rng, pi=pi, cfg=bin_cfg)
        if isinstance(logP, tuple):
            logP = logP[0]
        P_days = 10.0 ** logP
        e_arr = sample_eccentricity(bin_cfg, n_bin, rng)
        M1 = sample_primary_mass(bin_cfg, n_bin, rng)
        q = sample_mass_ratio(bin_cfg, n_bin, rng)
        M2 = M1 / q if bin_cfg.q_flipped else M1 * q
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
            v = K1[j] * (np.cos(omega[j] + nu)
                         + e_arr[j] * np.cos(omega[j]))
            noise = _draw_measurement_noise(
                error_model, error_params, sigma_meas, size=n_ep, rng=rng)
            v = v + noise
            delta_all[k] = float(v.max() - v.min()) if n_ep >= 2 else 0.0
    else:
        logP = np.zeros(0, dtype=float)
        P_days = np.zeros(0, dtype=float)
        e_arr = np.zeros(0, dtype=float)
        q = np.zeros(0, dtype=float)
        M1 = np.zeros(0, dtype=float)
        M2 = np.zeros(0, dtype=float)
        K1 = np.zeros(0, dtype=float)
        i_inc = np.zeros(0, dtype=float)
        omega = np.zeros(0, dtype=float)
        T0 = np.zeros(0, dtype=float)

    return {
        'delta_rv': delta_all,
        'logP': logP,
        'P_days': P_days,
        'e': e_arr,
        'q': q,
        'M1': M1,
        'M2': M2,
        'K1': K1,
        'cosi': np.cos(i_inc),
        'i_rad': i_inc,
        'omega': omega,
        'T0': T0,
        'phase': T0 / (2.0 * np.pi),
        'is_binary': is_binary,
        'n_bin': n_bin,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Model Explorer path  — uses rng.permutation(N)[:n_bin]
#                        (mirrors simulate_delta_rv_cadence_aware with n_sets=1)
# ─────────────────────────────────────────────────────────────────────────────

def _run_explorer_one_iter(
    *,
    seed: int,
    cadences: list[np.ndarray],
    f_bin: float,
    pi: float,
    sigma_single: float,
    sigma_meas: float,
    bin_cfg: BinaryParameterConfig,
    error_model: str,
    error_params: tuple,
) -> dict:
    """Single-iteration Model Explorer sampler.  RNG draw order MUST match
    `wr_bias_simulation.simulate_delta_rv_cadence_aware` with `n_sets=1`,
    using the SAME grouping-by-cadence-length pattern so the per-binary
    parameter draws are byte-identical to a 1-set production run.
    """
    rng = np.random.default_rng(int(seed))

    N = len(cadences)
    n_bin = int(round(N * float(f_bin)))
    n_bin = max(0, min(N, n_bin))

    is_binary = np.zeros(N, dtype=bool)
    if n_bin > 0:
        # EXPLORER PATH: rng.permutation, take first n_bin.  This is the
        # FIRST RNG draw — every subsequent sampler call inherits state.
        _perm = rng.permutation(N)
        is_binary[_perm[:n_bin]] = True
    idx_bin = np.where(is_binary)[0]
    idx_single = np.where(~is_binary)[0]

    delta_all = np.zeros(N, dtype=float)

    # --- Singles: GROUP BY CADENCE LENGTH (matches production) -----------
    single_groups: dict[int, list[int]] = {}
    for k in idx_single:
        n_ep = int(cadences[k].size)
        if n_ep >= 2:
            single_groups.setdefault(n_ep, []).append(int(k))

    for n_ep, ks_list in single_groups.items():
        n_grp = len(ks_list)
        v = rng.normal(loc=0.0, scale=sigma_single, size=(n_grp, n_ep))
        v += _draw_measurement_noise(
            error_model, error_params, sigma_meas, size=v.shape, rng=rng)
        drv = v.max(axis=1) - v.min(axis=1)
        delta_all[np.array(ks_list)] = drv

    # --- Binaries: vectorised orbital draws + grouped Kepler ------------
    if n_bin > 0:
        logP = sample_logP(size=n_bin, rng=rng, pi=pi, cfg=bin_cfg)
        if isinstance(logP, tuple):
            logP = logP[0]
        P_days = 10.0 ** logP
        e_arr = sample_eccentricity(bin_cfg, n_bin, rng)
        M1 = sample_primary_mass(bin_cfg, n_bin, rng)
        q = sample_mass_ratio(bin_cfg, n_bin, rng)
        M2 = M1 / q if bin_cfg.q_flipped else M1 * q
        i_inc = sample_inclination(n_bin, rng)
        omega = rng.uniform(0.0, 2.0 * np.pi, size=n_bin)
        T0 = rng.uniform(0.0, 2.0 * np.pi, size=n_bin)
        K1 = compute_K1(P_days=P_days, e=e_arr, M1=M1, M2=M2, i_rad=i_inc)

        bin_groups: dict[int, list[tuple[int, int]]] = {}
        for j, k in enumerate(idx_bin):
            n_ep = int(cadences[k].size)
            if n_ep < 2:
                delta_all[k] = 0.0
            else:
                bin_groups.setdefault(n_ep, []).append((int(j), int(k)))

        for n_ep, jk_list in bin_groups.items():
            js = np.array([x[0] for x in jk_list])
            ks_arr = np.array([x[1] for x in jk_list])
            t_mat = np.vstack([cadences[k] for k in ks_arr])
            M_mean = T0[js, None] + 2.0 * np.pi * (t_mat / P_days[js, None])
            E = solve_kepler(M_mean, e_arr[js, None])
            sqrt_fac = np.sqrt((1.0 + e_arr[js, None])
                                / (1.0 - e_arr[js, None]))
            nu = 2.0 * np.arctan2(sqrt_fac * np.tan(E / 2.0), 1.0)
            v = K1[js, None] * (
                np.cos(omega[js, None] + nu)
                + e_arr[js, None] * np.cos(omega[js, None])
            )
            v += _draw_measurement_noise(
                error_model, error_params, sigma_meas, size=v.shape, rng=rng)
            drv = v.max(axis=1) - v.min(axis=1)
            delta_all[ks_arr] = drv
    else:
        logP = np.zeros(0, dtype=float)
        P_days = np.zeros(0, dtype=float)
        e_arr = np.zeros(0, dtype=float)
        q = np.zeros(0, dtype=float)
        M1 = np.zeros(0, dtype=float)
        M2 = np.zeros(0, dtype=float)
        K1 = np.zeros(0, dtype=float)
        i_inc = np.zeros(0, dtype=float)
        omega = np.zeros(0, dtype=float)
        T0 = np.zeros(0, dtype=float)

    return {
        'delta_rv': delta_all,
        'logP': logP,
        'P_days': P_days,
        'e': e_arr,
        'q': q,
        'M1': M1,
        'M2': M2,
        'K1': K1,
        'cosi': np.cos(i_inc),
        'i_rad': i_inc,
        'omega': omega,
        'T0': T0,
        'phase': T0 / (2.0 * np.pi),
        'is_binary': is_binary,
        'n_bin': n_bin,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Multi-iteration drivers (the public API of this module)
# ─────────────────────────────────────────────────────────────────────────────

def _error_model_to_helper_args(error_model: str) -> tuple[str, tuple]:
    """Map the UI's three options to (model_type, params) for the
    production `_draw_measurement_noise` helper.

    - 'gaussian'   → 'fixed' with empty params  → N(0, sigma_meas)
    - 'asymmetric' → 'lognormal' with shape σ=0.5 → magnitudes drawn from
                    a log-normal then a random sign is applied (the helper
                    enforces symmetry around zero)
    - 'none'       → 'fixed' with sigma_fallback overridden later to 0
                    via passing sigma=0 (the helper short-circuits to zeros)
    """
    em = (error_model or 'gaussian').lower()
    if em == 'gaussian':
        return ('fixed', ())
    if em == 'asymmetric':
        # scipy lognorm.rvs(s, loc=0, scale=1) draws non-negative
        # magnitudes; the helper applies a random sign.  The shape σ=0.5
        # gives a moderately right-skewed magnitude distribution.
        return ('lognormal', (0.5,))
    if em == 'none':
        return ('none', ())
    return ('fixed', ())


def _run_pipeline(
    *,
    pipeline: str,
    sigma_single: float,
    sigma_meas: float,
    f_bin: float,
    pi: float,
    true_logPmax: float,
    error_model: str,
    n_iterations: int,
    seed_base: int,
    cadence_library: Optional[list[np.ndarray]] = None,
    progress_cb=None,
) -> dict:
    """Common driver — dispatches to the per-iteration sampler matching
    `pipeline` and stacks results into 2-D arrays.

    Parameters
    ----------
    pipeline : 'mock' or 'explorer'
    progress_cb : callable(frac: float) | None
        Called with the fraction of iterations done after each iteration
        (so the UI can drive a progress bar).
    """
    if cadence_library is None:
        cad, _w = load_cadence_library_uncached()
        cadences = [np.asarray(c, dtype=float) for c in cad]
    else:
        cadences = [np.asarray(c, dtype=float) for c in cadence_library]

    bin_cfg = _build_bin_cfg(true_logPmax)
    em_type, em_params = _error_model_to_helper_args(error_model)

    # 'none' means zero measurement noise — pass sigma=0 to short-circuit
    # _draw_measurement_noise (it returns zeros when sigma_fallback ≤ 0).
    sigma_meas_eff = float(sigma_meas)
    if em_type == 'none':
        sigma_meas_eff = 0.0
        em_type = 'fixed'

    n_iter = int(n_iterations)
    N = len(cadences)
    n_bin_const = int(round(N * float(f_bin)))
    n_bin_const = max(0, min(N, n_bin_const))

    delta_rv = np.zeros((n_iter, N), dtype=float)
    is_binary = np.zeros((n_iter, N), dtype=bool)
    logP_arr = np.zeros((n_iter, n_bin_const), dtype=float)
    P_days_arr = np.zeros((n_iter, n_bin_const), dtype=float)
    e_arr = np.zeros((n_iter, n_bin_const), dtype=float)
    q_arr = np.zeros((n_iter, n_bin_const), dtype=float)
    M1_arr = np.zeros((n_iter, n_bin_const), dtype=float)
    M2_arr = np.zeros((n_iter, n_bin_const), dtype=float)
    K1_arr = np.zeros((n_iter, n_bin_const), dtype=float)
    cosi_arr = np.zeros((n_iter, n_bin_const), dtype=float)
    i_rad_arr = np.zeros((n_iter, n_bin_const), dtype=float)
    omega_arr = np.zeros((n_iter, n_bin_const), dtype=float)
    T0_arr = np.zeros((n_iter, n_bin_const), dtype=float)
    phase_arr = np.zeros((n_iter, n_bin_const), dtype=float)
    n_bin_per_iter = np.zeros(n_iter, dtype=int)

    iter_fn = _run_mock_one_iter if pipeline == 'mock' else _run_explorer_one_iter
    method_label = 'rng.choice' if pipeline == 'mock' else 'rng.permutation'
    pipeline_label = 'Mock Data' if pipeline == 'mock' else 'Model Explorer'

    def _store_iter_result(i: int, d: dict) -> None:
        """Stack one iteration's dict into the pre-allocated 2-D arrays."""
        delta_rv[i, :] = d['delta_rv']
        is_binary[i, :] = d['is_binary']
        n_bin_per_iter[i] = int(d['n_bin'])
        if d['n_bin'] == n_bin_const:
            logP_arr[i, :] = d['logP']
            P_days_arr[i, :] = d['P_days']
            e_arr[i, :] = d['e']
            q_arr[i, :] = d['q']
            M1_arr[i, :] = d['M1']
            M2_arr[i, :] = d['M2']
            K1_arr[i, :] = d['K1']
            cosi_arr[i, :] = d['cosi']
            i_rad_arr[i, :] = d['i_rad']
            omega_arr[i, :] = d['omega']
            T0_arr[i, :] = d['T0']
            phase_arr[i, :] = d['phase']
        elif d['n_bin'] > 0:
            # Defensive: in the edge case n_bin differs (shouldn't happen
            # because round(N·f_bin) is constant), copy what we can.
            k = min(d['n_bin'], n_bin_const)
            logP_arr[i, :k] = d['logP'][:k]
            P_days_arr[i, :k] = d['P_days'][:k]
            e_arr[i, :k] = d['e'][:k]
            q_arr[i, :k] = d['q'][:k]
            M1_arr[i, :k] = d['M1'][:k]
            M2_arr[i, :k] = d['M2'][:k]
            K1_arr[i, :k] = d['K1'][:k]
            cosi_arr[i, :k] = d['cosi'][:k]
            i_rad_arr[i, :k] = d['i_rad'][:k]
            omega_arr[i, :k] = d['omega'][:k]
            T0_arr[i, :k] = d['T0'][:k]
            phase_arr[i, :k] = d['phase'][:k]

    # Serial loop.  The per-iteration samplers are heavily vectorised
    # (≈0.2 ms / iter for the 25-star explorer path on a 12-core M-series
    # Mac), so a pure serial driver is fast enough and avoids the
    # multiprocessing.Pool spawn overhead that was freezing the Streamlit
    # main thread for the duration of the run.
    #
    # Progress throttle: only call progress_cb at most ~100 times for the
    # whole run (interval = max(1, n_iter // 100)) plus the final iter, so
    # the websocket isn't flooded on huge N.
    progress_interval = max(1, n_iter // 100)
    for i in range(n_iter):
        d = iter_fn(
            seed=int(seed_base) + i,
            cadences=cadences,
            f_bin=float(f_bin),
            pi=float(pi),
            sigma_single=float(sigma_single),
            sigma_meas=sigma_meas_eff,
            bin_cfg=bin_cfg,
            error_model=em_type,
            error_params=em_params,
        )
        _store_iter_result(i, d)
        if progress_cb is not None:
            i_done = i + 1
            if i_done == n_iter or i_done % progress_interval == 0:
                progress_cb(i_done / n_iter)

    return {
        'delta_rv': delta_rv,
        'logP': logP_arr,
        'P_days': P_days_arr,
        'e': e_arr,
        'q': q_arr,
        'M1': M1_arr,
        'M2': M2_arr,
        'K1': K1_arr,
        'cosi': cosi_arr,
        'i_rad': i_rad_arr,
        'omega': omega_arr,
        'T0': T0_arr,
        'phase': phase_arr,
        'is_binary': is_binary,
        'n_binaries_per_iter': n_bin_per_iter,
        'binary_index_method': method_label,
        'pipeline_label': pipeline_label,
    }


def run_mock_pipeline(
    *,
    sigma_single: float,
    sigma_meas: float,
    f_bin: float,
    pi: float,
    true_logPmax: float,
    error_model: str,
    n_iterations: int,
    seed_base: int,
    cadence_library: Optional[list[np.ndarray]] = None,
    progress_cb=None,
) -> dict:
    """Mock Data path.  Binary indices via rng.choice(N, n_bin, replace=False).

    Returns a dict with keys: delta_rv, logP, e, q, cosi, omega, phase,
    is_binary, n_binaries_per_iter, binary_index_method, pipeline_label.
    See module docstring for shapes.
    """
    return _run_pipeline(
        pipeline='mock',
        sigma_single=sigma_single, sigma_meas=sigma_meas, f_bin=f_bin, pi=pi,
        true_logPmax=true_logPmax, error_model=error_model,
        n_iterations=n_iterations, seed_base=seed_base,
        cadence_library=cadence_library, progress_cb=progress_cb,
    )


def run_explorer_pipeline(
    *,
    sigma_single: float,
    sigma_meas: float,
    f_bin: float,
    pi: float,
    true_logPmax: float,
    error_model: str,
    n_iterations: int,
    seed_base: int,
    cadence_library: Optional[list[np.ndarray]] = None,
    progress_cb=None,
) -> dict:
    """Model Explorer path.  Binary indices via rng.permutation(N)[:n_bin].

    Same return schema as `run_mock_pipeline`.
    """
    return _run_pipeline(
        pipeline='explorer',
        sigma_single=sigma_single, sigma_meas=sigma_meas, f_bin=f_bin, pi=pi,
        true_logPmax=true_logPmax, error_model=error_model,
        n_iterations=n_iterations, seed_base=seed_base,
        cadence_library=cadence_library, progress_cb=progress_cb,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Observed ΔRVs (for the CDF reference curve)
# ─────────────────────────────────────────────────────────────────────────────

_OBS_DRV_CACHE: np.ndarray | None = None


def load_observed_delta_rv() -> np.ndarray:
    """Load real observed peak-to-peak ΔRVs (one per star) from the
    project's standard pipeline.  Mirrors `app.shared.cached_load_observed_delta_rvs`
    minus the @st.cache_data decorator (we memoise at module level instead).
    """
    global _OBS_DRV_CACHE
    if _OBS_DRV_CACHE is not None:
        return _OBS_DRV_CACHE
    from pipeline.load_observations import load_observed_delta_rvs  # noqa: WPS433
    drv, _detail = load_observed_delta_rvs(settings=None, obs=None)
    drv = np.asarray(drv, dtype=float)
    # Filter zero-padded missing values, per project convention.
    drv = drv[drv != 0]
    _OBS_DRV_CACHE = drv
    return drv
