# Git Changelog

Human-readable log of every push, with commit hashes for easy revert.
To revert a specific change: `git revert <hash>`
To see what a commit changed: `git show <hash>`

---

## 2026-05-04 — End-of-day docs only: CDF panel enrichment + Reset-to-best fix UNCOMMITTED awaiting visual sign-off

**Tag:** *(no tag — code work uncommitted; user explicitly said "we will continue tomorrow" on the CDF panel and "i think its still the same" on Reset-to-best, both pending visual confirmation. Two prior tags `v260430-partial-working` and `v260430-evening-working` remain the latest "working" markers.)*

| Hash | Summary |
|------|---------|
| `203a4f4` | End-of-day 2026-05-04 docs: TODO entries 198-199, DOCUMENTATION §7, daily log, COMMON_ERRORS E045, learnings + plot prefs |

**Major changes (committed):**
- **Docs end-of-day (2026-05-04):** TODO.md entries #198 (bias-correction CDF Comparison panel enrichment — per-star truth dots, per-rank gradient markers, mean line, marker-shape legend) and #199 (Likelihood Model Explorer Reset-to-best fix — joint argmax + slider quantisation bypass). DOCUMENTATION.md §7 gets a new 2026-05-04 entry with methodology notes for the paper (per-rank decomposition of the model CDF, Streamlit float-slider quantisation as a silent precision trap). COMMON_ERRORS.md gains **E045** (`st.slider` with float bounds quantises value to implicit step `(max-min)/100` — Bad/Fix/Why/Found-in/Prevention with the Reset-to-best workaround documented). `.claude/references/learnings.md` extends two existing rules: "Silent `except: pass` is a trap" (any new fallback path needs `st.warning(traceback)` during dev; revert to silent only after fixture verification) and "`result['settings']` is JSON string OR 0-d ndarray" (the `np.savez` round-trip can return either form; fix detects `isinstance(_settings_raw, np.ndarray)` first, calls `.item()` to unwrap, then guards with `isinstance(_, dict)` before falling back). `memory/plot_preferences.md` gets a new 2026-05-04 section documenting the CDF Comparison panel conventions (data semantics, marker conventions, colorbar scheme, mean-vs-median style, logL display, LIVE renderer architecture). `.claude/agents/coder.md` gains a "Plan-mode policy" exception clause (skip plan mode when invoked with an approved plan reference) — workaround for an unresolved harness-level plan-mode auto-injection issue. Daily log gained 4 conversation entries (16:04, 19:09, 23:38, 23:41).

