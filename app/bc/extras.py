"""bc.extras — RV Errors tab and Compare tab."""
from __future__ import annotations

import json
import math as _math
import os
import sys
import warnings as _warnings

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from shared import (
    cached_load_observed_delta_rvs, cached_load_cadence,
    cached_load_grid_result, settings_hash,
    find_best_grid_point, make_heatmap_fig,
    PLOTLY_THEME, get_palette,
)

from bc.helpers import (
    SCORING_METHODS, _METHOD_COLORS,
    _RESULT_DIR,
    _CMP_COLORS, _CMP_DASHES,
    _hex_to_rgba,
    _list_saved_results,
    _scan_result_metadata,
    _best_point, _make_heatmap_fig,
)

# ─────────────────────────────────────────────────────────────────────────────
# RV Errors tab: helpers
# ─────────────────────────────────────────────────────────────────────────────

import warnings as _warnings

_RVE_DISTRIBUTIONS = {
    'Normal': 'norm',
    'Log-normal': 'lognorm',
    'Gamma': 'gamma',
    'Weibull': 'weibull_min',
    'Exponential': 'expon',
    'Flat (uniform)': 'uniform',
}

# Parameter metadata: name -> list of (label, default, min, max, step)
_RVE_PARAM_META = {
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


@st.cache_data
def _rve_check_contamination(star_names: tuple) -> dict:
    """Check which stars have spatial contamination (cleaned_normalized_flux)."""
    from shared import get_obs_manager
    obs = get_obs_manager()
    result = {}
    for sn in star_names:
        has_cleaned = False
        try:
            star = obs.load_star_instance(sn, to_print=False)
            for ep in star.get_all_epoch_numbers():
                d = star.load_property('cleaned_normalized_flux', ep, 'COMBINED')
                if d is not None and isinstance(d, dict):
                    has_cleaned = True
                    break
        except Exception:
            pass
        result[sn] = has_cleaned
    return result


def _rve_collect_errors(stars: dict) -> np.ndarray:
    """Collect all per-epoch rv_err values from a group of stars."""
    all_err = []
    for d in stars.values():
        errs = np.asarray(d.get('rv_err', []), dtype=float)
        errs = errs[errs > 0]
        all_err.extend(errs.tolist())
    return np.array(all_err, dtype=float)


def _rve_fit_distribution(data: np.ndarray, dist_name: str) -> dict | None:
    """Fit a named distribution via MLE. Returns params + AIC/BIC."""
    import scipy.stats as st_stats
    if len(data) < 5:
        return None
    scipy_name = _RVE_DISTRIBUTIONS.get(dist_name)
    if scipy_name is None:
        return None
    dist = getattr(st_stats, scipy_name, None)
    if dist is None:
        return None
    try:
        with _warnings.catch_warnings():
            _warnings.simplefilter('ignore')
            params = dist.fit(data)
        k = len(params)
        n = len(data)
        log_lik = float(np.sum(dist.logpdf(data, *params)))
        if not np.isfinite(log_lik):
            return None
        aic = 2 * k - 2 * log_lik
        bic = k * np.log(n) - 2 * log_lik
        return {
            'dist_name': dist_name, 'scipy_name': scipy_name,
            'params': params, 'k': k, 'n': n,
            'log_lik': log_lik, 'aic': aic, 'bic': bic,
        }
    except Exception:
        return None


def _rve_compute_aic_bic(data: np.ndarray, scipy_name: str,
                          params: tuple) -> dict:
    """Compute AIC/BIC for given params (for manual adjustment)."""
    import scipy.stats as st_stats
    dist = getattr(st_stats, scipy_name)
    k = len(params)
    n = len(data)
    try:
        log_lik = float(np.sum(dist.logpdf(data, *params)))
    except Exception:
        log_lik = float('-inf')
    if not np.isfinite(log_lik):
        return {'aic': float('inf'), 'bic': float('inf'), 'log_lik': float('-inf')}
    aic = 2 * k - 2 * log_lik
    bic = k * np.log(n) - 2 * log_lik
    return {'aic': aic, 'bic': bic, 'log_lik': log_lik}


def _rve_fit_all(data: np.ndarray) -> list[dict]:
    """Fit all distributions, sort by AIC."""
    results = []
    for name in _RVE_DISTRIBUTIONS:
        r = _rve_fit_distribution(data, name)
        if r is not None:
            results.append(r)
    results.sort(key=lambda x: x['aic'])
    return results


# ─────────────────────────────────────────────────────────────────────────────
# RV Errors tab: renderer
# ─────────────────────────────────────────────────────────────────────────────

def _render_rv_errors_tab(p: str, settings: dict, sm) -> None:
    """Render the RV Error Explorer tab."""
    import scipy.stats as st_stats

    pal = get_palette()
    _sh = settings_hash(settings)
    obs_delta_rv, detail = cached_load_observed_delta_rvs(_sh)

    contamination = _rve_check_contamination(tuple(detail.keys()))

    # ── Controls ──────────────────────────────────────────────────────────
    _c1, _c2, _c3 = st.columns([0.3, 0.3, 0.4])
    threshold = _c1.slider(
        'ΔRV threshold (km/s)', 0.0, 200.0, 45.5, 0.5,
        key=f'{p}_threshold',
        help='Stars with ΔRV above this AND significance > 4σ are binary.',
    )
    star_filter = _c2.radio(
        'Star filter', ['All', 'Clean only', 'Contaminated only'],
        key=f'{p}_filter', horizontal=True,
    )
    normalize = _c3.checkbox('Normalize (probability density)', value=True,
                              key=f'{p}_normalize')

    # ── Reclassify ────────────────────────────────────────────────────────
    single_stars: dict = {}
    binary_stars: dict = {}
    for star_name, d in detail.items():
        is_contaminated = contamination.get(star_name, False)
        if star_filter == 'Clean only' and is_contaminated:
            continue
        if star_filter == 'Contaminated only' and not is_contaminated:
            continue
        dRV = float(d['best_dRV'])
        sigma = float(d['best_sigma']) if not np.isnan(d['best_sigma']) else 0.0
        is_binary = (dRV > threshold) and (dRV - 4 * sigma > 0)
        (binary_stars if is_binary else single_stars)[star_name] = d

    single_errs = _rve_collect_errors(single_stars)
    binary_errs = _rve_collect_errors(binary_stars)

    # ── Two-column layout ─────────────────────────────────────────────────
    st.markdown('---')
    col_s, col_b = st.columns(2)

    for _label, _errs, _col, _key in [
        ('Single', single_errs, col_s, 'single'),
        ('Binary', binary_errs, col_b, 'binary'),
    ]:
        _star_count = len(single_stars) if _key == 'single' else len(binary_stars)
        with _col:
            st.markdown(f'### {_label} Stars ({_star_count})')
            st.caption(f'{len(_errs)} per-epoch error measurements')

            if len(_errs) < 2:
                st.info(f'Not enough data for {_label.lower()} stars.')
                continue

            # Distribution selector + auto-fit
            _dist_name = st.selectbox(
                'Distribution', list(_RVE_DISTRIBUTIONS.keys()),
                key=f'{p}_{_key}_dist',
            )

            _fc1, _fc2 = st.columns(2)
            _fit_btn = _fc1.button('Auto-fit', key=f'{p}_{_key}_fit_btn')
            if _fit_btn:
                _fit_result = _rve_fit_distribution(_errs, _dist_name)
                if _fit_result is not None:
                    for i, val in enumerate(_fit_result['params']):
                        st.session_state[f'{p}_{_key}_param_{i}'] = float(val)
                    # Auto-record to fit history
                    _hist_key = f'{p}_{_key}_fit_history'
                    if _hist_key not in st.session_state:
                        st.session_state[_hist_key] = []
                    st.session_state[_hist_key].append({
                        '#': len(st.session_state[_hist_key]) + 1,
                        'Distribution': _dist_name,
                        'Params': ', '.join(f'{v:.4f}' for v in _fit_result['params']),
                        'AIC': round(_fit_result['aic'], 1),
                        'BIC': round(_fit_result['bic'], 1),
                        'log L': round(_fit_result['log_lik'], 1),
                    })

            # Parameter inputs
            _param_meta = _RVE_PARAM_META.get(_dist_name, [])
            _current_params = []
            _param_cols = st.columns(len(_param_meta)) if _param_meta else []
            for i, (label, default, pmin, pmax, step) in enumerate(_param_meta):
                _sk = f'{p}_{_key}_param_{i}'
                _val = st.session_state.get(_sk, default)
                with _param_cols[i]:
                    _val = st.number_input(
                        label, min_value=pmin, max_value=pmax,
                        value=float(_val), step=step,
                        format='%.4f', key=_sk,
                    )
                _current_params.append(_val)

            _scipy_name = _RVE_DISTRIBUTIONS[_dist_name]
            _scipy_dist = getattr(st_stats, _scipy_name)
            _params_tuple = tuple(_current_params)

            # Record manual params button
            _record_btn = _fc2.button('📝 Record fit', key=f'{p}_{_key}_record_btn')
            if _record_btn and len(_current_params) > 0:
                _man_stats = _rve_compute_aic_bic(_errs, _scipy_name, _params_tuple)
                _hist_key = f'{p}_{_key}_fit_history'
                if _hist_key not in st.session_state:
                    st.session_state[_hist_key] = []
                st.session_state[_hist_key].append({
                    '#': len(st.session_state[_hist_key]) + 1,
                    'Distribution': _dist_name,
                    'Params': ', '.join(f'{v:.4f}' for v in _current_params),
                    'AIC': round(_man_stats['aic'], 1),
                    'BIC': round(_man_stats['bic'], 1),
                    'log L': round(_man_stats['log_lik'], 1),
                })

            # Histogram + PDF overlay
            fig = go.Figure()
            histnorm = 'probability density' if normalize else ''
            fig.add_trace(go.Histogram(
                x=_errs, nbinsx=40, histnorm=histnorm,
                marker_color='#4A90D9', opacity=0.6,
                name='RV errors',
            ))

            if normalize and len(_current_params) > 0:
                try:
                    _x_lo = float(_errs.min()) - 0.5
                    _x_hi = float(_errs.max()) + 0.5
                    # Positive-only distributions: clamp lower bound to 0
                    _positive_only = {'lognorm', 'gamma', 'weibull_min', 'expon'}
                    if _scipy_name in _positive_only:
                        _x_lo = max(0.001, _x_lo)
                    x_range = np.linspace(_x_lo, _x_hi, 200)
                    pdf = _scipy_dist.pdf(x_range, *_params_tuple)
                    if np.all(np.isfinite(pdf)):
                        fig.add_trace(go.Scatter(
                            x=x_range, y=pdf, mode='lines',
                            line=dict(color='#E25A53', width=2.5),
                            name=f'{_dist_name} fit',
                        ))
                except Exception:
                    pass

            fig.update_layout(**{
                **PLOTLY_THEME,
                'title': dict(
                    text=f'{_label} RV errors (N={len(_errs)})',
                    font=dict(size=14)),
                'xaxis_title': 'σ_RV (km/s)',
                'yaxis_title': 'Density' if normalize else 'Count',
                'height': 380,
                'showlegend': True,
                'legend': dict(x=0.65, y=0.95),
            })
            st.plotly_chart(fig, use_container_width=True,
                            key=f'{p}_{_key}_hist')

            # AIC / BIC for current params
            if len(_current_params) > 0:
                _stats = _rve_compute_aic_bic(_errs, _scipy_name, _params_tuple)
                st.markdown(
                    f'**{_dist_name}** — '
                    f'AIC: {_stats["aic"]:.1f} · '
                    f'BIC: {_stats["bic"]:.1f} · '
                    f'log L: {_stats["log_lik"]:.1f}'
                )

            # Summary stats
            st.markdown(
                f'**Data:** mean={np.mean(_errs):.3f}, '
                f'median={np.median(_errs):.3f}, '
                f'std={np.std(_errs):.3f} km/s'
            )

            # ── Fit history table ──
            _hist_key = f'{p}_{_key}_fit_history'
            if st.session_state.get(_hist_key):
                st.markdown('#### Fit History')
                st.dataframe(
                    pd.DataFrame(st.session_state[_hist_key]),
                    use_container_width=True, hide_index=True,
                )
                if st.button('🗑️ Clear history', key=f'{p}_{_key}_clear_hist'):
                    st.session_state[_hist_key] = []
                    st.rerun()

    # ── Auto-Fit All ──────────────────────────────────────────────────────
    st.markdown('---')
    st.markdown('### Auto-Fit All Distributions')

    if st.button('🔍 Run Auto-Fit', key=f'{p}_autofit_btn', type='primary'):
        _af_results = {}
        for _lbl, _errs_af, _key_af in [
            ('Single', single_errs, 'single'),
            ('Binary', binary_errs, 'binary'),
        ]:
            if len(_errs_af) < 5:
                _af_results[_key_af] = None
                continue
            fits = _rve_fit_all(_errs_af)
            _af_results[_key_af] = fits if fits else None
            # Also add all fits to the per-column fit history
            _hist_key = f'{p}_{_key_af}_fit_history'
            if _hist_key not in st.session_state:
                st.session_state[_hist_key] = []
            for f in (fits or []):
                st.session_state[_hist_key].append({
                    '#': len(st.session_state[_hist_key]) + 1,
                    'Distribution': f['dist_name'],
                    'Params': ', '.join(f'{v:.4f}' for v in f['params']),
                    'AIC': round(f['aic'], 1),
                    'BIC': round(f['bic'], 1),
                    'log L': round(f['log_lik'], 1),
                })
        st.session_state[f'{p}_autofit_results'] = _af_results

    # Render persistent auto-fit results from session_state
    _af_results = st.session_state.get(f'{p}_autofit_results')
    if _af_results:
        _af_c1, _af_c2 = st.columns(2)
        for _lbl, _errs_af, _col, _key_af in [
            ('Single', single_errs, _af_c1, 'single'),
            ('Binary', binary_errs, _af_c2, 'binary'),
        ]:
            fits = _af_results.get(_key_af)
            with _col:
                st.markdown(f'#### {_lbl} Stars')
                if fits is None or len(fits) == 0:
                    st.warning('Not enough data or all fits failed.')
                    continue
                rows = []
                for i, f in enumerate(fits):
                    rows.append({
                        'Rank': i + 1,
                        'Distribution': f['dist_name'],
                        'AIC': round(f['aic'], 1),
                        'BIC': round(f['bic'], 1),
                        'log L': round(f['log_lik'], 1),
                        'Params': ', '.join(f'{v:.4f}' for v in f['params']),
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True,
                             hide_index=True)
                best = fits[0]
                st.success(f'Best: **{best["dist_name"]}** '
                           f'(AIC={best["aic"]:.1f})')

                # Best-fit PDF overlay on histogram
                if len(_errs_af) >= 2:
                    _best_dist = getattr(st_stats, best['scipy_name'])
                    _positive_only = {'lognorm', 'gamma', 'weibull_min', 'expon'}
                    _xlo_af = float(_errs_af.min()) - 0.5
                    if best['scipy_name'] in _positive_only:
                        _xlo_af = max(0.001, _xlo_af)
                    _xr_af = np.linspace(_xlo_af, float(_errs_af.max()) + 0.5, 200)
                    _pdf_af = _best_dist.pdf(_xr_af, *best['params'])
                    fig_af = go.Figure()
                    fig_af.add_trace(go.Histogram(
                        x=_errs_af, nbinsx=40, histnorm='probability density',
                        marker_color='#4A90D9', opacity=0.5,
                        name='RV errors',
                    ))
                    if np.all(np.isfinite(_pdf_af)):
                        fig_af.add_trace(go.Scatter(
                            x=_xr_af, y=_pdf_af, mode='lines',
                            line=dict(color='#E25A53', width=2.5),
                            name=f'{best["dist_name"]} (best)',
                        ))
                    fig_af.update_layout(**{
                        **PLOTLY_THEME,
                        'title': dict(
                            text=f'Best fit: {best["dist_name"]} ({_lbl})',
                            font=dict(size=13)),
                        'xaxis_title': 'σ_RV (km/s)',
                        'yaxis_title': 'Density',
                        'height': 340, 'showlegend': True,
                        'legend': dict(x=0.6, y=0.95),
                    })
                    st.plotly_chart(fig_af, use_container_width=True,
                                    key=f'{p}_af_hist_{_key_af}')

                # Q-Q plot
                sorted_data = np.sort(_errs_af)
                n = len(sorted_data)
                _best_dist = getattr(st_stats, best['scipy_name'])
                theor_q = _best_dist.ppf(
                    np.linspace(0.5/n, 1-0.5/n, n), *best['params'])
                fig_qq = go.Figure()
                fig_qq.add_trace(go.Scatter(
                    x=theor_q, y=sorted_data, mode='markers',
                    marker=dict(size=4, color='#4A90D9', opacity=0.6),
                    name='Data',
                ))
                _qmin = min(float(theor_q.min()), float(sorted_data.min()))
                _qmax = max(float(theor_q.max()), float(sorted_data.max()))
                fig_qq.add_trace(go.Scatter(
                    x=[_qmin, _qmax], y=[_qmin, _qmax], mode='lines',
                    line=dict(color='#E25A53', dash='dash', width=1.5),
                    name='y=x',
                ))
                fig_qq.update_layout(**{
                    **PLOTLY_THEME,
                    'title': dict(
                        text=f'Q-Q: {best["dist_name"]} ({_lbl})',
                        font=dict(size=13)),
                    'xaxis_title': 'Theoretical quantiles',
                    'yaxis_title': 'Sample quantiles',
                    'height': 320, 'showlegend': False,
                })
                st.plotly_chart(fig_qq, use_container_width=True,
                                key=f'{p}_qq_{_key_af}')

    # ── Score explanations ──────────────────────────────────────────────
    with st.expander('ℹ️ What do the scores mean?', expanded=False):
        st.markdown(
            '**AIC** (Akaike Information Criterion): *Lower is better.* '
            'Measures how well the model fits the data while penalizing complexity. '
            'Formula: AIC = 2k − 2·ln(L), where k = number of parameters, L = likelihood.\n\n'
            '**BIC** (Bayesian Information Criterion): *Lower is better.* '
            'Similar to AIC but with a stronger penalty for extra parameters, '
            'especially for larger sample sizes. '
            'Formula: BIC = k·ln(n) − 2·ln(L).\n\n'
            '**log L** (Log-likelihood): *Higher is better.* '
            'The raw measure of how probable the data is under the fitted model. '
            'Unlike AIC/BIC, it does not penalize complexity — a model with more '
            'parameters will almost always have a higher log L.\n\n'
            '**Practical guidance:** Compare distributions using AIC or BIC. '
            'They balance goodness-of-fit against model complexity. '
            'If AIC and BIC disagree, BIC tends to favor simpler models.'
        )

    # ── Combined overlay + K-S test ───────────────────────────────────────
    st.markdown('---')
    st.markdown('### Combined Population Comparison')

    if len(single_errs) > 0 and len(binary_errs) > 0:
        fig_comb = go.Figure()
        _hn = 'probability density' if normalize else ''
        fig_comb.add_trace(go.Histogram(
            x=single_errs, nbinsx=40, histnorm=_hn,
            marker_color='#4A90D9', opacity=0.5,
            name=f'Single ({len(single_errs)})',
        ))
        fig_comb.add_trace(go.Histogram(
            x=binary_errs, nbinsx=40, histnorm=_hn,
            marker_color='#E25A53', opacity=0.5,
            name=f'Binary ({len(binary_errs)})',
        ))
        fig_comb.update_layout(**{
            **PLOTLY_THEME,
            'title': dict(text='RV Error Distributions: Single vs Binary',
                           font=dict(size=14)),
            'xaxis_title': 'σ_RV (km/s)',
            'yaxis_title': 'Density' if normalize else 'Count',
            'barmode': 'overlay', 'height': 420,
            'legend': dict(x=0.65, y=0.95),
        })
        st.plotly_chart(fig_comb, use_container_width=True,
                        key=f'{p}_combined')

        ks_stat, ks_pval = st_stats.ks_2samp(single_errs, binary_errs)
        st.markdown(
            f'**Two-sample K-S test:** D = {ks_stat:.4f}, p = {ks_pval:.4e}  \n'
            f'{"Populations are **significantly different**" if ks_pval < 0.05 else "No significant difference detected"} '
            f'(α = 0.05)'
        )
    else:
        st.info('Need both populations to compare.')

    # ── Current error model reference ─────────────────────────────────────
    st.markdown('---')
    with st.expander('📋 Current Simulation Error Model', expanded=False):
        _sigma_m = float(settings.get('simulation', {}).get('sigma_measure', 1.622))
        _sigma_s = float(settings.get('grid', {}).get('sigma_single', 15.0))
        st.markdown(
            f'**Fixed model:** σ_measure = {_sigma_m:.3f} km/s, '
            f'σ_single = {_sigma_s:.1f} km/s  \n'
            f'**σ_total** = √(σ_single² + σ_measure²) = '
            f'{np.sqrt(_sigma_s**2 + _sigma_m**2):.2f} km/s  \n\n'
            f'The distributions explored above could replace the fixed σ_measure '
            f'with per-epoch draws from the best-fit distribution.'
        )


# ─────────────────────────────────────────────────────────────────────────────

def _render_one_error_model(p: str, suffix: str, simcfg: dict, sm,
                            settings_section: str, label: str = 'Error model') -> dict:
    """Render ONE error model selector. Returns {'type': str, 'sigma_measure': float, 'params': tuple}."""
    import scipy.stats as st_stats

    _err_options = ['Fixed', 'Normal', 'Log-normal', 'Gamma', 'Weibull', 'Exponential', 'Flat (uniform)']
    _saved_key = f'error_model_type{suffix}'
    _saved_type = str(simcfg.get(_saved_key, simcfg.get('error_model_type', 'Fixed')))
    _saved_idx = _err_options.index(_saved_type) if _saved_type in _err_options else 0
    _err_model = st.selectbox(
        label, _err_options,
        index=_saved_idx,
        key=f'{p}_err_model{suffix}',
        help='Fixed = constant σ_measure. Distribution = per-epoch error drawn from fitted model.',
        on_change=lambda: sm.save([settings_section, _saved_key],
                                  value=st.session_state[f'{p}_err_model{suffix}']),
    )

    if _err_model == 'Fixed':
        _sm_key = f'sigma_measure{suffix}'
        sigma_meas = st.number_input(
            'σ_measure (km/s)', 0.001, 20.0,
            float(simcfg.get(_sm_key, simcfg.get('sigma_measure', 1.622))), 0.001,
            format='%.3f', key=f'{p}_sigma_meas{suffix}',
            on_change=lambda: sm.save([settings_section, _sm_key],
                                      value=st.session_state[f'{p}_sigma_meas{suffix}']),
        )
        return {'type': 'fixed', 'sigma_measure': float(sigma_meas), 'params': ()}

    _param_meta = _RVE_PARAM_META.get(_err_model, [])
    _params = []
    if _param_meta:
        _pcols = st.columns(len(_param_meta))
        for i, (lbl, default, pmin, pmax, step) in enumerate(_param_meta):
            _saved_val = float(simcfg.get(f'errp{suffix}_{i}', default))
            with _pcols[i]:
                _val = st.number_input(
                    lbl, min_value=pmin, max_value=pmax,
                    value=float(st.session_state.get(f'{p}_errp{suffix}_{i}', _saved_val)),
                    step=step, format='%.4f', key=f'{p}_errp{suffix}_{i}',
                    on_change=lambda _i=i: sm.save(
                        [settings_section, f'errp{suffix}_{_i}'],
                        value=st.session_state[f'{p}_errp{suffix}_{_i}']),
                )
            _params.append(_val)

    _scipy_name = _RVE_DISTRIBUTIONS.get(_err_model, 'norm')
    try:
        _dist = getattr(st_stats, _scipy_name)
        _mean = float(_dist.mean(*_params))
        if not np.isfinite(_mean) or _mean <= 0:
            _mean = 1.622
    except Exception:
        _mean = 1.622

    st.caption(f'Distribution mean = {_mean:.3f} km/s (per-epoch draws)')
    return {'type': _err_model, 'sigma_measure': _mean, 'params': tuple(_params)}


def _render_error_model_selector(p: str, simcfg: dict, sm,
                                  settings_section: str = 'simulation') -> dict:
    """Render error model UI with separate selectors for singles and binaries.

    Returns dict with keys:
        type_single, sigma_measure, params_single,
        type_binary, params_binary
    """
    c1, c2 = st.columns(2)
    with c1:
        st.markdown('**Singles**')
        _single = _render_one_error_model(p, '_single', simcfg, sm,
                                          settings_section, 'Error model (singles)')
    with c2:
        st.markdown('**Binaries**')
        _binary = _render_one_error_model(p, '_binary', simcfg, sm,
                                          settings_section, 'Error model (binaries)')
    return {
        'type_single': _single['type'],
        'sigma_measure': _single['sigma_measure'],
        'params_single': _single['params'],
        'type_binary': _binary['type'],
        'sigma_measure_binary': _binary['sigma_measure'],
        'params_binary': _binary['params'],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Compare tab renderer

def _render_compare_tab(p: str) -> None:
    """Render a comparison tab for N saved bias correction results.

    Parameters
    ----------
    p : str
        Unique prefix for session-state keys (e.g. 'cmp', 'cmp2').
    """
    import math as _math

    st.markdown('### Compare saved results')
    st.caption('Select 2 or more rows from the table below to compare them.')

    # ── Clickable multi-select table ─────────────────────────────────────
    _cmp_meta = _scan_result_metadata()  # both models
    if len(_cmp_meta) < 2:
        st.info('Need at least 2 saved result files to compare. Run some simulations first!')
        return

    _cmp_display = _cmp_meta.drop(columns=['_path'], errors='ignore')
    _cmp_sel = st.dataframe(
        _cmp_display,
        on_select='rerun',
        selection_mode='multi-row',
        key=f'{p}_cmp_table',
        hide_index=True,
        use_container_width=True,
    )
    _cmp_rows = _cmp_sel.selection.rows if _cmp_sel.selection else []
    if len(_cmp_rows) < 2:
        st.info('Select 2 or more results from the table above to compare.')
        return

    # ── Load all selected results ─────────────────────────────────────────
    results = []  # list of dicts with label, short, res, info, color, dash
    for _i, _row_idx in enumerate(_cmp_rows):
        _row = _cmp_meta.iloc[_row_idx]
        _label = f"#{_i + 1}: {_row['File'][:30]}"
        _fpath = _row['_path']
        try:
            _res = dict(np.load(_fpath, allow_pickle=True))
        except Exception as _e:
            st.error(f'Error loading {_row["File"]}: {_e}')
            continue
        results.append({
            'label': _label,
            'short': f'#{_i + 1}',
            'res': _res,
            'info': None,  # filled below
            'color': _CMP_COLORS[_i % len(_CMP_COLORS)],
            'dash': _CMP_DASHES[_i % len(_CMP_DASHES)],
            'hdi': {},
        })
    if len(results) < 2:
        st.warning('Could not load enough results for comparison.')
        return

    # ── Selected-results confirmation table ───────────────────────────────
    _sel_rows = []
    for _r in results:
        _sel_rows.append({
            'Label': _r['short'],
            'Color': _r['color'],
            'File': _r['label'].split(': ', 1)[-1] if ': ' in _r['label'] else _r['label'],
        })
    st.dataframe(pd.DataFrame(_sel_rows), hide_index=True, use_container_width=True)
    if len(results) > 6:
        st.caption('More than 6 results selected — plots may be crowded. Consider narrowing your selection.')

    # ── View mode toggle ─────────────────────────────────────────────────
    view_mode = st.radio(
        'View mode', ['Side-by-side', 'Overlay'],
        horizontal=True, key=f'{p}_view_mode'
    )

    st.markdown('---')

    # ── Extract common arrays (per-result) ────────────────────────────────
    def _get_arrays(res, label):
        """Extract heatmap arrays and axis values from a result dict."""
        info = {'label': label, 'settings': {}, 'heatmap': None, 'type': 'unknown'}
        lk = res.get('likelihood', None)
        if lk is None:
            return info

        fbin_vals = res.get('fbin_grid', np.array([]))
        sigma_vals = res.get('sigma_grid', np.array([]))
        pi_vals = res.get('pi_grid', np.array([]))
        logPmax_vals = res.get('logPmax_grid', np.array([]))

        # Raw logL and observed ΔRV for AIC/BIC
        logL_raw = res.get('logL_raw', None)
        obs_delta_rv = res.get('obs_delta_rv', None)
        if obs_delta_rv is not None:
            try:
                n_obs = int(len(obs_delta_rv))
            except Exception:
                n_obs = None
        else:
            n_obs = None

        def _finalize_aicbic(info_dict, idx_tuple):
            """Fill best_logL, n_obs, k_params, aic, bic on info_dict given argmax idx."""
            # best_logL from logL_raw if shape matches lk
            _lk_local = info_dict.get('lk_full')
            if (logL_raw is not None and _lk_local is not None
                    and np.asarray(logL_raw).shape == np.asarray(_lk_local).shape):
                try:
                    info_dict['best_logL'] = float(np.asarray(logL_raw)[idx_tuple])
                except Exception:
                    pass
            # n_obs: obs_delta_rv → settings fallback → None
            _n = n_obs
            if _n is None:
                try:
                    _s_raw = res.get('settings', None)
                    _s_dict = json.loads(str(_s_raw)) if _s_raw is not None else {}
                    _ns = _s_dict.get('n_stars_sim', None)
                    if _ns is not None:
                        _n = int(_ns)
                except Exception:
                    _n = None
            if _n is not None:
                info_dict['n_obs'] = _n
            # k_params: count axes with size > 1 among candidate grids
            axes = [info_dict.get('fbin_vals'),
                    info_dict.get('sigma_vals'),
                    info_dict.get('logPmax_vals')]
            if info_dict.get('type') == 'dsilva':
                axes.append(info_dict.get('pi_vals'))
            _k = sum(1 for a in axes if a is not None and np.asarray(a).size > 1)
            info_dict['k_params'] = _k
            # AIC / BIC
            if 'best_logL' in info_dict:
                info_dict['aic'] = 2.0 * _k - 2.0 * info_dict['best_logL']
                if _n is not None and _n > 0:
                    info_dict['bic'] = _k * float(np.log(_n)) - 2.0 * info_dict['best_logL']

        if pi_vals.size > 0:
            info['type'] = 'dsilva'
            info['fbin_vals'] = fbin_vals
            info['pi_vals'] = pi_vals
            info['sigma_vals'] = sigma_vals
            info['logPmax_vals'] = logPmax_vals
            info['lk_full'] = lk

            if not np.any(np.isfinite(lk)):
                info['x_vals'] = pi_vals
                info['x_label'] = 'π'
                return info

            if lk.ndim == 4:
                flat_idx = int(np.nanargmax(lk))
                idx = np.unravel_index(flat_idx, lk.shape)
                info['best_logPmax_idx'] = idx[0]
                info['best_sigma_idx'] = idx[1]
                info['heatmap'] = lk[idx[0], idx[1]]
                info['best_fbin'] = float(fbin_vals[idx[2]])
                info['best_pi'] = float(pi_vals[idx[3]])
                info['best_sigma'] = float(sigma_vals[idx[1]]) if sigma_vals.size > 0 else None
                info['best_logPmax'] = float(logPmax_vals[idx[0]]) if logPmax_vals.size > 0 else None
                info['best_lk'] = float(lk[idx])
                _finalize_aicbic(info, idx)
            elif lk.ndim == 3:
                flat_idx = int(np.nanargmax(lk))
                idx = np.unravel_index(flat_idx, lk.shape)
                info['best_sigma_idx'] = idx[0]
                info['heatmap'] = lk[idx[0]]
                info['best_fbin'] = float(fbin_vals[idx[1]])
                info['best_pi'] = float(pi_vals[idx[2]])
                info['best_sigma'] = float(sigma_vals[idx[0]]) if sigma_vals.size > 0 else None
                info['best_lk'] = float(lk[idx])
                _finalize_aicbic(info, idx)
            elif lk.ndim == 2:
                info['heatmap'] = lk
                flat_idx = int(np.nanargmax(lk))
                idx = np.unravel_index(flat_idx, lk.shape)
                info['best_fbin'] = float(fbin_vals[idx[0]])
                info['best_pi'] = float(pi_vals[idx[1]])
                info['best_lk'] = float(lk[idx])
                _finalize_aicbic(info, idx)
            info['x_vals'] = pi_vals
            info['x_label'] = 'π'
        else:
            info['type'] = 'langer'
            info['fbin_vals'] = fbin_vals
            info['sigma_vals'] = sigma_vals
            info['x_vals'] = sigma_vals
            info['x_label'] = 'σ_single'
            info['lk_full'] = lk
            if lk.ndim == 2 and np.any(np.isfinite(lk)):
                info['heatmap'] = lk
                flat_idx = int(np.nanargmax(lk))
                idx = np.unravel_index(flat_idx, lk.shape)
                info['best_fbin'] = float(fbin_vals[idx[0]])
                info['best_sigma'] = float(sigma_vals[idx[1]])
                info['best_lk'] = float(lk[idx])
                _finalize_aicbic(info, idx)

        for _hk in ('mode_fbin', 'lo_fbin', 'hi_fbin',
                     'mode_pi', 'lo_pi', 'hi_pi',
                     'mode_sigma', 'lo_sigma', 'hi_sigma',
                     'mode_logPmax', 'lo_logPmax', 'hi_logPmax'):
            if _hk in res:
                info[_hk] = float(res[_hk])

        if 'settings' in res:
            try:
                info['settings'] = json.loads(str(res['settings']))
            except Exception:
                info['settings'] = {}
        return info

    for _r in results:
        _r['info'] = _get_arrays(_r['res'], _r['label'])

    # ── Run parameters for each result ───────────────────────────────────
    def _format_run_params(info, res):
        """Build a markdown summary of run parameters."""
        s = info.get('settings', {})
        fbin = info.get('fbin_vals', np.array([]))
        sigma = info.get('sigma_vals', np.array([]))
        logPmax = info.get('logPmax_vals', np.array([]))
        ts = str(res.get('timestamp', '—'))

        lines = []
        lines.append(f"**Model:** {info['type'].title()}")
        lines.append(f"**Timestamp:** {ts}")
        lines.append(f"**N stars:** {s.get('n_stars_sim', '—')}")
        lines.append(f"**σ_measure:** {s.get('sigma_measure', '—')} km/s")
        if fbin.size > 0:
            lines.append(f"**f_bin:** [{fbin[0]:.3f}, {fbin[-1]:.3f}] × {fbin.size} steps")
        if info['type'] == 'dsilva':
            _pi = info.get('pi_vals', np.array([]))
            if _pi.size > 0:
                lines.append(f"**π:** [{_pi[0]:.2f}, {_pi[-1]:.2f}] × {_pi.size} steps")
        if sigma.size > 0:
            if sigma.size == 1:
                lines.append(f"**σ_single:** {sigma[0]:.2f} km/s")
            else:
                lines.append(f"**σ_single:** [{sigma[0]:.2f}, {sigma[-1]:.2f}] × {sigma.size} steps")
        if logPmax.size > 0:
            if logPmax.size == 1:
                lines.append(f"**logP_max:** {logPmax[0]:.2f}")
            else:
                lines.append(f"**logP_max:** [{logPmax[0]:.2f}, {logPmax[-1]:.2f}] × {logPmax.size} steps")
        lines.append(f"**logP range:** [{s.get('logP_min', '—')}, {s.get('logP_max', '—')}]")

        orb = s.get('orbital', {})
        if orb:
            lines.append(f"**e_model:** {orb.get('e_model', '—')}, e_max={orb.get('e_max', '—')}")
            lines.append(f"**q_model:** {orb.get('q_model', '—')}, range=[{orb.get('q_range', '—')}]")
            lines.append(f"**M₁:** {orb.get('mass_primary_model', '—')}, {orb.get('mass_primary_fixed', '—')} M⊙")

        lp = s.get('langer_period_params', {})
        if lp:
            lines.append(
                f"**Period model:** C1={lp.get('dist_A','gauss')}(μ={lp.get('mu_A','—')}, σ={lp.get('sigma_A','—')}), "
                f"C2={lp.get('dist_B','logn')}(μ={lp.get('mu_B','—')}, σ={lp.get('sigma_B','—')}), "
                f"w₁={lp.get('weight_A','—')}")

        return '\n\n'.join(lines)

    _n = len(results)
    if _n <= 4:
        _param_cols = st.columns(_n)
        for _ci, (_col, _r) in enumerate(zip(_param_cols, results)):
            with _col:
                with st.expander(f'{_r["short"]} parameters', expanded=True):
                    st.markdown(_format_run_params(_r['info'], _r['res']))
    else:
        for _r in results:
            with st.expander(f'{_r["short"]}: {_r["label"]} parameters', expanded=False):
                st.markdown(_format_run_params(_r['info'], _r['res']))

    # ── Pre-compute HDI68 for all results ─────────────────────────────────
    from wr_bias_simulation import compute_hdi68 as _cmp_hdi68

    def _marginalize_1d(heatmap_2d, axis_vals, axis=1):
        """Marginalize 2D heatmap along given axis to get 1D posterior."""
        post = np.nansum(heatmap_2d, axis=axis)
        if post.sum() > 0 and len(axis_vals) == len(post):
            area = np.trapezoid(post, axis_vals)
            if area > 0:
                post = post / area
        return post

    def _get_hdi(info, param, grid, post):
        """Return (mode, lo, hi) from pre-computed keys or compute on-the-fly."""
        mk, lk, hk = f'mode_{param}', f'lo_{param}', f'hi_{param}'
        if mk in info and lk in info and hk in info:
            return info[mk], info[lk], info[hk]
        return _cmp_hdi68(grid, post)

    def _fmt_mode_err(mode, lo, hi, fmt='.4f'):
        return f'{mode:{fmt}} +{hi - mode:{fmt}} -{mode - lo:{fmt}}'

    for _r in results:
        _inf = _r['info']
        if _inf['heatmap'] is not None:
            _post_fb = _marginalize_1d(_inf['heatmap'], _inf['x_vals'], axis=1)
            _post_x = _marginalize_1d(_inf['heatmap'], _inf['fbin_vals'], axis=0)
            _xp = 'pi' if _inf['type'] == 'dsilva' else 'sigma'
            _m_fb, _lo_fb, _hi_fb = _get_hdi(_inf, 'fbin', _inf['fbin_vals'], _post_fb)
            _m_x, _lo_x, _hi_x = _get_hdi(_inf, _xp, _inf['x_vals'], _post_x)
            _r['hdi'] = {
                'fbin': (_m_fb, _lo_fb, _hi_fb),
                'x': (_m_x, _lo_x, _hi_x),
                'post_fbin': _post_fb, 'post_x': _post_x,
            }
        # Likelihood-based HDI (Dsilva+2023 proper posterior)
        _L_hm = _r['res'].get('likelihood')
        if _L_hm is not None:
            _L_hm = np.asarray(_L_hm)
            # Reduce to 2D if needed (take best sigma slice or squeeze)
            if _L_hm.ndim == 3 and _L_hm.shape[0] == 1:
                _L_hm = _L_hm[0]
            elif _L_hm.ndim == 3:
                # Multi-sigma: use slice with max total likelihood
                _sig_sums = [float(np.nansum(_L_hm[s])) for s in range(_L_hm.shape[0])]
                _best_sig = int(np.argmax(_sig_sums))
                _L_hm = _L_hm[_best_sig]
            if _L_hm.ndim == 2 and _inf.get('fbin_vals') is not None and _inf.get('x_vals') is not None:
                _Lpost_fb = _marginalize_1d(_L_hm, _inf['x_vals'], axis=1)
                _Lpost_x = _marginalize_1d(_L_hm, _inf['fbin_vals'], axis=0)
                if _Lpost_fb.sum() > 0:
                    _mL_fb, _loL_fb, _hiL_fb = _cmp_hdi68(_inf['fbin_vals'], _Lpost_fb)
                    _r.setdefault('hdi_L', {})['fbin'] = (_mL_fb, _loL_fb, _hiL_fb)
                if _Lpost_x.sum() > 0:
                    _mL_x, _loL_x, _hiL_x = _cmp_hdi68(_inf['x_vals'], _Lpost_x)
                    _r.setdefault('hdi_L', {})['x'] = (_mL_x, _loL_x, _hiL_x)

    # ── Best-fit comparison table (rows = results, cols = parameters) ─────
    st.markdown('### Best-fit comparison')

    _has_pi = any('best_pi' in _r['info'] for _r in results)
    _has_sig = any(_r['info'].get('best_sigma') is not None for _r in results)
    _has_logPmax = any(_r['info'].get('best_logPmax') is not None for _r in results)
    _has_resim_s = any(_r['res'].get('resim_S_raw') is not None for _r in results)
    _has_resim_p = any(_r['res'].get('resim_p_value') is not None for _r in results)

    _bf_rows = []
    for _r in results:
        _inf = _r['info']
        _hdi = _r['hdi']
        _row = {'Result': _r['short'], 'Model': _inf['type']}

        # f_bin + HDI
        _row['f_bin'] = f'{_inf["best_fbin"]:.4f}' if 'best_fbin' in _inf else '—'
        _row['f_bin HDI'] = _fmt_mode_err(*_hdi['fbin']) if 'fbin' in _hdi else '—'

        # π + HDI (Dsilva only)
        if _has_pi:
            _row['π'] = f'{_inf["best_pi"]:.4f}' if 'best_pi' in _inf else '—'
            _row['π HDI'] = (
                _fmt_mode_err(*_hdi['x']) if ('x' in _hdi and _inf['type'] == 'dsilva') else '—')

        # σ_single + HDI (Langer only)
        if _has_sig:
            _row['σ_single'] = f'{_inf["best_sigma"]:.2f}' if _inf.get('best_sigma') is not None else '—'
            _row['σ HDI'] = (
                _fmt_mode_err(*_hdi['x'], fmt='.2f') if ('x' in _hdi and _inf['type'] == 'langer') else '—')

        # logP_max (no HDI)
        if _has_logPmax:
            _row['logP_max'] = f'{_inf["best_logPmax"]:.2f}' if _inf.get('best_logPmax') is not None else '—'

        # p-value
        _row['Likelihood'] = f'{_inf["best_lk"]:.5f}' if 'best_lk' in _inf else '—'

        # Raw logL + model-selection stats
        _row['logL'] = f'{_inf["best_logL"]:.3f}' if 'best_logL' in _inf else '—'
        _row['k']    = str(_inf['k_params'])      if 'k_params'  in _inf else '—'
        _row['AIC']  = f'{_inf["aic"]:.2f}'       if 'aic'       in _inf else '—'
        _row['BIC']  = f'{_inf["bic"]:.2f}'       if 'bic'       in _inf else '—'

        # Re-simulation metrics
        if _has_resim_s:
            _v = _r['res'].get('resim_S_raw')
            _row['S_raw'] = f'{float(_v):.6f}' if _v is not None else '—'
        if _has_resim_p:
            _v = _r['res'].get('resim_p_value')
            _row['p (resim)'] = f'{float(_v):.4f}' if _v is not None else '—'

        _bf_rows.append(_row)

    _bf_df = pd.DataFrame(_bf_rows)

    # ΔAIC / ΔBIC relative to the best (minimum) across the selected rows
    for _col in ('AIC', 'BIC'):
        if _col in _bf_df.columns:
            _num = pd.to_numeric(_bf_df[_col], errors='coerce')
            if _num.notna().any():
                _ref = _num.min()
                _bf_df[f'Δ{_col}'] = (_num - _ref).map(
                    lambda v: f'{v:.2f}' if pd.notna(v) else '—')

    # Reorder so Δ columns sit right after their base columns
    _cols = list(_bf_df.columns)
    for _base in ('AIC', 'BIC'):
        _d = f'Δ{_base}'
        if _base in _cols and _d in _cols:
            _cols.remove(_d)
            _cols.insert(_cols.index(_base) + 1, _d)
    _bf_df = _bf_df[_cols]

    st.dataframe(_bf_df, use_container_width=True, hide_index=True)
    st.caption(
        "AIC = 2k − 2·logL   ·   BIC = k·ln(N) − 2·logL   "
        "(lower is better; ΔAIC/ΔBIC relative to best row). "
        "k = number of grid axes with >1 value in that run (fixed axes don't count). "
        "N = observed ΔRV points."
    )

    if _has_resim_s:
        st.caption('**S_raw** is the unweighted CvM distance — directly comparable across models. Lower = better fit.')

    # ── Parameter differences table ───────────────────────────────────────
    st.markdown('### Parameter differences')
    _all_sett_keys = sorted(set(
        k for _r in results for k in _r['info']['settings'].keys()))
    _diff_rows = []
    for _sk in _all_sett_keys:
        _vals = [str(_r['info']['settings'].get(_sk, '—')) for _r in results]
        _differs = len(set(_vals)) > 1
        _row_d = {'Parameter': _sk}
        for _r, _v in zip(results, _vals):
            _row_d[_r['short']] = _v
        _row_d['Differs'] = 'Yes' if _differs else ''
        _diff_rows.append(_row_d)
    if _diff_rows:
        _diff_df = pd.DataFrame(_diff_rows)

        def _highlight_diff(row):
            if row['Differs'] == 'Yes':
                return ['background-color: rgba(255, 165, 0, 0.15)'] * len(row)
            return [''] * len(row)

        st.dataframe(
            _diff_df.style.apply(_highlight_diff, axis=1),
            use_container_width=True,
            hide_index=True,
        )

    # ── Heatmaps ─────────────────────────────────────────────────────────
    _hm_results = [_r for _r in results if _r['info']['heatmap'] is not None]
    if _hm_results:
        st.markdown('### Score heatmaps')

        _all_same_type = len(set(_r['info']['type'] for _r in _hm_results)) == 1
        _all_same_shape = len(set(_r['info']['heatmap'].shape for _r in _hm_results)) == 1
        _can_overlay = _all_same_type and _all_same_shape and len(_hm_results) == 2

        if view_mode == 'Overlay' and _can_overlay:
            _ra, _rb = _hm_results[0], _hm_results[1]
            fig = go.Figure()
            fig.add_trace(go.Heatmap(
                z=_ra['info']['heatmap'],
                x=_ra['info']['x_vals'], y=_ra['info']['fbin_vals'],
                colorscale='Blues', opacity=0.6, zsmooth='best',
                name=_ra['label'],
                colorbar=dict(title=f'{_ra["short"]} score', x=1.0),
            ))
            fig.add_trace(go.Contour(
                z=_rb['info']['heatmap'],
                x=_rb['info']['x_vals'], y=_rb['info']['fbin_vals'],
                contours=dict(coloring='lines', showlabels=True),
                line=dict(color=_rb['color'], width=2, dash='dot'),
                name=_rb['label'],
                colorbar=dict(title=f'{_rb["short"]} score', x=1.12),
                showscale=True,
            ))
            fig.update_layout(**{
                **PLOTLY_THEME,
                'title': dict(text='Score overlay'),
                'xaxis_title': _ra['info']['x_label'],
                'yaxis_title': 'f<sub>bin</sub>',
                'height': 500,
            })
            st.plotly_chart(fig, use_container_width=True, key=f'{p}_hm_overlay')
        else:
            if view_mode == 'Overlay' and not _can_overlay:
                st.info('Overlay requires exactly 2 results with same model type and grid dimensions. Showing side-by-side.')
            _ncols = min(len(_hm_results), 3)
            _nrows = _math.ceil(len(_hm_results) / _ncols)
            for _ri in range(_nrows):
                _cols = st.columns(_ncols)
                for _ci, _col in enumerate(_cols):
                    _idx = _ri * _ncols + _ci
                    if _idx >= len(_hm_results):
                        break
                    _r = _hm_results[_idx]
                    with _col:
                        st.markdown(f'**{_r["short"]}: {_r["info"]["type"]}**')
                        _hm_fig = _make_heatmap_fig(
                            _r['info']['heatmap'],
                            _r['info']['fbin_vals'], _r['info']['x_vals'],
                            title=f'Score — {_r["short"]} ({_r["info"]["type"]})',
                            x_label=_r['info']['x_label'],
                            height=350,
                        )
                        st.plotly_chart(_hm_fig, use_container_width=True,
                                        key=f'{p}_hm_{_idx}')

    # ── 1D Posteriors with HDI68 errors ───────────────────────────────────
    _post_results = [_r for _r in results if 'post_fbin' in _r['hdi']]
    if _post_results:
        st.markdown('### 1D Posteriors (with 68% HDI errors)')

        def _add_hdi_shading(fig, grid, post, lo, hi, color, opacity=0.15):
            mask = (grid >= lo) & (grid <= hi)
            x_hdi = grid[mask]
            y_hdi = post[mask]
            if len(x_hdi) > 0:
                fig.add_trace(go.Scatter(
                    x=np.concatenate([x_hdi, x_hdi[::-1]]),
                    y=np.concatenate([y_hdi, np.zeros(len(y_hdi))]),
                    fill='toself', fillcolor=color,
                    line=dict(width=0), opacity=opacity,
                    showlegend=False, hoverinfo='skip',
                ))

        def _add_mode_line(fig, mode_val, color):
            fig.add_vline(x=mode_val, line=dict(color=color, width=1.5, dash='dash'))

        # f_bin posterior — all results overlaid
        fig_fb = go.Figure()
        for _r in _post_results:
            _inf = _r['info']
            _hdi = _r['hdi']
            fig_fb.add_trace(go.Scatter(
                x=_inf['fbin_vals'], y=_hdi['post_fbin'],
                mode='lines', line=dict(color=_r['color'], width=2, dash=_r['dash']),
                name=_r['short'],
            ))
            _m, _lo, _hi = _hdi['fbin']
            _add_hdi_shading(fig_fb, _inf['fbin_vals'], _hdi['post_fbin'],
                             _lo, _hi, _hex_to_rgba(_r['color'], 0.12))
            _add_mode_line(fig_fb, _m, _r['color'])
        fig_fb.update_layout(**{
            **PLOTLY_THEME,
            'title': dict(text='f<sub>bin</sub> posterior comparison'),
            'xaxis_title': 'f<sub>bin</sub>',
            'yaxis_title': 'Posterior density',
            'height': 400,
        })
        st.plotly_chart(fig_fb, use_container_width=True, key=f'{p}_post_fbin')

        # Second-axis posteriors — grouped by model type
        _dsilva_results = [_r for _r in _post_results if _r['info']['type'] == 'dsilva']
        _langer_results = [_r for _r in _post_results if _r['info']['type'] == 'langer']

        _x_groups = []
        if _dsilva_results:
            _x_groups.append(('π', _dsilva_results))
        if _langer_results:
            _x_groups.append(('σ_single', _langer_results))

        if len(_x_groups) == 2:
            _xcols = st.columns(2)
        elif len(_x_groups) == 1:
            _xcols = [st.container()]
        else:
            _xcols = []

        for (_xlabel, _group), _container in zip(_x_groups, _xcols):
            with _container:
                fig_x = go.Figure()
                for _r in _group:
                    _inf = _r['info']
                    _hdi = _r['hdi']
                    fig_x.add_trace(go.Scatter(
                        x=_inf['x_vals'], y=_hdi['post_x'],
                        mode='lines', line=dict(color=_r['color'], width=2, dash=_r['dash']),
                        name=_r['short'],
                    ))
                    _m, _lo, _hi = _hdi['x']
                    _add_hdi_shading(fig_x, _inf['x_vals'], _hdi['post_x'],
                                     _lo, _hi, _hex_to_rgba(_r['color'], 0.12))
                    _add_mode_line(fig_x, _m, _r['color'])
                fig_x.update_layout(**{
                    **PLOTLY_THEME,
                    'title': dict(text=f'{_xlabel} posterior comparison'),
                    'xaxis_title': _xlabel,
                    'yaxis_title': 'Posterior density',
                    'height': 400,
                })
                st.plotly_chart(fig_x, use_container_width=True,
                                key=f'{p}_post_x_{_xlabel}')

    # ── Likelihood-based 1D Posteriors (Dsilva+2023) ─────────────────────
    _L_post_results = [_r for _r in results
                       if _r.get('hdi_L') and 'fbin' in _r.get('hdi_L', {})]
    if _L_post_results:
        st.markdown('### 1D Posteriors — Likelihood (Dsilva+2023)')
        st.caption('Posteriors from binned multinomial likelihood. Compare with p-value posteriors above.')

        # Compute likelihood posteriors for each result
        from wr_bias_simulation import compute_hdi68 as _cmpL_hdi68

        # f_bin likelihood posterior — all results overlaid
        fig_Lfb = go.Figure()
        for _r in _L_post_results:
            _inf = _r['info']
            _L_hm = np.asarray(_r['res'].get('likelihood', []))
            if _L_hm.ndim < 2:
                continue
            if _L_hm.ndim == 3 and _L_hm.shape[0] == 1:
                _L_hm = _L_hm[0]
            elif _L_hm.ndim == 3:
                _sig_sums = [float(np.nansum(_L_hm[s])) for s in range(_L_hm.shape[0])]
                _L_hm = _L_hm[int(np.argmax(_sig_sums))]
            _Lp_fb = np.nansum(_L_hm, axis=1)
            _Lp_fb_area = float(np.trapezoid(_Lp_fb, _inf['fbin_vals']))
            if _Lp_fb_area > 0:
                _Lp_fb = _Lp_fb / _Lp_fb_area
            fig_Lfb.add_trace(go.Scatter(
                x=_inf['fbin_vals'], y=_Lp_fb,
                mode='lines', line=dict(color=_r['color'], width=2, dash=_r['dash']),
                name=_r['short'],
            ))
            _mLfb, _loLfb, _hiLfb = _r['hdi_L']['fbin']
            _add_hdi_shading(fig_Lfb, _inf['fbin_vals'], _Lp_fb,
                             _loLfb, _hiLfb, _hex_to_rgba(_r['color'], 0.12))
            _add_mode_line(fig_Lfb, _mLfb, _r['color'])
        fig_Lfb.update_layout(**{
            **PLOTLY_THEME,
            'title': dict(text='f<sub>bin</sub> posterior (Likelihood)'),
            'xaxis_title': 'f<sub>bin</sub>',
            'yaxis_title': 'Posterior density',
            'height': 400,
        })
        st.plotly_chart(fig_Lfb, use_container_width=True, key=f'{p}_Lpost_fbin')

    # ── Observed ΔRV CDF comparison ──────────────────────────────────────
    st.markdown('### Observed ΔRV CDF')
    st.caption('The observed ΔRV distribution is the same for all results (same dataset).')
    _obs = None
    for _r in results:
        _obs = _r['res'].get('obs_delta_rv', None)
        if _obs is not None:
            break
    if _obs is not None:
        obs_sorted = np.sort(_obs)
        obs_cdf_y = np.arange(1, len(obs_sorted) + 1) / len(obs_sorted)
        fig_cdf = go.Figure()
        fig_cdf.add_trace(go.Scatter(
            x=obs_sorted, y=obs_cdf_y,
            mode='lines+markers', line=dict(color='black', width=2),
            marker=dict(size=5),
            name='Observed ΔRV',
        ))
        # Overlay best-fit simulated CDFs if available (cadence-aware results)
        for _r in results:
            _bcdf = _r['res'].get('best_median_cdf')
            _be = _r['res'].get('bin_edges')
            if _bcdf is not None and _be is not None:
                fig_cdf.add_trace(go.Scatter(
                    x=np.asarray(_be), y=np.asarray(_bcdf),
                    mode='lines', line=dict(color=_r['color'], width=2, dash=_r['dash']),
                    name=f'{_r["short"]} sim CDF',
                ))
        fig_cdf.update_layout(**{
            **PLOTLY_THEME,
            'title': dict(text='Observed ΔRV CDF'),
            'xaxis_title': 'ΔRV (km/s)',
            'yaxis_title': 'Cumulative fraction',
            'height': 400,
        })
        st.plotly_chart(fig_cdf, use_container_width=True, key=f'{p}_cdf_obs')
    else:
        st.info('No observed ΔRV data found in results.')




