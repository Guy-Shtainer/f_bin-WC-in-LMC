# GRAPHS_PER_METHOD.md — Per-Scoring-Method Graph Catalog

> **Purpose:** Lists every graph/plot that appears for each scoring method in the bias correction page.
> Use as a regression checklist after code changes to verify no visualizations were broken.

---

## Method Status

The simulation engine **computes 4 scoring methods** per grid run: K-S standard, K-S weighted, CvM, Likelihood.
The **radio selector** (`subtabs.py`) currently exposes only **2 methods** for detailed analysis:

| Method | Key | Radio | Live 2×2 | Summary Table | Detailed Tab | Color |
|--------|-----|:-----:|:--------:|:-------------:|:------------:|-------|
| K-S (standard) | `ks` | Yes | Yes | Yes | Yes | #4A90D9 (steel blue) |
| K-S (weighted) | `weighted` | No | Yes | No | No | — |
| CvM | `cvm` | No | Yes | No | No | — |
| Likelihood | `likelihood` | Yes | Yes | Yes | Yes | #DAA520 (gold) |

**Registry:** `SCORING_METHODS` in `helpers.py:51-54` — only K-S and Likelihood entries.

---

## Heatmap Factory Spec (`make_heatmap_fig` in `shared.py`)

All 2D heatmaps share this renderer. Understanding it is key to verifying heatmap behavior.

| Property | Value |
|----------|-------|
| **Trace:** | `go.Heatmap` — colorscale `RdBu_r`, `zsmooth='best'`, zmin=0 |
| **Contours:** | `go.Contour` — black dotted lines, levels 0.05 to 0.30 step 0.05, labels on. **Always drawn from p-values**, even when heatmap shows D-statistics |
| **Best-fit star:** | `go.Scatter` — gold star symbol, size 18, color solid gold, border=plot_bg width 1, text label in #DAA520 size 11 positioned middle-right |
| **`live=True`:** | Contours hidden, star hidden (used during grid computation for speed) |
| **`live=False`:** | Contours shown, star shown (used for final/loaded results) |
| **`show_d=True`:** | Heatmap Z switches to D-statistic array; colorbar title changes; contours still from p-values; best-fit still from p-values |
| **Colorbar:** | Title from `scoring_label` + " p-value" or " D"; thickness 14, len 0.9 |
| **Hover:** | `{x_name}=%{x:.3f}<br>f_bin=%{y:.4f}<br>{colorbar_title}=%{z:.4f}<extra></extra>` |
| **Default height:** | 520px |

---

## A. Comparison — Shared Across All Scoring Methods

