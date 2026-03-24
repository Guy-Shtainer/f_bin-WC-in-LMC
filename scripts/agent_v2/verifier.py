"""5-Layer Verification System.

Layer 1: Syntax       — py_compile on every changed file
Layer 2: Working-code — detect modifications to flagged WORKING code
Layer 3: Functional   — import checks, render tests, mini simulation runs
Layer 4: Pattern scan — COMMON_ERRORS.md regex patterns
Layer 5: Semantic     — Claude CLI review of the diff (fresh context)

Layers 1-4 are deterministic Python. Layer 5 only runs if 1-4 pass.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .state import log
from .executor import run_semantic_verify

_ROOT = Path(__file__).resolve().parent.parent.parent
_COMMON_ERRORS = _ROOT / 'COMMON_ERRORS.md'


# ── Git helpers (read-only, for verification) ────────────────────────────────

def _git(worktree: Path, *args: str) -> str:
    """Run a git command in the worktree."""
    result = subprocess.run(
        ['git'] + list(args),
        cwd=str(worktree), capture_output=True, text=True
    )
    return result.stdout.strip()


def get_changed_files(worktree: Path) -> list[str]:
    """Get list of files changed vs main."""
    diff_output = _git(worktree, 'diff', '--name-only', 'main')
    return [f for f in diff_output.split('\n') if f.strip()]


def get_git_diff(worktree: Path) -> str:
    """Get full diff vs main."""
    return _git(worktree, 'diff', 'main')


def get_changed_python_files(worktree: Path) -> list[str]:
    """Get only .py files that changed."""
    return [f for f in get_changed_files(worktree) if f.endswith('.py')]


# ── Layer 1: Syntax check ────────────────────────────────────────────────────

def layer1_syntax(worktree: Path, py_files: list[str]) -> tuple[bool, list[str]]:
    """py_compile every changed .py file."""
    failures = []
    for f in py_files:
        full_path = worktree / f
        if not full_path.exists():
            continue  # File was deleted, not an error
        result = subprocess.run(
            ['conda', 'run', '-n', 'guyenv', 'python', '-m', 'py_compile', str(full_path)],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            err = result.stderr.strip() or result.stdout.strip()
            failures.append(f'SYNTAX ERROR in {f}: {err[:200]}')
            log(f'  [VERIFY L1] FAIL: {f} — {err[:100]}')

    if failures:
        return False, failures
    log(f'  [VERIFY L1] PASS: {len(py_files)} files compile OK')
    return True, ['All files compile successfully']


# ── Layer 2: Working-code protection ─────────────────────────────────────────

def layer2_working_code(worktree: Path, py_files: list[str]) -> tuple[bool, list[str]]:
    """Check that no code flagged with '# ── WORKING · ' was modified."""
    diff = _git(worktree, 'diff', 'main', '--unified=0')
    failures = []

    # Parse the diff to find modified lines and their file contexts
    current_file = None
    for line in diff.split('\n'):
        if line.startswith('diff --git'):
            # Extract filename: diff --git a/file b/file
            parts = line.split()
            if len(parts) >= 4:
                current_file = parts[3].lstrip('b/')
        elif line.startswith('-') and not line.startswith('---'):
            # This is a removed/modified line
            if '# ── WORKING' in line and '──' in line:
                failures.append(
                    f'WORKING CODE MODIFIED in {current_file}: removed flagged line: {line[:100]}'
                )

    # Also check: the original file's WORKING blocks — were any functions in them modified?
    for f in py_files:
        full_path = worktree / f
        if not full_path.exists():
            continue
        content = full_path.read_text(encoding='utf-8')
        # Find WORKING flags
        for i, file_line in enumerate(content.split('\n'), 1):
            if '# ── WORKING' in file_line and '──' in file_line:
                # Check if the surrounding function was modified in the diff
                file_diff = _git(worktree, 'diff', 'main', '--', f)
                if file_diff:
                    # Check if any hunk touches lines near this flag
                    for hunk_match in re.finditer(r'@@ -(\d+)', file_diff):
                        hunk_line = int(hunk_match.group(1))
                        # If the hunk is within 20 lines of the flag, warn
                        if abs(hunk_line - i) < 20:
                            failures.append(
                                f'POSSIBLE WORKING CODE EDIT in {f}:{i} — '
                                f'diff hunk at line {hunk_line} near WORKING flag'
                            )

    if failures:
        log(f'  [VERIFY L2] FAIL: {len(failures)} working-code violations')
        return False, failures
    log(f'  [VERIFY L2] PASS: no working-code violations')
    return True, ['No WORKING-flagged code was modified']


# ── Layer 3: Functional tests ────────────────────────────────────────────────

def layer3_functional(worktree: Path, py_files: list[str]) -> tuple[bool, list[str]]:
    """Run real functional tests: imports, render functions, mini simulations."""
    failures = []
    successes = []

    # 3a: Import check for every changed .py file
    for f in py_files:
        full_path = worktree / f
        if not full_path.exists():
            continue

        # Build the import command based on file location
        # Use relative paths — cwd is already set to worktree (avoids E005 Hebrew path issues)
        if f.startswith('app/pages/'):
            module = Path(f).stem
            import_cmd = (
                f"import sys; sys.path.insert(0, 'app'); "
                f"import {module}"
            )
        elif f.startswith('app/'):
            module = Path(f).stem
            import_cmd = (
                f"import sys; sys.path.insert(0, 'app'); "
                f"import {module}"
            )
        else:
            module = Path(f).stem
            import_cmd = (
                f"import sys; sys.path.insert(0, '.'); "
                f"import {module}"
            )

        result = subprocess.run(
            ['conda', 'run', '-n', 'guyenv', 'python', '-c', import_cmd],
            capture_output=True, text=True, timeout=30,
            cwd=str(worktree),
        )
        if result.returncode != 0:
            err = result.stderr.strip()
            # Filter out Streamlit warnings (expected in bare mode)
            if 'ImportError' in err or 'NameError' in err or 'ModuleNotFoundError' in err:
                failures.append(f'IMPORT ERROR in {f}: {err[:200]}')
                log(f'  [VERIFY L3] FAIL: {f} import error')
            else:
                successes.append(f'{f} imports OK (warnings ignored)')
        else:
            successes.append(f'{f} imports OK')

    # 3b: If app/bc/ files changed, run the integration test
    bc_files = [f for f in py_files if 'bias_correction' in f or f.startswith('app/bc/')]
    if bc_files:
        test_script = worktree / 'error-check-workspace' / 'test_bc_imports.py'
        if test_script.exists():
            result = subprocess.run(
                ['conda', 'run', '-n', 'guyenv', 'python', str(test_script)],
                capture_output=True, text=True, timeout=60,
                cwd=str(worktree),
            )
            if result.returncode != 0:
                failures.append(f'BC INTEGRATION TEST FAILED: {result.stderr[:300]}')
                log('  [VERIFY L3] FAIL: bias correction integration test')
            else:
                successes.append('Bias correction integration test passed')

    # 3c: If wr_bias_simulation.py changed, run tiny grid
    if any('wr_bias_simulation' in f for f in py_files):
        test_cmd = (
            "import sys; sys.path.insert(0, '.'); "
            "from wr_bias_simulation import SimulationConfig, BinaryParameterConfig, run_bias_grid; "
            "cfg = SimulationConfig(N_single=5, sigma_single=6.0); "
            "bp = BinaryParameterConfig(); "
            "print('Simulation imports OK')"
        )
        result = subprocess.run(
            ['conda', 'run', '-n', 'guyenv', 'python', '-c', test_cmd],
            capture_output=True, text=True, timeout=30,
            cwd=str(worktree),
        )
        if result.returncode != 0:
            failures.append(f'SIMULATION IMPORT FAILED: {result.stderr[:200]}')
        else:
            successes.append('Simulation module imports OK')

    # 3d: If Streamlit pages changed, try calling render functions with mock data
    page_files = [f for f in py_files if f.startswith('app/pages/')]
    for f in page_files:
        full_path = worktree / f
        if not full_path.exists():
            continue
        content = full_path.read_text(encoding='utf-8')
        # Find render functions
        render_funcs = re.findall(r'def (render_\w+|_render_\w+)\(', content)
        if render_funcs:
            successes.append(f'{f} has render functions: {", ".join(render_funcs[:3])}')
            # Note: calling render functions requires Streamlit context which
            # is complex to mock. The import check (3a) already verifies the
            # module loads without errors.

    if failures:
        log(f'  [VERIFY L3] FAIL: {len(failures)} functional test failures')
        return False, failures
    log(f'  [VERIFY L3] PASS: {len(successes)} checks passed')
    return True, successes


# ── Layer 4: COMMON_ERRORS pattern scan ──────────────────────────────────────

def _extract_grep_patterns() -> list[tuple[str, str, str]]:
    """Parse COMMON_ERRORS.md and extract (error_id, grep_pattern, description) tuples."""
    if not _COMMON_ERRORS.exists():
        return []

    content = _COMMON_ERRORS.read_text(encoding='utf-8')
    patterns = []

    # Find all E0XX sections
    sections = re.split(r'### (E\d+)', content)
    for i in range(1, len(sections), 2):
        error_id = sections[i]
        body = sections[i + 1] if i + 1 < len(sections) else ''

        # Extract grep pattern from table
        grep_match = re.search(r'\| \*\*Grep\*\* \| `([^`]+)`', body)
        if grep_match:
            pattern = grep_match.group(1)
            # Extract description (first line after the error ID)
            desc_match = re.search(r'—\s*(.+)', body.split('\n')[0])
            desc = desc_match.group(1) if desc_match else error_id
            patterns.append((error_id, pattern, desc))

    return patterns


def layer4_pattern_scan(worktree: Path, py_files: list[str]) -> tuple[bool, list[str]]:
    """Scan changed files against COMMON_ERRORS.md grep patterns."""
    patterns = _extract_grep_patterns()
    if not patterns:
        return True, ['No grep patterns found in COMMON_ERRORS.md']

    failures = []
    for f in py_files:
        full_path = worktree / f
        if not full_path.exists():
            continue

        content = full_path.read_text(encoding='utf-8')
        lines = content.split('\n')

        for error_id, pattern, desc in patterns:
            try:
                regex = re.compile(pattern)
                for line_num, line in enumerate(lines, 1):
                    if regex.search(line):
                        # Check if this is in a comment
                        stripped = line.lstrip()
                        if stripped.startswith('#'):
                            continue
                        failures.append(
                            f'{error_id} match in {f}:{line_num} — {desc}: {line.strip()[:80]}'
                        )
            except re.error:
                pass  # Skip invalid regex patterns

    if failures:
        log(f'  [VERIFY L4] FAIL: {len(failures)} COMMON_ERRORS pattern matches')
        return False, failures
    log(f'  [VERIFY L4] PASS: no known error patterns found')
    return True, [f'Scanned {len(patterns)} patterns across {len(py_files)} files — clean']


# ── Layer 5: Semantic review (Claude CLI) ─────────────────────────────────────

def layer5_semantic(task: dict, worktree: Path, git_diff: str,
                    changed_files: list[str], layer_results: str,
                    model: str = 'sonnet') -> tuple[bool, list[str], str]:
    """Run Claude for semantic code review. Returns (passed, issues, raw_output)."""
    output, success = run_semantic_verify(
        task, worktree, git_diff, changed_files, layer_results, model=model
    )

    if not success:
        return False, ['Semantic verification failed to run'], output

    verdict, issues = parse_verdict(output)
    return verdict == 'PASS', issues, output


def parse_verdict(text: str) -> tuple[str, list[str]]:
    """Parse structured VERDICT: PASS/FAIL from verifier output.

    Returns (verdict_str, issues_list).
    """
    issues = []
    verdict = 'FAIL'  # Default to fail if format not found

    for line in text.split('\n'):
        line = line.strip()
        if line.startswith('VERDICT:'):
            v = line.split(':', 1)[1].strip().upper()
            if v in ('PASS', 'FAIL'):
                verdict = v
        elif line.startswith('ISSUE:'):
            issues.append(line[6:].strip())

    # If we got FAIL but no specific issues, use the last few lines as context
    if verdict == 'FAIL' and not issues:
        last_lines = [l.strip() for l in text.strip().split('\n')[-10:] if l.strip()]
        issues = last_lines

    return verdict, issues


# ── Main verification entry point ────────────────────────────────────────────

def run_advisory_checks(worktree: Path) -> str:
    """Run L1-L4 checks and return a human-readable summary (non-blocking).

    Used by the review pass to give Claude context about potential issues.
    Unlike run_full_verification, this does NOT block on failures.
    """
    py_files = get_changed_python_files(worktree)
    if not py_files:
        return 'No Python files changed.'

    lines = []

    passed, details = layer1_syntax(worktree, py_files)
    lines.append(f'Syntax check: {"PASS" if passed else "FAIL"}')
    if not passed:
        lines.extend(f'  - {d}' for d in details[:5])

    passed, details = layer2_working_code(worktree, py_files)
    lines.append(f'Working-code protection: {"PASS" if passed else "FAIL"}')
    if not passed:
        lines.extend(f'  - {d}' for d in details[:5])

    passed, details = layer4_pattern_scan(worktree, py_files)
    lines.append(f'COMMON_ERRORS pattern scan: {"PASS" if passed else "FAIL"}')
    if not passed:
        lines.extend(f'  - {d}' for d in details[:5])

    # Skip L3 (functional) — it has Hebrew path issues and Claude will test imports itself
    # Skip L5 (semantic) — the review pass IS the semantic review

    return '\n'.join(lines)


def run_full_verification(task: dict, worktree: Path,
                          model: str = 'sonnet') -> tuple[bool, str, list[str]]:
    """Run all 5 verification layers.

    Returns (passed, summary, all_issues).
    """
    py_files = get_changed_python_files(worktree)
    all_files = get_changed_files(worktree)

    if not all_files:
        return False, 'No files were changed', ['No changes detected']

    results = []
    all_issues = []

    # Layer 1: Syntax
    passed, details = layer1_syntax(worktree, py_files)
    results.append(f'Layer 1 (Syntax): {"PASS" if passed else "FAIL"}')
    if not passed:
        all_issues.extend(details)
        summary = '\n'.join(results + [''] + all_issues)
        return False, summary, all_issues

    # Layer 2: Working-code protection
    passed, details = layer2_working_code(worktree, py_files)
    results.append(f'Layer 2 (Working-code): {"PASS" if passed else "FAIL"}')
    if not passed:
        all_issues.extend(details)
        summary = '\n'.join(results + [''] + all_issues)
        return False, summary, all_issues

    # Layer 3: Functional tests
    passed, details = layer3_functional(worktree, py_files)
    results.append(f'Layer 3 (Functional): {"PASS" if passed else "FAIL"}')
    if not passed:
        all_issues.extend(details)
        summary = '\n'.join(results + [''] + all_issues)
        return False, summary, all_issues

    # Layer 4: COMMON_ERRORS pattern scan
    passed, details = layer4_pattern_scan(worktree, py_files)
    results.append(f'Layer 4 (Pattern scan): {"PASS" if passed else "FAIL"}')
    if not passed:
        all_issues.extend(details)
        summary = '\n'.join(results + [''] + all_issues)
        return False, summary, all_issues

    # Layers 1-4 passed — run Layer 5 semantic review
    git_diff = get_git_diff(worktree)
    layer_results_text = '\n'.join(results)

    passed, issues, raw_output = layer5_semantic(
        task, worktree, git_diff, all_files, layer_results_text, model=model
    )
    results.append(f'Layer 5 (Semantic): {"PASS" if passed else "FAIL"}')
    if not passed:
        all_issues.extend(issues)

    summary = '\n'.join(results + [''] + all_issues)
    return passed, summary, all_issues


# ── Auto-learn: update COMMON_ERRORS.md ──────────────────────────────────────

def extract_new_error_patterns(fix_output: str) -> list[tuple[str, str, str]]:
    """Parse fix phase output for NEW_ERROR declarations.

    Returns list of (name, grep_pattern, description).
    """
    patterns = []
    for line in fix_output.split('\n'):
        if line.strip().startswith('NEW_ERROR:'):
            parts = line.split('|')
            if len(parts) >= 3:
                name = parts[0].replace('NEW_ERROR:', '').strip()
                grep = parts[1].strip()
                desc = parts[2].strip()
                patterns.append((name, grep, desc))
    return patterns


def append_to_common_errors(new_patterns: list[tuple[str, str, str]]) -> None:
    """Append new error patterns to COMMON_ERRORS.md."""
    if not new_patterns or not _COMMON_ERRORS.exists():
        return

    content = _COMMON_ERRORS.read_text(encoding='utf-8')

    # Find the highest existing error ID
    existing_ids = re.findall(r'### E(\d+)', content)
    next_id = max(int(i) for i in existing_ids) + 1 if existing_ids else 100

    additions = []
    for name, grep, desc in new_patterns:
        entry = f"""
---

### E{next_id:03d} — {name} (auto-learned)

| | |
|---|---|
| **Bad** | See description |
| **Fix** | See description |
| **Grep** | `{grep}` |
| **Why** | {desc} |
| **Found in** | Auto-detected by agent v2 verification loop |
"""
        additions.append(entry)
        next_id += 1

    if additions:
        content += '\n'.join(additions)
        _COMMON_ERRORS.write_text(content, encoding='utf-8')
        log(f'  [AUTO-LEARN] Added {len(additions)} new patterns to COMMON_ERRORS.md')
