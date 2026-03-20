"""plots/tab_emission_lines.py — Emission Lines sub-tab: table + per-line bar + wavelength scatter."""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from shared import (
    settings_hash, COLOR_BINARY, COLOR_SINGLE, ROOT,
)

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import specs  # noqa: E402

from plots.theme import _academic_fig, _show, _epoch_colors
from plots.data import _get_emission_lines
from plots.analysis import cached_load_drv_analysis, _is_significant_binary


def render_emission_lines_subtab(settings: dict):
    """Render the Emission Lines sub-tab."""
    st.markdown('### Emission Line dRV Table')
    sh = settings_hash(settings)
    try:
        df_el, drverr_el, _, el_lines = cached_load_drv_analysis(sh)
    except Exception as e:
        st.error(str(e))
        st.stop()

    cls_cfg = settings.get('classification', {})
    threshold = float(cls_cfg.get('threshold_dRV', 45.5))

    display_cols = ['Star', 'Clean']
    for lk in el_lines:
        cn = f'dRV | {lk}'
        if cn in df_el.columns:
            display_cols.append(cn)
    display_cols.extend(['Mean \u0394RV', 'Std \u0394RV'])

    df_display = df_el[display_cols].copy()
    for c in df_display.columns:
        if c not in ['Star', 'Clean', 'is_clean_bool']:
            df_display[c] = df_display[c].round(1)

    st.dataframe(df_display, width='stretch', height=600)
    st.caption('dRV (km/s) per star and emission line. Clean = check means no contamination.')

    # ── Per-Line dRV Comparison bar ───────────────────────────────────
    st.markdown('#### Per-Line dRV Comparison')
    el_star = st.selectbox('Star', specs.star_names, key='xsp_el_star')
    row_star = df_el[df_el['Star'] == el_star]
    if len(row_star) > 0:
        row_data = row_star.iloc[0]
        el_names = []
        el_drvs = []
        for lk in el_lines:
            cn = f'dRV | {lk}'
            if cn in row_data and pd.notna(row_data[cn]):
                el_names.append(lk)
                el_drvs.append(row_data[cn])

        if el_names:
            el_colors = [
                COLOR_BINARY if _is_significant_binary(el_star, lk, d, threshold, drverr_el)
                else COLOR_SINGLE
                for lk, d in zip(el_names, el_drvs)
            ]
            fig_elbar = _academic_fig(
                height=380, xaxis_title='Emission Line', yaxis_title='dRV (km/s)',
                title=dict(text=f'{el_star} -- dRV per Line'), xaxis_tickangle=-45,
            )
            fig_elbar.add_trace(go.Bar(x=el_names, y=el_drvs, marker_color=el_colors,
                                       showlegend=False))
            fig_elbar.add_hline(y=threshold, line_dash='dash', line_color='#DAA520',
                                annotation_text=f'{threshold:.1f} km/s')
            _show(fig_elbar,
                  f'Per-line dRV for {el_star}. Red = above threshold, blue = below.')
        else:
            st.info(f'No dRV data for {el_star}.')
    else:
        st.info(f'Star {el_star} not found in analysis.')

    # ── NEW: dRV vs Line Wavelength Scatter ───────────────────────────
    st.markdown('#### dRV vs Line Wavelength')
    emission_lines = _get_emission_lines()

    # Build central wavelength for each line (mean of range, in Angstrom)
    line_waves = {}
    for lk, rng in emission_lines.items():
        line_waves[lk] = (rng[0] + rng[1]) / 2.0 * 10.0  # nm -> Angstrom

    # Controls
    sc1, sc2 = st.columns([1, 1])
    scatter_log = sc1.checkbox('Log y-axis', value=True, key='xsp_el_scatter_log')
    scatter_thresh = sc2.number_input('Threshold (km/s)', value=threshold,
                                      step=1.0, key='xsp_el_scatter_thresh')

    # Collect per-star per-line dRV
    colors_scatter = _epoch_colors(len(specs.star_names))
    fig_scatter = _academic_fig(
        height=480,
        xaxis_title='Central wavelength (Ang.)',
        yaxis_title='dRV (km/s)',
        title=dict(text='dRV vs Line Wavelength (all stars)'),
    )
    if scatter_log:
        fig_scatter.update_layout(yaxis_type='log')

    for si, star_name in enumerate(specs.star_names):
        row_s = df_el[df_el['Star'] == star_name]
        if len(row_s) == 0:
            continue
        rd = row_s.iloc[0]
        xs_pts = []
        ys_pts = []
        for lk in el_lines:
            cn = f'dRV | {lk}'
            if lk in line_waves and cn in rd and pd.notna(rd[cn]) and np.isfinite(rd[cn]):
                xs_pts.append(line_waves[lk])
                ys_pts.append(rd[cn])
        if xs_pts:
            fig_scatter.add_trace(go.Scatter(
                x=xs_pts, y=ys_pts, mode='markers',
                marker=dict(size=6, color=colors_scatter[si], opacity=0.7),
                name=star_name,
            ))

    # Threshold line
    fig_scatter.add_hline(y=scatter_thresh, line_dash='dash', line_color='#DAA520',
                          annotation_text=f'{scatter_thresh:.1f} km/s')

    # Annotate binary fraction above each line column
    for lk in el_lines:
        if lk not in line_waves:
            continue
        cn = f'dRV | {lk}'
        if cn not in df_el.columns:
            continue
        vals = df_el[cn].dropna()
        n_total = len(vals)
        if n_total == 0:
            continue
        n_above = 0
        for _, row in df_el.iterrows():
            dv = row.get(cn)
            if pd.notna(dv) and np.isfinite(dv):
                if _is_significant_binary(row['Star'], lk, dv, scatter_thresh, drverr_el):
                    n_above += 1
        frac_pct = 100.0 * n_above / n_total
        fig_scatter.add_annotation(
            x=line_waves[lk], y=1.02, yref='paper',
            text=f'{frac_pct:.0f}%', showarrow=False,
            font=dict(size=8, color='black'),
        )

    _show(fig_scatter,
          'Each point is one star. X = central wavelength of the emission line. '
          'Percentages above show binary fraction at that line.')
