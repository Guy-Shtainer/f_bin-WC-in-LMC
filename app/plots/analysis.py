"""plots/analysis.py — ΔRV analysis pipeline (cached) and binary classification."""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import streamlit as st

from shared import get_obs_manager, ROOT

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import specs  # noqa: E402

from plots.data import _load_ccf_settings, _extract_rv


@st.cache_data
def cached_load_drv_analysis(settings_hash_val: str):
    cfg = _load_ccf_settings()
    lines_default = cfg.get('emission_lines_default', {})
    star_cfg = {s['star_name']: s for s in cfg.get('stars', [])}
    ordered_lines = list(lines_default.keys())

    obs = get_obs_manager()
    drverr_map = {}
    rv_epoch_cache = {}

    rows = []
    for star_name in specs.star_names:
        star = obs.load_star_instance(star_name, to_print=False)
        epochs = star.get_all_epoch_numbers()
        scfg = star_cfg.get(star_name, {})
        skip_epochs = scfg.get('skip_epochs', [])
        skip_lines = scfg.get('skip_emission_lines', {})

        has_cleaned = False
        for ep in epochs:
            d = star.load_property('cleaned_normalized_flux', ep, 'COMBINED')
            if d is not None and isinstance(d, dict):
                has_cleaned = True
                break
        is_clean_bool = not has_cleaned

        row = {
            'Star': star_name,
            'Clean': '\u2713' if is_clean_bool else 'X',
            'is_clean_bool': is_clean_bool,
        }

        for lk in ordered_lines:
            skip_ep_for_line = skip_lines.get(lk, [])
            rv_vals = []
            for ep in epochs:
                if ep in skip_epochs:
                    continue
                if ep in skip_ep_for_line or 0 in skip_ep_for_line:
                    continue
                rv_prop = star.load_property('RVs', ep, 'COMBINED')
                if not isinstance(rv_prop, dict) or lk not in rv_prop:
                    continue
                rv_val, rv_err = _extract_rv(rv_prop[lk])
                if rv_val is None or rv_val == 0.0:
                    continue
                if rv_err is None:
                    rv_err = np.nan
                rv_vals.append((ep, rv_val, rv_err))

            rv_epoch_cache[(star_name, lk)] = rv_vals

            if len(rv_vals) < 2:
                row[f'dRV | {lk}'] = np.nan
                drverr_map[(star_name, lk)] = np.nan
                continue

            ep_min, rv_min, err_min = min(rv_vals, key=lambda t: t[1])
            ep_max, rv_max, err_max = max(rv_vals, key=lambda t: t[1])
            dRV = abs(rv_max - rv_min)
            row[f'dRV | {lk}'] = dRV

            if np.isfinite(err_min) and np.isfinite(err_max):
                sigma_A = np.sqrt(err_min ** 2 + err_max ** 2)
            else:
                sigma_A = np.nan
            drverr_map[(star_name, lk)] = sigma_A

        drvs = [v for k, v in row.items() if isinstance(k, str) and k.startswith('dRV | ')]
        valid_drvs = [v for v in drvs if np.isfinite(v)]
        row['Mean ΔRV'] = float(np.mean(valid_drvs)) if valid_drvs else np.nan
        row['Std ΔRV'] = float(np.std(valid_drvs)) if valid_drvs else np.nan
        rows.append(row)

    df = pd.DataFrame(rows)
    civ_col = 'dRV | C IV 5808-5812'
    if civ_col in df.columns:
        df = df.sort_values(civ_col, ascending=False, na_position='last').reset_index(drop=True)

    return df, drverr_map, rv_epoch_cache, ordered_lines


def _is_significant_binary(star_name, line_key, drv_val, threshold_val, drverr_map):
    if not (pd.notna(drv_val) and np.isfinite(drv_val)):
        return False
    sigma_A = drverr_map.get((star_name, line_key), np.nan)
    if not np.isfinite(sigma_A):
        return False
    return bool(float(drv_val) >= threshold_val) and bool(float(drv_val) >= 4.0 * float(sigma_A))
