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

## 4b. Intrinsic RV Variability of Single WR Stars and Period Range Justification

The observed ΔRV of a single WR star is not zero: stochastic wind
clumping, corotating interaction regions (CIRs), and sub-surface
convection/pulsations all produce genuine radial velocity variations
unrelated to orbital motion. Understanding this intrinsic scatter is
essential for (i) setting the binary detection threshold and (ii)
modelling the single-star contribution in the bias-correction simulation.

### 4b.1 Wind-Induced RV Scatter by Subtype

The Dsilva et al. (2020–2023) spectroscopic multiplicity survey provides
the most systematic measurements of intrinsic wind variability (σ_w),
obtained from high-cadence monitoring of known single or very long-period
WR stars:

| Subtype | Proxy star | Line           | σ_w (km/s) | Peak-to-peak (km/s) | Source          |
|---------|-----------|----------------|------------|----------------------|-----------------|
| WC      | WR 137    | Full spectrum  | 1.6–6      | < 10                 | Dsilva+2020 (I)|
| WNE     | WR 138    | N V (weak)     | ~5         | ~15                  | Dsilva+2022 (II)|
| WNE     | WR 138    | He II / N IV   | ~10        | —                    | Dsilva+2022 (II)|
| WNL     | WR 136    | He II          | ~3–5       | —                    | Dsilva+2023 (III)|
| WNL     | WR 136    | N V λ4945      | ~15        | —                    | Dsilva+2023 (III)|

Key result: **WC stars exhibit systematically lower wind-induced RV scatter
than WN stars.** The Dsilva survey explicitly notes that "WNE stars exhibit
stronger line-profile variability" than WC stars (Paper II). This difference
drives the choice of detection threshold: C = 10 km/s for WC (Paper I)
versus C = 50 km/s = 3 × σ_w for WN (Papers II–III).

Additional measurements from the broader literature:

- **Schnurr et al. (2008):** 41 WNL stars in the LMC; 23 "constant" single
  stars show σ = 16 km/s on He II λ4686. Variability threshold set at
  σ_cut = 22.6 km/s (99.9% confidence).
- **Nazé et al. (2022):** WR 7 (WN4) shows peak-to-peak ~50 km/s over
  ~10 years, but erratic and non-orbital — attributed to simultaneous CIRs,
  pulsations, and stochastic clumping.
- **Koesterke et al. (2001):** WR 135 (WC8) and WR 111 (WC5) — C III λ5696
  LPV at the ~1% level with subpeaks migrating from line center to wings.
- **St-Louis et al. (2020):** WR 137 (WC7) — C III λ5696 shows only 0.4% rms
  variability, "remarkably low."
- **Kar et al. (2024):** WR 135 (WC8) — TESS detects high-frequency pulsations
  in He II and C IV emission lines.

### 4b.2 Line Dependence

Higher-ionization lines formed closer to the stellar surface show less
wind-induced scatter. Dsilva+2020 (Paper I) finds that "masks with ions of
higher ionisation state are least affected by wind variability." For WC
stars, C IV (the line used in our analysis) is among the least affected.
Shenar et al. (2019) explicitly warns that He II λ4686 "should be avoided
for RV measurements if possible because it is very susceptible to wind
variability."

Our choice of **C IV 5808–5812** is therefore optimal for minimising
intrinsic scatter in WC stars.

### 4b.3 Metallicity Effects on Wind Variability

The LMC has lower metallicity (Z ≈ 0.5 Z⊙) than the Galaxy. This affects
WR wind properties:

- **Crowther et al. (2002):** LMC WC4 stars have ~0.2 dex lower wind
  densities than Galactic WC5–8, with mass-loss scaling as Ṁ ∝ Z^(0.6±0.2).
- **Vink & de Koter (2005):** WC wind metallicity dependence is less steep
  than WN (Ṁ ∝ Z^0.86 for WC).
- **Sander & Vink (2020):** Theory-based mass-loss recipe confirms strong
  Eddington-Γ dependence at sub-solar Z.
- **Chené et al. (2020):** Faster winds (as found in lower-Z environments)
  show *lower* variability, counter to line-deshadowing instability (LDI)
  predictions.

Lower wind densities imply fewer and/or weaker clumps, suggesting that
**intrinsic RV scatter of LMC WC stars is likely equal to or lower than
that of Galactic WC stars.** The Galactic WC σ_w values of 0–6 km/s
therefore represent an upper bound for our LMC sample.

### 4b.4 Minimum RV Variability Floor

Can a single WR star have σ_RV ≈ 0? No:

**Observational evidence:**
- The lowest measured σ_RV for any single WR star is **1.8 km/s** (WR 3,
  WN3ha — the most compact subtype; Dsilva+2022).
- Typical single WR stars: σ_RV = 3–10 km/s (Dsilva+2020–2023).
- The measurement precision floor alone is ~1–3 km/s for high-S/N WR spectra.

**Theoretical predictions (Grassitelli et al. 2016):**
- Sub-surface convection in the iron opacity zone produces surface velocity
  fluctuations that seed wind clumping.
- M < 10 M⊙: convective velocities < 2 km/s (the theoretical floor).
- M ≥ 10 M⊙: ~10 km/s; M ~ 15 M⊙: up to ~20 km/s.
- Observational confirmation: variability amplitude increases linearly with
  mass above 10 M⊙ (correlation coefficient ~0.7).

**Practical floor:** σ_RV ≈ 2–3 km/s, combining measurement precision
and minimum wind/convective variability. Our simulation parameter σ_single
(scanned over 3–13 km/s in the grid) brackets the physically plausible range.

### 4b.5 Period Range Justification

Our simulation uses log P ∈ [0.15, 5.0] (days), spanning periods from
~1.4 days to ~274 years. This range is justified as follows:

**Observational constraints on WR binary periods:**

| System  | Type       | Period         | log P  | Method          |
|---------|-----------|----------------|--------|-----------------|
| WR 146  | WN4+O     | ~810–1120 yr   | ~5.5   | Radio interf.   |
| WR 125  | WC7+O9III | 28.12 yr       | ~4.01  | Spectroscopy    |
| WR 137  | WC7pd+O9  | ~13 yr         | ~3.68  | Spectroscopy    |
| WR 140  | WC7pd+O5.5| ~7.9 yr        | ~3.46  | Spectroscopy    |

The longest spectroscopically confirmed WR binary (WR 125, logP ≈ 4.01)
falls well within our grid. The radio-detected WR 146 (logP ≈ 5.5) is
near our upper boundary but would be undetectable by RV methods.

**Detection efficiency vs. period:**

The RV semi-amplitude scales as K₁ ∝ P^(−1/3). For the Dsilva WC survey
(threshold C = 10 km/s), detection probability is:
- ≥ 90% at P < 100 d (logP < 2)
- ~80% at P ~ 100 d
- ~40% at P ~ 1000 d (logP = 3)
- ~0% at P > 10⁴ d (logP > 4)

With our higher threshold (45.5 km/s), detection efficiency drops even
faster. Binaries with logP > 4.5 are essentially invisible to our survey.
Extending logP_max beyond 5.0 would increase the inferred f_int (to account
for undetectable long-period systems) but adds no constraining power from
the data.

**The Dsilva posterior constraints:**

| Sample     | logP_max best-fit      | Notes                              |
|------------|------------------------|------------------------------------|
| WC (Gal.)  | 4.00 (+0.42/−0.34)    | Well-constrained                   |
| WNE (Gal.) | 4.60 (+0.40/−0.77)    | Posterior hits grid boundary (5.0) |
| WNL (Gal.) | 4.90 (+0.09/−3.40)    | Posterior hits grid boundary (5.0) |
| WN combined| 4.99 (+0.00/−1.11)    | Pegged at boundary                 |

For WC stars specifically, the posterior is well-constrained at logP_max ≈ 4.0,
not requiring extension beyond our current grid.

**Complementary evidence:**

- **Sana et al. (2012):** O-star binary survey probed logP = 0.15–3.5 with
  a period power-law π = −0.55 ± 0.22. The logP = 3.5 limit is observational,
  not physical.
- **Moe & Di Stefano (2017):** Total O-star companion frequency peaks at
  logP ~ 3.5 and extends to logP ~ 8, but companions at logP > 5.5 are
  primarily tertiary components in hierarchical triples.
- **Deshmukh et al. (2024):** VLTI/GRAVITY interferometry of 39 Galactic
  WR stars reveals a **"long-period binary desert"** — a lack of WR systems
  at periods of a few hundred to a few thousand days (logP ~ 2–4). The
  200-day period peak predicted by Case B mass-transfer models is not
  observed. This suggests that extending logP_max adds primarily empty
  parameter space.
- **Sana et al. (2025):** 139 O-stars in the SMC — bias-corrected close
  binary fraction ≥70%, with **no significant metallicity trend**. Validates
  the Monte Carlo bias correction approach for low-Z massive stars.

**Conclusion:** Our logP range of [0.15, 5.0] is well-justified. For WC
stars, the Dsilva posterior favours logP_max ≈ 4.0. The scan of logP_max
as a free parameter in our cadence-aware simulation (currently 1.0–10.0)
allows the data to determine the optimal value without imposing a fixed
choice.

### 4b.6 Implications for Our Detection Threshold

Our binary detection threshold of ΔRV > 45.5 km/s on C IV 5808–5812 is:

- **~8–45× the WC wind variability σ_w** (0–6 km/s; Dsilva+2020)
- **~3× the WNE peak-to-peak wind scatter** (15 km/s; Dsilva+2022)
- **~2× the OB supergiant pulsational scatter** (20–25 km/s peak-to-peak;
  Simón-Díaz et al. 2024)
- **Well above the theoretical minimum** (2 km/s; Grassitelli+2016)

The threshold is conservative: it virtually eliminates false positives from
intrinsic variability while remaining sensitive to binaries with
K₁ ≳ 23 km/s (half the threshold for a two-epoch survey).

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
| σ_w (WC, C IV)              | 0–6 km/s       | Dsilva+2020; lowest for high-ion lines|
| σ_w (WNE, N V)              | ~5 km/s        | Dsilva+2022                           |
| σ_w (WNE, He II)            | ~10 km/s       | Dsilva+2022                           |
| Min observed σ_RV (single)  | 1.8 km/s       | WR 3 (WN3ha); Dsilva+2022            |
| Theoretical σ_RV floor      | ~2 km/s        | Grassitelli+2016 (M < 10 M⊙)         |
| σ_measure (per-epoch)       | ~5 km/s        | Formal CCF uncertainty               |
| N_stars per simulation      | 10,000         | Monte-Carlo sample size              |
| Period range (log P)        | [0.15, 5.0]    | Days; power-law distribution         |
| logP_max (WC best-fit)      | 4.00 (+0.42/−0.34) | Dsilva+2020                      |
| logP_max (WN combined)      | 4.99 (+0.00/−1.11) | Dsilva+2023; hits grid boundary  |
| Longest spectro. WR binary  | logP ≈ 4.01    | WR 125 (28.12 yr); WC7+O9III         |
| Eccentricity range          | [0, 0.9]       | Uniform (Dsilva model)               |
| Mass ratio range            | [0.1, 2.0]     | Flat prior (Dsilva model)            |

---

## 6. References

- Bartzakos, P., Moffat, A. F. J., & Niemela, V. S. 2001, MNRAS, 324, 18 —
  Original survey of 28 WC stars in the LMC.
- Chené, A.-N. & St-Louis, N. 2011, ApJ, 736, 140 — Systematic CIR search
  in 68 apparently single Galactic WR stars.
- Chené, A.-N., St-Louis, N., Moffat, A. F. J. & Gayley, K. G. 2020,
  ApJ, 903, 113 — Clumping in WR winds; faster winds show lower variability.
- Crowther, P. A. 2007, ARA&A, 45, 177 — Comprehensive WR review.
- Crowther, P. A., et al. 2002, A&A, 392, 653 — LMC WC4 wind properties;
  Ṁ ∝ Z^(0.6±0.2).
- Deshmukh, M., et al. 2024, A&A, 692, A109 — VLTI/GRAVITY survey of 39
  Galactic WR stars; long-period binary desert.
- Dsilva, K., et al. 2020, A&A, 641, A26 — WC multiplicity survey (Paper I);
  wind variability σ_w for WC stars.
- Dsilva, K., et al. 2022, A&A, 664, A93 — WNE multiplicity survey (Paper II);
  wind variability σ_w ~ 5–10 km/s; detection threshold C = 50 km/s.
- Dsilva, K., et al. 2023, A&A, 674, A108 — WNL multiplicity survey (Paper III);
  combined WN binary fraction and logP_max constraints.
- Grassitelli, L., et al. 2016, A&A, 590, A12 — Sub-surface convection in WR
  envelopes; predicted velocity floor ~2 km/s (M < 10 M⊙).
- Kar, A., et al. 2024, AJ, 168, 199 — TESS pulsations in WR 135 (WC8);
  C IV line variability.
- Koesterke, L., Hamann, W.-R. & Urrutia, T. 2001, A&A, 379, 224 —
  LPV in WR 135 (WC8) and WR 111 (WC5) on C III λ5696.
- Langer, N., et al. 2020, A&A, 638, A39 — Period distribution model for
  OB+BH systems (two-component mixture: Case A and Case B mass transfer).
- Moe, M. & Di Stefano, R. 2017, ApJS, 230, 15 — Comprehensive binary
  statistics; companion frequency peaks at logP ~ 3.5.
- Nazé, Y., et al. 2022, MNRAS, 514, 2269 — WR 7 (WN4) multiple variability
  timescales; peak-to-peak ~50 km/s (non-orbital).
- Sana, H., et al. 2012, Science, 337, 444 — O-star binary fraction 69%;
  period power-law π = −0.55 ± 0.22.
- Sana, H., et al. 2025, Nature Astronomy, 9, 1337 — SMC O-star multiplicity;
  ≥70% close binary fraction; no metallicity trend.
- Sander, A. A. C. & Vink, J. S. 2020, MNRAS, 491, 4406 — Theory-based WR
  mass-loss recipe; Γ and Z dependence.
- Schnurr, O., et al. 2008, MNRAS, 389, 806 — LMC WNL survey; single-star
  σ = 16 km/s.
- Shenar, T., et al. 2019, A&A, 627, A151 — LMC WN binaries; He II λ4686
  should be avoided for RV.
- Simón-Díaz, S., et al. 2024, arXiv:2405.11209 — OB supergiant pulsational
  RV up to 20–25 km/s; false-positive binary risk.
- St-Louis, N., et al. 2020, MNRAS, 497, 4448 — WR 137 (WC7) C III λ5696
  variability at 0.4% rms.
- Vink, J. S. & de Koter, A. 2005, A&A, 442, 587 — WR wind metallicity
  dependence; Ṁ ∝ Z^0.86 for WC.
- Zucker, S. & Mazeh, T. 1994, ApJ, 420, 806 — CCF methodology.
- Zucker, S., et al. 2003, MNRAS, 342, 1291 — Multi-order CCF formalism.

---

## 7. Work Log

Daily summaries of work sessions — what was done, key results, decisions,
and open questions. Written for thesis reference.

---

### 2026-03-29 — Graph review round 4: approvals, UI overhaul, cadence-aware re-sim

