"""plots/page.py — Top-level orchestrator for the Visualization Gallery."""
from __future__ import annotations

import streamlit as st

from shared import get_settings_manager

from plots.xshooter import render_xshooter_tab
from plots.nres import render_nres_tab


def render_plots_page():
    """Main entry point called by the thin wrapper pages/06_plots.py."""
    st.markdown('# 🖼️ Visualization Gallery')

    settings = get_settings_manager().load()
    sm = get_settings_manager()

    tab_xshooter, tab_nres = st.tabs(['X-Shooter', 'NRES'])

    with tab_xshooter:
        render_xshooter_tab(settings, sm)

    with tab_nres:
        render_nres_tab()
