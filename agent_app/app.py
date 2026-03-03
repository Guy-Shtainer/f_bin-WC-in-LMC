"""
agent_app/app.py — Agent Control Panel Dashboard
─────────────────────────────────────────────────
Entry point for the agent control webapp.
Launch: conda run -n guyenv streamlit run agent_app/app.py
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(
    page_title='Agent Control Panel',
    page_icon='🤖',
    layout='wide',
    initial_sidebar_state='expanded',
)

from shared import (
    inject_theme, render_sidebar, metric_card, render_pipeline_stages,
    get_agent_settings_manager, COLOR_DONE, COLOR_ACTIVE, COLOR_FAILED,
    COLOR_WAITING, COLOR_RUNNING,
)
from agent_comm import (
    get_state, is_running, launch_agent, get_log_tail,
    list_branches, list_task_dirs,
)

inject_theme()
settings = render_sidebar('Dashboard')

# Auto-refresh every 5 seconds
st_autorefresh(interval=5000, limit=None, key='dashboard_refresh')

# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('# Agent Control Panel')

state = get_state()
running = is_running()

# ─────────────────────────────────────────────────────────────────────────────
# Metric cards
# ─────────────────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns(4)

# Status
if state and state.get('awaiting_intervention'):
    status_val = 'WAITING'
    status_color = COLOR_WAITING
elif running:
    status_val = 'RUNNING'
    status_color = COLOR_RUNNING
else:
    status_val = 'STOPPED'
    status_color = COLOR_FAILED

metric_card(c1, 'Status', status_val, color=status_color)

# Current task
if state and state.get('current_task_id'):
    task_val = f"#{state['current_task_id']}"
    task_sub = state.get('current_task_title', '')[:40]
else:
    task_val = '--'
    task_sub = 'No active task'
metric_card(c2, 'Current Task', task_val, sub=task_sub)

# Stage
stage_val = '--'
if state and state.get('current_stage'):
    stage_val = state['current_stage'].replace('_', ' ').title()
metric_card(c3, 'Stage', stage_val)

# Elapsed
elapsed_sub = ''
if state and state.get('started_at'):
    from datetime import datetime
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

completed_count = len(state.get('completed_tasks', [])) if state else 0
metric_card(c4, 'Elapsed', elapsed_val, sub=f'{completed_count} task(s) completed')

# ─────────────────────────────────────────────────────────────────────────────
# Pipeline visualization
# ─────────────────────────────────────────────────────────────────────────────
if state and state.get('current_task_id'):
    stages_done = state.get('pipeline_stages_done', [])
    current_stage = state.get('current_stage')
    waiting = bool(state.get('awaiting_intervention'))
    failed = state.get('error')
    failed_stage = current_stage if failed else None

    pipeline_html = render_pipeline_stages(
        stages_done, current_stage, failed_stage, waiting
    )
    st.markdown(pipeline_html, unsafe_allow_html=True)

    # Rate limit indicator
    if state.get('rate_limited'):
        resume = state.get('rate_limit_resume_at', '?')
        st.warning(f'Rate limited. Resume at: {resume}')

st.markdown('---')

# ─────────────────────────────────────────────────────────────────────────────
# Quick controls + Recent activity (two columns)
# ─────────────────────────────────────────────────────────────────────────────
left, right = st.columns([1, 1.5])

with left:
    st.markdown('### Quick Controls')

    if running:
        st.info('Agent is running. Use sidebar to stop.')
    else:
        with st.form('launch_form'):
            mode = st.radio(
                'Task source',
                ['TODO.md tasks', 'Free-form task'],
                horizontal=True,
            )

            if mode == 'TODO.md tasks':
                quadrant = st.selectbox(
                    'Quadrant',
                    ['eliminate', 'delegate', 'schedule', 'all'],
                    index=0,
                )
                max_tasks = st.number_input(
                    'Max tasks (0 = unlimited)', min_value=0, value=0, step=1,
                )
                include_critical = st.checkbox('Include critical (do-first) tasks')
                freeform = None
            else:
                freeform = st.text_area(
                    'Task description',
                    placeholder='Describe what the agents should do...',
                )
                quadrant = 'eliminate'
                max_tasks = 0
                include_critical = False

            int_cfg = settings.get('intervention', {})
            wait_reject = st.checkbox(
                'Wait on reviewer rejection',
                value=int_cfg.get('wait_on_reject', True),
            )
            wait_fail = st.checkbox(
                'Wait on test failure',
                value=int_cfg.get('wait_on_fail', True),
            )

            submitted = st.form_submit_button('Start Agent', type='primary')
            if submitted:
                ok, msg = launch_agent(
                    quadrant=quadrant,
                    max_tasks=max_tasks if max_tasks > 0 else None,
                    include_critical=include_critical,
                    freeform_task=freeform if freeform and freeform.strip() else None,
                    wait_on_reject=wait_reject,
                    wait_on_fail=wait_fail,
                    intervention_timeout=int_cfg.get('timeout_seconds', 1800),
                )
                if ok:
                    st.success(msg)
                else:
                    st.error(msg)
                st.rerun()

with right:
    st.markdown('### Recent Activity')

    # Recent log
    log_tail = get_log_tail(15)
    if log_tail:
        st.code(log_tail, language='markdown')
    else:
        st.info('No agent log entries yet.')

    # Summary stats
    branches = list_branches()
    task_dirs = list_task_dirs()
    st.caption(
        f'{len(branches)} agent branch(es) | '
        f'{len(task_dirs)} task artifact dir(s)'
    )
