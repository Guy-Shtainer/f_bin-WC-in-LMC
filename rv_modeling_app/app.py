"""rv_modeling_app/app.py — Standalone RV Modeling app."""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for p in (_ROOT, _HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import streamlit as st

from shared_lite import inject_theme, get_settings_manager
from rv_modeling import render_rv_modeling_page

st.set_page_config(page_title='RV Modeling', page_icon='📈', layout='wide')
inject_theme()

sm = get_settings_manager()
settings = sm.load()

with st.sidebar:
    st.markdown('## RV Modeling')
    st.divider()
    if st.button('Clear cache', key='_sidebar_clear_cache'):
        st.cache_data.clear()
        st.success('Cache cleared.')

render_rv_modeling_page()
