"""bc.params — Orbital parameter rendering for bias correction tabs."""
from __future__ import annotations

import os
import sys

import numpy as np
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from shared import settings_hash, cached_load_observed_delta_rvs, PLOTLY_THEME

def _render_orbital_params_dsilva(
    p: str, sec: str, sm, orb: dict, gcfg: dict,
) -> dict:
    """Render Dsilva-style orbital params (logP, eccentricity, mass, q).

    Parameters
    ----------
    p : str
        Unique prefix for session-state keys.
    sec : str
        Settings section key (e.g. 'grid_dsilva', 'grid_cadence_dsilva').
    sm : SettingsManager
        For persisting changes.
    orb : dict
        Orbital sub-dict from settings (gcfg.get('orbital', {})).
    gcfg : dict
        Grid config section from settings.

    Returns
    -------
    dict with keys: logP_min, logP_max, e_model, e_max, mass_model,
        mass_fixed, mass_range, q_model, q_min, q_max, lq_mu, lq_sig
    """
    # Determine whether orbital settings are nested under 'orbital' key
    _orb_prefix = [sec, 'orbital'] if 'orbital' in gcfg else [sec]
    # For dsilva tabs, orbital params are always nested
    _orb_prefix = [sec, 'orbital']

    st.caption('Parameters of the Kepler orbit randomization in the simulation.')

    # Period range
    _lp1, _lp2 = st.columns(2)
    logP_min_val = _lp1.number_input(
        'log\u2081\u2080(P/days) min', 0.01, 10.0,
        float(orb.get('logP_min', gcfg.get('logP_min', 0.15))), 0.01,
        key=f'{p}_logP_min',
        on_change=lambda: sm.save(_orb_prefix + ['logP_min'],
                                  value=st.session_state[f'{p}_logP_min']))
    logP_max_val = _lp2.number_input(
        'log\u2081\u2080(P/days) max', 0.1, 10.0,
        float(orb.get('logP_max', gcfg.get('logP_max', 5.0))), 0.1,
        key=f'{p}_logP_max',
        on_change=lambda: sm.save(_orb_prefix + ['logP_max'],
                                  value=st.session_state[f'{p}_logP_max']))

    st.markdown('---')
    # Eccentricity + Primary mass side by side
    _em1, _em2 = st.columns(2)
    with _em1:
        e_model = st.selectbox(
            'Eccentricity model', ['flat', 'zero'],
            index=['flat', 'zero'].index(orb.get('e_model', 'flat')),
            key=f'{p}_e_model',
            on_change=lambda: sm.save(_orb_prefix + ['e_model'],
                                      value=st.session_state[f'{p}_e_model']))
        if e_model == 'flat':
            e_max = st.number_input(
                'e_max', 0.0, 0.99, float(orb.get('e_max', 0.9)), 0.05,
                key=f'{p}_e_max',
                on_change=lambda: sm.save(_orb_prefix + ['e_max'],
                                          value=st.session_state[f'{p}_e_max']))
        else:
            e_max = 0.0
    with _em2:
        mass_model = st.selectbox(
            'Primary mass model', ['fixed', 'uniform'],
            index=['fixed', 'uniform'].index(orb.get('mass_primary_model', 'fixed')),
            key=f'{p}_mass_model',
            on_change=lambda: sm.save(_orb_prefix + ['mass_primary_model'],
                                      value=st.session_state[f'{p}_mass_model']))
        if mass_model == 'fixed':
            mass_fixed = st.number_input(
                'M\u2081 (M\u2609)', 1.0, 200.0,
                float(orb.get('mass_primary_fixed', 10.0)), 1.0,
                key=f'{p}_mass_fixed',
                on_change=lambda: sm.save(_orb_prefix + ['mass_primary_fixed'],
                                          value=st.session_state[f'{p}_mass_fixed']))
            mass_range = (float(mass_fixed), float(mass_fixed))
        else:
            mass_fixed = 10.0
            _mr = orb.get('mass_primary_range', [10.0, 20.0])
            mass_min_v = st.number_input(
                'M\u2081 min', 1.0, 200.0, float(_mr[0]), 1.0,
                key=f'{p}_mass_min',
                on_change=lambda: sm.save(_orb_prefix + ['mass_primary_range'],
                                          value=[st.session_state[f'{p}_mass_min'],
                                                 st.session_state.get(f'{p}_mass_max', _mr[1])]))
            mass_max_v = st.number_input(
                'M\u2081 max', 1.0, 200.0, float(_mr[1]), 1.0,
                key=f'{p}_mass_max',
                on_change=lambda: sm.save(_orb_prefix + ['mass_primary_range'],
                                          value=[st.session_state.get(f'{p}_mass_min', _mr[0]),
                                                 st.session_state[f'{p}_mass_max']]))
            mass_range = (float(mass_min_v), float(mass_max_v))

    st.markdown('---')
    # Mass ratio q = M2/M1
    q_model = st.selectbox(
        'Mass ratio q model', ['flat', 'langer'],
        index=['flat', 'langer'].index(orb.get('q_model', 'flat')),
        key=f'{p}_q_model',
        on_change=lambda: sm.save(_orb_prefix + ['q_model'],
                                  value=st.session_state[f'{p}_q_model']))
    _qr = orb.get('q_range', [0.1, 2.0])
    qc1, qc2 = st.columns(2)
    q_min_v = qc1.number_input(
        'q min', 0.01, 10.0, float(_qr[0]), 0.01,
        key=f'{p}_q_min',
        on_change=lambda: sm.save(_orb_prefix + ['q_range'],
                                  value=[st.session_state[f'{p}_q_min'],
                                         st.session_state.get(f'{p}_q_max', _qr[1])]))
    q_max_v = qc2.number_input(
        'q max', 0.01, 10.0, float(_qr[1]), 0.1,
        key=f'{p}_q_max',
        on_change=lambda: sm.save(_orb_prefix + ['q_range'],
                                  value=[st.session_state.get(f'{p}_q_min', _qr[0]),
                                         st.session_state[f'{p}_q_max']]))
    if q_model == 'langer':
        lq_mu = st.number_input(
            'Langer q mean', 0.01, 5.0,
            float(orb.get('langer_q_mu', 0.7)), 0.05,
            key=f'{p}_lq_mu',
            on_change=lambda: sm.save(_orb_prefix + ['langer_q_mu'],
                                      value=st.session_state[f'{p}_lq_mu']))
        lq_sig = st.number_input(
            'Langer q sigma', 0.01, 5.0,
            float(orb.get('langer_q_sigma', 0.2)), 0.05,
            key=f'{p}_lq_sig',
            on_change=lambda: sm.save(_orb_prefix + ['langer_q_sigma'],
                                      value=st.session_state[f'{p}_lq_sig']))
    else:
        lq_mu = 0.7
        lq_sig = 0.2

    return dict(
        logP_min=float(logP_min_val), logP_max=float(logP_max_val),
        e_model=str(e_model), e_max=float(e_max),
        mass_model=str(mass_model), mass_fixed=float(mass_fixed),
        mass_range=mass_range,
        q_model=str(q_model), q_min=float(q_min_v), q_max=float(q_max_v),
        lq_mu=float(lq_mu), lq_sig=float(lq_sig),
    )


