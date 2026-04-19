"""bc.helpers — Shared constants and utility functions for bias correction."""
from __future__ import annotations

import hashlib
import json
import os
import sys

import numpy as np
import plotly.graph_objects as go
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from shared import (
    cached_load_observed_delta_rvs, cached_load_cadence,
    cached_load_grid_result, settings_hash,
    find_best_grid_point, make_heatmap_fig,
    PLOTLY_THEME, get_palette,
)

_best_point = find_best_grid_point
_make_heatmap_fig = make_heatmap_fig

# ── Re-export from file_ops for backward compatibility ────────────────────
from bc.file_ops import (  # noqa: F401
    _RESULT_DIR, _HISTORY_PATH,
    _build_descriptive_filename, _FILENAME_FORMAT_HELP,
    _list_saved_results, _build_partial_filename, _list_partial_results,
    _scan_partial_metadata, _render_partial_table,
    _scan_result_metadata,
    _find_reusable_fbin, _find_reusable_fbin_langer,
    _append_run_history,
    _result_path,
)

_CMP_COLORS = [
    '#4A90D9', '#E25A53', '#50C878', '#9B59B6', '#F39C12',
    '#1ABC9C', '#E67E22', '#3498DB', '#E74C3C', '#2ECC71',
]
_CMP_DASHES = [
    'solid', 'dash', 'dot', 'dashdot', 'longdash',
    'longdashdot', 'solid', 'dash', 'dot', 'dashdot',
]

# ── Scoring method registry ──────────────────────────────────────────────────
# (key, display_name, p_key, D_key, color)
SCORING_METHODS = [
    ('likelihood', 'Likelihood',      'likelihood', 'logL_raw',   '#DAA520'),
]

_METHOD_COLORS = {m[0]: m[4] for m in SCORING_METHODS}

# Scoring label for make_heatmap_fig colorbar per method
_METHOD_SCORING_LABELS = {
    'likelihood': 'Likelihood',
}

