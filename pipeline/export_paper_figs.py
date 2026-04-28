"""pipeline/export_paper_figs.py
================================

Export A&A-journal-ready PDF figures for the LMC WC-WR binary paper.

Figures produced (all in ``plots/``):

  - ``cdf_obs_vs_sim.pdf``        (Fig 4)
  - ``fbin_pi_heatmap.pdf``       (Fig 5)
  - ``fbin_pi_marginals.pdf``     (Fig 6)
  - ``langer_heatmap.pdf``        (Fig 7)
  - ``peak_drv_per_star.pdf``     (Fig 2; rebuilt from ObservationManager)
  - ``threshold_derivation.pdf``  (Fig 3, empirical-only — see DEFER notes)

Deferred (need full Plots.ipynb context — `df`, `_is_significant_binary`,
`ew_fail_stats`, etc., which are only built after running ~40 notebook cells
that depend on ObservationManager + per-line CCF cache):

  - ``agreement.pdf``  (Fig 1; per-line correlation across 11 emission lines)

Style: A&A-journal — white background, mirrored black axes, no gridlines,
serif font.  Single-column ~88 mm wide; two-column ~180 mm.

Usage:
    conda run -n guyenv python pipeline/export_paper_figs.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

# ── Path fix: allow running from anywhere ────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ─────────────────────────────────────────────────────────────────────────────
# A&A journal style — set via rcParams so every matplotlib figure inherits it
# ─────────────────────────────────────────────────────────────────────────────
_AA_RC: dict = {
    'figure.facecolor':  'white',
    'axes.facecolor':    'white',
    'savefig.facecolor': 'white',
    'savefig.edgecolor': 'white',
    'savefig.bbox':      'tight',
    'savefig.pad_inches': 0.02,
    # Serif typography (Times New Roman fallback to serif if not found)
    'font.family':       'serif',
    'font.serif':        ['Times New Roman', 'Times', 'STIXGeneral',
                          'DejaVu Serif', 'serif'],
    'mathtext.fontset':  'stix',
    'font.size':         9,
    'axes.titlesize':    10,
    'axes.labelsize':    9,
    'xtick.labelsize':   8,
    'ytick.labelsize':   8,
    'legend.fontsize':   8,
    'legend.frameon':    True,
    'legend.framealpha': 1.0,
    'legend.edgecolor':  'black',
    # Black mirrored axes; outside ticks; no grid
    'axes.edgecolor':    'black',
    'axes.linewidth':    0.8,
    'axes.spines.top':    True,
    'axes.spines.right':  True,
    'axes.spines.bottom': True,
    'axes.spines.left':   True,
    'axes.grid':         False,
    'xtick.direction':   'out',
    'ytick.direction':   'out',
    'xtick.major.size':  3.5,
    'ytick.major.size':  3.5,
    'xtick.minor.size':  2.0,
    'ytick.minor.size':  2.0,
    'xtick.color':       'black',
    'ytick.color':       'black',
    'xtick.top':          True,
    'ytick.right':        True,
    'pdf.fonttype':      42,   # embed Type-42 (TrueType) — A&A requirement
    'ps.fonttype':       42,
}
plt.rcParams.update(_AA_RC)


# ─────────────────────────────────────────────────────────────────────────────
# Figure-size presets (width × height in inches)
# ─────────────────────────────────────────────────────────────────────────────
FS_SC_SQUARE  = (3.5, 3.0)   # ~88 mm single-column, ~3:2.5
FS_SC_WIDE    = (3.5, 2.6)
FS_SC_TALL    = (3.5, 4.2)   # 1×2 stacked marginals
FS_DC_HALF    = (7.0, 2.8)   # ~180 mm two-column, single row
FS_DC_HALF_HI = (7.0, 3.2)


# ─────────────────────────────────────────────────────────────────────────────
# Path helpers
# ─────────────────────────────────────────────────────────────────────────────
PLOTS_DIR    = _ROOT / 'plots'
RESULTS_DIR  = _ROOT / 'results'
DSILVA_NPZ   = (RESULTS_DIR / 'cadence_dsilva_fb0.0-1.0x99_pi-3.0-3.0x100_'
                              'N1000_sig1.0-7.0x15_logP2.00-6.00x15_'
                              '260421-0211.npz')
LANGER_NPZ   = (RESULTS_DIR / 'cadence_langer_fb0.0-1.0x99_pi0.0-0.0x1_'
                              'N10000_sig0.1-9.0x100_logP1.00-9.00x100_'
                              '260331-0842.npz')
THRESH_KMS   = 45.5
SIGMA_FACTOR = 4.0


def _ensure_plots_dir() -> None:
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)


def _save(fig: plt.Figure, name: str) -> Path:
    """Save *fig* to ``plots/{name}`` as PDF and return the path."""
    out = PLOTS_DIR / name
    fig.savefig(out, format='pdf')
    plt.close(fig)
    print(f'  ✔ wrote {out.relative_to(_ROOT)}  ({out.stat().st_size / 1024:.0f} KB)')
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Posterior helpers (marginalisation, joint argmax, HDI68 contour)
# ─────────────────────────────────────────────────────────────────────────────

def _marginal_2d_fbin_pi(npz: dict) -> np.ndarray:
    """Profile-out logPmax (max), then sum over sigma → (n_fbin, n_pi).

    Matches the project's HDI convention in
    ``app/bc/runners_cadence.py`` (``_L_for_hdi = nanmax(L, axis=0)`` then
    ``sum(axis=...)``).  Axis order in the npz is
    ``[logPmax, sigma, fbin, pi]`` (per runners_cadence.py:592–596).
    Returns a ``(n_fbin, n_pi)`` array normalised to sum to 1.
    """
    lk = npz['likelihood']
    # Profile out logPmax (axis 0) by taking the max
    lk_p = np.nanmax(lk, axis=0)            # shape (n_sigma, n_fbin, n_pi)
    # Marginalise out sigma (axis 0 of the reduced array)
    marg = lk_p.sum(axis=0)                 # shape (n_fbin, n_pi)
    s = marg.sum()
    return marg / s if s > 0 else marg


def _marginal_2d_fbin_sigma(npz: dict) -> np.ndarray:
    """Profile-out logPmax (max), then sum over pi → (n_sigma, n_fbin).

    For Langer files ``pi_grid`` has length 1 so the sum is degenerate.
    """
    lk = npz['likelihood']
    lk_p = np.nanmax(lk, axis=0)            # shape (n_sigma, n_fbin, n_pi)
    marg = lk_p.sum(axis=2)                 # shape (n_sigma, n_fbin)
    s = marg.sum()
    return marg / s if s > 0 else marg


def _hdi_mask_2d(post: np.ndarray, frac: float = 0.68) -> np.ndarray:
    """Boolean mask of cells inside the highest-density-interval covering
    cumulative probability ``frac`` of *post*."""
    flat = post.flatten()
    order = np.argsort(flat)[::-1]   # descending
    cum = np.cumsum(flat[order])
    cutoff_idx = int(np.searchsorted(cum, frac * cum[-1])) + 1
    threshold = flat[order[min(cutoff_idx, len(order) - 1)]]
    return post >= threshold


def _hdi_1d(values: np.ndarray, density: np.ndarray,
            frac: float = 0.68) -> tuple[float, float, float]:
    """Highest-density 1D interval.  Returns (mode, lo, hi)."""
    if density.sum() <= 0:
        return float('nan'), float('nan'), float('nan')
    p = density / density.sum()
    order = np.argsort(p)[::-1]
    cum = np.cumsum(p[order])
    cutoff = int(np.searchsorted(cum, frac)) + 1
    mask = np.zeros_like(p, dtype=bool)
    mask[order[:cutoff]] = True
    inside = values[mask]
    return float(values[np.argmax(p)]), float(inside.min()), float(inside.max())


# ─────────────────────────────────────────────────────────────────────────────
# Figure 4 — Observed vs simulated CDF
# ─────────────────────────────────────────────────────────────────────────────

def fig_cdf_obs_vs_sim(npz: dict) -> Path:
    obs = np.sort(np.asarray(npz['obs_delta_rv'], dtype=float))
    bin_edges = np.asarray(npz['bin_edges'], dtype=float)
    med = np.asarray(npz['best_median_cdf'], dtype=float)
    lo  = np.asarray(npz['best_lo_cdf'], dtype=float)
    hi  = np.asarray(npz['best_hi_cdf'], dtype=float)
    lk_edges = np.asarray(npz['likelihood_bin_edges'], dtype=float)

    n = len(obs)
    obs_y = np.arange(1, n + 1) / n   # empirical CDF

    x_max = max(float(obs.max()), float(bin_edges.max())) * 1.04

    fig, ax = plt.subplots(figsize=FS_SC_SQUARE)
    # Best-fit simulation 16/84 band
    ax.fill_between(bin_edges, lo, hi,
                    color='#E25A53', alpha=0.20, linewidth=0,
                    label='Best-fit MC 16–84%')
    # Best-fit median curve (dashed red)
    ax.plot(bin_edges, med,
            color='#D62728', linestyle='--', linewidth=1.4,
            label='Best-fit MC median')
    # Observed empirical step (black solid)
    ax.step(obs, obs_y, where='post',
            color='#000000', linewidth=1.4,
            label=f'Observed ($N = {n}$)')
    # Place an opening dot at (obs.min, 0) for readability — extend down to 0
    ax.plot([obs[0], obs[0]], [0, obs_y[0]],
            color='#000000', linewidth=1.4)
    # Multinomial bin edges
    finite_lk = lk_edges[np.isfinite(lk_edges)]
    for x in finite_lk:
        if x <= 0:
            continue
        ax.axvline(x, color='#888888', linestyle=':', linewidth=0.8, zorder=0)
    # 45.5 km/s threshold marker
    ax.axvline(THRESH_KMS, color='#DAA520', linestyle='--', linewidth=1.0,
               zorder=1)
    ax.text(THRESH_KMS, 0.05, f' {THRESH_KMS:.1f} km/s',
            color='#B8860B', fontsize=7, ha='left', va='bottom')

    ax.set_xlim(0, x_max)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel(r'$\Delta\mathrm{RV}_\mathrm{max}$ (km s$^{-1}$)')
    ax.set_ylabel('Cumulative fraction')
    ax.set_title('Observed vs Best-fit Monte-Carlo CDF')
    ax.legend(loc='lower right', fontsize=7,
              facecolor='white', edgecolor='black', framealpha=1.0)
    fig.tight_layout()
    return _save(fig, 'cdf_obs_vs_sim.pdf')


# ─────────────────────────────────────────────────────────────────────────────
# Figure 5 — (f_bin, π) log-likelihood heatmap with HDI68 contour
# ─────────────────────────────────────────────────────────────────────────────

def fig_fbin_pi_heatmap(npz: dict) -> Path:
    fbin = np.asarray(npz['fbin_grid'], dtype=float)
    pi   = np.asarray(npz['pi_grid'],   dtype=float)
    L    = np.asarray(npz['logL_raw'],  dtype=float)   # (sigma, logP, fbin, pi)

    # Marginal posterior over (fbin, pi) — sum likelihood
    post = _marginal_2d_fbin_pi(npz)            # shape (n_fbin, n_pi)
    # Joint argmax over the FULL 4D grid
    i_sig, i_logP, i_fb, i_pi = np.unravel_index(np.argmax(L), L.shape)
    fb_argmax  = float(fbin[i_fb])
    pi_argmax  = float(pi[i_pi])

    # log-likelihood marginalised analogously (so the colour scale matches
    # the marginal likelihood surface — convert post back to logL units).
    # Use logL = log(marginal_likelihood); add tiny eps to avoid log(0).
    eps = post[post > 0].min() * 1e-3 if (post > 0).any() else 1e-30
    logL_marg = np.log(post + eps)               # (n_fbin, n_pi)

    # HDI68 mask (in linear posterior)
    hdi_mask = _hdi_mask_2d(post, frac=0.68)     # (n_fbin, n_pi)

    fig, ax = plt.subplots(figsize=FS_SC_SQUARE)
    extent = [pi[0], pi[-1], fbin[0], fbin[-1]]   # x = pi, y = fbin
    # logL heatmap
    im = ax.imshow(logL_marg, origin='lower', aspect='auto',
                   extent=extent, cmap='viridis', interpolation='nearest')
    # HDI68 contour — single white outline at 0.5 boundary
    ax.contour(pi, fbin, hdi_mask.astype(float),
               levels=[0.5], colors='#FFFFFF', linewidths=1.2)
    # Joint argmax — red cross
    ax.plot(pi_argmax, fb_argmax, marker='x', color='#D62728',
            markersize=8, markeredgewidth=2.0, zorder=5)

    cb = fig.colorbar(im, ax=ax, fraction=0.045, pad=0.04)
    cb.set_label(r'$\log\,\mathcal{L}_\mathrm{marg}(f_\mathrm{bin},\pi)$')
    cb.ax.tick_params(colors='black')
    cb.outline.set_edgecolor('black')

    ax.set_xlabel(r'$\pi$ (period-index slope)')
    ax.set_ylabel(r'$f_\mathrm{bin}$')
    ax.set_title(r'Marginal log-likelihood $(f_\mathrm{bin},\pi)$')
    fig.tight_layout()
    return _save(fig, 'fbin_pi_heatmap.pdf')


# ─────────────────────────────────────────────────────────────────────────────
# Figure 6 — 1D marginals of f_bin and π
# ─────────────────────────────────────────────────────────────────────────────

def fig_fbin_pi_marginals(npz: dict) -> Path:
    fbin = np.asarray(npz['fbin_grid'], dtype=float)
    pi   = np.asarray(npz['pi_grid'],   dtype=float)
    L    = np.asarray(npz['logL_raw'],  dtype=float)
    post = _marginal_2d_fbin_pi(npz)
    p_fb = post.sum(axis=1)   # marginal over pi   → (n_fbin,)
    p_pi = post.sum(axis=0)   # marginal over fbin → (n_pi,)

    # Joint argmax (same as in fig 5) — these vlines must come from the joint
    # 4D argmax, NOT from each 1D marginal max (per memory rule
    # "honest labels: joint argmax + 68% HDI only, no marginal mode").
    i_sig, i_logP, i_fb, i_pi = np.unravel_index(np.argmax(L), L.shape)
    fb_argmax = float(fbin[i_fb])
    pi_argmax = float(pi[i_pi])

    # Per-axis HDI68 from the 1D marginal density
    _, fb_lo, fb_hi = _hdi_1d(fbin, p_fb, frac=0.68)
    _, pi_lo, pi_hi = _hdi_1d(pi,   p_pi, frac=0.68)

    fig, axs = plt.subplots(1, 2, figsize=FS_DC_HALF)
    ax_fb, ax_pi = axs

    # f_bin marginal
    ax_fb.plot(fbin, p_fb / p_fb.max(),
               color='#000000', linewidth=1.4)
    in_hdi = (fbin >= fb_lo) & (fbin <= fb_hi)
    ax_fb.fill_between(fbin, 0, p_fb / p_fb.max(),
                       where=in_hdi, color='#4A90D9', alpha=0.30,
                       linewidth=0, label='68% HDI')
    ax_fb.axvline(fb_argmax, color='#D62728', linewidth=1.3,
                  label=f'argmax = {fb_argmax:.3f}')
    ax_fb.axvline(fb_lo, color='#4A90D9', linestyle='--', linewidth=0.9)
    ax_fb.axvline(fb_hi, color='#4A90D9', linestyle='--', linewidth=0.9)
    ax_fb.set_xlabel(r'$f_\mathrm{bin}$')
    ax_fb.set_ylabel('Marginal density (norm.)')
    ax_fb.set_xlim(fbin[0], fbin[-1])
    ax_fb.set_ylim(0, 1.05)
    ax_fb.set_title(r'Marginal posterior $f_\mathrm{bin}$')
    ax_fb.legend(loc='upper right', fontsize=7,
                 facecolor='white', edgecolor='black', framealpha=1.0)

    # π marginal
    ax_pi.plot(pi, p_pi / p_pi.max(),
               color='#000000', linewidth=1.4)
    in_hdi_pi = (pi >= pi_lo) & (pi <= pi_hi)
    ax_pi.fill_between(pi, 0, p_pi / p_pi.max(),
                       where=in_hdi_pi, color='#4A90D9', alpha=0.30,
                       linewidth=0, label='68% HDI')
    ax_pi.axvline(pi_argmax, color='#D62728', linewidth=1.3,
                  label=f'argmax = {pi_argmax:.2f}')
    ax_pi.axvline(pi_lo, color='#4A90D9', linestyle='--', linewidth=0.9)
    ax_pi.axvline(pi_hi, color='#4A90D9', linestyle='--', linewidth=0.9)
    ax_pi.set_xlabel(r'$\pi$ (period-index slope)')
    ax_pi.set_ylabel('Marginal density (norm.)')
    ax_pi.set_xlim(pi[0], pi[-1])
    ax_pi.set_ylim(0, 1.05)
    ax_pi.set_title(r'Marginal posterior $\pi$')
    ax_pi.legend(loc='upper right', fontsize=7,
                 facecolor='white', edgecolor='black', framealpha=1.0)

    fig.tight_layout()
    return _save(fig, 'fbin_pi_marginals.pdf')


# ─────────────────────────────────────────────────────────────────────────────
# Figure 7 — Langer model heatmap (f_bin, σ_single)
# ─────────────────────────────────────────────────────────────────────────────

def fig_langer_heatmap(npz: dict) -> Path:
    fbin   = np.asarray(npz['fbin_grid'],    dtype=float)
    sigma  = np.asarray(npz['sigma_grid'],   dtype=float)
    L      = np.asarray(npz['logL_raw'],     dtype=float)   # (sigma, logP, fbin, pi)

    # Langer file has pi_grid of size 1, so axis 3 collapses cleanly
    # Marginalise out logPmax (axis 1) and pi (axis 3) → (n_sigma, n_fbin)
    post = _marginal_2d_fbin_sigma(npz)

    # Joint argmax in original 4D
    i_sig, i_logP, i_fb, i_pi = np.unravel_index(np.argmax(L), L.shape)
    fb_argmax    = float(fbin[i_fb])
    sigma_argmax = float(sigma[i_sig])

    eps = post[post > 0].min() * 1e-3 if (post > 0).any() else 1e-30
    logL_marg = np.log(post + eps)   # (n_sigma, n_fbin)

    hdi_mask = _hdi_mask_2d(post, frac=0.68)

    fig, ax = plt.subplots(figsize=FS_SC_SQUARE)
    extent = [fbin[0], fbin[-1], sigma[0], sigma[-1]]   # x = fbin, y = sigma
    im = ax.imshow(logL_marg, origin='lower', aspect='auto',
                   extent=extent, cmap='viridis', interpolation='nearest')
    ax.contour(fbin, sigma, hdi_mask.astype(float),
               levels=[0.5], colors='#FFFFFF', linewidths=1.2)
    ax.plot(fb_argmax, sigma_argmax, marker='x', color='#D62728',
            markersize=8, markeredgewidth=2.0, zorder=5)

    cb = fig.colorbar(im, ax=ax, fraction=0.045, pad=0.04)
    cb.set_label(r'$\log\,\mathcal{L}_\mathrm{marg}(f_\mathrm{bin},\sigma_\mathrm{single})$')
    cb.ax.tick_params(colors='black')
    cb.outline.set_edgecolor('black')

    ax.set_xlabel(r'$f_\mathrm{bin}$')
    ax.set_ylabel(r'$\sigma_\mathrm{single}$ (km s$^{-1}$)')
    ax.set_title(r'Langer model: marginal $\log\mathcal{L}(f_\mathrm{bin},\sigma)$')
    fig.tight_layout()
    return _save(fig, 'langer_heatmap.pdf')


# ─────────────────────────────────────────────────────────────────────────────
# Figure 2 — Per-star peak ΔRV bar chart
# ─────────────────────────────────────────────────────────────────────────────

def fig_peak_drv_per_star() -> Path:
    """Re-build per-star peak ΔRV using ObservationManager + CCF property cache.

    Two binary criteria (matches `_classify` in
    `pipeline/load_observations.py`):
      (1) ΔRV > T  (T = 45.5 km/s)
      (2) ΔRV − 4σ > 0
    Stars satisfying both → red; failing → steel-blue/grey.
    """
    from pipeline.load_observations import load_observed_delta_rvs
    drv, detail = load_observed_delta_rvs()

    # Build a list of (star, drv, sigma, is_binary) and sort by drv desc
    rows: list = []
    for star, det in detail.items():
        d = float(det['best_dRV'])
        s = float(det['best_sigma']) if np.isfinite(det['best_sigma']) else 0.0
        ib = bool(det['is_binary']) if det['is_binary'] is not None else False
        rows.append((star, d, s, ib, len(det['rv'])))
    # Drop zero-ΔRV (stars without enough epochs) for clarity
    rows = [r for r in rows if r[1] > 0]
    rows.sort(key=lambda r: r[1], reverse=True)

    names    = [r[0] for r in rows]
    vals     = np.array([r[1] for r in rows], dtype=float)
    sigs     = np.array([r[2] for r in rows], dtype=float)
    is_bin   = np.array([r[3] for r in rows], dtype=bool)

    # Error bars: 4σ_p2p
    err = SIGMA_FACTOR * sigs

    n = len(rows)
    fig, ax = plt.subplots(figsize=(3.5, max(3.0, 0.16 * n + 0.8)))
    y = np.arange(n)
    colors = ['#D62728' if b else '#4A90D9' for b in is_bin]
    ax.barh(y, vals, color=colors, edgecolor='black',
            linewidth=0.4, height=0.7)
    # 4σ error bars on top
    ax.errorbar(vals, y, xerr=err, fmt='none', ecolor='black',
                elinewidth=0.7, capsize=2.0, zorder=3)
    # Threshold vline
    ax.axvline(THRESH_KMS, color='#000000', linestyle='--', linewidth=1.0)
    ax.text(THRESH_KMS, n - 0.5, f' $T = {THRESH_KMS:.1f}$ km s$^{{-1}}$',
            color='#000000', fontsize=7, ha='left', va='top')

    ax.set_yticks(y)
    ax.set_yticklabels(names, fontsize=7)
    ax.invert_yaxis()
    ax.set_xlabel(r'$\Delta\mathrm{RV}_\mathrm{max}$ (km s$^{-1}$)')
    ax.set_xlim(0, max(float(vals.max() + err.max()), THRESH_KMS) * 1.10)
    ax.set_title('Peak-to-peak $\\Delta$RV per star (C IV 5808)')

    # Legend (manual, two-colour swatch)
    from matplotlib.patches import Patch
    leg = [Patch(facecolor='#D62728', edgecolor='black', label='Binary (both criteria)'),
           Patch(facecolor='#4A90D9', edgecolor='black', label='Single')]
    ax.legend(handles=leg, loc='lower right', fontsize=7,
              facecolor='white', edgecolor='black', framealpha=1.0)

    fig.tight_layout()
    return _save(fig, 'peak_drv_per_star.pdf')


# ─────────────────────────────────────────────────────────────────────────────
# Figure 3 — Threshold derivation: empirical f_bin(>T) + two-Gaussian fit
# ─────────────────────────────────────────────────────────────────────────────

def fig_threshold_derivation() -> Path:
    """Cumulative f_bin(>T) vs T from observed peak-to-peak ΔRV, with the
    two-Gaussian survival-function fit per `methods.tex` Eq.~\\ref{eq:gauss_threshold}:

        f_bin(>T) = (1 - f_bin) Φ(T/σ_s) + f_bin Φ(T/σ_b)

    where Φ = ``scipy.stats.norm.sf`` is the standard-normal survival
    function.  Implementation mirrors ``_model_gauss`` from
    ``rv_modeling/compute.py:142–143``.

    σ_s is **fixed at 5 km/s** (instrumental-noise floor — see project
    notes; ΔRV uncertainties for X-SHOOTER cluster around 3–6 km/s).
    Only (σ_b, f_bin) are free parameters.  This breaks the σ_s/σ_b
    degeneracy that drove the unconstrained fit to a boundary.

    The empirical curve is built from ``best_dRV`` per star (matching the
    construction in ``rv_modeling/page.py:39–53``).  We fit the unfiltered
    ``raw_frac`` (= N(>T)/N) — the σ-significance criterion is a separate
    selection effect, not part of the two-Gaussian decomposition.
    """
    from pipeline.load_observations import load_observed_delta_rvs
    from scipy.stats import norm
    from scipy.optimize import curve_fit

    drv, detail = load_observed_delta_rvs()
    names = sorted(detail.keys())
    p2p     = np.array([detail[n]['best_dRV']  for n in names], dtype=float)
    p2p_err = np.array([detail[n]['best_sigma'] for n in names], dtype=float)
    # Drop stars with no measurable ΔRV (zero-pair); they do not contribute
    valid_mask = p2p > 0
    p2p     = p2p[valid_mask]
    p2p_err = p2p_err[valid_mask]
    n_stars = len(p2p)

    T_MAX         = 301
    t_full = np.arange(0, T_MAX, dtype=float)
    raw_frac  = np.array([float(np.sum(p2p > t)) / n_stars for t in t_full])

    # Two-Gaussian survival model — σ_s FIXED, only (σ_b, f_bin) free
    SIGMA_S_FIXED = 5.0   # km/s, instrumental noise floor

    def _model_gauss(t, sigma_s, sigma_b, f_bin):
        return ((1 - f_bin) * norm.sf(t / sigma_s)
                + f_bin       * norm.sf(t / sigma_b))

    def _model_gauss_fixed_s(t, sigma_b, f_bin):
        return _model_gauss(t, SIGMA_S_FIXED, sigma_b, f_bin)

    # Constrained fit: σ_b ∈ [σ_s, 300], f_bin ∈ [0, 1]
    sigma_s_fit = SIGMA_S_FIXED
    sigma_b_fit = f_bin_fit = None
    sigma_b_err = f_bin_err = float('nan')
    boundary_flag = ''
    try:
        popt, pcov = curve_fit(
            _model_gauss_fixed_s, t_full, raw_frac,
            p0=[60.0, 0.4],
            bounds=([SIGMA_S_FIXED + 0.1, 0.0],
                    [300.0,                1.0]))
        sigma_b_fit = float(popt[0])
        f_bin_fit   = float(popt[1])
        perr = np.sqrt(np.diag(pcov))
        sigma_b_err = float(perr[0])
        f_bin_err   = float(perr[1])
        flags = []
        if abs(sigma_b_fit - 300.0) < 1e-3 or abs(sigma_b_fit - (SIGMA_S_FIXED + 0.1)) < 1e-3:
            flags.append('σ_b at bound')
        if abs(f_bin_fit - 1.0) < 1e-3 or abs(f_bin_fit - 0.0) < 1e-3:
            flags.append('f_bin at bound')
        boundary_flag = '; '.join(flags) if flags else ''

        print('  ┌── Two-Gaussian fit (σ_s FIXED at 5 km/s) ────────────────────')
        print(f'  │  σ_single (FIXED — instrumental noise)    = {SIGMA_S_FIXED:.1f} km/s')
        print(f'  │  σ_binary (binary RV-spread scale)        = '
              f'{sigma_b_fit:.2f} ± {sigma_b_err:.2f} km/s')
        print(f'  │  f_bin   (analytic threshold-derivation)  = '
              f'{f_bin_fit:.3f} ± {f_bin_err:.3f}')
        if boundary_flag:
            print(f'  │  ⚠ {boundary_flag}.')
        print('  │  → Suggested paper macros:')
        print(f'  │      \\sigmaSingleFit  = {SIGMA_S_FIXED:.1f}    (literal, not a fit)')
        print(f'  │      \\sigmaBinaryFit  = {sigma_b_fit:.1f}')
        print(f'  │      \\fbinAnalytic    = {f_bin_fit:.2f}')
        print('  └─────────────────────────────────────────────────────────────')
    except Exception as exc:
        print(f'  ✗ two-Gaussian fit failed: {exc}')
        return Path('')

    # Build component curves on the dense t grid (use t_full directly — the
    # ΔRV axis spans 0..300 km/s)
    surv_s = norm.sf(t_full / sigma_s_fit)
    surv_b = norm.sf(t_full / sigma_b_fit)
    single_comp  = (1.0 - f_bin_fit) * surv_s
    binary_comp  =        f_bin_fit  * surv_b
    summed       = _model_gauss(t_full, sigma_s_fit, sigma_b_fit, f_bin_fit)

    # Wilson 1σ band on raw_frac (binomial counting)
    raw_err = np.sqrt(raw_frac * (1.0 - raw_frac) / n_stars)

    # ── Plot ─────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=FS_DC_HALF_HI)
    # Empirical step (raw, all-stars survival function)
    ax.step(t_full, raw_frac, where='post',
            color='#000000', linewidth=1.4,
            label=fr'Observed $f(>T) = N(>T)/N$  ($N = {n_stars}$)')
    # 1σ binomial error band
    ax.fill_between(t_full, np.maximum(0, raw_frac - raw_err),
                    np.minimum(1, raw_frac + raw_err),
                    color='#888888', alpha=0.20, linewidth=0,
                    label=r'1$\sigma$ binomial band')
    # Single-component contribution (dashed grey)
    ax.plot(t_full, single_comp,
            color='#888888', linestyle='--', linewidth=1.0,
            label=fr'Single component  $(1-f_\mathrm{{bin}})\,\Phi(T/\sigma_s)$')
    # Binary-component contribution (dashed red)
    ax.plot(t_full, binary_comp,
            color='#E25A53', linestyle='--', linewidth=1.0,
            label=fr'Binary component   $f_\mathrm{{bin}}\,\Phi(T/\sigma_b)$')
    # Summed two-Gaussian model (solid red)
    ax.plot(t_full, summed,
            color='#D62728', linestyle='-', linewidth=1.4,
            label=fr'Two-Gaussian fit')
    # Threshold marker
    ax.axvline(THRESH_KMS, color='#DAA520', linestyle='--', linewidth=1.0)
    ax.text(THRESH_KMS, 0.96, f' $T = {THRESH_KMS:.1f}$ km s$^{{-1}}$',
            color='#B8860B', fontsize=7, ha='left', va='top')

    # Annotation box with fit results — σ_s shown as fixed
    txt = (fr'$\sigma_s = {SIGMA_S_FIXED:.1f}$ km s$^{{-1}}$ (fixed)' '\n'
           fr'$\sigma_b = {sigma_b_fit:.1f} \pm {sigma_b_err:.1f}$ km s$^{{-1}}$' '\n'
           fr'$f_\mathrm{{bin}} = {f_bin_fit:.2f} \pm {f_bin_err:.2f}$')
    if boundary_flag:
        txt += '\n' + fr'($\!$ {boundary_flag} $\!$)'
    ax.text(0.97, 0.62, txt, transform=ax.transAxes,
            ha='right', va='top', fontsize=8,
            bbox=dict(boxstyle='round,pad=0.4', facecolor='white',
                      edgecolor='black', linewidth=0.6))

    ax.set_xlim(0, T_MAX - 1)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel(r'$T$ (km s$^{-1}$)')
    ax.set_ylabel(r'$f(>T)$')
    ax.set_title(r'Cumulative $\Delta$RV distribution and two-Gaussian fit')
    ax.legend(loc='upper right', fontsize=7,
              facecolor='white', edgecolor='black', framealpha=1.0)
    fig.tight_layout()
    return _save(fig, 'threshold_derivation.pdf')


# ─────────────────────────────────────────────────────────────────────────────
# Figure A — Per-line agreement ranking + S_ℓ vs equivalent width
# ─────────────────────────────────────────────────────────────────────────────

def _build_per_line_drv_table() -> tuple:
    """Return (df, ew_stats, ordered_lines) by walking ObservationManager
    over all 25 stars × 11 emission lines.

    df : pd.DataFrame with one row per star and one column per line, holding
         the per-star peak-to-peak ΔRV computed from the (full_RV, full_RV_err)
         pairs stored in the ``RVs`` property.  Stars with <2 valid epochs for
         a line have NaN in that cell.
    ew_stats : dict[line] = (success_rate, mean_EW, sem_EW)  — built from the
         ``EWs`` property (per-epoch (EW, sigma_EW) records).
    ordered_lines : list[str]  — the 11-line canonical order from
         ``ccf_settings_with_global_lines.json``.
    """
    import json
    import math
    import pandas as pd
    from pipeline.load_observations import _make_obs

    settings_path = _ROOT / 'ccf_settings_with_global_lines.json'
    if not settings_path.is_file():
        raise FileNotFoundError(f'CCF settings JSON not found: {settings_path}')
    with open(settings_path) as fh:
        cfg = json.load(fh)
    lines_default = cfg.get('emission_lines_default', {})
    ordered_lines = list(lines_default.keys())
    star_cfg = {s['star_name']: s for s in cfg.get('stars', [])}

    import specs
    obs = _make_obs()

    # Helpers (mirror Plots.ipynb cell 36)
    def _is_skipped(star_name: str, line_key: str, ep: int) -> bool:
        sc = star_cfg.get(star_name, {})
        if ep in set(sc.get('skip_epochs', [])):
            return True
        sl = sc.get('skip_emission_lines', {})
        if line_key in sl:
            skip_eps = sl[line_key]
            if isinstance(skip_eps, (int, np.integer)):
                skip_eps = [skip_eps]
            if 0 in skip_eps or ep in skip_eps:
                return True
        return False

    def _extract_full_rv(cell):
        try:
            if isinstance(cell, dict):
                return cell.get('full_RV')
            if hasattr(cell, 'item'):
                v = cell.item()
                if isinstance(v, dict):
                    return v.get('full_RV')
        except Exception:
            return None
        return None

    def _extract_full_rv_err(cell):
        keys = ('full_RV_err', 'full_err', 'sigma', 'err',
                'RV_err', 'RV_sigma')
        try:
            if isinstance(cell, dict):
                for k in keys:
                    if k in cell and cell[k] is not None:
                        return float(cell[k])
            if hasattr(cell, 'item'):
                v = cell.item()
                if isinstance(v, dict):
                    for k in keys:
                        if k in v and v[k] is not None:
                            return float(v[k])
        except Exception:
            return float('nan')
        return float('nan')

    # Storage
    drv_table:    dict = {ln: {} for ln in ordered_lines}    # line -> star -> ΔRV
    ew_records:   dict = {ln: [] for ln in ordered_lines}    # line -> [EW values]
    ew_attempts:  dict = {ln: 0  for ln in ordered_lines}
    ew_failures:  dict = {ln: 0  for ln in ordered_lines}

    for star_name in specs.star_names:
        try:
            star = obs.load_star_instance(star_name, to_print=False)
        except Exception as exc:
            print(f'    [agreement] WARN load {star_name}: {exc}')
            continue
        epochs = star.get_all_epoch_numbers()
        for line_key in ordered_lines:
            rv_vals: list = []
            err_vals: list = []
            for ep in epochs:
                if _is_skipped(star_name, line_key, ep):
                    continue
                # EW (independent of RV success)
                try:
                    EWs = star.load_property('EWs', ep, 'COMBINED')
                except Exception:
                    EWs = None
                rec = None
                if EWs is not None:
                    try:
                        rec_raw = EWs.get(line_key)
                        if rec_raw is not None:
                            try:
                                rec = rec_raw.item()
                            except Exception:
                                rec = rec_raw if isinstance(rec_raw, dict) else None
                    except Exception:
                        rec = None
                ew_attempts[line_key] += 1
                if rec is not None and isinstance(rec, dict):
                    val = rec.get('EW')
                    try:
                        v = float(val) if val is not None else float('nan')
                    except Exception:
                        v = float('nan')
                    if np.isfinite(v):
                        ew_records[line_key].append(v)
                    else:
                        ew_failures[line_key] += 1
                else:
                    ew_failures[line_key] += 1

                # RV
                try:
                    RVs = star.load_property('RVs', ep, 'COMBINED')
                except Exception:
                    RVs = None
                if RVs is None or line_key not in RVs:
                    continue
                cell = RVs[line_key]
                rv = _extract_full_rv(cell)
                if rv is None:
                    continue
                try:
                    rv_f = float(rv)
                except Exception:
                    continue
                if not np.isfinite(rv_f) or rv_f == 0.0:
                    continue
                err_f = _extract_full_rv_err(cell)
                rv_vals.append(rv_f)
                err_vals.append(err_f if np.isfinite(err_f) else 0.0)

            if len(rv_vals) >= 2:
                rv_arr = np.asarray(rv_vals, dtype=float)
                drv_table[line_key][star_name] = float(rv_arr.max() - rv_arr.min())

    # Convert to DataFrame: rows = stars (specs order), cols = lines (canonical)
    rows = []
    for sn in specs.star_names:
        row = {ln: drv_table[ln].get(sn, np.nan) for ln in ordered_lines}
        rows.append(row)
    df = pd.DataFrame(rows, index=list(specs.star_names), columns=ordered_lines)

    # EW per-line stats
    ew_stats: dict = {}
    for ln in ordered_lines:
        n_att = ew_attempts[ln]
        n_fail = ew_failures[ln]
        succ = (1.0 - n_fail / n_att) if n_att > 0 else 0.0
        vals = np.asarray(ew_records[ln], dtype=float)
        if vals.size > 0:
            mean = float(np.nanmean(vals))
            sem  = float(np.nanstd(vals) / np.sqrt(len(vals)))
        else:
            mean = float('nan')
            sem  = float('nan')
        ew_stats[ln] = (succ, mean, sem)

    return df, ew_stats, ordered_lines


def fig_agreement() -> Path:
    """Fig 1: Per-line agreement-score ranking and S_ℓ vs equivalent width.

    For each emission line ℓ, define
        S_ℓ = Σ_{m≠ℓ} w_{ℓm} r_{ℓm}  /  Σ_{m≠ℓ} 1
    with w_{ℓm} = n_{ℓm} / N_stars and r_{ℓm} = Pearson correlation between
    the per-star ΔRV columns for lines ℓ and m on the n_{ℓm} stars where
    both are measured (valid pairwise mask).  Pairs with n_{ℓm} <
    MIN_STARS_FOR_CORR (= 8) are dropped from the sum.

    Implementation mirrors Plots.ipynb cell 53.

    Two panels (DC, ~7×3):
      Left  — bar ranking of S_ℓ for the 11 lines, sorted descending.
              C IV 5808 (the binary-classifier line) highlighted in red.
      Right — S_ℓ vs equivalent width with error bars on EW (SEM).
    """
    import pandas as pd
    from scipy.stats import pearsonr
    df, ew_stats, ordered_lines = _build_per_line_drv_table()

    # Filter to lines with ≥ MIN_STARS detections (otherwise correlations
    # are undefined). Use the same threshold as the notebook.
    MIN_STARS_FOR_CORR = 8
    MAX_POSSIBLE_STARS = 25

    cols = [ln for ln in ordered_lines if df[ln].notna().sum() >= 2]
    n_lines = len(cols)
    if n_lines < 2:
        raise RuntimeError('Need at least 2 lines with ≥2 stars for agreement.')

    corr_mat = pd.DataFrame(np.nan, index=cols, columns=cols)
    n_mat    = pd.DataFrame(0,       index=cols, columns=cols)
    for i, c1 in enumerate(cols):
        for j, c2 in enumerate(cols):
            if i == j:
                continue
            mask = df[c1].notna() & df[c2].notna()
            n_pair = int(mask.sum())
            if n_pair < MIN_STARS_FOR_CORR:
                continue
            r, _ = pearsonr(df[c1][mask], df[c2][mask])
            corr_mat.at[c1, c2] = float(r)
            n_mat.at[c1, c2]    = n_pair

    weights = n_mat.astype(float) / MAX_POSSIBLE_STARS
    weighted = corr_mat * weights
    # Average over the surviving pairs (count of non-NaN entries per row)
    counts = corr_mat.count(axis=1).replace(0, np.nan)
    scores = (weighted.sum(axis=1) / counts)
    scores = scores.dropna().sort_values(ascending=False)
    if scores.empty:
        raise RuntimeError('No line pairs survived MIN_STARS_FOR_CORR filter.')

    # Console summary
    print('  ┌── Per-line agreement scores S_ℓ (descending) ──────────────')
    for ln, s in scores.items():
        succ, mean_ew, sem_ew = ew_stats.get(ln, (np.nan, np.nan, np.nan))
        n_det = int(df[ln].notna().sum())
        print(f'  │  {ln:<24s}  S = {s:+.3f}  '
              f'(n={n_det:2d}, EW = {mean_ew:+.2f} ± {sem_ew:.2f})')
    print('  └────────────────────────────────────────────────────────────')

    # Highlight the C IV line (binary classifier)
    HILITE = 'C IV 5808-5812'

    fig, axs = plt.subplots(1, 2, figsize=FS_DC_HALF_HI)
    ax_bar, ax_sc = axs

    # ── Panel A: bar ranking ─────────────────────────────────────────────
    y = np.arange(len(scores))
    colors = ['#D62728' if ln == HILITE else '#4A90D9' for ln in scores.index]
    ax_bar.barh(y, scores.values,
                color=colors, edgecolor='black', linewidth=0.4, height=0.7)
    ax_bar.set_yticks(y)
    ax_bar.set_yticklabels([s.replace('-', r'$-$') for s in scores.index],
                           fontsize=7)
    ax_bar.invert_yaxis()
    ax_bar.axvline(0, color='black', linewidth=0.6)
    ax_bar.set_xlabel(r'Agreement score $S_\ell$')
    ax_bar.set_title('Per-line agreement ranking')
    # Set xlim with some padding
    s_min = float(scores.min())
    s_max = float(scores.max())
    pad = 0.05 * max(abs(s_min), abs(s_max), 1e-3)
    ax_bar.set_xlim(min(s_min - pad, 0.0), s_max + pad)

    # ── Panel B: S_ℓ vs EW ───────────────────────────────────────────────
    ews   = np.array([ew_stats[ln][1] for ln in scores.index], dtype=float)
    ews_e = np.array([ew_stats[ln][2] for ln in scores.index], dtype=float)
    sc    = scores.values

    finite = np.isfinite(ews) & np.isfinite(sc)
    if finite.any():
        # Plot each point in the highlight color where applicable
        for i, ln in enumerate(scores.index):
            if not finite[i]:
                continue
            c = '#D62728' if ln == HILITE else '#4A90D9'
            ax_sc.errorbar(ews[i], sc[i],
                           xerr=(ews_e[i] if np.isfinite(ews_e[i]) else 0.0),
                           fmt='o', color=c, ecolor='black', elinewidth=0.6,
                           capsize=2.0, markersize=5,
                           markeredgecolor='black', markeredgewidth=0.4,
                           zorder=3)
            # Annotate point
            ax_sc.text(ews[i], sc[i] + 0.018, ln.split()[0] + ' ' +
                       (ln.split()[1] if len(ln.split()) > 1 else ''),
                       fontsize=6, ha='center', va='bottom',
                       color='#333333')
    ax_sc.axhline(0, color='black', linewidth=0.6)
    ax_sc.set_xlabel(r'Equivalent width (Å)')
    ax_sc.set_ylabel(r'Agreement score $S_\ell$')
    ax_sc.set_title(r'$S_\ell$ vs equivalent width')

    fig.tight_layout()
    return _save(fig, 'agreement.pdf')


# ─────────────────────────────────────────────────────────────────────────────
# Figure C — Bin-sensitivity forest plot
# ─────────────────────────────────────────────────────────────────────────────

def fig_bin_sensitivity() -> Path:
    """Forest plot of (f_bin argmax + HDI68) across the 6 binning schemes
    in ``results/bin_sensitivity_260423-1841.json``.  ``dsilva_default``
    highlighted in red (the published choice)."""
    import json as _json
    src = _ROOT / 'results' / 'bin_sensitivity_260423-1841.json'
    if not src.is_file():
        raise FileNotFoundError(f'Bin-sensitivity JSON not found: {src}')
    with open(src) as fh:
        data = _json.load(fh)

    schemes = data['schemes']
    selected = data.get('selected_scheme', 'dsilva_default')

    # Preserve insertion order
    rows: list = []
    for name, blk in schemes.items():
        rows.append((
            name,
            float(blk['best_fbin']),
            float(blk['hdi68_fbin'][0]),
            float(blk['hdi68_fbin'][1]),
            int(blk.get('n_eff_bins', blk.get('n_bins', -1))),
        ))

    n = len(rows)
    fig, ax = plt.subplots(figsize=(3.5, max(2.6, 0.45 * n + 0.8)))
    y = np.arange(n)
    for i, (name, fb, lo, hi, neff) in enumerate(rows):
        is_sel = (name == selected)
        col = '#D62728' if is_sel else '#4A90D9'
        # HDI bar
        ax.plot([lo, hi], [i, i], color=col, linewidth=2.0, solid_capstyle='butt')
        # End caps
        ax.plot([lo, lo], [i - 0.18, i + 0.18], color=col, linewidth=1.2)
        ax.plot([hi, hi], [i - 0.18, i + 0.18], color=col, linewidth=1.2)
        # argmax marker
        ax.plot(fb, i, marker='o', color=col, markersize=6,
                markeredgecolor='black', markeredgewidth=0.4, zorder=4)

    # Threshold marker at our headline value (Bartzakos+detected) is implicit;
    # instead, mark fb of selected scheme as a vertical line for reference.
    sel_fb = next(fb for nm, fb, *_ in rows if nm == selected)
    ax.axvline(sel_fb, color='#D62728', linestyle=':', linewidth=0.8,
               zorder=0, alpha=0.6)

    ax.set_yticks(y)
    ax.set_yticklabels([nm + (r'$^*$' if nm == selected else '')
                        for nm, *_ in rows], fontsize=7)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel(r'$f_\mathrm{bin}$')
    ax.set_title('Binning-scheme sensitivity (argmax + 68% HDI)')

    # Legend
    from matplotlib.lines import Line2D
    leg = [Line2D([0], [0], color='#D62728', marker='o', linewidth=2.0,
                  markeredgecolor='black', label='dsilva (selected)'),
           Line2D([0], [0], color='#4A90D9', marker='o', linewidth=2.0,
                  markeredgecolor='black', label='alternative scheme')]
    ax.legend(handles=leg, loc='lower right', fontsize=7,
              facecolor='white', edgecolor='black', framealpha=1.0)

    fig.tight_layout()
    return _save(fig, 'bin_sensitivity.pdf')


# ─────────────────────────────────────────────────────────────────────────────
# Figure D — Period probability density: Dsilva power-law vs Langer mixture
# ─────────────────────────────────────────────────────────────────────────────

def fig_period_models() -> Path:
    """Two period probability densities used in the bias-correction simulator:

      • Dsilva power-law:  p(log P) ∝ (log P)^π   on log P ∈ [0.15, 5.0] d
      • Langer mixture:    w_A · N(μ_A, σ_A) + (1-w_A) · LogN(mu=μ_B, σ=σ_B)
        where the second component is a "reflected log-normal" with
        ln(x) ~ N(ln(μ) + σ², σ).

    NOTE on Langer parameters: the paper text (`bias_correction.tex`,
    Eq.~\\ref{eq:langer_period}) lists σ_A=0.15, σ_B=0.20, but the bias-
    correction *simulator* (wr_bias_simulation.py) actually draws periods
    from σ_A=0.35, σ_B=0.45 — wider components that better match the
    Sana 2012 / Sana 2013 distributions used to bootstrap the model.
    Per user direction (2026-04-27), this figure now plots the **simulator
    values** so the figure reflects what the bias-correction grid actually
    samples.  The next paper revision should update Eq. (langer_period)
    to match.

    Both PDFs are normalised to integrate to 1 over log P ∈ [0.15, 5.0].
    The cadence-sensitive band log P ∈ [0.5, 3.5] is shaded.
    """
    LOGP_MIN, LOGP_MAX = 0.15, 5.0
    SHADE_MIN, SHADE_MAX = 0.5, 3.5
    PI_DEFAULT = 3.0   # placeholder until \pibestfit converges

    print('  ┌── Period model parameters used in fig_period_models ──────────')
    print(f'  │  Dsilva power-law slope π = {PI_DEFAULT:.2f}  '
          '(PLACEHOLDER — replace once \\pibestfit converges)')
    print('  │  Langer params (simulator values): '
          'μ_A=0.80, σ_A=0.35, μ_B=2.0, σ_B=0.45, w_A=0.2')
    print('  │  (paper Eq. langer_period currently shows σ_A=0.15, σ_B=0.20')
    print('  │   — update paper to match simulator.)')
    print('  └────────────────────────────────────────────────────────────')

    # Dsilva power-law PDF: p(x) ∝ x^π on [a, b]
    pi = PI_DEFAULT
    a, b = LOGP_MIN, LOGP_MAX
    if abs(pi + 1.0) < 1e-8:
        norm_dsilva = 1.0 / np.log(b / a)
    else:
        norm_dsilva = (pi + 1.0) / (b ** (pi + 1.0) - a ** (pi + 1.0))
    x_grid = np.linspace(a, b, 1200)
    pdf_dsilva = norm_dsilva * x_grid ** pi   # already normalised on [a,b]

    # Langer mixture — SIMULATOR values (not paper-Eq. values)
    mu_A, sig_A, w_A = 0.80, 0.35, 0.20
    mu_B, sig_B      = 2.00, 0.45

    # Component A: clipped Gaussian on [a,b] (then renormalise)
    pdf_A = (1.0 / (np.sqrt(2 * np.pi) * sig_A)) * np.exp(
        -0.5 * ((x_grid - mu_A) / sig_A) ** 2)
    # Component B: reflected log-normal (mode = mu_B). The simulator uses
    # x = 2*mu_B - rng.lognormal(mean=ln(mu_B)+σ², sigma).  The PDF of the
    # transformed variable y = 2*mu_B - x is f_Y(y) = f_X(2*mu_B - y).
    mu_ln = np.log(mu_B) + sig_B ** 2
    z = 2 * mu_B - x_grid                             # reflect about mu_B
    pos = z > 0
    pdf_B = np.zeros_like(x_grid)
    pdf_B[pos] = (1.0 / (z[pos] * sig_B * np.sqrt(2 * np.pi))) * np.exp(
        -0.5 * ((np.log(z[pos]) - mu_ln) / sig_B) ** 2)

    mix_unscaled = w_A * pdf_A + (1.0 - w_A) * pdf_B
    # Renormalise on [a,b]
    Z = np.trapezoid(mix_unscaled, x_grid)
    pdf_langer = mix_unscaled / Z if Z > 0 else mix_unscaled

    # ── Plot ─────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=FS_SC_WIDE)
    # Shade cadence-sensitive band
    ax.axvspan(SHADE_MIN, SHADE_MAX,
               color='#888888', alpha=0.10, linewidth=0,
               label='Cadence-sensitive band')

    ax.plot(x_grid, pdf_dsilva,
            color='#000000', linestyle='-', linewidth=1.4,
            label=fr'Dsilva power-law  ($\pi = {pi:.1f}$, placeholder)')
    ax.plot(x_grid, pdf_langer,
            color='#D62728', linestyle='--', linewidth=1.4,
            label=r'Langer two-component mixture')

    # Sub-component preview (faint) for diagnostic clarity
    a_part = w_A * pdf_A
    b_part = (1.0 - w_A) * pdf_B
    # renormalise the components to the same Z for plotting consistency
    if Z > 0:
        a_part = a_part / Z
        b_part = b_part / Z
    ax.plot(x_grid, a_part,
            color='#E25A53', linestyle=':', linewidth=0.8, alpha=0.7,
            label=fr'  Case A (Gaussian, $w_A = {w_A:.1f}$)')
    ax.plot(x_grid, b_part,
            color='#9467bd', linestyle=':', linewidth=0.8, alpha=0.7,
            label=fr'  Case B (reflected log-normal)')

    ax.set_xlim(a, b)
    ax.set_ylim(0, None)
    ax.set_xlabel(r'$\log_{10} P$ (d)')
    ax.set_ylabel(r'$p(\log_{10} P)$')
    ax.set_title('Period probability densities')
    # Legend in upper-left — the Dsilva power-law dominates the upper-right
    # corner with these σ values, so move legend out of the data
    ax.legend(loc='upper left', fontsize=6.5,
              facecolor='white', edgecolor='black', framealpha=1.0)
    fig.tight_layout()
    return _save(fig, 'period_models.pdf')


# ─────────────────────────────────────────────────────────────────────────────
# Figure E — Worked CCF profile for one (star, epoch, line)
# ─────────────────────────────────────────────────────────────────────────────

def _compute_ccf_profile(
        obs_wave: np.ndarray, obs_flux: np.ndarray,
        tpl_wave: np.ndarray, tpl_flux: np.ndarray,
        line_range_A: tuple,
        cross_velo_max: float = 2000.0,
        fit_fraction: float = 0.97,
) -> dict:
    """Recompute the CCF for a single (obs, template, line range) and return
    the velocity-shift array, the CCF function, the parabolic-fit overlay,
    and the fit-edge metadata.  Mirrors ``CCFclass._crosscorreal`` but
    without any plotting.

    Inputs are in **Angstroms** (line_range_A is the C-band Å range).

    Returns dict with keys:
        velo (1D km/s), ccf (1D), fine_velo (1D km/s), parable (1D),
        rv (float, km/s), sigma (float, km/s), ccf_max1 (float),
        fit_frac_line (float — y of horizontal dashed line),
        edge_lo (float, km/s), edge_hi (float, km/s).
    """
    from scipy.interpolate import interp1d
    clight = 2.9979e5

    CrossCorRangeA = np.asarray([line_range_A], dtype=float)
    CrossVeloMin = -cross_velo_max
    CrossVeloMax =  cross_velo_max

    LambdaRangeUser = CrossCorRangeA * np.array(
        [1 - 1.1 * CrossVeloMax / clight, 1 - 1.1 * CrossVeloMin / clight])
    LamRangeB = LambdaRangeUser[0, 0]
    LamRangeR = LambdaRangeUser[-1, 1]

    Dlam       = obs_wave[1] - obs_wave[0]
    Resolution = obs_wave[1] / Dlam
    vbin       = clight / Resolution

    Nwaves      = int(np.log(LamRangeR / LamRangeB) / np.log(1.0 + vbin / clight))
    wavegridlog = LamRangeB * (1.0 + vbin / clight) ** np.arange(Nwaves)

    IntIs = np.array([np.argmin(np.abs(wavegridlog - CrossCorRangeA[i][0]))
                      for i in range(len(CrossCorRangeA))])
    IntFs = np.array([np.argmin(np.abs(wavegridlog - CrossCorRangeA[i][1]))
                      for i in range(len(CrossCorRangeA))])
    Ns = IntFs - IntIs
    N  = int(np.sum(Ns))
    CrossCorInds = np.concatenate(
        [np.arange(IntIs[i], IntFs[i]) for i in range(len(IntFs))])
    sRange    = np.arange(int(CrossVeloMin / vbin),
                          int(CrossVeloMax / vbin) + 1, 1)
    veloRange = vbin * sRange

    # Interpolate template onto log grid
    Mask = interp1d(tpl_wave, np.nan_to_num(tpl_flux),
                    bounds_error=False, fill_value=1.0,
                    kind='cubic')(wavegridlog)
    # Interpolate observation flux onto log grid (within line range)
    flux_ccf = interp1d(obs_wave, np.nan_to_num(obs_flux),
                        bounds_error=False, fill_value=1.0,
                        kind='cubic')(wavegridlog[CrossCorInds])

    obs_zm  = flux_ccf - np.mean(flux_ccf)
    mask_zm = Mask     - np.mean(Mask)

    # CCF: roll the mask, dot-product with observation
    def _CCF(f1, f2, n):
        return np.sum(f1 * f2) / np.std(f1) / np.std(f2) / n

    CCFarr = np.array([
        _CCF(obs_zm, (np.roll(mask_zm, s))[CrossCorInds], N)
        for s in sRange
    ])

    IndMax  = int(np.argmax(CCFarr))
    CCFMAX1 = float(np.average(
        [CCFarr[IndMax - 3: IndMax - 1], CCFarr[IndMax + 2: IndMax + 4]]))

    LeftEdgeArr  = np.abs(fit_fraction * CCFMAX1 - CCFarr[:IndMax])
    RightEdgeArr = np.abs(fit_fraction * CCFMAX1 - CCFarr[IndMax + 1:])
    if len(LeftEdgeArr) == 0 or len(RightEdgeArr) == 0:
        raise RuntimeError('Cannot find CCF local maximum')

    IndFit1 = int(np.argmin(LeftEdgeArr))
    IndFit2 = int(np.argmin(RightEdgeArr)) + IndMax + 1
    a, b, c = np.polyfit(
        np.concatenate((veloRange[IndFit1:IndMax],
                        veloRange[IndMax + 1: IndFit2 + 1])),
        np.concatenate((CCFarr[IndFit1:IndMax],
                        CCFarr[IndMax + 1: IndFit2 + 1])),
        2,
    )
    vmax     = float(-b / (2 * a))
    CCFAtMax = float(min(1 - 1e-20, c - b ** 2 / 4.0 / a))
    FineVeloGrid = np.arange(veloRange[IndFit1], veloRange[IndFit2], 0.1)
    parable      = a * FineVeloGrid ** 2 + b * FineVeloGrid + c
    sigma = float(np.sqrt(-1.0 / (N * 2 * a * CCFAtMax / (1 - CCFAtMax ** 2))))

    return dict(
        velo=veloRange, ccf=CCFarr,
        fine_velo=FineVeloGrid, parable=parable,
        rv=vmax, sigma=sigma,
        ccf_max1=CCFMAX1,
        fit_frac_line=fit_fraction * CCFMAX1,
        edge_lo=float(veloRange[IndFit1]),
        edge_hi=float(veloRange[IndFit2]),
    )


def fig_ccf_profile(star_name: str = 'Brey  93',
                    epoch: int = 1) -> Path:
    """A worked CCF example for one (star, epoch) tuple on C IV 5808-5812.

    Plots:
      • CCF ρ(s) vs velocity shift in km/s (full panel)
      • Horizontal dashed line at fit-fraction · ρ_max
      • Parabolic fit overlaid on the peak region (red dashed)
      • Vertical line at centroid (RV); shaded ±1σ band

    Default: ``Brey 93`` epoch 1 (highest-mean-EW star on C IV 5808).
    """
    from pipeline.load_observations import _make_obs

    obs = _make_obs()
    star = obs.load_star_instance(star_name, to_print=False)

    # Template from epoch 1 normalised flux (mirrors ccf_tasks.py)
    d_tpl = (star.load_property('cleaned_normalized_flux', 1, 'COMBINED')
             or star.load_property('normalized_flux', 1, 'COMBINED'))
    if d_tpl is None:
        raise RuntimeError(f'No template flux for {star_name} epoch 1')
    tpl_wave_A = np.asarray(d_tpl['wavelengths'], dtype=float)
    tpl_flux   = np.asarray(d_tpl['normalized_flux'], dtype=float)

    # Observation at chosen epoch
    d_obs = (star.load_property('cleaned_normalized_flux', epoch, 'COMBINED')
             or star.load_property('normalized_flux', epoch, 'COMBINED'))
    if d_obs is None:
        raise RuntimeError(f'No flux for {star_name} epoch {epoch}')
    obs_wave_A = np.asarray(d_obs['wavelengths'], dtype=float)
    obs_flux   = np.asarray(d_obs['normalized_flux'], dtype=float)

    # Sanitize NaNs in the wavelength grid
    m = np.isfinite(obs_wave_A) & np.isfinite(obs_flux)
    obs_wave_A = obs_wave_A[m]; obs_flux = obs_flux[m]
    m = np.isfinite(tpl_wave_A) & np.isfinite(tpl_flux)
    tpl_wave_A = tpl_wave_A[m]; tpl_flux = tpl_flux[m]

    # Interpolate observation onto template grid (matches ccf_tasks.py)
    from scipy.interpolate import interp1d
    if len(obs_wave_A) >= 2 and not np.array_equal(obs_wave_A, tpl_wave_A):
        obs_flux = interp1d(obs_wave_A, obs_flux, kind='cubic',
                            bounds_error=False, fill_value=1.0)(tpl_wave_A)
        obs_wave_A = tpl_wave_A

    # Run CCF on the C IV 5808-5812 line range (570 - 588 nm => 5700 - 5880 Å)
    line_range_A = (5700.0, 5880.0)

    print(f'  CCF profile: {star_name} epoch {epoch} on C IV 5808-5812')
    res = _compute_ccf_profile(
        obs_wave_A, obs_flux, tpl_wave_A, tpl_flux,
        line_range_A=line_range_A,
        cross_velo_max=2000.0, fit_fraction=0.97,
    )
    print(f'    fitted RV = {res["rv"]:+.2f} ± {res["sigma"]:.2f} km/s   '
          f'(ρ_max ≈ {res["ccf_max1"]:.3f})')

    # ── Plot ─────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=FS_DC_HALF_HI)
    ax.plot(res['velo'], res['ccf'],
            color='#000000', linewidth=1.0,
            label=fr'CCF $\rho(s)$')
    # Fit-fraction horizontal line
    ax.axhline(res['fit_frac_line'],
               color='#888888', linestyle='--', linewidth=0.9,
               label=fr'$f_\mathrm{{fit}}\,\rho_\mathrm{{max}}$ '
                     fr'= ${0.97}\,\rho_\mathrm{{max}}$')
    # Mark fit edges (left and right) as small grey ticks
    for x in (res['edge_lo'], res['edge_hi']):
        ax.plot([x, x], [res['fit_frac_line'] - 0.01,
                          res['fit_frac_line'] + 0.01],
                color='#888888', linewidth=0.8)
    # Parabolic fit overlay (red dashed)
    ax.plot(res['fine_velo'], res['parable'],
            color='#D62728', linestyle='--', linewidth=1.4,
            label='Parabolic fit')
    # Centroid + 1σ band
    rv = res['rv']; sg = res['sigma']
    ax.axvline(rv, color='#DAA520', linewidth=1.0,
               label=fr'RV $= {rv:+.1f} \pm {sg:.1f}$ km s$^{{-1}}$')
    ax.axvspan(rv - sg, rv + sg,
               color='#DAA520', alpha=0.18, linewidth=0)

    # Cosmetics
    ax.set_xlim(-1500, 1500)
    y_min = float(min(0.0, res['ccf'].min())) * 1.1
    y_max = float(res['ccf'].max()) * 1.10
    ax.set_ylim(y_min, y_max)
    ax.set_xlabel(r'Velocity shift $s$ (km s$^{-1}$)')
    ax.set_ylabel(r'Cross-correlation $\rho(s)$')
    ax.set_title(fr'Worked CCF: {star_name} epoch {epoch} (C\,IV 5808\,\AA)')
    ax.legend(loc='upper right', fontsize=7,
              facecolor='white', edgecolor='black', framealpha=1.0)
    fig.tight_layout()
    return _save(fig, 'ccf_profile.pdf')


# ─────────────────────────────────────────────────────────────────────────────
# Figure F — Three representative stars: RV vs MJD time series
#            (top row only; bottom-row line profiles deferred — see notes)
# ─────────────────────────────────────────────────────────────────────────────

def fig_binary_examples() -> Path:
    """RV-vs-MJD time series for three representative stars:
      Panel 1: highest ΔRV_max binary (clearest SB1)
      Panel 2: marginal case nearest to the threshold (above or below)
      Panel 3: apparently single star with the lowest ΔRV_max

    The bottom-row line-profile panels are deferred (require a more complex
    spectrum-loading bootstrap that broke in the previous run).  The
    figure is currently a 1×3 layout.
    """
    from pipeline.load_observations import (
        load_observed_delta_rvs, _make_obs,
    )

    drv, detail = load_observed_delta_rvs()
    rows = []
    for sn, det in detail.items():
        d = float(det['best_dRV'])
        s = float(det['best_sigma']) if np.isfinite(det['best_sigma']) else 0.0
        ib = bool(det['is_binary']) if det['is_binary'] is not None else False
        rows.append((sn, d, s, ib, len(det['rv'])))
    # Drop zero-ΔRV
    rows = [r for r in rows if r[1] > 0]
    rows.sort(key=lambda r: -r[1])

    # Selection
    # Panel 1: highest ΔRV_max binary
    binaries = [r for r in rows if r[3]]
    if not binaries:
        raise RuntimeError('No detected binaries found.')
    sel_high = binaries[0]
    # Panel 2: marginal case — closest to THRESH_KMS but still above
    above_thr = [r for r in rows if r[1] > THRESH_KMS]
    below_thr = [r for r in rows if r[1] <= THRESH_KMS]
    if above_thr:
        sel_mid = min(above_thr, key=lambda r: abs(r[1] - THRESH_KMS))
    elif below_thr:
        sel_mid = max(below_thr, key=lambda r: r[1])
    else:
        raise RuntimeError('No marginal case')
    # Panel 3: apparently single (is_binary=False) with lowest ΔRV
    singles = [r for r in rows if not r[3]]
    if not singles:
        raise RuntimeError('No singles found.')
    sel_low = min(singles, key=lambda r: r[1])

    selections = [
        ('clear binary',  sel_high),
        ('marginal',      sel_mid),
        ('single',        sel_low),
    ]
    print('  ┌── binary_examples.pdf — selected stars ──────────────────────')
    for tag, (sn, d, s, ib, n) in selections:
        flag = 'BINARY' if ib else 'single'
        print(f'  │  [{tag:13}]  {sn:<22}  ΔRV = {d:6.1f} ± '
              f'{s:5.1f} km/s   ({flag}, n_ep = {n})')
    print('  └──────────────────────────────────────────────────────────────')

    # Build per-star RV(t) from observations (need MJDs + RVs at each epoch)
    obs = _make_obs()
    line_key = 'C IV 5808-5812'

    def _star_rv_timeseries(star_name: str) -> tuple:
        """Returns (mjds, rv, rv_err) for the C IV 5808 line."""
        star = obs.load_star_instance(star_name, to_print=False)
        epochs = star.get_all_epoch_numbers()
        mjds, rvs, errs = [], [], []
        for ep in epochs:
            try:
                rv_prop = star.load_property('RVs', ep, 'COMBINED')
            except Exception:
                continue
            if rv_prop is None or line_key not in rv_prop:
                continue
            entry = rv_prop[line_key]
            try:
                entry = entry.item()
            except Exception:
                pass
            if not isinstance(entry, dict):
                continue
            rv  = entry.get('full_RV')
            err = entry.get('full_RV_err')
            if rv is None or err is None:
                continue
            try:
                rv  = float(rv); err = float(err)
            except Exception:
                continue
            if not np.isfinite(rv) or rv == 0.0:
                continue

            mjd = None
            for band in ('NIR', 'VIS', 'UVB', 'COMBINED'):
                try:
                    fit = star.load_observation(ep, band=band)
                    if fit is not None:
                        mjd = float(fit.header['MJD-OBS'])
                        break
                except Exception:
                    continue
            if mjd is None:
                continue
            mjds.append(mjd); rvs.append(rv); errs.append(err)
        order = np.argsort(mjds)
        return (np.asarray(mjds)[order],
                np.asarray(rvs)[order],
                np.asarray(errs)[order])

    series = {}
    for tag, (sn, *_) in selections:
        mjds, rvs, errs = _star_rv_timeseries(sn)
        series[sn] = (mjds, rvs, errs)
        print(f'    {sn}: {len(mjds)} epochs')

    # ── Plot 1×3 ─────────────────────────────────────────────────────────
    fig, axs = plt.subplots(1, 3, figsize=(7.0, 2.6), sharey=False)
    for ax, (tag, sel) in zip(axs, selections):
        sn, dval, serr, ib, n = sel
        mjds, rvs, errs = series[sn]
        # Reference each panel's RV centred on the sample mean (for clarity)
        # but display the absolute MJD on x-axis
        ax.errorbar(mjds, rvs, yerr=errs, fmt='o',
                    color=('#D62728' if ib else '#4A90D9'),
                    ecolor='black', elinewidth=0.6, capsize=2.0,
                    markersize=4, markeredgecolor='black',
                    markeredgewidth=0.4, zorder=3,
                    label=f'C\\,IV 5808')
        # Reference line at the ΔRV mean
        rv_mean = float(np.mean(rvs)) if len(rvs) else 0.0
        ax.axhline(rv_mean, color='#888888', linestyle='--', linewidth=0.8)
        # Threshold zone: ±THRESH_KMS / 2 around the mean — visualises the
        # peak-to-peak that would trigger detection
        half_thr = THRESH_KMS / 2.0
        ax.axhspan(rv_mean - half_thr, rv_mean + half_thr,
                   color='#DAA520', alpha=0.15, linewidth=0,
                   label=fr'$\pm T/2 = \pm {half_thr:.1f}$ km/s')
        # Title with star + ΔRV
        cls_txt = 'binary' if ib else 'single'
        ax.set_title(f'{tag}: {sn}\n$\\Delta$RV $= {dval:.1f}$ km/s  ({cls_txt})',
                     fontsize=8.5)
        ax.set_xlabel('MJD (d)')
        if ax is axs[0]:
            ax.set_ylabel(r'RV (km s$^{-1}$)')
        # Legend only on first panel
        if ax is axs[0]:
            ax.legend(loc='upper right', fontsize=6,
                      facecolor='white', edgecolor='black', framealpha=1.0)

    fig.tight_layout()
    return _save(fig, 'binary_examples.pdf')


# ─────────────────────────────────────────────────────────────────────────────
# Figure G — LMC sample sky map (RA / Dec scatter, no Hα background)
# ─────────────────────────────────────────────────────────────────────────────

def fig_sample_map() -> Path:
    """Sky positions of the 25 WC LMC targets in our sample, colour-coded
    by C IV 5808 binary classification.  RA/Dec are read from FITS headers
    of each star's first available epoch (any band).

    No background image — the caption notes that the LMC body would
    normally be shown via an Hα cutout (DSS / Magellanic Cloud Emission-
    Line Survey).  This plain scatter is suitable for the methods section
    and avoids a network/external-image dependency.
    """
    from pipeline.load_observations import (
        load_observed_delta_rvs, _make_obs,
    )

    drv, detail = load_observed_delta_rvs()
    obs = _make_obs()

    # Gather (RA, Dec, is_binary, drv) for each of the 25 stars
    rows = []
    import specs
    for sn in specs.star_names:
        try:
            star = obs.load_star_instance(sn, to_print=False)
        except Exception:
            continue
        epochs = star.get_all_epoch_numbers()
        ra = dec = None
        for ep in epochs:
            for band in ('NIR', 'VIS', 'UVB', 'COMBINED'):
                try:
                    fit = star.load_observation(ep, band=band)
                except Exception:
                    fit = None
                if fit is None:
                    continue
                try:
                    ra  = float(fit.header.get('RA',  np.nan))
                    dec = float(fit.header.get('DEC', np.nan))
                except Exception:
                    ra = dec = None
                if ra is not None and dec is not None and np.isfinite(ra) and np.isfinite(dec):
                    break
            if ra is not None and np.isfinite(ra):
                break
        if ra is None or not np.isfinite(ra):
            print(f'    [sample_map] WARN no RA for {sn}')
            continue
        det = detail.get(sn, {})
        is_bin = bool(det.get('is_binary')) if det.get('is_binary') is not None else False
        d = float(det.get('best_dRV', 0.0))
        rows.append((sn, ra, dec, is_bin, d))

    if len(rows) < 5:
        raise RuntimeError(f'Only {len(rows)} stars have RA/Dec — too few.')

    print(f'  ┌── sample_map.pdf — {len(rows)} targets with RA/Dec ───────────')
    n_bin = sum(1 for r in rows if r[3])
    print(f'  │  Binary (red):   {n_bin}')
    print(f'  │  Single (blue): {len(rows) - n_bin}')
    print('  └──────────────────────────────────────────────────────────────')

    # ── Plot ─────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=FS_SC_SQUARE)
    # Background — faint LMC body as a guideline ellipse (centred at LMC
    # centroid: RA = 80.89, Dec = -69.76; semi-major ~ 5.3°, semi-minor ~ 3.5°)
    # ref: van der Marel & Kallivayalil 2014.
    from matplotlib.patches import Ellipse
    lmc_centre = (80.89, -69.76)
    lmc_a = 5.3   # semi-major (deg)
    lmc_b = 3.5   # semi-minor (deg)
    lmc_pa = 31.0 # position angle (deg, E of N)
    el = Ellipse(lmc_centre, 2 * lmc_a, 2 * lmc_b, angle=lmc_pa,
                 fc='#EEEEEE', ec='#AAAAAA', linewidth=0.6, alpha=0.6,
                 zorder=0)
    ax.add_patch(el)
    ax.text(lmc_centre[0], lmc_centre[1] + lmc_b + 0.3, 'LMC body (guide)',
            ha='center', va='bottom', fontsize=6, color='#666666',
            zorder=1)

    # Scatter targets
    for sn, ra, dec, is_bin, d in rows:
        col = '#D62728' if is_bin else '#4A90D9'
        marker = 's' if is_bin else 'o'
        ax.scatter(ra, dec, color=col, marker=marker, s=22,
                   edgecolor='black', linewidth=0.4, zorder=4)

    # Legend
    from matplotlib.lines import Line2D
    leg = [
        Line2D([0], [0], marker='s', color='#D62728', linestyle='',
               markersize=6, markeredgecolor='black', markeredgewidth=0.4,
               label=f'Binary  (n = {n_bin})'),
        Line2D([0], [0], marker='o', color='#4A90D9', linestyle='',
               markersize=6, markeredgecolor='black', markeredgewidth=0.4,
               label=f'Single  (n = {len(rows) - n_bin})'),
    ]
    ax.legend(handles=leg, loc='upper right', fontsize=7,
              facecolor='white', edgecolor='black', framealpha=1.0)

    # Astronomical convention: RA increases to the LEFT (eastward)
    ax.invert_xaxis()
    # Tight bounds around the data with some padding
    ras  = np.array([r[1] for r in rows])
    decs = np.array([r[2] for r in rows])
    ax.set_xlim(float(np.max(ras))  + 1.5,
                float(np.min(ras))  - 1.5)   # inverted
    ax.set_ylim(float(np.min(decs)) - 1.0,
                float(np.max(decs)) + 1.0)
    ax.set_xlabel(r'Right ascension $\alpha$ (deg, J2000)')
    ax.set_ylabel(r'Declination $\delta$ (deg, J2000)')
    ax.set_title('LMC WC/WO sample — sky positions')
    fig.tight_layout()
    return _save(fig, 'sample_map.pdf')


# ─────────────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    _ensure_plots_dir()
    print(f'Plots directory: {PLOTS_DIR}')
    print(f'Dsilva npz:      {DSILVA_NPZ.name}')
    print(f'Langer npz:      {LANGER_NPZ.name}')
    print()

    if not DSILVA_NPZ.is_file():
        print(f'ERROR: Dsilva npz not found: {DSILVA_NPZ}')
        return 1
    if not LANGER_NPZ.is_file():
        print(f'ERROR: Langer npz not found: {LANGER_NPZ}')
        return 1

    dsilva = np.load(DSILVA_NPZ, allow_pickle=True)
    langer = np.load(LANGER_NPZ, allow_pickle=True)

    successes: list = []
    failures:  list = []

    def _try(name: str, fn) -> None:
        try:
            p = fn()
            successes.append((name, p))
        except Exception as e:
            failures.append((name, str(e)))
            print(f'  ✗ {name} failed: {e}')

    print('[Fig 4] CDF observed vs simulated …')
    _try('cdf_obs_vs_sim',     lambda: fig_cdf_obs_vs_sim(dsilva))
    print('[Fig 5] (f_bin, π) heatmap …')
    _try('fbin_pi_heatmap',    lambda: fig_fbin_pi_heatmap(dsilva))
    print('[Fig 6] (f_bin, π) marginals …')
    _try('fbin_pi_marginals',  lambda: fig_fbin_pi_marginals(dsilva))
    print('[Fig 7] Langer (f_bin, σ_single) heatmap …')
    _try('langer_heatmap',     lambda: fig_langer_heatmap(langer))
    print('[Fig 2] Per-star peak ΔRV bar chart …')
    _try('peak_drv_per_star',  lambda: fig_peak_drv_per_star())
    print('[Fig 3] Threshold derivation (two-Gaussian fit) …')
    _try('threshold_derivation', lambda: fig_threshold_derivation())
    print('[Fig A] Per-line agreement ranking …')
    _try('agreement',          lambda: fig_agreement())
    print('[Fig C] Bin-sensitivity forest …')
    _try('bin_sensitivity',    lambda: fig_bin_sensitivity())
    print('[Fig D] Period models (Dsilva vs Langer) …')
    _try('period_models',      lambda: fig_period_models())

    print()
    print('=' * 70)
    print(f'Wrote {len(successes)} figures to {PLOTS_DIR}')
    for name, p in successes:
        print(f'  • {name:<22s} {p.relative_to(_ROOT)}')
    if failures:
        print()
        print(f'{len(failures)} failures:')
        for name, msg in failures:
            print(f'  ✗ {name}: {msg}')
    print()
    print('DEFERRED (need user input or external assets):')
    print('  • ccf_profile.pdf      — pick one (star, epoch) to feature')
    print('  • binary_examples.pdf  — pick 3 example stars')
    print('  • sample_map.pdf       — needs an LMC Hα image')
    print('  • lmc_vs_mw.pdf        — needs Dsilva 2023 numerical values')
    return 0 if not failures else 2


if __name__ == '__main__':
    sys.exit(main())
