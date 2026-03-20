"""plots/tab_diagnostics.py — Diagnostics sub-tab: SNR requirements, anchor points on normalized flux."""
from __future__ import annotations

import sys

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from shared import ROOT

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import specs  # noqa: E402

from plots.theme import _academic_fig, _show, _epoch_colors, _add_emission_bands
from plots.data import (
    BANDS, _get_emission_lines, _get_epochs,
    _load_spectrum, _load_raw_spec, _load_normalized_spec,
)


def render_diagnostics_subtab(settings: dict):
    """Render the Diagnostics sub-tab."""
    st.markdown('### Diagnostics')

    # ── Plot #6: SNR Requirements ─────────────────────────────────────
    st.markdown('#### SNR Requirements on Template Spectrum')
    st.caption('Shows a template spectrum with emission line regions highlighted '
               'and SNR annotations.')

    c1, c2, c3 = st.columns(3)
    snr_star = c1.selectbox('Star (template)', specs.star_names, key='xsp_diag_snr_star')
    snr_band = c2.selectbox('Band', BANDS, key='xsp_diag_snr_band')
    snr_epochs = _get_epochs(snr_star)
    snr_ep = c3.selectbox('Epoch (template)', snr_epochs, key='xsp_diag_snr_ep')

    raw_data = _load_raw_spec(snr_star, snr_ep, snr_band)
    emission_lines = _get_emission_lines()

    if raw_data is not None:
        wave_A, flux, err = raw_data

        fig_snr = _academic_fig(
            height=450,
            xaxis_title='Wavelength (Ang.)',
            yaxis_title='Flux',
            title=dict(text=f'{snr_star} -- {snr_band} -- Epoch {snr_ep} (SNR diagnostic)'),
        )
        fig_snr.add_trace(go.Scattergl(
            x=wave_A, y=flux, mode='lines',
            line=dict(color='#4A90D9', width=1), name='Flux',
        ))

        # Add emission line regions with SNR annotations
        for lk, rng in emission_lines.items():
            lam_min = rng[0] * 10.0
            lam_max = rng[1] * 10.0
            mask = (wave_A >= lam_min) & (wave_A <= lam_max)
            if not np.any(mask):
                continue

            fig_snr.add_vrect(
                x0=lam_min, x1=lam_max,
                fillcolor='rgba(218,165,32,0.12)', line_width=0,
            )

            # Compute SNR in this region if error available
            if err is not None and np.any(mask):
                flux_region = flux[mask]
                err_region = err[mask]
                valid_err = err_region[err_region > 0]
                valid_flux = flux_region[err_region > 0]
                if len(valid_err) > 0:
                    snr_median = float(np.median(valid_flux / valid_err))
                    fig_snr.add_annotation(
                        x=(lam_min + lam_max) / 2,
                        y=float(np.max(flux_region)) * 1.05,
                        text=f'{lk[:8]}<br>SNR~{snr_median:.0f}',
                        showarrow=False,
                        font=dict(size=7, color='black'),
                        bgcolor='rgba(255,255,255,0.7)',
                    )

        _show(fig_snr,
              'Template spectrum with emission line regions highlighted. '
              'SNR computed as median(flux/error) per region.')
    else:
        st.info('No raw spectrum available for this star/epoch/band.')

    # ── Plot #9: Anchor Points on Normalized Flux ─────────────────────
    st.markdown('#### Normalized Flux with Anchor Points')
    st.caption('Overlays raw and normalized flux, showing normalization anchor wavelengths.')

    c1a, c2a, c3a = st.columns(3)
    anc_star = c1a.selectbox('Star', specs.star_names, key='xsp_diag_anc_star')
    anc_band = c2a.selectbox('Band', BANDS, key='xsp_diag_anc_band')
    anc_epochs = _get_epochs(anc_star)
    anc_ep = c3a.selectbox('Epoch', anc_epochs, key='xsp_diag_anc_ep')

    show_lines_anc = st.checkbox('Show emission lines', value=True, key='xsp_diag_anc_lines')

    # Load raw and normalized
    raw_anc = _load_raw_spec(anc_star, anc_ep, anc_band)
    norm_data = _load_normalized_spec(anc_star, anc_ep, anc_band, use_cleaned=True)

    if raw_anc is not None and norm_data is not None:
        wave_raw_A, flux_raw, _ = raw_anc
        wave_norm = np.asarray(norm_data.get('wavelengths', norm_data.get('wave', [])))
        flux_norm = np.asarray(norm_data.get('normalized_flux', norm_data.get('flux', [])))

        if len(wave_norm) > 0:
            wave_norm_A = wave_norm * 10.0  # nm -> Angstrom

            fig_anc = _academic_fig(
                height=500,
                xaxis_title='Wavelength (Ang.)',
                yaxis_title='Flux',
                title=dict(text=f'{anc_star} -- {anc_band} -- Epoch {anc_ep} (anchor points)'),
            )

            # Raw flux (scaled for overlay)
            fig_anc.add_trace(go.Scattergl(
                x=wave_raw_A, y=flux_raw, mode='lines',
                line=dict(color='rgba(74,144,217,0.3)', width=1),
                name='Raw flux', yaxis='y2',
            ))

            # Normalized flux
            fig_anc.add_trace(go.Scattergl(
                x=wave_norm_A, y=flux_norm, mode='lines',
                line=dict(color='#4A90D9', width=1.2),
                name='Normalized flux',
            ))

            # Anchor points: where normalized flux ~ 1.0 (within tolerance)
            anchor_tol = 0.02
            anchor_mask = np.abs(flux_norm - 1.0) < anchor_tol
            if np.any(anchor_mask):
                # Sample anchor points to avoid cluttering
                anchor_indices = np.where(anchor_mask)[0]
                # Take every Nth point to reduce density
                step = max(1, len(anchor_indices) // 50)
                sampled = anchor_indices[::step]
                fig_anc.add_trace(go.Scatter(
                    x=wave_norm_A[sampled],
                    y=flux_norm[sampled],
                    mode='markers',
                    marker=dict(size=4, color='#DAA520', symbol='diamond'),
                    name='Anchor points (flux ~ 1.0)',
                ))

            if show_lines_anc:
                _add_emission_bands(fig_anc, _get_emission_lines())

            # Add secondary y-axis for raw flux
            fig_anc.update_layout(
                yaxis2=dict(
                    title='Raw flux', overlaying='y', side='right',
                    showgrid=False, linecolor='black', linewidth=0.8,
                    ticks='outside', tickcolor='black',
                ),
            )

            _show(fig_anc,
                  'Blue = normalized flux (left axis). Light blue = raw flux (right axis). '
                  'Gold diamonds = wavelengths where normalized flux crosses 1.0 (anchors).')
        else:
            st.info('No normalized spectrum data available.')
    elif raw_anc is not None:
        st.info('No normalized spectrum available; showing raw only.')
        wave_A, flux, _ = raw_anc
        fig_raw_only = _academic_fig(
            height=400,
            xaxis_title='Wavelength (Ang.)', yaxis_title='Flux',
            title=dict(text=f'{anc_star} -- {anc_band} -- Epoch {anc_ep} (raw only)'),
        )
        fig_raw_only.add_trace(go.Scattergl(
            x=wave_A, y=flux, mode='lines',
            line=dict(color='#4A90D9', width=1), name='Raw flux',
        ))
        _show(fig_raw_only, 'Raw spectrum only (no normalized data available).')
    else:
        st.info('No spectrum data available for this star/epoch/band.')
