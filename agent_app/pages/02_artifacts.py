"""
agent_app/pages/02_artifacts.py — Artifact Viewer
──────────────────────────────────────────────────
View plan.md, review.md, test_report.md etc. as they're generated.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title='Artifacts', page_icon='📄', layout='wide')

from shared import inject_theme, render_sidebar, COLOR_DONE, COLOR_FAILED
from agent_comm import list_task_dirs, get_artifacts, get_branch_diff

inject_theme()
settings = render_sidebar('Artifacts')

st_autorefresh(interval=10000, limit=None, key='artifacts_refresh')

st.markdown('# Artifact Viewer')

# ─────────────────────────────────────────────────────────────────────────────
# Task selector
# ─────────────────────────────────────────────────────────────────────────────
task_dirs = list_task_dirs()

if not task_dirs:
    st.info('No task artifacts found. Run an agent to generate artifacts.')
    st.stop()

task_options = {
    f"Task #{d['id']} ({len(d['artifacts'])} files, {d['mtime'][:16]})": d['id']
    for d in task_dirs
}

selected_label = st.selectbox('Select task', list(task_options.keys()))
selected_id = task_options[selected_label]

# ─────────────────────────────────────────────────────────────────────────────
# Artifact display
# ─────────────────────────────────────────────────────────────────────────────
artifacts = get_artifacts(selected_id)

if not artifacts:
    st.warning(f'No artifacts found for task #{selected_id}.')
    st.stop()

# Categorize artifacts
categories = {
    'Plan': [k for k in artifacts if 'plan' in k.lower() and 'fix' not in k.lower()],
    'Review': [k for k in artifacts if 'review' in k.lower()],
    'Test Reports': [k for k in artifacts if 'test' in k.lower()],
    'Fix Plans': [k for k in artifacts if 'fix' in k.lower()],
    'Regression': [k for k in artifacts if 'regression' in k.lower()],
    'Other': [],
}
# Catch uncategorized
categorized = set()
for files in categories.values():
    categorized.update(files)
categories['Other'] = [k for k in artifacts if k not in categorized]

# Remove empty categories
categories = {k: v for k, v in categories.items() if v}

tabs = st.tabs(list(categories.keys()))
for tab, (cat_name, file_list) in zip(tabs, categories.items()):
    with tab:
        for fname in file_list:
            content = artifacts[fname]
            st.markdown(f'**{fname}**')

            # Highlight verdicts
            if 'APPROVED' in content.upper():
                st.success('Verdict: APPROVED')
            elif 'REJECTED' in content.upper():
                st.error('Verdict: REJECTED')
            elif content.upper().rstrip().endswith('PASS'):
                st.success('Verdict: PASS')
            elif content.upper().rstrip().endswith('FAIL'):
                st.error('Verdict: FAIL')

            st.markdown(content)
            st.markdown('---')

# ─────────────────────────────────────────────────────────────────────────────
# Git diff toggle
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('### Git Diff')
if st.checkbox(f'Show diff for task #{selected_id} branch vs main'):
    branch_name = f'agent/{selected_id}-*'
    # Find the exact branch
    from agent_comm import list_branches
    branches = list_branches()
    matching = [b for b in branches if b['task_id'] == selected_id]
    if matching:
        diff = get_branch_diff(matching[0]['name'])
        if diff:
            st.code(diff, language='diff')
        else:
            st.caption('No diff available (branch may already be merged).')
    else:
        st.caption(f'No branch found for task #{selected_id}.')
