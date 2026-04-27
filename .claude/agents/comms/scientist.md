# Scientist — Round 1 (Bin-Sensitivity Sub-Tab)

_Last updated: 2026-04-20_

## Scientific Assessment

### The headline finding (for the orchestrator)

**The Dsilva et al. 2022/2023 binned-multinomial likelihood on 4 ΔRV bins has never been validated for bin-choice sensitivity in the WR binary-fraction literature.** Every other major comparable study (Sana 2012, Sana 2013, Kiminki & Kobulnicky 2012) uses **bin-free Kolmogorov-Smirnov** instead. The Dsilva series itself uses **different bin edges for their WC re-analysis (`[10, 30, 250, 300, ∞]`) than for their WNE/WNL samples (`[0, 50, 250, 650, ∞]`)** without discussing why. Building the Bin-Sensitivity sub-tab is therefore **not** a paranoid internal audit — it is a **methodological contribution** worth an appendix section in the thesis/paper. If the sub-tab reveals that HDI68 widths swing by 2x or more across reasonable bin schemes, we should report that result honestly, not hide it.

### Is the multinomial likelihood the right tool at all? (NEEDS-INPUT, but not blocking)

Flagging for future discussion: a serious question is whether we should follow the dominant community practice (bin-free K-S on the continuous CDF) rather than refine the binned multinomial. K-S eliminates the bin question entirely. Against: K-S makes Bayesian-posterior marginalisation less clean than the multinomial, and we would lose direct comparability with Dsilva. **Recommendation for this sprint: keep multinomial for the sub-tab, but the sub-tab should include a K-S statistic at each scheme's best cell as a cross-check. A full switch to K-S is a separate decision.**

### The eight schemes I recommend by default

See `memory/likelihood_bin_sensitivity.md` Section 2 for all 12 candidates + exact Python expressions. The four that MUST be on-by-default:
- `dsilva_default` — `[0, 45.5, 250, 650, inf]` — the status quo.
- `dsilva_shift_plus` — `[0, 50.5, 300, 700, inf]` — robustness check for edge-flip pitfall.
- `equal_width_10` — 10 bins `linspace(0, max_obs)` + `inf` tail — the simplest "what if we use more bins" test.
- `log_spaced_10` — log-spaced — the physically-motivated "equal resolution per decade" test.

Four more that should be available but not default-on: `equal_width_5`, `equal_width_20`, `quantile_10`, `anchored_inflection`.

## Key Data Points

| Quantity | Value | Source |
|----------|-------|--------|
| Sample size N | 25 LMC WC stars (excluding 3 Bartzakos binaries) | `specs.py`, briefing |
| Detection threshold | 45.5 km/s | CLAUDE.md; Dsilva 50 km/s shifted for our noise floor |
| Default bins today | `[0, 45.5, 250, 650, inf]` (4 bins) | `wr_bias_simulation.py:1191` |
| Typical `max(obs_dRV)` | 500-800 km/s | WC expectation |
| eps-floor today | `1/N_sim_pool` ~ 8e-5 (for n_sets=500, 25 stars) | `wr_bias_simulation.py:1240` |
| Dsilva WNL 2023 bin occupancies | 7, 2, 2, 0 (out of 11) | Dsilva+2023 Sec 4.2 |
| Dsilva WNE 2022 bin occupancies | 9, 4, 3, 0 (out of 16) | Dsilva+2022 Sec 5.2 |
| Dsilva WC 2022 re-do bin edges | `[10, 30, 250, 300, inf]` — **different scheme** | Dsilva+2022 Sec 5.3 |
| Best-fit Dsilva WNL | f_bin = 0.42 (+0.15, -0.12), pi = -0.70 (+0.73, -1.02) | Dsilva+2023 Fig 3 |
| Our current result (LMC WC) | f_bin ~ 0.46 observed, bias-corrected ~ 0.5-0.7 | project memory |

## Recommendations

### For the orchestrator (Round 2 briefing to coder + QA)

1. **Pools are not persisted in current .npz files**, only `logL_raw`. The coder must pick between:
   - **Option A (recommended):** re-simulate at scheme-evaluation time using the same `seed_base` and `n_sets`. Fast (~1 s per scheme on the existing grid). Requires persisting `seed_base` in the .npz going forward.
   - **Option B (rejected):** persist pools. ~12 GB per run. Infeasible.

2. **The new tab must scan schemes serially on the same simulation, not run multiple full grids.** Re-scoring is cheap; re-simulating is not. Design fragment so that the "simulate once" step is cached, "re-score with scheme X" is a fast inner loop.

3. **The comparison table is the headline UI.** Columns must include (in this order): scheme name, N_bins, N_eff_bins (non-empty), f_bin*, HDI68(f_bin) width, pi*, HDI68(pi) width, logL_max (within-scheme only), K-S stat at best cell, AIC = 2*N_eff - 2*logL_max, status flag (OK / WARN / FAIL). See `memory/likelihood_bin_sensitivity.md` Section 3.

4. **CRITICAL: do NOT rank schemes by `logL_max`.** The dropped multinomial-coefficient constant depends on bins, so cross-scheme logL comparison is meaningless. Report logL for **within-scheme HDI** only. Cross-scheme comparison uses AIC and K-S. `memory/likelihood_bin_sensitivity.md` Section 3.1 has the full derivation for the paper appendix.

5. **Report pitfall flags in the status column.** See `memory/likelihood_bin_sensitivity.md` Section 4 for the 6 pitfalls. Each scheme should be auto-flagged if it triggers any of P1-P5.

6. **The "headline" paper number should be:** median `f_bin*` across green-flagged schemes, with HDI68 width = envelope (union) across those schemes. This is a conservative, honest report.

### For the plots agent (already briefed, but for cross-reference)

The plot I most want to see: **HDI68_width(f_bin) vs. N_bins** with one marker per scheme, colour-coded by scheme family (parametric vs. anchored vs. quantile). This is the headline sensitivity figure for the paper appendix. The plots agent should make this one plot first and the rest follow.

### For the writer agent (Round 3 or whenever the sub-tab is ready)

If the sub-tab shows HDI68 stability (say, all widths within +/-15% of Dsilva default), the paper just cites Dsilva's bin choice and adds one sentence: *"We verified that the HDI68 widths are stable to +/-15% under a range of alternative bin schemes (see Appendix X)."*

If the sub-tab shows HDI68 instability (2x or more spread), the paper needs a full appendix section with the comparison table, the HDI68-vs-N_bins plot, and an expanded discussion of our choice. That discussion is where the literature review in `memory/likelihood_bin_sensitivity.md` Section 1 pays off.

## Deliverables produced this round

- `memory/likelihood_bin_sensitivity.md` — standalone reference note with frontmatter, self-contained for resumption in a future chat. Contains full literature review (Section 1), bin-scheme library with Python expressions (Section 2), diagnostic metric list + logL-cross-scheme derivation (Section 3), six statistical pitfalls (Section 4), test plan (Section 5), references (Section 7).
- This comms file — summary for the orchestrator.
- No code edits (Round 1 rule).

## Open flags

- **NEEDS-INPUT (non-blocking, for a future chat):** Should the project abandon the multinomial entirely in favour of K-S on the CDF? This is worth a separate discussion after the user sees the sub-tab results.
- Nothing blocking for Round 2. Coder + QA can proceed with the scheme list and metric definitions in the memory file.

## Status

READY
