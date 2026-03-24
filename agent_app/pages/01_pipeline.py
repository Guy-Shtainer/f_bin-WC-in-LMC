"""
agent_app/pages/01_pipeline.py — Live Phase Monitor
────────────────────────────────────────────────────
Real-time monitoring of agent v2 phases: IMPLEMENT → VERIFY → FIX.
Auto-refreshes every 5 seconds.
"""

import os
import sys
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title='Phase Monitor', page_icon='\U0001f504', layout='wide')

from shared import (
    inject_theme, render_sidebar, metric_card,
    render_v2_phases, render_v2_phase_history,
    COLOR_DONE, COLOR_ACTIVE, COLOR_FAILED, COLOR_WAITING,
    # Keep v1 imports for backward compat
    render_pipeline_stages, render_subagent_timeline, is_opus_architecture,
    PIPELINE_STAGES, SUBAGENT_COLORS,
)
from agent_comm import (
    get_state, is_running, get_log_tail, get_live_output, get_artifacts,
    get_v2_state, get_v2_phase_display, stop_agent,
)

inject_theme()
settings = render_sidebar('Phase Monitor')

st_autorefresh(interval=5000, limit=None, key='pipeline_refresh')

st.markdown('# Phase Monitor')

state = get_state()
running = is_running()

if not state:
    if running:
        st.info('Agent is running but no state available yet...')
    else:
        st.info('No active agent. Start one from the Dashboard.')
    st.stop()

# Detect v2 vs v1 state
is_v2 = state.get('version') == 2

# ─────────────────────────────────────────────────────────────────────────────
# Task header
# ─────────────────────────────────────────────────────────────────────────────
tid = state.get('task_id', state.get('current_task_id', '?'))
title = state.get('task_title', state.get('current_task_title', 'Unknown'))
branch = state.get('branch', '?')

st.markdown(f'**Task #{tid}:** {title}')
st.caption(f'Branch: `{branch}` | Engine: {"Agent v2" if is_v2 else "Legacy v1"}')

# ─────────────────────────────────────────────────────────────────────────────
# Status cards
# ─────────────────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)

# Status
if running:
    metric_card(c1, 'Status', 'RUNNING', color=COLOR_ACTIVE)
else:
    metric_card(c1, 'Status', 'IDLE', color=COLOR_FAILED)

# Phase
phase_name, phase_emoji, phases_done = get_v2_phase_display(state)
round_num = state.get('phase_round', 0)
metric_card(c2, 'Phase', f'{phase_emoji} {phase_name.title()}',
            sub=f'Round {round_num}')

# Fix rounds
fix_rounds = sum(1 for pd in phases_done if pd.startswith('fix'))
verify_fails = sum(1 for pd in phases_done if 'fail' in pd)
metric_card(c3, 'Fix Rounds', str(fix_rounds), sub=f'{verify_fails} verification failure(s)')

# Elapsed
if state.get('started_at'):
    try:
        started = datetime.fromisoformat(state['started_at'])
        delta = datetime.now() - started
        mins = int(delta.total_seconds() // 60)
        secs = int(delta.total_seconds() % 60)
        elapsed_val = f'{mins}m {secs}s'
    except (ValueError, TypeError):
        elapsed_val = '--'
else:
    elapsed_val = '--'
metric_card(c4, 'Elapsed', elapsed_val)

# ─────────────────────────────────────────────────────────────────────────────
# Phase visualization
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('---')

if is_v2:
    # V2: phase progress bar
    phase_html = render_v2_phases(state)
    st.markdown(phase_html, unsafe_allow_html=True)

    # Rate limit warning
    if state.get('rate_limited'):
        resume = state.get('rate_limit_resume_at', '?')
        st.warning(f'Rate limited — waiting until {resume}')

    # Phase history table
    st.markdown('### Phase History')
    history = render_v2_phase_history(phases_done)
    if history:
        st.dataframe(history, use_container_width=True, hide_index=True)
    else:
        st.caption('No phases completed yet.')

else:
    # V1 fallback: pipeline or opus visualization
    opus_mode = is_opus_architecture(state)
    if opus_mode:
        timeline_html = render_subagent_timeline(state)
        st.markdown(timeline_html, unsafe_allow_html=True)
    else:
        stages_done = state.get('pipeline_stages_done', [])
        current_stage = state.get('current_stage', '')
        failed_stage = current_stage if state.get('error') else None
        waiting = bool(state.get('awaiting_intervention'))
        pipeline_html = render_pipeline_stages(stages_done, current_stage, failed_stage, waiting)
        st.markdown(pipeline_html, unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Stop button
# ─────────────────────────────────────────────────────────────────────────────
if running:
    st.markdown('---')
    if st.button('Stop Agent', type='secondary', key='stop_from_monitor'):
        stopped = stop_agent()
        if stopped:
            st.success('Agent stopped.')
        else:
            st.info('Agent was not running.')
        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# Artifacts preview
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('### Artifacts')
artifacts = get_artifacts(tid)
if artifacts:
    tabs = st.tabs(list(artifacts.keys()))
    for tab, (name, content) in zip(tabs, artifacts.items()):
        with tab:
            st.markdown(content)
else:
    st.caption('No artifacts generated yet.')

# ─────────────────────────────────────────────────────────────────────────────
# Live Agent Output (scrollable)
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('### Live Agent Output')
live_output = get_live_output(200)
if live_output:
    import html as _html
    st.markdown(
        f'<div style="height:400px; overflow-y:auto; background:#1a1a2e; '
        f'padding:12px; border-radius:8px; font-family:monospace; font-size:13px; '
        f'white-space:pre-wrap; color:#e0e0e0;">{_html.escape(live_output)}</div>',
        unsafe_allow_html=True,
    )
else:
    st.caption('No live output yet. Agent may not have started streaming.')

# ─────────────────────────────────────────────────────────────────────────────
# Agent Log
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('### Agent Log')
log = get_log_tail(25)
if log:
    st.code(log, language='markdown')
else:
    st.caption('No log entries yet.')
