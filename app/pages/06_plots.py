"""pages/06_plots.py — Visualization Gallery (thin wrapper)."""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st
from shared import inject_theme, render_sidebar
from plots import render_plots_page

st.set_page_config(page_title='Plots — WR Binary', page_icon='🖼️', layout='wide')
inject_theme()
render_sidebar('Plots')
render_plots_page()
