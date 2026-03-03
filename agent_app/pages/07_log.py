"""
agent_app/pages/07_log.py — Log Viewer
──────────────────────────────────────
Full agent_log.md viewer with auto-refresh, search, and download.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title='Agent Log', page_icon='📋', layout='wide')

from shared import inject_theme, render_sidebar
from agent_comm import get_log_full, LOG_PATH

inject_theme()
settings = render_sidebar('Log Viewer')

# Auto-refresh control
auto = st.checkbox('Auto-refresh (10s)', value=True, key='log_auto_refresh')
if auto:
    st_autorefresh(interval=10000, limit=None, key='log_refresh')

st.markdown('# Agent Log')

# ─────────────────────────────────────────────────────────────────────────────
# Controls
# ─────────────────────────────────────────────────────────────────────────────
c1, c2, c3 = st.columns([2, 1, 1])

with c1:
    search = st.text_input('Search / filter', placeholder='e.g. REJECTED, FAIL, Task #5')

with c2:
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, 'r') as f:
            log_content = f.read()
        st.download_button(
            'Download log',
            data=log_content,
            file_name='agent_log.md',
            mime='text/markdown',
        )
    else:
        st.caption('No log file yet.')

with c3:
    if st.button('Clear log'):
        if os.path.exists(LOG_PATH):
            with open(LOG_PATH, 'w') as f:
                f.write('# Agent Log\n\n')
            st.success('Log cleared.')
            st.rerun()

st.markdown('---')

# ─────────────────────────────────────────────────────────────────────────────
# Log content
# ─────────────────────────────────────────────────────────────────────────────
full_log = get_log_full()

if not full_log.strip():
    st.info('Agent log is empty.')
    st.stop()

# Apply search filter
if search.strip():
    lines = full_log.split('\n')
    filtered = [
        line for line in lines
        if search.lower() in line.lower()
    ]
    if filtered:
        st.caption(f'{len(filtered)} matching line(s)')
        display_text = '\n'.join(filtered)
    else:
        st.warning(f'No lines matching "{search}"')
        display_text = ''
else:
    display_text = full_log

if display_text:
    # Color-code certain keywords with markdown
    st.markdown(display_text)
