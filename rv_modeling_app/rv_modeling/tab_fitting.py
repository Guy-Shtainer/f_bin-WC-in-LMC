"""rv_modeling/tab_fitting.py — Tab B: Model Fitting (parametric + physics-based)."""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import scipy.stats as sp_stats
import streamlit as st
from scipy.optimize import minimize

from shared_lite import PLOTLY_THEME, COLOR_BINARY, COLOR_SINGLE

from rv_modeling.helpers import (
    T_MAX, _theme_parts, _ann,
    render_error_model_pair, render_orbital_params,
    render_orbital_histograms,
)
from rv_modeling.compute import (
    compute_model_fraction_curve, compute_physics_fraction_curve,
    compute_physics_diagnostics, DIST_MAP,
)

# Wider parameter bounds for RV distributions
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
    "Laplace": [("μ (loc)", 0.0, -200.0, 200.0, 0.5),
                ("b (scale)", 20.0, 0.01, 300.0, 0.5)],
    "Gen. Normal": [("β (shape)", 1.0, 0.1, 10.0, 0.05),
                    ("loc", 0.0, -200.0, 200.0, 0.5),
                    ("scale", 20.0, 0.01, 300.0, 0.5)],
}


def _dist_selector(label: str, key_prefix: str,
                   default_dist: str = "Normal",
                   default_params: tuple | None = None,
                   sm=None, settings_path=None) -> tuple[str, tuple]:
    """Render a distribution selector with parameter inputs."""
    dist_names = list(DIST_MAP.keys())
    default_idx = dist_names.index(default_dist) if default_dist in dist_names else 0
    _oc_dist = {}
    if sm is not None and settings_path is not None:
        _k_d = f"{key_prefix}_dist"
        _oc_dist = dict(on_change=lambda k=_k_d, p=settings_path: sm.save(
            p + ['dist'], value=st.session_state[k]))
    dist_name = st.selectbox(f"{label} distribution", dist_names,
                             index=default_idx, key=f"{key_prefix}_dist",
                             **_oc_dist)

    pmeta = _PARAM_META.get(dist_name, [])
    params = []
    if pmeta:
        cols = st.columns(len(pmeta))
        for i, (plabel, default, pmin, pmax, step) in enumerate(pmeta):
            with cols[i]:
                init_val = default
                if (default_params is not None
                        and i < len(default_params)
                        and st.session_state.get(f"{key_prefix}_dist") == default_dist):
                    init_val = float(default_params[i])
                _oc_p = {}
                if sm is not None and settings_path is not None:
                    _k_p = f"{key_prefix}_p_{i}"
                    _oc_p = dict(on_change=lambda k=_k_p, p=settings_path, idx=str(i): sm.save(
                        p + ['params', idx], value=st.session_state[k]))
                val = st.number_input(
                    plabel,
                    value=float(st.session_state.get(f"{key_prefix}_p_{i}", init_val)),
                    step=step, format="%.4f", key=f"{key_prefix}_p_{i}",
                    **_oc_p,
                )
                params.append(val)
    return dist_name, tuple(params)


def _render_fit_plot(obs_data, result):
    """Render the f(T) + residuals plot for a fit result."""
    _ax, _ay, _al = _theme_parts()
    pal = obs_data["pal"]
    t_full = obs_data["t_full"]
    t_dots, f_dots, e_dots = obs_data["t_dots"], obs_data["f_dots"], obs_data["e_dots"]
    raw_frac = obs_data["raw_frac"]

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.75, 0.25], vertical_spacing=0.04,
    )

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

    fig.add_trace(go.Scatter(
        x=result["t_arr"], y=result["f_curve"], mode="lines",
        line=dict(color=COLOR_BINARY, width=2.5),
        name=f"Model (f={result['f_bin']:.3f}, χ²={result['chi2_red']:.2f})",
    ), row=1, col=1)

    ann_text = (
        f"<b>f_bin = {result['f_bin']:.4f}</b><br>"
        f"Mode: {result.get('mode', 'Parametric')}<br>"
        f"χ²_red = {result['chi2_red']:.3f}"
    )
    fig.add_annotation(
        x=0.02, y=0.05, xref="x domain", yref="y domain",
        text=ann_text, showarrow=False,
        **_ann(pal), row=1, col=1,
    )

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
        "title": dict(text="Model Fit: Binary Fraction vs ΔRV Threshold"),
        "legend": {**_al, "x": 0.98, "y": 0.98, "xanchor": "right",
                   "font": dict(size=10)},
        "height": 650,
    })
    _tf = dict(family='Times New Roman, serif', size=13, color='black')
    fig.update_yaxes(title_text="Binary fraction", title_font=_tf, row=1, col=1, **{
        k: v for k, v in _ay.items() if k != "title"})
    fig.update_yaxes(title_text="(Obs−Model)/σ", title_font=_tf, row=2, col=1, **{
        k: v for k, v in _ay.items() if k != "title"})
    fig.update_xaxes(title_text="ΔRV threshold (km/s)", title_font=_tf, row=2, col=1, **{
        k: v for k, v in _ax.items() if k != "title"})

    st.plotly_chart(fig, use_container_width=True, theme=None)


