# Meeting Prep: Tomer Meeting — 2026-03-19

## Context
Since last meeting, the main focus has been on **finding the right scoring method** for the bias correction Monte-Carlo simulation, and improving the webapp infrastructure. You went through a journey of trial and error with statistical methods, which is worth walking Tomer through.

---

## 1. The Scoring Method Journey (main discussion topic)

### Step 1: K-S Test — Started here
- **Assumption**: K-S p-value ranks models — highest p-value = best model
- **Problem**: p-value is NOT the right metric for choosing the best model. K-S p-value answers "can we reject this model?" not "which model fits best"
- Also tried **weighted K-S** (inverse-variance weighting per CDF bin by 1/sigma^2) — the weighted D values collapsed to ~0.01-0.05 (vs standard ~0.2-0.3), making Kolmogorov p-values flatten to ~1.0 everywhere. Scores were orders of magnitude apart. **Ditched it.**

### Step 2: Cramer-von Mises (CvM)
- Uses ALL CDF bins (not just max deviation like K-S)
- S = sum of (F_obs - F_sim_median)^2 / sigma^2
- **Works well for ranking** — clear minima in (f_bin, pi) space
- **Problem discovered**: S-score is normalized per sigma_single, so you **cannot compare** CvM scores between Dsilva and Langer period models directly
- **Solution**: Also compute S_raw (unweighted) — this IS cross-model comparable
- Empirical p-value (from 10k simulations) is ~0 everywhere (test too sensitive for N=25 stars) — confirms p-value shouldn't be the selection metric

