"""rv_modeling/page.py — Top-level orchestrator for the RV Modeling page."""
from __future__ import annotations

import numpy as np
import streamlit as st
from scipy.interpolate import interp1d

from shared import (
    get_settings_manager, cached_load_observed_delta_rvs, settings_hash,
    get_palette, COLOR_BINARY, COLOR_SINGLE,
)

from rv_modeling.helpers import NSIGMA_DETECT, T_MAX
from rv_modeling.compute import (
    compute_standard_ranges, compute_binary_delta_rvs,
    _empirical_survival, _fit_models,
)
from rv_modeling.tabs import (
    render_tab_sample_fit, render_tab_fraction_recovery,
    render_tab_global_correction, render_tab_population_sim,
)


def render_rv_modeling_page() -> None:  # noqa: C901
    st.title("Statistical RV Modeling")
    st.caption(
        "Two-component mixture model: fits the observed binary fraction vs ΔRV "
        "threshold curve using **two approaches side-by-side** — an empirical "
        "binary ΔRV distribution from orbital simulations, and a Gaussian "
        "analytical model."
    )

    pal = get_palette()

    # ── load observed data ───────────────────────────────────────────────
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

    # ==================================================================
    # PLAYGROUND — at top of page
    # ==================================================================
    st.subheader("Parameter Playground")

    # ── Preset callbacks (on_click, run before widgets) ───────────────
    def _preset_dsilva():
        for k, v in {
            "rvm_period": "powerlaw", "rvm_emod": "flat", "rvm_qmod": "flat",
            "rvm_sigma_s": 5.5, "rvm_sigma_m": 1.622,
            "rvm_logPmin": 0.15, "rvm_logPmax": 5.0,
            "rvm_q_min": 0.1, "rvm_q_max": 2.0, "rvm_q_flip": False,
            "rvm_mass_model": "fixed", "rvm_mass_fixed": 10.0,
        }.items():
            st.session_state[k] = v

    def _preset_langer():
        for k, v in {
            "rvm_period": "langer2020", "rvm_emod": "zero",
            "rvm_qmod": "lognormal",
            "rvm_sigma_s": 5.5, "rvm_sigma_m": 1.622,
            "rvm_logPmin": 0.5, "rvm_logPmax": 3.5,
            "rvm_q_min": 0.1, "rvm_q_max": 2.0, "rvm_q_flip": False,
            "rvm_lq_mu": 0.65, "rvm_lq_sig": 0.3,
            "rvm_mass_model": "fixed", "rvm_mass_fixed": 10.0,
            "rvm_wA": 0.20,
            "rvm_distA": "gaussian", "rvm_muA": 0.80, "rvm_sigA": 0.35,
            "rvm_distB": "reflected_lognormal", "rvm_muB": 2.0, "rvm_sigB": 0.45,
        }.items():
            st.session_state[k] = v

    # ── Row 1: Core simulation controls ───────────────────────────────
    st.markdown(
        "**Simulation controls** — change parameters, then click "
        "**Recompute** to re-run"
    )

    r1a, r1b, r1c, r1d, r1e, r1f = st.columns(6)
    with r1a:
        period_model = st.selectbox(
            "Period model", ["powerlaw", "langer2020"],
            index=0, key="rvm_period",
        )
    with r1b:
        pi_val: float = 0.0
        weight_A: float = 0.3
        if period_model == "powerlaw":
            pi_val = st.slider("π (power-law)", -3.0, 3.0, 0.0, 0.1,
                               key="rvm_pi")
        else:
            weight_A = st.slider("Weight A", 0.0, 1.0, 0.20, 0.05,
                                 key="rvm_wA")
    with r1c:
        e_model = st.selectbox("Eccentricity", ["flat", "zero"],
                               key="rvm_emod")
    with r1d:
        e_max: float = 0.9
        if e_model == "flat":
            e_max = st.slider("e_max", 0.1, 0.95, 0.9, 0.05, key="rvm_emax")
        else:
            e_max = 0.0
            st.markdown("*e = 0*")
    with r1e:
        rv_sigma_single = st.number_input(
            "σ_single (km/s)", 0.0, 500.0, 5.5, 0.5, key="rvm_sigma_s",
            help="Intrinsic single-star RV scatter.",
        )
    with r1f:
        _err_options = ["Fixed", "Normal", "Log-normal", "Gamma",
                        "Weibull", "Exponential", "Flat (uniform)"]
        err_model_type = st.selectbox(
            "Error model", _err_options, index=0, key="rvm_err_model",
            help="Fixed = constant σ. Distribution = per-epoch error drawn.",
        )

    # ── Row 1b: Error model parameters ────────────────────────────────
    _RVE_DISTS = {
        "Normal": "norm", "Log-normal": "lognorm", "Gamma": "gamma",
        "Weibull": "weibull_min", "Exponential": "expon",
        "Flat (uniform)": "uniform",
    }
    _RVE_PARAMS = {
        "Normal": [("μ (loc)", 2.0, -50.0, 50.0, 0.01),
                   ("σ (scale)", 1.0, 0.01, 50.0, 0.01)],
        "Log-normal": [("s (shape)", 0.5, 0.01, 5.0, 0.01),
                       ("loc", 0.0, -50.0, 50.0, 0.01),
                       ("scale", 1.0, 0.01, 50.0, 0.01)],
        "Gamma": [("a (shape)", 2.0, 0.01, 20.0, 0.01),
                  ("loc", 0.0, -50.0, 50.0, 0.01),
                  ("scale", 1.0, 0.01, 50.0, 0.01)],
        "Weibull": [("c (shape)", 1.5, 0.01, 10.0, 0.01),
                    ("loc", 0.0, -50.0, 50.0, 0.01),
                    ("scale", 1.0, 0.01, 50.0, 0.01)],
        "Exponential": [("loc", 0.0, -50.0, 50.0, 0.01),
                        ("scale", 1.0, 0.01, 50.0, 0.01)],
        "Flat (uniform)": [("loc (start)", 0.0, -50.0, 50.0, 0.01),
                           ("scale (width)", 5.0, 0.01, 100.0, 0.01)],
    }

    if err_model_type == "Fixed":
        rv_sigma_measure = st.number_input(
            "σ_measure (km/s)", 0.0, 20.0, 1.622, 0.001,
            format="%.3f", key="rvm_sigma_m",
            help="Constant per-epoch measurement uncertainty.",
        )
    else:
        _pmeta = _RVE_PARAMS.get(err_model_type, [])
        _err_params = []
        if _pmeta:
            _ecols = st.columns(len(_pmeta))
            for i, (label, default, pmin, pmax, step) in enumerate(_pmeta):
                with _ecols[i]:
                    _val = st.number_input(
                        label, min_value=pmin, max_value=pmax,
                        value=float(st.session_state.get(f"rvm_errp_{i}", default)),
                        step=step, format="%.4f", key=f"rvm_errp_{i}",
                    )
                _err_params.append(_val)
        # Compute distribution mean as sigma_measure
        import scipy.stats as _st_stats
        _scipy_name = _RVE_DISTS.get(err_model_type, "norm")
        try:
            _dist = getattr(_st_stats, _scipy_name)
            rv_sigma_measure = float(_dist.mean(*_err_params))
            if not np.isfinite(rv_sigma_measure) or rv_sigma_measure <= 0:
                rv_sigma_measure = 1.622
        except Exception:
            rv_sigma_measure = 1.622
        st.caption(
            f"**{err_model_type}** distribution → mean = "
            f"{rv_sigma_measure:.3f} km/s (used as σ_measure)"
        )

    # ── Row 2: Sim size + actions ─────────────────────────────────────
    r2a, r2b, r2c, r2d, r2e, r2f = st.columns(6)
    with r2a:
        n_sim = st.select_slider(
            "N_sim", options=[10_000, 50_000, 100_000, 200_000, 500_000],
            value=100_000, key="rvm_nsim",
        )
    with r2b:
        n_epochs = st.number_input("N_epochs", 2, 20, 6, key="rvm_nep")
    with r2c:
        time_span = st.number_input("Time span (d)", 100.0, 10_000.0,
                                    3650.0, step=100.0, key="rvm_ts")
    with r2d:
        seed = st.number_input("Seed", 0, 99999, 42, key="rvm_seed")
    with r2e:
        n_prior = st.number_input("N prior", 0, 10, 3, key="rvm_nprior",
                                  help="Bartzakos known binaries.")
    with r2f:
        pc1, pc2 = st.columns(2)
        with pc1:
            st.button("Dsilva", key="rvm_preset_d",
                      on_click=_preset_dsilva, use_container_width=True)
        with pc2:
            st.button("Langer", key="rvm_preset_l",
                      on_click=_preset_langer, use_container_width=True)

    # ── Expanders for detailed parameters ─────────────────────────────
    exp_col1, exp_col2, exp_col3 = st.columns(3)

    with exp_col1:
        with st.expander("Period Distribution", expanded=False):
            logP_min = st.number_input("logP_min", 0.01, 10.0, 0.15,
                                       0.05, key="rvm_logPmin")
            logP_max = st.number_input("logP_max", 0.1, 10.0, 5.0,
                                       0.1, key="rvm_logPmax")
            if period_model == "langer2020":
                st.markdown("**Component A (short-period)**")
                _dist_opts = ["gaussian", "lognormal", "reflected_lognormal",
                              "empirical", "flat"]
                dist_A = st.selectbox("Dist A", _dist_opts, index=0,
                                      key="rvm_distA")
                la1, la2 = st.columns(2)
                with la1:
                    mu_A = st.number_input("μ_A", 0.01, 10.0, 0.80,
                                           0.05, key="rvm_muA")
                with la2:
                    sigma_A = st.number_input("σ_A", 0.01, 5.0, 0.35,
                                              0.05, key="rvm_sigA")
                st.markdown("**Component B (long-period)**")
                dist_B = st.selectbox("Dist B", _dist_opts, index=2,
                                      key="rvm_distB")
                lb1, lb2 = st.columns(2)
                with lb1:
                    mu_B = st.number_input("μ_B", 0.01, 10.0, 2.0,
                                           0.05, key="rvm_muB")
                with lb2:
                    sigma_B = st.number_input("σ_B", 0.01, 5.0, 0.45,
                                              0.05, key="rvm_sigB")
            else:
                dist_A, mu_A, sigma_A = "gaussian", 0.80, 0.35
                dist_B, mu_B, sigma_B = "reflected_lognormal", 2.0, 0.45

    with exp_col2:
        with st.expander("Mass & Mass Ratio", expanded=False):
            _q_opts = ["flat", "gaussian", "lognormal",
                       "reflected_lognormal", "empirical"]
            q_model = st.selectbox("q model", _q_opts, index=0,
                                   key="rvm_qmod")
            qq1, qq2 = st.columns(2)
            with qq1:
                q_min = st.number_input("q_min", 0.01, 50.0, 0.1,
                                        0.05, key="rvm_q_min")
            with qq2:
                q_max = st.number_input("q_max", 0.01, 50.0, 2.0,
                                        0.1, key="rvm_q_max")
            q_flipped = st.checkbox("q flipped (M2=M1/q)", key="rvm_q_flip")
            langer_q_mu, langer_q_sigma = 0.7, 0.2
            if q_model not in ("flat", "empirical"):
                lqm1, lqm2 = st.columns(2)
                with lqm1:
                    langer_q_mu = st.number_input("q μ", 0.01, 50.0, 0.7,
                                                  0.05, key="rvm_lq_mu")
                with lqm2:
                    langer_q_sigma = st.number_input("q σ", 0.01, 50.0, 0.2,
                                                     0.05, key="rvm_lq_sig")
            st.markdown("---")
            mass_model = st.selectbox("Primary mass", ["fixed", "uniform"],
                                      key="rvm_mass_model")
            mass_fixed = 10.0
            mass_min, mass_max = 10.0, 20.0
            if mass_model == "fixed":
                mass_fixed = st.number_input("M₁ (M☉)", 1.0, 200.0, 10.0,
                                             1.0, key="rvm_mass_fixed")
            else:
                mm1, mm2 = st.columns(2)
                with mm1:
                    mass_min = st.number_input("M₁ min", 1.0, 200.0, 10.0,
                                               1.0, key="rvm_mass_min")
                with mm2:
                    mass_max = st.number_input("M₁ max", 1.0, 200.0, 20.0,
                                               1.0, key="rvm_mass_max")

    with exp_col3:
        recompute_btn = st.button(
            "🔬 Recompute Simulation", type="primary",
            use_container_width=True,
        )
        st.caption("Re-runs simulation with current parameters and re-fits both models.")

    # ==================================================================
    # Simulation + fitting (runs on Recompute or first load)
    # ==================================================================
    should_run = recompute_btn or "rvm_results" not in st.session_state
    if should_run:
      with st.spinner("Running simulation and fitting both models..."):
        binary_drvs = compute_binary_delta_rvs(
            n_sim=int(n_sim), n_epochs=int(n_epochs),
            time_span=float(time_span), period_model=period_model,
            pi=float(pi_val), e_model=e_model, e_max=float(e_max),
            q_model=q_model, seed=int(seed), weight_A=float(weight_A),
            sigma_single=float(rv_sigma_single),
            sigma_measure=float(rv_sigma_measure),
            logP_min=float(logP_min), logP_max=float(logP_max),
            q_min=float(q_min), q_max=float(q_max),
            q_flipped=bool(q_flipped),
            langer_q_mu=float(langer_q_mu),
            langer_q_sigma=float(langer_q_sigma),
            mass_primary_model=mass_model,
            mass_primary_fixed=float(mass_fixed),
            mass_primary_min=float(mass_min),
            mass_primary_max=float(mass_max),
            dist_A=dist_A, mu_A=float(mu_A), sigma_A=float(sigma_A),
            dist_B=dist_B, mu_B=float(mu_B), sigma_B=float(sigma_B),
        )
        sorted_binary = np.sort(binary_drvs)
        sorted_std_ranges = compute_standard_ranges(int(n_epochs))

        t_max_b = max(500.0, float(np.max(binary_drvs)) * 1.1)
        t_interp_b = np.linspace(0, t_max_b, 3000)
        surv_b_raw = _empirical_survival(sorted_binary, t_interp_b)
        binary_surv_fn = interp1d(t_interp_b, surv_b_raw, kind="linear",
                                  bounds_error=False, fill_value=(1.0, 0.0))

        t_interp_s = np.linspace(0, 15, 3000)
        surv_s_raw = _empirical_survival(sorted_std_ranges, t_interp_s)
        std_surv_fn = interp1d(t_interp_s, surv_s_raw, kind="linear",
                               bounds_error=False, fill_value=(1.0, 0.0))

        emp, gauss = _fit_models(
            t_full, t_dots, f_obs, f_dots, e_dots, raw_frac, sig_err,
            std_surv_fn, binary_surv_fn,
        )

        if emp is None and gauss is None:
            st.error("Both models failed to fit.")
            return

        st.session_state["_rvm_bestfit_fbin"] = (
            emp["f_fit"] if emp else (gauss["f_fit"] if gauss else 0.4))
        st.session_state["_rvm_bestfit_sigma_s"] = (
            emp["sigma_s"] if emp else (gauss["sigma_s"] if gauss else 10.0))
        st.session_state["_rvm_bestfit_sigma_b"] = (
            gauss["sigma_b"] if gauss else 60.0)

        st.session_state["rvm_results"] = dict(
            emp=emp, gauss=gauss,
            binary_drvs=binary_drvs,
            surv_s_x=t_interp_s, surv_s_y=surv_s_raw,
            surv_b_x=t_interp_b, surv_b_y=surv_b_raw,
            sim_info=dict(
                period_model=period_model, pi=pi_val, weight_A=weight_A,
                n_sim=int(n_sim), n_epochs=int(n_epochs),
                time_span=time_span, e_model=e_model, e_max=e_max,
                q_model=q_model, seed=int(seed),
                sigma_single=rv_sigma_single, sigma_measure=rv_sigma_measure,
                logP_min=logP_min, logP_max=logP_max,
                q_min=q_min, q_max=q_max, q_flipped=q_flipped,
                mass_model=mass_model, mass_fixed=mass_fixed,
            ),
        )

    # ── Instant controls (no re-simulation) ───────────────────────────
    st.markdown("---")
    st.markdown("**Instant controls** — adjust and see plots update immediately")
    ic1, ic2, ic3 = st.columns(3)
    with ic1:
        pg_fbin = st.slider(
            "f_bin (binary fraction)", 0.0, 1.0,
            st.session_state.get("_rvm_bestfit_fbin", 0.4),
            0.01, key="pg_fbin",
        )
    with ic2:
        pg_sigma_s = st.slider(
            "σ_single (km/s)", 0.5, 80.0,
            st.session_state.get("_rvm_bestfit_sigma_s", 10.0),
            0.5, key="pg_sigma_s",
        )
    with ic3:
        pg_sigma_b = st.slider(
            "σ_binary (km/s) — Gaussian model", 5.0, 300.0,
            st.session_state.get("_rvm_bestfit_sigma_b", 60.0),
            1.0, key="pg_sigma_b",
        )

    st.markdown("---")

    # ── Retrieve results ─────────────────────────────────────────────────
    res = st.session_state.get("rvm_results")
    if res is None:
        st.info("Click **Recompute** to run the simulation and fit.")
        return

    emp = res["emp"]
    gauss = res["gauss"]
    binary_drvs = res["binary_drvs"]
    sim_info = res["sim_info"]

    # Rebuild survival functions for instant playground
    std_surv_fn = interp1d(res["surv_s_x"], res["surv_s_y"], kind="linear",
                           bounds_error=False, fill_value=(1.0, 0.0))
    bin_surv_fn = interp1d(res["surv_b_x"], res["surv_b_y"], kind="linear",
                           bounds_error=False, fill_value=(1.0, 0.0))

    # Instant playground models (from current slider values)
    pg_emp_curve = (1 - pg_fbin) * std_surv_fn(t_full / pg_sigma_s) + \
                   pg_fbin * bin_surv_fn(t_full)
    pg_gauss_curve = (1 - pg_fbin) * std_surv_fn(t_full / pg_sigma_s) + \
                     pg_fbin * std_surv_fn(t_full / pg_sigma_b)

    # Chi-squared for playground
    pg_emp_d = (1 - pg_fbin) * std_surv_fn(t_dots / pg_sigma_s) + \
               pg_fbin * bin_surv_fn(t_dots)
    pg_gauss_d = (1 - pg_fbin) * std_surv_fn(t_dots / pg_sigma_s) + \
                 pg_fbin * std_surv_fn(t_dots / pg_sigma_b)
    pg_chi2_emp = float(np.sum(((f_dots - pg_emp_d) / e_dots) ** 2)) / max(1, len(t_dots) - 2)
    pg_chi2_gauss = float(np.sum(((f_dots - pg_gauss_d) / e_dots) ** 2)) / max(1, len(t_dots) - 3)

    # Best t_optimal for classification
    t_optimal_main = None
    if emp is not None:
        t_optimal_main = emp.get("t_optimal")
    elif gauss is not None:
        t_optimal_main = gauss.get("t_optimal")
    if t_optimal_main is None:
        t_optimal_main = 45.5

    # ── Build context dict for tabs ──────────────────────────────────────
    ctx = dict(
        pal=pal, t_full=t_full, f_obs=f_obs, raw_frac=raw_frac,
        sig_err=sig_err, t_dots=t_dots, f_dots=f_dots, e_dots=e_dots,
        change_mask=change_mask,
        is_sig=is_sig, p2p=p2p, p2p_err=p2p_err,
        names=names, n_stars=n_stars, n_prior=n_prior,
        star_centered_rvs=star_centered_rvs,
        emp=emp, gauss=gauss, binary_drvs=binary_drvs, sim_info=sim_info,
        pg_fbin=pg_fbin, pg_sigma_s=pg_sigma_s, pg_sigma_b=pg_sigma_b,
        pg_emp_curve=pg_emp_curve, pg_gauss_curve=pg_gauss_curve,
        pg_chi2_emp=pg_chi2_emp, pg_chi2_gauss=pg_chi2_gauss,
        t_optimal_main=t_optimal_main,
    )

    # ==================================================================
    # TABS
    # ==================================================================
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Sample Fit", "🔍 Fraction Recovery",
        "🌐 Global Correction", "🧪 Population Sim",
    ])

    with tab1:
        render_tab_sample_fit(ctx)
    with tab2:
        render_tab_fraction_recovery(ctx)
    with tab3:
        render_tab_global_correction(ctx)
    with tab4:
        render_tab_population_sim()
