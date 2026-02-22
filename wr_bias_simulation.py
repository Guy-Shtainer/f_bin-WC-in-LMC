"""
wr_bias_simulation.py

Monte-Carlo bias simulation for WR single + binary populations.

Main ideas
----------
- We simulate N_stars, of which a fraction f_bin are binaries and the rest
  are singles.
- For binaries we draw orbital parameters:
    * logP: from either a power-law p(logP) ~ (logP)^pi (Dsilva-style),
      or from an approximate Langer+2020 OB+BH logP distribution.
    * e: 0 (Langer-like) or flat in [0, e_max] (Dsilva-like).
    * q = M2/M1: flat in some interval, or a crude Langer-like Gaussian.
    * i: random orientation => p(i) ∝ sin(i).
    * omega: flat in [0, 2π].
    * T0: flat in [0, P] (implemented via a random mean anomaly M0 at t=0).
- We compute RV curves for the visible star, add noise, compute ΔRV per star,
  and compare the ΔRV distribution to the observed one with a K-S test.
- We scan a grid of (f_bin, pi) and run each grid point in parallel using
  multiprocessing.Pool. For the Langer+2020 period model, pi is ignored.

Key public pieces
-----------------
- SimulationConfig
- BinaryParameterConfig
- simulate_delta_rv_sample
- run_bias_grid
- plot_ks_heatmap (optional helper)

You can import this file from a Jupyter notebook:

    from wr_bias_simulation import (
        SimulationConfig, BinaryParameterConfig,
        run_bias_grid, plot_ks_heatmap
    )

and then call run_bias_grid(...) from a cell.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Tuple, List

import multiprocessing as mp
import matplotlib.pyplot as plt
import numpy as np

# Physical constants (SI)
G_SI = 6.67430e-11        # m^3 kg^-1 s^-2
M_SUN = 1.98847e30        # kg
DAY_S = 86400.0           # s/day


# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field
from typing import Optional, List
import numpy as np

@dataclass
class SimulationConfig:
    """
    Global settings for the Monte-Carlo simulation (per grid point).

    Parameters
    ----------
    n_stars : int
        Number of WR systems (single + binary) per grid point.
    n_epochs : int
        Number of RV epochs per star (if observation_times is None and
        cadence_library is None).
    time_span : float
        Total time baseline of the observations in days. If
        observation_times is None and cadence_library is None, epochs
        are spaced linearly from 0 to time_span.
    sigma_single : float
        "Intrinsic" RV scatter for single WR stars in km/s.
    sigma_measure : float
        Per-epoch measurement uncertainty in km/s, added to all stars.
    v_sys : float
        Systemic velocity in km/s (irrelevant for ΔRV, but kept for
        completeness).
    observation_times : array-like or None
        If provided (and cadence_library is None), a 1D array of times
        (days) at which every star is observed.
    cadence_library : list of 1D arrays or None
        If provided, each element is a 1D array of times (days) for one
        real star. For each simulated system we randomly pick one of
        these arrays and use it as that system's cadence.
        In this case, observation_times / n_epochs / time_span are ignored.
    cadence_weights : array-like or None
        Optional sampling weights for cadence_library entries. If None,
        all cadences are equally likely.
    """
    n_stars: int = 10_000
    n_epochs: int = 6
    time_span: float = 3650.0  # days
    sigma_single: float = 15.0  # km/s
    sigma_measure: float = 5.0  # km/s
    v_sys: float = 0.0          # km/s
    observation_times: Optional[np.ndarray] = field(default=None, repr=False)
    cadence_library: Optional[List[np.ndarray]] = field(default=None, repr=False)
    cadence_weights: Optional[np.ndarray] = field(default=None, repr=False)

    def get_observation_times(self) -> np.ndarray:
        """
        Return a 1D array of observation times in days for the
        'simple' case where all stars share the same cadence.
        """
        if self.observation_times is None:
            return np.linspace(0.0, self.time_span, self.n_epochs)
        t = np.asarray(self.observation_times, dtype=float)
        if t.ndim != 1:
            raise ValueError("observation_times must be 1-D.")
        return t

    def sample_times_for_systems(self, n_systems: int, rng: np.random.Generator) -> list[np.ndarray]:
        """
        For each simulated system, return a time array.

        If cadence_library is provided, we randomly pick an entry for
        each system (optionally weighted by cadence_weights).
        Otherwise, we use a single common time grid from get_observation_times().
        """
        # No cadence library: everyone uses the same times
        if self.cadence_library is None:
            t = self.get_observation_times()
            return [t] * n_systems

        # Use the provided cadence library
        lib = [np.asarray(t, dtype=float) for t in self.cadence_library]
        if any(t.ndim != 1 for t in lib):
            raise ValueError("All cadence_library entries must be 1-D arrays.")

        if self.cadence_weights is None:
            weights = np.ones(len(lib), dtype=float)
        else:
            weights = np.asarray(self.cadence_weights, dtype=float)
        weights = weights / weights.sum()

        idx = rng.choice(len(lib), size=n_systems, replace=True, p=weights)
        return [lib[i] for i in idx]



@dataclass
class BinaryParameterConfig:
    """
    Settings for the binary orbital-parameter distributions.

    Period distribution:
    --------------------
    logP_min, logP_max : float
        Minimum and maximum log10(P/days) for the power-law model.
    period_model : str
        "powerlaw"  -> p(logP) ∝ (logP)^pi between [logP_min, logP_max].
        "langer2020" -> approximate Langer+2020 OB+BH logP distribution.
                        In this case 'pi' is ignored and you may tune
                        langer_period_params to better match Fig. 6.
    langer_period_params : dict
        Extra kwargs passed to sample_logP_langer2020.

    Eccentricity:
    -------------
    e_model : str
        "zero" -> e = 0 for all binaries (Langer-like).
        "flat" -> e ~ U[0, e_max] (Dsilva-like).
    e_max : float
        Maximum eccentricity for the flat model.

    Primary mass:
    -------------
    mass_primary_model : str
        "fixed"   -> M1 is constant = mass_primary_fixed (Msun).
        "uniform" -> M1 ~ U[mass_primary_range[0], mass_primary_range[1]].
    mass_primary_fixed : float
        Fixed primary mass in Msun.
    mass_primary_range : tuple
        (min, max) mass range for uniform model.

    Mass ratio q = M2/M1:
    ---------------------
    q_model : str
        "flat"   -> q ~ U[q_range[0], q_range[1]].
        "langer" -> crude Gaussian approximation to Langer+2020 BH/OB
                    mass-ratio distribution; tune langer_q_mu/sigma.
    q_range : tuple
        (q_min, q_max) for flat model.
    langer_q_mu, langer_q_sigma : float
        Mean & sigma of Gaussian q-distribution for q_model="langer".
    """
    # Period
    logP_min: float = 0.15
    logP_max: float = 5.0
    period_model: str = "powerlaw"  # or "langer2020"
    langer_period_params: Dict[str, float] = field(default_factory=dict, repr=False)

    # Eccentricity
    e_model: str = "flat"  # "zero" or "flat"
    e_max: float = 0.9

    # Primary mass
    mass_primary_model: str = "fixed"  # "fixed" or "uniform"
    mass_primary_fixed: float = 10.0   # Msun
    mass_primary_range: Tuple[float, float] = (10.0, 20.0)

    # Mass ratio
    q_model: str = "flat"  # "flat" or "langer"
    q_range: Tuple[float, float] = (0.1, 2.0)
    langer_q_mu: float = 0.7
    langer_q_sigma: float = 0.2


# ---------------------------------------------------------------------------
# Sampling utilities
# ---------------------------------------------------------------------------

def sample_logP_powerlaw(
    pi: float,
    size: int,
    logP_min: float,
    logP_max: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Sample log10(P/days) from p(logP) ∝ (logP)^pi on [logP_min, logP_max].

    This matches the form p(log P) ∝ (log P)^π used by Dsilva+ (2023).  The
    exponents may be negative. logP_min/logP_max must be > 0.
    """
    if logP_min <= 0 or logP_max <= 0:
        raise ValueError("logP_min and logP_max must be positive for the power-law.")

    a = float(logP_min)
    b = float(logP_max)

    u = rng.random(size)

    if math.isclose(pi, -1.0, rel_tol=1e-8, abs_tol=1e-8):
        # π = -1 -> p(x) ∝ 1/x, CDF F(x) = ln(x/a) / ln(b/a)
        # => x = a * (b/a)^u
        x = a * (b / a) ** u
    else:
        exponent = pi + 1.0
        a_exp = a ** exponent
        b_exp = b ** exponent
        x = (u * (b_exp - a_exp) + a_exp) ** (1.0 / exponent)

    return x


