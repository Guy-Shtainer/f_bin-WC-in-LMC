# Git Changelog

Human-readable log of every push, with commit hashes for easy revert.
To revert a specific change: `git revert <hash>`
To see what a commit changed: `git show <hash>`

---

## 2026-03-31 — σ_p2p significance criterion, spectrum page overhaul, explorer bugfixes

| Hash | Summary |
|------|---------|
| `a6aa20b` | Add significance criterion to binary fraction graphs + spectrum page zoom nav |
| `cd4b5e8` | End-of-day documentation: work log, TODO audit, E043 error entry |
| `d36cdac` | Paper: add σ_p2p significance criterion and Bartzakos correction to bias correction section |

Earlier today (committed in previous sessions):
| `ee38837` | Restructure spectrum page into 3 tabs with persistent state |
| `04124f8` | Add sigma_p2p significance criterion to bias correction pipeline |
| `9e03996` | Spectrum page: absorption search, LMC correction, show-all-epochs, graph descriptions |
| `4e4b227` | Checkpoint: WIP changes before adding sigma_p2p significance criterion |
| `1d9b11f` | Update settings and command history log |

Tag: `v260331-working` — σ_p2p significance, spectrum overhaul, Dsilva explorer bugfixes, Bartzakos correction.

---

## 2026-03-30 — Langer cadence tab: full graph review + code duplication + D14/D15/D17 fixes + autosave

| Hash | Summary |
|------|---------|
| `eb0d9c6` | Cadence Langer: full graph review, code duplication (5 render files + polling), D14 axis fix, D15 constant-σ row, D17 langer2020 sim + slider dedup |
| `751aa94` | End-of-day docs: TODO #164-168, DOCUMENTATION.md, daily log, learnings |
| `b69e3b3` | Add autosave checkpoint to cadence simulation runner (every 120s) |
| `45f5108` | End-of-day docs: TODO #169 (autosave), DOCUMENTATION.md, daily log |

**Tag: `v260330-working`** — Langer graph review + D14/D15/D17 fixes + simulation autosave

---

## 2026-03-29 — Graph review round 4: all graphs resolved + cadence-aware re-sim

| Hash | Summary |
|------|---------|
| `52ec03e` | Graph review round 4: approve all remaining graphs, cadence-aware re-sim (D15, D17, D18, B2, G1, H2/H4, "Observed"→"Simulated") |
| `599bd8f` | Update GRAPHS_PER_METHOD.md: all graphs resolved, Langer heatmap note |
| `4195cf4` | End-of-day docs: TODO #162/#163 completed, DOCUMENTATION.md, daily log |

**Tag:** `v260329-working` — all 17/17 graphs approved/removed/folded

---

## 2026-03-26 — LogL sign convention unification + graph review round 3

| Hash | Summary |
|------|---------|
| `9b6a823` | Unify logL sign convention (−logL→logL everywhere), remove D4/D5a/Log10 toggle, add find_max to parabolic fit, 1D heatmap fallback, D10 approved |
| `1a4d5df` | End-of-day docs: logL convention, TODO #162/#163, daily log, learnings |

**Tag:** `v260326-working`

---

## 2026-03-25 — Graph review round 2 + page layout overhaul

| Hash | Summary |
|------|---------|
| `afe0732` | Graph review round 2: 9 graphs approved, page layout overhaul (16+ fixes, 4 top heatmaps, LaTeX labels) |
| `481c6f7` | Add runtime render test + pyflakes to error-check pipeline |
| `89f4b5f` | End-of-day docs: TODO #162/#163, DOCUMENTATION.md, daily log, learnings |

**Tag:** `v260325-working` — 9/17 graphs approved, page layout overhaul, error-check upgrade

---

## 2026-03-24 — Graph review overhaul + agent work + validation

