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

*Last updated: 2026-02-26*
