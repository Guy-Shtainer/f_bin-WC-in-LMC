"""rv_modeling/tab_simulation.py — Tab A: Binary RV Simulation + distribution fitting."""
from __future__ import annotations

import warnings as _warnings

import numpy as np
import plotly.graph_objects as go
import scipy.stats as sp_stats
import streamlit as st

from shared import PLOTLY_THEME, COLOR_BINARY

from rv_modeling.helpers import _theme_parts, _ann, resolve_nbins
from rv_modeling.compute import compute_binary_raw_rvs

# ---------------------------------------------------------------------------
# Distribution metadata (same definitions as bc.extras)
# ---------------------------------------------------------------------------
_DIST_MAP = {
    "Normal": "norm", "Log-normal": "lognorm", "Gamma": "gamma",
    "Weibull": "weibull_min", "Exponential": "expon",
    "Flat (uniform)": "uniform",
}

_PARAM_META = {
    "Normal": [("μ (loc)", 0.0, -200.0, 200.0, 0.1),
               ("σ (scale)", 20.0, 0.01, 200.0, 0.1)],
    "Log-normal": [("s (shape)", 0.5, 0.01, 5.0, 0.01),
                   ("loc", 0.0, -200.0, 200.0, 0.1),
                   ("scale", 20.0, 0.01, 200.0, 0.1)],
    "Gamma": [("a (shape)", 2.0, 0.01, 50.0, 0.01),
              ("loc", 0.0, -200.0, 200.0, 0.1),
              ("scale", 10.0, 0.01, 200.0, 0.1)],
    "Weibull": [("c (shape)", 1.5, 0.01, 10.0, 0.01),
                ("loc", 0.0, -200.0, 200.0, 0.1),
                ("scale", 20.0, 0.01, 200.0, 0.1)],
    "Exponential": [("loc", 0.0, -200.0, 200.0, 0.1),
                    ("scale", 20.0, 0.01, 200.0, 0.1)],
    "Flat (uniform)": [("loc (start)", -50.0, -500.0, 500.0, 0.1),
                       ("scale (width)", 100.0, 0.01, 1000.0, 0.1)],
}


# ---------------------------------------------------------------------------
# Distribution fitting helpers
# ---------------------------------------------------------------------------

def _fit_distribution(data: np.ndarray, dist_name: str) -> dict | None:
    """Fit a named distribution via MLE. Returns params + AIC/BIC."""
    scipy_name = _DIST_MAP.get(dist_name)
    if scipy_name is None or len(data) < 5:
        return None
    dist = getattr(sp_stats, scipy_name, None)
    if dist is None:
        return None
    try:
        with _warnings.catch_warnings():
            _warnings.simplefilter("ignore")
            params = dist.fit(data)
        k = len(params)
        n = len(data)
        log_lik = float(np.sum(dist.logpdf(data, *params)))
        if not np.isfinite(log_lik):
            return None
        aic = 2 * k - 2 * log_lik
        bic = k * np.log(n) - 2 * log_lik
        return {
            "dist_name": dist_name, "scipy_name": scipy_name,
            "params": params, "k": k, "n": n,
            "log_lik": log_lik, "aic": aic, "bic": bic,
        }
    except Exception:
        return None


def _compute_aic_bic(data: np.ndarray, scipy_name: str,
                     params: tuple) -> dict:
    """Compute AIC/BIC for given params (manual adjustment)."""
    dist = getattr(sp_stats, scipy_name)
    k = len(params)
    n = len(data)
    try:
        log_lik = float(np.sum(dist.logpdf(data, *params)))
    except Exception:
        log_lik = float("-inf")
    if not np.isfinite(log_lik):
        return {"aic": float("inf"), "bic": float("inf"), "log_lik": float("-inf")}
    aic = 2 * k - 2 * log_lik
    bic = k * np.log(n) - 2 * log_lik
    return {"aic": aic, "bic": bic, "log_lik": log_lik}


def _fit_all(data: np.ndarray) -> list[dict]:
    """Fit all distributions, sort by AIC."""
    results = []
    for name in _DIST_MAP:
        r = _fit_distribution(data, name)
        if r is not None:
            results.append(r)
    results.sort(key=lambda x: x["aic"])
    return results


# ---------------------------------------------------------------------------
# Orbital parameter UI (moved from page.py)
# ---------------------------------------------------------------------------

