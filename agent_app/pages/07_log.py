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
c1, c2, c3, c4 = st.columns([2, 1, 1, 1])

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
    max_lines = st.selectbox('Lines', [50, 100, 500, 0], index=1,
                             format_func=lambda x: 'All' if x == 0 else str(x),
                             key='log_max_lines')

with c4:
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
    # Reverse session order so newest appears first
    import re as _re
    _parts = _re.split(r'(?=^## Agent Session —)', full_log, flags=_re.MULTILINE)
    if len(_parts) > 1:
        _preamble = _parts[0]
        _sessions = _parts[1:]
        _sessions.reverse()
        display_text = _preamble + ''.join(_sessions)
    else:
        display_text = full_log

if display_text:
    # Truncate to max_lines if set
    if max_lines and max_lines > 0:
        lines = display_text.split('\n')
        if len(lines) > max_lines:
            display_text = '\n'.join(lines[:max_lines])
            st.caption(f'Showing first {max_lines} of {len(lines)} lines')

    # Scrollable container so user can navigate without page growing unbounded
    with st.container(height=600):
        st.markdown(display_text)
