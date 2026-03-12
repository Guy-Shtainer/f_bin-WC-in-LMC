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
try:
    from tqdm.auto import tqdm
except ImportError:
    tqdm = None

# Physical constants (SI)
G_SI = 6.67430e-11        # m^3 kg^-1 s^-2
M_SUN = 1.98847e30        # kg
DAY_S = 86400.0           # s/day

# Default bin edges for binned CDF K-S comparison (delta-RV in km/s)
DEFAULT_DRV_BIN_EDGES = np.arange(0.0, 360.0, 10.0)  # [0, 10, 20, ..., 350]


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

    def _build_cadence_cache(self):
        """
        Pre-convert cadence_library to numpy arrays and normalise weights once.
        Results are cached on the instance so repeated grid-point calls pay no cost.
        """
        if hasattr(self, '_cadence_lib_cache'):
            return  # already built
        lib = [np.asarray(t, dtype=float) for t in self.cadence_library]
        if any(t.ndim != 1 for t in lib):
            raise ValueError("All cadence_library entries must be 1-D arrays.")
        if self.cadence_weights is None:
            weights = np.ones(len(lib), dtype=float)
        else:
            weights = np.asarray(self.cadence_weights, dtype=float)
        weights = weights / weights.sum()
        self._cadence_lib_cache = lib
        self._cadence_weights_cache = weights

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

        # Build cache once, reuse across all grid-point calls
        self._build_cadence_cache()
        idx = rng.choice(len(self._cadence_lib_cache), size=n_systems, replace=True,
                         p=self._cadence_weights_cache)
        return [self._cadence_lib_cache[i] for i in idx]

    def assign_times_deterministic(self) -> list[np.ndarray]:
        """Return cadence_library entries in order (star i -> cadence i).

        Used by cadence-aware simulation where each simulated star is
        matched to a specific real star's observation cadence.
        """
        if self.cadence_library is None:
            raise ValueError("cadence_library must be set for deterministic assignment.")
        self._build_cadence_cache()
        return list(self._cadence_lib_cache)


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
        "flat"      -> q ~ U[q_range[0], q_range[1]].
        "langer"    -> Gaussian approximation to Langer+2020 BH/OB
                       mass-ratio distribution; tune langer_q_mu/sigma.
        "lognormal" -> log-normal with mode = langer_q_mu, shape = langer_q_sigma.
                       Right-skewed (rises fast, drops slow).
        "reflected_lognormal" -> mirrored log-normal around the mode.
                       Left-skewed (rises slow, drops fast).
        "empirical"  -> directly sample from digitized Langer+2020 Fig. 4
                       histogram (ignores langer_q_mu/sigma).
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
    q_flipped: bool = False  # if True, M2 = M1/q instead of M1*q


# ---------------------------------------------------------------------------
# Digitized Langer+2020 histograms (combined Case A + B + non-interacting)
# ---------------------------------------------------------------------------

# Fig. 4: M_BH / M_OB — mass ratio distribution
LANGER_Q_BIN_EDGES = np.array([
    0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0,
    1.125, 1.25, 1.375, 1.5, 1.625, 1.75])
LANGER_Q_WEIGHTS = np.array([
    0.010, 0.045, 0.150, 0.148, 0.140, 0.110,
    0.080, 0.058, 0.040, 0.030, 0.022, 0.022])

# Fig. 6: log₁₀(P/days) — orbital period distribution
LANGER_LOGP_BIN_EDGES = np.array([
    0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75,
    2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5])
LANGER_LOGP_WEIGHTS = np.array([
    0.002,   # [0.25, 0.50]
    0.010,   # [0.50, 0.75] — Case A rising
    0.035,   # [0.75, 1.00] — Case A PEAK (local max)
    0.025,   # [1.00, 1.25] — DIP between peaks
    0.038,   # [1.25, 1.50] — Case B rising
    0.050,   # [1.50, 1.75]
    0.060,   # [1.75, 2.00]
    0.068,   # [2.00, 2.25] — Case B PEAK
    0.065,   # [2.25, 2.50]
    0.042,   # [2.50, 2.75]
    0.018,   # [2.75, 3.00]
    0.005,   # [3.00, 3.25]
    0.012])  # [3.25, 3.50] — non-interacting bump


def _sample_empirical(
    bin_edges: np.ndarray, weights: np.ndarray,
    size: int, rng: np.random.Generator,
) -> np.ndarray:
    """Sample from a piecewise-constant PDF defined by bin edges + weights."""
    probs = weights / weights.sum()
    bin_idx = rng.choice(len(probs), size=size, p=probs)
    lo = bin_edges[bin_idx]
    hi = bin_edges[bin_idx + 1]
    return rng.uniform(lo, hi)


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


def _sample_single_component(
    rng: np.random.Generator, dist: str, mu: float, sigma: float,
    logP_min: float, logP_max: float, size: int,
) -> np.ndarray:
    """Sample from a single parametric distribution, clipped to [logP_min, logP_max]."""
    d = dist.lower()
    if d == "gaussian":
        return rng.normal(loc=mu, scale=sigma, size=size)
    elif d == "lognormal":
        # Mode-based: mode = mu, internally ln(x) ~ N(mu_ln, sigma)
        mu_ln = np.log(mu) + sigma ** 2
        return rng.lognormal(mean=mu_ln, sigma=sigma, size=size)
    elif d == "reflected_lognormal":
        # Left-skewed: rises slowly, drops fast after peak.
        # Mirror a log-normal around its mode (mu).
        mu_ln = np.log(mu) + sigma ** 2
        x = rng.lognormal(mean=mu_ln, sigma=sigma, size=size)
        return 2 * mu - x
    elif d == "empirical":
        return _sample_empirical(LANGER_LOGP_BIN_EDGES, LANGER_LOGP_WEIGHTS,
                                  size, rng)
    elif d == "flat":
        return rng.uniform(logP_min, logP_max, size=size)
    else:
        raise ValueError(f"Unknown component distribution: {dist}")


