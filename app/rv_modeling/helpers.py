"""rv_modeling/helpers.py — Constants and small layout helpers."""
from __future__ import annotations

import math
import numpy as np

from shared import PLOTLY_THEME

# ── Constants ────────────────────────────────────────────────────────────
NSIGMA_DETECT: float = 4.0
T_MAX: int = 301
COLOR_GAUSS = "#9B59B6"


def _theme_parts() -> tuple:
    """Return (xaxis_base, yaxis_base, legend_base) from PLOTLY_THEME."""
    return (
        PLOTLY_THEME.get("xaxis", {}),
        PLOTLY_THEME.get("yaxis", {}),
        PLOTLY_THEME.get("legend", {}),
    )


BIN_METHODS = [
    "Auto (Freedman-Diaconis)", "Auto (Sturges)", "Auto (Scott)",
    "Auto (sqrt N)", "Auto (Plotly)", "Manual",
]


def auto_nbins(data, method: str = "freedman-diaconis") -> int | None:
    """Compute histogram bin count using *method*. Returns None for Plotly default."""
    n = len(data)
    if n < 2:
        return 10
    rng = float(np.ptp(data))
    if rng == 0:
        return 10
    method = method.lower()
    if "plotly" in method:
        return None
    if "sturges" in method:
        return int(math.ceil(math.log2(n))) + 1
    if "scott" in method:
        s = float(np.std(data, ddof=1))
        if s == 0:
            return 10
        h = 3.5 * s * n ** (-1 / 3)
        return max(1, int(math.ceil(rng / h)))
    if "sqrt" in method:
        return max(1, int(math.ceil(math.sqrt(n))))
    # default: Freedman-Diaconis
    q75, q25 = np.percentile(data, [75, 25])
    iqr = float(q75 - q25)
    if iqr == 0:
        return 10
    h = 2.0 * iqr * n ** (-1 / 3)
    return max(1, int(math.ceil(rng / h)))


def resolve_nbins(data, obs_data: dict) -> int | None:
    """Return nbins from obs_data bin_method / manual_bins."""
    method = obs_data.get("bin_method", "Auto (Freedman-Diaconis)")
    if method == "Manual":
        return obs_data.get("manual_bins", 50)
    return auto_nbins(data, method)


def _ann(pal: dict) -> dict:
    """Annotation styling respecting palette."""
    return dict(
        bgcolor=pal["annotation_bg"],
        bordercolor=pal["annotation_border"],
        font=dict(color=pal["annotation_font"], size=11),
        borderwidth=1,
    )


# ── Error-model UI (self-contained, mirrors bc/extras.py pattern) ─────────

_RVE_DISTRIBUTIONS: dict[str, str] = {
    'Normal': 'norm',
    'Log-normal': 'lognorm',
    'Gamma': 'gamma',
    'Weibull': 'weibull_min',
    'Exponential': 'expon',
    'Flat (uniform)': 'uniform',
}

_RVE_PARAM_META: dict[str, list] = {
    'Normal': [('μ (loc)', 2.0, -50.0, 50.0, 0.01),
               ('σ (scale)', 1.0, 0.01, 50.0, 0.01)],
    'Log-normal': [('s (shape)', 0.5, 0.01, 5.0, 0.01),
                   ('loc', 0.0, -50.0, 50.0, 0.01),
                   ('scale', 1.0, 0.01, 50.0, 0.01)],
    'Gamma': [('a (shape)', 2.0, 0.01, 20.0, 0.01),
              ('loc', 0.0, -50.0, 50.0, 0.01),
              ('scale', 1.0, 0.01, 50.0, 0.01)],
    'Weibull': [('c (shape)', 1.5, 0.01, 10.0, 0.01),
                ('loc', 0.0, -50.0, 50.0, 0.01),
                ('scale', 1.0, 0.01, 50.0, 0.01)],
    'Exponential': [('loc', 0.0, -50.0, 50.0, 0.01),
                    ('scale', 1.0, 0.01, 50.0, 0.01)],
    'Flat (uniform)': [('loc (start)', 0.0, -50.0, 50.0, 0.01),
                       ('scale (width)', 5.0, 0.01, 100.0, 0.01)],
}


