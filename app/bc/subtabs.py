"""bc.subtabs — Scoring-method view orchestrator for model tabs.

Shows simulation overview + radio button to switch between 4 scoring methods.
All 4 model tabs (Dsilva, Langer, Cadence-Dsilva, Cadence-Langer) share this.
"""
from __future__ import annotations

import os, sys
import numpy as np
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bc.analysis import (
    _render_method_summary_section,
    _render_all_methods_cdf,
    _render_method_expander,
    _get_method_array,
)
from bc.helpers import SCORING_METHODS, _make_max_pval_fig
from bc.sim_plots import (
    render_period_distribution,
    render_binary_fraction_vs_threshold,
    render_orbital_histograms,
    render_methodology_equations,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: build extra_grids list for _render_method_summary_section
# ─────────────────────────────────────────────────────────────────────────────

def _build_extra_grids(ctx: dict) -> list[tuple[str, np.ndarray]] | None:
    """Build the extra_grids list for multi-dim models.

    Dsilva 4D: [logPmax, sigma, fbin, pi] — both sigma and logPmax.
    Cadence Dsilva 3D: [sigma, fbin, pi] — only sigma.
    """
    ndim = ctx['ndim_mode']
    extras: list[tuple[str, np.ndarray]] = []
    if ctx.get('sigma_g') is not None and ndim in ('dsilva', 'cadence_dsilva'):
        extras.append(('sigma', ctx['sigma_g']))
    if ctx.get('logPmax_g') is not None and ndim == 'dsilva':
        extras.append(('logPmax', ctx['logPmax_g']))
    return extras if extras else None


# ─────────────────────────────────────────────────────────────────────────────
# Helper: ensure scoring array has correct dimensionality
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_nd(arr: np.ndarray | None, ctx: dict) -> np.ndarray | None:
    """Pad a scoring array to the expected number of dimensions for the model."""
    if arr is None:
        return None
    if ctx['ndim_mode'] == 'dsilva':
        # Dsilva expects 4D: (logPmax, sigma, fbin, pi)
        if arr.ndim == 2:
            arr = arr[np.newaxis, np.newaxis, ...]
        elif arr.ndim == 3:
            arr = arr[np.newaxis, ...]
    return arr


# ─────────────────────────────────────────────────────────────────────────────
# Simulation sub-tab
# ─────────────────────────────────────────────────────────────────────────────

def _render_simulation_tab(p: str, ctx: dict) -> None:
    """Render the Simulation overview sub-tab."""
    result = ctx['result']
    fbin_g = ctx['fbin_g']
    x_g = ctx['x_g']
    extra_grids = _build_extra_grids(ctx)

    # ── Summary table of all methods ──────────────────────────────────────
    method_results = _render_method_summary_section(
        result, fbin_g, x_g,
        extra_grids=extra_grids,
        prefix=p,
        x_name=ctx['x_name'],
        x_label=ctx['x_label'],
        ndim_mode=ctx['ndim_mode'],
    )

    # ── A2 CDF comparison — REMOVED (redundant with E5) ──────────────────
    # _render_all_methods_cdf(
    #     result, method_results, fbin_g, x_g,
    #     prefix=p,
    #     x_name=ctx['x_name'],
    #     x_label=ctx['x_label'],
    # )

    # ── Analysis plots (period dist, binary fraction, orbital histograms) ─
    gap_sim = ctx.get('gap_sim')
    if gap_sim is not None:
        _render_analysis_plots(p, ctx, gap_sim, method_results)

    # ── Methodology equations at bottom ───────────────────────────────────
    render_methodology_equations(ctx['model_type'])


def _render_analysis_plots(
    p: str, ctx: dict, gap_sim: dict, method_results: dict,
) -> None:
    """Render period distribution, binary fraction, and orbital histograms."""
    from shared import get_palette
    pal = get_palette()

    thresh_dRV = ctx.get('thresh_dRV', 45.5)
    has_case_AB = ctx.get('has_case_AB', False)

    # Extract arrays from gap_sim
    gap_drv = np.asarray(gap_sim.get('delta_rv', []))
    gap_is_bin = np.asarray(gap_sim.get('is_binary', []), dtype=bool)
    gap_logP = np.asarray(gap_sim.get('logP', []))

    if gap_drv.size == 0:
        return

    # Binary-only sub-masks: P_days, e, q etc. have N_binary entries,
    # not N_total, so masks must be relative to binary-only arrays.
    idx_bin = gap_sim.get('idx_bin')
    if idx_bin is None:
        idx_bin = np.where(gap_is_bin)[0]
    bin_drv = gap_drv[idx_bin] if idx_bin.size > 0 else np.array([])
    bin_detected_mask = bin_drv > thresh_dRV
    bin_missed_mask = ~bin_detected_mask

    # Best-fit parameter values (from first available method)
    ana_fbin = None
    ana_x_val = None
    for mk, _, _, _, _ in SCORING_METHODS:
        mr = method_results.get(mk)
        if mr and 'best_vals' in mr:
            bv = mr['best_vals']
            ana_fbin = bv.get('fbin')
            ana_x_val = bv.get(ctx['x_name'])
            break

    intrinsic_fbin = float(gap_is_bin.mean()) if gap_is_bin.size > 0 else 0.5
    x_label = ctx['x_label']
    logP_min = ctx.get('logP_min', 0.15)
    logP_max = ctx.get('logP_max', 4.0)

    total_bin = int(np.sum(gap_is_bin))
    detected_bin_count = int(np.sum(bin_detected_mask))
    missed_count = int(np.sum(bin_missed_mask))
    observed_fbin = detected_bin_count / max(len(gap_drv), 1)

    # A4 Period distribution — REMOVED (already in A6 orbital histograms)
    # render_period_distribution(
    #     p, gap_sim, bin_detected_mask, bin_missed_mask,
    #     logP_min, logP_max, ana_x_val,
    #     x_label=x_label, has_case_AB=has_case_AB,
    # )

    # Binary fraction vs threshold
    render_binary_fraction_vs_threshold(
        p, gap_drv, gap_is_bin, intrinsic_fbin,
        observed_fbin, thresh_dRV, missed_count,
        total_bin, detected_bin_count, pal,
        model_label=ctx['model_type'],
    )

    # Orbital histograms
    render_orbital_histograms(
        p, gap_sim, bin_detected_mask, bin_missed_mask,
        ana_fbin, ana_x_val, x_label, thresh_dRV,
        detected_bin_count, missed_count,
        has_case_AB=has_case_AB,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Per-method sub-tab
# ─────────────────────────────────────────────────────────────────────────────

def _render_method_tab(
    p: str,
    method_key: str,
    display_name: str,
    p_key: str,
    D_key: str,
    ctx: dict,
    method_results: dict,
) -> None:
    """Render one scoring method's analysis inside its sub-tab."""
    result = ctx['result']

    p_nd = _get_method_array(result, p_key)
    D_nd = _get_method_array(result, D_key)

    if p_nd is None:
        st.info(f'No **{display_name}** data in this result.')
        return

    # Ensure correct dimensionality
    p_nd = _ensure_nd(p_nd, ctx)
    D_nd = _ensure_nd(D_nd, ctx)

    _render_method_expander(
        method_key=method_key,
        display_name=display_name,
        p_nd=p_nd,
        D_nd=D_nd,
        result=result,
        fbin_g=ctx['fbin_g'],
        x_g=ctx['x_g'],
        prefix=p,
        height=ctx.get('canvas_height', 520),
        width=ctx.get('canvas_width'),
        use_cw=ctx.get('use_container_width', True),
        x_label=ctx['x_label'],
        x_name=ctx['x_name'],
        x_display_label=ctx.get('x_display_label', ctx['x_label']),
        ndim_mode=ctx['ndim_mode'],
        disp_outer_slices=ctx.get('disp_outer_slices'),
        method_results=method_results,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sigma scan chart (Simulation tab)
# ─────────────────────────────────────────────────────────────────────────────

def _render_sigma_scan_chart(ctx: dict) -> None:
    """Show max K-S p-value vs σ_single line chart when sigma was scanned."""
    result = ctx['result']
    sigma_g = np.asarray(result.get('sigma_grid', []))
    if sigma_g.size <= 1:
        return
    ks_p = np.asarray(result.get('ks_p', []))
    if ks_p.size == 0:
        return
    # Compute max p per sigma slice
    if ks_p.ndim == 4:
        # Dsilva: [logPmax, sigma, fbin, pi]
        max_pvals = [float(np.nanmax(ks_p[:, i_s, :, :]))
                     if np.any(np.isfinite(ks_p[:, i_s, :, :])) else 0.0
                     for i_s in range(sigma_g.size)]
    elif ks_p.ndim == 3:
        # Cadence: [sigma, fbin, pi]
        max_pvals = [float(np.nanmax(ks_p[i_s]))
                     if np.any(np.isfinite(ks_p[i_s])) else 0.0
                     for i_s in range(sigma_g.size)]
    elif ks_p.ndim == 2:
        # Langer: [fbin, sigma]
        max_pvals = [float(np.nanmax(ks_p[:, i_s]))
                     if np.any(np.isfinite(ks_p[:, i_s])) else 0.0
                     for i_s in range(sigma_g.size)]
    else:
        return
    fig = _make_max_pval_fig(sigma_g, max_pvals, height=300)
    st.plotly_chart(fig, use_container_width=True, key=f'{ctx.get("_prefix", "sim")}_sig_scan')


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def render_model_subtabs(p: str, model_ctx: dict) -> None:
    """Show simulation overview + radio-selected scoring method detail.

    Parameters
    ----------
    p : str
        Unique key prefix for this model tab (e.g. 'ds', 'lg', 'cd', 'cl').
    model_ctx : dict
        Context dict built by the calling model tab. Must contain at minimum:
        result, fbin_g, x_g, x_name, x_label, ndim_mode, model_type.
    """
    result = model_ctx.get('result')

    if result is None:
        st.info('Run a simulation or load a saved result to see analysis.')
        return

    # ── Shared section ─────────────────────────────────────────────────────
    _ndim = model_ctx.get('ndim_mode', '')
    if _ndim in ('langer', 'cadence_langer'):
        from bc.render_shared_langer import render_shared_section
    else:
        from bc.render_shared import render_shared_section
    method_results = render_shared_section(p, model_ctx)

    # ── Likelihood scoring ────────────────────────────────────────────────
    st.markdown('---')
    if _ndim in ('langer', 'cadence_langer'):
        from bc.render_lk_langer import render_lk_tab
    else:
        from bc.render_lk import render_lk_tab
    render_lk_tab(p, model_ctx, method_results)
