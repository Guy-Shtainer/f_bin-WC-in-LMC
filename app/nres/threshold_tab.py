"""nres/threshold_tab.py — Threshold Analysis tab for NRES analysis."""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

from shared import (
    get_obs_manager, apply_theme, COLOR_BINARY, COLOR_SINGLE, ROOT,
)

from nres.config import NRES_STARS
from nres.data import (
    _load_star_epochs, _load_existing_rvs,
    _compute_epoch_summary, _compute_threshold_stats,
    _color_log_rainbow_text_col,
)

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def render_threshold_tab(settings):
    """Render the 'Threshold Analysis' tab."""
    st.markdown('### Single-Star RV Variability & Detection Threshold')
    st.caption(
        'WR 52 and WR17 are assumed single or very long-period binaries. '
        'Their RV scatter (σ_overall) is the noise floor used as σ in the '
        'binary detection criterion: **ΔRV − 4σ > 0**. '
        'The 45.5 km/s ΔRV threshold is a separate criterion; both must be met.'
    )

    # Gather data for both stars
    analysis_data = {}
    analysis_rv_dfs = {}
    for sn in NRES_STARS:
        ccf_key = f'nres_ccf_results_{sn}'
        if ccf_key in st.session_state:
            rv_df_t = st.session_state[ccf_key]
        else:
            ep_list, sp_per_ep = _load_star_epochs(sn)
            rv_df_t = _load_existing_rvs(sn, ep_list, sp_per_ep)

        if rv_df_t is not None and len(rv_df_t) > 0:
            stats = _compute_threshold_stats(rv_df_t)
            if stats:
                analysis_data[sn] = stats
                analysis_rv_dfs[sn] = rv_df_t

    if not analysis_data:
        st.info('No RV data available for either star. Run CCF in the "Spectra & CCF" tab first.')
        return

    # ── Structured table: rows=(star,line), columns grouped by epoch ─────
    st.markdown('### RV Summary Table')

    table_rows = []
    all_within = []
    all_between = []
    all_overall = []

    for sn, line_results in analysis_data.items():
        for line_name, stats in line_results.items():
            row = {'Star': sn, 'Line': line_name}
            for ei, (mu, err, n_sp) in enumerate(zip(
                stats['epoch_means'], stats['epoch_errs'],
                stats.get('n_spectra_per_ep', [0] * stats['n_epochs'])
            )):
                row[f'Ep{ei + 1} μ'] = round(mu, 2)
                row[f'Ep{ei + 1} σ'] = round(stats['sigma_within'], 2) if ei == 0 else ''
                row[f'Ep{ei + 1} N'] = int(n_sp)
            # Recalculate per-epoch σ individually
            rv_df_line = analysis_rv_dfs[sn]
            rv_line = rv_df_line[rv_df_line['Line'] == line_name]
            for ei, ep in enumerate(sorted(rv_line['Epoch'].unique())):
                ep_rvs = rv_line[rv_line['Epoch'] == ep]['RV (km/s)'].values.astype(float)
                ep_rvs = ep_rvs[np.isfinite(ep_rvs)]
                row[f'Ep{ei + 1} σ'] = round(np.std(ep_rvs, ddof=1), 2) if len(ep_rvs) >= 2 else 0.0

            row['Total μ'] = round(np.mean(stats['epoch_means']), 2)
            row['Total σ'] = round(stats['sigma_overall'], 2)
            row['ΔRV'] = round(stats['delta_rv'], 2)
            row['ΔRV/4σ'] = round(stats['significance'], 2)
            table_rows.append(row)

            all_within.append(stats['sigma_within'])
            all_between.append(stats['sigma_between'])
            all_overall.append(stats['sigma_overall'])

    summary_df = pd.DataFrame(table_rows)
    # Apply rainbow coloring to ΔRV and σ columns
    color_cols = [c for c in summary_df.columns if c in ['ΔRV', 'Total σ', 'ΔRV/4σ']]
    styler = summary_df.style
    if color_cols:
        styler = styler.apply(_color_log_rainbow_text_col, subset=color_cols)
    # Format numeric columns
    for c in summary_df.columns:
        if c not in ['Star', 'Line'] and summary_df[c].dtype in ['float64', 'int64']:
            styler = styler.format('{:.2f}', subset=[c], na_rep='—')
    st.dataframe(styler, use_container_width=True, hide_index=True)
    st.caption(
        'μ = weighted mean RV (km/s), σ = std of spectra RVs within epoch, '
        'N = number of spectra, ΔRV/4σ = significance for 4σ criterion. '
        'Colors: log-gradient rainbow (violet=low, red=high).'
    )

    # Per-spectra detail
    with st.expander('Per-spectra RV detail'):
        for sn in analysis_rv_dfs:
            st.markdown(f'**{sn}**')
            st.dataframe(analysis_rv_dfs[sn], use_container_width=True, hide_index=True)

    # ── Build color map for (star, line) ────────────────────────────────
    trace_colors_list = px.colors.qualitative.Plotly
    color_map = {}
    ci = 0
    for sn in analysis_data:
        for ln in analysis_data[sn]:
            color_map[(sn, ln)] = trace_colors_list[ci % len(trace_colors_list)]
            ci += 1

    # ── MJD-to-date helper ────────────────────────────────────────────────
    from astropy.time import Time as AstropyTime
    def _mjd_to_dates(mjds):
        return [AstropyTime(m, format='mjd').datetime for m in mjds]

    # ── Filters ───────────────────────────────────────────────────────────
    st.divider()
    st.markdown('### RV vs Date')
    all_lines_set = sorted({ln for sn in analysis_data for ln in analysis_data[sn]})

    fc1, fc2 = st.columns([1, 2])
    with fc1:
        star_filter = st.radio('Star', ['Both stars'] + NRES_STARS, horizontal=True, key='nres_rv_plot_filter')
    with fc2:
        visible_lines = st.multiselect('Lines', all_lines_set, default=all_lines_set, key='nres_rv_line_filter')

    # ── Epoch-mean RV plot ────────────────────────────────────────────────
    fig_rv_date = go.Figure()
    for sn in analysis_data:
        if star_filter != 'Both stars' and sn != star_filter:
            continue
        for line_name, stats in analysis_data[sn].items():
            if line_name not in visible_lines:
                continue
            dates = _mjd_to_dates(stats['epoch_mjds'])
            fig_rv_date.add_trace(go.Scatter(
                x=dates,
                y=stats['epoch_means'],
                error_y=dict(type='data', array=stats['epoch_errs'], visible=True),
                mode='markers+lines',
                name=f'{sn} — {line_name}',
                marker=dict(size=8, color=color_map.get((sn, line_name), '#333')),
                customdata=stats['epoch_mjds'],
                hovertemplate='Date: %{x}<br>RV: %{y:.2f} km/s<br>MJD: %{customdata:.2f}<extra>%{fullData.name}</extra>',
                legendgroup=f'{sn}_{line_name}',
            ))
    apply_theme(fig_rv_date, title='Per-Epoch Weighted Mean RV vs Date',
                xaxis_title='Date', yaxis_title='RV (km/s)', height=450)
    st.plotly_chart(fig_rv_date, use_container_width=True)
    st.caption('Each point is the weighted mean RV of all spectra in that epoch. Error bars are the weighted error.')

    # ── All individual RVs scatter plot ───────────────────────────────────
    st.markdown('### All Individual RVs vs Date')
    fig_all_rv = go.Figure()
    for sn in analysis_rv_dfs:
        if star_filter != 'Both stars' and sn != star_filter:
            continue
        rv_df_sn = analysis_rv_dfs[sn]
        for line_name in rv_df_sn['Line'].unique():
            if line_name not in visible_lines:
                continue
            sub = rv_df_sn[rv_df_sn['Line'] == line_name].copy()
            sub = sub[sub['RV (km/s)'].apply(lambda v: np.isfinite(float(v)))]
            if len(sub) == 0:
                continue
            dates = _mjd_to_dates(sub['MJD'].values)
            fig_all_rv.add_trace(go.Scatter(
                x=dates,
                y=sub['RV (km/s)'].values.astype(float),
                error_y=dict(type='data', array=sub['RV_err (km/s)'].values.astype(float), visible=True),
                mode='markers',
                name=f'{sn} — {line_name}',
                marker=dict(size=6, color=color_map.get((sn, line_name), '#333'),
                            symbol='circle' if sn == NRES_STARS[0] else 'diamond'),
                customdata=sub['MJD'].values,
                hovertemplate='Date: %{x}<br>RV: %{y:.2f} km/s<br>MJD: %{customdata:.2f}<br>Ep%{text}<extra>%{fullData.name}</extra>',
                text=[f'{int(r["Epoch"])} Sp{int(r["Spectra"])}' for _, r in sub.iterrows()],
                legendgroup=f'{sn}_{line_name}',
            ))
    apply_theme(fig_all_rv, title='All Individual Spectrum RVs vs Date',
                xaxis_title='Date', yaxis_title='RV (km/s)', height=450)
    st.plotly_chart(fig_all_rv, use_container_width=True)
    st.caption('Every individual spectrum RV measurement. Different marker shapes per star (circle vs diamond).')

    # ── Combined summary with per-star breakdown ──────────────────────────
    st.divider()
    st.markdown('### Combined Estimate (Both Stars)')

    mean_within = np.mean(all_within) if all_within else 0
    mean_between = np.mean(all_between) if all_between else 0
    mean_overall = np.mean(all_overall) if all_overall else 0

    # Per-star sigma averages
    star_sigma_rows = []
    for sn in analysis_data:
        sn_within = [s['sigma_within'] for s in analysis_data[sn].values()]
        sn_between = [s['sigma_between'] for s in analysis_data[sn].values()]
        sn_overall = [s['sigma_overall'] for s in analysis_data[sn].values()]
        star_sigma_rows.append({
            'Source': sn,
            'σ_within (km/s)': round(np.mean(sn_within), 2) if sn_within else 0,
            'σ_between (km/s)': round(np.mean(sn_between), 2) if sn_between else 0,
            'σ_overall (km/s)': round(np.mean(sn_overall), 2) if sn_overall else 0,
            '4σ_overall (km/s)': round(4 * np.mean(sn_overall), 2) if sn_overall else 0,
        })

    star_sigma_rows.append({
        'Source': 'Combined (mean)',
        'σ_within (km/s)': round(mean_within, 2),
        'σ_between (km/s)': round(mean_between, 2),
        'σ_overall (km/s)': round(mean_overall, 2),
        '4σ_overall (km/s)': round(4 * mean_overall, 2),
    })

    sigma_table = pd.DataFrame(star_sigma_rows)
    st.dataframe(sigma_table, use_container_width=True, hide_index=True)

    st.caption(
        'σ_within: measurement precision (avg std within epochs). '
        'σ_between: short-term variability (std of epoch means). '
        'σ_overall: combined noise + variability (std of all individual RVs). '
        '**Binary criterion: ΔRV > 45.5 km/s AND ΔRV − 4σ > 0.** '
        f'Combined 4σ = {4 * mean_overall:.2f} km/s. '
        + ' '.join(f'{r["Source"]}: 4σ = {r["4σ_overall (km/s)"]} km/s.' for r in star_sigma_rows if r['Source'] != 'Combined (mean)')
    )

    # ── Impact plot ──────────────────────────────────────────────────────
    st.markdown('### Impact on Binary Classification')
    try:
        from pipeline.load_observations import load_observed_delta_rvs
        thresholds = np.arange(10, 100, 5)
        fractions = []
        for thresh in thresholds:
            test_settings = dict(settings)
            test_settings['classification'] = {
                'threshold_dRV': float(thresh),
                'sigma_factor': settings.get('classification', {}).get('sigma_factor', 4.0),
            }
            obs = get_obs_manager()
            delta_rvs, detail = load_observed_delta_rvs(test_settings, obs)
            bartzakos = settings.get('classification', {}).get('bartzakos_binaries', 3)
            total_pop = settings.get('classification', {}).get('total_population', 28)
            n_bin = sum(1 for d in detail.values() if d.get('is_binary'))
            fractions.append((n_bin + bartzakos) / total_pop if detail else 0)

        fig_impact = go.Figure()
        fig_impact.add_trace(go.Scatter(
            x=thresholds, y=fractions, mode='lines+markers', name='f_bin(observed)',
            line=dict(color=COLOR_BINARY),
        ))
        fig_impact.add_vline(x=45.5, line_dash='dash', line_color=COLOR_SINGLE,
                             annotation_text='ΔRV threshold (45.5)')
        fig_impact.add_vline(x=4 * mean_overall, line_dash='dot', line_color='#DAA520',
                             annotation_text=f'4σ ({4 * mean_overall:.1f})')
        apply_theme(fig_impact, title='Observed Binary Fraction vs ΔRV Threshold',
                    xaxis_title='ΔRV Threshold (km/s)',
                    yaxis_title='Observed Binary Fraction', height=400)
        st.plotly_chart(fig_impact, use_container_width=True)
    except Exception as e:
        st.warning(f'Could not compute impact analysis: {e}')
