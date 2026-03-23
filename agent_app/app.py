"""
agent_app/app.py — Agent Control Panel Dashboard
─────────────────────────────────────────────────
Entry point for the agent control webapp.
Launch: conda run -n guyenv streamlit run agent_app/app.py

Backend: writes .claude/agent-task.json for the ralph-loop /run-task command.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

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
    inject_theme, render_sidebar, metric_card,
    COLOR_DONE, COLOR_FAILED, COLOR_RUNNING,
)
from agent_comm import (
    load_todos, get_quadrant,
    QUADRANT_LABELS, QUADRANT_COLORS,
    get_log_tail,
    launch_agent_v2, is_running, stop_agent,
    get_v2_state, get_v2_phase_display,
)

inject_theme()
settings = render_sidebar('Dashboard')

# Paths
TASK_FILE = Path(_ROOT) / '.claude' / 'agent-task.json'
STATUS_FILE = Path(_ROOT) / '.claude' / 'agent-status.json'


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _read_status():
    """Read .claude/agent-status.json if it exists."""
    if not STATUS_FILE.exists():
        return None
    try:
        return json.loads(STATUS_FILE.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return None


def _write_task_file(queue, freeform_text=None):
    """Write .claude/agent-task.json with the task queue."""
    data = {'queue': queue, 'created_at': datetime.now().isoformat()}
    if freeform_text:
        data['freeform'] = freeform_text
    TASK_FILE.parent.mkdir(parents=True, exist_ok=True)
    TASK_FILE.write_text(json.dumps(data, indent=2), encoding='utf-8')


# ─────────────────────────────────────────────────────────────────────────────
# Auto-refresh every 5 seconds
# ─────────────────────────────────────────────────────────────────────────────
st_autorefresh(interval=5000, limit=None, key='dashboard_refresh')

# ─────────────────────────────────────────────────────────────────────────────
# Header + Status Cards
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('# Agent Control Panel')

# Read status from BOTH v1 (.claude/agent-status.json) and v2 (.agent_state.json)
status_v1 = _read_status()
status_v2 = get_v2_state()

# Prefer v2 state if available, fall back to v1
status = status_v2 if status_v2 and status_v2.get('version') == 2 else status_v1
agent_running = is_running()

if agent_running:
    is_active = True
    status_val = 'RUNNING'
    status_color = COLOR_RUNNING
elif status and status.get('phase') in ('all_done', None):
    is_active = False
    status_val = 'DONE' if status.get('phase') == 'all_done' else 'IDLE'
    status_color = COLOR_DONE if status_val == 'DONE' else COLOR_FAILED
else:
    is_active = False
    status_val = 'IDLE'
    status_color = COLOR_FAILED

c1, c2, c3, c4 = st.columns(4)

metric_card(c1, 'Status', status_val, color=status_color)

# Current task
if status and status.get('task_id'):
    task_val = f"#{status['task_id']}"
    task_sub = status.get('task_title', status.get('title', ''))[:40]
else:
    task_val = '--'
    task_sub = 'No active task'
metric_card(c2, 'Current Task', task_val, sub=task_sub)

# Phase (v2 format: implement/verify/fix with round)
phase_name, phase_emoji, phases_done = get_v2_phase_display(status)
if phase_name != 'idle':
    phase_round = status.get('phase_round', 0) if status else 0
    phase_val = f'{phase_emoji} {phase_name.title()} R{phase_round}'
else:
    phase_val = '--'
metric_card(c3, 'Phase', phase_val)

# Elapsed
if status and status.get('started_at'):
    try:
        started = datetime.fromisoformat(status['started_at'])
        delta = datetime.now() - started
        mins = int(delta.total_seconds() // 60)
        secs = int(delta.total_seconds() % 60)
        elapsed_val = f'{mins}m {secs}s'
    except (ValueError, TypeError):
        elapsed_val = '--'
else:
    elapsed_val = '--'

completed_count = len(status.get('completed_tasks', [])) if status else 0
metric_card(c4, 'Elapsed', elapsed_val, sub=f'{completed_count} task(s) completed')

# Rate limit warning
if status and status.get('rate_limited'):
    resume = status.get('rate_limit_resume_at', '?')
    st.warning(f'Rate limited — waiting until {resume}')

# Phase progress bar (v2)
if is_active and phases_done:
    phase_labels = ['implement', 'verify', 'fix', 're-verify']
    progress_text = ' → '.join(
        f'**{p}**' if p == phase_name else f'~~{p}~~' if any(p in pd for pd in phases_done) else p
        for p in phase_labels
    )
    st.markdown(f'Progress: {progress_text}', unsafe_allow_html=True)

# Live log
if is_active:
    log_tail = get_log_tail(10)
    if log_tail:
        st.code(log_tail, language='text')
    if status and status.get('error'):
        st.error(f"Error: {status['error']}")

st.markdown('---')

# ─────────────────────────────────────────────────────────────────────────────
# Task Picker
# ─────────────────────────────────────────────────────────────────────────────

mode = st.radio(
    'Task source',
    ['Pick from TODO.md', 'Quadrant batch', 'Free-form task'],
    horizontal=True,
    key='task_mode',
)

PRIORITY_ORDER = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
STATUS_COLORS = {
    'open': '#4A90D9', 'to-test': '#DAA520', 'in-progress': '#F5A623',
}

if mode == 'Pick from TODO.md':
    st.markdown('### Select Tasks')

    all_tasks = load_todos()

    if not all_tasks:
        st.warning('No tasks in TODO.md.')
    else:
        # ── Filters row ──────────────────────────────────────────
        fc1, fc2, fc3, fc4, fc5 = st.columns(5)

        filter_status = fc1.selectbox(
            'Status', ['All', 'Open', 'To Test', 'In Progress'],
            key='agent_filter_status',
        )

        all_priorities = sorted(
            {t.get('priority', 'medium') for t in all_tasks},
            key=lambda p: PRIORITY_ORDER.get(p, 3),
        )
        filter_priority = fc2.multiselect(
            'Priority', all_priorities, default=all_priorities,
            key='agent_filter_priority',
        )

        filter_q = fc3.selectbox(
            'Quadrant',
            ['all', 'do_first', 'schedule', 'delegate', 'eliminate'],
            format_func=lambda q: 'All' if q == 'all' else QUADRANT_LABELS.get(q, q),
            key='agent_filter_quadrant',
        )

        all_tags = sorted({
            tag.strip()
            for t in all_tasks
            for tag in t.get('tags', '').split(',')
            if tag.strip()
        })
        filter_tags = fc4.multiselect(
            'Tags', all_tags, default=all_tags,
            key='agent_filter_tags',
        )

        sort_by = fc5.selectbox(
            'Sort by', ['Priority', 'ID', 'Date added', 'Urgent first'],
            key='agent_sort_by',
        )

        # ── Apply filters ────────────────────────────────────────
        filtered = all_tasks

        if filter_status == 'Open':
            filtered = [t for t in filtered if t.get('status', 'open') == 'open']
        elif filter_status == 'To Test':
            filtered = [t for t in filtered if t.get('status', 'open') == 'to-test']
        elif filter_status == 'In Progress':
            filtered = [t for t in filtered if t.get('status', 'open') == 'in-progress']

        if filter_priority:
            filtered = [t for t in filtered if t.get('priority', 'medium') in filter_priority]

        if filter_q != 'all':
            filtered = [t for t in filtered if get_quadrant(t) == filter_q]

        if filter_tags:
            filtered = [
                t for t in filtered
                if any(tag.strip() in filter_tags
                       for tag in t.get('tags', '').split(',') if tag.strip())
                or not t.get('tags', '').strip()
            ]

        # ── Apply sort ───────────────────────────────────────────
        if sort_by == 'Priority':
            filtered.sort(key=lambda t: PRIORITY_ORDER.get(t.get('priority', 'low'), 3))
        elif sort_by == 'Date added':
            filtered.sort(key=lambda t: t.get('date_added', ''), reverse=True)
        elif sort_by == 'Urgent first':
            filtered.sort(key=lambda t: (
                0 if t.get('urgent') and t.get('important') else
                1 if t.get('urgent') else
                2 if t.get('important') else 3
            ))
        else:  # ID
            filtered.sort(key=lambda t: t.get('id', 0))

        # Initialize selected IDs in session state
        if '_selected_task_ids' not in st.session_state:
            st.session_state['_selected_task_ids'] = set()

        # Quick select buttons
        qc1, qc2, qc3 = st.columns(3)
        if qc1.button('Select All', key='sel_all'):
            st.session_state['_selected_task_ids'] = {t['id'] for t in filtered}
            st.rerun()
        if qc2.button('Clear All', key='sel_none'):
            st.session_state['_selected_task_ids'] = set()
            st.rerun()
        if qc3.button('Select Critical', key='sel_crit'):
            st.session_state['_selected_task_ids'] = {
                t['id'] for t in filtered if t.get('priority') == 'critical'
            }
            st.rerun()

        st.caption(f'Showing {len(filtered)} of {len(all_tasks)} tasks')

        # Task list with checkboxes
        for task in filtered:
            q = get_quadrant(task)
            q_color = QUADRANT_COLORS.get(q, '#888')
            q_label = QUADRANT_LABELS.get(q, q)

            tid = task['id']
            checked = tid in st.session_state['_selected_task_ids']
            priority = task.get('priority', 'medium')
            task_status = task.get('status', 'open')
            s_color = STATUS_COLORS.get(task_status, '#888')

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
                status_badge = ''
                if task_status != 'open':
                    status_badge = (
                        f'<span style="background:{s_color};color:#fff;'
                        f'padding:1px 6px;border-radius:3px;font-size:0.7em;'
                        f'margin-right:4px;">{task_status.upper()}</span> '
                    )
                badges = (
                    f'{status_badge}'
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
    all_tasks = load_todos(status_filter='open')
    quadrant = st.selectbox(
        'Quadrant',
        ['eliminate', 'delegate', 'schedule', 'do_first'],
        format_func=lambda q: QUADRANT_LABELS.get(q, q),
        key='batch_quadrant',
    )
    batch_tasks = [t for t in all_tasks if get_quadrant(t) == quadrant]
    st.caption(f'{len(batch_tasks)} open task(s) in this quadrant')
    for t in batch_tasks:
        st.markdown(f"- **#{t['id']}** {t['title']} ({t.get('priority', 'medium')})")
    selected_ids = [t['id'] for t in batch_tasks]

else:  # Free-form
    st.markdown('### Free-form Task')
    freeform_text = st.text_area(
        'Task description',
        placeholder='Describe what the agent should do...',
        key='freeform_text',
    )
    selected_ids = []

# ─────────────────────────────────────────────────────────────────────────────
# Launch Controls
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('---')

lc1, lc2, lc3 = st.columns(3)
max_tasks = lc1.number_input('Max tasks', min_value=1, max_value=20, value=5, key='max_tasks_v2')
model_choice = lc2.selectbox('Model', ['sonnet', 'opus', 'haiku'], key='model_v2')
lc3.markdown('')  # spacer

bc1, bc2, bc3 = st.columns(3)

with bc1:
    if st.button('Launch Agent v2', type='primary', key='launch_v2', disabled=agent_running):
        if mode == 'Free-form task':
            text = st.session_state.get('freeform_text', '').strip()
            if not text:
                st.error('Please enter a task description.')
            else:
                ok, msg = launch_agent_v2(
                    freeform_task=text, max_tasks=int(max_tasks),
                    model=model_choice,
                )
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
        elif mode == 'Quadrant batch':
            ok, msg = launch_agent_v2(
                quadrant=st.session_state.get('batch_quadrant', 'eliminate'),
                max_tasks=int(max_tasks), model=model_choice,
            )
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
        else:
            ids = sorted(st.session_state.get('_selected_task_ids', set()))
            if not ids:
                st.error('No tasks selected.')
            else:
                ok, msg = launch_agent_v2(
                    task_ids=ids, max_tasks=int(max_tasks),
                    model=model_choice,
                )
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

with bc2:
    if st.button('Stop Agent', key='stop_v2', disabled=not agent_running):
        stopped = stop_agent()
        if stopped:
            st.success('Agent stopped.')
        else:
            st.info('Agent was not running.')
        st.rerun()

with bc3:
    if st.button('Save Task Queue (legacy)', key='save_queue'):
        if mode == 'Free-form task':
            text = st.session_state.get('freeform_text', '').strip()
            if not text:
                st.error('Please enter a task description.')
            else:
                _write_task_file(queue=[], freeform_text=text)
                st.success('Saved to legacy queue.')
        else:
            ids = selected_ids if mode == 'Quadrant batch' else sorted(
                st.session_state.get('_selected_task_ids', set())
            )
            if not ids:
                st.error('No tasks selected.')
            else:
                _write_task_file(queue=ids)
                st.success(f'Saved {len(ids)} task(s) to legacy queue.')

# Terminal command
with st.expander('CLI commands'):
    st.code(
        f'conda run -n guyenv python scripts/agent_v2/runner.py '
        f'--max-tasks {int(max_tasks)} --model {model_choice}',
        language='bash'
    )
    st.caption('Add --daemon to run in background, --task "..." for free-form')

# ─────────────────────────────────────────────────────────────────────────────
# Recent Activity
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('---')
st.markdown('### Recent Activity')

log_tail = get_log_tail(15)
if log_tail:
    st.code(log_tail, language='markdown')
else:
    # Fall back to git log
    try:
        result = subprocess.run(
            ['git', 'log', '--oneline', '-10'],
            capture_output=True, text=True, cwd=_ROOT, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            st.code(result.stdout.strip(), language='text')
        else:
            st.info('No recent activity.')
    except (subprocess.SubprocessError, OSError):
        st.info('No recent activity.')

# Rollback info
with st.expander('Rollback Instructions'):
    st.markdown("""
If something goes wrong, run in terminal:
```bash
git reset --hard pre-agent-rewrite && ln -sf ../Data Data
```
This restores everything to the state before the agent rewrite.
""")
