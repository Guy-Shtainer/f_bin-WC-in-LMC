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

The best-fit (f_bin, π) is the grid point with the maximum K-S p-value
(equivalently, the minimum K-S D statistic).

**Error estimation:** 1D posteriors are obtained by marginalizing the K-S p-value
grid over all other dimensions. The mode of each marginalized posterior is the
reported best-fit value. Uncertainties are given as the 68% highest density
interval (HDI68), which is the shortest interval enclosing 68% of the posterior
probability — analogous to ±1σ for Gaussian distributions but correct for
asymmetric posteriors. Results are reported as: mode +Δ_upper −Δ_lower.

**Two period distribution models are tested:**
1. **Dsilva (power-law):** p(log P) ∝ (log P)^π, where π is a free parameter
   searched over the grid. This is the standard assumption from Dsilva et al. (2023).
2. **Langer+2020 (two-component mixture):** p(log P) = w_A · N(μ_A, σ_A) + (1−w_A) · LogNorm(μ_B, σ_B),
   where Case A is a Gaussian in logP (short-period RLOF, μ_A=0.80, σ_A=0.15) and
   Case B is a log-normal in logP space (wide-orbit, mode μ_B=2.0, σ_B=0.2,
   right-skewed to match Langer+2020 Fig. 6). Default weight w_A=0.20 (Case B
   dominates ~80%). Circular orbits (e=0), Gaussian q (μ=0.7, σ=0.2).

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

### 2026-03-01 (cont.) — Infrastructure: error system, documentation, to-do improvements

**What was done:**
- Created `COMMON_ERRORS.md` documenting 4 known pitfalls (E001–E004) with
  grep-ready regex patterns for automated pre/post-edit scanning.
- Fixed `np.trapz` → `np.trapezoid` across 4 files (CCF.py, CCF-old.py,
  wr_bias_simulation.py, 05_bias_correction.py) — numpy 2.x deprecation.
- Restructured `DOCUMENTATION.md` with Section 7 (Work Log) containing
  dated daily entries for each working session. Backfilled 3 entries.
- Rewrote To-Do webapp page with Eisenhower matrix (2×2 urgent/important
  quadrants), inline editing for all task fields, and urgent/important
  boolean columns.
- Populated `TODO.md` with full project roadmap (22 open tasks) translated
  from `my_todo.md`, covering bias correction, NRES analysis, statistical
  modeling, Overleaf paper, plots, GUI fixes, and more.

**Decisions:**
- Plots will use matplotlib-style Plotly (white backgrounds, scientific fonts)
  rather than pure matplotlib — preserves interactivity while looking academic.
- Wavelength axes will use Angstrom throughout.
- Statistical RV modeling → separate page (`11_statistical_model.py`).
- Paper will use A&A (Astronomy & Astrophysics) journal format.

---

### 2026-03-09 — Bias correction improvements: descriptive filenames, summary errors, dynamic tabs

**What was done:**
- **Descriptive result filenames (Task 89):** Saved `.npz` result files now use
  parameter-encoding filenames instead of generic `dsilva_result.npz`. Format:
  `{model}_fb{min}-{max}x{steps}_{axis}{min}-{max}x{steps}_N{n_stars}_sig{value_or_range}_logP{min}-{max}_{YYMMDD-HHMM}.npz`.
  A load dropdown (popover with file preview) replaces the single-button load.
  Multiple results can coexist in `results/` for comparison.

- **Summary table with ±1σ errors (Task 90):** Rewrote the best-fit summary
  tables for both Dsilva and Langer models. Each row now shows the parameter name,
  best-fit value (argmax of K-S p), and the posterior mode ± 1σ (HDI68: highest
  density interval enclosing 68% of the marginalized 1D posterior). Parameters
  reported: f_bin, π (or σ_single for Langer), σ_measure (if scanned), logP_max
  (if scanned), and K-S p-value at the best-fit point. This is the standard
  reporting format following Dsilva et al. (2023).

- **Dynamic tab system:** Major refactoring of the bias correction page
  (`app/pages/05_bias_correction.py`, 4103 lines). Extracted Dsilva and Langer
  tab bodies into parameterized functions `_render_dsilva_tab(prefix)` and
  `_render_langer_tab(prefix)`, with all 114 session state keys parameterized
  by a unique prefix string. This allows multiple independent instances of the
  same model to run simultaneously with different settings. A "+" button adds
  new Dsilva, Langer, or Compare tabs at runtime.

- **Compare tab:** New `_render_compare_tab(prefix)` loads any two saved result
  files (from either model) and provides:
  - Parameter comparison table (side-by-side settings with match indicators)
  - K-S p-value heatmaps: side-by-side or contour overlay (Result A as heatmap,
    Result B as red contour lines)
  - 1D f_bin posteriors: side-by-side or overlaid on same axes
  - CDF comparison: observed distribution overlaid with both best-fit simulated CDFs

