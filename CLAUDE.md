# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Spectroscopic analysis pipeline for Wolf-Rayet (WR) stars in the LMC. Goal: measure radial velocities (RVs) from multi-epoch spectroscopy, classify binary/single stars, and constrain the binary fraction with Monte-Carlo bias correction.

**Instruments:** VLT/X-SHOOTER (UVB/VIS/NIR bands), NRES
**Stars:** 25 WR stars listed in `specs.py`
**Key algorithm:** Cross-Correlation Function (CCF) via Zucker & Mazeh (1994) / Zucker et al. (2003)

## Project Structure (evolving)

New directories added alongside existing root files (nothing moved, no import breakage):
- `pipeline/` — standalone analysis scripts (each starts with `sys.path.insert(0, parent_dir)`)
- `app/` — Streamlit web app (`streamlit run app/app.py`)
- `settings/` — `user_settings.json` (master), `run_history.json`, `states/`, `presets/`
- `results/` — saved grid outputs (.npz) with embedded `config_hash`
- `plots/` — saved publication figures
- `../output/` — **NEVER CHANGE THIS PATH** — existing CCF plot output one level above project root

## Performance Preferences

**Multiprocessing:** Always use `os.cpu_count() - 1` cores (auto-detected; reserves 1 for OS).

**Speed over memory:** Prefer faster code at the expense of memory — use pre-allocation,
vectorization, lookup tables, and in-memory caching freely. Storage is not a constraint.

## Webapp Conventions (app/)

- **State saving:** Sidebar must always include a "Save state" button accessible on every page.
  Saved states store: all settings + active page + active star + loaded result file path.
  States are JSON files in `settings/states/{timestamp}_{name}.json`.
- **Computation caching:** Every `.npz` result file stores a `config_hash` of the settings used.
  Before running any grid, check for an existing result with a matching hash — offer to load it.
- **Memory:** `@st.cache_data` with no expiry. A manual "Clear cache" button in Settings only.
- **Plots:** Use Plotly for all interactive charts in the webapp (not matplotlib).
- **Launch:** `conda run -n guyenv streamlit run app/app.py` → http://localhost:8501

## Documentation for Paper Writing

The user is a Masters student at Tel Aviv University writing a thesis (to be published on Overleaf).
Maintain `DOCUMENTATION.md` at the project root. After significant results or decisions, append:
- What was done and why (scientific context)
- Key numbers (fractions, best-fit parameters, thresholds)
- Methodology details and caveats
This is **not** a changelog — it is scientific prose for writing the paper.

## Running the Analysis

```bash
# Streamlit web app (primary workflow)
conda run -n guyenv streamlit run app/app.py

# Pipeline scripts (CLI, also called by app)
conda run -n guyenv python pipeline/dsilva_grid.py
conda run -n guyenv python pipeline/dsilva_grid.py --load-cached

# Legacy scripts (still work from root)
conda run -n guyenv python ccf_tasks.py
```

Interactive processing tools (open matplotlib GUI, run from terminal):
```bash
python ISE.py       # interactive spectrum normalization
python INnres.py    # same but for NRES multi-fiber data
python IC2D.py      # interactive 2D image spatial cleaning
```

Jupyter notebooks (reference / archive):
- `Thesis work.ipynb` — main analysis pipeline
- `Tests.ipynb` — validation and exploration
- `bias_simulation.ipynb` — binary fraction & bias grid search
- `Plots.ipynb` — publication figures

## Architecture

### Class Hierarchy

```
ObservationManager (ObservationClass.py)
    └─ creates/manages ──→ Star (StarClass.py)       # X-SHOOTER observations
                      └─→ NRES (NRESClass.py)        # NRES observations
                               └─ both use ──→ FITSFile (FitsClass.py)  # astropy wrapper
```

**ObservationManager** (`ObservationClass.ObservationManager`): factory that routes `star_name` → correct class, organizes raw FITS into structured directories.

**Star / NRES**: per-star data stores. Properties (RVs, normalized flux, etc.) are saved/loaded as `.npz` files.
- XShooter path: `Data/{star}/epoch{N}/{band}/output/{property}.npz`
- NRES path: `Data/{star}/epoch{N}/{spectra_num}/{data_type}/output/{property}.npz`
- Methods are symmetric: `get_file_path`, `load_observation`, `load_property`, `save_property`, `backup_property`, `delete_files`, `clean`, `list_available_properties`

**CCFclass** (`CCF.py`): pure numpy/scipy, no file I/O. Takes `(obs_wave, obs_flux, tpl_wave, tpl_flux)` → returns `(RV_km_s, sigma_RV)`. Key init params: `CrossCorRangeA` (list of wavelength interval pairs in nm), `CrossVeloMin/Max`.

**SimulationClass** (`SimulationClass.py`): generates mock SB2 spectra with Kepler orbital mechanics for testing the CCF pipeline.

### Support Modules

