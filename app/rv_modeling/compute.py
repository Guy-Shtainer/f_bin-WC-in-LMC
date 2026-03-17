"""rv_modeling/compute.py — Cached simulation and fitting functions."""
from __future__ import annotations

import sys

import numpy as np
import streamlit as st
from scipy.optimize import curve_fit

from shared import ROOT

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@st.cache_data(show_spinner="Simulating single-star Gaussian ranges …")
def compute_standard_ranges(
    n_epochs: int, n_sim: int = 500_000, seed: int = 12345,
) -> np.ndarray:
    """Return *sorted* ranges of n_epochs standard-normal draws (σ = 1)."""
    rng = np.random.default_rng(seed)
    samples = rng.standard_normal((n_sim, n_epochs))
    ranges = np.ptp(samples, axis=1)
    ranges.sort()
    return ranges


@st.cache_data(show_spinner="Simulating binary ΔRV distribution …")
def compute_binary_delta_rvs(
    n_sim: int, n_epochs: int, time_span: float,
    period_model: str, pi: float,
    e_model: str, e_max: float, q_model: str,
    seed: int, weight_A: float,
    # RV errors
    sigma_single: float = 0.0, sigma_measure: float = 0.0,
    # Period range
    logP_min: float = 0.15, logP_max: float = 5.0,
    # Mass ratio details
    q_min: float = 0.1, q_max: float = 2.0,
    q_flipped: bool = False,
    langer_q_mu: float = 0.7, langer_q_sigma: float = 0.2,
    # Primary mass
    mass_primary_model: str = "fixed",
    mass_primary_fixed: float = 10.0,
    mass_primary_min: float = 10.0, mass_primary_max: float = 20.0,
    # Langer component distributions
    dist_A: str = "gaussian", mu_A: float = 0.80, sigma_A: float = 0.35,
    dist_B: str = "reflected_lognormal", mu_B: float = 2.0, sigma_B: float = 0.45,
) -> np.ndarray:
    """Generate pure-binary ΔRVs using the orbital simulation engine."""
    from wr_bias_simulation import (
        simulate_delta_rv_sample, SimulationConfig, BinaryParameterConfig,
    )
    rng = np.random.default_rng(seed)
    sim_cfg = SimulationConfig(
        n_stars=n_sim, n_epochs=n_epochs, time_span=time_span,
        sigma_single=sigma_single, sigma_measure=sigma_measure,
    )
    langer_params: dict = {}
    if period_model == "langer2020":
        langer_params = {
            "weight_A": float(weight_A),
            "dist_A": dist_A, "mu_A": float(mu_A), "sigma_A": float(sigma_A),
            "dist_B": dist_B, "mu_B": float(mu_B), "sigma_B": float(sigma_B),
        }
    bin_cfg = BinaryParameterConfig(
        period_model=period_model, e_model=e_model, e_max=e_max,
        q_model=q_model, langer_period_params=langer_params,
        logP_min=logP_min, logP_max=logP_max,
        q_range=(q_min, q_max), q_flipped=q_flipped,
        langer_q_mu=langer_q_mu, langer_q_sigma=langer_q_sigma,
        mass_primary_model=mass_primary_model,
        mass_primary_fixed=mass_primary_fixed,
        mass_primary_range=(mass_primary_min, mass_primary_max),
    )
    return simulate_delta_rv_sample(
        f_bin=1.0, pi=pi, sim_cfg=sim_cfg, bin_cfg=bin_cfg, rng=rng,
    )


def _empirical_survival(sorted_vals: np.ndarray, t_arr: np.ndarray) -> np.ndarray:
    """S(t) = P(X > t) from a pre-sorted empirical sample."""
    idx = np.searchsorted(sorted_vals, t_arr, side="right")
    return 1.0 - idx / len(sorted_vals)


