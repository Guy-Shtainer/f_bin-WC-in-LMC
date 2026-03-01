# Scientific Documentation

This file records the methodology, decisions, and key results for the
WC-type Wolf-Rayet binary fraction analysis in the LMC, intended as
reference material for the Masters thesis.

---

## 1. Sample and Observations

We analyse 25 apparently single WC-type Wolf-Rayet stars in the Large
Magellanic Cloud, drawn from the Bartzakos (2001) survey of 28 WC LMC
stars. Three stars from that survey were already confirmed as spectroscopic
binaries by Bartzakos (2001) and are excluded from the RV analysis but
included in the final binary fraction denominator (N = 28).

Multi-epoch spectroscopy was obtained with VLT/X-SHOOTER, covering three
spectral arms: UVB (~300–560 nm), VIS (~560–1020 nm), and NIR (~1020–2480 nm).
Additional observations for a subset of stars come from NRES.

Observation times (MJD) are extracted from the FITS header keyword `MJD-OBS`.
Typical baselines span several years with 3–8 epochs per star.

### Star List (25 targets)

Brey 70, Brey 83, HD 38029, HD 37248, Brey 95a, MNM2014 LMC195-1,
HD 32125, HD 37026, HD 269818, HD 38448, HD 38030, HD 37680, Brey 58a,
HD 32228, HD 32257, HD 269888, HD 36156, H2013 LMCe 584, RMC 140,
HD 32402, Brey 70a, Brey 16a, Brey 93, Brey 90a, HD 269891.

---

## 2. Radial Velocity Measurement

Radial velocities are measured via Cross-Correlation Function (CCF) analysis
following the prescriptions of Zucker & Mazeh (1994) and Zucker et al. (2003).

For each epoch and each emission line, the observed spectrum is cross-correlated
against a template (a high-S/N reference epoch of the same star). The CCF peak
position gives the relative RV shift, and the peak curvature gives the formal
uncertainty σ_RV.

### Emission Lines Used

Eleven WR wind emission lines are defined in the CCF configuration, spanning
the full X-SHOOTER wavelength range:

| Line                        | Range (nm)      |
|-----------------------------|-----------------|
| O V 3100-3175               | 310.0 – 317.5   |
| O IV 3350-3480              | 335.0 – 348.0   |
| C IV 3650-3900              | 365.0 – 390.0   |
| He II 4686                  | 456.0 – 480.0   |
| O VI 5210-5340              | 521.0 – 533.5   |
| He II 5412 & C IV 5471      | 535.0 – 554.0   |
| **C IV 5808-5812**          | 570.0 – 588.0   |
| C III 6700-6800             | 666.5 – 684.0   |
| C IV 7063                   | 697.0 – 714.0   |
| C IV 17396                  | 1710.0 – 1763.0 |
| C IV 20842                  | 2050.0 – 2100.0 |

Per-star and per-epoch overrides (skipped lines, fit-fraction adjustments)
are stored in `ccf_settings_with_global_lines.json`.

---

## 3. Binary Classification

A star is classified as a spectroscopic binary if **both** of the following
criteria are satisfied:

1. **RV separation criterion:** ΔRV > 45.5 km/s, where ΔRV is the peak-to-peak
   radial velocity difference between the epoch pair with maximum separation.

2. **Significance criterion:** ΔRV − 4σ > 0, where σ is the combined formal
   uncertainty of the two epochs (quadrature sum).

The classification uses a single emission line: **C IV 5808-5812** (the
strongest and most reliably measured WC wind line).

### Classification Procedure

- **Stage 1:** Evaluate the max-separation epoch pair (the pair with the
  largest |RV_i − RV_j|). If both criteria are met, classify as binary.
- **Stage 2:** If Stage 1 fails, scan all remaining epoch pairs. If any
  pair satisfies both criteria, classify as binary.

### Result

- 10 out of 25 apparently-single stars detected as binary
- Plus 3 previously known binaries from Bartzakos (2001)
- **Total observed binary fraction: 13/28 ≈ 46%**

---

