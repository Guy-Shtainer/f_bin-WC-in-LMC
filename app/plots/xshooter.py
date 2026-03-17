"""plots/xshooter.py — X-Shooter tab: Spectra, RV Analysis, Emission Lines, CCF, Grid Results."""
from __future__ import annotations

import os
import re
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from shared import (
    cached_load_observed_delta_rvs, settings_hash, get_obs_manager,
    COLOR_BINARY, COLOR_SINGLE,
    make_heatmap_fig, cached_load_grid_result, find_best_grid_point,
    ROOT,
)

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import specs  # noqa: E402

from plots.theme import _academic_fig, _show, _epoch_colors, _add_emission_bands
from plots.data import (
    BANDS, _get_emission_lines, _get_star_config, _get_epochs,
    _load_spectrum, _load_raw_spec, _load_continuum, _load_rv_property, _extract_rv,
)
from plots.analysis import cached_load_drv_analysis, _is_significant_binary


def render_xshooter_tab(settings: dict, sm):
    """Render all X-Shooter sub-tabs."""
    xs_sub = st.tabs(['Spectra', 'RV Analysis', 'Emission Lines', 'CCF Outputs', 'Grid Results'])

    use_cleaned = True  # default; overridden inside Spectra tab

    # ─── X-Shooter > Spectra ─────────────────────────────────────────────
    with xs_sub[0]:
        st.markdown('### Spectra Viewer')

        # ── Normalized spectra overlay ────────────────────────────────────
        st.markdown('#### Normalized Spectra (all epochs)')
        c1, c2, c3 = st.columns([2, 1, 2])
        xs_star = c1.selectbox('Star', specs.star_names, key='xsp_star')
        xs_band = c2.selectbox('Band', BANDS, key='xsp_band')
        use_cleaned = c3.checkbox('Use cleaned spectra', value=True, key='xsp_clean')

        col_t1, col_t2 = st.columns(2)
        show_lines = col_t1.checkbox('Show emission line bands', value=False, key='xsp_lines')
        xs_log = col_t2.checkbox('Log y-scale', value=False, key='xsp_log')

        epochs = _get_epochs(xs_star)
        fig_norm = _academic_fig(
            height=480,
            xaxis_title='Wavelength (Å)',
            yaxis_title='Normalised flux',
            title=dict(text=f'{xs_star} — {xs_band} — all epochs'),
        )
        if xs_log:
            fig_norm.update_layout(yaxis_type='log')

        colors = _epoch_colors(len(epochs))
        has_raw = False
        for i, ep in enumerate(epochs):
            wave_A, flux, src = _load_spectrum(xs_star, ep, xs_band, use_cleaned)
            if wave_A is None:
                continue
            if src == 'raw':
                has_raw = True
            fig_norm.add_trace(go.Scattergl(
                x=wave_A, y=flux, mode='lines',
                line=dict(color=colors[i], width=1.2),
                name=f'Epoch {ep}' + (' (raw)' if src == 'raw' else ''),
            ))

        if show_lines:
            _add_emission_bands(fig_norm, _get_emission_lines())

        caption = 'Normalized spectra overlaid for all available epochs.'
        if has_raw:
            caption += ' Some epochs show raw (unnormalized) FITS data.'
        _show(fig_norm, caption)

        # Save button
        sv1, _ = st.columns([1, 3])
        if sv1.button('💾 Save to plots/', key='save_spec_plot'):
            import plotly.io as pio
            os.makedirs(os.path.join(ROOT, 'plots'), exist_ok=True)
            path = os.path.join(ROOT, 'plots',
                                f'{xs_star.replace(" ", "_")}_{xs_band}_spectra.png')
            pio.write_image(fig_norm, path, scale=2)
            fig_norm.write_html(path.replace('.png', '.html'))
            st.success(f'Saved: {path} (+ HTML)')

        # ── Raw spectrum viewer ───────────────────────────────────────────
        with st.expander('Raw Spectrum Viewer', expanded=False):
            c1r, c2r, c3r = st.columns(3)
            raw_star = c1r.selectbox('Star', specs.star_names, key='xsp_raw_star')
            raw_band = c2r.selectbox('Band', BANDS, key='xsp_raw_band')
            raw_epochs = _get_epochs(raw_star)
            ep_raw = c3r.selectbox('Epoch', raw_epochs, key='xsp_raw_ep')

            cr1, cr2, cr3 = st.columns(3)
            raw_log = cr1.checkbox('Log scale', value=False, key='xsp_raw_log')
            raw_cont = cr2.checkbox('Show continuum', value=False, key='xsp_raw_cont')
            raw_lines_chk = cr3.checkbox('Show emission lines', value=False, key='xsp_raw_lines')

            raw_data = _load_raw_spec(raw_star, ep_raw, raw_band)
            if raw_data is not None:
                wave_A, flux, err = raw_data
                fig_raw = _academic_fig(
                    height=420,
                    xaxis_title='Wavelength (Å)', yaxis_title='Flux',
                    title=dict(text=f'{raw_star} — {raw_band} — Epoch {ep_raw} (raw)'),
                )
                if raw_log:
                    fig_raw.update_layout(yaxis_type='log')

                plot_flux = flux.copy()
                if raw_log:
                    plot_flux = np.where(plot_flux > 0, plot_flux, np.nan)

                fig_raw.add_trace(go.Scattergl(
                    x=wave_A, y=plot_flux, mode='lines',
                    line=dict(color=COLOR_SINGLE, width=1),
                    name=f'Epoch {ep_raw}',
                ))

                if raw_cont:
                    cont_data = _load_continuum(raw_star, ep_raw, raw_band)
                    if cont_data is not None:
                        cont_flux = np.asarray(
                            cont_data.get('interpolated_flux', cont_data)
                            if isinstance(cont_data, dict) else cont_data
                        )
                        if cont_flux.ndim > 0 and len(cont_flux) == len(wave_A):
                            fig_raw.add_trace(go.Scattergl(
                                x=wave_A, y=cont_flux, mode='lines',
                                line=dict(color='#DAA520', width=1.5, dash='dash'),
                                name='Continuum',
                            ))

                if raw_lines_chk:
                    _add_emission_bands(fig_raw, _get_emission_lines())

                _show(fig_raw, 'Raw FITS spectrum (wavelengths converted from nm to Å).')
            else:
                st.info('No raw data available for this star/epoch/band.')

        # ── Error spectrum viewer ─────────────────────────────────────────
        with st.expander('Error Spectrum', expanded=False):
            c1e, c2e, c3e = st.columns(3)
            err_star = c1e.selectbox('Star', specs.star_names, key='xsp_err_star')
            err_band = c2e.selectbox('Band', BANDS, key='xsp_err_band')
            err_epochs = _get_epochs(err_star)
            ep_err = c3e.selectbox('Epoch', err_epochs, key='xsp_err_ep')

            raw_err_data = _load_raw_spec(err_star, ep_err, err_band)
            if raw_err_data is not None and raw_err_data[2] is not None:
                wave_A, _, err_arr = raw_err_data
                fig_err = _academic_fig(
                    height=350,
                    xaxis_title='Wavelength (Å)', yaxis_title='Error',
                    title=dict(text=f'{err_star} — {err_band} — Epoch {ep_err} (error)'),
                )
                fig_err.add_trace(go.Scattergl(
                    x=wave_A, y=err_arr, mode='lines',
                    line=dict(color='#E25A53', width=1), name='Error',
                ))
                _show(fig_err, 'Error spectrum from FITS ERR extension.')
            else:
                st.info('No error data available for this epoch.')

        # ── 2D Spectral Image ─────────────────────────────────────────────
        with st.expander('2D Spectral Image', expanded=False):
            c1d, c2d, c3d = st.columns(3)
            img_star = c1d.selectbox('Star', specs.star_names, key='xsp_2d_star')
            img_band = c2d.selectbox('Band', ['UVB', 'VIS', 'NIR'], key='xsp_2d_band')
            img_epochs = _get_epochs(img_star)
            ep_2d = c3d.selectbox('Epoch', img_epochs, key='xsp_2d_ep')

            try:
                obs_2d = get_obs_manager()
                star_2d = obs_2d.load_star_instance(img_star, to_print=False)
                # Load 1D FITS for wavelength axis (IC2D.py pattern)
                fit_1d = star_2d.load_observation(ep_2d, img_band)
                fit_2d = star_2d.load_2D_observation(ep_2d, img_band)
                if fit_2d is not None and fit_2d.primary_data is not None:
                    img = fit_2d.primary_data
                    wave_2d = (np.asarray(fit_1d.data['WAVE'][0]) * 10.0
                               if fit_1d is not None else None)

                    cv1, cv2 = st.columns(2)
                    vmin = cv1.number_input('ValMin', value=float(np.nanpercentile(img, 5)),
                                            key='xsp_2d_vmin')
                    vmax = cv2.number_input('ValMax', value=float(np.nanpercentile(img, 95)),
                                            key='xsp_2d_vmax')

                    fig_2d = _academic_fig(
                        height=400,
                        xaxis_title='Wavelength (Å)', yaxis_title='Spatial pixel',
                        title=dict(text=f'{img_star} — {img_band} — Epoch {ep_2d} (2D)'),
                    )
                    fig_2d.add_trace(go.Heatmap(
                        z=img, x=wave_2d, colorscale='Viridis',
                        zmin=vmin, zmax=vmax,
                        colorbar=dict(title='Counts'),
                    ))
                    _show(fig_2d, '2D spectral image from FITS primary extension.')
                else:
                    st.info('No 2D data available for this epoch/band.')
            except Exception as e:
                st.info(f'Could not load 2D image: {e}')

        # ── Epoch Consistency Check ───────────────────────────────────────
        with st.expander('Epoch Consistency Check', expanded=False):
            c1c, c2c = st.columns(2)
            cons_star = c1c.selectbox('Star', specs.star_names, key='xsp_cons_star')
            cons_band = c2c.selectbox('Band', BANDS, key='xsp_cons_band')
            cons_epochs = _get_epochs(cons_star)

            if len(cons_epochs) >= 2:
                ce1, ce2 = st.columns(2)
                ep1 = ce1.selectbox('Epoch A', cons_epochs, index=0, key='xsp_cons_ep1')
                ep2 = ce2.selectbox('Epoch B', cons_epochs,
                                    index=min(1, len(cons_epochs) - 1), key='xsp_cons_ep2')
                cw1, cw2 = st.columns(2)
                wmin = cw1.number_input('λ min (Å)', value=5750, key='xsp_cons_wmin')
                wmax = cw2.number_input('λ max (Å)', value=5950, key='xsp_cons_wmax')

                w1, f1, _ = _load_spectrum(cons_star, ep1, cons_band, use_cleaned)
                w2, f2, _ = _load_spectrum(cons_star, ep2, cons_band, use_cleaned)
                if w1 is not None and w2 is not None:

                    mask1 = (w1 >= wmin) & (w1 <= wmax)
                    mask2 = (w2 >= wmin) & (w2 <= wmax)

                    if np.any(mask1) and np.any(mask2):
                        from scipy.interpolate import interp1d
                        f2_interp = interp1d(w2[mask2], f2[mask2], kind='linear',
                                             bounds_error=False, fill_value=np.nan)
                        f2_on_w1 = f2_interp(w1[mask1])
                        valid = np.isfinite(f2_on_w1) & np.isfinite(f1[mask1])

                        fig_cons = _academic_fig(
                            height=450,
                            xaxis_title=f'Flux (Epoch {ep1})',
                            yaxis_title=f'Flux (Epoch {ep2})',
                            title=dict(text=f'Epoch {ep1} vs {ep2} ({wmin}–{wmax} Å)'),
                        )
                        fig_cons.add_trace(go.Scatter(
                            x=f1[mask1][valid], y=f2_on_w1[valid],
                            mode='markers', marker=dict(size=3, color=COLOR_SINGLE, opacity=0.5),
                            name='Flux comparison',
                        ))
                        fmin_v = min(f1[mask1][valid].min(), f2_on_w1[valid].min())
                        fmax_v = max(f1[mask1][valid].max(), f2_on_w1[valid].max())
                        fig_cons.add_trace(go.Scatter(
                            x=[fmin_v, fmax_v], y=[fmin_v, fmax_v], mode='lines',
                            line=dict(color='#DAA520', dash='dash', width=1),
                            name='1:1',
                        ))
                        _show(fig_cons, 'Flux comparison between two epochs in a wavelength window.')
                    else:
                        st.warning('No data in the selected wavelength window.')
                else:
                    st.info('Normalized spectra not available for one of the selected epochs.')
            else:
                st.info('Need at least 2 epochs for consistency check.')

        # ── Extreme RV Comparison ─────────────────────────────────────────
        with st.expander('Extreme RV Comparison', expanded=False):
            c1x, c2x = st.columns(2)
            ext_star = c1x.selectbox('Star', specs.star_names, key='xsp_ext_star')
            ext_band = c2x.selectbox('Band', BANDS, key='xsp_ext_band')
            primary_line = settings.get('primary_line', 'C IV 5808-5812')

            ext_epochs = _get_epochs(ext_star)
            rv_by_ep = {}
            for ep in ext_epochs:
                rv_prop = _load_rv_property(ext_star, ep)
                if rv_prop is None or primary_line not in rv_prop:
                    continue
                rv_val, _ = _extract_rv(rv_prop[primary_line])
                if rv_val is not None and rv_val != 0.0:
                    rv_by_ep[ep] = rv_val

            if len(rv_by_ep) >= 2:
                ep_min = min(rv_by_ep, key=rv_by_ep.get)
                ep_max = max(rv_by_ep, key=rv_by_ep.get)

                w_min, f_min, _ = _load_spectrum(ext_star, ep_min, ext_band, use_cleaned)
                w_max, f_max, _ = _load_spectrum(ext_star, ep_max, ext_band, use_cleaned)

                if w_min is not None and w_max is not None:
                    fig_ext = _academic_fig(
                        height=450,
                        xaxis_title='Wavelength (Å)', yaxis_title='Normalised flux',
                        title=dict(text=f'{ext_star} — Extreme RV epochs'),
                    )

                    fig_ext.add_trace(go.Scattergl(
                        x=w_min, y=f_min, mode='lines',
                        line=dict(color=COLOR_SINGLE, width=1),
                        name=f'Ep {ep_min} (min RV={rv_by_ep[ep_min]:.1f} km/s)',
                    ))
                    fig_ext.add_trace(go.Scattergl(
                        x=w_max, y=f_max, mode='lines',
                        line=dict(color=COLOR_BINARY, width=1),
                        name=f'Ep {ep_max} (max RV={rv_by_ep[ep_max]:.1f} km/s)',
                    ))

                    el_dict = _get_emission_lines()
                    if primary_line in el_dict:
                        rng = el_dict[primary_line]
                        fig_ext.add_vrect(
                            x0=rng[0] * 10, x1=rng[1] * 10,
                            fillcolor='rgba(218,165,32,0.12)', line_width=0,
                            annotation_text=primary_line,
                            annotation_position='top left',
                            annotation_font=dict(size=8, color='#333'),
                        )

                    _show(fig_ext,
                          f'Min-RV epoch {ep_min} vs Max-RV epoch {ep_max} '
                          f'(ΔRV = {abs(rv_by_ep[ep_max] - rv_by_ep[ep_min]):.1f} km/s).')
                else:
                    st.info('Could not load spectra for extreme RV epochs.')
            else:
                st.info('Need at least 2 epochs with RV measurements.')

    # ─── X-Shooter > RV Analysis ─────────────────────────────────────────
    with xs_sub[1]:
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
        threshold = ctrl1.slider('ΔRV threshold (km/s)', 5.0, 200.0,
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

        # ── Plot 1: ΔRV Bar Chart ────────────────────────────────────────
        st.markdown('#### Peak-to-Peak ΔRV (all stars)')
        if civ_col in df_view.columns:
            df_sorted = df_view.dropna(subset=[civ_col]).sort_values(
                civ_col, ascending=False).reset_index(drop=True)
            if len(df_sorted) > 0:
                names = df_sorted['Star'].tolist()
                drvs = df_sorted[civ_col].tolist()
                star_names_in_detail = set(detail.keys())
                bar_colors = []
                for sn, d in zip(names, drvs):
                    if sn in star_names_in_detail and detail[sn].get('is_binary'):
                        bar_colors.append(COLOR_BINARY)
                    else:
                        bar_colors.append(COLOR_SINGLE)

                fig_bar = _academic_fig(
                    height=380, xaxis_title='Star', yaxis_title='ΔRV (km/s)',
                    title=dict(text=f'Peak-to-Peak ΔRV ({primary_line_sel})'),
                    xaxis_tickangle=-45,
                )
                fig_bar.add_trace(go.Bar(x=names, y=drvs, marker_color=bar_colors,
                                         showlegend=False))
                fig_bar.add_hline(y=threshold, line_dash='dash', line_color='#DAA520',
                                  annotation_text=f'{threshold:.1f} km/s')
                _show(fig_bar,
                      f'Stars sorted by ΔRV. Red = binary, blue = single. '
                      f'Threshold = {threshold:.1f} km/s.')

        # ── Plot 2: Binary Fraction vs Threshold ─────────────────────────
        st.markdown('#### Binary Fraction vs ΔRV Threshold')
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
                height=420, xaxis_title='ΔRV threshold (km/s)',
                yaxis_title='Binary fraction',
                title=dict(text='Observed Binary Fraction vs ΔRV Threshold'),
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
        _show(fig_grade)
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
        err_arr = detail.get(star_rv, {}).get('rv_err', np.array([]))

        fig_rvep = _academic_fig(
            height=380, xaxis_title='Observation #', yaxis_title='RV (km/s)',
            title=dict(text=f'{star_rv} — RV per epoch'),
        )
        if len(rv_arr) > 0:
            is_bin = detail.get(star_rv, {}).get('is_binary')
            mc = COLOR_BINARY if is_bin else COLOR_SINGLE
            fig_rvep.add_trace(go.Scatter(
                x=list(range(1, len(rv_arr) + 1)), y=rv_arr,
                error_y=dict(type='data', array=err_arr, visible=True),
                mode='markers+lines', marker=dict(size=8, color=mc),
                name=f'RV ({primary_line_sel})',
            ))
        _show(fig_rvep)
        if len(rv_arr) > 0:
            drv_star = detail.get(star_rv, {}).get('best_dRV', 0)
            st.caption(f'ΔRV = {drv_star:.1f} km/s. '
                       f'{"Binary" if detail.get(star_rv, {}).get("is_binary") else "Single"}.')

        # ── Plot 7: Corner Plot ───────────────────────────────────────────
        st.markdown('#### ΔRV Correlation Matrix')
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
                        # Threshold reference lines
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
                    # Style each subplot
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
                title=dict(text='ΔRV Correlation Matrix',
                           font=dict(size=15, family='Times New Roman, serif', color='black')),
            )
            _show(fig_corner,
                  'Diagonal: histograms. Below diagonal: pairwise scatter. '
                  'Red = binary, blue = single.')
        elif len(corner_lines) == 1:
            st.info('Select at least 2 lines for the correlation matrix.')

    # ─── X-Shooter > Emission Lines ──────────────────────────────────────
    with xs_sub[2]:
        st.markdown('### Emission Line ΔRV Table')
        sh = settings_hash(settings)
        try:
            df_el, drverr_el, _, el_lines = cached_load_drv_analysis(sh)
        except Exception as e:
            st.error(str(e))
            st.stop()

        display_cols = ['Star', 'Clean']
        for lk in el_lines:
            cn = f'dRV | {lk}'
            if cn in df_el.columns:
                display_cols.append(cn)
        display_cols.extend(['Mean ΔRV', 'Std ΔRV'])

        df_display = df_el[display_cols].copy()
        for c in df_display.columns:
            if c not in ['Star', 'Clean', 'is_clean_bool']:
                df_display[c] = df_display[c].round(1)

        st.dataframe(df_display, use_container_width=True, height=600)
        st.caption('ΔRV (km/s) per star and emission line. Clean = ✓ means no contamination.')

        st.markdown('#### Per-Line ΔRV Comparison')
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
                el_colors = [COLOR_BINARY if d > threshold else COLOR_SINGLE for d in el_drvs]
                fig_elbar = _academic_fig(
                    height=380, xaxis_title='Emission Line', yaxis_title='ΔRV (km/s)',
                    title=dict(text=f'{el_star} — ΔRV per Line'), xaxis_tickangle=-45,
                )
                fig_elbar.add_trace(go.Bar(x=el_names, y=el_drvs, marker_color=el_colors,
                                           showlegend=False))
                fig_elbar.add_hline(y=threshold, line_dash='dash', line_color='#DAA520',
                                    annotation_text=f'{threshold:.1f} km/s')
                _show(fig_elbar,
                      f'Per-line ΔRV for {el_star}. Red = above threshold, blue = below.')
            else:
                st.info(f'No ΔRV data for {el_star}.')
        else:
            st.info(f'Star {el_star} not found in analysis.')

    # ─── X-Shooter > CCF Outputs ─────────────────────────────────────────
    with xs_sub[3]:
        output_root = os.path.normpath(os.path.join(ROOT, '..', 'output'))
        st.markdown(f'### CCF plots from `{output_root}`')
        if not os.path.isdir(output_root):
            st.info('Output directory not found.')
        else:
            star_f = st.selectbox('Filter by star', ['All'] + specs.star_names,
                                  key='xsp_ccf_star')
            pngs = []
            for sn in specs.star_names:
                clean_sn = re.sub(r"[^A-Za-z0-9_-]", "_", sn)
                d = os.path.join(output_root, clean_sn, 'CCF')
                if os.path.isdir(d):
                    for dp, _, fns in os.walk(d):
                        for fn in fns:
                            if fn.lower().endswith('.png'):
                                pngs.append(os.path.join(dp, fn))
            if star_f != 'All':
                clean_filter = re.sub(r"[^A-Za-z0-9_-]", "_", star_f)
                pngs = [p for p in pngs if clean_filter in p]
            st.write(f'{len(pngs)} CCF plot(s) found.')
            n_show = st.slider('Max plots to show', 3, 30, 12, key='xsp_ccf_n')
            cols = st.columns(3)
            for i, p in enumerate(pngs[:n_show]):
                cols[i % 3].image(p, caption=os.path.basename(p), use_container_width=True)
            if len(pngs) > n_show:
                st.info(f'Showing first {n_show} of {len(pngs)}.')

    # ─── X-Shooter > Grid Results ────────────────────────────────────────
    with xs_sub[4]:
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
                    x_label = 'σ  (velocity dispersion km/s)'
                    x_name = 'σ'
                else:
                    x_grid_key = 'pi_grid'
                    x_label = 'π  (period power-law index)'
                    x_name = 'π'

                x_grid = np.asarray(result.get(x_grid_key, result.get('pi_grid', [])))

                show_d = st.checkbox('Show K-S D statistic', value=False, key='xsp_grid_show_d')

                # Heatmap stays Plotly from shared utility
                fig_hm = make_heatmap_fig(
                    ks_p, fbin_grid, x_grid,
                    title=f'{model_sel} — K-S p-value heatmap',
                    show_d=show_d, ks_d_2d=ks_d,
                    x_label=x_label, x_name=x_name, height=520,
                )
                st.plotly_chart(fig_hm, use_container_width=True, theme=None)
                st.caption(f'{model_sel} grid search result.')

                # p-value slice — academic theme
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

                if st.button('💾 Save heatmap to plots/', key='save_grid_heatmap'):
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
