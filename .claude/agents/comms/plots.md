# Plots agent — 2026-04-27 deferred-figures run

Three deferred PDF figures rendered into `plots/` (extending existing
`pipeline/export_paper_figs.py` — no duplication; new entries wired into
`main()` and the deferred-list note pruned).

## Plot Spec: sample_map.pdf
## Chart Type: Sky map (RA / Dec scatter)
## Data Mapping
- X-axis: Right ascension α (deg, J2000) — INVERTED per astronomical convention
- Y-axis: Declination δ (deg, J2000)
- Color: C IV 5808-5812 binary classification (red square = binary, blue circle = single)
- Marker: square = binary (n = 10), circle = single (n = 15)
- Background: faint LMC body ellipse (van der Marel & Kallivayalil 2014 centroid)
## Scientific Justification
Show sample distribution within the LMC body. The binary detection is C IV-derived;
red squares cluster toward the LMC bar — a known WC concentration. The 3
Bartzakos-2001 binaries are NOT in our sample (the 28 = 25 + 3 = our 25 + 3
known) and have no FITS data in this repo, so they're not plotted; the caption
should note the 3 known binaries are in addition to these 25.
## Accuracy Checklist
- [x] Axes labeled with units (deg, J2000)
- [x] Legend matches actual data (10 binaries, 15 singles from C IV criterion)
- [x] No fabricated/placeholder data — RA/Dec from FITS headers per star
- [x] RA axis inverted (astronomical convention)
- [x] LMC body ellipse marked as guide only (not data)

## Plot Spec: binary_examples.pdf
## Chart Type: 1×3 small-multiples — RV vs MJD with errorbars
## Data Mapping
- X-axis: MJD (days)
- Y-axis: RV (km s⁻¹) — separate scale per panel
- Color: red = detected binary, blue = single
- Error bars: full_RV_err per epoch from RVs property
- Reference line: dashed grey at panel-mean RV
- Shaded band: ±T/2 = ±22.75 km/s around the panel-mean (visualises detection threshold)
## Scientific Justification
Three representative cases auto-picked from `_build_per_line_drv_table()`:
- **Clear binary (HD 269891)** — ΔRV_max = 341.5 ± 8.0 km/s, n_ep = 7. Spans
  −315 → +27 km/s across 5 distinct epochs; obvious orbital motion.
- **Marginal (MNM2014 LMC195-1)** — ΔRV_max = 59.9 ± 6.9 km/s, n_ep = 5.
  Closest to the 45.5 km/s threshold while still classified as binary.
- **Single (Brey 90a)** — ΔRV_max = 2.7 ± 2.1 km/s, n_ep = 6. Tightly
  clustered around the panel mean (no dispersion above instrumental floor).
## Accuracy Checklist
- [x] All axes labeled with units
- [x] No fabricated data — MJDs from FITS header (MJD-OBS), RVs from RVs property
- [x] Error bars are real σ_full_RV
- [x] Star selection algorithmic (no cherry-picking)
- [x] Bottom row (line profiles at peak-to-peak epochs) DEFERRED — not yet
      rendered; would require ObservationManager spectra-loading bootstrap

## Plot Spec: ccf_profile.pdf
## Chart Type: 1-panel line plot — CCF ρ(s) vs velocity shift s
## Data Mapping
- X-axis: Velocity shift s (km s⁻¹), range [−1500, +1500]
- Y-axis: Cross-correlation ρ(s), [0, 1.1]
- Black solid: full CCF
- Grey dashed horizontal: f_fit · ρ_max = 0.97 · ρ_max
- Red dashed: parabolic fit overlay on the peak region
- Gold vertical: fitted RV centroid; gold shaded band = ±1σ
## Scientific Justification
Worked example for `Brey 93 epoch 2` on C IV 5808-5812: a single, well-
sampled CCF profile demonstrating the fit_fraction = 0.97 peak detection,
parabolic-fit method (Zucker 2003), and resulting RV uncertainty estimate.
Fitted RV = +11.49 ± 2.31 km/s, ρ_max = 0.999. Brey 93 chosen as the highest-
EW star on C IV 5808 (selection criterion). Epoch 2 used (epoch 1 == template
gives degenerate σ on the std-normalisation step).
## Accuracy Checklist
- [x] Axes labeled with units (km s⁻¹)
- [x] No fabricated data — CCF recomputed live by `_compute_ccf_profile()`
      (mirrors `CCFclass._crosscorreal` without the plotting tail)
- [x] Wavelength UNITS FIX: FITS data stores in nm, so `wavelengths * 10`
      converts to Å before passing to CCF (which expects Å for the
      C IV 5700-5880 range). Without this conversion the CCF returned NaN.
- [x] Real CCF, real RV, real σ — no placeholder values

## Style audit (all three)
- paper_bgcolor = `#FFFFFF` (white) ✓
- All text black, serif (Times New Roman → DejaVu Serif fallback) ✓
- Mirrored black axes, outside ticks, no gridlines ✓
- pdf.fonttype = 42 (Type-42 embedded) ✓
- No 'gold' / `#FFD700`, no 'white' on traces ✓
- Hex colors that survive WCAG on white: `#4A90D9`, `#D62728`, `#DAA520`,
  `#888888`, `#000000` — all checked ✓

## Files modified
- `pipeline/export_paper_figs.py`:
  - Wired `fig_sample_map`, `fig_binary_examples`, `fig_ccf_profile`
    into `main()` driver (previously defined but never called)
  - Pruned the three from the "DEFERRED" tail-message
  - Fixed nm→Å conversion in `fig_ccf_profile` (`wavelengths * 10.0`)
  - Default epoch for `fig_ccf_profile` switched 1 → 2 (epoch 1 = template
    gives degenerate std-normalisation)
  - Cleaned legend / title strings:
    `'C\\,IV 5808'` → `r'C IV 5808'`
    `'\\,\\AA'` → Unicode `Å` (matplotlib mathtext doesn't render `\AA` outside math)
    Star names with double spaces collapsed via `' '.join(name.split())`

## Files NOT modified
- No paper LaTeX touched (per instruction — orchestrator will uncomment
  `\includegraphics` for the new files)
- `fig:threshold_derivation` left alone (user is producing themselves)

## Status
TO-TEST — visual sign-off needed from user. Per project rule
`feedback_no_self_approve.md`, plots agent does NOT mark figures WORKING
without explicit user approval.
