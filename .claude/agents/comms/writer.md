# Writer Comms — Figure Insertions + §rv_results Restructure

_Last updated: 2026-04-27_

## Status: COMPLETE

Both tasks delivered as a single self-contained edit pass. No coder hand-off, no `% TODO` strings remain, A&A style throughout. Each figure environment uses `\centering`, a commented-out `\includegraphics`, an A&A-publication-quality `\caption{...}`, and a `\label{fig:...}`.

## TASK 1 — 13 figure environments inserted

| # | Label | File | Inserted at | Width | Float type |
|---|---|---|---|---|---|
| 1 | `fig:ccf_profile` | `paper/sections/methods.tex` | line 49 (after Zucker curvature equation, before "For a small fraction…" paragraph) | `\columnwidth` | `figure` |
| 2 | `fig:agreement` | `paper/sections/methods.tex` | line 198 (immediately after the existing `Fig.~\ref{fig:agreement}` reference at line 196 — the ghost ref now resolves) | `\textwidth` | `figure*` |
| 3 | `fig:threshold_derivation` | `paper/sections/methods.tex` | line 246 (after the parametric Gaussian model paragraph, before the "Threshold value" paragraph) | `\columnwidth` | `figure` |
| 4 | `fig:peak_drv_per_star` | `paper/sections/results.tex` | line 15 (right after the introductory `\fbinobs` paragraph) | `\columnwidth` | `figure` |
| 5 | `fig:binary_examples` | `paper/sections/results.tex` | line 52 (inside the rewritten §rv_results — see Task 2) | `\textwidth` | `figure*` |
| 6 | `fig:cdf_obs_vs_sim` | `paper/sections/bias_correction.tex` | line 101 (after Eq.~\ref{eq:multinomial}, before §Grid search and results) | `\columnwidth` | `figure` |
| 7 | `fig:fbin_pi_heatmap` | `paper/sections/bias_correction.tex` | line 128 (immediately after the best-fit-parameters paragraph in §Grid search and results) | `\columnwidth` | `figure` |
| 8 | `fig:fbin_pi_marginals` | `paper/sections/bias_correction.tex` | line 140 (immediately after `fig:fbin_pi_heatmap`) | `\columnwidth` | `figure` |
| 9 | `fig:bin_sensitivity` | `paper/sections/bias_correction.tex` | line 152 (immediately after `fig:fbin_pi_marginals`, before the Langer subsection) | `\columnwidth` | `figure` |
| 10 | `fig:langer_heatmap` | `paper/sections/bias_correction.tex` | line 210 (after the 2D `(f_bin, sigma_single)` scan paragraph that closes the Langer model description) | `\columnwidth` | `figure` |
| 11 | `fig:period_models` | `paper/sections/bias_correction.tex` | line 220 (immediately after `fig:langer_heatmap`) | `\columnwidth` | `figure` |
| 12 | `fig:sample_map` | `paper/sections/observations.tex` | line 30 (right after the brightness-stratification sentence in §Target sample) | `\columnwidth` | `figure` |
| 13 | `fig:lmc_vs_mw` | `paper/sections/discussion.tex` | line 27 (right after the apples-to-apples comparison paragraph in §Comparison with Galactic WC stars) | `\columnwidth` | `figure` |

Per-file count:
- `methods.tex`: 3 figures
- `results.tex`: 2 figures
- `bias_correction.tex`: 6 figures
- `observations.tex`: 1 figure
- `discussion.tex`: 1 figure
- Total: 13

## TASK 2 — §rv_results restructured

`paper/sections/results.tex` lines 33–51. The forward-looking placeholder paragraph that pointed readers back to §detections has been replaced with a single 6-sentence paragraph that:

1. Names the three exemplars in `Fig.~\ref{fig:binary_examples}`: a clearly detected SB1, a marginal case, and an apparently single star.
2. Tells the reader what to look for in each panel — unambiguous red/blue shift across epochs (SB1), a shift comparable to the per-epoch combined uncertainty (marginal), no measurable variation between epochs (single).
3. Uses the marginal case to motivate the joint threshold + significance criterion, with explicit cross-reference to Sect.~\ref{sec:criteria}.
4. Closes by pointing to Appendix~\ref{app:rv_tables} for the full per-star tabulation.

