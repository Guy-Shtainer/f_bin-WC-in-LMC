"""
callbacks/simulation_cadence_cb.py
──────────────────────────────────
Synchronous callback for cadence-aware bias correction grid search.
Factory: serves both cadence-dsilva and cadence-langer pages.
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


def register_cadence_simulation_callback(
    prefix: str,
    period_model: str = 'powerlaw',
) -> None:
    """Register simulation callback for a cadence-aware model page."""
    p = prefix
    is_langer = (period_model == 'langer2020')

    # Build State list dynamically
    states = [
        State(f'{p}-fbin-min', 'value'),
        State(f'{p}-fbin-max', 'value'),
        State(f'{p}-fbin-steps', 'value'),
        State(f'{p}-n-stars', 'value'),
        State(f'{p}-sigma-min', 'value'),
        State(f'{p}-sigma-max', 'value'),
        State(f'{p}-sigma-steps', 'value'),
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
    ]
    if not is_langer:
        states.extend([
            State(f'{p}-pi-min', 'value'),
            State(f'{p}-pi-max', 'value'),
            State(f'{p}-pi-steps', 'value'),
        ])
    if is_langer:
        states.extend([
            State(f'{p}-mu-A', 'value'),
            State(f'{p}-sigma-A', 'value'),
            State(f'{p}-mu-B', 'value'),
            State(f'{p}-sigma-B', 'value'),
            State(f'{p}-weight-A', 'value'),
            State(f'{p}-q-preset', 'value'),
        ])

    @callback(
        Output(f'{p}-result-store', 'data'),
        Output(f'{p}-progress-text', 'children'),
        Input(f'{p}-run-btn', 'n_clicks'),
        *states,
        prevent_initial_call=True,
    )
    def run_cadence_grid(n_clicks, *args):
        if n_clicks is None:
            raise PreventUpdate

        from wr_bias_simulation import (
            SimulationConfig, BinaryParameterConfig, run_bias_grid,
        )
        from config import to_json_safe

        # Unpack common args
        idx = 0
        fbin_min = args[idx]; idx += 1
        fbin_max = args[idx]; idx += 1
        fbin_steps = args[idx]; idx += 1
        n_stars = args[idx]; idx += 1
        sigma_min = args[idx]; idx += 1
        sigma_max = args[idx]; idx += 1
        sigma_steps = args[idx]; idx += 1
        logp_min = args[idx]; idx += 1
        logp_max = args[idx]; idx += 1
        e_model = args[idx]; idx += 1
        e_max = args[idx]; idx += 1
        mass_model = args[idx]; idx += 1
        mass_fixed = args[idx]; idx += 1
        q_model = args[idx]; idx += 1
        q_min = args[idx]; idx += 1
        q_max = args[idx]; idx += 1
        n_proc = args[idx]; idx += 1

        if not is_langer:
            pi_min = args[idx]; idx += 1
            pi_max = args[idx]; idx += 1
            pi_steps = args[idx]; idx += 1
            pi_vals = np.linspace(pi_min or -3.0, pi_max or 3.0, int(pi_steps or 100))
        else:
            pi_vals = np.array([0.0])

        fbin_vals = np.linspace(fbin_min or 0.01, fbin_max or 1.0, int(fbin_steps or 99))
        sigma_vals = np.linspace(sigma_min or 3.0, sigma_max or 13.0, int(sigma_steps or 50))

        bin_cfg_kwargs = dict(
            logP_min=float(logp_min or 0.15),
            logP_max=float(logp_max or 4.0),
            period_model=period_model,
            e_model=e_model or 'flat',
            e_max=float(e_max or 0.9),
            mass_primary_model=mass_model or 'fixed',
            mass_primary_fixed=float(mass_fixed or 10.0),
            q_model=q_model or 'flat',
            q_range=(float(q_min or 0.1), float(q_max or 2.0)),
        )

        if is_langer:
            mu_A = args[idx]; idx += 1
            sigma_A = args[idx]; idx += 1
            mu_B = args[idx]; idx += 1
            sigma_B = args[idx]; idx += 1
            weight_A = args[idx]; idx += 1
            q_preset = args[idx]; idx += 1
            bin_cfg_kwargs['langer_period_params'] = {
                'mu_A': float(mu_A or 1.0), 'sigma_A': float(sigma_A or 0.12),
                'mu_B': float(mu_B or 2.1), 'sigma_B': float(sigma_B or 0.2),
                'weight_A': float(weight_A or 0.08),
                'dist_A': 'gaussian', 'dist_B': 'lognormal',
            }

        cfg_sim = SimulationConfig(
            n_stars=int(n_stars or 1000),
            sigma_single=float(sigma_vals[0]),
        )
        cfg_bin = BinaryParameterConfig(**bin_cfg_kwargs)

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
            period_model=period_model,
            sigma_values=sigma_vals,
            n_processes=int(n_proc or 1),
        )

        from datetime import datetime
        _results_dir = os.path.join(_ROOT, 'results')
        os.makedirs(_results_dir, exist_ok=True)
        _ts = datetime.now().strftime('%y%m%d-%H%M')
        _model = 'cadence_langer' if is_langer else 'cadence_dsilva'
        _fname = f'{_model}_fb{fbin_min:.2f}-{fbin_max:.2f}x{int(fbin_steps)}_N{int(n_stars)}_{_ts}.npz'
        np.savez(os.path.join(_results_dir, _fname), **result)

        return to_json_safe(result), f'Done! Saved: {_fname}'