def render_error_model_one(label: str, key_prefix: str,
                           sm=None, settings_path=None,
                           defaults=None) -> dict:
    """Render one error-model selector. Returns {type, sigma_measure, params}.

    When *sm* (SettingsManager) is provided, widget defaults are read from
    *defaults* dict and every change is persisted to *settings_path* in
    user_settings.json.
    """
    import scipy.stats as sp_stats
    import streamlit as st

    if defaults is None:
        defaults = {}
    _sp = settings_path or []

    options = ['Fixed', 'Normal', 'Log-normal', 'Gamma',
               'Weibull', 'Exponential', 'Flat (uniform)']
    _def_type = defaults.get('err_type', 'Fixed')
    _def_idx = options.index(_def_type) if _def_type in options else 0

    _oc_type = {}
    if sm is not None:
        _k_type = f'{key_prefix}_err_type'
        _oc_type = dict(on_change=lambda k=_k_type, p=_sp: sm.save(
            p + ['err_type'], value=st.session_state[k]))

    err_model = st.selectbox(
        label, options, index=_def_idx, key=f'{key_prefix}_err_type',
        help='Fixed = constant σ_measure. Distribution = per-epoch error drawn from model.',
        **_oc_type,
    )

    if err_model == 'Fixed':
        _def_sigma = float(defaults.get('sigma_meas', 1.622))
        _oc_sig = {}
        if sm is not None:
            _k_sig = f'{key_prefix}_sigma_meas'
            _oc_sig = dict(on_change=lambda k=_k_sig, p=_sp: sm.save(
                p + ['sigma_meas'], value=st.session_state[k]))
        sigma = st.number_input(
            'σ_measure (km/s)', 0.001, 20.0, _def_sigma, 0.001,
            format='%.3f', key=f'{key_prefix}_sigma_meas',
            **_oc_sig,
        )
        return {'type': 'fixed', 'sigma_measure': float(sigma), 'params': ()}

    pmeta = _RVE_PARAM_META.get(err_model, [])
    params: list[float] = []
    if pmeta:
        cols = st.columns(len(pmeta))
        saved_errp = defaults.get('errp', {})
        for i, (lbl, default, pmin, pmax, step) in enumerate(pmeta):
            with cols[i]:
                _init = float(saved_errp.get(str(i), default))
                _oc_p = {}
                if sm is not None:
                    _k_p = f'{key_prefix}_errp_{i}'
                    _oc_p = dict(on_change=lambda k=_k_p, p=_sp, idx=str(i): sm.save(
                        p + ['errp', idx], value=st.session_state[k]))
                val = st.number_input(
                    lbl, min_value=pmin, max_value=pmax,
                    value=float(st.session_state.get(f'{key_prefix}_errp_{i}', _init)),
                    step=step, format='%.4f', key=f'{key_prefix}_errp_{i}',
                    **_oc_p,
                )
                params.append(val)

    scipy_name = _RVE_DISTRIBUTIONS.get(err_model, 'norm')
    try:
        dist = getattr(sp_stats, scipy_name)
        mean_val = float(dist.mean(*params))
        if not np.isfinite(mean_val) or mean_val <= 0:
            mean_val = 1.622
    except Exception:
        mean_val = 1.622

    st.caption(f'Distribution mean = {mean_val:.3f} km/s (per-epoch draws)')
    return {'type': err_model, 'sigma_measure': mean_val, 'params': tuple(params)}


