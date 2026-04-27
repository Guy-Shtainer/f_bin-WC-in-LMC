"""bc.bin_schemes — Pure-function ΔRV bin-edge builders for the Bin-Sensitivity sub-tab.

No Streamlit imports — only numpy (+ optional scipy for the anchored scheme).
Every function returns a 1-D np.ndarray of bin edges that ends in np.inf.

Reference: memory/likelihood_bin_sensitivity.md §2.
"""
from __future__ import annotations

from typing import Optional

import numpy as np


# Supported scheme families. `custom` is opt-in from a text input.
SCHEME_FAMILIES: tuple[str, ...] = (
    "dsilva_default",
    "dsilva_shift_plus",
    "equal_width",
    "log_spaced",
    "quantile",
    "anchored",
    "freedman_diaconis",
    "custom",
)


def _ensure_sorted_with_inf_tail(edges: np.ndarray) -> np.ndarray:
    """Sort edges, drop duplicates, and guarantee an np.inf tail."""
    e = np.asarray(edges, dtype=float).ravel()
    e = np.sort(e[~np.isnan(e)])
    # Dedupe (keep unique, preserving order after sort)
    e = np.unique(e)
    # Ensure first edge is 0
    if e.size == 0 or e[0] > 0.0:
        e = np.concatenate([[0.0], e])
    # Ensure tail is inf
    if not np.isinf(e[-1]):
        e = np.concatenate([e, [np.inf]])
    return e


def _dsilva_default(threshold: float = 45.5) -> np.ndarray:
    """Status-quo Dsilva+2023 WNL scheme: [0, threshold, 250, 650, inf]."""
    return np.array([0.0, float(threshold), 250.0, 650.0, np.inf])


def _dsilva_shift_plus(threshold: float = 45.5) -> np.ndarray:
    """Robustness scheme: shift all interior edges by +5 / +50 / +50 km/s."""
    return np.array([0.0, float(threshold) + 5.0, 300.0, 700.0, np.inf])


def _equal_width(n_bins: int, max_obs: float) -> np.ndarray:
    """np.linspace(0, max_obs, n_bins+1) with np.inf tail."""
    n = max(int(n_bins), 1)
    hi = max(float(max_obs), 1.0)
    return np.concatenate([np.linspace(0.0, hi, n + 1), [np.inf]])


def _log_spaced(n_bins: int, threshold: float, max_obs: float) -> np.ndarray:
    """[0, logspace(log10(threshold), log10(max_obs), n), inf]."""
    n = max(int(n_bins), 1)
    lo = max(float(threshold), 1.0)
    hi = max(float(max_obs), lo * 2.0)
    mid = np.logspace(np.log10(lo), np.log10(hi), n)
    return np.concatenate([[0.0], mid, [np.inf]])


def _quantile(n_bins: int, obs_delta_rv: np.ndarray) -> np.ndarray:
    """Quantile bins of observed ΔRV, forcing first edge = 0, last = inf."""
    n = max(int(n_bins), 1)
    obs = np.asarray(obs_delta_rv, dtype=float).ravel()
    obs = obs[np.isfinite(obs)]
    if obs.size == 0:
        return np.array([0.0, 1.0, np.inf])
    q = np.quantile(obs, np.linspace(0.0, 1.0, n + 1))
    q = np.asarray(q, dtype=float)
    q[0] = 0.0
    # Replace the last (max) with +inf to capture the tail.
    out = np.concatenate([q[:-1], [np.inf]])
    return out


def _freedman_diaconis(obs_delta_rv: np.ndarray) -> np.ndarray:
    """Freedman-Diaconis rule: width = 2*IQR*N^(-1/3); then np.arange up to max_obs + inf tail."""
    obs = np.asarray(obs_delta_rv, dtype=float).ravel()
    obs = obs[np.isfinite(obs)]
    if obs.size < 2:
        return np.array([0.0, 1.0, np.inf])
    q75, q25 = np.percentile(obs, [75.0, 25.0])
    iqr = float(q75 - q25)
    n_obs = int(obs.size)
    raw_width = 2.0 * iqr * (n_obs ** (-1.0 / 3.0)) if iqr > 0 else 0.0
    # Ceil to integer km/s to avoid sub-km bins
    width = max(int(np.ceil(raw_width)), 1)
    hi = max(float(obs.max()), width * 2.0)
    edges = np.arange(0.0, hi + width, float(width))
    # Ensure edges contain at least [0, hi]
    if edges.size < 2:
        edges = np.array([0.0, hi])
    return np.concatenate([edges, [np.inf]])


