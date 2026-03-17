"""plots/nres.py — NRES tab: Spectra, RV Analysis, SNR & Quality."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from shared import get_obs_manager, COLOR_SINGLE

from plots.theme import _academic_fig, _show, _epoch_colors
from plots.data import NRES_STARS, _extract_rv


def render_nres_tab():
    """Render all NRES sub-tabs."""
    nres_sub = st.tabs(['Spectra', 'RV Analysis', 'SNR & Quality'])

    # ─── NRES > Spectra ──────────────────────────────────────────────────
    with nres_sub[0]:
        st.markdown('### NRES Spectra Viewer')
        nres_star = st.selectbox('Star', NRES_STARS, key='nsp_star')
        obs_nres = get_obs_manager()

        try:
            nres_obj = obs_nres.load_star_instance(nres_star, to_print=False)
            nres_epochs = nres_obj.get_all_epoch_numbers()
        except Exception as e:
            st.error(f'Could not load NRES star {nres_star}: {e}')
            nres_obj = None
            nres_epochs = []

        if nres_obj is not None and nres_epochs:
            nres_ep = st.selectbox('Epoch', nres_epochs, key='nsp_epoch')
            nres_spectra = nres_obj.get_all_spectra_in_epoch(nres_ep)

            if nres_spectra:
                nres_use_clean = st.checkbox('Use cleaned spectra', value=True, key='nsp_clean')

                st.markdown('#### Normalized Spectra (all spectra in epoch)')
                fig_nspec = _academic_fig(
                    height=480, xaxis_title='Wavelength (Å)',
                    yaxis_title='Normalised flux',
                    title=dict(text=f'{nres_star} — Epoch {nres_ep} — Normalized'),
                )
                ncolors = _epoch_colors(len(nres_spectra))

                for i, sp_num in enumerate(nres_spectra):
                    try:
                        if nres_use_clean:
                            data = nres_obj.load_property('clean_normalized_flux',
                                                          nres_ep, sp_num, to_print=False)
                            if data is None or not isinstance(data, dict):
                                data = nres_obj.load_property('normalized_flux',
                                                              nres_ep, sp_num, to_print=False)
                        else:
                            data = nres_obj.load_property('normalized_flux',
                                                          nres_ep, sp_num, to_print=False)
                    except Exception:
                        data = None

                    if not isinstance(data, dict):
                        continue
                    wave = np.asarray(data.get('wavelengths', []))
                    flux = np.asarray(data.get('normalized_flux', []))
                    if len(wave) == 0:
                        continue

                    fig_nspec.add_trace(go.Scattergl(
                        x=wave, y=flux, mode='lines',
                        line=dict(color=ncolors[i], width=1),
                        name=f'Spec {sp_num}',
                    ))

                _show(fig_nspec, 'Normalized spectra for all observations in this epoch.')

                # ── Stitched spectrum ─────────────────────────────────────
                st.markdown('#### Stitched Spectrum')
                sp_sel = st.selectbox('Spectrum number', nres_spectra, key='nsp_stitch_sp')
                try:
                    wave_st, flux_st, snr_st = nres_obj.get_stitched_spectra3(nres_ep, sp_sel)
                    if wave_st is not None and len(wave_st) > 0:
                        fig_stitch = _academic_fig(
                            height=420, xaxis_title='Wavelength (Å)', yaxis_title='Flux',
                            title=dict(text=f'{nres_star} — Ep {nres_ep} Spec {sp_sel} (stitched)'),
                        )
                        fig_stitch.add_trace(go.Scattergl(
                            x=wave_st, y=flux_st, mode='lines',
                            line=dict(color=COLOR_SINGLE, width=1), name='Stitched flux',
                        ))
                        _show(fig_stitch, 'Stitched spectrum (low-blaze filtering enabled).')
                    else:
                        st.info('Could not stitch spectra for this observation.')
                except Exception as e:
                    st.info(f'Stitching failed: {e}')
            else:
                st.info(f'No spectra found in epoch {nres_ep}.')
        else:
            st.info(f'No epochs found for {nres_star}.')

    # ─── NRES > RV Analysis ──────────────────────────────────────────────
    with nres_sub[1]:
        st.markdown('### NRES RV Analysis')
        nres_rv_star = st.selectbox('Star', NRES_STARS, key='nrv_star')
        try:
            nres_rv_obj = get_obs_manager().load_star_instance(nres_rv_star, to_print=False)
            nres_rv_epochs = nres_rv_obj.get_all_epoch_numbers()
        except Exception:
            nres_rv_epochs = []
            nres_rv_obj = None

        if nres_rv_obj is not None and nres_rv_epochs:
            all_rvs = []
            for ep in nres_rv_epochs:
                spectra_nums = nres_rv_obj.get_all_spectra_in_epoch(ep)
                for sp in spectra_nums:
                    try:
                        rv_prop = nres_rv_obj.load_property('RVs', ep, sp, to_print=False)
                        if not isinstance(rv_prop, dict):
                            continue
                        for line_key in ['C IV 5808-5812', 'He II 4686']:
                            if line_key in rv_prop:
                                rv_val, rv_err = _extract_rv(rv_prop[line_key])
                                if rv_val is not None and rv_val != 0.0:
                                    try:
                                        fit = nres_rv_obj.load_observation(ep, sp, '1D')
                                        mjd = float(fit.header['MJD-OBS'])
                                    except Exception:
                                        mjd = float(ep)
                                    all_rvs.append((ep, sp, rv_val,
                                                    rv_err if rv_err else 0, mjd))
                                break
                    except Exception:
                        continue

            if all_rvs:
                rvs_arr = np.array(all_rvs)
                mjds = rvs_arr[:, 4]
                rvs = rvs_arr[:, 2]
                errs = rvs_arr[:, 3]
                ep_nums = rvs_arr[:, 0].astype(int)

                fig_nrv = _academic_fig(
                    height=420, xaxis_title='MJD', yaxis_title='RV (km/s)',
                    title=dict(text=f'{nres_rv_star} — NRES RV measurements'),
                )
                fig_nrv.add_trace(go.Scatter(
                    x=mjds, y=rvs,
                    error_y=dict(type='data', array=errs, visible=True),
                    mode='markers', marker=dict(size=6, color=COLOR_SINGLE),
                    name='Individual RVs',
                    hovertext=[f'Ep{int(r[0])} Sp{int(r[1])}' for r in rvs_arr],
                ))

                unique_eps = sorted(set(ep_nums))
                for ep_u in unique_eps:
                    mask = ep_nums == ep_u
                    ep_rvs = rvs[mask]
                    ep_mjds = mjds[mask]
                    if len(ep_rvs) >= 2:
                        fig_nrv.add_trace(go.Scatter(
                            x=[np.mean(ep_mjds)], y=[np.mean(ep_rvs)],
                            error_y=dict(type='data', array=[np.std(ep_rvs)], visible=True),
                            mode='markers', marker=dict(size=12, color='#DAA520', symbol='star'),
                            name=f'Epoch {ep_u} mean',
                        ))

                _show(fig_nrv, 'Individual measurements (dots) and epoch means (stars).')

                st.markdown('#### Epoch Summary')
                summary_rows = []
                for ep_u in unique_eps:
                    mask = ep_nums == ep_u
                    ep_rvs = rvs[mask]
                    summary_rows.append({
                        'Epoch': ep_u, 'N spectra': int(np.sum(mask)),
                        'Mean RV': f'{np.mean(ep_rvs):.1f}',
                        'Std RV': f'{np.std(ep_rvs):.1f}',
                        'Min RV': f'{np.min(ep_rvs):.1f}',
                        'Max RV': f'{np.max(ep_rvs):.1f}',
                    })
                st.dataframe(pd.DataFrame(summary_rows), use_container_width=True)
            else:
                st.info(f'No RV measurements found for {nres_rv_star}.')
        else:
            st.info('Could not load NRES star data.')

    # ─── NRES > SNR & Quality ────────────────────────────────────────────
    with nres_sub[2]:
        st.markdown('### NRES SNR & Quality')
        nres_q_star = st.selectbox('Star', NRES_STARS, key='nq_star')
        try:
            nres_q_obj = get_obs_manager().load_star_instance(nres_q_star, to_print=False)
            nres_q_epochs = nres_q_obj.get_all_epoch_numbers()
        except Exception:
            nres_q_epochs = []
            nres_q_obj = None

        if nres_q_obj is not None and nres_q_epochs:
            nres_q_ep = st.selectbox('Epoch', nres_q_epochs, key='nq_epoch')
            nres_q_spectra = nres_q_obj.get_all_spectra_in_epoch(nres_q_ep)

            if nres_q_spectra:
                nres_q_sp = st.selectbox('Spectrum', nres_q_spectra, key='nq_sp')

                # ── SNR vs wavelength ─────────────────────────────────────
                st.markdown('#### SNR vs Wavelength')
                try:
                    wave_snr, flux_snr, snr_arr = nres_q_obj.get_stitched_spectra3(
                        nres_q_ep, nres_q_sp)
                    if wave_snr is not None and snr_arr is not None and len(snr_arr) > 0:
                        fig_snr = _academic_fig(
                            height=380, xaxis_title='Wavelength (Å)', yaxis_title='SNR',
                            title=dict(text=f'{nres_q_star} — Ep {nres_q_ep} Spec {nres_q_sp} — SNR'),
                        )
                        fig_snr.add_trace(go.Scatter(
                            x=wave_snr, y=snr_arr, mode='lines',
                            line=dict(color='#52B788', width=1), name='SNR',
                        ))
                        _show(fig_snr, 'Signal-to-noise ratio from stitched spectrum.')
                    else:
                        st.info('SNR data not available.')
                except Exception as e:
                    st.info(f'Could not compute SNR: {e}')

                # ── Individual NRES Orders ────────────────────────────────
                with st.expander('Individual NRES Orders', expanded=False):
                    blaze_corr = st.checkbox('Blaze correction', value=True, key='nq_blaze')
                    try:
                        fit_nres = nres_q_obj.load_observation(nres_q_ep, nres_q_sp, '1D')
                        if fit_nres is not None:
                            flux_arr = np.flip(np.array(fit_nres.data['flux']), axis=0)
                            blaze_arr = np.flip(np.array(fit_nres.data['blaze']), axis=0)
                            wave_arr = np.flip(np.array(fit_nres.data['wavelength']), axis=0)

                            n_orders = flux_arr.shape[0]
                            if nres_q_star == 'WR17' and nres_q_ep in [2, 3]:
                                obj_indices = list(range(1, n_orders, 2))
                            else:
                                obj_indices = list(range(0, n_orders, 2))

                            order_sel = st.multiselect(
                                'Orders to display', obj_indices,
                                default=obj_indices[:5] if len(obj_indices) > 5 else obj_indices,
                                key='nq_orders',
                            )

                            if order_sel:
                                fig_ord = _academic_fig(
                                    height=420, xaxis_title='Wavelength (Å)', yaxis_title='Flux',
                                    title=dict(text=f'{nres_q_star} — Orders '
                                               f'{"(blaze-corrected)" if blaze_corr else "(raw)"}'),
                                )
                                ord_colors = _epoch_colors(len(order_sel))
                                for ci, oidx in enumerate(order_sel):
                                    w = wave_arr[oidx]
                                    if blaze_corr:
                                        b = blaze_arr[oidx]
                                        b_safe = np.where(b > 0, b, 1.0)
                                        f = flux_arr[oidx] / b_safe
                                    else:
                                        f = flux_arr[oidx]
                                    fig_ord.add_trace(go.Scattergl(
                                        x=w, y=f, mode='lines',
                                        line=dict(color=ord_colors[ci], width=1),
                                        name=f'Order {oidx}',
                                    ))
                                _show(fig_ord,
                                      f'NRES fiber orders '
                                      f'{"with" if blaze_corr else "without"} blaze correction.')
                        else:
                            st.info('Could not load raw NRES observation.')
                    except Exception as e:
                        st.info(f'Error loading orders: {e}')

                # ── Blaze Function ────────────────────────────────────────
                with st.expander('Blaze Function', expanded=False):
                    try:
                        fit_blaze = nres_q_obj.load_observation(nres_q_ep, nres_q_sp, '1D')
                        if fit_blaze is not None:
                            blaze_data = np.flip(np.array(fit_blaze.data['blaze']), axis=0)
                            wave_data = np.flip(np.array(fit_blaze.data['wavelength']), axis=0)

                            fig_blaze = _academic_fig(
                                height=380, xaxis_title='Wavelength (Å)', yaxis_title='Blaze',
                                title=dict(text=f'{nres_q_star} — Blaze Functions'),
                            )
                            n_o = blaze_data.shape[0]
                            bl_colors = _epoch_colors(n_o)
                            for oi in range(0, n_o, max(1, n_o // 15)):
                                fig_blaze.add_trace(go.Scatter(
                                    x=wave_data[oi], y=blaze_data[oi], mode='lines',
                                    line=dict(color=bl_colors[oi], width=1),
                                    name=f'Order {oi}', showlegend=False,
                                ))
                            _show(fig_blaze, 'Blaze function for each order.')
                        else:
                            st.info('Could not load blaze data.')
                    except Exception as e:
                        st.info(f'Error loading blaze function: {e}')
            else:
                st.info(f'No spectra found in epoch {nres_q_ep}.')
        else:
            st.info(f'No data available for {nres_q_star}.')
