"""
todo_app.py — Standalone To-Do webapp.

Run alongside the main analysis app on a separate port:
    conda run -n guyenv streamlit run todo_app.py --server.port 8502

Shares the same TODO.md and all logic via app/todo_core.py.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

import streamlit as st
from shared import inject_theme
from todo_core import render_todo_page

st.set_page_config(
    page_title='To-Do List',
    page_icon='📝',
    layout='wide',
)
inject_theme()
render_todo_page()
