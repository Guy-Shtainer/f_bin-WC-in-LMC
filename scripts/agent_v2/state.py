"""State persistence for webapp monitoring — file-based IPC."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent  # scripts/
_STATE_PATH = _HERE / '.agent_state.json'
_LOG_PATH = _HERE / 'agent_log.md'
_PID_PATH = _HERE / '.agent.pid'
_COMPLETED_PATH = _HERE / '.agent_completed.json'

_daemon_mode = False
_last_log_msg = ''
_last_log_ts = ''


# ── State file ────────────────────────────────────────────────────────────────

def save_state(state: dict) -> None:
    """Write state dict to .agent_state.json for webapp to read."""
    state['version'] = 2
    state['updated_at'] = datetime.now().isoformat()
    _STATE_PATH.write_text(json.dumps(state, indent=2), encoding='utf-8')


def load_state() -> dict | None:
    if _STATE_PATH.exists():
        try:
            return json.loads(_STATE_PATH.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            pass
    return None


def clear_state() -> None:
    _STATE_PATH.unlink(missing_ok=True)


def update_phase(task: dict, phase: str, phase_round: int = 0,
                 phases_done: list[str] | None = None, **extra) -> None:
    """Update state with current phase info — called at each phase transition."""
    state = load_state() or {}
    state.update({
        'task_id': task.get('id', 0),
        'task_title': task.get('title', ''),
        'phase': phase,
        'phase_round': phase_round,
        'live_output': str(_HERE / '.agent_live_output.txt'),
    })
    if phases_done is not None:
        state['phases_done'] = phases_done
    state.update(extra)
    save_state(state)


# ── Completed tasks (survives crashes) ────────────────────────────────────────

def load_completed_ids() -> list[int]:
    if _COMPLETED_PATH.exists():
        try:
            data = json.loads(_COMPLETED_PATH.read_text(encoding='utf-8'))
            return data.get('completed_ids', [])
        except (json.JSONDecodeError, OSError):
            pass
    return []


def save_completed_id(task_id: int) -> None:
    ids = load_completed_ids()
    if task_id not in ids:
        ids.append(task_id)
    _COMPLETED_PATH.write_text(
        json.dumps({'completed_ids': ids, 'updated': datetime.now().isoformat()},
                   indent=2),
        encoding='utf-8'
    )


def clear_completed_ids() -> None:
    _COMPLETED_PATH.unlink(missing_ok=True)


# ── PID file ──────────────────────────────────────────────────────────────────

def write_pid() -> None:
    import os
    _PID_PATH.write_text(str(os.getpid()), encoding='utf-8')


def read_pid() -> int | None:
    if _PID_PATH.exists():
        try:
            return int(_PID_PATH.read_text().strip())
        except (ValueError, OSError):
            pass
    return None


def clear_pid() -> None:
    _PID_PATH.unlink(missing_ok=True)


def is_running() -> bool:
    """Check if an agent process is currently running."""
    import os
    pid = read_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)  # Signal 0 = check existence
        return True
    except OSError:
        clear_pid()
        return False


# ── Logging ───────────────────────────────────────────────────────────────────

def set_daemon_mode(enabled: bool) -> None:
    global _daemon_mode
    _daemon_mode = enabled


def log(msg: str) -> None:
    global _last_log_msg, _last_log_ts
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if msg == _last_log_msg and ts == _last_log_ts:
        return
    _last_log_msg, _last_log_ts = msg, ts
    line = f'[{ts}] {msg}'
    if _daemon_mode:
        print(line, flush=True)
    else:
        print(line, flush=True)
        with open(_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(line + '\n')


def log_session_start(quadrant: str) -> None:
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    header = (
        f'\n## Agent v2 Session — {ts}\n'
        f'**Quadrant:** {quadrant}\n\n'
    )
    with open(_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(header)


def log_task_result(task: dict, branch: str, status: str, summary: str) -> None:
    entry = (
        f'### Task #{task.get("id", "?")}: {task.get("title", "?")}\n'
        f'- **Branch:** `{branch}`\n'
    )
    if task.get('description'):
        entry += f'- **Prompt:** {task["description"][:300]}\n'
    entry += (
        f'- **Status:** {status}\n'
        f'- **Summary:** {summary[:500]}\n'
        f'- **UNSUPERVISED — needs human review and testing**\n\n'
    )
    with open(_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(entry)