**What was done:**
- Completed graph review round 4 (continuing #162/#163): approved H2, H4,
  D9, D10, D15, D17, D18 — bringing total approved/resolved to 17/17.
- D15 Summary Table rewritten with cadence-aware re-simulation using
  `simulate_delta_rv_cadence_aware()` instead of the previous `_me_cdf_band()`
  approach. Table now includes: normalised likelihood row (with asterisk noting
  grid normalisation), raw logL row, σ/logP values in the Re-sim column marked
  with "(grid)" to indicate they come from grid best rather than interpolation.
  Normalised likelihood computed as exp(logL_interp − logL_max).
- D17 Model Explorer overhauled: synced slider+number_input pairs with
  bidirectional callbacks, reset counter pattern for clean widget state on
  reset, logL metric cards showing best vs current scores, CDF x-axis.
- D18 CDF Sanity Check fixed to correctly render 5 random draws.
- Live polling (B2): added logP_max 1D fallback chart alongside σ_single 1D
  profile. Added NoneType guard on `live_heatmaps` dict access.
- Grid Range Exclusion (G1) moved above top heatmaps in `cadence.py` with
  folded `st.expander` (default collapsed).
- Top heatmaps: added logP_max-only 1D fallback for Langer model (when σ grid
  has size 1), added `y_name` parameter to heatmap calls.
- Renamed "Observed Binary Fraction vs Threshold" → "Simulated Binary Fraction
  vs Threshold" in `render_shared.py` and `sim_plots.py` to avoid confusion
  between simulated and real observations.
- GRAPHS_PER_METHOD.md fully updated: all MODIFY targets resolved, Cadence
  Langer note added (π unused → use f_bin vs logP_max or f_bin alone).
- WORKING flags throughout `cadence.py` updated to include "do not change
  this code" per project convention.

**Key results:**
- All 17 graphs in GRAPHS_PER_METHOD.md now resolved (WORKING ✓, REMOVED, or
  FOLDED). No remaining MODIFY targets except G1 (grid exclusion position,
  already implemented but pending final review).

**Methodology notes for paper:**
- Re-simulation at interpolated best-fit now uses cadence-aware simulation
  (same pipeline as the grid search), ensuring consistency. Previous approach
  used non-cadence `_me_cdf_band()`.
- Normalised likelihood at interpolated point: L_norm = exp(logL_interp − logL_max),
  where logL_max is the maximum over the entire grid.

**Decisions:**
- Cadence-aware re-sim replaces `_me_cdf_band()` for D15 — ensures the
  re-simulation at the interpolated best-fit uses the same cadence library,
  weights, and period model as the original grid search.
- "Observed" → "Simulated" for the binary fraction vs threshold plot title,
  since the data shown is from Monte Carlo simulations, not real observations.

**Bugs found and fixed:**
- NoneType error when `live_heatmaps` key returns None instead of empty dict
  (polling.py). No new COMMON_ERRORS entry — one-off guard.
- Model Explorer reset button was broken (deleting session_state keys didn't
  force widget re-creation). Fixed with reset counter pattern.

**Open questions:** None new.

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

### 2026-03-12 — Cadence methodology: weighted K-S scoring, bin_cfg fix; agent reliability; TODO webapp

**What was done:**

*Methodology (paper-relevant):*

- **Cadence-aware grouped simulation confirmed working.** The `simulate_delta_rv_cadence_aware()`
  function (implemented in a prior session from agent/99 branch) runs N_sets (default 10k)
  groups of 25 simulated stars, each matching one real star's MJD cadence. This replaces
  the previous independent-star approach described in the 2026-03-10 meeting entry. The
  binned CDF comparison (`ks_two_sample_binned()`) discretizes ΔRV into ~10 km/s bins
  up to ~350 km/s, regularizing the comparison and avoiding sparse-tail noise. Both
  functions are in `wr_bias_simulation.py` and are now confirmed operational after today's
  bug fixes.

- **Inverse-variance weighted K-S scoring.** Added `ks_weighted_D()` to
  `wr_bias_simulation.py` as an alternative to the standard K-S D statistic for
  cadence-aware runs. The weighted statistic is:
  D_w = Σ(|F_obs(x_i) - F_sim(x_i)| × w_i) / Σ(w_i),
  where w_i = 1/σ_i² and σ_i is the standard deviation of the simulated CDF at bin i
  across the N_sets realizations. This gives less weight to CDF bins where the simulation
  outcome is uncertain (high variance). D_w remains in [0,1], so the standard Kolmogorov
  p-value series applies as an approximation. A UI radio selector in both cadence tabs
  lets the user choose between "K-S (standard)" and "K-S (variance-weighted)". The scoring
  method is threaded through `_init_worker` → worker → `run_bias_grid_cadence_aware`.

- **Cadence diagnostic histogram bin_cfg fix (E029).** The `_render_cadence_results()`
  function was rebuilding a fresh `BinaryParameterConfig` from session_state keys with
  incorrect defaults — missing `langer_period_params` (empty dict → wrong logP
  distribution), missing `q_flipped`, wrong `e_model` default ('flat' instead of 'zero'
  for Langer), wrong logP range, wrong q_model session_state key. Fix: pass the
  already-constructed `_bin_cfg` object from the tab UI as a function parameter. This
  ensures the diagnostic histograms use the exact same orbital parameter distributions
  as the grid simulation.

*Infrastructure:*

- **Overnight agent git safety.** Diagnosed that `git_commit_all()` in
  `scripts/overnight_agent.py` was doing `git add -A` on the main working tree, sweeping
  the user's uncommitted files (e.g., newly created slash commands) into agent commits.
  Replaced with `git_commit_files()` that only stages specified files. Added stash
  push/pop safety in the finally block to preserve user uncommitted work across agent runs.

- **Git worktree isolation for overnight agent.** Converted the entire overnight agent
  from branch-checkout to worktree isolation. Agent work now happens in
  `../agent-worktree/` (a sibling directory created via `git worktree add`). All
  `run_pipeline`, `run_freeform_task`, and `agent_loop` functions updated (~20 edits).
  Added DONE status to `agent_app/app.py`. Added `[T]est` option to `--stop` interactive
  branch review that creates a temporary worktree for inspection before merge/discard.

- **Standalone TODO webapp.** Extracted all TODO logic from `app/pages/10_todo.py` (798
  lines) into `app/todo_core.py` as a shared module with `render_todo_page()`. The
  original page is now a 27-line thin wrapper. Created `todo_app.py` as a standalone
  Streamlit entry point on port 8502. Both apps read/write the same `TODO.md`.

- **EndConv/EnDay daily logging system.** Created `/EndConv` slash command that appends
  structured conversation summaries to `daily_logs/YYYY-MM-DD.md`. Updated `/EnDay`
  workflow to read daily logs as its first step, cross-referencing with git history for
  complete work inventory.

**Key results:**
- Cadence-aware pipeline (grouped sets + binned CDF + optional variance weighting) is
  now fully operational with correct orbital parameter passthrough.
- Overnight agent can no longer destroy user's uncommitted work.

**Methodology notes for paper:**
- The inverse-variance weighted K-S statistic should be described in the Methods section
  as a refinement for cadence-aware runs. It addresses the heteroscedasticity inherent
  in grouped-set simulation: bins with fewer contributing stars have higher variance.
  The weighting ensures the fit is driven by bins where the simulation gives reliable
  predictions.
- The cadence-matched Monte-Carlo method (10k sets × 25 stars) and binned CDF should
  be described as the primary simulation approach, contrasted with Dsilva et al. (2023)
  independent-star method. Paper section `bias_correction.tex` has TODO markers at
  lines 71–73 for these additions.

**Bugs found and fixed:**
- E029: Config object rebuilt from session_state with wrong defaults instead of passing
  constructed object (cadence diagnostic histograms).
- Overnight agent `git add -A` sweeping user files into agent commits (workflow bug,
  not a code pattern — fixed by replacing with targeted `git_commit_files()`).

**Open questions:**
- Is the Kolmogorov p-value series valid for the weighted D_w statistic? D_w is a
  weighted mean of per-bin |diffs|, not a supremum. This is an approximation — may
  need validation via permutation test or simulation study.
- Task #92 (per-star cadence simulation with median CDF + error band display) remains
  open — the backend computes per-set CDFs but the UI does not yet show the 68%
  error band as a shaded region.

### 2026-03-13 — Variance-weighted scoring: three approaches tested, not yet resolved

**What was done:**

*Methodology (paper-relevant):*

- **Variance-weighted KS scoring revisited.** The original `ks_weighted_D()` (implemented
  2026-03-12) used a weighted average D_w = Σ(|diff_i| × w_i)/Σ(w_i). Testing revealed
  this produces p-values ≈ 1.0 everywhere because the weighted average D is inherently
  much smaller than max|diff| (~0.01–0.05 vs ~0.2–0.3), and the Kolmogorov p-value
  formula is calibrated for the supremum statistic.

- **Three approaches attempted, none fully satisfactory:**
  1. **Weighted average + linear score** (1 − D_w): D_w too small → scores all ≈ 0.95–0.99,
     no dynamic range.
  2. **Weighted max** D_w = max(|diff_i| × w_norm_i) with w_norm ∈ [0,1]: The max-diff bin
     typically also has the lowest variance, so weights ≈ 1 → D_w ≈ standard D, and the
     linear 1−D score lacks the nonlinear amplification of the Kolmogorov series.
  3. **Chi-squared goodness-of-fit** χ² = Σ(diff_i² / σ²_i) with scipy chi2.sf() p-value:
     Conceptually correct (standard method for per-bin uncertainties), but σ² from 10,000
     repetitions is ~10⁻⁴, producing astronomical χ² values → p ≈ 10⁻⁴⁴.

- **Root cause identified for attempt 3:** The per-bin CDF variance σ²_i reflects the
  variance of the *median* over N_sets repetitions, which scales as ~1/N_sets. With
  N_sets = 10,000, σ² ≈ 10⁻⁴ even for well-behaved bins. Dividing diff² by this tiny
  number inflates χ² far beyond the expected range for n_dof ≈ 35 bins. Possible fixes:
  (a) multiply σ² by N_sets to recover per-single-realization variance,
  (b) use a reduced chi-squared χ²_red = χ²/n_dof with a custom score mapping,
  (c) use Anderson–Darling or Cramér–von Mises weighted statistics instead.

- **Web research conducted:** scipy issue #12315 (weighted ks_2samp proposal), hep_ml
  ks_2samp_weighted, R package Ecume (Monahan 2011 effective sample sizes). Standard
  weighted KS tests weight *observations* (to build weighted CDFs), not CDF bins — our
  use case (per-bin simulation uncertainty) is less standard.

**Key results:**
- No working variance-weighted scoring yet. Standard KS scoring remains the operational method.
- All three implementations are in `wr_bias_simulation.py` (`ks_weighted_D`, `chi2_weighted_score`).
  Current code calls `chi2_weighted_score` when weighted mode is selected.

**Open questions:**
- Best normalization for the chi-squared approach: scale variance by N_sets?
- Alternative: use the per-set D values (compute D for each of N_sets repetitions) and
  report the median D with uncertainty, bypassing the need for per-bin weighting entirely.
- Should the weighted scoring be abandoned in favor of reporting the 68% CDF band visually
  and relying on standard KS for the p-value?

---

### 2026-03-15 — CvM scoring implementation, grid exclusion, 3D interpolation, agent replacement

**What was done:**

*Methodology (paper-relevant):*

- **Cramér–von Mises (CvM) inverse-variance-weighted scoring** implemented as the primary
  alternative to standard K-S testing. The CvM statistic is defined as
  S = Σ(F_obs,i − F_sim,median,i)² / σ²_i, where σ²_i is the per-bin variance across
  N_sets simulation realizations. This replaces the three failed weighted-KS attempts
  from 2026-03-13. The CvM approach uses all bins (not just the supremum), weights by
  inverse variance (down-weighting noisy bins), and produces a scalar score where
  lower S = better fit — analogous to minimum χ².

- **Empirical p-value** computed alongside S: for each grid point, 10,000 simulated
  datasets are scored and the p-value = fraction with S ≥ S_obs. Found that p ≈ 0
  everywhere for N=25 stars (test is too sensitive), but S-score ranking remains valid
  for model selection. Healthy p-value range defined as [0.05, 0.95] — models outside
  this range are masked as implausible.

- **Parabolic interpolation** replaced spline fitting for best-fit parameter estimation.
  The S-score landscape spans 0 to ~3M+, causing splines to oscillate wildly. Instead,
  use CCF-style 2D quadratic fit (6-coefficient) with configurable selection modes:
  (a) height-based (S < threshold), (b) range-based (parameter within bounds), and
  (c) neighbourhood (±N nearest points). Per-axis interpolation factors allow different
  fit radii for f_bin vs σ_single.

- **3D quadratic interpolation** for cadence results: 10-coefficient quadratic fit over
  f_bin × π × σ_single simultaneously, producing 3 projected 2D surface plots.

- **Grid exclusion UI**: per-axis range sliders and per-value dropdowns to exclude
  implausible parameter regions before fitting. Exclusion masks propagate correctly
  to CDF recomputation, summary table, and downstream plots.

*Infrastructure (not paper-relevant):*

- **Agent system replaced**: the 7,300-line overnight agent + 7-page webapp replaced
  with ~300 lines: `.claude/commands/run-task.md` (slash command), `scripts/launch-agent.sh`
  (tmux + caffeinate launcher), and simplified `agent_app/app.py`.

**Key results:**
- CvM S-score successfully differentiates models where KS p-value was flat. The
  S-score heatmap shows clear minima in (f_bin, σ_single) space.
- Empirical p-value ≈ 0 everywhere confirms the CvM test is very sensitive with
  N=25. S-score ranking is the operational method; p-value is for visualization only.
- Save/load for cadence results now working (fixed `_scan_result_metadata` accessing
  closed numpy file, and `bin_edges` None fallback).

**Bugs found and fixed:**
- E030: `dict.get()` returns None when key exists with None value
- E031: `dict(**unpacked, key=val)` duplicate key collision
- E032: Hardcoded Streamlit widget keys in reusable function
- E033: Variable defined inside `if n_bin > 0` used unconditionally in return
- scoring_method NameError in cadence tab renderers (out-of-scope variable)
- CvM heatmap axes flipped vs main heatmaps
- Live heatmap title showing "K-S p-value" for CvM mode
- `_scan_result_metadata` accessing `d['n_sets']` after `d.close()`
- Exclusion mask shape mismatch between CvM grid and cadence array dimensions
- Session_state key conflict between stored values and multiselect widget

**Open questions:**
- Cadence resume uses wrong scoring method (BUG — to investigate next session)
- Need posterior edge error bars in summary table (±format, not just HDI range)
- Dsilva cadence 1D sigma plot should show S-score not p-value

---

### 2026-03-16 — Binned multinomial likelihood implementation (Dsilva+2023)

**What was done:**

*Methodology (paper-relevant):*

- **Binned multinomial likelihood** implemented following Dsilva et al. (2023) Section 4.2.
  The previous approach used K-S or CvM p-values as pseudo-posterior weights for marginalization
  and HDI68 error bar computation. While p-values correctly identify the best-fit location,
  they are not proper likelihoods — a p-value asks "how extreme is this data?" while a
  likelihood asks "how probable is this data given these parameters?" The shape difference
  affects error bar calibration.

- The likelihood is computed as ln L = Σ n_i · ln(p_i), where n_i is the observed count of
  stars in ΔRV bin i, and p_i is the simulated probability of a star falling in bin i (estimated
  from pooling all simulated sets at each grid point). The multiplicative constant N!/(n_1!...n_k!)
  is dropped as it is independent of model parameters.

- Bin edges for the likelihood are taken from the user's configured bins (adaptive or fixed grid),
  matching the CvM/KS evaluation points. Initial implementation with Dsilva's 4 coarse bins
  ([0, 50, 250, 650, ∞] km/s) was insensitive to σ_single because all single-star ΔRVs fell
  within the first bin regardless of σ.

- The likelihood surface is normalized across the grid as L = exp(ln L − max(ln L)), giving
  values in [0, 1] with 1.0 at the best-fit point. Marginalization and HDI68 computation
  follow the same procedure as for p-values.

- Likelihood is computed as a **bonus** alongside CvM scoring (using the same simulated data),
  and also available as a standalone scoring method. Both p-value and likelihood posteriors
  are displayed simultaneously when CvM is selected.

*Implementation:*

- New function `multinomial_log_likelihood()` in `wr_bias_simulation.py`
- Worker functions extended to return logL alongside existing D, p, S_raw
- `run_bias_grid()` and `run_bias_grid_cadence_aware()` now return `likelihood` and `logL_raw` arrays
- UI: "Likelihood (Dsilva+23)" scoring option added to all 4 simulation tabs
- Visualization: likelihood heatmaps, corner plots (red color scheme), and HDI68 columns
  added alongside existing p-value displays

**Open questions:**

- The likelihood surface appears nearly flat across σ_single even with fine bins. This may
  indicate that the multinomial discretization fundamentally loses sensitivity to σ compared
  to the continuous CvM comparison, or there may be a numerical issue with the pooling approach.
  Needs investigation.
- Whether to use Dsilva's coarse bins (for paper comparability) or fine bins (for σ sensitivity)
  as the default — currently using the user's configured bins.

### 2026-03-17 — Multi-score bias correction, RV modeling page rebuild, webapp reorganisation

**Unified multi-score bias correction.** The simulation engine (`wr_bias_simulation.py`) was
refactored to compute all four scoring methods — Kolmogorov–Smirnov, inverse-variance-weighted
CvM, Cramér–von Mises, and binned multinomial likelihood — in a single pass per grid point.
Previously each scoring method required a separate simulation run; now the ΔRV samples are
generated once and all four statistics are computed from the same data, with no performance
regression since simulation cost is dominated by orbital integration, not statistical tests.
The bias correction UI was restructured: per-method radio buttons removed, replaced by a
unified summary table comparing all four methods and collapsible per-method expanders showing
heatmaps, corner plots, CvM/likelihood analysis, and model explorers.

**Statistical RV Modeling page rebuilt** (Task #52/#103). The two-component mixture model page
was rewritten from scratch. Two models are now fitted side-by-side: (1) an **empirical model**
using binary ΔRV survival functions from the Monte Carlo orbital simulation, fitting
`(f_bin, σ_single)`; and (2) a **Gaussian analytical model** fitting
`(σ_single, σ_binary, f_bin)`. The page features an interactive parameter playground with
instant sliders for binary fraction and sigma values (updating plots without re-simulation),
plus full orbital parameter controls that require an explicit Recompute action. Four analysis
tabs: Sample Fit (with residuals and weighted PDFs), Fraction Recovery (noise/signal domain
separation), Global Correction (+Bartzakos prior), and Population Simulation (placeholder).

**Webapp reorganisation.** Three pages exceeding 1,000 lines were split into subpackages:
`06_plots.py` (1,456 → `app/plots/`), `11_nres_analysis.py` (1,117 → `app/nres/`), and
`12_rv_modeling.py` (1,193 → `app/rv_modeling/`). The bias correction page (9,977 lines)
was similarly split into `app/bc/`. An 800-line-per-file limit was established as a project
rule.

**Bug fixes.** E034 (nanargmax without isfinite guard) in dsilva.py, E038 (session_state
write after widget instantiation) in rv_modeling, cadence Langer shape mismatch, CDF origin
offset, colorbar labels, live heatmap persistence, 15+ additional UI fixes.

---

### 2026-03-18 — Per-epoch error model for binaries, spectrum page enhancements, RV modeling redesign

**Critical simulation fix: likelihood f_bin = 1 degeneracy (Task #140).** Investigation revealed
that the multinomial likelihood scoring method consistently returned f_bin ≈ 1.0 with zero
dependence on σ_single. The root cause was identified: binary RV simulations in both
`simulate_delta_rv_sample` and `simulate_delta_rv_cadence_aware` computed pure orbital velocities
with no measurement noise. Face-on binary systems (sin i ≈ 0) produced ΔRV ≈ 0.0 exactly, which
meant that adding more binaries to the model was cost-free in the likelihood function — hidden
binaries contributed zero probability mass to any bin, making f_bin = 1 the trivial maximum.

The fix adds per-epoch measurement noise to all simulated RV measurements. A new function
`_draw_measurement_noise()` supports seven distribution types (Fixed/Normal/Log-normal/Gamma/
Weibull/Exponential/Flat), drawing from scipy distributions with random sign for symmetric errors.
Four new fields were added to `SimulationConfig`: `error_model_single`, `error_params_single`,
`error_model_binary`, `error_params_binary`, allowing independent error model configuration for
single and binary populations. The error model is plumbed through all multiprocessing workers
(`_init_worker`, `_single_grid_task_lite`, `_single_grid_task_cadence_aware`) and both grid runner
functions. The UI was updated with separate error model selectors for singles and binaries in all
four simulation tabs (D'Silva, Langer, Cadence D'Silva, Cadence Langer).

Verification confirms the fix: with σ_measure = 5 km/s, zero binary systems now have ΔRV < 1 km/s
(previously 5 out of 1000 had ΔRV < 1 km/s due to exact face-on geometry).

**Spectrum browser enhancements.** The wavelength nm → Å conversion bug was fixed (`.npz` files
store wavelengths in nm; the page now consistently multiplies by 10.0 for display). Eight Oxygen
emission lines (O III/IV/V/VI) were added to the diagnostic line database. The model overlay
system was replaced: a multi-model folder browser allows selecting multiple model spectra from
`Data/Models_for_Guy/` with per-model scale/offset sliders. Multi-epoch spectral overlay was added
with vertical staggering (configurable offset slider) and a 6-colour cycling palette. A new
"Max ΔRV Epoch Comparison" section auto-identifies the epoch pair with maximum radial velocity
separation for a user-selected emission line and displays both spectra with a zoom-to-line option.

**RV Modeling page redesign.** The statistical RV modeling page was expanded from 4 to 6 tabs:
(A) Simulate Binary RVs — orbital simulation producing centred per-epoch RVs with full
distribution fitting (6 scipy distributions, MLE auto-fit, AIC/BIC, Q-Q plots);
(B) Model Fitting — two-component mixture model with parametric distributions, f_bin grid
optimisation; (C) Playground — slider-based manual exploration with snapshot comparison;
(D–F) existing Sample Fit, Fraction Recovery, and Global Correction tabs retained. Configurable
histogram binning was added via 5 auto-binning methods (Freedman–Diaconis, Sturges, Scott,
√N, Plotly auto) with a manual override slider.

**Bias correction UI improvements.** Across six earlier sessions today, 10 tasks from the bias
correction page were completed: per-method p-value label fixes (#130), live sigma-vs-score graph
persistence (#131), likelihood interpolation label fix (#137), sigma_single columns in comparison
table (#132), file structure split into fitting.py + scoring_detail.py (#136), score-vs-sigma
graphs for all methods (#133a), per-method sigma_single sliders (#133b), interactive Model
Explorer (#133c), corner plots expanded to 3 parameters (#134), manual likelihood bin edges (#135),
per-method best-fit summary tables (#138), and CDF comparison moved to top with per-method
toggles (#139).

---

### 2026-03-19 — Bias correction architecture overhaul, RV modeling physics mode, Plots page planning

**What was done:**

*Dsilva+2023 methodology review.* The Dsilva et al. 2023 (Paper III, A&A 674, A88) approach
to single-star modelling was reviewed in detail. A key finding: Dsilva does not simulate singles
at all — single stars contribute ΔRV = 0 in the Monte Carlo, with wind variability absorbed
into the detection threshold C = 50 km/s (approximately 3× the observed ~15 km/s variability).
This explains why σ_single is insensitive in our likelihood implementation: when using coarse
bins [0, 45.5, 250, 650, ∞], the distinction between singles and undetected long-period binaries
(both contributing to bin 1) is lost, creating a degeneracy ridge in (f_bin, π) space. Dsilva
breaks this with prior information on known orbital periods. For our analysis, the K-S test on
the continuous CDF may provide greater discriminating power within bin 1 compared to the
multinomial likelihood.

*Bias correction architecture overhaul.* The bias correction page underwent a major refactoring
to support sub-tab structure within each model tab. Each model (Dsilva, Langer, Cadence×2) now
contains 5 sub-tabs: Simulation, K-S, K-S Weighted, CvM, and Likelihood, orchestrated through
a shared `subtabs.py` module. Seven oversized files were split: `dsilva.py` (1599→796 lines),
`langer.py` (1479→791), `cadence.py` (1668→819), `helpers.py` (1008→445), and `runners.py`
(1382→4, split into three model-specific runner files). Six new files were created: `subtabs.py`
(317 lines), `sim_plots.py` (432), `file_ops.py` (589), `polling.py` (198), `runners_dsilva.py`
(420), `runners_langer.py` (409), `runners_cadence.py` (599). A logP_max scanning feature was
added as a full grid parameter alongside σ_single, with 4D corner plots and per-slice heatmaps.
CDF legendgroup linking ensures that toggling a CDF line also hides its uncertainty shadow.

*RV Modeling physics-based simulation.* The RV Modeling page was expanded with a physics-based
simulation mode alongside the existing parametric mode. In both the Playground (Tab C) and
Model Fitting (Tab B) tabs, a Parametric/Physics-based toggle now selects between analytical
Gaussian models and full orbital simulations using `simulate_delta_rv_sample` from
`wr_bias_simulation.py`. The physics mode uses real observation cadences (MJD-OBS timestamps
from FITS headers for all 25 WR stars) and supports separate error model selectors for singles
and binaries (6 distribution types: Normal, Log-normal, Gamma, Weibull, Exponential, Uniform).
A 9-panel orbital parameter histogram grid was added showing the distributions of log P, e, q,
K₁, M₁, M₂, i, ω, and T₀ with Detected/Missed/All view modes. Comprehensive end-to-end testing
verified that all 11 simulation parameters (f_bin, π, period model, both error models, mass,
logP bounds, eccentricity bounds) affect the output independently.

*Plots page gap analysis.* A systematic comparison was performed between all plots in the
Thesis work.ipynb notebook (27 plot cells), Plots.ipynb (25+ publication figures), and the
webapp Plots page. Nine missing or partially missing plots were identified: ΔRV vs emission
line wavelength scatter, piecewise f_bin(threshold) fit with elbow detection, equivalent
thresholds across lines, correlation-weighted agreement ranking, interactive epoch-strip
dashboard, SNR requirements on template spectrum, f_bin(t) survival function, PDF intersection
for threshold optimization, and normalized flux anchor points. A 410-line implementation plan
was created at `plans/plots_page_overhaul.md` with built-in iterative improvement and error
checking protocols for autonomous agent execution.

**Key results:**
- Dsilva's methodology confirmed: σ_single insensitivity in likelihood is methodological, not a bug
- f_bin = 1 degeneracy in multinomial likelihood arises from coarse binning (0–45.5 bin absorbs both singles and undetected long-period binaries)
- 9 missing plots identified for webapp completion
- Physics-based simulation validated with 11 independent parameter checks

**Methodology notes for paper:**
- The multinomial likelihood (Dsilva+2023 §4.2) provides complementary information to the K-S
  test: it constrains f_bin via binned detection rates, while K-S constrains via the full CDF
  shape. The choice of bin edges affects the degeneracy structure — finer binning within the
  0–45.5 km/s range may improve discrimination between singles and undetected binaries.
- Real observation cadences (as opposed to uniform or randomised cadences) can significantly
  affect the detection completeness, particularly for systems with periods comparable to the
  observation baseline.

**Decisions:**
- Sub-tab architecture adopted for bias correction: one shared orchestrator (`subtabs.py`)
  ensures feature/bug fixes apply once across all 4 model tabs.
- logP_max treated as a full model parameter (not fixed) — enables exploration of period range
  sensitivity.
- RV Modeling uses random cadence assignment (not deterministic like bias correction) —
  appropriate for exploratory parameter space exploration.

**Bugs found and fixed:**
- E039: ND squeeze removing wrong axis (new COMMON_ERRORS entry)
- Binary mask size mismatch (N_total vs N_binary) causing IndexError
- `_cam_presets` variable unbound in scoring_detail.py
- Corner plot dimension guard for cadence_langer mode
- Period model selectbox used `'dsilva'` instead of `'powerlaw'`

**Open questions:**
- Does the K-S test (continuous CDF) give a different best-fit f_bin than likelihood for the same data?
- Should period-bin priors (à la Dsilva) be implemented to break the f_bin=1 degeneracy?
- Task #151: Playground f(T) must apply the 4σ significance criterion

---

### 2026-03-21 — Bias correction UI overhaul, cadence 4D display fixes, Dash bias-correction webapp

**What was done:**

*Scoring method UI restructure.* The five sub-tabs per model (Simulation, K-S, K-S Weighted, CvM,
Likelihood) were replaced with horizontal radio buttons for scoring method selection. The Simulation
overview (summary table, CDF comparison, analysis plots) now remains always visible above the radio
selector, reducing navigation friction when comparing scoring methods. This change was implemented
in `render_model_subtabs()` in `subtabs.py`.

*Cadence-aware 4D array handling fixes.* Multiple fixes were applied to the cadence-aware simulation
display pipeline. For cadence_langer with logPmax scanning, the raw scoring arrays carry a trailing
pi=1 dimension that was not being squeezed, causing shape mismatches throughout the display code.
Fixes included: (1) proper pi-dimension squeeze at the start of `_render_method_expander`,
(2) dynamic grid construction in `_render_method_summary_section` based on which axes were actually
scanned (replacing hardcoded `[fbin, sigma]`), (3) a 2D transpose fix after slicing 3D→2D for
cadence_langer (`[sigma, fbin]` → `[fbin, sigma]`), (4) correct global_best_idx axis mapping for
cadence_langer 3D `[logPmax, sigma, fbin]`, (5) logPmax slider support in per-method expanders.

*Extra marginalized heatmaps.* Two additional heatmaps (f_bin × logPmax, σ × logPmax) were added
side-by-side below the main heatmap when both logPmax and sigma are scanned axes. These show the
score surface marginalized (via nanmax) over the remaining axes, providing a quick overview of the
parameter space structure. A critical IndexError was found and fixed in the marginalization code:
for cadence_dsilva 4D arrays `[logPmax, sigma, fbin, pi]`, the original code marginalized only over
axis=1 (sigma) leaving a 3D result, which then crashed `find_best_grid_point` via manual index
unraveling. The fix uses `axis=(1,3)` for 4D arrays to correctly collapse both sigma and pi.
Additionally, `find_best_grid_point` in `shared.py` was hardened to use `np.unravel_index` instead
of manual integer division.

*Corner plots with logPmax.* The corner plot renderer (`corner_plots.py`) was extended to include
logPmax as an axis when it is a scanned parameter, enabling visual inspection of parameter
correlations across all grid dimensions.

*Live sigma graph 4D fix.* The `runners_cadence.py` live sigma-scan progress graph was fixed to
correctly marginalize over the logPmax axis first when working with 4D result arrays, preventing
incorrect per-sigma indexing.

*Dash bias-correction webapp.* A parallel implementation of the bias correction interface was built
using Plotly Dash + Dash Mantine Components (DMC), motivated by Streamlit's inability to support
nested tabs. The `bias_app/` directory contains 28 Python files (4,372 lines) with 6 pages, nested
scoring method tabs, localStorage persistence, and 28/70 scoring plots implemented. Both webapps
coexist: Streamlit on :8501, Dash on :8050, sharing `results/` and `settings/`.

**Key results:**
- E040 and E041 added to COMMON_ERRORS: grid/array dimension mismatch (E040) and colorbar label
  mismatch (E041) are now documented with grep-ready patterns
- IndexError in cadence_dsilva likelihood heatmaps resolved (variant of E040)
- Dash webapp validates that nested-tab architecture is feasible for the bias correction UI

**Methodology notes for paper:**
- No changes to the underlying simulation methodology or statistical approach — all fixes are
  display/UI-level corrections that ensure the correct data is shown to the user.

**Decisions:**
- Radio buttons over sub-tabs: cleaner UX, simulation overview always visible
- Extra heatmaps use `np.nanmax` marginalization (conservative: shows best-case score across
  marginalized axes)
- `np.unravel_index` adopted as standard for all argmax→index conversions (defensive against
  shape mismatches)

**Bugs found and fixed:**
- E040 variant: 4D cadence_dsilva arrays passed to 3D-assuming marginalization code
- `find_best_grid_point` manual index unraveling (replaced with `np.unravel_index`)
- cadence_langer pi=1 trailing dimension not squeezed
- cadence_langer `[sigma, fbin]` not transposed to `[fbin, sigma]` after slicing
- `_build_extra_grids()` not including sigma for cadence_dsilva mode
- runners_cadence live sigma graph: missing logPmax axis marginalization for 4D

**Open questions:**
- Dash background callbacks in v4.0 unreliable — synchronous callbacks work but freeze UI
- 42/70 scoring plots still unimplemented in Dash app
- Task #147: 3D/4D parabolic fit including sigma_single still open

---

### 2026-03-22 — Bias correction simplification: two scoring methods, cadence-only simulation, graph rendering split

*Cadence checkpoint resume fix.* The cadence-aware simulation's checkpoint resume logic contained
a bug: on resume, the code used the current UI grid parameters (which may have changed) rather
than the grid parameters stored in the checkpoint file. This caused shape mismatches and incorrect
grid indexing when the user changed grid settings between a cancel and a resume. The fix overrides
`fbin_vals`, `pi_vals`, `sigma_vals`, `logPmax_scan_vals`, and `n_sets` from the checkpoint file
before resuming. Additionally, all 8 scoring arrays (K-S D, K-S p, weighted K-S, CvM D, CvM p,
CvM S, likelihood, chi2) are now loaded from partial results (previously only 2 were loaded).

*Scoring method simplification.* The bias correction page previously offered four scoring methods:
K-S test, inverse-variance weighted K-S, Cramér–von Mises (CvM) S-score, and multinomial
likelihood. After evaluation, the weighted K-S and CvM methods were removed, retaining only the
two-sample K-S test and the multinomial likelihood as the primary scoring methods. The K-S test
provides a distribution-free comparison of simulated and observed CDFs (Sect.~4.2 of Dsilva+2023),
while the multinomial likelihood (Sect.~4.2 of Dsilva+2023) bins the ΔRV distribution into coarse
intervals and computes the probability of the observed bin counts given the simulated fractions.
These two methods complement each other: K-S is sensitive to the overall CDF shape, while the
likelihood is sensitive to the bin-level population fractions. The removed methods remain available
in `wr_bias_simulation.py` (functions `ks_weighted_D`, `cvm_weighted_score`) for future use if
needed (tracked in TODO #153–155).

*Non-cadence tab removal.* The non-cadence Dsilva and Langer simulation tabs were removed from
the webapp. All simulation now uses the cadence-aware approach (Task #92): each simulated set
contains one star per real target, sampled at that star's actual observation epochs (MJD
timestamps from FITS headers). This is scientifically more appropriate than the original approach
of drawing N independent stars with arbitrary time baselines, as it faithfully reproduces the
observational sampling and accounts for per-star cadence limitations. Files deleted:
`dsilva.py`, `langer.py`, `runners_dsilva.py`, `runners_langer.py` (~2400 lines total).
Backups preserved in `Backups/bc_backup_20260322/`.

*Graph rendering hard-split.* The graph rendering code for the bias correction results was
reorganised into 9 independent files, separating K-S and Likelihood rendering completely:
`render_shared.py` (common graphs: summary table, CDF comparison, simulation diagnostics),
`render_ks.py`/`render_ks_scoring.py`/`render_ks_fit.py`/`render_ks_explorer.py` (K-S specific),
and the corresponding `render_lk_*` files for Likelihood. Code is intentionally duplicated
between K-S and Likelihood rather than shared, per user decision — this prevents cross-method
bugs where a fix for one scoring method inadvertently breaks another.

*Feature and graph catalog documentation.* Two reference documents were created in `app/bc/`:
`FEATURES.md` (374 lines, 128 features across 23 categories) cataloguing every UI widget,
parameter, and control in the bias correction page, and `GRAPHS_PER_METHOD.md` (516 lines)
documenting every Plotly chart that appears for each scoring method, including conditional
visibility rules and the heatmap factory specification.

*Code protection rules.* Five mandatory blocks were established to prevent modification of
working code during bug fixes: (1) identify root cause before editing, (2) one file only,
(3) revert test, (4) ask before refactoring, (5) flag working code with
`# ── WORKING · {feature} ──` comments. Sixteen such flags were added across the cadence
checkpoint resume code.

**Key results:**
- Bias correction page reduced from 4 scoring methods to 2 (K-S + Likelihood)
- All simulation now cadence-aware (no non-cadence mode)
- ~2400 lines of dead code removed; 9 new render files created (all < 800 lines)
- Cadence checkpoint resume bug fixed

**Methodology notes for paper:**
- The simplification to K-S + multinomial likelihood as the two retained scoring methods should
  be described in the bias correction methodology section. The K-S test is the standard
  comparison tool (Dsilva+2023); the multinomial likelihood provides complementary bin-level
  sensitivity.
- Cadence-aware simulation is now the sole approach — the paper should not describe a
  non-cadence variant.

**Decisions:**
- Duplicated graph code between K-S and Likelihood (no shared rendering functions) for isolation
- Retained weighted KS/CvM functions in simulation engine for potential future use
- Added WORKING code flags as a lightweight protection mechanism

**Bugs found and fixed:**
- Cadence checkpoint resume using UI params instead of saved params (logic bug, not greppable)

**Open questions:**
- GRAPHS_PER_METHOD.md review in progress — graphs A1-A4 have user comments, need implementation
- Old render files (analysis.py, scoring_detail.py, etc.) not yet deleted pending webapp testing
- Task #147: 3D/4D parabolic fit including sigma_single still open

---

### 2026-03-24 — Graph review overhaul: maximum likelihood framing, 15 fixes, 4 removals

*Systematic graph review.* All 21 graphs in the bias correction page were reviewed one-by-one
with the user in rendering order (top to bottom). Each graph was assessed for correctness,
clarity, and completeness. Seven graphs passed without changes, eleven required modifications,
and four were removed as redundant or superseded.

*Maximum likelihood convention.* The entire bias correction analysis page was switched from
a "minimum −log L" convention (where lower scores indicate better fits) to standard maximum
likelihood framing (where higher likelihood indicates better fits). This affects all user-facing
labels, success messages, and captions. The internal mathematical implementation (negation for
parabolic fitting) was preserved unchanged, as it is standard practice for gradient-based
optimisation. Function names (`_parabolic_min_*`) were retained to avoid call-site churn.

*Removed graphs.* Four graphs were eliminated: A4 (period distribution histogram, redundant
with the log₁₀P panel in the A6 9-panel orbital histograms), E5 (CDF with bin overlay,
redundant with the A2 CDF comparison at the top), D11 (3D/4D quadratic projections, removed
to simplify the analysis to f_bin×π interpolation only), and D16 (re-simulation at interpolated
best-fit, folded into D15 where it runs automatically after interpolation). This removed
approximately 320 lines of rendering code.

*Summary table enhancements (A1).* The summary table now includes a logP_max column (conditional
on the parameter being scanned) alongside the existing σ_single column, plus interpolated
best-fit values from the parabolic fitting when available. This gives a complete parameter
overview in one table.

*CDF comparison fix (A2).* The observed ΔRV CDF line was changed from black to white for
dark-mode visibility. A gold annotation box was added showing the best-fit model's ln L score,
σ_single, and logP_max values, giving immediate context for the plotted CDF.

*Max likelihood heatmap relocation (A3).* The σ_single × logP_max maximum likelihood chart
was moved from the shared section (visible before scoring selection) to the Likelihood Analysis
section where it logically belongs. The chart now uses unnormalized logL_raw values instead of
normalised likelihood, and the height was increased to 450 pixels for better readability.

*Live 2D heatmap (B2).* When both σ_single and logP_max are scanned simultaneously, the live
polling profile now displays a true 2D heatmap (σ × logP, max likelihood per grid point) instead
of two separate 1D line charts. The 2D data is computed in the cadence runner
(`live_sigma_logPmax_2d`) and persisted for the final post-completion display.

*Slider UX improvements (D1, D17).* The σ_single and logP_max sliders above the primary
heatmap now display captions with the best-fit values and include a green "Reset to best"
button. The Model Explorer sliders received the same treatment, plus a score delta comparison
(current ln L vs best ln L) shown as a Streamlit metric delta.

*Right panel fix (D5a).* The σ × logP_max maximum likelihood right panel was not rendering
because `logPmax_grid` was only passed to the scoring detail when `sigma_grid.size <= 1`.
The fix ensures logPmax_grid is always passed when it has >1 values.

*1D slice defaults (D9).* The default fit selection mode was changed from Height-based (factor
2.0) to Range-based (fraction 0.20), providing more stable parabolic fits across typical grid
resolutions.

*Interpolation key mismatch fix (D15).* The best-fit summary table was not showing interpolated
results because it checked `session_state[f'{prefix}_interp']` while the scoring code stored
at `session_state[f'{prefix}_likelihood_analysis_interp']`. The key was corrected.

*CDF sanity check fix (D18).* The cadence CDF sanity check (5 random draws at best-fit) was
not rendering because an extra empty dictionary `{}` was erroneously passed as an argument,
causing the `result` parameter to receive `{}` instead of the actual result dict. The fix
removed the spurious argument.

*Methodology explainer (E7).* A "bad example" section was added showing the multinomial
log-likelihood score for a uniform model (equal probability across all bins), contrasted with
the existing good example. This helps the user understand what distinguishes a well-fitting
model from a poor one.

*Code protection.* Fifteen `# WORKING — do not change this code` flags were added across 6
files, marking every verified graph function. These flags prevent accidental modification during
future bug fixes, per the project's five mandatory pre-fix blocks.

**Key results:**
- 21 graphs reviewed, 7 passed, 11 fixed, 4 removed
- Net code reduction: −98 lines (370 added, 468 removed) across 9 files
- 15 WORKING flags protecting verified graph functions
- 3 bugs fixed: D5a right panel, D15 interp key, D18 extra argument

**Methodology notes for paper:**
- The multinomial likelihood scoring is now presented in maximum likelihood framing throughout,
  consistent with standard statistical practice. The paper should describe maximising the
  log-likelihood rather than minimising its negation.
- The period distribution (A4) was deemed redundant with the log₁₀P panel in the orbital
  histograms, supporting a streamlined presentation in the paper.

**Decisions:**
- Removed D11 3D/4D projections — simplified to 2D f_bin×π interpolation at best σ/logP
- Maximum likelihood framing globally (labels only, math unchanged)
- True 2D live heatmap in polling (not side-by-side 1D charts)

**Bugs found and fixed:**
- D5a right panel not rendering (logPmax_grid conditionally excluded — logic bug)
- D15 interpolation key mismatch (prefix naming inconsistency)
- D18 extra `{}` argument (call-site typo)
- None added to COMMON_ERRORS.md (all one-off, not greppable patterns)

**Open questions:**
- Full visual app test deferred to 2026-03-25 (all changes compile, not yet run in browser)
- K-S scoring graphs not reviewed yet (only Likelihood reviewed this session)

### 2026-03-25: Graph review round 2 — page layout overhaul + 9 graphs approved

**What was done:** Systematic visual review of all bias correction graphs with the user, reviewing each graph in exact rendering order. Applied 16+ fixes across 8 files. Major page reorganisation: all 4 likelihood heatmaps (normalized and unnormalized, f_bin×π and σ×logP_max) moved to the top of the results section as the primary visualisation. These render live during simulation runs (2-column layout for the normalised pair) and persist after completion showing the best-fit result.

**Key changes:**
- Summary table (A1): fixed σ_single and logP_max columns showing NaN (grid dimension ordering bug in `_build_extra_grids`), moved score to rightmost column as raw ln L instead of normalised likelihood (which was always 1.0), removed the single-method Agreement column.
- CDF comparison (A2): observed line changed from white to lightblue for visibility, gold annotation box removed (parameters moved into legend label including σ and logP_max), likelihood bin toggle added with light grey vertical lines, right-side truncation fixed with margin.
- Binary fraction vs threshold (A5): added green dashed "real threshold" vertical line at the crossing point where intrinsic f_bin meets the observed fraction curve.
- Methodology equations (A7): discovered that `model_type='cadence_dsilva'` was falling through to the old K-S methodology text from helpers.py instead of the updated likelihood version — fixed the condition to include cadence_dsilva.
- Model explorer (D17): replaced single metric with dual D4-style boxes (current vs global best), removed CDF error band, added 4 interactive heatmaps responding to explorer sliders.
- CDF sanity check (D18): fixed `simulate_delta_rv_sample` call signature (was using non-existent keyword arguments, silently caught by bare `except`).

**Error-check improvements:** Installed pyflakes for static undefined-variable detection. Created `scripts/test_render.py` runtime render test that loads a real .npz result, mocks Streamlit widgets with smart defaults, and calls all rendering functions end-to-end. This caught a shape-mismatch bug (4D→2D squeeze) that py_compile could not detect. Added both tools to CLAUDE.md Rule #1 as mandatory.

**LaTeX labels:** Applied HTML subscript notation (`f<sub>bin</sub>`) and Unicode symbols (π, σ, log₁₀) across all Plotly chart titles and axis labels. Streamlit table headers remain plain text as `st.table` does not render HTML.

**9 graphs approved and locked as WORKING:** H1 (norm f_bin×π), H2 (norm σ×logP), H3 (unnorm f_bin×π), H4 (unnorm σ×logP), A1 (summary table), A2+E6 (CDF + per-bin table), A5 (binary fraction), A6 (orbital histograms), A7 (methodology).

**Open questions:** Review continues from D4 onwards. The unnormalized heatmaps are not available as live data during runs (runner does not store logL_raw progressively) — deferred.

---

### 2026-03-26: LogL sign convention unification + graph review round 3

**What was done:** Resolved a pervasive inconsistency in the log-likelihood display convention. The multinomial log-likelihood (Dsilva+2023) returns ln L = Σ nᵢ ln(pᵢ) ≤ 0 (always negative; higher = better fit). Several UI components labelled the raw values as "−log L" despite displaying the actual (negative) logL values, while the interpolation section actively negated values and searched for the minimum. All displays and fitting routines were unified to show logL directly (negative values, higher = better, search for maximum).

**Key changes:**
- Parabolic fitting functions (`_parabolic_min_1d/2d/3d`) extended with a `find_max` parameter. When True, the functions use `nanargmax` for seed finding, require negative-definite Hessian (downward parabola), and apply appropriate sanity bounds for negative logL values.
- Removed the sign negation in `render_lk_scoring.py` (`_S_work = -lk_D_2d` → `_S_work = lk_D_2d`), ensuring the interpolation section operates on raw logL values.
- All user-facing labels changed from "−log L" to "log L" across 5 files (cadence.py, render_lk_scoring.py, render_lk_explorer.py, render_shared.py, GRAPHS_PER_METHOD.md).
- Removed redundant UI elements left over from the round 2 heatmap reorganisation: D4 metric cards (Current slice best / Global best), D5a raw logL heatmap (duplicate of H3), Log10(-log L) scale checkbox.
- Added 1D fallback for top heatmaps: when only σ_single or only logP_max is scanned (not both), the right column now shows a 1D line profile (max likelihood vs the scanned parameter) instead of being empty.
- Flagged D10 (3D Parabolic Surface) as WORKING.

**Methodology notes for paper:** The likelihood scoring now consistently presents ln L values (always ≤ 0) with the convention that higher values indicate better fits. The parabolic interpolation searches for the maximum of the log-likelihood surface. This is the standard statistical convention and avoids the confusion of double-negation (−(−ln L)) that arose from the earlier CvM minimisation framework.

**Bugs found and fixed:** No new COMMON_ERRORS patterns.

**Open questions:**
- Live run heatmaps (polling.py) still need the 1D fallback treatment (fix was applied to final results only).
- Cancel & Save button reported as non-functional; investigation shows partial .npz files are being created correctly but UI feedback may be unclear.
- Remaining MODIFY-status graphs: D9 (1D slices), D15 (auto re-sim), D17 (Model Explorer), D18 (CDF sanity), A3.

---

### 2026-03-30: Langer cadence tab — full graph review, code duplication, D14/D15/D17 fixes

**What was done:** Comprehensive graph-by-graph review of the Cadence Langer tab. All 27 graph elements (+ 11 D17 sub-elements) catalogued in GRAPHS_PER_METHOD.md. Five shared rendering files duplicated into Langer-specific copies to protect Dsilva's tested code. Three broken graphs fixed: D14 corner plot (axis ordering + constant-σ exclusion), D15 summary table (constant-σ row), D17 model explorer (langer2020 period model, deduplicated slider, margin fixes).

**Key results:** 12 Langer graphs approved WORKING (H1-H4, A1, A2, E6, E7, A5, A6, A7). D14, D15, D17 fixed → TO-TEST. D10 and D18 remain BROKEN.

**Methodology notes for paper:** The Langer 2020 period model (Case A/B mixture, weight_A=0.3) is now correctly used in the model explorer's CDF simulation. The `logP_max` parameter controls the upper period truncation. Primary grid axes for Langer: f_bin × logP_max (σ_single is secondary/constant).

**Decisions:** Never modify shared Dsilva code — duplicate first. Status after fix = TO-TEST; only user approves WORKING. Plan mode mandatory for all changes.

**Autosave feature:** Added automatic periodic checkpointing to the cadence simulation runner (`runners_cadence.py`). Every 120 seconds during a running simulation, the existing `_save_partial_cadence()` function is called to write a `.npz` checkpoint. After the first autosave, `resume_from_path` is updated so subsequent autosaves overwrite the same file rather than creating new ones. This covers both Dsilva and Langer models (shared runner). The autosaved partial files use the same format as Cancel & Save, so they appear in the partial results table and support Load/Resume/Delete operations.

**Open questions:** D10 parabolic surface needs Langer adaptation. D18 CDF sanity check needs cadence-aware simulation. Model comparison methodology (Dsilva vs Langer) and likelihood bin sensitivity analysis needed. Autosave visual indicator (toast/progress text annotation) not yet implemented.

---

### 2026-03-31 — σ_p2p significance criterion, spectrum page overhaul, Dsilva explorer bugfixes

**What was done:**
- **Measurement noise in bias simulation:** `simulate_with_params()` now adds per-epoch measurement noise via `_draw_measurement_noise()` and returns σ_p2p = √(σ_max² + σ_min²) at the epochs of maximum and minimum RV. For fixed error models, σ_p2p = √2 · σ_measure.
- **4σ significance criterion on all binary fraction vs threshold graphs:** Both simulated curves (`(ΔRV > T) & (ΔRV − 4σ_p2p > 0)`) and observed curves now apply the same significance filter. Prevents artificial 100% detection at threshold = 0.
- **Bartzakos correction:** All observed binary fraction curves now use N = 28 (denominator) with +3 known binaries in the numerator, giving a floor of 3/28 ≈ 10.7% at high thresholds.
- **Observed stair-step CDF added to Dsilva graph** (previously only Langer had it). White stairs using real obs_delta_rv data.
- **Explorer JSON bug fixed:** `result['settings']` in .npz files is a JSON string, not a dict. Fixed with `json.loads(str(...))` in both explorer files (E043).
- **Dsilva explorer: logP_max passthrough fix:** `_me_cdf_band()` now accepts and passes `logPmax` parameter to `BinaryParameterConfig`. Previously all explorer CDF bands used default logP_max=5.0 regardless of grid settings — verified with smoke test (19.4% CDF difference between logPmax=3.03 vs 6.0).
- **Dsilva explorer: heatmap visibility fix:** Explorer heatmaps now show for single-sigma runs (relaxed condition). Added 1D logP profile as secondary plot; fixed 4D→1D profile bug.
- **Dsilva explorer: f_bin table columns:** Results table now shows both "f_bin (max)" (argmax) and "f_bin (HDI)" (marginalized mode) as separate columns. Added runtime_seconds column.
- **Spectrum page complete overhaul:** Created `app/spectrum_helpers.py` (314 lines) with DIAGNOSTIC_LINES, LINE_PRESETS, absorption search functions. Implemented absorption depth heatmap + epoch difference plot for SB1/SB2 detection. Added LMC redshift correction toggle (v_LMC = 262.2 km/s) applied at all 6 wavelength conversion sites. Added show-all-epochs checkbox. Restructured page into 3 tabs (Spectrum / Max ΔRV / Classification) with independent selectors and session_state persistence. Added zoom history navigation (Back/Forward/Home + preset region buttons). Added scientific descriptions to all graph sections.

**Key results:**
- σ_p2p significance criterion now ensures consistency between simulated and observed binary fraction curves across all threshold values.
- logP_max slider in Dsilva explorer produces 19.4% CDF change (logPmax=3.03 vs 6.0), confirming correct passthrough.
- Bartzakos correction sets observed binary fraction floor at 10.7% (3/28) rather than 0%.

**Methodology notes for paper:**
- The significance criterion (ΔRV − 4σ_p2p > 0) is now applied identically in both the simulation pipeline and the observational analysis, following the same detection criteria described in the methods section. This was added to bias_correction.tex.
- For the fixed error model, σ_p2p = √2 · σ_measure (constant for all stars) since both epochs share the same error distribution.
- For distribution error models, σ_p2p uses the actual per-epoch noise magnitudes drawn from the error distribution.

**Decisions:**
- Show both argmax and HDI f_bin in explorer table (user chose both over argmax-only).
- Keep Plotly for spectrum page (st.pyplot renders static PNG only, no toolbar in browser).
- Max ΔRV tab gets independent star selector (not linked to main spectrum tab).
- Zoom history tracks preset jumps only (Streamlit limitation prevents capturing manual Plotly zooms).

**Bugs found and fixed:** E043 (result['settings'] JSON string vs dict), logP_max default passthrough in explorer CDF, 4D→1D profile dimension mismatch, heatmap visibility for single-sigma runs, IndexError in likelihood explanation when bins > 4 (hardcoded 4-element array vs dynamic bin count).

**Likelihood binning methodology (evening session):**
- Analysed D'Silva et al. (2023) Section 4.2 binning strategy: 4 coarse ΔRV bins `[0, 50, 250, 650, ∞]` km/s, designed for their 11 Galactic WNL stars. With our 25 LMC WC stars, finer binning (5–6 bins) is statistically justified — more objects per bin, more discriminating power in the multinomial likelihood.
- Evaluated data-driven binning (placing edges at observed CDF steps) vs fixed presets. Concluded that bin edges should be chosen *a priori* based on data structure and physical meaning — NOT optimised to maximise likelihood (which would be circular).
- Selected new bin edges: `[0, 15, 45.5, 150, 300, ∞]` (5 bins). Rationale: (1) 15 km/s separates wind-variability noise from real ΔRV; (2) 45.5 km/s is the detection threshold — physically meaningful binary/single boundary; (3) 150 km/s and 300 km/s correspond to observed CDF structure; (4) upper edge ~300 captures all observed data (max ΔRV ≈ 354 km/s).
- Added `L bins` column to the file browser result table, displaying the likelihood bin edges stored in each .npz result file.

**Open questions:**
- User has not yet visually confirmed the significance + Bartzakos graphs or the spectrum page overhaul — all features are TO-TEST.
- Langer simulation analogous fixes (from daily log: "issues with both Dsilva and Langer, only Dsilva addressed so far").
- Zoom history only tracks preset jumps, not manual Plotly scroll-zooms.
- Preset bin configuration UI not yet implemented — user wants to think more about methodology before committing to a preset system.
- Continuous CDF methods (Cramér–von Mises, Anderson-Darling) as alternatives to binned likelihood — discussed but not pursued.

---

### 2026-04-06 — Spectrum companion detection tools + RV Modeling settings persistence

**What was done:**
- Spectrum page: Added telluric (O₂ A/B-band, H₂O) and ISM (Ca II H&K, DIB 6284)
  diagnostic line groups for distinguishing interstellar absorption from companion
  signatures. Added comprehensive companion detection guide with detectable companion
  types, diagnostic absorption lines (Balmer, He I singlet/triplet, He II Pickering),
  companion-type packages, and TLUSTY model naming decoder. Binary classification
  info banner shows per-star ΔRV, σ, and significance for the selected line.
- Fixed FITS loading bug in raw spectrum viewer: `'ERR' in fit.data` raises TypeError
  on astropy `FITS_rec` structured arrays — changed to `'ERR' in fit.data.dtype.names`.
  Added E044 to COMMON_ERRORS.md.
- Added raw spectrum overlay (all bands on one plot) and stitched COMBINED view.
- RV Modeling page: Implemented full file-based settings persistence across all 6 tabs
  (~100+ widgets) using the existing `SettingsManager` pattern from the bias correction
  page. Every configuration widget now saves to `settings/user_settings.json` via
  `on_change` callbacks, reads defaults from JSON on page load. Settings survive
  browser refresh. JSON structure: `rv_modeling.{simulation, fitting.{parametric,physics},
  playground.{parametric,physics}, fraction_recovery, global_correction}`.
- Converted all `select_slider` and `slider` widgets to unrestricted `number_input`
  on the RV Modeling page per user request — no hard min/max limits on any setting.

**Key results:**
- No new scientific results this session — infrastructure and UI improvements only.

**Methodology notes for paper:**
- Companion detection methodology now documented in the webapp's Spectrum page guide:
  O, B, A-type companions detectable via absorption features in WR spectra;
  late-type (G/K/M) companions not visible against the strong emission continuum.

**Decisions:**
- Tab D (Sample Fit) instant sliders not persisted — they are auto-seeded from
  best-fit results and intended for quick exploration, not configuration.
- Playground distribution shape sliders remain as `st.slider` for instant visual
  feedback; all other config widgets use `st.number_input`.

**Bugs found and fixed:**
- E044: `'COL' in fit.data` on astropy FITS_rec raises TypeError; use `.dtype.names`.
- Settings save/load field name mismatch (e.g., `nsim` vs `n_sim`) causing silent
  persistence failures — not greppable, requires manual audit.

**Open questions:**
- Spectrum page state persistence still unsolved — Streamlit's page navigation
  behaviour prevents the `on_change` pattern from working as it does on bias
  correction and RV Modeling pages. May need `@st.fragment` or alternative approach.

### 2026-04-09 — Grid exclusion overhaul, CDF/Explorer consistency fixes

**What was done:**
Major overhaul of the bias correction analysis pipeline focusing on grid exclusion, CDF consistency, and Model Explorer accuracy.

- **Grid Range Exclusion (G1):** Completely rewrote `render_grid_exclusion` in `helpers.py`. Now provides range sliders for all grid axes (f_bin, π, σ_single, logP_max) with proper N-dimensional boolean masks matching the likelihood array shape (2D/3D/4D). Excluded regions appear blank (NaN) on all heatmaps. Best-fit star correctly updates to the best non-excluded point.
- **logP_max best-fit override:** `BinaryParameterConfig` for `gap_sim` (the simulation at the best-fit point) now uses the best-fit `ana_logPmax` from the grid search when logPmax is a scanned axis, instead of the sidebar default value.
- **Gold star placement:** Fixed `find_best_grid_point` in `shared.py` to use `np.nanargmax` instead of `np.argmax`, preventing NaN values from being selected as the maximum. Added all-NaN guard for fully-excluded slices.
- **CDF Comparison (A2) consistency:** The CDF comparison now uses the actual `BinaryParameterConfig` from the model context (with correct logP_max, period model, eccentricity model) instead of `BinaryParameterConfig()` defaults. Changed simulation size from n_obs (~25) to 1000 stars per seed for statistical stability.
- **Per-Bin Likelihood Breakdown (E6):** Fixed `_compute_pooled_sim` to use actual `n_sets` from the result file instead of a hardcoded 100 iterations. Also uses best-fit logP_max instead of default.
- **Model Explorer cadence-aware simulation:** Switched `_me_cdf_band` from `simulate_delta_rv_sample` (basic, 1000 stars, no cadence) to `simulate_delta_rv_cadence_aware` (uses actual observation cadences, matches grid runner). This makes Explorer logL scores directly comparable to grid logL scores.
- **Detection Fraction → Binary Fraction vs Threshold (D17j):** Upgraded the sparse 2-line Detection Fraction plot to a full-featured Binary Fraction vs Threshold chart (copy-pasted from `render_shared.py`), including missed binaries shading, singles shading, observed step function, intrinsic f_bin line, threshold crossing, gap annotation, and best-fit overlay.
- **`_build_extra_grids` fix:** Only includes grid axes with >1 value, preventing grid count / array dimension mismatch that caused the CDF and summary table to vanish for simple 2D runs.

**Key results:**
- Grid exclusion now functional across all 4 grid dimension combinations (2D, 3D sigma-only, 3D logPmax-only, 4D)
- Explorer logL scores now match grid logL scores (cadence-aware simulation)
- All CDF and per-bin statistics use correct model parameters

**Methodology notes for paper:**
- The multinomial log-likelihood is computed from cadence-aware simulations that respect each star's actual observation cadence (deterministic assignment: star i always receives cadence i). The Model Explorer now uses the same methodology for direct comparability.

**Decisions:**
- Range sliders (not multiselects) for all grid exclusion axes
- Explorer uses `simulate_delta_rv_cadence_aware` with actual cadences for logL comparability
- Copy-paste existing working code for the Binary Fraction plot rather than rebuilding from scratch

**Bugs found and fixed:**
- E043: `np.argmax` on NaN arrays returns index 0 (gold star at corner)
- E044: `dict.get(key, default)` returns None when key exists with None value (CDF crash)
- Grid/dimension mismatch in `_build_extra_grids` hiding CDF for simple runs
- `BinaryParameterConfig()` defaults used instead of actual model parameters in 3 places
- Hardcoded `range(100)` instead of `result['n_sets']` in per-bin table
- None-format crash in orbital histograms caption

**Open questions:**
- Langer tab grid exclusion: same code path but not user-tested yet
- Explorer Binary Fraction uses `simulate_with_params` (10k stars) on every slider move — potential performance concern

---

---

### 2026-04-13 — Exclusion-aware gap_sim + role-based agent team

**What was done:**
- **Exclusion-aware best-fit for orbital-property histograms.** Fixed an architectural ordering bug in the bias-correction cadence tabs: the 10k-star simulation feeding the Binary Orbital Properties histograms (`gap_sim`) was computed from the unmasked likelihood, so grid-exclusion sliders updated the heatmap best-fit but histograms stayed stale. Added a `_find_best_model()` helper in `app/bc/cadence.py` that extracts `{f_bin, pi, sigma_single, logP_max}` from a (possibly NaN-masked) likelihood array, and moved the grid-exclusion call to run *before* best-fit computation and `gap_sim` generation in both `_render_cadence_results` and `_render_cadence_results_langer`. `app/bc/subtabs.py::_render_analysis_plots` now prefers `ctx['best_model']` over legacy argmax lookups for histogram labels. For non-grid-searched axes (σ_single or logP_max), the helper reads `grid[0]` which equals the hardcoded parameter value. All 16 error-check phases passed (static, py_compile, import, smoke 2D/3D/4D/all-NaN/Langer, render).
- **Role-based agent team.** Built a 7-agent team (`coder`/opus, `qa`/sonnet, `designer`/sonnet, `plots`/opus, `scientist`/opus, `writer`/opus, `meta-tools`/sonnet) under `.claude/agents/` with embedded domain knowledge and a file-based inter-agent communication system (`.claude/agents/comms/`). Reorganised the skill layout: moved 13 existing skills from `.claude/skills/` into per-agent `.claude/agents/{name}-skills/` directories, added 6 new skills (paper-research, python-production, live-testing, testable-code, academic-writing, latex-helper), and trimmed the orchestrator's visible skills from 19 to 6. Created `memory/current_focus.md` for live session state and `memory/feedback_file_size.md` capturing the <300-line preference.

**Key results:**
- Grid exclusion now consistently propagates to the Binary Orbital Properties histograms in both Dsilva and Langer cadence tabs.
- Agent-team infrastructure in place; subagents cannot spawn subagents (Claude Code constraint), so the orchestrator coordinates role-specialised agents through the comms files.

**Methodology notes for paper:**
- None (infrastructure + UI-consistency fix only).

**Decisions:**
- Restructure render order (exclusion → best-fit → `gap_sim`) rather than compute `gap_sim` twice — no layout change since exclusion UI is already rendered between grid extraction and the heatmaps.
- Store `best_model` only in `model_ctx` (transient per render); `gap_sim` persistence is handled by the existing fingerprint cache.
- Role-based agent specialisation (coder/qa/designer/plots/scientist/writer) preferred over domain-based split (science/webapp) to match how the user delegates work.
- Agents isolate their skills via dedicated `-skills/` directories rather than `disable-model-invocation: true`, keeping the orchestrator context small.

**Bugs found and fixed:**
- Ordering bug: grid-exclusion mask was applied after `gap_sim` was built, causing stale orbital-property histograms under exclusion. Not greppable — no COMMON_ERRORS entry added.

**Open questions:**
- Does the new agent team perform well on real tasks? Needs validation in the next working session.
- Should the largest bias-correction modules (`cadence.py` ≈ 1566 lines, `analysis.py` ≈ 1203 lines) eventually be split, given the <300-line preference? Currently deferred due to breakage risk.
- Are the six newly authored skills (paper-research, python-production, live-testing, testable-code, academic-writing, latex-helper) complete enough, or do they need iteration after first use?

---

### 2026-04-14 — Intrinsic RV variability review, AIC/BIC model comparison, standalone apps, A&A plot audit

**What was done:**
- **Intrinsic RV variability literature review (§4b).** Compiled ~40 quantitative citations on single-star ΔRV variability in Wolf–Rayet stars and authored a new `§4b Intrinsic RV Variability of Single WR Stars and Period Range Justification` (6 subsections: wind-induced scatter by subtype, line-dependence, metallicity effects, minimum RV floor, period-range justification, threshold implications). Expanded `§5 Key Numbers` with six new rows (σ_w per subtype, minimum observed σ_RV, theoretical RV floor, logP_max constraints, longest known spectroscopic-binary period). `§6 References` grew from 5 to 22 entries (Chené, Crowther, Deshmukh, Dsilva I/II/III, Grassitelli, Kar, Koesterke, Langer, Moe & Di Stefano, Nazé, Sana 2012/2025, Sander & Vink, Schnurr, Shenar, Simón-Díaz, St-Louis, Vink & de Koter).
- **AIC/BIC model selection in the Compare tab.** Extended `_render_compare_tab()` in `app/bc/extras.py` so the best-fit comparison table reports raw `logL`, the number of free parameters `k`, and the information criteria `AIC`, `ΔAIC`, `BIC`, `ΔBIC` alongside the existing normalized likelihood. `k` is derived dynamically from the grid-axis sizes (> 1) so single-σ or single-logP_max runs get the correct penalty. N for BIC is the number of observed stars (25). Implementation stayed inside the Compare tab; the Dsilva and Langer tabs were intentionally untouched. `/error-check` passed pyflakes and render phases.
- **Standalone `spectrum_app/` and `rv_modeling_app/`.** Promoted the spectrum viewer and RV-modeling pages to standalone Streamlit apps (isolated imports, shared `settings/user_settings.json` via namespaced keys). The spectrum app gained a peak-to-peak epoch banner and toggle, diagnostic-line-group quick-zoom buttons with type-aware Y ranges (abs [0.5, 1.3], emission data-driven, ISM / telluric [0, 1.2]), ISE anchor/interp toggles on the unnormalized chart, an unnormalized COMBINED panel with raw-FITS fallback for non-COMBINED bands, and LMC velocity correction. The RV-modeling app gained Laplace and Generalised-Normal distributions for double-exponential histogram fitting, an auto-fit-all ranking banner with AIC/BIC expander and positive-x clamping, and a 9-panel orbital-histogram grid in Tab A. Fixed a `KeyError 'n_epochs'` arising from a producer/consumer dict-contract mismatch by tightening both sides and preferring `.get(key, default)` for cross-module dicts.
- **Scientific audit of `DIAGNOSTIC_LINES`.** Removed the misidentified `O V 5590`, moved `[O III] 5007` to a new *Nebular / Circumstellar* group, split `He II (hot companion)` into *OB companion absorption* and *WR emission*, and separated the oxygen block into distinct *WC* and *WO* diagnostic groups.
- **A&A plot-style enforcement.** Strengthened the plots-agent definition (`.claude/agents/plots.md`) with HARD RULE #1 (WCAG contrast), the A&A Journal Standards section, and a mandatory six-step review protocol. Caught a recurring white-axis-title bug by adding `title.font.color=black` to `_ACADEMIC_AXIS` and `theme=None` on every `st.plotly_chart()` call. Fixed 12 chart-call sites missing `theme=None`, 7 bare-string axis titles, and 12 `update_xaxes/yaxes` calls missing `title_font`.

**Key results:**
- Period range `logP ∈ [0.15, 5.0]` is well-justified for WC binaries: Dsilva WC best-fit `logP_max = 4.00`, RV-detection efficiency drops to ≈ 0% beyond `logP ≈ 4.5`, and the Deshmukh binary desert occupies intermediate periods.
- No minimum σ_RV should be imposed at zero: the observed floor is ≈ 1.8 km s⁻¹ (WR 3) and the theoretical floor is ≈ 2 km s⁻¹ (Grassitelli+2016). WC wind variability (0–6 km s⁻¹) is substantially lower than WN (5–15 km s⁻¹), so the 45.5 km s⁻¹ detection threshold remains very conservative.
- Raw `logL` is biased toward Dsilva because Dsilva has an extra free parameter (π). AIC/BIC are the correct model-selection signal for a Dsilva-vs-Langer comparison in this pipeline.

**Methodology notes for paper:**
- Cite WC-specific σ_w values from Chené, St-Louis, Crowther, and Schnurr when motivating the detection threshold in the Methods section.
- Report AIC/BIC (not raw max-logL) whenever comparing period models with different parameter counts. Document `k` counting: one DOF per grid axis with size > 1.
- Use `§4b` of `DOCUMENTATION.md` as the canonical reference for the period-range justification in the paper's Methods/Discussion.

**Decisions:**
- Use AIC/BIC as the primary Dsilva-vs-Langer model-selection signal; defer a flat-π nested comparison as a follow-up variant.
- Keep the existing normalized `Likelihood` column for continuity; add raw `logL` alongside, not in place of it.
- Restrict the AIC/BIC edit to the Compare tab (scope guardrail) — the individual cadence tabs remain untouched.
- Standalone apps share `settings/user_settings.json` with the main app via namespaced keys — accepted for dev use; no race conditions expected in single-developer workflow.
- Matplotlib/A&A style + WCAG contrast is now a standing rule for every Plotly chart; enforced at agent level via `plots.md`.

**Bugs found and fixed:**
- `KeyError 'n_epochs'` — producer/consumer dict-contract mismatch between the orbital-parameter simulator and the histogram renderer. Both sides fixed; the pattern is captured in `memory/feedback_dict_contract_bugs.md` rather than `COMMON_ERRORS.md` (design pattern, not a greppable typo).
- White axis titles on white backgrounds — caused by missing `title.font.color=black` on `_ACADEMIC_AXIS` and missing `theme=None` on `st.plotly_chart()` calls. Fixed globally in `app/spectrum_helpers.py` and captured in `memory/feedback_matplotlib_style.md` and `memory/feedback_aa_journal_style.md`.

**Open questions:**
- Is `simulate_binary_rvs_raw` in `wr_bias_simulation.py:817` skipping `_draw_measurement_noise`? Scientist flagged this as a possible bug in the Tab A raw-RV path — not yet confirmed.
- `rv_modeling_app/` is not yet committed; needs first-run validation before committing.
- Should the paper address the fixed `M₁ = 10 M⊙` assumption and the `q_max = 2.0` choice in the Methods? Only period and noise covered so far in the parameter-by-parameter review; eccentricity, mass ratio, primary mass, and inclination still to do.
- Does the strengthened plots-agent review protocol actually catch contrast regressions on first pass? Needs a real-task trial.

---

### 2026-04-19 — Bias-correction reliability sprint: Langer slider, resume-fingerprint, CDF helpers, agent-system overhaul, corner-plot audit

**What was done:**

Six interleaved sub-sessions, all centred on the bias-correction page's analysis pipeline plus a structural agent-system overhaul.

- **Langer-tab slider crash (E045).** When the Langer model fixes `σ_single = 7.5`, the grid axis collapses to a single value and `_make_range_slider` raised `StreamlitAPIException: max_value must be >= min_value`. Added a single-value guard at `app/bc/helpers.py:100-111`: when `lo >= hi`, display a static `st.markdown` label (`σ_single = 7.5 (fixed)`) instead of constructing a slider, and return `(lo, hi)`. Minimal surgical fix, no other edits.

- **Cancel-resume sim-context fingerprint guard (E046).** Cancel-saved cadence-aware grids could resume with a horizontal-row kink in the `f_bin × σ_single` likelihood heatmap, potentially faking a best-likelihood cell and biasing the corrected binary fraction. Root cause: `_save_partial_cadence` only stored `logL_raw` + grid axes + `n_sets` / `drv_bin_width` / `drv_max` / `adaptive_bins`, while `bin_cfg`, `sigma_meas`, `bin_edges`, `likelihood_bin_edges`, error-model config, `cadence_library`, and `obs_delta_rv` were re-pulled from current UI + `@st.cache_data` caches without validation. A page refresh or Streamlit-process restart (cache eviction) can recompute these to slightly different arrays, producing a systematic logL offset for post-resume cells. The Explore agent's "seed mismatch" hypothesis was checked against the code and rejected — per-cell seed is a pure function of `(i_lp, i_sig, i_fb, i_pi)` and the per-task RNG is freshly seeded inside the worker, so seeds are identical in fresh and resumed runs. The real fix added `_array_fingerprint`, `_cadence_lib_fingerprint`, `build_sim_context_signature`, `diff_sim_contexts` in `app/bc/helpers.py:99-170`; built `_sim_context` + `_sim_context_hash` once at run start in `app/bc/runners_cadence.py:97-115` and persisted both as new npz keys (`sim_context`, `sim_context_hash`) — additive, backward compatible. On resume, `app/bc/cadence.py` validates the signature and branches: `ok` → silent resume, `legacy` (old checkpoints with no signature) → yellow warning, `mismatch` → red `st.error` with field-level diff + "Start fresh" / "Cancel" buttons. Caught a follow-up Streamlit button-flow bug (`st.button` inside a conditional block dropped first click on rerun) and re-armed `_auto_resume` + `_resume_from` session_state before `st.stop()`. E046 added to `COMMON_ERRORS.md`. /error-check 16/16 PASS.

- **CDF alignment + step-band rendering bug (E047).** The top "CDF Comparison" plot used `simulate_delta_rv_sample` (non-cadence-aware, n_stars=1000) while the likelihood grid and Model Explorer use `simulate_delta_rv_cadence_aware` — different curves for the same best-fit. The top plot also omitted `shape='hv'`, so Plotly cubic-spline-smoothed the empirical CDF. Fix: top CDF now imports `_me_cdf_band` (and Langer twin `_me_cdf_band_langer`) so both CDFs compute from the same helper; preserved `bv = info['best_vals']` so Grid Range Exclusion reactivity stays intact (NaN-masked `_hm_result` flows through `_method_best_and_hdi` → `method_results`). User then caught a secondary rendering artifact: the dashed median visibly exited the 16–84 band because `fill='toself'` polygon edges were linearly interpolated while the median used `shape='hv'`. Fixed in 4 files by replacing the single `fill='toself'` polygon with two `shape='hv'` traces using `fill='tonexty'`. E047 added to `COMMON_ERRORS.md`. Two new rules in `.claude/references/learnings.md` under a new "Plot Rendering" section: (a) step line + step band must match, (b) first-glance plausibility is not enough — zoom into rendering details.

- **CDF/Explorer logL consistency fix (E048) — physics-config drift in re-sim helper.** Two symptoms survived the E047 fix: (1) top CDF flatlines at 0.5 from ~27 → 320 km/s, (2) heatmap's stored best `logL_raw = -33.467` disagrees with Model Explorer's "Global best logL = -34.39" at the same parameters, and (3) user manually found a higher-logL point in Explorer — algorithm "fails to find" best. Diagnosed directly (no Explore spawn): `_me_cdf_band` at `app/bc/render_lk_explorer.py:48-93` was building a fresh `BinaryParameterConfig(logP_max=logPmax)` internally, discarding every other field of the user's `bin_cfg` AND silently defaulting `period_model` to `"powerlaw"`. The grid worker `_single_grid_task_cadence_aware` at `wr_bias_simulation.py:1607-1626` uses the full user `bin_cfg` and the correct `period_model`. One bug → all three symptoms, because every CDF/logL the helper recomputes lives on a physically different surface than `logL_raw`. Supporting bug in `app/bc/runners_cadence.py:480-496`: result dict didn't persist `bin_cfg`, `period_model`, or `cadence_weights`, so downstream callers couldn't reproduce the grid cell even if they wanted to. Fix: result dict at `runners_cadence.py:480-514` now persists `bin_cfg` (via `vars(bin_cfg)`), `period_model`, `cadence_weights`, `cadence_library`, `sigma_meas`. `_me_cdf_band` (Dsilva + Langer twin) gained `_bin_cfg_dict` + `period_model` parameters and rebuilds the full `BinaryParameterConfig`, only overriding `logP_max` from the slider. All 4 callsites in `render_lk_explorer.py` + `render_shared.py:_render_all_methods_cdf` thread the new params; Langer twins mirrored — and `_me_cdf_band_langer` gained the missing cadence-aware branch (previously basic-only). Caption guarded by `np.isfinite(...)` so the legend no longer shows `logP_max=nan` for degenerate 1-point HDIs. New regression test `scripts/test_explorer_logL_consistency.py` asserts `|logL_raw[best_idx] − recomputed| < tol`. E048 added to `COMMON_ERRORS.md`. Three new rules in `.claude/references/learnings.md` Plot Rendering section: re-simulated plots must use the same `bin_cfg` / `period_model` / `cadence_weights` as the grid scoring worker; helpers that re-simulate must accept ALL physics-affecting params, not a subset; result-dict completeness contract — list every field a runner must persist. /error-check 17 PASS / 1 expected WARN (Streamlit-mock `KeyError`, pre-existing, covered by `test_render.py`).

- **Skill / plugin audit + agent-system overhaul.** Audited installed skills/plugins: only `ralph-loop@claude-plugins-official` v1.0.0 is registry-tracked; bundled CLI skills (`/simplify`, `/claude-api`, `/update-config`, `/loop`, `/schedule`, `/keybindings-help`, `/less-permission-prompts`) are not marketplace-installable. Three parallel Explore agents found the 7-agent system was defined Apr 13–14 but never operationalized: `qa`, `designer`, `writer`, `meta-tools` had 0 invocations in 6 days; comms folder all "(never)" timestamps; `CLAUDE.md` had zero delegation rules. Wrote plan v1 (lean: merge designer→plots, retire qa, kill comms). User course-corrected; v2 plan keeps all 7 agents, activates comms, makes `CLAUDE.md` reference-based, no cleanup. v2 approved. Created `.claude/references/comms-protocol.md` (canonical briefing + comms write contract, standard chains, QA-FAIL 3-round loop) and `.claude/references/agent-delegation.md` (trigger table, hard rules, decision flow, parallel spawn rules). Created `.claude/agents/comms/briefing.template.md`. Rewrote `.claude/agents/designer.md` (UI Loop role, reads user-taste feedback memory, output now includes Acceptance Criteria) and `.claude/agents/qa.md` (PASS / FAIL / BLOCKED verdict with concrete fix suggestions, removed duplicated checklist). Added comms-protocol pointer to all 7 agent files; added a 3-line `## Agents` section to `CLAUDE.md` (92→97 lines); added Agent Team pointers to `MEMORY.md`.

- **Corner-plot marginalization audit (no code changes).** User asked how the 1D / 2D marginal distributions in the corner plots are produced and whether the procedure matches Dsilva 2022. Scientist agent (paper-research skill) traced the data flow: joint grid `result['likelihood'] = exp(logL_raw − logL_max)` defined at `wr_bias_simulation.py:1561-1563` and `:1749-1751` is linear likelihood with max=1.0 (NOT integral-normalized); 1D marginals at `app/bc/corner_plots.py:197-201` use `np.nansum` along all nuisance axes, then `_add_1d_posterior` at `:37-38` renormalizes each curve via `np.trapezoid` so it integrates to 1; 2D marginals at `:204-223` use `np.nansum` over nuisance axes; HDI contours at 68% / 95% are computed from cumulative mass at `:72-81`. Same marginalization is reused by `_method_best_and_hdi` at `app/bc/analysis.py:110-113`. Compared with Dsilva 2022 §5.2 p.6 col.2: "Assuming flat priors... marginalised posterior likelihood." Figs 7 and 8 captions both state flat priors. Under flat priors posterior ∝ likelihood, so marginalizing the posterior reduces to integrating linear likelihood over nuisance axes — exactly what the code does. **Verdict: implementation is scientifically correct and matches Dsilva 2022.** Caveats flagged for future reference (not action items): `nansum` assumes uniform grid spacing; `exp(logL − logL_max)` underflows to 0 far from max (same Dsilva white-zone behaviour); we plot 68% + 95% contours, Dsilva plots only 68% (cosmetic deviation).

**Key results:**
- Bias-correction analysis pipeline now self-consistent: grid scoring, top CDF, Model Explorer CDF, and per-method best-fit summary all run through the same `_me_cdf_band` / `_me_cdf_band_langer` helper with the same `bin_cfg` + `period_model` + `cadence_weights`. `logL_raw` from the heatmap and `logL` recomputed in Explorer should now agree within ~0.3 at `n_sets ≥ 1000`.
- Resumed cadence-aware grids no longer risk a silent physics-config drift; any drift surfaces as a red `st.error` listing exactly which field changed (`bin_cfg.*`, `sigma_meas`, `obs_delta_rv_fp`, `cadence_lib_fp`, adaptive bin edges).
- Corner-plot marginalization confirmed correct under flat priors — matches Dsilva 2022 methodology — so reported `f_bin`, `π`, `σ_single`, `logP_max` modes + HDI68 are statistically defensible.

**Methodology notes for paper:**
- Result-dict completeness contract: every cadence-aware bias-correction `.npz` should carry `bin_cfg` (full dataclass), `period_model`, `cadence_weights`, `cadence_library`, `sigma_meas`, and the new `sim_context` / `sim_context_hash` checkpoint signatures, in addition to the previously stored `logL_raw` + grid axes + `n_sets / drv_bin_width / drv_max / adaptive_bins`. This makes any saved grid fully reproducible from the file alone.
- Re-simulation at any best-fit point (interpolated or grid) must use the same `bin_cfg` / `period_model` / `cadence_weights` / `cadence_library` / `sigma_meas` as the original grid scoring worker. Helpers that recompute scores or CDFs must accept all physics-affecting parameters, not a subset.
- Posterior marginalization explicitly assumes flat priors on `f_bin`, `π`, `σ_single`, `logP_max` — same convention as Dsilva 2022. 1D posteriors are normalized by `np.trapezoid` so they integrate to 1; 2D marginals use `np.nansum`; HDI68 contours come from cumulative-mass thresholding.

**Decisions:**
- "Validate-and-refuse with field-level diff" on resume drift, not "auto-rerun on mismatch" — surfaces *which* parameter drifted so the next reproduction pinpoints the trigger; matches the user's requirement that the simulation be consistent.
- Backward compat: legacy checkpoints without `sim_context` get a yellow warning and proceed (legacy path), not hard-fail.
- One-bug-three-symptoms framing for E048 kept the fix surgical: touched only the helper + its callers + the runner's result-dict build step. No restructuring of the WORKING-flagged `_render_lk_model_explorer` body — only the 4 callsite lines inside it. Overrode WORKING flags with explicit user permission; updated to `# UPDATED 2026-04-19: …` comments.
- `_bin_cfg_dict` kept `_`-prefixed (per E023) so Streamlit cache still hits across re-runs. Trade-off acceptable because cache is invalidated per result-load anyway.
- Caption `np.isfinite` guard done at the caption site, not inside `_method_best_and_hdi`, to keep the change localized — `nan` remains the correct mathematical answer for a degenerate 1-point HDI.
- Kept all 7 agents (user override of v1's merge/retire recommendation). QA always runs after coder when change touches UI / user-facing behaviour / data display. Designer is the first step of the UI loop and reads feedback memory for user taste. Comms activated (not killed) — broadcast via `comms/{agent}.md`, orchestrator writes `briefing.md`. `CLAUDE.md` stays minimal — rules go in `.claude/references/`, only pointed to from `CLAUDE.md`. No bulk cleanup performed.

**Bugs found and fixed:**
- E045: `st.slider` with `min_value == max_value` (Langer single-value σ_single grid) → guard with static label.
- E046: `st.button` inside a one-shot conditional block drops first click on rerun (cancel-resume "Start fresh" / "Cancel" buttons) → re-arm session_state before `st.stop()`.
- E047: Plotly `fill='toself'` band rendered with linear edges while paired step line uses `shape='hv'` → median visibly exits the 16–84 band; replace with two `shape='hv'` traces + `fill='tonexty'`.
- E048: Re-sim helper builds fresh `BinaryParameterConfig(logP_max=...)`, silently discarding `bin_cfg` and defaulting `period_model='powerlaw'` → systematic CDF + logL drift between grid scoring and display layer; thread the full `bin_cfg` + `period_model` and rebuild the config.
- Cancel-resume drift (no E-code): non-checkpointed inputs (`bin_cfg`, `sigma_meas`, `cadence_library`, `obs_delta_rv`, adaptive bin edges) re-pulled from `@st.cache_data` after page refresh / process restart drift to slightly different arrays → systematic logL offset for post-resume cells. Mitigated by `sim_context` signature persistence + on-resume validate-and-refuse.

**Open questions:**
- Next time the cancel-resume drift bug reproduces, the diff message will name *which* field drifted (`bin_cfg.*`, `sigma_meas`, `obs_delta_rv_fp`, `cadence_lib_fp`, adaptive bin edges). That output decides whether the upstream trigger is `@st.cache_data` eviction, page-refresh widget re-init, or something deeper in `cached_load_cadence` / `_render_cadence_adaptive_bins`.
- User must rerun a bias-correction grid (any size) so the new result-dict fields land in a fresh `.npz`, then visually verify: (1) top CDF tracks the observed curve across the full ΔRV range (not flat at 0.5); (2) Explorer's "Global best logL" matches the heatmap's stored value within ~0.3 at `n_sets ≥ 1000`; (3) caption no longer shows `logP_max=nan`; (4) same on the Langer tab.
- Pre-existing `NameError: xv` in `render_lk_explorer_langer.py:189` (Re-sim button path, inside `try/except`) — deferred (out of scope per "one file only / don't refactor nearby working code").
- Does the activated 7-agent comms system (designer → coder → QA loop, briefing + per-agent comms files) actually produce better outcomes on real tasks? Two real delegations today: (a) E048 fix briefed via `comms/briefing.md` round 1 → coder agent shipped end-to-end and the worklog landed in `comms/coder.md`; (b) corner-plot audit delegated to scientist (paper-research). Both completed cleanly. Needs more trials.
- Is the `_me_cdf_band_langer` cadence-aware branch added in E048 sufficient, or do other Langer-side rendering helpers still call the basic (non-cadence-aware) simulator?

---

### 2026-04-20 — Binning-robustness literature review, marginalization audit, validation-tab overhaul, Bin-Sensitivity sub-tab (uncommitted; visual sign-off pending 2026-04-22)

**What was done:**

Four interleaved sub-sessions, all probing the robustness and interpretability of the cadence-aware multinomial-likelihood bias-correction pipeline. None of the code changes have been committed — they sit uncommitted on `main` awaiting a visual-sign-off sweep on Guy's return on 2026-04-22.

- **Binning-robustness literature review (research only).** Delegated a targeted search to the `paper-research` agent on how bin count and bin placement affect binned-likelihood inference of $(f_\mathrm{bin}, \pi)$ for $N = 25$ stars. Identified a direct precedent: \citet{Dsilva2022} Sect.~5.2 used $4$ coarse bins at physically motivated edges for $N = 12$--$16$ WR stars. Confirmed that Sturges', Rice's, and Scott's rules all converge on $\sim 5$--$6$ bins for $N = 25$, so $10$--$20$-bin schemes would be noise-dominated (${\sim}\,50\,\%$ empty bins). Clarified that the binned (multinomial) likelihood of \citet{Cash1979} and \citet{Baker1984} is valid at any counts-per-bin, but loses discriminating power below ${\sim}\,5$ stars per bin. Designed a 5-step robustness test protocol: (i) bin-count sweep, (ii) edge-shift sweep, (iii) quantile-vs-physical-edge comparison, (iv) Anderson--Darling bin-free cross-check, (v) leave-one-out jackknife. Anderson--Darling stands out as the single highest-leverage addition — bin-free, demonstrated to outperform K--S at small $N$ by \citet{Engmann2011}. Full findings + citation list (Cash 1979, Baker--Cousins 1984, Feigelson \& Babu 2012, Engmann \& Cousineau 2011, D'Silva et al.~2020/2022, Sana et al.~2012/2013, Kobulnicky \& Fryer 2007) written to `memory/binning_robustness_research.md` and indexed in `memory/MEMORY.md`.

- **Marginalization audit (discussion only, no code changes).** Explained the full chain from the 5-D `logL_raw` grid to the reported 1-D posterior on $f_\mathrm{bin}$: flat priors $\Rightarrow$ posterior $\propto$ likelihood $\Rightarrow$ marginalize over nuisance axes $\Rightarrow$ normalize via trapezoid. Traced the pipeline step-by-step through the code: `multinomial_log_likelihood` at `wr_bias_simulation.py:1244` computes $\ln L = \sum_i n_i \ln p_i$; the max-shift at `wr_bias_simulation.py:1561-1565` uses `likelihood = np.exp(logL_raw - logL_max)` purely for numerical stability (the log-sum-exp trick; it does *not* produce a normalized PDF on its own); marginalization at `corner_plots.py:198` and `analysis.py:111` uses `np.nansum(p_nd, axis=sum_axes)`; the final PDF normalization at `corner_plots.py:37-38` and `wr_bias_simulation.py:1285-1289` uses `np.trapezoid`. Flagged that `nansum` (no $\Delta$ weights) is only correct on uniform grids; verified all grid axes ($f_\mathrm{bin}$, $\pi$, $\sigma_\mathrm{single}$, $\log P_\mathrm{max}$) are constructed as `np.linspace` in `params.py` — uniform by construction. Clarified the distinction between *grid axes* (what we marginalize over in post-processing) and *binary-parameter drawing distributions* (Langer period mixture, $q$ distribution, masses) — the latter are Monte-Carlo-integrated inside `simulate_with_params` at each cell, not by our `nansum`. Verdict: the current marginalization is mathematically correct for both the Dsilva and Langer cadence tabs; no code correction needed.

- **Validation-tab overhaul: mock preview + parameter-recovery diagnostics + A\&A white-bg styling.** Added `generate_mock_observations_detail()` to `app/bc/validation.py` — cadence-aware single-set mock that returns per-star `is_binary`, per-epoch RVs, $RV_\mathrm{min/max}$, $N_\mathrm{ep}$ alongside $\Delta$RV. Added a pre-run `_render_mock_preview` to the validation tab: side-by-side CDF + binary-fraction-vs-threshold plots with red (single) / green (binary) dots per star, plus a mock-star table (\#, Type, $N_\mathrm{ep}$, $RV_\mathrm{min/max}$, $\Delta$RV p2p, per-epoch RVs) with row-color highlighting. Added a clearer \textit{Simulation Parameters \& Recovery Run} section header above the delegated Dsilva/Langer run. Added `n_sets_override: int | None` kwarg to both `_render_cadence_dsilva_tab` and `_render_cadence_langer_tab` in `app/bc/cadence.py` (applied as default only when session-state key is unset); the validation tab now passes `n_sets_override = 500` (previously $10\,000$, which inflated config without need for validation runs). Built a new **Parameter Recovery Diagnostics** section post-run: three new functions `_render_validation_diagnostics`, `_render_panel_a_fbin`, `_render_panel_b_cdf`. Panel A = truth-vs-recovered table + $f_\mathrm{bin}(t)$ overlay with residual panel. Panel B = $\Delta$RV CDF overlay with 68\,\% HDI band from $200\times$ bootstrap of `gap_sim['delta_rv']` chunks of size $N_\mathrm{mock}$ + residual panel. `render_validation.py` grew from $\sim$\,330 $\to$ 1281 lines (above the CLAUDE.md $\sim$\,800-line soft cap); the file-split is deferred until after visual sign-off. The Langer truth-vs-recovered table greys out the $\pi$ row because $\pi$ is not scanned in the Langer model. Discovered and fixed a root-cause bug: `PLOTLY_THEME` is always dark in this project (`app/shared.py:171` hardcodes `_DARK_PALETTE`), so any plot using `PLOTLY_THEME` alone ships a dark figure and violates the A\&A white-bg rule. Converted all new diagnostic figures to explicit white-bg via a module-level `_AA_OVERRIDES` dict with WCAG-audited colors. Rewrote `.claude/agents/plots.md` (Plotly Theme Application section) with the `_AA_OVERRIDES` recipe, a subplot axis-name gotcha, and a mandatory exit checklist. Rewrote `memory/feedback_aa_journal_style.md` to surface the \textit{PLOTLY\_THEME-is-dark} trap, and added two new memory files: `memory/validation_cdf_vs_fbin_diagnostic.md` (scientific reasoning for why $f_\mathrm{bin}(t)$ beats CDF overlays for diagnosing $f_\mathrm{bin}/\pi$ mis-recovery at this sample size) and `memory/pending_test_validation_diagnostics.md` (visual sign-off checklist for 2026-04-22).

- **Bin-Sensitivity sub-tab — 4 new files, 6 A\&A-ready plots, mock-data validation mode (4 coordinated rounds).** Built end-to-end over four rounds of scientist $\to$ plots $\to$ designer $\to$ coder $\to$ QA coordination. \textbf{Round 1:} the scientist agent wrote `memory/likelihood_bin_sensitivity.md` --- an 8-paper lit review (D'Silva 2020/22/23, Sana 2012/13, Kiminki \& Kobulnicky 2012, Moe \& Di Stefano 2017, Langer 2020), 12 candidate bin-scheme builders with exact Python expressions, 6 statistical pitfalls P1--P6 specific to $N = 25$, and a derivation of why `logL_max` cannot be compared across schemes with different bin counts (use AIC or a bin-free K--S instead). The plots agent wrote 6 plot specs with a colorblind-safe palette; the designer wrote a tab-placement + 4-file plan. \textbf{Round 2:} the coder built four new files in `app/bc/`: `bin_schemes.py` (263 lines, 8 scheme builders); `bin_sensitivity_scorer.py` ($\sim$\,793 lines, a `SchemeResult` dataclass + MP-pool re-simulation with seed-stable reconstruction bit-identical to `runners_cadence.py:82-92`, plus the P1--P6 pitfall detector, K--S statistic, and HDI68); `bin_sensitivity_plots.py` ($\sim$\,746 lines, six pure Figure-returning plot builders, all A\&A-ready via `_academic_fig` from `app/plots/theme.py`); `bin_sensitivity.py` ($\sim$\,720 lines, the tab renderer itself). Surgical edits touched only `app/bc/__init__.py`, `app/bc/helpers.py` (new `_BIN_SCHEME_COLORS` + `get_scheme_color` helper), and `app/pages/05_bias_correction.py` (tab registration). QA verified that `_logL_one_scheme` matches `wr_bias_simulation.multinomial_log_likelihood` bit-identically (diff $= 0$), that the per-cell seed formula matches `runners_cadence.py:82-92`, and that the E048 full `bin_cfg` / `period_model` / `cadence_weights` / `sigma_meas` forwarding is intact. \textbf{Round 3 (bug fix + scope pivot):} the user tested end-to-end and reported \textit{"ran but nothing showed after the progress bar"} $\to$ root cause: `@st.fragment(run_every=1)` polled `job['status']` but never triggered a main-script rerun when status flipped to \texttt{done}, so `_render_results` never fired. Fixed with a one-shot `st.rerun(scope='app')` inside `_render_progress_fragment._poll()`, which is exactly the remediation E026 prescribes. The user also clarified the product scope $\to$ \textit{"I only choose bins manually"}. Removed all parametric-family multiselects (`equal_width`, `log_spaced`, `quantile`, `anchored`, `freedman_diaconis`) from the UI and replaced them with an editable scheme-row list: a locked `dsilva_default` row 0 and user-added rows with name + edges + delete button. The parametric scheme-builder functions in `bin_schemes.py` were retained as a library for potential future exposure. Removed the stubbed \textit{"Run fresh simulation"} option from the source radio. \textbf{Round 4 (polish + mock):} per the user-approved plan \texttt{/Users/guyshtainer/.claude/plans/i-really-liked-the-moonlit-flamingo.md}, all six plots are now A\&A paper-ready via `_academic_fig` (white bg, Times New Roman serif, black mirrored axes, no gridlines); plot \#4 got a `vertical_spacing=0.22` + manual annotations fix to stop title overlap; plots \#4 and \#5 gained explanatory captions --- the \#5 caption directly answers the user's scientific question about whether quantile (equal-count) binning is cherry-picking (it is not, quantile binning is a legitimate robustness cross-check as long as edges are fixed once-and-for-all before re-scoring and the simulated histogram is scored in the same edges). Mock-data mode added: a 2-option radio + 5 number\_inputs ($f_\mathrm{bin,true} = 0.46$, $\pi_\mathrm{true} = 0$, $\sigma_\mathrm{true} = 15\,$km\,s$^{-1}$, $\log P_\mathrm{max,true} = 5$, seed $= 42$) calling `generate_mock_observations()` from `validation.py`. Truth overlays on plots \#2 (gold star), \#4 (green dashed lines), and \#6 (top-right annotation). Summary table gains $\Delta f_\mathrm{bin}$ and $\Delta \pi$ columns in mock mode only. QA caught one regression on the final pass: subplot `yaxis2/3/...` did not receive the academic-theme \textit{no-gridlines} override, so secondary panels leaked grey gridlines $\to$ one-line fix at `bin_sensitivity_plots.py:615`. Final error-check: py\_compile + pyflakes + `scripts/test_render.py` all clean (5 PASS / 0 FAIL / 0 WARN). Plot \#6 (the bin-edge map) flagged STRONGLY APPROVED in `memory/plot_preferences.md` per user feedback.

**Key results:**
- Direct paper defence of the current 5-bin choice: \citet{Dsilva2022} Sect.~5.2 used 4 bins at physically motivated edges for $N = 12$--$16$ WR stars, and standard binning rules (Sturges, Rice, Scott) all converge on $\sim 5$--$6$ bins for $N = 25$. $10$--$20$-bin schemes would guarantee ${\sim}\,50\,\%$ empty bins and noise-dominate the posterior.
- Mathematical verdict: the current marginalization procedure (flat priors on $f_\mathrm{bin}$, $\pi$, $\sigma_\mathrm{single}$, $\log P_\mathrm{max}$; `nansum` over nuisance axes of the linear-likelihood grid; `np.trapezoid` for the final 1-D PDF normalization) is correct on the `np.linspace`-constructed uniform grid, for both the Dsilva and Langer tabs.
- New validation diagnostic: at $f_\mathrm{bin} \sim 0.5$ and $\pi \sim 0$, the ΔRV CDF overlay and the recovered CDF can be within $\sim$\,1\,\% of each other while the inferred $f_\mathrm{bin}$ or $\pi$ is off by $> 1\,\sigma$, because the CDF carries almost no information along the $f_\mathrm{bin}/\pi$ degeneracy direction. The new $f_\mathrm{bin}(t)$ overlay reveals this mis-recovery where the CDF overlay hides it --- which is why the validation tab now shows both panels and a truth-vs-recovered table.
- Scope-level scientific tool: the new Bin-Sensitivity sub-tab lets any future reviewer run the exact same grid against multiple bin schemes (manual only for now, plus the default) and visually compare the recovered $f_\mathrm{bin}$ and $\pi$ to the ground truth in mock-data mode. Six A\&A-ready plots make this robustness test paper-publishable.

**Methodology notes for paper:**
- \textbf{Bin-count defence.} At $N = 25$, ${\sim}\,5$ coarse bins is the statistically defensible choice. The paper should cite \citet{Dsilva2022} Sect.~5.2 as precedent (4 bins at physical edges for $N = 12$--$16$ WR stars) and quote Sturges / Rice / Scott's rule which all give $\sim 5$--$6$ bins for $N = 25$. At $N = 25$, finer than this yields ${\sim}\,50\,\%$ empty bins and noise-dominates the posterior; coarser than this loses discriminating power.
- \textbf{Validation diagnostic choice.} Recovery diagnostics should report BOTH a ΔRV CDF overlay AND an $f_\mathrm{bin}(t)$ overlay, not just the CDF. At our sample size the CDF is nearly degenerate along the $f_\mathrm{bin}/\pi$ direction, so overlay agreement to $\sim$\,1\,\% can coexist with $> 1\,\sigma$ parameter-recovery errors.
- \textbf{Posterior convention.} Flat priors on $f_\mathrm{bin}$, $\pi$, $\sigma_\mathrm{single}$, $\log P_\mathrm{max}$; posterior $\propto$ likelihood; 1-D marginals via `np.trapezoid` normalization; 2-D marginals via `np.nansum`; HDI68 from cumulative-mass thresholding. Same convention as \citet{Dsilva2022}.
- \textbf{Anderson--Darling cross-check (planned).} The robustness protocol recommends \citet{Engmann2011}'s Anderson--Darling as the single highest-leverage bin-free cross-check at small $N$; it beats K--S in detecting tail differences. Not yet implemented; flagged as the next scientific addition before paper submission.

**Decisions:**
- Keep all four rounds of today's code \textit{uncommitted} until the user runs a visual sweep on 2026-04-22. This is a deliberate break from the usual end-of-day commit because two of the four sessions added several thousand lines of UI (validation-tab overhaul + Bin-Sensitivity sub-tab) that require Guy's eyes on real and mock data before we trust them.
- Keep \textbf{$\sim$\,5 bins} as the paper's headline choice and defend it by citing \citet{Dsilva2022}; do \textit{not} bump to $10$--$20$ bins.
- Do \textit{not} modify the shared \texttt{render\_binary\_fraction\_vs\_threshold} or shared CDF renderers --- they are WORKING-flagged and the new validation diagnostic is a separate panel.
- Reuse the existing \texttt{gap\_sim} (built by \texttt{\_render\_cadence\_results} at best-fit) for the simulated CDF in Panel B rather than running a second simulation, so the diagnostic stays consistent with what the main tab shows.
- Narrow the Bin-Sensitivity sub-tab to \textit{manual schemes only} per the user's product requirement; keep the parametric scheme-builder library in \texttt{bin\_schemes.py} for potential future exposure.
- All six Bin-Sensitivity plots A\&A-ready at once via \texttt{\_academic\_fig} --- no per-figure dark/light toggle --- because the user wants paper-ready plots by default.
- Explicit \texttt{\_AA\_OVERRIDES} white-bg dict in \texttt{render\_validation.py} rather than relying on \texttt{PLOTLY\_THEME}, because \texttt{PLOTLY\_THEME} is hardcoded dark at \texttt{app/shared.py:171} and any plot using it alone violates the A\&A white-bg rule.
- Do \textit{not} implement the four remaining gaps from the scientist's plan (multiple $n_\mathrm{bins}$ per family in one run, \texttt{dsilva\_shift\_minus}, P3 \& P5 auto-detectors) --- user said \textit{"ignore the gaps for now"} mid-session.

\textbf{Bugs found and fixed:}
\begin{itemize}
\item Fragment polling did not trigger a main-script rerun when the background job's status flipped to \texttt{done}, so \texttt{\_render\_results} never fired and the progress bar stayed on-screen forever. Root cause + fix recipe are already covered by E026. Fixed with a one-shot \texttt{st.rerun(scope='app')} inside \texttt{\_render\_progress\_fragment.\_poll()}.
\item The academic theme applied \texttt{showgrid=False} only to the primary \texttt{xaxis}/\texttt{yaxis}, so secondary subplot axes (\texttt{yaxis2/3/\ldots}) leaked grey gridlines through on plot \#4. Fixed with a one-line sweep in \texttt{bin\_sensitivity\_plots.py:615}.
\item Agents following \textit{"use PLOTLY\_THEME"} verbatim shipped dark figures when the user wanted A\&A white-bg. Not a greppable Python pattern but an agent-behaviour bug. Resolved by adding an explicit \texttt{\_AA\_OVERRIDES} recipe to \texttt{.claude/agents/plots.md} and a mandatory exit checklist requiring the agent to state the background color and list every text element's color before declaring done. Recorded in \texttt{memory/feedback\_aa\_journal\_style.md} and elevated to the top of \texttt{.claude/references/learnings.md} under \textit{Plot Rendering}.
\end{itemize}
No new \texttt{COMMON\_ERRORS.md} entries today --- all three issues map to existing patterns (E026) or live in agent-behaviour memory rather than Python-pattern space.

**Open questions:**
- Do the new validation diagnostic panels actually reveal the $f_\mathrm{bin}/\pi$ mis-recovery visually on the real 25-star observed data, or only in the mock-data mode? To be answered by Guy's visual sweep on 2026-04-22.
- Does the Bin-Sensitivity sub-tab recover $(f_\mathrm{bin,true}, \pi_\mathrm{true})$ cleanly in mock-data mode across all five default schemes? Same 2026-04-22 sweep.
- Should the paper add a formal robustness appendix showing parameter recovery across $\geq\,3$ bin schemes (default + quantile + edge-shifted)? Probably yes, but only after the sub-tab sign-off.
- Whether to wire an Anderson--Darling bin-free score into the Bin-Sensitivity sub-tab and the main cadence tab as a bin-free cross-check. Recommended by the literature review but not yet implemented.
- Whether to add Dirichlet$(\alpha = 1)$ smoothing for bins where the simulation gives zero probability (multinomial $\ln 0 = -\infty$). Currently finessed by the \texttt{nansum} clip; a principled smoothing would be more defensible.
- Whether to split \texttt{render\_validation.py} (now 1281 lines) into a separate \texttt{render\_validation\_diagnostics.py} after sign-off. Deferred to avoid churn if panels need tweaks.

---

### 2026-04-23 — Validation-tab consistency overhaul (TODO 187 stages A–D), Bin-Sensitivity persistence + plot polish, RV-modeling error-model port, To-Do app render fixes (all uncommitted; visual sign-off pending)

**What was done:**

Four interleaved coding sprints, all still uncommitted on \texttt{main} pending Guy's visual sign-off. The day's work was dominated by the validation-tab consistency sweep that closes out TODO~187 --- a six-symptom user-reported bug list whose unifying root cause was an inconsistency between the heatmap argmax used for the live display and the marginal-mode statistic used for the summary table and corner-plot vertical lines.

\textbf{Validation tab --- consistency overhaul (TODO 187, stages A--D).} Six user-reported symptoms after a controlled mock run with $f_\mathrm{bin,true} = 0.85$, $\pi_\mathrm{true} = 0.9$, $\sigma_\mathrm{true} = 5\,$km\,s$^{-1}$, $\log P_\mathrm{max,true} = 4$: (1) the top-of-page best-fit CDF was flat instead of tracking the heatmap-best curve; (2) summary-table statistics ($f_\mathrm{bin} = 0.97$, $\pi = 2.33$, $\log P_\mathrm{max} = $ NaN) disagreed with the heatmap argmax ($f_\mathrm{bin} = 1$, $\pi = 0.45$, $\log P_\mathrm{max} = 6$); (3) corner-plot vertical lines disagreed with the summary-table HDI68; (4) manually setting the true mock parameters in the Model Explorer produced a higher logL than the algorithmically-found best; (5) the CDF Sanity Check showed all $50$ resampled CDFs sitting strictly below the mock observation, falsely failing the sanity test; (6) the Model Explorer x-axis was truncated at the maximum mock $\Delta\!\,$RV. The unifying root cause was a long-standing inconsistency between two summary statistics: the \textit{heatmap argmax} (used for the live display, the explorer x-y default, and the corner-plot vlines) and the \textit{marginal mode} (used for the summary table). Stage A --- best-fit CDF reads the stored \texttt{best\_median\_cdf} array instead of re-simulating, eliminating the flat-line symptom; an \texttt{\_obs\_label(result)} helper renames \textit{"Observed"} $\to$ \textit{"Mock Observation"} when \texttt{is\_validation = True} across more than fifteen plot files; the Explorer x-axis now extends across the union of all traces (mock + simulated). Stage B --- \texttt{runners\_cadence.py} now stores all four argmax parameters (\texttt{argmax\_fbin}, \texttt{argmax\_pi}, \texttt{argmax\_sigma}, \texttt{argmax\_logPmax}) in the result dict; the \texttt{logP\_max = NaN} bug is fixed; the marginal-mode key (\texttt{mode\_*}) is stripped from the result dict and from every reader (\texttt{extras.py}, \texttt{file\_ops.py}, \texttt{validation\_io.py}, \texttt{bin\_sensitivity\_plots.py}); the summary-table column is renamed \textit{"Joint argmax"}. Stage C --- the grid runner stores \texttt{n\_sets} and \texttt{grid\_seed}, and the Explorer reads them so its re-simulation is bit-stable against the grid (no more seed/$N_\mathrm{sets}$ drift). The new regression test \texttt{scripts/test\_grid\_vs\_explorer\_score.py} verifies $|\Delta\,\!\ln L| = 0.103$ within the 5.0 tolerance --- explaining the symptom-(4) report (the ${\sim}\,0.1$ logL variability is a Monte-Carlo noise floor, not an algorithmic miss). Stage D --- the CDF Sanity Check is rewritten to use $N = 500$ per draw (configurable) with the mock-CDF percentile band drawn from $50$ resamples; the mock observation is plotted in black inside the band rather than appearing to sit above it. Cleanup --- corner-plot \texttt{vline} sources are now the joint argmax (not the marginal mode), with caption + annotation honest; the pre-existing \texttt{xv}-undefined bug at \texttt{render\_lk\_explorer\_langer.py:230} is patched to use \texttt{sig}, with \texttt{logP\_max} added to the title.

\textbf{Validation tab --- A\&A theming sweep, mock/Explorer parity, mock\_results/ persistence, error-distribution chooser.} Three independent fixes in the same sprint. (i) The A\&A overrides dict \texttt{\_AA\_OVERRIDES} was missing the top-level \texttt{title.font.color} key, so figure titles stayed light-grey on plots that did apply the override. The fix --- adding the missing key, then applying \texttt{\_AA\_OVERRIDES} to the seven plots that had previously skipped it (mock-preview CDF + binary fraction, Model Explorer CDF, CDF Sanity Check, the analysis-side \texttt{\_render\_all\_methods\_cdf}, and both Likelihood-CDF twins) --- was the simpler half. (ii) The mock and Explorer CDFs were reported diverging because the mock sampler was inlined into \texttt{generate\_mock\_observations\_detail} while the Explorer used the canonical helper. Extracted the inlined sampler into a single helper \texttt{\_sample\_delta\_rv\_mock} in \texttt{validation.py}; gave \texttt{\_me\_cdf\_band} new \texttt{validation\_mode = True}, \texttt{validation\_seed} kwargs that route to the same helper with $n_\mathrm{sets} = 1$ when a validation context is detected via the session-state key \texttt{\{p\}\_val\_mock\_params}. New regression tests \texttt{scripts/test\_explorer\_mock\_equal.py} and \texttt{\ldots\_langer.py} verify byte-identical $\Delta\!\,$RV arrays in both Dsilva and Langer flows, with a $\sigma_\mathrm{meas} = 1$ vs $\sigma_\mathrm{meas} = 10$ regression guard so the noise-addition behaviour cannot silently change again. (iii) New module \texttt{app/bc/validation\_io.py} (567 lines) implements a separate persistence layer for validation runs in \texttt{mock\_results/}: \texttt{save\_validation\_result}, \texttt{save\_mock\_stars} (pickled dict keyed by star index with rvs/times/errs/is\_binary), \texttt{list\_validation\_results}, \texttt{load\_validation\_result}, \texttt{scan\_validation\_metadata}. The cadence runner gains a \texttt{save\_backend = 'mock\_results'} gate; \texttt{cadence.py} injects the backend choice from session-state; \texttt{render\_validation.py} grew a saved-runs table at the top of the Single-Point Recovery panel with Load/Delete/Resume buttons mirroring the cadence pattern. Auto-saves every 120\,s while a job is running, plus a final save on completion. (iv) The error-distribution chooser was ported from the Dsilva tab into the validation mock UI: \texttt{\_render\_one\_error\_model} from \texttt{extras.py} now drives the noise drawn into the mock observation via \texttt{\_draw\_measurement\_noise} from \texttt{wr\_bias\_simulation} (the same helper the Dsilva grid uses), with per-epoch errors stored as \texttt{errs = sigma\_measure} broadcast in \texttt{errs\_per\_star}. Explorer's \texttt{validation\_mode} reads the \texttt{(error\_model, error\_params)} from the expanded $8$-tuple \texttt{\_val\_mock\_params} so the byte-identical invariant survives the distribution choice.

\textbf{Bin-Sensitivity sub-tab --- save/load + autosave + persistence + plot polish + E050 deadlock fix (sprint 3).} Revived the previous chat's save/load work where the storage layer (\texttt{bin\_sensitivity\_storage.py}) was complete but the tab-side UI was half-wired (two broken call sites). The final implementation mirrors the cadence \texttt{\_render\_partial\_table} / \texttt{\_scan\_partial\_metadata} / \texttt{\_scan\_result\_metadata} from \texttt{file\_ops.py} verbatim --- new \texttt{list\_bs\_partials()} in storage; new \texttt{\_scan\_bs\_partial\_metadata}, \texttt{\_scan\_bs\_result\_metadata}, \texttt{\_render\_bs\_partial\_table}, \texttt{\_render\_bs\_results\_table} in the tab; a shared \texttt{\_hydrate\_loaded\_bs\_run} helper. Partial and final results are visually separated (final in the Saved-runs table, partials inside an expander); the action buttons are the same Load/Delete/Resume pattern. The saved-runs UI was originally lifted from \texttt{\_render\_results} (which only fires for an actively-completed job) up to a top-of-tab \texttt{\_render\_bs\_saved\_runs\_panel} called unconditionally inside a \textit{Saved runs} expander, so the user can load prior partials after a browser refresh. Custom user-defined bin schemes are persisted to \texttt{user\_settings.json} under \texttt{bin\_sensitivity.schemes} via an unconditional \texttt{\_persist\_schemes(rows)} on every render of \texttt{\_render\_schemes\_list} (the initial signature-gated approach was replaced with the bulletproof unconditional version after the user reported schemes failing to stick). Mock-truth parameters ($f_\mathrm{bin}$, $\pi$, $\sigma_\mathrm{single}$, $\log P_\mathrm{max}$, seed) are persisted under \texttt{bin\_sensitivity.mock\_params}. Silent \texttt{except: pass} blocks in the persistence helpers were removed; errors now surface via \texttt{st.toast(\ldots, icon='\!warning\!')} plus a \texttt{print()} fallback. A first-call-per-session debug \texttt{print('[bsn] \_persist\_schemes first call, N rows')} was added so Guy can verify the persist actually fires from his Streamlit terminal. The deadlock fix (E050): \texttt{\_run\_all\_schemes\_bg} was calling \texttt{rescore\_scheme\_cached} (decorated with \texttt{@st.cache\_data}) from a \texttt{threading.Thread}, and Streamlit's cache deadlocked on internal locks without a \texttt{ScriptRunContext}. The third scheme would hang at $9900 / 9900$ with zero CPU. The bypass calls the uncached \texttt{rescore\_scheme} directly from the bg runner and passes the already-loaded \texttt{ctx} so the .npz is not re-opened per scheme. Plot improvements: the CDF Overlay subplot titles now show two lines with the best-fit and HDI68 per scheme (Option A, U+2212 minus); the Posterior Shapes panel shades the 68\,\% HDI region per scheme with a matching \texttt{legendgroup} (line + shadow toggle together); all six plots received a readable-text bump (ticks $\geq 12\,$pt, titles $\geq 14\,$pt, legend $\geq 14\,$pt for $\geq 3$ subplots). E049 fix: a new \texttt{\_apply\_aa\_axes(fig)} helper standardises unscoped \texttt{update\_xaxes} / \texttt{update\_yaxes} calls --- a previous scoping bug had caused the left and right subplot columns to receive different axis defaults (one had gridlines, the other did not).

\textbf{RV-modeling app --- histogram fix + parametric summary + measurement-error model port (sprint 1).} On the \textit{Simulate Binary RVs} tab, the orbital-parameter $3 \times 3$ histogram grid showed sparse and spiky distributions because \texttt{compute\_physics\_diagnostics} was being called with $n_\mathrm{sets} = 1$ (${\sim}\,25$ binaries drawn for diagnostics), while the main RV generator uses $n_\mathrm{sim} = 100\,000$. The fix --- $n_\mathrm{sets,hist} = \lceil n_\mathrm{sim} / n_\mathrm{per\,set} \rceil$ --- makes the histogram population match the main simulation. On the \textit{Model Fitting} tab in Parametric mode, a best-fit Parameter Summary now reports the chosen distribution names plus per-parameter labels (sourced from the \texttt{\_PARAM\_META} table) for both single and binary stars, plus $N_\mathrm{epochs}$ and the random seed; Physics mode is unchanged. The single-star and binary-star measurement-error models from the bias-correction webapp were ported into Parametric mode: a \texttt{render\_error\_model\_pair} call appears after the distribution selectors; \texttt{compute\_model\_fraction\_curve} was extended with six new error kwargs (all safe defaults so existing callers are unaffected); the per-star Bernoulli class assignment plus per-class intrinsic draws (singles get \textit{one} intrinsic draw per star tiled across epochs --- a behaviour change from the prior per-epoch draws, scientist-approved on the grounds that single stars have no intrinsic epoch-to-epoch variation; binaries keep per-epoch independent intrinsic draws) are now followed by independent per-epoch noise via \texttt{\_draw\_measurement\_noise}. The full $2$-test detection criterion is applied on the simulated $\Delta\!\,$RV: $(\Delta\!\,\mathrm{RV} > t)$ \textit{and} $(\Delta\!\,\mathrm{RV} - 4 \sigma_\mathrm{pair} > 0)$ with $\sigma_\mathrm{pair} = \sqrt{2} \, \sigma_\mathrm{measure}$ per class --- matching the observed-curve construction at \texttt{page.py:49--59}. QA and scientist fact-checks confirmed all seven core scientific points. One open caveat (logged in TODO 188): for non-Gaussian noise distributions (gamma, weibull, lognormal, exponential, uniform), $\sigma_\mathrm{measure}$ is not the actual $1\sigma$ of the noise drawn by \texttt{\_draw\_measurement\_noise} (the code applies $|X|$ then a random sign), so the $\sigma_\mathrm{pair} = \sqrt{2} \sigma_\mathrm{measure}$ approximation and the $4\sigma$ criterion are miscalibrated for those models. Exact for \texttt{fixed} and \texttt{normal}.

\textbf{Standalone To-Do webapp --- launch documentation + render bugfixes (sprint 2).} Documented the launch command (\texttt{conda run -n guyenv streamlit run todo\_app.py --server.port 8502}) and the zsh \texttt{!}-history-expansion gotcha for the Hebrew \texttt{תואר שני!/} path (use single quotes, or \texttt{cd} first and run a relative path). Two render bugs identified from user screenshots: descriptions with embedded backticks were rendering as bright-green code spans (unreadable), and task \#185 was showing its priority as the literal string \textit{"none"} with description text bleeding into the priority column. The first was fixed by HTML-escaping the description and stripping backticks before passing to \texttt{st.markdown} in the \texttt{col\_title} renderer. The second was a parser bug: the description contained the substring \texttt{int $\backslash$ | none} and the embedded \texttt{|} broke the naive \texttt{line.split('|')[1:-1]} parser at \texttt{todo\_core.py:72}, shifting all subsequent columns. The \texttt{\_parse\_table\_rows} parser was hardened with a regex that splits on \texttt{|} only when not preceded by \texttt{$\backslash$} (\texttt{re.compile(r'(?<!\verb|\|)\verb|||')}) and then unescapes \texttt{$\backslash$|} $\to$ \texttt{|} per cell; an \texttt{\_escape\_cell()} helper in \texttt{save\_todos} pre-escapes every string cell across the Open / Done / Deleted tables; the corrupted row in \texttt{TODO.md} was repaired surgically (\texttt{int $\backslash$ | none} $\to$ \texttt{int or None}). Verified scope is the To-Do app only --- \texttt{app/todo\_core.py} has no importers outside \texttt{todo\_app.py} and \texttt{app/pages/10\_todo.py}, so the bias-correction page is untouched.

\textbf{Key results:}
\begin{itemize}
\item TODO 187 closed at the structural level: heatmap argmax, summary table, corner-plot vlines, and Explorer Re-sim now read the \textit{same} statistic --- the joint argmax. The marginal-mode statistic (\texttt{mode\_*}) is purged from the result dict and every reader. The summary-table column is renamed \textit{"Joint argmax"} to make the convention explicit.
\item Mock vs Explorer CDFs are byte-identical when the validation slider configuration matches the Explorer slider configuration (regression-tested for both Dsilva and Langer flows, including a $\sigma_\mathrm{meas}$ regression guard).
\item Grid-vs-Explorer logL agree within $|\Delta\,\!\ln L| = 0.103$ at the 5.0 tolerance --- the previous symptom (\textit{"manual sliders give a higher score than the grid best"}) is reduced to a $\sim$\,0.1\,logL Monte-Carlo noise floor at the current $N_\mathrm{sets}$.
\item New persistence backend \texttt{mock\_results/} for validation runs, separate from the cadence \texttt{results/} folder, so validation experiments do not pollute the production grid catalogue.
\item Bin-Sensitivity sub-tab is now reload-safe across browser refreshes: schemes, mock-truth parameters, and saved partials all survive a hard refresh.
\item E050 (silent deadlock when \texttt{@st.cache\_data} is invoked from a \texttt{threading.Thread}) added to \texttt{COMMON\_ERRORS.md} with grep pattern, fix recipe, and the bin-sensitivity-scorer found-in note.
\end{itemize}

\textbf{Methodology notes for paper:}
\begin{itemize}
\item \textbf{Honest-labels rule.} The pipeline reports a single posterior summary statistic --- the \textit{joint argmax} of the linear-likelihood grid --- with a 68\,\% HDI from the marginalised 1-D posteriors. The marginal mode is no longer reported anywhere because it can disagree with the joint argmax in correlated-parameter regimes (this is what produced the symptom-(2) summary-table inconsistency). Every per-parameter point estimate quoted in the paper is the joint argmax; every uncertainty is a 68\,\% HDI from the trapezoid-normalised 1-D marginal. This convention is enforced by the source code; see \texttt{memory/feedback\_honest\_labels.md} for the rule statement.
\item \textbf{Argmax--marginal-mode discrepancy as a covariance diagnostic.} When the joint argmax and the marginal mode of the same parameter disagree by more than the HDI68 width, the parameter is strongly correlated with at least one nuisance axis, and the marginal mode is misleading because it ignores the correlation structure. We expect this in the $f_\mathrm{bin}$--$\pi$ plane at $N = 25$.
\item \textbf{Explorer / grid noise floor.} At $N_\mathrm{sets} \geq 1000$ the Monte-Carlo noise on logL between the grid scoring and a re-simulation at the best-fit point is $\sim 0.1$ in $\ln L$. Manual-slider experiments that produce $\ln L$ improvements smaller than this floor should be interpreted as Monte-Carlo noise, not as algorithmic misses.
\item \textbf{Validation-tab CDF Sanity Check.} The mock observation is one realisation of the noise process; a sanity check that draws $N = 50$ resamples from the mock generator and overplots the $16$--$84$ percentile band gives a fair eye-test of whether the recovered best-fit lies inside the natural sampling envelope. The mock observation is plotted in black \textit{inside} the band so the user can immediately see whether the algorithm has recovered a typical realisation.
\end{itemize}

\textbf{Decisions:}
\begin{itemize}
\item Hold all four sprints uncommitted on \texttt{main} until Guy's visual sign-off. The validation overhaul touches more than 15 files and rewrites a load-bearing summary statistic; the bin-sensitivity persistence layer touches \texttt{user\_settings.json} on every render; the RV-modeling change makes a behavioural change to single-star intrinsic draws; the To-Do parser change touches the file format of \texttt{TODO.md} itself. Each carries non-trivial blast radius and the agreed practice (per \texttt{feedback\_no\_self\_approve}) is to wait for explicit visual approval.
\item Marginal-mode statistic is purged from the result dict, not just from the renderers, so no future code path can quietly resurrect it. This is a deliberate one-way ratchet.
\item Mock noise behaviour is to \textit{add} the noise to the simulated radial velocities, drawn from the user-chosen distribution --- not to record \texttt{sigma\_meas} as the reported uncertainty without applying it. This matches the Dsilva grid behaviour. Two wrong turns mid-session (interpreting \textit{"$\sigma_\mathrm{meas}$ is just the error"} as a no-noise instruction) cost two coder sprints; the regression guard in the byte-identical tests now prevents the noise behaviour from changing silently again.
\item The new \texttt{mock\_results/} persistence folder is separate from the cadence \texttt{results/} folder so validation experiments cannot pollute the production grid catalogue. Save format is \texttt{.npz} for the result table plus a sibling pickled dict for per-star mock observations (\texttt{allow\_pickle=True}, top-level key \texttt{stars} keyed by integer star index). The user explicitly chose the pickled-dict format to keep the per-star mock observation queryable from notebooks without round-tripping through the runner.
\item Schemes persistence in the Bin-Sensitivity tab uses an unconditional write on every render (not signature-gated): the JSON payload is $1$--$2\,$KB, the cost is negligible, and unconditional writes eliminate a whole class of cache-skip and signature-mismatch bugs. The earlier signature-gated attempt was reported as failing to persist, and after one round of code review (which found nothing wrong) the user correctly insisted that the lived experience trumps the static read. Bullet-proofing was the right answer.
\item Silent \texttt{except: pass} in any persistence layer is a permanent anti-pattern in this codebase; surface every persistence error to the user via \texttt{st.toast} plus a \texttt{print()} fallback to the Streamlit terminal. Logged in \texttt{.claude/references/learnings.md} under \textit{User Interaction}.
\item Always-visible Saved-runs UI on tabs that own a long-running background job: do not nest the load/save table behind an \textit{"active job"} gate, because a browser refresh wipes session\_state and would otherwise make the UI unreachable. Logged as a learning.
\item Three white-on-white trace lines inside WORKING-flagged blocks of \texttt{render\_lk\_explorer.py} (lines 973, 995) and \texttt{render\_lk\_explorer\_langer.py} (line 284) were left untouched pending explicit user authorization. Same for the \texttt{render\_validation.py} file split (now $1281$ lines, above the soft cap).
\end{itemize}

\textbf{Bugs found and fixed:}
\begin{itemize}
\item E049 --- Plotly subplot inconsistency from scoped axis updates: \texttt{fig.update\_yaxes(\ldots, col=1)} only targets the first column, leaving the second column's y-axis on auto-range and producing visibly inconsistent panels. Canonical pattern is now an unscoped \texttt{\_apply\_aa\_axes(fig)} helper. Found in \texttt{app/bc/bin\_sensitivity\_plots.py:\_plot\_cdf\_faceted}.
\item E050 --- silent deadlock when \texttt{@st.cache\_data} is invoked from a non-Streamlit \texttt{threading.Thread}: the cache-store path takes locks that the main thread may already hold while polling state; symptom is a worker that completes its compute and then hangs at the cache write. Fix: bypass the cached wrapper from background-thread call sites; reserve the cached wrapper for main-thread callers and add a NOTE comment forbidding bg-thread invocation. Found in \texttt{app/bc/bin\_sensitivity\_scorer.py:\_run\_all\_schemes\_bg}.
\item Validation-tab summary-table inconsistency: argmax / marginal-mode mismatch (TODO 187, six symptoms collapsed into one root cause). Not greppable but documented in \texttt{memory/feedback\_honest\_labels.md}.
\item \texttt{logP\_max = NaN} in result dict caption: argmax for the $\log P_\mathrm{max}$ axis was being computed via \texttt{np.nanargmax} on an array that contained no finite values when the axis had only one grid point. Fixed by storing \texttt{argmax\_logPmax} unconditionally during result-dict construction.
\item Mock vs Explorer CDF divergence: two independent samplers with the same nominal parameters can diverge at the $\sim$\,1\,\% level due to seed and noise-distribution differences. Fixed by collapsing both code paths onto the single \texttt{\_sample\_delta\_rv\_mock} helper with explicit \texttt{validation\_mode} kwargs.
\item RV-modeling \textit{Simulate Binary RVs} 3$\times$3 histogram sparsity: \texttt{compute\_physics\_diagnostics} was called with $n_\mathrm{sets} = 1$ for the histogram while $n_\mathrm{sets} \approx 4000$ was used for the main simulation. Fixed via $n_\mathrm{sets,hist} = \lceil n_\mathrm{sim} / n_\mathrm{per\,set} \rceil$.
\item To-Do app green-code-span and pipe-corruption: backticks in user-authored task descriptions rendered as bright green \texttt{<code>} spans; embedded \texttt{|} characters broke the naive split parser. Fixes: HTML-escape + backtick-strip on the renderer side; pipe-aware parser + escape-on-write on the storage side.
\item Pre-existing \texttt{xv} \textit{undefined name} bug at \texttt{render\_lk\_explorer\_langer.py:230}: patched to use \texttt{sig} (the parameter actually in scope) and \texttt{logP\_max} added to the title.
\end{itemize}

\textbf{Open questions:}
\begin{itemize}
\item Does the validation overhaul actually clear all six of the user's reported symptoms on a controlled mock run? Visual sign-off pending.
\item Does the RV-modeling parametric error-model port behave correctly with a non-Gaussian distribution choice? The exactness of the $\sigma_\mathrm{pair} = \sqrt{2} \sigma_\mathrm{measure}$ approximation is only proven for \texttt{fixed} and \texttt{normal}; for the others the \texttt{abs(X) + random sign} construction in \texttt{\_draw\_measurement\_noise} means $\sigma_\mathrm{measure}$ is no longer the actual $1\sigma$ of the noise. Two paths forward: accept the caveat and stick to \texttt{fixed}/\texttt{normal} for paper figures, or compute $\sigma_\mathrm{eff} = \sqrt{E[X^2]}$ per distribution.
\item Does the bin-sensitivity persistence layer survive every refresh path (hard refresh, browser-back, page-reload-during-run)? The bulletproof unconditional persist plus the visible toast on failure should make any remaining failure mode self-reporting.
\item Should \texttt{render\_validation.py} (now $1281$ lines) be split into \texttt{render\_validation\_diagnostics.py} now that the structural overhaul has settled? Deferred until after sign-off, to avoid churn during visual review.
\end{itemize}

---

*Last updated: 2026-04-23*
