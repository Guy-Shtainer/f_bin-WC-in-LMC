"""
pages/06_plots.py — Visualization Gallery
Tabbed: Spectra | RV Analysis | Orbital | CCF output
"""
from __future__ import annotations
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from shared import (
    inject_theme, render_sidebar, get_settings_manager,
    cached_load_observed_delta_rvs, settings_hash,
    get_obs_manager, COLOR_BINARY, COLOR_SINGLE,
)
import specs

st.set_page_config(page_title='Plots — WR Binary', page_icon='🖼️', layout='wide')
inject_theme()
settings = render_sidebar('Plots')
sm = get_settings_manager()

st.markdown('# 🖼️ Visualization Gallery')

tab_spec, tab_rv, tab_ccf, tab_orbital = st.tabs(
    ['Spectra', 'RV Analysis', 'CCF outputs', 'Orbital / Simulation']
)

# ─────────────────────────────────────────────────────────────────────────────
# Spectra tab
# ─────────────────────────────────────────────────────────────────────────────
with tab_spec:
    st.markdown('### Normalized spectra')
    ui_cfg = settings.get('ui', {})
    star_names = specs.star_names
    default_st = ui_cfg.get('last_star', star_names[0])
    if default_st not in star_names:
        default_st = star_names[0]

    star_name = st.selectbox('Star', star_names,
        index=star_names.index(default_st), key='plots_spec_star')
    BANDS = ['COMBINED', 'UVB', 'VIS', 'NIR']
    band  = st.selectbox('Band', BANDS, key='plots_spec_band')

    obs  = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    epochs = star.get_all_epoch_numbers()

    @st.cache_data
    def _load_spec(sn, ep, bd):
        o  = get_obs_manager()
        s  = o.load_star_instance(sn, to_print=False)
        d  = s.load_property('normalized_flux', ep, bd)
        if d is None:
            d = s.load_property('cleaned_normalized_flux', ep, bd)
        return d

    fig = go.Figure()
    colormap = [f'hsl({int(i*360/max(len(epochs),1))},80%,60%)' for i in range(len(epochs))]
    for i, ep in enumerate(epochs):
        data = _load_spec(star_name, ep, band)
        if data is None:
            continue
        wave = np.asarray(data.get('wavelengths', data.get('wave', [])))
        flux = np.asarray(data.get('normalized_flux', data.get('flux', [])))
        if len(wave) > 0:
            fig.add_trace(go.Scatter(x=wave, y=flux, mode='lines',
                                     line=dict(color=colormap[i], width=1),
                                     name=f'Ep {ep}'))
    fig.update_layout(
        xaxis_title='Wavelength (Å)', yaxis_title='Normalised flux',
        title=f'{star_name} — {band} — all epochs',
        plot_bgcolor='#1a1a2e', paper_bgcolor='#1a1a2e',
        font_color='#e0e0e0', height=480,
    )
    st.plotly_chart(fig, use_container_width=True)

    save_col, _ = st.columns([1, 3])
    if save_col.button('💾 Save to plots/', key='save_spec_plot'):
        os.makedirs(os.path.join(_ROOT, 'plots'), exist_ok=True)
        import plotly.io as pio
        path = os.path.join(_ROOT, 'plots', f'{star_name.replace(" ","_")}_{band}_spectra.png')
        pio.write_image(fig, path, scale=2)
        st.success(f'Saved: {path}')

# ─────────────────────────────────────────────────────────────────────────────
# RV Analysis tab
# ─────────────────────────────────────────────────────────────────────────────
with tab_rv:
    st.markdown('### RV vs epoch')
    sh = settings_hash(settings)
    with st.spinner('Loading RVs …'):
        try:
            obs_delta_rv, detail = cached_load_observed_delta_rvs(sh)
        except Exception as e:
            st.error(str(e))
            st.stop()

    star_rv = st.selectbox('Star', specs.star_names, key='plots_rv_star')
    rv_arr  = detail.get(star_rv, {}).get('rv', np.array([]))
    err_arr = detail.get(star_rv, {}).get('rv_err', np.array([]))

    fig2 = go.Figure()
    if len(rv_arr) > 0:
        fig2.add_trace(go.Scatter(
            x=list(range(1, len(rv_arr)+1)), y=rv_arr,
            error_y=dict(type='data', array=err_arr, visible=True),
            mode='markers+lines',
            marker=dict(size=8, color=COLOR_BINARY
                        if detail.get(star_rv, {}).get('is_binary') else COLOR_SINGLE),
            name='RV (C IV 5808-5812)',
        ))
    fig2.update_layout(
        xaxis_title='Observation #', yaxis_title='RV (km/s)',
        title=f'{star_rv} — RV per epoch',
        plot_bgcolor='#1a1a2e', paper_bgcolor='#1a1a2e',
        font_color='#e0e0e0', height=380,
    )
    st.plotly_chart(fig2, use_container_width=True)

    st.markdown('### ΔRV bar chart (all stars)')
    cls_cfg   = settings.get('classification', {})
    threshold = cls_cfg.get('threshold_dRV', 45.5)
    valid = [(sn, float(detail[sn]['best_dRV'])) for sn in specs.star_names
             if sn in detail and detail[sn]['best_dRV'] > 0]
    if valid:
        names = [v[0] for v in valid]
        drvs  = [v[1] for v in valid]
        colors = [COLOR_BINARY if d > threshold else COLOR_SINGLE for d in drvs]
        fig3 = go.Figure(go.Bar(x=names, y=drvs, marker_color=colors))
        fig3.add_hline(y=threshold, line_dash='dash', line_color='gold',
                       annotation_text=f'{threshold:.1f} km/s')
        fig3.update_layout(
            xaxis_title='Star', yaxis_title='ΔRV (km/s)',
            xaxis_tickangle=-45,
            plot_bgcolor='#1a1a2e', paper_bgcolor='#1a1a2e',
            font_color='#e0e0e0', height=380,
        )
        st.plotly_chart(fig3, use_container_width=True)