def render_tab_fitting(obs_data: dict) -> None:
    """Tab B: Parametric or physics-based model fitting."""
    t_dots, f_dots, e_dots = obs_data["t_dots"], obs_data["f_dots"], obs_data["e_dots"]
    n_stars = obs_data["n_stars"]
    sm = obs_data.get('sm')
    rvm = obs_data.get('rvm_settings', {})
    fit_cfg = rvm.get('fitting', {})
    _FIT = ['rv_modeling', 'fitting']

    st.subheader("Model Fitting")
    st.caption(
        "Choose simulation mode, configure parameters, then fit the model "
        "to the observed binary fraction vs ΔRV threshold curve."
    )

    # ── Mode toggle ──
    _mode_opts = ["Parametric", "Physics-based"]
    _mode_def = fit_cfg.get("mode", "Parametric")
    _mode_idx = _mode_opts.index(_mode_def) if _mode_def in _mode_opts else 0
    _oc_mode = {}
    if sm is not None:
        _oc_mode = dict(on_change=lambda: sm.save(
            _FIT + ['mode'], value=st.session_state['rvm_fit_mode']))
    sim_mode = st.radio(
        "Simulation mode", _mode_opts, index=_mode_idx,
        horizontal=True, key="rvm_fit_mode", **_oc_mode,
    )

    if sim_mode == "Parametric":
        _render_parametric_fitting(obs_data, t_dots, f_dots, e_dots, n_stars)
    else:
        _render_physics_fitting(obs_data, t_dots, f_dots, e_dots, n_stars)

    # ── Display results (shared) ──
    result = st.session_state.get("rvm_fit_result")
    if result is None:
        st.info("Configure parameters above, then click **Run Model Fit**.")
        return

    st.markdown("---")
    st.subheader("Fit Results")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("f_bin", f"{result['f_bin']:.4f}")
    m2.metric("χ²_red", f"{result['chi2_red']:.3f}")
    m3.metric("N_dof", f"{result['ndof']}")
    m4.metric("Mode", result.get("mode", "Parametric"))

    _render_fit_plot(obs_data, result)

    st.caption(
        "Model simulates a mixed population and counts the fraction exceeding "
        "each ΔRV threshold. Best f_bin minimizes χ² against observed data."
    )

    # Parameter summary
    st.subheader("Parameter Summary")
    import pandas as pd
    rows = [
        {"Parameter": "f_bin", "Value": f"{result['f_bin']:.4f}"},
        {"Parameter": "Mode", "Value": result.get("mode", "Parametric")},
        {"Parameter": "χ²_red", "Value": f"{result['chi2_red']:.4f}"},
        {"Parameter": "N_dof", "Value": str(result['ndof'])},
        {"Parameter": "N_sim", "Value": f"{result.get('n_sim', '—')}"},
    ]

    if result.get("mode") == "Parametric":
        def _fmt(v):
            try:
                return f"{float(v):.4g}"
            except (TypeError, ValueError):
                return str(v)

        rows.append({"Parameter": "N_epochs", "Value": f"{result.get('n_epochs', '—')}"})
        rows.append({"Parameter": "Seed", "Value": f"{result.get('seed', '—')}"})

        for role, dist_key, params_key in (("Single", "single_dist", "single_params"),
                                           ("Binary", "binary_dist", "binary_params")):
            dist_name = result.get(dist_key, "—")
            params = result.get(params_key, ()) or ()
            rows.append({"Parameter": f"{role} distribution", "Value": str(dist_name)})
            labels = [pm[0] for pm in _PARAM_META.get(dist_name, [])]
            for i, v in enumerate(params):
                lbl = labels[i] if i < len(labels) else f"p{i}"
                rows.append({"Parameter": f"{role} — {lbl}", "Value": _fmt(v)})

        rows.append({"Parameter": "Single error model",
                     "Value": str(result.get('error_model_single', '—'))})
        rows.append({"Parameter": "Single σ_measure",
                     "Value": f"{result.get('sigma_measure_single', 0.0):.3f} km/s"})
        for i, v in enumerate(result.get('error_params_single', ()) or ()):
            rows.append({"Parameter": f"Single err p{i}", "Value": _fmt(v)})
        rows.append({"Parameter": "Binary error model",
                     "Value": str(result.get('error_model_binary', '—'))})
        rows.append({"Parameter": "Binary σ_measure",
                     "Value": f"{result.get('sigma_measure_binary', 0.0):.3f} km/s"})
        for i, v in enumerate(result.get('error_params_binary', ()) or ()):
            rows.append({"Parameter": f"Binary err p{i}", "Value": _fmt(v)})

    st.table(pd.DataFrame(rows))

    # Orbital histograms (physics-based mode only)
    phys_params = result.get("_phys_params")
    if result.get("mode") == "Physics-based" and phys_params is not None:
        st.markdown("---")
        st.markdown("### Binary Orbital Properties")
        try:
            diag = compute_physics_diagnostics(
                f_bin=result['f_bin'], **phys_params,
            )
            render_orbital_histograms(diag, result['f_bin'], "rvm_fit_phys")
        except Exception as exc:
            st.warning(f"Orbital diagnostics failed: {exc}")


