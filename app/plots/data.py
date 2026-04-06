"""plots/data.py — Cached data loaders and helper functions for plots."""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import streamlit as st

from shared import get_obs_manager, ROOT

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import specs  # noqa: E402

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
NRES_STARS = ['WR 52', 'WR17']
BANDS = ['COMBINED', 'UVB', 'VIS', 'NIR']
c_kms = 299792.458

_CCF_JSON_PATH = os.path.join(ROOT, 'ccf_settings_with_global_lines.json')


# ─────────────────────────────────────────────────────────────────────────────
# CCF config loaders
# ─────────────────────────────────────────────────────────────────────────────

def _load_ccf_settings() -> dict:
    if '_ccf_json' not in st.session_state:
        with open(_CCF_JSON_PATH) as f:
            st.session_state['_ccf_json'] = json.load(f)
    return st.session_state['_ccf_json']


def _get_emission_lines() -> dict:
    cfg = _load_ccf_settings()
    return cfg.get('emission_lines_default', {})


def _get_star_config() -> dict:
    cfg = _load_ccf_settings()
    return {s['star_name']: s for s in cfg.get('stars', [])}


# ─────────────────────────────────────────────────────────────────────────────
# Spectrum / property loaders
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data
def _load_normalized_spec(star_name: str, epoch: int, band: str, use_cleaned: bool = True):
    obs = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    if use_cleaned:
        data = star.load_property('cleaned_normalized_flux', epoch, band)
        if data is not None and isinstance(data, dict):
            return data
    data = star.load_property('normalized_flux', epoch, band)
    if isinstance(data, dict):
        return data
    return None


@st.cache_data
def _load_spectrum(star_name: str, epoch: int, band: str, use_cleaned: bool = True):
    """Load spectrum: tries cleaned/normalized .npz first, falls back to raw FITS.

    Returns (wave_A, flux, source_type) where source_type is
    'cleaned_normalized', 'normalized', or 'raw'.  All three are None on failure.
    """
    obs = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    # Try cleaned normalized .npz
    if use_cleaned:
        data = star.load_property('cleaned_normalized_flux', epoch, band)
        if data is not None and isinstance(data, dict):
            wave = np.asarray(data.get('wavelengths', data.get('wave', [])))
            flux = np.asarray(data.get('normalized_flux', data.get('flux', [])))
            if len(wave) > 0:
                return wave * 10.0, flux, 'cleaned_normalized'
    # Try normalized .npz
    data = star.load_property('normalized_flux', epoch, band)
    if data is not None and isinstance(data, dict):
        wave = np.asarray(data.get('wavelengths', data.get('wave', [])))
        flux = np.asarray(data.get('normalized_flux', data.get('flux', [])))
        if len(wave) > 0:
            return wave * 10.0, flux, 'normalized'
    # Fallback: raw FITS (like StarClass.plot_spectra)
    try:
        fit = star.load_observation(epoch, band)
        if fit is not None:
            wave_nm = np.asarray(fit.data['WAVE'][0])
            flux = np.asarray(fit.data['FLUX'][0])
            return wave_nm * 10.0, flux, 'raw'
    except Exception:
        pass
    return None, None, None


@st.cache_data
def _load_raw_spec(star_name: str, epoch: int, band: str):
    obs = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    try:
        fit = star.load_observation(epoch, band)
        if fit is None:
            return None
        wave_nm = np.asarray(fit.data['WAVE'][0])
        flux = np.asarray(fit.data['FLUX'][0])
        err = np.asarray(fit.data['ERR'][0]) if 'ERR' in fit.data.dtype.names else None
        wave_A = wave_nm * 10.0
        return wave_A, flux, err
    except Exception:
        return None


@st.cache_data
def _load_continuum(star_name: str, epoch: int, band: str):
    obs = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    data = star.load_property('interpolated_flux', epoch, band)
    if isinstance(data, dict):
        return data
    return None


@st.cache_data
def _load_rv_property(star_name: str, epoch: int, band: str = 'COMBINED'):
    obs = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    data = star.load_property('RVs', epoch, band)
    if isinstance(data, dict):
        return data
    return None


def _extract_rv(rv_entry):
    if rv_entry is None:
        return None, None
    if hasattr(rv_entry, 'item'):
        rv_entry = rv_entry.item()
    if isinstance(rv_entry, dict):
        rv = rv_entry.get('full_RV', None)
        err = rv_entry.get('full_RV_err', None)
        if rv is not None:
            rv = float(rv)
        if err is not None:
            err = float(err)
        return rv, err
    return None, None


def _wilson_score_interval(k: int, n: int, z: float = 1.0) -> tuple:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z ** 2 / n
    center = (p + z ** 2 / (2 * n)) / denom
    margin = (z * np.sqrt((p * (1 - p) / n) + (z ** 2 / (4 * n ** 2)))) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def _get_epochs(star_name: str):
    """Get epoch list for a star, with caching."""
    obs = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    return star.get_all_epoch_numbers()
