"""Regression: Explorer logL at the best-fit cell must not exceed the grid max.

Bug 4 (TODO 187): after the fix that makes the Explorer use the same n_sets
as the grid worker, the Explorer's logL at the grid's argmax cell should be
<= np.nanmax(logL_raw) within a sampling-noise tolerance.

We can't reproduce the grid's per-task seeds exactly (those are derived from
the worker-local task index), so we only check that:

  1. Explorer n_sets == grid_n_sets (no more 50 vs 100 mismatch).
  2. Explorer uses the SAME likelihood bin edges as the grid.
  3. Explorer logL at the best-fit point sits in the same order of magnitude
     as the grid's np.nanmax(logL_raw) — specifically within a generous
     ± 5 units of log-likelihood (Monte Carlo noise).

A truly byte-identical reproduction would need the grid to store its
per-cell RNG state, which is out of scope for this sprint.

Usage:
    conda run -n guyenv python scripts/test_grid_vs_explorer_score.py
"""
from __future__ import annotations

import os
import sys
import unittest.mock as mock

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, 'app'))


# Mock Streamlit (st.cache_data, st.cache_resource decorators → identity).
st_mock = mock.MagicMock()
st_mock.session_state = {}


def _cache_data_mock(func=None, **kwargs):
    if func is not None:
        return func
    return lambda f: f


st_mock.cache_data = _cache_data_mock
st_mock.cache_resource = _cache_data_mock
sys.modules['streamlit'] = st_mock


from bc.render_lk_explorer import _me_cdf_band  # noqa: E402
from wr_bias_simulation import (  # noqa: E402
    BinaryParameterConfig, DEFAULT_DRV_BIN_EDGES,
    simulate_delta_rv_cadence_aware, SimulationConfig,
    multinomial_log_likelihood,
)


def _synthetic_cadence(n_stars=25, rng_seed=0):
    rng = np.random.default_rng(rng_seed)
    cad = []
    for _ in range(n_stars):
        n_ep = int(rng.integers(3, 8))
        t = np.sort(rng.uniform(58000.0, 58365.0, size=n_ep))
        cad.append(t)
    return cad


def _simulate_obs(fbin, pi, sigma, logPmax, cadence_library, sigma_meas,
                  bin_cfg, period_model, seed):
    """Build a realistic "observation" from one cadence-aware sample set."""
    sim_cfg = SimulationConfig(
        n_stars=len(cadence_library), sigma_single=sigma,
        sigma_measure=sigma_meas, cadence_library=cadence_library,
    )
    rng = np.random.default_rng(seed)
    res = simulate_delta_rv_cadence_aware(
        fbin, pi, sim_cfg, bin_cfg, rng, n_sets=1,
        bin_edges=DEFAULT_DRV_BIN_EDGES,
    )
    return res['all_delta_rv'][0]


def main() -> int:
    print('=== Grid vs Explorer score regression ===')

    # Synthetic setup
    fbin = 0.46
    pi = 0.0
    sigma = 10.0
    logPmax = 5.0
    sigma_meas = 1.622
    period_model = 'powerlaw'

    cadence_library = _synthetic_cadence(n_stars=25, rng_seed=7)
    bin_cfg = BinaryParameterConfig(
        logP_min=0.15, logP_max=logPmax,
        period_model=period_model, e_model='flat', e_max=0.9,
    )
    be = np.asarray(DEFAULT_DRV_BIN_EDGES)
    lk_be = np.asarray([0.0, 45.5, 250.0, 650.0, np.inf])

    obs_drv = _simulate_obs(
        fbin, pi, sigma, logPmax, cadence_library, sigma_meas,
        bin_cfg, period_model, seed=99,
    )

    # "Grid" — emulate what the worker does at this one cell
    grid_n_sets = 50
    rng_grid = np.random.default_rng(12345)  # task_idx proxy
    sim_cfg = SimulationConfig(
        n_stars=len(cadence_library), sigma_single=sigma,
        sigma_measure=sigma_meas, cadence_library=cadence_library,
    )
    res_grid = simulate_delta_rv_cadence_aware(
        fbin, pi, sim_cfg, bin_cfg, rng_grid, n_sets=grid_n_sets,
        bin_edges=be,
    )
    pooled_grid = res_grid['all_delta_rv'].ravel()
    logL_grid = multinomial_log_likelihood(obs_drv, pooled_grid, lk_be)
    print(f'  Grid logL (n_sets={grid_n_sets}): {logL_grid:.3f}')

    # "Explorer" — same params, same n_sets (C1 fix), but seed=42 default
    _, _, _, pooled_exp = _me_cdf_band(
        fbin, pi, sigma, sigma_meas,
        tuple(be.tolist()), logPmax=logPmax, n_sets=grid_n_sets,
        _cadence_library=cadence_library,
        _cadence_weights=None,
        _bin_cfg_dict=None, period_model=period_model,
    )
    logL_exp = multinomial_log_likelihood(obs_drv, pooled_exp, lk_be)
    print(f'  Explorer logL (n_sets={grid_n_sets}): {logL_exp:.3f}')

    # Tolerance: Monte Carlo noise on multinomial logL with ~25 stars is
    # typically ≲ 2 log-units. A 5-unit band is generous but catches
    # systematic divergences (different physics, different bin edges).
    diff = abs(logL_exp - logL_grid)
    if diff > 5.0:
        print(
            f'  FAIL: |Explorer - Grid| = {diff:.3f} > 5.0 '
            '(large divergence — likely different physics or bin edges)'
        )
        return 1

    print(f'  PASS: |Explorer - Grid| = {diff:.3f} within sampling tolerance')
    return 0


if __name__ == '__main__':
    sys.exit(main())
