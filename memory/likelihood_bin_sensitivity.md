---
name: Likelihood-bin sensitivity for bias correction
description: Reference note on how ΔRV-bin choice affects the binary-fraction posterior; schemes to test; diagnostic metrics; pitfalls for N=25
type: reference
created: 2026-04-20
author: scientist agent (Round 1 briefing on new Bin-Sensitivity sub-tab)
---

# Likelihood-Bin Sensitivity for the WR-LMC Binary-Fraction Bias Correction

## 0. Scope and motivation

The thesis infers the intrinsic binary fraction `f_bin` and the period power-law index `π` of the 25 "apparently single" LMC WC sample by scanning a 2-D grid of (`f_bin`, `π`) and, at each cell, computing a **binned multinomial log-likelihood** of the observed ΔRV distribution against a pooled Monte-Carlo simulation (Dsilva et al. 2023, Sec. 4.2 method; implemented in `wr_bias_simulation.py:1202-1244`).

The default bin edges are **four coarse bins**: `[0, 45.5, 250, 650, ∞]` km/s. This is the scheme Dsilva et al. (2022, 2023) used for samples of 11-16 Galactic WN stars. Our LMC WC sample has **25 stars** — roughly twice as many — yet we inherited the same four bins. The user's concern: *does doubling the sample not justify finer binning?* and *do the reported error bars change significantly under different bin choices?*

The point of the Bin-Sensitivity sub-tab is to re-score the **same** simulation under many binning schemes in one run, and let the user read off whether the best-fit cell and its HDI68 widths are stable against bin choice. If they are not, that is itself a scientific result worth reporting (and potentially an appendix figure in the paper).

---

## 1. Literature review — how binary-fraction studies handle bin choice

### 1.1 Dsilva et al. 2023 (A&A 674, A88) — **methodological anchor, WNL**

- **Bin scheme used:** `ΔRV < 50 | 50-250 | 250-650 | ≥650 km/s`. Four bins. Only the first three are populated in their sample of 11 northern WNL stars (2 objects in `50-250`, 2 in `250-650`, 0 in `≥650`).
- **Likelihood:** binned multinomial, `ln L = Σ n_i ln p_i` (their Sec. 4.2); the Dsilva+2023 text writes *"We divided the sample into various ΔRV bins as follows: ΔRV < 50 km s⁻¹ ... ΔRV ≥ 650 km s⁻¹ (no object)."*
- **Bin-sensitivity test performed:** **None.** No footnote, no appendix, no alternative scheme shown. The bin edges are stated as a fait-accompli.
- **Implicit rationale (reverse-engineered):** the first edge (50 km/s) equals their detection threshold *C*, which is justified independently in Sec. 4.1 as ~3× the peak-to-peak wind-variability for WR 136. The two interior edges (250, 650) align roughly with the inflection points of the observed CDF for their joint WNE+WNL sample (Dsilva+2023 Fig. 4). They are data-driven but not formally optimised.

### 1.2 Dsilva et al. 2022 (A&A 664, A93) — **same method, WNE + re-analysed WC**

- **Bin scheme used (WNE, 16 stars):** *identical* to Paper III: `<50 | 50-250 | 250-650 | ≥650 km/s`. Occupancies: `9, 4, 3, 0`.
- **Bin scheme used (WC re-analysis, 12 stars, Paper I data):** **different edges.** Quoting Sec. 5.3 of Paper II: *"The WC sample was separated into four ΔRV bins: 10 ≤ ΔRV ≤ 30 (six objects), 30 ≤ ΔRV ≤ 250 (no objects), 250 < ΔRV ≤ 300 (one object) and ΔRV ≥ 300 (no objects)."* → `[10, 30, 250, 300, ∞]`.
- **Implication for our project:** Dsilva themselves chose *different bin edges* for WC vs. WN without discussing why, and without any consistency check. This is direct evidence that the bin choice is ad-hoc and that a sensitivity audit is missing from the published methodology.

### 1.3 Dsilva et al. 2020 (A&A 641, A26) — **Paper I, original WC**