def _fit_models(t_full, t_dots, f_obs, f_dots, e_dots, raw_frac, sig_err,
                std_surv_fn, binary_surv_fn):
    """Run both Empirical and Gaussian fits. Returns (emp_dict, gauss_dict)."""
    mid_t = t_full[:-1] + 0.5
    dt = np.diff(t_full)

    # ── Empirical: fits (f_bin, σ_single) ─────────────────────────────
    def _model_emp(t, f_bin, sigma_s):
        return (1.0 - f_bin) * std_surv_fn(t / sigma_s) + f_bin * binary_surv_fn(t)

    emp = None
    try:
        p0_raw, _ = curve_fit(_model_emp, t_full, raw_frac,
                              p0=[0.4, 10.0], bounds=([0, 0.1], [1, 100]))
        popt, pcov = curve_fit(_model_emp, t_full, f_obs, p0=p0_raw,
                               bounds=([0, 0.1], [1, 100]),
                               sigma=sig_err, absolute_sigma=True)
        perr = np.sqrt(np.diag(pcov))
        surv_s = std_surv_fn(t_full / popt[1])
        surv_b = binary_surv_fn(t_full)
        pdf_s = np.maximum(0, -np.diff(surv_s) / dt)
        pdf_b = np.maximum(0, -np.diff(surv_b) / dt)
        w_s = (1 - popt[0]) * pdf_s
        w_b = popt[0] * pdf_b
        cross = w_b > w_s
        fitted_dots = _model_emp(t_dots, *popt)
        residuals = (f_dots - fitted_dots) / e_dots
        chi2 = float(np.sum(residuals ** 2))
        ndof = max(1, len(t_dots) - 2)
        emp = dict(
            f_fit=float(popt[0]), f_err=float(perr[0]),
            sigma_s=float(popt[1]), sigma_s_err=float(perr[1]),
            fitted_full=_model_emp(t_full, *popt),
            fitted_dots=fitted_dots, residuals=residuals,
            chi2_red=chi2 / ndof, ndof=ndof,
            surv_s=surv_s, surv_b=surv_b,
            single_comp=(1 - popt[0]) * surv_s,
            binary_comp=popt[0] * surv_b,
            w_pdf_s=w_s, w_pdf_b=w_b, mid_t=mid_t,
            t_optimal=float(mid_t[np.argmax(cross)]) if np.any(cross) else None,
        )
    except Exception as exc:
        st.warning(f"Empirical fit failed: {exc}")

    # ── Gaussian: fits (σ_single, σ_binary, f_bin) ────────────────────
    def _model_gauss(t, sigma_s, sigma_b, f_bin):
        return (1 - f_bin) * std_surv_fn(t / sigma_s) + f_bin * std_surv_fn(t / sigma_b)

    gauss = None
    try:
        p0_gr, _ = curve_fit(_model_gauss, t_full, raw_frac,
                             p0=[10, 60, 0.4],
                             bounds=([0.1, 5, 0], [100, 300, 1]))
        popt_g, pcov_g = curve_fit(_model_gauss, t_full, f_obs, p0=p0_gr,
                                   bounds=([0.1, 5, 0], [100, 300, 1]),
                                   sigma=sig_err, absolute_sigma=True)
        perr_g = np.sqrt(np.diag(pcov_g))
        surv_sg = std_surv_fn(t_full / popt_g[0])
        surv_bg = std_surv_fn(t_full / popt_g[1])
        pdf_sg = np.maximum(0, -np.diff(surv_sg) / dt)
        pdf_bg = np.maximum(0, -np.diff(surv_bg) / dt)
        w_sg = (1 - popt_g[2]) * pdf_sg
        w_bg = popt_g[2] * pdf_bg
        cross_g = w_bg > w_sg
        fitted_dots_g = _model_gauss(t_dots, *popt_g)
        res_g = (f_dots - fitted_dots_g) / e_dots
        chi2_g = float(np.sum(res_g ** 2))
        ndof_g = max(1, len(t_dots) - 3)
        gauss = dict(
            sigma_s=float(popt_g[0]), sigma_s_err=float(perr_g[0]),
            sigma_b=float(popt_g[1]), sigma_b_err=float(perr_g[1]),
            f_fit=float(popt_g[2]), f_err=float(perr_g[2]),
            fitted_full=_model_gauss(t_full, *popt_g),
            fitted_dots=fitted_dots_g, residuals=res_g,
            chi2_red=chi2_g / ndof_g, ndof=ndof_g,
            surv_s=surv_sg, surv_b=surv_bg,
            single_comp=(1 - popt_g[2]) * surv_sg,
            binary_comp=popt_g[2] * surv_bg,
            w_pdf_s=w_sg, w_pdf_b=w_bg, mid_t=mid_t,
            t_optimal=float(mid_t[np.argmax(cross_g)]) if np.any(cross_g) else None,
        )
    except Exception as exc:
        st.warning(f"Gaussian fit failed: {exc}")

    return emp, gauss