def _render_orbital_params() -> dict:
    """Render orbital parameter controls. Returns dict of all param values."""
    # ── Preset callbacks ──
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

    st.markdown("**Orbital simulation parameters**")

    # Row 1: core controls
    r1a, r1b, r1c, r1d = st.columns(4)
    with r1a:
        period_model = st.selectbox(
            "Period model", ["powerlaw", "langer2020"], index=0, key="rvm_period",
        )
    with r1b:
        pi_val: float = 0.0
        weight_A: float = 0.3
        if period_model == "powerlaw":
            pi_val = st.slider("π (power-law)", -3.0, 3.0, 0.0, 0.1, key="rvm_pi")
        else:
            weight_A = st.slider("Weight A", 0.0, 1.0, 0.20, 0.05, key="rvm_wA")
    with r1c:
        e_model = st.selectbox("Eccentricity", ["flat", "zero"], key="rvm_emod")
    with r1d:
        e_max: float = 0.9
        if e_model == "flat":
            e_max = st.slider("e_max", 0.1, 0.95, 0.9, 0.05, key="rvm_emax")
        else:
            e_max = 0.0
            st.markdown("*e = 0*")

    # Row 2: sim size + presets
    r2a, r2b, r2c, r2d, r2e = st.columns(5)
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
        pc1, pc2 = st.columns(2)
        with pc1:
            st.button("Dsilva", key="rvm_preset_d",
                      on_click=_preset_dsilva, use_container_width=True)
        with pc2:
            st.button("Langer", key="rvm_preset_l",
                      on_click=_preset_langer, use_container_width=True)

    # Expanders for detailed parameters
    exp1, exp2 = st.columns(2)
    with exp1:
        with st.expander("Period Distribution", expanded=False):
            logP_min = st.number_input("logP_min", 0.01, 10.0, 0.15, 0.05,
                                       key="rvm_logPmin")
            logP_max = st.number_input("logP_max", 0.1, 10.0, 5.0, 0.1,
                                       key="rvm_logPmax")
            dist_A, mu_A, sigma_A = "gaussian", 0.80, 0.35
            dist_B, mu_B, sigma_B = "reflected_lognormal", 2.0, 0.45
            if period_model == "langer2020":
                st.markdown("**Component A (short-period)**")
                _dist_opts = ["gaussian", "lognormal", "reflected_lognormal",
                              "empirical", "flat"]
                dist_A = st.selectbox("Dist A", _dist_opts, index=0, key="rvm_distA")
                la1, la2 = st.columns(2)
                with la1:
                    mu_A = st.number_input("μ_A", 0.01, 10.0, 0.80, 0.05,
                                           key="rvm_muA")
                with la2:
                    sigma_A = st.number_input("σ_A", 0.01, 5.0, 0.35, 0.05,
                                              key="rvm_sigA")
                st.markdown("**Component B (long-period)**")
                dist_B = st.selectbox("Dist B", _dist_opts, index=2, key="rvm_distB")
                lb1, lb2 = st.columns(2)
                with lb1:
                    mu_B = st.number_input("μ_B", 0.01, 10.0, 2.0, 0.05,
                                           key="rvm_muB")
                with lb2:
                    sigma_B = st.number_input("σ_B", 0.01, 5.0, 0.45, 0.05,
                                              key="rvm_sigB")

    with exp2:
        with st.expander("Mass & Mass Ratio", expanded=False):
            _q_opts = ["flat", "gaussian", "lognormal",
                       "reflected_lognormal", "empirical"]
            q_model = st.selectbox("q model", _q_opts, index=0, key="rvm_qmod")
            qq1, qq2 = st.columns(2)
            with qq1:
                q_min = st.number_input("q_min", 0.01, 50.0, 0.1, 0.05,
                                        key="rvm_q_min")
            with qq2:
                q_max = st.number_input("q_max", 0.01, 50.0, 2.0, 0.1,
                                        key="rvm_q_max")
            q_flipped = st.checkbox("q flipped (M2=M1/q)", key="rvm_q_flip")
            langer_q_mu, langer_q_sigma = 0.7, 0.2
            if q_model not in ("flat", "empirical"):
                lqm1, lqm2 = st.columns(2)
                with lqm1:
                    langer_q_mu = st.number_input("q μ", 0.01, 50.0, 0.7, 0.05,
                                                  key="rvm_lq_mu")
                with lqm2:
                    langer_q_sigma = st.number_input("q σ", 0.01, 50.0, 0.2, 0.05,
                                                     key="rvm_lq_sig")
            st.markdown("---")
            mass_model = st.selectbox("Primary mass", ["fixed", "uniform"],
                                      key="rvm_mass_model")
            mass_fixed = 10.0
            mass_min, mass_max = 10.0, 20.0
            if mass_model == "fixed":
                mass_fixed = st.number_input("M₁ (M☉)", 1.0, 200.0, 10.0, 1.0,
                                             key="rvm_mass_fixed")
            else:
                mm1, mm2 = st.columns(2)
                with mm1:
                    mass_min = st.number_input("M₁ min", 1.0, 200.0, 10.0, 1.0,
                                               key="rvm_mass_min")
                with mm2:
                    mass_max = st.number_input("M₁ max", 1.0, 200.0, 20.0, 1.0,
                                               key="rvm_mass_max")

    return dict(
        period_model=period_model, pi=pi_val, weight_A=weight_A,
        e_model=e_model, e_max=e_max, q_model=q_model,
        n_sim=int(n_sim), n_epochs=int(n_epochs), time_span=float(time_span),
        seed=int(seed), logP_min=float(logP_min), logP_max=float(logP_max),
        q_min=float(q_min), q_max=float(q_max), q_flipped=bool(q_flipped),
        langer_q_mu=float(langer_q_mu), langer_q_sigma=float(langer_q_sigma),
        mass_model=mass_model, mass_fixed=float(mass_fixed),
        mass_min=float(mass_min), mass_max=float(mass_max),
        dist_A=dist_A, mu_A=float(mu_A), sigma_A=float(sigma_A),
        dist_B=dist_B, mu_B=float(mu_B), sigma_B=float(sigma_B),
    )