## 4. Bias Correction via Monte-Carlo Simulation

The observed binary fraction is a lower limit because binaries with
unfavourable orbital geometry (long periods, low inclinations, low RV
semi-amplitudes) can escape detection. We correct for this observational
bias using a Monte-Carlo simulation framework following Dsilva et al. (2023).

### Simulation Method

For each grid point in (f_bin, π) parameter space:

1. Simulate N_stars = 10,000 WR systems.
2. Assign each system as binary (probability f_bin) or single.
3. For binaries, draw orbital parameters from specified distributions:
   - **Period:** p(log P) ∝ (log P)^π (power-law; Dsilva model) or
     mixture of two Gaussians (Langer+2020 model for OB+BH systems).
     Range: log P ∈ [0.15, 5.0].
   - **Eccentricity:** Uniform on [0, e_max=0.9] (Dsilva) or circular (Langer).
   - **Mass ratio:** q = M₂/M₁ ∼ U[0.1, 2.0] (flat) or Gaussian with
     μ=0.7, σ=0.2 clipped to [0.25, 1.75] (Langer).
   - **Inclination:** p(i) ∝ sin(i) on [0, π/2] (isotropic).
   - **Primary mass:** M₁ = 10 M⊙ (fixed) or U[10, 20] M⊙.
4. Compute the RV semi-amplitude K₁ from Kepler's third law:
   K₁ = [(2πG)/P]^(1/3) × (M₂ sin i) / (M₁+M₂)^(2/3) / √(1−e²)
5. Draw random orbital phases, solve Kepler's equation numerically, and
   compute the RV at each observed epoch using the real cadence library
   (MJD timestamps from the 25 target stars).
6. Add Gaussian noise: σ_single (intrinsic WR wind variability, ~15 km/s)
   for all stars, plus σ_measure (~5 km/s) per epoch.
7. Compute the peak-to-peak ΔRV for each simulated star.
8. Compare the simulated ΔRV cumulative distribution to the observed one
   via the Kolmogorov-Smirnov test.

The best-fit (f_bin, π) is the grid point with the minimum K-S D statistic.
The K-S p-value provides a goodness-of-fit assessment.

### Cadence Library

Rather than assuming uniform epoch spacing, the simulation uses the actual
observation cadences of all 25 stars. Each simulated star is randomly
assigned a real cadence (set of MJD timestamps), optionally weighted by
the number of epochs. This preserves the real temporal sampling, including
gaps and clustering.

### Grid Search

The simulation scans a 2D grid:
- f_bin: intrinsic binary fraction (typically 0.3–1.0 in steps of 0.005–0.01)
- π: period distribution power-law exponent (typically −3 to +1)

All grid points are evaluated in parallel using Python multiprocessing
(os.cpu_count() − 1 cores). Results are stored as `.npz` files with an
embedded `config_hash` to enable caching and avoid redundant computation.

### Diagnostic Plots

The bias correction page of the Streamlit webapp provides:

- **Heatmap:** K-S D statistic over the (f_bin, π) grid, with contour
  lines and a gold star at the best-fit point.
- **CDF comparison:** Observed vs simulated ΔRV cumulative distributions
  at the best-fit model.
- **Period distribution:** Histogram of simulated orbital periods, split
  into detected (red) and missed (amber) binaries.
- **Binary fraction vs threshold:** Observed binary fraction as a function
  of ΔRV threshold, with the intrinsic f_bin shown as a horizontal reference
  line. Shaded regions show missed binaries (below threshold) and singles
  scattered above threshold.
- **Orbital properties of missed binaries:** Five-panel histogram showing
  period, eccentricity, mass ratio, K₁, and inclination distributions for
  detected vs missed binaries. Missed systems are typically long-period,
  low-inclination, or low-K₁.

---

## 5. Key Numbers and Thresholds