def sample_logP_langer2020(
    size: int,
    rng: np.random.Generator,
    mu_A: float = 1.1,
    sigma_A: float = 0.15,
    mu_B: float = 2.2,
    sigma_B: float = 0.35,
    weight_A: float = 0.3,
    logP_min: float = 0.5,
    logP_max: float = 3.5,
) -> np.ndarray:
    """
    Crude approximation to the OB+BH logP distribution in Langer+2020.

    We approximate the distribution as a mixture of two Gaussians in log10 P:
    - "Case A" peak around ~10-20 d (mu_A, sigma_A).
    - "Case B" peak around ~150 d (mu_B, sigma_B).

    Parameters can be tuned by passing a dict as BinaryParameterConfig.langer_period_params.
    """
    u = rng.random(size)
    logP = np.empty(size, dtype=float)

    mask_A = u < weight_A
    mask_B = ~mask_A

    n_A = mask_A.sum()
    n_B = mask_B.sum()

    if n_A > 0:
        logP[mask_A] = rng.normal(loc=mu_A, scale=sigma_A, size=n_A)
    if n_B > 0:
        logP[mask_B] = rng.normal(loc=mu_B, scale=sigma_B, size=n_B)

    logP = np.clip(logP, logP_min, logP_max)
    return logP


def sample_primary_mass(cfg: BinaryParameterConfig, size: int, rng: np.random.Generator) -> np.ndarray:
    """Sample primary WR mass M1 [Msun]."""
    mode = cfg.mass_primary_model.lower()
    if mode == "fixed":
        return np.full(size, cfg.mass_primary_fixed, dtype=float)
    elif mode == "uniform":
        mmin, mmax = cfg.mass_primary_range
        return rng.uniform(mmin, mmax, size=size)
    else:
        raise ValueError(f"Unknown mass_primary_model: {cfg.mass_primary_model}")


