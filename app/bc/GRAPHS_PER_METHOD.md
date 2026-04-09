# GRAPHS_PER_METHOD.md — Likelihood Scoring Graph Catalog

> **Purpose:** Lists every graph/plot in the bias correction page (likelihood-only scoring).
> Use as a regression checklist after code changes. Status tags: `WORKING ✓`, `MODIFY`, `BUILD`, `REMOVE`.
> **After every code change, verify all `WORKING ✓` graphs still render correctly.**

---

## Scoring Method: Likelihood Only

| Method | Key | Color |
|--------|-----|-------|
| Likelihood (multinomial log-likelihood, Dsilva+2023) | `likelihood` | #DAA520 (gold) |

**Registry:** `SCORING_METHODS` in `helpers.py` — single entry.
**Convention:** Maximum likelihood framing throughout (higher = better). Internal negation for optimization only.

### Global Rule: LaTeX Labels
**ALL graphs** must use LaTeX/Unicode for parameter names in axis labels, titles, annotations, and legends:
- `f_bin` → `f<sub>bin</sub>` or `$f_{\rm bin}$`
- `pi` → `π`
- `sigma` / `sigma_single` → `σ_single`
- `logP_max` → `log₁₀(P_max)`
- `lnL` → `ln L`

---

## Cadence Dsilva — Rendering Order (top to bottom as user sees it)

### Grid Range Exclusion (`cadence.py`) — above heatmaps, default folded

| # | ID | Graph | Status | File | Comment |
|---|-----|-------|--------|------|---------|
| - | G1 | Grid Range Exclusion (folded `st.expander`) | **WORKING ✓** | `helpers.py` + `cadence.py` | Approved 2026-04-09. Range sliders for all axes (f_bin, π, σ_single, logP_max). N-D mask applied to heatmaps + downstream scoring. Excluded regions show blank. Best-fit star updates. 2D projection stored in session_state for backward compat. |

### Top Heatmaps (`cadence.py` → `_render_top_heatmaps()`) — live during runs, persistent after

| # | ID | Graph | Status | File | Comment |
|---|-----|-------|--------|------|---------|
| 0a | H1 | Normalized Likelihood (f_bin × π) at best σ/logP | **WORKING ✓** | `cadence.py` | |
| 0b | H2 | Max Normalized Likelihood (σ × logP_max) | **WORKING ✓** | `cadence.py` | Approved 2026-03-29 |
| 0c | H3 | log L (f_bin × π) at best σ/logP | **WORKING ✓** | `cadence.py` | |
| 0d | H4 | Max log L (σ × logP_max) | **WORKING ✓** | `cadence.py` | Approved 2026-03-29 |

> **Cadence Langer note:** π is constant/unused → heatmap should be `f_bin` vs `log₁₀(P_max)` if available, or simply `f_bin` (1D).

### Shared Section (`render_shared.py` → `render_shared_section()`)

| # | ID | Graph | Status | File | Comment |
|---|-----|-------|--------|------|---------|
| 1 | A1 | Summary Table (best-fit + 68% HDI + logP_max + interpolated) | **WORKING ✓** | `render_shared.py` | |
| 2 | A2 | CDF Comparison (observed lightblue line + params in legend) | **WORKING ✓** | `render_shared.py` | Fixed 2026-04-09: uses actual BinaryParameterConfig (with best-fit logP_max), n_stars=1000. Was using defaults. |
| 2b | E6 | Per-Bin Likelihood Breakdown Table | **WORKING ✓** | `render_lk_fit.py` (called from `render_shared.py`) | Fixed 2026-04-09: n_sim uses actual n_sets from result (was hardcoded 100). Uses best-fit logP_max. |
| - | ~~A4~~ | ~~Period Distribution Histogram~~ | **REMOVED** | | Already present inside A6 orbital histograms (logP panel) |
| 3 | A5 | Binary Fraction vs ΔRV Threshold | **WORKING ✓** | `render_shared.py` | **Dsilva has same issues as Langer had:** (1) Blue curve labeled "Observed" is actually simulated — rename to "Simulated". (2) No real observed curve shown — add white step curve from `obs_delta_rv`. (3) Caption says "Observed" for simulated data. Apply same fix as Langer version when ready. |
| 4 | A6 | Orbital Histograms (9-panel + best-model subtitle) | **WORKING ✓** | `render_shared.py` | **Dsilva has same issue:** When M₁ is fixed (constant), histogram shows fake flat rectangle instead of vertical line. Same constant-parameter fix needed as Langer version. Apply when ready. |
| 5 | A7 | Methodology Equations (LaTeX) | **WORKING ✓** | `render_shared.py` | **Dsilva has wrong σ description:** says "σ_total = √(σ_single² + σ_measure²)" but code actually draws from N(v_sys, σ_single) then adds σ_measure separately. Fix text to match code when ready. |