def _render_orbital_params_langer(
    p: str, sec: str, sm, lg_pp: dict, lg_cfg: dict,
) -> dict:
    """Render Langer-style orbital params (period components, q distribution, mass).

    Parameters
    ----------
    p : str
        Unique prefix for session-state keys.
    sec : str
        Settings section key (e.g. 'grid_langer', 'grid_cadence_langer').
    sm : SettingsManager
        For persisting changes.
    lg_pp : dict
        Langer period params sub-dict.
    lg_cfg : dict
        Grid config section from settings.

    Returns
    -------
    dict with all orbital parameter values needed for BinaryParameterConfig.
    """
    st.caption('Period distribution: two-component mixture in log\u2081\u2080(P/days), '
               'fitting the combined Langer+2020 Fig. 6 shape.')

    # --- Distribution type options (shared by both components) ---
    _pd_options = ['Gaussian', 'Log-normal', 'Reflected log-normal',
                   'Empirical (Langer Fig.)', 'Flat (uniform)']
    _pd_map = {'Gaussian': 'gaussian', 'Log-normal': 'lognormal',
               'Reflected log-normal': 'reflected_lognormal',
               'Empirical (Langer Fig.)': 'empirical',
               'Flat (uniform)': 'flat'}
    _pd_inv = {v: k for k, v in _pd_map.items()}

    def _mu_label(dist_key):
        if dist_key in ('lognormal', 'reflected_lognormal'):
            return 'mode'
        return 'mean'

    # Components 1 & 2 side-by-side
    _comp1_col, _comp2_col = st.columns(2)
    with _comp1_col:
        st.markdown('**Comp 1** (short-P)')
        _saved_dA = lg_pp.get('dist_A', 'gaussian')
        _dist_A_label = st.selectbox(
            'Distribution', _pd_options,
            index=_pd_options.index(_pd_inv.get(_saved_dA, _pd_options[0])),
            key=f'{p}_dist_A',
            on_change=lambda: sm.save(
                [sec, 'langer_period_params', 'dist_A'],
                value=_pd_map[st.session_state[f'{p}_dist_A']]))
        dist_A = _pd_map[_dist_A_label]
        if dist_A not in ('flat', 'empirical'):
            mu_A = st.number_input(
                f'\u03bc\u2081 ({_mu_label(dist_A)})', 0.01, 10.0,
                float(lg_pp.get('mu_A', 0.80)), 0.05, key=f'{p}_mu_A',
                on_change=lambda: sm.save(
                    [sec, 'langer_period_params', 'mu_A'],
                    value=st.session_state[f'{p}_mu_A']))
            sigma_A = st.number_input(
                '\u03c3\u2081', 0.01, 5.0,
                float(lg_pp.get('sigma_A', 0.35)), 0.01, key=f'{p}_sigma_A',
                on_change=lambda: sm.save(
                    [sec, 'langer_period_params', 'sigma_A'],
                    value=st.session_state[f'{p}_sigma_A']))
        else:
            mu_A = float(lg_pp.get('mu_A', 0.80))
            sigma_A = float(lg_pp.get('sigma_A', 0.35))
    with _comp2_col:
        st.markdown('**Comp 2** (long-P)')
        _saved_dB = lg_pp.get('dist_B', 'reflected_lognormal')
        _dist_B_label = st.selectbox(
            'Distribution ', _pd_options,
            index=_pd_options.index(_pd_inv.get(_saved_dB, _pd_options[2])),
            key=f'{p}_dist_B',
            on_change=lambda: sm.save(
                [sec, 'langer_period_params', 'dist_B'],
                value=_pd_map[st.session_state[f'{p}_dist_B']]))
        dist_B = _pd_map[_dist_B_label]
        if dist_B not in ('flat', 'empirical'):
            mu_B = st.number_input(
                f'\u03bc\u2082 ({_mu_label(dist_B)})', 0.01, 10.0,
                float(lg_pp.get('mu_B', 2.0)), 0.05, key=f'{p}_mu_B',
                on_change=lambda: sm.save(
                    [sec, 'langer_period_params', 'mu_B'],
                    value=st.session_state[f'{p}_mu_B']))
            sigma_B = st.number_input(
                '\u03c3\u2082', 0.01, 5.0,
                float(lg_pp.get('sigma_B', 0.45)), 0.01, key=f'{p}_sigma_B',
                on_change=lambda: sm.save(
                    [sec, 'langer_period_params', 'sigma_B'],
                    value=st.session_state[f'{p}_sigma_B']))
        else:
            mu_B = float(lg_pp.get('mu_B', 2.0))
            sigma_B = float(lg_pp.get('sigma_B', 0.45))

    # Mixture weight (full width — benefits from slider width)
    weight_A = st.slider(
        'Weight of Component 1', 0.0, 1.0,
        float(lg_pp.get('weight_A', 0.20)), 0.01, key=f'{p}_weight_A',
        on_change=lambda: sm.save(
            [sec, 'langer_period_params', 'weight_A'],
            value=st.session_state[f'{p}_weight_A']))

    st.markdown('---')
    # Period range — side by side
    _lp1, _lp2 = st.columns(2)
    logP_min = _lp1.number_input(
        'logP min', 0.01, 5.0,
        float(lg_cfg.get('logP_min', 0.5)), 0.01, key=f'{p}_logP_min',
        on_change=lambda: sm.save([sec, 'logP_min'],
                                  value=st.session_state[f'{p}_logP_min']))
    logP_max = _lp2.number_input(
        'logP max', 0.1, 10.0,
        float(lg_cfg.get('logP_max', 3.5)), 0.1, key=f'{p}_logP_max',
        on_change=lambda: sm.save([sec, 'logP_max'],
                                  value=st.session_state[f'{p}_logP_max']))

    # Eccentricity + Primary mass — side by side
    _em1, _em2 = st.columns(2)
    with _em1:
        st.markdown('**Eccentricity**')
        st.caption('Fixed at e = 0 (Langer+2020)')
    with _em2:
        mass_model = st.selectbox(
            'Primary mass model', ['fixed', 'uniform'],
            index=['fixed', 'uniform'].index(
                lg_cfg.get('mass_primary_model', 'fixed')),
            key=f'{p}_mass_model',
            on_change=lambda: sm.save([sec, 'mass_primary_model'],
                                      value=st.session_state[f'{p}_mass_model']))
        if mass_model == 'fixed':
            mass_fixed = st.number_input(
                'M\u2081 (M\u2609)', 1.0, 200.0,
                float(lg_cfg.get('mass_primary_fixed', 10.0)), 1.0,
                key=f'{p}_mass_fixed',
                on_change=lambda: sm.save([sec, 'mass_primary_fixed'],
                                          value=st.session_state[f'{p}_mass_fixed']))
            mass_range = (float(mass_fixed), float(mass_fixed))
        else:
            mass_fixed = 10.0
            _mr = lg_cfg.get('mass_primary_range', [10.0, 20.0])
            mass_min_v = st.number_input(
                'M\u2081 min', 1.0, 200.0, float(_mr[0]), 1.0,
                key=f'{p}_mass_min',
                on_change=lambda: sm.save([sec, 'mass_primary_range'],
                                          value=[st.session_state[f'{p}_mass_min'],
                                                 st.session_state.get(f'{p}_mass_max', _mr[1])]))
            mass_max_v = st.number_input(
                'M\u2081 max', 1.0, 200.0, float(_mr[1]), 1.0,
                key=f'{p}_mass_max',
                on_change=lambda: sm.save([sec, 'mass_primary_range'],
                                          value=[st.session_state.get(f'{p}_mass_min', _mr[0]),
                                                 st.session_state[f'{p}_mass_max']]))
            mass_range = (float(mass_min_v), float(mass_max_v))

    st.markdown('---')
    # Mass ratio q — distribution + range + params compact
    _q_dist_options = ['Flat (uniform)', 'Gaussian', 'Log-normal',
                       'Reflected log-normal',
                       'Empirical (Langer Fig.)']
    _q_dist_map = {'Flat (uniform)': 'flat', 'Gaussian': 'langer',
                   'Log-normal': 'lognormal',
                   'Reflected log-normal': 'reflected_lognormal',
                   'Empirical (Langer Fig.)': 'empirical'}
    _q_dist_inv = {v: k for k, v in _q_dist_map.items()}
    _saved_qm = lg_cfg.get('q_model', 'lognormal')
    q_dist_label = st.selectbox(
        'Mass ratio q distribution', _q_dist_options,
        index=_q_dist_options.index(
            _q_dist_inv.get(_saved_qm, _q_dist_options[0])),
        key=f'{p}_q_dist',
        on_change=lambda: sm.save(
            [sec, 'q_model'],
            value=_q_dist_map[st.session_state[f'{p}_q_dist']]))
    q_model = _q_dist_map[q_dist_label]

    if q_model != 'empirical':
        _qr = lg_cfg.get('q_range', [0.1, 2.0])
        _qc1, _qc2 = st.columns(2)
        with _qc1:
            q_min = st.number_input(
                'q min', 0.01, 50.0, float(_qr[0]), 0.05,
                key=f'{p}_q_min',
                on_change=lambda: sm.save(
                    [sec, 'q_range'],
                    value=[st.session_state[f'{p}_q_min'],
                           st.session_state.get(f'{p}_q_max', 2.0)]))
        with _qc2:
            q_max = st.number_input(
                'q max', 0.01, 50.0, float(_qr[1]), 0.05,
                key=f'{p}_q_max',
                on_change=lambda: sm.save(
                    [sec, 'q_range'],
                    value=[st.session_state.get(f'{p}_q_min', 0.1),
                           st.session_state[f'{p}_q_max']]))
    else:
        q_min, q_max = 0.1, 2.0
        st.caption('Sampling from digitized Langer+2020 Fig. 4')

    if q_model not in ('flat', 'empirical'):
        _ql = _mu_label(q_model) if q_model in (
            'lognormal', 'reflected_lognormal') else 'mean'
        _qmu_c1, _qmu_c2 = st.columns(2)
        lq_mu = _qmu_c1.number_input(
            f'q \u03bc ({_ql})', 0.01, 50.0,
            float(lg_cfg.get('langer_q_mu', 0.65)), 0.05,
            key=f'{p}_lq_mu',
            on_change=lambda: sm.save(
                [sec, 'langer_q_mu'],
                value=st.session_state[f'{p}_lq_mu']))
        lq_sig = _qmu_c2.number_input(
            'q \u03c3', 0.01, 50.0,
            float(lg_cfg.get('langer_q_sigma', 0.3)), 0.05,
            key=f'{p}_lq_sig',
            on_change=lambda: sm.save(
                [sec, 'langer_q_sigma'],
                value=st.session_state[f'{p}_lq_sig']))
    else:
        lq_mu = float(lg_cfg.get('langer_q_mu', 0.65))
        lq_sig = float(lg_cfg.get('langer_q_sigma', 0.3))

    # q flip toggle
    q_flipped = st.checkbox(
        'Flip q (M\u2081/M\u2082 instead of M\u2082/M\u2081)',
        value=bool(lg_cfg.get('q_flipped', False)),
        key=f'{p}_q_flipped',
        on_change=lambda: sm.save(
            [sec, 'q_flipped'],
            value=st.session_state[f'{p}_q_flipped']))

    _q_extra = (f', \u03bc={lq_mu}, \u03c3={lq_sig}'
                if q_model not in ('flat', 'empirical') else '')
    st.caption(f'q_model="{q_model}", '
               f'range=[{q_min}, {q_max}]{_q_extra}')

    return dict(
        dist_A=str(dist_A), mu_A=float(mu_A), sigma_A=float(sigma_A),
        dist_B=str(dist_B), mu_B=float(mu_B), sigma_B=float(sigma_B),
        weight_A=float(weight_A),
        logP_min=float(logP_min), logP_max=float(logP_max),
        mass_model=str(mass_model), mass_fixed=float(mass_fixed),
        mass_range=mass_range,
        q_model=str(q_model), q_min=float(q_min), q_max=float(q_max),
        lq_mu=float(lq_mu), lq_sig=float(lq_sig),
        q_flipped=bool(q_flipped),
    )