# ---------------------------------------------------------------------------
# Distribution fitting UI
# ---------------------------------------------------------------------------

def _render_dist_fitting(data: np.ndarray, obs_data: dict, prefix: str = "rvm_df") -> None:
    """Render distribution fitting UI for the given data array."""
    _ax, _ay, _al = _theme_parts()

    st.subheader("Distribution Fitting")

    dist_names = list(_DIST_MAP.keys())
    dist_name = st.selectbox("Distribution", dist_names, key=f"{prefix}_dist")
    scipy_name = _DIST_MAP[dist_name]

    # ── Buttons ──
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        auto_fit = st.button("Auto-fit (MLE)", key=f"{prefix}_autofit",
                             use_container_width=True)
    with btn_col2:
        record_btn = st.button("Record fit", key=f"{prefix}_record",
                               use_container_width=True)

    # ── Auto-fit ──
    if auto_fit:
        result = _fit_distribution(data, dist_name)
        if result is not None:
            for i, val in enumerate(result["params"]):
                st.session_state[f"{prefix}_p_{i}"] = float(val)
            st.session_state[f"{prefix}_last_fit"] = result
            # Store best fit for Tab B to use
            st.session_state["rvm_best_binary_dist"] = dist_name
            st.session_state["rvm_best_binary_params"] = tuple(result["params"])
            st.toast(f"Auto-fit: {dist_name} (AIC={result['aic']:.1f})")
        else:
            st.warning(f"Auto-fit failed for {dist_name}.")

    # ── Parameter inputs ──
    pmeta = _PARAM_META.get(dist_name, [])
    current_params = []
    if pmeta:
        pcols = st.columns(len(pmeta))
        for i, (label, default, pmin, pmax, step) in enumerate(pmeta):
            with pcols[i]:
                val = st.number_input(
                    label, min_value=pmin, max_value=pmax,
                    value=float(st.session_state.get(f"{prefix}_p_{i}", default)),
                    step=step, format="%.4f", key=f"{prefix}_p_{i}",
                )
            current_params.append(val)

    params_tuple = tuple(current_params)

    # ── Record fit to history ──
    if record_btn and len(current_params) > 0:
        stats = _compute_aic_bic(data, scipy_name, params_tuple)
        hist = st.session_state.get(f"{prefix}_history", [])
        hist.append({"dist": dist_name, "params": params_tuple, **stats})
        st.session_state[f"{prefix}_history"] = hist
        # Also store as best fit
        st.session_state["rvm_best_binary_dist"] = dist_name
        st.session_state["rvm_best_binary_params"] = params_tuple
        st.toast("Fit recorded.")

    # ── Histogram + PDF overlay ──
    _nb = resolve_nbins(data, obs_data)
    _hist_kw = dict(nbinsx=_nb) if _nb is not None else {}
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=data, **_hist_kw, histnorm="probability density",
        marker_color=COLOR_BINARY, opacity=0.6,
        name="Simulated binary RVs",
    ))

    if len(current_params) > 0:
        x_lo = max(float(data.min()) - 10, -500)
        x_hi = min(float(data.max()) + 10, 500)
        x_range = np.linspace(x_lo, x_hi, 500)
        dist_obj = getattr(sp_stats, scipy_name)
        try:
            pdf = dist_obj.pdf(x_range, *params_tuple)
            mask = np.isfinite(pdf)
            fig.add_trace(go.Scatter(
                x=x_range[mask], y=pdf[mask], mode="lines",
                line=dict(color="#E25A53", width=2.5),
                name=f"{dist_name} PDF",
            ))
        except Exception:
            pass

    fig.update_layout(**{
        **PLOTLY_THEME,
        "title": dict(text="Binary RV Distribution + Fitted PDF"),
        "xaxis": {**_ax, "title": "Centred RV (km/s)"},
        "yaxis": {**_ay, "title": "Probability density"},
        "barmode": "overlay",
        "height": 500,
    })
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        f"Histogram of {len(data):,} centred binary RVs. "
        f"Red line = {dist_name} PDF with current parameters."
    )

    # ── Statistics ──
    if len(current_params) > 0:
        stats = _compute_aic_bic(data, scipy_name, params_tuple)
        s1, s2, s3, s4, s5 = st.columns(5)
        s1.metric("AIC", f"{stats['aic']:.1f}")
        s2.metric("BIC", f"{stats['bic']:.1f}")
        s3.metric("log L", f"{stats['log_lik']:.1f}")
        s4.metric("Data mean", f"{np.mean(data):.2f}")
        s5.metric("Data std", f"{np.std(data):.2f}")

    # ── Fit history ──
    hist = st.session_state.get(f"{prefix}_history", [])
    if hist:
        with st.expander(f"Fit History ({len(hist)} entries)"):
            import pandas as pd
            df = pd.DataFrame(hist)
            st.dataframe(df, use_container_width=True)
            if st.button("Clear history", key=f"{prefix}_clear_hist"):
                st.session_state[f"{prefix}_history"] = []
                st.rerun()

    # ── Auto-fit all distributions ──
    st.markdown("---")
    if st.button("Run Auto-Fit All Distributions", key=f"{prefix}_fitall",
                 use_container_width=True):
        all_fits = _fit_all(data)
        if all_fits:
            st.session_state[f"{prefix}_all_fits"] = all_fits
            best = all_fits[0]
            st.success(f"Best: **{best['dist_name']}** (AIC={best['aic']:.1f})")
            # Store best fit for Tab B
            st.session_state["rvm_best_binary_dist"] = best["dist_name"]
            st.session_state["rvm_best_binary_params"] = tuple(best["params"])
        else:
            st.warning("All distribution fits failed.")

    all_fits = st.session_state.get(f"{prefix}_all_fits")
    if all_fits:
        import pandas as pd
        rows = [{"Distribution": r["dist_name"],
                 "AIC": f"{r['aic']:.1f}",
                 "BIC": f"{r['bic']:.1f}",
                 "log L": f"{r['log_lik']:.1f}",
                 "Params": str(tuple(round(p, 4) for p in r["params"]))}
                for r in all_fits]
        st.dataframe(pd.DataFrame(rows), use_container_width=True)

        # Best-fit overlay
        best = all_fits[0]
        _nb2 = resolve_nbins(data, obs_data)
        _hist_kw2 = dict(nbinsx=_nb2) if _nb2 is not None else {}
        fig_best = go.Figure()
        fig_best.add_trace(go.Histogram(
            x=data, **_hist_kw2, histnorm="probability density",
            marker_color=COLOR_BINARY, opacity=0.5,
            name="Data",
        ))
        x_lo = max(float(data.min()) - 10, -500)
        x_hi = min(float(data.max()) + 10, 500)
        x_range = np.linspace(x_lo, x_hi, 500)
        dist_obj = getattr(sp_stats, _DIST_MAP[best["dist_name"]])
        try:
            pdf = dist_obj.pdf(x_range, *best["params"])
            mask = np.isfinite(pdf)
            fig_best.add_trace(go.Scatter(
                x=x_range[mask], y=pdf[mask], mode="lines",
                line=dict(color="#E25A53", width=2.5),
                name=f"Best: {best['dist_name']}",
            ))
        except Exception:
            pass
        fig_best.update_layout(**{
            **PLOTLY_THEME,
            "title": dict(text=f"Best Fit: {best['dist_name']}"),
            "xaxis": {**_ax, "title": "Centred RV (km/s)"},
            "yaxis": {**_ay, "title": "Probability density"},
            "height": 400,
        })
        st.plotly_chart(fig_best, use_container_width=True)

        # Q-Q plot
        st.markdown("**Q-Q Plot (best fit)**")
        sorted_data = np.sort(data)
        n = len(sorted_data)
        theoretical_q = dist_obj.ppf(
            np.linspace(0.01, 0.99, n), *best["params"]
        )
        fig_qq = go.Figure()
        fig_qq.add_trace(go.Scatter(
            x=theoretical_q, y=sorted_data, mode="markers",
            marker=dict(size=2, color=COLOR_BINARY, opacity=0.5),
            name="Q-Q",
        ))
        qq_min = min(float(theoretical_q.min()), float(sorted_data.min()))
        qq_max = max(float(theoretical_q.max()), float(sorted_data.max()))
        fig_qq.add_trace(go.Scatter(
            x=[qq_min, qq_max], y=[qq_min, qq_max],
            mode="lines", line=dict(color="grey", dash="dash", width=1),
            name="y=x",
        ))
        fig_qq.update_layout(**{
            **PLOTLY_THEME,
            "title": dict(text=f"Q-Q: {best['dist_name']}"),
            "xaxis": {**_ax, "title": "Theoretical quantiles"},
            "yaxis": {**_ay, "title": "Sample quantiles"},
            "height": 400,
        })
        st.plotly_chart(fig_qq, use_container_width=True)


