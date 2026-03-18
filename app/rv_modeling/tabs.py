"""rv_modeling/tabs.py — Existing tabs: Sample Fit, Fraction Recovery, Global Correction."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from scipy.interpolate import interp1d

from shared import PLOTLY_THEME, COLOR_BINARY, COLOR_SINGLE

from rv_modeling.helpers import NSIGMA_DETECT, T_MAX, COLOR_GAUSS, _theme_parts, _ann, resolve_nbins
from rv_modeling.compute import (
    compute_standard_ranges, compute_binary_delta_rvs,
    _empirical_survival, _fit_models,
)


# ---------------------------------------------------------------------------
# Tab D: Sample Fit (Empirical + Gaussian)
# ---------------------------------------------------------------------------

def render_tab_sample_fit(obs_data: dict):
    """Tab D: Fitted binary fraction vs ΔRV threshold (Empirical + Gaussian)."""
    pal = obs_data["pal"]
    _ax, _ay, _al = _theme_parts()
    t_full = obs_data["t_full"]
    t_dots, f_dots, e_dots = obs_data["t_dots"], obs_data["f_dots"], obs_data["e_dots"]
    f_obs = obs_data["f_obs"] if "f_obs" in obs_data else np.array(
        [np.sum(obs_data["is_sig"] & (obs_data["p2p"] > t)) / obs_data["n_stars"]
         for t in t_full])
    raw_frac = obs_data["raw_frac"]
    sig_err = obs_data["sig_err"]
    is_sig, p2p, p2p_err = obs_data["is_sig"], obs_data["p2p"], obs_data["p2p_err"]
    names = obs_data["names"]
    n_stars = obs_data["n_stars"]
    star_centered_rvs = obs_data["star_centered_rvs"]

    st.subheader("Sample Fit (Empirical + Gaussian)")
    st.caption(
        "Uses simulated binary ΔRVs from Tab A to fit two models: "
        "Empirical (uses actual ΔRV distribution) and Gaussian (analytical)."
    )

    # ── Check if simulation has been run in Tab A ──
    sim_params = st.session_state.get("rvm_sim_params")
    if sim_params is None:
        st.warning("Run the simulation in the **Simulate Binary RVs** tab first.")
        return

    # ── Run ΔRV simulation + fitting ──
    should_run = ("rvm_sf_results" not in st.session_state
                  or st.button("Re-run fitting", key="rvm_sf_rerun"))

    if should_run:
        with st.spinner("Computing ΔRVs and fitting models..."):
            p = sim_params
            binary_drvs = compute_binary_delta_rvs(
                n_sim=p["n_sim"], n_epochs=p["n_epochs"],
                time_span=p["time_span"],
                period_model=p["period_model"], pi=p["pi"],
                e_model=p["e_model"], e_max=p["e_max"],
                q_model=p["q_model"], seed=p["seed"],
                weight_A=p["weight_A"],
                logP_min=p["logP_min"], logP_max=p["logP_max"],
                q_min=p["q_min"], q_max=p["q_max"],
                q_flipped=p["q_flipped"],
                langer_q_mu=p["langer_q_mu"],
                langer_q_sigma=p["langer_q_sigma"],
                mass_primary_model=p["mass_model"],
                mass_primary_fixed=p["mass_fixed"],
                mass_primary_min=p.get("mass_min", 10.0),
                mass_primary_max=p.get("mass_max", 20.0),
                dist_A=p["dist_A"], mu_A=p["mu_A"], sigma_A=p["sigma_A"],
                dist_B=p["dist_B"], mu_B=p["mu_B"], sigma_B=p["sigma_B"],
            )
            sorted_binary = np.sort(binary_drvs)
            sorted_std_ranges = compute_standard_ranges(p["n_epochs"])

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

            st.session_state["rvm_sf_results"] = dict(
                emp=emp, gauss=gauss,
                binary_drvs=binary_drvs,
                surv_s_x=t_interp_s, surv_s_y=surv_s_raw,
                surv_b_x=t_interp_b, surv_b_y=surv_b_raw,
                sim_info=sim_params,
            )

    res = st.session_state.get("rvm_sf_results")
    if res is None:
        st.info("Waiting for computation...")
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

    # ── Instant controls ──
    st.markdown("**Instant controls** — adjust and see plots update immediately")
    ic1, ic2, ic3 = st.columns(3)
    with ic1:
        pg_fbin = st.slider(
            "f_bin", 0.0, 1.0,
            st.session_state.get("_rvm_bestfit_fbin", 0.4),
            0.01, key="rvm_sf_fbin",
        )
    with ic2:
        pg_sigma_s = st.slider(
            "σ_single (km/s)", 0.5, 80.0,
            st.session_state.get("_rvm_bestfit_sigma_s", 10.0),
            0.5, key="rvm_sf_sigma_s",
        )
    with ic3:
        pg_sigma_b = st.slider(
            "σ_binary (km/s) — Gaussian model", 5.0, 300.0,
            st.session_state.get("_rvm_bestfit_sigma_b", 60.0),
            1.0, key="rvm_sf_sigma_b",
        )

    # Playground curves
    pg_emp_curve = (1 - pg_fbin) * std_surv_fn(t_full / pg_sigma_s) + \
                   pg_fbin * bin_surv_fn(t_full)
    pg_gauss_curve = (1 - pg_fbin) * std_surv_fn(t_full / pg_sigma_s) + \
                     pg_fbin * std_surv_fn(t_full / pg_sigma_b)

    pg_emp_d = (1 - pg_fbin) * std_surv_fn(t_dots / pg_sigma_s) + \
               pg_fbin * bin_surv_fn(t_dots)
    pg_gauss_d = (1 - pg_fbin) * std_surv_fn(t_dots / pg_sigma_s) + \
                 pg_fbin * std_surv_fn(t_dots / pg_sigma_b)
    pg_chi2_emp = float(np.sum(((f_dots - pg_emp_d) / e_dots) ** 2)) / max(1, len(t_dots) - 2)
    pg_chi2_gauss = float(np.sum(((f_dots - pg_gauss_d) / e_dots) ** 2)) / max(1, len(t_dots) - 3)

    t_optimal_main = None
    if emp is not None:
        t_optimal_main = emp.get("t_optimal")
    elif gauss is not None:
        t_optimal_main = gauss.get("t_optimal")
    if t_optimal_main is None:
        t_optimal_main = 45.5

    st.markdown("---")

    # ── Main plot ──
    fig1 = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.75, 0.25], vertical_spacing=0.04,
    )

    # Observed
    fig1.add_trace(go.Scatter(
        x=t_dots, y=f_dots, mode="markers",
        marker=dict(size=6, color=pal["font_color"]),
        name="Observed (sig-filtered)",
        error_y=dict(type="data", array=e_dots, visible=True,
                     thickness=1, width=2, color=pal["muted_color"]),
    ), row=1, col=1)

    fig1.add_trace(go.Scatter(
        x=t_full, y=raw_frac, mode="lines",
        line=dict(color="grey", width=1), opacity=0.4,
        name="Raw (no sig filter)",
    ), row=1, col=1)

    # Playground curves
    fig1.add_trace(go.Scatter(
        x=t_full, y=pg_emp_curve, mode="lines",
        line=dict(color=COLOR_BINARY, width=2.5),
        name=f"Empirical (f={pg_fbin:.3f}, σ_s={pg_sigma_s:.1f}) "
             f"χ²={pg_chi2_emp:.2f}",
    ), row=1, col=1)
    fig1.add_trace(go.Scatter(
        x=t_full, y=pg_gauss_curve, mode="lines",
        line=dict(color=COLOR_GAUSS, width=2.5),
        name=f"Gaussian (f={pg_fbin:.3f}, σ_s={pg_sigma_s:.1f}, "
             f"σ_b={pg_sigma_b:.1f}) χ²={pg_chi2_gauss:.2f}",
    ), row=1, col=1)

    # Best-fit references (faded)
    if emp is not None:
        fig1.add_trace(go.Scatter(
            x=t_full, y=emp["fitted_full"], mode="lines",
            line=dict(color=COLOR_BINARY, width=1.2, dash="dot"),
            opacity=0.35, name=f"Best-fit emp (f={emp['f_fit']:.3f})",
        ), row=1, col=1)
    if gauss is not None:
        fig1.add_trace(go.Scatter(
            x=t_full, y=gauss["fitted_full"], mode="lines",
            line=dict(color=COLOR_GAUSS, width=1.2, dash="dot"),
            opacity=0.35, name=f"Best-fit gauss (f={gauss['f_fit']:.3f})",
        ), row=1, col=1)

    # Optimal threshold lines
    for mdl, clr, lbl in [(emp, "#DAA520", "Emp"), (gauss, COLOR_GAUSS, "Gauss")]:
        if mdl is not None and mdl.get("t_optimal") is not None:
            fig1.add_vline(
                x=mdl["t_optimal"],
                line=dict(color=clr, width=1.5, dash="dot"),
                annotation_text=f"{lbl} t_opt={mdl['t_optimal']:.0f}",
                annotation_position="top right",
                annotation_font=dict(size=10, color=clr),
                row=1, col=1,
            )

    # Annotation
    ann_parts = []
    if emp is not None:
        ann_parts.append(
            f"<b>Emp best-fit:</b> f={emp['f_fit']:.3f}±{emp['f_err']:.3f}, "
            f"σ_s={emp['sigma_s']:.1f}, χ²_r={emp['chi2_red']:.2f}")
    if gauss is not None:
        ann_parts.append(
            f"<b>Gauss best-fit:</b> f={gauss['f_fit']:.3f}±{gauss['f_err']:.3f}, "
            f"σ_s={gauss['sigma_s']:.1f}, σ_b={gauss['sigma_b']:.1f}, "
            f"χ²_r={gauss['chi2_red']:.2f}")
    fig1.add_annotation(
        x=0.02, y=0.05, xref="x domain", yref="y domain",
        text="<br>".join(ann_parts), showarrow=False,
        **_ann(pal), row=1, col=1,
    )

    # Residuals
    if emp is not None:
        fig1.add_trace(go.Scatter(
            x=t_dots, y=emp["residuals"], mode="markers",
            marker=dict(size=4, color=COLOR_BINARY, symbol="circle"),
            name="Emp residuals", showlegend=False,
        ), row=2, col=1)
    if gauss is not None:
        fig1.add_trace(go.Scatter(
            x=t_dots, y=gauss["residuals"], mode="markers",
            marker=dict(size=4, color=COLOR_GAUSS, symbol="diamond"),
            name="Gauss residuals", showlegend=False,
        ), row=2, col=1)
    fig1.add_hline(y=0, line=dict(color="grey", width=1, dash="dash"), row=2, col=1)
    fig1.add_hline(y=2, line=dict(color="grey", width=0.5, dash="dot"), row=2, col=1)
    fig1.add_hline(y=-2, line=dict(color="grey", width=0.5, dash="dot"), row=2, col=1)

    fig1.update_layout(**{
        **PLOTLY_THEME,
        "title": dict(text="Binary Fraction vs ΔRV Threshold"),
        "legend": {**_al, "x": 0.98, "y": 0.98, "xanchor": "right",
                   "font": dict(size=10)},
        "height": 700,
    })
    fig1.update_yaxes(title_text="Binary fraction", row=1, col=1, **{
        k: v for k, v in _ay.items() if k != "title"})
    fig1.update_yaxes(title_text="(Obs−Model)/σ", row=2, col=1, **{
        k: v for k, v in _ay.items() if k != "title"})
    fig1.update_xaxes(title_text="ΔRV threshold (km/s)", row=2, col=1, **{
        k: v for k, v in _ax.items() if k != "title"})

    st.plotly_chart(fig1, use_container_width=True)
    st.caption(
        "**Solid lines** = current slider values. "
        "**Dotted** = best-fit from last run. "
        "Red = empirical, Purple = Gaussian."
    )

    # ── Weighted PDFs ──
    st.subheader("Weighted PDF Components")
    fig2 = go.Figure()
    for mdl, label, clr_s, clr_b, dash in [
        (emp, "Emp", COLOR_SINGLE, COLOR_BINARY, "solid"),
        (gauss, "Gauss", COLOR_GAUSS, COLOR_GAUSS, "dash"),
    ]:
        if mdl is None:
            continue
        fig2.add_trace(go.Scatter(
            x=mdl["mid_t"], y=mdl["w_pdf_s"], mode="lines",
            line=dict(color=clr_s, width=2, dash=dash),
            name=f"{label} (1−f)·PDF_s",
            fill="tozeroy" if dash == "solid" else None,
            fillcolor="rgba(74,144,217,0.15)" if dash == "solid" else None,
        ))
        fig2.add_trace(go.Scatter(
            x=mdl["mid_t"], y=mdl["w_pdf_b"], mode="lines",
            line=dict(color=clr_b, width=2, dash=dash),
            name=f"{label} f·PDF_b",
            fill="tozeroy" if dash == "solid" else None,
            fillcolor="rgba(226,90,83,0.15)" if dash == "solid" else None,
        ))
        if mdl.get("t_optimal") is not None:
            fig2.add_vline(
                x=mdl["t_optimal"],
                line=dict(color=clr_b if dash == "solid" else COLOR_GAUSS,
                          width=1.5, dash="dot"),
                annotation_text=f"{label}: {mdl['t_optimal']:.0f} km/s",
                annotation_font=dict(size=10),
            )

    fig2.update_layout(**{
        **PLOTLY_THEME,
        "title": dict(text="Weighted PDF Components"),
        "xaxis": {**_ax, "title": "ΔRV (km/s)"},
        "yaxis": {**_ay, "title": "Weighted PDF"},
        "legend": {**_al, "x": 0.98, "y": 0.98, "xanchor": "right"},
    })
    st.plotly_chart(fig2, use_container_width=True)

    # ── Parameter tables ──
    st.subheader("Best-Fit Parameters")
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(f"##### Empirical ({n_stars} stars)")
        if emp is not None:
            st.table({
                "Parameter": ["f_bin", "σ_single (km/s)", "χ²_red",
                              "N_dof", "t_optimal (km/s)"],
                "Value": [
                    f"{emp['f_fit']:.4f}", f"{emp['sigma_s']:.2f}",
                    f"{emp['chi2_red']:.3f}", f"{emp['ndof']}",
                    f"{emp['t_optimal']:.1f}" if emp.get("t_optimal") else "—",
                ],
                "Error": [
                    f"± {emp['f_err']:.4f}", f"± {emp['sigma_s_err']:.2f}",
                    "—", "—", "—",
                ],
            })
        else:
            st.warning("Empirical model failed.")
    with col_b:
        st.markdown(f"##### Gaussian ({n_stars} stars)")
        if gauss is not None:
            st.table({
                "Parameter": ["f_bin", "σ_single (km/s)", "σ_binary (km/s)",
                              "χ²_red", "N_dof", "t_optimal (km/s)"],
                "Value": [
                    f"{gauss['f_fit']:.4f}", f"{gauss['sigma_s']:.2f}",
                    f"{gauss['sigma_b']:.2f}", f"{gauss['chi2_red']:.3f}",
                    f"{gauss['ndof']}",
                    f"{gauss['t_optimal']:.1f}" if gauss.get("t_optimal") else "—",
                ],
                "Error": [
                    f"± {gauss['f_err']:.4f}", f"± {gauss['sigma_s_err']:.2f}",
                    f"± {gauss['sigma_b_err']:.2f}", "—", "—", "—",
                ],
            })
        else:
            st.warning("Gaussian model failed.")

    # ── Binary ΔRV histogram ──
    st.subheader("Simulated Binary ΔRV Distribution")
    _nb_drv = resolve_nbins(binary_drvs, obs_data)
    _hkw_drv = dict(nbinsx=_nb_drv) if _nb_drv is not None else {}
    fig_h = go.Figure()
    fig_h.add_trace(go.Histogram(
        x=binary_drvs, **_hkw_drv, marker_color=COLOR_BINARY,
        opacity=0.6, name="Simulated binary ΔRVs",
    ))
    obs_bin_mask = is_sig & (p2p > t_optimal_main)
    obs_sin_mask = ~obs_bin_mask
    if np.any(obs_bin_mask):
        fig_h.add_trace(go.Scatter(
            x=p2p[obs_bin_mask], y=np.zeros(int(np.sum(obs_bin_mask))),
            mode="markers",
            marker=dict(size=10, color=COLOR_BINARY, symbol="diamond",
                        line=dict(width=1, color=pal["font_color"])),
            name=f"Obs binaries (N={int(np.sum(obs_bin_mask))})",
        ))
    if np.any(obs_sin_mask):
        fig_h.add_trace(go.Scatter(
            x=p2p[obs_sin_mask], y=np.zeros(int(np.sum(obs_sin_mask))),
            mode="markers",
            marker=dict(size=8, color=COLOR_SINGLE, symbol="circle",
                        line=dict(width=1, color=pal["font_color"])),
            name=f"Obs singles (N={int(np.sum(obs_sin_mask))})",
        ))
    fig_h.add_vline(
        x=t_optimal_main,
        line=dict(color="#DAA520", width=2, dash="dot"),
        annotation_text=f"t_opt = {t_optimal_main:.0f} km/s",
        annotation_font=dict(color="#DAA520"),
    )
    fig_h.update_layout(**{
        **PLOTLY_THEME,
        "title": dict(text="Simulated Binary ΔRV Distribution"),
        "xaxis": {**_ax, "title": "ΔRV (km/s)"},
        "yaxis": {**_ay, "title": "Count"},
        "legend": {**_al, "x": 0.98, "y": 0.98, "xanchor": "right"},
        "barmode": "overlay",
    })
    st.plotly_chart(fig_h, use_container_width=True)
    st.caption(
        f"Histogram of {len(binary_drvs):,} simulated binary ΔRVs. "
        f"Median={np.median(binary_drvs):.1f}, "
        f"95th %ile={np.percentile(binary_drvs, 95):.1f} km/s."
    )


# ---------------------------------------------------------------------------
# Tab E: Fraction Recovery
# ---------------------------------------------------------------------------

def render_tab_fraction_recovery(obs_data: dict):
    """Tab E: Fraction Recovery."""
    _ax, _ay, _al = _theme_parts()
    pal = obs_data["pal"]
    t_full = obs_data["t_full"]
    f_obs = obs_data.get("f_obs")
    if f_obs is None:
        f_obs = np.array([np.sum(obs_data["is_sig"] & (obs_data["p2p"] > t))
                          / obs_data["n_stars"] for t in t_full])

    res = st.session_state.get("rvm_sf_results")
    if res is None:
        st.warning("Run Sample Fit first (or Simulate Binary RVs tab).")
        return

    emp, gauss = res["emp"], res["gauss"]

    t_optimal_main = None
    if emp is not None:
        t_optimal_main = emp.get("t_optimal")
    elif gauss is not None:
        t_optimal_main = gauss.get("t_optimal")
    if t_optimal_main is None:
        t_optimal_main = 45.5

    st.subheader("Recovered Binary Fraction vs Threshold")
    st.caption(
        "f_recovered(t) = (f_obs(t) − S_single(t)) / (S_binary(t) − S_single(t)). "
        "A stable plateau indicates reliable binary fraction recovery."
    )

    t_slider = st.slider(
        "Highlight threshold (km/s)", 0.0, 300.0,
        float(t_optimal_main), 1.0, key="rvm_t_slider",
    )

    for mdl, label, clr, dash in [
        (emp, "Empirical", COLOR_BINARY, "solid"),
        (gauss, "Gaussian", COLOR_GAUSS, "dash"),
    ]:
        if mdl is None:
            continue

        surv_s = mdl["surv_s"]
        surv_b = mdl["surv_b"]
        denom = surv_b - surv_s
        safe = np.abs(denom) > 1e-6
        f_rec = np.full_like(t_full, np.nan)
        f_rec[safe] = (f_obs[safe] - surv_s[safe]) / denom[safe]
        f_rec = np.clip(f_rec, -0.5, 1.5)

        fig_r = go.Figure()
        t_opt = mdl.get("t_optimal") or 45.5

        fig_r.add_vrect(x0=0, x1=t_opt,
                        fillcolor="rgba(226,90,83,0.08)", line_width=0,
                        annotation_text="Noise-dominated",
                        annotation_position="top left",
                        annotation_font=dict(size=10, color=COLOR_BINARY))
        fig_r.add_vrect(x0=t_opt, x1=T_MAX,
                        fillcolor="rgba(39,174,96,0.08)", line_width=0,
                        annotation_text="Signal-dominated",
                        annotation_position="top right",
                        annotation_font=dict(size=10, color="#27AE60"))

        fig_r.add_trace(go.Scatter(
            x=t_full, y=f_rec, mode="lines",
            line=dict(color=clr, width=2.5),
            name=f"f_recovered ({label})",
        ))
        fig_r.add_hline(
            y=mdl["f_fit"],
            line=dict(color=clr, width=1.5, dash="dash"),
            annotation_text=f"f_bin = {mdl['f_fit']:.3f}",
            annotation_position="bottom right",
            annotation_font=dict(color=clr, size=11),
        )

        t_idx = int(np.clip(t_slider, 0, T_MAX - 1))
        if t_idx < len(f_rec) and np.isfinite(f_rec[t_idx]):
            fig_r.add_trace(go.Scatter(
                x=[t_slider], y=[f_rec[t_idx]], mode="markers",
                marker=dict(size=12, color="#DAA520", symbol="star",
                            line=dict(width=1, color=pal["font_color"])),
                name=f"At t={t_slider:.0f}: f={f_rec[t_idx]:.3f}",
            ))

        fig_r.update_layout(**{
            **PLOTLY_THEME,
            "title": dict(text=f"Fraction Recovery — {label}"),
            "xaxis": {**_ax, "title": "ΔRV threshold (km/s)", "range": [0, 250]},
            "yaxis": {**_ay, "title": "Recovered f_bin", "range": [-0.1, 1.1]},
            "legend": {**_al, "x": 0.98, "y": 0.02, "xanchor": "right",
                       "yanchor": "bottom"},
            "height": 450,
        })
        st.plotly_chart(fig_r, use_container_width=True)

    st.caption(
        "Red = noise-dominated. Green = signal-dominated (fraction plateau). "
        "Gold star = value at selected threshold."
    )


# ---------------------------------------------------------------------------
# Tab F: Global Correction
# ---------------------------------------------------------------------------

def render_tab_global_correction(obs_data: dict):
    """Tab F: Global Correction (+Bartzakos Prior)."""
    _ax, _ay, _al = _theme_parts()
    pal = obs_data["pal"]
    t_full = obs_data["t_full"]
    f_obs = obs_data.get("f_obs")
    if f_obs is None:
        f_obs = np.array([np.sum(obs_data["is_sig"] & (obs_data["p2p"] > t))
                          / obs_data["n_stars"] for t in t_full])
    t_dots, f_dots, e_dots = obs_data["t_dots"], obs_data["f_dots"], obs_data["e_dots"]
    change_mask = obs_data["change_mask"]
    is_sig, p2p = obs_data["is_sig"], obs_data["p2p"]
    names = obs_data["names"]
    n_stars = obs_data["n_stars"]
    star_centered_rvs = obs_data["star_centered_rvs"]
    sig_err = obs_data["sig_err"]

    n_prior = st.number_input("N prior (Bartzakos known binaries)",
                              0, 10, 3, key="rvm_gc_nprior")

    res = st.session_state.get("rvm_sf_results")
    if res is None:
        st.warning("Run Sample Fit first.")
        return

    emp, gauss = res["emp"], res["gauss"]

    t_optimal_main = None
    if emp is not None:
        t_optimal_main = emp.get("t_optimal")
    elif gauss is not None:
        t_optimal_main = gauss.get("t_optimal")
    if t_optimal_main is None:
        t_optimal_main = 45.5

    st.subheader("Global Bias Correction (+Bartzakos Prior)")
    n_global = n_stars + n_prior
    st.caption(
        f"Raises observed fraction by {n_prior} known binaries: "
        f"f_global = (f_sample × {n_stars} + {n_prior}) / {n_global}."
    )

    f_obs_global = (f_obs * n_stars + n_prior) / n_global
    sig_err_global = np.sqrt(
        f_obs_global * (1 - f_obs_global) / n_global) + 1e-4
    f_dots_global = (f_dots * n_stars + n_prior) / n_global
    e_dots_global = sig_err_global[change_mask]

    for mdl, label, clr in [
        (emp, "Empirical", COLOR_BINARY),
        (gauss, "Gaussian", COLOR_GAUSS),
    ]:
        if mdl is None:
            continue

        f_sample = mdl["f_fit"]
        f_global_val = (f_sample * n_stars + n_prior) / n_global
        f_global_err = mdl["f_err"] * n_stars / n_global

        col_s, col_g = st.columns(2)
        with col_s:
            st.markdown(f"**{label} — Sample** (N={n_stars})")
            st.metric("f_bin (sample)", f"{f_sample:.4f} ± {mdl['f_err']:.4f}")
        with col_g:
            st.markdown(f"**{label} — Global** (N={n_global})")
            n_det = int(round(f_sample * n_stars))
            st.metric("f_bin (global)", f"{f_global_val:.4f} ± {f_global_err:.4f}")
            st.markdown(f"{n_det} detected + {n_prior} prior = "
                        f"**{n_det + n_prior}** / {n_global}")

        fig_g = go.Figure()
        fig_g.add_trace(go.Scatter(
            x=t_dots, y=f_dots, mode="markers",
            marker=dict(size=5, color=pal["muted_color"], opacity=0.4),
            name="Sample data",
            error_y=dict(type="data", array=e_dots, visible=True,
                         thickness=1, width=2, color=pal["muted_color"]),
        ))
        fig_g.add_trace(go.Scatter(
            x=t_dots, y=f_dots_global, mode="markers",
            marker=dict(size=6, color=pal["font_color"]),
            name=f"Global (+{n_prior} prior)",
            error_y=dict(type="data", array=e_dots_global, visible=True,
                         thickness=1, width=2, color=pal["muted_color"]),
        ))
        fig_g.add_trace(go.Scatter(
            x=t_full, y=mdl["fitted_full"], mode="lines",
            line=dict(color=clr, width=1.5, dash="dash"),
            opacity=0.5, name="Sample fit",
        ))
        fig_g.add_hline(
            y=f_global_val,
            line=dict(color="#DAA520", width=1.5, dash="dot"),
            annotation_text=f"f_global = {f_global_val:.3f}",
            annotation_position="bottom right",
            annotation_font=dict(color="#DAA520", size=11),
        )
        fig_g.update_layout(**{
            **PLOTLY_THEME,
            "title": dict(text=f"Global Correction — {label}"),
            "xaxis": {**_ax, "title": "ΔRV threshold (km/s)"},
            "yaxis": {**_ay, "title": "Binary fraction"},
            "legend": {**_al, "x": 0.98, "y": 0.98, "xanchor": "right"},
            "height": 450,
        })
        st.plotly_chart(fig_g, use_container_width=True)
        st.markdown("---")

    # ── Centered RV histograms ──
    st.subheader("Centered RV Distributions by Classification")
    t_class = t_optimal_main
    obs_binary = is_sig & (p2p > t_class)

    rvs_singles, rvs_binaries = [], []
    for i, nm in enumerate(names):
        if nm in star_centered_rvs:
            if bool(obs_binary[i]):
                rvs_binaries.extend(star_centered_rvs[nm].tolist())
            else:
                rvs_singles.extend(star_centered_rvs[nm].tolist())

    fig_rv = make_subplots(rows=1, cols=2, subplot_titles=[
        f"Singles (N_stars={int(np.sum(~obs_binary))})",
        f"Binaries (N_stars={int(np.sum(obs_binary))})",
    ])

    _nb_rv_s = resolve_nbins(np.asarray(rvs_singles), obs_data) if len(rvs_singles) > 0 else 30
    _nb_rv_b = resolve_nbins(np.asarray(rvs_binaries), obs_data) if len(rvs_binaries) > 0 else 30
    _hkw_s = dict(nbinsx=_nb_rv_s) if _nb_rv_s is not None else {}
    _hkw_b = dict(nbinsx=_nb_rv_b) if _nb_rv_b is not None else {}

    if len(rvs_singles) > 0:
        fig_rv.add_trace(go.Histogram(
            x=rvs_singles, **_hkw_s, marker_color=COLOR_SINGLE,
            opacity=0.7, name="Singles RVs",
        ), row=1, col=1)
        if emp is not None:
            x_g = np.linspace(min(rvs_singles), max(rvs_singles), 200)
            sig_val = emp["sigma_s"]
            _nb_s_eff = _nb_rv_s if _nb_rv_s is not None else 30
            sc = len(rvs_singles) * (max(rvs_singles) - min(rvs_singles)) / _nb_s_eff
            y_g = sc * np.exp(-0.5 * (x_g / sig_val) ** 2) / (
                sig_val * np.sqrt(2 * np.pi))
            fig_rv.add_trace(go.Scatter(
                x=x_g, y=y_g, mode="lines",
                line=dict(color=COLOR_SINGLE, width=2, dash="dash"),
                name=f"Gauss (σ={sig_val:.1f})",
            ), row=1, col=1)

    if len(rvs_binaries) > 0:
        fig_rv.add_trace(go.Histogram(
            x=rvs_binaries, **_hkw_b, marker_color=COLOR_BINARY,
            opacity=0.7, name="Binary RVs",
        ), row=1, col=2)
        if gauss is not None:
            x_g = np.linspace(min(rvs_binaries), max(rvs_binaries), 200)
            sig_bv = gauss["sigma_b"]
            _nb_b_eff = _nb_rv_b if _nb_rv_b is not None else 30
            sc_b = len(rvs_binaries) * (max(rvs_binaries) - min(rvs_binaries)) / _nb_b_eff
            y_g = sc_b * np.exp(-0.5 * (x_g / sig_bv) ** 2) / (
                sig_bv * np.sqrt(2 * np.pi))
            fig_rv.add_trace(go.Scatter(
                x=x_g, y=y_g, mode="lines",
                line=dict(color=COLOR_BINARY, width=2, dash="dash"),
                name=f"Gauss (σ={sig_bv:.1f})",
            ), row=1, col=2)

    fig_rv.update_layout(**{
        **PLOTLY_THEME,
        "title": dict(text="Centered RV Distributions"),
        "height": 400,
        "legend": {**_al, "x": 0.98, "y": 0.98, "xanchor": "right"},
    })
    for c in [1, 2]:
        fig_rv.update_xaxes(title_text="Centered RV (km/s)", row=1, col=c, **{
            k: v for k, v in _ax.items() if k != "title"})
        fig_rv.update_yaxes(title_text="Count", row=1, col=c, **{
            k: v for k, v in _ay.items() if k != "title"})
    st.plotly_chart(fig_rv, use_container_width=True)