def _render_cadence_sigma_scan(
    p: str, sec: str, sm, gcfg: dict, settings: dict,
) -> list:
    """Render sigma scan expander for cadence tabs. Returns list of sigma values."""
    _scan_sigma = st.checkbox('Scan \u03c3_single', key=f'{p}_scan_sigma',
        on_change=lambda: sm.save([sec, 'scan_sigma'],
                                  value=st.session_state[f'{p}_scan_sigma']))
    if _scan_sigma:
        _s1, _s2, _s3 = st.columns(3)
        sig_min = _s1.number_input('\u03c3 min', 0.1, 100.0,
            float(gcfg.get('sigma_min', 5.0)), 0.5, key=f'{p}_sig_min',
            on_change=lambda: sm.save([sec, 'sigma_min'],
                                      value=st.session_state[f'{p}_sig_min']))
        sig_max = _s2.number_input('\u03c3 max', 0.1, 100.0,
            float(gcfg.get('sigma_max', 30.0)), 0.5, key=f'{p}_sig_max',
            on_change=lambda: sm.save([sec, 'sigma_max'],
                                      value=st.session_state[f'{p}_sig_max']))
        sig_steps = _s3.number_input('\u03c3 steps', 2, 100,
            int(gcfg.get('sigma_steps', 10)), 1, key=f'{p}_sig_steps',
            on_change=lambda: sm.save([sec, 'sigma_steps'],
                                      value=st.session_state[f'{p}_sig_steps']))
        return np.linspace(sig_min, sig_max, sig_steps).tolist()
    else:
        _single_sig = st.number_input('\u03c3_single (km/s)', 0.1, 100.0,
            float(gcfg.get('sigma_single',
                  float(settings.get('grid', {}).get('sigma_single', 15.0)))),
            0.5, key=f'{p}_sigma_single',
            on_change=lambda: sm.save([sec, 'sigma_single'],
                                      value=st.session_state[f'{p}_sigma_single']))
        return [_single_sig]


