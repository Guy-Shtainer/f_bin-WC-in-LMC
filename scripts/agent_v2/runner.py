#!/usr/bin/env python3
"""Agent v2 runner — orchestrates the implement-verify-fix loop.

Usage:
    conda run -n guyenv python scripts/agent_v2/runner.py
    conda run -n guyenv python scripts/agent_v2/runner.py --task "Add feature X"
    conda run -n guyenv python scripts/agent_v2/runner.py --task-ids "42,43"
    conda run -n guyenv python scripts/agent_v2/runner.py --quadrant schedule
    conda run -n guyenv python scripts/agent_v2/runner.py --dry-run
    conda run -n guyenv python scripts/agent_v2/runner.py --daemon
    conda run -n guyenv python scripts/agent_v2/runner.py --status
    conda run -n guyenv python scripts/agent_v2/runner.py --stop
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure this package is importable
_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
_ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from agent_v2.state import (
    log, save_state, load_state, clear_state, update_phase,
    write_pid, read_pid, clear_pid, is_running,
    save_completed_id, load_completed_ids, clear_completed_ids,
    log_session_start, log_task_result, set_daemon_mode,
)
from agent_v2.todo_parser import load_todos, save_todos, select_tasks, update_task_status
from agent_v2.executor import run_implement, run_fix, run_review
from agent_v2.verifier import (
    run_full_verification, run_advisory_checks,
    extract_new_error_patterns, append_to_common_errors,
)

_WORKTREE_PATH = _ROOT.parent / 'agent-worktree'
_SETTINGS_PATH = _SCRIPTS / 'agent_settings.json'
_LOG_PATH = _SCRIPTS / 'agent_log.md'


# ── Settings ──────────────────────────────────────────────────────────────────

def load_settings() -> dict:
    defaults = {
        'max_fix_rounds': 3,
        'model': 'sonnet',
        'verify_model': 'sonnet',
        'implement_budget': 5.0,
        'fix_budget': 3.0,
        'default_quadrant': 'eliminate',
    }
    if _SETTINGS_PATH.exists():
        try:
            with open(_SETTINGS_PATH) as f:
                loaded = json.load(f)
            defaults.update(loaded)
        except (json.JSONDecodeError, OSError):
            pass
    return defaults


# ── Git helpers (ONLY the runner touches git) ─────────────────────────────────

def git(*args: str, cwd: Path | str | None = None, check: bool = True) -> str:
    result = subprocess.run(
        ['git'] + list(args),
        cwd=str(cwd or _ROOT), capture_output=True, text=True
    )
    if check and result.returncode != 0:
        raise RuntimeError(f'git {" ".join(args)} failed: {result.stderr.strip()}')
    return result.stdout.strip()


def git_create_worktree(task: dict, base_branch: str = 'main') -> tuple[str, Path]:
    """Create isolated worktree for a task. Returns (branch, worktree_path).

    base_branch: which branch to start from (default 'main').
    Use a previous agent branch to iterate on existing work.
    """
    slug = re.sub(r'[^a-z0-9]+', '-', task.get('title', 'task').lower())[:40].strip('-')
    branch = f'agent/{task.get("id", 0)}-{slug}'
    wt = _WORKTREE_PATH

    # Clean up stale worktree
    if wt.exists():
        log(f'  Removing stale worktree at {wt}')
        git('worktree', 'remove', str(wt), '--force', check=False)
        if wt.exists():
            shutil.rmtree(wt, ignore_errors=True)

    # Delete stale branch
    git('branch', '-D', branch, check=False)

    # Create worktree from specified base branch
    git('worktree', 'add', str(wt), '-b', branch, base_branch)

    # Create Data symlink (critical — E019)
    data_link = wt / 'Data'
    if not data_link.exists():
        os.symlink('../Data', str(data_link))
        log('  Created Data symlink in worktree')

    return branch, wt


def git_worktree_commit(message: str, worktree: Path) -> bool:
    """Stage and commit all changes in worktree. Returns True if committed."""
    git('add', '-A', cwd=worktree)
    status = git('status', '--porcelain', cwd=worktree)
    if not status.strip():
        return False
    try:
        git('commit', '-m', message, cwd=worktree)
        return True
    except RuntimeError as e:
        log(f'  Warning: worktree commit failed: {e}')
        return False


def git_remove_worktree(commit_msg: str | None = None) -> None:
    """Remove agent worktree. Branch preserved for review."""
    wt = _WORKTREE_PATH
    if not wt.exists():
        return
    if commit_msg:
        try:
            git_worktree_commit(commit_msg, wt)
        except Exception as e:
            log(f'  Warning: final commit failed: {e}')
    try:
        git('worktree', 'remove', str(wt), '--force')
    except RuntimeError:
        shutil.rmtree(wt, ignore_errors=True)
    git('worktree', 'prune', check=False)


def git_revert_worktree(worktree: Path) -> None:
    """Discard all changes in worktree."""
    git('checkout', '.', cwd=worktree)
    git('clean', '-fd', cwd=worktree)


# ── Core quality loop ────────────────────────────────────────────────────────

def run_task(task: dict, settings: dict) -> tuple[str, str]:
    """Execute one task through multi-pass quality loop.

    Pass 1: IMPLEMENT — full Claude session to plan + implement + self-test
    Pass 2+: REVIEW — full Claude session to review, test, and improve

    Returns (status, summary) where status is one of:
    'completed', 'implement_failed', 'error'
    """
    max_passes = settings.get('max_passes', 2)
    model = settings.get('model', 'opus')
    impl_budget = settings.get('implement_budget', 5.0)
    review_budget = settings.get('review_budget', 5.0)

    task_id = task.get('id', 0)
    base_branch = settings.get('base_branch', 'main')
    log(f'Starting task #{task_id}: {task.get("title", "?")}')
    if base_branch != 'main':
        log(f'  Base branch: {base_branch}')

    # Create worktree
    branch, wt = git_create_worktree(task, base_branch=base_branch)
    log(f'  Branch: {branch}, Worktree: {wt}')

    save_state({
        'task_id': task_id,
        'task_title': task.get('title', ''),
        'branch': branch,
        'worktree': str(wt),
        'phase': 'implement',
        'phase_round': 0,
        'phases_done': [],
        'started_at': datetime.now().isoformat(),
        'rate_limited': False,
        'completed_tasks': load_completed_ids(),
    })

    phases_done = []
    prev_summary = ''

    try:
        # Pass 1: IMPLEMENT
        update_phase(task, 'implement', 0, phases_done)
        output, success = run_implement(task, wt, model=model, max_budget=impl_budget)

        if not success:
            git_remove_worktree()
            return 'implement_failed', f'Implement phase failed: {output[:200]}'

        phases_done.append('implement')
        prev_summary = output

        # Pass 2+: REVIEW & IMPROVE
        for pass_num in range(1, max_passes):
            update_phase(task, 'review', pass_num, phases_done)

            # Run quick advisory checks (L1, L2, L4 — non-blocking)
            advisory = run_advisory_checks(wt)
            log(f'  [ADVISORY] {advisory[:200]}')

            review_output, success = run_review(
                task, wt, prev_summary,
                advisory_checks=advisory,
                model=model, max_budget=review_budget,
            )

            phases_done.append(f'review-{pass_num}')
            prev_summary = review_output

            # If reviewer says LGTM, stop early
            if review_output and ('LGTM' in review_output or
                                   'no issues found' in review_output.lower()):
                log(f'  Review pass {pass_num}: LGTM — stopping early')
                break

        # Commit whatever we have
        commit_msg = (
            f'[AGENT] Task #{task_id}: {task.get("title", "")}\n\n'
            f'Auto-implemented by agent v3.\n'
            f'Passes: {len(phases_done)} ({", ".join(phases_done)})'
        )
        committed = git_worktree_commit(commit_msg, wt)
        if committed:
            log(f'  Committed to branch {branch}')
        else:
            log('  Warning: nothing to commit (no changes?)')

        git_remove_worktree()
        return 'completed', f'Task completed after {len(phases_done)} passes. {prev_summary[:300]}'

    except Exception as e:
        log(f'  ERROR: {e}')
        git_remove_worktree(f'[AGENT] Task #{task_id}: ERROR — {str(e)[:100]}')
        return 'error', str(e)


# ── Task loop ─────────────────────────────────────────────────────────────────

def agent_loop(tasks: list[dict], settings: dict, max_tasks: int = 5) -> None:
    """Process a list of tasks sequentially."""
    completed_ids = load_completed_ids()

    for i, task in enumerate(tasks[:max_tasks]):
        task_id = task.get('id', 0)
        if task_id in completed_ids:
            log(f'Skipping task #{task_id} (already completed this session)')
            continue

        log(f'\n{"="*60}')
        log(f'Task {i+1}/{min(len(tasks), max_tasks)}: #{task_id} — {task.get("title", "?")}')
        log(f'{"="*60}')

        # Mark as in-progress
        if task_id:
            update_task_status(task_id, 'in-progress')

        status, summary = run_task(task, settings)

        log(f'Result: {status}')
        log(f'Summary: {summary[:200]}')

        # Update state so dashboard shows per-task result
        save_state({
            'task_id': task_id,
            'task_title': task.get('title', ''),
            'phase': 'completed' if status == 'completed' else 'failed',
            'result': status,
            'result_summary': summary[:200],
            'completed_tasks': load_completed_ids(),
        })

        # Log result
        branch = f'agent/{task_id}-*'
        log_task_result(task, branch, status, summary)

        # Update TODO status
        if task_id:
            if status == 'completed':
                update_task_status(task_id, 'to-test')
                save_completed_id(task_id)
            else:
                update_task_status(task_id, 'open')  # Reset to open on failure

    log('\nAll tasks processed.')


# ── CLI commands ──────────────────────────────────────────────────────────────

def show_status() -> None:
    """Show current agent status."""
    state = load_state()
    if state:
        running = is_running()
        print(f'Agent v2 status: {"RUNNING" if running else "IDLE"}')
        print(f'  Task: #{state.get("task_id", "?")} — {state.get("task_title", "?")}')
        print(f'  Phase: {state.get("phase", "?")} (round {state.get("phase_round", 0)})')
        print(f'  Phases done: {state.get("phases_done", [])}')
        if state.get('rate_limited'):
            print(f'  RATE LIMITED until {state.get("rate_limit_resume_at", "?")}')
        print(f'  Started: {state.get("started_at", "?")}')
        print(f'  Updated: {state.get("updated_at", "?")}')
        completed = state.get('completed_tasks', [])
        if completed:
            print(f'  Completed this session: {completed}')
    else:
        print('Agent v2: no state file found (not running)')


def stop_agent() -> None:
    """Stop a running agent."""
    pid = read_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            print(f'Sent SIGTERM to PID {pid}')
            time.sleep(2)
            try:
                os.kill(pid, 0)
                os.kill(pid, signal.SIGKILL)
                print(f'Force-killed PID {pid}')
            except OSError:
                pass
        except OSError as e:
            print(f'Could not kill PID {pid}: {e}')
        clear_pid()
    else:
        print('No PID file found')

    # Clean up worktree
    git_remove_worktree('[AGENT] Stopped by user')
    clear_state()
    print('Agent stopped and cleaned up')


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Agent v2 — overnight autonomous coding agent'
    )
    parser.add_argument('--task', type=str, help='Free-form task (skip TODO.md)')
    parser.add_argument('--task-ids', type=str, help='Comma-separated task IDs')
    parser.add_argument('--quadrant', type=str, default=None,
                        help='Eisenhower quadrant: eliminate, delegate, schedule, do_first, all')
    parser.add_argument('--include-critical', action='store_true',
                        help='Allow working on do_first (urgent+important) tasks')
    parser.add_argument('--max-tasks', type=int, default=5,
                        help='Max tasks to process (default: 5)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without doing it')
    parser.add_argument('--daemon', action='store_true',
                        help='Run detached in background')
    parser.add_argument('--status', action='store_true', help='Show agent status')
    parser.add_argument('--stop', action='store_true', help='Stop running agent')
    parser.add_argument('--model', type=str, default=None,
                        help='Claude model (default: sonnet)')
    parser.add_argument('--base-branch', type=str, default='main',
                        help='Branch to base worktree on (default: main). Use a previous agent branch to iterate.')
    args = parser.parse_args()

    # Status/stop commands
    if args.status:
        show_status()
        return
    if args.stop:
        stop_agent()
        return

    # Check for already running
    if is_running():
        print('ERROR: An agent is already running. Use --stop first.')
        sys.exit(1)

    settings = load_settings()
    if args.model:
        settings['model'] = args.model
    settings['base_branch'] = args.base_branch

    quadrant = args.quadrant or settings.get('default_quadrant', 'eliminate')

    # Build task list
    if args.task:
        # Free-form task
        tasks = [{
            'id': 0,
            'title': args.task[:60],
            'description': args.task,
            'priority': 'medium',
            'status': 'open',
            'urgent': False,
            'important': False,
        }]
    elif args.task_ids:
        task_ids = [int(x.strip()) for x in args.task_ids.split(',')]
        tasks = select_tasks(quadrant, args.include_critical, task_ids=task_ids)
    else:
        tasks = select_tasks(quadrant, args.include_critical)

    if not tasks:
        print(f'No tasks found for quadrant "{quadrant}".')
        return

    # Dry run
    if args.dry_run:
        print(f'DRY RUN — would process {min(len(tasks), args.max_tasks)} tasks:')
        for i, t in enumerate(tasks[:args.max_tasks]):
            print(f'  {i+1}. #{t.get("id", "?")} [{t.get("priority", "?")}] {t.get("title", "?")}')
            if t.get('description'):
                print(f'     {t["description"][:100]}')
        return

    # Daemon mode
    if args.daemon:
        log_file = open(_LOG_PATH, 'a', encoding='utf-8')
        # Fork
        pid = os.fork()
        if pid > 0:
            print(f'Agent v2 started in background (PID {pid})')
            print(f'Monitor: tail -f {_LOG_PATH}')
            print(f'Webapp:  conda run -n guyenv streamlit run agent_app/app.py')
            return
        # Child — redirect stdout/stderr to log
        os.setsid()
        sys.stdout = log_file
        sys.stderr = log_file
        set_daemon_mode(True)

    # Set up PID and signal handlers
    write_pid()

    def cleanup(signum=None, frame=None):
        log('Received shutdown signal — cleaning up')
        git_remove_worktree('[AGENT] Interrupted')
        clear_pid()
        sys.exit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    # Prevent caffeinate double-exec
    try:
        subprocess.Popen(['caffeinate', '-i', '-w', str(os.getpid())])
    except FileNotFoundError:
        pass  # Not on macOS

    try:
        clear_completed_ids()
        log_session_start(quadrant)
        log(f'Processing {min(len(tasks), args.max_tasks)} tasks from "{quadrant}" quadrant')
        log(f'Settings: model={settings.get("model")}, max_fix_rounds={settings.get("max_fix_rounds")}')

        agent_loop(tasks, settings, max_tasks=args.max_tasks)
    except KeyboardInterrupt:
        log('Interrupted by user')
    except Exception as e:
        log(f'FATAL: {e}')
        import traceback
        log(traceback.format_exc())
    finally:
        git_remove_worktree('[AGENT] Session ended')
        clear_pid()
        # Write final state so dashboard shows DONE (not IDLE)
        save_state({
            'phase': 'all_done',
            'finished_at': datetime.now().isoformat(),
            'completed_tasks': load_completed_ids(),
        })
        log('Agent v2 session ended')


if __name__ == '__main__':
    main()
