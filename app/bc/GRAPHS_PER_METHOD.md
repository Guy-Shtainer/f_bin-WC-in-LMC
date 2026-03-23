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

---

## Rendering Order (top to bottom as user sees it)

### Shared Section (`render_shared.py` → `render_model_subtabs()`)

| ID | Graph | Status | File | Comment |
|----|-------|--------|------|---------|
| A1 | Summary Table (best-fit + 68% HDI) | MODIFY | `render_shared.py` | Rename from "Scoring Method Comparison" to "Summary Table". Check if D15 duplicates — if so remove A1 |
| ~~A2~~ | ~~CDF Comparison~~ | REMOVE | | Redundant with E5 |
| A3 | Max Likelihood vs σ/logPmax | MODIFY | `render_shared.py` | If ONLY σ grid → 1D line (σ on x). If ONLY logPmax → 1D line (logPmax on x). If BOTH → 2D heatmap (σ × logPmax). This drives which slice D1 shows |
| ~~A4~~ | ~~Period Distribution Histogram~~ | REMOVE | | Already present inside A6 orbital histograms |
| A5 | Binary Fraction vs ΔRV Threshold | KEEP | `render_shared.py` | Gap analysis with observed f(T), intrinsic line, missed area |
| A6 | Orbital Histograms (9-panel) | KEEP | `render_shared.py` | log₁₀P, e, q, K₁, M₁, M₂, i, ω, T₀ with radio selector |
| A7 | Methodology Equations (LaTeX) | KEEP | `render_shared.py` | Kepler equation, RV curve, binary criterion |

### Live Run Section (`polling.py`)

| ID | Graph | Status | File | Comment |
|----|-------|--------|------|---------|
| B1 | Live Heatmap | MODIFY | `polling.py` | Single likelihood tile (not 4-method 2×2 grid). Show f_bin×π heatmap |
| B2 | Live σ/logPmax Profile | MODIFY | `polling.py` | Follow A3 style: 1D or 2D depending on grid axes |

### Likelihood Analysis (`render_lk.py` → `render_lk_scoring.py`)

| ID | Graph | Status | File | Comment |
|----|-------|--------|------|---------|
| D1 | Primary Heatmap — f_bin×π | MODIFY | `render_lk.py` | (1) Fix "p-value" sidebar → "Likelihood", (2) LaTeX for f_bin and π axes, (3) Show slice at best σ & logPmax from A3 heatmap max |
| ~~D2-D3~~ | ~~Extra Heatmaps (f_bin×logPmax, σ×logPmax)~~ | REMOVE | | Covered by A3 upgrade |
| D4 | Best-Fit Metric Cards | KEEP | `render_lk.py` | Show global best + current slice. Add logPmax slider below σ slider |
| D5a | Raw logL Heatmap | MODIFY | `render_lk_scoring.py` | LEFT panel: f_bin×π raw logL. RIGHT panel: σ×logPmax max-likelihood (if both grids exist, 1D if one, nothing if neither) |
| ~~D5b~~ | ~~Score-Masked Heatmap~~ | REMOVE | | |
| ~~D5c~~ | ~~Normalized Likelihood Heatmap~~ | REMOVE | | |
| D9 | 1D Slices (parabolic fit + HDI) | MODIFY | `render_lk_scoring.py` | Use LaTeX labels. Change slice factor minimum from 1.1 to 1.01 |
| D10 | 3D Parabolic Surface | KEEP | `render_lk_scoring.py` | Conditional: only if 2D fit succeeds |
| D11 | 3D Projections (full N-D fit) | BUILD | `render_lk_scoring.py` | Default: find best σ/logPmax from grid, fit f_bin×π. Optional checkbox: full 4D quadratic fit |
| ~~D12~~ | ~~Score vs σ Profile~~ | REMOVE | | Covered by A3 |
| ~~D13~~ | ~~Score vs logPmax Profile~~ | REMOVE | | Covered by A3 |
| D14 | Corner Plot (N×N marginals) | KEEP | `render_lk_fit.py` | Add caption: gold star = joint max (argmax of full N-D), not marginal mode. This is standard — joint max ≠ marginal mode |
| D15 | Summary Table | MODIFY | `render_lk.py` | Add interpolation results column. Add re-run feature: re-simulate at interpolated best-fit with user-chosen # of star sets |

### Likelihood Extras (`render_lk_fit.py` → called from `render_lk_scoring.py`)

| ID | Graph | Status | File | Comment |
|----|-------|--------|------|---------|
| E5 | Likelihood CDF with Bin Overlay | MODIFY | `render_lk_fit.py` | Repurpose: show algorithm's best-fit CDF + overlay with Model Explorer sliders CDF for interactive comparison |
| E6 | Per-Bin Breakdown Table | **WORKING ✓** | `render_lk_fit.py` | DO NOT TOUCH. Shows bin label, n_obs, n_sim, p_i, ln(p_i), n_i·ln(p_i) |
| E7 | LaTeX Methodology Explainer | **WORKING ✓** | `render_lk_fit.py` | DO NOT TOUCH. Raw formula + normalization + flat surface discussion |

### Interactive (`render_lk_explorer.py`)

| ID | Graph | Status | File | Comment |
|----|-------|--------|------|---------|
| D16 | Re-sim CDF at Interpolated Best-Fit | BUILD | `render_lk_explorer.py` | Wire into render_lk.py after interpolation. Guard: only if interpolation results exist |
| D17 | Model Explorer (sliders → CDF + histogram + det fraction + score) | MODIFY | `render_lk_explorer.py` | (1) Bins toggle must use scoring method bins (likelihood_bin_edges), not unrelated bins. (2) Binary fraction chart must match A5 style/data |
| D18 | CDF Sanity Check (5 random draws, cadence only) | KEEP | `render_lk_explorer.py` | Cadence-only. Verify cadence_library injection works |

---

## Removed Graphs (backed up in Backups/)

D2-D3, D5b, D5c, D8 (S_raw, KS-only), D12, D13, A2, A4,
E8 (corner plot was marked "not rendered" for LK — now D14 renders it),
E9 (S_raw, KS-only), all K-S/CvM/weighted graphs

---

## Session Plan

### Session 1: Documentation + Quick Fixes
- [x] Backup + rewrite this file
- [ ] Update FEATURES.md
- [ ] D9: slice factor 1.01, LaTeX
- [ ] D1: fix labels, LaTeX axes
- [ ] D14: add caption
- [ ] Remove: A2, A4, D2-D3, D5b, D5c, D12, D13

### Session 2: Structural Changes
- [ ] A3: 1D/2D upgrade
- [ ] D5a: dual panel
- [ ] D4: logPmax slider
- [ ] D17: bins + binary fraction fixes
- [ ] B1: single tile

### Session 3: Advanced Features
- [ ] Wire D16
- [ ] D11: 4D optional fit
- [ ] D15: interpolation + re-run
- [ ] E5: repurpose as comparison
- [ ] A1: resolve D15 duplicate

### Session 4: Testing
- [ ] Mock data recovery test
- [ ] End-to-end smoke test
- [ ] Flag all approved graphs with `# ── WORKING` guards