def _auto_drv_max(obs_drv, bin_width: float, headroom_bins: int = 5) -> float:
    """Round observed max up to a multiple of bin_width, plus headroom bins.

    Auto-derives the upper edge of the non-adaptive ΔRV bin grid from the
    observed ΔRVs, so the Mock Observation CDF always reaches the full
    data range. Mirrors how adaptive mode self-sizes.
    """
    if obs_drv is None or len(obs_drv) == 0:
        return 500.0  # safe fallback when observations not yet loaded
    _m = float(np.nanmax(obs_drv))
    return float(np.ceil(_m / bin_width) * bin_width + headroom_bins * bin_width)


def _render_cadence_adaptive_bins(
    p: str, sec: str, sm, gcfg: dict, settings: dict,
):
    """Render cadence-aware bin settings. Returns (use_adaptive, bin_edges, drv_bin_width, drv_max)."""
    st.caption('Bins for CDF visualization only \u2014 likelihood score uses the separate "Likelihood bin mode" control above the Run button.')
    _use_adaptive = st.checkbox(
        'Adaptive bins (recommended)', value=bool(gcfg.get('adaptive_bins', True)),
        key=f'{p}_adaptive_bins',
        on_change=lambda: sm.save(
            [sec, 'adaptive_bins'],
            value=st.session_state[f'{p}_adaptive_bins']),
        help='Use observed \u0394RV values as CDF evaluation points \u2014 eliminates bin-width parameter. (Affects CDF visual only, not likelihood score.)')
    if _use_adaptive:
        from wr_bias_simulation import adaptive_bin_edges as _abe
        try:
            _sh = settings_hash(settings)
            _obs_drv, _ = cached_load_observed_delta_rvs(_sh)
        except Exception:
            _obs_drv = None
        if _obs_drv is not None and len(_obs_drv) > 0:
            _cad_bin_edges = _abe(_obs_drv, min_gap=1.0)
            st.caption(f'{len(_cad_bin_edges)} adaptive bins from observed \u0394RVs')
        else:
            _cad_bin_edges = None
            st.caption('Observed \u0394RVs not loaded yet \u2014 will compute on run')
        return True, _cad_bin_edges, None, None
    else:
        drv_bin_width = st.number_input(
            '\u0394RV bin width (km/s)', 0.1, 50.0,
            float(gcfg.get('drv_bin_width', 5.0)), 0.1,
            key=f'{p}_drv_bin_width',
            on_change=lambda: sm.save(
                [sec, 'drv_bin_width'],
                value=st.session_state[f'{p}_drv_bin_width']))
        try:
            _sh = settings_hash(settings)
            _obs_drv, _ = cached_load_observed_delta_rvs(_sh)
        except Exception:
            _obs_drv = None
        drv_max = _auto_drv_max(_obs_drv, drv_bin_width)
        _n_bins = int(drv_max / drv_bin_width)
        st.caption(f'{_n_bins} bins \u00b7 max \u0394RV = {drv_max:.0f} km/s (auto)')
        return False, None, drv_bin_width, drv_max