The `\subsection{Radial-velocity measurements}` heading and `\label{sec:rv_results}` are preserved unchanged.

## VERIFICATION RESULTS

```
$ grep -rn "% TODO" paper/sections/ paper/main.tex
(no output) — TODO total: 0   PASS

$ grep -c "begin{figure" paper/sections/*.tex
bias_correction.tex:6
discussion.tex:1
methods.tex:3
results.tex:2
observations.tex:1
(others: 0)
TOTAL: 13   PASS

$ grep -rn "label{fig:" paper/sections/
13 unique labels (one per figure env, all distinct)   PASS
fig:agreement is now defined at methods.tex:212 (no longer ghost)   PASS

$ grep -rn "ref{fig:" paper/sections/ paper/main.tex
4 refs total — all resolve to defined labels:
  results.tex:35  -> fig:binary_examples       (defined)
  methods.tex:196 -> fig:agreement             (defined)
  bias_correction.tex:146 -> fig:fbin_pi_heatmap (defined)
  bias_correction.tex:216 -> fig:fbin_pi_heatmap (defined)
PASS

$ grep -rn "^[^%]*\\\\includegraphics" paper/sections/
(no output) — every \includegraphics line is commented out   PASS

$ grep -rn "Kolmog" paper/sections/ paper/main.tex
(no output)   PASS
```

## Framing decisions to flag

1. **`fig:langer_heatmap` placement.** The brief said "after the equation describing the Langer mixture". I placed it after the closing 2D-scan paragraph rather than immediately after Eq.~\ref{eq:langer_period}, because the equation is followed by an `itemize` block listing the Case A / Case B / weight parameters and then by two paragraphs describing the orbital priors and the 2D scan. Inserting a `figure` between the equation and its own itemize would have orphaned the parameter list. The current placement (right where the model description ends and the scan results would live) is the natural reading break. If you'd rather see it earlier — say, immediately after the closing `\end{itemize}` — let me know.

2. **§rv_results scope.** The brief asked for one short paragraph (4–6 sentences). Final paragraph is 6 sentences. It deliberately does not duplicate the SB1 catalogue summary that lives in §Binary detections; it focuses entirely on what the reader sees in the three exemplar panels and why the joint criterion is needed. The §Observed binary fraction subsection that follows it is unchanged.

3. **`fig:peak_drv_per_star` placement.** Inserted in §Binary detections rather than §rv_results because the brief specified "right after the sentence introducing the \fbinobs result", which lives in §Binary detections (lines 7–13).

4. **`fig:agreement` is `figure*` (2-column).** Correct per the brief — the two-panel figure (ranking + score-vs-EW) needs the textwidth.

5. **`fig:binary_examples` is `figure*` (2-column).** Correct per the brief — three columns of stacked top/bottom panels need textwidth.

6. **No conclusions.tex insertion.** Brief did not list any figure for §Conclusions. Confirmed.

7. **Compile sanity not run locally.** No pdflatex on this machine; structural verification (grep checks above) is the strongest test possible from here. All figure refs resolve; all macros referenced in captions (`\primaryline`, `\drvthresh`, `\NlinesAll`, `\Nstars`, `\Nknown`, `\Ntotal`, `\fbinobs`, `\sigthresh`, `\Nstarsmincorr`, `\fitFracDefault`, `\pibestfit`) are defined in `main.tex`.

## Files modified

- `paper/sections/methods.tex` — +3 figures
- `paper/sections/results.tex` — +2 figures, §rv_results rewritten
- `paper/sections/bias_correction.tex` — +6 figures
- `paper/sections/observations.tex` — +1 figure
- `paper/sections/discussion.tex` — +1 figure

`paper/main.tex` was not modified (all macros it defines were already in place).