| Hash | Summary |
|------|---------|
| `7bbe4a2` | Cherry-pick validation tab from overnight agent |
| `958f50b` | Overnight agent self-upgrades: v2 architecture + agent_app improvements |
| `3211e6d` | Fix NameError: remove fig_masked/fig_pval leftover references |
| `7609139` | [AGENT] Task #0: validation tab improvements |
| `2bc538a` | Agent work: validation improvements, docs, skills, daily log |
| `52f720e` | **Graph review overhaul**: removals (A4/E5/D11), 15 fixes, max-LK framing (-98 lines net) |
| `c7de572` | Add WORKING flags to all 15 verified graph functions |
| `9395333` | End-of-conversation log: graph review session |
| `818d892` | End-of-day docs: TODO, DOCUMENTATION.md, learnings |
| **Tag** | `v260324-working` — working version after full graph review |

---

## 2026-03-23 — Likelihood-only: KS removal, graph review, Sessions 1-3 fixes

| Hash | Summary |
|------|---------|
| `c50c828` | Slim CLAUDE.md + create references/ directory for context management |
| `567a481` | Remove KS/CvM/weighted scoring — likelihood only (backend 2922→2291, 4 KS files deleted) |
| `5ffa312` | Likelihood graph review: Sessions 1-3 fixes + documentation (D1/D5a/D9/A3/D4/D17/B1/D11/D16) |
| `84adbff` | End-of-day docs: E042, TODO #162, daily log, learnings |
| `8fb510c` | Agent app v2: phase-based visualization + v2 launch controls |

**Tag:** `v260323-working` — KS removal complete, likelihood-only graph review (3 sessions), agent v2

---

## 2026-03-22 — BC simplification: 2 scoring methods, cadence-only, graph split

| Hash | Summary |
|------|---------|
| `3359956` | Simplify bias correction: 2 scoring methods, cadence-only, graph split |
| `fca8dce` | Add "Do Not Touch Working Code — 5 Mandatory Blocks" rule |
| `ddfdf23` | Add bias correction feature catalog and per-method graph inventory |
| `43b0759` | Update paper: dual scoring methods, cadence-aware sim, error model |
| `d70c38f` | End-of-day docs: DOCUMENTATION.md, TODO #156-159, daily log |

**Tag:** `v260322-working`

**Highlights:**
- Removed weighted K-S and CvM scoring methods; retained K-S + multinomial likelihood
- Removed non-cadence Dsilva/Langer tabs; cadence-aware simulation is sole approach
- Deleted 4 files (~2400 lines), created 9 independent render files (all < 800 lines)
- Fixed cadence checkpoint resume bug (UI params vs saved params)
- Added "5 Mandatory Blocks" code protection rule to CLAUDE.md
- Created FEATURES.md (128 features) and GRAPHS_PER_METHOD.md (per-method graph catalog)
- Paper updated: dual scoring methods, cadence-aware description, error model for binaries

---

## 2026-03-21 — BC radio buttons, 4D cadence fixes, Dash bias-correction webapp

| Hash | Summary |
|------|---------|
| `7180822` | BC display fixes: radio buttons, 4D cadence marginalization, extra heatmaps |
| `cbfe6d9` | Add Dash bias-correction webapp (bias_app/) + developing-with-dash skill |
| `38281d6` | Install developing-with-streamlit and ui-ux-pro-max skills |
| `5c55267` | Update settings and add Streamlit dark theme config |
| `5d4c733` | End-of-day docs: DOCUMENTATION.md, TODO #141-148 to-test, daily log, memories |

**Tag:** `v260321-working`

**Highlights:**
- BC scoring method sub-tabs replaced with radio buttons; simulation overview always visible
- Fixed cadence_dsilva 4D marginalization IndexError in extra heatmaps + hardened find_best_grid_point
- Fixed cadence_langer pi-squeeze, transpose, logPmax slider, corner plots with logPmax axis
- Built complete Dash bias-correction webapp (bias_app/) with 28 files, nested DMC tabs, 28/70 plots
- Installed 3 skills: developing-with-dash, developing-with-streamlit, ui-ux-pro-max
- E040 (grid/array mismatch), E041 (colorbar labels) added to COMMON_ERRORS

---

## 2026-03-19 — BC architecture overhaul, RV modeling physics mode, plots page plan

| Hash | Summary |
|------|---------|
| `be1377b` | Plots page overhaul plan + agent task + design skills installation |
| `84e7488` | End-of-day docs: DOCUMENTATION.md, daily log, TODO #151-152, COMMON_ERRORS E039 |
| `77fb68e` | RV Modeling: physics-based simulation with real cadences + error models + orbital histograms |
| `d2d27a1` | Bias correction architecture overhaul: sub-tab structure + file splits + logPmax parameter |

