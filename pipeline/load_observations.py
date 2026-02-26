"""
pipeline/load_observations.py
─────────────────────────────
Load observed RVs, MJDs, and binary classification for all 25 WR stars.

IMPORTANT:
- MJDs come from FITS header ['MJD-OBS'], NOT from the RV property dict.
- The RV property only stores: {line_name: {'full_RV': float, 'full_RV_err': float}}
- Binary line used: 'C IV 5808-5812' (hardcoded, matching bias_simulation.ipynb)
- Binary criteria: (1) ΔRV > threshold_dRV  AND  (2) ΔRV - sigma_factor * σ > 0
- Always cast numpy.bool_ → Python bool() before storing or using 'is True'.
"""

import sys, os, math
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np

# ── Path fix: allow running from pipeline/ or from project root ───────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from ObservationClass import ObservationManager
import specs


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def load_observed_delta_rvs(
    settings: dict | None = None,
    obs: ObservationManager | None = None,
) -> tuple[np.ndarray, dict]:
    """
    Apply binary classification to all 25 stars using the C IV 5808-5812 line.

    Returns
    -------
    obs_delta_rv : np.ndarray, shape (25,)
        Best-pair ΔRV (km/s) for each star (whether binary or not).
    detail : dict
        Per-star dict with keys:
          'rv'        : np.ndarray of non-zero RVs
          'rv_err'    : np.ndarray of corresponding errors
          'is_binary' : bool
          'best_dRV'  : float
          'best_sigma': float
    """
    cfg = _get_classification_cfg(settings)
    if obs is None:
        obs = _make_obs()

    def _load_one_star(star_name: str) -> tuple:
        """Load and classify one star. Thread-safe (file reads only)."""
        try:
            star   = obs.load_star_instance(star_name, to_print=False)
            epochs = star.get_all_epoch_numbers()
            n_ep   = max(epochs) if epochs else 0
            rv_list     = np.zeros(n_ep)
            rv_err_list = np.zeros(n_ep)
            for j in epochs:
                rv_prop = star.load_property('RVs', j, 'COMBINED')
                if rv_prop is None or cfg['line'] not in rv_prop:
                    continue
                entry   = rv_prop[cfg['line']].item() if hasattr(rv_prop[cfg['line']], 'item') \
                          else rv_prop[cfg['line']]
                rv_val  = entry.get('full_RV',     0.0)
                err_val = entry.get('full_RV_err', 0.0)
                if rv_val is not None and err_val is not None:
                    rv_list[j - 1]     = float(rv_val)
                    rv_err_list[j - 1] = float(err_val)
            mask   = rv_list != 0
            rv     = rv_list[mask]
            rv_err = rv_err_list[mask]
            if len(rv) < 2:
                return star_name, rv, rv_err, None, 0.0, np.nan
            is_binary, best_dRV, best_sigma = _classify(rv, rv_err, cfg)
            return star_name, rv, rv_err, is_binary, best_dRV, best_sigma
        except Exception as e:
            print(f"  [load_obs] WARNING: could not load {star_name}: {e}")
            return star_name, np.array([]), np.array([]), None, 0.0, np.nan

    # Load all 25 stars in parallel (thread-safe: only file reads)
    n_workers = max(1, (os.cpu_count() or 2) - 1)
    results_map: dict = {}
    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(_load_one_star, sn): sn for sn in specs.star_names}
        for fut in as_completed(futures):
            sn, rv, rv_err, is_bin, drv, sigma = fut.result()
            results_map[sn] = (rv, rv_err, is_bin, drv, sigma)

    # Reassemble in original star order
    detail:    dict  = {}
    delta_rvs: list  = []
    for star_name in specs.star_names:
        rv, rv_err, is_bin, drv, sigma = results_map[star_name]
        detail[star_name] = {
            'rv': rv, 'rv_err': rv_err,
            'is_binary': is_bin, 'best_dRV': drv, 'best_sigma': sigma,
        }
        delta_rvs.append(drv)

    return np.array(delta_rvs, dtype=float), detail


def load_cadence_library(
    obs: ObservationManager | None = None,
) -> tuple[list[np.ndarray], np.ndarray]:
    """
    Build cadence_library from actual FITS MJD-OBS header values.

    Returns
    -------
    cadence_list : list of np.ndarray
        One array per star of relative observation times (days from global min MJD).
    weights : np.ndarray
        Uniform weights (1/N_stars each), shape (N_stars,).
    """
    if obs is None:
        obs = _make_obs()

    all_mjds_raw = {}
    global_min   = np.inf

    for star_name in specs.star_names:
        try:
            star   = obs.load_star_instance(star_name, to_print=False)
            epochs = star.get_all_epoch_numbers()
            mjds   = []
            for ep in epochs:
                try:
                    fit = star.load_observation(ep, band='NIR')
                    mjds.append(float(fit.header['MJD-OBS']))
                except Exception:
                    try:
                        fit = star.load_observation(ep, band='VIS')
                        mjds.append(float(fit.header['MJD-OBS']))
                    except Exception:
                        pass   # skip this epoch
            if mjds:
                all_mjds_raw[star_name] = np.array(mjds)
                global_min = min(global_min, np.min(mjds))
        except Exception as e:
            print(f"  [cadence] WARNING: {star_name}: {e}")

    cadence_list = []
    for star_name in specs.star_names:
        if star_name in all_mjds_raw:
            cadence_list.append(all_mjds_raw[star_name] - global_min)
        else:
            cadence_list.append(np.array([0.0, 365.0]))   # fallback

    n = len(cadence_list)
    weights = np.full(n, 1.0 / n)
    return cadence_list, weights


