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
# Figure 3 — Threshold derivation: empirical f_bin(>T) step
# ─────────────────────────────────────────────────────────────────────────────

def fig_threshold_derivation(npz: dict) -> Path:
    """Empirical cumulative f_bin(>T) vs T from the observed ΔRV array.

    NOTE: The "two-Gaussian-component" parametric overlay referenced in the
    paper text is NOT implemented in this codebase — only the
    `_fit_two_segment_linear_weighted` elbow fit is present
    (Plots.ipynb cell 47).  The notebook fit also depends on
    `_is_significant_binary` (sigma criterion), `ew_fail_stats`, and
    `clean_map`, none of which are reproducible without ObservationManager
    and the per-line CCF cache.  This figure therefore shows the empirical
    step + threshold marker only; the parametric overlay is DEFERRED.
    """
    obs = np.asarray(npz['obs_delta_rv'], dtype=float)
    obs = obs[obs > 0]
    n = len(obs)

    t_max = max(float(obs.max()), THRESH_KMS) * 1.05
    t_grid = np.linspace(0, t_max, 600)
    fbin_curve = np.array([float(np.sum(obs > t)) / n for t in t_grid])

    # Wilson-1σ band on the cumulative count
    def wilson(k: int, n_total: int, z: float = 1.0) -> tuple[float, float]:
        if n_total == 0:
            return 0.0, 0.0
        p = k / n_total
        denom = 1 + z * z / n_total
        centre = (p + z * z / (2 * n_total)) / denom
        half = (z * np.sqrt(p * (1 - p) / n_total + z * z /
                             (4 * n_total * n_total))) / denom
        return centre - half, centre + half

    counts = np.array([int(np.sum(obs > t)) for t in t_grid])
    lo_arr = np.array([wilson(c, n)[0] for c in counts])
    hi_arr = np.array([wilson(c, n)[1] for c in counts])

    fig, ax = plt.subplots(figsize=FS_SC_WIDE)
    # Wilson band
    ax.fill_between(t_grid, lo_arr, hi_arr,
                    color='#888888', alpha=0.20, linewidth=0,
                    label=r'1$\sigma$ Wilson interval')
    # Empirical curve (since it's piecewise constant from a 25-star sample,
    # show as a step)
    ax.step(t_grid, fbin_curve, where='post',
            color='#000000', linewidth=1.4,
            label=r'$f_\mathrm{bin}(>T)$')
    # 45.5 km/s threshold
    ax.axvline(THRESH_KMS, color='#D62728', linestyle='--', linewidth=1.1)
    ax.text(THRESH_KMS, 0.95, f' $T = {THRESH_KMS:.1f}$ km s$^{{-1}}$',
            color='#D62728', fontsize=7, ha='left', va='top')

    ax.set_xlim(0, t_max)
    ax.set_ylim(0, 1.02)
    ax.set_xlabel(r'$T$ (km s$^{-1}$)')
    ax.set_ylabel(r'$f_\mathrm{bin}(>T)$')
    ax.set_title(r'Empirical binary fraction vs $\Delta$RV threshold')
    ax.legend(loc='upper right', fontsize=7,
              facecolor='white', edgecolor='black', framealpha=1.0)
    fig.tight_layout()
    return _save(fig, 'threshold_derivation.pdf')


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
    print('[Fig 3] Threshold derivation (empirical) …')
    _try('threshold_derivation', lambda: fig_threshold_derivation(dsilva))

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
    print('DEFERRED:')
    print('  • agreement.pdf       — Plots.ipynb cell 53 needs `df`, '
          '`build_masked_df`, per-line CCF cache, and `pearsonr` over 11 '
          'lines × 25 stars. Render manually by running Plots.ipynb cells '
          '0–53 in order.')
    return 0 if not failures else 2


if __name__ == '__main__':
    sys.exit(main())