def sample_logP_langer2020(
    size: int,
    rng: np.random.Generator,
    dist_A: str = "gaussian",
    mu_A: float = 0.80,
    sigma_A: float = 0.35,
    dist_B: str = "reflected_lognormal",
    mu_B: float = 2.0,
    sigma_B: float = 0.45,
    weight_A: float = 0.20,
    logP_min: float = 0.5,
    logP_max: float = 3.5,
    return_components: bool = False,
    **_ignored,
) -> "np.ndarray | tuple":
    """
    Two-component mixture approximation to Langer+2020 Fig. 6 (combined).

    Each component can be 'gaussian', 'lognormal', or 'flat':
    - Component 1 (short-period): default Gaussian, peak ~6 d.
    - Component 2 (long-period): default log-normal (mode-based), peak ~100 d.

    The total distribution is the weighted sum of both components.
    """
    u = rng.random(size)
    logP = np.empty(size, dtype=float)

    mask_A = u < weight_A
    mask_B = ~mask_A
    n_A = int(mask_A.sum())
    n_B = int(mask_B.sum())

    if n_A > 0:
        logP[mask_A] = _sample_single_component(
            rng, dist_A, mu_A, sigma_A, logP_min, logP_max, n_A)
    if n_B > 0:
        logP[mask_B] = _sample_single_component(
            rng, dist_B, mu_B, sigma_B, logP_min, logP_max, n_B)

    logP = np.clip(logP, logP_min, logP_max)
    if return_components:
        return logP, mask_A
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
        # Gaussian approximation to Langer+2020 BH/OB mass ratios.
        q = rng.normal(loc=cfg.langer_q_mu, scale=cfg.langer_q_sigma, size=size)
        qmin, qmax = cfg.q_range
        return np.clip(q, qmin, qmax)
    elif mode == "lognormal":
        # Log-normal with mode = langer_q_mu, shape = langer_q_sigma.
        mu_ln = np.log(cfg.langer_q_mu) + cfg.langer_q_sigma ** 2
        q = rng.lognormal(mean=mu_ln, sigma=cfg.langer_q_sigma, size=size)
        qmin, qmax = cfg.q_range
        return np.clip(q, qmin, qmax)
    elif mode == "reflected_lognormal":
        # Left-skewed: rises slowly, drops fast after peak (mode = langer_q_mu).
        mu_ln = np.log(cfg.langer_q_mu) + cfg.langer_q_sigma ** 2
        x = rng.lognormal(mean=mu_ln, sigma=cfg.langer_q_sigma, size=size)
        q = 2 * cfg.langer_q_mu - x
        qmin, qmax = cfg.q_range
        return np.clip(q, qmin, qmax)
    elif mode == "empirical":
        # Directly sample from digitized Langer+2020 Fig. 4 histogram.
        q = _sample_empirical(LANGER_Q_BIN_EDGES, LANGER_Q_WEIGHTS, size, rng)
        qmin, qmax = cfg.q_range
        return np.clip(q, qmin, qmax)
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


def sample_logP_langer_single(
    size: int,
    rng: np.random.Generator,
    distribution: str = "lognormal",
    mu: float = 2.0,
    sigma: float = 0.45,
    logP_min: float = 0.5,
    logP_max: float = 3.5,
    **_ignored,
) -> np.ndarray:
    """
    Single parametric distribution for logP, fitting the combined
    Langer+2020 Fig. 6 shape (Case A + Case B treated as one distribution).

    Parameters
    ----------
    distribution : str
        "flat"      -> logP ~ U[logP_min, logP_max]
        "gaussian"  -> logP ~ N(mu, sigma), clipped
        "lognormal" -> log-normal with mode = mu in logP space, clipped
    mu : float
        Mean (Gaussian) or mode (log-normal) of the distribution.
    sigma : float
        Std dev (Gaussian) or shape parameter (log-normal).
    """
    dist = distribution.lower()
    if dist == "flat":
        return rng.uniform(logP_min, logP_max, size=size)
    elif dist == "gaussian":
        logP = rng.normal(loc=mu, scale=sigma, size=size)
        return np.clip(logP, logP_min, logP_max)
    elif dist == "lognormal":
        # Log-normal in logP: mode = mu, right-skewed.
        # Internal: ln(logP) ~ N(mu_ln, sigma) where mu_ln = ln(mu) + sigma^2
        mu_ln = np.log(mu) + sigma ** 2
        logP = rng.lognormal(mean=mu_ln, sigma=sigma, size=size)
        return np.clip(logP, logP_min, logP_max)
    else:
        raise ValueError(f"Unknown logP distribution: {distribution}")


def sample_logP(
    size: int,
    rng: np.random.Generator,
    pi: float,
    cfg: BinaryParameterConfig,
    return_components: bool = False,
) -> "np.ndarray | tuple":
    """Dispatch to the requested period model.

    When *return_components* is True, returns ``(logP, case_A_mask)`` where
    *case_A_mask* is a boolean array (True = Case A origin) for Langer, or
    None for other models.
    """
    model = cfg.period_model.lower()
    if model == "powerlaw":
        logP = sample_logP_powerlaw(pi, size, cfg.logP_min, cfg.logP_max, rng)
        return (logP, None) if return_components else logP
    elif model == "langer2020":
        params = dict(cfg.langer_period_params)  # copy
        # allow overriding logP_min/max via params, but fall back to cfg if absent
        params.setdefault("logP_min", cfg.logP_min)
        params.setdefault("logP_max", cfg.logP_max)
        # New single-distribution mode (has 'distribution' key)
        if "distribution" in params:
            logP = sample_logP_langer_single(size=size, rng=rng, **params)
            return (logP, None) if return_components else logP
        # Legacy: Case A/B mixture
        if return_components:
            return sample_logP_langer2020(size=size, rng=rng,
                                          return_components=True, **params)
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
    # Singles: group by cadence length and draw all RVs in one batch
    # ------------------------------------------------------------------
    # Build a map: cadence_length -> list of system indices
    single_groups: dict = {}
    single_skip = []
    for k in idx_single:
        n_ep = times_list[k].size
        if n_ep < 2:
            single_skip.append(k)
        else:
            single_groups.setdefault(n_ep, []).append(k)

    for n_ep, ks in single_groups.items():
        n_stars_grp = len(ks)
        # Draw all RVs for this group in one call: shape (n_stars_grp, n_ep)
        v = rng.normal(
            loc=sim_cfg.v_sys,
            scale=sim_cfg.sigma_single,
            size=(n_stars_grp, n_ep),
        )
        drv = v.max(axis=1) - v.min(axis=1)
        for idx_in_grp, k in enumerate(ks):
            delta_all[k] = drv[idx_in_grp]

    # ------------------------------------------------------------------
    # Binaries: draw all orbital parameters at once (already vectorized),
    # then group by cadence length to batch Kepler solver
    # ------------------------------------------------------------------
    if n_bin > 0:
        logP = sample_logP(size=n_bin, rng=rng, pi=pi, cfg=bin_cfg)
        P_days = 10.0 ** logP

        e    = sample_eccentricity(bin_cfg, n_bin, rng)
        M1   = sample_primary_mass(bin_cfg, n_bin, rng)
        q    = sample_mass_ratio(bin_cfg, n_bin, rng)
        M2   = M1 / q if bin_cfg.q_flipped else M1 * q
        i    = sample_inclination(n_bin, rng)
        omega = rng.uniform(0.0, 2.0 * np.pi, size=n_bin)
        T0    = rng.uniform(0.0, 2.0 * np.pi, size=n_bin)

        K1 = compute_K1(P_days=P_days, e=e, M1=M1, M2=M2, i_rad=i)

        # Group binaries by cadence length so Kepler can be solved in batches
        # bin_groups: cadence_length -> list of (j, k) where j = index into
        # binary param arrays, k = index into delta_all
        bin_groups: dict = {}
        for j, k in enumerate(idx_bin):
            n_ep = times_list[k].size
            if n_ep < 2:
                delta_all[k] = 0.0
            else:
                bin_groups.setdefault(n_ep, []).append((j, k))

        for n_ep, jk_list in bin_groups.items():
            js = np.array([x[0] for x in jk_list])
            ks = np.array([x[1] for x in jk_list])
            n_grp = len(js)

            # Stack time arrays: shape (n_grp, n_ep)  — all same length in this group
            t_mat = np.vstack([times_list[k] for k in ks])  # (n_grp, n_ep)

            # Mean anomaly: (n_grp, n_ep)
            M_mean = T0[js, None] + 2.0 * np.pi * (t_mat / P_days[js, None])

            # Solve Kepler for the whole batch at once
            # e[js] is shape (n_grp,); broadcast to (n_grp, n_ep)
            E = solve_kepler(M_mean, e[js, None])

            sqrt_fac = np.sqrt((1.0 + e[js, None]) / (1.0 - e[js, None]))
            nu = 2.0 * np.arctan2(sqrt_fac * np.tan(E / 2.0), 1.0)

            # RV curve: (n_grp, n_ep)
            v = sim_cfg.v_sys + K1[js, None] * (
                np.cos(omega[js, None] + nu) + e[js, None] * np.cos(omega[js, None])
            )

            drv = v.max(axis=1) - v.min(axis=1)
            delta_all[ks] = drv

    return delta_all


