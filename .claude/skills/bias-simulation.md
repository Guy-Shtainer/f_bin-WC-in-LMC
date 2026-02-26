---
name: bias-simulation
description: Guide for running, interpreting, or modifying the Monte-Carlo binary fraction bias simulation for WR stars. Use this skill whenever the user mentions bias correction, binary fraction grid search, f_bin vs pi heatmap, K-S test comparison, period distribution models (Dsilva or Langer), simulation parameters, or the bias correction page in the webapp. Also trigger when the user asks about SimulationConfig, BinaryParameterConfig, run_bias_grid, sigma_single, sigma_measure, cadence library, observed vs simulated CDFs, or any parameter tuning for the Monte-Carlo simulation.
---

# Bias Simulation

## Purpose

The Monte-Carlo simulation compares simulated ΔRV CDFs to the observed one via a
Kolmogorov-Smirnov test, scanning a 2D grid over `(f_bin, π)` — intrinsic binary
fraction and period power-law exponent. The best-fit model is the grid point with
the minimum K-S D statistic.

## How to Run

There are three ways to run the simulation:

1. **Webapp** — `app/pages/05_bias_correction.py` (primary workflow).
   Live heatmap fills in as slices complete. Supports sigma scan and animated 4D.
   Launch: `conda run -n guyenv streamlit run app/app.py` → navigate to Bias Correction page.

2. **CLI** — `pipeline/dsilva_grid.py`.
   ```bash
   conda run -n guyenv python pipeline/dsilva_grid.py
   conda run -n guyenv python pipeline/dsilva_grid.py --load-cached
   ```

3. **Python import** — `from wr_bias_simulation import run_bias_grid, SimulationConfig, BinaryParameterConfig`

## Key Classes

### SimulationConfig (`wr_bias_simulation.py`)

Global simulation settings. Values come from `settings/user_settings.json` → `simulation` section:

| Parameter        | Settings value | Description                              |
|------------------|---------------|------------------------------------------|
| `n_stars`        | 10,000        | Simulated systems per grid point         |
| `sigma_single`   | 5.5 km/s      | Intrinsic RV scatter for single WR stars |
| `sigma_measure`  | 1.622 km/s    | Per-epoch measurement uncertainty        |
| `cadence_library`| from data     | Real MJD timestamps from the 25 stars    |

The cadence library preserves real temporal sampling (gaps, clustering) rather than
assuming uniform epoch spacing. Each simulated star is randomly assigned a real
cadence from the 25 targets.

### BinaryParameterConfig (`wr_bias_simulation.py`)

Orbital parameter distributions:

| Parameter     | Dsilva model              | Langer+2020 model                        |
|---------------|--------------------------|------------------------------------------|
| Period        | p(logP) ∝ (logP)^π      | Two-Gaussian mixture (Case A + Case B)   |
| Eccentricity  | U[0, 0.9]               | Circular (e = 0)                         |
| Mass ratio    | U[0.1, 2.0]             | Gaussian(μ=0.7, σ=0.2) clipped           |
| Inclination   | p(i) ∝ sin(i)           | Same                                     |
| Primary mass  | Fixed 10 M⊙ or U[10,20] | Same                                     |

Period range: logP ∈ [0.15, 5.0] (days). Grid params in `settings/user_settings.json`
→ `grid_dsilva` and `grid_langer` sections.

## Observed Data Source

`pipeline/load_observations.py` → `load_observed_delta_rvs()` loads RVs + MJDs for
all 25 stars, applies the binary detection criteria (ΔRV > 45.5 km/s AND ΔRV − 4σ > 0),
and returns the observed ΔRV array that feeds the K-S comparison.

## Output

Results are saved as `.npz` files in `results/` with an embedded `config_hash`.
Before running a new grid, the system checks for an existing result with a matching
hash and offers to load it instead of recomputing.

The output contains: `fbin_grid`, `pi_grid`, `ks_d_grid`, `ks_p_grid`, plus the
`config_hash` and all simulation parameters for reproducibility.

## Parallelization

Uses `multiprocessing.Pool` with `os.cpu_count() - 1` workers. The webapp uses
`imap_unordered` for live heatmap updates as each (f_bin, π) slice completes,
updating `st.progress()` and the Plotly heatmap in real time.

## Common Modifications

- **Grid resolution**: Change `fbin_steps` / `pi_steps` in `settings/user_settings.json`
- **Period range**: Change `logP_min` / `logP_max` in settings
- **Noise model**: Change `sigma_single` / `sigma_measure` in settings
- **Period model**: Switch between `dsilva` (power-law) and `langer2020` (two-Gaussian)
- **Number of simulated stars**: Change `n_stars_sim` in settings (more = smoother but slower)
