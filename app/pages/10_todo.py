"""
pages/10_todo.py — Project To-Do List (thin wrapper).

All logic lives in todo_core.py for reuse by the standalone todo_app.py.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st
from shared import inject_theme, render_sidebar
from todo_core import render_todo_page

st.set_page_config(
    page_title='To-Do — WR Binary',
    page_icon='📝',
    layout='wide',
)
inject_theme()
render_sidebar('To-Do')
render_todo_page()