def sample_mass_ratio(cfg: BinaryParameterConfig, size: int, rng: np.random.Generator) -> np.ndarray:
    """Sample mass ratio q = M2/M1."""
    mode = cfg.q_model.lower()
    if mode == "flat":
        qmin, qmax = cfg.q_range
        return rng.uniform(qmin, qmax, size=size)
    elif mode == "langer":
        # Very rough Gaussian approximation to Langer+2020 BH/OB mass ratios.
        q = rng.normal(loc=cfg.langer_q_mu, scale=cfg.langer_q_sigma, size=size)
        return np.clip(q, 0.25, 1.75)
    else:
        raise ValueError(f"Unknown q_model: {cfg.q_model}")


def sample_eccentricity(cfg: BinaryParameterConfig, size: int, rng: np.random.Generator) -> np.ndarray:
    """Sample eccentricities."""
    mode = cfg.e_model.lower()
    if mode == "zero":
        return np.zeros(size, dtype=float)
    elif mode == "flat":
        return rng.uniform(0.0, cfg.e_max, size=size)
    else:
        raise ValueError(f"Unknown e_model: {cfg.e_model}")


def sample_inclination(size: int, rng: np.random.Generator) -> np.ndarray:
    """Sample inclination angles i [rad] with p(i) ∝ sin(i), i in [0, π/2]."""
    cos_i = rng.uniform(0.0, 1.0, size=size)
    return np.arccos(cos_i)


def sample_logP(
    size: int,
    rng: np.random.Generator,
    pi: float,
    cfg: BinaryParameterConfig,
) -> np.ndarray:
    """Dispatch to the requested period model."""
    model = cfg.period_model.lower()
    if model == "powerlaw":
        return sample_logP_powerlaw(pi, size, cfg.logP_min, cfg.logP_max, rng)
    elif model == "langer2020":
        params = dict(cfg.langer_period_params)  # copy
        # allow overriding logP_min/max via params, but fall back to cfg if absent
        params.setdefault("logP_min", cfg.logP_min)
        params.setdefault("logP_max", cfg.logP_max)
        return sample_logP_langer2020(size=size, rng=rng, **params)
    else:
        raise ValueError(f"Unknown period_model: {cfg.period_model}")


# ---------------------------------------------------------------------------
# Orbital dynamics
# ---------------------------------------------------------------------------

def compute_K1(
    P_days: np.ndarray,
    e: np.ndarray,
    M1: np.ndarray,
    M2: np.ndarray,
    i_rad: np.ndarray,
) -> np.ndarray:
    """
    Compute RV semi-amplitude K1 [km/s] of star 1.

    Formula:
        K1 = ( (2π G) / P )^(1/3) * (M2 sin i) / (M1 + M2)^(2/3) / sqrt(1 - e^2)

    with P in seconds, masses in kg.
    """
    P_days = np.asarray(P_days, dtype=float)
    e = np.asarray(e, dtype=float)
    M1 = np.asarray(M1, dtype=float)
    M2 = np.asarray(M2, dtype=float)
    i_rad = np.asarray(i_rad, dtype=float)

    P_sec = P_days * DAY_S
    M1_kg = M1 * M_SUN
    M2_kg = M2 * M_SUN
    Mtot_kg = M1_kg + M2_kg

    factor = (2.0 * np.pi * G_SI / P_sec) ** (1.0 / 3.0)
    numerator = M2_kg * np.sin(i_rad)
    denom = (Mtot_kg ** (2.0 / 3.0)) * np.sqrt(1.0 - e ** 2)

    K1_m_s = factor * numerator / denom
    return K1_m_s / 1000.0  # km/s


def solve_kepler(
    M: np.ndarray,
    e: np.ndarray,
    tol: float = 1e-10,
    maxiter: int = 50,
) -> np.ndarray:
    """
    Solve Kepler's equation E - e sin E = M for E (eccentric anomaly).

    Works on arrays using Newton-Raphson iteration.
    """
    M = np.asarray(M, dtype=float)
    e = np.asarray(e, dtype=float)

    E = M.copy()
    for _ in range(maxiter):
        f = E - e * np.sin(E) - M
        fprime = 1.0 - e * np.cos(E)
        delta = -f / fprime
        E += delta
        if np.all(np.abs(delta) < tol):
            break
    return E


# ---------------------------------------------------------------------------
# Core simulation: one (f_bin, pi) point
# ---------------------------------------------------------------------------