- **Likelihood:** **NOT a multinomial on binned ΔRV.** Paper I uses a **threshold-counting rejection criterion**: *"we reject combinations of orbital configurations and binary fractions that cannot reproduce a simple observational fact: six objects are observed with values of ΔRV between 10 and 30 km/s within 1σ."* This is a single-bin count constraint (`n_obs ∈ [10,30] km/s`), not a full likelihood. The upgrade to the 4-bin multinomial happens only in Paper II (2022).
- **Implication:** the multinomial-on-binned-ΔRV is a recent, not-yet-standardised technique in WR binary-fraction work. There is no community consensus on bin placement.

### 1.4 Sana et al. 2012 (Science 337, 444) — **O-star binary fraction**

- **Method:** Monte-Carlo with a compound merit function `Ξ' = P_KS(ΔRV) · P_KS(ΔHJD) · B(N_bin, N, f_bin^simul)` — product of a **K-S test on continuous ΔRV CDF**, a K-S test on time-sampling, and a **binomial** on the detected-binary count. **No ΔRV binning in the likelihood.**
- **Bin-sensitivity:** not applicable — the K-S statistic is bin-free by construction.
- **Relevance:** demonstrates the community's default goodness-of-fit statistic is K-S on the continuous CDF, *not* multinomial on bins. Dsilva's switch to multinomial-on-4-bins is the methodological outlier.

### 1.5 Sana et al. 2013 (A&A 550, A107) — **VLT-FLAMES Tarantula Survey O stars**

- Same KS × binomial compound merit function as Sana 2012. `f_bin = 0.51 ± 0.04` after bias correction.
- **Bin-sensitivity:** none mentioned; N/A due to bin-free KS.

### 1.6 Kiminki & Kobulnicky 2012 (ApJ 747, 41; arXiv:1203.2156) — **Cygnus OB2**

- **Method:** two-sided **Kolmogorov-Smirnov test on cumulative distributions** of mass ratio, log-period, and eccentricity. For ΔRV: *"We constrain the binary fraction by comparing the χ² probability density function for the simulated radial velocities to that of the Cyg OB2 data using a 2-sided K-S test."*
- **Bin-sensitivity:** none — K-S is bin-free.
- **Validation:** they tested the code on synthetic data and recovered input parameters to ±0.3 rms on power-law indices and ±5% on binary fraction. Useful as a **calibration target** for any new bin scheme we propose: a good scheme should at least match K-S performance on synthetic data.

### 1.7 Moe & Di Stefano 2017 (ApJS 230, 15) — **binary statistics review**

- Meta-analysis of many surveys, each with its own statistic. They caution (Sec. 9) that *"the velocity semi-amplitude K₁ criterion used in previous studies does not adequately describe the detection efficiencies of eccentric binaries."* i.e. the observable (ΔRV peak-to-peak, K₁, variance) matters more than the binning, but no paper they review validates a bin choice either.
- **Takeaway:** even the field's most-cited review does not propose a sensitivity protocol for ΔRV binning. Our proposed Bin-Sensitivity sub-tab would be a **methodological contribution** to the WR-binary literature, not just an internal diagnostic.

### 1.8 Langer et al. 2020 (A&A 638, A39) — **population-synthesis predictions**

- **No observed ΔRV binning** because this paper is theoretical (BPASS-style prediction of the OB+BH period distribution). Relevant here only because we use their 2-component Case-A/Case-B Gaussian-mixture log-P prior in our simulation. No methodological guidance on binning.

### 1.9 Summary of the literature state

| Paper | Sample N | ΔRV statistic | Bin scheme | Sensitivity test? |
|-------|----------|---------------|------------|-------------------|
| Dsilva 2020 (WC) | 12 | threshold count | single `[10, 30]` bin | no |
| Dsilva 2022 (WNE) | 16 | multinomial | `<50, 50-250, 250-650, ≥650` | **no** |
| Dsilva 2022 (WC re-do) | 12 | multinomial | `10-30, 30-250, 250-300, ≥300` | **no** |
| Dsilva 2023 (WNL) | 11 | multinomial | `<50, 50-250, 250-650, ≥650` | **no** |
| Sana 2012 | 71 | KS × binomial | **bin-free** | N/A |
| Sana 2013 | 360 | KS × binomial | **bin-free** | N/A |
| Kiminki & Kobulnicky 2012 | 114 | KS | **bin-free** | N/A |
| Moe & Di Stefano 2017 | meta | varies | varies | not discussed |