| Quantity                   | Value          | Source / Notes                        |
|----------------------------|----------------|---------------------------------------|
| Sample size                | 25 (+ 3 known) | Bartzakos (2001)                     |
| ΔRV threshold              | 45.5 km/s      | Binary detection criterion            |
| Significance level          | 4σ             | Combined epoch-pair error             |
| Binary line                | C IV 5808-5812 | Strongest WC wind line                |
| Detected binaries          | 10/25          | This work                             |
| Total binary fraction      | 13/28 ≈ 46%   | Including 3 Bartzakos binaries        |
| σ_single (wind variability) | ~15 km/s       | Intrinsic WR RV scatter              |
| σ_measure (per-epoch)       | ~5 km/s        | Formal CCF uncertainty               |
| N_stars per simulation      | 10,000         | Monte-Carlo sample size              |
| Period range (log P)        | [0.15, 5.0]    | Days; power-law distribution         |
| Eccentricity range          | [0, 0.9]       | Uniform (Dsilva model)               |
| Mass ratio range            | [0.1, 2.0]     | Flat prior (Dsilva model)            |

---

## 6. References

- Bartzakos, P., Moffat, A. F. J., & Niemela, V. S. 2001, MNRAS, 324, 18 —
  Original survey of 28 WC stars in the LMC.
- Dsilva, K., et al. 2023 — Binary fraction bias correction methodology
  (power-law period model, Monte-Carlo simulation framework).
- Langer, N., et al. 2020 — Alternative period distribution model for OB+BH
  systems (two-Gaussian mixture representing Case A and Case B mass transfer).
- Zucker, S., & Mazeh, T. 1994, ApJ, 420, 806 — CCF methodology.
- Zucker, S., et al. 2003, MNRAS, 342, 1291 — Multi-order CCF formalism.

---

## 7. Work Log

Daily summaries of work sessions — what was done, key results, decisions,
and open questions. Written for thesis reference.

---

### 2026-02-25 — Webapp creation, bias correction page, performance fixes

**What was done:**
- Created the Streamlit webapp (`app/`) with 9 pages: Stars, Spectrum, CCF,
  Classification, Bias Correction, Plots, Tables, Results, Settings.
- Built `app/pages/05_bias_correction.py` — the main bias correction interface
  with live-filling heatmap, sigma scan support, and animated 4D visualization.
- Created `pipeline/load_observations.py` and `pipeline/dsilva_grid.py` as
  standalone CLI scripts that can also be called from the webapp.
- Parallelised 25-star data loading with `ThreadPoolExecutor` (was sequential).
- Removed automatic SIMBAD API calls from Star/NRES `__init__` (caused startup
  latency and network errors).
- Added preload system in `app.py` to warm all `st.cache_data` caches at session
  start — eliminates disk I/O on page navigation.
- Fixed `settings_hash` to only hash classification-relevant keys (`primary_line`,
  `classification`) so that navigating between pages does not invalidate caches.

**Key results:**
- First full bias correction grid run completed via webapp. K-S heatmap renders
  correctly with live updates during computation.
- Observed binary fraction: 13/28 = 46% (10 detected + 3 Bartzakos).

**Decisions:**
- All original files remain in project root (no restructuring) to avoid import
  breakage. New code goes in `pipeline/` and `app/`.
- Used persistent `multiprocessing.Pool` with `imap_unordered` for the grid
  computation (avoids Pool creation overhead per row).
- Settings stored as JSON (`settings/user_settings.json`) with immediate
  persistence — no "Save" buttons.

**Bugs found and fixed:**
- `numpy.bool_` identity comparison (`is True` fails) — cast with `bool()`.
- Negative default for `sigma_single` caused silent errors in grid computation.
- Pool overhead from re-creating per f_bin row — switched to persistent Pool.
- Variable scoping issue in nested sigma scan loop.
- Missing zero-filter on RV arrays (epochs with no data stored as 0.0).

---

### 2026-02-26 — GitHub repo setup, heatmap bug fix (interrupted)

**What was done:**
- Created public GitHub repository `f_bin-WC-in-LMC` and pushed full codebase.
- Fixed `StreamlitDuplicateElementKey` error in the bias correction heatmap —
  the live-update path and the post-run display path both called
  `plotly_chart()` with the same key in one script run. Fix: guard the display
  path with `if not run_btn:`.
