"""bc.render_validation — Validation tab UI (tasks #160/#161).

Uses render_model_subtabs() to share all cadence-tab analysis plots.
"""
from __future__ import annotations

import os
import sys
import threading

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
    settings_hash, make_heatmap_fig,
    PLOTLY_THEME, get_palette,
)

# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def _render_validation_tab(p: str, settings: dict, sm) -> None:
    """Render the Validation tab for parameter recovery testing."""
    st.markdown('### Parameter Recovery Validation')
    st.caption(
        'Test whether the likelihood pipeline can recover known "true" parameters '
        'from synthetic (mock) observations. A low recovery score means good recovery.'
    )

    # Load real cadence data (needed for mock generation)
    sh = settings_hash(settings) if settings else ''
    try:
        _, _ = cached_load_observed_delta_rvs(sh)
        cadence_list, cadence_weights = cached_load_cadence(sh)
    except Exception as exc:
        st.error(f'Cannot load cadence data: {exc}')
        return

    # ── Model selector ────────────────────────────────────────────────────
    model_choice = st.radio(
        'Period model',
        ['Dsilva (power-law)', 'Langer 2020'],
        horizontal=True,
        key=f'{p}_val_model',
    )
    is_dsilva = model_choice.startswith('Dsilva')
    period_model = 'powerlaw' if is_dsilva else 'langer2020'

    # ── Mode tabs ─────────────────────────────────────────────────────────
    single_tab, batch_tab = st.tabs(['Single-Point Recovery', 'Batch Sweep'])

    with single_tab:
        _render_single_point(p, is_dsilva, period_model, cadence_list,
                             cadence_weights, settings, sm)

    with batch_tab:
        _render_batch_sweep(p, is_dsilva, period_model, cadence_list,
                            cadence_weights, settings, sm)


# ─────────────────────────────────────────────────────────────────────────────
# Single-point recovery UI
# ─────────────────────────────────────────────────────────────────────────────