# ---------------------------------------------------------------------------
# Main tab renderer
# ---------------------------------------------------------------------------

def render_tab_simulation(obs_data: dict) -> None:
    """Tab A: Binary RV Simulation — orbital sim + distribution fitting."""
    st.subheader("Binary RV Simulation")
    st.caption(
        "Simulate binary star systems with chosen orbital parameters, then "
        "fit statistical distributions to the resulting RV histogram."
    )

    # ── Orbital parameter UI ──
    params = _render_orbital_params()

    # ── Recompute button ──
    recompute = st.button("Simulate Binary RVs", type="primary",
                          use_container_width=True, key="rvm_sim_btn")
    st.caption("Generates centred per-epoch RVs for a pure-binary population.")

    should_run = recompute or "rvm_raw_rvs" not in st.session_state

    if should_run:
        with st.spinner("Simulating binary RVs..."):
            raw_rvs = compute_binary_raw_rvs(
                n_sim=params["n_sim"], n_epochs=params["n_epochs"],
                time_span=params["time_span"],
                period_model=params["period_model"], pi=params["pi"],
                e_model=params["e_model"], e_max=params["e_max"],
                q_model=params["q_model"], seed=params["seed"],
                weight_A=params["weight_A"],
                logP_min=params["logP_min"], logP_max=params["logP_max"],
                q_min=params["q_min"], q_max=params["q_max"],
                q_flipped=params["q_flipped"],
                langer_q_mu=params["langer_q_mu"],
                langer_q_sigma=params["langer_q_sigma"],
                mass_primary_model=params["mass_model"],
                mass_primary_fixed=params["mass_fixed"],
                mass_primary_min=params["mass_min"],
                mass_primary_max=params["mass_max"],
                dist_A=params["dist_A"], mu_A=params["mu_A"],
                sigma_A=params["sigma_A"],
                dist_B=params["dist_B"], mu_B=params["mu_B"],
                sigma_B=params["sigma_B"],
            )
            st.session_state["rvm_raw_rvs"] = raw_rvs
            st.session_state["rvm_sim_params"] = params

    # ── Show results ──
    raw_rvs = st.session_state.get("rvm_raw_rvs")
    if raw_rvs is None or len(raw_rvs) == 0:
        st.info("Click **Simulate Binary RVs** to generate data.")
        return

    st.success(f"Generated {len(raw_rvs):,} centred RV values "
               f"(median={np.median(raw_rvs):.1f}, std={np.std(raw_rvs):.1f} km/s).")

    st.markdown("---")
    _render_dist_fitting(raw_rvs, obs_data, prefix="rvm_df")
