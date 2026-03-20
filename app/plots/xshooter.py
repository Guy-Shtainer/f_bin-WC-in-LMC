"""plots/xshooter.py — X-Shooter tab orchestrator: delegates to sub-tab modules."""
from __future__ import annotations

import streamlit as st

from plots.tab_spectra import render_spectra_subtab
from plots.tab_rv_analysis import render_rv_analysis_subtab
from plots.tab_emission_lines import render_emission_lines_subtab
from plots.tab_threshold import render_threshold_subtab
from plots.tab_dashboard import render_dashboard_subtab
from plots.tab_diagnostics import render_diagnostics_subtab
from plots.tab_ccf import render_ccf_subtab
from plots.tab_grid import render_grid_subtab


def render_xshooter_tab(settings: dict, sm):
    """Render all X-Shooter sub-tabs."""
    tab_names = [
        'Spectra', 'RV Analysis', 'Emission Lines',
        'Threshold Analysis', 'Dashboard', 'Diagnostics',
        'CCF Outputs', 'Grid Results',
    ]
    tabs = st.tabs(tab_names)

    with tabs[0]:
        render_spectra_subtab(settings)

    with tabs[1]:
        render_rv_analysis_subtab(settings)

    with tabs[2]:
        render_emission_lines_subtab(settings)

    with tabs[3]:
        render_threshold_subtab(settings)

    with tabs[4]:
        render_dashboard_subtab(settings)

    with tabs[5]:
        render_diagnostics_subtab(settings)

    with tabs[6]:
        render_ccf_subtab()

    with tabs[7]:
        render_grid_subtab()
