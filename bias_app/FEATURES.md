# Bias App — Complete Feature Checklist

Master inventory of ALL features from the Streamlit bias correction webapp (`app/bc/`).
Built by analyzing every plot, table, toggle, and callback in the Streamlit code.
`[x]` = implemented in Dash, `[~]` = partial, `[ ]` = not yet.

---

# PART 1: PAGE-LEVEL CONTROLS

- [x] Page title & subtitle
- [ ] Canvas size expander (height px: 200–2000, width px: 0=auto to 3000)
- [ ] Dynamic tab management ("+" button to add tabs, popover with type selector + name input)
- [ ] Remove Last Tab button
- [ ] Toast notifications (on result load, cancel, save)
- [ ] Markdown captions below every chart (st.caption equivalent)

Source: `app/pages/05_bias_correction.py:1-126`

---

# PART 2: PER-MODEL TAB CONFIGURATION (×4 tabs)

## Grid Parameters
- [x] f_bin min/max/steps (3-column layout)
- [x] π min/max/steps (Dsilva/Cadence-D)
- [x] σ min/max/steps (Langer/Cadence-L, as grid axis)
- [x] N stars per grid point

## Sigma Scan
- [x] σ_single scan toggle (on/off)
- [x] σ min/max/steps (when scan on)
- [x] Single σ_single value (when scan off)

## logP_max Scan
- [x] logP_max scan toggle
- [x] logP_max min/max/steps (when scan on)

## Orbital Parameters
- [x] logP_min / logP_max
- [x] Eccentricity model (flat/zero) + e_max
- [x] Primary mass model (fixed/uniform) + M₁ value/range
- [x] Mass ratio q model (flat/langer) + q min/max + μ_q/σ_q

## Langer-Specific
- [x] Case A/B period distribution: μ₁/σ₁, μ₂/σ₂, weight_A
- [x] Case A/B/Both preset buttons
- [ ] Distribution type selectors per component (Gaussian/Log-normal/Reflected/Empirical/Flat)
- [ ] q flip toggle (M₁/M₂ vs M₂/M₁)
- [x] q distribution preset selector

Source: `app/bc/params.py:1-594`, `app/bc/dsilva.py`, `app/bc/langer.py`

