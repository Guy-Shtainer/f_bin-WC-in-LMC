Commit and push all pending changes, following the project's commit-per-change rule.

## Workflow

1. Run `git status` to see all modified, staged, and untracked files.
2. Run `git diff` and `git diff --cached` to understand what changed.
3. Run `git log --oneline -5` to match the existing commit message style.
4. **Group changes into logical commits.** Each commit should represent ONE logical change
   (e.g., "fix bug in X", "add feature Y", "update config Z"). Never bundle unrelated
   changes into a single commit — this provides fine-grained rollback points and clear history.
5. For each logical group:
   - Stage only the relevant files by name (`git add file1 file2`). Never use `git add -A` or
     `git add .` — these can accidentally include secrets, large binaries, or unrelated files.
   - Write a concise commit message (1–2 sentences) that explains **why**, not just **what**.
   - Use a HEREDOC for the commit message to ensure proper formatting:
     ```bash
     git commit -m "$(cat <<'EOF'
     Your commit message here.

     Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
     EOF
     )"
     ```
6. After all commits are done, push to the remote:
   ```bash
   git push
   ```
   If there is no upstream branch set, use `git push -u origin <branch>`.
7. Run `git status` one final time to confirm a clean working tree.

## Safety Rules

- NEVER force-push (`--force`) unless the user explicitly asks for it.
- NEVER amend a previous commit — always create new commits.
- NEVER skip hooks (`--no-verify`).
- NEVER commit files that look like secrets (`.env`, `credentials.json`, API keys).
- If a pre-commit hook fails, fix the issue, re-stage, and create a NEW commit.
- If there are no changes to commit, say so and do nothing.

## What NOT to Commit

Check `.gitignore` before staging. Common exclusions in this project:
- `Data/` — large observation FITS files
- `__pycache__/`, `*.pyc` — Python bytecode
- `.DS_Store` — macOS metadata
- `Backups/` — manual backup files
- `*.log` — debug logs

## If $ARGUMENTS is provided

Interpret it as a hint for what to commit. Examples:
- `/git` — commit and push everything pending
- `/git just the skills` — only commit skill-related changes
- `/git don't push` — commit but skip the push step