# ---------------------------------------------------------------------------
# Cadence-aware simulation: N_sets x N_stars_per_set
# ---------------------------------------------------------------------------

def simulate_delta_rv_cadence_aware(
    f_bin: float,
    pi: float,
    sim_cfg: SimulationConfig,
    bin_cfg: BinaryParameterConfig,
    rng: np.random.Generator,
    n_sets: int = 10_000,
    bin_edges: np.ndarray | None = None,
) -> dict:
    """Cadence-aware simulation: *n_sets* repetitions of *N_stars* sets.

    Each set contains exactly ``len(sim_cfg.cadence_library)`` simulated stars,
    where star *i* always receives cadence *i* (the real observation cadence of
    the *i*-th star in the sample).  This is repeated *n_sets* times.

    For each set, the binned CDF is computed.  Across sets we report the median
    and 16th/84th percentile envelope.

    Returns
    -------
    dict with keys ``median_cdf``, ``lo_cdf``, ``hi_cdf``, ``all_delta_rv``.
    """
    if bin_edges is None:
        bin_edges = DEFAULT_DRV_BIN_EDGES

    cadences = sim_cfg.assign_times_deterministic()
    n_stars_per_set = len(cadences)
    N_total = n_sets * n_stars_per_set

    # Binary / single decision for every system
    is_binary = rng.random(N_total) < f_bin
    idx_bin = np.where(is_binary)[0]
    idx_single = np.where(~is_binary)[0]
    n_bin = idx_bin.size

    # Assign cadences deterministically: system s*25+i gets cadence i
    times_list: list[np.ndarray] = [cadences[k % n_stars_per_set] for k in range(N_total)]

    delta_all = np.zeros(N_total, dtype=float)

    # Singles: group by cadence length, batch-draw RVs
    single_groups: dict[int, list[int]] = {}
    for k in idx_single:
        n_ep = times_list[k].size
        if n_ep >= 2:
            single_groups.setdefault(n_ep, []).append(k)

    for n_ep, ks_list in single_groups.items():
        n_grp = len(ks_list)
        v = rng.normal(loc=sim_cfg.v_sys, scale=sim_cfg.sigma_single,
                       size=(n_grp, n_ep))
        drv = v.max(axis=1) - v.min(axis=1)
        delta_all[np.array(ks_list)] = drv

    # Binaries: draw orbital params, group by cadence length
    if n_bin > 0:
        logP = sample_logP(size=n_bin, rng=rng, pi=pi, cfg=bin_cfg)
        P_days = 10.0 ** logP
        e    = sample_eccentricity(bin_cfg, n_bin, rng)
        M1   = sample_primary_mass(bin_cfg, n_bin, rng)
        q    = sample_mass_ratio(bin_cfg, n_bin, rng)
        M2   = M1 / q if bin_cfg.q_flipped else M1 * q
        i_inc = sample_inclination(n_bin, rng)
        omega = rng.uniform(0.0, 2.0 * np.pi, size=n_bin)
        T0    = rng.uniform(0.0, 2.0 * np.pi, size=n_bin)
        K1    = compute_K1(P_days=P_days, e=e, M1=M1, M2=M2, i_rad=i_inc)

        bin_groups: dict[int, list[tuple[int, int]]] = {}
        for j, k in enumerate(idx_bin):
            n_ep = times_list[k].size
            if n_ep < 2:
                delta_all[k] = 0.0
            else:
                bin_groups.setdefault(n_ep, []).append((j, k))

        for n_ep, jk_list in bin_groups.items():
            js = np.array([x[0] for x in jk_list])
            ks_arr = np.array([x[1] for x in jk_list])
            n_grp = len(js)

            t_mat = np.vstack([times_list[k] for k in ks_arr])
            M_mean = T0[js, None] + 2.0 * np.pi * (t_mat / P_days[js, None])
            E = solve_kepler(M_mean, e[js, None])
            sqrt_fac = np.sqrt((1.0 + e[js, None]) / (1.0 - e[js, None]))
            nu = 2.0 * np.arctan2(sqrt_fac * np.tan(E / 2.0), 1.0)
            v = sim_cfg.v_sys + K1[js, None] * (
                np.cos(omega[js, None] + nu) + e[js, None] * np.cos(omega[js, None])
            )
            drv = v.max(axis=1) - v.min(axis=1)
            delta_all[ks_arr] = drv

    # Reshape to (n_sets, n_stars_per_set) and compute per-set CDFs
    all_drv = delta_all.reshape(n_sets, n_stars_per_set)
    n_bins = len(bin_edges)
    all_cdfs = np.empty((n_sets, n_bins), dtype=float)
    for s in range(n_sets):
        all_cdfs[s] = binned_cdf(all_drv[s], bin_edges)

    median_cdf = np.median(all_cdfs, axis=0)
    lo_cdf = np.percentile(all_cdfs, 16, axis=0)
    hi_cdf = np.percentile(all_cdfs, 84, axis=0)
    cdf_var = np.var(all_cdfs, axis=0)

    return {
        'median_cdf': median_cdf,
        'lo_cdf': lo_cdf,
        'hi_cdf': hi_cdf,
        'cdf_var': cdf_var,
        'all_delta_rv': all_drv,
    }