**Methodology notes for paper:**
- The HDI68 interval is computed by binary-searching for the horizontal threshold
  level h such that the set {x : posterior(x) ≥ h} has integrated probability = 0.68.
  This gives the shortest credible interval and handles asymmetric posteriors correctly.
  For symmetric, Gaussian-like posteriors, HDI68 ≈ mode ± 1σ.
- The comparison infrastructure enables systematic exploration of how results depend
  on model choices (Dsilva vs Langer period distributions), grid resolution, N_stars,
  and σ_single range. This is essential for the discussion section of the paper.
- Result files embed the full settings JSON, enabling reproducibility: any saved
  result can be traced back to the exact parameter configuration that produced it.

- **Langer 2020 period model refinements (Task 4):** Verified implementation
  against Langer et al. 2020 (A&A 638, A39) Figures 4 and 6. Key changes:
  - **Case B distribution:** Changed from Gaussian to **log-normal in logP space**
    to match the right-skewed tail in Langer Fig. 6. Internal implementation:
    `ln(logP) ~ Normal(μ_ln, σ_B)` where `μ_ln = ln(μ_B) + σ_B²`, ensuring
    the mode sits at exactly μ_B ≈ 2.0 (periods ~100 days). Default params:
    μ_A=0.80, σ_A=0.15 (Case A Gaussian); μ_B=2.0, σ_B=0.2 (Case B log-normal);
    weight_A=0.20 (Case B dominates ~80%).
  - **q mass-ratio flip toggle:** Added `q_flipped` boolean to `BinaryParameterConfig`.
    Default: q = M_companion/M_primary (BH as companion, M₂ = M₁ × q).
    Flipped: q = M_primary/M_companion (M₂ = M₁ / q). Langer Fig. 4 shows
    M_BH/M_OB peaks at ~0.5–0.7.
  - **Case A/B preset buttons:** Three convenience presets in the Langer tab UI:
    "Case A only" (w_A=1.0), "Case B only" (w_A=0.0), "Both (Langer)" (w_A=0.20).
  - **Cache fix:** `_find_reusable_fbin_langer()` now checks `q_preset`,
    `q_flipped`, and `langer_period_params` — previously missing, causing false
    cache hits when switching between q presets or Case A/B weights.
  - **Descriptive filename tags:** Langer result files now include case suffix:
    `_caseA` (w_A=1.0), `_caseB` (w_A=0.0), or `_wA{value}` (custom weight).

- **NRES analysis page:** New `app/pages/11_nres_analysis.py` for NRES
  spectroscopy CCF processing. Worker functions extracted to
  `app/nres_ccf_worker.py` to enable `multiprocessing.Pool` (Streamlit pages
  can't pickle functions defined in `__main__` — see E022).

**Simulation runs performed (Langer model):**
- Case A only (w_A=1.0): `langer_..._260309-1751_caseA.npz`
- Case A+B mixed (w_A=0.30): three runs at 20:09, 20:16, 20:27
- Various sigma ranges tested: σ ∈ [1.0, 9.0] and [3.0, 13.0]
- All runs: 100×100 grid, N=10,000 stars, logP ∈ [0.5, 3.5]

**Bugs found and fixed:**
- **E020:** Missing `title` argument to `_make_heatmap_fig()` in compare tab.
- **E021:** Dict comprehension variable `p` shadowed function parameter `prefix`
  in `_render_compare_tab()`, breaking all session state key lookups.
- **E022:** `multiprocessing.Pool` can't pickle functions defined in Streamlit
  pages (running as `__main__`). Fix: move workers to separate importable module.
- **E023:** `@st.cache_data` silently ignores underscore-prefixed parameters
  from cache key — `_star_name` meant all stars returned WR 52's cached data.
- **E024:** Cache reuse function missing checks for newly added config fields
  (`q_preset`, `q_flipped`, `langer_period_params`), causing stale results.

**Decisions:**
- Settings save to `user_settings.json` only from the primary tabs (prefix `bc`
  for Dsilva, `lg` for Langer). Duplicate tabs created via "+" are session-only
  and do not persist settings across restarts.
- The compare tab auto-discovers all `.npz` files in `results/` matching either
  model prefix, sorted by modification time (newest first).
- Case B log-normal distribution chosen over Gaussian because Langer+2020 Fig. 6
  shows a clear right-skewed tail for Case B periods — a symmetric Gaussian
  underestimates the long-period tail.

**Open questions:**
- What are the best-fit corrected f_bin values from the Langer model runs?
  Need to extract and compare with Dsilva model results.
- Does the Case A/B weight significantly affect the corrected binary fraction?
  Preliminary runs suggest moderate sensitivity — need systematic comparison.

---

### 2026-03-10 — Meeting 41 with Tomer: cadence-aware simulation, binned CDF, error propagation

**Meeting with Tomer (41st):**

Tomer reviewed the Dsilva and Langer bias correction results. Six methodological
improvements were agreed upon, several of which represent fundamental changes to the
simulation framework. These are documented below in order of scientific impact.

**1. Cadence-aware grouped simulation (replaces independent-star approach):**

The current simulation draws N_stars=10,000 independent stars, each randomly
assigned a cadence from the 25-star library. Tomer's key insight: simulate in
**sets** of 25 stars, where each set contains exactly one simulated star per
real star in the sample, using that star's actual observation cadence (MJD
timestamps). Run N_sets (user-configurable, default 10k) of these grouped sets,
yielding 25 × N_sets = 250,000 total simulated stars.

