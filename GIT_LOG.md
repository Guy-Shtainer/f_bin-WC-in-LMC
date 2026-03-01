# Git Changelog

Human-readable log of every push, with commit hashes for easy revert.
To revert a specific change: `git revert <hash>`
To see what a commit changed: `git show <hash>`

---

## 2026-03-01 — Infrastructure: skills, docs, papers

| Hash | Summary |
|------|---------|
| `8b1e616` | Add /git slash command for commit-per-change workflow |
| `9106340` | Add reference papers (Dsilva 2023, Langer 2020) |
| `d4d2ae8` | Rewrite slash commands with detailed instructions and edge cases |
| `8ca15dd` | Rewrite auto-triggered skills with YAML frontmatter and improved content |
| `1d75bad` | Add DOCUMENTATION.md with scientific methodology and key results |
| `774334e` | Improve bias correction diagnostic plots |

Rewrote all 4 auto-triggered skills with YAML frontmatter for reliable triggering.
Rewrote 3 slash commands with detailed edge-case handling. Added DOCUMENTATION.md
for thesis writing. Added reference papers to papers/ folder.

## 2026-02-26 — Bias correction page fixes

| Hash | Summary |
|------|---------|
| `d9f85ef` | Fix heatmap duplicate key error — remove keys from st.empty() calls |
| `232fb0c` | Add commit-per-change and backup-before-edit rules to CLAUDE.md |
| `9f04361` | Fix StreamlitDuplicateElementKey in heatmap display |

Fixed duplicate Streamlit widget key errors in the bias correction heatmap.
Added code quality rules to CLAUDE.md.

## 2026-02-25 — Initial commit + early backups

| Hash | Summary |
|------|---------|
| `4e3588b` | Initial commit |

Project setup with full analysis pipeline.
