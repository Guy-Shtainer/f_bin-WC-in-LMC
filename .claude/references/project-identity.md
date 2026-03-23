# Project Identity — WR Binary Analysis

## What This Project Is
Spectroscopic analysis pipeline for Wolf-Rayet (WR) stars in the LMC (Large Magellanic Cloud).
Masters thesis at Tel Aviv University — to be published as an A&A journal paper.
**Title**: "The multiplicity properties of carbon-rich Wolf-Rayet stars in the LMC"

## Scientific Context
- **Goal**: Measure radial velocities (RVs) from multi-epoch spectroscopy, classify binary/single stars, constrain the binary fraction with Monte-Carlo bias correction
- **Instruments**: VLT/X-SHOOTER (UVB/VIS/NIR bands), NRES
- **Stars**: 25 WR stars listed in `specs.py`, from Bartzakos (2001) survey of 28 WC LMC stars
- **Key algorithm**: Cross-Correlation Function (CCF) via Zucker & Mazeh (1994) / Zucker et al. (2003)
- **Binary line**: Only `'C IV 5808-5812'` for binary classification
- **Binary criteria**: Both must be met: (1) ΔRV > 45.5 km/s, (2) significance: ΔRV − 4σ > 0
- **Current result**: 10/25 detected + 3 Bartzakos = **13/28 ≈ 46%** total binary fraction

## Critical Data Conventions
- **WAVELENGTH UNITS**: FITS files store wavelengths in **nm**. Display in **Ångströms (Å)**: `wave_A = wave_nm * 10.0`. Exception: NRES wavelengths already in Å
- **MJD source**: FITS header `fit.header['MJD-OBS']` — NOT in RV property dict
- **Zero-filter**: Missing epochs stored as 0.0 — filter with `rv[rv != 0]`
- **Data symlink**: `Data/` → `../Data`. Git operations destroy it. Fix: `ln -s ../Data Data`
- **Spectral bands**: COMBINED (full stitched), UVB (~300–560 nm), VIS (~560–1020 nm), NIR (~1020–2480 nm)
- **Property persistence**: `.npz` files via `star.save_property()` / `star.load_property()`

## File Conventions
- **Import convention for `app/pages/`**: Use `from shared import ...` (NOT `from app.shared import ...`)
- **Git**: Always commit to `main`. `agent/*` branches = unconfirmed
- **Conda**: Always use `conda run -n guyenv python ...`
- **Output path**: `../output/` — NEVER CHANGE THIS PATH

## Paper Relevance — Always Think About This
After every task, ask: "Is this relevant for the paper?" If yes → update `DOCUMENTATION.md`.
- Relevant: simulation methods, statistical approaches, binary classification, key results, parameter choices, model comparisons
- NOT relevant: pure GUI fixes, webapp plumbing, code refactoring with no scientific impact
- Meeting notes with Tomer → almost always paper-relevant
