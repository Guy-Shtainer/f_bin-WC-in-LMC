"""rv_modeling/page.py — Top-level orchestrator for the RV Modeling page."""
from __future__ import annotations

import numpy as np
import streamlit as st

from shared_lite import (
    get_settings_manager, cached_load_observed_delta_rvs, settings_hash,
    get_palette, COLOR_BINARY, COLOR_SINGLE, cached_load_cadence,
)

from rv_modeling.helpers import NSIGMA_DETECT, T_MAX, BIN_METHODS
from rv_modeling.tab_simulation import render_tab_simulation
from rv_modeling.tab_fitting import render_tab_fitting
from rv_modeling.tab_playground import render_tab_playground
from rv_modeling.tabs import (
    render_tab_sample_fit, render_tab_fraction_recovery,
    render_tab_global_correction,
)


def render_rv_modeling_page() -> None:
    st.title("Statistical RV Modeling")
    st.caption(
        "Explore binary RV distributions, fit parametric models to the observed "
        "binary fraction vs ΔRV threshold, and test models interactively."
    )

    pal = get_palette()

    # ── Load observed data ─────────────────────────────────────────────
    sm = get_settings_manager()
    current_settings = sm.load()
    s_hash = settings_hash(current_settings)
    obs_drv, detail = cached_load_observed_delta_rvs(s_hash)

    names = sorted(detail.keys())
    n_stars = len(names)
    p2p = np.array([detail[n]["best_dRV"] for n in names])
    p2p_err = np.array([detail[n]["best_sigma"] for n in names])

    star_centered_rvs: dict = {}
    for nm in names:
        rvs = np.asarray(detail[nm].get("rv", []), dtype=float)
        rvs = rvs[rvs != 0]
        if len(rvs) > 0:
            star_centered_rvs[nm] = rvs - np.median(rvs)

    t_full = np.arange(0, T_MAX, dtype=float)
    is_sig = (p2p - NSIGMA_DETECT * p2p_err) > 0.0
    f_obs = np.array([np.sum(is_sig & (p2p > t)) / n_stars for t in t_full])
    raw_frac = np.array([np.sum(p2p > t) / n_stars for t in t_full])
    sig_err = np.sqrt(f_obs * (1.0 - f_obs) / n_stars) + 1e-4

    diffs = np.diff(f_obs, prepend=-999.0)
    change_mask = diffs != 0.0
    t_dots = t_full[change_mask]
    f_dots = f_obs[change_mask]
    e_dots = sig_err[change_mask]

    # ── RV-modeling settings sub-tree ─────────────────────────────────
    rvm_settings = current_settings.get('rv_modeling', {})
    _RVM = ['rv_modeling']  # root path for sm.save()

    # ── Histogram binning control ──────────────────────────────────────
    _bm_def = rvm_settings.get('bin_method', 'Auto (Freedman-Diaconis)')
    _bm_idx = BIN_METHODS.index(_bm_def) if _bm_def in BIN_METHODS else 0
    with st.sidebar:
        st.markdown("**Histogram binning**")
        bin_method = st.selectbox(
            "Binning method", BIN_METHODS, index=_bm_idx, key="rvm_bin_method",
            on_change=lambda: sm.save(_RVM + ['bin_method'],
                                      value=st.session_state['rvm_bin_method']),
        )
        manual_bins = int(rvm_settings.get('manual_bins', 50))
        if bin_method == "Manual":
            manual_bins = st.number_input(
                "Number of bins", value=manual_bins, step=5,
                key="rvm_manual_bins",
                on_change=lambda: sm.save(_RVM + ['manual_bins'],
                                          value=st.session_state['rvm_manual_bins']),
            )

    # ── Load cadence library for physics-based mode ──────────────────
    cadence_lib, _ = cached_load_cadence(s_hash)
    cadence_tuples = tuple(tuple(float(v) for v in t) for t in cadence_lib)

    # ── Package observed data for all tabs ─────────────────────────────
    obs_data = dict(
        pal=pal, t_full=t_full, f_obs=f_obs, raw_frac=raw_frac,
        sig_err=sig_err, t_dots=t_dots, f_dots=f_dots, e_dots=e_dots,
        change_mask=change_mask,
        is_sig=is_sig, p2p=p2p, p2p_err=p2p_err,
        names=names, n_stars=n_stars,
        star_centered_rvs=star_centered_rvs,
        bin_method=bin_method, manual_bins=manual_bins,
        cadence_tuples=cadence_tuples,
        n_cadence_stars=len(cadence_lib),
        sm=sm, rvm_settings=rvm_settings,
    )

    # ── Tabs ───────────────────────────────────────────────────────────
    tab_a, tab_b, tab_c, tab_d, tab_e, tab_f = st.tabs([
        "Simulate Binary RVs", "Model Fitting", "Playground",
        "Sample Fit", "Fraction Recovery", "Global Correction",
    ])

    with tab_a:
        render_tab_simulation(obs_data)
    with tab_b:
        render_tab_fitting(obs_data)
    with tab_c:
        render_tab_playground(obs_data)
    with tab_d:
        render_tab_sample_fit(obs_data)
    with tab_e:
        render_tab_fraction_recovery(obs_data)
    with tab_f:
        render_tab_global_correction(obs_data)