# ─────────────────────────────────────────────────────────────────────────────
# CCF output plots tab
# ─────────────────────────────────────────────────────────────────────────────
with tab_ccf:
    output_root = os.path.normpath(os.path.join(_ROOT, '..', 'output'))
    st.markdown(f'### CCF plots from `{output_root}`')
    if not os.path.isdir(output_root):
        st.info('Output directory not found.')
    else:
        star_f  = st.selectbox('Filter by star', ['All'] + specs.star_names, key='plots_ccf_star')
        pngs = []
        for star_name in specs.star_names:
            d = os.path.join(output_root, star_name, 'CCF')
            if os.path.isdir(d):
                for dp, _, fns in os.walk(d):
                    for fn in fns:
                        if fn.lower().endswith('.png'):
                            pngs.append(os.path.join(dp, fn))
        if star_f != 'All':
            pngs = [p for p in pngs if star_f in p]
        st.write(f'{len(pngs)} CCF plot(s) found.')
        cols = st.columns(3)
        for i, p in enumerate(pngs[:12]):
            cols[i % 3].image(p, caption=os.path.basename(p), use_column_width=True)
        if len(pngs) > 12:
            st.info(f'Showing first 12 of {len(pngs)}.')

# ─────────────────────────────────────────────────────────────────────────────
# Orbital / Simulation tab
# ─────────────────────────────────────────────────────────────────────────────
with tab_orbital:
    result_path = os.path.join(_ROOT, 'results', 'dsilva_result.npz')
    if not os.path.exists(result_path):
        st.info('No grid result found. Run the Dsilva grid first (Grid Search page).')
    else:
        result = dict(np.load(result_path, allow_pickle=True))
        fbin_grid = np.asarray(result['fbin_grid'])
        pi_grid   = np.asarray(result['pi_grid'])
        ks_p = np.squeeze(np.asarray(result['ks_p']), axis=0)
        ks_D = np.squeeze(np.asarray(result['ks_D']), axis=0)

        # Heatmap
        fig_h = go.Figure(go.Heatmap(
            z=ks_p, x=pi_grid, y=fbin_grid, colorscale='RdBu_r',
            colorbar=dict(title='K-S p-value'),
            hovertemplate='π=%{x:.2f}<br>f_bin=%{y:.3f}<br>p=%{z:.4f}<extra></extra>',
        ))
        best_flat = int(np.argmax(ks_p))
        bfi = best_flat // ks_p.shape[1]
        bpi = best_flat  % ks_p.shape[1]
        fig_h.add_trace(go.Scatter(
            x=[pi_grid[bpi]], y=[fbin_grid[bfi]],
            mode='markers', marker=dict(symbol='star', size=14, color='gold'),
            name=f'Best: f_bin={fbin_grid[bfi]:.3f}, π={pi_grid[bpi]:.2f}',
        ))
        fig_h.update_layout(
            title='Dsilva grid — K-S p-value heatmap',
            xaxis_title='π', yaxis_title='f_bin',
            plot_bgcolor='#1a1a2e', paper_bgcolor='#1a1a2e',
            font_color='#e0e0e0', height=480,
        )
        st.plotly_chart(fig_h, use_container_width=True)

        # f_bin slice at best π
        st.markdown('### p-value vs f_bin at best π')
        fig_s = go.Figure(go.Scatter(x=fbin_grid, y=ks_p[:, bpi], mode='lines',
                                     line=dict(color='#4A90D9', width=2)))
        fig_s.add_vline(x=fbin_grid[bfi], line_dash='dash', line_color='gold')
        fig_s.update_layout(
            xaxis_title='f_bin', yaxis_title='K-S p-value',
            yaxis_type='log',
            plot_bgcolor='#1a1a2e', paper_bgcolor='#1a1a2e',
            font_color='#e0e0e0', height=350,
        )
        st.plotly_chart(fig_s, use_container_width=True)

        save_col2, _ = st.columns([1, 3])
        if save_col2.button('💾 Save heatmap to plots/', key='save_heatmap'):
            import plotly.io as pio
            os.makedirs(os.path.join(_ROOT, 'plots'), exist_ok=True)
            path = os.path.join(_ROOT, 'plots', 'dsilva_ks_pvalue_interactive.png')
            pio.write_image(fig_h, path, scale=2)
            st.success(f'Saved: {path}')
