"""plots/tab_spectra.py — Spectra sub-tab: normalized, raw, error, 2D, consistency, extreme RV."""
from __future__ import annotations

import os
import sys

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from shared import (
    COLOR_BINARY, COLOR_SINGLE, get_obs_manager, ROOT,
)

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import specs  # noqa: E402

from plots.theme import _academic_fig, _show, _epoch_colors, _add_emission_bands
from plots.data import (
    BANDS, _get_emission_lines, _get_epochs,
    _load_spectrum, _load_raw_spec, _load_continuum, _load_rv_property, _extract_rv,
)


def render_spectra_subtab(settings: dict):
    """Render the Spectra sub-tab."""
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
        xaxis_title='Wavelength (Ang.)',
        yaxis_title='Normalised flux',
        title=dict(text=f'{xs_star} -- {xs_band} -- all epochs'),
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
    if sv1.button('Save to plots/', key='save_spec_plot'):
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
                xaxis_title='Wavelength (Ang.)', yaxis_title='Flux',
                title=dict(text=f'{raw_star} -- {raw_band} -- Epoch {ep_raw} (raw)'),
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

            _show(fig_raw, 'Raw FITS spectrum (wavelengths converted from nm to Ang.).')
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
                xaxis_title='Wavelength (Ang.)', yaxis_title='Error',
                title=dict(text=f'{err_star} -- {err_band} -- Epoch {ep_err} (error)'),
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
                    xaxis_title='Wavelength (Ang.)', yaxis_title='Spatial pixel',
                    title=dict(text=f'{img_star} -- {img_band} -- Epoch {ep_2d} (2D)'),
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
            wmin = cw1.number_input('lam min (Ang.)', value=5750, key='xsp_cons_wmin')
            wmax = cw2.number_input('lam max (Ang.)', value=5950, key='xsp_cons_wmax')

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
                        title=dict(text=f'Epoch {ep1} vs {ep2} ({wmin}--{wmax} Ang.)'),
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
                    xaxis_title='Wavelength (Ang.)', yaxis_title='Normalised flux',
                    title=dict(text=f'{ext_star} -- Extreme RV epochs'),
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
                      f'(dRV = {abs(rv_by_ep[ep_max] - rv_by_ep[ep_min]):.1f} km/s).')
            else:
                st.info('Could not load spectra for extreme RV epochs.')
        else:
            st.info('Need at least 2 epochs with RV measurements.')