**Conclusion.** The binned-multinomial approach we inherited from Dsilva+2023 has never been validated in the literature for bin-choice sensitivity. This gap is the scientific justification for the Bin-Sensitivity sub-tab.

---

## 2. Proposed bin schemes (exact Python expressions)

The user needs 6-10 schemes that span the space: parametric (equal-width, log, quantile), physically-anchored (threshold + inflection), and rule-based (Freedman-Diaconis). Each is one line the coder can paste.

```python
import numpy as np
# obs = np.array of observed peak-to-peak ΔRV for the 25 stars.
#        For 25 LMC WC stars, approximate values expected:
#        max(obs) ≈ 500-800 km/s, median ≈ 40-100 km/s.
# thr = detection threshold, default 45.5 km/s.

BIN_SCHEMES = {
    # -- Anchor: the status-quo scheme we ship as default --
    "dsilva_default":      np.array([0.0, 45.5, 250.0, 650.0, np.inf]),
    # Rationale: direct reproduction of Dsilva 2022/2023 Sec 4.2.

    # -- Anchor: shift the interior edges by ±5 km/s and ±50 km/s (robustness check) --
    "dsilva_shift_minus":  np.array([0.0, 40.5, 200.0, 600.0, np.inf]),
    "dsilva_shift_plus":   np.array([0.0, 50.5, 300.0, 700.0, np.inf]),
    # Rationale: Pitfall P5 (edge-placement near a single observation can flip it
    # between bins and shift logL discontinuously). ±5 km/s < typical σ_ΔRV,
    # so the result should be stable. If it isn't, the choice is fragile.

    # -- Equal-width N bins from 0 to max(obs) + tail bin for [max_obs, ∞] --
    "equal_width_5":   np.r_[np.linspace(0.0, obs.max(), 5+1), np.inf],
    "equal_width_10":  np.r_[np.linspace(0.0, obs.max(), 10+1), np.inf],
    "equal_width_20":  np.r_[np.linspace(0.0, obs.max(), 20+1), np.inf],
    # Rationale: the simplest reasonable choice; tests whether the multinomial
    # likelihood even converges to a stable (f_bin*, π*) as N_bins grows.

    # -- Log-spaced from threshold to max(obs), with [0, thr] and [max_obs, ∞] --
    "log_spaced_5":  np.r_[[0.0], np.logspace(np.log10(45.5), np.log10(obs.max()), 5),  [np.inf]],
    "log_spaced_10": np.r_[[0.0], np.logspace(np.log10(45.5), np.log10(obs.max()), 10), [np.inf]],
    "log_spaced_20": np.r_[[0.0], np.logspace(np.log10(45.5), np.log10(obs.max()), 20), [np.inf]],
    # Rationale: orbital RV amplitudes span ~2 orders of magnitude (45 → 600+ km/s),
    # so log-spacing gives each decade equal resolution. Matches the physical
    # intuition that a star with K = 50 km/s and a star with K = 500 km/s are
    # equally different as a star with K = 50 km/s and one with K = 5 km/s.

    # -- Quantile-based (equal observation count per bin, Freedman-Diaconis style) --
    "quantile_5":  np.r_[np.quantile(obs, np.linspace(0,1,5+1)),  [np.inf]],
    "quantile_10": np.r_[np.quantile(obs, np.linspace(0,1,10+1)), [np.inf]],
    # Rationale: maximises statistical power by putting every observed star
    # in a bin with ~equal count. Caveat: with 25 stars, 10 quantile bins = 2-3 stars
    # per bin, which is close to the small-N regime where multinomial ≠ Gaussian.

    # -- Freedman-Diaconis rule: bin width = 2·IQR·N^(-1/3) --
    "freedman_diaconis": (lambda o: (
        np.r_[
            np.arange(0.0, o.max() + 2*np.subtract(*np.percentile(o, [75,25]))*o.size**(-1/3),
                      2*np.subtract(*np.percentile(o, [75,25]))*o.size**(-1/3)),
            [np.inf]
        ]
    ))(obs),
    # Rationale: classical statistics textbook rule for optimal histogram width
    # assuming a unimodal distribution (Freedman & Diaconis 1981).
    # NOTE: WR ΔRV is strongly bimodal (detected binaries cluster above the
    # threshold); expect FD to under-bin the binary side.

    # -- Physically-anchored on inflection points of observed CDF --
    "anchored_inflection": _compute_inflection_bins(obs, threshold=45.5),
    # Helper: see §2.1 below. Finds local maxima in the empirical density
    # (2nd-derivative zero-crossings) and uses them as interior edges.

    # -- User-custom (from text box in the UI) --
    "custom": _parse_custom_edges(user_input_string),
}
```