def _infer_lk_bin_mode(bin_edges) -> tuple[str, float | None, str]:
    """Map a likelihood_bin_edges array to (mode, threshold, manual_text).

    Recognises the canonical dsilva_likelihood_bins schema
    [0, T, 250, 650, inf] as Threshold-based; everything else
    is Manual with the comma-joined finite edges.
    """
    be = np.asarray(bin_edges, dtype=float)
    finite = be[np.isfinite(be)]
    if (finite.size == 4
            and float(finite[0]) == 0.0
            and float(finite[2]) == 250.0
            and float(finite[3]) == 650.0):
        T = float(finite[1])
        return 'Threshold-based', T, f'0, {T:g}, 250, 650'
    return 'Manual', None, ', '.join(f'{e:g}' for e in finite)


def _render_likelihood_bin_config(
    p: str, prefix: str = '', sm=None,
    default_bin_edges: np.ndarray | None = None,
) -> np.ndarray:
    """Render likelihood bin edges configuration. Returns bin_edges array.

    Provides two modes: Threshold-based (auto-generate from detection threshold)
    and Manual (user edits comma-separated bin edges).

    When ``default_bin_edges`` is provided and the session-state flag
    ``f'{p}_is_loaded_result'`` is True, the widget seeds its mode /
    threshold / manual-edges keys from those edges for one render
    (one-shot override of any current state).  The flag is cleared by
    the caller at the end of the page render.
    """
    from wr_bias_simulation import dsilva_likelihood_bins

    # One-shot seeding from a freshly-loaded saved result.  The Load
    # handler sets f'{p}_is_loaded_result' = True; the page clears it
    # after widgets render, so this block fires for exactly one rerun.
    if (st.session_state.get(f'{p}_is_loaded_result', False)
            and default_bin_edges is not None):
        _mode, _thresh, _manual_text = _infer_lk_bin_mode(default_bin_edges)
        st.session_state[f'{p}{prefix}_lk_bin_mode'] = _mode
        if _thresh is not None:
            st.session_state[f'{p}{prefix}_lk_threshold'] = float(_thresh)
        st.session_state[f'{p}{prefix}_manual_edges'] = _manual_text
        st.session_state[f'{p}{prefix}_lk_edges_text'] = _manual_text

    # Pre-populate session_state from saved settings
    if sm is not None:
        _lk_cfg = sm.load().get('likelihood_bin_config', {})
        _sk = f'{p}{prefix}_lk_bin_mode'
        if _sk not in st.session_state and 'mode' in _lk_cfg:
            st.session_state[_sk] = _lk_cfg['mode']
        _tk = f'{p}{prefix}_lk_threshold'
        if _tk not in st.session_state and 'threshold' in _lk_cfg:
            st.session_state[_tk] = float(_lk_cfg['threshold'])
        _mk = f'{p}{prefix}_manual_edges'
        if _mk not in st.session_state and 'manual_edges' in _lk_cfg:
            st.session_state[_mk] = str(_lk_cfg['manual_edges'])

    def _lk_save(key, val):
        if sm is not None:
            sm.save(['likelihood_bin_config', key], value=val)

    _mode = st.radio('Likelihood bin mode', ['Threshold-based', 'Manual'],
                     horizontal=True, key=f'{p}{prefix}_lk_bin_mode',
                     on_change=lambda: _lk_save('mode',
                                                st.session_state[f'{p}{prefix}_lk_bin_mode']))

    if _mode == 'Threshold-based':
        _lk_threshold = st.number_input(
            'Detection threshold (km/s)', value=45.5,
            min_value=1.0, max_value=200.0, step=0.5,
            key=f'{p}{prefix}_lk_threshold',
            on_change=lambda: _lk_save('threshold',
                                       st.session_state[f'{p}{prefix}_lk_threshold']))
        _lk_bin_edges = dsilva_likelihood_bins(_lk_threshold)
    else:
        _default = st.session_state.get(f'{p}{prefix}_manual_edges', '0, 45.5, 250, 650')
        _edges_text = st.text_input(
            'Bin edges (comma-separated, ∞ added automatically)',
            value=_default, key=f'{p}{prefix}_lk_edges_text',
            on_change=lambda: _lk_save('manual_edges',
                                       st.session_state[f'{p}{prefix}_lk_edges_text']))
        try:
            _parsed = sorted([float(x.strip()) for x in _edges_text.split(',')
                              if x.strip()])
            if len(_parsed) < 2:
                st.error('Need at least 2 bin edges.')
                _parsed = [0, 45.5, 250, 650]
            _lk_bin_edges = np.array(_parsed + [np.inf])
            st.session_state[f'{p}{prefix}_manual_edges'] = _edges_text
        except ValueError:
            st.error('Invalid format. Use comma-separated numbers.')
            _lk_bin_edges = dsilva_likelihood_bins(45.5)

    _labels = [f'{e:.0f}' if np.isfinite(e) else '∞' for e in _lk_bin_edges]
    st.caption(f'Likelihood bins: [{", ".join(_labels)}]')
    return _lk_bin_edges