def simulate_with_params(
    f_bin: float,
    pi: float,
    sim_cfg: SimulationConfig,
    bin_cfg: BinaryParameterConfig,
    rng: np.random.Generator,
) -> dict:
    """
    Like simulate_delta_rv_sample but also returns per-system orbital parameters.

    Returns
    -------
    dict with keys:
        delta_rv   : ndarray (N,)      — peak-to-peak ΔRV for every system
        is_binary  : ndarray (N,) bool  — True if the system is a binary
        P_days     : ndarray (n_bin,)   — orbital period [days], binaries only
        e          : ndarray (n_bin,)   — eccentricity, binaries only
        q          : ndarray (n_bin,)   — mass ratio M2/M1, binaries only
        i_rad      : ndarray (n_bin,)   — inclination [rad], binaries only
        K1         : ndarray (n_bin,)   — RV semi-amplitude [km/s], binaries only
        M1         : ndarray (n_bin,)   — primary mass [M_sun], binaries only
        idx_bin    : ndarray (n_bin,)   — indices of binaries into the delta_rv array
    """
    N = sim_cfg.n_stars

    is_binary = rng.random(N) < f_bin
    idx_bin = np.where(is_binary)[0]
    idx_single = np.where(~is_binary)[0]
    n_bin = idx_bin.size

    times_list = sim_cfg.sample_times_for_systems(N, rng)
    delta_all = np.zeros(N, dtype=float)

    # Singles
    single_groups: dict = {}
    for k in idx_single:
        n_ep = times_list[k].size
        if n_ep >= 2:
            single_groups.setdefault(n_ep, []).append(k)

    for n_ep, ks in single_groups.items():
        n_stars_grp = len(ks)
        v = rng.normal(loc=sim_cfg.v_sys, scale=sim_cfg.sigma_single,
                       size=(n_stars_grp, n_ep))
        drv = v.max(axis=1) - v.min(axis=1)
        for idx_in_grp, k in enumerate(ks):
            delta_all[k] = drv[idx_in_grp]

    # Binaries — keep orbital params
    out_P = np.array([])
    out_e = np.array([])
    out_q = np.array([])
    out_i = np.array([])
    out_K1 = np.array([])
    out_M1 = np.array([])
    out_case_A = None

    if n_bin > 0:
        logP, case_A_mask = sample_logP(size=n_bin, rng=rng, pi=pi, cfg=bin_cfg,
                                         return_components=True)
        out_case_A = case_A_mask
        P_days = 10.0 ** logP

        e    = sample_eccentricity(bin_cfg, n_bin, rng)
        M1   = sample_primary_mass(bin_cfg, n_bin, rng)
        q    = sample_mass_ratio(bin_cfg, n_bin, rng)
        M2   = M1 / q if bin_cfg.q_flipped else M1 * q
        i    = sample_inclination(n_bin, rng)
        omega = rng.uniform(0.0, 2.0 * np.pi, size=n_bin)
        T0    = rng.uniform(0.0, 2.0 * np.pi, size=n_bin)

        K1 = compute_K1(P_days=P_days, e=e, M1=M1, M2=M2, i_rad=i)

        bin_groups: dict = {}
        for j, k in enumerate(idx_bin):
            n_ep = times_list[k].size
            if n_ep < 2:
                delta_all[k] = 0.0
            else:
                bin_groups.setdefault(n_ep, []).append((j, k))

        for n_ep, jk_list in bin_groups.items():
            js = np.array([x[0] for x in jk_list])
            ks = np.array([x[1] for x in jk_list])

            t_mat = np.vstack([times_list[k] for k in ks])
            M_mean = T0[js, None] + 2.0 * np.pi * (t_mat / P_days[js, None])
            E = solve_kepler(M_mean, e[js, None])
            sqrt_fac = np.sqrt((1.0 + e[js, None]) / (1.0 - e[js, None]))
            nu = 2.0 * np.arctan2(sqrt_fac * np.tan(E / 2.0), 1.0)

            v = sim_cfg.v_sys + K1[js, None] * (
                np.cos(omega[js, None] + nu) + e[js, None] * np.cos(omega[js, None])
            )
            drv = v.max(axis=1) - v.min(axis=1)
            delta_all[ks] = drv

        out_P = P_days
        out_e = e
        out_q = q
        out_i = i
        out_K1 = K1
        out_M1 = M1

    return {
        'delta_rv': delta_all,
        'is_binary': is_binary,
        'P_days': out_P,
        'e': out_e,
        'q': out_q,
        'i_rad': out_i,
        'K1': out_K1,
        'M1': out_M1,
        'omega': omega,   # argument of periapsis (rad)
        'T0': T0,         # periastron phase (rad)
        'idx_bin': idx_bin,
        'case_A_mask': out_case_A,  # bool array (n_bin,) or None
    }


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
# Binned CDF K-S comparison
# ---------------------------------------------------------------------------

def binned_cdf(data: np.ndarray, bin_edges: np.ndarray) -> np.ndarray:
    """Empirical CDF evaluated at *bin_edges*: CDF(x) = fraction of data <= x."""
    sorted_data = np.sort(data)
    return np.searchsorted(sorted_data, bin_edges, side='right') / len(sorted_data)


def ks_two_sample_binned(
    sim_data: np.ndarray,
    obs_data: np.ndarray,
    bin_edges: np.ndarray | None = None,
) -> Tuple[float, float]:
    """Binned K-S test: D = max|CDF_sim(b) - CDF_obs(b)| over *bin_edges*.

    Uses the same Kolmogorov-series p-value approximation as ks_two_sample
    with effective sample sizes n1=len(sim_data), n2=len(obs_data).
    """
    if bin_edges is None:
        bin_edges = DEFAULT_DRV_BIN_EDGES

    sim_data = np.asarray(sim_data, dtype=float)
    obs_data = np.asarray(obs_data, dtype=float)
    n1 = sim_data.size
    n2 = obs_data.size

    cdf_sim = binned_cdf(sim_data, bin_edges)
    cdf_obs = binned_cdf(obs_data, bin_edges)
    D = float(np.max(np.abs(cdf_sim - cdf_obs)))

    # Approximate p-value (Kolmogorov series)
    en = math.sqrt(n1 * n2 / (n1 + n2))
    x = (en + 0.12 + 0.11 / en) * D
    term_sum = 0.0
    for j in range(1, 101):
        term = 2.0 * ((-1) ** (j - 1)) * math.exp(-2.0 * (j ** 2) * (x ** 2))
        term_sum += term
        if abs(term) < 1e-8:
            break
    p_value = max(0.0, min(1.0, term_sum))
    return D, p_value


def ks_weighted_D(
    sim_median_cdf: np.ndarray,
    obs_cdf: np.ndarray,
    sim_cdf_var: np.ndarray,
) -> float:
    """Inverse-variance weighted K-S D statistic.

    D_w = Σ(|sim_i - obs_i| × w_i) / Σ(w_i)

    where w_i = 1/σ_i² and σ_i² is the simulation CDF variance at bin i
    (across all N_sets repetitions).  Bins where σ_i² ≈ 0 are skipped.

    This down-weights bins where the simulation is uncertain (wide 16-84%
    band), giving more influence to bins with tightly constrained CDFs.
    The result stays in [0, 1] so the standard Kolmogorov p-value applies.
    """
    sim_median_cdf = np.asarray(sim_median_cdf, dtype=float)
    obs_cdf = np.asarray(obs_cdf, dtype=float)
    sim_cdf_var = np.asarray(sim_cdf_var, dtype=float)

    valid = sim_cdf_var > 1e-12
    if valid.sum() < 2:
        # Fallback to standard D if too few informative bins
        return float(np.max(np.abs(sim_median_cdf - obs_cdf)))
    w = 1.0 / sim_cdf_var[valid]
    diffs = np.abs(sim_median_cdf[valid] - obs_cdf[valid])
    return float(np.sum(diffs * w) / np.sum(w))


# ---------------------------------------------------------------------------
# Marginalization & HDI68 credible intervals (Dsilva et al. 2023 style)
# ---------------------------------------------------------------------------

