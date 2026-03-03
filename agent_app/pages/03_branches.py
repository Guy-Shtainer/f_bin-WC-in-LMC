"""
agent_app/pages/03_branches.py — Branch Manager
────────────────────────────────────────────────
Review/merge/discard completed agent branches (GUI version of --stop).
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st

st.set_page_config(page_title='Branches', page_icon='🌿', layout='wide')

from shared import inject_theme, render_sidebar, COLOR_DONE, COLOR_FAILED
from agent_comm import (
    list_branches, get_branch_log, get_branch_diff, get_artifacts,
    merge_branch, discard_branch,
)

inject_theme()
settings = render_sidebar('Branches')

st.markdown('# Branch Manager')

branches = list_branches()

if not branches:
    st.info('No agent branches found.')
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# Summary table
# ─────────────────────────────────────────────────────────────────────────────
st.markdown(f'**{len(branches)} agent branch(es)**')

for branch in branches:
    name = branch['name']
    tid = branch['task_id']
    commits = branch['commits']

    with st.expander(f"{name}  ({commits} commit(s))"):
        col1, col2, col3 = st.columns(3)

        # Actions
        with col1:
            if st.button(f'Merge to main', key=f'merge_{name}'):
                ok, msg = merge_branch(name)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
                st.rerun()

        with col2:
            if st.button(f'Discard', key=f'discard_{name}',
                         type='secondary'):
                ok, msg = discard_branch(name)
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
                st.rerun()

        with col3:
            st.caption(f'Task #{tid} | {branch["date"][:16]}')

        # Commit log
        st.markdown('**Commit log:**')
        log = get_branch_log(name)
        if log:
            st.code(log, language='text')
        else:
            st.caption('No commits relative to main.')

        # Diff stat
        if branch['stat']:
            st.markdown('**Diff stat:**')
            st.code(branch['stat'], language='text')

        # Artifacts preview
        if tid:
            artifacts = get_artifacts(tid)
            if artifacts:
                st.markdown('**Artifacts:**')
                for fname, content in artifacts.items():
                    with st.popover(fname):
                        st.markdown(content)

st.markdown('---')

# ─────────────────────────────────────────────────────────────────────────────
# Bulk actions
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('### Bulk Actions')

col_a, col_b = st.columns(2)

with col_a:
    if st.button('Merge all branches', type='primary'):
        results = []
        for b in branches:
            ok, msg = merge_branch(b['name'])
            results.append((b['name'], ok, msg))
        for name, ok, msg in results:
            if ok:
                st.success(msg)
            else:
                st.error(msg)
        st.rerun()

with col_b:
    if st.button('Discard all branches', type='secondary'):
        results = []
        for b in branches:
            ok, msg = discard_branch(b['name'])
            results.append((b['name'], ok, msg))
        for name, ok, msg in results:
            if ok:
                st.success(msg)
            else:
                st.error(msg)
        st.rerun()