def _anchored(
    n_anchors: int,
    threshold: float,
    max_obs: float,
    obs_delta_rv: np.ndarray,
) -> np.ndarray:
    """Anchor-point scheme.

    Edges = [0, threshold, <inflection anchors>, max_obs, inf].
    Inflections are found as local maxima of a smoothed empirical density of
    ``obs_delta_rv``. If fewer than *n_anchors* inflections are detected the
    remaining anchor slots are filled with evenly-spaced points between
    ``threshold`` and ``max_obs``.
    Fallback when detection fails entirely: [0, threshold, max_obs, inf].
    """
    n = max(int(n_anchors), 0)
    thr = float(threshold)
    hi = max(float(max_obs), thr * 2.0)
    obs = np.asarray(obs_delta_rv, dtype=float).ravel()
    obs = obs[np.isfinite(obs)]

    # Base fallback
    base = [0.0, thr, hi, np.inf]
    if n == 0 or obs.size < 4:
        return _ensure_sorted_with_inf_tail(np.array(base, dtype=float))

    try:
        from scipy.signal import find_peaks
    except Exception:
        # Scipy not available — fall back to equally-spaced anchors between thr and hi
        if n > 0:
            mids = np.linspace(thr, hi, n + 2)[1:-1]
            return _ensure_sorted_with_inf_tail(
                np.concatenate([[0.0, thr], mids, [hi, np.inf]]))
        return _ensure_sorted_with_inf_tail(np.array(base, dtype=float))

    # Build a smoothed empirical density on a uniform grid between thr and hi
    grid_n = 128
    grid = np.linspace(max(thr, 1.0), hi, grid_n)
    bw = max((hi - thr) / 20.0, 1.0)  # km/s
    # Gaussian kernel density estimate (cheap, no scipy dependency)
    diffs = (grid[:, None] - obs[None, :]) / bw
    pdf = np.exp(-0.5 * diffs ** 2).sum(axis=1)
    if pdf.max() <= 0:
        return _ensure_sorted_with_inf_tail(np.array(base, dtype=float))
    pdf = pdf / pdf.max()

    # Find peaks in the smoothed density (d(pdf)/dx zero-crossings)
    peaks, _ = find_peaks(pdf)
    if peaks.size == 0:
        # Fall back to evenly-spaced anchors
        mids = np.linspace(thr, hi, n + 2)[1:-1]
        return _ensure_sorted_with_inf_tail(
            np.concatenate([[0.0, thr], mids, [hi, np.inf]]))

    # Sort peaks by descending density so we pick the strongest first
    peaks_sorted = peaks[np.argsort(-pdf[peaks])]
    chosen = grid[peaks_sorted[:n]]
    # Pad with evenly-spaced anchors if we still need more
    if chosen.size < n:
        extra = np.linspace(thr, hi, n - chosen.size + 2)[1:-1]
        chosen = np.concatenate([chosen, extra])
    return _ensure_sorted_with_inf_tail(
        np.concatenate([[0.0, thr], chosen, [hi, np.inf]]))


def _custom(custom_str: Optional[str]) -> np.ndarray:
    """Parse a comma-separated string of floats into a sorted edge array.

    Tolerates 'inf' and 'infinity' as the last entry. Always prepends 0.0 and
    appends np.inf if missing.
    """
    if custom_str is None or not str(custom_str).strip():
        return np.array([0.0, np.inf])
    parts = [p.strip().lower() for p in str(custom_str).split(",") if p.strip()]
    vals: list[float] = []
    for p in parts:
        if p in ("inf", "infinity", "+inf", "np.inf"):
            vals.append(np.inf)
        else:
            try:
                vals.append(float(p))
            except ValueError:
                continue
    return _ensure_sorted_with_inf_tail(np.array(vals, dtype=float))


def build_edges(
    family: str,
    n_bins: int = 10,
    threshold: float = 45.5,
    max_obs: float = 500.0,
    obs_delta_rv: Optional[np.ndarray] = None,
    custom: Optional[str] = None,
) -> np.ndarray:
    """Dispatcher — returns bin edges for the requested family.

    Parameters
    ----------
    family
        One of :data:`SCHEME_FAMILIES`.
    n_bins
        For parametric families (equal_width, log_spaced, quantile, anchored).
    threshold
        Detection threshold in km/s (anchor for Dsilva-style and anchored schemes).
    max_obs
        Upper reach for equal_width / log_spaced / anchored when obs is unavailable.
    obs_delta_rv
        Observed ΔRV array (needed for quantile, freedman_diaconis, anchored).
    custom
        Comma-separated edge string (only for family='custom').
    """
    fam = str(family).lower().strip()
    if fam == "dsilva_default":
        edges = _dsilva_default(threshold)
    elif fam == "dsilva_shift_plus":
        edges = _dsilva_shift_plus(threshold)
    elif fam == "equal_width":
        edges = _equal_width(n_bins, max_obs)
    elif fam == "log_spaced":
        edges = _log_spaced(n_bins, threshold, max_obs)
    elif fam == "quantile":
        if obs_delta_rv is None:
            raise ValueError("quantile scheme requires obs_delta_rv")
        edges = _quantile(n_bins, obs_delta_rv)
    elif fam == "freedman_diaconis":
        if obs_delta_rv is None:
            raise ValueError("freedman_diaconis scheme requires obs_delta_rv")
        edges = _freedman_diaconis(obs_delta_rv)
    elif fam == "anchored":
        if obs_delta_rv is None:
            raise ValueError("anchored scheme requires obs_delta_rv")
        edges = _anchored(n_bins, threshold, max_obs, obs_delta_rv)
    elif fam == "custom":
        edges = _custom(custom)
    else:
        raise ValueError(f"Unknown bin-scheme family: {family!r}")
    return _ensure_sorted_with_inf_tail(edges)


def scheme_label(family: str, n_bins: int) -> str:
    """Render a canonical scheme label used as a dict key and table row.

    Examples
    --------
    >>> scheme_label("dsilva_default", 4)
    'dsilva_default'
    >>> scheme_label("equal_width", 10)
    'equal_width_10'
    """
    fam = str(family).lower().strip()
    if fam in ("dsilva_default", "dsilva_shift_plus", "freedman_diaconis", "custom"):
        return fam
    return f"{fam}_{int(n_bins)}"


def n_bins_from_edges(edges: np.ndarray) -> int:
    """Number of bins = len(edges) - 1. Treats inf tail as a bin."""
    e = np.asarray(edges, dtype=float).ravel()
    return max(int(e.size) - 1, 0)