def _render_single_point(
    p: str,
    is_dsilva: bool,
    period_model: str,
    cadence_list: list,
    cadence_weights,
    settings: dict,
    sm,
) -> None:
    """Single-point recovery: set true params -> generate mock -> grid search -> score."""
    from wr_bias_simulation import BinaryParameterConfig

    st.markdown('#### True Parameters')
    st.caption('Set the "ground truth" parameters. The pipeline will try to recover these.')

    c1, c2, c3, c4 = st.columns(4)
    true_fbin = c1.slider('True f_bin', 0.05, 1.0, 0.46, 0.01,
                          key=f'{p}_val_true_fbin')
    if is_dsilva:
        true_pi = c2.slider('True pi', -3.0, 3.0, 0.0, 0.1,
                             key=f'{p}_val_true_pi')
    else:
        true_pi = 0.0
        c2.info('pi not used for Langer model')

    true_sigma = c3.slider('True sigma_single (km/s)', 1.0, 40.0, 15.0, 0.5,
                           key=f'{p}_val_true_sigma')
    true_logPmax = c4.slider('True logP_max', 1.0, 6.0, 4.0, 0.1,
                             key=f'{p}_val_true_logPmax')

    # ── Grid settings (user-configurable ranges) ──────────────────────────
    with st.expander('Grid settings', expanded=False):
        st.caption('Configure the search grid ranges and resolution.')
        # f_bin grid
        fc1, fc2, fc3 = st.columns(3)
        fb_min = fc1.number_input('f_bin min', 0.0, 1.0, 0.0, 0.01,
                                  key=f'{p}_val_fb_min')
        fb_max = fc2.number_input('f_bin max', 0.0, 1.0, 1.0, 0.01,
                                  key=f'{p}_val_fb_max')
        n_fbin = fc3.number_input('f_bin steps', 5, 200, 25, 5,
                                  key=f'{p}_val_nfbin')

        # pi grid (Dsilva only)
        if is_dsilva:
            pc1, pc2, pc3 = st.columns(3)
            pi_min = pc1.number_input('pi min', -5.0, 5.0, -3.0, 0.1,
                                      key=f'{p}_val_pi_min')
            pi_max = pc2.number_input('pi max', -5.0, 5.0, 3.0, 0.1,
                                      key=f'{p}_val_pi_max')
            n_pi = pc3.number_input('pi steps', 5, 200, 15, 5,
                                    key=f'{p}_val_npi')
        else:
            n_pi = 1
            pi_min = 0.0
            pi_max = 0.0

        # sigma grid
        sgc1, sgc2, sgc3 = st.columns(3)
        sig_min = sgc1.number_input('sigma min (km/s)', 0.1, 50.0, 1.0, 0.5,
                                    key=f'{p}_val_sig_min')
        sig_max = sgc2.number_input('sigma max (km/s)', 0.1, 50.0, 40.0, 0.5,
                                    key=f'{p}_val_sig_max')
        n_sigma = sgc3.number_input('sigma steps', 1, 50, 1, 1,
                                    key=f'{p}_val_nsigma')

        gc1, gc2 = st.columns(2)
        n_sets = gc1.number_input('N_sets per point', 100, 50000, 500, 100,
                                  key=f'{p}_val_nsets')
        seed = gc2.number_input('Random seed', 1, 99999, 42, 1,
                                key=f'{p}_val_seed')

        sc1, sc2 = st.columns(2)
        sigma_meas = sc1.number_input('sigma_meas (km/s)', 0.1, 10.0, 1.622, 0.1,
                                      key=f'{p}_val_sigma_meas')

    # Build grids from user-specified ranges
    fbin_grid = np.linspace(float(fb_min), float(fb_max), int(n_fbin))
    if is_dsilva:
        pi_grid = np.linspace(float(pi_min), float(pi_max), int(n_pi))
    else:
        pi_grid = np.array([0.0])

    if int(n_sigma) > 1:
        sigma_grid = np.linspace(float(sig_min), float(sig_max), int(n_sigma))
    else:
        sigma_grid = np.array([true_sigma])

    # Build bin_cfg
    e_model = 'flat' if is_dsilva else 'zero'
    bin_cfg = BinaryParameterConfig(
        logP_min=0.15,
        logP_max=true_logPmax,
        period_model=period_model,
        e_model=e_model,
        e_max=0.9,
    )

    # ── Run button ────────────────────────────────────────────────────────
    run_btn = st.button('Run Single-Point Validation', type='primary',
                        key=f'{p}_val_run_single')

    # Check for running job
    job_key = f'{p}_val_single_job'
    result_key = f'{p}_val_single_result'

    if run_btn:
        st.session_state.pop(result_key, None)
        progress_dict = {'progress': 0.0, 'done': False, 'result': None}
        st.session_state[job_key] = progress_dict

        def _worker():
            from bc.validation import run_single_validation
            try:
                vp = run_single_validation(
                    true_fbin=true_fbin,
                    true_pi=true_pi,
                    true_sigma=true_sigma,
                    true_logPmax=true_logPmax,
                    fbin_grid=fbin_grid,
                    pi_grid=pi_grid,
                    sigma_grid=sigma_grid,
                    cadence_library=cadence_list,
                    cadence_weights=cadence_weights,
                    sigma_meas=float(sigma_meas),
                    bin_cfg=bin_cfg,
                    period_model=period_model,
                    seed=int(seed),
                    n_sets=int(n_sets),
                    progress_callback=lambda frac: progress_dict.update(
                        {'progress': frac}),
                )
                progress_dict['result'] = vp
            except Exception as exc:
                progress_dict['error'] = str(exc)
            finally:
                progress_dict['done'] = True

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        st.rerun()

    # ── Poll running job ──────────────────────────────────────────────────
    job = st.session_state.get(job_key)
    if job is not None and not job.get('done', False):
        _poll_single_job(p)
        return

    # If job just finished, extract result
    if job is not None and job.get('done', False):
        if 'error' in job:
            st.error(f'Validation failed: {job["error"]}')
            st.session_state.pop(job_key, None)
            return
        if job.get('result') is not None:
            st.session_state[result_key] = job['result']
        st.session_state.pop(job_key, None)

    # ── Display results ───────────────────────────────────────────────────
    vp = st.session_state.get(result_key)
    if vp is None:
        st.info('Set true parameters and click **Run** to test parameter recovery.')
        return

    _display_single_result(p, vp, is_dsilva, period_model, cadence_list,
                           cadence_weights, settings)