### Step 3: Likelihood (Dsilva+2023 approach)
- Realized Dsilva et al. 2023 used **binned multinomial likelihood**, not p-value
- Formula: ln L = sum( n_i * ln(p_i) ) — coarse bins [0, 45.5, 250, 650, inf] km/s
- **Major difficulty**: likelihood showed NO dependence on sigma_single, and always gave f_bin ~ 1.0
- **Root cause found (Task #140)**: binary RVs had zero measurement noise — face-on binaries (sin i ~ 0) had exactly deltaRV = 0, making f_bin=1 cost-free in likelihood
- **Fix**: added per-epoch measurement noise model (7 distribution types) for both singles and binaries
- **Insight**: sigma_single insensitivity is actually **correct** — Dsilva doesn't model sigma_single at all. Singles have deltaRV=0 with wind variability absorbed by the threshold (C=50 km/s, ~3x the observed ~15 km/s)
- **Remaining issue**: f_bin=1 degeneracy is a real methodological limitation of coarse binning — Dsilva breaks it with period-bin priors (enforcing known orbital periods)

### Current state: 4 methods computed in parallel (K-S, weighted K-S, CvM, likelihood)
- K-S: flat heatmap (not useful)
- CvM: shows structure, good for ranking within a model
- Likelihood: shows structure after error model fix, matches Dsilva methodology
- S_raw (unweighted CvM): for cross-model comparison (Dsilva vs Langer)

---

## 2. Error Distributions
- Implemented per-epoch measurement noise: 7 distribution types (Fixed, Normal, Log-normal, Gamma, Weibull, Exponential, Uniform)
- Separate error models for singles vs binaries
- This was needed to fix the likelihood degeneracy AND is scientifically correct
- **Question for Tomer**: What error distribution is appropriate? Fixed sigma from CCF? Empirically measured per-epoch errors? Something from the data?

---

## 3. Interpolation
- Replaced spline fitting (oscillated wildly on S-score landscape spanning 0 to 3M+)
- Now using **parabolic (quadratic) interpolation**: 2D (6 coefficients) and 3D (10 coefficients)
- Hessian positive-definite check to confirm true minimum (not maximum)
- 3 selection modes: height-based, range-based, neighborhood (default +/-2 neighbors)
- Re-simulation at interpolated best-fit point with p-value validation

---

## 4. Cadence-Aware Simulation
- Each simulated "group" of 25 stars matches real MJD cadences
- Binned CDF comparison
- Multiple bug fixes in parameter propagation (wrong orbital params in diagnostics, shape mismatches)
- Live heatmap normalization fixed (was per-slice, now uses running global max)

---

## 5. RV Modeling Page (new)
- 6 tabs: Simulate Binary RVs, Model Fitting, Playground + 3 existing tabs
- Tab A: orbital simulation + distribution fitting (6 scipy dists, MLE, AIC/BIC, Q-Q)
- Tab B: two-component mixture model, parametric f_bin grid search
- Tab C: slider-based exploration with snapshots
- Configurable histogram binning (5 auto methods + manual)

---

## 6. Infrastructure Improvements (mention briefly)
- Split 4 files exceeding 1000+ lines into subpackages (bias correction was 9,977 lines!)
- 800-line limit enforced
- Runtime integration test suite (30 checks for app/bc/)
- Spectrum page: nm->A fix, model browser, O lines, multi-epoch overlay

---

## Open Questions for Tomer

1. **Scoring method**: Which should we use as the primary result? CvM (continuous, good ranking) vs Likelihood (matches Dsilva methodology, coarser but published)?
2. **f_bin=1 degeneracy**: Should we implement period-bin priors like Dsilva, or rely on CvM (continuous CDF) which doesn't have this degeneracy?
3. **Error model**: What distribution for measurement noise? Should we use the actual per-epoch CCF errors from the data?
4. **Finer likelihood bins**: Would adding bins within [0, 45.5] km/s help distinguish singles from undetected long-period binaries?
5. **Cross-model comparison**: Is S_raw (unweighted CvM) a valid metric for comparing Dsilva vs Langer period distributions?
6. **Paper methodology section**: Which approach(es) to present? All 4 methods as comparison, or pick one as primary?

---

## How to Present This

**Narrative arc**: "I went through 3 scoring methods, each teaching me something:
- K-S showed me p-value isn't for model selection
- CvM works for ranking but isn't cross-model comparable (normalized per sigma)
- Likelihood matches Dsilva but exposed a noise bug and a binning degeneracy
- Now I have all 4 running in parallel and need to decide which to use for the paper"

This is a good story of methodological exploration — Tomer will appreciate the depth.

---

## Additional Work You Might Forget to Mention

### Dsilva+23 Paper Deep Dive (today, 2026-03-19)
- Read Paper II (2022) and Paper III (2023) in full
- **Key finding**: Dsilva does NOT simulate singles — singles have ΔRV=0 exactly, wind variability absorbed by threshold C=50 km/s (3× observed ~15 km/s)
- This explains why sigma_single is insensitive in likelihood — it's correct behavior, not a bug
- Dsilva breaks f_bin=1 degeneracy with **period-bin priors** (enforcing known orbital periods)

### Three Failed Weighting Attempts (2026-03-13) — worth mentioning for methodology depth
1. **Weighted average D** → values ~0.01-0.05, Kolmogorov p-value ~1.0 everywhere
2. **Weighted max D** → nearly identical to standard K-S (max-diff bin also has low variance)
3. **Chi-squared (diff²/σ²)** → σ² from 10k repetitions was ~10⁻⁴, making χ² values ~10⁴⁴ (absurdly sensitive)

### Adaptive CDF Bins (2026-03-16)
- Implemented classical CvM approach: CDF evaluation at observed ΔRV order statistics
- 25 observed stars → 17 unique bins (merged when <1 km/s apart)
- Toggle in UI for adaptive vs fixed 10 km/s bins

### N-Result Comparison Tab (2026-03-16)
- Upgraded from comparing exactly 2 results to any N≥2
- Transposed table (results as rows), overlaid CDF curves with 10 distinct colors
- Can now compare Dsilva vs Langer results side-by-side with different parameter grids

### Agent System Replacement (2026-03-15)
- Replaced 7,300-line overnight agent + 7-page webapp with ralph-loop plugin + /run-task command (~300 lines)
- Git worktree isolation so agent work doesn't destroy user's uncommitted changes

### Spectrum Page Improvements (2026-03-18)
- Fixed **critical wavelength bug**: .npz files store nm but page plotted with "Å" label (off by 10×)
- Added multi-epoch overlay with vertical offset stacking
- Added max-ΔRV epoch comparison: auto-finds the two epochs with largest separation for a given line
- Added 8 Oxygen diagnostic emission lines
- Added model browser (TLUSTY/POLLUX OB star models for WR+OB composite spectra)

### Cadence Diagnostic Histogram Bug (2026-03-12)
- **Critical**: diagnostic histograms were using wrong orbital parameters (rebuilt from session_state with wrong defaults instead of using the actual BinaryParameterConfig from the simulation)
- Missing: langer_period_params, q_flipped, wrong e_model default
- Fix: pass constructed bin_cfg object directly

### Error Pattern Analysis (2026-03-16)
- Analyzed 187 commits: ~47% productive, ~53% error correction
- Identified 9 cascading fix sequences (12.3% of commits)
- Created systematic error-check workflow (5-phase: static scan, cache cleanup, functional test, webapp smoke test, auto-learn)

### Partial Checkpoint System for Long Runs (2026-03-17)
- Cadence runs can take hours — now saves partial results to .npz checkpoints
- Resume from checkpoint with progress tracking (shows overall completion including pre-done cells)
- Parallel run collision guard (prevents starting 2nd run while one is active)

### Live Heatmap Updates During Simulation (2026-03-15-18)
- All 4 scoring method heatmaps update in real-time as simulation progresses
- Fixed normalization: was per-slice, now uses running global max across all completed slices
- Live 1D sigma graph shows score vs sigma_single during cadence runs

### TODO Task Count
- Tasks #119-#150 created and worked on during this period (~30 tasks)
- Most are in `to-test` status awaiting verification
