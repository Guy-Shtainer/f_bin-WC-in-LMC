"""Statistical RV Modeling — two-component mixture model.

Fits f_bin and σ_single to the observed binary fraction vs ΔRV threshold
curve.  The binary component uses an empirical ΔRV distribution from
Monte-Carlo orbital simulations (Dsilva / Langer models) instead of the
Gaussian assumption used in the original notebook analysis.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import numpy as np
import streamlit as st
import plotly.graph_objects as go
from scipy.optimize import curve_fit
from scipy.interpolate import interp1d

from shared import (
    inject_theme,
    render_sidebar,
    get_settings_manager,
    cached_load_observed_delta_rvs,
    settings_hash,
    PLOTLY_THEME,
    COLOR_BINARY,
    COLOR_SINGLE,
)

# ── Page configuration ───────────────────────────────────────────────────
st.set_page_config(
    page_title="RV Modeling — WR Binary",
    page_icon="📈",
    layout="wide",
)
inject_theme()
_settings = render_sidebar("RV Modeling")

# ── Constants ────────────────────────────────────────────────────────────
_NSIGMA_DETECT: float = 4.0
_N_PRIOR_BINARIES: int = 3
_T_MAX: int = 301          # exclusive upper bound for threshold grid


# =====================================================================
#  Cached helper functions
# =====================================================================

@st.cache_data(show_spinner="Simulating single-star Gaussian ranges …")
def compute_standard_ranges(
    n_epochs: int, n_sim: int = 500_000, seed: int = 12345,
) -> np.ndarray:
    """Return *sorted* ranges of n_epochs standard-normal draws (σ = 1).

    The survival function for any σ_s is obtained by querying at t / σ_s.
    Using empirical simulation (500 K samples) instead of the analytical
    double integral — orders of magnitude faster, same accuracy.
    """
    rng = np.random.default_rng(seed)
    samples = rng.standard_normal((n_sim, n_epochs))
    ranges = np.ptp(samples, axis=1)
    ranges.sort()
    return ranges


@st.cache_data(show_spinner="Simulating binary ΔRV distribution …")
def compute_binary_delta_rvs(
    n_sim: int,
    n_epochs: int,
    time_span: float,
    period_model: str,
    pi: float,
    e_model: str,
    e_max: float,
    q_model: str,
    seed: int,
    weight_A: float,
) -> np.ndarray:
    """Generate pure-binary ΔRVs using the orbital simulation engine."""
    from wr_bias_simulation import (
        simulate_delta_rv_sample,
        SimulationConfig,
        BinaryParameterConfig,
    )

    rng = np.random.default_rng(seed)
    sim_cfg = SimulationConfig(
        n_stars=n_sim,
        n_epochs=n_epochs,
        time_span=time_span,
        sigma_single=0.0,
        sigma_measure=0.0,
    )
    langer_params: dict = {}
    if period_model == "langer2020":
        langer_params = {"weight_A": float(weight_A)}

    bin_cfg = BinaryParameterConfig(
        period_model=period_model,
        e_model=e_model,
        e_max=e_max,
        q_model=q_model,
        langer_period_params=langer_params,
    )
    return simulate_delta_rv_sample(
        f_bin=1.0, pi=pi, sim_cfg=sim_cfg, bin_cfg=bin_cfg, rng=rng,
    )


def _empirical_survival(sorted_vals: np.ndarray, t_arr: np.ndarray) -> np.ndarray:
    """S(t) = P(X > t) from a pre-sorted empirical sample."""
    idx = np.searchsorted(sorted_vals, t_arr, side="right")
    return 1.0 - idx / len(sorted_vals)


# =====================================================================
#  Page logic
# =====================================================================

def _run_page() -> None:  # noqa: C901 (page-level function, intentionally long)
    st.title("Statistical RV Modeling")
    st.caption(
        "Two-component mixture model: fits **f_bin** and **σ_single** to the "
        "observed binary fraction vs ΔRV threshold curve. The binary ΔRV "
        "distribution comes from Monte-Carlo orbital simulations rather than "
        "a Gaussian assumption."
    )

    # ── load observed data ───────────────────────────────────────────────
    sm = get_settings_manager()
    current_settings = sm.load()
    s_hash = settings_hash(current_settings)
    obs_drv, detail = cached_load_observed_delta_rvs(s_hash)

    names = sorted(detail.keys())
    n_stars = len(names)
    p2p = np.array([detail[n]["best_dRV"] for n in names])
    p2p_err = np.array([detail[n]["best_sigma"] for n in names])

    # Observed binary fraction at each threshold
    t_full = np.arange(0, _T_MAX, dtype=float)
    is_sig = (p2p - _NSIGMA_DETECT * p2p_err) > 0.0
    f_obs = np.array(
        [np.sum(is_sig & (p2p > t)) / n_stars for t in t_full]
    )
    raw_frac = np.array([np.sum(p2p > t) / n_stars for t in t_full])
    sig_err = np.sqrt(f_obs * (1.0 - f_obs) / n_stars) + 1e-4

    # ── sidebar controls ─────────────────────────────────────────────────
    with st.sidebar:
        st.subheader("Simulation Parameters")

        period_model = st.selectbox(
            "Period model", ["powerlaw", "langer2020"],
            index=0, key="rvm_period",
        )
        pi_val: float = 0.0
        weight_A: float = 0.3
        if period_model == "powerlaw":
            pi_val = st.slider(
                "π (period power-law index)", -3.0, 3.0, 0.0, 0.1,
                key="rvm_pi",
            )
        else:
            weight_A = st.slider(
                "Weight A (Case A fraction)", 0.0, 1.0, 0.3, 0.05,
                key="rvm_wA",
            )

        n_sim = st.select_slider(
            "N_sim (binary systems)",
            options=[10_000, 50_000, 100_000, 200_000, 500_000],
            value=100_000,
            key="rvm_nsim",
        )
        n_epochs = st.number_input(
            "Number of epochs", 2, 20, 6, key="rvm_nep",
        )
        time_span = st.number_input(
            "Time span (days)", 100.0, 10_000.0, 3650.0,
            step=100.0, key="rvm_ts",
        )

        with st.expander("Advanced orbital parameters"):
            e_model = st.selectbox(
                "Eccentricity model", ["flat", "zero"], key="rvm_emod",
            )
            e_max: float = 0.9
            if e_model == "flat":
                e_max = st.slider(
                    "e_max", 0.1, 0.95, 0.9, 0.05, key="rvm_emax",
                )
            q_model = st.selectbox(
                "Mass-ratio model", ["flat", "langer"], key="rvm_qmod",
            )
            seed = st.number_input(
                "Random seed", 0, 99999, 42, key="rvm_seed",
            )

        run_btn = st.button(
            "🔬 Run Fit", type="primary", use_container_width=True,
        )

    # ── preview (before run) ─────────────────────────────────────────────
    if not run_btn and "rvm_results" not in st.session_state:
        st.info(
            "Configure simulation parameters in the sidebar and click "
            "**Run Fit**."
        )
        fig_prev = go.Figure()
        fig_prev.add_trace(go.Scatter(
            x=t_full, y=f_obs, mode="markers",
            marker=dict(size=3, color=COLOR_SINGLE),
            name="Observed (significance-filtered)",
        ))
        fig_prev.add_trace(go.Scatter(
            x=t_full, y=raw_frac, mode="markers",
            marker=dict(size=3, color="grey", opacity=0.5),
            name="Observed (raw)",
        ))
        fig_prev.update_layout(**{
            **PLOTLY_THEME,
            "title": dict(text="Observed Binary Fraction vs ΔRV Threshold"),
            "xaxis": {
                **PLOTLY_THEME.get("xaxis", {}),
                "title": "ΔRV threshold (km/s)",
            },
            "yaxis": {
                **PLOTLY_THEME.get("yaxis", {}),
                "title": "Binary fraction",
            },
        })
        st.plotly_chart(fig_prev, use_container_width=True)
        st.caption(
            "Observed binary fraction at each ΔRV threshold. "
            "Blue: significance-filtered (ΔRV − 4σ > 0). "
            "Grey: raw (no significance cut)."
        )
        return

    # ── run simulation & fitting ─────────────────────────────────────────
    if run_btn:
        # -- binary distribution -------------------------------------------
        binary_drvs = compute_binary_delta_rvs(
            n_sim=int(n_sim),
            n_epochs=int(n_epochs),
            time_span=float(time_span),
            period_model=period_model,
            pi=float(pi_val),
            e_model=e_model,
            e_max=float(e_max),
            q_model=q_model,
            seed=int(seed),
            weight_A=float(weight_A),
        )
        sorted_binary = np.sort(binary_drvs)

        # -- single-star standard ranges -----------------------------------
        sorted_std_ranges = compute_standard_ranges(int(n_epochs))

        # -- smooth interpolated survival functions -------------------------
        # Binary: evaluate on a fine grid then interpolate
        t_max_b = max(500.0, float(np.max(binary_drvs)) * 1.1)
        t_interp_b = np.linspace(0, t_max_b, 3000)
        surv_b_raw = _empirical_survival(sorted_binary, t_interp_b)
        binary_surv_fn = interp1d(
            t_interp_b, surv_b_raw, kind="linear",
            bounds_error=False, fill_value=(1.0, 0.0),
        )

        # Single (standardised, sigma=1): evaluate on [0, 15]
        t_interp_s = np.linspace(0, 15, 3000)
        surv_s_raw = _empirical_survival(sorted_std_ranges, t_interp_s)
        std_surv_fn = interp1d(
            t_interp_s, surv_s_raw, kind="linear",
            bounds_error=False, fill_value=(1.0, 0.0),
        )

        # -- mixture model -------------------------------------------------
        def _model(t: np.ndarray, f_bin: float, sigma_s: float) -> np.ndarray:
            s_single = std_surv_fn(t / sigma_s)
            s_binary = binary_surv_fn(t)
            return (1.0 - f_bin) * s_single + f_bin * s_binary

        fit_ok = False
        try:
            # Stage 1: raw (no significance cut) for stable initial guesses
            popt_raw, _ = curve_fit(
                _model, t_full, raw_frac,
                p0=[0.4, 10.0],
                bounds=([0.0, 0.1], [1.0, 100.0]),
            )
            # Stage 2: significance-filtered, weighted by binomial error
            popt, pcov = curve_fit(
                _model, t_full, f_obs,
                p0=popt_raw,
                bounds=([0.0, 0.1], [1.0, 100.0]),
                sigma=sig_err,
                absolute_sigma=True,
            )
            perr = np.sqrt(np.diag(pcov))
            f_fit, sigma_s_fit = float(popt[0]), float(popt[1])
            f_err, sigma_s_err = float(perr[0]), float(perr[1])

            fitted_vals = _model(t_full, *popt)
            residuals_arr = (f_obs - fitted_vals) / sig_err
            chi2 = float(np.sum(residuals_arr ** 2))
            ndof = len(t_full) - 2
            chi2_red = chi2 / ndof

            # Survival curves at best-fit
            surv_s_best = std_surv_fn(t_full / sigma_s_fit)
            surv_b_best = binary_surv_fn(t_full)

            # Weighted PDF components
            dt = np.diff(t_full)
            pdf_s = np.maximum(0.0, -np.diff(surv_s_best) / dt)
            pdf_b = np.maximum(0.0, -np.diff(surv_b_best) / dt)
            mid_t = t_full[:-1] + 0.5
            w_pdf_s = (1.0 - f_fit) * pdf_s
            w_pdf_b = f_fit * pdf_b

            # Optimal threshold (PDF crossover)
            cross_mask = w_pdf_b > w_pdf_s
            t_optimal = (
                float(mid_t[np.argmax(cross_mask)])
                if np.any(cross_mask)
                else None
            )

            # Bartzakos prior correction
            n_global = n_stars + _N_PRIOR_BINARIES
            f_global = (f_fit * n_stars + _N_PRIOR_BINARIES) / n_global
            f_global_err = f_err * n_stars / n_global

            st.session_state["rvm_results"] = dict(
                f_fit=f_fit, f_err=f_err,
                sigma_s_fit=sigma_s_fit, sigma_s_err=sigma_s_err,
                chi2_red=chi2_red, ndof=ndof,
                f_global=f_global, f_global_err=f_global_err,
                n_global=n_global,
                fitted_vals=fitted_vals,
                residuals=residuals_arr,
                single_comp=(1.0 - f_fit) * surv_s_best,
                binary_comp=f_fit * surv_b_best,
                w_pdf_s=w_pdf_s, w_pdf_b=w_pdf_b,
                mid_t=mid_t,
                t_optimal=t_optimal,
                binary_drvs=binary_drvs,
                sim_info=dict(
                    period_model=period_model, pi=pi_val,
                    weight_A=weight_A, n_sim=int(n_sim),
                    n_epochs=int(n_epochs), time_span=time_span,
                    e_model=e_model, e_max=e_max,
                    q_model=q_model, seed=int(seed),
                ),
            )
            fit_ok = True
        except Exception as exc:
            st.error(f"Fitting failed: {exc}")

        if not fit_ok:
            return

    # ── render cached results ────────────────────────────────────────────
    res = st.session_state.get("rvm_results")
    if res is None:
        return

    f_fit = res["f_fit"]
    f_err = res["f_err"]
    sigma_s_fit = res["sigma_s_fit"]
    sigma_s_err = res["sigma_s_err"]
    chi2_red = res["chi2_red"]
    ndof = res["ndof"]
    f_global = res["f_global"]
    f_global_err = res["f_global_err"]
    n_global = res["n_global"]
    fitted_vals = res["fitted_vals"]
    residuals_arr = res["residuals"]
    single_comp = res["single_comp"]
    binary_comp = res["binary_comp"]
    w_pdf_s = res["w_pdf_s"]
    w_pdf_b = res["w_pdf_b"]
    mid_t = res["mid_t"]
    t_optimal = res["t_optimal"]
    sim_info = res["sim_info"]
    binary_drvs = res["binary_drvs"]

    # ── Panel 1: fitted curve + observed points ──────────────────────────
    st.subheader("1 · Fitted Binary Fraction vs ΔRV Threshold")

    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(
        x=t_full, y=f_obs, mode="markers",
        marker=dict(size=4, color=COLOR_SINGLE),
        name="Observed (sig-filtered)",
        error_y=dict(
            type="data", array=sig_err, visible=True,
            thickness=1, width=0,
        ),
    ))
    fig1.add_trace(go.Scatter(
        x=t_full, y=raw_frac, mode="markers",
        marker=dict(size=3, color="grey", opacity=0.4),
        name="Observed (raw)",
    ))
    fig1.add_trace(go.Scatter(
        x=t_full, y=fitted_vals, mode="lines",
        line=dict(color="#E25A53", width=2.5),
        name=f"Model (f_bin = {f_fit:.3f})",
    ))
    fig1.add_trace(go.Scatter(
        x=t_full, y=single_comp, mode="lines",
        line=dict(color=COLOR_SINGLE, width=1.5, dash="dash"),
        name=f"Singles (σ = {sigma_s_fit:.1f} km/s)",
    ))
    fig1.add_trace(go.Scatter(
        x=t_full, y=binary_comp, mode="lines",
        line=dict(color=COLOR_BINARY, width=1.5, dash="dash"),
        name="Binaries (empirical)",
    ))
    if t_optimal is not None:
        fig1.add_vline(
            x=t_optimal,
            line=dict(color="#DAA520", width=2, dash="dot"),
            annotation_text=f"t_opt = {t_optimal:.0f} km/s",
            annotation_position="top right",
        )

    fig1.update_layout(**{
        **PLOTLY_THEME,
        "title": dict(text="Binary Fraction vs ΔRV Threshold — Mixture Model Fit"),
        "xaxis": {
            **PLOTLY_THEME.get("xaxis", {}),
            "title": "ΔRV threshold (km/s)",
        },
        "yaxis": {
            **PLOTLY_THEME.get("yaxis", {}),
            "title": "Binary fraction",
        },
        "legend": {
            **PLOTLY_THEME.get("legend", {}),
            "x": 0.98, "y": 0.98, "xanchor": "right",
        },
    })
    st.plotly_chart(fig1, use_container_width=True)
    st.caption(
        "Fitted two-component mixture model. Solid red: total model curve. "
        "Dashed blue: single-star contribution (Gaussian range). "
        "Dashed red: binary contribution (empirical from simulation). "
        "Gold line: optimal classification threshold (PDF crossover)."
    )

    # ── Panel 2: weighted PDFs ───────────────────────────────────────────
    st.subheader("2 · Weighted PDF Components")

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=mid_t, y=w_pdf_s, mode="lines",
        line=dict(color=COLOR_SINGLE, width=2),
        name="(1−f) · PDF_singles",
        fill="tozeroy", fillcolor="rgba(74,144,217,0.2)",
    ))
    fig2.add_trace(go.Scatter(
        x=mid_t, y=w_pdf_b, mode="lines",
        line=dict(color=COLOR_BINARY, width=2),
        name="f · PDF_binaries",
        fill="tozeroy", fillcolor="rgba(226,90,83,0.2)",
    ))
    if t_optimal is not None:
        fig2.add_vline(
            x=t_optimal,
            line=dict(color="#DAA520", width=2, dash="dot"),
            annotation_text=f"Optimal: {t_optimal:.0f} km/s",
        )

    fig2.update_layout(**{
        **PLOTLY_THEME,
        "title": dict(text="Weighted PDF Components (ΔRV Range Distribution)"),
        "xaxis": {
            **PLOTLY_THEME.get("xaxis", {}),
            "title": "ΔRV (km/s)",
        },
        "yaxis": {
            **PLOTLY_THEME.get("yaxis", {}),
            "title": "Weighted PDF",
        },
        "legend": {
            **PLOTLY_THEME.get("legend", {}),
            "x": 0.98, "y": 0.98, "xanchor": "right",
        },
    })
    st.plotly_chart(fig2, use_container_width=True)
    st.caption(
        "Weighted probability densities of the single-star (blue, Gaussian "
        "range) and binary (red, empirical) ΔRV distributions. The optimal "
        "threshold (gold) is where the binary PDF first exceeds the singles "
        "PDF — the Bayes-optimal decision boundary."
    )

    # ── Panel 3: residuals ───────────────────────────────────────────────
    st.subheader("3 · Fit Residuals")

    fig3 = go.Figure()
    fig3.add_trace(go.Scatter(
        x=t_full, y=residuals_arr, mode="markers",
        marker=dict(size=3, color=COLOR_SINGLE),
        name="Residuals",
    ))
    fig3.add_hline(y=0, line=dict(color="grey", width=1, dash="dash"))
    fig3.add_hline(y=2, line=dict(color="grey", width=0.5, dash="dot"))
    fig3.add_hline(y=-2, line=dict(color="grey", width=0.5, dash="dot"))

    fig3.update_layout(**{
        **PLOTLY_THEME,
        "title": dict(
            text=f"Normalized Residuals (χ²_red = {chi2_red:.2f})",
        ),
        "xaxis": {
            **PLOTLY_THEME.get("xaxis", {}),
            "title": "ΔRV threshold (km/s)",
        },
        "yaxis": {
            **PLOTLY_THEME.get("yaxis", {}),
            "title": "(Obs − Model) / σ",
        },
    })
    st.plotly_chart(fig3, use_container_width=True)
    st.caption(
        f"Normalized residuals of the fit. Grey dashed lines: ±2σ bands. "
        f"χ²_red = {chi2_red:.2f} ({ndof} d.o.f.)."
    )

    # ── Panel 4: best-fit parameters table ───────────────────────────────
    st.subheader("4 · Best-Fit Parameters")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("##### Sample Fit ({} stars)".format(n_stars))
        st.table({
            "Parameter": [
                "f_bin", "σ_single (km/s)", "χ²_red", "N_dof",
            ],
            "Value": [
                f"{f_fit:.4f}",
                f"{sigma_s_fit:.2f}",
                f"{chi2_red:.3f}",
                f"{ndof}",
            ],
            "Error": [
                f"± {f_err:.4f}",
                f"± {sigma_s_err:.2f}",
                "—",
                "—",
            ],
        })

    with col_b:
        st.markdown("##### With Bartzakos Prior (+3 known binaries)")
        n_det = int(round(f_fit * n_stars))
        st.table({
            "Parameter": [
                "f_bin (global)",
                "N_total",
                "N_detected (sample)",
                "N_prior",
            ],
            "Value": [
                f"{f_global:.4f}",
                f"{n_global}",
                f"{n_det}",
                f"{_N_PRIOR_BINARIES}",
            ],
            "Error": [
                f"± {f_global_err:.4f}",
                "—",
                "—",
                "—",
            ],
        })

    if t_optimal is not None:
        st.info(
            f"📌 **Optimal ΔRV threshold** (PDF crossover): "
            f"**{t_optimal:.0f} km/s**  —  this is the Bayes-optimal "
            f"boundary between the single-star and binary populations."
        )

    # ── simulation details expander ──────────────────────────────────────
    with st.expander("Simulation Details"):
        pm = sim_info["period_model"]
        pm_detail = (
            f'π = {sim_info["pi"]:.1f}'
            if pm == "powerlaw"
            else f'w_A = {sim_info["weight_A"]:.2f}'
        )
        st.markdown(
            f"- **Period model:** {pm} ({pm_detail})\n"
            f"- **N_sim:** {sim_info['n_sim']:,} binary systems\n"
            f"- **n_epochs:** {sim_info['n_epochs']}\n"
            f"- **Time span:** {sim_info['time_span']:.0f} days\n"
            f"- **Eccentricity:** {sim_info['e_model']} "
            f"(e_max = {sim_info['e_max']:.2f})\n"
            f"- **Mass ratio:** {sim_info['q_model']}\n"
            f"- **Seed:** {sim_info['seed']}\n"
            f"- **Median simulated binary ΔRV:** "
            f"{np.median(binary_drvs):.1f} km/s\n"
            f"- **Mean simulated binary ΔRV:** "
            f"{np.mean(binary_drvs):.1f} km/s\n"
            f"- **95th percentile:** "
            f"{np.percentile(binary_drvs, 95):.1f} km/s"
        )


# ── entry point ──────────────────────────────────────────────────────────
_run_page()
