"""
agent_app/agent_comm.py
───────────────────────
Communication layer between the Agent Control Panel webapp and the
overnight_agent.py supervisor process. All interaction is file-based:
  - Read: .agent_state.json, agent_log.md, .agent_work/ artifacts, .agent_notes/
  - Write: .intervention.json, agent_settings.json
  - Process: launch / stop via subprocess
"""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_SCRIPTS = _ROOT / 'scripts'

# Key file paths
STATE_PATH   = _SCRIPTS / '.agent_state.json'
PID_PATH     = _SCRIPTS / '.agent.pid'
LOG_PATH     = _SCRIPTS / 'agent_log.md'
WORK_DIR     = _SCRIPTS / '.agent_work'
NOTES_DIR    = _SCRIPTS / '.agent_notes'
SETTINGS_PATH = _SCRIPTS / 'agent_settings.json'
TODO_PATH    = _ROOT / 'TODO.md'

AGENT_ROLES = [
    'global', 'planner', 'reviewer', 'implementer', 'tester',
    'regression', 'fix_planner', 'fix_implementer',
]

# ─────────────────────────────────────────────────────────────────────────────
# TODO.md parsing (mirrors scripts/overnight_agent.py — kept separate to avoid
# importing the full agent with its async/SDK deps)
# ─────────────────────────────────────────────────────────────────────────────

def _parse_bool(val: str) -> bool:
    return val.strip().lower() in ('y', 'yes', 'true', '1')


def _parse_table_rows(lines: list[str]) -> list[list[str]]:
    rows = []
    for line in lines:
        line = line.strip()
        if not line.startswith('|') or line.startswith('|--') or line.startswith('| --'):
            continue
        cells = [c.strip() for c in line.split('|')[1:-1]]
        if cells and all(c == '' or set(c) <= {'-', ' '} for c in cells):
            continue
        rows.append(cells)
    return rows


def load_todos() -> list[dict]:
    """Parse TODO.md and return open tasks as dicts."""
    if not TODO_PATH.exists():
        return []
    content = TODO_PATH.read_text(encoding='utf-8')
    open_tasks: list[dict] = []

    sections = re.split(r'^## ', content, flags=re.MULTILINE)
    for section in sections:
        if section.startswith('Open Tasks'):
            rows = _parse_table_rows(section.split('\n'))
            for cells in rows[1:] if len(rows) > 1 else []:
                if len(cells) >= 9:
                    open_tasks.append({
                        'id': int(cells[0]) if cells[0].isdigit() else 0,
                        'title': cells[1],
                        'description': cells[2],
                        'priority': cells[3].lower().strip(),
                        'tags': cells[4],
                        'status': cells[5].lower().strip(),
                        'added_by': cells[6],
                        'suggested_by': cells[7],
                        'date_added': cells[8],
                        'urgent': _parse_bool(cells[9]) if len(cells) > 9 else False,
                        'important': _parse_bool(cells[10]) if len(cells) > 10 else False,
                    })
    return open_tasks


def get_quadrant(task: dict) -> str:
    """Return Eisenhower quadrant name for a task."""
    u, i = task.get('urgent', False), task.get('important', False)
    if u and i:
        return 'do_first'
    if u and not i:
        return 'delegate'
    if not u and i:
        return 'schedule'
    return 'eliminate'


QUADRANT_LABELS = {
    'do_first': 'Do First',
    'delegate': 'Delegate',
    'schedule': 'Schedule',
    'eliminate': 'Eliminate',
}

QUADRANT_COLORS = {
    'do_first': '#E25A53',   # red
    'delegate': '#F5A623',   # amber
    'schedule': '#4A90D9',   # blue
    'eliminate': '#888888',  # grey
}


# ─────────────────────────────────────────────────────────────────────────────
# State
# ─────────────────────────────────────────────────────────────────────────────

def get_state() -> dict | None:
    """Read .agent_state.json. Returns None if missing or stale."""
    if not STATE_PATH.exists():
        return None
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def is_running() -> bool:
    """Check if the agent process is alive via PID file."""
    if not PID_PATH.exists():
        return False
    try:
        pid = int(PID_PATH.read_text().strip())
        os.kill(pid, 0)  # signal 0 = check if process exists
        return True
    except (ValueError, ProcessLookupError, PermissionError, OSError):
        return False


