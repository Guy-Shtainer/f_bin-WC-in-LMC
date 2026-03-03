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
    list_branches, list_task_dirs, load_todos, get_quadrant,
    QUADRANT_LABELS, QUADRANT_COLORS,
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
# Task picker + controls
# ─────────────────────────────────────────────────────────────────────────────

if running:
    st.info('Agent is running. Use sidebar to stop.')
else:
    mode = st.radio(
        'Task source',
        ['Pick from TODO.md', 'Quadrant batch', 'Free-form task'],
        horizontal=True,
        key='task_mode',
    )

    if mode == 'Pick from TODO.md':
        st.markdown('### Select Tasks')

        # Load and display TODO tasks
        all_tasks = load_todos()
        open_tasks = [t for t in all_tasks if t.get('status', 'open') == 'open']

        if not open_tasks:
            st.warning('No open tasks in TODO.md.')
        else:
            # Quadrant filter
            filter_q = st.selectbox(
                'Filter by quadrant',
                ['all', 'do_first', 'schedule', 'delegate', 'eliminate'],
                format_func=lambda q: 'All quadrants' if q == 'all' else QUADRANT_LABELS.get(q, q),
                key='todo_quadrant_filter',
            )
            if filter_q != 'all':
                open_tasks = [t for t in open_tasks if get_quadrant(t) == filter_q]

            # Initialize selected IDs in session state
            if '_selected_task_ids' not in st.session_state:
                st.session_state['_selected_task_ids'] = set()

            # Quick select buttons
            qc1, qc2, qc3 = st.columns(3)
            if qc1.button('Select All', key='sel_all'):
                st.session_state['_selected_task_ids'] = {t['id'] for t in open_tasks}
                st.rerun()
            if qc2.button('Clear All', key='sel_none'):
                st.session_state['_selected_task_ids'] = set()
                st.rerun()
            if qc3.button('Select Critical', key='sel_crit'):
                st.session_state['_selected_task_ids'] = {
                    t['id'] for t in open_tasks if t.get('priority') == 'critical'
                }
                st.rerun()

            # Task list with checkboxes
            for task in open_tasks:
                q = get_quadrant(task)
                q_color = QUADRANT_COLORS.get(q, '#888')
                q_label = QUADRANT_LABELS.get(q, q)

                tid = task['id']
                checked = tid in st.session_state['_selected_task_ids']
                priority = task.get('priority', 'medium')

                col_cb, col_info = st.columns([0.05, 0.95])
                with col_cb:
                    new_val = st.checkbox(
                        f'{tid}', value=checked, key=f'_todo_cb_{tid}',
                        label_visibility='collapsed',
                    )
                    if new_val and tid not in st.session_state['_selected_task_ids']:
                        st.session_state['_selected_task_ids'].add(tid)
                    elif not new_val and tid in st.session_state['_selected_task_ids']:
                        st.session_state['_selected_task_ids'].discard(tid)

                with col_info:
                    badges = (
                        f'<span style="color:{q_color};font-weight:600;">[{q_label}]</span> '
                        f'<span style="color:#9a9a9a;">#{tid}</span> '
                        f'<span style="color:#d4d4d4;font-weight:500;">{task["title"]}</span> '
                        f'<span style="color:#777;font-size:0.8em;">({priority})</span>'
                    )
                    st.markdown(badges, unsafe_allow_html=True)

            selected_ids = sorted(st.session_state['_selected_task_ids'])
            st.caption(f'{len(selected_ids)} task(s) selected')

    elif mode == 'Quadrant batch':
        st.markdown('### Quadrant Batch')
        quadrant = st.selectbox(
            'Quadrant',
            ['eliminate', 'delegate', 'schedule', 'all'],
            index=0,
            key='batch_quadrant',
        )
        max_tasks = st.number_input(
            'Max tasks (0 = unlimited)', min_value=0, value=0, step=1,
            key='batch_max',
        )
        include_critical = st.checkbox('Include critical (do-first) tasks',
                                       key='batch_critical')

    else:  # Free-form
        st.markdown('### Free-form Task')
        freeform = st.text_area(
            'Task description',
            placeholder='Describe what the agents should do...',
            key='freeform_text',
        )

    # ── Launch options ────────────────────────────────────────────────────
    st.markdown('---')
    int_cfg = settings.get('intervention', {})
    opt1, opt2 = st.columns(2)
    wait_reject = opt1.checkbox(
        'Wait on reviewer rejection',
        value=int_cfg.get('wait_on_reject', True),
        key='wait_reject',
    )
    wait_fail = opt2.checkbox(
        'Wait on test failure',
        value=int_cfg.get('wait_on_fail', True),
        key='wait_fail',
    )

    if st.button('Start Agent', type='primary', key='start_agent_btn'):
        launch_kwargs = dict(
            wait_on_reject=wait_reject,
            wait_on_fail=wait_fail,
            intervention_timeout=int_cfg.get('timeout_seconds', 1800),
        )

        if mode == 'Pick from TODO.md':
            selected = sorted(st.session_state.get('_selected_task_ids', set()))
            if not selected:
                st.error('No tasks selected. Check at least one task.')
                st.stop()
            launch_kwargs['task_ids'] = selected
        elif mode == 'Quadrant batch':
            launch_kwargs['quadrant'] = quadrant
            launch_kwargs['max_tasks'] = max_tasks if max_tasks > 0 else None
            launch_kwargs['include_critical'] = include_critical
        else:
            text = st.session_state.get('freeform_text', '').strip()
            if not text:
                st.error('Please enter a task description.')
                st.stop()
            launch_kwargs['freeform_task'] = text

        ok, msg = launch_agent(**launch_kwargs)
        if ok:
            st.success(msg)
        else:
            st.error(msg)
        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# Recent Activity
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('---')
st.markdown('### Recent Activity')

log_tail = get_log_tail(15)
if log_tail:
    st.code(log_tail, language='markdown')
else:
    st.info('No agent log entries yet.')

branches = list_branches()
task_dirs = list_task_dirs()
st.caption(
    f'{len(branches)} agent branch(es) | '
    f'{len(task_dirs)} task artifact dir(s)'
)
