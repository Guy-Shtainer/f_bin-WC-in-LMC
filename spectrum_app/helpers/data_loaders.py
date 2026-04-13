"""
helpers/data_loaders.py — Cached data loaders for the Spectrum app.
All @st.cache_data functions extracted from 02_spectrum.py.
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.dirname(_HERE)
_ROOT = os.path.dirname(_APP_DIR)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from shared_lite import get_obs_manager


@st.cache_data
def load_spectrum(star_name: str, epoch: int, band: str):
    """Load normalized flux for a star/epoch/band. Falls back to raw FITS if unavailable."""
    obs = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    data = star.load_property('normalized_flux', epoch, band)
    if data is None:
        data = star.load_property('cleaned_normalized_flux', epoch, band)
    if data is not None:
        return data
    # Fallback: load raw FITS spectrum (for non-COMBINED bands)
    try:
        fit = star.load_observation(epoch, band=band)
        if fit is not None and fit.data is not None:
            wave = np.asarray(fit.data['WAVE'][0], dtype=float)  # nm
            flux = np.asarray(fit.data['FLUX'][0], dtype=float)
            return {'wavelengths': wave, 'normalized_flux': flux, '_raw': True}
    except Exception:
        pass
    return None


@st.cache_data
def load_rvs(star_name: str, epoch: int):
    """Load RV properties for a star/epoch."""
    obs = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    return star.load_property('RVs', epoch, 'COMBINED')


@st.cache_data
def get_mjd(star_name: str, epoch: int) -> float | None:
    """Extract MJD from FITS header."""
    obs = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    for b in ['NIR', 'VIS', 'UVB']:
        try:
            fit = star.load_observation(epoch, band=b)
            return float(fit.header['MJD-OBS'])
        except Exception:
            pass
    return None


@st.cache_data
def load_model_file(path: str):
    """Load a model spectrum file using plot.read_file()."""
    try:
        from plot import read_file
        mw, mf = read_file(path)
        return np.asarray(mw), np.asarray(mf)
    except Exception:
        return None, None


@st.cache_data
def load_all_lines_rvs(star_name: str) -> dict:
    """Load RVs for all emission lines for a star."""
    from pipeline.load_observations import load_star_rvs_all_lines
    return load_star_rvs_all_lines(star_name, obs=get_obs_manager())


@st.cache_data
def classify_star_line(star_name: str, line_name: str,
                       _threshold: float = 45.5, _sigma_factor: float = 4.0) -> dict:
    """Classify one star for a specific emission line (binary detection)."""
    all_lines = load_all_lines_rvs(star_name)
    if line_name not in all_lines or len(all_lines[line_name]['rv']) < 2:
        n = len(all_lines.get(line_name, {}).get('rv', []))
        return {'is_binary': None, 'best_dRV': 0.0, 'best_sigma': float('nan'), 'n_epochs': n}
    rv = np.array(all_lines[line_name]['rv'])
    rv_err = np.array(all_lines[line_name]['rv_err'])
    idx_min, idx_max = int(np.argmin(rv)), int(np.argmax(rv))
    abs_base = float(abs(rv[idx_max] - rv[idx_min]))
    sigma_base = math.sqrt(float(rv_err[idx_min])**2 + float(rv_err[idx_max])**2)
    best_dRV, best_sigma = abs_base, sigma_base
    found = (abs_base > _threshold) and ((abs_base - _sigma_factor * sigma_base) > 0.0)
    if not found:
        for i in range(len(rv)):
            for k in range(i + 1, len(rv)):
                if {i, k} == {idx_min, idx_max}:
                    continue
                d = float(abs(rv[k] - rv[i]))
                sig = math.sqrt(float(rv_err[i])**2 + float(rv_err[k])**2)
                if d > _threshold and (d - _sigma_factor * sig) > 0.0:
                    if d > best_dRV:
                        best_dRV, best_sigma = d, sig
                    found = True
    return {'is_binary': bool(found), 'best_dRV': best_dRV, 'best_sigma': best_sigma, 'n_epochs': len(rv)}


@st.cache_data
def is_star_cleaned(star_name: str) -> bool:
    """Check if any epoch/band has spatial cleaning done."""
    _obs = get_obs_manager()
    _star = _obs.load_star_instance(star_name, to_print=False)
    for ep in _star.get_all_epoch_numbers():
        for b in ['UVB', 'VIS', 'NIR']:
            if _star.load_property('include_range', ep, b) is not None:
                return True
    return False


@st.cache_data
def load_anchor_wavelengths(star_name: str, epoch: int, band: str):
    """Load ISE normalization anchor wavelengths (nm)."""
    obs = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    return star.load_property('norm_anchor_wavelengths', epoch, band)


@st.cache_data
def load_interpolated_flux(star_name: str, epoch: int, band: str):
    """Load ISE interpolated continuum."""
    obs = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    return star.load_property('interpolated_flux', epoch, band)


@st.cache_data
def get_peak_to_peak_epochs(star_name: str, line_name: str) -> dict | None:
    """Return {'ep_lo', 'ep_hi', 'rv_lo', 'rv_hi', 'delta_rv'} for the min-RV/max-RV epoch pair, or None."""
    all_lines = load_all_lines_rvs(star_name)
    if line_name not in all_lines:
        return None
    d = all_lines[line_name]
    rv = np.asarray(d['rv'])
    eps = d['epochs']
    if len(rv) < 2:
        return None
    idx_lo = int(np.argmin(rv))
    idx_hi = int(np.argmax(rv))
    if idx_lo == idx_hi:
        return None
    return {
        'ep_lo': eps[idx_lo], 'ep_hi': eps[idx_hi],
        'rv_lo': float(rv[idx_lo]), 'rv_hi': float(rv[idx_hi]),
        'delta_rv': float(abs(rv[idx_hi] - rv[idx_lo])),
    }
