import numpy as np
from dataclasses import dataclass
from typing import Tuple, List

# ==========================
# USER-CONTROLLED PARAMETERS
# ==========================

N_SIM = 100000        # number of simulated binaries
N_EPOCHS = 6            # how many RV measurements per star
BASELINE_YEARS = 1.5    # total time span of the observations
DELTA_RV_THRESHOLD = 50.0  # km/s detection threshold for "binary"

M1_MSUN = 10.0          # WR mass in solar masses
SIGMA_RV = 10.0         # typical RV error per epoch (km/s)

# Underlying period distribution (log10 P in days)
LOGP_MIN = 0.75         # ~5.6 d
LOGP_MAX = 4.0          # ~27 yr
USE_POWER_LAW_IN_LOGP = False  # if True, use p(logP) ~ (logP)**PI_LOGP
PI_LOGP = 1.9           # only used if USE_POWER_LAW_IN_LOGP = True

# Mass-ratio and eccentricity distributions
Q_MIN, Q_MAX = 0.1, 2.0
ECC_MIN, ECC_MAX = 0.0, 0.9

# Parallelization
USE_PARALLEL = False    # set to True if N_SIM is large and you want speed
N_PROCESSES = 1

# Random seed for reproducibility
SEED = 42


# ==========================
# PHYSICAL HELPER FUNCTIONS
# ==========================

@dataclass
class BinaryParams:
    """Physical orbital parameters for a single binary."""
    P_days: float
    e: float
    q: float
    i_rad: float
    omega_rad: float
    M1: float
    M2: float
    T0_days: float


def generate_observation_times(n_epochs: int, baseline_years: float) -> np.ndarray:
    """
    1) OBSERVATION SCHEDULE (time sampling)
    Generate observation times in days over the given baseline.
    Replace this with your real BJDs per star if you want!
    """
    baseline_days = baseline_years * 365.25
    return np.linspace(0.0, baseline_days, n_epochs)


def sample_logP(size: int) -> np.ndarray:
    """
    2) INTRINSIC PERIOD DISTRIBUTION
    Sample log10(P_days). For now, either:
    - flat in logP (default, simple)
    - or a power law p(logP) ~ (logP)**PI_LOGP (if USE_POWER_LAW_IN_LOGP=True)
    """
    rng = np.random.default_rng()
    if not USE_POWER_LAW_IN_LOGP:
        return rng.uniform(LOGP_MIN, LOGP_MAX, size=size)
    else:
        # Simple rejection sampling for p(x) ~ x**PI_LOGP on [a, b]
        a, b = LOGP_MIN, LOGP_MAX
        x = []
        max_val = max(a**PI_LOGP, b**PI_LOGP)
        while len(x) < size:
            x_try = rng.uniform(a, b)
            y_try = rng.uniform(0, max_val)
            if y_try < x_try**PI_LOGP:
                x.append(x_try)
        return np.array(x)


def draw_binary_params() -> BinaryParams:
    """
    3) DRAW INTRINSIC ORBITAL PARAMETERS (population-level physics)
    """
    rng = np.random.default_rng()
    logP = sample_logP(1)[0]
    P_days = 10.0 ** logP

    q = rng.uniform(Q_MIN, Q_MAX)
    M1 = M1_MSUN
    M2 = q * M1

    e = rng.uniform(ECC_MIN, ECC_MAX)

    # isotropic inclinations: cos i uniform in [0,1]
    cos_i = rng.uniform(0.0, 1.0)
    i_rad = np.arccos(cos_i)

    omega_rad = rng.uniform(0.0, 2.0 * np.pi)
    T0_days = rng.uniform(0.0, P_days)

    return BinaryParams(
        P_days=P_days,
        e=e,
        q=q,
        i_rad=i_rad,
        omega_rad=omega_rad,
        M1=M1,
        M2=M2,
        T0_days=T0_days,
    )


def kepler_true_anomaly(M, e, tol=1e-8, max_iter=50):
    """
    4) ORBITAL DYNAMICS (Kepler's equation)
    Convert mean anomaly M to true anomaly f for eccentric orbit.
    """
    M = np.mod(M, 2.0 * np.pi)

    if e < 1e-3:
        # nearly circular
        return M

    # initial guess for eccentric anomaly
    E = M if e < 0.8 else np.pi

    for _ in range(max_iter):
        f = E - e * np.sin(E) - M
        fprime = 1.0 - e * np.cos(E)
        dE = -f / fprime
        E = E + dE
        if np.all(np.abs(dE) < tol):
            break

    cosf = (np.cos(E) - e) / (1 - e * np.cos(E))
    sinf = (np.sqrt(1 - e**2) * np.sin(E)) / (1 - e * np.cos(E))
    f_true = np.arctan2(sinf, cosf)
    return f_true


