"""
bias_app/data_loader.py
───────────────────────
Framework-agnostic data loading with functools.lru_cache.
Replaces Streamlit's @st.cache_data for the Dash app.
"""
from __future__ import annotations

import functools
import json
import os
import sys

import numpy as np

# ── Path setup ───────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
SETTINGS_PATH = os.path.join(ROOT, 'settings', 'user_settings.json')

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Import the ACTUAL functions from pipeline (these are the real signatures)
from pipeline.load_observations import (
    load_observed_delta_rvs as _pipeline_load_obs_drv,
    load_cadence_library as _pipeline_load_cadence,
)
from ObservationClass import ObservationManager
import specs


@functools.lru_cache(maxsize=1)
def get_obs_manager() -> ObservationManager:
    """Singleton ObservationManager."""
    return ObservationManager()


@functools.lru_cache(maxsize=4)
def load_observed_delta_rvs(settings_hash: str | None = None) -> np.ndarray:
    """Load observed delta-RV array from all stars.

    Returns
    -------
    obs_delta_rv : np.ndarray, shape (N_stars,)
        Peak-to-peak ΔRV for each star.
    """
    settings = load_settings()
    om = get_obs_manager()
    # _pipeline_load_obs_drv returns (np.ndarray, dict) — we only need the array
    obs_delta_rv, _detail = _pipeline_load_obs_drv(settings, om)
    return obs_delta_rv


@functools.lru_cache(maxsize=4)
def load_cadence_library(settings_hash: str | None = None):
    """Load per-star cadence (observation times) for cadence-aware sims.

    Returns
    -------
    cadence_list : list of np.ndarray
        Relative observation times per star.
    """
    om = get_obs_manager()
    # _pipeline_load_cadence returns (list[np.ndarray], np.ndarray weights)
    cadence_list, _weights = _pipeline_load_cadence(om)
    return cadence_list


def load_settings() -> dict:
    """Load user_settings.json."""
    if not os.path.exists(SETTINGS_PATH):
        return {}
    with open(SETTINGS_PATH) as f:
        return json.load(f)


def load_grid_result(path: str) -> dict:
    """Load a saved .npz grid result file."""
    return dict(np.load(path, allow_pickle=True))