### Live Run Section (`polling.py`) — visible during active simulation

| # | ID | Graph | Status | File | Comment |
|---|-----|-------|--------|------|---------|
| - | B1 | Live Heatmap | **WORKING ✓** | `polling.py` | |
| - | B2 | Live σ/logPmax Profile | **WORKING ✓** | `polling.py` + `runners_cadence.py` | 2D heatmap when both σ and logPmax scanned. Fallback: separate 1D charts for σ-only or logP-only. Fixed 2026-03-29 |

### Likelihood Analysis (`render_lk.py` → `render_lk_scoring.py` → `render_lk_fit.py` → `render_lk_explorer.py`)

| # | ID | Graph | Status | File | Comment |
|---|-----|-------|--------|------|---------|
| 6 | A3 | ~~Max logL vs σ/logPmax (unnormalized)~~ | **FOLDED** | `cadence.py` | Now part of top heatmaps (H2/H4). Original MODIFY target (D5a) was removed. |
| 7 | D1 | ~~Primary Heatmap~~ | **MOVED** | `cadence.py` | Moved to top heatmaps (H1-H4). Sliders removed. |
| - | ~~D2-D3~~ | ~~Extra Heatmaps~~ | **REMOVED** | | Covered by A3 upgrade |
| - | ~~D4~~ | ~~Best-Fit Metric Cards~~ | **REMOVED** | `render_lk.py` | Redundant with top heatmaps |
| - | ~~D5a~~ | ~~Raw logL Heatmap~~ | **REMOVED** | `render_lk_scoring.py` | Duplicate of H3 in top heatmaps |
| - | ~~D5b~~ | ~~Score-Masked Heatmap~~ | **REMOVED** | | |
| - | ~~D5c~~ | ~~Normalized Likelihood Heatmap~~ | **REMOVED** | | |
| - | ~~E6~~ | ~~Per-Bin Breakdown Table~~ | **MOVED** | | Moved to Shared Section (#2b), directly under A2 CDF |
| 11 | E7 | LaTeX Methodology Explainer (good + bad example) | **WORKING ✓** | `render_lk_fit.py` | Approved 2026-03-25 |
| 12 | D10 | 3D Parabolic Surface | **WORKING ✓** | `render_lk_scoring.py` | Approved 2026-03-29 |
| 13 | D9 | 1D Slices (parabolic fit + HDI) | **WORKING ✓** | `render_lk_scoring.py` | Approved 2026-03-29 |
| - | ~~D11~~ | ~~3D Projections (N-D fit)~~ | **REMOVED** | | Simplified to f_bin×π only |
| - | ~~D12~~ | ~~Score vs σ Profile~~ | **REMOVED** | | Covered by A3 |
| - | ~~D13~~ | ~~Score vs logPmax Profile~~ | **REMOVED** | | Covered by A3 |
| 14 | D14 | Corner Plot (N×N marginals) | **WORKING ✓** | `render_lk_fit.py` | Approved 2026-03-25 |
| 15 | D15 | Summary Table (with interpolation + cadence-aware re-sim) | **WORKING ✓** | `render_lk.py` | Approved 2026-03-29. Cadence-aware re-sim, normalized likelihood with asterisk, logL row, σ/logP in re-sim with (grid) note |
| - | ~~D16~~ | ~~Re-sim CDF at Interpolated Best-Fit~~ | **FOLDED** | | Folded into D15 (auto re-sim after interpolation) |
| 16 | D17 | Model Explorer (sliders + reset + score comparison) | **WORKING ✓** | `render_lk_explorer.py` | Approved 2026-04-09. Cadence-aware simulation for logL scores (matches grid). CDF + Binary Fraction plots with best-fit overlay. Full-featured detection fraction chart. |
| 17 | D18 | CDF Sanity Check (5 random draws, cadence only) | **WORKING ✓** | `render_lk_explorer.py` | Approved 2026-03-29 |
| - | ~~E5~~ | ~~Likelihood CDF with Bin Overlay~~ | **REMOVED** | | Redundant with A2 CDF |

---

## Cadence Langer — Rendering Order (top to bottom as user sees it)

> **Key differences from Dsilva:** **Primary axes = f_bin × logP_max** (NOT σ_single). π grid unused `[0.0]`. σ_single is either constant (preset) or optionally scanned as a secondary axis. Period model = `langer2020` (Case A + Case B mixture). `has_case_AB = True` → A6 has "Case A vs Case B" radio option.
> All code is currently shared with Dsilva via `_render_cadence_results()` — **must be duplicated** into Langer-specific files to avoid breaking Dsilva's 2-week-tested code.
>
> **Langer grid combos:** (1) f_bin only → 1D. (2) f_bin × logP_max → heatmap f_bin×logP_max. (3) f_bin × σ → heatmap f_bin×σ. (4) f_bin × σ × logP_max → heatmap f_bin×logP_max + 1D σ profile.

### Grid Range Exclusion (`cadence.py:468-475`)

| # | ID | Graph | Status | File | Notes |
|---|-----|-------|--------|------|-------|
| 0 | G1 | Grid Range Exclusion (folded expander) | **WORKING ✓** | `helpers.py` + `cadence.py` | Approved 2026-04-09. Same fix as Dsilva: range sliders for all axes, N-D mask, excluded regions blank on heatmaps. |

### Top Heatmaps (`cadence.py:45-230`, `_render_top_heatmaps`)

| # | ID | Graph | Status | File | Notes |
|---|-----|-------|--------|------|-------|
| 1 | H1 | Normalized Likelihood — LEFT primary heatmap | **WORKING ✓** | `cadence.py` | Approved 2026-03-30 (Langer). Uses `_render_top_heatmaps_langer`. f_bin×logP_max (default), f_bin×σ (if no logP), 1D f_bin (if only f_bin). Live-updates every 3s during runs via `polling_langer.py`. |
| 2 | H2 | Max Norm. Likelihood — RIGHT secondary panel | **WORKING ✓** | `cadence.py` | Approved 2026-03-30 (Langer). 1D σ profile only when 3 grids scanned. Otherwise empty. |
| 3 | H3 | log L — LEFT primary heatmap (unnormalized) | **WORKING ✓** | `cadence.py` | Approved 2026-03-30 (Langer). Same logic as H1 for raw logL. |
| 4 | H4 | Max log L — RIGHT secondary panel (unnormalized) | **WORKING ✓** | `cadence.py` | Approved 2026-03-30 (Langer). Same logic as H2 for raw logL. |
|   |    | Best-fit caption (f_bin, σ, optionally logP_max) | **WORKING ✓** | `cadence.py` | Approved 2026-03-30 (Langer). Only shows scanned params. Constants marked "(constant)". |

### Shared Section (`render_shared.py:784-835`, `render_shared_section`)

| # | ID | Graph | Status | File | Notes |
|---|-----|-------|--------|------|-------|
| 5 | A1 | Summary Table (best f_bin, σ_single, HDI, logP_max if scanned, interp, logL) | **WORKING ✓** | `render_shared_langer.py` | Approved 2026-03-30 (Langer). Explicit 4-case grid handler matching runner dimension order. Constant σ shown as "X.XX (constant)" with "—" for HDI. |
| 6 | A2 | CDF Comparison (observed lightblue + model gold, 100 runs, median+68% bands) | **WORKING ✓** | `render_shared_langer.py` | Approved 2026-03-30 (Langer). Observed CDF uses `shape='hv'` for step rendering. Model CDF renders with 68% band. Legend correct. Toggle hides line+band together. |
| 7 | E6 | Per-Bin Likelihood Breakdown Table (obs vs sim counts per bin) | **WORKING ✓** | `render_lk_fit.py` (called from `render_shared.py`) | Approved 2026-03-30 (Langer) |
| 8 | A5 | Binary Fraction vs ΔRV Threshold (gap annotation, missed/singles shading) | **WORKING ✓** | `render_shared_langer.py` | Approved 2026-03-30 (Langer). Simulated curve correctly labeled. Real observed step curve (white, `shape='hv'`) added from `obs_delta_rv`. Caption clarified. |
| 9 | A6 | Orbital Histograms (9-panel 3×3, radio: detected/missed/all/**Case A vs B**) | **WORKING ✓** | `render_shared_langer.py` | Approved 2026-03-30 (Langer). Constant parameters (e=0, M₁=10) show vertical line instead of fake histogram. q density > 1 is correct (narrow distribution). |
| 10 | A7 | Methodology Equations (LaTeX expander) | **WORKING ✓** | `render_shared_langer.py` | Approved 2026-03-30 (Langer). Full Langer-specific inline expander with LaTeX equations. Correct σ description (σ_single + separate σ_measure). Langer period model (Case A + B mixture equation). Likelihood scoring only. No K-S/CvM. |

### Likelihood Analysis (`render_lk.py:123-169` → `render_lk_scoring.py:95-416`)

| # | ID | Graph | Status | File | Notes |
|---|-----|-------|--------|------|-------|
| 11 |    | "Likelihood Analysis" header | **WORKING ✓** | `render_lk_scoring.py` | Static text |
| 12 | E7 | Methodology Explainer (good+bad example, expander) | **WORKING ✓** | `render_lk_fit.py` | Approved 2026-03-25 (Dsilva), 2026-03-30 (Langer). Model-agnostic |
| 13 |    | "3D Parabolic Surface & Interpolation" header | **BROKEN** | `render_lk_scoring.py` | See D10 notes |
| 14 |    | Fit mode radio (Height/Range/Neighborhood) + controls | **BROKEN** | `render_lk_scoring.py` | See D10 notes |
| 15 |    | Parabolic best-fit success message | **BROKEN** | `render_lk_scoring.py` | See D10 notes |
| 16 |    | Camera preset radio (Default/Top-down/Front/Side) | **BROKEN** | `render_lk_scoring.py` | See D10 notes |
| 17 | D10 | 3D Parabolic Surface | **BROKEN** | `render_lk_scoring.py` | **Completely broken for Langer.** Shared code with Dsilva is causing problems. **Prefer duplicate Langer-specific code** to avoid breaking Dsilva (2 weeks of fixes). **Logic should be:** (1) f_bin × logP_max → 3D parabolic surface over f_bin × logP_max → logL. If σ is also scanned, pick the σ slice with best max-likelihood for the surface. (2) f_bin only → simple 1D parabola interpolation, no 3D surface needed. **Also fix:** `f<sub>bin</sub>` rendering as raw HTML in captions/labels — must render properly everywhere. |
| 18 | D9a | 1D Parabolic Slice — f_bin (left col) | **BROKEN** | `render_lk_scoring.py` | See D10 notes. Only show 1D slices when there are 2+ grid dimensions. For f_bin-only runs, the 1D parabola IS the main interpolation (no separate slice). |
| 19 | D9b | 1D Parabolic Slice — σ_single/logP_max (right col) | **BROKEN** | `render_lk_scoring.py` | See D10 notes. Should slice logP_max (not σ_single) when primary heatmap is f_bin × logP_max. |
| 20 |    | 1D slice context caption (σ/logP values) | **BROKEN** | `render_lk_scoring.py` | `f<sub>bin</sub>` renders as raw HTML text instead of formatted. Fix all HTML-in-caption occurrences. |

### Corner Plot + Summary (`render_lk.py:373-560`, `render_lk_fit.py:352-550`)

| # | ID | Graph | Status | File | Notes |
|---|-----|-------|--------|------|-------|
| 21 | D14 | Corner Plot — Likelihood (expander, N×N: diagonal=1D posteriors, lower=2D heatmaps) | **TO-TEST** | `render_lk_fit_langer.py` | Fixed 2026-03-30: axis ordering + constant-sigma exclusion. Only scanned dims shown. |
| 22 |    | "Best-fit Summary -- Likelihood" header | | `render_lk.py` | |
| 23 |    | N_sets for re-simulation number_input | | `render_lk.py` | |
| 24 | D15 | Best-fit Summary Table (Parameter / Best grid / Mode±HDI68 / Interpolated / Re-sim) | **TO-TEST** | `render_lk_langer.py` | Fixed 2026-03-30: constant σ shows actual value + "(constant)". f_bin/logPmax correct after D14 axis fix. Interpolated column depends on D10. |
| 25 |    | Normalized logL asterisk caption | | `render_lk.py` | |

### Model Explorer (`render_lk.py:529-542`, `render_lk_explorer.py:236-631`)

| # | ID | Graph | Status | File | Notes |
|---|-----|-------|--------|------|-------|
| 26 | D17 | Model Explorer (folded expander) | **TO-TEST** | `render_lk_explorer_langer.py` | Fixed 2026-03-30: Langer period model, correct best-fit extraction, dynamic sliders/labels. See sub-element notes below. |

**Inside D17 expander:**

| Sub | Element | Status | Notes |
|------|---------|--------|-------|
| D17a | Best-fit caption + 🟢 Reset button | **TO-TEST** | Fixed: shows f_bin, logP_max (if scanned), σ (constant annotated) |
| D17b | Sliders: f_bin, σ_single (+ logP_max if scanned) + synced number_inputs | **TO-TEST** | Fixed: dynamic column count, σ hidden when constant, logPmax slider correct |
| D17c | Score metric cards (Current vs Global, logL) | **TO-TEST** | Fixed: shows all scanned params, logL only |
| D17d | Compare with best-fit checkbox | **TO-TEST** | Uses Langer CDF simulation |
| D17e | Show likelihood bin edges checkbox | **TO-TEST** | Works |
| D17f | CDF plot (observed white + explorer gold + best-fit overlay) | **TO-TEST** | Cadence-aware simulation. Best-fit overlay when checkbox checked. |
| D17g | Per-bin breakdown table | **TO-TEST** | Conditional: bins checkbox ON |
| D17h | 4 heatmaps (2×2) with green dot at explorer position | **TO-TEST** | Conditional: BOTH σ AND logP scanned |
| D17i | ΔRV Distribution histogram (observed vs simulated overlay) | **TO-TEST** | Code present, works with fixed CDF simulation |
| D17j | Binary Fraction vs Threshold (full-featured, copy-pasted from render_shared.py) | **TO-TEST** | Upgraded 2026-04-09: all traces (shading, gap annotation, diamond, crossings). Best-fit overlay when checkbox checked. |
| D17k | Explorer caption | **TO-TEST** | |

### CDF Sanity Check (`render_lk.py:544-560`, `render_lk_explorer.py:148-229`)

| # | ID | Graph | Status | File | Notes |
|---|-----|-------|--------|------|-------|
| 27 | D18 | CDF Sanity Check (5 random draws × 25 stars vs observed) | **BROKEN** | `render_lk_explorer.py` | **BUG 1:** Title shows `f_bin=nan` — cascading from broken best-fit extraction. **BUG 2:** 5 draw CDFs are all flat at 0 — simulating with nan f_bin produces no binaries. Once best-fit values are fixed, draws should appear. **BUG 3:** Graph overflows right panel — x-axis too wide, shrink so entire plot is visible. **BUG 4:** Must use cadence-aware simulation with Langer period model, not generic `simulate_delta_rv_sample`. Duplicate working Dsilva cadence code. |

---

## Removed Graphs (backed up in Backups/)

D2-D3, D4, D5a, D5b, D5c, D8, D11, D12, D13, A2 (old), A4, E5, D16 (folded into D15),
E8, E9, all K-S/CvM/weighted graphs

---

## Change Log

### 2026-04-09: Grid Exclusion, CDF, Explorer Overhaul
- **G1 WORKING:** Rewrote grid exclusion with range sliders for all axes (f_bin, π, σ_single, logP_max). N-D masks. Excluded regions blank on heatmaps. Best-fit star updates correctly (nanargmax + all-NaN guard).
- **A2 Fixed:** CDF comparison now uses actual BinaryParameterConfig (was using defaults with wrong logP_max). n_stars=1000.
- **E6 Fixed:** Per-bin table n_sim uses actual n_sets from result (was hardcoded 100). Best-fit logP_max used.
- **D17 Upgraded:** Model Explorer CDF + Binary Fraction now use cadence-aware simulation (matches grid runner). logL scores directly comparable. Best-fit overlay on both CDF and Binary Fraction charts.
- **D17j Upgraded:** Detection Fraction → full "Binary Fraction vs Threshold" plot (copy-pasted from render_shared.py). All traces: shading, gap annotation, diamond, crossings, best-fit overlay.
- **Gap sim logP_max:** BinaryParameterConfig for gap_sim now uses best-fit ana_logPmax when logPmax is a grid search axis.
- **Gold star fix:** `find_best_grid_point` uses `nanargmax` + all-NaN guard.
- **Extra grids fix:** `_build_extra_grids` only includes axes with >1 value (prevents grid/dim mismatch).
- **Files:** helpers.py, cadence.py, subtabs.py, shared.py, render_shared.py, render_lk_scoring.py, render_lk_scoring_langer.py, render_lk_explorer.py

### 2026-03-30: Cadence Langer Graph Catalog
- Added full "Cadence Langer — Rendering Order" section with 27 top-level elements + 11 D17 sub-elements
- Renamed existing rendering order to "Cadence Dsilva" for clarity
- Documented Langer-specific differences: σ_single x-axis, Case A vs B radio, langer2020 period model

### 2026-03-26: LogL Consistency + Cleanup
- **Removed:** D4 (metric cards, redundant with top heatmaps), D5a (logL heatmap, duplicate of H3)
- **Removed:** Log10 scale toggle (redundant after top heatmaps)
- **Global:** Unified sign convention — all "−log L" labels → "log L". Parabolic fit now finds maximum (not minimum). Values shown as negative (higher = better)
- **Files:** cadence.py, render_lk_scoring.py, render_lk_fit.py, render_lk_explorer.py, render_shared.py

### 2026-03-25: Rendering Order Audit
- Reordered entire catalog to match actual code rendering sequence
- Merged "Likelihood Extras" and "Interactive" sections into unified "Likelihood Analysis" section
- Added numbered (#) column for visual rendering position
- Cleared comments on previously approved graphs

### 2026-03-24: Graph Review Overhaul
- **Removed:** A4, E5, D11 (3D/4D projections), D16 (folded into D15)
- **Global:** Switched from "minimum -logL" to "maximum likelihood" framing
- **A1:** Added logP_max column + interpolated results
- **A2:** White observed line + gold annotation with lnL/σ/logP
- **A3:** Moved to Likelihood Analysis section, uses unnormalized logL_raw, taller
- **A6:** Added best-model params subtitle
- **B2:** True 2D heatmap when both σ and logPmax scanned
- **D1:** Slider best-fit captions + green reset button
- **D5a:** Fixed right panel (logPmax_grid was not passed when both axes scanned)
- **D9:** Default Range-based 0.2, shows σ/logP slice context
- **D15:** Fixed interpolation key mismatch, added N_sets chooser
- **D17:** Reset button, best-fit labels, score comparison
- **D18:** Fixed extra argument bug preventing cadence_library detection
- **E7:** Added bad example (uniform model)
