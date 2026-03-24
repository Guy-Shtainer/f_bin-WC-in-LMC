"""Prompt builders for agent phases.

Each builder returns a string to be passed to `claude -p "..."`.
Key innovation: CLAUDE.md and COMMON_ERRORS.md are injected directly into
the prompt text so the agent CANNOT skip reading them.
"""
from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent.parent
_CLAUDE_MD = _ROOT / 'CLAUDE.md'
_COMMON_ERRORS = _ROOT / 'COMMON_ERRORS.md'
_NOTES_DIR = _ROOT / 'scripts' / '.agent_notes'


def _read_file(path: Path) -> str:
    """Read a file, returning empty string if missing."""
    if path.exists():
        return path.read_text(encoding='utf-8')
    return ''


def _load_notes() -> str:
    """Load all agent notes (.agent_notes/*.md) into a single string."""
    if not _NOTES_DIR.exists():
        return ''
    parts = []
    for f in sorted(_NOTES_DIR.glob('*.md')):
        content = f.read_text(encoding='utf-8').strip()
        if content:
            parts.append(f'### {f.stem}\n{content}')
    return '\n\n'.join(parts)


def build_implement_prompt(task: dict, worktree: Path) -> str:
    """Build the full implement-phase prompt.

    This is the main prompt — Claude gets full context and autonomy to plan,
    implement, and self-test within a single session.
    """
    claude_md = _read_file(_CLAUDE_MD)
    common_errors = _read_file(_COMMON_ERRORS)
    notes = _load_notes()

    task_id = task.get('id', '?')
    title = task.get('title', 'Unknown task')
    description = task.get('description', title)

    prompt = f"""You are an autonomous coding agent working on the WR Binary Analysis project.
You are working in an isolated git worktree at: {worktree}

# YOUR TASK
Task #{task_id}: {title}
{description}

# PROJECT RULES (MANDATORY — read carefully)
{claude_md}

# COMMON ERRORS (check your code against ALL of these)
{common_errors}

"""
    if notes:
        prompt += f"""# LEARNED NOTES FROM PREVIOUS TASKS
{notes}

"""

    prompt += """# YOUR WORKFLOW
Follow these steps carefully. Take your time — quality matters more than speed.

1. **UNDERSTAND**: Read the relevant source files. Understand the current state before changing anything.
2. **PLAN**: Think out loud about your approach. Consider edge cases and how your changes interact with existing code.
3. **IMPLEMENT**: Make the changes. Follow all project conventions from CLAUDE.md.
4. **SELF-TEST after EVERY file edit**:
   - Run: `conda run -n guyenv python -m py_compile <file>`
   - If editing app/ files, also run: `conda run -n guyenv python -c "import sys; sys.path.insert(0, '<worktree>/app'); import <module>"`
5. **REVIEW**: After all edits, re-read your changes and check against COMMON_ERRORS patterns.
6. **FIX**: If you find any issues in your review, fix them immediately.

# CRITICAL CONSTRAINTS
- Use `conda run -n guyenv python ...` for ALL Python execution
- Do NOT run any git commands (the supervisor handles git)
- Do NOT modify TODO.md, DOCUMENTATION.md, or GIT_LOG.md
- Do NOT modify files that are not related to the task
- Do NOT touch code flagged with `# ── WORKING · ` comments
- Import convention for app/pages/: `from shared import ...` (NOT `from app.shared import ...`)
- PLOTLY_THEME: use dict-merge pattern `**{**PLOTLY_THEME, 'title': dict(text='...')}` — NEVER pass as both kwarg and spread
- File size limit: 800 lines per .py file
- Always use `bool()` to cast numpy.bool_ before `is True` checks

# WHEN YOU'RE DONE
Summarize what you changed and why. List every file you modified.
"""
    return prompt


def build_verify_prompt(task: dict, git_diff: str, changed_files: list[str],
                        layer_results: str) -> str:
    """Build the semantic verification prompt (Layer 5).

    This runs AFTER layers 1-4 (syntax, working-code, functional, pattern scan)
    have already passed. Claude only needs to check semantic correctness.
    """
    task_id = task.get('id', '?')
    title = task.get('title', 'Unknown task')
    description = task.get('description', title)

    prompt = f"""You are a code reviewer verifying changes made by an autonomous agent.

# ORIGINAL TASK
Task #{task_id}: {title}
{description}

# AUTOMATED CHECKS ALREADY PASSED
The following checks have already passed:
{layer_results}

# FILES CHANGED
{chr(10).join(f'- {f}' for f in changed_files)}

# GIT DIFF
```diff
{git_diff}
```

# YOUR REVIEW CHECKLIST
1. Does the implementation actually fulfill the task requirements?
2. Are there logic errors that compile but produce wrong results?
3. Is there scope creep (changes beyond what was asked)?
4. Are there any subtle bugs (off-by-one, wrong variable, missing edge case)?
5. Does the code follow the project conventions visible in the diff context?

# OUTPUT FORMAT (CRITICAL — follow exactly)
Write your analysis, then end with EXACTLY one of these lines:

VERDICT: PASS

or

VERDICT: FAIL
ISSUE: <file>:<line> - <description>
ISSUE: <file>:<line> - <description>

The VERDICT line must be on its own line with no other text.
If FAIL, list every issue with the ISSUE: prefix format.
"""
    return prompt