### 2.1 Helper: inflection-anchored bins

```python
def _compute_inflection_bins(obs, threshold=45.5, n_smooth=5):
    """
    Find ΔRV values where the empirical CDF has zero 2nd derivative (inflection).
    Use these plus [0, threshold, max_obs, ∞] as bin edges.
    """
    obs_sorted = np.sort(obs)
    cdf = np.arange(1, len(obs_sorted)+1) / len(obs_sorted)
    # Smooth & differentiate twice
    from scipy.signal import savgol_filter
    d2 = np.gradient(np.gradient(savgol_filter(cdf, n_smooth, 2)))
    # Zero-crossings of d2 = inflection points
    zero_crossings = obs_sorted[np.where(np.diff(np.sign(d2)))[0]]
    # Keep crossings above threshold and below max
    inflections = zero_crossings[(zero_crossings > threshold) &
                                 (zero_crossings < obs_sorted.max())]
    edges = np.r_[[0.0, threshold], inflections, [obs_sorted.max(), np.inf]]
    return np.unique(edges)
```

### 2.2 Count

That's **12 schemes** (dsilva_default, 2× dsilva_shift, 3× equal_width, 3× log_spaced, 2× quantile, freedman_diaconis, anchored_inflection) + `custom`. The UI should make 4-6 default-on and the rest opt-in checkbox.

---

## 3. Diagnostic metrics to compute per scheme

For every scheme the tab should report:

| Metric | Why it matters |
|--------|----------------|
| `(f_bin*, π*)` best cell | The central result. Is it stable across schemes? |
| `HDI68_width(f_bin)` | The reported error bar in the paper. If it halves under scheme X and doubles under Y, the reported ± is **entirely a bin-choice artefact**. |
| `HDI68_width(π)` | Same for the period index. |
| `logL_max` | **For within-scheme comparison only** — cannot be compared across schemes because the bin-count changes the constant `N!/∏n_i!` term (dropped in our implementation, see `multinomial_log_likelihood`). A scheme with more bins generally yields more negative logL for mechanical reasons, not because it fits worse. See §3.1. |
| `KS_stat` at best cell | **Bin-free cross-check.** If two schemes disagree on (f_bin*, π*) but both yield roughly the same K-S statistic against the observed CDF at their respective best cells, the disagreement is binning-driven, not physics-driven. |
| `n_obs` per bin (occupancy) | Flags degenerate schemes. If >50% of bins have n_obs=0, the likelihood is underspecified and most of its "signal" comes from the ε=1/N_sim floor. |
| `N_eff_bins` = count of bins with `n_obs ≥ 1` | The effective degrees of freedom. A 20-bin scheme where only 5 bins have data is a 5-bin scheme in disguise. |
| `n_obs` in the `[max_obs, ∞]` tail | If this is always 0 (true for our WC sample), the tail bin contributes nothing to logL and effectively wastes one bin. |
| **AIC-like penalty:** `logL_max - k · N_eff_bins` with `k=1` (AIC) or `k=ln(N_stars)/2` (BIC) | A cross-scheme comparison metric that penalises overfitting. |