def _render_parametric_fitting(obs_data, t_dots, f_dots, e_dots, n_stars):
    """Parametric model fitting branch."""
    sm = obs_data.get('sm')
    par_cfg = obs_data.get('rvm_settings', {}).get('fitting', {}).get('parametric', {})
    _PAR = ['rv_modeling', 'fitting', 'parametric']

    def _oc(field):
        if sm is None:
            return {}
        _k = f'rvm_fit_{field}'
        return dict(on_change=lambda k=_k, f=field, p=_PAR: sm.save(
            p + [f], value=st.session_state[k]))

    # Auto-populate from Tab A
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

    col_s, col_b = st.columns(2)
    with col_s:
        st.markdown("**Single-star RV distribution**")
        _sin_def = par_cfg.get('single_dist', 'Normal')
        single_dist, single_params = _dist_selector(
            "Single", "rvm_fit_sin",
            default_dist=_sin_def, default_params=(0.0, 5.5),
            sm=sm, settings_path=_PAR + ['sin'],
        )
    with col_b:
        st.markdown("**Binary-star RV distribution**")
        _bin_def = par_cfg.get('binary_dist', best_dist or 'Normal')
        binary_dist, binary_params = _dist_selector(
            "Binary", "rvm_fit_bin",
            default_dist=_bin_def,
            default_params=best_params,
            sm=sm, settings_path=_PAR + ['bin'],
        )

    st.markdown("**Measurement errors**")
    st.caption("Parametric distributions represent intrinsic RVs; "
               "measurement noise is added separately.")
    err = render_error_model_pair(
        "rvm_fit_par_err", sm=sm,
        settings_path=_PAR + ['errors'],
        defaults=par_cfg.get('errors', {}),
    )

    mc1, mc2, mc3, mc4 = st.columns(4)
    with mc1:
        n_sim = st.number_input(
            "N_sim", value=int(par_cfg.get('n_sim', 100_000)),
            step=10_000, key="rvm_fit_nsim", **_oc('nsim'),
        )
    with mc2:
        n_epochs = st.number_input("N_epochs",
                                   value=int(par_cfg.get('n_epochs', 6)),
                                   step=1,
                                   key="rvm_fit_nep", **_oc('nep'))
    with mc3:
        seed = st.number_input("Seed",
                               value=int(par_cfg.get('seed', 42)),
                               step=1,
                               key="rvm_fit_seed", **_oc('seed'))
    with mc4:
        optimize_fbin = st.checkbox(
            "Optimize f_bin",
            value=bool(par_cfg.get('optimize_fbin', True)),
            key="rvm_fit_opt_fbin", **_oc('opt_fbin'))
        if not optimize_fbin:
            fixed_fbin = st.number_input(
                "Fixed f_bin", 0.0, 1.0,
                float(par_cfg.get('fixed_fbin', 0.4)), 0.01,
                key="rvm_fit_fixed_fbin", **_oc('fixed_fbin'))

    run_fit = st.button("Run Model Fit", type="primary",
                        use_container_width=True, key="rvm_fit_run")
    if not run_fit:
        return

    with st.spinner("Fitting parametric model..."):
        if optimize_fbin:
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
                    error_model_single=err['type_single'],
                    error_params_single=err['params_single'],
                    sigma_measure_single=err['sigma_measure'],
                    error_model_binary=err['type_binary'],
                    error_params_binary=err['params_binary'],
                    sigma_measure_binary=err['sigma_measure_binary'],
                )
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

        t_arr, f_curve = compute_model_fraction_curve(
            dist_single=single_dist, params_single=single_params,
            dist_binary=binary_dist, params_binary=binary_params,
            f_bin=fit_fbin, n_sim=int(n_sim),
            n_epochs=int(n_epochs), seed=int(seed),
            t_max=T_MAX,
            error_model_single=err['type_single'],
            error_params_single=err['params_single'],
            sigma_measure_single=err['sigma_measure'],
            error_model_binary=err['type_binary'],
            error_params_binary=err['params_binary'],
            sigma_measure_binary=err['sigma_measure_binary'],
        )
        f_model_dots = np.interp(t_dots, t_arr, f_curve)
        residuals = (f_dots - f_model_dots) / e_dots
        chi2 = float(np.sum(residuals ** 2))
        ndof = max(1, len(t_dots) - (1 if optimize_fbin else 0))

        st.session_state["rvm_fit_result"] = dict(
            t_arr=t_arr, f_curve=f_curve,
            f_bin=fit_fbin, mode="Parametric",
            single_dist=single_dist, single_params=single_params,
            binary_dist=binary_dist, binary_params=binary_params,
            chi2_red=chi2 / ndof, ndof=ndof,
            residuals=residuals, f_model_dots=f_model_dots,
            n_sim=int(n_sim), n_epochs=int(n_epochs), seed=int(seed),
            error_model_single=err['type_single'],
            error_params_single=err['params_single'],
            sigma_measure_single=err['sigma_measure'],
            error_model_binary=err['type_binary'],
            error_params_binary=err['params_binary'],
            sigma_measure_binary=err['sigma_measure_binary'],
        )


