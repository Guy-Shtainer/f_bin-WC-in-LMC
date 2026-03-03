"""
agent_app/pages/05_notes.py — Agent Notes / Memory
───────────────────────────────────────────────────
View and edit per-role learning notes. Agents read these at startup
to build on previous experience.
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import streamlit as st

st.set_page_config(page_title='Agent Notes', page_icon='📝', layout='wide')

from shared import (
    inject_theme, render_sidebar, get_agent_settings_manager,
    AGENT_ROLES,
)
from agent_comm import get_notes, save_notes

inject_theme()
settings = render_sidebar('Agent Notes')
asm = get_agent_settings_manager()

st.markdown('# Agent Notes')
st.caption(
    'Agents read these notes at startup to learn your preferences. '
    'They also auto-append learnings after each completed task.'
)

# ─────────────────────────────────────────────────────────────────────────────
# Auto-learn toggle
# ─────────────────────────────────────────────────────────────────────────────
auto_learn = st.checkbox(
    'Auto-learn: agents append reflections after each task',
    value=bool(settings.get('auto_learn', False)),
    key='auto_learn_toggle',
)
if auto_learn != settings.get('auto_learn', False):
    asm.save('auto_learn', auto_learn)

st.markdown('---')

# ─────────────────────────────────────────────────────────────────────────────
# Role tabs
# ─────────────────────────────────────────────────────────────────────────────
all_roles = ['global'] + [r for r in AGENT_ROLES if r != 'global']
role_labels = [r.replace('_', ' ').title() for r in all_roles]

tabs = st.tabs(role_labels)

for tab, role in zip(tabs, all_roles):
    with tab:
        content = get_notes(role)

        # Edit mode
        edit_key = f'edit_mode_{role}'
        if edit_key not in st.session_state:
            st.session_state[edit_key] = False

        c1, c2, c3 = st.columns([1, 1, 4])
        with c1:
            if st.button(
                'Edit' if not st.session_state[edit_key] else 'View',
                key=f'toggle_{role}',
            ):
                st.session_state[edit_key] = not st.session_state[edit_key]
                st.rerun()
        with c2:
            if st.button('Clear', key=f'clear_{role}'):
                save_notes(role, '')
                st.success(f'Cleared {role} notes.')
                st.rerun()

        if st.session_state[edit_key]:
            edited = st.text_area(
                f'{role} notes',
                value=content,
                height=400,
                key=f'editor_{role}',
            )
            if st.button('Save', key=f'save_{role}', type='primary'):
                save_notes(role, edited)
                st.session_state[edit_key] = False
                st.success(f'Saved {role} notes.')
                st.rerun()
        else:
            if content.strip():
                st.markdown(content)
            else:
                st.caption(f'No notes yet for {role}. '
                           f'They will be auto-generated after tasks complete.')
