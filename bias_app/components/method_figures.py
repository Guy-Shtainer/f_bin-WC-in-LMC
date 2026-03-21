"""
components/method_figures.py — Pure figure factories for per-method detail panels.
No Dash callbacks here.  Each function takes an explicit ``theme: dict`` parameter.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import dash_mantine_components as dmc
from dash import html


# ── Helpers ──────────────────────────────────────────────────────────────────

def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'rgba({r},{g},{b},{alpha})'


def _empty_fig(message: str, theme: dict, height: int = 300) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, xref='paper', yref='paper',
                       x=0.5, y=0.5, showarrow=False,
                       font=dict(size=14, color='#888'))
    fig.update_layout(**{**theme, 'height': height,
                         'xaxis': dict(visible=False),
                         'yaxis': dict(visible=False)})
    return fig


def _empirical_cdf(arr: np.ndarray):
    """Return (sorted_values, cdf_values) for an empirical CDF."""
    xs = np.sort(arr)
    ys = np.arange(1, len(xs) + 1) / len(xs)
    return xs, ys


# ── 1. CDF at one method's best-fit point ───────────────────────────────────

def make_method_cdf_fig(
    obs_delta_rv: np.ndarray,
    best_fbin: float,
    best_pi: float,
    best_sigma: float,
    theme: dict,
    n_draws: int = 50,
    method_color: str = '#4A90D9',
    method_name: str = '',
    result_meta: dict | None = None,
) -> go.Figure:
    """CDF comparing observed data to simulated ensemble at best-fit point."""
    from wr_bias_simulation import (
        binned_cdf, DEFAULT_DRV_BIN_EDGES,
        simulate_delta_rv_sample, SimulationConfig, BinaryParameterConfig,
    )

    obs = np.asarray(obs_delta_rv)
    if obs.size == 0:
        return _empty_fig('No observed data for CDF', theme)

    meta = result_meta or {}
    bin_edges_raw = meta.get('bin_edges')
    be = np.asarray(bin_edges_raw) if bin_edges_raw is not None else DEFAULT_DRV_BIN_EDGES
    n_obs = len(obs)

    # Observed CDF (binned if available, else empirical)
    try:
        obs_cdf = binned_cdf(obs, be)
        obs_x = np.concatenate([[0.0], be])
        obs_y = np.concatenate([[0.0], obs_cdf])
    except Exception:
        obs_x, obs_y = _empirical_cdf(obs)

    # Simulated ensemble
    all_cdfs = []
    sigma_meas = float(meta.get('sigma_meas', 3.0))
    for seed_i in range(n_draws):
        sim_cfg = SimulationConfig(
            n_stars=n_obs,
            sigma_single=float(best_sigma),
            sigma_measure=sigma_meas,
        )
        bin_cfg = BinaryParameterConfig()
        rng = np.random.default_rng(42 + seed_i)
        sim_drv = simulate_delta_rv_sample(
            f_bin=float(best_fbin), pi=float(best_pi),
            sim_cfg=sim_cfg, bin_cfg=bin_cfg, rng=rng,
        )
        try:
            all_cdfs.append(binned_cdf(sim_drv, be))
        except Exception:
            _, ey = _empirical_cdf(sim_drv)
            all_cdfs.append(ey)

    fig = go.Figure()

    # Observed
    fig.add_trace(go.Scatter(
        x=obs_x, y=obs_y, mode='lines', name='Observed',
        line=dict(color='black', width=2.5)))

    # Simulated band (16-84 percentile) + median
    if len(all_cdfs) > 1:
        cdfs = np.array(all_cdfs)
        median_cdf = np.median(cdfs, axis=0)
        lo = np.percentile(cdfs, 16, axis=0)
        hi = np.percentile(cdfs, 84, axis=0)
        sim_x = np.concatenate([[0.0], be]) if len(median_cdf) == len(be) else obs_x

        med_x = sim_x[:len(median_cdf) + 1] if len(sim_x) > len(median_cdf) else sim_x
        med_y = np.concatenate([[0.0], median_cdf])[:len(med_x)]
        lo_y = np.concatenate([[0.0], lo])[:len(med_x)]
        hi_y = np.concatenate([[0.0], hi])[:len(med_x)]

        # Confidence band
        fig.add_trace(go.Scatter(
            x=np.concatenate([med_x, med_x[::-1]]),
            y=np.concatenate([hi_y, lo_y[::-1]]),
            fill='toself', fillcolor=_hex_to_rgba(method_color, 0.2),
            line=dict(color='rgba(0,0,0,0)'),
            showlegend=False, hoverinfo='skip'))
        # Median line
        lbl = method_name or 'Simulated'
        lbl += f' (f_bin={best_fbin:.3f}, pi={best_pi:.2f})'
        fig.add_trace(go.Scatter(
            x=med_x, y=med_y, mode='lines', name=lbl,
            line=dict(color=method_color, width=2, dash='dash')))

    fig.update_layout(**{
        **theme,
        'title': dict(text=f'CDF at Best-Fit ({method_name})',
                       font=dict(size=14)),
        'xaxis_title': '\u0394RV (km/s)',
        'yaxis_title': 'Cumulative Fraction',
        'height': 400,
        'legend': dict(x=0.50, y=0.05),
    })
    return fig


# ── 2. Corner / triangle plot ────────────────────────────────────────────────

def make_corner_fig(
    p_nd: np.ndarray,
    fbin_g: np.ndarray,
    x_g: np.ndarray,
    x_name: str,
    x_label: str,
    method_key: str,
    method_color: str,
    theme: dict,
) -> go.Figure:
    """2x2 corner plot: 1D marginals + 2D heatmap of score surface."""
    arr = np.asarray(p_nd)
    if arr.ndim != 2 or arr.size == 0:
        return _empty_fig('Need 2D score grid for corner plot', theme)

    fb = np.asarray(fbin_g)
    xv = np.asarray(x_g)

    # Marginalized posteriors (take max along each axis)
    marg_x = np.nanmax(arr, axis=0)   # shape (len(x_g),)
    marg_fb = np.nanmax(arr, axis=1)  # shape (len(fbin_g),)

    fig = make_subplots(
        rows=2, cols=2,
        row_heights=[0.3, 0.7],
        column_widths=[0.7, 0.3],
        horizontal_spacing=0.04,
        vertical_spacing=0.04,
        shared_xaxes=False,
        shared_yaxes=False,
    )

    # (0,0): 1D marginal of x — top-left
    fig.add_trace(go.Bar(
        x=xv, y=marg_x, marker_color=method_color, opacity=0.7,
        showlegend=False,
        hovertemplate=f'{x_label}=%{{x:.2f}}<br>Score=%{{y:.4f}}<extra></extra>',
    ), row=1, col=1)

    # (1,0): 2D heatmap — bottom-left
    fig.add_trace(go.Heatmap(
        z=arr, x=xv, y=fb,
        colorscale='Viridis',
        colorbar=dict(title='Score', len=0.65, y=0.35),
        hovertemplate=(f'{x_label}=%{{x:.2f}}<br>f_bin=%{{y:.3f}}'
                       '<br>Score=%{z:.4f}<extra></extra>'),
    ), row=2, col=1)

    # Best-fit star marker on heatmap
    if arr.size == 0 or not np.any(np.isfinite(arr)):
        return None
    best_idx = np.unravel_index(int(np.nanargmax(arr)), arr.shape)
    fig.add_trace(go.Scatter(
        x=[float(xv[best_idx[1]])], y=[float(fb[best_idx[0]])],
        mode='markers',
        marker=dict(symbol='star', size=14, color='#DAA520',
                    line=dict(color='black', width=1)),
        showlegend=False,
    ), row=2, col=1)

    # (1,1): 1D marginal of fbin — bottom-right (horizontal bar)
    fig.add_trace(go.Bar(
        x=marg_fb, y=fb, orientation='h',
        marker_color=method_color, opacity=0.7,
        showlegend=False,
        hovertemplate='f_bin=%{y:.3f}<br>Score=%{x:.4f}<extra></extra>',
    ), row=2, col=2)

    # Axis labels
    fig.update_xaxes(title_text=x_label, row=2, col=1)
    fig.update_yaxes(title_text='f_bin', row=2, col=1)
    fig.update_yaxes(title_text='Score', row=1, col=1)
    fig.update_xaxes(title_text='Score', row=2, col=2)

    # Hide top-right cell axes
    fig.update_xaxes(visible=False, row=1, col=2)
    fig.update_yaxes(visible=False, row=1, col=2)

    fig.update_layout(**{
        **theme,
        'title': dict(text=f'Corner Plot ({method_key})', font=dict(size=14)),
        'height': 550,
        'showlegend': False,
        'margin': dict(l=60, r=20, t=50, b=50),
    })
    return fig


# ── 3. Slice controls (sigma / logPmax selector for 3D+ results) ────────────

def make_slice_controls(
    result_data: dict,
    prefix: str,
    method_key: str,
) -> html.Div:
    """Sigma slider for 3D+ results, or empty Div for 2D."""
    sigma_grid = result_data.get('sigma_grid', [])
    if isinstance(sigma_grid, np.ndarray):
        sigma_grid = sigma_grid.tolist()
    if not sigma_grid or len(sigma_grid) <= 1:
        return html.Div()

    # Find best sigma index from the score array
    p_arr = None
    for _, _, pk, _, _ in _get_scoring_methods():
        if _ == method_key:
            break
    # Default to index 0
    best_sigma_idx = 0

    marks = [
        {"value": i, "label": f'{v:.1f}'}
        for i, v in enumerate(sigma_grid)
        if i % max(1, len(sigma_grid) // 8) == 0
    ]

    return dmc.Stack([
        dmc.Text('Sigma slice:', size='sm', fw=500),
        dmc.Slider(
            id=f'{prefix}-{method_key}-sigma-slice',
            min=0,
            max=len(sigma_grid) - 1,
            value=best_sigma_idx,
            marks=marks,
            step=1,
        ),
    ], gap='xs')


def _get_scoring_methods():
    """Import SCORING_METHODS lazily to avoid circular imports."""
    from config import SCORING_METHODS
    return SCORING_METHODS


# ── 4. Explorer table (top-N grid points by score) ──────────────────────────

def make_explorer_table(
    result_data: dict,
    method_key: str,
    p_key: str,
    fbin_g: np.ndarray,
    x_g: np.ndarray,
    x_label: str = 'pi',
    top_n: int = 5,
) -> dmc.Table | dmc.Text:
    """Table of the top-N grid points ranked by score."""
    p_arr = result_data.get(p_key)
    if p_arr is None:
        return dmc.Text(f'No {method_key} data available.', c='dimmed')

    arr = np.asarray(p_arr)
    fb = np.asarray(fbin_g)
    xv = np.asarray(x_g)

    # Collapse to 2D if needed (take max over leading dims)
    while arr.ndim > 2:
        arr = np.nanmax(arr, axis=0)

    # Flatten and sort descending
    flat = arr.ravel()
    n_valid = min(top_n, int(np.sum(np.isfinite(flat))))
    if n_valid == 0:
        return dmc.Text('No valid scores found.', c='dimmed')

    sorted_indices = np.argsort(flat)[::-1][:n_valid]
    rows = []
    for rank, flat_idx in enumerate(sorted_indices, 1):
        i_fb, i_x = np.unravel_index(int(flat_idx), arr.shape)
        score = float(flat[flat_idx])
        rows.append([
            str(rank),
            f'{float(fb[i_fb]):.4f}',
            f'{float(xv[i_x]):.3f}',
            f'{score:.6f}',
        ])

    return dmc.Table(
        data={
            'head': ['Rank', 'f_bin', x_label, 'Score'],
            'body': rows,
        },
        striped=True,
        highlightOnHover=True,
        withTableBorder=True,
        withColumnBorders=True,
    )
