"""
agent_app/pages/01_pipeline.py — Live Pipeline Monitor
───────────────────────────────────────────────────────
Shows real-time stage-by-stage tracking of the current agent pipeline.
Supports both architectures:
  - 'pipeline': Fixed 5-stage horizontal view
  - 'opus-manager': Dynamic subagent timeline
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title='Pipeline Monitor', page_icon='\U0001f504', layout='wide')

from shared import (
    inject_theme, render_sidebar, render_pipeline_stages,
    render_subagent_timeline, is_opus_architecture, metric_card,
    PIPELINE_STAGES, COLOR_DONE, COLOR_ACTIVE, COLOR_FAILED, COLOR_WAITING,
    SUBAGENT_COLORS,
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
opus_mode = is_opus_architecture(state)

arch_label = 'Opus Manager' if opus_mode else 'Fixed Pipeline'
st.markdown(f'**Task #{tid}:** {title}')
st.caption(f'Branch: `{branch}` | Architecture: {arch_label}')

# ─────────────────────────────────────────────────────────────────────────────
# Pipeline / Subagent visualization
# ─────────────────────────────────────────────────────────────────────────────
if opus_mode:
    timeline_html = render_subagent_timeline(state)
    st.markdown(timeline_html, unsafe_allow_html=True)
else:
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
# Stage timeline / Subagent activity
# ─────────────────────────────────────────────────────────────────────────────
from datetime import datetime

if opus_mode:
    # Opus mode: show subagent invocation timeline
    st.markdown('### Subagent Activity')

    completed = state.get('subagents_completed', [])
    if completed:
        rows = []
        for entry in completed:
            agent_type = entry.get('type', 'unknown')
            ts = entry.get('time', '')
            rows.append({
                'Subagent': agent_type.replace('-', ' ').title(),
                'Type': agent_type,
                'Completed': ts[11:19] if len(ts) > 19 else ts,
            })

        # Add current if running
        if current_stage.startswith('subagent:'):
            agent_type = current_stage.split(':', 1)[1]
            started = state.get('updated_at', '')
            rows.append({
                'Subagent': agent_type.replace('-', ' ').title(),
                'Type': agent_type,
                'Completed': 'Running...',
            })

        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        if current_stage == 'opus_starting':
            st.caption('Opus manager is starting up...')
        elif current_stage == 'opus_running':
            elapsed = ''
            if state.get('started_at'):
                try:
                    started = datetime.fromisoformat(state['started_at'])
                    delta = datetime.now() - started
                    mins = int(delta.total_seconds() // 60)
                    secs = int(delta.total_seconds() % 60)
                    elapsed = f' ({mins}m {secs}s elapsed)'
                except (ValueError, TypeError):
                    pass
            st.caption(f'Opus manager is actively working...{elapsed}')
        else:
            st.caption('No subagent invocations yet.')

    # Show progress.md if available
    st.markdown('### Progress Log')
    artifacts = get_artifacts(tid)
    if artifacts and 'progress.md' in artifacts:
        st.markdown(artifacts['progress.md'])
    else:
        st.caption('No progress updates yet.')

else:
    # Pipeline mode: show fixed stage timeline table
    st.markdown('### Stage Timeline')
    stages_done = state.get('pipeline_stages_done', [])
    failed_stage = current_stage if state.get('error') else None

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
    # Filter out progress.md from artifact tabs (shown above in opus mode)
    display_artifacts = {k: v for k, v in artifacts.items()
                         if not (opus_mode and k == 'progress.md')}
    if display_artifacts:
        tabs = st.tabs(list(display_artifacts.keys()))
        for tab, (name, content) in zip(tabs, display_artifacts.items()):
            with tab:
                st.markdown(content)
    else:
        st.caption('No artifacts generated yet.')
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