**Uncommitted on `main` (today's code work + 4-day backlog from `v260430-*`, all pending visual sign-off):**
- **TODAY — Bias-correction CDF Comparison panel enrichment (TODO #198, 5 chunks across 6 files).** `wr_bias_simulation.py` (4 new arrays in `simulate_delta_rv_cadence_aware` return; 11-tuple in `_single_grid_task_cadence_aware`; `_process_result` and `run_bias_grid_cadence_aware` mirror); `app/bc/runners_cadence.py` (4 new `best_*` keys threaded through); `app/bc/render_lk_explorer.py` and `_langer.py` (`CDFBandResult` NamedTuple + `_me_cdf_band` returns); `app/bc/render_shared.py` and `_langer.py` (per-star truth dots, per-rank median squares, per-rank mean triangles, native Plotly colorbar, phantom legend traces, surface-except diagnostics). User explicitly said "its not perfect, we will continue tomorrow" — visual approval pending on 5 features (truth dots on observed CDF, squares riding median lines, triangles riding mean lines, "MC binary fraction" colorbar, phantom legend entries). After visual approval: revert `st.error`/`st.warning` diagnostics back to silent `pass`.
- **TODAY — Likelihood Model Explorer Reset-to-best fix (TODO #199, 2 rounds in 1 file).** `app/bc/render_lk_explorer.py` only. Round 1: moved joint-argmax decomposition above slider rendering, replaced slider defaults with `_bf_*` values, fixed σ/lp non-scanned-axis fallbacks (use `sigma_grid[0]` / `bin_cfg.logP_max` instead of `sigma_meas`), rewrote caption with joint-argmax + `(fixed)` annotations. Round 2: added `_just_reset` detection via `_last_rc` tracker, override `me_*` and `_eff_logPmax` with exact `_bf_*` floats post-widget-render (only on first render after Reset; subsequent slider movements pass through untouched). User reported Round 2 may not have closed the gap entirely ("i think its still the same") but ended conversation before screenshot — pending next-session visual confirmation. Backup: `Backups/render_lk_explorer.py.bak`.
- **All `v260430-*` backlog still uncommitted on `main`** — Sprint 4 validation-tab overhaul (TODO #191), mock-data overhaul (TODO #192), Explorer ↔ grid parity (TODO #195), three-stage binarity memo (TODO #194), logP_max scan fixed-value input (TODO #196), skill/agent system reorg, all carrying forward unchanged. See `v260430-partial-working` entry below for full file list.

**Pending visual verification (next session — multi-sprint hand-off, growing list):**
- **(today)** CDF panel enrichment 5-feature checklist (per above).
- **(today)** Reset-to-best Current Explorer logL == Global best logL after click. If still mismatched after Round 2 fix, next theories: cadence library precision through save/load round-trip, or `seed_base` actually persisted in user's grid `.npz` (Explorer falls back to 1234 if absent).
- **(rolling forward from 2026-04-30)** Five overnight validation runs (Tabs 1–2 f_bin extremes, Tabs 3–4 bin-at-slope, Tab 5 :8502 σ_single search ON).
- **(rolling forward from 2026-04-30)** Sprint 4 / mock-data overhaul / Explorer parity / logP_max sign-off and commit-block split.

---

## 2026-04-30 (evening) — logP_max fixed-value input + corner staircase diagnosis + single-star RV inspection plot

**Tag:** `v260430-evening-working` *(same caveat as `v260430-partial-working` — Sprint 4 / mock-data overhaul / Explorer parity / logP_max code change all still UNCOMMITTED on `main` awaiting visual sign-off after the five overnight validation runs.)*

| Hash | Summary |
|------|---------|
| `89ae134` | Add single-star RV / σ / ΔRV peak-to-peak inspection plot (`scripts/plot_single_star_rvs.py` + `plots/single_star_rvs.html`) |
| `3657a7d` | End-of-day 2026-04-30 (afternoon): docs, TODO entries 196-197, daily log |

**Major changes (committed):**
- **Afternoon docs (2026-04-30):** TODO.md entries #196 (logP_max scan fixed-value input — coder-agent edit, /error-check PASS, user "nice.") and #197 (single-star RV inspection plot — interactive HTML, σ_weighted = 4.49 ± 0.17 km/s, σ_population_scatter = 2.67 km/s). DOCUMENTATION.md §7 gets a new "(afternoon)" subsection within the existing 2026-04-30 entry covering: closed-form Gaussian propagation of sample-σ uncertainty (`err(s) = √(Σ d_i² σ_i²) / (s (N − 1))`), the f_bin grid 1/N bias as the inherent precision of a 25-star sample (corner-plot staircase artefact accepted as statistically defensible), and the σ_intrinsic vs σ_measured open question for the bias-correction prior. Daily log gained 4 conversation entries at 16:31–16:32.
- **Single-star RV inspection plot (`scripts/plot_single_star_rvs.py`):** loads observed RVs via `pipeline.load_observations.load_observed_delta_rvs`, filters `is_binary is False & N≥2`, sorts by σ ascending, plots per-epoch RV scatter with error bars + ⟨RV⟩ tick + σ-diamonds blended onto the *left* RV axis (same units), with ΔRV peak-to-peak triangles on the *right* axis. Output: `plots/single_star_rvs.html` (interactive).

**Uncommitted on `main` (still awaiting visual sign-off — same as `v260430-partial-working` plus logP_max code change):**
- **logP_max scan fixed-value input (TODO #196).** `app/bc/params.py` (`_render_logPmax_scan` now seeds + renders the fixed-value `st.number_input` + caption + new return when scan OFF) and `app/bc/cadence.py` (added `import dataclasses`; two `dataclasses.replace(_bin_cfg, logP_max=float(_*_logPmax_vals[0]))` calls — one per tab — to override `_bin_cfg.logP_max` after the scan expander returns). Did NOT touch `runners_cadence.py` (still `# WORKING`). /error-check PASS in all 5 phases.
- All previously listed sprints (Sprint 4, mock-data overhaul, Explorer parity, three-stage memo, skill / agent reorg) still UNCOMMITTED on `main` — see the `v260430-partial-working` entry below for full file list.

**Pending visual verification:**
- Same five overnight validation runs as before (Tabs 1–2 f_bin extremes, Tabs 3–4 bin-at-slope, Tab 5 :8502 σ_single search ON). Check 2026-05-01.
- After sign-off, the logP_max fix can either roll into the Sprint 4 commit-block or be its own small commit before the larger sprint commits.

---

## 2026-04-30 — Docs end-of-day; three sprints (validation Sprint 4, mock-data overhaul, Explorer parity) UNCOMMITTED awaiting overnight-runs sign-off

**Tag:** `v260430-partial-working` *("partial" because the validation-tab Sprint 4, the mock-data overhaul, and the Explorer↔grid parity sprint are all held back in the working tree pending the five overnight validation runs that landed evening 2026-04-30 — check 2026-05-01.)*

| Hash | Summary |
|------|---------|
| `4c868eb` | End-of-day 2026-04-30: docs, TODO entries 191-195, learnings, daily logs |
| `4f779b4` | A&A / Shenar-style polish (7 fixes) — 2026-04-29 paper session |
| `e8d2e44` | Fix 8 LaTeX bugs causing 'small text glued together' rendering — 2026-04-29 |
| `191ed50` | Populate star_sample table with BAT99 IDs + WC/WO subtypes — 2026-04-29 |
| `7ce5437` | Fix star_sample table: H2013 LMCe 584 = L72 LH 41-1042 substitution + actual epoch counts — 2026-04-29 |
| `982cf91` | Render 3 deferred figures + populate star_sample table from ESO proposal — 2026-04-29 |

**Major changes (committed):**
- **Docs end-of-day (2026-04-30):** TODO.md entries #191–#195 cover the validation-tab Sprint 4 phases (#191), mock-data overhaul (#192), paper writing session (#193 — already committed), three-stage binarity strategy memo (#194), and Likelihood Model Explorer ↔ grid score parity (#195). DOCUMENTATION.md §7 gets three new entries (2026-04-28, 2026-04-29, 2026-04-30) covering all sprints. COMMON_ERRORS.md gains E051 (runner-mode tag passed as `period_model` value — three callers of `_render_lk_cdf_sanity_check` passed `'dsilva'` where `sample_logP` expects `'powerlaw'`; translate at the data-source boundary). `.claude/references/learnings.md` gains four Plot Rendering rules (never blindly drop a leading axis, two-namespace string bugs, don't trust an agent's "all sites updated" claim, step line + step band must match) plus four Paper / LaTeX rules (math-mode contamination cluster, `\tablefoot{}` `\par` separators, `\input{tables/X}` silently optional, two-stage figure rendering coordination). Daily conversation logs added for 2026-04-28, 2026-04-29, 2026-04-30.
- **Paper writing session (2026-04-29 — already committed in 5 separate commits + 7 Overleaf pushes; latest Overleaf master `0a5a359`):** 13 figure environments inserted across 5 section files; 11 PDFs rendered to `plots/` from real data via the new 1664-line `pipeline/export_paper_figs.py` driver; `paper/tables/star_sample.tex` populated with 25 stars × (Name, BAT99, RA, Dec, Group, Subtype, N_epochs, Source) + 4 footnotes; H2013 LMCe 584 ≡ L72 LH 41-1042 substitution resolved; 8 LaTeX bugs fixed (math-mode contamination in unit macros, `\fbincorr^{...}_{...}` atom-binding malformations, `\tablefoot{}` without `\par` separators, silent missing `\input{tables/star_sample}`); 7 Shenar-style fixes (deleted dead `abstract.tex`, populated Conclusions narrative paragraphs, `\tablefoot{}` on `tab:emission_lines`, populated appendix placeholder, `\esoProgrammes` macro). Methods grew from ~150 to ~310 lines.

**Uncommitted on `main` (Sprint 4 + mock-data overhaul + Explorer parity, awaiting visual sign-off after overnight validation runs):**
- **Sprint 4 — validation-tab consistency overhaul (TODO #191).** 16 modified files in `app/bc/`: `analysis.py`, `cadence.py`, `corner_plots.py`, `extras.py`, `file_ops.py`, `helpers.py`, `likelihood_viz.py`, `render_lk.py`, `render_lk_explorer.py`, `render_lk_explorer_langer.py`, `render_lk_fit.py`, `render_lk_fit_langer.py`, `render_shared.py`, `render_shared_langer.py`, `render_validation.py`, `runners_cadence.py`, `validation.py`, `validation_io.py` (new); `app/shared.py` (`make_heatmap_fig` A&A pass + colorbar font + `gold→#DAA520`).
- **Mock-data overhaul (TODO #192).** `app/bc/validation.py` (function signatures + deterministic binary count); `app/bc/render_validation.py` (two error-model selectors, error bars, 2-criteria curves, removed all realised f_bin references, persistence wiring).
- **Likelihood Model Explorer ↔ grid score parity (TODO #195).** `wr_bias_simulation.py` (deterministic n_bin in `simulate_delta_rv_sample:715` and `simulate_delta_rv_cadence_aware:930`); `app/bc/render_lk_explorer.py` (cached wrapper `_explorer_run_grid_pipeline_cached`, n_sets `number_input`, CDF extension to `(pooled_max, 1.0)`, removed hardcoded x-range); `app/bc/render_lk_explorer_langer.py` (Langer twin).
- **Three-stage binarity strategy (TODO #194).** Memory-only artifact: `memory/project_three_stage_binarity_strategy.md` and `memory/pending_validation_runs_2026_04_30.md`; both indexed in `MEMORY.md` Live State.
- **Skill / agent system reorg.** `.claude/agents/*-skills/` deleted (14+ skill subdirectories); `.claude/skills/{coder,designer,meta-tools,plots,qa,scientist,writer}/` untracked. The reorg moves from per-agent skill dirs to a single shared dir. Held back as a separate logical unit pending an explicit user decision on the migration path.
- **Background data.** `mock_results/`, `bin_sensitivity_results/`, several `results/cadence_*.npz` files from overnight runs, and `scripts/.agent_work/` are untracked but are run outputs, not source — not committed.

**Pending visual verification (user — multi-sprint hand-off):**
- Five overnight validation runs queued evening 2026-04-30: Tabs 1–2 (low/high f_bin extremes with σ_single pinned), Tabs 3–4 (sensitivity to an extra histogram bin near the steep CDF slope), Tab 5 on `:8502` (σ_single included as a free search dimension). Check 2026-05-01. The Tab 5 result decides whether σ_single can live in Stage 1 or must be deferred to Stage 3.
- Once results are reviewed, three commit-blocks expected: (1) Sprint 4 validation-tab consistency overhaul + mock-data overhaul as one or two commits; (2) Explorer ↔ grid parity (`wr_bias_simulation.py` deterministic-n_bin + Explorer cached wrapper) as one commit; (3) skill / agent system reorg as a separate, explicitly-discussed commit.
- Tag at that point: `v260501-working` (or whichever date the sign-off lands).

---

## 2026-04-23 — Three sprints landed; validation tab held back (six symptoms remain)

**Tag:** `v260423-partial-working` *("partial" because Sprint 4 — validation-tab consistency overhaul — is held back in the working tree pending fixes for six remaining symptoms.)*

| Hash | Summary |
|------|---------|
| `4699bc4` | End-of-day 2026-04-23: docs, error catalog (E049-E050), TODO entries 187-190 |
| `c7534ef` | Add standalone RV modeling webapp + today's parametric error-model port |
| `a57c56d` | Fix To-Do webapp render bugs: green code-spans + table pipe corruption |
| `cc6f753` | Add Bin Sensitivity sub-tab to bias correction page |

**Major changes (committed):**
- **Docs:** TODO #187 moved to `to-test` with detailed sign-off notes; new entries #188 (RV modeling), #189 (To-Do app), #190 (Bin Sensitivity). DOCUMENTATION.md §7 entry covering all four sprints. COMMON_ERRORS.md gets E049 (Plotly subplot scoped axis update inconsistency) and E050 (silent deadlock when `@st.cache_data` is invoked from a `threading.Thread`). learnings.md gets three new User Interaction rules; plot_preferences.md gets readable-text size minimums; plots agent CRITICAL RULES rewritten (A&A always; never auto-zoom; always high-contrast).
- **Sprint 1 — RV modeling app:** new standalone Streamlit app at `rv_modeling_app/` (4025 lines: `app.py`, `page.py`, three tabs Simulate/Fitting/Playground, `compute.py`, `helpers.py`, `tabs.py`, `shared_lite.py`). Today's diff: orbital-parameter histogram fix in tab_simulation (n_sets_hist now matches main n_sim); Parametric mode best-fit Parameter Summary; six-kwarg measurement-error model port to `compute_model_fraction_curve` with per-class intrinsic + per-epoch noise via `_draw_measurement_noise`, full 2-test detection. Caveat: σ_pair=√2·σ_measure exact for `fixed`/`normal` only (TODO #188).
- **Sprint 2 — To-Do app:** `app/todo_core.py` HTML-escapes + backtick-strips descriptions (no more bright green code-spans), pipe-aware regex parser `re.compile(r'(?<!\\)\|')` + `_escape_cell` writer (no more column-shift on descriptions containing `|`).
- **Sprint 3 — Bin Sensitivity sub-tab:** five new files in `app/bc/` (~4750 lines total): `bin_schemes.py` (8 scheme builders), `bin_sensitivity_scorer.py` (SchemeResult dataclass + MP-pool re-simulation + P1-P6 pitfall detector + E050-bypass on bg-thread path), `bin_sensitivity_plots.py` (6 A&A-ready plot builders + readable-text bumps + `_apply_aa_axes()` for E049), `bin_sensitivity_storage.py` (autosave + promote_partial + list_bs_partials), `bin_sensitivity.py` (tab renderer with manual scheme rows + mock-data mode + saved-runs panel rendered unconditionally at top of tab + bulletproof unconditional schemes-persist). Surgical edits: `app/bc/__init__.py` (register tab), `app/bc/helpers.py` (`_BIN_SCHEME_COLORS` + `get_scheme_color`), `app/pages/05_bias_correction.py` (tab type registration), `settings/user_settings.json` (persisted schemes + mock_params under `bin_sensitivity.*`). New memory file: `memory/likelihood_bin_sensitivity.md` (8-paper lit review + 12 scheme builders + P1-P6 + AIC vs logL_max derivation).

**Uncommitted on `main` (Sprint 4 — validation-tab overhaul, TODO #187):**
- 15 modified files in `app/bc/`: `validation.py`, `render_validation.py`, `render_lk_explorer.py`, `render_lk_explorer_langer.py`, `runners_cadence.py`, `cadence.py`, `corner_plots.py`, `analysis.py`, `render_shared.py`, `render_shared_langer.py`, `sim_plots.py`, `helpers.py` (Sprint 4 portion only — `_obs_label` + sanity-check delegator; Sprint 3 portion already committed), `file_ops.py`, `extras.py`, `likelihood_viz.py`, `render_lk_fit.py`, `render_lk_fit_langer.py`.
- 1 new file in `app/bc/`: `validation_io.py` (mock_results/ persistence layer).
- 3 new test files in `scripts/`: `test_explorer_mock_equal.py`, `test_explorer_mock_equal_langer.py`, `test_grid_vs_explorer_score.py`.
- 1 new directory: `mock_results/` (validation run outputs).

**Pending visual verification (user — Sprint 4 hand-off):** Six symptoms reported after end-of-day testing of TODO #187 stages A–D. (1) Need ΔRV error bars on mock CDF + binary-fraction graphs. (1a) About half the validation plots are still not A&A white-bg — sweep again with two parallel agents. (1b) Best f_bin matches heatmap argmax but the 68% HDI value does NOT match the maximum of the marginalised f_bin (or the interpolated one); same for π; logP_max still NaN despite Stage B fix attempt. (1c) Symptom 2 from original TODO #187 still broken — flat CDF at 0.12. (1d) Blocked by 1c. (1e) The 5 Draws CDFs in the Sanity Check feel "way off" relative to the best-fit CDF — likely calculated by a different code path. Sprint 4 must be re-attempted with these explicit symptoms in a new chat. Hand-off summary written separately; see TODO #187 notes.

---

## 2026-04-20 — Docs-only end-of-day (two code sprints UNCOMMITTED pending 2026-04-22 sign-off)

**Tag:** *(none — code sprints awaiting visual sign-off; no working-version tag today.)*

| Hash | Summary |
|------|---------|
| `6a13688` | End-of-day 2026-04-20: docs + daily log (code sprints uncommitted, awaiting 2026-04-22 sign-off) |

**Major changes (committed — docs only):**
- **TODO.md:** entries #184 (binning-robustness literature research), #185 (validation-tab overhaul + A&A diagnostics), #186 (Bin-Sensitivity sub-tab — 4 new `app/bc/` files + 6 A&A plots + mock-data validation mode). All three flagged `UNCOMMITTED — awaiting user visual sign-off ~2026-04-22`.
- **DOCUMENTATION.md §7:** new 2026-04-20 work-log entry covering four sub-sessions — binning-robustness lit review (Dsilva 2022 Sect. 5.2 precedent, Sturges/Rice/Scott rules all giving ~5 bins for N=25, 5-step robustness protocol with AD cross-check), marginalization audit (flat-prior posterior ∝ likelihood ⇒ nansum over nuisance axes + trapezoid normalization verified correct for both Dsilva and Langer tabs), validation-tab overhaul (mock-preview + truth-vs-recovered table + f_bin(t) overlay + CDF overlay with bootstrap HDI band, plus `_AA_OVERRIDES` white-bg recipe), and the Bin-Sensitivity sub-tab (4-round scientist→plots→designer→coder→QA coordination, 8 scheme builders + SchemeResult scorer + 6 A&A-ready plots + mock-data validation mode with Δf_bin/Δπ columns). Includes paper-relevant methodology notes on bin-count defence, validation-diagnostic choice, posterior convention, and Anderson–Darling cross-check plan.
- **daily_logs/2026-04-20.md:** full conversation log from all four sessions.

**Uncommitted on `main` (awaiting 2026-04-22 visual sign-off):**
- **Validation-tab overhaul:** `app/bc/validation.py` (`generate_mock_observations_detail`), `app/bc/render_validation.py` (grew ~330→1281 lines: pre-run mock preview, post-run truth-vs-recovered diagnostics, `_AA_OVERRIDES` white-bg styling), `app/bc/cadence.py` (added `n_sets_override` kwarg to both cadence tab renderers).
- **Bin-Sensitivity sub-tab:** four new files `app/bc/bin_schemes.py`, `app/bc/bin_sensitivity_scorer.py`, `app/bc/bin_sensitivity_plots.py`, `app/bc/bin_sensitivity.py` (total ~2500 lines); surgical edits to `app/bc/__init__.py`, `app/bc/helpers.py`, `app/pages/05_bias_correction.py`. Companion memory/config updates: `memory/plot_preferences.md` (plot #6 STRONGLY APPROVED), `memory/likelihood_bin_sensitivity.md` (new 8-paper lit review + scheme formulas + pitfall catalogue).
- **Agent system updates tied to today's work:** `.claude/agents/plots.md` (new `_AA_OVERRIDES` recipe + mandatory exit checklist), `.claude/agents/comms/*` (4-round comms trail from today's sprints), `.claude/references/learnings.md` (new top-of-Plot-Rendering entry on PLOTLY_THEME-is-dark trap).

**Pending visual verification (user):** Guy runs the visual sweep on 2026-04-22 per `memory/pending_test_validation_diagnostics.md` and `memory/current_focus.md`. On PASS, sprint-commits follow: (1) validation-tab overhaul as one commit, (2) Bin-Sensitivity sub-tab + memory/plot_preferences + likelihood_bin_sensitivity + agent comms + learnings as one commit. Tag `v260422-working` created after sign-off.

---

## 2026-04-19 — Bias-correction reliability sprint (E045–E048), 7-agent comms activation

**Tag:** `v260419-working`

| Hash | Summary |
|------|---------|
| `8018e6b` | Bias-correction reliability sprint: Langer slider, resume-fingerprint, CDF helpers, Explorer-grid logL parity |
| `ddcc108` | Activate 7-agent team comms protocol; rewrite designer + qa for UI loop |
| `0d8f931` | End-of-day 2026-04-19: docs, error catalog (E045-E048), TODO entries 178-183 |
| `b771413` | Add 2026-04-19 daily conversation log + Dsilva 2022 northern WNE reference paper |

**Major changes:**
- **E045 — Langer slider crash:** `_make_range_slider` now displays a static label when `min == max` (Langer fixes σ_single = 7.5).
- **E046 — Cancel-resume sim-context fingerprint guard:** `_save_partial_cadence` now persists `sim_context` + `sim_context_hash` (additive npz keys); on resume `cadence.py` validates against the live signature and refuses with a field-level diff if `bin_cfg` / `sigma_meas` / `cadence_library` / `obs_delta_rv` / adaptive bin edges drifted (root cause of post-resume horizontal-row kink in `f_bin × σ_single` heatmap). Also fixed Streamlit `st.button`-in-conditional-block click-drop by re-arming session_state.
- **E047 — Plot rendering:** Top "CDF Comparison" now routed through `_me_cdf_band` / `_me_cdf_band_langer` (was non-cadence-aware); replaced `fill='toself'` polygon with two `shape='hv'` traces using `fill='tonexty'` so the median dashed line stays inside the 16–84 band.
- **E048 — Re-sim helper physics-config drift:** `_me_cdf_band` was discarding `bin_cfg` and silently defaulting `period_model='powerlaw'`, producing flat CDF + logL mismatches with the grid. Result dict now persists `bin_cfg`, `period_model`, `cadence_weights`, `cadence_library`, `sigma_meas`; helper threads the full config; Langer twin gained the missing cadence-aware branch; new regression test `scripts/test_explorer_logL_consistency.py`.
- **7-agent system activated:** new `comms-protocol.md` + `agent-delegation.md` references; designer rewritten with UI Loop role + Acceptance Criteria; qa rewritten with PASS / FAIL / BLOCKED verdict; `CLAUDE.md` gained 3-line `## Agents` section.
- **Corner-plot marginalization audit:** verdict — implementation matches Dsilva 2022 §5.2 under flat priors; no code changes.
- **TODO.md:** entries 178–183 logged; **DOCUMENTATION.md §7** new 2026-04-19 entry; **COMMON_ERRORS.md** E045–E048 added; daily conversation log + Dsilva 2022 northern WNE reference paper added.

**Pending visual verification (user):** rerun a bias-correction grid (any size) so the new result-dict fields land in a fresh `.npz`, then verify (1) top CDF tracks observed across the full ΔRV range; (2) Explorer "Global best logL" matches stored heatmap logL within ~0.3 at `n_sets ≥ 1000`; (3) caption no longer shows `logP_max=nan`; (4) same on Langer tab.

---

## 2026-04-14 — AIC/BIC Compare tab + intrinsic-RV review + A&A plots audit

**Tag:** `v260414-working`

| Hash | Summary |
|------|---------|
| `4bf0450` | Add AIC/BIC model selection to Compare tab |
| `e822912` | Strengthen plots agent: WCAG contrast + A&A standards + review protocol |
| `f1411c4` | End-of-day 2026-04-14: intrinsic-RV review, AIC/BIC, standalone apps, A&A audit |

**Major changes:**
- Compare tab reports raw `logL`, dynamic `k`, `AIC/ΔAIC`, `BIC/ΔBIC` alongside the normalized likelihood; `k` derived from grid-axis sizes > 1, N=25.
- DOCUMENTATION §4b added: intrinsic single-star RV variability (~40 citations), period-range justification; six new rows in §5 Key Numbers; references expanded 5→22.
- Plots agent `.claude/agents/plots.md` gains HARD RULE #1 (WCAG contrast), A&A Journal Standards, 6-step review protocol.
- TODO.md: #174–#177 logged (literature review, AIC/BIC, standalone apps, A&A plots audit).
- Background: standalone `spectrum_app/` extracted (already on d53d92d); `rv_modeling_app/` still uncommitted pending validation.

---

## 2026-04-13 — Exclusion-aware gap_sim + role-based agent team

**Tag:** `v260413-working`

| Hash | Summary |
|------|---------|
| `ba31e15` | Fix exclusion-aware gap_sim for Binary Orbital Properties histograms |
| `c251859` | Document 2026-04-13: gap_sim exclusion fix + agent team creation |
| `7a9621f` | Add role-based agent team and reorganise skills into per-agent dirs |

**Major changes:**
- `gap_sim` (10k-star simulation feeding orbital-property histograms) now respects grid exclusion: `_find_best_model()` helper in `cadence.py`, exclusion mask applied before best-fit / gap_sim in both Dsilva and Langer cadence renderers; `subtabs._render_analysis_plots` prefers `ctx['best_model']`.
- 7-agent role-based team (coder/qa/designer/plots/scientist/writer/meta-tools) under `.claude/agents/` with file-based comms. 13 existing skills moved into per-agent `-skills/` dirs; 6 new skills added (paper-research, python-production, live-testing, testable-code, academic-writing, latex-helper). Orchestrator visible skills: 19→6.

---

## 2026-04-09 — Grid exclusion overhaul, CDF/Explorer consistency, Binary Fraction upgrade

**Tag:** `v260409-working`

| Hash | Summary |
|------|---------|
| `f0211c8` | Rewrite grid exclusion with range sliders for all axes (fbin, pi, sigma, logPmax) |
| `73976ef` | Fix logP_max override + apply exclusion mask to heatmaps |
| `bb6c7a2` | Fix gold star: argmax → nanargmax + guard all-NaN in find_best_grid_point |
| `a705e0a` | Fix CDF comparison: use actual BinaryParameterConfig, n_sets, and extra_grids |
| `5d38fcb` | Switch Model Explorer to cadence-aware simulation for comparable logL scores |
| `9bc0eb4` | Upgrade Detection Fraction to full Binary Fraction chart + add WORKING flags |
| `5779bdd` | End-of-day documentation: grid exclusion overhaul, CDF/Explorer fixes |

**Major changes:**
- Grid exclusion: range sliders for all axes, N-D masks, excluded regions blank on heatmaps
- CDF comparison uses actual BinaryParameterConfig (was using defaults with wrong logP_max)
- Per-bin table uses actual n_sets (was hardcoded 100)
- Model Explorer uses cadence-aware simulation (logL scores now match grid)
- Detection Fraction upgraded to full Binary Fraction vs Threshold with best-fit overlay
- Gold star fix (nanargmax), extra_grids fix (only >1 value axes), sigma_meas None fix

---

## 2026-04-06 — Companion detection, raw spectrum fix, RV Modeling persistence

| Hash | Summary |
|------|---------|
| `bdd35cd` | Add telluric/ISM diagnostic lines, companion detection guide, and heatmap wavelength sort |
| `16396ca` | Add binary classification banner and companion guide to Spectrum page |
| `fff25ab` | Fix ERR column check in plots/data.py + update tab_spectra rendering |
| `e771669` | Add settings persistence to RV Modeling page + convert sliders to number_input |
| `a8ba268` | End-of-day documentation: RV Modeling persistence, companion detection tools |

Three sessions: (1) Raw spectrum FITS loading bug fix (E044) + overlay/stitched views.
(2) Spectrum companion detection guide with telluric/ISM line groups, absorption line
reference, and binary classification banner. (3) Full settings persistence for RV
Modeling page (6 tabs, ~100+ widgets) mirroring Bias Correction pattern. Converted
all sliders to unrestricted number_input. Tagged: `v260406-working`.

---

## 2026-03-31 — σ_p2p significance criterion, spectrum page overhaul, explorer bugfixes, likelihood binning

| Hash | Summary |
|------|---------|
| `a46e7f4` | End-of-day documentation: binning methodology, TODO audit, daily log |
| `40fd943` | Fix IndexError in likelihood explanation (bins>4) + add L bins column to file browser |
| `c7d5635` | Update GIT_LOG.md with 2026-03-31 commits and working tag |
| `d36cdac` | Paper: add σ_p2p significance criterion and Bartzakos correction to bias correction section |
| `cd4b5e8` | End-of-day documentation: work log, TODO audit, E043 error entry |
| `a6aa20b` | Add significance criterion to binary fraction graphs + spectrum page zoom nav |
| `ee38837` | Restructure spectrum page into 3 tabs with persistent state |
| `04124f8` | Add sigma_p2p significance criterion to bias correction pipeline |
| `9e03996` | Spectrum page: absorption search, LMC correction, show-all-epochs, graph descriptions |
| `4e4b227` | Checkpoint: WIP changes before adding sigma_p2p significance criterion |
| `1d9b11f` | Update settings and command history log |

Tag: `v260331-working` — σ_p2p significance, spectrum overhaul, Dsilva explorer bugfixes, Bartzakos correction, likelihood binning methodology, L bins column.

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
