"""plots/compute.py — Pure computation functions for plot analytics (no Streamlit)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import optimize


# ─────────────────────────────────────────────────────────────────────────────
# Agreement scores (Plot #4)
# ─────────────────────────────────────────────────────────────────────────────

def compute_agreement_scores(df: pd.DataFrame, ordered_lines: list[str]) -> dict[str, float]:
    """Compute correlation-weighted agreement score per emission line.

    For each line, compute pairwise Pearson r with every other line on common stars.
    Weight each r by (n_common / n_total). Score = mean of weighted r values.

    Parameters
    ----------
    df : DataFrame with columns 'dRV | {line}' for each line, and 'Star'.
    ordered_lines : list of line keys to compare.

    Returns
    -------
    dict mapping line_key -> agreement score (0..1).
    """
    n_total = len(df)
    if n_total == 0:
        return {}

    scores = {}
    for lk in ordered_lines:
        col_i = f'dRV | {lk}'
        if col_i not in df.columns:
            continue
        weighted_rs = []
        for other in ordered_lines:
            if other == lk:
                continue
            col_j = f'dRV | {other}'
            if col_j not in df.columns:
                continue
            common = df[['Star', col_i, col_j]].dropna()
            n_common = len(common)
            if n_common < 3:
                continue
            r = np.corrcoef(common[col_i].values, common[col_j].values)[0, 1]
            if np.isfinite(r):
                weight = n_common / n_total
                weighted_rs.append(r * weight)
        if weighted_rs:
            scores[lk] = float(np.mean(weighted_rs))
    return scores


# ─────────────────────────────────────────────────────────────────────────────
# Two-segment piecewise linear fit (Plot #2 enhanced)
# ─────────────────────────────────────────────────────────────────────────────

def _two_segment(x, x_break, y0, s1, s2):
    """Piecewise linear with breakpoint at x_break."""
    return np.where(x <= x_break,
                    y0 + s1 * (x - x[0]),
                    y0 + s1 * (x_break - x[0]) + s2 * (x - x_break))


def fit_two_segment_linear(
    x: np.ndarray,
    y: np.ndarray,
    y_err: np.ndarray | None = None,
) -> dict:
    """Fit a two-segment piecewise linear model to f_bin(threshold) data.

    Parameters
    ----------
    x : threshold values (1D array)
    y : binary fraction values (1D array)
    y_err : optional errors on y

    Returns
    -------
    dict with keys: 'x_break' (elbow), 'y0', 's1', 's2', 'y_fit',
    'residuals', 'chi2', 'dof', 'chi2_dof'.
    """
    if len(x) < 5:
        return {}

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    # Initial guess: breakpoint in the middle
    x_mid = (x.min() + x.max()) / 2.0
    p0 = [x_mid, float(y[0]), -0.001, -0.0001]

    bounds = ([x.min() + 1, -1, -1, -1],
              [x.max() - 1, 2, 1, 1])

    sigma = y_err if y_err is not None else None

    try:
        popt, _ = optimize.curve_fit(
            lambda xv, xb, y0v, s1v, s2v: _two_segment(xv, xb, y0v, s1v, s2v),
            x, y, p0=p0, bounds=bounds, sigma=sigma, maxfev=10000,
        )
    except (RuntimeError, ValueError):
        return {}

    y_fit = _two_segment(x, *popt)
    residuals = y - y_fit

    if sigma is not None and np.all(sigma > 0):
        chi2 = float(np.sum((residuals / sigma) ** 2))
    else:
        chi2 = float(np.sum(residuals ** 2))

    dof = max(len(x) - 4, 1)

    return {
        'x_break': float(popt[0]),
        'y0': float(popt[1]),
        's1': float(popt[2]),
        's2': float(popt[3]),
        'y_fit': y_fit,
        'residuals': residuals,
        'chi2': chi2,
        'dof': dof,
        'chi2_dof': chi2 / dof,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Equivalent thresholds (Plot #3)
# ─────────────────────────────────────────────────────────────────────────────

def find_equiv_thresholds(
    frac_data: dict[str, list[float]],
    t_vals: np.ndarray,
    ref_line: str,
    ref_threshold: float,
) -> dict[str, float]:
    """For each line, find threshold t* where f_bin(t*) = f_bin(ref_line, ref_threshold).

    Parameters
    ----------
    frac_data : dict mapping line_key -> list of fracs (one per t_vals entry)
    t_vals : 1D array of threshold values
    ref_line : reference line key
    ref_threshold : reference threshold (km/s)

    Returns
    -------
    dict mapping line_key -> equivalent threshold (km/s). NaN if not found.
    """
    if ref_line not in frac_data:
        return {}

    ref_fracs = np.asarray(frac_data[ref_line])
    # Find ref fraction at ref_threshold
    idx_ref = int(np.argmin(np.abs(t_vals - ref_threshold)))
    target_frac = ref_fracs[idx_ref]

    result = {}
    for lk, fracs in frac_data.items():
        farr = np.asarray(fracs)
        # Find where fraction crosses target_frac (monotonically decreasing)
        diffs = farr - target_frac
        sign_changes = np.where(np.diff(np.sign(diffs)))[0]
        if len(sign_changes) > 0:
            idx = sign_changes[0]
            # Linear interpolation
            if abs(diffs[idx + 1] - diffs[idx]) > 1e-12:
                t_star = t_vals[idx] + (t_vals[idx + 1] - t_vals[idx]) * \
                    (-diffs[idx]) / (diffs[idx + 1] - diffs[idx])
            else:
                t_star = t_vals[idx]
            result[lk] = float(t_star)
        elif np.any(np.abs(diffs) < 1e-6):
            result[lk] = float(t_vals[np.argmin(np.abs(diffs))])
        else:
            result[lk] = float('nan')
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Survival function (Plot #7)
# ─────────────────────────────────────────────────────────────────────────────

def compute_survival_curve(
    thresholds: np.ndarray,
    sigma: float,
    n_epochs: int,
    n_samples: int = 50000,
    rng_seed: int = 42,
) -> np.ndarray:
    """Compute P(max dRV > t) for Gaussian noise with given sigma over n_epochs.

    Simulates n_samples realizations, each with n_epochs RV draws from N(0, sigma).
    Returns the survival function P(max_dRV > t) for each threshold.

    Parameters
    ----------
    thresholds : 1D array of threshold values
    sigma : Gaussian noise sigma (km/s)
    n_epochs : number of observation epochs
    n_samples : Monte Carlo sample size
    rng_seed : random seed

    Returns
    -------
    1D array of survival probabilities, same length as thresholds.
    """
    rng = np.random.default_rng(rng_seed)
    # Draw RVs: shape (n_samples, n_epochs)
    rvs = rng.normal(0, sigma, size=(n_samples, n_epochs))
    # Peak-to-peak dRV per realization
    max_drvs = rvs.max(axis=1) - rvs.min(axis=1)

    thresholds = np.asarray(thresholds)
    # Survival: fraction with max_dRV > t
    survival = np.array([np.mean(max_drvs > t) for t in thresholds])
    return survival


# ─────────────────────────────────────────────────────────────────────────────
# PDF from survival (for Plot #8)
# ─────────────────────────────────────────────────────────────────────────────

def survival_to_pdf(thresholds: np.ndarray, survival: np.ndarray) -> np.ndarray:
    """Numerical derivative of survival curve -> PDF (negated gradient)."""
    dt = np.diff(thresholds)
    # Prepend zero-width bin for matching length
    pdf = -np.gradient(survival, thresholds)
    # Ensure non-negative
    pdf = np.maximum(pdf, 0)
    return pdf
