"""bc.langer — Langer 2020 bias correction tab renderer."""
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

from bc.analysis import _get_method_array  # noqa: F401 — re-export for tests
from bc.helpers import (
    _METHOD_SCORING_LABELS, _METHOD_COLORBAR_OVERRIDE,
    _RESULT_DIR,
    _fmt_eta, _result_path,
    _build_descriptive_filename,
    _scan_partial_metadata, _render_partial_table,
    _scan_result_metadata,
    _make_max_pval_fig,
    _make_heatmap_fig,
    _find_reusable_fbin_langer,
)
from bc.params import _render_orbital_params_langer
from bc.runners import _run_langer_bg
from bc.extras import _render_error_model_selector


# ---------------------------------------------------------------------------
# Langer 2020 tab renderer
# ---------------------------------------------------------------------------
def _render_langer_tab(p: str, settings: dict, sm) -> None:
    """Render a Langer 2020 bias correction tab.

    Parameters
    ----------
    p : str
        Unique prefix for session-state keys (e.g. 'lg', 'lg2').
    settings : dict
        User settings dict.
    sm : SettingsManager
        Settings manager (saves only when p is the primary prefix 'lg').
    """
    _is_primary = (p == 'lg')  # only primary tab saves to settings file
    _ch = int(st.session_state.get('bc_canvas_height', 520))
    _cw_raw = int(st.session_state.get('bc_canvas_width', 0))
    _cw = _cw_raw if _cw_raw > 0 else None
    _use_cw = (_cw is None)
    lg_cfg   = settings.get('grid_langer', {})
    lg_sim   = settings.get('simulation', {})
    lg_cls   = settings.get('classification', {})
    lg_pp    = lg_cfg.get('langer_period_params', {})

    # Pre-initialise session_state from settings (only on first visit)
    _lg_defaults = {
        f'{p}_fbin_min':   float(lg_cfg.get('fbin_min', 0.01)),
        f'{p}_fbin_max':   float(lg_cfg.get('fbin_max', 0.99)),
        f'{p}_fbin_steps': int(lg_cfg.get('fbin_steps', 100)),
        f'{p}_sigma_min':  float(lg_cfg.get('sigma_min', 1.0)),
        f'{p}_sigma_max':  float(lg_cfg.get('sigma_max', 15.0)),
        f'{p}_sigma_steps': int(lg_cfg.get('sigma_steps', 30)),
        f'{p}_n_stars':    int(lg_cfg.get('n_stars_sim', 10000)),
        f'{p}_sigma_meas': float(lg_sim.get('sigma_measure', 1.622)),
        f'{p}_dist_A':     str(lg_pp.get('dist_A', 'gaussian')),
        f'{p}_mu_A':       float(lg_pp.get('mu_A', 0.80)),
        f'{p}_sigma_A':    float(lg_pp.get('sigma_A', 0.35)),
        f'{p}_dist_B':     str(lg_pp.get('dist_B', 'reflected_lognormal')),
        f'{p}_mu_B':       float(lg_pp.get('mu_B', 2.0)),
        f'{p}_sigma_B':    float(lg_pp.get('sigma_B', 0.45)),
        f'{p}_weight_A':   float(lg_pp.get('weight_A', 0.20)),
        f'{p}_logP_min':   float(lg_cfg.get('logP_min', 0.5)),
        f'{p}_logP_max':   float(lg_cfg.get('logP_max', 3.5)),
        f'{p}_scan_logPmax':       bool(lg_cfg.get('scan_logPmax', False)),
        f'{p}_logPmax_scan_min':   float(lg_cfg.get('logPmax_scan_min', 1.0)),
        f'{p}_logPmax_scan_max':   float(lg_cfg.get('logPmax_scan_max', 6.0)),
        f'{p}_logPmax_scan_steps': int(lg_cfg.get('logPmax_scan_steps', 20)),
        f'{p}_mass_fixed': float(lg_cfg.get('mass_primary_fixed', 10.0)),
    }
    for _k, _v in _lg_defaults.items():
        if _k not in st.session_state:
            st.session_state[_k] = _v

    lg_col_left, lg_col_right = st.columns([0.30, 0.70])

    # -- Left column: grid parameters (compact 3-col layout) -----------------
    with lg_col_left:
        with st.expander('⚙️ Grid parameters', expanded=True):
            st.markdown('**f_bin**')
            _fc1, _fc2, _fc3 = st.columns(3)
            lg_fbin_min = _fc1.number_input(
                'min', 0.0, 0.5, float(lg_cfg.get('fbin_min', 0.01)), 0.01,
                key=f'{p}_fbin_min',
                on_change=lambda: sm.save(['grid_langer', 'fbin_min'],
                                          value=st.session_state[f'{p}_fbin_min']))
            lg_fbin_max = _fc2.number_input(
                'max', 0.5, 1.0, float(lg_cfg.get('fbin_max', 0.99)), 0.01,
                key=f'{p}_fbin_max',
                on_change=lambda: sm.save(['grid_langer', 'fbin_max'],
                                          value=st.session_state[f'{p}_fbin_max']))
            lg_fbin_steps = _fc3.number_input(
                'steps', 10, 500, int(lg_cfg.get('fbin_steps', 100)), 1,
                key=f'{p}_fbin_steps',
                on_change=lambda: sm.save(['grid_langer', 'fbin_steps'],
                                          value=st.session_state[f'{p}_fbin_steps']))

            st.markdown('**σ_single (km/s)**')
            _sc1, _sc2, _sc3 = st.columns(3)
            lg_sigma_min = _sc1.number_input(
                'min', 0.1, 100.0,
                float(lg_cfg.get('sigma_min', 1.0)), 0.1,
                key=f'{p}_sigma_min',
                on_change=lambda: sm.save(['grid_langer', 'sigma_min'],
                                          value=st.session_state[f'{p}_sigma_min']))
            lg_sigma_max = _sc2.number_input(
                'max', 0.5, 100.0,
                float(lg_cfg.get('sigma_max', 15.0)), 0.1,
                key=f'{p}_sigma_max',
                on_change=lambda: sm.save(['grid_langer', 'sigma_max'],
                                          value=st.session_state[f'{p}_sigma_max']))
            lg_sigma_steps = _sc3.number_input(
                'steps', 5, 500, int(lg_cfg.get('sigma_steps', 30)), 1,
                key=f'{p}_sigma_steps',
                on_change=lambda: sm.save(['grid_langer', 'sigma_steps'],
                                          value=st.session_state[f'{p}_sigma_steps']))

            lg_n_stars = st.number_input(
                'N stars / point', 100, 50000, int(lg_cfg.get('n_stars_sim', 10000)), 100,
                key=f'{p}_n_stars',
                on_change=lambda: sm.save(['grid_langer', 'n_stars_sim'],
                                          value=st.session_state[f'{p}_n_stars']))
            _lg_err_info = _render_error_model_selector(p, lg_sim, sm, 'grid_langer')
            lg_sigma_meas = _lg_err_info['sigma_measure']

    # -- Right column: orbital params + actions + display ---------------------
    with lg_col_right:
        with st.expander('🔧 Orbital parameters (Langer 2020)', expanded=False):
            _lg_orb = _render_orbital_params_langer(p, 'grid_langer', sm, lg_pp, lg_cfg)
            lg_dist_A    = _lg_orb['dist_A']
            lg_mu_A      = _lg_orb['mu_A']
            lg_sigma_A   = _lg_orb['sigma_A']
            lg_dist_B    = _lg_orb['dist_B']
            lg_mu_B      = _lg_orb['mu_B']
            lg_sigma_B   = _lg_orb['sigma_B']
            lg_weight_A  = _lg_orb['weight_A']
            lg_logP_min  = _lg_orb['logP_min']
            lg_logP_max  = _lg_orb['logP_max']
            lg_mass_model = _lg_orb['mass_model']
            lg_mass_fixed = _lg_orb['mass_fixed']
            lg_mass_range = _lg_orb['mass_range']
            lg_q_model   = _lg_orb['q_model']
            lg_q_min     = _lg_orb['q_min']
            lg_q_max     = _lg_orb['q_max']
            lg_lq_mu     = _lg_orb['lq_mu']
            lg_lq_sig    = _lg_orb['lq_sig']
            lg_q_flipped = _lg_orb['q_flipped']

        with st.expander('🎚️ logP_max scan (period upper bound)', expanded=False):
            lg_scan_logPmax = st.toggle('Scan logP_max over a range',
                                        key=f'{p}_scan_logPmax',
                                        on_change=lambda: sm.save(['grid_langer', 'scan_logPmax'],
                                                                  value=st.session_state[f'{p}_scan_logPmax']))
            if lg_scan_logPmax:
                _lp_c1, _lp_c2, _lp_c3 = st.columns(3)
                lg_logPmax_scan_min = _lp_c1.number_input(
                    'logP_max min', 0.5, 10.0,
                    float(st.session_state[f'{p}_logPmax_scan_min']), 0.1,
                    key=f'{p}_logPmax_scan_min',
                    on_change=lambda: sm.save(['grid_langer', 'logPmax_scan_min'],
                                              value=st.session_state[f'{p}_logPmax_scan_min']))
                lg_logPmax_scan_max = _lp_c2.number_input(
                    'logP_max max', 1.0, 10.0,
                    float(st.session_state[f'{p}_logPmax_scan_max']), 0.1,
                    key=f'{p}_logPmax_scan_max',
                    on_change=lambda: sm.save(['grid_langer', 'logPmax_scan_max'],
                                              value=st.session_state[f'{p}_logPmax_scan_max']))
                lg_logPmax_scan_steps = _lp_c3.number_input(
                    'logP_max steps', 3, 100,
                    int(st.session_state[f'{p}_logPmax_scan_steps']), 1,
                    key=f'{p}_logPmax_scan_steps',
                    on_change=lambda: sm.save(['grid_langer', 'logPmax_scan_steps'],
                                              value=st.session_state[f'{p}_logPmax_scan_steps']))
                lg_logPmax_scan_vals = np.linspace(
                    float(lg_logPmax_scan_min),
                    max(float(lg_logPmax_scan_min) + 0.1,
                        float(lg_logPmax_scan_max)),
                    int(lg_logPmax_scan_steps))
            else:
                lg_logPmax_scan_vals = np.array(
                    [float(st.session_state[f'{p}_logP_max'])])

        # Action row
        lg_max_proc = max(1, (os.cpu_count() or 2) - 1)
        _lg_ac1, _lg_ac2, _lg_ac3 = st.columns([0.15, 0.25, 0.60])
        lg_n_proc = _lg_ac1.number_input('Workers', 1, lg_max_proc, lg_max_proc,
                                          key=f'{p}_nproc')
        _lg_p_lbl = 'K-S p'
        lg_view_mode = _lg_ac2.radio('View',
                                      ['K-S p-value', 'K-S D-statistic'],
                                      horizontal=True, key=f'{p}_view_mode')
        lg_show_d = lg_view_mode == 'K-S D-statistic'
        _lg_cvm_cols = st.columns([0.3, 0.7])
        lg_n_sets_cvm = _lg_cvm_cols[0].number_input(
            'N sets', 100, 50000, 1000, step=100,
            key=f'{p}_n_sets_cvm',
            help='Number of simulation sets per grid point for CvM variance estimation and likelihood')
        from bc.params import _render_likelihood_bin_config
        with _lg_cvm_cols[1]:
            _lg_lk_bin_edges = _render_likelihood_bin_config(p, sm=sm)
        _lg_run_col, _lg_load_col, _lg_save_col = _lg_ac3.columns(3)
        _lg_job_running = bool(
            st.session_state.get(f'{p}_job', {}).get('status') == 'running')
        lg_run_btn = _lg_run_col.button(
            '▶️ Run Langer Grid', type='primary', key=f'{p}_run',
            disabled=_lg_job_running)
        if _lg_job_running:
            _lcc1, _lcc2 = _lg_run_col.columns(2)
            if _lcc1.button('\u23f9 Cancel', key=f'{p}_cancel'):
                st.session_state[f'{p}_job']['cancel'] = True
                st.session_state[f'{p}_job']['cancel_mode'] = 'discard'
                st.rerun()
            if _lcc2.button('\U0001f4be Cancel & Save', key=f'{p}_cancel_save'):
                st.session_state[f'{p}_job']['cancel'] = True
                st.session_state[f'{p}_job']['cancel_mode'] = 'save'
                st.rerun()

        # Load saved results — clickable parameter table (Langer)
        lg_load_btn = False
        _lg_meta = _scan_result_metadata('langer')
        if not _lg_meta.empty:
            with st.expander('📂 Load saved result', expanded=False):
                _lg_display = _lg_meta.drop(columns=['_path', 'Model'], errors='ignore')
                _lg_sel = st.dataframe(
                    _lg_display,
                    on_select='rerun',
                    selection_mode='single-row',
                    key=f'{p}_load_table',
                    hide_index=True,
                    use_container_width=True,
                )
                _lg_sel_rows = _lg_sel.selection.rows if _lg_sel.selection else []
                if _lg_sel_rows:
                    _lg_idx = _lg_sel_rows[0]
                    _lg_sel_path = _lg_meta.iloc[_lg_idx]['_path']
                    if st.session_state.get(f'{p}_loaded_path') != _lg_sel_path:
                        _lg_loaded = dict(np.load(_lg_sel_path, allow_pickle=True))
                        st.session_state[f'{p}_result'] = _lg_loaded
                        st.session_state[f'{p}_loaded_path'] = _lg_sel_path
                        st.toast(f"Loaded: {_lg_meta.iloc[_lg_idx]['File']}")
                        lg_load_btn = True
                    if st.button('🗑️ Delete this result', key=f'{p}_del_full'):
                        os.remove(_lg_sel_path)
                        _scan_result_metadata.clear()
                        st.session_state.pop(f'{p}_loaded_path', None)
                        st.session_state.pop(f'{p}_result', None)
                        st.toast(f"Deleted: {_lg_meta.iloc[_lg_idx]['File']}")
                        st.rerun()
        else:
            _lg_load_col.caption('No saved results yet.')

        # Manual save button (Langer)
        if _lg_save_col.button('💾 Save result', key=f'{p}_save_btn'):
            _lg_cur_res = st.session_state.get(f'{p}_result')
            if _lg_cur_res is not None:
                _lg_save_kw = dict(
                    **{k: v for k, v in _lg_cur_res.items()},
                    config_hash=np.array('manual_save'),
                    settings=np.array(json.dumps(
                        {**lg_cfg, 'simulation': lg_sim, 'langer_period_params': lg_pp},
                        default=str)),
                    obs_delta_rv=cached_load_observed_delta_rvs(),
                    timestamp=np.array(_dt.datetime.now().isoformat()),
                )
                _lg_desc = _build_descriptive_filename(
                    'langer',
                    float(st.session_state.get(f'{p}_fbin_min', 0.01)),
                    float(st.session_state.get(f'{p}_fbin_max', 0.99)),
                    int(st.session_state.get(f'{p}_fbin_steps', 100)),
                    float(st.session_state.get(f'{p}_sigma_min', 1.0)),
                    float(st.session_state.get(f'{p}_sigma_max', 15.0)),
                    int(st.session_state.get(f'{p}_sigma_steps', 30)),
                    int(st.session_state.get(f'{p}_n_stars', 10000)),
                    np.array([float(st.session_state.get(f'{p}_sigma_meas', 1.622))]),
                    float(st.session_state.get(f'{p}_logP_min', 0.5)),
                    float(st.session_state.get(f'{p}_logP_max', 3.5)),
                    x_label='sig',
                )
                # Append case indicator to filename
                _wA = float(st.session_state.get(f'{p}_weight_A', 0.3))
                if _wA == 1.0:
                    _case_tag = '_caseA'
                elif _wA == 0.0:
                    _case_tag = '_caseB'
                else:
                    _case_tag = f'_wA{_wA:.2f}'
                _lg_desc = _lg_desc.replace('.npz', f'{_case_tag}.npz')
                _lg_save_path = os.path.join(_RESULT_DIR, _lg_desc)
                np.savez(_lg_save_path, **_lg_save_kw)
                cached_load_grid_result.clear()
                _scan_result_metadata.clear()
                st.toast(f'Saved: {_lg_desc}')
            else:
                _lg_save_col.warning('No result to save. Run first.')

        # Display slots
        lg_progress_slot = st.empty()
        lg_status_slot   = st.empty()
        lg_heatmap_slot  = st.empty()
        lg_result_slot   = st.empty()

    # -- Partial results table ------------------------------------------------
    _render_partial_table(p, 'langer', lg_status_slot)

    # -- Stable config --------------------------------------------------------
    lg_period_params = {
        'dist_A': str(lg_dist_A), 'mu_A': float(lg_mu_A), 'sigma_A': float(lg_sigma_A),
        'dist_B': str(lg_dist_B), 'mu_B': float(lg_mu_B), 'sigma_B': float(lg_sigma_B),
        'weight_A': float(lg_weight_A),
    }
    lg_stable_cfg = {
        'n_stars_sim':        int(lg_n_stars),
        'sigma_measure':      float(lg_sigma_meas),
        'logP_min':           float(lg_logP_min),
        'logP_max':           float(lg_logP_max),
        'period_model':       'langer2020',
        'e_model':            'zero',
        'e_max':              0.0,
        'mass_primary_model': str(lg_mass_model),
        'mass_primary_fixed': float(lg_mass_fixed),
        'q_model':            str(lg_q_model),
        'q_min':              float(lg_q_min),
        'q_max':              float(lg_q_max),
        'q_flipped':          bool(lg_q_flipped),
        'langer_q_mu':        float(lg_lq_mu),
        'langer_q_sigma':     float(lg_lq_sig),
        'langer_period_params': lg_period_params,
        'primary_line':       settings.get('primary_line', 'C IV 5808-5812'),
        'threshold_dRV':      lg_cls.get('threshold_dRV', 45.5),
        'sigma_factor':       lg_cls.get('sigma_factor', 4.0),
    }

    lg_fbin_vals  = np.linspace(float(lg_fbin_min), float(lg_fbin_max), int(lg_fbin_steps))
    lg_sigma_vals = np.linspace(max(0.1, float(lg_sigma_min)),
                                max(float(lg_sigma_min) + 0.1, float(lg_sigma_max)),
                                int(lg_sigma_steps))

    # -- Run grid (background thread) -----------------------------------------
    _lg_auto_resume = st.session_state.pop(f'{p}_auto_resume', False)
    if (lg_run_btn or _lg_auto_resume) and not _lg_job_running:
        sh_lg = settings_hash(settings)
        try:
            lg_obs_drv, _ = cached_load_observed_delta_rvs(sh_lg)
            lg_cad_list, lg_cad_weights = cached_load_cadence(sh_lg)
        except Exception as e:
            lg_status_slot.error(f'Failed to load observations: {e}')
            st.stop()

        from wr_bias_simulation import BinaryParameterConfig

        lg_bin_cfg = BinaryParameterConfig(
            logP_min=float(lg_logP_min),
            logP_max=float(lg_logP_max),
            period_model='langer2020',
            langer_period_params=lg_period_params,
            e_model='zero', e_max=0.0,
            mass_primary_model=str(lg_mass_model),
            mass_primary_fixed=float(lg_mass_fixed),
            mass_primary_range=tuple(lg_mass_range),
            q_model=str(lg_q_model),
            q_range=(float(lg_q_min), float(lg_q_max)),
            langer_q_mu=float(lg_lq_mu),
            langer_q_sigma=float(lg_lq_sig),
            q_flipped=bool(lg_q_flipped),
        )

        # -- Check for partial reuse (main thread, needs UI) ------------------
        lg_cached_existing = None
        lg_reuse_info = None
        lg_existing_path = _result_path('langer')
        if os.path.exists(lg_existing_path):
            try:
                lg_cached_existing = dict(np.load(lg_existing_path, allow_pickle=True))
                lg_reuse_info = _find_reusable_fbin_langer(
                    lg_cached_existing, lg_fbin_vals, lg_sigma_vals, lg_stable_cfg)
            except Exception:
                lg_cached_existing = None

        if lg_reuse_info:
            lg_reuse_new_idx, lg_reuse_cache_idx = lg_reuse_info
            lg_n_reused = len(lg_reuse_new_idx)
            lg_status_slot.info(
                f'♻️ Reusing {lg_n_reused}/{len(lg_fbin_vals)} f_bin rows from cached result.')
        else:
            lg_reuse_new_idx, lg_reuse_cache_idx = [], []
            lg_n_reused = 0

        # -- Also check partial checkpoint for resume -------------------------
        _lg_resume_from = st.session_state.pop(f'{p}_resume_from', None)
        _lg_partial_resume_path = (_lg_resume_from
                                   if _lg_resume_from and os.path.exists(_lg_resume_from)
                                   else _result_path('langer') + '.partial.npz')
        if os.path.exists(_lg_partial_resume_path) and lg_n_reused == 0:
            try:
                _lg_ptl_data = dict(np.load(_lg_partial_resume_path, allow_pickle=True))
                _lg_ptl_reuse = _find_reusable_fbin_langer(
                    _lg_ptl_data, lg_fbin_vals, lg_sigma_vals, lg_stable_cfg)
                if _lg_ptl_reuse:
                    lg_reuse_new_idx, lg_reuse_cache_idx = _lg_ptl_reuse
                    lg_cached_existing = _lg_ptl_data
                    lg_reuse_info = _lg_ptl_reuse
                    # Only count rows where ALL sigma values are non-NaN
                    _ptl_ks_p = np.asarray(_lg_ptl_data['ks_p'])
                    _complete_rows = []
                    for ni, ci in zip(lg_reuse_new_idx, lg_reuse_cache_idx):
                        if not np.any(np.isnan(_ptl_ks_p[ci, :])):
                            _complete_rows.append(ni)
                    lg_reuse_new_idx = _complete_rows
                    lg_reuse_cache_idx = [ci for ni, ci in
                        zip(_lg_ptl_reuse[0], _lg_ptl_reuse[1])
                        if ni in set(_complete_rows)]
                    lg_n_reused = len(_complete_rows)
                    lg_status_slot.info(
                        f'♻️ Resuming from checkpoint: '
                        f'{lg_n_reused}/{len(lg_fbin_vals)} f_bin rows complete.')
            except Exception:
                pass

        # Pre-allocate and fill reused rows
        lg_n_fbin  = len(lg_fbin_vals)
        lg_n_sigma = len(lg_sigma_vals)
        lg_acc_ks_p = np.full((lg_n_fbin, lg_n_sigma), np.nan)
        lg_acc_ks_D = np.full_like(lg_acc_ks_p, np.nan)
        if lg_reuse_info and lg_cached_existing is not None:
            lg_c_ks_p = np.asarray(lg_cached_existing['ks_p'])
            lg_c_ks_D = np.asarray(lg_cached_existing['ks_D'])
            for new_i, cache_i in zip(lg_reuse_new_idx, lg_reuse_cache_idx):
                lg_acc_ks_p[new_i, :] = lg_c_ks_p[cache_i, :]
                lg_acc_ks_D[new_i, :] = lg_c_ks_D[cache_i, :]

        lg_reuse_set = set(lg_reuse_new_idx)
        lg_missing_fbin_idx = [i for i in range(lg_n_fbin) if i not in lg_reuse_set]

        _lg_job = {
            'status': 'running', 'progress_pct': 0.0,
            'progress_text': 'Starting...', 'live_heatmaps': None,
            'live_status': '', 'result': None, 'error': None, 'cancel': False,
        }
        _lg_params = {
            'cadence_list': lg_cad_list, 'cadence_weights': lg_cad_weights,
            'obs_delta_rv': lg_obs_drv,
            'n_stars': int(lg_n_stars), 'sigma_meas': float(lg_sigma_meas),
            'n_proc': int(lg_n_proc),
            'fbin_vals': lg_fbin_vals, 'sigma_vals': lg_sigma_vals,
            'bin_cfg': lg_bin_cfg, 'stable_cfg': lg_stable_cfg,
            'logPmax_scan_vals': lg_logPmax_scan_vals,
            'acc_ks_p': lg_acc_ks_p, 'acc_ks_D': lg_acc_ks_D,
            'missing_fbin_idx': lg_missing_fbin_idx,
            'n_sets_cvm': int(lg_n_sets_cvm),
            'likelihood_bin_edges': _lg_lk_bin_edges,
            'error_model_single': _lg_err_info.get('type_single', 'fixed'),
            'error_params_single': _lg_err_info.get('params_single', ()),
            'error_model_binary': _lg_err_info.get('type_binary', 'fixed'),
            'error_params_binary': _lg_err_info.get('params_binary', ()),
            'save_params': {
                'fbin_min': float(lg_fbin_min), 'fbin_max': float(lg_fbin_max),
                'fbin_steps': int(lg_fbin_steps),
                'sigma_min': float(lg_sigma_min), 'sigma_max': float(lg_sigma_max),
                'sigma_steps': int(lg_sigma_steps),
                'logP_min': float(lg_logP_min), 'logP_max': float(lg_logP_max),
                'weight_A': float(lg_weight_A),
            },
        }
        _lg_t = threading.Thread(target=_run_langer_bg, args=(_lg_job, _lg_params),
                                 daemon=True)
        _lg_t.start()
        st.session_state[f'{p}_job'] = _lg_job
        st.rerun()

    # -- Poll running / completed job -----------------------------------------
    _lg_job = st.session_state.get(f'{p}_job')
    if _lg_job is not None and _lg_job.get('status') == 'running':
        @st.fragment(run_every=3)
        def _langer_live_poll():
            _j = st.session_state.get(f'{p}_job')
            if _j is None or _j.get('status') != 'running':
                st.rerun(scope='app')
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
            if _j.get('live_status'):
                st.markdown(_j['live_status'])
        _langer_live_poll()

    elif _lg_job is not None and _lg_job.get('status') == 'done':
        _lg_res = _lg_job['result']
        st.session_state[f'{p}_result'] = _lg_res
        cached_load_grid_result.clear()
        if _lg_job.get('live_heatmaps'):
            st.session_state[f'{p}_final_live_heatmaps'] = _lg_job['live_heatmaps']
        _lg_elapsed = _lg_job.get('elapsed_total', 0)
        _lg_desc = _lg_job.get('desc_name', '')
        _lg_nc = _lg_job.get('n_cells_total', 0)
        lg_progress_slot.progress(
            1.0, text=f'Done in {_fmt_eta(_lg_elapsed)}.')
        lg_status_slot.success(
            f'Saved to results/{_lg_desc}  '
            f'({_lg_nc} cells computed in {_fmt_eta(_lg_elapsed)})')
        del st.session_state[f'{p}_job']

    elif _lg_job is not None and _lg_job.get('status') == 'error':
        lg_status_slot.error(
            f"Simulation failed:\n```\n{_lg_job['error']}\n```")
        del st.session_state[f'{p}_job']

    elif _lg_job is not None and _lg_job.get('status') == 'cancelled':
        if _lg_job.get('partial_saved'):
            lg_status_slot.warning('Simulation cancelled \u2014 partial progress saved.')
            _scan_partial_metadata.clear()
        else:
            lg_status_slot.warning('Simulation cancelled.')
        del st.session_state[f'{p}_job']

    # -- Show persisted final live heatmaps -----------------------------------
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

    # -- Display result (always shown when result exists) ---------------------
    lg_result = st.session_state.get(f'{p}_result')
    if lg_result is None:
        lg_result = cached_load_grid_result('langer')
        if lg_result is not None:
            st.session_state[f'{p}_result'] = lg_result

    if lg_result is not None:
        lg_fbin_g  = np.asarray(lg_result['fbin_grid'])
        lg_sigma_g = np.asarray(lg_result['sigma_grid'])
        lg_logPmax_g = np.asarray(lg_result.get('logPmax_grid',
                                   [float(lg_logP_max)]))
        lg_ks_p_full = np.asarray(lg_result['ks_p'])
        lg_ks_D_full = np.asarray(lg_result['ks_D'])

        # Detect logPmax scan dimension
        _lg_has_logPmax_scan = len(lg_logPmax_g) > 1

        # Ensure 3D if logPmax scan present: (n_logPmax, n_fbin, n_sigma)
        if _lg_has_logPmax_scan and lg_ks_p_full.ndim == 2:
            lg_ks_p_full = lg_ks_p_full[np.newaxis, ...]
            lg_ks_D_full = lg_ks_D_full[np.newaxis, ...]

        # -- logPmax browse ---------------------------------------------------
        _lg_disp_lp_idx = 0
        if _lg_has_logPmax_scan:
            _lg_outer_max = np.nanmax(lg_ks_p_full, axis=1)  # (n_lp, n_sig)
            lg_heatmap_slot.plotly_chart(
                _make_heatmap_fig(
                    _lg_outer_max, lg_logPmax_g, lg_sigma_g,
                    title=f'Max {_lg_p_lbl}-value  (logP_max × σ_single)',
                    height=_ch, width=_cw,
                    x_label='σ_single (km/s)',
                    y_label='log₁₀(P_max / days)',
                    x_name='σ',
                    best_label_fmt='  logP_max={fbin:.2f}, σ={x:.1f}, p={p:.4f}',
                ),
                use_container_width=_use_cw,
            )
            if np.any(np.isfinite(lg_ks_p_full)):
                _lg_flat = int(np.nanargmax(lg_ks_p_full))
                _lg_best_lp = _lg_flat // (len(lg_fbin_g) * len(lg_sigma_g))
            else:
                _lg_best_lp = 0
            _lg_lp_opts = [round(float(v), 4) for v in lg_logPmax_g]
            _lg_sel_lp = st.select_slider(
                'Browse logP_max heatmaps',
                options=_lg_lp_opts,
                value=_lg_lp_opts[min(_lg_best_lp, len(_lg_lp_opts) - 1)],
                format_func=lambda v: f'{v:.2f}',
                key=f'{p}_logPmax_browse',
            )
            _lg_disp_lp_idx = int(np.argmin(
                np.abs(lg_logPmax_g - _lg_sel_lp)))

        # Slice to 2D for display
        if _lg_has_logPmax_scan:
            lg_ks_p_2d = lg_ks_p_full[_lg_disp_lp_idx]
            lg_ks_D_2d = lg_ks_D_full[_lg_disp_lp_idx]
        else:
            lg_ks_p_2d = lg_ks_p_full if lg_ks_p_full.ndim == 2 else lg_ks_p_full[0]
            lg_ks_D_2d = lg_ks_D_full if lg_ks_D_full.ndim == 2 else lg_ks_D_full[0]

        # Show heatmap (skip if job is running)
        if not _lg_job_running:
            _lp_title = (f', logP_max={lg_logPmax_g[_lg_disp_lp_idx]:.2f}'
                         if _lg_has_logPmax_scan else '')
            lg_heatmap_slot.plotly_chart(
                _make_heatmap_fig(
                    lg_ks_p_2d, lg_fbin_g, lg_sigma_g,
                    title=f'Langer 2020 — {_lg_p_lbl}-value{_lp_title}',
                    show_d=lg_show_d, ks_d_2d=lg_ks_D_2d,
                    height=_ch, width=_cw,
                    x_label='σ_single (km/s)',
                    x_name='σ',
                    best_label_fmt='  f={fbin:.3f}, σ={x:.1f}, p={p:.3f}',
                ),
                use_container_width=_use_cw,
            )

        # -- Find best point for gap_sim computation --------------------------
        if not np.any(np.isfinite(lg_ks_p_full)):
            st.warning('No finite p-values in grid.')
            return
        _flat_best = int(np.nanargmax(lg_ks_p_full))
        if _lg_has_logPmax_scan:
            _n_fb = lg_ks_p_full.shape[1]
            _n_sig = lg_ks_p_full.shape[2]
            best_lp_idx = _flat_best // (_n_fb * _n_sig)
            best_fb_idx = (_flat_best // _n_sig) % _n_fb
            best_sig_idx = _flat_best % _n_sig
        else:
            best_lp_idx = 0
            _arr_2d = lg_ks_p_2d
            _flat_2d = int(np.nanargmax(_arr_2d))
            best_fb_idx = _flat_2d // _arr_2d.shape[1]
            best_sig_idx = _flat_2d % _arr_2d.shape[1]

        ana_logPmax = float(lg_logPmax_g[best_lp_idx])

        # -- Load observed data for model_ctx ---------------------------------
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

        # -- Compute gap_sim at best-fit for analysis plots -------------------
        gap_sim = None
        _bin_cfg_explore = None
        if _has_obs:
            from wr_bias_simulation import (
                SimulationConfig, BinaryParameterConfig,
                simulate_with_params,
            )
            thresh_dRV = float(lg_cls.get('threshold_dRV', 45.5))

            _bin_cfg_explore = BinaryParameterConfig(
                logP_min=float(lg_logP_min),
                logP_max=ana_logPmax,
                period_model='langer2020',
                langer_period_params=lg_period_params,
                e_model='zero', e_max=0.0,
                mass_primary_model=str(lg_mass_model),
                mass_primary_fixed=float(lg_mass_fixed),
                mass_primary_range=tuple(lg_mass_range),
                q_model=str(lg_q_model),
                q_range=(float(lg_q_min), float(lg_q_max)),
                langer_q_mu=float(lg_lq_mu),
                langer_q_sigma=float(lg_lq_sig),
                q_flipped=bool(lg_q_flipped),
            )

            best_fbin_v = float(lg_fbin_g[best_fb_idx])
            best_sigma_v = float(lg_sigma_g[best_sig_idx])

            _sim_cfg_gap = SimulationConfig(
                n_stars=int(lg_n_stars),
                sigma_single=best_sigma_v,
                sigma_measure=float(lg_sigma_meas),
                cadence_library=cadence_list_a,
                cadence_weights=cadence_weights_a,
            )
            _gap_fingerprint = (best_fbin_v, best_sigma_v, ana_logPmax,
                                lg_ks_p_full.shape)
            if (st.session_state.get(f'{p}_gap_fingerprint') != _gap_fingerprint
                    or f'{p}_gap_sim' not in st.session_state):
                rng_gap = np.random.default_rng(199)
                st.session_state[f'{p}_gap_sim'] = simulate_with_params(
                    best_fbin_v, 0.0,  # pi unused for langer
                    _sim_cfg_gap, _bin_cfg_explore, rng_gap,
                )
                st.session_state[f'{p}_gap_fingerprint'] = _gap_fingerprint
                st.session_state.pop(f'{p}_sim_drv', None)
            gap_sim = st.session_state[f'{p}_gap_sim']

        # -- Build model_ctx and delegate to subtabs --------------------------
        from bc.subtabs import render_model_subtabs

        _lg_outer = (_lg_disp_lp_idx,) if _lg_has_logPmax_scan else None

        model_ctx = {
            'model_type': 'langer',
            'ndim_mode': 'langer',
            'x_name': 'sigma',
            'x_label': 'sigma_single',
            'x_display_label': 'σ_single (km/s)',
            'period_model': 'langer2020',
            'has_case_AB': True,
            'result': lg_result,
            'fbin_g': lg_fbin_g,
            'x_g': lg_sigma_g,
            'sigma_g': lg_sigma_g,
            'logPmax_g': lg_logPmax_g,
            'gap_sim': gap_sim,
            'obs_delta_rv': obs_drv_analysis,
            'obs_detail': obs_detail,
            'cadence_list': cadence_list_a,
            'cadence_weights': cadence_weights_a,
            'n_stars_sim': int(lg_n_stars),
            'sigma_meas': float(lg_sigma_meas),
            'bin_cfg': _bin_cfg_explore,
            'logP_min': float(lg_logP_min),
            'logP_max': ana_logPmax,
            'thresh_dRV': float(lg_cls.get('threshold_dRV', 45.5)),
            'canvas_height': _ch,
            'canvas_width': _cw,
            'use_container_width': _use_cw,
            'disp_outer_slices': _lg_outer,
            'settings': settings,
            'classification': lg_cls,
        }

        render_model_subtabs(p, model_ctx)
