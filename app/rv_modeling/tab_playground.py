"""rv_modeling/tab_playground.py — Tab C: Manual parameter playground."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import scipy.stats as sp_stats
import streamlit as st

from shared import PLOTLY_THEME, COLOR_BINARY, COLOR_SINGLE

from rv_modeling.helpers import (
    T_MAX, COLOR_GAUSS, _theme_parts, _ann,
    render_error_model_pair, render_orbital_params,
    render_orbital_histograms,
)
from rv_modeling.compute import (
    compute_model_fraction_curve, compute_physics_fraction_curve,
    compute_physics_diagnostics, DIST_MAP,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slider_dist_selector(label: str, key_prefix: str,
                          default_dist: str = "Normal") -> tuple[str, tuple]:
    """Distribution selector using sliders for instant updates."""
    dist_names = list(DIST_MAP.keys())
    default_idx = dist_names.index(default_dist) if default_dist in dist_names else 0
    dist_name = st.selectbox(f"{label} distribution", dist_names,
                             index=default_idx, key=f"{key_prefix}_dist")

    _slider_meta = {
        "Normal": [("μ", -100.0, 100.0, 0.0, 0.5),
                   ("σ", 0.5, 200.0, 20.0, 0.5)],
        "Log-normal": [("s", 0.01, 3.0, 0.5, 0.01),
                       ("loc", -100.0, 100.0, 0.0, 0.5),
                       ("scale", 0.5, 200.0, 20.0, 0.5)],
        "Gamma": [("a", 0.1, 30.0, 2.0, 0.1),
                  ("loc", -100.0, 100.0, 0.0, 0.5),
                  ("scale", 0.5, 100.0, 10.0, 0.5)],
        "Weibull": [("c", 0.1, 5.0, 1.5, 0.05),
                    ("loc", -100.0, 100.0, 0.0, 0.5),
                    ("scale", 0.5, 200.0, 20.0, 0.5)],
        "Exponential": [("loc", -100.0, 100.0, 0.0, 0.5),
                        ("scale", 0.5, 200.0, 20.0, 0.5)],
        "Flat (uniform)": [("loc", -200.0, 200.0, -50.0, 1.0),
                           ("width", 1.0, 500.0, 100.0, 1.0)],
    }

    pmeta = _slider_meta.get(dist_name, [])
    params = []
    if pmeta:
        cols = st.columns(len(pmeta))
        for i, (plabel, pmin, pmax, default, step) in enumerate(pmeta):
            with cols[i]:
                val = st.slider(
                    plabel, pmin, pmax,
                    float(st.session_state.get(f"{key_prefix}_s_{i}", default)),
                    step, key=f"{key_prefix}_s_{i}",
                )
                params.append(val)
    return dist_name, tuple(params)


def _render_playground_plot(
    obs_data: dict, t_arr: np.ndarray, f_curve: np.ndarray,
    pg_fbin: float, chi2_red: float, residuals: np.ndarray,
    model_label: str,
) -> None:
    """Shared plot renderer for both parametric and physics-based modes."""
    _ax, _ay, _al = _theme_parts()
    pal = obs_data["pal"]
    t_full = obs_data["t_full"]
    t_dots, f_dots, e_dots = obs_data["t_dots"], obs_data["f_dots"], obs_data["e_dots"]
    raw_frac = obs_data["raw_frac"]

    fit_result = st.session_state.get("rvm_fit_result")

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.75, 0.25], vertical_spacing=0.04,
    )

    # Observed
    fig.add_trace(go.Scatter(
        x=t_dots, y=f_dots, mode="markers",
        marker=dict(size=6, color=pal["font_color"]),
        name="Observed",
        error_y=dict(type="data", array=e_dots, visible=True,
                     thickness=1, width=2, color=pal["muted_color"]),
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=t_full, y=raw_frac, mode="lines",
        line=dict(color="grey", width=1), opacity=0.3,
        name="Raw (no sig filter)",
    ), row=1, col=1)

    # Current playground model
    fig.add_trace(go.Scatter(
        x=t_arr, y=f_curve, mode="lines",
        line=dict(color=COLOR_BINARY, width=2.5),
        name=f"{model_label} (f={pg_fbin:.3f}, χ²={chi2_red:.2f})",
    ), row=1, col=1)

    # Tab B best fit
    if fit_result is not None:
        fig.add_trace(go.Scatter(
            x=fit_result["t_arr"], y=fit_result["f_curve"], mode="lines",
            line=dict(color=COLOR_GAUSS, width=1.5, dash="dot"),
            opacity=0.6,
            name=f"Tab B fit (f={fit_result['f_bin']:.3f})",
        ), row=1, col=1)

    # Snapshots
    snapshots = st.session_state.get("rvm_pg_snapshots", [])
    snap_colors = ["#2ECC71", "#F39C12", "#9B59B6", "#1ABC9C", "#E74C3C"]
    for i, snap in enumerate(snapshots):
        clr = snap_colors[i % len(snap_colors)]
        fig.add_trace(go.Scatter(
            x=snap["t_arr"], y=snap["f_curve"], mode="lines",
            line=dict(color=clr, width=1.2, dash="dash"),
            opacity=0.5,
            name=f"Snap #{i+1} (f={snap['f_bin']:.3f}, χ²={snap['chi2_red']:.2f})",
        ), row=1, col=1)

    # Residuals
    fig.add_trace(go.Scatter(
        x=t_dots, y=residuals, mode="markers",
        marker=dict(size=4, color=COLOR_BINARY, symbol="circle"),
        name="Residuals", showlegend=False,
    ), row=2, col=1)
    fig.add_hline(y=0, line=dict(color="grey", width=1, dash="dash"), row=2, col=1)
    fig.add_hline(y=2, line=dict(color="grey", width=0.5, dash="dot"), row=2, col=1)
    fig.add_hline(y=-2, line=dict(color="grey", width=0.5, dash="dot"), row=2, col=1)

    fig.update_layout(**{
        **PLOTLY_THEME,
        "title": dict(text="Playground: Binary Fraction vs ΔRV Threshold"),
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
        "Solid red = current slider values. Dotted purple = Tab B best fit. "
        "Dashed = saved snapshots. Bottom: residuals vs observed."
    )


# ---------------------------------------------------------------------------
# Main tab renderer
# ---------------------------------------------------------------------------

def render_tab_playground(obs_data: dict) -> None:
    """Tab C: Playground — manually adjust distributions and see f(T) instantly."""
    t_dots, f_dots, e_dots = obs_data["t_dots"], obs_data["f_dots"], obs_data["e_dots"]

    st.subheader("Playground")
    st.caption(
        "Adjust parameters with sliders and instantly see how "
        "the model fits the observed binary fraction vs ΔRV threshold."
    )

    # ── Mode toggle ──
    sim_mode = st.radio(
        "Simulation mode", ["Parametric", "Physics-based"],
        horizontal=True, key="rvm_pg_mode",
    )

    # ── f_bin slider (shared) ──
    pg_fbin = st.slider("f_bin (binary fraction)", 0.01, 0.99, 0.40, 0.01,
                        key="rvm_pg_fbin")

    if sim_mode == "Parametric":
        _render_parametric_branch(obs_data, pg_fbin, t_dots, f_dots, e_dots)
    else:
        _render_physics_branch(obs_data, pg_fbin, t_dots, f_dots, e_dots)

    # ── Snapshot comparison table ──
    snapshots = st.session_state.get("rvm_pg_snapshots", [])
    if snapshots:
        st.subheader("Saved Snapshots")
        import pandas as pd
        rows = []
        for i, snap in enumerate(snapshots):
            rows.append({
                "#": i + 1,
                "f_bin": f"{snap['f_bin']:.4f}",
                "χ²_red": f"{snap['chi2_red']:.3f}",
                "Mode": snap.get("mode", "Parametric"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True)


def _render_parametric_branch(obs_data, pg_fbin, t_dots, f_dots, e_dots):
    """Parametric mode: scipy distribution draws."""
    # Distribution selectors
    col_s, col_b = st.columns(2)
    with col_s:
        st.markdown("**Single stars**")
        single_dist, single_params = _slider_dist_selector(
            "Single", "rvm_pg_sin", default_dist="Normal",
        )
    with col_b:
        st.markdown("**Binary stars**")
        best_dist = st.session_state.get("rvm_best_binary_dist", "Normal")
        binary_dist, binary_params = _slider_dist_selector(
            "Binary", "rvm_pg_bin", default_dist=best_dist,
        )

    # Sim controls
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        n_sim = st.select_slider(
            "N_sim", [10_000, 50_000, 100_000, 200_000],
            value=50_000, key="rvm_pg_nsim",
        )
    with sc2:
        n_epochs = st.number_input("N_epochs", 2, 20, 6, key="rvm_pg_nep")
    with sc3:
        seed = st.number_input("Seed", 0, 99999, 42, key="rvm_pg_seed")

    # Compute
    try:
        t_arr, f_curve = compute_model_fraction_curve(
            dist_single=single_dist, params_single=single_params,
            dist_binary=binary_dist, params_binary=binary_params,
            f_bin=pg_fbin, n_sim=int(n_sim),
            n_epochs=int(n_epochs), seed=int(seed),
            t_max=T_MAX,
        )
        f_model_dots = np.interp(t_dots, t_arr, f_curve)
        residuals = (f_dots - f_model_dots) / e_dots
        chi2 = float(np.sum(residuals ** 2))
        ndof = max(1, len(t_dots) - 1)
        chi2_red = chi2 / ndof
    except Exception as exc:
        st.error(f"Model computation failed: {exc}")
        return

    # Metrics + snapshot + plot
    _render_metrics_and_snapshot(pg_fbin, chi2_red, t_arr, f_curve, "Parametric",
                                single_dist=single_dist, single_params=single_params,
                                binary_dist=binary_dist, binary_params=binary_params)
    _render_playground_plot(obs_data, t_arr, f_curve, pg_fbin, chi2_red,
                           residuals, "Parametric")


def _render_physics_branch(obs_data, pg_fbin, t_dots, f_dots, e_dots):
    """Physics-based mode: orbital simulation + real cadences + error models."""
    cadence_tuples = obs_data["cadence_tuples"]
    n_cadence = obs_data["n_cadence_stars"]

    st.info(f"Using real observation cadences from {n_cadence} WR stars. "
            f"N_total = n_sets × {n_cadence}.")

    # sigma_single + seed + n_sets
    rc1, rc2, rc3 = st.columns(3)
    with rc1:
        sigma_single = st.slider("σ_single (km/s)", 0.0, 30.0, 15.0, 0.5,
                                  key="rvm_pg_phys_sigma_s")
    with rc2:
        n_sets = st.select_slider(
            "N_sets (×25 stars)", [10, 50, 100, 200, 500],
            value=50, key="rvm_pg_phys_nsets",
        )
    with rc3:
        seed = st.number_input("Seed", 0, 99999, 42, key="rvm_pg_phys_seed")

    # Error models
    st.markdown("#### RV Error Models")
    err = render_error_model_pair("rvm_pg_phys")

    # Orbital params
    st.markdown("#### Orbital Parameters")
    orb = render_orbital_params("rvm_pg_phys")

    # Compute
    try:
        t_arr, f_curve = compute_physics_fraction_curve(
            f_bin=pg_fbin, pi=orb['pi'], n_sets=int(n_sets), seed=int(seed),
            error_model_single=err['type_single'],
            error_params_single=err['params_single'],
            sigma_measure_single=err['sigma_measure'],
            error_model_binary=err['type_binary'],
            error_params_binary=err['params_binary'],
            sigma_measure_binary=err['sigma_measure_binary'],
            sigma_single=sigma_single,
            period_model=orb['period_model'],
            logP_min=orb['logP_min'], logP_max=orb['logP_max'],
            e_model=orb['e_model'], e_max=orb['e_max'],
            q_model=orb['q_model'], q_min=orb['q_min'], q_max=orb['q_max'],
            q_flipped=orb['q_flipped'],
            mass_primary_fixed=orb['mass_primary_fixed'],
            weight_A=orb['weight_A'], dist_A=orb['dist_A'],
            mu_A=orb['mu_A'], sigma_A=orb['sigma_A'],
            dist_B=orb['dist_B'], mu_B=orb['mu_B'], sigma_B=orb['sigma_B'],
            langer_q_mu=orb['langer_q_mu'], langer_q_sigma=orb['langer_q_sigma'],
            cadence_tuples=cadence_tuples,
            t_max=T_MAX,
        )
        f_model_dots = np.interp(t_dots, t_arr, f_curve)
        residuals = (f_dots - f_model_dots) / e_dots
        chi2 = float(np.sum(residuals ** 2))
        ndof = max(1, len(t_dots) - 1)
        chi2_red = chi2 / ndof
    except Exception as exc:
        st.error(f"Physics simulation failed: {exc}")
        return

    # Metrics + snapshot + plot
    _render_metrics_and_snapshot(pg_fbin, chi2_red, t_arr, f_curve, "Physics-based")
    _render_playground_plot(obs_data, t_arr, f_curve, pg_fbin, chi2_red,
                           residuals, "Physics-based")

    # Orbital parameter histograms
    st.markdown("---")
    st.markdown("### Binary Orbital Properties")
    try:
        diag = compute_physics_diagnostics(
            f_bin=pg_fbin, pi=orb['pi'], n_sets=int(n_sets), seed=int(seed),
            error_model_single=err['type_single'],
            error_params_single=err['params_single'],
            sigma_measure_single=err['sigma_measure'],
            error_model_binary=err['type_binary'],
            error_params_binary=err['params_binary'],
            sigma_measure_binary=err['sigma_measure_binary'],
            sigma_single=sigma_single,
            period_model=orb['period_model'],
            logP_min=orb['logP_min'], logP_max=orb['logP_max'],
            e_model=orb['e_model'], e_max=orb['e_max'],
            q_model=orb['q_model'], q_min=orb['q_min'], q_max=orb['q_max'],
            q_flipped=orb['q_flipped'],
            mass_primary_fixed=orb['mass_primary_fixed'],
            weight_A=orb['weight_A'], dist_A=orb['dist_A'],
            mu_A=orb['mu_A'], sigma_A=orb['sigma_A'],
            dist_B=orb['dist_B'], mu_B=orb['mu_B'], sigma_B=orb['sigma_B'],
            langer_q_mu=orb['langer_q_mu'], langer_q_sigma=orb['langer_q_sigma'],
            cadence_tuples=cadence_tuples,
        )
        render_orbital_histograms(diag, pg_fbin, "rvm_pg_phys")
    except Exception as exc:
        st.warning(f"Orbital diagnostics failed: {exc}")


def _render_metrics_and_snapshot(
    pg_fbin, chi2_red, t_arr, f_curve, mode, **extra_snap,
):
    """Render metrics row and snapshot buttons."""
    m1, m2, m3 = st.columns(3)
    m1.metric("f_bin", f"{pg_fbin:.3f}")
    m2.metric("χ²_red", f"{chi2_red:.3f}")
    m3.metric("Mode", mode)

    snap_col1, snap_col2 = st.columns(2)
    with snap_col1:
        if st.button("Save snapshot", key="rvm_pg_snap_save"):
            snap = st.session_state.get("rvm_pg_snapshots", [])
            snap.append(dict(
                f_bin=pg_fbin, chi2_red=chi2_red,
                f_curve=f_curve.copy(), t_arr=t_arr.copy(),
                mode=mode, **extra_snap,
            ))
            st.session_state["rvm_pg_snapshots"] = snap
            st.toast(f"Snapshot #{len(snap)} saved (χ²={chi2_red:.3f})")
    with snap_col2:
        if st.button("Clear snapshots", key="rvm_pg_snap_clear"):
            st.session_state["rvm_pg_snapshots"] = []
            st.rerun()