**Tag:** `v260319-working`

**Highlights:**
- BC page split 7 oversized files into 13 modules (all under 800 lines), added 5 sub-tabs per model, logPmax as full grid parameter
- RV Modeling dual-mode (Parametric/Physics-based) with real cadences, 6 error model distributions, 9-panel orbital histograms
- Plots page gap analysis: 9 missing plots identified, 410-line agent task plan created with 3× improvement + 3× error check passes
- Installed 3 design skills (Streamlit, UI/UX Pro Max, Scientific Dashboard Design)

---

## 2026-03-18 — Per-epoch error model, spectrum enhancements, RV modeling redesign

| Hash | Summary |
|------|---------|
| `bc377fa` | End-of-day docs: DOCUMENTATION.md, daily log, CLAUDE.md testing rules |
| `efb3372` | Add likelihood CDF visualization + runtime integration test suite |
| `196af6c` | RV Modeling page: 3 new tabs (Simulation/Fitting/Playground) + configurable binning |
| `5939b59` | Spectrum page: nm→Å fix, model browser, O lines, multi-epoch overlay, ΔRV comparison |
| `70b4a80` | **Fix likelihood f_bin=1 degeneracy**: per-epoch error model for binary RVs (Task #140) |
| `d76af72` | Mark tasks #135, #138, #139 as to-test (Group 4 complete) |
| `268b41c` | Add manual likelihood bin edges selector (Task #135) |
| `2756765` | Per-method best-fit summary tables inside each expander (Task #138) |
| `58448d6` | Move CDF comparison to top with per-method toggle checkboxes (Task #139) |
| `4811125` | Mark tasks #133, #134 as to-test (Group 3 complete) |
| `d6c975f` | Interactive Model Explorer with f_bin, pi, sigma sliders (Task #133c) |
| `78fd373` | Add per-method sigma_single slider in scoring method expanders (Task #133b) |
| `555b4ba` | Score-vs-sigma graph for ALL methods (Task #133a) |
| `117cf43` | Extract corner plots to corner_plots.py + expand to 3-param (Task #134) |
| `6f3ccb4` | Mark tasks #132, #136 as to-test (Group 2 complete) |
| `bd32383` | Pass sigma_grid and full ND arrays to parabolic fit |
| `af3a014` | Add sigma_single columns to Scoring Method Comparison table |
| `dd4acfc` | Split analysis.py: extract fitting.py + scoring_detail.py |
| `e747fe0` | Mark tasks #130, #131, #137 as to-test (Group 1 complete) |
| `075a79f` | Fix likelihood interpolation labels: show "Likelihood" not "S" |
| `035d407` | Persist live sigma-vs-score graph after cadence simulation completes |
| `793606c` | Fix p-value labels for non-p-value metrics + add 10 BC tasks |

**Tag:** `v260318-working` — Per-epoch error model for binaries, spectrum enhancements, RV modeling redesign, 10 BC tasks

---

## 2026-03-17 — Multi-score bias correction, RV modeling rebuild, webapp subpackages

Major day: unified all 4 scoring methods into single simulation pass, rebuilt RV modeling page from scratch, split 4 large pages into subpackages.

| Hash | Summary |
|------|---------|
| `76de227` | Pre-refactor revert point |
| `80638c2` | Compute all 4 scoring methods per grid point in single simulation pass |
| `6acfaf6` | Update background runners to accumulate all 4 scoring methods |
| `0790c30` | Remove scoring method radio buttons, show all 4 methods in UI |
| `18d4049` | Add scoring method summary table + per-method expanders |
| `d1acfa2` | Add CDF comparison plot to scoring method summary section |
| `c76b2a6` | Add corner plots and model explorer to per-method expanders |
| `1b6e0de` | Extract duplicated orbital param UI into shared helper functions |
| `955cb86` | Fix cadence Langer shape mismatch in summary + method expanders |
| `7f2e425` | Fix bugs 1,2,11,12,13,14: live heatmaps persist, remove old sections |
| `933c9ed` | Fix bugs 3,4,7,8,9,10: CDF plot, likelihood analysis, corner plot, metrics |
| `1d0e846` | Split bias correction page into app/bc/ package (9,977 → 10 files) |
| `b2d8119` | Fix missing pandas imports, colorbar labels, likelihood normalization |
| `677bcc4` | Show scores in live heatmaps instead of p-values |
| `3f52b16` | Split 06_plots.py (1456 lines) into app/plots/ package |
| `aadfe0d` | Split 11_nres_analysis.py (1117 lines) into app/nres/ package |
| `17fcb69` | Split 12_rv_modeling.py (1193 lines) into app/rv_modeling/ package |
| `0d200e7` | End-of-day: docs, TODO updates, E034 fix, file size limit rule |
| `74cc245` | Add daily log for 2026-03-17 |

**Tag:** `v260317-working`

---

## 2026-03-16 — Likelihood implementation (Dsilva+2023) + cadence fixes

- `8fc7746` Add binned multinomial likelihood (Dsilva+2023) + heatmaps + corner plots
  - multinomial_log_likelihood(): ln L = Σ n_i · ln(p_i) with epsilon floor
  - 'Likelihood (Dsilva+23)' scoring option in all 4 tabs
  - CvM bonus: computes likelihood alongside p-value from same data
  - Likelihood heatmaps, corner plots (red/Hot_r), HDI68 columns
  - Fixed cadence _initargs (11→13 args), ~20 title label ternaries
  - Fixed numpy `or` on arrays crash (E037)
  - Known: likelihood flat across sigma — needs investigation
- `5d6df78` Update docs: likelihood methodology, E037, TODO #128
- `19b08b0` Add daily log entries and session settings for 2026-03-16
- Tag: `v260316-working`

## 2026-03-16 — Cadence bug fixes, NaN guards, live heatmap, table alignment

- `d9c6bbe` Fix cadence bugs + add features: NaN guards, live heatmap, scoring labels, table alignment
  - BUG #119: scoring_method saved in partial checkpoints, enforced on resume
  - BUG #1: exclusion masks rebuilt from value sets (not index arrays)
  - BUG #2: removed st.rerun() after cadence save
  - Feature #120: posterior ± error bars in cadence summary table
  - Feature #121: 1D weighted S-score vs sigma_single plot
  - 5 nanargmax/nanargmin all-NaN crash guards in _render_cadence_results
  - Live heatmap shows current sigma being simulated, not just best
  - S-score labels updated to "weighted S-score"
  - Partial table: .1f precision, added ΔRV/Scoring/Best f_bin columns
- `8a4281c` Add cadence simulation results and partial checkpoints from 2026-03-15/16
- `f717d45` Update user_settings.json
- `1cff912` Update TODO.md: mark #119-121 to-test, add #122-127

---

## 2026-03-15 — CvM scoring, grid exclusion, 3D interpolation, agent replacement

| Hash | Summary |
|------|---------|
| `717fb73` | Cadence Langer 100% working: exclusion propagation, CDF, save/load, load table |
| `3e1f1ab` | Restore old sidebar + task picker UI in agent control panel |
| `c2d1051` | Replace agent system: /run-task command + simplified webapp + launch script |
| `8b65ffe` | Snapshot: pre-agent-rewrite — all current working state |
| `96746fe` | CvM scoring, grid exclusion, 3D interpolation, parabolic fit, neighborhood mode |
| `ffe392a` | Add E030-E033: dict.get None, dict unpack collision, widget keys, unbound var |
| `a259c2d` | Update docs: CvM methodology work log, TODO #117-121, 3 new tasks |
| `0fcac77` | Add weekly-prep command, daily log, update settings |
| `ff3d30d` | Add cadence simulation results, remove stale partial checkpoints |

Major session: implemented CvM inverse-variance-weighted scoring as alternative to KS
(resolves the 3 failed approaches from 2026-03-13). Added grid exclusion UI, parabolic
2D/3D interpolation, neighborhood fitting mode. Fixed 10 bugs (E030-E033 + 6 more).
Replaced overnight agent system with ralph-loop + /run-task command.

Tagged: `v260315-working`

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