def render_error_model_pair(key_prefix: str,
                            sm=None, settings_path=None,
                            defaults=None) -> dict:
    """Render two-column error-model selectors (Singles | Binaries).

    Returns dict with keys:
        type_single, sigma_measure, params_single,
        type_binary, sigma_measure_binary, params_binary
    """
    import streamlit as st

    if defaults is None:
        defaults = {}
    _sp = settings_path or []

    c1, c2 = st.columns(2)
    with c1:
        st.markdown('**Singles error model**')
        single = render_error_model_one(
            'Error model (singles)', f'{key_prefix}_single',
            sm=sm, settings_path=_sp + ['single'] if sm else None,
            defaults=defaults.get('single', {}),
        )
    with c2:
        st.markdown('**Binaries error model**')
        binary = render_error_model_one(
            'Error model (binaries)', f'{key_prefix}_binary',
            sm=sm, settings_path=_sp + ['binary'] if sm else None,
            defaults=defaults.get('binary', {}),
        )
    return {
        'type_single': single['type'],
        'sigma_measure': single['sigma_measure'],
        'params_single': single['params'],
        'type_binary': binary['type'],
        'sigma_measure_binary': binary['sigma_measure'],
        'params_binary': binary['params'],
    }


def render_orbital_params(key_prefix: str,
                          sm=None, settings_path=None,
                          defaults=None) -> dict:
    """Render always-visible orbital parameter controls. Returns param dict.

    When *sm* (SettingsManager) is provided, widget defaults are read from
    *defaults* dict and every change is persisted via *settings_path*.
    """
    import streamlit as st

    if defaults is None:
        defaults = {}
    _sp = settings_path or []

    def _oc(field):
        """Build on_change kwargs for a widget that saves *field*."""
        if sm is None:
            return {}
        _k = f'{key_prefix}_{field}'
        return dict(on_change=lambda k=_k, f=field, p=_sp: sm.save(
            p + [f], value=st.session_state[k]))

    # Row 1: Period model, pi, logP range
    _pm_opts = ['powerlaw', 'langer2020']
    _pm_def = defaults.get('period_model', 'powerlaw')
    _pm_idx = _pm_opts.index(_pm_def) if _pm_def in _pm_opts else 0

    r1c1, r1c2, r1c3, r1c4 = st.columns(4)
    with r1c1:
        period_model = st.selectbox(
            'Period model', _pm_opts, index=_pm_idx,
            key=f'{key_prefix}_period_model', **_oc('period_model'),
        )
    with r1c2:
        pi = st.number_input('π (power-law index)',
                             value=float(defaults.get('pi', 0.0)), step=0.1,
                             key=f'{key_prefix}_pi', **_oc('pi'))
    with r1c3:
        logP_min = st.number_input('logP_min', 0.01, 6.0,
                                    float(defaults.get('logP_min', 0.15)), 0.05,
                                    format='%.2f', key=f'{key_prefix}_logPmin',
                                    **_oc('logPmin'))
    with r1c4:
        logP_max = st.number_input('logP_max', 0.5, 8.0,
                                    float(defaults.get('logP_max', 4.0)), 0.1,
                                    format='%.1f', key=f'{key_prefix}_logPmax',
                                    **_oc('logPmax'))

    # Row 2: Eccentricity, mass ratio, primary mass
    _em_opts = ['flat', 'zero']
    _em_def = defaults.get('e_model', 'flat')
    _em_idx = _em_opts.index(_em_def) if _em_def in _em_opts else 0

    _qm_opts = ['flat', 'langer', 'lognormal', 'reflected_lognormal', 'empirical']
    _qm_def = defaults.get('q_model', 'flat')
    _qm_idx = _qm_opts.index(_qm_def) if _qm_def in _qm_opts else 0

    r2c1, r2c2, r2c3, r2c4, r2c5 = st.columns(5)
    with r2c1:
        e_model = st.selectbox('e model', _em_opts, index=_em_idx,
                               key=f'{key_prefix}_e_model', **_oc('e_model'))
    with r2c2:
        e_max = st.number_input('e_max', 0.0, 0.99,
                                 float(defaults.get('e_max', 0.9)), 0.05,
                                 format='%.2f', key=f'{key_prefix}_e_max',
                                 **_oc('e_max'))
    with r2c3:
        q_model = st.selectbox('q model', _qm_opts, index=_qm_idx,
                               key=f'{key_prefix}_q_model', **_oc('q_model'))
    with r2c4:
        q_min = st.number_input('q_min', 0.01, 5.0,
                                 float(defaults.get('q_min', 0.1)), 0.05,
                                 format='%.2f', key=f'{key_prefix}_q_min',
                                 **_oc('q_min'))
    with r2c5:
        q_max = st.number_input('q_max', 0.1, 10.0,
                                 float(defaults.get('q_max', 2.0)), 0.1,
                                 format='%.1f', key=f'{key_prefix}_q_max',
                                 **_oc('q_max'))

    r3c1, r3c2 = st.columns(2)
    with r3c1:
        mass_primary = st.number_input('M₁ (M☉)', 1.0, 100.0,
                                        float(defaults.get('mass1', 10.0)), 1.0,
                                        key=f'{key_prefix}_mass1', **_oc('mass1'))
    with r3c2:
        q_flipped = st.checkbox('q flipped (M₂ = M₁/q)',
                                value=bool(defaults.get('q_flipped', False)),
                                key=f'{key_prefix}_q_flipped', **_oc('q_flipped'))

    result = dict(
        period_model=period_model, pi=float(pi),
        logP_min=float(logP_min), logP_max=float(logP_max),
        e_model=e_model, e_max=float(e_max),
        q_model=q_model, q_min=float(q_min), q_max=float(q_max),
        q_flipped=bool(q_flipped),
        mass_primary_fixed=float(mass_primary),
    )

    # Langer-specific params (Row 3)
    langer_q_mu = float(defaults.get('lqmu', 0.7))
    langer_q_sigma = float(defaults.get('lqsig', 0.2))
    weight_A = float(defaults.get('wA', 0.3))
    dist_A = defaults.get('distA', 'gaussian')
    mu_A = float(defaults.get('muA', 0.80))
    sigma_A = float(defaults.get('sigA', 0.35))
    dist_B = defaults.get('distB', 'reflected_lognormal')
    mu_B = float(defaults.get('muB', 2.0))
    sigma_B = float(defaults.get('sigB', 0.45))

    if period_model == 'langer2020':
        st.markdown('**Langer 2020 parameters**')
        lc1, lc2, lc3 = st.columns(3)
        with lc1:
            weight_A = st.number_input('weight_A (Case A fraction)',
                                       value=float(defaults.get('wA', 0.3)),
                                       step=0.05,
                                       key=f'{key_prefix}_wA', **_oc('wA'))
        with lc2:
            langer_q_mu = st.number_input('q μ (Langer)', 0.1, 2.0,
                                           float(defaults.get('lqmu', 0.7)), 0.05,
                                           format='%.2f', key=f'{key_prefix}_lqmu',
                                           **_oc('lqmu'))
        with lc3:
            langer_q_sigma = st.number_input('q σ (Langer)', 0.01, 1.0,
                                              float(defaults.get('lqsig', 0.2)), 0.01,
                                              format='%.2f', key=f'{key_prefix}_lqsig',
                                              **_oc('lqsig'))

        _dA_opts = ['gaussian', 'lognormal', 'reflected_lognormal', 'empirical']
        _dA_def = defaults.get('distA', 'gaussian')
        _dA_idx = _dA_opts.index(_dA_def) if _dA_def in _dA_opts else 0

        lc4, lc5, lc6 = st.columns(3)
        with lc4:
            dist_A = st.selectbox('dist_A', _dA_opts, index=_dA_idx,
                                  key=f'{key_prefix}_distA', **_oc('distA'))
        with lc5:
            mu_A = st.number_input('μ_A', 0.01, 5.0,
                                    float(defaults.get('muA', 0.80)), 0.05,
                                    format='%.2f', key=f'{key_prefix}_muA',
                                    **_oc('muA'))
        with lc6:
            sigma_A = st.number_input('σ_A', 0.01, 2.0,
                                       float(defaults.get('sigA', 0.35)), 0.05,
                                       format='%.2f', key=f'{key_prefix}_sigA',
                                       **_oc('sigA'))

        _dB_opts = ['gaussian', 'lognormal', 'reflected_lognormal', 'empirical']
        _dB_def = defaults.get('distB', 'reflected_lognormal')
        _dB_idx = _dB_opts.index(_dB_def) if _dB_def in _dB_opts else 0

        lc7, lc8, lc9 = st.columns(3)
        with lc7:
            dist_B = st.selectbox('dist_B', _dB_opts, index=_dB_idx,
                                  key=f'{key_prefix}_distB', **_oc('distB'))
        with lc8:
            mu_B = st.number_input('μ_B', 0.01, 5.0,
                                    float(defaults.get('muB', 2.0)), 0.1,
                                    format='%.2f', key=f'{key_prefix}_muB',
                                    **_oc('muB'))
        with lc9:
            sigma_B = st.number_input('σ_B', 0.01, 2.0,
                                       float(defaults.get('sigB', 0.45)), 0.05,
                                       format='%.2f', key=f'{key_prefix}_sigB',
                                       **_oc('sigB'))

    result.update(
        weight_A=float(weight_A), dist_A=dist_A,
        mu_A=float(mu_A), sigma_A=float(sigma_A),
        dist_B=dist_B, mu_B=float(mu_B), sigma_B=float(sigma_B),
        langer_q_mu=float(langer_q_mu), langer_q_sigma=float(langer_q_sigma),
    )
    return result