These graphs appear **regardless of which scoring method is selected** in the radio selector.
They use data from ALL methods simultaneously (e.g., overlaid CDFs from every method's best-fit)
and provide cross-method comparison. Rendered by `subtabs.py → render_model_subtabs()` in the
Simulation Overview section, before the per-method radio selector.

### A1. Scoring Method Summary Table
- **Type:** st.dataframe (not a plot)
- **Rows:** One per registered method (K-S, Likelihood)
- **Columns:** Method | Best f_bin | 68% HDI f_bin | Best π/σ | 68% HDI π/σ | Best σ (if multi) | Score | Agreement
- **Agreement:** Does this method's best f_bin fall in every other method's 68% HDI?
- **File:** `analysis.py` → `_render_method_summary_section()`
- **Condition:** Always shown if result loaded

### A2. CDF Comparison — All Methods' Best-Fits
- **Type:** Plotly Scatter — step lines (`shape='hv'`) + filled confidence bands
- **X:** ΔRV (km/s) — bin edges
- **Y:** Cumulative fraction (0–1)
- **Observed:** Solid black, width 2.5
- **Per method:** Dashed line in method color (median of 100 re-simulations, seeds 42–141, N_stars = observed count) + semi-transparent 16th–84th percentile band (fill, opacity ~0.2)
- **Toggles:** st.checkbox for legend visibility, st.checkbox for shadow bands
- **File:** `analysis.py` → `_render_all_methods_cdf()`
- **Condition:** Requires `obs_delta_rv` and ≥1 method with best-fit values

### A3. Max K-S p-value vs σ_single
- **Type:** Plotly Scatter — lines+markers (steel blue, width 2, marker size 8) + gold star at best (size 16, text label: "σ=X.XX, K-S=Y.YYYY")
- **X:** σ_single (km/s)
- **Y:** Max K-S p-value across (f_bin, π) at each σ
- **Hover:** `σ_single=%{x:.2f}<br>max K-S=%{y:.4f}`
- **Height:** 350px
- **File:** `subtabs.py` → `_render_sigma_scan_chart()`, `helpers.py` → `_make_max_pval_fig()`
- **Condition:** Only if sigma_grid has >1 value

### A4. Period Distribution Histogram
- **Type:** Plotly Histogram (overlaid bars)
- **X:** log₁₀(P / days)
- **Y:** Probability density or fraction per bin (toggle radio)
- **Two forms depending on model:**
  - **No Case A/B (Dsilva):** Single histogram — detected (tomato #E25A53) vs missed (amber). No radio switcher
  - **Has Case A/B (Langer):** st.radio with 3 options: "Detected/Missed" (red+amber), "Case A/B" (blue+amber), "All overlaid" (all 4 traces). Plus normalization toggle: "Probability density" vs "Probability"
- **Annotations:** Vertical dashed lines at logP_min and logP_max bounds
- **Caption:** Explains missed systems concentrate at long periods
- **File:** `sim_plots.py` → `render_period_distribution()`
- **Condition:** Always shown if `gap_sim` data available

### A5. Binary Fraction vs ΔRV Threshold (Gap Analysis)
- **Type:** Plotly Scatter + filled areas
- **X:** ΔRV threshold (0 to 1.05 × max observed ΔRV)
- **Y:** Fraction of sample
- **Elements (always):**
  - Blue solid line: observed f_bin(T)
  - Red dashed horizontal: intrinsic f_bin target
  - Amber dashed vertical: 45.5 km/s detection threshold
  - Amber filled area: missed binaries below threshold
  - Diamond marker at observed (threshold, f_bin) point
  - Arrow annotation showing gap between intrinsic and observed f_bin
  - Text box: "Gap: X% (N missed / M binaries)"
- **Conditional:** Blue filled area (singles above threshold) — only if `np.any(false_pos_curve > 0)`
- **File:** `sim_plots.py` → `render_binary_fraction_vs_threshold()`
- **Condition:** Always shown if `gap_sim` data available

### A6. Orbital Histograms (9-panel grid)
- **Type:** Plotly `make_subplots(3, 3)` — 9 histograms, 30 bins each
- **Panels:** log₁₀P, e, q, K₁ (km/s), M₁ (M☉), M₂ (M☉), i (°), ω (°), T₀ (rad)
- **Radio selector** (5 options, horizontal):
  - "Compare detected vs missed" — red (detected) + amber (missed)
  - "Detected binaries only" — red
  - "Missed binaries only" — amber
  - "All binaries (combined)" — green
  - "Case A vs Case B" — blue + gold (**only if** Langer with `has_case_AB=True`)
- **File:** `sim_plots.py` → `render_orbital_histograms()`
- **Condition:** Always shown if `gap_sim` data available

### A7. Methodology Equations
- **Type:** st.expander with LaTeX + markdown (not a Plotly chart)
- **Dsilva:** Inline equations — K₁ formula, Kepler equation, true anomaly, RV curve, binary criterion (ΔRV > 45.5 AND ΔRV − 4σ > 0)
- **Langer/Cadence:** Delegates to `_render_methodology_expander()` in helpers.py
- **File:** `sim_plots.py` → `render_methodology_equations()`

---

## B. Live Run Graphs (During Grid Computation)

Rendered by `polling.py → _render_running_fragment()` — `@st.fragment(run_every=3)`.

### B1. Live 2×2 Heatmap Grid (all 4 computed methods)
- **Layout:** 2 rows × 2 columns
  - Top-left: **K-S (standard)** p-value
  - Top-right: **K-S (weighted)** p-value
  - Bottom-left: **CvM** p-value
  - Bottom-right: **Likelihood** normalized likelihood
- **Each tile:** `make_heatmap_fig()` with `live=True` — contours and star HIDDEN
- **Height:** 300px per tile
- **Data source:** `job['live_heatmaps']` dict, updated by background thread at ≤1 Hz
- **File:** `polling.py` → `_render_heatmap_row()`
- **Condition:** Always shown while job status = 'running'

### B2. Live σ_single 1D Profile
- **Type:** Plotly Scatter — lines+markers (steel blue) + gold star
- **X:** σ_single (km/s), **Y:** Max K-S p-value per σ (or max likelihood if available)
- **Height:** 250px
- **Branching:** If `max_likelihood` has any value > 0 → shows likelihood curve; else → K-S curve
- **File:** `helpers.py` → `_make_max_pval_fig()`
- **Condition:** sigma_grid has >1 value

### B3. Live logPmax 1D Profile
- **Type:** Same as B2 but X = logP_max
- **Height:** 250px
- **File:** `helpers.py` → `_make_max_pval_fig()`
- **Condition:** logPmax scan enabled (cadence tabs)

---

## C. Final Persisted Graphs (After Job Completes)

Same data as B1–B2 but with `live=False` → contours + best-fit star now VISIBLE. Stored in `{p}_final_live_heatmaps` / `{p}_final_live_sigma_1d` session_state keys.

### C1. Final 2×2 Heatmap Grid
- Same 4 tiles as B1 + contour lines (black dotted, 0.05–0.30) + gold star markers with labels
- **File:** `polling.py` → `_render_final_heatmaps()`

### C2. Final σ_single 1D Profile
- Same as B2, persisted. Branches K-S vs Likelihood.
- **File:** `polling.py` → `_render_final_sigma_1d()`

---

## D. K-S (Standard) — Detailed Analysis Tab

Selected via radio "K-S (standard)". Path: `subtabs.py → _render_method_tab(method_key='ks') → analysis.py → _render_method_expander()`.

### D1. Primary Heatmap — K-S p-value (2D slice)
- **Type:** `make_heatmap_fig()` with `show_d=False`, `scoring_label='K-S'`
- **X:** π (Dsilva) or σ_single (Langer/Cadence)
- **Y:** f_bin
- **Z/Colorbar:** K-S p-value [0,1], RdBu_r
- **Contours:** p-value levels 0.05–0.30 (black dotted)
- **Star:** Gold at global max p-value
- **Slice controls:** σ_single st.select_slider (if n_sig > 1), logPmax st.select_slider (if n_logPmax > 1)
- **File:** `analysis.py:642-654`
- **Condition:** Always shown

### D2. Extra Heatmap — f_bin × logPmax
- **Type:** `make_heatmap_fig()`
- **X:** logP_max, **Y:** f_bin
- **Z:** Max K-S p over (π, σ) axes
- **File:** `analysis.py:666-675`
- **Condition:** Dsilva 4D with logPmax_grid.size > 1 AND sigma_grid.size > 1

### D3. Extra Heatmap — σ × logPmax
- **Type:** `make_heatmap_fig()`
- **X:** logP_max, **Y:** σ_single
- **Z:** Max K-S p over (f_bin, π) axes
- **File:** `analysis.py:679-689`
- **Condition:** Same as D2

### D4. Best-Fit Metrics
- **Type:** st.metric cards (not a chart)
- **2D modes (Langer):** Single card — best f_bin, best π/σ, K-S p-value
- **Higher-D modes:** Two cards side-by-side — "Current slice best" + "Global best"
- **File:** `analysis.py:696-715`

### D5. Scoring Detail — Three Stacked Heatmaps
Called by `_render_cvm_analysis(mode='ks')` — despite the function name, it handles all methods.

**D5a. Raw Statistic Heatmap**
- **Z:** K-S D-statistic (all grid points; excluded = NaN/white)
- **Colorbar:** "K-S D-statistic" (or Log₁₀ if toggle on)
- **Caption:** "All models shown"
- **File:** `scoring_detail.py:169-181`

**D5b. Score-Masked Heatmap**
- **Z:** K-S D-statistic, but implausible points masked white
- **Mask rule (K-S):** p ∉ [0.05, 0.95] → NaN
- **Gold star:** From 2D parabolic fit minimum (added via st.empty() re-render)
- **Green star:** Interpolated best-fit (if fit succeeded, added later)
- **File:** `scoring_detail.py:183-207`

**D5c. Normalized Score Heatmap**
- **Z:** K-S p-value [0,1]
- **Gold + green stars** same as D5b
- **File:** `scoring_detail.py:209-224`

**All three:** Rendered via st.empty() slots to support later re-rendering with stars.

### D6. Log₁₀ Scale Toggle
- **Type:** st.checkbox "Log₁₀(S) scale"
- **Effect:** Applies `np.log10()` to D5a/D5b colorbar values; NaN for ≤0
- **File:** `scoring_detail.py:60-70`

### D7. Grid Range Exclusion UI
- **Type:** Expandable — per-axis range sliders (if ≥5 grid values) or multiselect (if <5) + sigma exclusion multiselect
- **Effect:** Builds `_exc_mask_2d` → excluded points become NaN/white on all 3 heatmaps
- **Info box:** "Excluding N / M grid points"
- **File:** `scoring_detail.py:73-151`

### D8. S_raw Heatmap (K-S ONLY)
- **Z:** Unweighted CvM S-score — cross-model comparable (lower = better)
- **Caption:** "Lower S_raw = better fit. Directly comparable across models."
- **File:** `scoring_detail.py:242-257`
- **Condition:** `not _is_likelihood` AND `ks_S_raw_2d is not None` AND has finite values

### D9. Fit Mode Selector + 1D Slices
- **Radio:** "Height-based" / "Range-based" / "Neighborhood" — controls which grid points are included in parabolic fit
  - Height-based: S < S_min × factor (default 2.0) + per-axis factor sliders
  - Range-based: ±fraction of grid range (default 0.1)
  - Neighborhood: ±N neighbors per axis (max = grid_size/2)
- **1D Slices:** 2 columns (f_bin slice + x slice) or 3 columns (+ σ/logPmax slice if 3D)
  - Each: Plotly Scatter with grid-point markers + quadratic fit curve (green) + gold star (grid best) + green star (interpolated best)
  - Blue HDI shading rectangle on each slice
- **File:** `scoring_detail.py:259-610`, `fitting.py` → `_render_cvm_1d_plot()`

### D10. 3D Parabolic Surface
- **Type:** Plotly Surface (50×50 grid, Viridis_r, opacity 0.7) + Scatter3d (grid points, size 3) + gold star (size 8)
- **Camera presets radio:** Default (1.5,1.5,1.2), Top-down (0,0,2.5), Front (1.5,0,0.5), Side (0,1.5,0.5)
- **Height:** 500px
- **File:** `scoring_detail.py:344-417`
- **Condition:** Only after successful 2D parabolic fit (`_fit_coeffs is not None`)

### D11. 3D Quadratic Fit + 3 Projections
- **Type:** 3 Plotly Surface plots — cross-sections at best-fit:
  1. f_bin × y (fix z at best)
  2. f_bin × z (fix y at best)
  3. y × z (fix f_bin at best)
- Each: 50×50 paraboloid + grid points + gold star
- **File:** `scoring_detail.py:419-551`, `fitting.py → _parabolic_min_3d()`
- **Condition:** sigma_grid.size > 1 OR logPmax_grid.size > 1 (adds 3rd dimension)

### D12. Score vs σ_single Profile
- **Type:** `_make_max_pval_fig()` — lines+markers (steel blue) + gold star
- **X:** σ_single, **Y:** Max K-S p per σ (higher = better)
- **Height:** 350px
- **File:** `analysis.py:772-820`
- **Condition:** sigma_grid.size > 1

### D13. Score vs logPmax Profile
- **Type:** Same as D12 but X = logP_max
- **File:** `analysis.py:824-860`
- **Condition:** logPmax_grid.size > 1

### D14. Corner Plot (N×N)
- **Type:** Plotly `make_subplots(n, n)` — N×N grid
- **Diagonal:** 1D posteriors — normalized K-S p histogram + blue 68% HDI fill + red dashed mode line
- **Off-diagonal (lower):** 2D marginalized heatmap (RdBu_r) + 68%/95% contour lines (white/gray dotted) + gold star with black border
- **Upper triangle:** Hidden
- **Shape:** 2×2 (f_bin × x) up to 4×4 depending on scanned axes
- **File:** `corner_plots.py → _render_corner_plot()`
- **Condition:** Always called for K-S; requires ≥2 scanned parameters

### D15. Per-Method Summary Table
- **Type:** st.dataframe (not a chart)
- **Rows:** Parameter (f_bin, π/σ, σ if multi, logPmax if multi, Score)
- **Columns:** Parameter | Best (grid) | Mode ± HDI68 | Interpolated (if fit)
- **File:** `analysis.py`
- **Condition:** Always shown after corner plot

### D16. Re-simulation CDF at Interpolated Best-Fit
- **Type:** Plotly Scatter — step lines + shaded 68% band
- **Observed:** Solid black step function
- **Simulated:** Dashed method-color median + semi-transparent band
- **Controls:** N_sets number_input (100–50k) + "Re-simulate" button
- **File:** `analysis.py → _render_resim_interp()`
- **Condition:** Only if parabolic fit succeeded (interpolated best available)

### D17. Model Explorer
Interactive parameter space exploration with live feedback.
- **Controls:** Sliders for f_bin [0,1], x_val [grid range], σ_single [grid range] (if multi), logPmax [grid range] (if present)
- **Plot 1 — CDF:** Observed (black solid step, width 2.5) + simulated median (dashed method-color) + 16th–84th band (fill, opacity 0.2). Uses `_me_cdf_band()` (cached, N_sets=50)
- **Plot 2 — Histogram:** Simulated ΔRV distribution (blue bars, ~40 bins)
- **Metric:** "Detected: X / Y (Z%)" — applies full 4σ criterion (ΔRV > 45.5 AND ΔRV − 4σ > 0)
- **Score display:** Per-method score value (K-S p or D) at current slider position
- **File:** `analysis.py → _render_model_explorer()`
- **Condition:** Always shown in method expander if `obs_delta_rv` available

### D18. CDF Sanity Check (cadence tabs only)
- **Type:** Plotly Scatter — step lines (`shape='hv'`)
- **Observed:** Dark blue (#4A90D9), solid, width 3
- **5 simulated draws:** Seeds 42–46, each with 25 stars at best-fit params
  - Colors: #E25A53 (red), #50C878 (green), #9B59B6 (purple), #F39C12 (orange), #1ABC9C (teal)
  - Dashed, width 1.5, opacity 0.7
- **Title:** "CDF Sanity Check (f_bin=X.XXX, 25 stars × 5 draws)"
- **Height:** 420px
- **Legend:** x=0.55, y=0.35, font size 10
- **File:** `helpers.py → _render_cdf_sanity_check()`
- **Condition:** Cadence tabs only (`cadence_library is not None`)

---

## E. Likelihood — Detailed Analysis Tab

Selected via radio "Likelihood". Path: same as K-S but with `method_key='likelihood'`.

**Shares ALL graphs from D1–D18** with these differences:

### E1. Primary Heatmap — Normalized Likelihood
- Same as D1 but `scoring_label='Likelihood'`, `show_d=False`
- **Z/Colorbar:** Normalized likelihood [0,1] (best = 1.0), title "Normalized Likelihood"

### E2–E3. Extra Heatmaps
- Same as D2–D3 but with likelihood values

### E4. Scoring Detail — Three Stacked Heatmaps (different masking)

**E4a. Raw Statistic Heatmap**
- **Z:** −log L (raw log-likelihood, negated so lower = better)

**E4b. Score-Masked Heatmap**
- **Mask rule (Likelihood):** L < 5% of max likelihood → NaN (**different from** K-S's p ∈ [0.05, 0.95] rule)

**E4c. Normalized Likelihood Heatmap**
- **Z:** Normalized likelihood [0,1]

### E5. Likelihood CDF with Bin Overlay (LIKELIHOOD-ONLY)
- **Type:** Plotly Scatter — CDF step lines + optional bin overlay
- **Observed:** Solid blue step function
- **Simulated:** Dashed red median CDF at best-fit + rose 16th–84th band
- **Bin overlay (st.checkbox toggle):** Vertical dashed grey lines at bin edges + alternating semi-transparent rectangles + bin labels at top
- **Annotation:** ln L value in top-right corner
- **File:** `likelihood_viz.py → render_likelihood_cdf()`
- **Condition:** Only for likelihood method, requires `obs_delta_rv` and `likelihood_bin_edges`

### E6. Per-Bin Likelihood Breakdown Table (LIKELIHOOD-ONLY)
- **Type:** st.dataframe
- **Columns:** Bin label (e.g., "0–45.5 km/s") | n_obs | n_sim | p_i (fraction) | ln(p_i) | n_i·ln(p_i)
- **Footer row:** Total ln L = Σ n_i·ln(p_i)
- **File:** `likelihood_viz.py → render_likelihood_stats_table()`
- **Condition:** Same as E5

### E7. Likelihood Methodology Explainer (LIKELIHOOD-ONLY)
- **Type:** st.expander "How is the likelihood calculated?" — 3 sections:
  1. Raw formula: ln L = Σ nᵢ ln(pᵢ) + worked example with actual bin counts
  2. Normalization to [0,1]: divides by global max
  3. "Flat surface" discussion: why many points cluster near 1.0 with coarse bins
- **File:** `likelihood_viz.py → render_likelihood_explanation()`
- **Condition:** Same as E5

### E8. Corner Plot — NOT rendered for Likelihood
- Corner plots are **skipped** for the likelihood method in current implementation

### E9. S_raw Heatmap — NOT rendered for Likelihood
- The unweighted CvM S-score heatmap only appears when `not _is_likelihood`

---

## F. Compare Tab Graphs

Rendered in Compare tab when 2+ saved results loaded. `extras.py → _render_compare_tab()`.

### F1. Selected Results Confirmation Table
- **Type:** st.dataframe — Label (#1, #2, ...), Color swatch, Filename
- **Warning:** ">6 results: plots may be crowded"

### F2. Run Parameters Expanders
- **Type:** Per-result st.expander (up to 4 columns) showing full config — model, timestamp, N stars, σ_measure, f_bin range, π range, σ range, logP range, e_model, q_model, M₁, Langer period params

### F3. Best-Fit Comparison Table
- **Type:** st.dataframe — Result | Model | Best f_bin | f_bin HDI (mode ⁺ᵘᵖ₋ₗₒ) | Best π/σ | π/σ HDI | p-value | S_raw | p(resim)

### F4. Parameter Differences Table
- **Type:** st.dataframe with `.style.apply()` — all settings keys across results; **rows where values differ highlighted orange**

### F5. Score Heatmaps (two modes)
- **Overlay** (2 results, same model/shape): Result 1 as filled heatmap (blue, opacity 0.6) + Result 2 as contour lines (dotted dark)
- **Side-by-side** (any count): Up to 3 columns, one `make_heatmap_fig()` per result with best-fit star
- **Toggle:** st.radio "Side-by-side" / "Overlay"

### F6. 1D Posterior Overlays — f_bin
- **Type:** Plotly Scatter — per-result line (color/dash rotation from `_CMP_COLORS`/`_CMP_DASHES`, 10 colors × 5 dash patterns) + semi-transparent HDI shading + dashed mode line
- **X:** f_bin, **Y:** Posterior density (marginalized from heatmap)

### F7. 1D Posterior Overlays — x-axis
- **Type:** Same as F6, grouped by model type — π posteriors (Dsilva results) on left column, σ posteriors (Langer results) on right column

### F8. Likelihood Posteriors (Dsilva+2023)
- **Type:** Same structure as F6/F7 but using multinomial likelihood arrays
- **Condition:** Only if likelihood data present in results

### F9. Observed ΔRV CDF with Simulated Overlays
- **Type:** Plotly Scatter — observed (solid black) + per-result simulated CDF (dashed, colored per `_CMP_COLORS`)
- **For cadence results:** Includes median CDF with confidence band

---

## G. RV Errors Tab Graphs

Rendered in RV Errors tab. `extras.py → _render_rv_errors_tab()`.

### G1. Per-Population Histogram + PDF Overlay
- **Type:** Plotly Histogram (40 bins, normalized) + Scatter (fitted PDF curve, red dashed)
- **Layout:** 2 columns — Singles (left), Binaries (right)
- **Each column:** Distribution selectbox (6 options) + Auto-fit button + parameter inputs + plot + "AIC: X · BIC: Y · log L: Z" display + data summary (mean, median, std)
- **Positive-only distributions** (lognorm, gamma, Weibull, expon): x_lo clamped to 0.001

### G2. Q-Q Plot (best-fit distribution)
- **Type:** Plotly Scatter — sample quantiles (y) vs theoretical quantiles from `ppf()` (x) + y=x reference line (red dashed)
- **Condition:** Shown after "🔍 Run Auto-Fit" button fits all 6 distributions and ranks by AIC

### G3. Combined Population Overlay Histogram
- **Type:** Plotly Histogram × 2 — singles vs binaries overlaid (different colors)
- **Below:** Two-sample K-S test result: "D = X.XXX, p = Y.YYY" + significance interpretation at α = 0.05

---

## H. 3D Stacked Surfaces (Exploratory)

### H1. Stacked Semi-Transparent Surfaces
- **Type:** Plotly `go.Surface` — one layer per σ_single value
- **X-mesh:** π values, **Y-mesh:** f_bin values, **Z-position:** constant at σ value
- **Surface color:** p-value at that σ slice
- **Colorscale:** RdBu_r, cmin=0, cmax=global max, opacity 0.6
- **Layer cap:** Max 20 layers (evenly sampled via `np.linspace` if n_sig > 20)
- **Colorbar:** Only on last layer — title "{stat} p", thickness 14, len 60%
- **Height:** 700px
- **Hover:** `σ_single={σ:.1f}<br>π={x:.2f}<br>f_bin={y:.3f}<br>p={surfacecolor:.4f}`
- **File:** `helpers.py → _make_3d_stacked_fig()`
- **Condition:** Sigma sweep with 3D result available

---

## Conditional Visibility Summary

| Graph | Always | σ > 1 | logP > 1 | Both > 1 | Cadence | Lk only | KS only | Langer |
|-------|:------:|:-----:|:--------:|:--------:|:-------:|:-------:|:-------:|:------:|
| A1 Summary table | ✓ | | | | | | | |
| A2 CDF comparison | ✓ | | | | | | | |
| A3 σ scan chart | | ✓ | | | | | | |
| A4 Period histogram | ✓ | | | | | | | |
| A5 Gap analysis | ✓ | | | | | | | |
| A6 Orbital histograms | ✓ | | | | | | | |
| B1 Live 2×2 grid | ✓ | | | | | | | |
| D1 Primary heatmap | ✓ | | | | | | | |
| D2–D3 Extra heatmaps | | | | ✓ | | | | |
| D5a–c Three heatmaps | ✓ | | | | | | | |
| D8 S_raw heatmap | | | | | | | ✓ | |
| D9 1D slices (2 cols) | ✓ | | | | | | | |
| D9 1D slices (3 cols) | | ✓ or logP>1 | | | | | | |
| D10 3D surface | | fit ok | | | | | | |
| D11 3D projections | | ✓ or logP>1 | | | | | | |
| D12 Score vs σ | | ✓ | | | | | | |
| D13 Score vs logPmax | | | ✓ | | | | | |
| D14 Corner plot | | | | | | | ✓ | |
| D16 Re-sim CDF | | fit ok | | | | | | |
| D17 Model Explorer | ✓ | | | | | | | |
| D18 CDF sanity check | | | | | ✓ | | | |
| E5 Likelihood CDF+bins | | | | | | ✓ | | |
| E6 Per-bin table | | | | | | ✓ | | |
| E7 Methodology | | | | | | ✓ | | |
| A4 Case A/B radio | | | | | | | | ✓ |
| A6 Case A/B option | | | | | | | | ✓ |
| H1 3D stacked surfaces | | ✓ | | | | | | |

---

## Graph Count Per Method (min–max)

| Context | K-S | Likelihood | Weighted | CvM |
|---------|:---:|:----------:|:--------:|:---:|
| Live 2×2 tile | 1 | 1 | 1 | 1 |
| Final 2×2 tile | 1 | 1 | 1 | 1 |
| Primary heatmap | 1 | 1 | — | — |
| Extra heatmaps (4D) | 0–2 | 0–2 | — | — |
| Three scoring heatmaps | 3 | 3 | — | — |
| S_raw heatmap | 1 | **0** | — | — |
| 1D slices | 2–3 | 2–3 | — | — |
| 3D surface | 0–1 | 0–1 | — | — |
| 3D projections | 0–3 | 0–3 | — | — |
| Score vs σ | 0–1 | 0–1 | — | — |
| Score vs logPmax | 0–1 | 0–1 | — | — |
| Corner plot | 1 | **0** | — | — |
| Re-sim CDF | 0–1 | 0–1 | — | — |
| Model Explorer CDF+hist | 2 | 2 | — | — |
| CDF sanity check | 0–1 | 0–1 | — | — |
| Likelihood CDF+bins | — | 1 | — | — |
| Likelihood table | — | 1 | — | — |
| **Total (min–max)** | **14–23** | **12–21** | **2** | **2** |

**Shared (all methods):** ~14 graphs/tables (summary table, CDF comparison, σ chart, period hist, gap analysis, 9 orbital hists, methodology).