## Error Model
- [ ] Error model selector (per single/binary): fixed, normal, lognormal, gamma, Weibull, uniform
- [ ] Error model parameters (conditional on type: μ, σ, shape, scale, min, max)
- [ ] Per-epoch error model option (from Task #140)

Source: `app/bc/extras.py`

---

# PART 3: RUN CONTROLS & RESULT MANAGEMENT

## Run Controls
- [x] Workers (N processes)
- [x] Run button (background callback)
- [x] Cancel button
- [ ] Cancel & Save button (partial checkpoint on cancel)
- [x] Progress bar (animated during run)
- [x] Progress text (status messages)
- [ ] View mode radio (K-S p-value / K-S D-statistic)
- [ ] N sets input for CvM/Likelihood (100–50000, step 100)
- [ ] Likelihood bin config expander (threshold-based / manual edges)

## Result Management
- [x] Load saved result (clickable parameter table with single-row selection)
- [x] Refresh results list button
- [x] Save result to disk on completion (.npz)
- [ ] Delete result button (🗑️ on selected row)
- [ ] Save result button (manual)
- [ ] Partial results table (show cached f_bin rows, last checkpoint info)
- [ ] Resume from partial checkpoint
- [ ] Descriptive filenames (encode all params + timestamp)
- [ ] Run history tracking

Source: `app/bc/file_ops.py:1-589`, `app/bc/dsilva.py`, `app/bc/langer.py`

---

# PART 4: LIVE POLLING (during simulation)

All live plots update every 3s via polling fragment. Streamlit uses
`@st.fragment(run_every=3)` + `st.session_state['{p}_job']` dict.

- [~] Progress bar (exists, but no live heatmap updates)
- [ ] Live heatmaps — 2×2 grid updated as rows complete:
  - [ ] Live K-S p-value heatmap
  - [ ] Live K-S D-statistic heatmap
  - [ ] Live CvM S-score heatmap
  - [ ] Live Likelihood heatmap
- [ ] Live σ_single 1D profile (max p-value vs σ, updated per slice)
- [ ] Live logP_max 1D profile (max p-value vs logPmax, updated per slice)
- [ ] Final σ_single 1D profile (persisted after run completes)
- [ ] Live status text (markdown: "Computing f_bin=0.45 (34/137)...")
- [ ] Cancel mode handling ('discard' vs 'save' partial)

Source: `app/bc/polling.py:1-199`, `app/bc/runners_dsilva.py`, `app/bc/runners_cadence.py`

---

# PART 5: SIMULATION OVERVIEW TAB

Appears after a result is loaded or run completes. Shows cross-method comparison.

## Method Summary Table
- [~] Summary table (basic — missing HDI bounds and agreement column)
- [ ] 68% HDI bounds for f_bin (per method)
- [ ] 68% HDI bounds for π/σ (per method)
- [ ] 68% HDI bounds for σ_single (if scanned, per method)
- [ ] Agreement column ("Yes"/"No" — does each method's best f_bin fall within ALL other methods' 68% HDI?)
- [ ] Best σ_single column (if scanned)

Source: `app/bc/analysis.py` — `_render_method_summary_section()`

## CDF Comparison
- [x] All-methods CDF comparison (observed black + per-method dashed, 16-84% bands)

Source: `app/bc/analysis.py` — `_render_all_methods_cdf()`

## Sigma Scan Charts
- [x] Max p-value vs σ_single line chart (gold star at best)
- [ ] Max score vs σ_single line chart (per scoring method, not just K-S)

Source: `app/bc/subtabs.py` — `_render_sigma_scan_chart()`

## Period Distribution
- [x] Period distribution histogram (detected red / missed amber, 35 bins)
- [ ] Case A/B view toggle (3 options: "Detected/Missed", "Case A/B", "All") — Langer only
- [ ] Density vs fraction normalization toggle
- [ ] logP_min / logP_max dashed annotation lines

Source: `app/bc/sim_plots.py` — `render_period_distribution()`

## Binary Fraction vs Threshold
- [x] f_bin vs ΔRV threshold curve (fill areas + diamond marker + gap arrow annotation)

Source: `app/bc/sim_plots.py` — `render_binary_fraction_vs_threshold()`

## Orbital Histograms
- [x] 9-panel grid (logP, e, q, K₁, M₁, M₂, i, ω, T₀)
- [ ] Population view radio: "Detected vs Missed" / "Detected only" / "Missed only" / "All combined" / "Case A vs B"

Source: `app/bc/sim_plots.py` — `render_orbital_histograms()`

## Methodology
- [ ] Methodology equations expander (LaTeX: Kepler equation, RV curve, K₁, K-S test, binary criteria)
- [ ] Model-specific variants (Dsilva power-law, Langer Case A/B, Cadence modifications)

Source: `app/bc/sim_plots.py` — `render_methodology_equations()`, `app/bc/helpers.py`

---

# PART 6: PER-SCORING-METHOD TABS (×4 methods)

Each of the 4 scoring methods (K-S, K-S Weighted, CvM, Likelihood) gets a tab
with the following components. Some are universal, some are method-specific.

## Slice Selectors (for 3D+ results)
- [x] σ_single slider (select sigma slice when multiple sigmas scanned)
- [x] logP_max slider (select logPmax slice when scanned)

## 2D Heatmaps
- [x] Primary p-value/score heatmap (fbin × π/σ, Viridis, gold star)
- [x] D-statistic heatmap (K-S D, Weighted D, CvM S-raw, Likelihood -logL)
- [ ] Extra 2D heatmaps for 3D+ models (side-by-side):
  - [ ] f_bin vs logP_max (max over sigma)
  - [ ] σ vs logP_max (max over f_bin)

Source: `app/bc/analysis.py:656-689`

## Best-Fit Metrics
- [~] Best-fit display (basic — missing HDI, slice vs global)
- [ ] 2D mode: single card with f_bin, π/σ, p-value
- [ ] Multi-D mode: two cards — "Current slice best" + "Global best" (across ALL dimensions)
- [ ] 68% HDI bounds on each parameter

Source: `app/bc/analysis.py:691-715`

## Score Profiles (per method)
- [ ] Score vs σ_single line chart (max p-value or min S-score vs σ, gold star at best)
- [ ] Score vs logP_max line chart (max score vs logPmax, gold star at best)

Source: `app/bc/analysis.py:770-859`

## Corner Plots
- [x] K-S corner plot (N×N: 1D posteriors + 2D heatmaps, 68%/95% contours, HDI shading)
- [x] Weighted corner plot
- [x] CvM corner plot
- [x] Likelihood corner plot
- [ ] Axes auto-adapt to scanned dimensions (f_bin, π/σ, σ_single, logPmax)

Source: `app/bc/corner_plots.py:1-254`

## Per-Method Summary Table
- [ ] Per-method best-fit summary: grid best, mode ± HDI68, interpolated (for each scanned axis)

Source: `app/bc/analysis.py:869-930`

## CDF at Best-Fit
- [x] CDF comparison at best-fit point (observed vs simulated with 16-84% bands)

## Model Explorer
- [x] Top-N grid points table

## 1D Marginal Slices
- [x] K-S fbin 1D slice (grid points + parabolic fit + gold star)
- [x] K-S π 1D slice
- [ ] K-S σ 1D slice (if sigma scanned)
- [x] Weighted fbin 1D slice
- [x] Weighted π 1D slice
- [ ] Weighted σ 1D slice
- [x] CvM fbin 1D slice
- [x] CvM π 1D slice
- [ ] CvM σ 1D slice
- [x] Likelihood fbin 1D slice
- [ ] Likelihood π/σ 1D slice (verify — may already exist)
- [ ] Likelihood σ 1D slice

---

# PART 7: SCORING DETAIL ANALYSIS (CvM & Likelihood specific)

From `app/bc/scoring_detail.py:1-650`. This is a major section with its own
UI controls and multiple plots. Applies to CvM and Likelihood methods.

## Controls
- [ ] Log scale toggle checkbox ("Log₁₀(S) scale" / "Log₁₀(−log L) scale")
- [ ] Grid range exclusion expander (sliders or multiselect per axis to mask boundary regions)

## Heatmap Variants (per method)
- [ ] Raw statistic heatmap (all grid points, white = excluded by range)
- [ ] Score-masked heatmap (white = implausible: K-S p<0.05 or p>0.95, Likelihood L<5% of max)
- [ ] Score heatmap (standard, with gold star — may overlap with Part 6 primary heatmap)

## Parabolic Fitting
- [ ] Fit mode selector: Height-based / Range-based / Neighborhood radio
- [ ] 3D parabolic surface plot (go.Surface with camera presets)
- [ ] 1D fit slices along each axis (data points + fit curve + interpolated best-fit marker)
- [ ] Fit quality metrics (R², residuals)

Source: `app/bc/fitting.py:1-262`

## Likelihood-Specific Plots
- [ ] Likelihood CDF with bin edges overlay (100 draws + 16-84% band)
- [ ] Checkbox: "Show likelihood bins on CDF" (vertical shaded regions at bin edges)
- [ ] Per-bin breakdown table (n_obs, n_sim, p_i, ln(p_i), contribution per bin)
- [ ] Likelihood explanation expander (LaTeX equations + worked example)

Source: `app/bc/likelihood_viz.py:1-328`

## Re-simulation
- [ ] Re-simulate at interpolated best-fit point (button)
- [ ] Re-simulation CDF plot (observed vs new draw at interpolated params)

---

# PART 8: COMPARE TAB

Side-by-side comparison of multiple saved results.

- [x] Side-by-side heatmaps (selectable method)
- [x] CDF overlay (observed)
- [ ] Model selector (multiselect: choose 2+ saved results)
- [ ] Result metadata table (parameter comparison: model, date, f_bin, π, σ, logP_max)
- [ ] Best-fit comparison table (K-S p, CvM p, Likelihood per result)
- [ ] Difference heatmap (Δp-value between two selected models)
- [ ] Method-specific CDF comparison (overlay CDFs from different results)

---

# PART 9: RV ERRORS TAB

From `app/bc/extras.py:1-1237`. Error distribution analysis and validation.

- [x] Distribution selector (single/binary: fixed, normal, lognormal, gamma, Weibull, uniform)
- [x] Live PDF preview plot
- [ ] ΔRV threshold slider (reclassify binary/single interactively)
- [ ] Star filter radio (all / clean / contaminated)
- [ ] Auto-fit button (MLE parameter fitting to observed errors)
- [ ] Record fit button (save manually adjusted params)
- [ ] Histogram + fitted PDF overlay (observed error distribution with fit curve)
- [ ] Statistics display (mean, median, std of errors)
- [ ] Fit history table with AIC/BIC comparison
- [ ] Clear history button
- [ ] Auto-fit ALL distributions (ranked table by AIC/BIC)
- [ ] Q-Q plot (quantile-quantile diagnostic)
- [ ] Best-fit indicator highlighting

---

# PART 10: APP SHELL & INFRASTRUCTURE

## Dash App Shell
- [x] MantineProvider with dark/light toggle (clientside, instant)
- [x] AppShell with navbar + page_container
- [x] Active NavLink highlighting
- [x] Theme persistence (localStorage)
- [x] Auto-open browser on launch
- [x] Auto-find free port
- [x] NotificationProvider registered
- [ ] Notification on job completion (toast/notification when background sim finishes)

## State & Persistence
- [x] Auto-save all params to localStorage
- [x] Restore params on page load
- [x] Named presets (save/load to localStorage + disk JSON)
- [ ] New Instance button (open parallel run in new browser tab)
- [ ] Settings persistence to user_settings.json (only primary tab saves)

## Figures Module
- [x] `components/figures.py` — simulation tab figure factories
- [x] `components/method_figures.py` — per-method figure factories
- [x] `components/detail_figures.py` — D-stat heatmaps, 1D slices, re-sim CDF factories
- [ ] `components/surface_figures.py` — 3D parabolic surface + projection factories (NEW)
- [ ] `components/live_figures.py` — live polling chart builders (NEW, if needed)

## Callbacks Coverage
- [x] `callbacks/simulation_cb.py` — Dsilva background run
- [x] `callbacks/simulation_langer_cb.py` — Langer background run
- [x] `callbacks/simulation_cadence_cb.py` — Cadence background run (both models)
- [x] `callbacks/scoring_cb.py` — per-method heatmap + best-fit
- [x] `callbacks/sim_plots_cb.py` — simulation tab analysis plots
- [x] `callbacks/method_detail_cb.py` — CDF, corner, slice, explorer
- [x] `callbacks/detail_plots_cb.py` — D-stat heatmaps, fbin/x 1D slices (per method)
- [x] `callbacks/persistence_cb.py` — auto-save/restore + presets
- [x] `callbacks/result_browser_cb.py` — load saved results
- [x] `callbacks/ui_callbacks.py` — toggle visibility + Langer presets
- [ ] `callbacks/scoring_detail_cb.py` — CvM/Likelihood detail analysis (NEW)
- [ ] `callbacks/live_polling_cb.py` — live heatmap polling during runs (NEW)

## Helper/Reusable Plot Generators
- [x] General heatmap figure builder (make_heatmap_fig)
- [x] Max p-value line chart builder (make_max_pval_fig)
- [ ] Min score line chart builder (make_min_score_fig — for CvM where lower = better)
- [ ] 3D surface builder (go.Surface with camera controls)
- [ ] CDF sanity check plot

---

## Score Summary

**Implemented:** Count all `[x]` items above.
**Partial:** Count all `[~]` items above.
**Remaining:** Count all `[ ]` items above.

---

## Session Progress
- [x] Session 1: Figure extraction + Simulation tab plots
- [x] Session 2: Langer + Cadence simulation callbacks
- [x] Session 3: Per-method panels (CDF, slices, corner, explorer)
- [x] Session 4: Polish (CDF stub, Langer presets, ID mismatch fix)
- [x] Bug fixes: root 404, cadence-dsilva missing logPmax, hidden input types
- [x] Result saving to disk on completion