def compute_hdi68(
    x_vals: np.ndarray,
    posterior_1d: np.ndarray,
) -> Tuple[float, float, float]:
    """
    Compute the mode and 68% Highest Density Interval from a 1D posterior.

    Following Dsilva et al. (2023): the posterior is the marginalized K-S
    p-value curve (summed over other dimensions and normalized). The HDI
    is found by lowering a horizontal line from the mode until the enclosed
    area under the curve equals 68% of the total area.

    Parameters
    ----------
    x_vals : 1D array
        Parameter grid values (e.g., f_bin values).
    posterior_1d : 1D array
        Marginalized posterior values (same length as x_vals).

    Returns
    -------
    (mode, lower, upper) : tuple of floats
        mode: parameter value at the peak
        lower: left bound of 68% HDI
        upper: right bound of 68% HDI
    """
    x_vals = np.asarray(x_vals, dtype=float)
    posterior_1d = np.asarray(posterior_1d, dtype=float)

    # Normalize to a probability density
    dx = np.diff(x_vals)
    # Use trapezoidal integration for normalization
    total_area = float(np.trapezoid(posterior_1d, x_vals))
    if total_area <= 0:
        mode_idx = int(np.argmax(posterior_1d))
        return float(x_vals[mode_idx]), float(x_vals[0]), float(x_vals[-1])
    pdf = posterior_1d / total_area

    # Mode = peak
    mode_idx = int(np.argmax(pdf))
    mode_val = float(x_vals[mode_idx])
    peak_height = float(pdf[mode_idx])

    # Binary search for the horizontal line height where enclosed area = 68%
    target = 0.68
    h_low, h_high = 0.0, peak_height
    for _ in range(200):  # plenty of iterations for convergence
        h_mid = (h_low + h_high) / 2.0
        # Mask: where pdf >= h_mid
        mask = pdf >= h_mid
        if not np.any(mask):
            h_high = h_mid
            continue
        # Area under the curve where pdf >= threshold
        clipped = np.where(mask, pdf, 0.0)
        area = float(np.trapezoid(clipped, x_vals))
        if area > target:
            h_low = h_mid
        else:
            h_high = h_mid

    # Find the bounds: leftmost and rightmost x where pdf >= h_mid
    final_h = (h_low + h_high) / 2.0
    mask = pdf >= final_h
    indices = np.where(mask)[0]
    if len(indices) == 0:
        return mode_val, float(x_vals[0]), float(x_vals[-1])

    # Interpolate for smoother bounds
    left_idx = int(indices[0])
    right_idx = int(indices[-1])

    # Left bound: interpolate between left_idx-1 and left_idx
    if left_idx > 0:
        x0, x1 = x_vals[left_idx - 1], x_vals[left_idx]
        y0, y1 = pdf[left_idx - 1], pdf[left_idx]
        if y1 != y0:
            lower = float(x0 + (final_h - y0) * (x1 - x0) / (y1 - y0))
        else:
            lower = float(x_vals[left_idx])
    else:
        lower = float(x_vals[0])

    # Right bound: interpolate between right_idx and right_idx+1
    if right_idx < len(x_vals) - 1:
        x0, x1 = x_vals[right_idx], x_vals[right_idx + 1]
        y0, y1 = pdf[right_idx], pdf[right_idx + 1]
        if y1 != y0:
            upper = float(x0 + (final_h - y0) * (x1 - x0) / (y1 - y0))
        else:
            upper = float(x_vals[right_idx])
    else:
        upper = float(x_vals[-1])

    return mode_val, lower, upper


# ---------------------------------------------------------------------------
# Grid runner with multiprocessing
# ---------------------------------------------------------------------------

def _single_grid_task(args):
    """Worker for a single (f_bin, pi, sigma_single) point. Defined at top level for pickling."""
    (
        f_bin,
        pi,
        sigma_single,
        sim_cfg,
        bin_cfg,
        obs_delta_rv,
        period_model,
        seed,
    ) = args

    # ensure period model is set on cfg copy
    bin_cfg_local = BinaryParameterConfig(**vars(bin_cfg))
    bin_cfg_local.period_model = period_model

    # apply sigma_single override on a local copy of sim_cfg
    from dataclasses import replace as dc_replace
    sim_cfg_local = dc_replace(sim_cfg, sigma_single=sigma_single)

    rng = np.random.default_rng(seed)
    delta_sim = simulate_delta_rv_sample(
        f_bin=f_bin,
        pi=pi,
        sim_cfg=sim_cfg_local,
        bin_cfg=bin_cfg_local,
        rng=rng,
    )
    D, p = ks_two_sample_binned(delta_sim, obs_delta_rv)
    return f_bin, pi, sigma_single, D, p


# ── Pool initializer pattern (avoids pickle overhead per task) ────────────
_WORKER_GLOBALS: dict = {}


def _init_worker(cadence_library, cadence_weights, obs_delta_rv,
                 n_stars, sigma_measure,
                 n_epochs=6, time_span=3650.0,
                 observation_times=None, v_sys=0.0,
                 bin_edges=None, scoring_method='ks'):
    """Pool initializer: store shared data as process-level globals."""
    global _WORKER_GLOBALS
    _WORKER_GLOBALS = {
        'cadence_library': cadence_library,
        'cadence_weights': cadence_weights,
        'obs_delta_rv': obs_delta_rv,
        'n_stars': n_stars,
        'sigma_measure': sigma_measure,
        'n_epochs': n_epochs,
        'time_span': time_span,
        'observation_times': observation_times,
        'v_sys': v_sys,
        'bin_edges': bin_edges,
        'scoring_method': scoring_method,
    }


def _single_grid_task_lite(args):
    """Lightweight worker: shared data comes from _WORKER_GLOBALS (set by pool initializer).

    args = (f_bin, pi, sigma_single, bin_cfg, period_model, seed)
    """
    f_bin, pi, sigma_single, bin_cfg, period_model, seed = args
    g = _WORKER_GLOBALS

    sim_cfg_local = SimulationConfig(
        n_stars=g['n_stars'],
        n_epochs=g.get('n_epochs', 6),
        time_span=g.get('time_span', 3650.0),
        sigma_single=sigma_single,
        sigma_measure=g['sigma_measure'],
        v_sys=g.get('v_sys', 0.0),
        observation_times=g.get('observation_times'),
        cadence_library=g['cadence_library'],
        cadence_weights=g['cadence_weights'],
    )
    bin_cfg_local = BinaryParameterConfig(**vars(bin_cfg))
    bin_cfg_local.period_model = period_model

    rng = np.random.default_rng(seed)
    delta_sim = simulate_delta_rv_sample(
        f_bin=f_bin, pi=pi,
        sim_cfg=sim_cfg_local, bin_cfg=bin_cfg_local, rng=rng,
    )
    D, p = ks_two_sample_binned(delta_sim, g['obs_delta_rv'], g.get('bin_edges'))
    return f_bin, pi, sigma_single, D, p