@st.fragment(run_every=3)
def _poll_single_job(p: str) -> None:
    """Poll background validation job — displays live progress bar."""
    job_key = f'{p}_val_single_job'
    job = st.session_state.get(job_key)
    if job is None:
        return
    if job.get('done', False):
        st.rerun(scope='app')
    else:
        prog = job.get('progress', 0.0)
        st.progress(prog, text=f'Grid search: {prog:.0%} complete')


def _display_single_result(
    p: str, vp, is_dsilva: bool, period_model: str,
    cadence_list: list, cadence_weights, settings: dict,
) -> None:
    """Display results of a single-point validation with full cadence-tab plots."""
    pal = get_palette()

    # ── Recovery score metric ─────────────────────────────────────────────
    score = vp.recovery_score
    if score < 0.05:
        score_label = 'Excellent'
    elif score < 0.15:
        score_label = 'Good'
    elif score < 0.30:
        score_label = 'Fair'
    else:
        score_label = 'Poor'

    m1, m2, m3 = st.columns(3)
    m1.metric('Recovery Score', f'{score:.4f}',
              help='0 = perfect recovery, 1 = worst possible')
    m2.metric('Quality', score_label)
    m3.metric('Seed', vp.seed)

    # ── Per-parameter breakdown table ─────────────────────────────────────
    st.markdown('##### Per-Parameter Breakdown')
    rows = []
    for name, info in vp.per_param.items():
        rows.append({
            'Parameter': name,
            'True': f'{info["true"]:.4f}',
            'Recovered': f'{info["recovered"]:.4f}',
            'Abs Error': f'{info["abs_error"]:.4f}',
            'Norm Distance': f'{info["distance"]:.4f}',
            'Grid Points': info['weight'],
        })
    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

    # ── Likelihood heatmap with true + recovered marked ───────────────────
    st.markdown('##### Likelihood Heatmap')
    st.caption('Star = true parameters, circle = recovered best-fit.')

    lk_2d = vp.likelihood_grid
    fbin_g = vp.fbin_grid
    x_g = vp.x_grid

    if is_dsilva:
        x_label = 'pi (period power-law index)'
        x_name = 'pi'
        true_x = vp.true_pi
        rec_x = vp.rec_pi
    else:
        x_label = 'sigma_single (km/s)'
        x_name = 'sigma'
        true_x = vp.true_sigma
        rec_x = vp.rec_sigma

    fig = make_heatmap_fig(
        lk_2d, fbin_g, x_g,
        title='Likelihood — Validation Recovery',
        height=520,
        x_label=x_label,
        y_label='f_bin (intrinsic binary fraction)',
        x_name=x_name,
        scoring_label='Likelihood',
        colorbar_title_override='log-Likelihood',
    )

    # Add true-parameter marker (star)
    fig.add_trace(go.Scatter(
        x=[true_x], y=[vp.true_fbin],
        mode='markers+text',
        marker=dict(symbol='star', size=18, color='lime',
                    line=dict(width=2, color='black')),
        text=['TRUE'], textposition='top center',
        textfont=dict(size=12, color='lime'),
        name='True',
        showlegend=True,
    ))

    # Add recovered-parameter marker (circle)
    fig.add_trace(go.Scatter(
        x=[rec_x], y=[vp.rec_fbin],
        mode='markers+text',
        marker=dict(symbol='circle', size=14, color='red',
                    line=dict(width=2, color='white')),
        text=['REC'], textposition='bottom center',
        textfont=dict(size=12, color='red'),
        name='Recovered',
        showlegend=True,
    ))

    st.plotly_chart(fig, use_container_width=True, key=f'{p}_val_heatmap')

    # ── Full cadence-tab analysis plots via render_model_subtabs ──────────
    st.markdown('---')
    st.markdown('##### Full Analysis (same tools as cadence tabs)')
    _render_shared_analysis(p, vp, is_dsilva, period_model,
                            cadence_list, cadence_weights, settings)


