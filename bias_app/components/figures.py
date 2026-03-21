"""
bias_app/components/figures.py
──────────────────────────────
Pure Plotly figure factories for bias-correction simulation plots.

Each function takes an explicit ``theme: dict`` parameter and returns a
``go.Figure``.  No Streamlit, no Dash html/dcc imports.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config import SCORING_METHODS

# ── Shared colours ────────────────────────────────────────────────────────────
_CLR_DETECTED = '#E25A53'
_CLR_MISSED = '#F5A623'
_CLR_ALL = '#52B788'
_CLR_OBS = '#4A90D9'


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'rgba({r},{g},{b},{alpha})'


def _safe_mask(arr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    return arr[mask] if arr.size > 0 else np.array([])


def _empty_fig(message: str, theme: dict, height: int = 300) -> go.Figure:
    """Return an empty figure with a centred annotation."""
    fig = go.Figure()
    fig.add_annotation(text=message, xref='paper', yref='paper',
                       x=0.5, y=0.5, showarrow=False,
                       font=dict(size=14, color='#888'))
    fig.update_layout(**{**theme, 'height': height,
                         'xaxis': dict(visible=False),
                         'yaxis': dict(visible=False)})
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 1. Max p-value vs scan variable
# ─────────────────────────────────────────────────────────────────────────────

def make_max_pval_fig(
    sigma_vals: np.ndarray,
    max_pvals: list[float],
    theme: dict,
    height: int = 300,
    x_label: str = 'σ_single',
    stat_label: str = 'K-S',
) -> go.Figure:
    best_idx = int(np.argmax(max_pvals))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sigma_vals, y=max_pvals, mode='lines+markers',
        marker=dict(size=8, color='#4A90D9'),
        line=dict(color='#4A90D9', width=2),
        hovertemplate=(f'{x_label}=%{{x:.2f}}<br>'
                       f'max {stat_label}=%{{y:.4f}}<extra></extra>'),
        showlegend=False))
    fig.add_trace(go.Scatter(
        x=[float(sigma_vals[best_idx])], y=[max_pvals[best_idx]],
        mode='markers+text',
        marker=dict(symbol='star', size=16, color='gold',
                    line=dict(color='black', width=1)),
        text=[f'  {x_label}={float(sigma_vals[best_idx]):.2f}, '
              f'{stat_label}={max_pvals[best_idx]:.4f}'],
        textposition='middle right',
        textfont=dict(color='gold', size=11),
        showlegend=False))
    fig.update_layout(**{
        **theme,
        'title': dict(text=f'Max {stat_label} vs {x_label}',
                       font=dict(size=14)),
        'xaxis_title': x_label,
        'yaxis_title': f'Max {stat_label}',
        'height': height,
        'margin': dict(l=60, r=20, t=50, b=50),
    })
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 2. Period distribution histogram
# ─────────────────────────────────────────────────────────────────────────────

def make_period_dist_fig(
    gap_sim: dict,
    bin_detected_mask: np.ndarray,
    bin_missed_mask: np.ndarray,
    logP_min: float,
    logP_max: float,
    theme: dict,
    has_case_AB: bool = False,
) -> go.Figure:
    logP_all = (np.log10(gap_sim['P_days'])
                if gap_sim['P_days'].size > 0 else np.array([]))
    logP_det = (_safe_mask(logP_all, bin_detected_mask)
                if logP_all.size > 0 and np.any(bin_detected_mask)
                else np.array([]))
    logP_mis = (_safe_mask(logP_all, bin_missed_mask)
                if logP_all.size > 0 and np.any(bin_missed_mask)
                else np.array([]))

    fig = go.Figure()
    for arr, lbl, clr in [(logP_det, 'Detected', _CLR_DETECTED),
                           (logP_mis, 'Missed', _CLR_MISSED)]:
        if arr.size > 0:
            fig.add_trace(go.Histogram(
                x=arr, nbinsx=35, histnorm='probability density',
                name=f'{lbl} ({arr.size})', marker_color=clr, opacity=0.6))

    # Vertical boundary lines
    for val, txt, pos in [(logP_min, 'logP_min', 'top left'),
                           (logP_max, 'logP_max', 'top right')]:
        fig.add_vline(x=float(val), line_dash='dash', line_color='#888',
                      line_width=1.5, annotation_text=txt,
                      annotation_position=pos,
                      annotation_font_color='#888')

    fig.update_layout(**{
        **theme, 'barmode': 'overlay',
        'title': dict(text='Period Distribution (log P)',
                       font=dict(size=14)),
        'xaxis_title': 'log\u2081\u2080(P / days)',
        'yaxis_title': 'Probability density',
        'height': 400,
        'margin': dict(l=60, r=20, t=50, b=50),
        'legend': dict(x=0.65, y=0.95),
    })
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 3. Binary fraction vs threshold
# ─────────────────────────────────────────────────────────────────────────────

def make_binary_frac_fig(
    gap_drv: np.ndarray,
    gap_is_bin: np.ndarray,
    intrinsic_fbin: float,
    observed_fbin: float,
    thresh_dRV: float,
    theme: dict,
) -> go.Figure:
    n_sim = len(gap_drv)
    thresh_arr = np.linspace(0, float(np.max(gap_drv) * 1.05), 200)
    fbin_curve = np.array([float(np.sum(gap_drv > t)) / n_sim
                           for t in thresh_arr])
    bin_drv_all = gap_drv[gap_is_bin]
    sin_drv_all = gap_drv[~gap_is_bin]
    missed_bin_curve = np.array(
        [float(np.sum(bin_drv_all <= t)) / n_sim for t in thresh_arr])
    false_pos_curve = np.array(
        [float(np.sum(sin_drv_all > t)) / n_sim for t in thresh_arr])

    total_bin = int(np.sum(gap_is_bin))
    detected_count = int(np.sum(gap_drv[gap_is_bin] > thresh_dRV)) \
        if total_bin > 0 else 0
    missed_count = total_bin - detected_count

    fig = go.Figure()
    # Missed binaries fill
    fig.add_trace(go.Scatter(
        x=thresh_arr, y=missed_bin_curve,
        fill='tozeroy', fillcolor='rgba(242,166,35,0.25)',
        line=dict(width=0), mode='lines',
        name='Missed binaries', showlegend=True))
    # Singles above threshold
    if np.any(false_pos_curve > 0):
        fig.add_trace(go.Scatter(
            x=thresh_arr, y=false_pos_curve,
            fill='tozeroy', fillcolor='rgba(74,144,217,0.25)',
            line=dict(width=0), mode='lines',
            name='Singles above threshold', showlegend=True))
    # Observed f_bin line
    fig.add_trace(go.Scatter(
        x=thresh_arr, y=fbin_curve, mode='lines',
        name='Observed f_bin(threshold)',
        line=dict(color=_CLR_OBS, width=2.5)))
    # Intrinsic f_bin horizontal line
    fig.add_hline(y=intrinsic_fbin, line_dash='dot',
                  line_color=_CLR_DETECTED, line_width=2,
                  annotation_text=f'Intrinsic f_bin = {intrinsic_fbin:.1%}',
                  annotation_position='top left',
                  annotation_font=dict(size=11, color=_CLR_DETECTED))
    # Threshold vertical line
    fig.add_vline(x=thresh_dRV, line_dash='dash',
                  line_color=_CLR_MISSED, line_width=2,
                  annotation_text=f'Threshold = {thresh_dRV} km/s',
                  annotation_position='top right',
                  annotation_font=dict(size=11, color=_CLR_MISSED))
    # Diamond marker at observed point
    fig.add_trace(go.Scatter(
        x=[thresh_dRV], y=[observed_fbin], mode='markers+text',
        marker=dict(size=14, color='white', symbol='diamond',
                    line=dict(width=2, color='black')),
        text=[f'{observed_fbin:.1%}'], textposition='top left',
        textfont=dict(size=12, color='#333333'),
        name=f'Observed @ {thresh_dRV} km/s', showlegend=True))
    # Gap annotation
    gap_pct = intrinsic_fbin - observed_fbin
    fig.add_annotation(
        x=thresh_dRV + 15,
        y=(intrinsic_fbin + observed_fbin) / 2,
        text=f'Gap: {gap_pct:.1%}<br>({missed_count} missed / {total_bin} binaries)',
        showarrow=False, font=dict(size=11, color=_CLR_MISSED),
        bgcolor='rgba(255,255,255,0.7)', bordercolor=_CLR_MISSED,
        borderwidth=1, borderpad=4)
    fig.add_annotation(
        x=thresh_dRV, y=intrinsic_fbin,
        ax=thresh_dRV, ay=observed_fbin,
        xref='x', yref='y', axref='x', ayref='y',
        showarrow=True, arrowhead=3, arrowwidth=2, arrowcolor=_CLR_MISSED)

    fig.update_layout(**{
        **theme,
        'title': dict(text='Binary Fraction vs \u0394RV Threshold',
                       font=dict(size=14)),
        'xaxis_title': '\u0394RV threshold (km/s)',
        'yaxis_title': 'Fraction of sample',
        'height': 400,
        'margin': dict(l=60, r=80, t=50, b=50),
        'showlegend': True,
        'legend': dict(x=0.55, y=0.95, font=dict(size=10)),
        'yaxis': dict(range=[0, min(1.0, intrinsic_fbin * 1.5)]),
    })
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 4. Orbital parameter histograms (3x3)
# ─────────────────────────────────────────────────────────────────────────────

def make_orbital_hist_fig(
    gap_sim: dict,
    bin_detected_mask: np.ndarray,
    bin_missed_mask: np.ndarray,
    theme: dict,
) -> go.Figure:
    titles = ['log\u2081\u2080(P / days)', 'Eccentricity', 'Mass ratio q',
              'K\u2081 (km/s)', 'M\u2081 (M\u2299)', 'M\u2082 (M\u2299)',
              'Inclination (\u00b0)', '\u03c9 (\u00b0)', 'T\u2080 (rad)']
    xlabs = ['log\u2081\u2080(P / days)', 'e', 'q = M\u2082/M\u2081',
             'K\u2081 (km/s)', 'M\u2081 (M\u2299)', 'M\u2082 (M\u2299)',
             'i (degrees)', '\u03c9 (degrees)', 'T\u2080 (rad)']
    NC, NR, NBINS = 3, 3, 30

    def _logP(arr):
        return np.log10(arr) if arr.size > 0 else arr

    has_omega = 'omega' in gap_sim

    P_det = _safe_mask(gap_sim['P_days'], bin_detected_mask)
    P_mis = _safe_mask(gap_sim['P_days'], bin_missed_mask)
    e_det = _safe_mask(gap_sim['e'], bin_detected_mask)
    e_mis = _safe_mask(gap_sim['e'], bin_missed_mask)
    q_det = _safe_mask(gap_sim['q'], bin_detected_mask)
    q_mis = _safe_mask(gap_sim['q'], bin_missed_mask)
    K1_det = _safe_mask(gap_sim['K1'], bin_detected_mask)
    K1_mis = _safe_mask(gap_sim['K1'], bin_missed_mask)
    M1_det = _safe_mask(gap_sim['M1'], bin_detected_mask)
    M1_mis = _safe_mask(gap_sim['M1'], bin_missed_mask)
    i_det = np.degrees(_safe_mask(gap_sim['i_rad'], bin_detected_mask))
    i_mis = np.degrees(_safe_mask(gap_sim['i_rad'], bin_missed_mask))
    if has_omega:
        omega_det = np.degrees(_safe_mask(gap_sim['omega'], bin_detected_mask))
        omega_mis = np.degrees(_safe_mask(gap_sim['omega'], bin_missed_mask))
        T0_det = _safe_mask(gap_sim['T0'], bin_detected_mask)
        T0_mis = _safe_mask(gap_sim['T0'], bin_missed_mask)
    else:
        omega_det = omega_mis = T0_det = T0_mis = np.array([])
    M2_det = q_det * M1_det if q_det.size > 0 and M1_det.size > 0 \
        else np.array([])
    M2_mis = q_mis * M1_mis if q_mis.size > 0 and M1_mis.size > 0 \
        else np.array([])

    det_ds = [_logP(P_det), e_det, q_det, K1_det, M1_det, M2_det,
              i_det, omega_det, T0_det]
    mis_ds = [_logP(P_mis), e_mis, q_mis, K1_mis, M1_mis, M2_mis,
              i_mis, omega_mis, T0_mis]

    fig = make_subplots(rows=NR, cols=NC, subplot_titles=titles,
                        horizontal_spacing=0.08, vertical_spacing=0.10)

    def _pos(idx):
        return (idx // NC + 1, idx % NC + 1)

    def _add_hist(row, col, data, name, color, show_legend):
        if data.size == 0:
            return
        d_min, d_max = float(data.min()), float(data.max())
        bsz = (d_max - d_min) / NBINS if d_max > d_min else 1.0
        fig.add_trace(go.Histogram(
            x=data,
            xbins=dict(start=d_min, end=d_max + bsz * 0.01, size=bsz),
            histnorm='probability density', name=name, marker_color=color,
            opacity=0.6, legendgroup=name, showlegend=show_legend,
        ), row=row, col=col)

    for pi, d in enumerate(det_ds):
        _add_hist(*_pos(pi), d, 'Detected', _CLR_DETECTED, pi == 0)
    for pi, d in enumerate(mis_ds):
        _add_hist(*_pos(pi), d, 'Missed', _CLR_MISSED, pi == 0)

    fig.update_layout(**{
        **theme, 'barmode': 'overlay', 'height': 850,
        'margin': dict(l=40, r=20, t=40, b=60),
        'legend': dict(orientation='h', yanchor='bottom', y=1.04,
                       xanchor='center', x=0.5),
    })
    for pi in range(9):
        r, c = _pos(pi)
        fig.update_xaxes(title_text=xlabs[pi], showgrid=False, row=r, col=c)
        fig.update_yaxes(showgrid=False, row=r, col=c)
    for ri in range(1, NR + 1):
        fig.update_yaxes(title_text='Prob. density', row=ri, col=1)

    return fig


# ─────────────────────────────────────────────────────────────────────────────
# 5. All-methods CDF comparison
# ─────────────────────────────────────────────────────────────────────────────

def make_all_methods_cdf_fig(
    result: dict,
    method_results: dict,
    fbin_g: np.ndarray,
    x_g: np.ndarray,
    theme: dict,
    x_name: str = 'pi',
    x_label: str = 'pi',
) -> go.Figure:
    """Observed CDF vs best-fit model CDFs from each scoring method."""
    from wr_bias_simulation import (
        binned_cdf, DEFAULT_DRV_BIN_EDGES,
        simulate_delta_rv_sample, SimulationConfig, BinaryParameterConfig,
    )

    obs_drv = np.asarray(result.get('obs_delta_rv', []))
    if obs_drv.size == 0 or len(method_results) < 1:
        return _empty_fig('No observation data for CDF', theme)

    _be = result.get('bin_edges')
    _be = np.asarray(_be) if _be is not None else DEFAULT_DRV_BIN_EDGES
    _n_obs = len(obs_drv)
    obs_cdf = binned_cdf(obs_drv, _be)
    _obs_x = np.concatenate([[0.0], _be])
    _obs_y = np.concatenate([[0.0], obs_cdf])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=_obs_x, y=_obs_y, mode='lines', name='Observed',
        line=dict(color='black', width=2.5)))

    _n_cdf_sets = 100
    for mk, info in method_results.items():
        bv = info['best_vals']
        fb = bv.get('fbin', 0.5)
        pi_v = bv.get(x_name, 0.0)
        sig_v = bv.get('sigma', 5.0)
        _mcolor = next(
            (c for k, _, _, _, c in SCORING_METHODS if k == mk), '#888888')
        _mname = next(
            (n for k, n, _, _, _ in SCORING_METHODS if k == mk), mk)
        try:
            _all_cdfs = []
            for _seed_i in range(_n_cdf_sets):
                sim_cfg = SimulationConfig(
                    n_stars=_n_obs,
                    sigma_single=float(sig_v),
                    sigma_measure=float(result.get('sigma_meas', 3.0)),
                )
                bin_cfg = BinaryParameterConfig()
                rng = np.random.default_rng(42 + _seed_i)
                sim_drv = simulate_delta_rv_sample(
                    f_bin=float(fb), pi=float(pi_v),
                    sim_cfg=sim_cfg, bin_cfg=bin_cfg, rng=rng)
                _all_cdfs.append(binned_cdf(sim_drv, _be))
            _all_cdfs = np.array(_all_cdfs)
            _median = np.median(_all_cdfs, axis=0)
            _lo = np.percentile(_all_cdfs, 16, axis=0)
            _hi = np.percentile(_all_cdfs, 84, axis=0)

            _med_x = np.concatenate([[0.0], _be])
            _med_y = np.concatenate([[0.0], _median])
            _lo_y = np.concatenate([[0.0], _lo])
            _hi_y = np.concatenate([[0.0], _hi])

            _lbl = f'{_mname} (f_bin={fb:.3f}'
            if x_name in bv:
                _lbl += f', {x_label}={bv[x_name]:.2f}'
            _lbl += ')'

            fig.add_trace(go.Scatter(
                x=np.concatenate([_med_x, _med_x[::-1]]),
                y=np.concatenate([_hi_y, _lo_y[::-1]]),
                fill='toself', fillcolor=_hex_to_rgba(_mcolor, 0.2),
                line=dict(color='rgba(0,0,0,0)'),
                legendgroup=mk, showlegend=False, hoverinfo='skip'))
            fig.add_trace(go.Scatter(
                x=_med_x, y=_med_y, mode='lines', name=_lbl,
                legendgroup=mk,
                line=dict(color=_mcolor, width=2, dash='dash')))
        except Exception:
            pass

    fig.update_layout(**{
        **theme,
        'title': dict(text='CDF Comparison: Observed vs Best-Fit Models',
                       font=dict(size=14)),
        'xaxis_title': '\u0394RV (km/s)',
        'yaxis_title': 'Cumulative Fraction',
        'height': 400,
        'legend': dict(x=0.55, y=0.05),
    })
    return fig