def build_review_prompt(task: dict, worktree: Path, prev_summary: str,
                        advisory_checks: str = '') -> str:
    """Build the review-and-improve prompt for pass 2+.

    This is a full Claude session with full autonomy. The reviewer reads the
    current state of the code, tests it, finds issues, and fixes them.
    """
    claude_md = _read_file(_CLAUDE_MD)
    common_errors = _read_file(_COMMON_ERRORS)
    notes = _load_notes()

    task_id = task.get('id', '?')
    title = task.get('title', 'Unknown task')
    description = task.get('description', title)

    prompt = f"""You are reviewing and improving code written by a previous agent session.
You are working in an isolated git worktree at: {worktree}

# ORIGINAL TASK
Task #{task_id}: {title}
{description}

# WHAT THE PREVIOUS AGENT DID
{prev_summary[:4000]}

# PROJECT RULES (MANDATORY — read carefully)
{claude_md}

# COMMON ERRORS (check against ALL of these)
{common_errors}

"""
    if advisory_checks:
        prompt += f"""# AUTOMATED CHECK RESULTS (advisory — use your judgment)
{advisory_checks}

"""

    if notes:
        prompt += f"""# LEARNED NOTES FROM PREVIOUS TASKS
{notes}

"""

    prompt += """# YOUR WORKFLOW
You are the quality gate. Be thorough but practical.

1. **READ the changed files** — understand what was implemented and how.
2. **TEST everything**:
   - Run `conda run -n guyenv python -m py_compile <file>` on every changed .py file
   - For app/ files, test imports: `conda run -n guyenv python -c "import sys; sys.path.insert(0, 'app'); import <module>"`
   - Look for logic bugs, edge cases, missing error handling
3. **CHECK against COMMON_ERRORS** — scan for known bad patterns
4. **FIX any issues you find** — you have full edit access, fix them directly
5. **RE-TEST after fixes** — make sure your fixes compile and import correctly
6. **ASSESS overall quality** — does this implementation fully satisfy the task?

# CRITICAL CONSTRAINTS
- Use `conda run -n guyenv python ...` for ALL Python execution
- Do NOT run any git commands (the supervisor handles git)
- Do NOT modify TODO.md, DOCUMENTATION.md, or GIT_LOG.md
- Do NOT touch code flagged with `# ── WORKING · ` comments
- Import convention for app/pages/: `from shared import ...` (NOT `from app.shared import ...`)

# WHEN YOU'RE DONE
Summarize your findings and any fixes you made. End with one of:
- **LGTM** — if the implementation is correct and complete
- **FIXED** — if you found and fixed issues (list what you fixed)
- **ISSUES REMAIN** — if there are problems you couldn't fix (describe them)
"""
    return prompt


def build_fix_prompt(task: dict, verify_output: str, issues: list[str],
                     worktree: Path) -> str:
    """Build the fix-phase prompt with verification feedback (legacy, kept for compatibility)."""
    task_id = task.get('id', '?')
    title = task.get('title', 'Unknown task')
    description = task.get('description', title)

    common_errors = _read_file(_COMMON_ERRORS)

    issues_text = '\n'.join(f'- {issue}' for issue in issues) if issues else verify_output

    prompt = f"""You are fixing issues found during code review.
You are working in an isolated git worktree at: {worktree}

# ORIGINAL TASK
Task #{task_id}: {title}
{description}

# VERIFICATION FEEDBACK
{verify_output[:3000]}

# SPECIFIC ISSUES TO FIX
{issues_text}

# COMMON ERRORS (check fixes against these)
{common_errors}

# INSTRUCTIONS
1. Fix ONLY the issues listed above. Do NOT add features or refactor unrelated code.
2. After each fix, run: `conda run -n guyenv python -m py_compile <file>`
3. If fixing an app/ file, also test the import works.
4. Use `conda run -n guyenv python ...` for ALL Python execution.
5. Do NOT run any git commands.
6. Do NOT touch code flagged with `# ── WORKING · ` comments.

# WHEN YOU'RE DONE
Summarize what you fixed and confirm each issue is resolved.
If you discovered a NEW error pattern not in COMMON_ERRORS.md, describe it in this format:
NEW_ERROR: <pattern_name> | <grep_pattern> | <description>
"""
    return prompt


