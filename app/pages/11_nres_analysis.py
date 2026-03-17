"""pages/11_nres_analysis.py — NRES Analysis & DeltaRV Threshold (thin wrapper)."""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st
from shared import inject_theme, render_sidebar
from nres import render_nres_page

st.set_page_config(page_title='NRES Analysis — WR Binary', page_icon='🔭', layout='wide')
inject_theme()
render_sidebar('NRES Analysis')
render_nres_page()
