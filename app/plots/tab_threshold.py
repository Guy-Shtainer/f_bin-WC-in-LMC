"""plots/tab_threshold.py — Threshold Analysis sub-tab: piecewise fit, equiv thresholds, survival, PDF."""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from shared import (
    settings_hash, COLOR_BINARY, COLOR_SINGLE, ROOT,
)

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import specs  # noqa: E402

from plots.theme import _academic_fig, _show, _epoch_colors
from plots.data import _wilson_score_interval
from plots.analysis import cached_load_drv_analysis, _is_significant_binary
from plots.compute import (
    fit_two_segment_linear, find_equiv_thresholds,
    compute_survival_curve, survival_to_pdf,
)


def _build_frac_data(df_view, ordered_lines, drverr_map, t_vals):
    """Build fraction-vs-threshold data for all lines."""
    frac_data = {}
    frac_counts = {}  # (n_above, n_total) per line per threshold
    for lk in ordered_lines:
        col_name = f'dRV | {lk}'
        if col_name not in df_view.columns:
            continue
        fracs = []
        counts = []
        for t in t_vals:
            n_above = 0
            n_total = 0
            for _, row in df_view.iterrows():
                dv = row.get(col_name)
                if pd.notna(dv) and np.isfinite(dv):
                    n_total += 1
                    if _is_significant_binary(row['Star'], lk, dv, t, drverr_map):
                        n_above += 1
            fracs.append(n_above / max(n_total, 1))
            counts.append((n_above, n_total))
        frac_data[lk] = fracs
        frac_counts[lk] = counts
    return frac_data, frac_counts


