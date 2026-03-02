#!/usr/bin/env python3
"""
overnight_agent.py — Autonomous overnight agent for WR Binary project.

Reads TODO.md, picks low-priority tasks, runs Claude to complete them,
handles rate limits by sleeping and resuming, creates safe git branches
for each task, and logs everything for easy review.

Quick start:
    conda run -n guyenv python scripts/overnight_agent.py

Options:
    --daemon              Run detached in background
    --quadrant X          Which tasks: eliminate (default), delegate, schedule, do_first, all
    --include-critical    Allow working on "Do First" (urgent+important) tasks
    --dry-run             Show what it would do without doing it
    --stop                Stop a running daemon
    --max-tasks N         Stop after completing N tasks
    --task "prompt"       Free-form task (skip TODO.md — e.g. paper writing, maintenance)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_TODO_PATH = _ROOT / 'TODO.md'
_DOC_PATH = _ROOT / 'DOCUMENTATION.md'
_STATE_PATH = _HERE / '.agent_state.json'
_LOG_PATH = _HERE / 'agent_log.md'
_PID_PATH = _HERE / '.agent.pid'
_CLAUDE_MD = _ROOT / 'CLAUDE.md'

# ── Constants ─────────────────────────────────────────────────────────────────
RATE_LIMIT_SLEEP = 300  # 5 minutes default, adjusted by retry-after if available
MAX_CONSECUTIVE_ERRORS = 3

ALLOWED_TOOLS = [
    'Read', 'Write', 'Edit', 'Glob', 'Grep',
    'Bash(conda run*)', 'Bash(python*)', 'Bash(git status*)',
    'Bash(git diff*)', 'Bash(git log*)', 'Bash(git add*)',
    'Bash(git commit*)', 'Bash(git branch*)', 'Bash(git checkout*)',
    'Bash(git tag*)', 'Bash(git stash*)', 'Bash(ls*)',
    'Bash(mkdir*)', 'Bash(cp*)',
    'WebSearch', 'WebFetch',
    'TodoWrite', 'Task', 'NotebookEdit',
]

QUADRANT_FILTERS = {
    'eliminate': lambda t: not t.get('urgent') and not t.get('important'),
    'delegate': lambda t: t.get('urgent') and not t.get('important'),
    'schedule': lambda t: not t.get('urgent') and t.get('important'),
    'do_first': lambda t: t.get('urgent') and t.get('important'),
}

# Processing order for --quadrant all (safest first)
QUADRANT_ORDER = ['eliminate', 'delegate', 'schedule']


# ── TODO.md parsing (reuse same logic as 10_todo.py) ─────────────────────────
def _parse_bool(val: str) -> bool:
    return val.strip().lower() in ('y', 'yes', 'true', '1')


def _bool_str(val: bool) -> str:
    return 'Y' if val else 'N'


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


def load_todos() -> tuple[list[dict], list[dict]]:
    if not _TODO_PATH.exists():
        return [], []
    content = _TODO_PATH.read_text(encoding='utf-8')
    open_tasks, done_tasks = [], []

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
        elif section.startswith('Done'):
            rows = _parse_table_rows(section.split('\n'))
            for cells in rows[1:] if len(rows) > 1 else []:
                if len(cells) >= 12:
                    done_tasks.append({
                        'id': int(cells[0]) if cells[0].isdigit() else 0,
                        'title': cells[1],
                        'description': cells[2],
                        'priority': cells[3].lower().strip(),
                        'tags': cells[4],
                        'added_by': cells[6],
                        'suggested_by': cells[7],
                        'date_added': cells[8],
                        'urgent': _parse_bool(cells[9]),
                        'important': _parse_bool(cells[10]),
                        'date_done': cells[11],
                    })
                elif len(cells) >= 3:
                    done_tasks.append({
                        'id': int(cells[0]) if cells[0].isdigit() else 0,
                        'title': cells[1],
                        'date_done': cells[2],
                    })
    return open_tasks, done_tasks


def save_todos(open_tasks: list[dict], done_tasks: list[dict]) -> None:
    priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
    open_tasks.sort(key=lambda t: priority_order.get(t.get('priority', 'low'), 3))

    lines = ['# Project To-Do List\n', '\n## Open Tasks\n']
    lines.append(
        '| ID | Title | Description | Priority | Tags | Status '
        '| Added by | Suggested by | Date added | Urgent | Important |'
    )
    lines.append(
        '|----|-------|-------------|----------|------|--------'
        '|----------|-------------|------------|--------|-----------|'
    )
    for t in open_tasks:
        lines.append(
            f"| {t['id']} | {t['title']} | {t.get('description', '')} "
            f"| {t.get('priority', 'medium')} | {t.get('tags', '')} "
            f"| {t.get('status', 'open')} | {t.get('added_by', '')} "
            f"| {t.get('suggested_by', '')} | {t.get('date_added', '')} "
            f"| {_bool_str(t.get('urgent', False))} "
            f"| {_bool_str(t.get('important', False))} |"
        )

    lines.append('\n## Done\n')
    lines.append(
        '| ID | Title | Description | Priority | Tags | Status '
        '| Added by | Suggested by | Date added | Urgent | Important | Date done |'
    )
    lines.append(
        '|----|-------|-------------|----------|------|--------'
        '|----------|-------------|------------|--------|-----------|-----------|'
    )
    for t in done_tasks:
        lines.append(
            f"| {t['id']} | {t['title']} | {t.get('description', '')} "
            f"| {t.get('priority', 'medium')} | {t.get('tags', '')} "
            f"| done | {t.get('added_by', '')} "
            f"| {t.get('suggested_by', '')} | {t.get('date_added', '')} "
            f"| {_bool_str(t.get('urgent', False))} "
            f"| {_bool_str(t.get('important', False))} "
            f"| {t.get('date_done', '')} |"
        )
    lines.append('')
    _TODO_PATH.write_text('\n'.join(lines), encoding='utf-8')


# ── Git helpers ───────────────────────────────────────────────────────────────
def git(*args: str) -> str:
    result = subprocess.run(
        ['git'] + list(args),
        cwd=str(_ROOT), capture_output=True, text=True
    )
    if result.returncode != 0:
        raise RuntimeError(f'git {" ".join(args)} failed: {result.stderr.strip()}')
    return result.stdout.strip()


def git_checkpoint() -> str:
    ts = datetime.now().strftime('%Y%m%d-%H%M')
    tag = f'pre-agent-{ts}'
    try:
        git('tag', tag)
    except RuntimeError:
        pass  # Tag already exists (re-run in same minute)
    return tag


def git_create_branch(task: dict) -> str:
    slug = re.sub(r'[^a-z0-9]+', '-', task['title'].lower())[:40].strip('-')
    branch = f'agent/{task["id"]}-{slug}'

    # Stash any uncommitted changes (e.g. agent_log.md from dry runs)
    has_stash = False
    status = git('status', '--porcelain')
    if status.strip():
        git('stash', '--include-untracked')
        has_stash = True

    try:
        git('checkout', '-b', branch)
    except RuntimeError:
        # Branch exists — check if it has commits ahead of main
        try:
            ahead = git('rev-list', '--count', f'main..{branch}')
            if int(ahead.strip()) == 0:
                # Empty branch from a crashed run — delete and recreate
                git('branch', '-D', branch)
                git('checkout', '-b', branch)
            else:
                # Has real work — just check it out
                git('checkout', branch)
        except RuntimeError:
            git('checkout', branch)

    # Restore stashed changes
    if has_stash:
        try:
            git('stash', 'pop')
        except RuntimeError:
            pass  # stash pop conflict — not critical

    return branch


def git_commit_agent(task: dict, summary: str) -> None:
    git('add', '-A')
    # Check if there's anything to commit
    status = git('status', '--porcelain')
    if not status.strip():
        return
    msg = (
        f'[AGENT] #{task["id"]}: {task["title"]}\n\n'
        f'{summary}\n\n'
        f'UNSUPERVISED — done by overnight agent, needs human review.\n\n'
        f'Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>'
    )
    git('commit', '-m', msg)


def git_back_to_main() -> None:
    # Stash any uncommitted changes (e.g. agent_log.md written by log())
    has_stash = False
    status = git('status', '--porcelain')
    if status.strip():
        git('stash', '--include-untracked')
        has_stash = True
    git('checkout', 'main')
    if has_stash:
        try:
            git('stash', 'pop')
        except RuntimeError:
            pass  # stash pop conflict — not critical


# ── Logging ───────────────────────────────────────────────────────────────────
def log(msg: str) -> None:
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line)
    with open(_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def log_session_start(checkpoint: str, quadrant: str) -> None:
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    header = (
        f'\n## Agent Session — {ts}\n'
        f'**Checkpoint:** `{checkpoint}`\n'
        f'**Rollback:** `git checkout main` or `git reset --hard {checkpoint}`\n'
        f'**Quadrant:** {quadrant}\n\n'
    )
    with open(_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(header)


def log_task_result(task: dict, branch: str, status: str, summary: str) -> None:
    entry = (
        f'### Task #{task["id"]}: {task["title"]}\n'
        f'- **Branch:** `{branch}`\n'
        f'- **Status:** {status}\n'
        f'- **Summary:** {summary}\n'
        f'- **UNSUPERVISED — needs human review and testing**\n\n'
    )
    with open(_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(entry)


# ── State persistence ─────────────────────────────────────────────────────────
def save_state(state: dict) -> None:
    _STATE_PATH.write_text(json.dumps(state, indent=2), encoding='utf-8')


def load_state() -> dict | None:
    if _STATE_PATH.exists():
        return json.loads(_STATE_PATH.read_text(encoding='utf-8'))
    return None


def clear_state() -> None:
    if _STATE_PATH.exists():
        _STATE_PATH.unlink()


# ── Task selection ────────────────────────────────────────────────────────────
def select_tasks(quadrant: str, include_critical: bool = False) -> list[dict]:
    open_tasks, _ = load_todos()
    open_only = [t for t in open_tasks if t.get('status', 'open') == 'open']

    if quadrant == 'all':
        # Process in safety order: eliminate → delegate → schedule → (do_first if allowed)
        order = list(QUADRANT_ORDER)
        if include_critical:
            order.append('do_first')
        candidates = []
        for q in order:
            filt = QUADRANT_FILTERS[q]
            group = [t for t in open_only if filt(t)]
            # Within each quadrant, lower priority first (safest)
            priority_order = {'low': 0, 'medium': 1, 'high': 2, 'critical': 3}
            group.sort(key=lambda t: priority_order.get(t.get('priority', 'low'), 0))
            candidates.extend(group)
        return candidates

    filt = QUADRANT_FILTERS.get(quadrant)
    if not filt:
        return []
    if quadrant == 'do_first' and not include_critical:
        log('WARNING: "do_first" quadrant requires --include-critical flag.')
        return []
    candidates = [t for t in open_only if filt(t)]
    priority_order = {'low': 0, 'medium': 1, 'high': 2, 'critical': 3}
    candidates.sort(key=lambda t: priority_order.get(t.get('priority', 'low'), 0))
    return candidates


# ── Run a single task ─────────────────────────────────────────────────────────
async def run_task(task: dict) -> tuple[str, str]:
    """Run Claude on a single task. Returns (status, summary)."""
    # Allow nested Claude sessions (the agent SDK spawns Claude Code internally)
    os.environ.pop('CLAUDECODE', None)
    from claude_agent_sdk import query, ClaudeAgentOptions

    prompt = (
        f'You are an autonomous overnight agent working on the WR Binary project.\n'
        f'Complete this task:\n\n'
        f'**Task #{task["id"]}:** {task["title"]}\n'
        f'**Description:** {task.get("description", "No description")}\n'
        f'**Tags:** {task.get("tags", "")}\n\n'
        f'IMPORTANT RULES:\n'
        f'- Read CLAUDE.md first for project conventions\n'
        f'- Always run `conda run -n guyenv python -m py_compile <file>` after editing .py files\n'
        f'- Do NOT modify any files in the "Do First" (urgent+important) category\n'
        f'- Keep changes focused on this specific task\n'
        f'- When done, provide a brief summary of what you did\n'
    )

    options = ClaudeAgentOptions(
        permission_mode='plan',
        allowed_tools=ALLOWED_TOOLS,
        cwd=str(_ROOT),
        max_turns=50,
    )

    result_text = ''
    session_id = None
    rate_limited = False

    try:
        gen = query(prompt=prompt, options=options)
        try:
            async for message in gen:
                if hasattr(message, 'result') and message.result:
                    result_text = message.result
                    session_id = getattr(message, 'session_id', None)
                elif hasattr(message, 'error') and message.error == 'rate_limit':
                    rate_limited = True
                    break
        finally:
            # Gracefully close the generator, catching anyio cancel scope errors
            try:
                await gen.aclose()
            except (RuntimeError, Exception):
                pass  # anyio cancel scope cleanup — safe to ignore
    except Exception as e:
        err_str = str(e)
        if 'rate' in err_str.lower() or '429' in err_str:
            rate_limited = True
        else:
            return 'error', f'Exception: {err_str}'

    if rate_limited:
        return 'rate_limited', session_id or ''

    summary = result_text[:500] if result_text else 'No output captured'
    return 'completed', summary


# ── Main agent loop ───────────────────────────────────────────────────────────
async def run_freeform_task(task_prompt: str, dry_run: bool) -> None:
    """Run a single free-form task (not from TODO.md)."""
    ts = datetime.now().strftime('%Y%m%d-%H%M')

    # Commit any leftover agent_log.md from previous sessions
    try:
        log_status = git('status', '--porcelain', '--', 'scripts/agent_log.md')
        if log_status.strip():
            git('add', 'scripts/agent_log.md')
            git('commit', '-m', '[AGENT] Save agent log from previous session')
    except RuntimeError:
        pass

    checkpoint = git_checkpoint()
    log(f'Agent starting — free-form task')
    log(f'Git checkpoint: {checkpoint}')
    log_session_start(checkpoint, 'freeform')

    if dry_run:
        log(f'  [DRY RUN] Would run free-form task:')
        log(f'  Prompt: {task_prompt[:200]}...' if len(task_prompt) > 200 else f'  Prompt: {task_prompt}')
        log('Agent session complete.')
        return

    branch = f'agent/freeform-{ts}'
    try:
        git('checkout', '-b', branch)
    except RuntimeError:
        git('checkout', branch)
    log(f'Working on branch: {branch}')

    fake_task = {'id': 0, 'title': 'Free-form task', 'description': task_prompt, 'tags': ''}
    consecutive_rate_limits = 0
    status, summary = await run_task(fake_task)

    while status == 'rate_limited':
        consecutive_rate_limits += 1
        sleep_time = RATE_LIMIT_SLEEP * consecutive_rate_limits
        log(f'Rate limited. Sleeping {sleep_time}s (attempt {consecutive_rate_limits})...')
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, time.sleep, sleep_time)
        log('Resuming after rate limit...')
        status, summary = await run_task(fake_task)

    if status == 'completed':
        git_commit_agent(fake_task, summary)
        log_task_result(fake_task, branch, 'completed', summary)
        log('Free-form task completed.')
        git_back_to_main()
        try:
            git('merge', branch, '--no-edit')
            log(f'Merged branch {branch} into main.')
        except RuntimeError as e:
            log(f'Merge conflict on {branch}: {e}. Branch preserved for manual merge.')
    else:
        log_task_result(fake_task, branch, status, summary)
        log(f'Free-form task finished with status: {status}')
        git_back_to_main()

    log('Agent session complete.')


async def agent_loop(quadrant: str, max_tasks: int | None, dry_run: bool,
                     include_critical: bool = False) -> None:
    log(f'Agent starting — quadrant={quadrant}, max_tasks={max_tasks}')

    # Commit any leftover agent_log.md from previous sessions
    try:
        log_status = git('status', '--porcelain', '--', 'scripts/agent_log.md')
        if log_status.strip():
            git('add', 'scripts/agent_log.md')
            git('commit', '-m', '[AGENT] Save agent log from previous session')
    except RuntimeError:
        pass

    # Create checkpoint
    checkpoint = git_checkpoint()
    log(f'Git checkpoint: {checkpoint}')
    log_session_start(checkpoint, quadrant)

    # Load or resume state
    state = load_state()
    completed_ids: list[int] = state.get('completed_tasks', []) if state else []
    tasks_done = len(completed_ids)

    while True:
        # Refresh task list each iteration (in case TODO.md was updated)
        candidates = select_tasks(quadrant, include_critical=include_critical)
        # Skip already completed tasks
        candidates = [t for t in candidates if t['id'] not in completed_ids]

        if not candidates:
            log(f'No more tasks in "{quadrant}" quadrant. Agent done.')
            break

        if max_tasks and tasks_done >= max_tasks:
            log(f'Reached max_tasks={max_tasks}. Agent done.')
            break

        task = candidates[0]
        log(f'--- Starting task #{task["id"]}: {task["title"]} ---')

        if dry_run:
            log(f'  [DRY RUN] Would work on: #{task["id"]} — {task["title"]}')
            log(f'  Description: {task.get("description", "N/A")}')
            completed_ids.append(task['id'])
            tasks_done += 1
            continue

        # Create branch for this task
        branch = git_create_branch(task)
        log(f'Working on branch: {branch}')

        # Save state before starting
        save_state({
            'current_task_id': task['id'],
            'completed_tasks': completed_ids,
            'checkpoint_tag': checkpoint,
            'quadrant': quadrant,
            'branch': branch,
            'started_at': datetime.now().isoformat(),
        })

        # Run Claude
        consecutive_rate_limits = 0
        status, summary = await run_task(task)

        while status == 'rate_limited':
            consecutive_rate_limits += 1
            sleep_time = RATE_LIMIT_SLEEP * consecutive_rate_limits
            log(f'Rate limited. Sleeping {sleep_time}s (attempt {consecutive_rate_limits})...')
            # Use synchronous sleep in executor to avoid anyio cancel scope conflicts
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, time.sleep, sleep_time)
            log('Resuming after rate limit...')
            status, summary = await run_task(task)

        if status == 'completed':
            # Commit changes on the task branch
            git_commit_agent(task, summary)
            log_task_result(task, branch, 'completed', summary)
            log(f'Task #{task["id"]} completed.')

            # Update TODO.md — mark as to-test
            open_tasks, done_tasks = load_todos()
            for t in open_tasks:
                if t['id'] == task['id']:
                    t['status'] = 'to-test'
                    t['description'] = (
                        t.get('description', '') +
                        ' [Done by overnight agent — needs review]'
                    ).strip()
                    break
            save_todos(open_tasks, done_tasks)
            git('add', 'TODO.md')
            try:
                git('commit', '-m',
                    f'[AGENT] Mark #{task["id"]} as to-test')
            except RuntimeError:
                pass  # Nothing to commit

            # Back to main and merge the branch
            git_back_to_main()
            try:
                git('merge', branch, '--no-edit')
                log(f'Merged branch {branch} into main.')
            except RuntimeError as e:
                log(f'Merge conflict on {branch}: {e}. Branch preserved for manual merge.')

            completed_ids.append(task['id'])
            tasks_done += 1

        elif status == 'error':
            log_task_result(task, branch, 'error', summary)
            log(f'Task #{task["id"]} failed: {summary}')
            git_back_to_main()
            completed_ids.append(task['id'])  # Skip it, don't retry
            tasks_done += 1

        # Update state
        save_state({
            'completed_tasks': completed_ids,
            'checkpoint_tag': checkpoint,
            'quadrant': quadrant,
            'started_at': state.get('started_at', datetime.now().isoformat())
            if state else datetime.now().isoformat(),
        })

    clear_state()
    log('Agent session complete.')


# ── CLI ───────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description='Overnight autonomous agent for WR Binary project'
    )
    p.add_argument('--quadrant', default='eliminate',
                   choices=['eliminate', 'delegate', 'schedule', 'do_first', 'all'],
                   help='Which Eisenhower quadrant to work on (default: eliminate)')
    p.add_argument('--include-critical', action='store_true',
                   help='Allow working on "Do First" (urgent+important) tasks')
    p.add_argument('--max-tasks', type=int, default=None,
                   help='Stop after completing N tasks')
    p.add_argument('--dry-run', action='store_true',
                   help='Show what would be done without executing')
    p.add_argument('--daemon', action='store_true',
                   help='Run in background (detach from terminal)')
    p.add_argument('--stop', action='store_true',
                   help='Stop a running daemon')
    p.add_argument('--task', type=str, default=None,
                   help='Free-form task prompt (skip TODO.md, e.g. paper writing)')
    return p.parse_args()


def stop_daemon() -> None:
    if not _PID_PATH.exists():
        print('No daemon running.')
        return
    pid = int(_PID_PATH.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        print(f'Stopped daemon (PID {pid}).')
    except ProcessLookupError:
        print(f'Daemon (PID {pid}) was not running.')
    _PID_PATH.unlink(missing_ok=True)


def main() -> None:
    args = parse_args()

    if args.stop:
        stop_daemon()
        return

    if args.daemon:
        # Fork and detach
        pid = os.fork()
        if pid > 0:
            # Parent
            _PID_PATH.write_text(str(pid))
            print(f'Agent daemon started (PID {pid}).')
            print(f'Logs: {_LOG_PATH}')
            print(f'Stop: python {__file__} --stop')
            return
        # Child continues below
        os.setsid()
        # Redirect stdout/stderr to log
        sys.stdout = open(_LOG_PATH, 'a')
        sys.stderr = sys.stdout

    # Wrap with caffeinate to prevent macOS sleep
    if sys.platform == 'darwin' and not os.environ.get('_CAFFEINATE_ACTIVE'):
        os.environ['_CAFFEINATE_ACTIVE'] = '1'
        os.execvp('caffeinate', ['caffeinate', '-i', sys.executable] + sys.argv)

    # Run the async loop
    try:
        if args.task:
            asyncio.run(run_freeform_task(args.task, args.dry_run))
        else:
            asyncio.run(agent_loop(args.quadrant, args.max_tasks, args.dry_run,
                                   include_critical=args.include_critical))
    except KeyboardInterrupt:
        log('Agent stopped by user (Ctrl+C).')
    finally:
        _PID_PATH.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
