"""plots/tab_rv_analysis.py — RV Analysis sub-tab: bar chart, f_bin curve, per-line, confidence, clean/contam, RV vs epoch, corner."""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from shared import (
    cached_load_observed_delta_rvs, settings_hash,
    COLOR_BINARY, COLOR_SINGLE, ROOT,
)

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import specs  # noqa: E402

from plots.theme import _academic_fig, _show, _epoch_colors
from plots.analysis import cached_load_drv_analysis, _is_significant_binary
from plots.compute import compute_agreement_scores


def render_rv_analysis_subtab(settings: dict):
    """Render the RV Analysis sub-tab."""
    st.markdown('### RV Analysis')

    sh = settings_hash(settings)
    cls_cfg = settings.get('classification', {})

    with st.spinner('Loading RV data...'):
        try:
            obs_delta_rv, detail = cached_load_observed_delta_rvs(sh)
        except Exception as e:
            st.error(str(e))
            st.stop()
        try:
            df_analysis, drverr_map, rv_epoch_cache, ordered_lines = \
                cached_load_drv_analysis(sh)
        except Exception as e:
            st.error(f'Error building analysis DataFrame: {e}')
            st.stop()

    # User controls: threshold, primary line, star filter
    ctrl1, ctrl2, ctrl3 = st.columns(3)
    threshold = ctrl1.slider('dRV threshold (km/s)', 5.0, 200.0,
                              float(cls_cfg.get('threshold_dRV', 45.5)),
                              step=0.5, key='xsp_rv_threshold')
    civ_default = ordered_lines.index('C IV 5808-5812') \
        if 'C IV 5808-5812' in ordered_lines else 0
    primary_line_sel = ctrl2.selectbox('Primary emission line', ordered_lines,
                                        index=civ_default, key='xsp_rv_primary_line')
    rv_filter = ctrl3.radio('Star filter', ['All', 'Clean only', 'Contaminated only'],
                            horizontal=True, key='xsp_rv_filter')

    civ_col = f'dRV | {primary_line_sel}'

    df_view = df_analysis.copy()
    if rv_filter == 'Clean only':
        df_view = df_view[df_view['is_clean_bool']].reset_index(drop=True)
    elif rv_filter == 'Contaminated only':
        df_view = df_view[~df_view['is_clean_bool']].reset_index(drop=True)

    # ── Plot 1: dRV Bar Chart (with sorting controls) ─────────────────
    st.markdown('#### Peak-to-Peak dRV (all stars)')

    # Sorting controls
    sc1, sc2 = st.columns([2, 1])
    sort_col_options = [primary_line_sel] + [lk for lk in ordered_lines if lk != primary_line_sel]
    sort_col_sel = sc1.selectbox('Sort by line', sort_col_options, key='xsp_bar_sort_col')
    sort_asc = sc2.radio('Order', ['Descending', 'Ascending'], horizontal=True,
                         key='xsp_bar_sort_order') == 'Ascending'

    sort_drv_col = f'dRV | {sort_col_sel}'
    if sort_drv_col in df_view.columns:
        df_sorted = df_view.dropna(subset=[sort_drv_col]).sort_values(
            sort_drv_col, ascending=sort_asc).reset_index(drop=True)
        if len(df_sorted) > 0:
            # Show bar using primary line values, sorted by sort_col
            bar_col = civ_col if civ_col in df_sorted.columns else sort_drv_col
            names = df_sorted['Star'].tolist()
            drvs = df_sorted[bar_col].tolist()
            star_names_in_detail = set(detail.keys())
            bar_colors = []
            for sn, d in zip(names, drvs):
                if sn in star_names_in_detail and detail[sn].get('is_binary'):
                    bar_colors.append(COLOR_BINARY)
                else:
                    bar_colors.append(COLOR_SINGLE)

            fig_bar = _academic_fig(
                height=380, xaxis_title='Star', yaxis_title='dRV (km/s)',
                title=dict(text=f'Peak-to-Peak dRV ({primary_line_sel})'),
                xaxis_tickangle=-45,
            )
            fig_bar.add_trace(go.Bar(x=names, y=drvs, marker_color=bar_colors,
                                     showlegend=False))
            fig_bar.add_hline(y=threshold, line_dash='dash', line_color='#DAA520',
                              annotation_text=f'{threshold:.1f} km/s')
            _show(fig_bar,
                  f'Stars sorted by dRV ({sort_col_sel}, {"asc" if sort_asc else "desc"}). '
                  f'Red = binary, blue = single. Threshold = {threshold:.1f} km/s.')

    # ── Plot 2: Binary Fraction vs Threshold ──────────────────────────
    st.markdown('#### Binary Fraction vs dRV Threshold')
    t_vals = np.arange(5, 401, 1)
    frac_data = {}
    for lk in ordered_lines:
        col_name = f'dRV | {lk}'
        if col_name not in df_view.columns:
            continue
        fracs = []
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
        frac_data[lk] = fracs

    if frac_data:
        fig_frac = _academic_fig(
            height=420, xaxis_title='dRV threshold (km/s)',
            yaxis_title='Binary fraction',
            title=dict(text='Observed Binary Fraction vs dRV Threshold'),
        )
        line_colors = _epoch_colors(len(frac_data))
        for i, (lk, fracs) in enumerate(frac_data.items()):
            fig_frac.add_trace(go.Scatter(
                x=t_vals, y=fracs, mode='lines',
                line=dict(color=line_colors[i], width=1.5), name=lk,
            ))
        fig_frac.add_vline(x=threshold, line_dash='dash', line_color='#DAA520',
                           annotation_text=f'{threshold:.1f} km/s')
        _show(fig_frac, 'Each curve shows fraction of stars above threshold for a given line.')

    # ── Plot 3: Binary Fraction per Emission Line ─────────────────────
    st.markdown('#### Binary Fraction per Emission Line')
    line_fracs = {}
    for lk in ordered_lines:
        col_name = f'dRV | {lk}'
        if col_name not in df_view.columns:
            continue
        n_above = n_total = 0
        for _, row in df_view.iterrows():
            dv = row.get(col_name)
            if pd.notna(dv) and np.isfinite(dv):
                n_total += 1
                if _is_significant_binary(row['Star'], lk, dv, threshold, drverr_map):
                    n_above += 1
        if n_total > 0:
            line_fracs[lk] = (n_above / n_total, n_above, n_total)

    if line_fracs:
        lf_names = list(line_fracs.keys())
        lf_vals = [line_fracs[k][0] for k in lf_names]
        lf_texts = [f'{line_fracs[k][1]}/{line_fracs[k][2]}' for k in lf_names]

        fig_lf = _academic_fig(
            height=380, xaxis_title='Emission Line', yaxis_title='Binary Fraction',
            title=dict(text=f'Binary Fraction per Line (threshold={threshold:.1f} km/s)'),
            xaxis_tickangle=-45,
        )
        fig_lf.add_trace(go.Bar(
            x=lf_names, y=lf_vals, marker_color=COLOR_SINGLE,
            text=lf_texts, textposition='outside', showlegend=False,
            textfont=dict(size=10, color='black'),
        ))
        _show(fig_lf,
              f'Fraction classified as binary per emission line at {threshold:.1f} km/s.')

    # ── Plot 4: Confidence Grading ────────────────────────────────────
    st.markdown('#### Confidence Grading')
    confidence_data = {'Golden': [], 'Silver': [], 'Bronze': []}
    for _, row in df_view.iterrows():
        sn = row['Star']
        n_binary = n_single = n_valid = 0
        for lk in ordered_lines:
            dv = row.get(f'dRV | {lk}')
            if pd.notna(dv) and np.isfinite(dv):
                n_valid += 1
                if _is_significant_binary(sn, lk, dv, threshold, drverr_map):
                    n_binary += 1
                else:
                    n_single += 1
        if n_valid == 0:
            continue
        agreement = max(n_binary, n_single) / n_valid
        if agreement >= 0.9:
            confidence_data['Golden'].append(sn)
        elif agreement >= 0.7:
            confidence_data['Silver'].append(sn)
        else:
            confidence_data['Bronze'].append(sn)

    grades = list(confidence_data.keys())
    grade_counts = [len(confidence_data[g]) for g in grades]
    grade_colors_map = ['#DAA520', '#C0C0C0', '#CD7F32']

    fig_grade = _academic_fig(
        height=350, xaxis_title='Grade', yaxis_title='Number of stars',
        title=dict(text='Confidence Grading'),
    )
    fig_grade.add_trace(go.Bar(
        x=grades, y=grade_counts, marker_color=grade_colors_map,
        text=grade_counts, textposition='outside', showlegend=False,
        textfont=dict(size=12, color='black'),
    ))
    _show(fig_grade, 'Confidence grading based on line agreement. Gold >= 90%, Silver >= 70%, Bronze < 70%.')
    for g in grades:
        if confidence_data[g]:
            st.caption(f"**{g}** ({len(confidence_data[g])}): "
                       f"{', '.join(confidence_data[g])}")

    # ── Plot 5: Clean vs Contaminated ─────────────────────────────────
    st.markdown('#### Clean vs Contaminated Comparison')
    if civ_col in df_analysis.columns:
        categories = ['All', 'Clean', 'Contaminated']
        counts_bin = []
        counts_sin = []
        for cat in categories:
            sub = df_analysis if cat == 'All' else (
                df_analysis[df_analysis['is_clean_bool']] if cat == 'Clean'
                else df_analysis[~df_analysis['is_clean_bool']])
            n_b = n_s = 0
            for _, row in sub.iterrows():
                dv = row.get(civ_col)
                if pd.notna(dv) and np.isfinite(dv):
                    if _is_significant_binary(row['Star'], primary_line_sel, dv,
                                              threshold, drverr_map):
                        n_b += 1
                    else:
                        n_s += 1
            counts_bin.append(n_b)
            counts_sin.append(n_s)

        fig_cc = _academic_fig(
            height=380, xaxis_title='Sample', yaxis_title='Count',
            title=dict(text='Binary/Single by Sample'), barmode='group',
        )
        fig_cc.add_trace(go.Bar(
            x=categories, y=counts_bin, marker_color=COLOR_BINARY, name='Binary',
            text=counts_bin, textposition='auto',
        ))
        fig_cc.add_trace(go.Bar(
            x=categories, y=counts_sin, marker_color=COLOR_SINGLE, name='Single',
            text=counts_sin, textposition='auto',
        ))
        _show(fig_cc, 'Binary vs single counts for all, clean-only, and contaminated-only.')

    # ── Plot 6: RV vs Epoch (per star) ────────────────────────────────
    st.markdown('#### RV vs Epoch')
    star_rv = st.selectbox('Star', specs.star_names, key='xsp_rv_star')
    rv_arr = detail.get(star_rv, {}).get('rv', np.array([]))
    err_arr_rv = detail.get(star_rv, {}).get('rv_err', np.array([]))

    fig_rvep = _academic_fig(
        height=380, xaxis_title='Observation #', yaxis_title='RV (km/s)',
        title=dict(text=f'{star_rv} -- RV per epoch'),
    )
    if len(rv_arr) > 0:
        is_bin = detail.get(star_rv, {}).get('is_binary')
        mc = COLOR_BINARY if is_bin else COLOR_SINGLE
        fig_rvep.add_trace(go.Scatter(
            x=list(range(1, len(rv_arr) + 1)), y=rv_arr,
            error_y=dict(type='data', array=err_arr_rv, visible=True),
            mode='markers+lines', marker=dict(size=8, color=mc),
            name=f'RV ({primary_line_sel})',
        ))
    if len(rv_arr) > 0:
        drv_star = detail.get(star_rv, {}).get('best_dRV', 0)
        _show(fig_rvep,
              f'RV per epoch for {star_rv}. dRV = {drv_star:.1f} km/s. '
              f'{"Binary" if detail.get(star_rv, {}).get("is_binary") else "Single"}.')
    else:
        _show(fig_rvep, f'RV per epoch for {star_rv}. No data available.')

    # ── Plot 7: Corner Plot ───────────────────────────────────────────
    st.markdown('#### dRV Correlation Matrix')
    valid_lines = []
    for lk in ordered_lines:
        cn = f'dRV | {lk}'
        if cn in df_view.columns and df_view[cn].dropna().shape[0] >= 3:
            valid_lines.append(lk)

    corner_lines = st.multiselect('Lines to include', valid_lines,
                                  default=valid_lines[:5] if len(valid_lines) > 5 else valid_lines,
                                  key='xsp_corner_lines')

    if len(corner_lines) >= 2:
        n = len(corner_lines)
        fig_corner = make_subplots(rows=n, cols=n,
                                   horizontal_spacing=0.03, vertical_spacing=0.03)

        for i, li in enumerate(corner_lines):
            for j, lj in enumerate(corner_lines):
                col_i = f'dRV | {li}'
                col_j = f'dRV | {lj}'

                if i == j:
                    xi = df_view[col_i].dropna().values
                    fig_corner.add_trace(go.Histogram(
                        x=xi, nbinsx=12, marker_color=COLOR_SINGLE, opacity=0.7,
                        showlegend=False,
                    ), row=i + 1, col=j + 1)
                elif i > j:
                    common = df_view[['Star', col_i, col_j]].dropna()
                    err_y = [drverr_map.get((s, li), np.nan) for s in common['Star']]
                    err_x = [drverr_map.get((s, lj), np.nan) for s in common['Star']]
                    cc = [COLOR_BINARY if detail.get(s, {}).get('is_binary')
                          else COLOR_SINGLE for s in common['Star']]
                    fig_corner.add_trace(go.Scatter(
                        x=common[col_j].values, y=common[col_i].values,
                        error_x=dict(type='data', array=err_x, visible=True,
                                     thickness=1, width=3),
                        error_y=dict(type='data', array=err_y, visible=True,
                                     thickness=1, width=3),
                        mode='markers', marker=dict(size=5, color=cc, opacity=0.7),
                        showlegend=False, hovertext=common['Star'].values,
                    ), row=i + 1, col=j + 1)
                    fig_corner.add_hline(y=threshold, line_dash='dash',
                                         line_color='#DAA520', line_width=1,
                                         row=i + 1, col=j + 1)
                    fig_corner.add_vline(x=threshold, line_dash='dash',
                                         line_color='#DAA520', line_width=1,
                                         row=i + 1, col=j + 1)

                if j == 0:
                    fig_corner.update_yaxes(title_text=li[:12], row=i + 1, col=j + 1,
                                            title_font=dict(size=8, color='black'))
                if i == n - 1:
                    fig_corner.update_xaxes(title_text=lj[:12], row=i + 1, col=j + 1,
                                            title_font=dict(size=8, color='black'))
                fig_corner.update_xaxes(
                    showgrid=False, linecolor='black', linewidth=0.8, mirror=True,
                    ticks='outside', tickcolor='black',
                    row=i + 1, col=j + 1)
                fig_corner.update_yaxes(
                    showgrid=False, linecolor='black', linewidth=0.8, mirror=True,
                    ticks='outside', tickcolor='black',
                    row=i + 1, col=j + 1)

        fig_corner.update_layout(
            height=200 * n, showlegend=False,
            plot_bgcolor='white', paper_bgcolor='white',
            font=dict(family='Times New Roman, serif', color='black'),
            title=dict(text='dRV Correlation Matrix',
                       font=dict(size=15, family='Times New Roman, serif', color='black')),
        )
        _show(fig_corner,
              'Diagonal: histograms. Below diagonal: pairwise scatter. '
              'Red = binary, blue = single.')
    elif len(corner_lines) == 1:
        st.info('Select at least 2 lines for the correlation matrix.')

    # ── Plot 8: Agreement Ranking ─────────────────────────────────────
    st.markdown('#### Agreement Ranking (line-line correlation)')
    if len(valid_lines) >= 2:
        scores = compute_agreement_scores(df_view, valid_lines)
        if scores:
            sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
            ag_names = [s[0] for s in sorted_scores]
            ag_vals = [s[1] for s in sorted_scores]

            fig_agree = _academic_fig(
                height=380, xaxis_title='Emission Line', yaxis_title='Agreement Score',
                title=dict(text='Line Agreement Ranking (correlation-weighted)'),
                xaxis_tickangle=-45,
            )
            fig_agree.add_trace(go.Bar(
                x=ag_names, y=ag_vals, marker_color=COLOR_SINGLE,
                showlegend=False,
                text=[f'{v:.2f}' for v in ag_vals], textposition='outside',
                textfont=dict(size=10, color='black'),
            ))
            _show(fig_agree,
                  'Each line scored by mean Pearson r with all other lines, '
                  'weighted by number of common stars / total stars.')
    else:
        st.info('Need at least 2 valid lines for agreement ranking.')