This change is important because:
- It preserves the exact sample structure — each simulated "survey" mirrors
  the real one (same number of stars, same cadences, same epoch counts).
- It enables proper uncertainty quantification on the simulated CDF: across
  the N_sets realizations, compute the **median** binary fraction in each ΔRV
  bin, and the **68% posterior width** as a shaded error band.
- The K-S score is then computed against the median CDF, **weighted by the
  per-bin standard deviation** — giving less weight to bins where the
  simulation outcome is uncertain.

For the paper: this is the "cadence-matched Monte-Carlo" method. It should be
described in Section 4 (Bias Correction) as the primary simulation approach,
contrasted with the simpler independent-star method used in Dsilva et al. (2023).

**2. Binned CDF (replaces raw-value CDF):**

Instead of constructing the CDF from raw ΔRV values, discretize into a regular
grid with ~10 km/s bins, ending at ~350 km/s. This:
- Regularizes the CDF comparison (avoids noise from sparse high-RV tails).
- Aligns with the CDF truncation idea from meeting 40 (#1 in TODO).
- Makes the per-bin median and standard deviation from the grouped simulation
  well-defined.

**3. RV measurement errors in the observed CDF:**

The observed CDF currently treats each measured ΔRV as exact. Tomer raised the
question of how to propagate RV measurement uncertainties — options include
binomial confidence intervals on the observed fraction per bin, or Monte-Carlo
resampling of ΔRV within the measurement error bars. If incorporated, these
errors could serve as weights in the K-S comparison. This is a **research item**
— needs theoretical work before implementation.

**4. Langer model: direct distribution sampling:**

Instead of parametric fits (Gaussian + log-normal) for the Langer period and
mass-ratio distributions, directly sample from the full distributions shown in
Langer et al. (2020) Fig. 6 (logP) and Fig. 4 (q). This requires digitizing
the histogram from the published figure. The advantage: no parametric assumptions
beyond what the evolutionary models already encode.

**5. Marginalized posterior σ_single handling:**

Tomer flagged a potential issue: the posterior summary may display the
last-computed σ_single slice rather than the true best-fit across all σ values.
Additionally, the marginalization over σ_single may implicitly assume a flat
prior on σ_single rather than weighting by the K-S p-value. Both the GUI
behaviour and the mathematical marginalization need verification. Related to
the HDI68 computation in `compute_hdi68()`.

**6. NRES validation + per-epoch STD diagnostic:**

The NRES-derived RVs need independent validation. A per-epoch STD plot (showing
the scatter of RV measurements within each epoch) would reveal outlier epochs or
instrumental systematics. This feeds into the ΔRV threshold determination from
the NRES sample (task #51).

**Scientific context for the paper:**

Items 1–3 together represent a significant methodological advance over the
Dsilva et al. (2023) approach:
- **Dsilva (2023):** Independent stars, raw CDF, error-free observed CDF.
- **This work (after implementation):** Cadence-matched grouped sets with
  uncertainty bands, binned CDF, potential error propagation.

This should be highlighted in both the Methods section and the Discussion as a
strength of this analysis compared to the prior work.

---

### 2026-03-11 — Bias correction page: flicker fix, Langer cadence display correction

**What was done:**
- Diagnosed and fixed the live heatmap UI flicker during bias correction simulations.
  Root cause: a global `@st.fragment(run_every=3)` was calling `st.rerun(scope='app')`
  every 3 seconds, triggering a full page rerun that cleared all `st.empty()` slots
  before re-populating them. Fix: replaced with per-tab `@st.fragment(run_every=3)`
  functions that render live elements (progress bar, heatmap, status text) directly
  inside the fragment — only the fragment's content re-renders, not the full page.
- Fixed the Langer cadence-aware live heatmap display: was showing f_bin vs π (π always
  0.0 for Langer), now correctly shows f_bin vs σ_single when sigma scan is active.
  The 3D array `ks_p[n_sig, n_fb, n_pi=1]` is reshaped to `(n_fb, n_sig)` by squeezing
  the pi dimension and transposing.
- Fixed `np.empty()` → `np.full(..., np.nan)` in the cadence-aware background runner,
  preventing garbage values in uncomputed grid cells from corrupting `max()` / `argmax()`
  calculations during live updates.

**Methodology notes:**
- Also investigated the observed slowdown in grid point completion rate: higher f_bin
  values require more binary systems to be simulated (more Kepler equation solving via
  Newton-Raphson), so tasks with high f_bin are inherently slower. This is not a bug —
  it is an expected consequence of the physics simulation cost scaling with binary fraction.

**Bugs found and fixed:**
- E026: `st.rerun(scope='app')` inside polling fragment causes full-page flicker
- E027: `np.empty()` leaves garbage values in accumulation arrays

---

*Last updated: 2026-03-11*