def run_bias_grid(
    fbin_values: Iterable[float],
    pi_values: Iterable[float],
    obs_delta_rv: np.ndarray,
    sim_cfg: Optional[SimulationConfig] = None,
    bin_cfg: Optional[BinaryParameterConfig] = None,
    period_model: str = "powerlaw",
    sigma_values: Optional[Iterable[float]] = None,
    n_processes: Optional[int] = None,
    seed_base: int = 1234,
    use_multiprocessing: bool = True,
) -> Dict[str, np.ndarray]:
    """
    Run a (f_bin, pi[, sigma_single]) grid of simulations and K-S comparisons.

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
    sigma_values : iterable of float or None
        Grid of sigma_single values (km/s) to scan. If None, uses the
        single value already set in sim_cfg (2D grid as before).
    n_processes : int or None
        Number of worker processes; if None, mp.Pool chooses.
    seed_base : int
        Base seed; each grid point gets seed = seed_base + idx.
    use_multiprocessing : bool
        If False, run everything serially (useful for debugging).

    Returns
    -------
    result : dict with keys:
        "fbin_grid"  : 1D array of f_bin values.
        "pi_grid"    : 1D array of π values.
        "sigma_grid" : 1D array of sigma_single values (length 1 if not scanned).
        "ks_D"       : 3D array [n_sigma, n_fbin, n_pi] of K-S D.
        "ks_p"       : 3D array of corresponding p-values.
    """
    if sim_cfg is None:
        sim_cfg = SimulationConfig()
    if bin_cfg is None:
        bin_cfg = BinaryParameterConfig()

    fbin_grid  = np.array(list(fbin_values), dtype=float)
    pi_grid    = np.array(list(pi_values), dtype=float)
    sigma_grid = np.array(list(sigma_values), dtype=float) if sigma_values is not None                  else np.array([sim_cfg.sigma_single], dtype=float)

    obs_delta_rv = np.asarray(obs_delta_rv, dtype=float)

    # Build lightweight task tuples (shared data via pool initializer)
    tasks = []
    idx = 0
    for sigma in sigma_grid:
        for fb in fbin_grid:
            for pi in pi_grid:
                tasks.append((
                    float(fb),
                    float(pi),
                    float(sigma),
                    bin_cfg,
                    period_model,
                    seed_base + idx,
                ))
                idx += 1

    n_tasks = len(tasks)
    desc = f"Bias grid ({period_model}, {len(sigma_grid)} σ slice(s))"

    _initargs = (
        sim_cfg.cadence_library,
        getattr(sim_cfg, 'cadence_weights', None),
        obs_delta_rv,
        sim_cfg.n_stars,
        sim_cfg.sigma_measure,
        sim_cfg.n_epochs,
        sim_cfg.time_span,
        sim_cfg.observation_times,
        sim_cfg.v_sys,
        DEFAULT_DRV_BIN_EDGES,
    )

    if use_multiprocessing and n_tasks > 1:
        with mp.Pool(processes=n_processes,
                     initializer=_init_worker,
                     initargs=_initargs) as pool:
            if tqdm is not None:
                results = list(tqdm(
                    pool.imap(_single_grid_task_lite, tasks),
                    total=n_tasks,
                    desc=desc,
                ))
            else:
                results = pool.map(_single_grid_task_lite, tasks)
    else:
        # Serial fallback: manually init worker globals
        _init_worker(*_initargs)
        if tqdm is not None:
            tasks_iter = tqdm(tasks, total=n_tasks, desc=desc)
        else:
            tasks_iter = tasks
        results = [_single_grid_task_lite(t) for t in tasks_iter]

    # Pack results into 3D arrays: [n_sigma, n_fbin, n_pi]
    n_sig = sigma_grid.size
    n_fb  = fbin_grid.size
    n_pi  = pi_grid.size
    ks_D  = np.empty((n_sig, n_fb, n_pi), dtype=float)
    ks_p  = np.empty((n_sig, n_fb, n_pi), dtype=float)

    for idx, (fb, pi, sigma, D, p) in enumerate(results):
        i_sig = idx // (n_fb * n_pi)
        i_fb  = (idx % (n_fb * n_pi)) // n_pi
        i_pi  = idx % n_pi
        ks_D[i_sig, i_fb, i_pi] = D
        ks_p[i_sig, i_fb, i_pi] = p

    return {
        "fbin_grid":  fbin_grid,
        "pi_grid":    pi_grid,
        "sigma_grid": sigma_grid,
        "ks_D":       ks_D,
        "ks_p":       ks_p,
    }


# ---------------------------------------------------------------------------
# Cadence-aware grid runner
# ---------------------------------------------------------------------------

def _single_grid_task_cadence_aware(args):
    """Worker for cadence-aware grid search.

    args = (f_bin, pi, sigma_single, bin_cfg, period_model, seed, n_sets)
    """
    f_bin, pi, sigma_single, bin_cfg, period_model, seed, n_sets = args
    g = _WORKER_GLOBALS

    sim_cfg_local = SimulationConfig(
        n_stars=len(g['cadence_library']),
        n_epochs=g.get('n_epochs', 6),
        time_span=g.get('time_span', 3650.0),
        sigma_single=sigma_single,
        sigma_measure=g['sigma_measure'],
        v_sys=g.get('v_sys', 0.0),
        observation_times=g.get('observation_times'),
        cadence_library=g['cadence_library'],
        cadence_weights=g['cadence_weights'],
    )
    bin_cfg_local = BinaryParameterConfig(**vars(bin_cfg))
    bin_cfg_local.period_model = period_model

    _bin_edges = g.get('bin_edges')

    rng = np.random.default_rng(seed)
    result = simulate_delta_rv_cadence_aware(
        f_bin=f_bin, pi=pi,
        sim_cfg=sim_cfg_local, bin_cfg=bin_cfg_local, rng=rng,
        n_sets=n_sets, bin_edges=_bin_edges,
    )

    obs_cdf = binned_cdf(g['obs_delta_rv'],
                         _bin_edges if _bin_edges is not None else DEFAULT_DRV_BIN_EDGES)
    median_cdf = result['median_cdf']
    n2 = len(g['obs_delta_rv'])

    scoring = g.get('scoring_method', 'ks')
    if scoring == 'weighted':
        D = ks_weighted_D(median_cdf, obs_cdf, result['cdf_var'])
    else:
        D = float(np.max(np.abs(median_cdf - obs_cdf)))

    # Approximate p-value (Kolmogorov series) — same formula for both modes
    n1 = n_sets * len(g['cadence_library'])
    en = math.sqrt(n1 * n2 / (n1 + n2))
    x = (en + 0.12 + 0.11 / en) * D
    term_sum = 0.0
    for j in range(1, 101):
        term = 2.0 * ((-1) ** (j - 1)) * math.exp(-2.0 * (j ** 2) * (x ** 2))
        term_sum += term
        if abs(term) < 1e-8:
            break
    p_value = max(0.0, min(1.0, term_sum))

    return (f_bin, pi, sigma_single, D, p_value,
            result['median_cdf'], result['lo_cdf'], result['hi_cdf'])