### 3.1 Why `logL_max` cannot be compared across schemes (critical pitfall)

The full multinomial log-likelihood is

```
ln L_full = ln(N! / ∏n_i!) + Σ_i n_i · ln p_i
```

We drop the first term (`ln multinomial coefficient`) because it is model-independent *within a single bin scheme*. But it is **strongly scheme-dependent**: it depends on how the 25 observations are partitioned across bins. If we change schemes, the dropped constant changes, so the reported `Σ n_i ln p_i` values live on different offset scales.

**Consequence:** ranking schemes by `logL_max` is nonsense. A scheme with 20 bins will have most `p_i < 0.1`, so `ln p_i < -2.3` in every bin, and `Σ n_i ln p_i` will be ~25 · (-2.3) = -60 even for the best-fit model. A 4-bin scheme will have typical `p_i ~ 0.25`, `ln p_i ~ -1.4`, `Σ n_i ln p_i ~ -35`. This -25-unit difference is entirely a bin-count artefact.

**What IS valid across schemes:**
1. Compare the **best-fit cell** (f_bin*, π*) directly.
2. Compare the **HDI68 widths** directly.
3. Compare the **K-S statistic** at the best cell (bin-free).
4. Compare `AIC = 2·k - 2·logL_max` where `k = N_eff_bins` — this penalises bin count consistently.

**What is also valid within a single scheme:**
- Posterior ratios (Bayes factors) between grid cells of the same scheme are fully meaningful.
- HDI68 computation is entirely within-scheme and is comparable to Dsilva et al.'s HDI68.

---

## 4. Statistical pitfalls specific to N = 25

### P1. Empty bins → dominated by the ε floor

Our code floors empty simulated bins at `ε = 1/N_sim_pooled`. For `N_stars = 25, n_sets = 500` the pool is `12500` samples, so `ε = 8·10⁻⁵`. If `n_obs = 3` in a bin that the simulation predicts should be empty, the bin contributes `3 · ln(8·10⁻⁵) = -28` to the logL — a massive penalty that drowns all other information.

**Detection:** flag any scheme where the worst-bin penalty exceeds `|median(logL_bin_contrib)| × 5` in any best-fit cell.
**Mitigation:** increase `n_sets` so `ε < 1/(10·N_stars)`, or merge very-low-probability bins.

### P2. Bins above `max(obs_ΔRV)` contribute 0 to logL regardless of simulated density

Dsilva's top bin `[650, ∞]` has `n_obs = 0` for all three of their samples. Our WC sample's `max(ΔRV)` is below 650 as well, so this bin has **zero information** for us. The likelihood is identical whether the model predicts 0% or 50% of binaries above 650 km/s.

**Detection:** compute `n_obs_tail / sum(n_obs)`. Flag if this is 0 for all schemes. If yes, the bin-count report should include a warning: *"Tail bin [X, ∞] has no observed counts — effectively N_bins → N_bins-1."*

### P3. Too many bins → Poisson noise ≈ signal

For 25 stars in 20 bins, every bin has expected count ~1.25. The variance-to-mean ratio of the multinomial is ~1, so the logL variance per bin is comparable to the mean. The signal-to-noise degrades as bins increase.

**Detection:** run `equal_width_20`, `quantile_10`, `log_spaced_20` and compare their HDI68 widths to `dsilva_default`. If they blow up (HDI68 triples), it's Poisson-noise-limited; report the finer schemes as informative about *precision* but not recommended for the headline number.

### P4. Small-N multinomial ≠ Gaussian