def rv_semi_amplitude(params: BinaryParams) -> float:
    """
    5) PROJECT ORBIT INTO LINE OF SIGHT
    Compute RV semi-amplitude K1 (km/s) of the primary.
    """
    P = params.P_days
    M1, M2 = params.M1, params.M2
    e = params.e
    i = params.i_rad

    Mtot = M1 + M2

    # K1 in km/s, P in days, M in Msun
    K_const = 212.9  # from standard Keplerian formula
    K1 = K_const * (M2 * np.sin(i)) / (Mtot ** (2.0 / 3.0) * P ** (1.0 / 3.0) * np.sqrt(1 - e**2))
    return K1


def simulate_rv_curve(params: BinaryParams, times_days: np.ndarray) -> np.ndarray:
    """
    6) ORBITAL RADIAL VELOCITY CURVE (no noise yet)
    """
    P = params.P_days
    e = params.e
    omega = params.omega_rad
    T0 = params.T0_days

    K1 = rv_semi_amplitude(params)

    # mean motion
    n = 2.0 * np.pi / P

    # mean anomaly
    M = n * (times_days - T0)

    # true anomaly from Kepler's equation
    f_true = kepler_true_anomaly(M, e)

    # standard RV formula of primary (gamma set to 0)
    rv = K1 * (np.cos(omega + f_true) + e * np.cos(omega))
    return rv


def add_measurement_noise(rv: np.ndarray, sigma_rv: float) -> np.ndarray:
    """
    7) MEASUREMENT NOISE (instrumental + wind variability)
    """
    rng = np.random.default_rng()
    noise = rng.normal(loc=0.0, scale=sigma_rv, size=rv.shape)
    return rv + noise


def detect_binary(rv_measured: np.ndarray, threshold: float) -> Tuple[bool, float]:
    """
    8) DETECTION STEP: from RVs to 'binary / non-binary'
    """
    delta_rv = float(np.max(rv_measured) - np.min(rv_measured))
    detected = bool(delta_rv >= threshold)
    return detected, delta_rv


def simulate_one_system(times_days: np.ndarray) -> Tuple[bool, float]:
    """
    Run all physical + observational stages for one binary.
    """
    params = draw_binary_params()
    rv_true = simulate_rv_curve(params, times_days)
    rv_measured = add_measurement_noise(rv_true, SIGMA_RV)
    detected, delta_rv = detect_binary(rv_measured, DELTA_RV_THRESHOLD)
    return detected, delta_rv


def _simulate_one_system_with_times(times_days: np.ndarray) -> Tuple[bool, float]:
    """
    Small wrapper needed because ProcessPoolExecutor
    can only pass picklable arguments.
    """
    return simulate_one_system(times_days)


def run_simulation(n_sim: int, use_parallel: bool = False) -> Tuple[float, np.ndarray]:
    """
    Main driver: simulate a population of binaries and
    return detection efficiency and all ΔRVs.
    """
    np.random.seed(SEED)  # for reproducibility of the whole run

    times_days = generate_observation_times(N_EPOCHS, BASELINE_YEARS)

    if not use_parallel:
        results = [simulate_one_system(times_days) for _ in range(n_sim)]
    else:
        import concurrent.futures
        with concurrent.futures.ProcessPoolExecutor(max_workers=N_PROCESSES) as ex:
            results = list(ex.map(
                _simulate_one_system_with_times,
                [times_days] * n_sim
            ))

    detected_flags = np.array([r[0] for r in results])
    delta_rvs = np.array([r[1] for r in results])

    detection_efficiency = detected_flags.mean()
    return detection_efficiency, delta_rvs


if __name__ == "__main__":
    p_det, delta_rvs = run_simulation(N_SIM, use_parallel=USE_PARALLEL)
    print(f"Detection efficiency p_det ≈ {p_det:.3f}")
    print(f"Median ΔRV in simulation: {np.median(delta_rvs):.1f} km/s")
