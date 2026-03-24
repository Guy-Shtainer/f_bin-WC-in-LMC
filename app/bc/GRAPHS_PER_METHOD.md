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

---

## Rendering Order (top to bottom as user sees it)

### Shared Section (`render_shared.py` → `render_model_subtabs()`)

| ID | Graph | Status | File | Comment |
|----|-------|--------|------|---------|
| A1 | Summary Table (best-fit + 68% HDI + logP_max + interpolated) | **WORKING ✓** | `render_shared.py` | Includes σ_single, logP_max columns + interpolated results from parabolic fit |
| A2 | CDF Comparison (observed white line + lnL/σ/logP annotation) | **WORKING ✓** | `render_shared.py` | White observed line for dark mode, gold annotation box with best-fit params |
| ~~A3~~ | ~~Max Likelihood vs σ/logPmax~~ | **MOVED** | `render_lk.py` | Moved to Likelihood Analysis section. Uses unnormalized logL_raw, taller (450px) |
| ~~A4~~ | ~~Period Distribution Histogram~~ | **REMOVED** | | Already present inside A6 orbital histograms (logP panel) |
| A5 | Binary Fraction vs ΔRV Threshold | **WORKING ✓** | `render_shared.py` | Gap analysis with observed f(T), intrinsic line, missed area |
| A6 | Orbital Histograms (9-panel + best-model subtitle) | **WORKING ✓** | `render_shared.py` | log₁₀P, e, q, K₁, M₁, M₂, i, ω, T₀ with radio selector. Shows best-fit params subtitle |
| A7 | Methodology Equations (LaTeX) | **WORKING ✓** | `render_shared.py` | Kepler equation, RV curve, binary criterion |

### Live Run Section (`polling.py`)

| ID | Graph | Status | File | Comment |
|----|-------|--------|------|---------|
| B1 | Live Heatmap | **WORKING ✓** | `polling.py` | Single likelihood tile (f_bin×π heatmap) |
| B2 | Live σ/logPmax Profile | **WORKING ✓** | `polling.py` + `runners_cadence.py` | 2D heatmap when both σ and logPmax scanned. Fallback: separate 1D charts |

### Likelihood Analysis (`render_lk.py` → `render_lk_scoring.py`)

| ID | Graph | Status | File | Comment |
|----|-------|--------|------|---------|
| A3 | Max −logL vs σ/logPmax (unnormalized) | **WORKING ✓** | `render_shared.py` (called from `render_lk.py`) | 1D or 2D depending on scanned axes. Height 450px |
| D1 | Primary Heatmap — f_bin×π + sliders | **WORKING ✓** | `render_lk.py` | σ/logP sliders with best-fit captions, green reset button |
| ~~D2-D3~~ | ~~Extra Heatmaps~~ | **REMOVED** | | Covered by A3 upgrade |
| D4 | Best-Fit Metric Cards | **WORKING ✓** | `render_lk.py` | Global best + current slice |
| D5a | Raw logL Heatmap (dual panel) | **WORKING ✓** | `render_lk_scoring.py` | LEFT: f_bin×π raw logL. RIGHT: σ×logPmax max-likelihood (if both grids, 1D if one) |
| ~~D5b~~ | ~~Score-Masked Heatmap~~ | **REMOVED** | | |
| ~~D5c~~ | ~~Normalized Likelihood Heatmap~~ | **REMOVED** | | |
| D10 | 3D Parabolic Surface | **WORKING ✓** | `render_lk_scoring.py` | Camera presets. Default range-based 0.2 fit |
| D9 | 1D Slices (parabolic fit + HDI) | **WORKING ✓** | `render_lk_scoring.py` | Default Range-based 0.2. Shows σ/logP slice context |
| ~~D11~~ | ~~3D Projections (N-D fit)~~ | **REMOVED** | | Simplified to f_bin×π only |
| ~~D12~~ | ~~Score vs σ Profile~~ | **REMOVED** | | Covered by A3 |
| ~~D13~~ | ~~Score vs logPmax Profile~~ | **REMOVED** | | Covered by A3 |
| D14 | Corner Plot (N×N marginals) | **WORKING ✓** | `render_lk_fit.py` | Caption: gold star = joint max (argmax), not marginal mode |
| D15 | Summary Table (with interpolation + auto re-sim) | **WORKING ✓** | `render_lk.py` | Interpolated column, N_sets chooser, auto re-sim after interpolation |

### Likelihood Extras (`render_lk_fit.py` → called from `render_lk_scoring.py`)

| ID | Graph | Status | File | Comment |
|----|-------|--------|------|---------|
| ~~E5~~ | ~~Likelihood CDF with Bin Overlay~~ | **REMOVED** | | Redundant with A2 CDF |
| E6 | Per-Bin Breakdown Table | **WORKING ✓** | `render_lk_fit.py` | DO NOT TOUCH. Shows bin label, n_obs, n_sim, p_i, ln(p_i), n_i·ln(p_i) |
| E7 | LaTeX Methodology Explainer (good + bad example) | **WORKING ✓** | `render_lk_fit.py` | Raw formula + good example + bad example (uniform) + normalization + flat surface discussion |

### Interactive (`render_lk_explorer.py`)

| ID | Graph | Status | File | Comment |
|----|-------|--------|------|---------|
| ~~D16~~ | ~~Re-sim CDF at Interpolated Best-Fit~~ | **FOLDED** | | Folded into D15 (auto re-sim after interpolation) |
| D17 | Model Explorer (sliders + reset + score comparison) | **WORKING ✓** | `render_lk_explorer.py` | Preset to best-fit, reset button, current vs best score delta |
| D18 | CDF Sanity Check (5 random draws, cadence only) | **WORKING ✓** | `render_lk_explorer.py` | Fixed: extra argument bug was preventing cadence_library from being found |

---

## Removed Graphs (backed up in Backups/)

D2-D3, D5b, D5c, D8, D11, D12, D13, A2 (old), A4, E5, D16 (folded into D15),
E8, E9, all K-S/CvM/weighted graphs

---

## Change Log

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
