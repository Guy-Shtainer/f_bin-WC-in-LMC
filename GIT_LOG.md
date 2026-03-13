# Git Changelog

Human-readable log of every push, with commit hashes for easy revert.
To revert a specific change: `git revert <hash>`
To see what a commit changed: `git show <hash>`

---

## 2026-03-13 — Variance-weighted scoring debugging (WIP)

| Hash | Summary |
|------|---------|
| `6234a8d` | WIP: variance-weighted scoring — 3 approaches (avg/max/chi2), none working yet |
| `bdabafa` | Update docs: weighted scoring attempts log, TODO #117 status, daily log |

Debugged why weighted KS scoring produced all p≈1.0. Tried 3 approaches: weighted average
(D too small), weighted max (same as standard), chi-squared (σ² from 10k reps is ~1e-4,
χ² explodes to ~1e44). Needs variance normalization fix. Task #117 reverted to `open`.

Tagged: `v260313-working`

---

## 2026-03-12 — Agent worktree isolation, TODO webapp, weighted K-S scoring, cadence fixes

| Hash | Summary |
|------|---------|
| `5898b56` | Add EndConv/EnDay daily logging system |
| `cf84d17` | Add git worktree isolation + stash safety to overnight agent |
| `42eb9e1` | Extract TODO logic into shared module + standalone webapp |
| `165f894` | Add inverse-variance weighted K-S scoring + fix cadence diagnostic histogram |
| `ddab1ca` | Update settings and simulation results |
| `5767006` | Update documentation: COMMON_ERRORS E029, DOCUMENTATION.md work log, TODO.md +6 tasks |
| `aa3dd0a` | Add cadence + Langer simulation result files from today's runs |

Major changes: overnight agent now uses git worktrees (no more branch checkout + stash
that could destroy user files). TODO webapp extracted into reusable module with standalone
entry point. Cadence tabs got inverse-variance weighted K-S scoring and a critical fix
for diagnostic histograms using wrong orbital parameters. 6 new TODO tasks (#113-#118).

Tagged: `v260312-working`

---

## 2026-03-11 — Flicker fix + Langer cadence display

| Hash | Summary |
|------|---------|
| `e966140` | Fix bias correction page flicker (fragment-based polling) + Langer cadence display (fbin×σ) + np.empty bug |
| `236bf15` | Update docs: E026 (flicker), E027 (np.empty), work log, TODO #83 |

Tagged: `v260311-working`

---

## 2026-03-11 — Agent branch cherry-picks + task completions

| Hash | Summary |
|------|---------|
| `4f7b719` | Integrate Task #103: RV Modeling page improvements + bias correction updates |
| `c5a9551` | Fix NRES low-blaze mask not applied to uncertainty arrays + plots null safety |

---

## 2026-03-09 — Dynamic tabs for bias correction page + bug fixes

| Hash | Summary |
|------|---------|
| `50f3d77` | Fix compare tab: missing title arg + run parameter display |
| `f6d57d4` | Update user settings and run history |
| `ee97c8f` | Add bias correction simulation results (Dsilva + Langer) |
| `aa49dd5` | Refactor bias correction page: dynamic tabs with parameterized session keys |
| `bb299da` | Fix dynamic tabs: save button, compare tab bugs, heatmap resolution |

Major refactor of `app/pages/05_bias_correction.py`: extracted Dsilva and Langer
tab bodies into parameterized `_render_dsilva_tab(p)` and `_render_langer_tab(p)`
functions (114 session state keys parameterized). Added `_render_compare_tab(p)`
for side-by-side and overlay comparison of saved results. Added dynamic tab
management with a "+" popover to create new Dsilva, Langer, or Compare tabs
at runtime, each with full independent run capability.

Bug fixes: critical `p` variable shadowing in compare tab dict comprehension,
wrong npz key names (`ks_p_3d`→`ks_p`, `fbin_vals`→`fbin_grid`), missing palette
keys, heatmap `zsmooth='best'` removed for crisp rendering, added explicit save
buttons to both tabs.

---

## 2026-03-01 — To-Do page improvements + full roadmap population

| Hash | Summary |
|------|---------|
| `c6ce6ae` | Populate TODO.md with full project roadmap (22 open tasks) |
| `63be78b` | Rewrite To-Do page with Eisenhower matrix, inline editing, urgent/important fields |

Rewrote To-Do webapp page: added 2×2 Eisenhower matrix (urgent/important
quadrants), inline editing for all task fields, urgent/important boolean
columns, quadrant filtering, and auto-sizing text areas. Populated TODO.md
with all items from my_todo.md covering bias correction, NRES, statistical
modeling, Overleaf paper, plots, GUI fixes, and more (22 open tasks total).

## 2026-03-01 — Documentation system for thesis writing

| Hash | Summary |
|------|---------|
| `ce55316` | Add documentation-for-paper rule to CLAUDE.md |
| `121c722` | Add documentation auto-triggered skill for thesis writing |
| `d3094ad` | Add dated Work Log (Section 7) to DOCUMENTATION.md |

Restructured `DOCUMENTATION.md` with a new Section 7 (Work Log) containing
dated daily entries for each working session. Backfilled entries for 2026-02-25,
2026-02-26, and 2026-03-01 with scientific context, key results, decisions,
and open questions. Added auto-triggered skill to maintain the log going forward.

## 2026-03-01 — Common errors system + np.trapz fix

| Hash | Summary |
|------|---------|
| `9c1a161` | Fix np.trapz → np.trapezoid across all files (numpy 2.x) |
| `b86c5e0` | Add common-errors checking rule to CLAUDE.md |
| `7eae2eb` | Add error-checker auto-triggered skill |
| `9778eb9` | Create COMMON_ERRORS.md with known pitfalls and grep patterns |

Created `COMMON_ERRORS.md` documenting 4 known pitfalls (E001–E004) with
grep-ready regex patterns for automated scanning. Added auto-triggered
`error-checker` skill that checks patterns before/after writing code.
Fixed `np.trapz` → `np.trapezoid` in 4 files (6 occurrences) — numpy 2.x
removed the old name.

## 2026-03-01 — Session 1: marginalization, corner plot, orbital histograms

| Hash | Summary |
|------|---------|
| `409a783` | Expand orbital histograms to 9 panels (3×3) with T₀, ω, M₂ |
| `00a6b40` | Add omega and T₀ to simulate_with_params return dict |
| `4ea67de` | Add marginalized posteriors corner plot to bias correction page |
| `7d2877f` | Add compute_hdi68 marginalization helper (Dsilva 2023 style) |
| `b869cfb` | Add GIT_LOG and TODO maintenance rules to CLAUDE.md |
| `d4061be` | Add TODO.md and interactive to-do page in webapp |
| `32c0b3b` | Add git-workflow and todo-manager auto-triggered skills |
| `e3ec1ea` | Add GIT_LOG.md changelog for easy revert communication |

Dsilva-style marginalization with HDI68 credible intervals for f_bin, π, σ_single.
Corner plot with 1D posteriors (diagonal) and 2D heatmaps (off-diagonal).
Orbital histograms expanded from 5 to 9 panels: logP, e, q, K₁, M₁, M₂, i, ω, T₀.
Added "All binaries (combined)" toggle. Created TODO.md + webapp to-do page.

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
