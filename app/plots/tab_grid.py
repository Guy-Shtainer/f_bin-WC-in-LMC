"""plots/tab_grid.py — Grid Results sub-tab: heatmap + p-value slice."""
from __future__ import annotations

import os
import sys

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from shared import (
    COLOR_SINGLE, ROOT,
    make_heatmap_fig, cached_load_grid_result, find_best_grid_point,
)

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from plots.theme import _academic_fig, _show  # noqa: E402


def render_grid_subtab():
    """Render the Grid Results sub-tab."""
    st.markdown('### Grid Search Results')
    model_sel = st.radio('Model', ['Dsilva', 'Langer'], horizontal=True,
                         key='xsp_grid_model')
    model_key = model_sel.lower()

    result = st.session_state.get(f'result_{model_key}')
    if result is None:
        result = cached_load_grid_result(model_key)
    if result is None:
        results_dir = os.path.join(ROOT, 'results')
        if os.path.isdir(results_dir):
            npz_files = [f for f in os.listdir(results_dir)
                         if f.endswith('.npz') and model_key in f.lower()]
            if npz_files:
                chosen_file = st.selectbox('Result file', npz_files, key='xsp_grid_file')
                result = cached_load_grid_result(
                    model_key, os.path.join(results_dir, chosen_file))

    if result is not None:
        try:
            fbin_grid = np.asarray(result['fbin_grid'])
            ks_p = np.asarray(result['ks_p'])
            if ks_p.ndim == 3:
                ks_p = np.squeeze(ks_p, axis=0)
            ks_d = np.asarray(result.get('ks_D', np.zeros_like(ks_p)))
            if ks_d.ndim == 3:
                ks_d = np.squeeze(ks_d, axis=0)

            if model_key == 'langer':
                x_grid_key = 'sigma_grid'
                x_label = 'sigma (velocity dispersion km/s)'
                x_name = 'sigma'
            else:
                x_grid_key = 'pi_grid'
                x_label = 'pi (period power-law index)'
                x_name = 'pi'

            x_grid = np.asarray(result.get(x_grid_key, result.get('pi_grid', [])))

            show_d = st.checkbox('Show K-S D statistic', value=False, key='xsp_grid_show_d')

            fig_hm = make_heatmap_fig(
                ks_p, fbin_grid, x_grid,
                title=f'{model_sel} -- K-S p-value heatmap',
                show_d=show_d, ks_d_2d=ks_d,
                x_label=x_label, x_name=x_name, height=520,
            )
            st.plotly_chart(fig_hm, width='stretch', theme=None)
            st.caption(f'{model_sel} grid search result.')

            # p-value slice
            best_fbin, best_x, best_pval = find_best_grid_point(ks_p, fbin_grid, x_grid)
            bpi = int(np.argmin(np.abs(x_grid - best_x)))

            st.markdown(f'### p-value vs f_bin at best {x_name}={best_x:.3f}')
            fig_slice = _academic_fig(
                height=350, xaxis_title='f_bin', yaxis_title='K-S p-value',
                title=dict(text=f'p-value slice at {x_name}={best_x:.3f}'),
                yaxis_type='log',
            )
            fig_slice.add_trace(go.Scatter(
                x=fbin_grid, y=ks_p[:, bpi], mode='lines',
                line=dict(color=COLOR_SINGLE, width=2), showlegend=False,
            ))
            fig_slice.add_vline(x=best_fbin, line_dash='dash', line_color='#DAA520')
            _show(fig_slice,
                  f'Best fit: f_bin={best_fbin:.3f}, {x_name}={best_x:.3f}, p={best_pval:.4f}')

            if st.button('Save heatmap to plots/', key='save_grid_heatmap'):
                import plotly.io as pio
                os.makedirs(os.path.join(ROOT, 'plots'), exist_ok=True)
                path = os.path.join(ROOT, 'plots',
                                    f'{model_key}_ks_pvalue_interactive.png')
                pio.write_image(fig_hm, path, scale=2)
                st.success(f'Saved: {path}')
        except Exception as e:
            st.error(f'Error displaying grid result: {e}')
    else:
        st.info(f'No {model_sel} grid result found. Run the grid search first.')
