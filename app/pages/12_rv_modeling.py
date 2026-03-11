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
from plotly.subplots import make_subplots
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
    """Return *sorted* ranges of n_epochs standard-normal draws (σ = 1)."""
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

def _run_page() -> None:  # noqa: C901
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

    # ── Change-point filter (only thresholds where fraction changes) ─────
    diffs = np.diff(f_obs, prepend=-999.0)
    change_mask = diffs != 0.0
    t_dots = t_full[change_mask]
    f_dots = f_obs[change_mask]
    e_dots = sig_err[change_mask]

    # ── sidebar controls ─────────────────────────────────────────────────
    with st.sidebar:
        st.subheader("Simulation Parameters")

        period_model = st.selectbox(
            "Period model", ["powerlaw", "langer2020"],
            index=0, key="rvm_period",
            help="Dsilva: power-law logP. Langer: two-component mixture (Case A+B).",
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
                help="Dsilva uses flat; Langer uses zero (post-RLOF circular).",
            )
            e_max: float = 0.9
            if e_model == "flat":
                e_max = st.slider(
                    "e_max", 0.1, 0.95, 0.9, 0.05, key="rvm_emax",
                )
            q_model = st.selectbox(
                "Mass-ratio model", ["flat", "langer"], key="rvm_qmod",
                help="Dsilva uses flat; Langer uses peaked q distribution.",
            )
            seed = st.number_input(
                "Random seed", 0, 99999, 42, key="rvm_seed",
            )

        st.markdown("---")
        st.markdown(
            "**Approach presets:**"
        )
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            if st.button("Dsilva preset", key="rvm_preset_dsilva", use_container_width=True):
                st.session_state["rvm_period"] = "powerlaw"
                st.session_state["rvm_emod"] = "flat"
                st.session_state["rvm_qmod"] = "flat"
                st.rerun()
        with col_p2:
            if st.button("Langer preset", key="rvm_preset_langer", use_container_width=True):
                st.session_state["rvm_period"] = "langer2020"
                st.session_state["rvm_emod"] = "zero"
                st.session_state["rvm_qmod"] = "langer"
                st.rerun()

        st.markdown("---")
        run_btn = st.button(
            "🔬 Run Fit", type="primary", use_container_width=True,
        )

    # ── run simulation & fitting ─────────────────────────────────────────
    should_run = run_btn or "rvm_results" not in st.session_state
    if should_run:
      with st.spinner("Running simulation and fitting model..."):
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
        t_max_b = max(500.0, float(np.max(binary_drvs)) * 1.1)
        t_interp_b = np.linspace(0, t_max_b, 3000)
        surv_b_raw = _empirical_survival(sorted_binary, t_interp_b)
        binary_surv_fn = interp1d(
            t_interp_b, surv_b_raw, kind="linear",
            bounds_error=False, fill_value=(1.0, 0.0),
        )

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

            fitted_vals_full = _model(t_full, *popt)
            fitted_vals_dots = _model(t_dots, *popt)
            residuals_dots = (f_dots - fitted_vals_dots) / e_dots
            chi2 = float(np.sum(residuals_dots ** 2))
            ndof = max(1, len(t_dots) - 2)
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

            # Store survival functions in session_state so playground can use them
            # (we can't pickle interp1d, so store the arrays)
            st.session_state["rvm_results"] = dict(
                f_fit=f_fit, f_err=f_err,
                sigma_s_fit=sigma_s_fit, sigma_s_err=sigma_s_err,
                chi2_red=chi2_red, ndof=ndof,
                f_global=f_global, f_global_err=f_global_err,
                n_global=n_global,
                fitted_vals_full=fitted_vals_full,
                fitted_vals_dots=fitted_vals_dots,
                residuals_dots=residuals_dots,
                single_comp=(1.0 - f_fit) * surv_s_best,
                binary_comp=f_fit * surv_b_best,
                w_pdf_s=w_pdf_s, w_pdf_b=w_pdf_b,
                mid_t=mid_t,
                t_optimal=t_optimal,
                binary_drvs=binary_drvs,
                # Survival function data for playground
                surv_interp_s_x=t_interp_s,
                surv_interp_s_y=surv_s_raw,
                surv_interp_b_x=t_interp_b,
                surv_interp_b_y=surv_b_raw,
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
    fitted_vals_full = res["fitted_vals_full"]
    fitted_vals_dots = res["fitted_vals_dots"]
    residuals_dots = res["residuals_dots"]
    single_comp = res["single_comp"]
    binary_comp = res["binary_comp"]
    w_pdf_s = res["w_pdf_s"]
    w_pdf_b = res["w_pdf_b"]
    mid_t = res["mid_t"]
    t_optimal = res["t_optimal"]
    sim_info = res["sim_info"]
    binary_drvs = res["binary_drvs"]

    # ══════════════════════════════════════════════════════════════════════
    # Panel 1: Combined Fit + Residuals (subplot with shared x-axis)
    # ══════════════════════════════════════════════════════════════════════
    st.subheader("1 · Fitted Binary Fraction vs ΔRV Threshold")

    fig1 = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.75, 0.25],
        vertical_spacing=0.04,
    )

    # ── Top panel: fit ────────────────────────────────────────────────
    # Observed data at change points only
    fig1.add_trace(go.Scatter(
        x=t_dots, y=f_dots, mode="markers",
        marker=dict(size=5, color="black"),
        name="Observed (sig-filtered)",
        error_y=dict(
            type="data", array=e_dots, visible=True,
            thickness=1, width=2,
        ),
        legendgroup="obs",
    ), row=1, col=1)

    # Raw fraction (all points, light grey)
    fig1.add_trace(go.Scatter(
        x=t_full, y=raw_frac, mode="lines",
        line=dict(color="grey", width=1),
        opacity=0.4,
        name="Raw (no sig filter)",
        legendgroup="raw",
    ), row=1, col=1)

    # Model curve
    fig1.add_trace(go.Scatter(
        x=t_full, y=fitted_vals_full, mode="lines",
        line=dict(color="#E25A53", width=2.5),
        name=f"Model (f_bin = {f_fit:.3f})",
        legendgroup="model",
    ), row=1, col=1)

    # Single component
    fig1.add_trace(go.Scatter(
        x=t_full, y=single_comp, mode="lines",
        line=dict(color=COLOR_SINGLE, width=1.5, dash="dash"),
        name=f"Singles (σ = {sigma_s_fit:.1f} km/s)",
        legendgroup="single",
    ), row=1, col=1)

    # Binary component
    fig1.add_trace(go.Scatter(
        x=t_full, y=binary_comp, mode="lines",
        line=dict(color=COLOR_BINARY, width=1.5, dash="dash"),
        name="Binaries (empirical)",
        legendgroup="binary",
    ), row=1, col=1)

    # Optimal threshold line
    if t_optimal is not None:
        fig1.add_vline(
            x=t_optimal,
            line=dict(color="#DAA520", width=2, dash="dot"),
            annotation_text=f"t_opt = {t_optimal:.0f} km/s",
            annotation_position="top right",
            row=1, col=1,
        )

    # Chi_red annotation on the fit panel
    fig1.add_annotation(
        x=0.02, y=0.05, xref="x domain", yref="y domain",
        text=(
            f"χ²_red = {chi2_red:.2f}<br>"
            f"f_bin = {f_fit:.3f} ± {f_err:.3f}<br>"
            f"σ_s = {sigma_s_fit:.1f} ± {sigma_s_err:.1f} km/s"
        ),
        showarrow=False,
        font=dict(size=11),
        bgcolor="rgba(255,255,255,0.8)",
        bordercolor="grey",
        borderwidth=1,
        row=1, col=1,
    )

    # ── Bottom panel: residuals ───────────────────────────────────────
    fig1.add_trace(go.Scatter(
        x=t_dots, y=residuals_dots, mode="markers",
        marker=dict(size=4, color="black"),
        name="Residuals",
        showlegend=False,
        error_y=dict(
            type="constant", value=1.0, visible=True,
            thickness=1, width=2,
        ),
    ), row=2, col=1)
    fig1.add_hline(y=0, line=dict(color="grey", width=1, dash="dash"), row=2, col=1)
    fig1.add_hline(y=2, line=dict(color="grey", width=0.5, dash="dot"), row=2, col=1)
    fig1.add_hline(y=-2, line=dict(color="grey", width=0.5, dash="dot"), row=2, col=1)

    # Layout
    _theme_xaxis = PLOTLY_THEME.get("xaxis", {})
    _theme_yaxis = PLOTLY_THEME.get("yaxis", {})
    _theme_legend = PLOTLY_THEME.get("legend", {})

    fig1.update_layout(**{
        **PLOTLY_THEME,
        "title": dict(text="Binary Fraction vs ΔRV Threshold — Mixture Model Fit"),
        "legend": {**_theme_legend, "x": 0.98, "y": 0.98, "xanchor": "right"},
        "height": 650,
    })
    fig1.update_yaxes(title_text="Binary fraction", row=1, col=1, **{
        k: v for k, v in _theme_yaxis.items() if k != "title"
    })
    fig1.update_yaxes(title_text="(Obs − Model) / σ", row=2, col=1, **{
        k: v for k, v in _theme_yaxis.items() if k != "title"
    })
    fig1.update_xaxes(title_text="ΔRV threshold (km/s)", row=2, col=1, **{
        k: v for k, v in _theme_xaxis.items() if k != "title"
    })

    st.plotly_chart(fig1, use_container_width=True)
    st.caption(
        "**Top:** Fitted two-component mixture model. Black dots: observed fraction "
        "at significance-filtered change points. Red: total model. Dashed: "
        "single/binary components. Gold: optimal threshold (PDF crossover).  \n"
        f"**Bottom:** Normalized residuals (χ²_red = {chi2_red:.2f}, "
        f"{ndof} d.o.f.). Dotted lines: ±2σ bands."
    )

    # ══════════════════════════════════════════════════════════════════════
    # Panel 2: Weighted PDF Components
    # ══════════════════════════════════════════════════════════════════════
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
        "xaxis": {**_theme_xaxis, "title": "ΔRV (km/s)"},
        "yaxis": {**_theme_yaxis, "title": "Weighted PDF"},
        "legend": {**_theme_legend, "x": 0.98, "y": 0.98, "xanchor": "right"},
    })
    st.plotly_chart(fig2, use_container_width=True)
    st.caption(
        "Weighted probability densities of single (blue) and binary (red) ΔRV "
        "distributions. The optimal threshold (gold) is where the binary PDF "
        "first exceeds the singles — the Bayes-optimal decision boundary."
    )

    # ══════════════════════════════════════════════════════════════════════
    # Panel 3: Parameter Playground (interactive sliders)
    # ══════════════════════════════════════════════════════════════════════
    st.subheader("3 · Parameter Playground")
    st.caption(
        "Adjust f_bin and σ_single manually to see how the model changes. "
        "The simulation is **not** re-run — only the mixture weights are "
        "updated using the cached survival functions."
    )

    pg_col1, pg_col2 = st.columns(2)
    with pg_col1:
        pg_fbin = st.slider(
            "f_bin (binary fraction)", 0.0, 1.0,
            float(f_fit), 0.01, key="pg_fbin",
        )
    with pg_col2:
        pg_sigma = st.slider(
            "σ_single (km/s)", 0.5, 80.0,
            float(sigma_s_fit), 0.5, key="pg_sigma",
        )

    # Rebuild survival functions from stored data
    pg_std_surv_fn = interp1d(
        res["surv_interp_s_x"], res["surv_interp_s_y"],
        kind="linear", bounds_error=False, fill_value=(1.0, 0.0),
    )
    pg_bin_surv_fn = interp1d(
        res["surv_interp_b_x"], res["surv_interp_b_y"],
        kind="linear", bounds_error=False, fill_value=(1.0, 0.0),
    )

    pg_surv_s = pg_std_surv_fn(t_full / pg_sigma)
    pg_surv_b = pg_bin_surv_fn(t_full)
    pg_model = (1.0 - pg_fbin) * pg_surv_s + pg_fbin * pg_surv_b

    # Chi_red for playground params
    pg_model_at_dots = (1.0 - pg_fbin) * pg_std_surv_fn(t_dots / pg_sigma) + pg_fbin * pg_bin_surv_fn(t_dots)
    pg_res = (f_dots - pg_model_at_dots) / e_dots
    pg_chi2 = float(np.sum(pg_res ** 2))
    pg_ndof = max(1, len(t_dots) - 2)
    pg_chi2_red = pg_chi2 / pg_ndof

    fig3 = go.Figure()
    # Observed data
    fig3.add_trace(go.Scatter(
        x=t_dots, y=f_dots, mode="markers",
        marker=dict(size=5, color="black"),
        name="Observed",
        error_y=dict(type="data", array=e_dots, visible=True, thickness=1, width=2),
    ))
    # Best-fit reference
    fig3.add_trace(go.Scatter(
        x=t_full, y=fitted_vals_full, mode="lines",
        line=dict(color="grey", width=1.5, dash="dash"),
        name=f"Best fit (f={f_fit:.3f}, σ={sigma_s_fit:.1f})",
        opacity=0.5,
    ))
    # Playground model
    fig3.add_trace(go.Scatter(
        x=t_full, y=pg_model, mode="lines",
        line=dict(color="#E25A53", width=2.5),
        name=f"Manual (f={pg_fbin:.3f}, σ={pg_sigma:.1f})",
    ))

    fig3.add_annotation(
        x=0.02, y=0.05, xref="x domain", yref="y domain",
        text=f"χ²_red = {pg_chi2_red:.2f}",
        showarrow=False,
        font=dict(size=12, color="#E25A53"),
        bgcolor="rgba(255,255,255,0.8)",
        bordercolor="#E25A53",
        borderwidth=1,
    )

    fig3.update_layout(**{
        **PLOTLY_THEME,
        "title": dict(text="Parameter Playground — Interactive Model Comparison"),
        "xaxis": {**_theme_xaxis, "title": "ΔRV threshold (km/s)"},
        "yaxis": {**_theme_yaxis, "title": "Binary fraction"},
        "legend": {**_theme_legend, "x": 0.98, "y": 0.98, "xanchor": "right"},
    })
    st.plotly_chart(fig3, use_container_width=True)
    st.caption(
        f"Interactive parameter exploration. Grey dashed: best-fit model. "
        f"Red solid: manual model with χ²_red = {pg_chi2_red:.2f}."
    )

    # ══════════════════════════════════════════════════════════════════════
    # Panel 4: Binary ΔRV Histogram
    # ══════════════════════════════════════════════════════════════════════
    st.subheader("4 · Simulated Binary ΔRV Distribution")

    fig4 = go.Figure()
    # Histogram of simulated binary ΔRVs
    fig4.add_trace(go.Histogram(
        x=binary_drvs,
        nbinsx=80,
        marker_color=COLOR_BINARY,
        opacity=0.6,
        name="Simulated binary ΔRVs",
    ))

    # Overlay observed ΔRVs as rug/markers
    obs_binary_mask = is_sig & (p2p > (t_optimal if t_optimal is not None else 45.5))
    obs_single_mask = ~obs_binary_mask

    # Mark observed binaries
    if np.any(obs_binary_mask):
        fig4.add_trace(go.Scatter(
            x=p2p[obs_binary_mask],
            y=np.zeros(int(np.sum(obs_binary_mask))),
            mode="markers",
            marker=dict(
                size=10, color=COLOR_BINARY,
                symbol="diamond", line=dict(width=1, color="black"),
            ),
            name=f"Observed binaries (N={int(np.sum(obs_binary_mask))})",
        ))
    # Mark observed singles
    if np.any(obs_single_mask):
        fig4.add_trace(go.Scatter(
            x=p2p[obs_single_mask],
            y=np.zeros(int(np.sum(obs_single_mask))),
            mode="markers",
            marker=dict(
                size=8, color=COLOR_SINGLE,
                symbol="circle", line=dict(width=1, color="black"),
            ),
            name=f"Observed singles (N={int(np.sum(obs_single_mask))})",
        ))

    # Optimal threshold line
    if t_optimal is not None:
        fig4.add_vline(
            x=t_optimal,
            line=dict(color="#DAA520", width=2, dash="dot"),
            annotation_text=f"t_opt = {t_optimal:.0f} km/s",
        )

    fig4.update_layout(**{
        **PLOTLY_THEME,
        "title": dict(text="Simulated Binary ΔRV Distribution"),
        "xaxis": {**_theme_xaxis, "title": "ΔRV (km/s)"},
        "yaxis": {**_theme_yaxis, "title": "Count"},
        "legend": {**_theme_legend, "x": 0.98, "y": 0.98, "xanchor": "right"},
        "barmode": "overlay",
    })
    st.plotly_chart(fig4, use_container_width=True)
    st.caption(
        f"Histogram of {len(binary_drvs):,} simulated binary ΔRVs "
        f"({sim_info['period_model']} model). Diamond markers: observed "
        f"binaries; circles: observed singles. "
        f"Median = {np.median(binary_drvs):.1f} km/s, "
        f"95th %ile = {np.percentile(binary_drvs, 95):.1f} km/s."
    )

    # ══════════════════════════════════════════════════════════════════════
    # Panel 5: Best-Fit Parameters
    # ══════════════════════════════════════════════════════════════════════
    st.subheader("5 · Best-Fit Parameters")

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
        approach_desc = (
            "**Dsilva et al. (2023)**: Power-law period distribution, "
            "flat eccentricity, flat mass ratio."
            if pm == "powerlaw"
            else "**Langer et al. (2020)**: Two-component period mixture "
            "(Case A + Case B), zero eccentricity (post-RLOF), "
            "peaked mass-ratio distribution."
        )
        st.markdown(
            f"- **Approach:** {approach_desc}\n"
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
