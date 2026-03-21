"""
components/detail_figures.py
────────────────────────────
Pure figure factories for D-statistic heatmaps, 1D slices, and re-simulation
CDF plots.  No Dash callbacks here.  Each function takes an explicit
``theme: dict`` parameter and returns a ``go.Figure``.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go


# ── Helpers ──────────────────────────────────────────────────────────────────

def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'rgba({r},{g},{b},{alpha})'


def _empty_fig(message: str, theme: dict, height: int = 300) -> go.Figure:
    """Return an empty figure with a centred annotation."""
    fig = go.Figure()
    fig.add_annotation(
        text=message, xref='paper', yref='paper',
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=14, color='#888'),
    )
    fig.update_layout(**{
        **theme,
        'height': height,
        'xaxis': dict(visible=False),
        'yaxis': dict(visible=False),
    })
    return fig


def _empirical_cdf(arr: np.ndarray):
    """Return (sorted_values, cdf_values) for an empirical CDF."""
    xs = np.sort(arr)
    ys = np.arange(1, len(xs) + 1) / len(xs)
    return xs, ys


# ── 1. D-statistic heatmap ──────────────────────────────────────────────────

def make_d_heatmap_fig(
    D_2d: np.ndarray,
    fbin_g: np.ndarray,
    x_g: np.ndarray,
    method_name: str,
    method_color: str,
    theme: dict,
    x_label: str = '\u03c0',
) -> go.Figure:
    """Heatmap of the D-statistic surface.

    For K-S / weighted / CvM the D-statistic is *lower-is-better*, so the
    best-fit is at the minimum and we use a reversed colour scale.
    For likelihood, ``D_2d`` actually holds ``logL_raw`` which is
    *higher-is-better*, so the best-fit is at the maximum (no reversal).

    Parameters
    ----------
    D_2d : 2-D array, shape (len(fbin_g), len(x_g))
    fbin_g, x_g : 1-D grid arrays
    method_name : display label (used for title + annotation)
    method_color : hex colour for the method
    theme : Plotly layout dict
    x_label : axis label for the x-axis parameter
    """
    arr = np.asarray(D_2d, dtype=float)
    fb = np.asarray(fbin_g, dtype=float)
    xv = np.asarray(x_g, dtype=float)

    if arr.ndim != 2 or arr.size == 0:
        return _empty_fig('Need 2-D D-stat grid for heatmap', theme)

    # Decide direction: likelihood is higher-is-better; others lower-is-better
    is_likelihood = 'likelihood' in method_name.lower()
    if is_likelihood:
        if arr.size == 0 or not np.any(np.isfinite(arr)):
            return None
        best_flat = int(np.nanargmax(arr))
        colorscale = 'Viridis'
        bar_title = 'log L'
    else:
        if arr.size == 0 or not np.any(np.isfinite(arr)):
            return None
        best_flat = int(np.nanargmin(arr))
        colorscale = 'Viridis_r'
        bar_title = 'D-stat'

    best_idx = np.unravel_index(best_flat, arr.shape)
    best_fbin = float(fb[best_idx[0]]) if best_idx[0] < len(fb) else 0.0
    best_x = float(xv[best_idx[1]]) if best_idx[1] < len(xv) else 0.0
    best_val = float(arr[best_idx])

    fig = go.Figure()

    # Heatmap
    fig.add_trace(go.Heatmap(
        z=arr, x=xv, y=fb,
        colorscale=colorscale,
        colorbar=dict(title=bar_title, len=0.85),
        hovertemplate=(
            f'{x_label}=%{{x:.3f}}<br>f_bin=%{{y:.4f}}'
            f'<br>{bar_title}=%{{z:.5f}}<extra></extra>'
        ),
    ))

    # Gold star at best point
    fig.add_trace(go.Scatter(
        x=[best_x], y=[best_fbin],
        mode='markers',
        marker=dict(
            symbol='star', size=16, color='#DAA520',
            line=dict(color='black', width=1.5),
        ),
        showlegend=False,
        hovertemplate=(
            f'Best: f_bin={best_fbin:.4f}, {x_label}={best_x:.3f}'
            f'<br>{bar_title}={best_val:.5f}<extra></extra>'
        ),
    ))

    fig.update_layout(**{
        **theme,
        'title': dict(
            text=f'{method_name} \u2014 D-Statistic Heatmap',
            font=dict(size=14),
        ),
        'xaxis_title': x_label,
        'yaxis_title': 'f_bin',
        'height': 420,
        'margin': dict(l=60, r=20, t=50, b=50),
    })
    return fig


# ── 2. 1-D slice along one axis ─────────────────────────────────────────────

def make_1d_slice_fig(
    grid_vals: np.ndarray,
    scores_1d: np.ndarray,
    axis_label: str,
    best_val: float,
    theme: dict,
    method_color: str = '#4A90D9',
    score_label: str = 'Score',
    fit_coeffs: np.ndarray | None = None,
    fit_range: tuple[float, float] | None = None,
) -> go.Figure:
    """Line + markers chart of scores along one axis at the best slice.

    Parameters
    ----------
    grid_vals : 1-D array of parameter values
    scores_1d : 1-D array of corresponding score / p-values
    axis_label : x-axis label string
    best_val : parameter value at the best-fit point (gold star)
    theme : Plotly layout dict
    method_color : hex colour for the line
    score_label : y-axis label string
    fit_coeffs : optional (a, b, c) polynomial coefficients for parabolic fit
    fit_range : optional (t_lo, t_hi) range for drawing the fit curve
    """
    gv = np.asarray(grid_vals, dtype=float)
    sv = np.asarray(scores_1d, dtype=float)

    if gv.size == 0 or sv.size == 0:
        return _empty_fig(f'No data for {axis_label} slice', theme)

    fig = go.Figure()

    # Main data line
    fig.add_trace(go.Scatter(
        x=gv, y=sv, mode='lines+markers',
        marker=dict(size=7, color=method_color),
        line=dict(color=method_color, width=2),
        name='Grid values',
        hovertemplate=f'{axis_label}=%{{x:.4f}}<br>{score_label}=%{{y:.5f}}<extra></extra>',
    ))

    # Parabolic fit overlay
    if fit_coeffs is not None and fit_range is not None:
        t_lo, t_hi = fit_range
        t_smooth = np.linspace(t_lo, t_hi, 200)
        s_smooth = np.polyval(fit_coeffs, t_smooth)
        fig.add_trace(go.Scatter(
            x=t_smooth, y=s_smooth, mode='lines',
            line=dict(color='#888', width=1.5, dash='dot'),
            name='Parabolic fit',
            hoverinfo='skip',
        ))

    # Gold star at best point
    best_idx = int(np.argmin(np.abs(gv - best_val)))
    best_score = float(sv[best_idx])
    fig.add_trace(go.Scatter(
        x=[float(gv[best_idx])], y=[best_score],
        mode='markers',
        marker=dict(
            symbol='star', size=16, color='#DAA520',
            line=dict(color='black', width=1.5),
        ),
        showlegend=False,
        hovertemplate=(
            f'Best: {axis_label}={float(gv[best_idx]):.4f}'
            f'<br>{score_label}={best_score:.5f}<extra></extra>'
        ),
    ))

    fig.update_layout(**{
        **theme,
        'title': dict(
            text=f'1-D Slice along {axis_label}',
            font=dict(size=14),
        ),
        'xaxis_title': axis_label,
        'yaxis_title': score_label,
        'height': 350,
        'margin': dict(l=60, r=20, t=50, b=50),
        'showlegend': True,
        'legend': dict(x=0.65, y=0.95),
    })
    return fig


# ── 3. Re-simulation CDF at best-fit point ──────────────────────────────────

def make_resim_cdf_fig(
    obs_delta_rv: np.ndarray,
    best_fbin: float,
    best_x: float,
    best_sigma: float,
    method_name: str,
    theme: dict,
    method_color: str = '#4A90D9',
    n_draws: int = 50,
    result_meta: dict | None = None,
) -> go.Figure:
    """Observed CDF vs re-simulated ensemble at the best-fit point.

    Draws ``n_draws`` Monte-Carlo realisations at the best-fit parameters,
    plots median + 16-84% confidence band.

    Imports simulation machinery inside the function to avoid top-level
    dependency on wr_bias_simulation.
    """
    from wr_bias_simulation import (
        binned_cdf, DEFAULT_DRV_BIN_EDGES,
        simulate_delta_rv_sample, SimulationConfig, BinaryParameterConfig,
    )

    obs = np.asarray(obs_delta_rv)
    if obs.size == 0:
        return _empty_fig('No observed data for CDF', theme)

    meta = result_meta or {}
    bin_edges_raw = meta.get('bin_edges')
    be = (np.asarray(bin_edges_raw) if bin_edges_raw is not None
          else DEFAULT_DRV_BIN_EDGES)
    n_obs = len(obs)

    # Observed CDF (binned if available, else empirical)
    try:
        obs_cdf = binned_cdf(obs, be)
        obs_x = np.concatenate([[0.0], be])
        obs_y = np.concatenate([[0.0], obs_cdf])
    except Exception:
        obs_x, obs_y = _empirical_cdf(obs)

    # Simulated ensemble
    sigma_meas = float(meta.get('sigma_meas', 3.0))
    all_cdfs = []
    for seed_i in range(n_draws):
        sim_cfg = SimulationConfig(
            n_stars=n_obs,
            sigma_single=float(best_sigma),
            sigma_measure=sigma_meas,
        )
        bin_cfg = BinaryParameterConfig()
        rng = np.random.default_rng(42 + seed_i)
        sim_drv = simulate_delta_rv_sample(
            f_bin=float(best_fbin), pi=float(best_x),
            sim_cfg=sim_cfg, bin_cfg=bin_cfg, rng=rng,
        )
        try:
            all_cdfs.append(binned_cdf(sim_drv, be))
        except Exception:
            _, ey = _empirical_cdf(sim_drv)
            all_cdfs.append(ey)

    fig = go.Figure()

    # Observed line (solid black)
    fig.add_trace(go.Scatter(
        x=obs_x, y=obs_y, mode='lines', name='Observed',
        line=dict(color='black', width=2.5),
    ))

    # Simulated band (16-84%) + median
    if len(all_cdfs) > 1:
        cdfs = np.array(all_cdfs)
        median_cdf = np.median(cdfs, axis=0)
        lo = np.percentile(cdfs, 16, axis=0)
        hi = np.percentile(cdfs, 84, axis=0)

        sim_x = (np.concatenate([[0.0], be])
                 if len(median_cdf) == len(be) else obs_x)
        med_x = sim_x[:len(median_cdf) + 1] if len(sim_x) > len(median_cdf) else sim_x
        med_y = np.concatenate([[0.0], median_cdf])[:len(med_x)]
        lo_y = np.concatenate([[0.0], lo])[:len(med_x)]
        hi_y = np.concatenate([[0.0], hi])[:len(med_x)]

        # Confidence band
        fig.add_trace(go.Scatter(
            x=np.concatenate([med_x, med_x[::-1]]),
            y=np.concatenate([hi_y, lo_y[::-1]]),
            fill='toself',
            fillcolor=_hex_to_rgba(method_color, 0.2),
            line=dict(color='rgba(0,0,0,0)'),
            showlegend=False, hoverinfo='skip',
        ))

        # Median line (dashed, method colour)
        lbl = (f'{method_name} (f_bin={best_fbin:.3f}, '
               f'\u03c0={best_x:.2f}, \u03c3={best_sigma:.1f})')
        fig.add_trace(go.Scatter(
            x=med_x, y=med_y, mode='lines', name=lbl,
            line=dict(color=method_color, width=2, dash='dash'),
        ))

    fig.update_layout(**{
        **theme,
        'title': dict(
            text=f'Re-simulation CDF ({method_name})',
            font=dict(size=14),
        ),
        'xaxis_title': '\u0394RV (km/s)',
        'yaxis_title': 'Cumulative Fraction',
        'height': 400,
        'legend': dict(x=0.45, y=0.05),
    })
    return fig
