# Bias Simulation Skill

Use this skill when the user asks about running, modifying, or interpreting the Monte-Carlo binary fraction bias simulation.

## Overview

The main script is `wr_bias_simulation.py`. It performs a grid search over `(f_bin, π)` — binary fraction and period power-law index — comparing simulated ΔRV CDFs to the observed one via a K-S test.

## Key Classes & Parameters

- `SimulationConfig`: global settings — `n_stars`, `n_epochs`, `time_span_years`, `sigma_single` (intrinsic RV scatter ~5.5 km/s), `sigma_measure` (per-epoch error ~1.6 km/s)
- `BinaryParameterConfig`: orbital distributions — `logP_min/max`, `q_min/max`, `e_max`, period model (`dsilva` power-law or `langer2020`)

## Two Period Models

- **Dsilva**: `p(logP) ∝ (logP)^π`, `π` is the grid parameter
- **Langer+2020**: empirical OB+BH period distribution; `π` still modulates shape

## Binary Detection Applied in Simulation

Same two criteria as the real data:
1. ΔRV > 45.5 km/s
2. ΔRV − 4σ > 0

## When Asked to Run or Modify

1. Read `wr_bias_simulation.py` to understand current parameter values in the dataclasses
2. Identify which `SimulationConfig` or `BinaryParameterConfig` fields need changing
3. Propose changes with scientific justification (e.g., changing `logP_max` affects period range)
4. The output is a 2D p-value grid saved as a numpy array — high p-value = model consistent with data
5. The simulation is parallelized with `multiprocessing`; check `n_workers` if performance is slow
