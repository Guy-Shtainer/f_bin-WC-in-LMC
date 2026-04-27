# Plots agent — Validation Recovery Diagnostics

## Plot Spec: Parameter Recovery Diagnostics (post-run)
## Chart Type: Two subplot figures (each 2-row shared-x) + a truth-vs-recovered dataframe

### Data Mapping

**Panel A — f_bin(ΔRV) overlay + residual**
- X-axis (both rows): ΔRV threshold t (km/s), shared
- Upper Y-axis: f_bin(t) = P(ΔRV > t), dimensionless, range [0, 1]
- Lower Y-axis: Δf_bin = f_bin_mock(t) − f_bin_sim(t), dimensionless
- Color coding:
  - Mock empirical stairs: white (`#FFFFFF`), shape='hv', width 2.5
  - Best-fit sim line: steel blue (`#4A90D9`), width 2
  - Single-star dots: `_CLR_SINGLE = #E25A53` (red)
  - Binary-star dots: `_CLR_BINARY = #52B788` (green)
  - Realised mock f_bin hline: `#C44536` (dim red), dashed
  - Recovered f_bin hline: `#4A90D9`, dotted
  - Detection threshold vline: `#DAA520` (dark goldenrod), dashed
  - Residual fill: `#8c564b` (brown) at 25 % alpha
  - ±1/√N Poisson band: grey 15 % alpha

**Panel B — ΔRV CDF overlay + residual**
- X-axis (both rows): ΔRV threshold t (km/s)
- Upper Y-axis: CDF(t) = P(ΔRV ≤ t), [0, 1]
- Lower Y-axis: ΔCDF = mock − sim_med, dimensionless
- Sim band: bootstrap 200× resamples of size N_mock from `gap_sim['delta_rv']`,
  16/84 percentile band at `rgba(74,144,217,0.20)`, median line at `#4A90D9`
- Residual panel: brown filled area vs 0, grey ±(hi−lo)/2 band showing sim
  sampling uncertainty

**Truth vs Recovered table**
- Rows: `f_bin`, `π`, `σ_single (km/s)`, `logP_max`
- Columns: Parameter, True, Recovered, |Δ|, rel. error, |Δ| / σ
- σ = HDI half-width from `lo_*_L` / `hi_*_L` if present; else median grid step
- Row highlighted red when |Δ| > 1σ; π row greyed out + italic for Langer

### Scientific Justification

Today's validation run (n_sets=100, 25 mock stars, Dsilva, seed=42) showed a
visually good ΔRV CDF overlay while the best-fit `(f_bin, π)` landed >1σ off
the true values. This is a known failure mode: the binned-multinomial
likelihood collapses the full joint ΔRV distribution into a low-dimensional
summary, and that summary is highly degenerate in `(f_bin, π)`.

Adding `f_bin(t) = P(ΔRV > t)` as a co-diagnostic is the cheapest way to
break the degeneracy visually — it responds differently to `(f_bin, π)` than
the CDF does, and its tail is directly what the 45.5 km/s detection
threshold reads off. The residual panels make the "good CDF / bad fit"
failure mode visible rather than hidden behind eyeball overlays.

### Accuracy Checklist

- [x] All axes labeled with units (`ΔRV threshold t (km/s)`, `f_bin(t)`, `CDF`)
- [x] Legend matches actual data series (Mock, Sim, Single(N), Binary(N))
- [x] No fabricated/placeholder data — every curve is computed from
      `mock_detail`, `gap_sim`, or `result` arrays in session state
- [x] Error bars / uncertainty bands where uncertainty matters (Poisson
      band, bootstrap 16/84 band)
- [x] PLOTLY_THEME applied; annotations use their own explicit colors
      that remain readable regardless of the active (dark or light) theme
- [x] Guard clauses: returns silently if `result` or `mock_detail` not yet
      available; shows `st.info` note if `gap_sim` missing
- [x] π row greyed out for Langer (fixed) so we never display a
      meaningless recovered π
- [x] Best-fit unravel logic replicated locally (not imported from
      cadence.py) to avoid circular import; unit-tested for 2D/3D/4D
      likelihood arrays

### Follow-ups for the user to verify visually (TO-TEST, not WORKING)
1. Run **Bias Correction → Validation → Single-Point Recovery** with
   `f_bin=0.46, π=0.0, σ=15, logP_max=4.0, seed=42`.
2. Confirm `N_sets` in the delegated Dsilva tab defaults to **500**.
3. After the run completes, scroll below the standard Dsilva/Langer output.
   The new **Parameter Recovery Diagnostics** section should show:
   - Truth-vs-recovered dataframe
   - Panel A (f_bin overlay + residual)
   - Panel B (CDF overlay + residual)
4. For Langer: π row should be greyed out + italic.
