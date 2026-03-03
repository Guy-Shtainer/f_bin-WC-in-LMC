"""
agent_app/pages/04_interventions.py — Human-in-the-Loop Controls
────────────────────────────────────────────────────────────────
When the agent awaits input (reviewer rejection, test failure), this page
lets you approve, guide, edit, or abort.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st
from streamlit_autorefresh import st_autorefresh

st.set_page_config(page_title='Interventions', page_icon='🖐️', layout='wide')

from shared import (
    inject_theme, render_sidebar, get_agent_settings_manager,
    COLOR_WAITING, COLOR_DONE,
)
from agent_comm import (
    get_state, get_intervention_status, write_intervention,
    get_artifacts, has_pending_intervention,
)

inject_theme()
settings = render_sidebar('Interventions')
asm = get_agent_settings_manager()

st_autorefresh(interval=5000, limit=None, key='intervention_refresh')

st.markdown('# Interventions')

# ─────────────────────────────────────────────────────────────────────────────
# Current intervention status
# ─────────────────────────────────────────────────────────────────────────────
state = get_intervention_status()

if state is None:
    st.info('No intervention needed. Agent is running autonomously (or stopped).')

    # Show auto-intervention rules
    st.markdown('---')
    st.markdown('### Auto-Intervention Rules')
    st.caption('These rules apply when the agent is running.')

    int_cfg = settings.get('intervention', {})

    c1, c2 = st.columns(2)
    with c1:
        auto_replan = st.number_input(
            'Auto-replan on rejection (0 = disabled)',
            min_value=0, max_value=5,
            value=int(int_cfg.get('auto_replan_max', 0)),
            key='auto_replan_max',
        )
        if auto_replan != int_cfg.get('auto_replan_max', 0):
            asm.save(['intervention', 'auto_replan_max'], auto_replan)

    with c2:
        auto_skip = st.number_input(
            'Auto-skip test after N fix attempts (0 = disabled)',
            min_value=0, max_value=5,
            value=int(int_cfg.get('auto_skip_test_max', 0)),
            key='auto_skip_test_max',
        )
        if auto_skip != int_cfg.get('auto_skip_test_max', 0):
            asm.save(['intervention', 'auto_skip_test_max'], auto_skip)

    st.stop()

# ─────────────────────────────────────────────────────────────────────────────
# Active intervention
# ─────────────────────────────────────────────────────────────────────────────
tid = state['current_task_id']
itype = state.get('intervention_type', 'unknown')
current_stage = state.get('current_stage', '?')

st.markdown(f"""
<div class="intervention-banner">
    <div class="title">Intervention Required</div>
    <div class="detail">
        Task #{tid} | Stage: {current_stage} | Type: {itype}
    </div>
</div>
""", unsafe_allow_html=True)

# Check for pending (already submitted) intervention
if has_pending_intervention(tid):
    st.warning('An intervention response is already pending. '
               'The agent will pick it up shortly.')
    st.stop()

# Show relevant artifact for context
artifacts = get_artifacts(tid)

if 'reviewer_rejected' in itype:
    # Show the review
    review = artifacts.get('review.md', '')
    if review:
        with st.expander('Review details (why it was rejected)', expanded=True):
            st.markdown(review)

    # Show the plan
    plan_content = artifacts.get('plan.md', '')

    st.markdown('### Choose an action')

    action = st.radio(
        'What should the agent do?',
        [
            'Replan with guidance',
            'Override: approve plan anyway',
            'Edit plan manually',
            'Abort this task',
        ],
        key='intervention_action',
    )

    if action == 'Replan with guidance':
        guidance = st.text_area(
            'Guidance for the planner',
            placeholder='Consider using X approach instead of Y...',
            key='replan_guidance',
        )
        max_retries = st.slider(
            'Max re-plan attempts', 1, 5, 2, key='replan_retries',
        )
        if st.button('Submit', type='primary'):
            write_intervention(tid, {
                'action': 'replan_with_guidance',
                'guidance': guidance,
                'max_retries': max_retries,
            })
            st.success('Intervention submitted: replan with guidance.')
            st.rerun()

    elif action == 'Override: approve plan anyway':
        st.warning('This will skip the reviewer and proceed to implementation.')
        if st.button('Approve Plan', type='primary'):
            write_intervention(tid, {'action': 'approve_override'})
            st.success('Intervention submitted: plan approved.')
            st.rerun()

    elif action == 'Edit plan manually':
        if plan_content:
            edited = st.text_area(
                'Edit plan.md',
                value=plan_content,
                height=400,
                key='edit_plan',
            )
            if st.button('Save and approve', type='primary'):
                write_intervention(tid, {
                    'action': 'edit_plan',
                    'plan_content': edited,
                })
                st.success('Intervention submitted: edited plan.')
                st.rerun()
        else:
            st.error('No plan.md found to edit.')

    elif action == 'Abort this task':
        st.error('This will cancel the task and move to the next one.')
        if st.button('Confirm Abort', type='primary'):
            write_intervention(tid, {'action': 'abort'})
            st.success('Intervention submitted: task aborted.')
            st.rerun()

elif 'tester_failed' in itype:
    # Show test report
    test_reports = {k: v for k, v in artifacts.items() if 'test' in k.lower()}
    if test_reports:
        latest_report = list(test_reports.values())[-1]
        with st.expander('Test report (why it failed)', expanded=True):
            st.markdown(latest_report)

    st.markdown('### Choose an action')

    action = st.radio(
        'What should the agent do?',
        [
            'Retry fix with guidance',
            'Skip test failure (proceed anyway)',
            'Abort this task',
        ],
        key='test_intervention_action',
    )

    if action == 'Retry fix with guidance':
        guidance = st.text_area(
            'Guidance for the fix',
            placeholder='The issue is likely in X...',
            key='fix_guidance',
        )
        if st.button('Submit', type='primary'):
            write_intervention(tid, {
                'action': 'retry_with_guidance',
                'guidance': guidance,
            })
            st.success('Intervention submitted: retry with guidance.')
            st.rerun()

    elif action == 'Skip test failure (proceed anyway)':
        st.warning('This will mark the task as completed despite test failure.')
        if st.button('Skip', type='primary'):
            write_intervention(tid, {'action': 'skip_stage'})
            st.success('Intervention submitted: skipping test.')
            st.rerun()

    elif action == 'Abort this task':
        if st.button('Confirm Abort', type='primary'):
            write_intervention(tid, {'action': 'abort'})
            st.success('Intervention submitted: task aborted.')
            st.rerun()

else:
    st.warning(f'Unknown intervention type: {itype}')
    guidance = st.text_area('Provide guidance', key='generic_guidance')
    if st.button('Submit guidance', type='primary'):
        write_intervention(tid, {
            'action': 'provide_guidance',
            'guidance': guidance,
        })
        st.success('Guidance submitted.')
        st.rerun()
