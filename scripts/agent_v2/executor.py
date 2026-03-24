"""Executor — runs claude CLI as subprocess, captures output, handles rate limits.

Each phase (implement, verify, fix) is a single `claude --print -p "..."` call
with `--output-format stream-json --verbose` for real-time monitoring.
Output is parsed from JSON events and streamed to a live file.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from .state import log, save_state, load_state, update_phase, _HERE
from .prompts import (
    build_implement_prompt, build_verify_prompt, build_fix_prompt,
    build_review_prompt,
)

# Live output file — tail -f this to watch agent thoughts in real time
_LIVE_OUTPUT_PATH = _HERE / '.agent_live_output.txt'

# Rate limit patterns in stderr
_RATE_LIMIT_PATTERNS = [
    r'rate.?limit',
    r'429',
    r'overloaded',
    r'too many requests',
    r'capacity',
    r'throttl',
]
_RATE_RE = re.compile('|'.join(_RATE_LIMIT_PATTERNS), re.IGNORECASE)


def _blocking_sleep(total_seconds: float, chunk: float = 60.0) -> None:
    """Sleep using time.sleep in small chunks. Immune to asyncio cancel scopes."""
    remaining = total_seconds
    while remaining > 0:
        time.sleep(min(chunk, remaining))
        remaining -= chunk
        if remaining > 0:
            log(f'  Rate limit wait: {remaining:.0f}s remaining...')


def _sleep_until_next_hour() -> float:
    """Calculate seconds until the next hour boundary."""
    now = datetime.now()
    next_hour = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return (next_hour - now).total_seconds()


def _is_rate_limited(stderr_text: str, returncode: int) -> bool:
    """Check if the CLI output indicates a rate limit."""
    if returncode != 0 and _RATE_RE.search(stderr_text):
        return True
    # Also check for specific exit codes
    if returncode in (2, 75):  # 75 = EX_TEMPFAIL
        return True
    return False


def _maybe_log(phase: str, line: str) -> None:
    """Log a line to agent_log.md if it matches meaningful patterns."""
    ll = line.lower()
    stripped = line.lstrip()
    if (any(kw in ll for kw in ['reading', 'writing', 'editing', 'running',
                                 'error', 'fix', 'created', 'modified', 'deleted'])
            or stripped.startswith('#')
            or stripped.startswith('- **')
            or stripped.startswith('* **')):
        log(f'  [{phase.upper()}] {line[:120]}')


def run_claude(prompt: str, worktree: Path, model: str = 'sonnet',
               max_budget: float = 5.0, task: dict | None = None,
               phase: str = 'implement',
               allowed_tools: str | None = None) -> tuple[str, bool]:
    """Run claude CLI and return (output_text, success).

    Handles rate limits with retry. Streams output to log.
    Returns the full stdout text and whether it succeeded.
    """
    import tempfile

    # Write prompt to temp file (avoids shell escaping issues with Hebrew paths)
    prompt_dir = Path(tempfile.mkdtemp(prefix='agent_v2_'))
    prompt_file = prompt_dir / 'prompt.md'
    prompt_file.write_text(prompt, encoding='utf-8')

    # Also save for debugging/artifacts
    if task:
        from .state import _HERE
        work_dir = _HERE / '.agent_work' / str(task.get('id', 'freeform'))
        work_dir.mkdir(parents=True, exist_ok=True)
        artifact = work_dir / f'{phase}_prompt.md'
        artifact.write_text(prompt, encoding='utf-8')

    max_retries = 7  # ~7 hours of retries
    hourly_failures = 0

    for attempt in range(max_retries):
        log(f'  [{phase.upper()}] Starting claude (attempt {attempt + 1}/{max_retries}, model={model})')

        cmd = [
            'claude',
            '--print',
            '--dangerously-skip-permissions',
            '--model', model,
            '--max-budget-usd', str(max_budget),
            '--output-format', 'stream-json',
            '--verbose',
        ]
        if allowed_tools:
            cmd.extend(['--allowedTools', allowed_tools])

        # Read prompt from file
        cmd.extend(['-p', prompt_file.read_text(encoding='utf-8')])

        # Remove CLAUDECODE env var to allow nested sessions (E006)
        env = os.environ.copy()
        env.pop('CLAUDECODE', None)

        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(worktree),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                bufsize=1,  # Line-buffered
            )
        except FileNotFoundError:
            log('  ERROR: claude CLI not found. Is it installed?')
            return '', False

        # Stream JSON events — parse and write human-readable text to live file
        output_texts = []
        result_text = ''
        _LIVE_OUTPUT_PATH.write_text(
            f'=== {phase.upper()} — {datetime.now():%H:%M:%S} ===\n',
            encoding='utf-8',
        )
        try:
            with open(_LIVE_OUTPUT_PATH, 'a', encoding='utf-8') as live_f:
                for raw_line in proc.stdout:
                    raw_line = raw_line.rstrip('\n')
                    if not raw_line:
                        continue
                    try:
                        event = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue

                    etype = event.get('type', '')

                    if etype == 'assistant':
                        # Complete assistant turn — extract text content
                        msg = event.get('message', {})
                        for block in msg.get('content', []):
                            if block.get('type') == 'text':
                                text = block['text']
                                output_texts.append(text)
                                live_f.write(text + '\n')
                                live_f.flush()
                                for tline in text.split('\n'):
                                    _maybe_log(phase, tline)

                    elif etype == 'result':
                        result_text = event.get('result', '')

        except Exception as e:
            log(f'  [{phase.upper()}] Stream read error: {e}')

        proc.wait()
        stderr_text = proc.stderr.read() if proc.stderr else ''
        output_text = result_text or '\n'.join(output_texts)

        # Save output artifact
        if task:
            artifact_out = work_dir / f'{phase}_output.md'
            artifact_out.write_text(output_text, encoding='utf-8')
            if stderr_text.strip():
                artifact_err = work_dir / f'{phase}_stderr.txt'
                artifact_err.write_text(stderr_text, encoding='utf-8')

        # Check for rate limits
        if _is_rate_limited(stderr_text, proc.returncode):
            hourly_failures += 1
            if hourly_failures >= 6:
                # Weekly limit — sleep until Sunday 11 AM
                log('  WARNING: 6 hourly failures — likely weekly limit. Sleeping until Sunday 11 AM.')
                now = datetime.now()
                days_until_sunday = (6 - now.weekday()) % 7
                if days_until_sunday == 0 and now.hour >= 11:
                    days_until_sunday = 7
                target = now.replace(hour=11, minute=0, second=0) + timedelta(days=days_until_sunday)
                sleep_secs = (target - now).total_seconds()

                if task:
                    state = load_state() or {}
                    state['rate_limited'] = True
                    state['rate_limit_resume_at'] = target.isoformat()
                    save_state(state)

                _blocking_sleep(max(sleep_secs, 60))

                if task:
                    state = load_state() or {}
                    state['rate_limited'] = False
                    state.pop('rate_limit_resume_at', None)
                    save_state(state)
                continue

            sleep_secs = _sleep_until_next_hour()
            resume_at = (datetime.now() + timedelta(seconds=sleep_secs)).isoformat()
            log(f'  Rate limited. Sleeping {sleep_secs:.0f}s until next hour ({resume_at})')

            if task:
                state = load_state() or {}
                state['rate_limited'] = True
                state['rate_limit_resume_at'] = resume_at
                save_state(state)

            _blocking_sleep(sleep_secs)

            if task:
                state = load_state() or {}
                state['rate_limited'] = False
                state.pop('rate_limit_resume_at', None)
                save_state(state)
            continue

        # Success or non-rate-limit failure
        if proc.returncode != 0:
            log(f'  [{phase.upper()}] Claude exited with code {proc.returncode}')
            if stderr_text.strip():
                log(f'  stderr: {stderr_text[:300]}')
            return output_text, False

        log(f'  [{phase.upper()}] Completed successfully ({len(output_texts)} turns)')
        return output_text, True

    log(f'  [{phase.upper()}] Exhausted all retries')
    return '', False


def run_implement(task: dict, worktree: Path, model: str = 'sonnet',
                  max_budget: float = 5.0) -> tuple[str, bool]:
    """Run the implement phase — full autonomy to plan+implement+self-test."""
    prompt = build_implement_prompt(task, worktree)
    return run_claude(prompt, worktree, model=model, max_budget=max_budget,
                      task=task, phase='implement')


def run_semantic_verify(task: dict, worktree: Path, git_diff: str,
                        changed_files: list[str], layer_results: str,
                        model: str = 'sonnet') -> tuple[str, bool]:
    """Run Layer 5 semantic verification — fresh context, read-only."""
    prompt = build_verify_prompt(task, git_diff, changed_files, layer_results)
    # Restrict to read-only tools for verification
    return run_claude(prompt, worktree, model=model, max_budget=1.0,
                      task=task, phase='verify',
                      allowed_tools='Read,Glob,Grep,Bash')


def run_fix(task: dict, worktree: Path, verify_output: str,
            issues: list[str], model: str = 'sonnet',
            max_budget: float = 3.0) -> tuple[str, bool]:
    """Run the fix phase with verification feedback."""
    prompt = build_fix_prompt(task, verify_output, issues, worktree)
    return run_claude(prompt, worktree, model=model, max_budget=max_budget,
                      task=task, phase='fix')


def run_review(task: dict, worktree: Path, prev_summary: str,
               advisory_checks: str = '',
               model: str = 'opus', max_budget: float = 5.0) -> tuple[str, bool]:
    """Run the review-and-improve pass — full Claude session with full autonomy."""
    prompt = build_review_prompt(task, worktree, prev_summary,
                                 advisory_checks=advisory_checks)
    return run_claude(prompt, worktree, model=model, max_budget=max_budget,
                      task=task, phase='review')