- Added code quality rules to `CLAUDE.md`: commit-per-change workflow, backup
  before editing app pages.

**Decisions:**
- `.gitignore` excludes `Data/`, `Backups/`, `__pycache__/`, `.DS_Store`,
  `.idea/`, `*.log` — keeps repo clean of large data and IDE artifacts.

**Session interrupted** — context window exhausted before completing all planned
work.

---

### 2026-03-01 — Meeting 40 with Tomer: marginalization, histograms, infrastructure

**Meeting with Tomer (40th):**
- Tomer requested error bars on f_bin, π, σ_single using the K-S p-value grid.
  Method: marginalize to 1D posteriors by summing over other dimensions,
  normalize, find mode and 68% HDI (highest density interval) using the
  horizontal-line method from Dsilva et al. (2023).
- Requested corner plot: diagonal = 1D posteriors with mode + HDI68 shaded;
  off-diagonal = 2D marginalized heatmaps.
- Requested expanding orbital parameter histograms to include all binary
  parameters (M₂, ω, T₀) and a toggle to view all binaries combined.
- Discussed CDF truncation at ~350 km/s where observation gaps begin —
  **deferred** for now, needs more thought.
- Discussed 2D parameter histograms (e.g., P vs e) — **research only**, will
  confirm with Tomer if scientifically useful before implementing.

**What was done:**
- Implemented `compute_hdi68()` in `wr_bias_simulation.py` — marginalizes 3D
  K-S p-value grid to 1D posteriors, finds mode and 68% HDI via binary search
  on a horizontal threshold line.
- Added corner plot to bias correction page using Plotly `make_subplots`:
  diagonal shows 1D posteriors with mode (dashed red) and HDI68 (shaded green);
  off-diagonal shows 2D marginalized heatmaps.
- Expanded orbital histograms from 5 to 9 panels (3×3 layout): log₁₀(P), e,
  q, K₁, M₁, M₂, i, ω, T₀. Added "All binaries (combined)" toggle.
- Added ω (argument of periapsis) and T₀ (periastron phase) to the
  `simulate_with_params()` return dict — previously computed but discarded.
- Verified K-S test scoring: `argmax(ks_p)` correctly finds the highest p-value
  (best model fit). The `scipy.stats.ks_2samp` implementation with manual
  fallback is correct.
- Verified q = M₂/M₁ definition in `BinaryParameterConfig` — confirmed as
  companion mass / primary WR star mass.
- Created project infrastructure: `GIT_LOG.md` (changelog), `TODO.md` (task
  tracker), `app/pages/10_todo.py` (webapp to-do page), auto-triggered skills
  for git-workflow and todo-manager.
- Created `COMMON_ERRORS.md` documenting 4 known pitfalls with grep-ready
  regex patterns. Added error-checker skill for automated scanning.
- Fixed `np.trapz` → `np.trapezoid` across 4 files (numpy 2.x deprecation).

**Key results:**
- Best-fit values now reported with HDI68 errors:
  f_bin = mode +upper/−lower, π = mode +upper/−lower, σ_single = mode +upper/−lower.
- Corner plot provides visual confirmation that posteriors are well-behaved
  (single-peaked, reasonable widths).

**Decisions:**
- Used horizontal-line method for HDI68 (not equal-tailed intervals) — this is
  the standard for asymmetric posteriors and matches Dsilva et al. (2023).
- Layout for orbital histograms: 3×3 grid (9 panels) rather than 2×4+1 —
  cleaner visual arrangement.
- T₀ displayed in radians (raw orbital phase), ω converted to degrees.

**Open questions:**
- CDF truncation at 350 km/s — would this improve the K-S fit? Need to test.
- logP_max = 4 vs 5 — does extending the period range matter?
- Langer 2020 period model — needs implementation (pipeline/langer_grid.py).
- Are 2D parameter histograms (P vs e, q vs i) scientifically informative?

---

*Last updated: 2026-03-01*