- `specs.py` — `star_names` list (25 WR stars) + `obs_file_names` dict mapping `star → epoch → band → filename`
- `ccf_settings_with_global_lines.json` — 11 emission lines with wavelength ranges; per-star epoch/line skipping and fit-fraction overrides
- `settings/user_settings.json` — master runtime settings for webapp and pipeline scripts
- `utils.py` — `robust_mean`, `double_robust_mean`, `robust_std` (σ-clipping)
- `catalogs.py` — schema dicts for SIMBAD, Gaia DR3, BAT99, etc.
- `ccf_tasks.py` — multiprocessing orchestrator: reads the JSON config, runs CCF for all stars/lines
- `pipeline/load_observations.py` — loads RVs + MJDs (from FITS `MJD-OBS` header), applies binary criteria
- `wr_bias_simulation.py` — simulation engine: `SimulationConfig`, `BinaryParameterConfig`, `run_bias_grid()`

### Interactive Processing Tools

- `TwoDImage.py` — 2D FITS spectral image visualization
- `plot.py` / `plot2.py` — multi-instrument FITS reader supporting X-SHOOTER, HERMES, FEROS, UVES, COS, STIS, MUSE

### Bias Simulation

`wr_bias_simulation.py` — Monte-Carlo grid search over `(f_bin, π)`:
- Draws binary populations, computes RV curves with observational noise
- Compares simulated ΔRV CDFs to observed via K-S test
- Parallelized with `multiprocessing`
- `SimulationConfig` + `BinaryParameterConfig` dataclasses hold all parameters
- Two period models: power-law (Dsilva) and Langer+2020

## Key Conventions

**Property persistence:** All computed results (RVs, normalized flux, EWs, SNR bounds) stored as `.npz` files using `star.save_property(name, data, epoch, band)`. Load with `star.load_property(name, epoch, band)`.

**Binary detection:** Two criteria must both be met: (1) ΔRV > 45.5 km/s, and (2) significance: ΔRV − 4σ > 0 (where σ is combined epoch-pair error). Applied to the max-separation epoch pair first; if not satisfied, all pairs are scanned. Single emission line used: `C IV 5808-5812`. Result: 10/25 detected + 3 Bartzakos (2001) = **13/28 ≈ 46%** total binary fraction.

**MJD source:** Observation times come from FITS headers (`fit.header['MJD-OBS']`), NOT from the RV property dict. The RV property only contains `full_RV` and `full_RV_err`.

**numpy.bool_ pitfall:** Comparisons on numpy arrays return `numpy.bool_`, not Python `bool`. Always cast with `bool()` before storing or using `is True` checks.

**Spectral bands:** COMBINED (full stitched), UVB (~300–560 nm), VIS (~560–1020 nm), NIR (~1020–2480 nm).

**Emission lines for CCF:** defined in `ccf_settings_with_global_lines.json` — 11 WR wind lines (O V, O IV, C IV, He II, O VI, C III, etc.).

**Parallelism:** `ccf_tasks.py` uses `multiprocessing.Pool`; logging uses file-based thread-safe `log_msg()` to `debug_parallel.log`.

**Printing:** Classes accept `to_print=True/False`; internal output via `self.print(text)`.

## Code Quality Rules

**Always test before finishing:** After writing any new `.py` file, run:
```bash
conda run -n guyenv python -m py_compile path/to/file.py
```
Verify zero output (no syntax or import errors) before marking work complete.

**Import convention for `app/pages/`:** Always use `from shared import ...`
(NOT `from app.shared import ...`). Streamlit adds the `app/` directory to
`sys.path` when running pages, so `shared` is importable directly.

**Commit after each change:** When making multiple changes to the codebase,
commit each logical change separately with a descriptive message before moving
to the next change. This provides fine-grained rollback points and clear history.

**Backup before editing app pages:** Before modifying any file in `app/pages/`,
run `cp app/pages/{file} Backups/{file}.bak` to create a rollback point.
Always verify the backup compiles before overwriting it with a newer version.

**Progress bars for long runs:** Any computation taking >5 seconds must show
`st.progress()`. For multi-slice loops (e.g., sigma scan in the bias correction
page), update the progress bar and the live heatmap slot after each slice
completes. Use `st.empty()` as a placeholder for the live-updating chart.

## Graph Style Preferences

When producing plots, consider what best communicates the data — sometimes
simple and clean is best, sometimes more detailed with color coding helps
explain the science. Always add a short `st.caption(...)` below each plot.

Learn from user feedback: when they are unhappy with a graph, note what they
disliked; when they seem satisfied, note what worked. Update this section with
short descriptions of preferred graph styles as patterns emerge.

**Current preferences (update as feedback arrives):**
- Dark theme plots (`plot_bgcolor='#1a1a2e'`, `paper_bgcolor='#1a1a2e'`,
  `font_color='#e0e0e0'`)
- Gold star markers for best-fit points
- Observed data: solid lines in steel blue (#4A90D9)
- Simulated/model data: dashed lines in tomato red (#E25A53)
- Annotations with key statistics (K-S D, p-value) in semi-transparent boxes
- Contour lines on heatmaps (white, dotted)
- Semi-transparent histogram overlays for distribution comparisons
