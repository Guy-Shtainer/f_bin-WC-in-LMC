"""
pages/13_tests_verification.py — Tests & Verification page.
Discovers scripts/test_*.py, runs them in subprocesses with live stdout,
and persists last-run results across sessions.
"""
from __future__ import annotations
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import streamlit as st

from shared import inject_theme, render_sidebar, get_settings_manager
from _tests_verification_helpers import (
    discover_tests,
    any_running,
    drain_completed,
    render_summary_table,
    render_run_panel,
    run_all_tick,
)

st.set_page_config(
    page_title='Tests & Verification — WR Binary',
    page_icon='🧪',
    layout='wide',
)
inject_theme()
settings = render_sidebar('Tests & Verification')
sm = get_settings_manager()

# ─── Session-state init (idempotent) ────────────────────────────────────────
st.session_state.setdefault('tests_runs', {})
st.session_state.setdefault('tests_run_all_queue', [])

# Drain completed runs from in-memory state into persisted last_runs.
drain_completed(sm)

# ─── Title ──────────────────────────────────────────────────────────────────
st.markdown('# 🧪 Tests & Verification')
st.caption(
    'Run and inspect verification scripts. Each script exits 0 on success, '
    'non-zero on failure.'
)

# ─── Discover scripts ───────────────────────────────────────────────────────
tests = discover_tests()
if not tests:
    st.warning('No scripts/test_*.py files found.')
    st.stop()
script_names = [p.name for p in tests]

# ─── Top action row ─────────────────────────────────────────────────────────
runs = st.session_state['tests_runs']
busy = any_running(runs) or bool(st.session_state['tests_run_all_queue'])

c1, c2, _ = st.columns([1, 1, 6])
if c1.button('Run all (sequential)', disabled=busy, key='tests_run_all_btn'):
    st.session_state['tests_run_all_queue'] = list(script_names)
    st.rerun()
if c2.button('Refresh', key='tests_refresh_btn'):
    st.rerun()

# ─── Summary table ──────────────────────────────────────────────────────────
render_summary_table(tests, settings, runs)

# ─── Focused-test selectbox ─────────────────────────────────────────────────
saved_sel = settings.get('tests', {}).get('selected_test')
default_idx = script_names.index(saved_sel) if saved_sel in script_names else 0
selected = st.selectbox(
    'Focused test',
    options=script_names,
    index=default_idx,
    key='tests_selected_test',
    on_change=lambda: sm.save(
        ['tests', 'selected_test'],
        value=st.session_state['tests_selected_test'],
    ),
    disabled=busy,
)
selected_path = next(p for p in tests if p.name == selected)

# ─── Tabs: Source / Run ─────────────────────────────────────────────────────
source_tab, run_tab = st.tabs(['Source', 'Run'])

with source_tab:
    try:
        src = selected_path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as e:
        st.error(f'Could not read source: {e}')
    else:
        with st.container(height=600):
            st.code(src, language='python', line_numbers=True)

with run_tab:
    render_run_panel(selected_path, sm)

# ─── Sequential run-all driver ──────────────────────────────────────────────
run_all_tick(sm)
