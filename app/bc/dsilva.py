"""bc.dsilva — Dsilva (power-law) bias correction tab renderer."""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
import threading

import numpy as np
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from shared import (
    cached_load_observed_delta_rvs, cached_load_cadence,
    cached_load_grid_result, settings_hash,
)

from bc.helpers import (
    _METHOD_SCORING_LABELS, _METHOD_COLORBAR_OVERRIDE,
    _RESULT_DIR,
    _fmt_eta, _result_path,
    _build_descriptive_filename,
    _scan_partial_metadata, _render_partial_table,
    _scan_result_metadata,
    _make_max_pval_fig,
    _make_heatmap_fig,
)
from bc.params import _render_orbital_params_dsilva
from bc.runners import _run_dsilva_bg
from bc.extras import _render_error_model_selector

# Dsilva tab
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Dsilva tab renderer
# ─────────────────────────────────────────────────────────────────────────────
def _render_dsilva_tab(p: str, settings: dict, sm) -> None:
    """Render a Dsilva (power-law) bias correction tab.

    Parameters
    ----------
    p : str
        Unique prefix for session-state keys (e.g. 'bc', 'bc2').
    settings : dict
        User settings dict.
    sm : SettingsManager
        Settings manager (saves only when p is the primary prefix 'bc').
    """
    _is_primary = (p == 'bc')  # only primary tab saves to settings file
    _ch = int(st.session_state.get('bc_canvas_height', 520))
    _cw_raw = int(st.session_state.get('bc_canvas_width', 0))
    _cw = _cw_raw if _cw_raw > 0 else None
    _use_cw = (_cw is None)
    gcfg   = settings.get('grid_dsilva', {})
    simcfg = settings.get('simulation', {})
    cls    = settings.get('classification', {})
    orb    = gcfg.get('orbital', {})

    # Pre-initialise session_state from settings (only on first visit)
    _bc_grid_defaults = {
        f'{p}_fbin_min':   float(gcfg.get('fbin_min', 0.01)),
        f'{p}_fbin_max':   float(gcfg.get('fbin_max', 0.99)),
        f'{p}_fbin_steps': int(gcfg.get('fbin_steps', 137)),
        f'{p}_pi_min':     float(gcfg.get('pi_min', -3.0)),
        f'{p}_pi_max':     float(gcfg.get('pi_max', 3.0)),
        f'{p}_pi_steps':   int(gcfg.get('pi_steps', 249)),
        f'{p}_n_stars':    int(gcfg.get('n_stars_sim', 3000)),
        f'{p}_sigma_meas': float(simcfg.get('sigma_measure', 1.622)),
        f'{p}_logP_min':   float(orb.get('logP_min', gcfg.get('logP_min', 0.15))),
        f'{p}_logP_max':   float(orb.get('logP_max', gcfg.get('logP_max', 5.0))),
        f'{p}_e_max':      float(orb.get('e_max', 0.9)),
        f'{p}_mass_fixed': float(orb.get('mass_primary_fixed', 10.0)),
        f'{p}_q_min':      float(orb.get('q_range', [0.1, 2.0])[0]),
        f'{p}_q_max':      float(orb.get('q_range', [0.1, 2.0])[1]),
        f'{p}_lq_mu':      float(orb.get('langer_q_mu', 0.7)),
        f'{p}_lq_sig':     float(orb.get('langer_q_sigma', 0.2)),
    }
    for _k, _v in _bc_grid_defaults.items():
        if _k not in st.session_state:
            st.session_state[_k] = _v

    col_left, col_right = st.columns([0.30, 0.70])

    # ── Left column: grid parameters (compact 3-col layout) ────────────────
    with col_left:
        with st.expander('⚙️ Grid parameters', expanded=True):
            st.markdown('**f_bin**')
            _fc1, _fc2, _fc3 = st.columns(3)
            fbin_min = _fc1.number_input(
                'min', 0.0, 0.5, float(gcfg.get('fbin_min', 0.01)), 0.01,
                key=f'{p}_fbin_min',
                on_change=lambda: sm.save(['grid_dsilva', 'fbin_min'],
                                          value=st.session_state[f'{p}_fbin_min']))
            fbin_max = _fc2.number_input(
                'max', 0.5, 1.0, float(gcfg.get('fbin_max', 0.99)), 0.01,
                key=f'{p}_fbin_max',
                on_change=lambda: sm.save(['grid_dsilva', 'fbin_max'],
                                          value=st.session_state[f'{p}_fbin_max']))
            fbin_steps = _fc3.number_input(
                'steps', 10, 500, int(gcfg.get('fbin_steps', 137)), 1,
                key=f'{p}_fbin_steps',
                on_change=lambda: sm.save(['grid_dsilva', 'fbin_steps'],
                                          value=st.session_state[f'{p}_fbin_steps']))

            st.markdown('**π (period power-law index)**')
            _pc1, _pc2, _pc3 = st.columns(3)
            pi_min = _pc1.number_input(
                'min', -5.0, 0.0, float(gcfg.get('pi_min', -3.0)), 0.1,
                key=f'{p}_pi_min',
                on_change=lambda: sm.save(['grid_dsilva', 'pi_min'],
                                          value=st.session_state[f'{p}_pi_min']))
            pi_max = _pc2.number_input(
                'max', 0.0, 5.0, float(gcfg.get('pi_max', 3.0)), 0.1,
                key=f'{p}_pi_max',
                on_change=lambda: sm.save(['grid_dsilva', 'pi_max'],
                                          value=st.session_state[f'{p}_pi_max']))
            pi_steps = _pc3.number_input(
                'steps', 10, 500, int(gcfg.get('pi_steps', 249)), 1,
                key=f'{p}_pi_steps',
                on_change=lambda: sm.save(['grid_dsilva', 'pi_steps'],
                                          value=st.session_state[f'{p}_pi_steps']))

            n_stars_sim = st.number_input(
                'N stars / point', 100, 50000, int(gcfg.get('n_stars_sim', 3000)), 100,
                key=f'{p}_n_stars',
                on_change=lambda: sm.save(['grid_dsilva', 'n_stars_sim'],
                                          value=st.session_state[f'{p}_n_stars']))
            _err_info = _render_error_model_selector(p, simcfg, sm, 'simulation')
            sigma_meas = _err_info['sigma_measure']

    # ── Right column: sigma scan + orbital params + actions + display ─────
    with col_right:
        # ── Pre-initialise session_state for conditional widgets ───────────
        # These survive page navigation even when the widgets are not rendered.
        _sigma_default = float(simcfg.get('sigma_single', 5.5))
        _bc_defaults = {
            f'{p}_scan_sigma':         bool(gcfg.get('scan_sigma', False)),
            f'{p}_sigma_min':          float(gcfg.get('sigma_min', max(0.1, _sigma_default - 2.0))),
            f'{p}_sigma_max':          float(gcfg.get('sigma_max', _sigma_default + 2.0)),
            f'{p}_sigma_steps':        int(gcfg.get('sigma_steps', 5)),
            f'{p}_scan_logPmax':       bool(gcfg.get('scan_logPmax', False)),
            f'{p}_logPmax_scan_min':   float(gcfg.get('logPmax_scan_min', 1.0)),
            f'{p}_logPmax_scan_max':   float(gcfg.get('logPmax_scan_max', 6.0)),
            f'{p}_logPmax_scan_steps': int(gcfg.get('logPmax_scan_steps', 20)),
        }
        for _k, _v in _bc_defaults.items():
            if _k not in st.session_state:
                st.session_state[_k] = _v

        with st.expander('🎚️ σ_single scan (intrinsic single-star scatter)', expanded=True):
            scan_sigma = st.toggle('Scan σ_single over a range', key=f'{p}_scan_sigma',
                                    on_change=lambda: sm.save(['grid_dsilva', 'scan_sigma'],
                                                              value=st.session_state[f'{p}_scan_sigma']))
            if scan_sigma:
                _sc1, _sc2, _sc3 = st.columns(3)
                sigma_min = _sc1.number_input(
                    'σ_single min (km/s)', 0.1, 500.0,
                    float(st.session_state[f'{p}_sigma_min']), 0.1,
                    key=f'{p}_sigma_min',
                    on_change=lambda: sm.save(['grid_dsilva', 'sigma_min'],
                                              value=st.session_state[f'{p}_sigma_min']))
                sigma_max_val_w = _sc2.number_input(
                    'σ_single max (km/s)', 0.5, 500.0,
                    float(st.session_state[f'{p}_sigma_max']), 0.1,
                    key=f'{p}_sigma_max',
                    on_change=lambda: sm.save(['grid_dsilva', 'sigma_max'],
                                              value=st.session_state[f'{p}_sigma_max']))
                sigma_steps = _sc3.number_input(
                    'σ_single steps', 2, 500,
                    int(st.session_state[f'{p}_sigma_steps']), 1,
                    key=f'{p}_sigma_steps',
                    on_change=lambda: sm.save(['grid_dsilva', 'sigma_steps'],
                                              value=st.session_state[f'{p}_sigma_steps']))
                sigma_vals = np.linspace(max(0.1, sigma_min),
                                         max(sigma_min + 0.1, sigma_max_val_w),
                                         int(sigma_steps))
            else:
                sigma_single = st.number_input(
                    'σ_single (km/s)', 0.1, 500.0,
                    float(simcfg.get('sigma_single', 5.5)), 0.1,
                    key=f'{p}_sigma_single',
                    on_change=lambda: sm.save(
                        ['simulation', 'sigma_single'],
                        value=st.session_state[f'{p}_sigma_single']))
                sigma_vals = np.array([float(sigma_single)])

        with st.expander('🎚️ logP_max scan (period upper bound)', expanded=False):
            scan_logPmax = st.toggle('Scan logP_max over a range', key=f'{p}_scan_logPmax',
                                      on_change=lambda: sm.save(['grid_dsilva', 'scan_logPmax'],
                                                                value=st.session_state[f'{p}_scan_logPmax']))
            if scan_logPmax:
                _lp_c1, _lp_c2, _lp_c3 = st.columns(3)
                logPmax_scan_min = _lp_c1.number_input(
                    'logP_max min', 0.5, 10.0,
                    float(st.session_state[f'{p}_logPmax_scan_min']), 0.1,
                    key=f'{p}_logPmax_scan_min',
                    on_change=lambda: sm.save(['grid_dsilva', 'logPmax_scan_min'],
                                              value=st.session_state[f'{p}_logPmax_scan_min']))
                logPmax_scan_max = _lp_c2.number_input(
                    'logP_max max', 1.0, 10.0,
                    float(st.session_state[f'{p}_logPmax_scan_max']), 0.1,
                    key=f'{p}_logPmax_scan_max',
                    on_change=lambda: sm.save(['grid_dsilva', 'logPmax_scan_max'],
                                              value=st.session_state[f'{p}_logPmax_scan_max']))
                logPmax_scan_steps = _lp_c3.number_input(
                    'logP_max steps', 3, 100,
                    int(st.session_state[f'{p}_logPmax_scan_steps']), 1,
                    key=f'{p}_logPmax_scan_steps',
                    on_change=lambda: sm.save(['grid_dsilva', 'logPmax_scan_steps'],
                                              value=st.session_state[f'{p}_logPmax_scan_steps']))
                logPmax_scan_vals = np.linspace(
                    float(logPmax_scan_min),
                    max(float(logPmax_scan_min) + 0.1, float(logPmax_scan_max)),
                    int(logPmax_scan_steps))
            else:
                logPmax_scan_vals = np.array([float(st.session_state[f'{p}_logP_max'])])

        with st.expander('🔧 Orbital parameters (Kepler)', expanded=False):
            _orb_vals = _render_orbital_params_dsilva(p, 'grid_dsilva', sm, orb, gcfg)
            logP_min_val = _orb_vals['logP_min']
            logP_max_val = _orb_vals['logP_max']
            e_model      = _orb_vals['e_model']
            e_max        = _orb_vals['e_max']
            mass_model   = _orb_vals['mass_model']
            mass_fixed   = _orb_vals['mass_fixed']
            mass_range   = _orb_vals['mass_range']
            q_model      = _orb_vals['q_model']
            q_min_v      = _orb_vals['q_min']
            q_max_v      = _orb_vals['q_max']
            langer_q_mu  = _orb_vals['lq_mu']
            langer_q_sig = _orb_vals['lq_sig']

        # Action row
        max_proc = max(1, (os.cpu_count() or 2) - 1)
        _ac1, _ac2, _ac3 = st.columns([0.15, 0.25, 0.60])
        n_proc = _ac1.number_input('Workers', 1, max_proc, max_proc, key=f'{p}_nproc')
        # All 4 scoring methods are computed in a single run
        _p_lbl = 'K-S p'
        view_mode = _ac2.radio('View',
                               ['K-S p-value', 'K-S D-statistic'],
                               horizontal=True, key=f'{p}_view_mode')
        show_d = view_mode == 'K-S D-statistic'
        _cvm_cols = st.columns([0.3, 0.7])
        n_sets_cvm = _cvm_cols[0].number_input(
            'N sets', 100, 50000, 1000, step=100,
            key=f'{p}_n_sets_cvm',
            help='Number of simulation sets per grid point for CvM variance estimation and likelihood')
        from bc.params import _render_likelihood_bin_config
        with _cvm_cols[1]:
            _lk_bin_edges = _render_likelihood_bin_config(p, sm=sm)
        _run_col, _load_col, _save_col = _ac3.columns(3)
        _job_running = bool(
            st.session_state.get(f'{p}_job', {}).get('status') == 'running')
        run_btn  = _run_col.button(
            '▶️ Run Bias Correction', type='primary', key=f'{p}_run',
            disabled=_job_running)
        if _job_running:
            _cc1, _cc2 = _run_col.columns(2)
            if _cc1.button('\u23f9 Cancel', key=f'{p}_cancel'):
                st.session_state[f'{p}_job']['cancel'] = True
                st.session_state[f'{p}_job']['cancel_mode'] = 'discard'
                st.rerun()
            if _cc2.button('\U0001f4be Cancel & Save', key=f'{p}_cancel_save'):
                st.session_state[f'{p}_job']['cancel'] = True
                st.session_state[f'{p}_job']['cancel_mode'] = 'save'
                st.rerun()

        # Load saved results — clickable parameter table
        load_btn = False
        _ds_meta = _scan_result_metadata('dsilva')
        if not _ds_meta.empty:
            with st.expander('📂 Load saved result', expanded=False):
                _ds_display = _ds_meta.drop(columns=['_path', 'Model'], errors='ignore')
                _ds_sel = st.dataframe(
                    _ds_display,
                    on_select='rerun',
                    selection_mode='single-row',
                    key=f'{p}_load_table',
                    hide_index=True,
                    use_container_width=True,
                )
                _ds_sel_rows = _ds_sel.selection.rows if _ds_sel.selection else []
                if _ds_sel_rows:
                    _sel_idx = _ds_sel_rows[0]
                    _sel_path = _ds_meta.iloc[_sel_idx]['_path']
                    # Avoid re-loading same file on rerun
                    if st.session_state.get(f'{p}_loaded_path') != _sel_path:
                        _loaded = dict(np.load(_sel_path, allow_pickle=True))
                        st.session_state[f'{p}_result'] = _loaded
                        st.session_state['result_dsilva'] = _loaded
                        st.session_state[f'{p}_loaded_path'] = _sel_path
                        st.toast(f"Loaded: {_ds_meta.iloc[_sel_idx]['File']}")
                        load_btn = True
                    if st.button('🗑️ Delete this result', key=f'{p}_del_full'):
                        os.remove(_sel_path)
                        _scan_result_metadata.clear()
                        st.session_state.pop(f'{p}_loaded_path', None)
                        st.session_state.pop(f'{p}_result', None)
                        st.toast(f"Deleted: {_ds_meta.iloc[_sel_idx]['File']}")
                        st.rerun()
        else:
            _load_col.caption('No saved results yet.')

        # Manual save button
        if _save_col.button('💾 Save result', key=f'{p}_save_btn'):
            _cur_res = st.session_state.get(f'{p}_result')
            if _cur_res is not None:
                _save_kwargs_manual = dict(
                    **{k: v for k, v in _cur_res.items()},
                    config_hash=np.array('manual_save'),
                    settings=np.array(json.dumps(
                        {**gcfg, 'simulation': simcfg, 'orbital': orb},
                        default=str)),
                    obs_delta_rv=cached_load_observed_delta_rvs(),
                    timestamp=np.array(_dt.datetime.now().isoformat()),
                )
                _desc = _build_descriptive_filename(
                    'dsilva',
                    float(st.session_state.get(f'{p}_fbin_min', 0.01)),
                    float(st.session_state.get(f'{p}_fbin_max', 0.99)),
                    int(st.session_state.get(f'{p}_fbin_steps', 100)),
                    float(st.session_state.get(f'{p}_pi_min', -3.0)),
                    float(st.session_state.get(f'{p}_pi_max', 3.0)),
                    int(st.session_state.get(f'{p}_pi_steps', 100)),
                    int(st.session_state.get(f'{p}_n_stars', 3000)),
                    np.array([float(st.session_state.get(f'{p}_sigma_meas', 5.0))]),
                    float(st.session_state.get(f'{p}_logP_min', 0.15)),
                    float(st.session_state.get(f'{p}_logP_max', 5.0)),
                    x_label='pi',
                )
                _save_path = os.path.join(_RESULT_DIR, _desc)
                np.savez(_save_path, **_save_kwargs_manual)
                cached_load_grid_result.clear()
                _scan_result_metadata.clear()
                st.toast(f'Saved: {_desc}')
            else:
                _save_col.warning('No result to save. Run a simulation first.')

        # Display slots
        progress_slot       = st.empty()
        status_slot         = st.empty()
        outer_heatmap_slot  = st.empty()   # logP_max × σ 2D heatmap (when both scanned)
        max_pval_line_slot  = st.empty()
        sigma_browse_slot   = st.empty()
        logPmax_browse_slot = st.empty()
        heatmap_slot        = st.empty()
        result_slot         = st.empty()

    # ── Stable config (used for partial reuse check) ──────────────────────────
    stable_cfg = {
        'n_stars_sim':        int(n_stars_sim),
        'sigma_measure':      float(sigma_meas),
        'logP_min':           float(logP_min_val),
        'logP_max':           float(logP_max_val),
        'period_model':       'powerlaw',
        'e_model':            str(e_model),
        'e_max':              float(e_max),
        'mass_primary_model': str(mass_model),
        'mass_primary_fixed': float(mass_fixed),
        'q_model':            str(q_model),
        'q_min':              float(q_min_v),
        'q_max':              float(q_max_v),
        'primary_line':       settings.get('primary_line', 'C IV 5808-5812'),
        'threshold_dRV':      cls.get('threshold_dRV', 45.5),
        'sigma_factor':       cls.get('sigma_factor', 4.0),
    }

    fbin_vals = np.linspace(float(fbin_min), float(fbin_max), int(fbin_steps))
    pi_vals   = np.linspace(float(pi_min),   float(pi_max),   int(pi_steps))

    # ── Partial results table (replaces single-button detection) ────────────
    _render_partial_table(p, 'dsilva', status_slot)

    # ── Run grid (background thread) ─────────────────────────────────────────
    _auto_resume = st.session_state.pop(f'{p}_auto_resume', False)
    if (run_btn or _auto_resume) and not _job_running:
        sh = settings_hash(settings)
        try:
            obs_delta_rv, _ = cached_load_observed_delta_rvs(sh)
            cadence_list, cadence_weights = cached_load_cadence(sh)
        except Exception as e:
            status_slot.error(f'Failed to load observations: {e}')
            st.stop()

        _job = {
            'status': 'running', 'progress_pct': 0.0,
            'progress_text': 'Starting...', 'live_heatmaps': None,
            'live_status': '', 'live_outer_heatmap': None,
            'result': None, 'error': None, 'cancel': False,
        }
        _params = {
            'cadence_list': cadence_list, 'cadence_weights': cadence_weights,
            'obs_delta_rv': obs_delta_rv,
            'n_stars_sim': int(n_stars_sim), 'sigma_meas': float(sigma_meas),
            'n_proc': int(n_proc),
            'fbin_vals': fbin_vals, 'pi_vals': pi_vals,
            'sigma_vals': sigma_vals, 'logPmax_scan_vals': logPmax_scan_vals,
            'stable_cfg': stable_cfg,
            'n_sets_cvm': int(n_sets_cvm),
            'likelihood_bin_edges': _lk_bin_edges,
            'error_model_single': _err_info.get('type_single', 'fixed'),
            'error_params_single': _err_info.get('params_single', ()),
            'error_model_binary': _err_info.get('type_binary', 'fixed'),
            'error_params_binary': _err_info.get('params_binary', ()),
            'bin_cfg_params': {
                'logP_min': float(logP_min_val), 'logP_max': float(logP_max_val),
                'e_model': str(e_model), 'e_max': float(e_max),
                'mass_model': str(mass_model), 'mass_fixed': float(mass_fixed),
                'mass_range': tuple(mass_range),
                'q_model': str(q_model),
                'q_range': (float(q_min_v), float(q_max_v)),
                'langer_q_mu': float(langer_q_mu),
                'langer_q_sig': float(langer_q_sig),
            },
            'save_params': {
                'fbin_min': float(fbin_min), 'fbin_max': float(fbin_max),
                'fbin_steps': int(fbin_steps),
                'pi_min': float(pi_min), 'pi_max': float(pi_max),
                'pi_steps': int(pi_steps),
                'logP_max': float(logP_max_val),
            },
        }
        # ── Check partial checkpoint for resume ──────────────────────────
        def _try_load_dsilva_partial(ptl_path):
            """Attempt to load partial and prefill arrays if grids match."""
            if not os.path.exists(ptl_path):
                return False
            try:
                _ds_ptl = np.load(ptl_path, allow_pickle=True)
                _grids_match = (
                    np.allclose(np.asarray(_ds_ptl['fbin_grid']),
                                fbin_vals, atol=1e-6)
                    and np.allclose(np.asarray(_ds_ptl['pi_grid']),
                                    pi_vals, atol=1e-6)
                    and np.allclose(np.asarray(_ds_ptl['sigma_grid']),
                                    sigma_vals, atol=1e-6)
                    and np.allclose(np.asarray(_ds_ptl['logPmax_grid']),
                                    logPmax_scan_vals, atol=1e-6)
                )
                if _grids_match:
                    _params['prefilled_ks_p'] = np.asarray(_ds_ptl['ks_p'])
                    _params['prefilled_ks_D'] = np.asarray(_ds_ptl['ks_D'])
                    _n_pre = int(np.count_nonzero(
                        ~np.isnan(_params['prefilled_ks_p'])))
                    _n_tot = _params['prefilled_ks_p'].size
                    status_slot.info(
                        f'\u267b\ufe0f Resuming from checkpoint '
                        f'({_n_pre}/{_n_tot} cells, '
                        f'{_n_pre/_n_tot*100:.0f}%).')
                    _ds_ptl.close()
                    return True
                _ds_ptl.close()
            except Exception:
                pass
            return False

        # First check user-selected resume path, then legacy path
        _resume_path = st.session_state.pop(f'{p}_resume_from', None)
        if _resume_path:
            _try_load_dsilva_partial(_resume_path)
        if 'prefilled_ks_p' not in _params:
            _try_load_dsilva_partial(
                _result_path('dsilva') + '.partial.npz')
        _t = threading.Thread(target=_run_dsilva_bg, args=(_job, _params),
                              daemon=True)
        _t.start()
        st.session_state[f'{p}_job'] = _job
        st.rerun()

    # ── Poll running / completed job ─────────────────────────────────────────
    _job = st.session_state.get(f'{p}_job')
    if _job is not None and _job.get('status') == 'running':
        # Fragment-based polling: only re-renders itself every 3s, no full-page rerun
        @st.fragment(run_every=3)
        def _dsilva_live_poll():
            _j = st.session_state.get(f'{p}_job')
            if _j is None or _j.get('status') != 'running':
                st.rerun(scope='app')  # one final full rerun to show done state
                return
            st.progress(_j.get('progress_pct', 0), text=_j.get('progress_text', '...'))
            if _j.get('live_heatmaps'):
                _lhm = _j['live_heatmaps']
                _lc1, _lc2 = st.columns(2)
                for _mk, _col in [('ks', _lc1), ('weighted', _lc2)]:
                    if _mk in _lhm:
                        hd = _lhm[_mk]
                        with _col:
                            st.plotly_chart(
                                _make_heatmap_fig(
                                    hd['p'] if _mk == 'likelihood' else hd['d'],
                                    hd['fbin'], hd['x'],
                                    title=hd['title'], height=300,
                                    live=not hd['is_final'],
                                    scoring_label=_METHOD_SCORING_LABELS[_mk],
                                    colorbar_title_override=_METHOD_COLORBAR_OVERRIDE.get(_mk)),
                                use_container_width=True)
                _lc3, _lc4 = st.columns(2)
                for _mk, _col in [('cvm', _lc3), ('likelihood', _lc4)]:
                    if _mk in _lhm:
                        hd = _lhm[_mk]
                        with _col:
                            st.plotly_chart(
                                _make_heatmap_fig(
                                    hd['p'] if _mk == 'likelihood' else hd['d'],
                                    hd['fbin'], hd['x'],
                                    title=hd['title'], height=300,
                                    live=not hd['is_final'],
                                    scoring_label=_METHOD_SCORING_LABELS[_mk],
                                    colorbar_title_override=_METHOD_COLORBAR_OVERRIDE.get(_mk)),
                                use_container_width=True)
            if _j.get('live_outer_heatmap'):
                ohd = _j['live_outer_heatmap']
                st.plotly_chart(
                    _make_heatmap_fig(
                        ohd['p'], ohd['y'], ohd['x'],
                        title=f'Max {_p_lbl}  (logP_max × σ_single)',
                        height=_ch, width=_cw,
                        x_label='σ_single (km/s)',
                        y_label='log₁₀(P_max / days)',
                        x_name='σ',
                        best_label_fmt='  logP_max={fbin:.2f}, σ={x:.1f}, p={p:.4f}',
                        live=not ohd['is_final'],
                    ), use_container_width=_use_cw)
            if _j.get('live_status'):
                st.markdown(_j['live_status'])
        _dsilva_live_poll()

    elif _job is not None and _job.get('status') == 'done':
        _res = _job['result']
        st.session_state[f'{p}_result'] = _res
        st.session_state['result_dsilva'] = _res
        cached_load_grid_result.clear()
        # Persist final live heatmaps so they remain visible after job cleanup
        if _job.get('live_heatmaps'):
            st.session_state[f'{p}_final_live_heatmaps'] = _job['live_heatmaps']
        _elapsed = _job.get('elapsed_total', 0)
        _desc = _job.get('desc_name', '')
        _nrows = _job.get('n_rows_total', 0)
        progress_slot.progress(
            1.0, text=f'Done in {_fmt_eta(_elapsed)}.')
        status_slot.success(
            f'Saved to results/{_desc}  '
            f'({_nrows} rows computed in {_fmt_eta(_elapsed)})')
        del st.session_state[f'{p}_job']

    elif _job is not None and _job.get('status') == 'error':
        status_slot.error(
            f"Simulation failed:\n```\n{_job['error']}\n```")
        del st.session_state[f'{p}_job']

    elif _job is not None and _job.get('status') == 'cancelled':
        if _job.get('partial_saved'):
            status_slot.warning('Simulation cancelled \u2014 partial progress saved.')
            _scan_partial_metadata.clear()
        else:
            status_slot.warning('Simulation cancelled.')
        del st.session_state[f'{p}_job']

    # ── Show persisted final live heatmaps (Bug 1: survive job cleanup) ─────
    _final_lhm = st.session_state.get(f'{p}_final_live_heatmaps')
    if _final_lhm:
        _lc1, _lc2 = st.columns(2)
        for _mk, _col in [('ks', _lc1), ('weighted', _lc2)]:
            if _mk in _final_lhm:
                hd = _final_lhm[_mk]
                with _col:
                    st.plotly_chart(
                        _make_heatmap_fig(
                            hd['p'] if _mk == 'likelihood' else hd['d'],
                            hd['fbin'], hd['x'],
                            title=hd['title'], height=300, live=False,
                            scoring_label=_METHOD_SCORING_LABELS[_mk],
                            colorbar_title_override=_METHOD_COLORBAR_OVERRIDE.get(_mk)),
                        use_container_width=True)
        _lc3, _lc4 = st.columns(2)
        for _mk, _col in [('cvm', _lc3), ('likelihood', _lc4)]:
            if _mk in _final_lhm:
                hd = _final_lhm[_mk]
                with _col:
                    st.plotly_chart(
                        _make_heatmap_fig(
                            hd['p'] if _mk == 'likelihood' else hd['d'],
                            hd['fbin'], hd['x'],
                            title=hd['title'], height=300, live=False,
                            scoring_label=_METHOD_SCORING_LABELS[_mk],
                            colorbar_title_override=_METHOD_COLORBAR_OVERRIDE.get(_mk)),
                        use_container_width=True)

    # ── Display result (always shown when result exists) ─────────────────────
    result = st.session_state.get(f'{p}_result') or st.session_state.get('result_dsilva')

    if result is None:
        result = cached_load_grid_result('dsilva')
        if result is not None:
            st.session_state[f'{p}_result'] = result

    if result is not None:
        fbin_g    = np.asarray(result['fbin_grid'])
        pi_g      = np.asarray(result['pi_grid'])
        sigma_g   = np.asarray(result['sigma_grid'])
        logPmax_g = np.asarray(result.get('logPmax_grid', [float(logP_max_val)]))
        ks_p_4d   = np.asarray(result['ks_p'])
        ks_D_4d   = np.asarray(result['ks_D'])

        # Ensure 4D shape [n_logPmax, n_sigma, n_fbin, n_pi]
        if ks_p_4d.ndim == 2:
            ks_p_4d = ks_p_4d[np.newaxis, np.newaxis, ...]
            ks_D_4d = ks_D_4d[np.newaxis, np.newaxis, ...]
        elif ks_p_4d.ndim == 3:
            ks_p_4d = ks_p_4d[np.newaxis, ...]
            ks_D_4d = ks_D_4d[np.newaxis, ...]

        _has_logPmax_scan = len(logPmax_g) > 1
        _has_sigma_scan   = len(sigma_g) > 1

        # ── Outer heatmap: logP_max × σ (max p over fbin×pi) ──────────
        if _has_logPmax_scan and _has_sigma_scan:
            _outer_max_p = np.nanmax(ks_p_4d, axis=(2, 3))  # [n_lp, n_sig]
            outer_heatmap_slot.plotly_chart(
                _make_heatmap_fig(
                    _outer_max_p, logPmax_g, sigma_g,
                    title=f'Max {_p_lbl}-value  (logP_max × σ_single)',
                    height=_ch, width=_cw,
                    x_label='σ_single (km/s)',
                    y_label='log₁₀(P_max / days)',
                    x_name='σ',
                    best_label_fmt='  logP_max={fbin:.2f}, σ={x:.1f}, p={p:.4f}',
                ),
                use_container_width=_use_cw,
            )
        elif _has_logPmax_scan:
            # 1D line chart: max p vs logP_max
            _lp_max_p = [float(np.nanmax(ks_p_4d[i_lp]))
                         for i_lp in range(len(logPmax_g))]
            max_pval_line_slot.plotly_chart(
                _make_max_pval_fig(logPmax_g, _lp_max_p, height=280,
                                   x_label='logP_max'),
                use_container_width=True,
                key=f'{p}_max_pval_logPmax_line',
            )

        # ── Sigma browse ──────────────────────────────────────────────────
        # Find global best across all dimensions
        if not np.any(np.isfinite(ks_p_4d)):
            st.warning('No finite p-values in grid — cannot determine best point.')
            return
        _flat_best_4d = int(np.nanargmax(ks_p_4d))
        _n_sig, _n_fb, _n_pi = ks_p_4d.shape[1], ks_p_4d.shape[2], ks_p_4d.shape[3]
        best_lp_idx  = _flat_best_4d // (_n_sig * _n_fb * _n_pi)
        best_sig_idx = (_flat_best_4d // (_n_fb * _n_pi)) % _n_sig
        best_fb_idx  = (_flat_best_4d // _n_pi) % _n_fb
        best_pi_idx  = _flat_best_4d % _n_pi

        # Max p per sigma (summed over logPmax)
        if _has_sigma_scan:
            max_pvals = [float(np.nanmax(ks_p_4d[:, i_s, :, :]))
                         for i_s in range(len(sigma_g))]
            if not (_has_logPmax_scan and _has_sigma_scan):
                max_pval_line_slot.plotly_chart(
                    _make_max_pval_fig(sigma_g, max_pvals, height=280),
                    use_container_width=True,
                    key=f'{p}_max_pval_line',
                )

            sigma_float_opts = [round(float(s), 4) for s in sigma_g]
            selected_sigma_f = sigma_browse_slot.select_slider(
                'Browse σ_single heatmaps',
                options=sigma_float_opts,
                value=sigma_float_opts[best_sig_idx],
                format_func=lambda v: f'{v:.2f} km/s',
                key=f'{p}_sigma_browse',
            )
            disp_sig_idx = int(np.argmin(np.abs(sigma_g - selected_sigma_f)))
        else:
            disp_sig_idx = 0

        # ── logP_max browse ───────────────────────────────────────────────
        if _has_logPmax_scan:
            logPmax_float_opts = [round(float(lp), 4) for lp in logPmax_g]
            selected_logPmax_f = logPmax_browse_slot.select_slider(
                'Browse logP_max heatmaps',
                options=logPmax_float_opts,
                value=logPmax_float_opts[best_lp_idx],
                format_func=lambda v: f'{v:.2f}',
                key=f'{p}_logPmax_browse',
            )
            disp_lp_idx = int(np.argmin(np.abs(logPmax_g - selected_logPmax_f)))
        else:
            disp_lp_idx = 0

        # ── Load observed data for model_ctx ──────────────────────────────
        sh_analysis = settings_hash(settings)
        try:
            obs_drv_analysis, obs_detail = cached_load_observed_delta_rvs(sh_analysis)
            cadence_list_a, cadence_weights_a = cached_load_cadence(sh_analysis)
            _has_obs = True
        except Exception:
            obs_drv_analysis = None
            obs_detail = None
            cadence_list_a = None
            cadence_weights_a = None
            _has_obs = False

        # ── Compute gap_sim at best-fit for analysis plots ────────────────
        gap_sim = None
        _bin_cfg_explore = None
        ana_logPmax = float(logPmax_g[best_lp_idx])
        if _has_obs:
            from wr_bias_simulation import (
                SimulationConfig, BinaryParameterConfig,
                simulate_with_params,
            )
            thresh_dRV = float(cls.get('threshold_dRV', 45.5))

            _bin_cfg_explore = BinaryParameterConfig(
                logP_min=float(logP_min_val),
                logP_max=ana_logPmax,
                period_model='powerlaw',
                e_model=str(e_model),
                e_max=float(e_max),
                mass_primary_model=str(mass_model),
                mass_primary_fixed=float(mass_fixed),
                mass_primary_range=tuple(mass_range),
                q_model=str(q_model),
                q_range=(float(q_min_v), float(q_max_v)),
                langer_q_mu=float(langer_q_mu),
                langer_q_sigma=float(langer_q_sig),
            )

            best_fbin_v = float(fbin_g[best_fb_idx])
            best_pi_v = float(pi_g[best_pi_idx])
            best_sigma_v = float(sigma_g[best_sig_idx])

            _sim_cfg_gap = SimulationConfig(
                n_stars=int(n_stars_sim),
                sigma_single=best_sigma_v,
                sigma_measure=float(sigma_meas),
                cadence_library=cadence_list_a,
                cadence_weights=cadence_weights_a,
            )
            _gap_fingerprint = (best_fbin_v, best_pi_v, best_sigma_v,
                                ana_logPmax, ks_p_4d.shape)
            if (st.session_state.get(f'{p}_gap_fingerprint') != _gap_fingerprint
                    or f'{p}_gap_sim' not in st.session_state):
                rng_gap = np.random.default_rng(99)
                st.session_state[f'{p}_gap_sim'] = simulate_with_params(
                    best_fbin_v, best_pi_v,
                    _sim_cfg_gap, _bin_cfg_explore, rng_gap,
                )
                st.session_state[f'{p}_gap_fingerprint'] = _gap_fingerprint
                st.session_state.pop(f'{p}_sim_drv', None)
            gap_sim = st.session_state[f'{p}_gap_sim']

        # ── Build model_ctx and delegate to subtabs ───────────────────────
        from bc.subtabs import render_model_subtabs

        model_ctx = {
            'model_type': 'dsilva',
            'ndim_mode': 'dsilva',
            'x_name': 'pi',
            'x_label': 'pi',
            'x_display_label': 'pi (period power-law index)',
            'period_model': 'powerlaw',
            'has_case_AB': False,
            'result': result,
            'fbin_g': fbin_g,
            'x_g': pi_g,
            'sigma_g': sigma_g,
            'logPmax_g': logPmax_g,
            'gap_sim': gap_sim,
            'obs_delta_rv': obs_drv_analysis,
            'obs_detail': obs_detail,
            'cadence_list': cadence_list_a,
            'cadence_weights': cadence_weights_a,
            'n_stars_sim': int(n_stars_sim),
            'sigma_meas': float(sigma_meas),
            'bin_cfg': _bin_cfg_explore,
            'logP_min': float(logP_min_val),
            'logP_max': ana_logPmax,
            'thresh_dRV': float(cls.get('threshold_dRV', 45.5)),
            'canvas_height': _ch,
            'canvas_width': _cw,
            'use_container_width': _use_cw,
            'disp_outer_slices': (disp_lp_idx, disp_sig_idx),
            'settings': settings,
            'classification': cls,
        }

        render_model_subtabs(p, model_ctx)

