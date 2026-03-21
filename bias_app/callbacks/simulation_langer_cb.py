"""
callbacks/simulation_langer_cb.py
─────────────────────────────────
Synchronous callback for Langer 2020 bias correction grid search.
Grid axes: f_bin x sigma (pi is not used).
"""
from __future__ import annotations

import os
import sys

import numpy as np
from dash import callback, Input, Output, State
from dash.exceptions import PreventUpdate

_APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.dirname(_APP)
for _p in [_ROOT, _APP]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


def register_langer_simulation_callback(prefix: str) -> None:
    """Register the simulation callback for the Langer model page."""
    p = prefix

    @callback(
        Output(f'{p}-result-store', 'data'),
        Output(f'{p}-progress-text', 'children'),
        Input(f'{p}-run-btn', 'n_clicks'),
        State(f'{p}-fbin-min', 'value'),
        State(f'{p}-fbin-max', 'value'),
        State(f'{p}-fbin-steps', 'value'),
        State(f'{p}-sigma-min', 'value'),
        State(f'{p}-sigma-max', 'value'),
        State(f'{p}-sigma-steps', 'value'),
        State(f'{p}-n-stars', 'value'),
        State(f'{p}-mu-A', 'value'),
        State(f'{p}-sigma-A', 'value'),
        State(f'{p}-mu-B', 'value'),
        State(f'{p}-sigma-B', 'value'),
        State(f'{p}-weight-A', 'value'),
        State(f'{p}-q-preset', 'value'),
        State(f'{p}-logp-min', 'value'),
        State(f'{p}-logp-max', 'value'),
        State(f'{p}-e-model', 'value'),
        State(f'{p}-e-max', 'value'),
        State(f'{p}-mass-model', 'value'),
        State(f'{p}-mass-fixed', 'value'),
        State(f'{p}-q-model', 'value'),
        State(f'{p}-q-min', 'value'),
        State(f'{p}-q-max', 'value'),
        State(f'{p}-n-proc', 'value'),
        prevent_initial_call=True,
    )
    def run_langer_grid(
        n_clicks,
        fbin_min, fbin_max, fbin_steps,
        sigma_min, sigma_max, sigma_steps,
        n_stars,
        mu_A, sigma_A, mu_B, sigma_B, weight_A, q_preset,
        logp_min, logp_max, e_model, e_max, mass_model, mass_fixed,
        q_model, q_min, q_max,
        n_proc,
    ):
        if n_clicks is None:
            raise PreventUpdate

        from wr_bias_simulation import (
            SimulationConfig, BinaryParameterConfig, run_bias_grid,
        )
        from config import to_json_safe

        fbin_vals = np.linspace(fbin_min or 0.01, fbin_max or 1.0, int(fbin_steps or 99))
        sigma_vals = np.linspace(sigma_min or 3.0, sigma_max or 13.0, int(sigma_steps or 100))
        pi_vals = np.array([0.0])  # dummy — Langer doesn't use pi

        cfg_sim = SimulationConfig(
            n_stars=int(n_stars or 1000),
            sigma_single=float(sigma_vals[0]),
        )
        cfg_bin = BinaryParameterConfig(
            logP_min=float(logp_min or 0.15),
            logP_max=float(logp_max or 4.0),
            period_model='langer2020',
            langer_period_params={
                'mu_A': float(mu_A or 1.0), 'sigma_A': float(sigma_A or 0.12),
                'mu_B': float(mu_B or 2.1), 'sigma_B': float(sigma_B or 0.2),
                'weight_A': float(weight_A or 0.08),
                'dist_A': 'gaussian', 'dist_B': 'lognormal',
            },
            e_model=e_model or 'flat',
            e_max=float(e_max or 0.9),
            mass_primary_model=mass_model or 'fixed',
            mass_primary_fixed=float(mass_fixed or 10.0),
            q_model=q_model or 'flat',
            q_range=(float(q_min or 0.1), float(q_max or 2.0)),
        )

        _cache_path = os.path.join(_APP, '.obs_delta_rv_cache.npy')
        if os.path.exists(_cache_path):
            obs_delta_rv = np.load(_cache_path)
        else:
            from data_loader import load_observed_delta_rvs
            obs_delta_rv = load_observed_delta_rvs()

        result = run_bias_grid(
            fbin_values=fbin_vals,
            pi_values=pi_vals,
            obs_delta_rv=obs_delta_rv,
            sim_cfg=cfg_sim,
            bin_cfg=cfg_bin,
            period_model='langer2020',
            sigma_values=sigma_vals,
            n_processes=int(n_proc or 1),
        )

        from datetime import datetime
        _results_dir = os.path.join(_ROOT, 'results')
        os.makedirs(_results_dir, exist_ok=True)
        _ts = datetime.now().strftime('%y%m%d-%H%M')
        _fname = (f'langer_fb{fbin_min:.2f}-{fbin_max:.2f}x{int(fbin_steps)}'
                  f'_sig{sigma_min:.1f}-{sigma_max:.1f}x{int(sigma_steps)}'
                  f'_N{int(n_stars)}_{_ts}.npz')
        np.savez(os.path.join(_results_dir, _fname), **result)

        return to_json_safe(result), f'Done! Saved: {_fname}'