# ── Orbital parameter histogram grid ──────────────────────────────────

_CLR_ALL = '#52B788'       # green — all binaries
_CLR_DETECTED = '#E25A53'  # tomato — detected
_CLR_MISSED = '#F5A623'    # amber — missed

_PARAM_TITLES = [
    'log₁₀(P / days)', 'Eccentricity', 'Mass ratio q',
    'K₁ (km/s)', 'M₁ (M⊙)', 'M₂ (M⊙)',
    'Inclination (°)', 'ω (°)', 'T₀ (rad)',
]
_X_LABELS = [
    'log₁₀(P / days)', 'e', 'q = M₂/M₁',
    'K₁ (km/s)', 'M₁ (M⊙)', 'M₂ (M⊙)',
    'i (degrees)', 'ω (degrees)', 'T₀ (rad)',
]


def render_orbital_histograms(
    sim_dict: dict, f_bin: float, key_prefix: str,
    threshold_dRV: float = 45.5,
) -> None:
    """Render 3×3 orbital parameter histogram grid from simulate_with_params output."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import streamlit as st

    if sim_dict is None or sim_dict.get('P_days') is None:
        st.info("No orbital diagnostics available.")
        return

    idx_bin = sim_dict['idx_bin']
    if idx_bin.size == 0:
        st.info("No binaries in simulation (f_bin may be too low).")
        return

    delta_rv = sim_dict['delta_rv']
    n_bins = 30

    # Detected vs missed masks (among binaries)
    bin_drv = delta_rv[idx_bin]
    detected_mask = bin_drv > threshold_dRV
    missed_mask = ~detected_mask

    def _safe(arr, mask):
        return arr[mask] if arr.size > 0 else np.array([])

    P_all = sim_dict['P_days']
    e_all = sim_dict['e']
    q_all = sim_dict['q']
    K1_all = sim_dict['K1']
    M1_all = sim_dict['M1']
    i_all = np.degrees(sim_dict['i_rad'])
    omega_all = np.degrees(sim_dict.get('omega', np.array([])))
    T0_all = sim_dict.get('T0', np.array([]))
    M2_all = q_all * M1_all if q_all.size > 0 else np.array([])

    # View mode
    view = st.radio(
        'Show populations',
        ['All binaries (combined)', 'Compare detected vs missed',
         'Detected only', 'Missed only'],
        horizontal=True, key=f'{key_prefix}_hist_view',
    )

    fig = make_subplots(rows=3, cols=3, subplot_titles=_PARAM_TITLES,
                        horizontal_spacing=0.08, vertical_spacing=0.10)

    def _add_hist(row, col, data, name, color, show_legend):
        if data.size == 0:
            return
        d_min, d_max = float(data.min()), float(data.max())
        bin_sz = (d_max - d_min) / n_bins if d_max > d_min else 1.0
        fig.add_trace(go.Histogram(
            x=data,
            xbins=dict(start=d_min, end=d_max + bin_sz * 0.01, size=bin_sz),
            histnorm='probability density',
            name=name, marker_color=color, opacity=0.6,
            legendgroup=name, showlegend=show_legend,
        ), row=row, col=col)

    def _pos(idx):
        return (idx // 3 + 1, idx % 3 + 1)

    def _build_data_list(mask=None):
        if mask is None:
            P, e, q, K1, M1, M2, i = P_all, e_all, q_all, K1_all, M1_all, M2_all, i_all
            omega, T0 = omega_all, T0_all
        else:
            P = _safe(P_all, mask)
            e = _safe(e_all, mask)
            q = _safe(q_all, mask)
            K1 = _safe(K1_all, mask)
            M1 = _safe(M1_all, mask)
            M2 = _safe(M2_all, mask)
            i = np.degrees(_safe(sim_dict['i_rad'], mask))
            omega = np.degrees(_safe(sim_dict.get('omega', np.array([])), mask))
            T0 = _safe(sim_dict.get('T0', np.array([])), mask)

        logP = np.log10(P) if P.size > 0 else P
        return [logP, e, q, K1, M1, M2, i, omega, T0]

    if view == 'All binaries (combined)':
        data_list = _build_data_list()
        for pi, d in enumerate(data_list):
            r, c = _pos(pi)
            _add_hist(r, c, d, 'All binaries', _CLR_ALL, pi == 0)
    else:
        if view in ('Compare detected vs missed', 'Detected only'):
            det_data = _build_data_list(detected_mask)
            for pi, d in enumerate(det_data):
                r, c = _pos(pi)
                _add_hist(r, c, d, 'Detected', _CLR_DETECTED, pi == 0)
        if view in ('Compare detected vs missed', 'Missed only'):
            mis_data = _build_data_list(missed_mask)
            for pi, d in enumerate(mis_data):
                r, c = _pos(pi)
                _add_hist(r, c, d, 'Missed', _CLR_MISSED, pi == 0)

    fig.update_layout(**{
        **PLOTLY_THEME,
        'barmode': 'overlay',
        'height': 850,
        'margin': dict(l=40, r=20, t=40, b=60),
        'legend': dict(orientation='h', yanchor='bottom', y=1.04,
                       xanchor='center', x=0.5),
    })
    for pi in range(9):
        r, c = _pos(pi)
        fig.update_xaxes(title_text=_X_LABELS[pi], showgrid=False, row=r, col=c)
        fig.update_yaxes(showgrid=False, row=r, col=c)
    for row_i in range(1, 4):
        fig.update_yaxes(title_text='Prob. density', row=row_i, col=1)

    st.plotly_chart(fig, use_container_width=True, key=f'{key_prefix}_orb_hist')

    n_det = int(np.sum(detected_mask))
    n_mis = int(np.sum(missed_mask))
    st.caption(
        f'Orbital parameter distributions of {idx_bin.size} simulated binaries '
        f'(f_bin={f_bin:.3f}). **Detected**: {n_det} with ΔRV > {threshold_dRV} km/s. '
        f'**Missed**: {n_mis} below threshold.'
    )