def _render_shared_analysis(
    p: str, vp, is_dsilva: bool, period_model: str,
    cadence_list: list, cadence_weights, settings: dict,
) -> None:
    """Build model_ctx from validation result and call render_model_subtabs."""
    from wr_bias_simulation import SimulationConfig, BinaryParameterConfig, simulate_with_params
    from bc.subtabs import render_model_subtabs

    lk_arr = vp.full_likelihood
    fbin_grid, pi_grid, sigma_grid = vp.fbin_grid, vp.pi_grid, vp.sigma_grid
    mock_drv = vp.mock_delta_rv

    if not np.any(np.isfinite(lk_arr)):
        st.warning('No finite likelihood values — cannot run analysis.')
        return

    flat_best = int(np.nanargmax(lk_arr))
    n_sig, n_fb, n_pi = lk_arr.shape
    best_sig_idx = flat_best // (n_fb * n_pi)
    best_fb_idx = (flat_best // n_pi) % n_fb
    best_pi_idx = flat_best % n_pi
    best_fbin = float(fbin_grid[best_fb_idx])
    best_pi = float(pi_grid[best_pi_idx]) if is_dsilva else 0.0
    best_sigma = float(sigma_grid[best_sig_idx])

    # ndim_mode and x-axis
    _is_langer_sigma = (not is_dsilva) and len(sigma_grid) > 1
    if _is_langer_sigma:
        ndim_mode, x_g, x_name = 'cadence_langer', sigma_grid, 'sigma'
        x_label, x_disp = 'sigma_single', 'sigma_single (km/s)'
    elif is_dsilva:
        ndim_mode, x_g, x_name = 'cadence_dsilva', pi_grid, 'pi'
        x_label, x_disp = 'pi', 'pi (period power-law index)'
    else:
        ndim_mode, x_g, x_name = 'cadence_langer', sigma_grid, 'sigma'
        x_label, x_disp = 'sigma_single', 'sigma_single (km/s)'

    result = {
        'likelihood': lk_arr, 'fbin_grid': fbin_grid,
        'pi_grid': pi_grid, 'sigma_grid': sigma_grid,
        'obs_delta_rv': mock_drv,
        'sigma_meas': float(st.session_state.get(f'{p}_val_sigma_meas', 1.622)),
        'cadence_library': cadence_list,
    }

    e_model = 'flat' if is_dsilva else 'zero'
    bin_cfg = BinaryParameterConfig(
        logP_min=0.15, logP_max=vp.true_logPmax,
        period_model=period_model, e_model=e_model, e_max=0.9,
    )

    # gap_sim at best-fit
    sigma_meas_val = float(st.session_state.get(f'{p}_val_sigma_meas', 1.622))
    fp_key, gap_key = f'{p}_val_gap_fp', f'{p}_val_gap_sim'
    gap_fp = (best_fbin, best_pi, best_sigma, vp.true_logPmax, lk_arr.shape)
    if st.session_state.get(fp_key) != gap_fp or gap_key not in st.session_state:
        sim_cfg = SimulationConfig(
            n_stars=10000, sigma_single=best_sigma, sigma_measure=sigma_meas_val,
            cadence_library=cadence_list, cadence_weights=cadence_weights,
        )
        st.session_state[gap_key] = simulate_with_params(
            best_fbin, best_pi, sim_cfg, bin_cfg, np.random.default_rng(42))
        st.session_state[fp_key] = gap_fp
    gap_sim = st.session_state[gap_key]

    # outer slices
    outer_list = []
    if len(sigma_grid) > 1:
        outer_list.append(best_sig_idx)
    elif lk_arr.ndim == 3 and not is_dsilva:
        outer_list.append(0)
    disp_outer = tuple(outer_list) if outer_list else None

    cls = (settings or {}).get('classification', {})
    val_prefix = f'{p}_vr'

    model_ctx = {
        'model_type': 'cadence_dsilva' if is_dsilva else 'cadence_langer',
        'ndim_mode': ndim_mode, 'x_name': x_name,
        'x_label': x_label, 'x_display_label': x_disp,
        'period_model': period_model, 'has_case_AB': not is_dsilva,
        'result': result, 'fbin_g': fbin_grid, 'x_g': np.asarray(x_g),
        'sigma_g': np.asarray(sigma_grid),
        'logPmax_g': np.array([vp.true_logPmax]),
        'gap_sim': gap_sim, 'obs_delta_rv': mock_drv, 'obs_detail': None,
        'cadence_list': cadence_list, 'cadence_weights': cadence_weights,
        'n_stars_sim': 10000, 'sigma_meas': sigma_meas_val, 'bin_cfg': bin_cfg,
        'logP_min': 0.15, 'logP_max': vp.true_logPmax,
        'thresh_dRV': float(cls.get('threshold_dRV', 45.5)),
        'canvas_height': 520, 'canvas_width': None, 'use_container_width': True,
        'disp_outer_slices': disp_outer,
        'settings': settings or {}, 'classification': cls,
    }
    render_model_subtabs(val_prefix, model_ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Batch sweep UI (Task #161)
# ─────────────────────────────────────────────────────────────────────────────

def _render_batch_sweep(
    p: str,
    is_dsilva: bool,
    period_model: str,
    cadence_list: list,
    cadence_weights,
    settings: dict,
    sm,
) -> None:
    """Batch sweep: test recovery across a grid of true parameter values."""
    from wr_bias_simulation import BinaryParameterConfig

    st.markdown('#### Batch Sweep Settings')
    st.caption(
        'Test parameter recovery at many true-parameter combinations. '
        'Produces a heatmap showing where the pipeline is reliable.'
    )

    # ── True parameter sweep grid ─────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    n_true_fbin = c1.number_input('True f_bin points', 3, 10, 5, 1,
                                  key=f'{p}_val_batch_nfbin')
    if is_dsilva:
        n_true_pi = c2.number_input('True pi points', 3, 10, 5, 1,
                                    key=f'{p}_val_batch_npi')
    else:
        n_true_pi = 1
        c2.info('pi = 1 for Langer')
    n_true_sigma = c3.number_input('True sigma points', 1, 5, 1, 1,
                                   key=f'{p}_val_batch_nsigma')

    true_fbin_vals = np.linspace(0.1, 0.9, int(n_true_fbin))
    true_pi_vals = np.linspace(-2.0, 2.0, int(n_true_pi)) if is_dsilva else np.array([0.0])
    true_sigma_vals = np.linspace(5.0, 30.0, int(n_true_sigma)) if int(n_true_sigma) > 1 else np.array([15.0])

    n_total = len(true_fbin_vals) * len(true_pi_vals) * len(true_sigma_vals)
    st.info(f'Total test points: **{n_total}** '
            f'({len(true_fbin_vals)} f_bin x {len(true_pi_vals)} pi x {len(true_sigma_vals)} sigma)')

    # ── Recovery grid settings (user-configurable ranges) ─────────────────
    with st.expander('Recovery grid settings', expanded=False):
        st.caption('Configure the recovery search grid ranges.')
        fc1, fc2, fc3 = st.columns(3)
        rec_fb_min = fc1.number_input('f_bin min', 0.0, 1.0, 0.0, 0.01,
                                      key=f'{p}_val_batch_fb_min')
        rec_fb_max = fc2.number_input('f_bin max', 0.0, 1.0, 1.0, 0.01,
                                      key=f'{p}_val_batch_fb_max')
        rec_n_fbin = fc3.number_input('f_bin steps', 5, 100, 15, 5,
                                      key=f'{p}_val_batch_rec_nfbin')
        if is_dsilva:
            pc1, pc2, pc3 = st.columns(3)
            rec_pi_min = pc1.number_input('pi min', -5.0, 5.0, -3.0, 0.1,
                                          key=f'{p}_val_batch_pi_min')
            rec_pi_max = pc2.number_input('pi max', -5.0, 5.0, 3.0, 0.1,
                                          key=f'{p}_val_batch_pi_max')
            rec_n_pi = pc3.number_input('pi steps', 5, 60, 10, 5,
                                        key=f'{p}_val_batch_rec_npi')
        else:
            rec_n_pi = 1
            rec_pi_min = 0.0
            rec_pi_max = 0.0
        rec_n_sets = st.number_input('N_sets per grid point', 100, 50000, 300, 100,
                                     key=f'{p}_val_batch_nsets')

    sc1, sc2 = st.columns(2)
    batch_logPmax = sc1.slider('True logP_max (fixed)', 1.0, 6.0, 4.0, 0.1,
                               key=f'{p}_val_batch_logPmax')
    batch_sigma_meas = sc2.number_input('sigma_meas (km/s)', 0.1, 10.0, 1.622, 0.1,
                                        key=f'{p}_val_batch_sigma_meas')

    # Build recovery grids from user-specified ranges
    rec_fbin_grid = np.linspace(float(rec_fb_min), float(rec_fb_max), int(rec_n_fbin))
    if is_dsilva:
        rec_pi_grid = np.linspace(float(rec_pi_min), float(rec_pi_max), int(rec_n_pi))
    else:
        rec_pi_grid = np.array([0.0])
    rec_sigma_grid = np.array([15.0])  # single sigma for speed in batch

    e_model = 'flat' if is_dsilva else 'zero'
    bin_cfg = BinaryParameterConfig(
        logP_min=0.15,
        logP_max=float(batch_logPmax),
        period_model=period_model,
        e_model=e_model,
        e_max=0.9,
    )

    # ── Run button ────────────────────────────────────────────────────────
    run_btn = st.button('Run Batch Sweep', type='primary',
                        key=f'{p}_val_run_batch')

    batch_job_key = f'{p}_val_batch_job'
    batch_result_key = f'{p}_val_batch_result'

    if run_btn:
        st.session_state.pop(batch_result_key, None)
        progress_dict = {'n_done': 0, 'n_total': n_total,
                         'done': False, 'current_point': '', 'result': None}
        st.session_state[batch_job_key] = progress_dict

        def _batch_worker():
            from bc.validation import run_batch_validation
            try:
                result = run_batch_validation(
                    true_fbin_vals=true_fbin_vals,
                    true_pi_vals=true_pi_vals,
                    true_sigma_vals=true_sigma_vals,
                    true_logPmax=float(batch_logPmax),
                    fbin_grid=rec_fbin_grid,
                    pi_grid=rec_pi_grid,
                    sigma_grid=rec_sigma_grid,
                    cadence_library=cadence_list,
                    cadence_weights=cadence_weights,
                    sigma_meas=float(batch_sigma_meas),
                    bin_cfg=bin_cfg,
                    period_model=period_model,
                    n_sets=int(rec_n_sets),
                    progress_dict=progress_dict,
                )
                progress_dict['result'] = result
            except Exception as exc:
                progress_dict['error'] = str(exc)
            finally:
                progress_dict['done'] = True

        thread = threading.Thread(target=_batch_worker, daemon=True)
        thread.start()
        st.rerun()

    # ── Poll running batch job ────────────────────────────────────────────
    job = st.session_state.get(batch_job_key)
    if job is not None and not job.get('done', False):
        _poll_batch_job(p)
        return

    # If job just finished
    if job is not None and job.get('done', False):
        if 'error' in job:
            st.error(f'Batch sweep failed: {job["error"]}')
            st.session_state.pop(batch_job_key, None)
            return
        if job.get('result') is not None:
            st.session_state[batch_result_key] = job['result']
        st.session_state.pop(batch_job_key, None)

    # ── Display batch results ─────────────────────────────────────────────
    batch = st.session_state.get(batch_result_key)
    if batch is None:
        st.info('Configure sweep parameters and click **Run Batch Sweep**.')
        return

    _display_batch_result(p, batch, is_dsilva)


@st.fragment(run_every=3)
def _poll_batch_job(p: str) -> None:
    """Poll background batch validation job — displays live progress bar."""
    job_key = f'{p}_val_batch_job'
    job = st.session_state.get(job_key)
    if job is None:
        return
    if job.get('done', False):
        st.rerun(scope='app')
    else:
        n_done = job.get('n_done', 0)
        n_tot = job.get('n_total', 1)
        cur = job.get('current_point', '')
        st.progress(n_done / max(n_tot, 1),
                    text=f'Batch sweep: {n_done}/{n_tot} — {cur}')


def _display_batch_result(p: str, batch, is_dsilva: bool) -> None:
    """Display batch sweep results."""
    from bc.validation import batch_to_recovery_heatmap

    st.markdown('##### Recovery Quality Heatmap')

    if is_dsilva:
        st.caption(
            'Mean recovery score per (f_bin, pi) cell, marginalized over sigma. '
            'Green = good recovery, red = poor recovery.'
        )
    else:
        st.caption(
            'Mean recovery score per (f_bin, sigma) cell. '
            'Green = good recovery, red = poor recovery.'
        )

    scores_2d, y_vals, x_vals = batch_to_recovery_heatmap(batch, is_dsilva)

    # Custom heatmap with green-yellow-red color scale
    fig = go.Figure(data=go.Heatmap(
        z=scores_2d,
        x=np.round(x_vals, 3),
        y=np.round(y_vals, 3),
        colorscale=[
            [0.0, '#2ECC71'],    # green = good (low score)
            [0.15, '#82E0AA'],
            [0.30, '#F7DC6F'],   # yellow = fair
            [0.50, '#F0B27A'],
            [1.0, '#E74C3C'],    # red = poor (high score)
        ],
        colorbar=dict(title='Recovery<br>Score'),
        zmin=0.0,
        zmax=max(0.5, float(np.nanmax(scores_2d)) if np.any(np.isfinite(scores_2d)) else 0.5),
        hovertemplate=(
            'x: %{x:.3f}<br>y: %{y:.3f}<br>'
            'Score: %{z:.4f}<extra></extra>'
        ),
    ))

    x_title = 'True pi' if is_dsilva else 'True sigma_single (km/s)'
    fig.update_layout(**{**PLOTLY_THEME,
        'title': dict(text='Recovery Quality Across Parameter Space'),
        'xaxis': {**PLOTLY_THEME.get('xaxis', {}), 'title': x_title},
        'yaxis': {**PLOTLY_THEME.get('yaxis', {}), 'title': 'True f_bin'},
        'height': 520,
    })

    st.plotly_chart(fig, use_container_width=True, key=f'{p}_val_batch_heatmap')

    # ── Summary statistics ────────────────────────────────────────────────
    st.markdown('##### Summary Statistics')

    scores_flat = np.array([pt.recovery_score for pt in batch.points])
    finite = scores_flat[np.isfinite(scores_flat)]

    if len(finite) > 0:
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric('Mean Score', f'{np.mean(finite):.4f}')
        mc2.metric('Median Score', f'{np.median(finite):.4f}')
        mc3.metric('Best (min)', f'{np.min(finite):.4f}')
        mc4.metric('Worst (max)', f'{np.max(finite):.4f}')

        good_frac = np.mean(finite < 0.10)
        fair_frac = np.mean((finite >= 0.10) & (finite < 0.25))
        poor_frac = np.mean(finite >= 0.25)

        qc1, qc2, qc3 = st.columns(3)
        qc1.metric('Good (< 0.10)', f'{good_frac:.0%}')
        qc2.metric('Fair (0.10-0.25)', f'{fair_frac:.0%}')
        qc3.metric('Poor (> 0.25)', f'{poor_frac:.0%}')

    # ── Detailed results table ────────────────────────────────────────────
    with st.expander('Detailed Results Table', expanded=False):
        rows = []
        for pt in batch.points:
            row = {
                'True f_bin': pt.true_fbin,
                'True pi': pt.true_pi,
                'True sigma': pt.true_sigma,
                'Rec f_bin': pt.rec_fbin,
                'Rec pi': pt.rec_pi,
                'Rec sigma': pt.rec_sigma,
                'Score': pt.recovery_score,
            }
            rows.append(row)
        if rows:
            df = pd.DataFrame(rows)

            def _color_score(val):
                if not isinstance(val, (int, float)) or np.isnan(val):
                    return ''
                if val < 0.10:
                    return 'background-color: rgba(46, 204, 113, 0.3)'
                elif val < 0.25:
                    return 'background-color: rgba(247, 220, 111, 0.3)'
                else:
                    return 'background-color: rgba(231, 76, 60, 0.3)'

            styled = df.style.map(_color_score, subset=['Score'])
            st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Score distribution histogram ──────────────────────────────────────
    st.markdown('##### Score Distribution')
    if len(finite) > 0:
        fig_hist = go.Figure(data=go.Histogram(
            x=finite,
            nbinsx=20,
            marker_color='#4A90D9',
            opacity=0.8,
        ))
        fig_hist.update_layout(**{**PLOTLY_THEME,
            'title': dict(text='Distribution of Recovery Scores'),
            'xaxis': {**PLOTLY_THEME.get('xaxis', {}),
                      'title': 'Recovery Score'},
            'yaxis': {**PLOTLY_THEME.get('yaxis', {}),
                      'title': 'Count'},
            'height': 350,
        })
        st.plotly_chart(fig_hist, use_container_width=True,
                        key=f'{p}_val_batch_hist')