def _render_explorer_lk_bin_config(
    p: str, prefix: str, sm, default_bin_edges: np.ndarray,
) -> np.ndarray:
    """Explorer-only likelihood-bin editor.

    Mirrors `_render_likelihood_bin_config` (Threshold-based + Manual modes)
    but writes/reads under the SEPARATE settings namespace
    ``'explorer_likelihood_bin_config'`` so the simulation's saved
    ``'likelihood_bin_config'`` is NEVER touched.

    On first render (no Explorer-specific saved config), Manual-mode default
    text is seeded from ``default_bin_edges`` (drop trailing ``inf``, comma-
    joined).  Always visible — no expander.
    """
    from wr_bias_simulation import dsilva_likelihood_bins

    # Seed manual default text from the simulation's bin edges.
    _seed_edges = np.asarray(default_bin_edges, dtype=float)
    _seed_finite = _seed_edges[np.isfinite(_seed_edges)]
    if _seed_finite.size >= 2:
        _seed_text = ', '.join(f'{e:g}' for e in _seed_finite)
    else:
        _seed_text = '0, 45.5, 250, 650'

    # One-shot seeding from a freshly-loaded saved result.  Uses the
    # same flag as the global widget (f'{p}_is_loaded_result') so both
    # widgets re-seed atomically on a single Load click.
    if (st.session_state.get(f'{p}_is_loaded_result', False)
            and default_bin_edges is not None):
        _mode, _thresh, _manual_text = _infer_lk_bin_mode(default_bin_edges)
        st.session_state[f'{p}{prefix}_explorer_lk_bin_mode'] = _mode
        if _thresh is not None:
            st.session_state[f'{p}{prefix}_explorer_lk_threshold'] = float(_thresh)
        st.session_state[f'{p}{prefix}_explorer_manual_edges'] = _manual_text
        st.session_state[f'{p}{prefix}_explorer_lk_edges_text'] = _manual_text

    # Pre-populate session_state from saved settings (Explorer namespace).
    if sm is not None:
        _lk_cfg = sm.load().get('explorer_likelihood_bin_config', {})
        _sk = f'{p}{prefix}_explorer_lk_bin_mode'
        if _sk not in st.session_state and 'mode' in _lk_cfg:
            st.session_state[_sk] = _lk_cfg['mode']
        _tk = f'{p}{prefix}_explorer_lk_threshold'
        if _tk not in st.session_state and 'threshold' in _lk_cfg:
            st.session_state[_tk] = float(_lk_cfg['threshold'])
        _mk = f'{p}{prefix}_explorer_manual_edges'
        if _mk not in st.session_state:
            if 'manual_edges' in _lk_cfg:
                st.session_state[_mk] = str(_lk_cfg['manual_edges'])
            else:
                st.session_state[_mk] = _seed_text

    def _lk_save(key, val):
        if sm is not None:
            sm.save(['explorer_likelihood_bin_config', key], value=val)

    _mode = st.radio(
        'Likelihood bin mode', ['Threshold-based', 'Manual'],
        horizontal=True, key=f'{p}{prefix}_explorer_lk_bin_mode',
        on_change=lambda: _lk_save(
            'mode',
            st.session_state[f'{p}{prefix}_explorer_lk_bin_mode']))

    if _mode == 'Threshold-based':
        _lk_threshold = st.number_input(
            'Detection threshold (km/s)', value=45.5,
            min_value=1.0, max_value=200.0, step=0.5,
            key=f'{p}{prefix}_explorer_lk_threshold',
            on_change=lambda: _lk_save(
                'threshold',
                st.session_state[f'{p}{prefix}_explorer_lk_threshold']))
        _lk_bin_edges = dsilva_likelihood_bins(_lk_threshold)
    else:
        _default = st.session_state.get(
            f'{p}{prefix}_explorer_manual_edges', _seed_text)
        _edges_text = st.text_input(
            'Bin edges (comma-separated, ∞ added automatically)',
            value=_default,
            key=f'{p}{prefix}_explorer_lk_edges_text',
            on_change=lambda: _lk_save(
                'manual_edges',
                st.session_state[
                    f'{p}{prefix}_explorer_lk_edges_text']))
        try:
            _parsed = sorted([float(x.strip()) for x in _edges_text.split(',')
                              if x.strip()])
            if len(_parsed) < 2:
                st.error('Need at least 2 bin edges.')
                _parsed = [0, 45.5, 250, 650]
            _lk_bin_edges = np.array(_parsed + [np.inf])
            st.session_state[f'{p}{prefix}_explorer_manual_edges'] = _edges_text
        except ValueError:
            st.error('Invalid format. Use comma-separated numbers.')
            _lk_bin_edges = dsilva_likelihood_bins(45.5)

    _labels = [f'{e:.0f}' if np.isfinite(e) else '∞' for e in _lk_bin_edges]
    st.caption(f'Likelihood bins (Explorer): [{", ".join(_labels)}]')
    return _lk_bin_edges


