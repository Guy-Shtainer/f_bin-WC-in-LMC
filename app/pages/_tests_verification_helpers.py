"""
_tests_verification_helpers.py — runner, state, persistence, and rendering
helpers for pages/13_tests_verification.py.
Underscore prefix excludes this module from Streamlit's multipage discovery.
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import TypedDict

import pandas as pd
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

PROJECT_ROOT = Path(_ROOT)
SCRIPTS_DIR = PROJECT_ROOT / 'scripts'

S_PASS, S_FAIL, S_RUN, S_STOP, S_NONE = 'PASS', 'FAIL', 'RUNNING', 'STOPPED', '—'


class RunState(TypedDict, total=False):
    thread: threading.Thread
    proc: subprocess.Popen
    queue: 'queue.Queue[str]'
    output: str
    status: str          # 'running' | 'done' | 'stopped'
    exit_code: int | None
    t_start: float
    t_end: float | None
    timestamp: str
    persisted: bool


# ─────────────────────────────────────────────────────────────────────────────
# Discovery
# ─────────────────────────────────────────────────────────────────────────────

def discover_tests() -> list[Path]:
    if not SCRIPTS_DIR.is_dir():
        return []
    return sorted(SCRIPTS_DIR.glob('test_*.py'))


# ─────────────────────────────────────────────────────────────────────────────
# Subprocess runner
# ─────────────────────────────────────────────────────────────────────────────

def _build_cmd(script_path: Path) -> list[str]:
    return [
        'conda', 'run', '--no-capture-output', '-n', 'guyenv',
        'python', '-u', str(script_path),
    ]


def _runner_thread(state: RunState, cmd: list[str]) -> None:
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except (OSError, FileNotFoundError) as e:
        state['queue'].put(f'[runner error] {e}\n')
        state['status'] = 'done'
        state['exit_code'] = -1
        state['t_end'] = datetime.now().timestamp()
        return

    state['proc'] = proc
    if proc.stdout is not None:
        for line in iter(proc.stdout.readline, ''):
            state['queue'].put(line)
        proc.stdout.close()
    proc.wait()
    state['exit_code'] = proc.returncode
    state['t_end'] = datetime.now().timestamp()
    if state.get('status') != 'stopped':
        state['status'] = 'done'


def start_run(script_path: Path) -> None:
    runs = st.session_state.setdefault('tests_runs', {})
    name = script_path.name
    state: RunState = {
        'queue': queue.Queue(),
        'output': '',
        'status': 'running',
        'exit_code': None,
        't_start': datetime.now().timestamp(),
        't_end': None,
        'timestamp': datetime.now().isoformat(timespec='seconds'),
        'persisted': False,
    }
    runs[name] = state
    t = threading.Thread(
        target=_runner_thread, args=(state, _build_cmd(script_path)), daemon=True,
    )
    state['thread'] = t
    t.start()


def stop_run(state: RunState) -> None:
    proc = state.get('proc')
    if proc is None:
        return
    state['status'] = 'stopped'
    try:
        proc.terminate()
    except (ProcessLookupError, OSError):
        return

    def _watchdog(p: subprocess.Popen) -> None:
        try:
            p.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                p.kill()
            except (ProcessLookupError, OSError):
                pass

    threading.Thread(target=_watchdog, args=(proc,), daemon=True).start()


def drain_queue(state: RunState) -> None:
    q = state.get('queue')
    if q is None:
        return
    chunks = []
    try:
        while True:
            chunks.append(q.get_nowait())
    except queue.Empty:
        pass
    if chunks:
        state['output'] = state.get('output', '') + ''.join(chunks)


# ─────────────────────────────────────────────────────────────────────────────
# Persistence
# ─────────────────────────────────────────────────────────────────────────────

def _persist_one(sm, script_name: str, state: RunState) -> None:
    settings = sm.load()
    last_runs = dict(settings.get('tests', {}).get('last_runs', {}))
    duration = (state.get('t_end') or 0.0) - state.get('t_start', 0.0)
    tail = '\n'.join(state.get('output', '').splitlines()[-50:])
    if state.get('status') == 'stopped':
        status_label = S_STOP
    else:
        status_label = S_PASS if state.get('exit_code') == 0 else S_FAIL
    last_runs[script_name] = {
        'exit_code': state.get('exit_code'),
        'duration_s': float(duration),
        'timestamp_iso': state.get('timestamp', ''),
        'stdout_tail': tail,
        'status': status_label,
    }
    sm.save(['tests', 'last_runs'], value=last_runs)


def drain_completed(sm) -> None:
    """Persist any in-memory runs that have finished but not yet been saved."""
    runs = st.session_state.get('tests_runs', {})
    for name, state in runs.items():
        drain_queue(state)
        if state.get('status') in ('done', 'stopped') and not state.get('persisted'):
            _persist_one(sm, name, state)
            state['persisted'] = True


def any_running(runs: dict) -> bool:
    return bool(any(s.get('status') == 'running' for s in runs.values()))


# ─────────────────────────────────────────────────────────────────────────────
# Rendering
# ─────────────────────────────────────────────────────────────────────────────

def _row_tint_styler(df: pd.DataFrame):
    def _color(row):
        s = row['Last status']
        if s == S_PASS:
            bg = 'background-color: rgba(82, 183, 136, 0.18);'
        elif s == S_FAIL:
            bg = 'background-color: rgba(226, 90, 83, 0.18);'
        elif s == S_RUN:
            bg = 'background-color: rgba(218, 165, 32, 0.18);'
        else:
            bg = ''
        return [bg] * len(row)
    return df.style.apply(_color, axis=1)


def render_summary_table(tests: list[Path], settings: dict, runs: dict) -> None:
    last_runs = settings.get('tests', {}).get('last_runs', {})
    rows = []
    for p in tests:
        name = p.name
        live = runs.get(name, {})
        live_status = live.get('status')
        if live_status == 'running':
            status = S_RUN
            duration = f'{datetime.now().timestamp() - live.get("t_start", 0.0):.1f}'
            ts = live.get('timestamp', '')
        else:
            persisted = last_runs.get(name, {})
            status = persisted.get('status', S_NONE)
            d = persisted.get('duration_s')
            duration = f'{d:.1f}' if isinstance(d, (int, float)) else S_NONE
            ts = persisted.get('timestamp_iso', '') or S_NONE
        try:
            line_count = sum(1 for _ in p.open('r', encoding='utf-8', errors='replace'))
        except OSError:
            line_count = 0
        rows.append({
            'Script': name,
            'Lines': line_count,
            'Last status': status,
            'Last duration (s)': duration,
            'Last run': ts,
        })
    df = pd.DataFrame(rows)
    st.dataframe(_row_tint_styler(df), use_container_width=True, hide_index=True)


def render_run_panel(script_path: Path, sm) -> None:
    runs = st.session_state.setdefault('tests_runs', {})
    name = script_path.name
    state = runs.get(name, {})
    is_running = state.get('status') == 'running'

    c1, c2, _ = st.columns([1, 1, 6])
    if c1.button('Run', key=f'tests_run_{name}', disabled=is_running):
        start_run(script_path)
        st.rerun()
    if c2.button('Stop', key=f'tests_stop_{name}', disabled=not is_running):
        stop_run(state)
        st.rerun()

    if is_running:
        _live_block(name)
    else:
        _static_block(state, sm, name)


@st.fragment(run_every=0.5)
def _live_block(name: str) -> None:
    runs = st.session_state.get('tests_runs', {})
    state = runs.get(name, {})
    drain_queue(state)
    elapsed = datetime.now().timestamp() - state.get('t_start', 0.0)
    st.info(f'{S_RUN} — elapsed {elapsed:.1f} s')
    with st.container(height=420):
        st.code(state.get('output', '') or '(no output yet)', language='text')
    if state.get('status') != 'running':
        st.rerun()


def _static_block(state: dict, sm, name: str) -> None:
    if not state:
        settings = sm.load()
        persisted = settings.get('tests', {}).get('last_runs', {}).get(name, {})
        if persisted:
            label = persisted.get('status', S_NONE)
            dur = persisted.get('duration_s')
            ts = persisted.get('timestamp_iso', '')
            if isinstance(dur, (int, float)):
                st.write(f'Last result: **{label}** — {dur:.1f}s @ {ts}')
            else:
                st.write(f'Last result: **{label}**')
            tail = persisted.get('stdout_tail', '')
            if tail:
                with st.container(height=420):
                    st.code(tail, language='text')
        else:
            st.write('No prior run on record.')
        return

    status = state.get('status')
    exit_code = state.get('exit_code')
    duration = (state.get('t_end') or 0.0) - state.get('t_start', 0.0)
    if status == 'stopped':
        st.warning(f'{S_STOP} — exit {exit_code} after {duration:.1f}s')
    elif exit_code == 0:
        st.success(f'{S_PASS} — finished in {duration:.1f}s')
    else:
        st.error(f'{S_FAIL} — exit {exit_code} after {duration:.1f}s')
    with st.container(height=420):
        st.code(state.get('output', '') or '(no output)', language='text')


# ─────────────────────────────────────────────────────────────────────────────
# Sequential run-all driver
# ─────────────────────────────────────────────────────────────────────────────

def run_all_tick(sm) -> None:
    q = st.session_state.get('tests_run_all_queue', [])
    runs = st.session_state.get('tests_runs', {})
    if not q or any_running(runs):
        return
    next_name = q.pop(0)
    st.session_state['tests_run_all_queue'] = q
    target = next((p for p in discover_tests() if p.name == next_name), None)
    if target is None:
        return
    start_run(target)
    st.rerun()