def run_bias_grid_cadence_aware(
    fbin_values: Iterable[float],
    pi_values: Iterable[float],
    obs_delta_rv: np.ndarray,
    sim_cfg: Optional[SimulationConfig] = None,
    bin_cfg: Optional[BinaryParameterConfig] = None,
    period_model: str = "powerlaw",
    sigma_values: Optional[Iterable[float]] = None,
    n_sets: int = 10_000,
    n_processes: Optional[int] = None,
    seed_base: int = 1234,
    use_multiprocessing: bool = True,
    callback=None,
    scoring_method: str = 'ks',
) -> Dict[str, np.ndarray]:
    """Cadence-aware grid search over (f_bin, pi[, sigma_single]).

    Like ``run_bias_grid`` but each grid point uses
    ``simulate_delta_rv_cadence_aware`` with *n_sets* repetitions of 25-star
    sets, comparing the **median binned CDF** to the observed CDF.

    Extra parameter *callback(completed, total, result_tuple)* is called after
    each completed task (useful for live progress updates in the webapp).
    """
    if sim_cfg is None:
        sim_cfg = SimulationConfig()
    if bin_cfg is None:
        bin_cfg = BinaryParameterConfig()

    obs_delta_rv = np.asarray(obs_delta_rv, dtype=float)
    fbin_grid = np.asarray(list(fbin_values), dtype=float)
    pi_grid   = np.asarray(list(pi_values), dtype=float)

    if sigma_values is not None:
        sigma_grid = np.asarray(list(sigma_values), dtype=float)
    else:
        sigma_grid = np.array([sim_cfg.sigma_single])

    # Build task list
    tasks = []
    idx = 0
    for sigma in sigma_grid:
        for fb in fbin_grid:
            for pi_val in pi_grid:
                tasks.append((
                    fb, pi_val, sigma,
                    bin_cfg, period_model,
                    seed_base + idx,
                    n_sets,
                ))
                idx += 1

    n_tasks = len(tasks)

    _initargs = (
        sim_cfg.cadence_library,
        getattr(sim_cfg, 'cadence_weights', None),
        obs_delta_rv,
        len(sim_cfg.cadence_library) if sim_cfg.cadence_library else 25,
        sim_cfg.sigma_measure,
        sim_cfg.n_epochs,
        sim_cfg.time_span,
        sim_cfg.observation_times,
        sim_cfg.v_sys,
        DEFAULT_DRV_BIN_EDGES,
        scoring_method,
    )

    # Storage for best-fit CDF band
    best_p = -1.0
    best_median_cdf = None
    best_lo_cdf = None
    best_hi_cdf = None

    n_sig = sigma_grid.size
    n_fb  = fbin_grid.size
    n_pi  = pi_grid.size
    ks_D  = np.empty((n_sig, n_fb, n_pi), dtype=float)
    ks_p  = np.empty((n_sig, n_fb, n_pi), dtype=float)

    def _process_result(res_tuple, completed):
        nonlocal best_p, best_median_cdf, best_lo_cdf, best_hi_cdf
        fb, pi_val, sigma, D, p, med_cdf, lo_cdf, hi_cdf = res_tuple
        i_sig = np.searchsorted(sigma_grid, sigma)
        i_fb  = np.searchsorted(fbin_grid, fb)
        i_pi  = np.searchsorted(pi_grid, pi_val)
        if i_sig < n_sig and i_fb < n_fb and i_pi < n_pi:
            ks_D[i_sig, i_fb, i_pi] = D
            ks_p[i_sig, i_fb, i_pi] = p
        if p > best_p:
            best_p = p
            best_median_cdf = med_cdf
            best_lo_cdf = lo_cdf
            best_hi_cdf = hi_cdf
        if callback is not None:
            callback(completed, n_tasks, res_tuple)

    if use_multiprocessing and n_tasks > 1:
        with mp.Pool(processes=n_processes,
                     initializer=_init_worker,
                     initargs=_initargs) as pool:
            for completed, res in enumerate(pool.imap_unordered(
                    _single_grid_task_cadence_aware, tasks), 1):
                _process_result(res, completed)
    else:
        _init_worker(*_initargs)
        for completed, t in enumerate(tasks, 1):
            res = _single_grid_task_cadence_aware(t)
            _process_result(res, completed)

    return {
        "fbin_grid":       fbin_grid,
        "pi_grid":         pi_grid,
        "sigma_grid":      sigma_grid,
        "ks_D":            ks_D,
        "ks_p":            ks_p,
        "best_median_cdf": best_median_cdf,
        "best_lo_cdf":     best_lo_cdf,
        "best_hi_cdf":     best_hi_cdf,
        "n_sets":          n_sets,
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
        M2 = M1 / q if bin_cfg.q_flipped else M1 * q
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
    obs_single_rv: Optional[np.ndarray] = None,
    obs_binary_rv: Optional[np.ndarray] = None,
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
    obs_single_rv : array-like or None
        Observed RV measurements (km/s) for stars classified as singles.
        If provided, plotted alongside the simulated distributions.
    obs_binary_rv : array-like or None
        Observed RV measurements (km/s) for stars classified as binaries.
        If provided, plotted alongside the simulated distributions.

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

    # Convert optional observed arrays
    obs_single_rv = np.asarray(obs_single_rv, dtype=float) if obs_single_rv is not None else np.empty(0)
    obs_binary_rv = np.asarray(obs_binary_rv, dtype=float) if obs_binary_rv is not None else np.empty(0)

    # Build common bin edges from ALL arrays so everything is on the same scale
    all_arrays = [arr for arr in [rv_single_all, rv_binary_all, obs_single_rv, obs_binary_rv] if arr.size > 0]
    if not all_arrays:
        raise RuntimeError("No RV samples to plot.")
    all_rv = np.concatenate(all_arrays)

    if isinstance(bins, int):
        bin_edges = np.linspace(all_rv.min(), all_rv.max(), bins + 1)
    else:
        bin_edges = bins  # user-specified array or None

    if ax is None:
        fig, ax = plt.subplots()

    # Simulated — dashed lines
    if rv_single_all.size > 0:
        ax.hist(
            rv_single_all,
            bins=bin_edges,
            density=True,
            histtype="step",
            linestyle="--",
            linewidth=1.5,
            label=f"Sim singles (f_bin={best_fbin:.2f}, π={best_pi:.2f})",
        )
    if rv_binary_all.size > 0:
        ax.hist(
            rv_binary_all,
            bins=bin_edges,
            density=True,
            histtype="step",
            linestyle="--",
            linewidth=1.5,
            label=f"Sim binaries (f_bin={best_fbin:.2f}, π={best_pi:.2f})",
        )

    # Observed — solid lines
    if obs_single_rv.size > 0:
        ax.hist(
            obs_single_rv,
            bins=bin_edges,
            density=True,
            histtype="step",
            linewidth=2,
            label="Obs singles",
        )
    if obs_binary_rv.size > 0:
        ax.hist(
            obs_binary_rv,
            bins=bin_edges,
            density=True,
            histtype="step",
            linewidth=2,
            label="Obs binaries",
        )

    ax.set_xlabel(r"RV (km s$^{-1}$)")
    ax.set_ylabel("Normalised counts")
    ax.set_title("RV distribution: singles vs binaries (best model)")
    ax.legend()

    return ax, best_fbin, best_pi


# ---------------------------------------------------------------------------
# 3D and animated visualisations of the (f_bin, π, σ_single) grid
# ---------------------------------------------------------------------------

def plot_3d_ks(
    grid_result: Dict[str, np.ndarray],
    use_pvalue: bool = True,
    sigma_idx: Optional[int] = None,
):
    """
    Interactive 3D surface of the KS statistic over (f_bin, π) for one
    or all sigma_single slices.

    If grid_result contains multiple sigma slices and sigma_idx is None,
    the surface shown is the best p-value (or min D) projected over sigma —
    i.e. for each (f_bin, π) cell we take the best value across all sigmas.
    If sigma_idx is given, only that slice is shown.

    Parameters
    ----------
    grid_result : dict
        Output of run_bias_grid.
    use_pvalue : bool
        If True, plot KS p-value (higher = better).
        If False, plot KS D statistic (lower = better).
    sigma_idx : int or None
        Index into sigma_grid to plot. If None and multiple sigmas exist,
        collapses over sigma by taking max p (or min D).

    Returns
    -------
    fig, ax : matplotlib Figure and Axes3D
    """
    from mpl_toolkits.mplot3d import Axes3D  # noqa: F401

    fbin_grid  = grid_result["fbin_grid"]
    pi_grid    = grid_result["pi_grid"]
    sigma_grid = grid_result["sigma_grid"]
    Z3         = grid_result["ks_p"] if use_pvalue else grid_result["ks_D"]
    # Z3 shape: (n_sigma, n_fbin, n_pi)

    if sigma_idx is not None:
        Z = Z3[sigma_idx]
        title = (f"KS {'p-value' if use_pvalue else 'D'} — "
                 f"σ_single = {sigma_grid[sigma_idx]:.1f} km/s")
    else:
        # collapse: best p (max) or best D (min) across sigma axis
        Z = Z3.max(axis=0) if use_pvalue else Z3.min(axis=0)
        title = (f"KS {'p-value' if use_pvalue else 'D'} — "
                 f"best over σ_single ∈ [{sigma_grid.min():.1f}, {sigma_grid.max():.1f}] km/s")

    Pi, Fb = np.meshgrid(pi_grid, fbin_grid)

    fig = plt.figure(figsize=(9, 6))
    ax  = fig.add_subplot(111, projection="3d")
    surf = ax.plot_surface(Pi, Fb, Z, cmap="viridis", edgecolor="none", alpha=0.9)
    fig.colorbar(surf, ax=ax, shrink=0.5, label="KS p-value" if use_pvalue else "KS D")

    ax.set_xlabel("π (period index)")
    ax.set_ylabel("f_bin")
    ax.set_zlabel("KS p-value" if use_pvalue else "KS D")
    ax.set_title(title)

    plt.tight_layout()
    return fig, ax


def plot_ks_movie(
    grid_result: Dict[str, np.ndarray],
    use_pvalue: bool = True,
):
    """
    Animated heatmap of the KS statistic over (f_bin, π) where each frame
    is one sigma_single value.  Includes play/pause button and a frame slider.

    A second panel shows the best p-value (or min D) as a function of
    sigma_single, with a vertical line tracking the current frame.

    Parameters
    ----------
    grid_result : dict
        Output of run_bias_grid.
    use_pvalue : bool
        If True, animate KS p-value.  If False, animate KS D.

    Returns
    -------
    fig : matplotlib Figure
    anim : matplotlib FuncAnimation (keep a reference to prevent GC)
    """
    import matplotlib.animation as animation
    from matplotlib.widgets import Slider, Button

    fbin_grid  = grid_result["fbin_grid"]
    pi_grid    = grid_result["pi_grid"]
    sigma_grid = grid_result["sigma_grid"]
    Z3         = grid_result["ks_p"] if use_pvalue else grid_result["ks_D"]
    # Z3 shape: (n_sigma, n_fbin, n_pi)

    stat_label = "KS p-value" if use_pvalue else "KS D"
    n_sigma    = sigma_grid.size

    # Best statistic per sigma slice
    best_per_sigma = Z3.max(axis=(1, 2)) if use_pvalue else Z3.min(axis=(1, 2))

    # Common colour scale across all frames
    vmin = Z3.min()
    vmax = Z3.max()

    Pi, Fb = np.meshgrid(pi_grid, fbin_grid)

    # ---- layout ----
    fig = plt.figure(figsize=(13, 6))
    # Leave room at the bottom for widgets
    fig.subplots_adjust(bottom=0.22, wspace=0.35)

    ax_heat  = fig.add_subplot(1, 2, 1)
    ax_sigma = fig.add_subplot(1, 2, 2)

    # --- heatmap (frame 0) ---
    mesh = ax_heat.pcolormesh(Pi, Fb, Z3[0], shading="auto",
                              vmin=vmin, vmax=vmax, cmap="viridis")
    fig.colorbar(mesh, ax=ax_heat, label=stat_label)
    ax_heat.set_xlabel("π (period index)")
    ax_heat.set_ylabel("f_bin")
    title_obj = ax_heat.set_title(f"σ_single = {sigma_grid[0]:.2f} km/s")

    # --- best-per-sigma panel ---
    ax_sigma.plot(sigma_grid, best_per_sigma, "o-", color="steelblue")
    vline = ax_sigma.axvline(sigma_grid[0], color="tomato", lw=2, ls="--")
    ax_sigma.set_xlabel("σ_single (km/s)")
    ax_sigma.set_ylabel(f"Best {stat_label}")
    ax_sigma.set_title(f"Best {stat_label} vs σ_single")

    # --- slider ---
    ax_slider = fig.add_axes([0.15, 0.10, 0.55, 0.03])
    slider = Slider(ax_slider, "Frame", 0, n_sigma - 1,
                    valinit=0, valstep=1, color="steelblue")

    # --- play / pause button ---
    ax_button = fig.add_axes([0.78, 0.08, 0.10, 0.05])
    button = Button(ax_button, "▶ Play", color="lightgray", hovercolor="silver")

    # ---- animation state ----
    state = {"playing": False, "frame": 0}

    def draw_frame(i):
        i = int(i)
        mesh.set_array(Z3[i].ravel())
        title_obj.set_text(f"σ_single = {sigma_grid[i]:.2f} km/s")
        vline.set_xdata([sigma_grid[i], sigma_grid[i]])
        slider.set_val(i)
        fig.canvas.draw_idle()

    def update_slider(val):
        state["frame"] = int(slider.val)
        draw_frame(state["frame"])

    slider.on_changed(update_slider)

    def toggle_play(event):
        state["playing"] = not state["playing"]
        button.label.set_text("⏸ Pause" if state["playing"] else "▶ Play")
        fig.canvas.draw_idle()

    button.on_clicked(toggle_play)

    def animate(frame_unused):
        if state["playing"]:
            state["frame"] = (state["frame"] + 1) % n_sigma
            draw_frame(state["frame"])

    anim = animation.FuncAnimation(
        fig, animate, interval=600, cache_frame_data=False
    )

    plt.show()
    return fig, anim