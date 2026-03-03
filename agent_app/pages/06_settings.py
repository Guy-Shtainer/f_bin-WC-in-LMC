"""
agent_app/pages/06_settings.py — Agent Settings
────────────────────────────────────────────────
Configure timeouts, quadrants, intervention rules, and other agent parameters.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st

st.set_page_config(page_title='Agent Settings', page_icon='⚙️', layout='wide')

from shared import inject_theme, render_sidebar, get_agent_settings_manager, AGENT_ROLES

inject_theme()
settings = render_sidebar('Settings')
asm = get_agent_settings_manager()

st.markdown('# Agent Settings')
st.caption('Changes are saved immediately to scripts/agent_settings.json.')

# ─────────────────────────────────────────────────────────────────────────────
# General
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('### General')

c1, c2, c3 = st.columns(3)

with c1:
    quadrant = st.selectbox(
        'Default quadrant',
        ['eliminate', 'delegate', 'schedule', 'all'],
        index=['eliminate', 'delegate', 'schedule', 'all'].index(
            settings.get('default_quadrant', 'eliminate')
        ),
        key='cfg_quadrant',
    )
    if quadrant != settings.get('default_quadrant', 'eliminate'):
        asm.save('default_quadrant', quadrant)

with c2:
    max_tasks_val = settings.get('max_tasks') or 0
    max_tasks = st.number_input(
        'Max tasks per run (0 = unlimited)',
        min_value=0, value=int(max_tasks_val), step=1,
        key='cfg_max_tasks',
    )
    new_val = max_tasks if max_tasks > 0 else None
    if new_val != settings.get('max_tasks'):
        asm.save('max_tasks', new_val)

with c3:
    include_crit = st.checkbox(
        'Include critical (do-first) tasks',
        value=bool(settings.get('include_critical', False)),
        key='cfg_include_critical',
    )
    if include_crit != settings.get('include_critical', False):
        asm.save('include_critical', include_crit)

c4, c5 = st.columns(2)

with c4:
    rate_sleep = st.number_input(
        'Rate limit sleep (seconds)',
        min_value=30, max_value=3600,
        value=int(settings.get('rate_limit_sleep', 300)),
        step=30, key='cfg_rate_sleep',
    )
    if rate_sleep != settings.get('rate_limit_sleep', 300):
        asm.save('rate_limit_sleep', rate_sleep)

with c5:
    max_fix = st.number_input(
        'Max fix attempts',
        min_value=0, max_value=10,
        value=int(settings.get('max_fix_attempts', 2)),
        key='cfg_max_fix',
    )
    if max_fix != settings.get('max_fix_attempts', 2):
        asm.save('max_fix_attempts', max_fix)

st.markdown('---')

# ─────────────────────────────────────────────────────────────────────────────
# Timeouts
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('### Timeouts (seconds)')

timeouts = settings.get('timeouts', {})
timeout_roles = [r for r in AGENT_ROLES if r != 'global']
cols = st.columns(len(timeout_roles))

for col, role in zip(cols, timeout_roles):
    with col:
        default = {
            'planner': 1200, 'reviewer': 300, 'implementer': 1500,
            'tester': 300, 'regression': 300,
            'fix_planner': 300, 'fix_implementer': 600,
        }.get(role, 300)
        val = st.number_input(
            role.replace('_', ' ').title(),
            min_value=60, max_value=7200,
            value=int(timeouts.get(role, default)),
            step=60, key=f'timeout_{role}',
        )
        if val != timeouts.get(role, default):
            asm.save(['timeouts', role], val)

st.markdown('---')

# ─────────────────────────────────────────────────────────────────────────────
# Intervention
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('### Intervention')

int_cfg = settings.get('intervention', {})

c1, c2 = st.columns(2)

with c1:
    wait_reject = st.checkbox(
        'Wait on reviewer rejection',
        value=bool(int_cfg.get('wait_on_reject', True)),
        key='cfg_wait_reject',
    )
    if wait_reject != int_cfg.get('wait_on_reject', True):
        asm.save(['intervention', 'wait_on_reject'], wait_reject)

    auto_replan = st.number_input(
        'Auto-replan max (0 = always wait)',
        min_value=0, max_value=10,
        value=int(int_cfg.get('auto_replan_max', 0)),
        key='cfg_auto_replan',
    )
    if auto_replan != int_cfg.get('auto_replan_max', 0):
        asm.save(['intervention', 'auto_replan_max'], auto_replan)

with c2:
    wait_fail = st.checkbox(
        'Wait on test failure',
        value=bool(int_cfg.get('wait_on_fail', True)),
        key='cfg_wait_fail',
    )
    if wait_fail != int_cfg.get('wait_on_fail', True):
        asm.save(['intervention', 'wait_on_fail'], wait_fail)

    auto_skip = st.number_input(
        'Auto-skip test max (0 = always wait)',
        min_value=0, max_value=10,
        value=int(int_cfg.get('auto_skip_test_max', 0)),
        key='cfg_auto_skip',
    )
    if auto_skip != int_cfg.get('auto_skip_test_max', 0):
        asm.save(['intervention', 'auto_skip_test_max'], auto_skip)

timeout_mins = st.slider(
    'Intervention timeout (minutes)',
    min_value=5, max_value=120,
    value=int(int_cfg.get('timeout_seconds', 1800)) // 60,
    key='cfg_int_timeout',
)
new_timeout = timeout_mins * 60
if new_timeout != int_cfg.get('timeout_seconds', 1800):
    asm.save(['intervention', 'timeout_seconds'], new_timeout)

st.markdown('---')

# ─────────────────────────────────────────────────────────────────────────────
# Auto-learn
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('### Auto-Learn')

auto_learn = st.checkbox(
    'Agents auto-append reflections after each task',
    value=bool(settings.get('auto_learn', False)),
    key='cfg_auto_learn',
)
if auto_learn != settings.get('auto_learn', False):
    asm.save('auto_learn', auto_learn)

st.caption(
    'When enabled, a brief reflection prompt runs after each completed task. '
    'The agent appends learnings to its role-specific notes file.'
)

# ─────────────────────────────────────────────────────────────────────────────
# Raw JSON view
# ─────────────────────────────────────────────────────────────────────────────
with st.expander('Raw settings JSON'):
    import json
    st.code(json.dumps(settings, indent=2), language='json')
