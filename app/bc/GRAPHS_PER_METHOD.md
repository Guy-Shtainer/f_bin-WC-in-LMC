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

## Rendering Order (top to bottom as user sees it)

### Top Heatmaps (`cadence.py` → `_render_top_heatmaps()`) — live during runs, persistent after

| # | ID | Graph | Status | File | Comment |
|---|-----|-------|--------|------|---------|
| 0a | H1 | Normalized Likelihood (f_bin × π) at best σ/logP | **WORKING ✓** | `cadence.py` | |
| 0b | H2 | Max Normalized Likelihood (σ × logP_max) | **WORKING ✓** | `cadence.py` | |
| 0c | H3 | −log L (f_bin × π) at best σ/logP | **WORKING ✓** | `cadence.py` | |
| 0d | H4 | Max −log L (σ × logP_max) | **WORKING ✓** | `cadence.py` | |

### Shared Section (`render_shared.py` → `render_shared_section()`)

| # | ID | Graph | Status | File | Comment |
|---|-----|-------|--------|------|---------|
| 1 | A1 | Summary Table (best-fit + 68% HDI + logP_max + interpolated) | **WORKING ✓** | `render_shared.py` | |
| 2 | A2 | CDF Comparison (observed lightblue line + params in legend) | **WORKING ✓** | `render_shared.py` | |
| 2b | E6 | Per-Bin Likelihood Breakdown Table | **WORKING ✓** | `render_lk_fit.py` (called from `render_shared.py`) | |
| - | ~~A4~~ | ~~Period Distribution Histogram~~ | **REMOVED** | | Already present inside A6 orbital histograms (logP panel) |
| 3 | A5 | Binary Fraction vs ΔRV Threshold | **WORKING ✓** | `render_shared.py` | |
| 4 | A6 | Orbital Histograms (9-panel + best-model subtitle) | **WORKING ✓** | `render_shared.py` | |
| 5 | A7 | Methodology Equations (LaTeX) | **WORKING ✓** | `render_shared.py` | |

### Live Run Section (`polling.py`) — visible during active simulation

| # | ID | Graph | Status | File | Comment |
|---|-----|-------|--------|------|---------|
| - | B1 | Live Heatmap | **WORKING ✓** | `polling.py` | |
| - | B2 | Live σ/logPmax Profile | **WORKING ✓** | `polling.py` + `runners_cadence.py` | 2D heatmap when both σ and logPmax scanned. Fallback: separate 1D charts |

### Likelihood Analysis (`render_lk.py` → `render_lk_scoring.py` → `render_lk_fit.py` → `render_lk_explorer.py`)

| # | ID | Graph | Status | File | Comment |
|---|-----|-------|--------|------|---------|
| 6 | A3 | Max −logL vs σ/logPmax (unnormalized) | **MODIFY** | `render_shared.py` (called from `render_lk.py`) | MOVE: place as RIGHT panel of D5a (unnormalized row). Replace current D5a right panel (σ×logPmax max-L) with this. See D1/D5a for full layout reorganization |
| 7 | D1 | ~~Primary Heatmap~~ | **MOVED** | `cadence.py` | Moved to top heatmaps (H1-H4). Sliders removed. |
| - | ~~D2-D3~~ | ~~Extra Heatmaps~~ | **REMOVED** | | Covered by A3 upgrade |
| 8 | D4 | Best-Fit Metric Cards | **WORKING ✓** | `render_lk.py` | |
| 9 | D5a | Raw logL Heatmap (single panel) | **MODIFY** | `render_lk_scoring.py` | RIGHT panel moved to top (H4). LEFT panel kept for parabolic fit overlay |
| - | ~~D5b~~ | ~~Score-Masked Heatmap~~ | **REMOVED** | | |
| - | ~~D5c~~ | ~~Normalized Likelihood Heatmap~~ | **REMOVED** | | |
| - | ~~E6~~ | ~~Per-Bin Breakdown Table~~ | **MOVED** | | Moved to Shared Section (#2b), directly under A2 CDF |
| 11 | E7 | LaTeX Methodology Explainer (good + bad example) | **WORKING ✓** | `render_lk_fit.py` | Approved 2026-03-25 |
| 12 | D10 | 3D Parabolic Surface | **MODIFY** | `render_lk_scoring.py` | Move fit selection controls (Height/Range/Neighborhood radio + params) to be under the "3D Parabolic Surface" title, not above it |
| 13 | D9 | 1D Slices (parabolic fit + HDI) | **MODIFY** | `render_lk_scoring.py` | (1) Only show f_bin and π slices — remove σ and logP_max 1D slices. (2) LaTeX axis labels. (3) Change star marker from yellow to green |
| - | ~~D11~~ | ~~3D Projections (N-D fit)~~ | **REMOVED** | | Simplified to f_bin×π only |
| - | ~~D12~~ | ~~Score vs σ Profile~~ | **REMOVED** | | Covered by A3 |
| - | ~~D13~~ | ~~Score vs logPmax Profile~~ | **REMOVED** | | Covered by A3 |
| 14 | D14 | Corner Plot (N×N marginals) | **WORKING ✓** | `render_lk_fit.py` | Approved 2026-03-25 |
| 15 | D15 | Summary Table (with interpolation + auto re-sim) | **MODIFY** | `render_lk.py` | (1) Auto re-sim immediately when interpolated result available — no button needed. (2) Re-sim result gets its own column in same table. (3) Interpolation is on 3D -logL vs f_bin×π at best σ/logP — no interpolation on σ/logP themselves. (4) N_sets change + Enter triggers re-sim automatically (no button) |
| - | ~~D16~~ | ~~Re-sim CDF at Interpolated Best-Fit~~ | **FOLDED** | | Folded into D15 (auto re-sim after interpolation) |
| 16 | D17 | Model Explorer (sliders + reset + score comparison) | **MODIFY** | `render_lk_explorer.py` | (1) No green dots on sliders for best-fit. (2) Reset button broken. (3) LnL display: mimic the metric boxes from D4 (best + current). (4) Remove ability to explore from top sliders — just show best-fit model. (5) Add all 4 heatmaps (norm f_bin×π, norm σ×logP, unnorm f_bin×π, unnorm σ×logP) with green dot for current. (6) Remove green shade/thick line from CDF |
| 17 | D18 | CDF Sanity Check (5 random draws, cadence only) | **MODIFY** | `render_lk_explorer.py` | Only 1 line visible — 5 simulated CDFs not rendering. Fix to show 5 semi-transparent + observed solid white |
| - | ~~E5~~ | ~~Likelihood CDF with Bin Overlay~~ | **REMOVED** | | Redundant with A2 CDF |

---

## Removed Graphs (backed up in Backups/)

D2-D3, D5b, D5c, D8, D11, D12, D13, A2 (old), A4, E5, D16 (folded into D15),
E8, E9, all K-S/CvM/weighted graphs

---

## Change Log

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
