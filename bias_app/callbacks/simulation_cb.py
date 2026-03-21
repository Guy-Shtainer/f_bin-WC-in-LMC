"""
callbacks/simulation_cb.py
──────────────────────────
Synchronous callback that runs the Dsilva bias correction grid search.
Uses a regular callback (not background) for reliability in Dash 4.0.
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


def register_simulation_callback(prefix: str) -> None:
    """Register the simulation callback for a Dsilva model page."""
    p = prefix

    @callback(
        Output(f'{p}-result-store', 'data'),
        Output(f'{p}-progress-text', 'children'),
        Input(f'{p}-run-btn', 'n_clicks'),
        # Grid params
        State(f'{p}-fbin-min', 'value'),
        State(f'{p}-fbin-max', 'value'),
        State(f'{p}-fbin-steps', 'value'),
        State(f'{p}-pi-min', 'value'),
        State(f'{p}-pi-max', 'value'),
        State(f'{p}-pi-steps', 'value'),
        State(f'{p}-n-stars', 'value'),
        # Sigma
        State(f'{p}-scan-sigma', 'checked'),
        State(f'{p}-sigma-single', 'value'),
        State(f'{p}-sigma-min', 'value'),
        State(f'{p}-sigma-max', 'value'),
        State(f'{p}-sigma-steps', 'value'),
        # logP_max scan
        State(f'{p}-scan-logpmax', 'checked'),
        State(f'{p}-logpmax-scan-min', 'value'),
        State(f'{p}-logpmax-scan-max', 'value'),
        State(f'{p}-logpmax-scan-steps', 'value'),
        # Orbital params
        State(f'{p}-logp-min', 'value'),
        State(f'{p}-logp-max', 'value'),
        State(f'{p}-e-model', 'value'),
        State(f'{p}-e-max', 'value'),
        State(f'{p}-mass-model', 'value'),
        State(f'{p}-mass-fixed', 'value'),
        State(f'{p}-q-model', 'value'),
        State(f'{p}-q-min', 'value'),
        State(f'{p}-q-max', 'value'),
        # Run config
        State(f'{p}-n-proc', 'value'),
        prevent_initial_call=True,
    )
    def run_dsilva_grid(
        n_clicks,
        fbin_min, fbin_max, fbin_steps,
        pi_min, pi_max, pi_steps,
        n_stars,
        scan_sigma, sigma_single, sigma_min, sigma_max, sigma_steps,
        scan_logpmax, logpmax_min, logpmax_max, logpmax_steps,
        logp_min, logp_max, e_model, e_max, mass_model, mass_fixed,
        q_model, q_min, q_max,
        n_proc,
    ):
        """Synchronous callback: runs the full Dsilva grid search."""
        if n_clicks is None:
            raise PreventUpdate

        from wr_bias_simulation import (
            SimulationConfig, BinaryParameterConfig, run_bias_grid,
        )
        from config import to_json_safe

        # Build parameter grids
        fbin_vals = np.linspace(fbin_min or 0.01, fbin_max or 0.99, int(fbin_steps or 99))
        pi_vals = np.linspace(pi_min or -3.0, pi_max or 3.0, int(pi_steps or 100))

        if scan_sigma:
            sigma_vals = np.linspace(sigma_min or 3.0, sigma_max or 13.0, int(sigma_steps or 50))
        else:
            sigma_vals = np.array([sigma_single or 6.0])

        # Build configs
        cfg_sim = SimulationConfig(
            n_stars=int(n_stars or 1000),
            sigma_single=float(sigma_single or 6.0),
        )
        cfg_bin = BinaryParameterConfig(
            logP_min=float(logp_min or 0.15),
            logP_max=float(logp_max or 4.0),
            period_model='powerlaw',
            e_model=e_model or 'flat',
            e_max=float(e_max or 0.9),
            mass_primary_model=mass_model or 'fixed',
            mass_primary_fixed=float(mass_fixed or 10.0),
            q_model=q_model or 'flat',
            q_range=(float(q_min or 0.1), float(q_max or 2.0)),
        )

        # Load observed delta-RVs from cache file
        _cache_path = os.path.join(_APP, '.obs_delta_rv_cache.npy')
        if os.path.exists(_cache_path):
            obs_delta_rv = np.load(_cache_path)
        else:
            from data_loader import load_observed_delta_rvs
            obs_delta_rv = load_observed_delta_rvs()

        # Run the grid search (synchronous, uses multiprocessing internally)
        result = run_bias_grid(
            fbin_values=fbin_vals,
            pi_values=pi_vals,
            obs_delta_rv=obs_delta_rv,
            sim_cfg=cfg_sim,
            bin_cfg=cfg_bin,
            period_model='powerlaw',
            sigma_values=sigma_vals,
            n_processes=int(n_proc or 1),
        )

        # Save result to disk
        from datetime import datetime
        _results_dir = os.path.join(_ROOT, 'results')
        os.makedirs(_results_dir, exist_ok=True)
        _ts = datetime.now().strftime('%y%m%d-%H%M')
        _fname = (f'dsilva_fb{fbin_min:.2f}-{fbin_max:.2f}x{int(fbin_steps)}'
                  f'_pi{pi_min:.1f}-{pi_max:.1f}x{int(pi_steps)}'
                  f'_N{int(n_stars)}_sig{sigma_vals[0]:.1f}'
                  f'{"" if len(sigma_vals)==1 else f"-{sigma_vals[-1]:.1f}x{len(sigma_vals)}"}'
                  f'_{_ts}.npz')
        np.savez(os.path.join(_results_dir, _fname), **result)

        # Convert numpy → JSON for dcc.Store
        return to_json_safe(result), f'Done! Saved: {_fname}'