def simulate_delta_rv_sample(
    f_bin: float,
    pi: float,
    sim_cfg: SimulationConfig,
    bin_cfg: BinaryParameterConfig,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Simulate ΔRV values for a mixed population of single + binary WR stars.

    Parameters
    ----------
    f_bin : float
        Intrinsic binary fraction in [0,1].
    pi : float
        Power-law index for the period distribution. Ignored if
        bin_cfg.period_model == "langer2020".
    sim_cfg : SimulationConfig
        Global simulation configuration (N_stars, noise, cadence...).
    bin_cfg : BinaryParameterConfig
        Orbital-parameter distribution configuration for binaries.
    rng : np.random.Generator
        RNG instance for reproducibility.

    Returns
    -------
    delta_all : ndarray, shape (n_stars,)
        Peak-to-peak ΔRV [km/s] for each simulated WR system.
    """
    N = sim_cfg.n_stars

    # Decide which systems are binaries
    is_binary = rng.random(N) < f_bin
    idx_bin = np.where(is_binary)[0]
    idx_single = np.where(~is_binary)[0]
    n_bin = idx_bin.size

    # Draw a time array for each system: this uses cadence_library if provided
    times_list = sim_cfg.sample_times_for_systems(N, rng)

    # Output array
    delta_all = np.zeros(N, dtype=float)

    # ------------------------------------------------------------------
    # Singles: RVs are Gaussian around v_sys with sigma_single + sigma_measure
    # ------------------------------------------------------------------
    sigma_single_total = math.sqrt(sim_cfg.sigma_single**2 + sim_cfg.sigma_measure**2)

    for k in idx_single:
        t = times_list[k]
        if t.size < 2:
            delta_all[k] = 0.0
            continue

        v = rng.normal(
            loc=sim_cfg.v_sys,
            scale=sigma_single_total,
            size=t.size,
        )
        delta_all[k] = v.max() - v.min()

    # ------------------------------------------------------------------
    # Binaries
    # ------------------------------------------------------------------
    if n_bin > 0:
        # Draw orbital parameters for all binaries (vectorized)
        logP = sample_logP(size=n_bin, rng=rng, pi=pi, cfg=bin_cfg)
        P_days = 10.0 ** logP

        e = sample_eccentricity(bin_cfg, n_bin, rng)
        M1 = sample_primary_mass(bin_cfg, n_bin, rng)
        q = sample_mass_ratio(bin_cfg, n_bin, rng)
        M2 = M1 * q
        i = sample_inclination(n_bin, rng)
        omega = rng.uniform(0.0, 2.0 * np.pi, size=n_bin)
        M0 = rng.uniform(0.0, 2.0 * np.pi, size=n_bin)

        K1 = compute_K1(P_days=P_days, e=e, M1=M1, M2=M2, i_rad=i)

        # Loop over binaries, but orbital params are already drawn
        for j, k in enumerate(idx_bin):
            t = times_list[k]
            if t.size < 2:
                delta_all[k] = 0.0
                continue

            # Mean anomaly at each epoch
            M_mean = M0[j] + 2.0 * np.pi * (t / P_days[j])

            # Solve Kepler for this system
            E = solve_kepler(M_mean, e[j])
            tan_halfE = np.tan(E / 2.0)
            sqrt_factor = np.sqrt((1.0 + e[j]) / (1.0 - e[j]))
            nu = 2.0 * np.arctan2(sqrt_factor * tan_halfE, 1.0)

            # RV curve of star 1 (WR): v = gamma + K1[cos(ω+ν) + e cos ω]
            v = sim_cfg.v_sys + K1[j] * (
                np.cos(omega[j] + nu) + e[j] * np.cos(omega[j])
            )

            # Add measurement noise (per epoch)
            if sim_cfg.sigma_measure > 0.0:
                v += rng.normal(
                    loc=0.0,
                    scale=sim_cfg.sigma_measure,
                    size=t.size,
                )

            delta_all[k] = v.max() - v.min()

    return delta_all



# ---------------------------------------------------------------------------
# K-S comparison
# ---------------------------------------------------------------------------

def ks_two_sample(
    sim_data: np.ndarray,
    obs_data: np.ndarray,
) -> Tuple[float, float]:
    """
    Two-sample Kolmogorov-Smirnov test between simulated and observed ΔRV.

    Returns (D, p_value). If SciPy is available, we use scipy.stats.ks_2samp;
    otherwise we fall back to a simple implementation with an approximate
    p-value.
    """
    sim_data = np.asarray(sim_data, dtype=float)
    obs_data = np.asarray(obs_data, dtype=float)

    # Try SciPy if present
    try:
        from scipy import stats  # type: ignore
        D, p_value = stats.ks_2samp(sim_data, obs_data)
        return float(D), float(p_value)
    except Exception:
        pass

    # Manual K-S computation
    x1 = np.sort(sim_data)
    x2 = np.sort(obs_data)
    n1 = x1.size
    n2 = x2.size

    data_all = np.concatenate([x1, x2])
    cdf1 = np.searchsorted(x1, data_all, side="right") / n1
    cdf2 = np.searchsorted(x2, data_all, side="right") / n2
    D = np.max(np.abs(cdf1 - cdf2))

    # Approximate p-value for large n using the usual Kolmogorov series
    en = math.sqrt(n1 * n2 / (n1 + n2))
    x = (en + 0.12 + 0.11 / en) * D

    # Q_KS(x) ~ 2 * sum_{j=1}^\infty (-1)^{j-1} exp(-2 j^2 x^2)
    term_sum = 0.0
    for j in range(1, 101):
        term = 2.0 * ((-1) ** (j - 1)) * math.exp(-2.0 * (j ** 2) * (x ** 2))
        term_sum += term
        if abs(term) < 1e-8:
            break
    p_value = max(0.0, min(1.0, term_sum))
    return float(D), float(p_value)


# ---------------------------------------------------------------------------
# Grid runner with multiprocessing
# ---------------------------------------------------------------------------

def _single_grid_task(args):
    """Worker for a single (f_bin, pi) point. Defined at top level for pickling."""
    (
        f_bin,
        pi,
        sim_cfg,
        bin_cfg,
        obs_delta_rv,
        period_model,
        seed,
    ) = args

    # ensure period model is set on cfg copy (so we can swap Dsilva vs Langer)
    bin_cfg_local = BinaryParameterConfig(**vars(bin_cfg))
    bin_cfg_local.period_model = period_model

    rng = np.random.default_rng(seed)
    delta_sim = simulate_delta_rv_sample(
        f_bin=f_bin,
        pi=pi,
        sim_cfg=sim_cfg,
        bin_cfg=bin_cfg_local,
        rng=rng,
    )
    D, p = ks_two_sample(delta_sim, obs_delta_rv)
    return f_bin, pi, D, p


def run_bias_grid(
    fbin_values: Iterable[float],
    pi_values: Iterable[float],
    obs_delta_rv: np.ndarray,
    sim_cfg: Optional[SimulationConfig] = None,
    bin_cfg: Optional[BinaryParameterConfig] = None,
    period_model: str = "powerlaw",
    n_processes: Optional[int] = None,
    seed_base: int = 1234,
    use_multiprocessing: bool = True,
) -> Dict[str, np.ndarray]:
    """
    Run a (f_bin, pi) grid of simulations and K-S comparisons.

    Parameters
    ----------
    fbin_values : iterable of float
        Grid of intrinsic binary fractions f_bin (0..1).
    pi_values : iterable of float
        Grid of power-law indices π for the logP distribution. For
        period_model="langer2020", π is ignored but still looped over.
    obs_delta_rv : array-like
        Observed ΔRV values for your WR sample [km/s].
    sim_cfg : SimulationConfig or None
        Simulation configuration; if None, uses default SimulationConfig().
    bin_cfg : BinaryParameterConfig or None
        Binary parameter configuration; if None, uses default BinaryParameterConfig().
    period_model : str
        "powerlaw" or "langer2020".
    n_processes : int or None
        Number of worker processes; if None, mp.Pool chooses.
    seed_base : int
        Base seed; each grid point gets seed = seed_base + idx.
    use_multiprocessing : bool
        If False, run everything serially (useful for debugging).

    Returns
    -------
    result : dict with keys:
        "fbin_grid" : 1D array of f_bin values (sorted as input).
        "pi_grid"   : 1D array of π values (sorted as input).
        "ks_D"      : 2D array [len(fbin_grid), len(pi_grid)] of K-S D.
        "ks_p"      : 2D array of corresponding p-values.
    """
    if sim_cfg is None:
        sim_cfg = SimulationConfig()
    if bin_cfg is None:
        bin_cfg = BinaryParameterConfig()

    fbin_grid = np.array(list(fbin_values), dtype=float)
    pi_grid = np.array(list(pi_values), dtype=float)

    obs_delta_rv = np.asarray(obs_delta_rv, dtype=float)

    tasks = []
    idx = 0
    for fb in fbin_grid:
        for pi in pi_grid:
            tasks.append(
                (
                    float(fb),
                    float(pi),
                    sim_cfg,
                    bin_cfg,
                    obs_delta_rv,
                    period_model,
                    seed_base + idx,
                )
            )
            idx += 1

    if use_multiprocessing and len(tasks) > 1:
        with mp.Pool(processes=n_processes) as pool:
            results = pool.map(_single_grid_task, tasks)
    else:
        results = [_single_grid_task(t) for t in tasks]

    # Pack results into 2D arrays
    n_fb = fbin_grid.size
    n_pi = pi_grid.size
    ks_D = np.empty((n_fb, n_pi), dtype=float)
    ks_p = np.empty((n_fb, n_pi), dtype=float)

    for idx, (fb, pi, D, p) in enumerate(results):
        i_fb = idx // n_pi
        i_pi = idx % n_pi
        ks_D[i_fb, i_pi] = D
        ks_p[i_fb, i_pi] = p

    return {
        "fbin_grid": fbin_grid,
        "pi_grid": pi_grid,
        "ks_D": ks_D,
        "ks_p": ks_p,
    }


# ---------------------------------------------------------------------------
# Plotting helper (optional)
# ---------------------------------------------------------------------------

def plot_ks_heatmap(
    grid_result: Dict[str, np.ndarray],
    use_pvalue: bool = False,
    ax=None,
):
    

    fbin_grid = grid_result["fbin_grid"]
    pi_grid   = grid_result["pi_grid"]
    Z = grid_result["ks_p" if use_pvalue else "ks_D"]

    # rows = f_bin, columns = π  -> meshgrid in that order
    Pi, Fb = np.meshgrid(pi_grid, fbin_grid)  # x = π, y = f_bin

    if ax is None:
        fig, ax = plt.subplots()

    im = ax.pcolormesh(Pi, Fb, Z, shading="auto")
    cbar = plt.colorbar(im, ax=ax)
    cbar.set_label("K-S p-value" if use_pvalue else "K-S D")

    ax.set_xlabel("π (period power-law index)")
    ax.set_ylabel("f_bin")
    ax.set_title("K-S p-value over (f_bin, π)" if use_pvalue
                 else "K-S D over (f_bin, π)")

    return ax

def _find_best_grid_point(
    grid_result: Dict[str, np.ndarray],
    by: str = "p",
) -> Tuple[int, int, float, float]:
    """
    Internal helper: find best (f_bin, pi) indices in the grid.

    Parameters
    ----------
    grid_result : dict
        Output of run_bias_grid.
    by : {"p", "D"}
        If "p": maximize K-S p-value.
        If "D": minimize K-S D statistic.

    Returns
    -------
    i_fb, i_pi : int
        Indices into fbin_grid and pi_grid.
    best_fbin, best_pi : float
        Corresponding parameter values.
    """
    fbin_grid = grid_result["fbin_grid"]
    pi_grid = grid_result["pi_grid"]

    if by.lower() == "p":
        Z = grid_result["ks_p"]
        i_fb, i_pi = np.unravel_index(np.argmax(Z), Z.shape)
    elif by.lower() == "d":
        Z = grid_result["ks_D"]
        i_fb, i_pi = np.unravel_index(np.argmin(Z), Z.shape)
    else:
        raise ValueError("by must be 'p' or 'D'.")

    best_fbin = float(fbin_grid[i_fb])
    best_pi = float(pi_grid[i_pi])
    return i_fb, i_pi, best_fbin, best_pi


def simulate_best_model(
    grid_result: Dict[str, np.ndarray],
    sim_cfg: SimulationConfig,
    bin_cfg: BinaryParameterConfig,
    period_model: str = "powerlaw",
    by: str = "p",
    seed: int = 1234,
) -> Tuple[float, float, np.ndarray]:
    """
    Re-simulate one sample at the best (f_bin, pi) grid point.

    Parameters
    ----------
    grid_result : dict
        Output of run_bias_grid.
    sim_cfg, bin_cfg :
        Same configs used for run_bias_grid.
    period_model : str
        "powerlaw" or "langer2020".
    by : {"p", "D"}
        How to choose the best grid point (max p or min D).
    seed : int
        RNG seed for the new simulation.

    Returns
    -------
    best_fbin, best_pi : float
        Best-fitting grid point.
    delta_rv_sim : ndarray
        Simulated ΔRV sample (one 10k-star population) at that point.
    """
    _, _, best_fbin, best_pi = _find_best_grid_point(grid_result, by=by)

    # Local copy of binary config with correct period_model
    bin_cfg_local = BinaryParameterConfig(**vars(bin_cfg))
    bin_cfg_local.period_model = period_model

    rng = np.random.default_rng(seed)
    delta_rv_sim = simulate_delta_rv_sample(
        f_bin=best_fbin,
        pi=best_pi,
        sim_cfg=sim_cfg,
        bin_cfg=bin_cfg_local,
        rng=rng,
    )
    return best_fbin, best_pi, delta_rv_sim


def plot_best_cdf(
    grid_result: Dict[str, np.ndarray],
    obs_delta_rv: np.ndarray,
    sim_cfg: SimulationConfig,
    bin_cfg: BinaryParameterConfig,
    period_model: str = "powerlaw",
    by: str = "p",
    seed: int = 1234,
    ax=None,
):
    """
    Plot CDF of ΔRV for observations vs the best (f_bin, pi) model.

    Parameters
    ----------
    grid_result : dict
        Output of run_bias_grid.
    obs_delta_rv : array-like
        Observed ΔRV values (one per star).
    sim_cfg, bin_cfg :
        Same configs used for run_bias_grid.
    period_model : str
        "powerlaw" or "langer2020".
    by : {"p", "D"}
        Which K-S statistic to optimise: "p" (max p-value) or "D" (min D).
    seed : int
        RNG seed for re-simulating the best model.
    ax : matplotlib Axes or None
        Optional Axes to draw on.

    Returns
    -------
    ax : matplotlib Axes
    best_fbin, best_pi : float
    """
    

    obs_delta_rv = np.asarray(obs_delta_rv, dtype=float)

    best_fbin, best_pi, delta_rv_sim = simulate_best_model(
        grid_result=grid_result,
        sim_cfg=sim_cfg,
        bin_cfg=bin_cfg,
        period_model=period_model,
        by=by,
        seed=seed,
    )

    # CDFs
    obs_sorted = np.sort(obs_delta_rv)
    sim_sorted = np.sort(delta_rv_sim)

    n_obs = obs_sorted.size
    n_sim = sim_sorted.size

    cdf_obs = np.arange(1, n_obs + 1) / n_obs
    cdf_sim = np.arange(1, n_sim + 1) / n_sim

    if ax is None:
        fig, ax = plt.subplots()

    ax.step(obs_sorted, cdf_obs, where="post", label="Observed", linewidth=2)
    ax.step(
        sim_sorted, cdf_sim, where="post",
        label=f"Best sim (f_bin={best_fbin:.2f}, π={best_pi:.2f})",
        linestyle="--"
    )

    ax.set_xlabel(r"$\Delta \mathrm{RV}\ \mathrm{(km\,s^{-1})}$")
    ax.set_ylabel("CDF")
    ax.set_title(r"$\Delta \mathrm{RV}$ CDF: Observed vs Best Model")
    ax.legend()

    return ax, best_fbin, best_pi


def plot_best_detection_fraction_vs_threshold(
    grid_result: Dict[str, np.ndarray],
    obs_delta_rv: np.ndarray,
    sim_cfg: SimulationConfig,
    bin_cfg: BinaryParameterConfig,
    period_model: str = "powerlaw",
    by: str = "p",
    thresholds: Optional[np.ndarray] = None,
    seed: int = 1234,
    ax=None,
):
    """
    Plot fraction of stars above a ΔRV threshold (a proxy for f_bin)
    as a function of threshold, for both observations and the best model.

    For each threshold T we plot:
        f_obs(T) = N_obs(ΔRV > T) / N_obs
        f_sim(T) = N_sim(ΔRV > T) / N_sim

    Parameters
    ----------
    grid_result : dict
        Output of run_bias_grid.
    obs_delta_rv : array-like
        Observed ΔRV values (one per star).
    sim_cfg, bin_cfg :
        Same configs used for run_bias_grid.
    period_model : str
        "powerlaw" or "langer2020".
    by : {"p", "D"}
        Which K-S statistic to optimise for the best model.
    thresholds : array-like or None
        ΔRV thresholds (km/s). If None, a sensible grid from 0 up to
        max(max(obs), max(sim)) is used.
    seed : int
        RNG seed for re-simulating the best model.
    ax : matplotlib Axes or None
        Optional Axes to draw on.

    Returns
    -------
    ax : matplotlib Axes
    best_fbin, best_pi : float
    """
    

    obs_delta_rv = np.asarray(obs_delta_rv, dtype=float)

    best_fbin, best_pi, delta_rv_sim = simulate_best_model(
        grid_result=grid_result,
        sim_cfg=sim_cfg,
        bin_cfg=bin_cfg,
        period_model=period_model,
        by=by,
        seed=seed,
    )

    if thresholds is None:
        vmax = max(obs_delta_rv.max(), delta_rv_sim.max())
        thresholds = np.linspace(0.0, vmax, 50)
    thresholds = np.asarray(thresholds, dtype=float)

    # Fractions above threshold
    frac_obs = np.array([(obs_delta_rv > T).mean() for T in thresholds])
    frac_sim = np.array([(delta_rv_sim > T).mean() for T in thresholds])

    if ax is None:
        fig, ax = plt.subplots()

    ax.plot(thresholds, frac_obs, label="Observed", linewidth=2)
    ax.plot(
        thresholds, frac_sim, label=f"Best sim (f_bin={best_fbin:.2f}, π={best_pi:.2f})",
        linestyle="--"
    )

    ax.set_xlabel(r"$\Delta \mathrm{RV}$ threshold (km s$^{-1}$)")
    ax.set_ylabel(r"Fraction with $\Delta \mathrm{RV} > T$")
    ax.set_title("Detection fraction vs ΔRV threshold")
    ax.legend()

    return ax, best_fbin, best_pi

def _simulate_rv_sample_full(
    f_bin: float,
    pi: float,
    sim_cfg: SimulationConfig,
    bin_cfg: BinaryParameterConfig,
    rng: np.random.Generator,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Simulate *all RV measurements* for singles and binaries separately.

    Returns
    -------
    rv_single_all : ndarray
        Flattened array of all RV measurements (km/s) for single stars.
    rv_binary_all : ndarray
        Flattened array of all RV measurements (km/s) for binary stars.
    """
    N = sim_cfg.n_stars

    # Decide which systems are binaries
    is_binary = rng.random(N) < f_bin
    idx_bin = np.where(is_binary)[0]
    idx_single = np.where(~is_binary)[0]
    n_bin = idx_bin.size

    # Draw a time array for each system
    times_list = sim_cfg.sample_times_for_systems(N, rng)

    sigma_single_total = math.sqrt(sim_cfg.sigma_single**2 + sim_cfg.sigma_measure**2)

    rv_single_list = []
    rv_bin_list = []

    # Singles
    for k in idx_single:
        t = times_list[k]
        if t.size == 0:
            continue
        v = rng.normal(
            loc=sim_cfg.v_sys,
            scale=sigma_single_total,
            size=t.size,
        )
        rv_single_list.append(v)

    # Binaries
    if n_bin > 0:
        # orbital parameters for all binaries
        logP = sample_logP(size=n_bin, rng=rng, pi=pi, cfg=bin_cfg)
        P_days = 10.0 ** logP

        e = sample_eccentricity(bin_cfg, n_bin, rng)
        M1 = sample_primary_mass(bin_cfg, n_bin, rng)
        q = sample_mass_ratio(bin_cfg, n_bin, rng)
        M2 = M1 * q
        i = sample_inclination(n_bin, rng)
        omega = rng.uniform(0.0, 2.0 * np.pi, size=n_bin)
        M0 = rng.uniform(0.0, 2.0 * np.pi, size=n_bin)

        K1 = compute_K1(P_days=P_days, e=e, M1=M1, M2=M2, i_rad=i)

        for j, k in enumerate(idx_bin):
            t = times_list[k]
            if t.size == 0:
                continue

            M_mean = M0[j] + 2.0 * np.pi * (t / P_days[j])

            E = solve_kepler(M_mean, e[j])
            tan_halfE = np.tan(E / 2.0)
            sqrt_factor = np.sqrt((1.0 + e[j]) / (1.0 - e[j]))
            nu = 2.0 * np.arctan2(sqrt_factor * tan_halfE, 1.0)

            v = sim_cfg.v_sys + K1[j] * (
                np.cos(omega[j] + nu) + e[j] * np.cos(omega[j])
            )

            if sim_cfg.sigma_measure > 0.0:
                v += rng.normal(
                    loc=0.0,
                    scale=sim_cfg.sigma_measure,
                    size=t.size,
                )

            rv_bin_list.append(v)

    if rv_single_list:
        rv_single_all = np.concatenate(rv_single_list)
    else:
        rv_single_all = np.empty(0, dtype=float)

    if rv_bin_list:
        rv_binary_all = np.concatenate(rv_bin_list)
    else:
        rv_binary_all = np.empty(0, dtype=float)

    return rv_single_all, rv_binary_all


def simulate_best_rv_distributions(
    grid_result: Dict[str, np.ndarray],
    sim_cfg: SimulationConfig,
    bin_cfg: BinaryParameterConfig,
    period_model: str = "powerlaw",
    by: str = "p",
    seed: int = 1234,
) -> Tuple[float, float, np.ndarray, np.ndarray]:
    """
    For the best (f_bin, pi) in the grid, simulate all RVs and split
    them into singles vs binaries.

    Parameters
    ----------
    grid_result : dict
        Output of run_bias_grid.
    sim_cfg, bin_cfg :
        Same configs used for run_bias_grid.
    period_model : str
        "powerlaw" or "langer2020".
    by : {"p", "D"}
        Optimise by maximum K-S p-value ("p") or minimum D ("D").
    seed : int
        RNG seed for the simulation.

    Returns
    -------
    best_fbin, best_pi : float
    rv_single_all : ndarray
        All RV samples for single stars (km/s).
    rv_binary_all : ndarray
        All RV samples for binaries (km/s).
    """
    _, _, best_fbin, best_pi = _find_best_grid_point(grid_result, by=by)

    bin_cfg_local = BinaryParameterConfig(**vars(bin_cfg))
    bin_cfg_local.period_model = period_model

    rng = np.random.default_rng(seed)
    rv_single_all, rv_binary_all = _simulate_rv_sample_full(
        f_bin=best_fbin,
        pi=best_pi,
        sim_cfg=sim_cfg,
        bin_cfg=bin_cfg_local,
        rng=rng,
    )

    return best_fbin, best_pi, rv_single_all, rv_binary_all


def plot_best_rv_distributions(
    grid_result: Dict[str, np.ndarray],
    sim_cfg: SimulationConfig,
    bin_cfg: BinaryParameterConfig,
    period_model: str = "powerlaw",
    by: str = "p",
    seed: int = 1234,
    bins: Optional[int] = 40,
    ax=None,
):
    """
    Plot the RV distributions of single stars and binaries for the best
    (f_bin, pi) combination.

    Parameters
    ----------
    grid_result : dict
        Output of run_bias_grid.
    sim_cfg, bin_cfg :
        Same configs used for run_bias_grid.
    period_model : str
        "powerlaw" or "langer2020".
    by : {"p", "D"}
        Optimise by maximum K-S p-value ("p") or minimum D ("D").
    seed : int
        RNG seed for the simulation.
    bins : int or None
        Number of histogram bins. If None, matplotlib's default is used.
    ax : matplotlib Axes or None
        Optional Axes to draw on.

    Returns
    -------
    ax : matplotlib Axes
    best_fbin, best_pi : float
    """
    

    best_fbin, best_pi, rv_single_all, rv_binary_all = simulate_best_rv_distributions(
        grid_result=grid_result,
        sim_cfg=sim_cfg,
        bin_cfg=bin_cfg,
        period_model=period_model,
        by=by,
        seed=seed,
    )

    # Combine all RVs to define a common binning
    if rv_single_all.size > 0 and rv_binary_all.size > 0:
        all_rv = np.concatenate([rv_single_all, rv_binary_all])
    elif rv_single_all.size > 0:
        all_rv = rv_single_all
    elif rv_binary_all.size > 0:
        all_rv = rv_binary_all
    else:
        raise RuntimeError("No RV samples generated for singles or binaries.")

    if isinstance(bins, int):
        rv_min = all_rv.min()
        rv_max = all_rv.max()
        bin_edges = np.linspace(rv_min, rv_max, bins + 1)
    else:
        bin_edges = bins  # user-specified array or None

    if ax is None:
        fig, ax = plt.subplots()

    # Normalised histograms (PDF-like)
    if rv_single_all.size > 0:
        ax.hist(
            rv_single_all,
            bins=bin_edges,
            density=True,
            histtype="step",
            label="Singles",
        )
    if rv_binary_all.size > 0:
        ax.hist(
            rv_binary_all,
            bins=bin_edges,
            density=True,
            histtype="step",
            linestyle="--",
            label=f"Binaries (f_bin={best_fbin:.2f}, π={best_pi:.2f})",
        )

    ax.set_xlabel(r"RV (km s$^{-1}$)")
    ax.set_ylabel("Normalised counts")
    ax.set_title("RV distribution: singles vs binaries (best model)")
    ax.legend()

    return ax, best_fbin, best_pi
