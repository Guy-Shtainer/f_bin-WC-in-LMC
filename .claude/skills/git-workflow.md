---
name: git-workflow
description: Automatically commit, document, and push code changes following the project's commit-per-change rule. This skill triggers whenever code changes have been made and need to be committed, or when the user finishes a task, completes modifications, or says things like "done", "commit this", "push", "save my work", or "we're finished". Also trigger after completing any coding task — even if the user doesn't explicitly ask for a commit. Always commit each logical change separately, update GIT_LOG.md, and push.
---

# Git Workflow

After making code changes, follow this workflow every time:

## 1. Commit Each Logical Change Separately

Group related file changes into one commit. Unrelated changes get separate commits.

```bash
git add <specific files>
git commit -m "$(cat <<'EOF'
Descriptive message explaining why, not just what.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

Stage files by name — never use `git add -A` or `git add .`.

## 2. Update GIT_LOG.md

After all commits are made, append a new entry to `GIT_LOG.md` at the top
(below the header), with today's date, all commit hashes, and a brief
description of what changed and why.

Format:
```markdown
## YYYY-MM-DD — Short description of this push

| Hash | Summary |
|------|---------|
| `abc1234` | First commit message |
| `def5678` | Second commit message |

Brief paragraph explaining the changes.
```

Commit the GIT_LOG.md update as a separate final commit.

## 3. Push

```bash
git push
```

If no upstream branch: `git push -u origin <branch>`.

## Safety Rules

- NEVER force-push (`--force`)
- NEVER amend a previous commit — always create new commits
- NEVER skip hooks (`--no-verify`)
- NEVER commit secrets (`.env`, credentials, API keys)
- If a pre-commit hook fails: fix the issue, re-stage, create a NEW commit

## When NOT to commit

- If there are no changes (`git status` shows clean tree)
- If the user explicitly says "don't commit yet"
