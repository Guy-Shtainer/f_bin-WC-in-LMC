# Architecture Reference

## Class Hierarchy

```
ObservationManager (ObservationClass.py)
    └─ creates/manages ──→ Star (StarClass.py)       # X-SHOOTER observations
                      ──→ NRES (NRESClass.py)        # NRES observations (parallel to Star)
                               └─ both use ──→ FITSFile (FitsClass.py)  # astropy wrapper
```

Star and NRES are **parallel classes** at the same level — ObservationManager routes to one or the other based on `star_name in self.NRES_stars`. Both have symmetric interfaces.

**ObservationManager** (`ObservationClass.ObservationManager`): factory that routes `star_name` → Star or NRES, organizes raw FITS into structured directories.

**Star** (`StarClass.py`): per-star data store for X-SHOOTER observations.
- Path: `Data/{star}/epoch{N}/{band}/output/{property}.npz`

**NRES** (`NRESClass.py`): per-star data store for NRES observations (parallel to Star, same interface).
- Path: `Data/{star}/epoch{N}/{spectra_num}/{data_type}/output/{property}.npz`

Both share methods: `get_file_path`, `load_observation`, `load_property`, `save_property`, `backup_property`, `delete_files`, `clean`, `list_available_properties`

**CCFclass** (`CCF.py`): pure numpy/scipy, no file I/O. `(obs_wave, obs_flux, tpl_wave, tpl_flux)` → `(RV_km_s, sigma_RV)`. Init params: `CrossCorRangeA` (wavelength interval pairs in nm), `CrossVeloMin/Max`.

**SimulationClass** (`SimulationClass.py`): mock SB2 spectra with Kepler orbital mechanics.

## Support Modules
- `specs.py` — `star_names` (25 WR stars) + `obs_file_names` dict
- `ccf_settings_with_global_lines.json` — 11 emission lines with wavelength ranges; per-star overrides
- `settings/user_settings.json` — master runtime settings
- `utils.py` — `robust_mean`, `double_robust_mean`, `robust_std` (σ-clipping)
- `catalogs.py` — schema dicts for SIMBAD, Gaia DR3, BAT99, etc.
- `ccf_tasks.py` — multiprocessing orchestrator for CCF
- `pipeline/load_observations.py` — loads RVs + MJDs, applies binary criteria
- `wr_bias_simulation.py` — Monte-Carlo grid: `SimulationConfig`, `BinaryParameterConfig`, `run_bias_grid()`

## Interactive Processing Tools
- `ISE.py` — interactive spectrum normalization
- `INnres.py` — NRES multi-fiber normalization
- `IC2D.py` — 2D image spatial cleaning
- `TwoDImage.py` — 2D FITS spectral image visualization
- `plot.py` / `plot2.py` — multi-instrument FITS reader (X-SHOOTER, HERMES, FEROS, UVES, COS, STIS, MUSE)

## Bias Simulation
`wr_bias_simulation.py` — Monte-Carlo grid search over `(f_bin, π)`:
- Draws binary populations, computes RV curves with observational noise
- Compares simulated ΔRV CDFs to observed via K-S test
- Parallelized with `multiprocessing`
- Two period models: power-law (Dsilva) and Langer+2020
