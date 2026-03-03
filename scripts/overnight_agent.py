#!/usr/bin/env python3
"""
overnight_agent.py — Multi-agent overnight supervisor for WR Binary project.

Architecture: Pure-Python supervisor orchestrating a pipeline of specialized
Claude agents per task. Each agent has a focused role (plan, review, implement,
test, regression check, fix). Git is ONLY touched by the supervisor.

Quick start:
    conda run -n guyenv python scripts/overnight_agent.py

Options:
    --daemon              Run detached in background
    --quadrant X          Which tasks: eliminate (default), delegate, schedule, do_first, all
    --include-critical    Allow working on "Do First" (urgent+important) tasks
    --dry-run             Show what it would do without doing it
    --stop                Stop a running daemon + interactive branch review
    --status              Show current agent status
    --max-tasks N         Stop after completing N tasks
    --task "prompt"       Free-form task (skip TODO.md)
    --wait-on-reject      Pause and wait for human input when reviewer rejects
    --wait-on-fail        Pause and wait for human input when tester fails
    --intervention-timeout N  Seconds to wait for human intervention (default: from settings)
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
from datetime import datetime, timedelta
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_TODO_PATH = _ROOT / 'TODO.md'
_STATE_PATH = _HERE / '.agent_state.json'
_LOG_PATH = _HERE / 'agent_log.md'
_PID_PATH = _HERE / '.agent.pid'
_WORK_DIR = _HERE / '.agent_work'
_NOTES_DIR = _HERE / '.agent_notes'
_SETTINGS_PATH = _HERE / 'agent_settings.json'


# ── Agent settings (from agent_settings.json) ─────────────────────────────────
_AGENT_SETTINGS_DEFAULTS = {
    'rate_limit_sleep': 300,
    'max_fix_attempts': 2,
    'intervention': {
        'wait_on_reject': False,
        'wait_on_fail': False,
        'timeout_seconds': 1800,
        'auto_replan_max': 0,
        'auto_skip_test_max': 0,
    },
    'auto_learn': False,
}


def load_agent_settings() -> dict:
    """Load agent_settings.json, merged with defaults."""
    defaults = dict(_AGENT_SETTINGS_DEFAULTS)
    if _SETTINGS_PATH.exists():
        try:
            with open(_SETTINGS_PATH) as f:
                loaded = json.load(f)
            for k, v in loaded.items():
                if isinstance(v, dict) and isinstance(defaults.get(k), dict):
                    defaults[k] = {**defaults[k], **v}
                else:
                    defaults[k] = v
        except (json.JSONDecodeError, OSError):
            pass
    return defaults


# ── Constants (read from settings, with fallbacks) ────────────────────────────
_settings_cache: dict | None = None


def _get_settings() -> dict:
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = load_agent_settings()
    return _settings_cache


def _reload_settings() -> dict:
    global _settings_cache
    _settings_cache = None
    return _get_settings()


# Legacy constants — kept as fallbacks, but prefer _get_settings()
RATE_LIMIT_SLEEP = 300
MAX_FIX_ATTEMPTS = 2

QUADRANT_FILTERS = {
    'eliminate': lambda t: not t.get('urgent') and not t.get('important'),
    'delegate': lambda t: t.get('urgent') and not t.get('important'),
    'schedule': lambda t: not t.get('urgent') and t.get('important'),
    'do_first': lambda t: t.get('urgent') and t.get('important'),
}
QUADRANT_ORDER = ['eliminate', 'delegate', 'schedule']


# ── TODO.md parsing ──────────────────────────────────────────────────────────
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


# ── Git helpers (ONLY the supervisor touches git) ────────────────────────────
def git(*args: str, check: bool = True) -> str:
    """Run a git command in the project root."""
    result = subprocess.run(
        ['git'] + list(args),
        cwd=str(_ROOT), capture_output=True, text=True
    )
    if check and result.returncode != 0:
        raise RuntimeError(f'git {" ".join(args)} failed: {result.stderr.strip()}')
    return result.stdout.strip()


def git_resolve_conflicts() -> None:
    """Resolve any UU (unmerged) files by accepting current version."""
    status = git('status', '--porcelain')
    for line in status.split('\n'):
        if line.startswith('UU '):
            filepath = line[3:].strip()
            log(f'Resolving conflict in {filepath} (accepting ours)')
            git('checkout', '--ours', filepath)
            git('add', filepath)
    # Commit the resolution if we resolved anything
    status_after = git('diff', '--cached', '--name-only')
    if status_after.strip():
        git('commit', '-m', '[AGENT] Auto-resolve merge conflicts')


def git_safe_stash() -> bool:
    """Stash changes safely, resolving UU files first."""
    # First resolve any merge conflicts
    git_resolve_conflicts()
    # Now stash if there are changes
    status = git('status', '--porcelain')
    if status.strip():
        git('stash', '--include-untracked')
        return True
    return False


def git_safe_checkout(branch: str) -> None:
    """Safely checkout a branch, handling dirty working tree."""
    has_stash = git_safe_stash()
    git('checkout', branch)
    if has_stash:
        git('stash', 'pop', check=False)  # ignore pop conflicts


def git_checkpoint() -> str:
    ts = datetime.now().strftime('%Y%m%d-%H%M')
    tag = f'pre-agent-{ts}'
    try:
        git('tag', tag)
    except RuntimeError:
        pass
    return tag


def git_create_branch(task: dict) -> str:
    """Create or switch to a task branch from main."""
    slug = re.sub(r'[^a-z0-9]+', '-', task['title'].lower())[:40].strip('-')
    branch = f'agent/{task["id"]}-{slug}'

    # Ensure we're on main first
    current = git('branch', '--show-current')
    if current != 'main':
        git_safe_checkout('main')

    try:
        git('checkout', '-b', branch)
    except RuntimeError:
        # Branch exists — check if it has commits ahead of main
        try:
            ahead = git('rev-list', '--count', f'main..{branch}')
            if int(ahead.strip()) == 0:
                git('branch', '-D', branch)
                git('checkout', '-b', branch)
            else:
                git('checkout', branch)
        except RuntimeError:
            git('checkout', branch)

    return branch


def git_commit_all(message: str) -> bool:
    """Stage all changes and commit. Returns True if a commit was made."""
    git('add', '-A')
    status = git('status', '--porcelain')
    if not status.strip():
        return False
    git('commit', '-m', message)
    return True


def git_back_to_main() -> None:
    """Safely return to main branch."""
    current = git('branch', '--show-current')
    if current == 'main':
        return
    git_safe_checkout('main')


def git_list_agent_branches() -> list[str]:
    """List all agent/* branches."""
    output = git('branch', '--list', 'agent/*')
    return [b.strip().lstrip('* ') for b in output.split('\n') if b.strip()]


def git_branch_diff_stat(branch: str) -> str:
    """Get diff stat for a branch vs main."""
    try:
        return git('diff', '--stat', f'main...{branch}')
    except RuntimeError:
        return '(unable to compute diff)'


def git_branch_log(branch: str) -> str:
    """Get commit log for a branch vs main."""
    try:
        return git('log', '--oneline', f'main..{branch}')
    except RuntimeError:
        return '(no commits)'


# ── Logging ───────────────────────────────────────────────────────────────────
def log(msg: str) -> None:
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line, flush=True)
    with open(_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def log_session_start(checkpoint: str, quadrant: str) -> None:
    ts = datetime.now().strftime('%Y-%m-%d %H:%M')
    header = (
        f'\n## Agent Session — {ts}\n'
        f'**Checkpoint:** `{checkpoint}`\n'
        f'**Rollback:** `git reset --hard {checkpoint}`\n'
        f'**Quadrant:** {quadrant}\n\n'
    )
    with open(_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(header)


def log_pipeline_stage(task: dict, stage: str, status: str, detail: str = '') -> None:
    entry = (
        f'  [{stage.upper()}] Task #{task["id"]}: {status}'
        f'{" — " + detail if detail else ""}\n'
    )
    with open(_LOG_PATH, 'a', encoding='utf-8') as f:
        f.write(entry)


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
    _STATE_PATH.unlink(missing_ok=True)


# ── Task selection ────────────────────────────────────────────────────────────
def select_tasks(quadrant: str, include_critical: bool = False,
                  task_ids: list[int] | None = None) -> list[dict]:
    open_tasks, _ = load_todos()
    open_only = [t for t in open_tasks if t.get('status', 'open') == 'open']

    # Direct task ID selection (from webapp checkboxes)
    if task_ids:
        id_set = set(task_ids)
        selected = [t for t in open_only if t['id'] in id_set]
        # Preserve the order from task_ids
        id_order = {tid: i for i, tid in enumerate(task_ids)}
        selected.sort(key=lambda t: id_order.get(t['id'], 999))
        return selected

    if quadrant == 'all':
        order = list(QUADRANT_ORDER)
        if include_critical:
            order.append('do_first')
        candidates = []
        for q in order:
            filt = QUADRANT_FILTERS[q]
            group = [t for t in open_only if filt(t)]
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


# ── Work directory management ─────────────────────────────────────────────────
def create_work_dir(task: dict) -> Path:
    """Create a per-task working directory for agent artifacts."""
    task_dir = _WORK_DIR / str(task['id'])
    task_dir.mkdir(parents=True, exist_ok=True)
    return task_dir


# ── Agent runner ──────────────────────────────────────────────────────────────
def _load_notes_for_role(role: str) -> str:
    """Load global + role-specific notes for injection into system prompt."""
    notes_parts = []
    global_path = _NOTES_DIR / 'global_notes.md'
    if global_path.exists():
        content = global_path.read_text(encoding='utf-8').strip()
        if content:
            notes_parts.append(f'### General Project Notes\n{content}')

    role_path = _NOTES_DIR / f'{role}_notes.md'
    if role_path.exists():
        content = role_path.read_text(encoding='utf-8').strip()
        if content:
            notes_parts.append(f'### {role.replace("_", " ").title()} Specific Notes\n{content}')

    if notes_parts:
        return '## Learnings from Previous Runs\n\n' + '\n\n'.join(notes_parts) + '\n\n---\n\n'
    return ''


async def run_agent(role: str, user_prompt: str, timeout: int | None = None) -> str:
    """Run a single Claude agent with the given role and prompt.

    Returns the agent's text output, or raises on error.
    """
    # Allow nested Claude sessions
    os.environ.pop('CLAUDECODE', None)
    from agent_prompts import get_agent_config
    from claude_agent_sdk import query, ClaudeAgentOptions, ResultMessage

    config = get_agent_config(role)
    # Use timeout from agent_settings.json if available
    settings = _get_settings()
    timeouts = settings.get('timeouts', {})
    effective_timeout = timeout or timeouts.get(role, config['timeout'])

    # Inject notes into system prompt
    notes_prefix = _load_notes_for_role(role)
    system_prompt = notes_prefix + config['system_prompt']

    options = ClaudeAgentOptions(
        permission_mode='bypassPermissions',
        allowed_tools=config['allowed_tools'],
        system_prompt=system_prompt,
        cwd=str(_ROOT),
        max_turns=config['max_turns'],
        setting_sources=['project'],  # Read CLAUDE.md for project conventions
    )

    result_text = ''
    rate_limited = False

    try:
        gen = query(prompt=user_prompt, options=options)
        try:
            # Use asyncio.wait_for for timeout
            async def consume():
                nonlocal result_text, rate_limited
                async for message in gen:
                    if isinstance(message, ResultMessage) and message.result:
                        result_text = message.result
                    elif hasattr(message, 'error') and message.error == 'rate_limit':
                        rate_limited = True
                        return

            await asyncio.wait_for(consume(), timeout=effective_timeout)
        except asyncio.TimeoutError:
            log(f'  Agent [{role}] timed out after {effective_timeout}s')
            return f'TIMEOUT after {effective_timeout}s'
        finally:
            try:
                await gen.aclose()
            except (RuntimeError, Exception):
                pass
    except Exception as e:
        err_str = str(e).lower()
        if 'rate' in err_str or '429' in err_str or 'overloaded' in err_str or '529' in err_str:
            rate_limited = True
        else:
            raise

    if rate_limited:
        raise RateLimitError()

    return result_text or 'No output captured'


class RateLimitError(Exception):
    """Raised when the API returns a rate limit error."""
    pass


async def run_agent_with_retry(role: str, user_prompt: str,
                                timeout: int | None = None) -> str:
    """Run an agent with rate-limit retry logic.

    Retries indefinitely with exponential backoff (capped at 1 hour).
    After 2 failures, aligns sleep to the next hour boundary (session reset).
    Writes rate_limited state so the webapp can show a countdown.
    """
    settings = _get_settings()
    rate_sleep = settings.get('rate_limit_sleep', RATE_LIMIT_SLEEP)
    attempt = 0
    while True:
        try:
            return await run_agent(role, user_prompt, timeout)
        except RateLimitError:
            attempt += 1
            # Exponential backoff: base * 2^(attempt-1), capped at 1 hour
            base_sleep = min(rate_sleep * (2 ** (attempt - 1)), 3600)

            # After 2nd failure, align to next hour boundary (API session reset)
            if attempt >= 2:
                now = datetime.now()
                next_hour = (now + timedelta(hours=1)).replace(
                    minute=0, second=0, microsecond=0
                )
                sleep_time = max(base_sleep, (next_hour - now).total_seconds())
            else:
                sleep_time = base_sleep

            resume_at = (datetime.now() + timedelta(seconds=sleep_time)).isoformat()
            log(f'  Rate limited (attempt {attempt}). '
                f'Sleeping {sleep_time:.0f}s until ~{resume_at}...')

            # Update state so webapp shows countdown
            state = load_state() or {}
            state['rate_limited'] = True
            state['rate_limit_resume_at'] = resume_at
            save_state(state)

            await asyncio.sleep(sleep_time)

            # Clear rate limit flag
            state = load_state() or {}
            state['rate_limited'] = False
            state['rate_limit_resume_at'] = None
            save_state(state)
            log('  Resuming after rate limit...')


# ── CLI flags (set from main, read by pipeline) ──────────────────────────────
_cli_flags: dict = {}


# ── Pipeline ──────────────────────────────────────────────────────────────────
async def run_pipeline(task: dict) -> tuple[str, str]:
    """Run the full multi-agent pipeline for a task.

    Returns (status, summary) where status is one of:
    'completed', 'rejected', 'error', 'test_failed'
    """
    work_dir = create_work_dir(task)
    task_desc = (
        f'Task #{task["id"]}: {task["title"]}\n'
        f'Description: {task.get("description", "No description")}\n'
        f'Tags: {task.get("tags", "")}\n'
    )

    # ── Stage 1: Plan ────────────────────────────────────────────────────
    log(f'  [PLANNER] Starting...')
    save_state_stage(task, 'planner')
    plan_path = work_dir / 'plan.md'
    planner_prompt = (
        f'{task_desc}\n\n'
        f'Write your implementation plan to: {plan_path}\n\n'
        f'Start by reading CLAUDE.md and COMMON_ERRORS.md at the project root.\n'
        f'Then explore the codebase to understand the relevant files.\n'
    )

    try:
        planner_result = await run_agent_with_retry('planner', planner_prompt)
    except (RateLimitError, Exception) as e:
        return 'error', f'Planner failed: {e}'

    if planner_result.startswith('TIMEOUT'):
        return 'error', f'Planner timed out'

    # If the planner didn't write the file, save its output as the plan
    if not plan_path.exists():
        plan_path.write_text(planner_result, encoding='utf-8')

    stages_done = ['planner']
    log_pipeline_stage(task, 'planner', 'done')
    git_commit_all(f'[AGENT] Plan for #{task["id"]}: {task["title"]}')

    # ── Stage 2: Review ──────────────────────────────────────────────────
    log(f'  [REVIEWER] Starting...')
    save_state_stage(task, 'reviewer', stages_done)
    review_path = work_dir / 'review.md'
    reviewer_prompt = (
        f'{task_desc}\n\n'
        f'Read the implementation plan at: {plan_path}\n'
        f'Write your review to: {review_path}\n\n'
        f'Also read CLAUDE.md and COMMON_ERRORS.md to check the plan follows conventions.\n'
        f'End your review with APPROVED, APPROVED WITH NOTES, or REJECTED.\n'
    )

    try:
        reviewer_result = await run_agent_with_retry('reviewer', reviewer_prompt)
    except (RateLimitError, Exception) as e:
        return 'error', f'Reviewer failed: {e}'

    if not review_path.exists():
        review_path.write_text(reviewer_result, encoding='utf-8')

    review_text = review_path.read_text(encoding='utf-8')
    stages_done.append('reviewer')
    log_pipeline_stage(task, 'reviewer', 'done')
    git_commit_all(f'[AGENT] Review for #{task["id"]}: {task["title"]}')

    # Check if rejected — with intervention support
    if 'REJECTED' in review_text.upper():
        settings = _get_settings()
        int_cfg = settings.get('intervention', {})
        wait_on_reject = (
            _cli_flags.get('wait_on_reject', False) or
            int_cfg.get('wait_on_reject', False)
        )

        if wait_on_reject:
            intervention = await wait_for_intervention(
                task['id'], 'reviewer_rejected',
                timeout=_cli_flags.get('intervention_timeout')
            )
            if intervention:
                action = intervention.get('action', '')
                if action == 'approve_override':
                    log('  Intervention: Plan approved despite rejection.')
                elif action == 'replan_with_guidance':
                    guidance = intervention.get('guidance', '')
                    max_retries = intervention.get('max_retries', 1)
                    log(f'  Intervention: Replanning with guidance (max {max_retries})...')
                    for retry in range(max_retries):
                        replan_prompt = (
                            f'{task_desc}\n\n'
                            f'Your previous plan was REJECTED.\n'
                            f'Reviewer feedback: {review_text[-500:]}\n'
                            f'Human guidance: {guidance}\n\n'
                            f'Write an improved plan to: {plan_path}\n'
                        )
                        try:
                            await run_agent_with_retry('planner', replan_prompt)
                        except Exception:
                            break
                        git_commit_all(f'[AGENT] Replan attempt {retry+1} for #{task["id"]}')
                        # Re-review
                        reviewer_prompt_retry = (
                            f'{task_desc}\n\n'
                            f'Read the REVISED plan at: {plan_path}\n'
                            f'Write your review to: {review_path}\n'
                            f'End with APPROVED, APPROVED WITH NOTES, or REJECTED.\n'
                        )
                        try:
                            await run_agent_with_retry('reviewer', reviewer_prompt_retry)
                        except Exception:
                            break
                        review_text = review_path.read_text(encoding='utf-8')
                        git_commit_all(f'[AGENT] Re-review {retry+1} for #{task["id"]}')
                        if 'REJECTED' not in review_text.upper():
                            break
                    else:
                        if 'REJECTED' in review_text.upper():
                            return 'rejected', 'Plan rejected after replan attempts'
                elif action == 'edit_plan':
                    plan_content = intervention.get('plan_content', '')
                    if plan_content:
                        plan_path.write_text(plan_content, encoding='utf-8')
                        log('  Intervention: Plan edited by human.')
                        git_commit_all(f'[AGENT] Human-edited plan for #{task["id"]}')
                elif action == 'abort':
                    return 'aborted', 'Task aborted by human intervention'
            else:
                # Timeout — fall through to default rejection behavior
                return 'rejected', f'Reviewer rejected the plan: {review_text[-200:]}'
        else:
            return 'rejected', f'Reviewer rejected the plan: {review_text[-200:]}'

    # ── Stage 3: Implement ───────────────────────────────────────────────
    log(f'  [IMPLEMENTER] Starting...')
    save_state_stage(task, 'implementer', stages_done)
    implementer_prompt = (
        f'{task_desc}\n\n'
        f'Read the approved plan at: {plan_path}\n'
        f'Read the reviewer notes at: {review_path}\n\n'
        f'Implement the plan. Follow it exactly.\n'
        f'Read CLAUDE.md first for project conventions.\n'
        f'After editing any .py file, run: conda run -n guyenv python -m py_compile <file>\n'
        f'Do NOT run any git commands.\n'
    )

    try:
        impl_result = await run_agent_with_retry('implementer', implementer_prompt)
    except (RateLimitError, Exception) as e:
        return 'error', f'Implementer failed: {e}'

    stages_done.append('implementer')
    log_pipeline_stage(task, 'implementer', 'done', impl_result[:100])
    git_commit_all(f'[AGENT] Implement #{task["id"]}: {task["title"]}')

    # ── Stage 4: Test (with fix cycle) ───────────────────────────────────
    settings = _get_settings()
    max_fix = settings.get('max_fix_attempts', MAX_FIX_ATTEMPTS)
    test_passed = False
    for attempt in range(1, max_fix + 2):  # +1 for initial test, +1 for range
        log(f'  [TESTER] Starting (attempt {attempt})...')
        save_state_stage(task, f'tester-{attempt}')
        test_path = work_dir / f'test_report_{attempt}.md'

        # Get list of changed files for the tester
        try:
            changed = git('diff', '--name-only', 'main')
        except RuntimeError:
            changed = ''

        tester_prompt = (
            f'{task_desc}\n\n'
            f'Files changed (vs main):\n{changed}\n\n'
            f'Read the plan at: {plan_path}\n'
            f'Write your test report to: {test_path}\n\n'
            f'Check all modified .py files with py_compile.\n'
            f'Check COMMON_ERRORS.md patterns against modified files.\n'
            f'End with: PASS or FAIL\n'
        )

        try:
            tester_result = await run_agent_with_retry('tester', tester_prompt)
        except (RateLimitError, Exception) as e:
            log_pipeline_stage(task, 'tester', f'error: {e}')
            break

        if not test_path.exists():
            test_path.write_text(tester_result, encoding='utf-8')

        test_text = test_path.read_text(encoding='utf-8')
        git_commit_all(f'[AGENT] Test report {attempt} for #{task["id"]}')

        if 'PASS' in test_text.upper().split('\n')[-5:]:
            # Check last 5 lines for PASS verdict
            test_passed = True
            log_pipeline_stage(task, 'tester', 'PASS')
            break

        log_pipeline_stage(task, 'tester', f'FAIL (attempt {attempt})')

        if attempt > max_fix:
            break

        # ── Fix cycle ────────────────────────────────────────────────────
        log(f'  [FIX PLANNER] Starting (attempt {attempt})...')
        save_state_stage(task, f'fix_planner-{attempt}')
        fix_plan_path = work_dir / f'fix_plan_{attempt}.md'

        fix_planner_prompt = (
            f'{task_desc}\n\n'
            f'The test report at {test_path} shows FAILURES.\n'
            f'Read the original plan at: {plan_path}\n'
            f'Write your fix plan to: {fix_plan_path}\n\n'
            f'Diagnose the root cause and plan specific fixes.\n'
        )

        try:
            await run_agent_with_retry('fix_planner', fix_planner_prompt)
        except (RateLimitError, Exception) as e:
            log_pipeline_stage(task, 'fix_planner', f'error: {e}')
            break

        git_commit_all(f'[AGENT] Fix plan {attempt} for #{task["id"]}')

        log(f'  [FIX IMPLEMENTER] Starting (attempt {attempt})...')
        save_state_stage(task, f'fix_implementer-{attempt}')

        fix_impl_prompt = (
            f'{task_desc}\n\n'
            f'Read the fix plan at: {fix_plan_path}\n'
            f'Read the test report at: {test_path}\n\n'
            f'Execute the fixes. Follow the fix plan exactly.\n'
            f'After editing any .py file, run: conda run -n guyenv python -m py_compile <file>\n'
            f'Do NOT run any git commands.\n'
        )

        try:
            await run_agent_with_retry('fix_implementer', fix_impl_prompt)
        except (RateLimitError, Exception) as e:
            log_pipeline_stage(task, 'fix_implementer', f'error: {e}')
            break

        git_commit_all(f'[AGENT] Fix attempt {attempt} for #{task["id"]}')

    # ── Stage 5: Regression ──────────────────────────────────────────────
    stages_done.append('tester')
    log(f'  [REGRESSION] Starting...')
    save_state_stage(task, 'regression', stages_done)
    regression_path = work_dir / 'regression.md'

    try:
        changed = git('diff', '--name-only', 'main')
    except RuntimeError:
        changed = ''

    regression_prompt = (
        f'{task_desc}\n\n'
        f'Files changed (vs main):\n{changed}\n\n'
        f'Read the plan at: {plan_path}\n'
        f'Write your regression report to: {regression_path}\n\n'
        f'Check that existing project files still compile:\n'
        f'- app/app.py, app/shared.py, all files in app/pages/\n'
        f'- CCF.py, ccf_tasks.py, ObservationClass.py, StarClass.py\n'
        f'- wr_bias_simulation.py, pipeline/*.py\n\n'
        f'End with: PASS or FAIL\n'
    )

    try:
        regression_result = await run_agent_with_retry('regression', regression_prompt)
    except (RateLimitError, Exception) as e:
        log_pipeline_stage(task, 'regression', f'error: {e}')
        regression_result = f'Error: {e}'

    if not regression_path.exists():
        regression_path.write_text(regression_result, encoding='utf-8')

    regression_text = regression_path.read_text(encoding='utf-8')
    git_commit_all(f'[AGENT] Regression report for #{task["id"]}')

    regression_passed = 'PASS' in regression_text.upper().split('\n')[-5:]
    log_pipeline_stage(task, 'regression', 'PASS' if regression_passed else 'FAIL')

    stages_done.append('regression')

    # ── Final status ─────────────────────────────────────────────────────
    if test_passed and regression_passed:
        return 'completed', impl_result[:500] if impl_result else 'Implementation done'
    elif not test_passed:
        return 'test_failed', f'Tests failed after {max_fix} fix attempts'
    else:
        return 'regression_failed', f'Regression check failed: {regression_text[-200:]}'


def save_state_stage(task: dict, stage: str,
                     stages_done: list[str] | None = None) -> None:
    """Update state with current pipeline stage (enhanced for webapp)."""
    state = load_state() or {}
    state.update({
        'current_task_id': task['id'],
        'current_task_title': task.get('title', ''),
        'current_stage': stage,
        'stage_started_at': datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat(),
        'pipeline_stages_done': stages_done or state.get('pipeline_stages_done', []),
        'pipeline_stages_total': ['planner', 'reviewer', 'implementer', 'tester', 'regression'],
        'awaiting_intervention': False,
        'intervention_type': None,
        'rate_limited': False,
        'rate_limit_resume_at': None,
    })
    save_state(state)


# ── Intervention support ─────────────────────────────────────────────────────
def check_intervention(task_id: int) -> dict | None:
    """Check if there's a pending intervention file. Returns its content or None."""
    intervention_path = _WORK_DIR / str(task_id) / '.intervention.json'
    if not intervention_path.exists():
        return None
    try:
        with open(intervention_path) as f:
            intervention = json.load(f)
        intervention_path.unlink()  # Consume the intervention
        # Clear awaiting flag
        state = load_state() or {}
        state['awaiting_intervention'] = False
        state['intervention_type'] = None
        save_state(state)
        return intervention
    except (json.JSONDecodeError, OSError):
        return None


async def wait_for_intervention(task_id: int, intervention_type: str,
                                timeout: int | None = None) -> dict | None:
    """Wait for human intervention via the webapp.

    Sets state to awaiting_intervention=True, polls for .intervention.json.
    Returns the intervention dict, or None if timeout expires.
    """
    settings = _get_settings()
    int_cfg = settings.get('intervention', {})
    effective_timeout = timeout or int_cfg.get('timeout_seconds', 1800)

    # Update state to signal webapp
    state = load_state() or {}
    state['awaiting_intervention'] = True
    state['intervention_type'] = intervention_type
    state['updated_at'] = datetime.now().isoformat()
    save_state(state)

    log(f'  Waiting for human intervention ({intervention_type}). '
        f'Timeout: {effective_timeout}s')

    poll_interval = 10  # seconds
    elapsed = 0
    loop = asyncio.get_event_loop()

    while elapsed < effective_timeout:
        intervention = check_intervention(task_id)
        if intervention:
            log(f'  Received intervention: {intervention.get("action", "unknown")}')
            return intervention
        await loop.run_in_executor(None, time.sleep, poll_interval)
        elapsed += poll_interval

    # Timeout — clear waiting state
    log(f'  Intervention timeout ({effective_timeout}s). Proceeding with default behavior.')
    state = load_state() or {}
    state['awaiting_intervention'] = False
    state['intervention_type'] = None
    save_state(state)
    return None


async def auto_learn_reflection(task: dict, status: str, summary: str) -> None:
    """Run a brief reflection agent after task completion to append learnings."""
    settings = _get_settings()
    if not settings.get('auto_learn', False):
        return

    log('  [AUTO-LEARN] Running reflection...')
    prompt = (
        f'You just completed task #{task["id"]}: {task["title"]}\n'
        f'Status: {status}\n'
        f'Summary: {summary[:500]}\n\n'
        f'Based on this experience, write 3-5 concise bullet points about what '
        f'you learned that would help future agents working on this project.\n'
        f'Focus on: patterns that worked, pitfalls to avoid, project-specific '
        f'conventions discovered.\n\n'
        f'Write your learnings to EACH of these files (append, do not overwrite):\n'
        f'- {_NOTES_DIR}/global_notes.md\n'
        f'- {_NOTES_DIR}/planner_notes.md\n'
        f'- {_NOTES_DIR}/implementer_notes.md\n'
    )
    try:
        await run_agent('planner', prompt, timeout=300)
        log('  [AUTO-LEARN] Reflection complete.')
    except Exception as e:
        log(f'  [AUTO-LEARN] Reflection failed: {e}')


# ── Main agent loop ───────────────────────────────────────────────────────────
async def run_freeform_task(task_prompt: str, dry_run: bool) -> None:
    """Run a single free-form task through the pipeline."""
    commit_pending_log()
    checkpoint = git_checkpoint()
    log(f'Agent starting — free-form task')
    log(f'Git checkpoint: {checkpoint}')
    log_session_start(checkpoint, 'freeform')

    if dry_run:
        log(f'  [DRY RUN] Would run free-form task:')
        log(f'  Prompt: {task_prompt[:200]}...' if len(task_prompt) > 200 else f'  Prompt: {task_prompt}')
        log('Agent session complete.')
        return

    task = {'id': 0, 'title': 'Free-form task', 'description': task_prompt, 'tags': ''}
    branch = f'agent/freeform-{datetime.now().strftime("%Y%m%d-%H%M")}'

    git_safe_checkout('main')
    try:
        git('checkout', '-b', branch)
    except RuntimeError:
        git('checkout', branch)

    log(f'Working on branch: {branch}')
    status, summary = await run_pipeline(task)

    log_task_result(task, branch, status, summary)
    log(f'Free-form task finished: {status}')

    # Return to main (do NOT merge — user reviews via --stop)
    git_back_to_main()
    log('Agent session complete.')


async def agent_loop(quadrant: str, max_tasks: int | None, dry_run: bool,
                     include_critical: bool = False,
                     task_ids: list[int] | None = None) -> None:
    """Main loop: pick tasks, run pipeline, repeat."""
    commit_pending_log()
    checkpoint = git_checkpoint()
    mode_desc = f'task_ids={task_ids}' if task_ids else f'quadrant={quadrant}'
    log(f'Agent starting — {mode_desc}, max_tasks={max_tasks}')
    log(f'Git checkpoint: {checkpoint}')
    log_session_start(checkpoint, quadrant)

    state = load_state()
    completed_ids: list[int] = state.get('completed_tasks', []) if state else []
    tasks_done = len(completed_ids)

    while True:
        candidates = select_tasks(quadrant, include_critical=include_critical,
                                  task_ids=task_ids)
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
            log(f'  [DRY RUN] Pipeline stages: planner -> reviewer -> implementer -> tester -> regression')
            log(f'  Description: {task.get("description", "N/A")}')
            completed_ids.append(task['id'])
            tasks_done += 1
            continue

        # Create branch
        branch = git_create_branch(task)
        log(f'Working on branch: {branch}')

        save_state({
            'current_task_id': task['id'],
            'current_task_title': task.get('title', ''),
            'completed_tasks': completed_ids,
            'checkpoint_tag': checkpoint,
            'quadrant': quadrant,
            'branch': branch,
            'current_stage': 'starting',
            'started_at': datetime.now().isoformat(),
            'pipeline_stages_done': [],
            'pipeline_stages_total': ['planner', 'reviewer', 'implementer', 'tester', 'regression'],
            'awaiting_intervention': False,
            'intervention_type': None,
            'rate_limited': False,
            'rate_limit_resume_at': None,
        })

        # Run the full pipeline
        try:
            status, summary = await run_pipeline(task)
        except Exception as e:
            status, summary = 'error', f'Pipeline crashed: {e}'
            log(f'  Pipeline error: {e}')

        log_task_result(task, branch, status, summary)
        log(f'Task #{task["id"]} finished: {status}')

        # Auto-learn reflection
        if status in ('completed', 'test_failed', 'regression_failed'):
            await auto_learn_reflection(task, status, summary)

        if status == 'completed':
            # Update TODO.md
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
            git_commit_all(f'[AGENT] Mark #{task["id"]} as to-test')

        # Return to main (do NOT merge — user reviews via --stop)
        git_back_to_main()

        completed_ids.append(task['id'])
        tasks_done += 1

        save_state({
            'completed_tasks': completed_ids,
            'checkpoint_tag': checkpoint,
            'quadrant': quadrant,
            'current_stage': 'idle',
            'started_at': state.get('started_at', datetime.now().isoformat())
            if state else datetime.now().isoformat(),
        })

    clear_state()
    log('Agent session complete.')


def commit_pending_log() -> None:
    """Commit any leftover agent_log.md from previous sessions."""
    try:
        log_status = git('status', '--porcelain', '--', 'scripts/agent_log.md')
        if log_status.strip():
            git('add', 'scripts/agent_log.md')
            git('commit', '-m', '[AGENT] Save agent log from previous session')
    except RuntimeError:
        pass


# ── --stop: Interactive branch review ─────────────────────────────────────────
def stop_daemon() -> None:
    """Stop the daemon and offer interactive branch review."""
    if _PID_PATH.exists():
        pid = int(_PID_PATH.read_text().strip())
        try:
            os.kill(pid, signal.SIGTERM)
            print(f'Stopped daemon (PID {pid}).')
        except ProcessLookupError:
            print(f'Daemon (PID {pid}) was not running.')
        _PID_PATH.unlink(missing_ok=True)
    else:
        print('No daemon running.')

    # Interactive review of agent branches
    branches = git_list_agent_branches()
    if not branches:
        print('\nNo agent branches to review.')
        return

    print(f'\n{"=" * 60}')
    print(f'  Agent Branch Review — {len(branches)} branch(es)')
    print(f'{"=" * 60}\n')

    for branch in branches:
        print(f'\n--- Branch: {branch} ---')

        # Show commit log
        commit_log = git_branch_log(branch)
        print(f'\nCommits:\n{commit_log}')

        # Show diff stat
        diff_stat = git_branch_diff_stat(branch)
        print(f'\nChanges:\n{diff_stat}')

        # Check for test/regression reports in work dir
        task_id = branch.split('/')[1].split('-')[0] if '/' in branch else '0'
        task_work = _WORK_DIR / task_id
        if task_work.exists():
            for report in sorted(task_work.glob('*.md')):
                print(f'\n[{report.name}]')
                content = report.read_text(encoding='utf-8')
                # Show last 10 lines (usually contains verdict)
                lines = content.strip().split('\n')
                for line in lines[-10:]:
                    print(f'  {line}')

        # Ask user
        print(f'\nOptions: [K]eep (leave branch) / [M]erge into main / [D]iscard (delete branch)')
        while True:
            choice = input(f'Choice for {branch}: ').strip().lower()
            if choice in ('k', 'keep'):
                print(f'  Keeping {branch}')
                break
            elif choice in ('m', 'merge'):
                try:
                    git_safe_checkout('main')
                    git('merge', branch, '--no-edit')
                    print(f'  Merged {branch} into main.')
                except RuntimeError as e:
                    print(f'  Merge failed: {e}')
                    print(f'  Branch preserved for manual merge.')
                break
            elif choice in ('d', 'discard'):
                try:
                    git_safe_checkout('main')
                    git('branch', '-D', branch)
                    print(f'  Deleted {branch}.')
                    # Clean up work dir
                    task_work = _WORK_DIR / task_id
                    if task_work.exists():
                        import shutil
                        shutil.rmtree(task_work)
                except RuntimeError as e:
                    print(f'  Delete failed: {e}')
                break
            else:
                print('  Invalid choice. Enter K, M, or D.')

    print(f'\n{"=" * 60}')
    print('  Review complete.')
    print(f'{"=" * 60}')


# ── --status ──────────────────────────────────────────────────────────────────
def show_status() -> None:
    """Show current agent status."""
    print(f'\n{"=" * 50}')
    print(f'  Overnight Agent Status')
    print(f'{"=" * 50}\n')

    # Check if running
    if _PID_PATH.exists():
        pid = int(_PID_PATH.read_text().strip())
        try:
            os.kill(pid, 0)  # Check if process exists
            print(f'Status:  RUNNING (PID {pid})')
        except ProcessLookupError:
            print(f'Status:  STOPPED (stale PID {pid})')
    else:
        print(f'Status:  STOPPED')

    # Show state
    state = load_state()
    if state:
        print(f'Task:    #{state.get("current_task_id", "?")}')
        print(f'Stage:   {state.get("current_stage", "?")}')
        print(f'Started: {state.get("started_at", "?")}')
        completed = state.get('completed_tasks', [])
        print(f'Done:    {len(completed)} task(s) ({completed})')
    else:
        print(f'State:   No active state')

    # Show branches
    branches = git_list_agent_branches()
    print(f'\nAgent branches: {len(branches)}')
    for b in branches:
        log_oneline = git_branch_log(b)
        commit_count = len([l for l in log_oneline.split('\n') if l.strip()])
        print(f'  {b}  ({commit_count} commits)')

    # Show recent log
    if _LOG_PATH.exists():
        lines = _LOG_PATH.read_text(encoding='utf-8').strip().split('\n')
        print(f'\nRecent log (last 5 lines):')
        for line in lines[-5:]:
            print(f'  {line}')

    print()


# ── CLI ───────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description='Multi-agent overnight supervisor for WR Binary project'
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
                   help='Stop daemon + interactive branch review')
    p.add_argument('--status', action='store_true',
                   help='Show current agent status')
    p.add_argument('--task', type=str, default=None,
                   help='Free-form task prompt (skip TODO.md)')
    p.add_argument('--task-ids', type=str, default=None,
                   help='Comma-separated TODO task IDs to run (e.g. "18,20,2")')
    p.add_argument('--wait-on-reject', action='store_true',
                   help='Wait for human input when reviewer rejects a plan')
    p.add_argument('--wait-on-fail', action='store_true',
                   help='Wait for human input when tester fails')
    p.add_argument('--intervention-timeout', type=int, default=None,
                   help='Seconds to wait for human intervention (default: from settings)')
    return p.parse_args()


def main() -> None:
    args = parse_args()

    if args.status:
        show_status()
        return

    if args.stop:
        stop_daemon()
        return

    if args.daemon:
        pid = os.fork()
        if pid > 0:
            _PID_PATH.write_text(str(pid))
            print(f'Agent daemon started (PID {pid}).')
            print(f'Logs: {_LOG_PATH}')
            print(f'Monitor: python {__file__} --status')
            print(f'Stop: python {__file__} --stop')
            return
        os.setsid()
        sys.stdout = open(_LOG_PATH, 'a')
        sys.stderr = sys.stdout

    # Set CLI flags for intervention system
    global _cli_flags
    _cli_flags = {
        'wait_on_reject': args.wait_on_reject,
        'wait_on_fail': args.wait_on_fail,
        'intervention_timeout': args.intervention_timeout,
    }

    # Wrap with caffeinate to prevent macOS sleep
    if sys.platform == 'darwin' and not os.environ.get('_CAFFEINATE_ACTIVE'):
        os.environ['_CAFFEINATE_ACTIVE'] = '1'
        os.execvp('caffeinate', ['caffeinate', '-i', sys.executable] + sys.argv)

    # Parse --task-ids if provided
    task_ids = None
    if args.task_ids:
        task_ids = [int(x.strip()) for x in args.task_ids.split(',') if x.strip().isdigit()]

    try:
        if args.task:
            asyncio.run(run_freeform_task(args.task, args.dry_run))
        else:
            asyncio.run(agent_loop(args.quadrant, args.max_tasks, args.dry_run,
                                   include_critical=args.include_critical,
                                   task_ids=task_ids))
    except KeyboardInterrupt:
        log('Agent stopped by user (Ctrl+C).')
    finally:
        _PID_PATH.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
