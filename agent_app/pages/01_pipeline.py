"""
agent_app/pages/01_pipeline.py — Live Pipeline Monitor
───────────────────────────────────────────────────────
Shows real-time stage-by-stage tracking of the current agent pipeline.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title='Pipeline Monitor', page_icon='🔄', layout='wide')

from shared import (
    inject_theme, render_sidebar, render_pipeline_stages, metric_card,
    PIPELINE_STAGES, COLOR_DONE, COLOR_ACTIVE, COLOR_FAILED, COLOR_WAITING,
)
from agent_comm import get_state, is_running, get_log_tail, get_artifacts

inject_theme()
settings = render_sidebar('Pipeline Monitor')

st_autorefresh(interval=5000, limit=None, key='pipeline_refresh')

st.markdown('# Pipeline Monitor')

state = get_state()
running = is_running()

if not state or not state.get('current_task_id'):
    if running:
        st.info('Agent is running but no task state available yet...')
    else:
        st.info('No active pipeline. Start an agent from the Dashboard.')
    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# Task header
# ─────────────────────────────────────────────────────────────────────────────
tid = state['current_task_id']
title = state.get('current_task_title', 'Unknown')
branch = state.get('branch', '?')
current_stage = state.get('current_stage', '')
waiting = bool(state.get('awaiting_intervention'))

st.markdown(f'**Task #{tid}:** {title}')
st.caption(f'Branch: `{branch}`')

# ─────────────────────────────────────────────────────────────────────────────
# Pipeline visualization
# ─────────────────────────────────────────────────────────────────────────────
stages_done = state.get('pipeline_stages_done', [])
failed_stage = current_stage if state.get('error') else None

pipeline_html = render_pipeline_stages(stages_done, current_stage, failed_stage, waiting)
st.markdown(pipeline_html, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Intervention banner
# ─────────────────────────────────────────────────────────────────────────────
if waiting:
    itype = state.get('intervention_type', 'unknown')
    st.markdown(f"""
    <div class="intervention-banner">
        <div class="title">Awaiting Human Input</div>
        <div class="detail">Type: {itype} | Go to <b>Interventions</b> page to respond.</div>
    </div>
    """, unsafe_allow_html=True)

# Rate limit
if state.get('rate_limited'):
    resume = state.get('rate_limit_resume_at', '?')
    st.warning(f'Rate limited. Expected resume: {resume}')

st.markdown('---')

# ─────────────────────────────────────────────────────────────────────────────
# Stage timeline table
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('### Stage Timeline')

from datetime import datetime

rows = []
for stage in PIPELINE_STAGES:
    if stage in stages_done:
        status = 'Done'
    elif stage == current_stage:
        status = 'Waiting' if waiting else 'In Progress'
    elif stage == failed_stage:
        status = 'Failed'
    else:
        status = 'Pending'

    # Duration estimate from stage_started_at
    duration = '--'
    if stage == current_stage and state.get('stage_started_at'):
        try:
            started = datetime.fromisoformat(state['stage_started_at'])
            delta = datetime.now() - started
            mins = int(delta.total_seconds() // 60)
            secs = int(delta.total_seconds() % 60)
            duration = f'{mins}m {secs}s'
        except (ValueError, TypeError):
            pass

    rows.append({
        'Stage': stage.replace('_', ' ').title(),
        'Status': status,
        'Duration': duration,
    })

st.dataframe(rows, use_container_width=True, hide_index=True)

# ─────────────────────────────────────────────────────────────────────────────
# Current artifacts preview
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('### Latest Artifacts')
artifacts = get_artifacts(tid)
if artifacts:
    tabs = st.tabs(list(artifacts.keys()))
    for tab, (name, content) in zip(tabs, artifacts.items()):
        with tab:
            st.markdown(content)
else:
    st.caption('No artifacts generated yet.')

# ─────────────────────────────────────────────────────────────────────────────
# Live log tail
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('### Live Log')
log = get_log_tail(20)
if log:
    st.code(log, language='markdown')
else:
    st.caption('No log entries yet.')
