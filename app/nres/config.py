"""nres/config.py — Emission line configuration management for NRES analysis."""
from __future__ import annotations

import json
import os
import sys

import pandas as pd
import streamlit as st

from shared import ROOT

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# ── Constants ─────────────────────────────────────────────────────────────────
NRES_STARS = ['WR 52', 'WR17']
c_kms = 299792.458

NRES_LINE_NAMES = [
    'He II 4686', 'O VI 5210-5340', 'He II 5412 & C IV 5471',
    'C IV 5808-5812', 'C III 6700-6800', 'C IV 7063',
]

_NRES_CFG_PATH = os.path.join(ROOT, 'settings', 'nres_line_config.json')
_NRES_OVR_PATH = os.path.join(ROOT, 'settings', 'nres_line_overrides.json')


def _load_line_config_from_global():
    """Load defaults from the shared X-SHOOTER config (fallback)."""
    json_path = os.path.join(ROOT, 'ccf_settings_with_global_lines.json')
    with open(json_path) as f:
        cfg = json.load(f)
    lines = cfg.get('emission_lines_default', {})
    fit_frac_default = cfg.get('fit_fraction_default', 0.95)
    result = {}
    for name in NRES_LINE_NAMES:
        if name in lines:
            rng_nm = lines[name]
            result[name] = {
                'lam_min': rng_nm[0] * 10.0,
                'lam_max': rng_nm[1] * 10.0,
                'fit_fraction': fit_frac_default,
                'enabled': True,
            }
    return result


def _save_line_config_to_disk(df):
    """Save line config DataFrame to settings/nres_line_config.json."""
    records = df.to_dict(orient='records')
    with open(_NRES_CFG_PATH, 'w') as f:
        json.dump(records, f, indent=2)


def _save_overrides_to_disk(star_name, overrides_df):
    """Save per-star overrides to settings/nres_line_overrides.json."""
    if os.path.exists(_NRES_OVR_PATH):
        with open(_NRES_OVR_PATH) as f:
            all_ovr = json.load(f)
    else:
        all_ovr = {}
    all_ovr[star_name] = overrides_df.to_dict(orient='records')
    with open(_NRES_OVR_PATH, 'w') as f:
        json.dump(all_ovr, f, indent=2)


def _get_line_config_df():
    """Global line config table (6 rows). Loads from disk config, falls back to global JSON."""
    if 'nres_line_cfg' not in st.session_state:
        if os.path.exists(_NRES_CFG_PATH):
            with open(_NRES_CFG_PATH) as f:
                records = json.load(f)
            st.session_state['nres_line_cfg'] = pd.DataFrame(records)
        else:
            cfg = _load_line_config_from_global()
            rows = []
            for name, d in cfg.items():
                rows.append({
                    'Line': name, 'lam_min': d['lam_min'], 'lam_max': d['lam_max'],
                    'fit_fraction': d['fit_fraction'], 'enabled': d['enabled'],
                })
            st.session_state['nres_line_cfg'] = pd.DataFrame(rows)
    return st.session_state['nres_line_cfg']


def _get_overrides_df(star_name):
    """Per-epoch/per-spectra override table. Loads from disk, empty by default."""
    key = f'nres_line_overrides_{star_name}'
    if key not in st.session_state:
        if os.path.exists(_NRES_OVR_PATH):
            with open(_NRES_OVR_PATH) as f:
                all_ovr = json.load(f)
            if star_name in all_ovr and all_ovr[star_name]:
                st.session_state[key] = pd.DataFrame(all_ovr[star_name])
            else:
                st.session_state[key] = pd.DataFrame(
                    columns=['Epoch', 'Spectra', 'Line', 'lam_min', 'lam_max', 'fit_fraction', 'enabled']
                )
        else:
            st.session_state[key] = pd.DataFrame(
                columns=['Epoch', 'Spectra', 'Line', 'lam_min', 'lam_max', 'fit_fraction', 'enabled']
            )
    return st.session_state[key]


def _resolve_line_config(epoch, spectra, line_name, global_df, overrides_df):
    """Resolve line config: check overrides (exact match then epoch-wide), fall back to global."""
    if len(overrides_df) > 0:
        # Exact match: (epoch, spectra, line)
        exact = overrides_df[
            (overrides_df['Epoch'] == epoch) &
            (overrides_df['Spectra'] == spectra) &
            (overrides_df['Line'] == line_name)
        ]
        if len(exact) > 0:
            r = exact.iloc[0]
            return r['lam_min'], r['lam_max'], r['fit_fraction'], bool(r['enabled'])
        # Epoch-wide match: (epoch, 'All', line)
        epoch_wide = overrides_df[
            (overrides_df['Epoch'] == epoch) &
            (overrides_df['Spectra'] == 'All') &
            (overrides_df['Line'] == line_name)
        ]
        if len(epoch_wide) > 0:
            r = epoch_wide.iloc[0]
            return r['lam_min'], r['lam_max'], r['fit_fraction'], bool(r['enabled'])
    # Fall back to global
    g = global_df[global_df['Line'] == line_name]
    if len(g) > 0:
        r = g.iloc[0]
        return r['lam_min'], r['lam_max'], r['fit_fraction'], bool(r['enabled'])
    return None, None, None, False
