"""nres/page.py — Top-level orchestrator for NRES Analysis page."""
from __future__ import annotations

import streamlit as st

from shared import get_settings_manager
from nres.config import NRES_STARS
from nres.data import _load_star_epochs
from nres.spectra_tab import render_spectra_tab
from nres.threshold_tab import render_threshold_tab


def render_nres_page():
    """Main entry point called by the thin wrapper pages/11_nres_analysis.py."""
    st.markdown('# NRES Analysis & DeltaRV Threshold')

    sm = get_settings_manager()
    settings = sm.load()

    col_star, col_velo = st.columns([2, 1])
    with col_star:
        star_name = st.selectbox('Select NRES Star', NRES_STARS, key='nres_star')
    with col_velo:
        cross_velo = st.number_input(
            'CrossVelo (km/s)', min_value=100, max_value=5000, value=2000, step=100,
            key='nres_cross_velo',
        )

    epochs, spectra_per_epoch = _load_star_epochs(star_name)

    tab_spec, tab_thresh = st.tabs(['Spectra & CCF', 'Threshold Analysis'])

    with tab_spec:
        render_spectra_tab(star_name, epochs, spectra_per_epoch, cross_velo, settings)

    with tab_thresh:
        render_threshold_tab(settings)