# ─────────────────────────────────────────────────────────────────────────────
# logP_max scan expander (shared by cadence tabs)
# ─────────────────────────────────────────────────────────────────────────────

def _render_logPmax_scan(p: str, sec: str, sm, default_logP_max: float = 5.0,
                         ) -> np.ndarray:
    """Render the logP_max scan toggle + sliders inside an expander.

    Returns an ndarray of logPmax values to scan (length 1 if scan is off).
    """
    # Seed the fixed-value default if not yet in session_state.
    if f'{p}_logPmax_fixed' not in st.session_state:
        st.session_state[f'{p}_logPmax_fixed'] = float(
            st.session_state.get(f'{p}_logP_max', default_logP_max))

    _scan_lp = st.toggle(
        'Scan logP_max over a range',
        key=f'{p}_scan_logPmax',
        on_change=lambda: sm.save(
            [sec, 'scan_logPmax'],
            value=st.session_state[f'{p}_scan_logPmax']))
    if _scan_lp:
        _lpc1, _lpc2, _lpc3 = st.columns(3)
        _lp_min = _lpc1.number_input(
            'logP_max min', 0.5, 10.0,
            float(st.session_state[f'{p}_logPmax_scan_min']), 0.1,
            key=f'{p}_logPmax_scan_min',
            on_change=lambda: sm.save(
                [sec, 'logPmax_scan_min'],
                value=st.session_state[f'{p}_logPmax_scan_min']))
        _lp_max = _lpc2.number_input(
            'logP_max max', 1.0, 10.0,
            float(st.session_state[f'{p}_logPmax_scan_max']), 0.1,
            key=f'{p}_logPmax_scan_max',
            on_change=lambda: sm.save(
                [sec, 'logPmax_scan_max'],
                value=st.session_state[f'{p}_logPmax_scan_max']))
        _lp_steps = _lpc3.number_input(
            'logP_max steps', 3, 100,
            int(st.session_state[f'{p}_logPmax_scan_steps']), 1,
            key=f'{p}_logPmax_scan_steps',
            on_change=lambda: sm.save(
                [sec, 'logPmax_scan_steps'],
                value=st.session_state[f'{p}_logPmax_scan_steps']))
        return np.linspace(
            float(_lp_min),
            max(float(_lp_min) + 0.1, float(_lp_max)),
            int(_lp_steps))
    st.number_input(
        'logP_max (fixed)', 0.5, 10.0,
        float(st.session_state[f'{p}_logPmax_fixed']), 0.1,
        key=f'{p}_logPmax_fixed',
        on_change=lambda: sm.save(
            [sec, 'logPmax_fixed'],
            value=st.session_state[f'{p}_logPmax_fixed']))
    st.caption(
        'Overrides the orbital logP_max when the scan is off; this is the '
        'value used for simulating binary stars.')
    return np.array([float(st.session_state[f'{p}_logPmax_fixed'])])
