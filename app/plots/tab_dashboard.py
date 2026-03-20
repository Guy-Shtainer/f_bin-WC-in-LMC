"""plots/tab_dashboard.py — Interactive Dashboard sub-tab: dRV table + epoch RV heatmap."""
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
from plots.analysis import cached_load_drv_analysis, _is_significant_binary


def render_dashboard_subtab(settings: dict):
    """Render the Interactive Dashboard sub-tab."""
    st.markdown('### Interactive Dashboard')

    sh = settings_hash(settings)
    cls_cfg = settings.get('classification', {})

    try:
        df_analysis, drverr_map, rv_epoch_cache, ordered_lines = \
            cached_load_drv_analysis(sh)
    except Exception as e:
        st.error(str(e))
        st.stop()

    threshold = float(cls_cfg.get('threshold_dRV', 45.5))

    # ── Controls ──────────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    sort_line_options = ordered_lines
    sort_line = c1.selectbox('Sort by line', sort_line_options, key='xsp_dash_sort_line')
    sort_order = c2.radio('Order', ['Descending', 'Ascending'],
                           horizontal=True, key='xsp_dash_sort_order')
    color_mode = c3.radio('Cell coloring', ['Gradient', 'Binary/Single'],
                           horizontal=True, key='xsp_dash_color_mode')

    sort_col = f'dRV | {sort_line}'
    ascending = sort_order == 'Ascending'

    # Sort dataframe
    if sort_col in df_analysis.columns:
        df_sorted = df_analysis.sort_values(sort_col, ascending=ascending,
                                            na_position='last').reset_index(drop=True)
    else:
        df_sorted = df_analysis.copy()

    star_order = df_sorted['Star'].tolist()

    # ── dRV Heatmap (stars x lines) ──────────────────────────────────
    st.markdown('#### dRV Heatmap (Stars x Emission Lines)')
    drv_matrix = []
    hover_matrix = []
    for star_name in star_order:
        row_vals = []
        hover_vals = []
        for lk in ordered_lines:
            cn = f'dRV | {lk}'
            row_star = df_sorted[df_sorted['Star'] == star_name]
            if len(row_star) > 0 and cn in row_star.columns:
                val = row_star.iloc[0][cn]
                if pd.notna(val) and np.isfinite(val):
                    row_vals.append(float(val))
                    is_bin = _is_significant_binary(star_name, lk, val, threshold, drverr_map)
                    hover_vals.append(
                        f'{star_name}<br>{lk}<br>dRV={val:.1f} km/s<br>'
                        f'{"Binary" if is_bin else "Single"}'
                    )
                else:
                    row_vals.append(float('nan'))
                    hover_vals.append(f'{star_name}<br>{lk}<br>No data')
            else:
                row_vals.append(float('nan'))
                hover_vals.append(f'{star_name}<br>{lk}<br>No data')
        drv_matrix.append(row_vals)
        hover_matrix.append(hover_vals)

    z_arr = np.array(drv_matrix)

    if color_mode == 'Binary/Single':
        # Create binary mask: 1 = binary, 0 = single, NaN = no data
        z_binary = np.full_like(z_arr, np.nan)
        for si, star_name in enumerate(star_order):
            for li, lk in enumerate(ordered_lines):
                val = z_arr[si, li]
                if np.isfinite(val):
                    is_bin = _is_significant_binary(star_name, lk, val, threshold, drverr_map)
                    z_binary[si, li] = 1.0 if is_bin else 0.0
        colorscale = [[0, COLOR_SINGLE], [1, COLOR_BINARY]]
        z_plot = z_binary
        zmin_val, zmax_val = 0, 1
    else:
        colorscale = 'RdBu_r'
        z_plot = z_arr
        finite_vals = z_arr[np.isfinite(z_arr)]
        if len(finite_vals) > 0:
            zmin_val = float(np.nanpercentile(finite_vals, 5))
            zmax_val = float(np.nanpercentile(finite_vals, 95))
        else:
            zmin_val, zmax_val = 0, 100

    fig_hm = _academic_fig(
        height=max(400, 18 * len(star_order)),
        xaxis_title='Emission Line',
        yaxis_title='Star',
        title=dict(text='dRV Heatmap'),
    )
    fig_hm.add_trace(go.Heatmap(
        z=z_plot, x=ordered_lines, y=star_order,
        colorscale=colorscale, zmin=zmin_val, zmax=zmax_val,
        hovertext=hover_matrix, hoverinfo='text',
        colorbar=dict(title='dRV (km/s)' if color_mode == 'Gradient' else 'Binary'),
    ))
    fig_hm.update_xaxes(tickangle=-45)
    _show(fig_hm,
          f'Stars sorted by {sort_line} ({sort_order.lower()}). '
          f'{"Gradient: dRV magnitude" if color_mode == "Gradient" else "Red=binary, blue=single"}.')

    # ── Per-epoch RV heatmap (stars x epochs) ─────────────────────────
    st.markdown('#### Per-Epoch RV Strip')
    ep_line = st.selectbox('Emission line for epoch view', ordered_lines,
                            key='xsp_dash_ep_line')

    # Build epoch-RV matrix
    all_epochs_set = set()
    for star_name in star_order:
        rv_list = rv_epoch_cache.get((star_name, ep_line), [])
        for ep, rv_val, rv_err in rv_list:
            all_epochs_set.add(ep)

    if all_epochs_set:
        all_epochs = sorted(all_epochs_set)
        rv_matrix = np.full((len(star_order), len(all_epochs)), np.nan)
        hover_ep = [['' for _ in all_epochs] for _ in star_order]

        for si, star_name in enumerate(star_order):
            rv_list = rv_epoch_cache.get((star_name, ep_line), [])
            for ep, rv_val, rv_err in rv_list:
                if ep in all_epochs:
                    ei = all_epochs.index(ep)
                    rv_matrix[si, ei] = rv_val
                    err_text = f' +/- {rv_err:.1f}' if np.isfinite(rv_err) else ''
                    hover_ep[si][ei] = (
                        f'{star_name}<br>Epoch {ep}<br>RV={rv_val:.1f}{err_text} km/s'
                    )

        fig_ep = _academic_fig(
            height=max(400, 18 * len(star_order)),
            xaxis_title='Epoch',
            yaxis_title='Star',
            title=dict(text=f'RV per Epoch ({ep_line})'),
        )
        fig_ep.add_trace(go.Heatmap(
            z=rv_matrix,
            x=[str(e) for e in all_epochs],
            y=star_order,
            colorscale='RdBu_r',
            hovertext=hover_ep, hoverinfo='text',
            colorbar=dict(title='RV (km/s)'),
        ))
        _show(fig_ep,
              f'Per-epoch radial velocity for {ep_line}. '
              'Diverging colorscale centered on mean RV.')
    else:
        st.info(f'No epoch data available for {ep_line}.')
