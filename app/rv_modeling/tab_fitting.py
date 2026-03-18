"""rv_modeling/tab_fitting.py — Tab B: Model Fitting (parametric distributions)."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import scipy.stats as sp_stats
import streamlit as st
from scipy.optimize import minimize

from shared import PLOTLY_THEME, COLOR_BINARY, COLOR_SINGLE

from rv_modeling.helpers import T_MAX, _theme_parts, _ann
from rv_modeling.compute import compute_model_fraction_curve, DIST_MAP

# Wider parameter bounds for RV distributions (centred RVs can be large)
_PARAM_META = {
    "Normal": [("μ (loc)", 0.0, -200.0, 200.0, 0.5),
               ("σ (scale)", 20.0, 0.01, 300.0, 0.5)],
    "Log-normal": [("s (shape)", 0.5, 0.01, 5.0, 0.01),
                   ("loc", 0.0, -200.0, 200.0, 0.5),
                   ("scale", 20.0, 0.01, 300.0, 0.5)],
    "Gamma": [("a (shape)", 2.0, 0.01, 50.0, 0.1),
              ("loc", 0.0, -200.0, 200.0, 0.5),
              ("scale", 10.0, 0.01, 200.0, 0.5)],
    "Weibull": [("c (shape)", 1.5, 0.01, 10.0, 0.01),
                ("loc", 0.0, -200.0, 200.0, 0.5),
                ("scale", 20.0, 0.01, 200.0, 0.5)],
    "Exponential": [("loc", 0.0, -200.0, 200.0, 0.5),
                    ("scale", 20.0, 0.01, 200.0, 0.5)],
    "Flat (uniform)": [("loc (start)", -50.0, -500.0, 500.0, 1.0),
                       ("scale (width)", 100.0, 0.01, 1000.0, 1.0)],
}


def _dist_selector(label: str, key_prefix: str,
                   default_dist: str = "Normal",
                   default_params: tuple | None = None) -> tuple[str, tuple]:
    """Render a distribution selector with parameter inputs. Returns (name, params)."""
    dist_names = list(DIST_MAP.keys())
    default_idx = dist_names.index(default_dist) if default_dist in dist_names else 0
    dist_name = st.selectbox(f"{label} distribution", dist_names,
                             index=default_idx, key=f"{key_prefix}_dist")

    pmeta = _PARAM_META.get(dist_name, [])
    params = []
    if pmeta:
        cols = st.columns(len(pmeta))
        for i, (plabel, default, pmin, pmax, step) in enumerate(pmeta):
            with cols[i]:
                # Use provided default if available and dist matches
                init_val = default
                if (default_params is not None
                        and i < len(default_params)
                        and st.session_state.get(f"{key_prefix}_dist") == default_dist):
                    init_val = float(default_params[i])
                val = st.number_input(
                    plabel, min_value=pmin, max_value=pmax,
                    value=float(st.session_state.get(f"{key_prefix}_p_{i}", init_val)),
                    step=step, format="%.4f", key=f"{key_prefix}_p_{i}",
                )
                params.append(val)
    return dist_name, tuple(params)


def render_tab_fitting(obs_data: dict) -> None:
    """Tab B: Parametric model fitting to binary fraction vs threshold."""
    _ax, _ay, _al = _theme_parts()
    pal = obs_data["pal"]
    t_full = obs_data["t_full"]
    t_dots, f_dots, e_dots = obs_data["t_dots"], obs_data["f_dots"], obs_data["e_dots"]
    f_obs = obs_data["f_obs"]
    raw_frac = obs_data["raw_frac"]
    n_stars = obs_data["n_stars"]

    st.subheader("Parametric Model Fitting")
    st.caption(
        "Choose RV distributions for single and binary stars, then fit the model "
        "to the observed binary fraction vs ΔRV threshold curve. The model draws "
        "6 RVs per star and computes ΔRV = max − min."
    )

    # ── Auto-populate from Tab A ──
    best_dist = st.session_state.get("rvm_best_binary_dist")
    best_params = st.session_state.get("rvm_best_binary_params")
    if best_dist:
        st.info(f"Tab A best fit: **{best_dist}** — params: "
                f"{tuple(round(p, 3) for p in best_params) if best_params else '—'}")
        if st.button("Use Tab A best fit for binary distribution",
                     key="rvm_use_taba"):
            st.session_state["rvm_fit_bin_dist"] = best_dist
            if best_params:
                for i, v in enumerate(best_params):
                    st.session_state[f"rvm_fit_bin_p_{i}"] = float(v)
            st.rerun()

    # ── Distribution selectors ──
    col_s, col_b = st.columns(2)
    with col_s:
        st.markdown("**Single-star RV distribution**")
        single_dist, single_params = _dist_selector(
            "Single", "rvm_fit_sin",
            default_dist="Normal", default_params=(0.0, 5.5),
        )
    with col_b:
        st.markdown("**Binary-star RV distribution**")
        binary_dist, binary_params = _dist_selector(
            "Binary", "rvm_fit_bin",
            default_dist=best_dist or "Normal",
            default_params=best_params,
        )

    # ── Model controls ──
    mc1, mc2, mc3, mc4 = st.columns(4)
    with mc1:
        n_sim = st.select_slider(
            "N_sim", [10_000, 50_000, 100_000, 200_000, 500_000],
            value=100_000, key="rvm_fit_nsim",
        )
    with mc2:
        n_epochs = st.number_input("N_epochs", 2, 20, 6, key="rvm_fit_nep")
    with mc3:
        seed = st.number_input("Seed", 0, 99999, 42, key="rvm_fit_seed")
    with mc4:
        optimize_fbin = st.checkbox("Optimize f_bin", value=True,
                                    key="rvm_fit_opt_fbin")
        if not optimize_fbin:
            fixed_fbin = st.number_input("Fixed f_bin", 0.0, 1.0, 0.4, 0.01,
                                         key="rvm_fit_fixed_fbin")

    # ── Run fit ──
    run_fit = st.button("Run Model Fit", type="primary",
                        use_container_width=True, key="rvm_fit_run")

    if run_fit:
        with st.spinner("Fitting parametric model..."):
            if optimize_fbin:
                # Optimize f_bin via grid search (simple and robust)
                best_chi2 = float("inf")
                best_fb = 0.4
                fbin_grid = np.linspace(0.01, 0.99, 99)
                progress = st.progress(0.0, text="Scanning f_bin...")
                for idx, fb in enumerate(fbin_grid):
                    t_arr, f_curve = compute_model_fraction_curve(
                        dist_single=single_dist, params_single=single_params,
                        dist_binary=binary_dist, params_binary=binary_params,
                        f_bin=float(fb), n_sim=int(n_sim),
                        n_epochs=int(n_epochs), seed=int(seed),
                        t_max=T_MAX,
                    )
                    # Chi-squared at observed data points
                    f_model_dots = np.interp(t_dots, t_arr, f_curve)
                    chi2 = float(np.sum(((f_dots - f_model_dots) / e_dots) ** 2))
                    if chi2 < best_chi2:
                        best_chi2 = chi2
                        best_fb = float(fb)
                    progress.progress((idx + 1) / len(fbin_grid))
                progress.empty()
                fit_fbin = best_fb
            else:
                fit_fbin = fixed_fbin

            # Final computation with best f_bin
            t_arr, f_curve = compute_model_fraction_curve(
                dist_single=single_dist, params_single=single_params,
                dist_binary=binary_dist, params_binary=binary_params,
                f_bin=fit_fbin, n_sim=int(n_sim),
                n_epochs=int(n_epochs), seed=int(seed),
                t_max=T_MAX,
            )
            f_model_dots = np.interp(t_dots, t_arr, f_curve)
            residuals = (f_dots - f_model_dots) / e_dots
            chi2 = float(np.sum(residuals ** 2))
            ndof = max(1, len(t_dots) - (1 if optimize_fbin else 0))

            st.session_state["rvm_fit_result"] = dict(
                t_arr=t_arr, f_curve=f_curve,
                f_bin=fit_fbin,
                single_dist=single_dist, single_params=single_params,
                binary_dist=binary_dist, binary_params=binary_params,
                chi2_red=chi2 / ndof, ndof=ndof,
                residuals=residuals,
                f_model_dots=f_model_dots,
                n_sim=int(n_sim), n_epochs=int(n_epochs), seed=int(seed),
            )

    # ── Display results ──
    result = st.session_state.get("rvm_fit_result")
    if result is None:
        st.info("Configure distributions above, then click **Run Model Fit**.")
        return

    st.markdown("---")
    st.subheader("Fit Results")

    # Metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("f_bin", f"{result['f_bin']:.4f}")
    m2.metric("χ²_red", f"{result['chi2_red']:.3f}")
    m3.metric("N_dof", f"{result['ndof']}")
    m4.metric("N_sim", f"{result['n_sim']:,}")

    # Main plot: f(T) + residuals
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.75, 0.25], vertical_spacing=0.04,
    )

    # Observed
    fig.add_trace(go.Scatter(
        x=t_dots, y=f_dots, mode="markers",
        marker=dict(size=6, color=pal["font_color"]),
        name="Observed (sig-filtered)",
        error_y=dict(type="data", array=e_dots, visible=True,
                     thickness=1, width=2, color=pal["muted_color"]),
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=t_full, y=raw_frac, mode="lines",
        line=dict(color="grey", width=1), opacity=0.4,
        name="Raw (no sig filter)",
    ), row=1, col=1)

    # Model
    fig.add_trace(go.Scatter(
        x=result["t_arr"], y=result["f_curve"], mode="lines",
        line=dict(color=COLOR_BINARY, width=2.5),
        name=f"Model (f={result['f_bin']:.3f}, χ²={result['chi2_red']:.2f})",
    ), row=1, col=1)

    # Annotation
    ann_text = (
        f"<b>f_bin = {result['f_bin']:.4f}</b><br>"
        f"Single: {result['single_dist']} {tuple(round(p, 2) for p in result['single_params'])}<br>"
        f"Binary: {result['binary_dist']} {tuple(round(p, 2) for p in result['binary_params'])}<br>"
        f"χ²_red = {result['chi2_red']:.3f}"
    )
    fig.add_annotation(
        x=0.02, y=0.05, xref="x domain", yref="y domain",
        text=ann_text, showarrow=False,
        **_ann(pal), row=1, col=1,
    )

    # Residuals
    fig.add_trace(go.Scatter(
        x=t_dots, y=result["residuals"], mode="markers",
        marker=dict(size=4, color=COLOR_BINARY, symbol="circle"),
        name="Residuals", showlegend=False,
    ), row=2, col=1)
    fig.add_hline(y=0, line=dict(color="grey", width=1, dash="dash"), row=2, col=1)
    fig.add_hline(y=2, line=dict(color="grey", width=0.5, dash="dot"), row=2, col=1)
    fig.add_hline(y=-2, line=dict(color="grey", width=0.5, dash="dot"), row=2, col=1)

    fig.update_layout(**{
        **PLOTLY_THEME,
        "title": dict(text="Parametric Model: Binary Fraction vs ΔRV Threshold"),
        "legend": {**_al, "x": 0.98, "y": 0.98, "xanchor": "right",
                   "font": dict(size=10)},
        "height": 650,
    })
    fig.update_yaxes(title_text="Binary fraction", row=1, col=1, **{
        k: v for k, v in _ay.items() if k != "title"})
    fig.update_yaxes(title_text="(Obs−Model)/σ", row=2, col=1, **{
        k: v for k, v in _ay.items() if k != "title"})
    fig.update_xaxes(title_text="ΔRV threshold (km/s)", row=2, col=1, **{
        k: v for k, v in _ax.items() if k != "title"})

    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Model draws N_epochs RVs per star from the chosen distributions, "
        "computes ΔRV = max − min, and counts the fraction exceeding each threshold."
    )

    # Parameter summary table
    st.subheader("Parameter Summary")
    import pandas as pd
    rows = [
        {"Parameter": "f_bin", "Value": f"{result['f_bin']:.4f}"},
        {"Parameter": f"Single dist ({result['single_dist']})",
         "Value": str(tuple(round(p, 4) for p in result['single_params']))},
        {"Parameter": f"Binary dist ({result['binary_dist']})",
         "Value": str(tuple(round(p, 4) for p in result['binary_params']))},
        {"Parameter": "χ²_red", "Value": f"{result['chi2_red']:.4f}"},
        {"Parameter": "N_dof", "Value": str(result['ndof'])},
        {"Parameter": "N_sim", "Value": f"{result['n_sim']:,}"},
        {"Parameter": "N_epochs", "Value": str(result['n_epochs'])},
    ]
    st.table(pd.DataFrame(rows))