Standard χ² tests require `n_i ≥ 5` per bin (Cochran's rule). With 25 stars and 4 bins, typical `n_i ~ 6` — borderline OK. With 10 bins it's `~2.5` — Gaussian approximation fails, and the posterior from the multinomial logL is **not** well-approximated by a 2-D Gaussian around (f_bin*, π*).

**Implication:** the HDI68 computed by marginalising the likelihood surface is the correct Bayesian credible interval, but standard-error-type interpretations ("1-σ") do not apply. The sub-tab should label intervals as "HDI68" not "1σ".

### P5. Bin-edge placement near a single observation can flip logL discontinuously

If an observed star has ΔRV = 249.0 km/s, the Dsilva edge 250 km/s puts it in bin 2 (`50-250`). Shift the edge to 248 km/s and it flips to bin 3 (`250-650`). The bin counts change, the logL surface shifts, and potentially the best cell moves. With 25 stars, a single-star flip changes bin counts by 4 percentage points.

**Detection:** the `dsilva_shift_minus/plus` schemes are designed to catch this. If the best cell (f_bin*, π*) moves by more than the grid spacing under a ±5 km/s edge shift, the choice is fragile.

### P6. Correlated observations (same star measured multiple times) are not independent

Not a binning pitfall per se, but a reminder: the 25 ΔRV values are peak-to-peak **across epochs of the same star**, so the 25 values are themselves summary statistics. Treating them as i.i.d. multinomial draws (which we do) is an approximation; Dsilva et al. do the same. The sub-tab does not need to address this, but the user should know our uncertainty estimates may be slightly underestimated for all schemes equally.

---

## 5. Test plan the coder will follow (Round 2)

1. **Load a recent** `cadence_dsilva_*.npz` result from `results/`. Currently these store `logL_raw[f_bin, π, σ_single]` but **not** the pooled ΔRV samples. Two options:
   - **Option A (re-simulate):** Re-run the simulation at evaluation time using the **same** `seed_base` and `n_sets` as the original run. This guarantees bit-identical pools. Needs `seed_base` to be persisted in the .npz (check — it isn't today).
   - **Option B (extend the result dict):** On the next full run, write pools to a new .npz (size: `N_grid × N_stars × n_sets × 8 bytes` = for a 49×50×500 grid with 25 stars ≈ 12 GB — infeasible). **Pick Option A.**

2. For each scheme in the chosen subset:
   - Compute `likelihood_bin_edges = scheme(obs, threshold=45.5)`
   - Re-score every grid cell: call `multinomial_log_likelihood(obs, pool_cell, likelihood_bin_edges)` — this is ~µs per cell, so the full grid re-scores in < 1 second.
   - Store `logL_raw_scheme[f_bin, π]` (σ_single collapsed to its best value at the default scheme's best cell, or profiled).

3. For each scheme compute:
   - `(f_bin*, π*)` = argmax of `logL_raw_scheme`
   - Marginalise → `HDI68_fbin`, `HDI68_pi` via `compute_hdi68()` from `wr_bias_simulation.py:1251`.
   - `logL_max`
   - `KS_stat` at best cell = `scipy.stats.ks_2samp(obs, pool_at_best_cell).statistic`
   - Bin occupancy `n_obs_bins`, `N_eff_bins`
   - `AIC_relative = -2·logL_max + 2·N_eff_bins`

4. Populate the comparison table (plots agent specifies the plots).

5. **Flag schemes** that trigger any of P1-P5. Rendering: a 🔴/🟡/🟢 status column on the summary table (or, per project feedback: no emoji — use a `WARN`/`FLAG` text column instead).

6. **Report** to the user: the paper's headline number is the median `f_bin*` across the green-flagged schemes, with `HDI68_width` being the **envelope** of HDI68s across those schemes (i.e., the union interval). This is conservative and honest.

---

## 6. Open methodological flags

### NOT-invalidating (the sub-tab is useful):
- Dsilva's binned-multinomial approach is not a standard. The sub-tab is a methodological contribution.
- Our 25 stars are 2× more than Dsilva's WN samples, so finer binning is defensible — but pitfalls P3-P4 may still bite.

### Worth discussing in the paper's appendix:
- We propose reporting both the Dsilva-default result (for direct comparability) **and** the envelope across schemes (for honesty about bin-choice sensitivity).

### NEEDS-INPUT from user (possible future direction, outside this sub-tab):
- Should we consider **abandoning the multinomial entirely** in favour of K-S on the continuous CDF (Sana 2012/2013/Kiminki 2012 style)? That would eliminate the binning question but lose the Bayesian-posterior structure Dsilva established. Worth a separate conversation — but not this sprint.

---

## 7. References

- **Dsilva, K., Shenar, T., Sana, H., Marchant, P.** 2020, *A&A*, 641, A26. "A spectroscopic multiplicity survey of Galactic Wolf-Rayet stars. I. The northern WC sequence." DOI: [10.1051/0004-6361/202038446](https://doi.org/10.1051/0004-6361/202038446).
- **Dsilva, K., Shenar, T., Sana, H., Marchant, P.** 2022, *A&A*, 664, A93. "A spectroscopic multiplicity survey of Galactic Wolf-Rayet stars. II. The northern WNE sequence." DOI: [10.1051/0004-6361/202142729](https://doi.org/10.1051/0004-6361/202142729). *Local copy:* `papers/Dsilva et al. - 2022 - ... WNE sequence.pdf`.
- **Dsilva, K., Shenar, T., Sana, H., Marchant, P.** 2023, *A&A*, 674, A88. "A spectroscopic multiplicity survey of Galactic Wolf-Rayet stars. III. The northern late-type nitrogen-rich sample." DOI: [10.1051/0004-6361/202244308](https://doi.org/10.1051/0004-6361/202244308). *Local copy:* `papers/Dsilva et al. - 2023 - ... WNL sequence.pdf`.
- **Sana, H., de Mink, S. E., de Koter, A., et al.** 2012, *Science*, 337, 444. "Binary Interaction Dominates the Evolution of Massive Stars." arXiv:[1207.6397](https://arxiv.org/abs/1207.6397). DOI: [10.1126/science.1223344](https://doi.org/10.1126/science.1223344).
- **Sana, H., de Koter, A., de Mink, S. E., et al.** 2013, *A&A*, 550, A107. "The VLT-FLAMES Tarantula Survey. VIII. Multiplicity properties of the O-type star population." DOI: [10.1051/0004-6361/201219621](https://doi.org/10.1051/0004-6361/201219621). ADS: [2013A&A...550A.107S](https://ui.adsabs.harvard.edu/abs/2013A%26A...550A.107S/abstract).
- **Kiminki, D. C., Kobulnicky, H. A.** 2012, *ApJ*, 747, 41. "An Updated Look at Binary Characteristics of Massive Stars in the Cygnus OB2 Association." arXiv:[1203.2156](https://arxiv.org/abs/1203.2156).
- **Moe, M., Di Stefano, R.** 2017, *ApJS*, 230, 15. "Mind Your Ps and Qs: The Interrelation between Period (P) and Mass-ratio (Q) Distributions of Binary Stars." arXiv:[1606.05347](https://arxiv.org/abs/1606.05347). DOI: [10.3847/1538-4365/aa6fb6](https://doi.org/10.3847/1538-4365/aa6fb6).
- **Langer, N., Schürmann, C., Stoll, K., et al.** 2020, *A&A*, 638, A39. "Properties of OB star-black hole systems derived from detailed binary evolution models." *Local copy:* `papers/Langer et al. - 2020 - ...pdf`.
- **Freedman, D., Diaconis, P.** 1981, *Z. Wahrscheinlichkeitstheorie verw. Gebiete*, 57, 453. "On the histogram as a density estimator." — rule for optimal bin width.
- **Zucker, S.** 2003, *MNRAS*, 342, 1291. "Cross-correlation and maximum-likelihood analysis: a new approach to combining cross-correlation functions." — the RV-measurement technique underlying every ΔRV value we bin.

---

## 8. Next-chat continuity hook

If the user starts a new chat on likelihood-bin sensitivity, point them to this file and to `.claude/agents/comms/scientist.md` from the 2026-04-20 round. The live questions to pick up:
1. After the sub-tab is built, run the 12 schemes on the production .npz and tabulate HDI68 envelope.
2. Decide whether to report Dsilva-default + envelope, or switch the headline to a bin-free K-S result.
3. Consider adding an appendix figure to the paper showing the HDI68-vs-N_bins sensitivity curve.