def get_pid() -> int | None:
    """Get the agent PID, or None."""
    if not PID_PATH.exists():
        return None
    try:
        return int(PID_PATH.read_text().strip())
    except (ValueError, OSError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Launch / Stop
# ─────────────────────────────────────────────────────────────────────────────

def launch_agent(
    quadrant: str = 'eliminate',
    max_tasks: int | None = None,
    include_critical: bool = False,
    freeform_task: str | None = None,
    task_ids: list[int] | None = None,
    wait_on_reject: bool = True,
    wait_on_fail: bool = True,
    intervention_timeout: int = 1800,
) -> tuple[bool, str]:
    """
    Launch overnight_agent.py as a background subprocess.
    Returns (success, message).
    """
    if is_running():
        return False, 'Agent is already running.'

    cmd = [
        sys.executable,  # same Python (conda env)
        str(_SCRIPTS / 'overnight_agent.py'),
        '--daemon',
    ]

    if freeform_task:
        cmd.extend(['--task', freeform_task])
    elif task_ids:
        cmd.extend(['--task-ids', ','.join(str(i) for i in task_ids)])
    else:
        cmd.extend(['--quadrant', quadrant])
        if max_tasks is not None:
            cmd.extend(['--max-tasks', str(max_tasks)])
        if include_critical:
            cmd.append('--include-critical')

    if wait_on_reject:
        cmd.append('--wait-on-reject')
    if wait_on_fail:
        cmd.append('--wait-on-fail')
    cmd.extend(['--intervention-timeout', str(intervention_timeout)])

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return True, f'Agent launched (PID {proc.pid}), quadrant={quadrant}'
    except Exception as e:
        return False, f'Failed to launch: {e}'


def stop_agent() -> bool:
    """Send SIGTERM to the agent process. Returns True if stopped."""
    pid = get_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        # Clean up PID file
        if PID_PATH.exists():
            PID_PATH.unlink(missing_ok=True)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        # Process already gone, clean up PID file
        if PID_PATH.exists():
            PID_PATH.unlink(missing_ok=True)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Log
# ─────────────────────────────────────────────────────────────────────────────

def get_log_full() -> str:
    """Read the full agent_log.md content."""
    if not LOG_PATH.exists():
        return ''
    try:
        return LOG_PATH.read_text(encoding='utf-8')
    except OSError:
        return ''


def get_log_tail(n_lines: int = 50) -> str:
    """Read last N lines of agent_log.md."""
    content = get_log_full()
    if not content:
        return ''
    lines = content.strip().split('\n')
    return '\n'.join(lines[-n_lines:])


# ─────────────────────────────────────────────────────────────────────────────
# Artifacts
# ─────────────────────────────────────────────────────────────────────────────

def list_task_dirs() -> list[dict]:
    """
    Scan .agent_work/ for task directories.
    Returns list of {id, path, artifacts: [filenames], mtime}.
    """
    if not WORK_DIR.exists():
        return []
    dirs = []
    for entry in sorted(WORK_DIR.iterdir()):
        if not entry.is_dir():
            continue
        try:
            task_id = int(entry.name)
        except ValueError:
            task_id = 0
        artifacts = sorted(
            f.name for f in entry.iterdir()
            if f.is_file() and f.suffix == '.md'
        )
        mtime = max(
            (f.stat().st_mtime for f in entry.iterdir() if f.is_file()),
            default=0,
        )
        dirs.append({
            'id': task_id,
            'path': str(entry),
            'artifacts': artifacts,
            'mtime': datetime.fromtimestamp(mtime).isoformat() if mtime else '',
        })
    return sorted(dirs, key=lambda d: d['id'], reverse=True)


def get_artifacts(task_id: int) -> dict[str, str]:
    """Read all .md files from .agent_work/{task_id}/. Returns {filename: content}."""
    task_dir = WORK_DIR / str(task_id)
    if not task_dir.exists():
        return {}
    result = {}
    for f in sorted(task_dir.iterdir()):
        if f.is_file() and f.suffix == '.md':
            try:
                result[f.name] = f.read_text(encoding='utf-8')
            except OSError:
                result[f.name] = '[Error reading file]'
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Interventions
# ─────────────────────────────────────────────────────────────────────────────

def write_intervention(task_id: int, intervention: dict) -> bool:
    """
    Write .intervention.json for the agent to pick up.
    intervention dict should have keys: action, guidance (optional), max_retries (optional).
    Returns True on success.
    """
    task_dir = WORK_DIR / str(task_id)
    task_dir.mkdir(parents=True, exist_ok=True)
    path = task_dir / '.intervention.json'
    intervention['timestamp'] = datetime.now().isoformat()
    try:
        with open(path, 'w') as f:
            json.dump(intervention, f, indent=2)
        return True
    except OSError:
        return False


def get_intervention_status() -> dict | None:
    """Check if agent is awaiting intervention. Returns state dict or None."""
    state = get_state()
    if state and state.get('awaiting_intervention'):
        return state
    return None


def has_pending_intervention(task_id: int) -> bool:
    """Check if an intervention file exists that hasn't been consumed yet."""
    path = WORK_DIR / str(task_id) / '.intervention.json'
    return path.exists()


# ─────────────────────────────────────────────────────────────────────────────
# Branches
# ─────────────────────────────────────────────────────────────────────────────

def _git(*args: str, check: bool = True) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ['git'] + list(args),
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise RuntimeError(f'git {" ".join(args)}: {result.stderr.strip()}')
    return result.stdout.strip()


def list_branches() -> list[dict]:
    """List all agent/* branches with metadata."""
    try:
        raw = _git('branch', '--list', 'agent/*', '--format',
                    '%(refname:short)|%(committerdate:iso)')
    except RuntimeError:
        return []
    if not raw:
        return []
    branches = []
    for line in raw.split('\n'):
        if '|' not in line:
            continue
        name, date_str = line.split('|', 1)
        name = name.strip()
        # Count commits relative to main
        try:
            log = _git('log', '--oneline', f'main..{name}', check=False)
            commit_count = len(log.strip().split('\n')) if log.strip() else 0
        except RuntimeError:
            commit_count = 0
        # Diff stat
        try:
            stat = _git('diff', '--stat', f'main...{name}', check=False)
        except RuntimeError:
            stat = ''
        # Extract task ID from branch name: agent/{id}-{slug}
        task_id = 0
        parts = name.replace('agent/', '').split('-', 1)
        if parts and parts[0].isdigit():
            task_id = int(parts[0])
        branches.append({
            'name': name,
            'task_id': task_id,
            'date': date_str.strip(),
            'commits': commit_count,
            'stat': stat,
        })
    return branches


def get_branch_log(branch: str) -> str:
    """Get commit log for a branch relative to main."""
    try:
        return _git('log', '--oneline', '--decorate', f'main..{branch}')
    except RuntimeError:
        return ''


def get_branch_diff(branch: str) -> str:
    """Get full diff of branch vs main."""
    try:
        return _git('diff', f'main...{branch}')
    except RuntimeError:
        return ''


def merge_branch(branch: str) -> tuple[bool, str]:
    """Merge a branch into main. Returns (success, message)."""
    try:
        _git('checkout', 'main')
        _git('merge', branch, '--no-edit')
        return True, f'Merged {branch} into main.'
    except RuntimeError as e:
        # Try to return to main on error
        try:
            _git('merge', '--abort', check=False)
            _git('checkout', 'main', check=False)
        except RuntimeError:
            pass
        return False, f'Merge failed: {e}'


def discard_branch(branch: str) -> tuple[bool, str]:
    """Delete a branch and clean up its work directory."""
    try:
        # Extract task ID for cleanup
        parts = branch.replace('agent/', '').split('-', 1)
        task_id = parts[0] if parts and parts[0].isdigit() else None

        _git('branch', '-D', branch)

        # Clean up work directory
        if task_id:
            work_path = WORK_DIR / task_id
            if work_path.exists():
                import shutil
                shutil.rmtree(work_path)

        return True, f'Discarded {branch}.'
    except RuntimeError as e:
        return False, f'Failed to discard: {e}'


# ─────────────────────────────────────────────────────────────────────────────
# Agent Notes
# ─────────────────────────────────────────────────────────────────────────────

def get_notes(role: str) -> str:
    """Read .agent_notes/{role}_notes.md. Returns empty string if missing."""
    if role == 'global':
        path = NOTES_DIR / 'global_notes.md'
    else:
        path = NOTES_DIR / f'{role}_notes.md'
    if not path.exists():
        return ''
    try:
        return path.read_text(encoding='utf-8')
    except OSError:
        return ''


def save_notes(role: str, content: str) -> None:
    """Write .agent_notes/{role}_notes.md."""
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    if role == 'global':
        path = NOTES_DIR / 'global_notes.md'
    else:
        path = NOTES_DIR / f'{role}_notes.md'
    path.write_text(content, encoding='utf-8')


# ─────────────────────────────────────────────────────────────────────────────
# Agent Settings (disk-level, no Streamlit dependency)
# ─────────────────────────────────────────────────────────────────────────────

def load_agent_settings() -> dict:
    """Read agent_settings.json. Returns defaults if missing."""
    from shared import _DEFAULTS
    if not SETTINGS_PATH.exists():
        return dict(_DEFAULTS)
    try:
        with open(SETTINGS_PATH) as f:
            loaded = json.load(f)
        merged = {**_DEFAULTS}
        for k, v in loaded.items():
            if isinstance(v, dict) and isinstance(merged.get(k), dict):
                merged[k] = {**merged[k], **v}
            else:
                merged[k] = v
        return merged
    except (json.JSONDecodeError, OSError):
        return dict(_DEFAULTS)


def save_agent_settings(settings: dict) -> None:
    """Write agent_settings.json."""
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, 'w') as f:
        json.dump(settings, f, indent=2, default=str)