def load_star_rvs_all_lines(
    star_name: str,
    obs: ObservationManager | None = None,
) -> dict:
    """
    Load ALL saved RV measurements for one star, all lines, all epochs.

    Returns
    -------
    result : dict
        {line_name: {'epochs': [...], 'rv': [...], 'rv_err': [...]}}
    """
    if obs is None:
        obs = _make_obs()
    star   = obs.load_star_instance(star_name, to_print=False)
    epochs = star.get_all_epoch_numbers()
    result = {}
    for ep in epochs:
        rv_prop = star.load_property('RVs', ep, 'COMBINED')
        if rv_prop is None:
            continue
        for line_name in rv_prop.keys():
            entry = rv_prop[line_name].item() if hasattr(rv_prop[line_name], 'item') \
                    else rv_prop[line_name]
            if not isinstance(entry, dict):
                continue
            rv_val  = entry.get('full_RV')
            err_val = entry.get('full_RV_err')
            if rv_val is None or err_val is None:
                continue
            result.setdefault(line_name, {'epochs': [], 'rv': [], 'rv_err': []})
            result[line_name]['epochs'].append(ep)
            result[line_name]['rv'].append(float(rv_val))
            result[line_name]['rv_err'].append(float(err_val))
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_obs() -> ObservationManager:
    """Create ObservationManager pointed at the project root Data/ directory."""
    root = _ROOT
    return ObservationManager(
        data_dir   = os.path.join(root, 'Data/'),
        backup_dir = os.path.join(root, 'Backups/'),
    )


def _get_classification_cfg(settings: dict | None) -> dict:
    if settings is None:
        return {'line': 'C IV 5808-5812', 'threshold_dRV': 45.5, 'sigma_factor': 4.0}
    cls = settings.get('classification', {})
    return {
        'line':         settings.get('primary_line', 'C IV 5808-5812'),
        'threshold_dRV': cls.get('threshold_dRV', 45.5),
        'sigma_factor':  cls.get('sigma_factor',  4.0),
    }


def _classify(rv: np.ndarray, rv_err: np.ndarray, cfg: dict) -> tuple[bool, float, float]:
    """
    Apply two-criteria binary classification (mirrors bias_simulation.ipynb).
    Returns (is_binary: bool, best_dRV: float, best_sigma: float).
    """
    threshold = cfg['threshold_dRV']
    kfactor   = cfg['sigma_factor']

    idx_min, idx_max = int(np.argmin(rv)), int(np.argmax(rv))
    abs_base   = float(abs(rv[idx_max] - rv[idx_min]))
    sigma_base = math.sqrt(float(rv_err[idx_min])**2 + float(rv_err[idx_max])**2)
    best_dRV, best_sigma = abs_base, sigma_base
    found = (abs_base > threshold) and ((abs_base - kfactor * sigma_base) > 0.0)

    if not found:
        n = len(rv)
        for i in range(n):
            for k in range(i + 1, n):
                if (i == idx_min and k == idx_max) or (i == idx_max and k == idx_min):
                    continue
                d   = float(abs(rv[k] - rv[i]))
                sig = math.sqrt(float(rv_err[i])**2 + float(rv_err[k])**2)
                if d > threshold and (d - kfactor * sig) > 0.0:
                    if d > best_dRV:
                        best_dRV, best_sigma = d, sig
                    found = True

    return bool(found), best_dRV, best_sigma   # bool() cast: numpy.bool_ → Python bool


# ─────────────────────────────────────────────────────────────────────────────
# CLI convenience
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import json
    settings_path = os.path.join(_ROOT, 'settings', 'user_settings.json')
    settings = json.load(open(settings_path)) if os.path.exists(settings_path) else None

    print('Loading observed ΔRVs ...')
    obs = _make_obs()
    delta_rvs, detail = load_observed_delta_rvs(settings, obs)

    n_binary = sum(1 for d in detail.values() if d['is_binary'] is True)
    n_data   = sum(1 for d in detail.values() if d['is_binary'] is not None)
    bartzakos = (settings or {}).get('classification', {}).get('bartzakos_binaries', 3)
    total_pop = (settings or {}).get('classification', {}).get('total_population', 28)

    print(f'\nBinary fraction: ({n_binary} + {bartzakos}) / {total_pop} = '
          f'{(n_binary + bartzakos) / total_pop * 100:.1f}%')
    print(f'(Detected {n_binary}/{n_data} in our 25-star sample)\n')

    for star_name, d in detail.items():
        status = '✓ BINARY' if d['is_binary'] else ('? NO DATA' if d['is_binary'] is None else '✗ single')
        print(f'  {star_name:<24s}  {status}  ΔRV={d["best_dRV"]:.1f} km/s')
