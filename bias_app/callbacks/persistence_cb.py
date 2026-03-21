"""
callbacks/persistence_cb.py
───────────────────────────
Auto-save params to localStorage, restore on page load, named presets.
"""
from __future__ import annotations

import json
import os

from dash import callback, Input, Output, State, no_update, ctx
from dash.exceptions import PreventUpdate

from config import PRESETS_DIR


def register_persistence_callbacks(prefix: str) -> None:
    """Register auto-save/restore and preset callbacks for a model page."""
    p = prefix

    # ── Auto-save all params to localStorage on every change ─────────────
    @callback(
        Output(f'{p}-params-store', 'data'),
        Input(f'{p}-fbin-min', 'value'),
        Input(f'{p}-fbin-max', 'value'),
        Input(f'{p}-fbin-steps', 'value'),
        Input(f'{p}-pi-min', 'value'),
        Input(f'{p}-pi-max', 'value'),
        Input(f'{p}-pi-steps', 'value'),
        Input(f'{p}-n-stars', 'value'),
        Input(f'{p}-scan-sigma', 'checked'),
        Input(f'{p}-sigma-single', 'value'),
        Input(f'{p}-sigma-min', 'value'),
        Input(f'{p}-sigma-max', 'value'),
        Input(f'{p}-sigma-steps', 'value'),
        Input(f'{p}-scan-logpmax', 'checked'),
        Input(f'{p}-logpmax-scan-min', 'value'),
        Input(f'{p}-logpmax-scan-max', 'value'),
        Input(f'{p}-logpmax-scan-steps', 'value'),
        Input(f'{p}-logp-min', 'value'),
        Input(f'{p}-logp-max', 'value'),
        Input(f'{p}-e-model', 'value'),
        Input(f'{p}-e-max', 'value'),
        Input(f'{p}-mass-model', 'value'),
        Input(f'{p}-mass-fixed', 'value'),
        Input(f'{p}-q-model', 'value'),
        Input(f'{p}-q-min', 'value'),
        Input(f'{p}-q-max', 'value'),
        Input(f'{p}-n-proc', 'value'),
    )
    def auto_save(
        fbin_min, fbin_max, fbin_steps,
        pi_min, pi_max, pi_steps, n_stars,
        scan_sigma, sigma_single, sigma_min, sigma_max, sigma_steps,
        scan_logpmax, logpmax_min, logpmax_max, logpmax_steps,
        logp_min, logp_max, e_model, e_max, mass_model, mass_fixed,
        q_model, q_min, q_max, n_proc,
    ):
        return {
            'fbin_min': fbin_min, 'fbin_max': fbin_max, 'fbin_steps': fbin_steps,
            'pi_min': pi_min, 'pi_max': pi_max, 'pi_steps': pi_steps,
            'n_stars': n_stars,
            'scan_sigma': scan_sigma, 'sigma_single': sigma_single,
            'sigma_min': sigma_min, 'sigma_max': sigma_max, 'sigma_steps': sigma_steps,
            'scan_logpmax': scan_logpmax,
            'logpmax_min': logpmax_min, 'logpmax_max': logpmax_max,
            'logpmax_steps': logpmax_steps,
            'logp_min': logp_min, 'logp_max': logp_max,
            'e_model': e_model, 'e_max': e_max,
            'mass_model': mass_model, 'mass_fixed': mass_fixed,
            'q_model': q_model, 'q_min': q_min, 'q_max': q_max,
            'n_proc': n_proc,
        }

    # ── Restore params from localStorage on page load ────────────────────
    @callback(
        Output(f'{p}-fbin-min', 'value', allow_duplicate=True),
        Output(f'{p}-fbin-max', 'value', allow_duplicate=True),
        Output(f'{p}-fbin-steps', 'value', allow_duplicate=True),
        Output(f'{p}-pi-min', 'value', allow_duplicate=True),
        Output(f'{p}-pi-max', 'value', allow_duplicate=True),
        Output(f'{p}-pi-steps', 'value', allow_duplicate=True),
        Output(f'{p}-n-stars', 'value', allow_duplicate=True),
        Output(f'{p}-scan-sigma', 'checked', allow_duplicate=True),
        Output(f'{p}-sigma-single', 'value', allow_duplicate=True),
        Output(f'{p}-sigma-min', 'value', allow_duplicate=True),
        Output(f'{p}-sigma-max', 'value', allow_duplicate=True),
        Output(f'{p}-sigma-steps', 'value', allow_duplicate=True),
        Output(f'{p}-scan-logpmax', 'checked', allow_duplicate=True),
        Output(f'{p}-logpmax-scan-min', 'value', allow_duplicate=True),
        Output(f'{p}-logpmax-scan-max', 'value', allow_duplicate=True),
        Output(f'{p}-logpmax-scan-steps', 'value', allow_duplicate=True),
        Output(f'{p}-logp-min', 'value', allow_duplicate=True),
        Output(f'{p}-logp-max', 'value', allow_duplicate=True),
        Output(f'{p}-e-model', 'value', allow_duplicate=True),
        Output(f'{p}-e-max', 'value', allow_duplicate=True),
        Output(f'{p}-mass-model', 'value', allow_duplicate=True),
        Output(f'{p}-mass-fixed', 'value', allow_duplicate=True),
        Output(f'{p}-q-model', 'value', allow_duplicate=True),
        Output(f'{p}-q-min', 'value', allow_duplicate=True),
        Output(f'{p}-q-max', 'value', allow_duplicate=True),
        Output(f'{p}-n-proc', 'value', allow_duplicate=True),
        Input(f'{p}-params-store', 'modified_timestamp'),
        State(f'{p}-params-store', 'data'),
        prevent_initial_call=True,
    )
    def restore_params(ts, data):
        if data is None:
            raise PreventUpdate
        g = data.get
        return (
            g('fbin_min', 0.01), g('fbin_max', 0.99), g('fbin_steps', 99),
            g('pi_min', -3.0), g('pi_max', 3.0), g('pi_steps', 100),
            g('n_stars', 1000),
            g('scan_sigma', False), g('sigma_single', 6.0),
            g('sigma_min', 3.0), g('sigma_max', 13.0), g('sigma_steps', 50),
            g('scan_logpmax', False),
            g('logpmax_min', 1.0), g('logpmax_max', 6.0), g('logpmax_steps', 15),
            g('logp_min', 0.15), g('logp_max', 4.0),
            g('e_model', 'flat'), g('e_max', 0.9),
            g('mass_model', 'fixed'), g('mass_fixed', 10.0),
            g('q_model', 'flat'), g('q_min', 0.1), g('q_max', 2.0),
            g('n_proc', 7),
        )

    # ── Save named preset to disk ────────────────────────────────────────
    @callback(
        Output(f'{p}-presets-store', 'data'),
        Output(f'{p}-preset-name', 'value'),
        Input(f'{p}-save-preset-btn', 'n_clicks'),
        State(f'{p}-preset-name', 'value'),
        State(f'{p}-params-store', 'data'),
        State(f'{p}-presets-store', 'data'),
        prevent_initial_call=True,
    )
    def save_preset(n_clicks, name, params, presets):
        if not name or not params:
            raise PreventUpdate
        presets = presets or {}
        presets[name] = params
        # Also save to disk
        os.makedirs(PRESETS_DIR, exist_ok=True)
        path = os.path.join(PRESETS_DIR, f'{p}_{name}.json')
        with open(path, 'w') as f:
            json.dump(params, f, indent=2)
        return presets, ''  # clear name input

    # ── Update preset dropdown from store ────────────────────────────────
    @callback(
        Output(f'{p}-preset-select', 'data'),
        Input(f'{p}-presets-store', 'data'),
    )
    def update_preset_list(presets):
        items = []
        # From store
        if presets:
            for name in presets:
                items.append({'value': f'store:{name}', 'label': name})
        # From disk
        if os.path.isdir(PRESETS_DIR):
            for fname in sorted(os.listdir(PRESETS_DIR)):
                if fname.startswith(f'{p}_') and fname.endswith('.json'):
                    name = fname[len(f'{p}_'):-5]
                    key = f'disk:{name}'
                    if not any(i['label'] == name for i in items):
                        items.append({'value': key, 'label': f'{name} (disk)'})
        return items

    # ── Load selected preset ─────────────────────────────────────────────
    @callback(
        Output(f'{p}-params-store', 'data', allow_duplicate=True),
        Input(f'{p}-preset-select', 'value'),
        State(f'{p}-presets-store', 'data'),
        prevent_initial_call=True,
    )
    def load_preset(selection, presets):
        if not selection:
            raise PreventUpdate
        if selection.startswith('store:'):
            name = selection[6:]
            if presets and name in presets:
                return presets[name]
        elif selection.startswith('disk:'):
            name = selection[5:]
            path = os.path.join(PRESETS_DIR, f'{p}_{name}.json')
            if os.path.exists(path):
                with open(path) as f:
                    return json.load(f)
        raise PreventUpdate
