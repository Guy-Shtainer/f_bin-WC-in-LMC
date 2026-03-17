"""rv_modeling/tabs.py — The 4 result tabs for the RV Modeling page."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from shared import PLOTLY_THEME, COLOR_BINARY, COLOR_SINGLE

from rv_modeling.helpers import T_MAX, COLOR_GAUSS, _theme_parts, _ann


def render_tab_sample_fit(ctx: dict):
    """Tab 1: Sample Fit — fitted binary fraction vs ΔRV threshold."""
    pal = ctx["pal"]
    _ax, _ay, _al = _theme_parts()
    t_full = ctx["t_full"]
    t_dots, f_dots, e_dots = ctx["t_dots"], ctx["f_dots"], ctx["e_dots"]
    raw_frac = ctx["raw_frac"]
    emp, gauss = ctx["emp"], ctx["gauss"]
    binary_drvs = ctx["binary_drvs"]
    sim_info = ctx["sim_info"]
    pg_fbin, pg_sigma_s, pg_sigma_b = ctx["pg_fbin"], ctx["pg_sigma_s"], ctx["pg_sigma_b"]
    pg_emp_curve, pg_gauss_curve = ctx["pg_emp_curve"], ctx["pg_gauss_curve"]
    pg_chi2_emp, pg_chi2_gauss = ctx["pg_chi2_emp"], ctx["pg_chi2_gauss"]
    t_optimal_main = ctx["t_optimal_main"]
    is_sig, p2p, p2p_err = ctx["is_sig"], ctx["p2p"], ctx["p2p_err"]
    names = ctx["names"]
    n_stars = ctx["n_stars"]
    star_centered_rvs = ctx["star_centered_rvs"]

    st.subheader("Fitted Binary Fraction vs ΔRV Threshold")

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

    # Playground curves (current slider values)
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
            f"σ_s={emp['sigma_s']:.1f}, χ²_r={emp['chi2_red']:.2f}"
        )
    if gauss is not None:
        ann_parts.append(
            f"<b>Gauss best-fit:</b> f={gauss['f_fit']:.3f}±{gauss['f_err']:.3f}, "
            f"σ_s={gauss['sigma_s']:.1f}, σ_b={gauss['sigma_b']:.1f}, "
            f"χ²_r={gauss['chi2_red']:.2f}"
        )
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
        "**Solid lines** = current slider values (playground). "
        "**Dotted** = best-fit from last Recompute. "
        "Red = empirical, Purple = Gaussian. "
        "**Bottom:** normalized residuals of best-fit."
    )

    # ── Weighted PDFs ─────────────────────────────────────────────
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
        "title": dict(text="Weighted PDF Components (ΔRV Range Distribution)"),
        "xaxis": {**_ax, "title": "ΔRV (km/s)"},
        "yaxis": {**_ay, "title": "Weighted PDF"},
        "legend": {**_al, "x": 0.98, "y": 0.98, "xanchor": "right"},
    })
    st.plotly_chart(fig2, use_container_width=True)
    st.caption(
        "Solid = empirical, dashed = Gaussian. Vertical lines = optimal "
        "threshold (PDF crossover = Bayes-optimal boundary)."
    )

    # ── Parameter tables ──────────────────────────────────────────
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

    # ── Binary ΔRV histogram ──────────────────────────────────────
    st.subheader("Simulated Binary ΔRV Distribution")
    fig_h = go.Figure()
    fig_h.add_trace(go.Histogram(
        x=binary_drvs, nbinsx=80, marker_color=COLOR_BINARY,
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
        f"Histogram of {len(binary_drvs):,} simulated binary ΔRVs "
        f"({sim_info['period_model']} model). "
        f"Median={np.median(binary_drvs):.1f}, "
        f"95th %ile={np.percentile(binary_drvs, 95):.1f} km/s."
    )

    with st.expander("Simulation Details"):
        pm = sim_info["period_model"]
        pm_d = (f'π = {sim_info["pi"]:.1f}' if pm == "powerlaw"
                else f'w_A = {sim_info["weight_A"]:.2f}')
        st.markdown(
            f"- **Period model:** {pm} ({pm_d})\n"
            f"- **logP range:** [{sim_info.get('logP_min', '?')}, "
            f"{sim_info.get('logP_max', '?')}]\n"
            f"- **N_sim:** {sim_info['n_sim']:,}\n"
            f"- **n_epochs:** {sim_info['n_epochs']}\n"
            f"- **Time span:** {sim_info['time_span']:.0f} days\n"
            f"- **Eccentricity:** {sim_info['e_model']} "
            f"(e_max={sim_info['e_max']:.2f})\n"
            f"- **Mass ratio:** {sim_info['q_model']} "
            f"[{sim_info.get('q_min', '?')}, {sim_info.get('q_max', '?')}]"
            f"{' (flipped)' if sim_info.get('q_flipped') else ''}\n"
            f"- **Primary mass:** {sim_info.get('mass_model', 'fixed')} "
            f"({sim_info.get('mass_fixed', 10.0):.1f} M☉)\n"
            f"- **σ_single:** {sim_info.get('sigma_single', 0):.1f} km/s\n"
            f"- **σ_measure:** {sim_info.get('sigma_measure', 0):.3f} km/s\n"
            f"- **Seed:** {sim_info['seed']}"
        )


def render_tab_fraction_recovery(ctx: dict):
    """Tab 2: Fraction Recovery."""
    _ax, _ay, _al = _theme_parts()
    pal = ctx["pal"]
    t_full, f_obs = ctx["t_full"], ctx["f_obs"]
    emp, gauss = ctx["emp"], ctx["gauss"]
    t_optimal_main = ctx["t_optimal_main"]

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


def render_tab_global_correction(ctx: dict):
    """Tab 3: Global Correction (+Bartzakos Prior)."""
    _ax, _ay, _al = _theme_parts()
    pal = ctx["pal"]
    t_full, f_obs = ctx["t_full"], ctx["f_obs"]
    t_dots, f_dots, e_dots = ctx["t_dots"], ctx["f_dots"], ctx["e_dots"]
    emp, gauss = ctx["emp"], ctx["gauss"]
    n_stars, n_prior = ctx["n_stars"], ctx["n_prior"]
    change_mask = ctx["change_mask"]
    is_sig, p2p = ctx["is_sig"], ctx["p2p"]
    names = ctx["names"]
    star_centered_rvs = ctx["star_centered_rvs"]
    t_optimal_main = ctx["t_optimal_main"]

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

    # ── Centered RV histograms ────────────────────────────────────
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

    if len(rvs_singles) > 0:
        fig_rv.add_trace(go.Histogram(
            x=rvs_singles, nbinsx=30, marker_color=COLOR_SINGLE,
            opacity=0.7, name="Singles RVs",
        ), row=1, col=1)
        if emp is not None:
            x_g = np.linspace(min(rvs_singles), max(rvs_singles), 200)
            sig_val = emp["sigma_s"]
            sc = len(rvs_singles) * (max(rvs_singles) - min(rvs_singles)) / 30
            y_g = sc * np.exp(-0.5 * (x_g / sig_val) ** 2) / (
                sig_val * np.sqrt(2 * np.pi))
            fig_rv.add_trace(go.Scatter(
                x=x_g, y=y_g, mode="lines",
                line=dict(color=COLOR_SINGLE, width=2, dash="dash"),
                name=f"Gauss (σ={sig_val:.1f})",
            ), row=1, col=1)

    if len(rvs_binaries) > 0:
        fig_rv.add_trace(go.Histogram(
            x=rvs_binaries, nbinsx=30, marker_color=COLOR_BINARY,
            opacity=0.7, name="Binary RVs",
        ), row=1, col=2)
        if gauss is not None:
            x_g = np.linspace(min(rvs_binaries), max(rvs_binaries), 200)
            sig_bv = gauss["sigma_b"]
            sc_b = len(rvs_binaries) * (max(rvs_binaries) - min(rvs_binaries)) / 30
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


def render_tab_population_sim():
    """Tab 4: Population Sim (placeholder)."""
    st.subheader("Population Simulation")
    st.info(
        "🚧 **Coming soon** — Per-emission-line simulation, sorted p2p "
        "waterfall, two-line piecewise fit, MC confidence bands."
    )