# Colorbar title override for score display (not p-values)
_METHOD_COLORBAR_OVERRIDE = {
    'likelihood': 'Normalized Likelihood',
}


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Convert hex color to rgba string for Plotly shading."""
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'rgba({r},{g},{b},{alpha})'

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_eta(seconds: float) -> str:
    """Format seconds as human-readable HH:MM:SS (with days if needed)."""
    s = int(seconds)
    if s < 60:
        return f'{s}s'
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    if d > 0:
        return f'{d}d {h:02d}:{m:02d}:{s:02d}'
    if h > 0:
        return f'{h}:{m:02d}:{s:02d}'
    return f'{m}:{s:02d}'


def _stable_cfg_hash(cfg: dict) -> str:
    return hashlib.sha256(
        json.dumps(cfg, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


# ─────────────────────────────────────────────────────────────────────────────
# Simulation-context signature (cadence resume guard)
# ─────────────────────────────────────────────────────────────────────────────

def _array_fingerprint(arr) -> str:
    """Cheap content fingerprint for an ndarray-ish: shape|sha1[:12]."""
    if arr is None:
        return 'None'
    a = np.asarray(arr)
    return f'{tuple(a.shape)}|{hashlib.sha1(np.ascontiguousarray(a).tobytes()).hexdigest()[:12]}'


def _cadence_lib_fingerprint(cadence_list, cadence_weights) -> str:
    """Fingerprint a cadence library: number of stars + per-star MJD fingerprints + weights."""
    if cadence_list is None:
        return 'None'
    parts = [f'n={len(cadence_list)}']
    for i, c in enumerate(cadence_list):
        parts.append(f'{i}:{_array_fingerprint(c)}')
    parts.append(f'w={_array_fingerprint(cadence_weights)}')
    return ';'.join(parts)


def build_sim_context_signature(
    *, stable_cfg, bin_cfg, sigma_meas, period_model,
    bin_edges, likelihood_bin_edges,
    error_model_single, error_params_single,
    error_model_binary, error_params_binary,
    cadence_list, cadence_weights, obs_delta_rv,
) -> dict:
    """Build a structured field-level signature of the simulation context.

    Two signatures with the same dict are guaranteed to produce identical
    per-cell logL values for any (i_lp, i_sig, i_fb, i_pi). Any difference
    means resuming would mix incompatible cells.
    """
    bcfg_dict = {k: (list(v) if isinstance(v, tuple) else v)
                 for k, v in vars(bin_cfg).items()}
    return {
        'stable_cfg': dict(stable_cfg) if stable_cfg else {},
        'bin_cfg': bcfg_dict,
        'sigma_meas': float(sigma_meas),
        'period_model': str(period_model),
        'bin_edges_fp': _array_fingerprint(bin_edges),
        'likelihood_bin_edges_fp': _array_fingerprint(likelihood_bin_edges),
        'error_model_single': str(error_model_single),
        'error_params_single': list(error_params_single or ()),
        'error_model_binary': str(error_model_binary),
        'error_params_binary': list(error_params_binary or ()),
        'cadence_lib_fp': _cadence_lib_fingerprint(cadence_list, cadence_weights),
        'obs_delta_rv_fp': _array_fingerprint(obs_delta_rv),
    }


def diff_sim_contexts(old: dict, new: dict) -> list[str]:
    """Return human-readable lines for fields whose values differ.

    Recurses one level into nested dicts (e.g. bin_cfg, stable_cfg) so the
    output is precise: `bin_cfg.logP_max: 5.0 → 5.5` rather than the whole dict.
    """
    diffs: list[str] = []
    keys = sorted(set(old) | set(new))
    for k in keys:
        ov, nv = old.get(k, '<missing>'), new.get(k, '<missing>')
        if isinstance(ov, dict) and isinstance(nv, dict):
            for sk in sorted(set(ov) | set(nv)):
                sov, snv = ov.get(sk, '<missing>'), nv.get(sk, '<missing>')
                if sov != snv:
                    diffs.append(f'  • {k}.{sk}:  {sov!r}  →  {snv!r}')
        elif ov != nv:
            diffs.append(f'  • {k}:  {ov!r}  →  {nv!r}')
    return diffs


# WORKING — do not change this code (G1: Grid Range Exclusion)
def _make_range_slider(container, grid: np.ndarray, label: str, key: str):
    """Render a range slider for a grid axis. Returns (min, max) tuple."""
    vals = [float(v) for v in grid]
    lo, hi = vals[0], vals[-1]
    if len(vals) < 2 or lo >= hi:
        container.markdown(f'**{label}**: {lo:g} (fixed)')
        return lo, hi
    step = round(vals[1] - vals[0], 6)
    rng = container.slider(
        f'{label} range', min_value=lo, max_value=hi,
        value=(lo, hi), step=step, key=key)
    return rng


def render_grid_exclusion(
    prefix: str,
    x_grid: np.ndarray,
    y_grid: np.ndarray,
    x_label: str = 'f<sub>bin</sub>',
    y_label: str = 'π',
    sigma_grid: np.ndarray | None = None,
    logPmax_grid: np.ndarray | None = None,
    ndim: int = 2,
) -> np.ndarray:
    """Render Grid Range Exclusion expander and return N-D boolean mask.

    Each grid axis gets a range slider. Points outside the selected range
    are excluded (set to NaN) from likelihood fitting.

    Stores 2D (x × y) projection in st.session_state[f'{prefix}_exc_mask_2d']
    for backward compat with scoring_detail / render_lk_scoring consumers.
    Returns full N-D mask matching the likelihood array shape (True = EXCLUDED).
    """
    _has_sigma = (sigma_grid is not None and len(sigma_grid) > 1)
    _has_logPmax = (logPmax_grid is not None and len(logPmax_grid) > 1)

    with st.expander('Grid Range Exclusion', expanded=False):
        # Row 1: primary axes (f_bin, π / σ_single)
        _c1, _c2 = st.columns(2)
        _x_lo, _x_hi = _make_range_slider(
            _c1, x_grid, x_label, f'{prefix}_exc_xrange')
        _y_lo, _y_hi = _make_range_slider(
            _c2, y_grid, y_label, f'{prefix}_exc_yrange')

        # Row 2: extra axes (σ_single, logP_max) when present
        if _has_sigma or _has_logPmax:
            _extra_cols = st.columns(
                (1 if _has_sigma else 0) + (1 if _has_logPmax else 0))
            _ci = 0
            if _has_sigma:
                _sig_lo, _sig_hi = _make_range_slider(
                    _extra_cols[_ci], sigma_grid, 'σ_single',
                    f'{prefix}_exc_sigrange')
                _ci += 1
            if _has_logPmax:
                _lp_lo, _lp_hi = _make_range_slider(
                    _extra_cols[_ci], logPmax_grid, 'logP_max',
                    f'{prefix}_exc_lprange')

    # Build 1D exclusion masks per axis (True = EXCLUDED)
    _x_exc = (x_grid < _x_lo) | (x_grid > _x_hi)
    _y_exc = (y_grid < _y_lo) | (y_grid > _y_hi)
    _sig_exc = None
    _lp_exc = None
    if _has_sigma:
        _sig_exc = (sigma_grid < _sig_lo) | (sigma_grid > _sig_hi)
    if _has_logPmax:
        _lp_exc = (logPmax_grid < _lp_lo) | (logPmax_grid > _lp_hi)

    # Always store 2D (x × y) projection for backward compat
    _exc_mask_2d = _x_exc[:, None] | _y_exc[None, :]
    st.session_state[f'{prefix}_exc_mask_2d'] = _exc_mask_2d

    # Build N-D mask matching likelihood array shape
    if ndim == 4:
        # [logPmax, sigma, fbin, pi]
        _exc_mask = _x_exc[None, None, :, None] | _y_exc[None, None, None, :]
        if _sig_exc is not None:
            _exc_mask = _exc_mask | _sig_exc[None, :, None, None]
        if _lp_exc is not None:
            _exc_mask = _exc_mask | _lp_exc[:, None, None, None]
    elif ndim == 3:
        # [sigma, fbin, pi]
        _exc_mask = _x_exc[None, :, None] | _y_exc[None, None, :]
        if _sig_exc is not None:
            _exc_mask = _exc_mask | _sig_exc[:, None, None]
    else:
        _exc_mask = _exc_mask_2d

    # Show exclusion count outside expander (always visible)
    _n_excluded = int(_exc_mask.sum())
    if _n_excluded > 0:
        st.caption(
            f'Grid exclusion active: **{_n_excluded}** / {_exc_mask.size} '
            f'points excluded from fitting')

    return _exc_mask


def _make_max_pval_fig(
    sigma_vals: np.ndarray,
    max_pvals: list[float],
    height: int = 300,
    x_label: str = 'σ_single',
    stat_label: str = 'K-S',
) -> go.Figure:
    """Line chart: max score vs a scan variable."""
    best_idx = int(np.argmax(max_pvals))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sigma_vals, y=max_pvals,
        mode='lines+markers',
        marker=dict(size=8, color='#4A90D9'),
        line=dict(color='#4A90D9', width=2),
        hovertemplate=f'{x_label}=%{{x:.2f}}<br>max {stat_label}=%{{y:.4f}}<extra></extra>',
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=[float(sigma_vals[best_idx])],
        y=[max_pvals[best_idx]],
        mode='markers+text',
        marker=dict(symbol='star', size=16, color='gold',
                    line=dict(color='black', width=1)),
        text=[f'  {x_label}={float(sigma_vals[best_idx]):.2f}, {stat_label}={max_pvals[best_idx]:.4f}'],
        textposition='middle right',
        textfont=dict(color='gold', size=11),
        showlegend=False,
    ))
    fig.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(text=f'Max {stat_label} vs {x_label}', font=dict(size=14)),
        'xaxis_title': x_label,
        'yaxis_title': f'Max {stat_label}',
        'height': height,
        'margin': dict(l=60, r=20, t=50, b=50),
    })
    return fig


def _make_min_score_fig(
    sigma_vals: np.ndarray,
    min_scores: list[float],
    height: int = 300,
    x_label: str = 'σ_single',
    stat_label: str = 'CvM',
) -> go.Figure:
    """Line chart: min weighted score (S) vs a scan variable. Lower = better fit."""
    best_idx = int(np.argmin(min_scores))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sigma_vals, y=min_scores,
        mode='lines+markers',
        marker=dict(size=8, color='#E25A53'),
        line=dict(color='#E25A53', width=2),
        hovertemplate=f'{x_label}=%{{x:.2f}}<br>min weighted S=%{{y:.4f}}<extra></extra>',
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=[float(sigma_vals[best_idx])],
        y=[min_scores[best_idx]],
        mode='markers+text',
        marker=dict(symbol='star', size=16, color='#DAA520',
                    line=dict(color='black', width=1)),
        text=[f'  {x_label}={float(sigma_vals[best_idx]):.2f}, S={min_scores[best_idx]:.4f}'],
        textposition='middle right',
        textfont=dict(color='#DAA520', size=11),
        showlegend=False,
    ))
    fig.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(text=f'Min {stat_label} weighted S-score vs {x_label}', font=dict(size=14)),
        'xaxis_title': x_label,
        'yaxis_title': f'Min {stat_label} weighted S-score',
        'height': height,
        'margin': dict(l=60, r=20, t=50, b=50),
    })
    return fig


def _make_3d_stacked_fig(
    ks_p_3d: np.ndarray,
    fbin_vals: np.ndarray,
    pi_vals: np.ndarray,
    sigma_vals: np.ndarray,
    height: int = 700,
    width: int | None = None,
    stat_label: str = 'K-S',
) -> go.Figure:
    """3D stacked semi-transparent surfaces: one per sigma_single."""
    pal = get_palette()
    valid = ks_p_3d[~np.isnan(ks_p_3d)]
    global_zmax = float(np.nanmax(valid)) if valid.size > 0 else 1.0

    fig = go.Figure()
    pi_mesh, fbin_mesh = np.meshgrid(pi_vals, fbin_vals)

    n_sigma = len(sigma_vals)
    # Cap layers to avoid overly heavy plots
    max_layers = 20
    if n_sigma > max_layers:
        indices = np.linspace(0, n_sigma - 1, max_layers, dtype=int)
    else:
        indices = np.arange(n_sigma)

    sigma_min_val = float(sigma_vals[indices[0]])
    sigma_max_val = float(sigma_vals[indices[-1]])
    sigma_range = max(sigma_max_val - sigma_min_val, 1.0)

    for count, i_s in enumerate(indices):
        sigma_val = float(sigma_vals[i_s])
        # z position = actual sigma value for meaningful axis
        z_layer = np.full_like(pi_mesh, sigma_val)
        p_slice = ks_p_3d[i_s]

        fig.add_trace(go.Surface(
            x=pi_mesh, y=fbin_mesh, z=z_layer,
            surfacecolor=p_slice,
            colorscale='RdBu_r',
            cmin=0.0, cmax=global_zmax,
            opacity=0.6,
            showscale=(count == len(indices) - 1),
            colorbar=dict(title=f'{stat_label} p', thickness=14, len=0.6)
            if count == len(indices) - 1 else None,
            name=f'σ={sigma_val:.1f}',
            hovertemplate=(
                f'σ_single={sigma_val:.1f} km/s<br>'
                'π=%{x:.2f}<br>f_bin=%{y:.3f}<br>p=%{surfacecolor:.4f}<extra></extra>'
            ),
        ))

    layout_kw = {
        **PLOTLY_THEME,
        'title': dict(text='3D Stacked Heatmaps (f_bin x π x σ_single)',
                       font=dict(size=14)),
        'scene': dict(
            xaxis_title='π  (period power-law index)',
            yaxis_title='f_bin  (binary fraction)',
            zaxis_title='σ_single (km/s)',
            bgcolor=pal['plot_bg'],
        ),
        'height': height,
        'margin': dict(l=10, r=10, t=50, b=10),
    }
    if width is not None:
        layout_kw['width'] = width

    fig.update_layout(**layout_kw)
    return fig



# ─────────────────────────────────────────────────────────────────────────────
# CDF Sanity Check (cadence tabs only)
# ─────────────────────────────────────────────────────────────────────────────

def _render_cdf_sanity_check(best_fbin, best_x, sigma_single,
                              obs_delta_rv, period_model, result,
                              settings, p_prefix: str) -> None:
    """Render 5 random CDF draws vs observed for cadence sanity check.

    Generates 5 independent sets of 25 simulated stars at the best-fit
    parameters, overlaid on the observed CDF. This verifies the cadence-aware
    pipeline produces sensible ΔRV distributions.
    """
    from wr_bias_simulation import (
        simulate_delta_rv_sample, BinaryParameterConfig,
        DEFAULT_DRV_BIN_EDGES,
    )

    def _bcdf(data, edges):
        s = np.sort(data)
        return np.searchsorted(s, edges, side='right') / len(s)

    cadence_library = result.get('cadence_library')
    if cadence_library is None:
        return

    _bin_edges = DEFAULT_DRV_BIN_EDGES
    obs_cdf_b = _bcdf(obs_delta_rv, _bin_edges)

    st.markdown('### CDF Sanity Check')
    st.caption(
        '5 random draws of 25 simulated stars at the best-fit parameters, '
        'compared to the observed CDF. Each draw uses different random seeds '
        'but identical cadence assignments.'
    )

    # Build BinaryParameterConfig from result metadata
    _bcfg_dict = result.get('bin_cfg', {})
    bcfg = BinaryParameterConfig(**_bcfg_dict) if _bcfg_dict else BinaryParameterConfig()

    fig = go.Figure()

    # Observed CDF
    fig.add_trace(go.Scatter(
        x=_bin_edges, y=obs_cdf_b,
        mode='lines', name='Observed',
        line=dict(color='#4A90D9', width=3, shape='hv'),
    ))

    # 5 random draws
    _draw_colors = ['#E25A53', '#50C878', '#9B59B6', '#F39C12', '#1ABC9C']
    for i, seed in enumerate([42, 43, 44, 45, 46]):
        try:
            drv = simulate_delta_rv_sample(
                n_stars=25,
                f_bin=best_fbin,
                sigma_single=sigma_single,
                sigma_measure=float(result.get('sigma_meas', 1.622)),
                binary_config=bcfg,
                rng_seed=seed,
                period_model=period_model,
                cadence_library=cadence_library,
            )
            sim_cdf = _bcdf(drv, _bin_edges)
            fig.add_trace(go.Scatter(
                x=_bin_edges, y=sim_cdf,
                mode='lines', name=f'Draw {i+1} (seed={seed})',
                line=dict(color=_draw_colors[i], width=1.5,
                          dash='dash', shape='hv'),
                opacity=0.7,
            ))
        except Exception:
            pass

    fig.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(
            text=f'CDF Sanity Check  (f_bin={best_fbin:.3f}, 25 stars × 5 draws)',
            font=dict(size=14)),
        'xaxis_title': 'ΔRV (km/s)',
        'yaxis_title': 'Cumulative fraction',
        'height': 420,
        'legend': dict(x=0.55, y=0.35, font=dict(size=10)),
    })
    st.plotly_chart(fig, use_container_width=True, key=f'{p_prefix}_cdf_sanity')


# ─────────────────────────────────────────────────────────────────────────────
# Methodology Explainer (all tabs)
# ─────────────────────────────────────────────────────────────────────────────

_LANGER_EXPLAINER = r'''
**Langer 2020 period model** — uses physically motivated orbital parameter
distributions from binary population synthesis (Langer et al. 2020, A&A 638, A39).

1. **Draw N systems** (default 3,000). Each is binary with probability f_bin,
   or single with probability 1 − f_bin.

2. **Single stars:** draw RV at each epoch from
   N(v_sys, σ_total) where σ_total = √(σ_single² + σ_measure²).
   ΔRV = max(v) − min(v).

3. **Binary stars — period distribution:**
   Two-component mixture of Case A (short-period) and Case B (long-period)
   mass transfer channels:
   - **Case A:** Gaussian in log₁₀P with μ_A and σ_A
   - **Case B:** Log-normal in log₁₀P with mode μ_B and width σ_B
   - **Mixture weight:** w_A for Case A, (1 − w_A) for Case B

4. **Mass ratio q = M₂/M₁:** sampled from a Gaussian centered on μ_q
   with width σ_q (based on Langer+2020 Fig. 4, BH companion masses).

5. **Eccentricity e = 0** (post-RLOF circularization).

6. **Remaining steps** (K₁ computation, Kepler equation, K-S test)
   are identical to the power-law (Dsilva) model — see that tab for equations.

7. **Grid search** over f_bin × σ_single to find the best-fit parameters
   that maximize the K-S p-value.
'''

_CADENCE_EXPLAINER = r'''
**Cadence-aware modification:**

Unlike the basic simulation which draws random observation times, the
cadence-aware mode preserves the **exact observation timestamps** from the
real survey:

1. Each of **N_sets** iterations (default 10,000) generates a complete
   set of 25 simulated stars.
2. Each simulated star is assigned the **exact MJD sequence** of a randomly
   chosen real star (with replacement, weighted by epoch count).
3. RV curves are computed at those specific times, producing one ΔRV per star.
4. The 25-star ΔRV sample is compared to the observed via binned K-S test.
5. The **median, 16th, and 84th percentile** CDFs across all N_sets are
   stored — the median CDF is used for the K-S statistic, while the
   percentiles define the 68% confidence band.

This approach captures the effects of:
- Uneven time sampling between stars
- Varying number of epochs per star
- Correlated observation windows (multi-star campaigns)

**Scoring methods:**

- **K-S (standard):** D = max|CDF_sim − CDF_obs| across all ΔRV bins.
  All bins contribute equally to the statistic.
- **K-S (variance-weighted):** χ² = Σ (sim_i − obs_i)² / σ²_i, where σ²_i
  is the variance of the simulated CDF at bin i across all N_sets repetitions.
  Bins with high simulation variance contribute less to the statistic.
  The p-value is the chi-squared survival function (higher = better fit).
- **CvM (S-score):** S = Σ (sim_i − obs_i)² / σ²_i (variance-weighted Cramér–von Mises).
  Unlike K-S, uses ALL bins — the full CDF shape matters, not just the single worst bin.
  Bins with high simulation variance contribute less (inverse-variance weighting).
  The p-value is **empirical**: for each of the N_sets simulated star sets, we compute
  S against the median CDF. The p-value = fraction with S ≥ S_obs.
  Models with p outside [0.05, 0.95] are masked as implausible (white on heatmap).
  The true minimum is found via spline interpolation over the valid region.
'''


def _render_methodology_expander(tab_type: str) -> None:
    """Render a methodology expander for the given tab type.

    Parameters
    ----------
    tab_type : str
        One of 'dsilva', 'langer', 'cadence_dsilva', 'cadence_langer'.
    """
    if tab_type == 'dsilva':
        # Dsilva already has its own inline expander (lines 2704-2781)
        return

    st.markdown('---')
    with st.expander('📖 How this bias correction works', expanded=False):
        if tab_type == 'langer':
            st.markdown(_LANGER_EXPLAINER)
        elif tab_type == 'cadence_dsilva':
            st.markdown(
                'This tab uses the **power-law period model** (Dsilva 2023) '
                'with cadence-aware sampling. See the Dsilva tab for the full '
                'methodology equations.'
            )
            st.markdown(_CADENCE_EXPLAINER)
        elif tab_type == 'cadence_langer':
            st.markdown(_LANGER_EXPLAINER)
            st.markdown(_CADENCE_EXPLAINER)



