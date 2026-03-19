"""bc.sim_plots — Shared analysis plot functions for bias correction tabs.

Extracted from dsilva.py and langer.py to avoid code duplication.
Used by Dsilva, Langer, and Cadence tabs for post-simulation analysis plots.
"""
from __future__ import annotations
import os, sys
import numpy as np
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from shared import PLOTLY_THEME, get_palette

# ── Shared colors ────────────────────────────────────────────────────────────
_CLR_DETECTED = '#E25A53'   # tomato red
_CLR_MISSED   = '#F5A623'   # amber/orange
_CLR_ALL      = '#52B788'   # green for combined
_CLR_OBS      = '#4A90D9'   # steel blue (observed data)
_CLR_CASE_A   = '#4A90D9'   # steel blue
_CLR_CASE_B   = '#F5A623'   # amber

# ── Helpers ──────────────────────────────────────────────────────────────────

def _safe_mask(arr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Apply boolean mask, returning empty array if source is empty."""
    return arr[mask] if arr.size > 0 else np.array([])


# ─────────────────────────────────────────────────────────────────────────────
# 1. Period Distribution (log P histogram)
# ─────────────────────────────────────────────────────────────────────────────

def render_period_distribution(p, gap_sim, bin_detected_mask, bin_missed_mask,
                               logP_min, logP_max, ana_x_val,
                               x_label='pi', has_case_AB=False):
    """Period distribution histogram with optional Case A/B decomposition."""
    st.markdown('### Period Distribution  (log P)')

    case_A_mask = gap_sim.get('case_A_mask')
    _has_cases = has_case_AB and case_A_mask is not None and gap_sim['P_days'].size > 0

    if _has_cases:
        logP_view = st.radio(
            'View', ['Detected / Missed', 'Case A / B', 'All (Det/Mis + A/B)'],
            horizontal=True, key=f'{p}_logP_view', label_visibility='collapsed')
    else:
        logP_view = 'Detected / Missed'

    logP_all = (np.log10(gap_sim['P_days'])
                if gap_sim['P_days'].size > 0 else np.array([]))
    logP_det = (logP_all[bin_detected_mask]
                if logP_all.size > 0 and np.any(bin_detected_mask)
                else np.array([]))
    logP_mis = (logP_all[bin_missed_mask]
                if logP_all.size > 0 and np.any(bin_missed_mask)
                else np.array([]))
    show_det = logP_view in ('Detected / Missed', 'All (Det/Mis + A/B)')
    show_ab  = logP_view in ('Case A / B', 'All (Det/Mis + A/B)')

    def _add_vlines(fig):
        for val, txt, pos in [(logP_min, 'logP_min', 'top left'),
                              (logP_max, 'logP_max', 'top right')]:
            fig.add_vline(x=float(val), line_dash='dash', line_color='#888',
                          line_width=1.5, annotation_text=txt,
                          annotation_position=pos, annotation_font_color='#888')

    def _add_traces(fig, histnorm_val):
        if show_det:
            for arr, lbl, clr in [(logP_det, 'Detected', _CLR_DETECTED),
                                  (logP_mis, 'Missed', _CLR_MISSED)]:
                if arr.size > 0:
                    fig.add_trace(go.Histogram(
                        x=arr, nbinsx=35, histnorm=histnorm_val,
                        name=f'{lbl} ({arr.size})', marker_color=clr, opacity=0.6))
        if show_ab and _has_cases:
            for mask, lbl, clr in [(case_A_mask, 'Case A', _CLR_CASE_A),
                                   (~case_A_mask, 'Case B', _CLR_CASE_B)]:
                sub = logP_all[mask]
                if sub.size > 0:
                    fig.add_trace(go.Histogram(
                        x=sub, nbinsx=35, histnorm=histnorm_val,
                        name=f'{lbl} ({sub.size})', marker_color=clr, opacity=0.5))

    if _has_cases:
        title_base = {'Detected / Missed': 'Detected vs Missed',
                      'Case A / B': 'Case A vs Case B',
                      'All (Det/Mis + A/B)': 'All Components'}.get(logP_view, '')
        for norm, suffix, ylab, key_sfx, cap in [
            ('probability density', 'density', 'Probability density',
             '_logP_hist_density',
             '**Probability density** normalization (area under curve = 1). '
             'Best for comparing distribution *shapes* independent of sample size.'),
            ('probability', 'fraction', 'Fraction of binaries',
             '_logP_hist_frac',
             '**Fraction per bin** normalization (bin heights sum to 1), '
             'matching the convention used in Langer+2020 Fig. 6. '
             'Directly comparable to the paper.'),
        ]:
            fig = go.Figure()
            _add_traces(fig, norm)
            _add_vlines(fig)
            fig.update_layout(**{
                **PLOTLY_THEME, 'barmode': 'overlay',
                'title': dict(text=f'Period Distribution \u2014 {title_base} ({suffix})',
                              font=dict(size=14)),
                'xaxis_title': 'log\u2081\u2080(P / days)', 'yaxis_title': ylab,
                'height': 400, 'margin': dict(l=60, r=20, t=50, b=50),
                'legend': dict(x=0.60, y=0.95),
            })
            st.plotly_chart(fig, use_container_width=True, key=f'{p}{key_sfx}')
            st.caption(cap)
    else:
        fig_logP = go.Figure()
        if gap_sim['P_days'].size > 0:
            for arr, lbl, clr in [(logP_det, 'Detected', _CLR_DETECTED),
                                  (logP_mis, 'Missed', _CLR_MISSED)]:
                if arr.size > 0:
                    fig_logP.add_trace(go.Histogram(
                        x=arr, nbinsx=35, histnorm='probability density',
                        name=f'{lbl} ({arr.size})', marker_color=clr, opacity=0.6))
        _add_vlines(fig_logP)
        fig_logP.update_layout(**{
            **PLOTLY_THEME, 'barmode': 'overlay',
            'title': dict(text=f'Simulated Period Distribution  ({x_label} = {ana_x_val:.3f})',
                          font=dict(size=14)),
            'xaxis_title': 'log\u2081\u2080(P / days)', 'yaxis_title': 'Probability density',
            'height': 400, 'margin': dict(l=60, r=20, t=50, b=50),
            'legend': dict(x=0.65, y=0.95),
        })
        st.plotly_chart(fig_logP, use_container_width=True, key=f'{p}_logP_hist')
        st.caption(
            'Period distribution of simulated binaries at the best-fit model. '
            'Red: detected binaries (\u0394RV above threshold). '
            'Amber: missed binaries (below threshold). '
            'Missed systems are concentrated at longer periods. '
            'Dashed lines mark the logP bounds used in the simulation.')


# ─────────────────────────────────────────────────────────────────────────────
# 2. Binary Fraction vs Threshold
# ─────────────────────────────────────────────────────────────────────────────

def render_binary_fraction_vs_threshold(p, gap_drv, gap_is_bin, intrinsic_fbin,
                                        observed_fbin, thresh_dRV, missed_count,
                                        total_bin, detected_bin_count, pal,
                                        model_label=''):
    """Binary fraction vs deltaRV threshold with gap annotation."""
    st.markdown('### Observed Binary Fraction vs Threshold')

    n_sim = len(gap_drv)
    thresh_arr = np.linspace(0, float(np.max(gap_drv) * 1.05), 200)
    fbin_curve = np.array([float(np.sum(gap_drv > t)) / n_sim for t in thresh_arr])
    bin_drv_all = gap_drv[gap_is_bin]
    sin_drv_all = gap_drv[~gap_is_bin]
    missed_bin_curve = np.array(
        [float(np.sum(bin_drv_all <= t)) / n_sim for t in thresh_arr])
    false_pos_curve = np.array(
        [float(np.sum(sin_drv_all > t)) / n_sim for t in thresh_arr])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=thresh_arr, y=missed_bin_curve,
        fill='tozeroy', fillcolor='rgba(242,166,35,0.25)',
        line=dict(width=0), mode='lines', name='Missed binaries', showlegend=True))
    if np.any(false_pos_curve > 0):
        fig.add_trace(go.Scatter(
            x=thresh_arr, y=false_pos_curve,
            fill='tozeroy', fillcolor='rgba(74,144,217,0.25)',
            line=dict(width=0), mode='lines', name='Singles above threshold', showlegend=True))
    fig.add_trace(go.Scatter(
        x=thresh_arr, y=fbin_curve, mode='lines',
        name='Observed f_bin(threshold)', line=dict(color=_CLR_OBS, width=2.5)))
    fig.add_hline(y=intrinsic_fbin, line_dash='dot', line_color=_CLR_DETECTED,
                  line_width=2,
                  annotation_text=f'Intrinsic f_bin = {intrinsic_fbin:.1%}',
                  annotation_position='top left',
                  annotation_font=dict(size=11, color=_CLR_DETECTED))
    fig.add_vline(x=thresh_dRV, line_dash='dash', line_color=_CLR_MISSED,
                  line_width=2,
                  annotation_text=f'Threshold = {thresh_dRV} km/s',
                  annotation_position='top right',
                  annotation_font=dict(size=11, color=_CLR_MISSED))
    fig.add_trace(go.Scatter(
        x=[thresh_dRV], y=[observed_fbin], mode='markers+text',
        marker=dict(size=14, color='white', symbol='diamond',
                    line=dict(width=2, color='black')),
        text=[f'{observed_fbin:.1%}'], textposition='top left',
        textfont=dict(size=12, color='#333333'),
        name=f'Observed @ {thresh_dRV} km/s', showlegend=True))

    gap_pct = intrinsic_fbin - observed_fbin
    fig.add_annotation(
        x=thresh_dRV + 15, y=(intrinsic_fbin + observed_fbin) / 2,
        text=f'Gap: {gap_pct:.1%}<br>({missed_count} missed / {total_bin} binaries)',
        showarrow=False, font=dict(size=11, color=_CLR_MISSED),
        bgcolor=pal['annotation_bg'], bordercolor=_CLR_MISSED,
        borderwidth=1, borderpad=4)
    fig.add_annotation(
        x=thresh_dRV, y=intrinsic_fbin, ax=thresh_dRV, ay=observed_fbin,
        xref='x', yref='y', axref='x', ayref='y',
        showarrow=True, arrowhead=3, arrowwidth=2, arrowcolor=_CLR_MISSED)

    fig.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(text='Binary Fraction vs \u0394RV Threshold', font=dict(size=14)),
        'xaxis_title': '\u0394RV threshold (km/s)',
        'yaxis_title': 'Fraction of sample',
        'height': 400, 'margin': dict(l=60, r=80, t=50, b=50),
        'showlegend': True,
        'legend': dict(x=0.55, y=0.95, font=dict(size=10)),
        'yaxis': dict(range=[0, min(1.0, intrinsic_fbin * 1.5)]),
    })
    st.plotly_chart(fig, use_container_width=True, key=f'{p}_gap_chart')
    sfx = f' ({model_label})' if model_label else ''
    st.caption(
        f'Observed binary fraction as a function of \u0394RV threshold{sfx}. '
        f'The blue curve shows the fraction of stars classified as '
        f'binary at each threshold. The dashed red line is the '
        f'intrinsic f_bin = {intrinsic_fbin:.1%}. At our threshold '
        f'({thresh_dRV} km/s), the observed fraction is '
        f'{observed_fbin:.1%} \u2014 a gap of {gap_pct:.1%} due to '
        f'{missed_count} undetectable binaries. '
        f'Amber shading shows missed binaries; blue shading shows '
        f'singles scattered above each threshold.')


# ─────────────────────────────────────────────────────────────────────────────
# 3. Binary Orbital Parameter Histograms (9-panel)
# ─────────────────────────────────────────────────────────────────────────────

def render_orbital_histograms(p, gap_sim, bin_detected_mask, bin_missed_mask,
                              ana_fbin, ana_x_val, x_label, thresh_dRV,
                              detected_bin_count, missed_count,
                              has_case_AB=False):
    """9-panel orbital parameter histograms (detected vs missed)."""
    st.markdown('---')
    st.markdown('### Binary Orbital Properties')

    mb_opts = ['Compare detected vs missed', 'Detected binaries only',
               'Missed binaries only', 'All binaries (combined)']
    if has_case_AB and gap_sim.get('case_A_mask') is not None:
        mb_opts.append('Case A vs Case B')
    mb_view = st.radio('Show populations', mb_opts, horizontal=True,
                       key=f'{p}_mb_view')

    # Extract arrays
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
    has_omega = 'omega' in gap_sim
    if has_omega:
        omega_det = np.degrees(_safe_mask(gap_sim['omega'], bin_detected_mask))
        omega_mis = np.degrees(_safe_mask(gap_sim['omega'], bin_missed_mask))
        T0_det = _safe_mask(gap_sim['T0'], bin_detected_mask)
        T0_mis = _safe_mask(gap_sim['T0'], bin_missed_mask)
    else:
        omega_det = omega_mis = T0_det = T0_mis = np.array([])
    M2_det = q_det * M1_det if q_det.size > 0 and M1_det.size > 0 else np.array([])
    M2_mis = q_mis * M1_mis if q_mis.size > 0 and M1_mis.size > 0 else np.array([])

    P_all = gap_sim['P_days']; e_all = gap_sim['e']; q_all = gap_sim['q']
    K1_all = gap_sim['K1']; M1_all = gap_sim['M1']
    i_all = np.degrees(gap_sim['i_rad'])
    omega_all = np.degrees(gap_sim['omega']) if has_omega else np.array([])
    T0_all = gap_sim['T0'] if has_omega else np.array([])
    M2_all = q_all * M1_all if q_all.size > 0 else np.array([])

    titles = ['log\u2081\u2080(P / days)', 'Eccentricity', 'Mass ratio q',
              'K\u2081 (km/s)', 'M\u2081 (M\u2299)', 'M\u2082 (M\u2299)',
              'Inclination (\u00b0)', '\u03c9 (\u00b0)', 'T\u2080 (rad)']
    xlabs = ['log\u2081\u2080(P / days)', 'e', 'q = M\u2082/M\u2081',
             'K\u2081 (km/s)', 'M\u2081 (M\u2299)', 'M\u2082 (M\u2299)',
             'i (degrees)', '\u03c9 (degrees)', 'T\u2080 (rad)']
    NC, NR, NBINS = 3, 3, 30

    fig_mb = make_subplots(rows=NR, cols=NC, subplot_titles=titles,
                           horizontal_spacing=0.08, vertical_spacing=0.10)

    def _pos(idx):
        return (idx // NC + 1, idx % NC + 1)

    def _add_hist(row, col, data, name, color, show_legend):
        if data.size == 0:
            return
        d_min, d_max = float(data.min()), float(data.max())
        bsz = (d_max - d_min) / NBINS if d_max > d_min else 1.0
        fig_mb.add_trace(go.Histogram(
            x=data, xbins=dict(start=d_min, end=d_max + bsz * 0.01, size=bsz),
            histnorm='probability density', name=name, marker_color=color,
            opacity=0.6, legendgroup=name, showlegend=show_legend,
        ), row=row, col=col)

    def _logP(arr):
        return np.log10(arr) if arr.size > 0 else arr

    if mb_view == 'All binaries (combined)':
        ds = [_logP(P_all), e_all, q_all, K1_all, M1_all, M2_all,
              i_all, omega_all, T0_all]
        for pi, d in enumerate(ds):
            _add_hist(*_pos(pi), d, 'All binaries', _CLR_ALL, pi == 0)
    elif mb_view == 'Case A vs Case B':
        cA = gap_sim['case_A_mask']; cB = ~cA
        for mask, lbl, clr in [(cA, f'Case A ({int(cA.sum())})', _CLR_CASE_A),
                                (cB, f'Case B ({int(cB.sum())})', _CLR_CASE_B)]:
            ds = [_logP(_safe_mask(gap_sim['P_days'], mask)),
                  _safe_mask(gap_sim['e'], mask),
                  _safe_mask(gap_sim['q'], mask),
                  _safe_mask(gap_sim['K1'], mask),
                  _safe_mask(gap_sim['M1'], mask),
                  _safe_mask(gap_sim['q'], mask) * _safe_mask(gap_sim['M1'], mask),
                  np.degrees(_safe_mask(gap_sim['i_rad'], mask)),
                  np.degrees(_safe_mask(gap_sim.get('omega', np.array([])), mask)) if has_omega else np.array([]),
                  _safe_mask(gap_sim.get('T0', np.array([])), mask) if has_omega else np.array([])]
            for pi, d in enumerate(ds):
                _add_hist(*_pos(pi), d, lbl, clr, pi == 0)
    else:
        det_ds = [_logP(P_det), e_det, q_det, K1_det, M1_det, M2_det,
                  i_det, omega_det, T0_det]
        mis_ds = [_logP(P_mis), e_mis, q_mis, K1_mis, M1_mis, M2_mis,
                  i_mis, omega_mis, T0_mis]
        if mb_view in ('Compare detected vs missed', 'Detected binaries only'):
            for pi, d in enumerate(det_ds):
                _add_hist(*_pos(pi), d, 'Detected', _CLR_DETECTED, pi == 0)
        if mb_view in ('Compare detected vs missed', 'Missed binaries only'):
            for pi, d in enumerate(mis_ds):
                _add_hist(*_pos(pi), d, 'Missed', _CLR_MISSED, pi == 0)

    fig_mb.update_layout(**{
        **PLOTLY_THEME, 'barmode': 'overlay', 'height': 850,
        'margin': dict(l=40, r=20, t=40, b=60),
        'legend': dict(orientation='h', yanchor='bottom', y=1.04,
                       xanchor='center', x=0.5),
    })
    for pi in range(9):
        r, c = _pos(pi)
        fig_mb.update_xaxes(title_text=xlabs[pi], showgrid=False, row=r, col=c)
        fig_mb.update_yaxes(showgrid=False, row=r, col=c)
    for ri in range(1, NR + 1):
        fig_mb.update_yaxes(title_text='Prob. density', row=ri, col=1)

    st.plotly_chart(fig_mb, use_container_width=True, key=f'{p}_missed_binaries')
    st.caption(
        f'Orbital parameter distributions of simulated binaries at the '
        f'best-fit model (f_bin={ana_fbin:.3f}, {x_label}={ana_x_val:.2f}). '
        f'**Detected** (red): {detected_bin_count} binaries with '
        f'\u0394RV > {thresh_dRV} km/s. '
        f'**Missed** (amber): {missed_count} binaries below threshold. '
        f'Use "All binaries" to view the full population as a sanity check '
        f'that input distributions match expectations.')



# ─────────────────────────────────────────────────────────────────────────────
# 4. Methodology Equations (Dsilva inline expander)
# ─────────────────────────────────────────────────────────────────────────────

def render_methodology_equations(model_type):
    """Methodology expander with equations.

    For 'langer'/'cadence_*', delegates to helpers._render_methodology_expander.
    For 'dsilva', renders the full inline methodology equations.
    """
    if model_type != 'dsilva':
        from bc.helpers import _render_methodology_expander
        _render_methodology_expander(model_type)
        return

    st.markdown('---')
    with st.expander('Simulation methodology & equations', expanded=False):
        st.markdown(
            '**Simulation overview** \u2014 for each grid point '
            '(f_bin, \u03c0, \u03c3_single):\n\n'
            '1. **Draw N systems** (default 3,000). Each system is binary '
            'with probability f_bin, or single with probability 1 \u2212 f_bin.\n\n'
            '2. **Assign observation cadences.** Each simulated system is randomly '
            'paired with a real star\'s observation times (MJD from FITS headers).\n\n'
            '3. **Single stars:** draw RV at each epoch from '
            'N(v_sys, \u03c3_total) where \u03c3_total = '
            '\u221a(\u03c3_single\u00b2 + \u03c3_measure\u00b2). '
            'Compute \u0394RV = max(v) \u2212 min(v).\n\n'
            '4. **Binary stars:** sample orbital parameters:\n'
            '   - Period P from power-law p(log P) \u221d (log P)^\u03c0\n'
            '   - Eccentricity e ~ U[0, e_max]\n'
            '   - Primary mass M\u2081, mass ratio q = M\u2082/M\u2081\n'
            '   - Inclination i from sin(i) distribution\n'
            '   - \u03c9 ~ U[0, 2\u03c0], T\u2080 ~ U[0, 2\u03c0]\n\n'
            '5. **Compute the RV semi-amplitude K\u2081:**')
        st.latex(
            r'K_1 = \left(\frac{2\pi G}{P}\right)^{1/3}'
            r'\frac{M_2 \sin i}{(M_1 + M_2)^{2/3}}'
            r'\frac{1}{\sqrt{1 - e^2}}')
        st.markdown(
            '6. **Solve Kepler\'s equation** via Newton-Raphson:')
        st.latex(r'E - e \sin E = M, \quad M = T_0 + \frac{2\pi t}{P}')
        st.markdown('7. **True anomaly** \u03bd from E:')
        st.latex(
            r'\tan\frac{\nu}{2} = '
            r'\sqrt{\frac{1+e}{1-e}} \, \tan\frac{E}{2}')
        st.markdown('8. **Radial velocity curve:**')
        st.latex(
            r'v(t) = v_{\rm sys} + K_1 '
            r'\left[\cos(\omega + \nu) + e\cos\omega\right]')
        st.markdown(
            'Then \u0394RV = max(v) \u2212 min(v) over observed epochs.\n\n'
            '9. **Compare** simulated vs observed \u0394RV distribution '
            'using the two-sample K-S test:')
        st.latex(
            r'D = \max_x \left| F_{\rm obs}(x) - F_{\rm sim}(x) \right|')
        st.markdown(
            'Higher p-value \u2192 better match.\n\n'
            '10. **Binary detection criteria** (both required):')
        st.latex(
            r'\Delta\mathrm{RV} > 45.5 \; \mathrm{km/s}'
            r'\quad \text{and} \quad'
            r'\Delta\mathrm{RV} - 4\sigma > 0')
        st.markdown(
            'where \u03c3 is the combined measurement error of the epoch pair.')