def render_threshold_subtab(settings: dict):
    """Render the Threshold Analysis sub-tab."""
    st.markdown('### Threshold Analysis')

    sh = settings_hash(settings)
    cls_cfg = settings.get('classification', {})

    try:
        df_analysis, drverr_map, rv_epoch_cache, ordered_lines = \
            cached_load_drv_analysis(sh)
    except Exception as e:
        st.error(str(e))
        st.stop()

    # Controls
    c1, c2, c3 = st.columns(3)
    threshold = c1.slider('Reference threshold (km/s)', 5.0, 200.0,
                           float(cls_cfg.get('threshold_dRV', 45.5)),
                           step=0.5, key='xsp_thresh_t')
    civ_default = ordered_lines.index('C IV 5808-5812') \
        if 'C IV 5808-5812' in ordered_lines else 0
    ref_line = c2.selectbox('Reference line', ordered_lines,
                             index=civ_default, key='xsp_thresh_ref_line')
    rv_filter = c3.radio('Filter', ['All', 'Clean only', 'Contaminated only'],
                          horizontal=True, key='xsp_thresh_filter')

    df_view = df_analysis.copy()
    if rv_filter == 'Clean only':
        df_view = df_view[df_view['is_clean_bool']].reset_index(drop=True)
    elif rv_filter == 'Contaminated only':
        df_view = df_view[~df_view['is_clean_bool']].reset_index(drop=True)

    t_vals = np.arange(5, 401, 1)
    frac_data, frac_counts = _build_frac_data(df_view, ordered_lines, drverr_map, t_vals)

    # ── Plot #2: Enhanced f_bin vs Threshold with piecewise fit ───────
    st.markdown('#### f_bin vs Threshold (piecewise fit)')
    if ref_line in frac_data:
        fracs_ref = np.asarray(frac_data[ref_line])
        counts_ref = frac_counts[ref_line]

        # Wilson score error bars
        y_err = np.array([
            (_wilson_score_interval(c[0], c[1])[1] - _wilson_score_interval(c[0], c[1])[0]) / 2.0
            if c[1] > 0 else 0.0
            for c in counts_ref
        ])

        # Fit piecewise
        fit_result = fit_two_segment_linear(t_vals, fracs_ref, y_err if np.any(y_err > 0) else None)

        fig_pw = make_subplots(
            rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
            row_heights=[0.7, 0.3],
            subplot_titles=[f'f_bin vs Threshold ({ref_line})', 'Residuals'],
        )

        # Data + fit
        fig_pw.add_trace(go.Scatter(
            x=t_vals, y=fracs_ref, mode='lines',
            line=dict(color=COLOR_SINGLE, width=1.5), name='Observed f_bin',
        ), row=1, col=1)

        if fit_result:
            fig_pw.add_trace(go.Scatter(
                x=t_vals, y=fit_result['y_fit'], mode='lines',
                line=dict(color='#E25A53', width=2, dash='dash'), name='Piecewise fit',
            ), row=1, col=1)

            # Elbow marker
            fig_pw.add_trace(go.Scatter(
                x=[fit_result['x_break']],
                y=[fit_result['y_fit'][int(np.argmin(np.abs(t_vals - fit_result['x_break'])))]],
                mode='markers', marker=dict(size=12, color='#DAA520', symbol='star'),
                name=f'Elbow = {fit_result["x_break"]:.1f} km/s',
            ), row=1, col=1)

            # Residuals
            fig_pw.add_trace(go.Scatter(
                x=t_vals, y=fit_result['residuals'], mode='lines',
                line=dict(color='grey', width=1), name='Residuals', showlegend=False,
            ), row=2, col=1)
            fig_pw.add_hline(y=0, line_dash='dot', line_color='black', row=2, col=1)

            chi2_text = f'chi2/dof = {fit_result["chi2_dof"]:.3f}'
        else:
            chi2_text = 'Fit failed'

        fig_pw.add_vline(x=threshold, line_dash='dash', line_color='#DAA520',
                         row=1, col=1)

        # Academic styling for subplots
        for row_idx in [1, 2]:
            fig_pw.update_xaxes(showgrid=False, linecolor='black', linewidth=1, mirror=True,
                                ticks='outside', tickcolor='black', row=row_idx, col=1)
            fig_pw.update_yaxes(showgrid=False, linecolor='black', linewidth=1, mirror=True,
                                ticks='outside', tickcolor='black', row=row_idx, col=1)
        fig_pw.update_xaxes(title_text='dRV threshold (km/s)', row=2, col=1)
        fig_pw.update_yaxes(title_text='Binary fraction', row=1, col=1)
        fig_pw.update_yaxes(title_text='Residual', row=2, col=1)
        fig_pw.update_layout(
            height=550, plot_bgcolor='white', paper_bgcolor='white',
            font=dict(family='Times New Roman, serif', color='black'),
            legend=dict(bgcolor='rgba(255,255,255,0)', bordercolor='black', borderwidth=0.5,
                        font=dict(size=10, color='black')),
        )

        _show(fig_pw, f'Two-segment piecewise fit with elbow detection. {chi2_text}.')

    # ── Plot #3: Equivalent Thresholds ────────────────────────────────
    st.markdown('#### Equivalent Thresholds Across Lines')
    if frac_data:
        equiv = find_equiv_thresholds(frac_data, t_vals, ref_line, threshold)
        if equiv:
            eq_names = list(equiv.keys())
            eq_vals = [equiv[k] for k in eq_names]

            fig_eq = _academic_fig(
                height=380, xaxis_title='Emission Line',
                yaxis_title='Equivalent threshold (km/s)',
                title=dict(text=f'Thresholds equivalent to {ref_line} at {threshold:.1f} km/s'),
                xaxis_tickangle=-45,
            )
            bar_colors_eq = [
                '#DAA520' if k == ref_line else COLOR_SINGLE
                for k in eq_names
            ]
            fig_eq.add_trace(go.Bar(
                x=eq_names, y=eq_vals, marker_color=bar_colors_eq,
                showlegend=False,
                text=[f'{v:.1f}' if np.isfinite(v) else 'N/A' for v in eq_vals],
                textposition='outside',
                textfont=dict(size=10, color='black'),
            ))
            fig_eq.add_hline(y=threshold, line_dash='dash', line_color='#DAA520',
                             annotation_text=f'Reference: {threshold:.1f} km/s')
            _show(fig_eq,
                  f'For each line, the threshold that yields the same f_bin as {ref_line} '
                  f'at {threshold:.1f} km/s. Gold = reference line.')

    # ── Plot #7: Survival Function ────────────────────────────────────
    st.markdown('#### Survival Function P(dRV > t)')
    sc1, sc2, sc3, sc4 = st.columns(4)
    sig_single = sc1.number_input('sigma_single (km/s)', value=5.0, step=0.5,
                                   key='xsp_surv_sig_single')
    sig_binary = sc2.number_input('sigma_binary (km/s)', value=30.0, step=1.0,
                                   key='xsp_surv_sig_binary')
    f_bin_surv = sc3.slider('f_bin', 0.0, 1.0, 0.46, step=0.01, key='xsp_surv_fbin')
    n_epochs_surv = sc4.number_input('n_epochs', value=5, min_value=2, max_value=20,
                                      key='xsp_surv_nep')

    t_surv = np.linspace(1, 200, 400)
    surv_single = compute_survival_curve(t_surv, sig_single, n_epochs_surv)
    surv_binary = compute_survival_curve(t_surv, sig_binary, n_epochs_surv)
    surv_mixed = (1 - f_bin_surv) * surv_single + f_bin_surv * surv_binary

    fig_surv = _academic_fig(
        height=420,
        xaxis_title='dRV threshold (km/s)',
        yaxis_title='P(dRV > t)',
        title=dict(text='Survival Function: single vs binary populations'),
    )
    fig_surv.add_trace(go.Scatter(
        x=t_surv, y=surv_single, mode='lines',
        line=dict(color=COLOR_SINGLE, width=2), name=f'Single (sigma={sig_single})',
    ))
    fig_surv.add_trace(go.Scatter(
        x=t_surv, y=surv_binary, mode='lines',
        line=dict(color=COLOR_BINARY, width=2), name=f'Binary (sigma={sig_binary})',
    ))
    fig_surv.add_trace(go.Scatter(
        x=t_surv, y=surv_mixed, mode='lines',
        line=dict(color='#DAA520', width=2, dash='dash'),
        name=f'Mixed (f_bin={f_bin_surv:.2f})',
    ))
    fig_surv.add_vline(x=threshold, line_dash='dot', line_color='grey')
    _show(fig_surv,
          'P(max dRV > t) from Gaussian noise model. '
          'Mixed = (1-f)*P_single + f*P_binary.')

    # ── Plot #8: PDF Intersection ─────────────────────────────────────
    st.markdown('#### PDF Intersection & Optimal Threshold')
    pdf_single = survival_to_pdf(t_surv, surv_single)
    pdf_binary = survival_to_pdf(t_surv, surv_binary)

    wpdf_single = (1 - f_bin_surv) * pdf_single
    wpdf_binary = f_bin_surv * pdf_binary

    fig_pdf = _academic_fig(
        height=420,
        xaxis_title='dRV (km/s)',
        yaxis_title='Probability density',
        title=dict(text='Weighted PDFs and intersection'),
    )

    # Shaded region where binary dominates
    binary_dominates = wpdf_binary > wpdf_single
    if np.any(binary_dominates):
        x_shade = t_surv[binary_dominates]
        y_shade = wpdf_binary[binary_dominates]
        fig_pdf.add_trace(go.Scatter(
            x=np.concatenate([x_shade, x_shade[::-1]]),
            y=np.concatenate([y_shade, np.zeros(len(y_shade))]),
            fill='toself', fillcolor='rgba(226,90,83,0.15)',
            line=dict(width=0), name='Binary dominates', showlegend=True,
        ))

    fig_pdf.add_trace(go.Scatter(
        x=t_surv, y=wpdf_single, mode='lines',
        line=dict(color=COLOR_SINGLE, width=2),
        name=f'(1-f) * PDF_single',
    ))
    fig_pdf.add_trace(go.Scatter(
        x=t_surv, y=wpdf_binary, mode='lines',
        line=dict(color=COLOR_BINARY, width=2),
        name=f'f * PDF_binary',
    ))

    # Find intersection
    diff_pdf = wpdf_single - wpdf_binary
    sign_changes = np.where(np.diff(np.sign(diff_pdf)))[0]
    if len(sign_changes) > 0:
        idx_cross = sign_changes[0]
        t_opt = t_surv[idx_cross]
        fig_pdf.add_vline(x=t_opt, line_dash='dash', line_color='#DAA520',
                          annotation_text=f'Optimal t = {t_opt:.1f} km/s')

    _show(fig_pdf,
          'Weighted PDFs for single and binary populations. '
          'Shaded region = binary dominates. Optimal threshold at intersection.')