def _render_physics_fitting(obs_data, t_dots, f_dots, e_dots, n_stars):
    """Physics-based model fitting branch."""
    sm = obs_data.get('sm')
    phys_cfg = obs_data.get('rvm_settings', {}).get('fitting', {}).get('physics', {})
    _PHY = ['rv_modeling', 'fitting', 'physics']
    cadence_tuples = obs_data["cadence_tuples"]
    n_cadence = obs_data["n_cadence_stars"]

    def _oc(field):
        if sm is None:
            return {}
        _k = f'rvm_fit_phys_{field}'
        return dict(on_change=lambda k=_k, f=field, p=_PHY: sm.save(
            p + [f], value=st.session_state[k]))

    st.info(f"Using real observation cadences from {n_cadence} WR stars. "
            f"Binary RVs from orbital simulation (Kepler mechanics).")

    # sigma_single + n_sets + seed
    rc1, rc2, rc3 = st.columns(3)
    with rc1:
        sigma_single = st.number_input(
            "σ_single (km/s)",
            value=float(phys_cfg.get('sigma_single', 15.0)), step=0.5,
            key="rvm_fit_phys_sigma_s", **_oc('sigma_s'))
    with rc2:
        n_sets = st.number_input(
            "N_sets (×25 stars)",
            value=int(phys_cfg.get('n_sets', 50)), step=10,
            key="rvm_fit_phys_nsets", **_oc('nsets'),
        )
    with rc3:
        seed = st.number_input("Seed",
                               value=int(phys_cfg.get('seed', 42)),
                               step=1,
                               key="rvm_fit_phys_seed", **_oc('seed'))

    # Error models
    st.markdown("#### RV Error Models")
    err = render_error_model_pair(
        "rvm_fit_phys", sm=sm,
        settings_path=_PHY + ['error'],
        defaults=phys_cfg.get('error', {}),
    )

    # Orbital params
    st.markdown("#### Orbital Parameters")
    orb = render_orbital_params(
        "rvm_fit_phys", sm=sm,
        settings_path=_PHY + ['orbital'],
        defaults=phys_cfg.get('orbital', {}),
    )

    # f_bin optimization control
    oc1, oc2 = st.columns(2)
    with oc1:
        optimize_fbin = st.checkbox(
            "Optimize f_bin",
            value=bool(phys_cfg.get('optimize_fbin', True)),
            key="rvm_fit_phys_opt_fbin", **_oc('opt_fbin'))
    with oc2:
        if not optimize_fbin:
            fixed_fbin = st.number_input(
                "Fixed f_bin", 0.0, 1.0,
                float(phys_cfg.get('fixed_fbin', 0.4)), 0.01,
                key="rvm_fit_phys_fixed_fbin", **_oc('fixed_fbin'))

    run_fit = st.button("Run Physics Fit", type="primary",
                        use_container_width=True, key="rvm_fit_phys_run")
    if not run_fit:
        return

    with st.spinner("Physics-based fitting (this may take a moment)..."):
        if optimize_fbin:
            best_chi2 = float("inf")
            best_fb = 0.4
            fbin_grid = np.linspace(0.01, 0.99, 49)
            progress = st.progress(0.0, text="Scanning f_bin (physics-based)...")
            for idx, fb in enumerate(fbin_grid):
                t_arr, f_curve = compute_physics_fraction_curve(
                    f_bin=float(fb), pi=orb['pi'],
                    n_sets=int(n_sets), seed=int(seed),
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
                    q_model=orb['q_model'], q_min=orb['q_min'],
                    q_max=orb['q_max'], q_flipped=orb['q_flipped'],
                    mass_primary_fixed=orb['mass_primary_fixed'],
                    weight_A=orb['weight_A'], dist_A=orb['dist_A'],
                    mu_A=orb['mu_A'], sigma_A=orb['sigma_A'],
                    dist_B=orb['dist_B'], mu_B=orb['mu_B'],
                    sigma_B=orb['sigma_B'],
                    langer_q_mu=orb['langer_q_mu'],
                    langer_q_sigma=orb['langer_q_sigma'],
                    cadence_tuples=cadence_tuples,
                    t_max=T_MAX,
                )
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

        # Final run with best f_bin
        t_arr, f_curve = compute_physics_fraction_curve(
            f_bin=fit_fbin, pi=orb['pi'],
            n_sets=int(n_sets), seed=int(seed),
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
            q_model=orb['q_model'], q_min=orb['q_min'],
            q_max=orb['q_max'], q_flipped=orb['q_flipped'],
            mass_primary_fixed=orb['mass_primary_fixed'],
            weight_A=orb['weight_A'], dist_A=orb['dist_A'],
            mu_A=orb['mu_A'], sigma_A=orb['sigma_A'],
            dist_B=orb['dist_B'], mu_B=orb['mu_B'],
            sigma_B=orb['sigma_B'],
            langer_q_mu=orb['langer_q_mu'],
            langer_q_sigma=orb['langer_q_sigma'],
            cadence_tuples=cadence_tuples,
            t_max=T_MAX,
        )
        f_model_dots = np.interp(t_dots, t_arr, f_curve)
        residuals = (f_dots - f_model_dots) / e_dots
        chi2 = float(np.sum(residuals ** 2))
        ndof = max(1, len(t_dots) - (1 if optimize_fbin else 0))

        # Store diagnostic params for histogram rendering after fit
        _phys_params = dict(
            pi=orb['pi'], n_sets=int(n_sets), seed=int(seed),
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
            q_model=orb['q_model'], q_min=orb['q_min'],
            q_max=orb['q_max'], q_flipped=orb['q_flipped'],
            mass_primary_fixed=orb['mass_primary_fixed'],
            weight_A=orb['weight_A'], dist_A=orb['dist_A'],
            mu_A=orb['mu_A'], sigma_A=orb['sigma_A'],
            dist_B=orb['dist_B'], mu_B=orb['mu_B'],
            sigma_B=orb['sigma_B'],
            langer_q_mu=orb['langer_q_mu'],
            langer_q_sigma=orb['langer_q_sigma'],
            cadence_tuples=cadence_tuples,
        )

        st.session_state["rvm_fit_result"] = dict(
            t_arr=t_arr, f_curve=f_curve,
            f_bin=fit_fbin, mode="Physics-based",
            chi2_red=chi2 / ndof, ndof=ndof,
            residuals=residuals, f_model_dots=f_model_dots,
            n_sim=int(n_sets) * n_cadence,
            _phys_params=_phys_params,
        )
