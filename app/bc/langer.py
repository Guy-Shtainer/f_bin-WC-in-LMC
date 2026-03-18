"""bc.langer — Langer 2020 bias correction tab renderer."""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
import threading
import time

import numpy as np
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
    SCORING_METHODS, _METHOD_COLORS, _METHOD_SCORING_LABELS, _METHOD_COLORBAR_OVERRIDE,
    _RESULT_DIR, _HISTORY_PATH, _FILENAME_FORMAT_HELP,
    _hex_to_rgba, _fmt_eta, _result_path, _stable_cfg_hash,
    _build_descriptive_filename, _list_saved_results,
    _build_partial_filename, _list_partial_results,
    _scan_partial_metadata, _render_partial_table,
    _scan_result_metadata,
    _make_max_pval_fig, _make_min_score_fig, _make_3d_stacked_fig,
    _find_reusable_fbin_langer, _append_run_history,
    _render_methodology_expander,
    _best_point, _make_heatmap_fig,
)
from bc.analysis import (
    _render_method_summary_section, _render_method_expander,
    _render_cvm_analysis, _get_method_array,
)
from bc.params import _render_orbital_params_langer
from bc.runners import _run_langer_bg
from bc.extras import _render_error_model_selector


# ─────────────────────────────────────────────────────────────────────────────
# Langer 2020 tab renderer
# ─────────────────────────────────────────────────────────────────────────────
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
        f'{p}_mass_fixed': float(lg_cfg.get('mass_primary_fixed', 10.0)),
    }
    for _k, _v in _lg_defaults.items():
        if _k not in st.session_state:
            st.session_state[_k] = _v

    lg_col_left, lg_col_right = st.columns([0.30, 0.70])

    # ── Left column: grid parameters (compact 3-col layout) ────────────────
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

    # ── Right column: orbital params + actions + display ──────────────────
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

        # Action row
        lg_max_proc = max(1, (os.cpu_count() or 2) - 1)
        _lg_ac1, _lg_ac2, _lg_ac3 = st.columns([0.15, 0.25, 0.60])
        lg_n_proc = _lg_ac1.number_input('Workers', 1, lg_max_proc, lg_max_proc,
                                          key=f'{p}_nproc')
        # All 4 scoring methods are computed in a single run
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
            _lg_lk_bin_edges = _render_likelihood_bin_config(p)
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

    # ── Partial results table (replaces single-button detection) ────────────
    _render_partial_table(p, 'langer', lg_status_slot)

    # ── Stable config ─────────────────────────────────────────────────────────
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

    # ── Run grid (background thread) ─────────────────────────────────────────
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

        # ── Check for partial reuse (main thread, needs UI) ──────────────────
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

        # ── Also check partial checkpoint for resume ─────────────────────────
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
            'acc_ks_p': lg_acc_ks_p, 'acc_ks_D': lg_acc_ks_D,
            'missing_fbin_idx': lg_missing_fbin_idx,
            'n_sets_cvm': int(lg_n_sets_cvm),
            'likelihood_bin_edges': _lg_lk_bin_edges,
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

    # ── Poll running / completed job ─────────────────────────────────────────
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
        # Persist final live heatmaps so they remain visible after job cleanup
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
    lg_result = st.session_state.get(f'{p}_result')
    if lg_result is None:
        lg_result = cached_load_grid_result('langer')
        if lg_result is not None:
            st.session_state[f'{p}_result'] = lg_result

    if lg_result is not None:
        lg_fbin_g  = np.asarray(lg_result['fbin_grid'])
        lg_sigma_g = np.asarray(lg_result['sigma_grid'])
        lg_ks_p_2d = np.asarray(lg_result['ks_p'])
        lg_ks_D_2d = np.asarray(lg_result['ks_D'])

        # Show heatmap (skip if job is running — live heatmap shown by poller)
        if not _lg_job_running:
            lg_heatmap_slot.plotly_chart(
                _make_heatmap_fig(
                    lg_ks_p_2d, lg_fbin_g, lg_sigma_g,
                    title=f'Langer 2020 — {_lg_p_lbl}-value',
                    show_d=lg_show_d, ks_d_2d=lg_ks_D_2d,
                    height=_ch, width=_cw,
                    x_label='σ_single (km/s)',
                    x_name='σ',
                    best_label_fmt='  f={fbin:.3f}, σ={x:.1f}, p={p:.3f}',
                ),
                use_container_width=_use_cw,
            )

        # ── Multi-method comparison summary (Langer, shown directly) ─────
        _method_res = _render_method_summary_section(
            lg_result, lg_fbin_g, lg_sigma_g,
            prefix=p, x_name='sigma', x_label='sigma_single',
            ndim_mode='langer',
        )

        # ── Per-method expanders (Langer) ───────────────────────────────
        for _mk, _mname, _pk, _dk, _mcolor in SCORING_METHODS:
            _m_p_arr = _get_method_array(lg_result, _pk)
            if _m_p_arr is None:
                continue
            _m_d_arr = _get_method_array(lg_result, _dk)
            with st.expander(f'{_mname}', expanded=(_mk == 'ks')):
                _render_method_expander(
                    _mk, _mname, _m_p_arr, _m_d_arr,
                    lg_result, lg_fbin_g, lg_sigma_g, prefix=p,
                    height=_ch, width=_cw, use_cw=_use_cw,
                    x_label='sigma_single', x_name='sigma',
                    x_display_label='sigma_single (km/s)',
                    ndim_mode='langer',
                    disp_outer_slices=None,
                    method_results=_method_res,
                )

        # Best-fit point
        best_fbin_lg, best_sigma_lg, best_pval_lg = _best_point(
            lg_ks_p_2d, lg_fbin_g, lg_sigma_g)

        # (Bug 11 removed: old CvM expander is now in per-method expanders)

        # Apply grid exclusion mask to 2D arrays for downstream sections
        # Use stored 1D per-axis masks (includes range sliders + per-value exclusions)
        _cvm_fb_exc = st.session_state.get(f'{p}_cvm_exc_x_mask_1d')
        _cvm_sig_exc = st.session_state.get(f'{p}_cvm_exc_y_mask_1d')
        _has_fb_exc = _cvm_fb_exc is not None and np.any(_cvm_fb_exc)
        _has_sig_exc = _cvm_sig_exc is not None and np.any(_cvm_sig_exc)
        if _has_fb_exc or _has_sig_exc:
            _fb_exc = _cvm_fb_exc if _has_fb_exc else np.zeros(len(lg_fbin_g), dtype=bool)
            _sig_exc = _cvm_sig_exc if _has_sig_exc else np.zeros(len(lg_sigma_g), dtype=bool)
            _lg_exc_2d = _fb_exc[:, None] | _sig_exc[None, :]
            lg_ks_p_2d = lg_ks_p_2d.copy()
            lg_ks_D_2d = lg_ks_D_2d.copy()
            lg_ks_p_2d[_lg_exc_2d] = np.nan
            lg_ks_D_2d[_lg_exc_2d] = np.nan
            best_fbin_lg, best_sigma_lg, best_pval_lg = _best_point(
                lg_ks_p_2d, lg_fbin_g, lg_sigma_g)

        lg_bartzakos = lg_cls.get('bartzakos_binaries', 3)
        lg_total_pop = lg_cls.get('total_population', 28)

        sh_lg_curr = settings_hash(settings)
        try:
            lg_obs_drv_a, _ = cached_load_observed_delta_rvs(sh_lg_curr)
            lg_n_det = int(np.sum(lg_obs_drv_a > lg_cls.get('threshold_dRV', 45.5)))
        except Exception:
            lg_n_det = 0


        # ── Analysis plots (period dist, binary fraction, orbital properties) ─
        from wr_bias_simulation import (
            SimulationConfig, BinaryParameterConfig,
            simulate_delta_rv_sample, _simulate_rv_sample_full,
            simulate_with_params, ks_two_sample,
        )

        sh_lg_a = settings_hash(settings)
        try:
            lg_obs_drv_analysis, lg_obs_detail = cached_load_observed_delta_rvs(sh_lg_a)
            lg_cad_a, lg_cad_w_a = cached_load_cadence(sh_lg_a)
            _lg_has_obs = True
        except Exception:
            _lg_has_obs = False

        if _lg_has_obs:
            lg_thresh_dRV = float(lg_cls.get('threshold_dRV', 45.5))

            _lg_bin_cfg_ex = BinaryParameterConfig(
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
            )

            # Simulate at best-fit
            _lg_sim_cfg_gap = SimulationConfig(
                n_stars=int(lg_n_stars),
                sigma_single=float(best_sigma_lg),
                sigma_measure=float(lg_sigma_meas),
                cadence_library=lg_cad_a,
                cadence_weights=lg_cad_w_a,
            )
            _lg_gap_fp = (best_fbin_lg, best_sigma_lg, lg_ks_p_2d.shape)
            if (st.session_state.get(f'{p}_gap_fingerprint') != _lg_gap_fp
                    or f'{p}_gap_sim' not in st.session_state):
                rng_lg_gap = np.random.default_rng(199)
                st.session_state[f'{p}_gap_sim'] = simulate_with_params(
                    best_fbin_lg, 0.0,  # pi unused for langer
                    _lg_sim_cfg_gap, _lg_bin_cfg_ex, rng_lg_gap,
                )
                st.session_state[f'{p}_gap_fingerprint'] = _lg_gap_fp
                st.session_state.pop(f'{p}_sim_drv', None)
            lg_gap_sim = st.session_state[f'{p}_gap_sim']

            lg_gap_drv = lg_gap_sim['delta_rv']
            lg_gap_is_bin = lg_gap_sim['is_binary']
            lg_gap_idx_bin = lg_gap_sim['idx_bin']

            lg_intrinsic_fbin = float(lg_gap_is_bin.mean())
            lg_detected_mask = lg_gap_drv > lg_thresh_dRV
            lg_observed_fbin = float(lg_detected_mask.mean())
            lg_missed_count = int(np.sum(lg_gap_is_bin & ~lg_detected_mask))
            lg_detected_bin_count = int(np.sum(lg_gap_is_bin & lg_detected_mask))
            lg_total_bin = int(lg_gap_is_bin.sum())

            _lg_bin_drv = lg_gap_drv[lg_gap_idx_bin] if lg_gap_idx_bin.size > 0 else np.array([])
            _lg_bin_det_mask = _lg_bin_drv > lg_thresh_dRV
            _lg_bin_mis_mask = ~_lg_bin_det_mask

            # ── Period Distribution + Binary Fraction vs Threshold ────────────
            st.markdown('---')
            _lg_lp_col, _lg_bf_col = st.columns(2)

            _CLR_DETECTED = '#E25A53'
            _CLR_MISSED   = '#F5A623'

            with _lg_lp_col:
                st.markdown('### Period Distribution  (log P)')

                # Check if Case A/B mask is available
                _lg_case_A = lg_gap_sim.get('case_A_mask')
                _has_cases = _lg_case_A is not None and lg_gap_sim['P_days'].size > 0

                _view_opts = ['Detected / Missed']
                if _has_cases:
                    _view_opts += ['Case A / B', 'All (Det/Mis + A/B)']
                _lg_logP_view = st.radio(
                    'View', _view_opts, horizontal=True,
                    key=f'{p}_logP_view', label_visibility='collapsed')

                # --- Prepare data arrays once ---
                _lg_logP_all = (np.log10(lg_gap_sim['P_days'])
                                if lg_gap_sim['P_days'].size > 0 else np.array([]))
                _lg_logP_det = (_lg_logP_all[_lg_bin_det_mask]
                                if _lg_logP_all.size > 0 and np.any(_lg_bin_det_mask)
                                else np.array([]))
                _lg_logP_mis = (_lg_logP_all[_lg_bin_mis_mask]
                                if _lg_logP_all.size > 0 and np.any(_lg_bin_mis_mask)
                                else np.array([]))
                _show_det = _lg_logP_view in ('Detected / Missed', 'All (Det/Mis + A/B)')
                _show_ab  = _lg_logP_view in ('Case A / B', 'All (Det/Mis + A/B)')

                # Helper: add vlines to a figure
                def _add_logP_vlines(fig):
                    fig.add_vline(x=float(lg_logP_min), line_dash='dash',
                                  line_color='#888', line_width=1.5,
                                  annotation_text='logP_min',
                                  annotation_position='top left',
                                  annotation_font_color='#888')
                    fig.add_vline(x=float(lg_logP_max), line_dash='dash',
                                  line_color='#888', line_width=1.5,
                                  annotation_text='logP_max',
                                  annotation_position='top right',
                                  annotation_font_color='#888')

                # Helper: add histogram traces
                def _add_logP_traces(fig, histnorm_val):
                    if _show_det:
                        if _lg_logP_det.size > 0:
                            fig.add_trace(go.Histogram(
                                x=_lg_logP_det, nbinsx=35,
                                histnorm=histnorm_val,
                                name=f'Detected ({_lg_logP_det.size})',
                                marker_color=_CLR_DETECTED, opacity=0.6,
                            ))
                        if _lg_logP_mis.size > 0:
                            fig.add_trace(go.Histogram(
                                x=_lg_logP_mis, nbinsx=35,
                                histnorm=histnorm_val,
                                name=f'Missed ({_lg_logP_mis.size})',
                                marker_color=_CLR_MISSED, opacity=0.6,
                            ))
                    if _show_ab and _has_cases:
                        _lg_logP_caseA = _lg_logP_all[_lg_case_A]
                        _lg_logP_caseB = _lg_logP_all[~_lg_case_A]
                        if _lg_logP_caseA.size > 0:
                            fig.add_trace(go.Histogram(
                                x=_lg_logP_caseA, nbinsx=35,
                                histnorm=histnorm_val,
                                name=f'Case A ({_lg_logP_caseA.size})',
                                marker_color='#4A90D9', opacity=0.5,
                            ))
                        if _lg_logP_caseB.size > 0:
                            fig.add_trace(go.Histogram(
                                x=_lg_logP_caseB, nbinsx=35,
                                histnorm=histnorm_val,
                                name=f'Case B ({_lg_logP_caseB.size})',
                                marker_color='#F5A623', opacity=0.5,
                            ))

                _lg_logP_title_base = {
                    'Detected / Missed': 'Detected vs Missed',
                    'Case A / B': 'Case A vs Case B',
                    'All (Det/Mis + A/B)': 'All Components',
                }.get(_lg_logP_view, '')

                # ── Plot 1: Probability Density (integral = 1) ──
                fig_lg_logP_pd = go.Figure()
                _add_logP_traces(fig_lg_logP_pd, 'probability density')
                _add_logP_vlines(fig_lg_logP_pd)
                fig_lg_logP_pd.update_layout(**{
                    **PLOTLY_THEME,
                    'barmode': 'overlay',
                    'title': dict(text=f'Period Distribution — {_lg_logP_title_base} (density)',
                                  font=dict(size=14)),
                    'xaxis_title': 'log₁₀(P / days)',
                    'yaxis_title': 'Probability density',
                    'height': 400,
                    'margin': dict(l=60, r=20, t=50, b=50),
                    'legend': dict(x=0.60, y=0.95),
                })
                st.plotly_chart(fig_lg_logP_pd, use_container_width=True,
                                key=f'{p}_logP_hist_density')
                st.caption('**Probability density** normalization (area under curve = 1). '
                           'Best for comparing distribution *shapes* independent of sample size.')

                # ── Plot 2: Fraction per bin (sum = 1), matching Langer+2020 Fig. 6 ──
                fig_lg_logP_fr = go.Figure()
                _add_logP_traces(fig_lg_logP_fr, 'probability')
                _add_logP_vlines(fig_lg_logP_fr)
                fig_lg_logP_fr.update_layout(**{
                    **PLOTLY_THEME,
                    'barmode': 'overlay',
                    'title': dict(text=f'Period Distribution — {_lg_logP_title_base} (fraction)',
                                  font=dict(size=14)),
                    'xaxis_title': 'log₁₀(P / days)',
                    'yaxis_title': 'Fraction of binaries',
                    'height': 400,
                    'margin': dict(l=60, r=20, t=50, b=50),
                    'legend': dict(x=0.60, y=0.95),
                })
                st.plotly_chart(fig_lg_logP_fr, use_container_width=True,
                                key=f'{p}_logP_hist_frac')
                st.caption('**Fraction per bin** normalization (bin heights sum to 1), '
                           'matching the convention used in Langer+2020 Fig. 6. '
                           'Directly comparable to the paper.')

            with _lg_bf_col:
                st.markdown('### Observed Binary Fraction vs Threshold')

                _lg_n_sim = len(lg_gap_drv)
                _lg_thresh_arr = np.linspace(0, float(np.max(lg_gap_drv) * 1.05), 200)
                _lg_fbin_curve = np.array(
                    [float(np.sum(lg_gap_drv > t)) / _lg_n_sim for t in _lg_thresh_arr])

                _lg_bin_drv_all = lg_gap_drv[lg_gap_is_bin]
                _lg_sin_drv_all = lg_gap_drv[~lg_gap_is_bin]
                _lg_missed_curve = np.array(
                    [float(np.sum(_lg_bin_drv_all <= t)) / _lg_n_sim for t in _lg_thresh_arr])
                _lg_fp_curve = np.array(
                    [float(np.sum(_lg_sin_drv_all > t)) / _lg_n_sim for t in _lg_thresh_arr])

                fig_lg_gap = go.Figure()
                fig_lg_gap.add_trace(go.Scatter(
                    x=_lg_thresh_arr, y=_lg_missed_curve,
                    fill='tozeroy', fillcolor='rgba(242,166,35,0.25)',
                    line=dict(width=0), mode='lines',
                    name='Missed binaries', showlegend=True,
                ))
                if np.any(_lg_fp_curve > 0):
                    fig_lg_gap.add_trace(go.Scatter(
                        x=_lg_thresh_arr, y=_lg_fp_curve,
                        fill='tozeroy', fillcolor='rgba(74,144,217,0.25)',
                        line=dict(width=0), mode='lines',
                        name='Singles above threshold', showlegend=True,
                    ))
                fig_lg_gap.add_trace(go.Scatter(
                    x=_lg_thresh_arr, y=_lg_fbin_curve,
                    mode='lines', name='Observed f_bin(threshold)',
                    line=dict(color='#4A90D9', width=2.5),
                ))
                fig_lg_gap.add_hline(
                    y=lg_intrinsic_fbin, line_dash='dot',
                    line_color='#E25A53', line_width=2,
                    annotation_text=f'Intrinsic f_bin = {lg_intrinsic_fbin:.1%}',
                    annotation_position='top left',
                    annotation_font=dict(size=11, color='#E25A53'),
                )
                fig_lg_gap.add_vline(
                    x=lg_thresh_dRV, line_dash='dash',
                    line_color='#F5A623', line_width=2,
                    annotation_text=f'Threshold = {lg_thresh_dRV} km/s',
                    annotation_position='top right',
                    annotation_font=dict(size=11, color='#F5A623'),
                )
                fig_lg_gap.add_trace(go.Scatter(
                    x=[lg_thresh_dRV], y=[lg_observed_fbin],
                    mode='markers+text',
                    marker=dict(size=12, color='#FFD700', symbol='star',
                                line=dict(width=1, color='#fff')),
                    text=[f'{lg_observed_fbin:.1%}'],
                    textposition='top left',
                    textfont=dict(size=12, color='#FFD700'),
                    name=f'Observed @ {lg_thresh_dRV} km/s',
                    showlegend=True,
                ))

                lg_gap_pct = lg_intrinsic_fbin - lg_observed_fbin
                fig_lg_gap.add_annotation(
                    x=lg_thresh_dRV + 15,
                    y=(lg_intrinsic_fbin + lg_observed_fbin) / 2,
                    text=f'Gap: {lg_gap_pct:.1%}<br>({lg_missed_count} missed / {lg_total_bin} binaries)',
                    showarrow=False,
                    font=dict(size=11, color='#F5A623'),
                    bgcolor=pal['annotation_bg'],
                    bordercolor='#F5A623', borderwidth=1, borderpad=4,
                )
                fig_lg_gap.add_annotation(
                    x=lg_thresh_dRV, y=lg_intrinsic_fbin,
                    ax=lg_thresh_dRV, ay=lg_observed_fbin,
                    xref='x', yref='y', axref='x', ayref='y',
                    showarrow=True, arrowhead=3,
                    arrowwidth=2, arrowcolor='#F5A623',
                )
                fig_lg_gap.update_layout(**{
                    **PLOTLY_THEME,
                    'title': dict(text='Binary Fraction vs ΔRV Threshold',
                                  font=dict(size=14)),
                    'xaxis_title': 'ΔRV threshold (km/s)',
                    'yaxis_title': 'Fraction of sample',
                    'height': 400,
                    'margin': dict(l=60, r=80, t=50, b=50),
                    'showlegend': True,
                    'legend': dict(x=0.55, y=0.95, font=dict(size=10)),
                    'yaxis': dict(range=[0, min(1.0, lg_intrinsic_fbin * 1.5)]),
                })
                st.plotly_chart(fig_lg_gap, use_container_width=True, key=f'{p}_gap_chart')
                st.caption(
                    f'Binary fraction as a function of ΔRV threshold (Langer model). '
                    f'At {lg_thresh_dRV} km/s: observed = {lg_observed_fbin:.1%}, '
                    f'intrinsic = {lg_intrinsic_fbin:.1%}, '
                    f'gap = {lg_gap_pct:.1%} ({lg_missed_count} missed).'
                )

            # ── Binary Orbital Parameter Histograms ───────────────────────────
            st.markdown('---')
            st.markdown('### Binary Orbital Properties')

            _lg_has_case_mask = lg_gap_sim.get('case_A_mask') is not None
            _lg_mb_opts = ['Compare detected vs missed', 'Detected binaries only',
                           'Missed binaries only', 'All binaries (combined)']
            if _lg_has_case_mask:
                _lg_mb_opts.append('Case A vs Case B')
            _lg_mb_view = st.radio(
                'Show populations', _lg_mb_opts,
                horizontal=True, key=f'{p}_mb_view',
            )

            def _lg_safe_mask(arr, mask):
                return arr[mask] if arr.size > 0 else np.array([])

            lg_P_det = _lg_safe_mask(lg_gap_sim['P_days'], _lg_bin_det_mask)
            lg_P_mis = _lg_safe_mask(lg_gap_sim['P_days'], _lg_bin_mis_mask)
            lg_e_det = _lg_safe_mask(lg_gap_sim['e'], _lg_bin_det_mask)
            lg_e_mis = _lg_safe_mask(lg_gap_sim['e'], _lg_bin_mis_mask)
            lg_q_det = _lg_safe_mask(lg_gap_sim['q'], _lg_bin_det_mask)
            lg_q_mis = _lg_safe_mask(lg_gap_sim['q'], _lg_bin_mis_mask)
            lg_K1_det = _lg_safe_mask(lg_gap_sim['K1'], _lg_bin_det_mask)
            lg_K1_mis = _lg_safe_mask(lg_gap_sim['K1'], _lg_bin_mis_mask)
            lg_M1_det = _lg_safe_mask(lg_gap_sim['M1'], _lg_bin_det_mask)
            lg_M1_mis = _lg_safe_mask(lg_gap_sim['M1'], _lg_bin_mis_mask)
            lg_i_det = np.degrees(_lg_safe_mask(lg_gap_sim['i_rad'], _lg_bin_det_mask))
            lg_i_mis = np.degrees(_lg_safe_mask(lg_gap_sim['i_rad'], _lg_bin_mis_mask))

            _lg_has_omega = 'omega' in lg_gap_sim
            if _lg_has_omega:
                lg_omega_det = np.degrees(_lg_safe_mask(lg_gap_sim['omega'], _lg_bin_det_mask))
                lg_omega_mis = np.degrees(_lg_safe_mask(lg_gap_sim['omega'], _lg_bin_mis_mask))
                lg_T0_det = _lg_safe_mask(lg_gap_sim['T0'], _lg_bin_det_mask)
                lg_T0_mis = _lg_safe_mask(lg_gap_sim['T0'], _lg_bin_mis_mask)
            else:
                lg_omega_det = lg_omega_mis = lg_T0_det = lg_T0_mis = np.array([])

            lg_M2_det = lg_q_det * lg_M1_det if lg_q_det.size > 0 and lg_M1_det.size > 0 else np.array([])
            lg_M2_mis = lg_q_mis * lg_M1_mis if lg_q_mis.size > 0 and lg_M1_mis.size > 0 else np.array([])

            lg_P_all = lg_gap_sim['P_days']
            lg_e_all = lg_gap_sim['e']
            lg_q_all = lg_gap_sim['q']
            lg_K1_all = lg_gap_sim['K1']
            lg_M1_all = lg_gap_sim['M1']
            lg_i_all = np.degrees(lg_gap_sim['i_rad'])
            lg_omega_all = np.degrees(lg_gap_sim['omega']) if _lg_has_omega else np.array([])
            lg_T0_all = lg_gap_sim['T0'] if _lg_has_omega else np.array([])
            lg_M2_all = lg_q_all * lg_M1_all if lg_q_all.size > 0 else np.array([])

            from plotly.subplots import make_subplots as _lg_make_subplots

            _lg_titles = [
                'log₁₀(P / days)', 'Eccentricity', 'Mass ratio q',
                'K₁ (km/s)', 'M₁ (M⊙)', 'M₂ (M⊙)',
                'Inclination (°)', 'ω (°)', 'T₀ (rad)',
            ]
            _lg_x_labels = [
                'log₁₀(P / days)', 'e', 'q = M₂/M₁',
                'K₁ (km/s)', 'M₁ (M⊙)', 'M₂ (M⊙)',
                'i (degrees)', 'ω (degrees)', 'T₀ (rad)',
            ]
            _lg_n_panels = 9
            _lg_n_cols = 3
            _lg_n_rows = 3
            _lg_nbins = 30

            fig_lg_mb = _lg_make_subplots(
                rows=_lg_n_rows, cols=_lg_n_cols,
                subplot_titles=_lg_titles,
                horizontal_spacing=0.08, vertical_spacing=0.10)

            _CLR_ALL = '#52B788'

            def _lg_add_hist(fig, row, col, data, name, color, show_legend):
                if data.size == 0:
                    return
                d_min, d_max = float(data.min()), float(data.max())
                bin_sz = (d_max - d_min) / _lg_nbins if d_max > d_min else 1.0
                fig.add_trace(go.Histogram(
                    x=data,
                    xbins=dict(start=d_min, end=d_max + bin_sz * 0.01, size=bin_sz),
                    histnorm='probability density',
                    name=name, marker_color=color, opacity=0.6,
                    legendgroup=name, showlegend=show_legend,
                ), row=row, col=col)

            def _lg_pos(idx):
                return (idx // _lg_n_cols + 1, idx % _lg_n_cols + 1)

            if _lg_mb_view == 'All binaries (combined)':
                _lg_data_all = [
                    np.log10(lg_P_all) if lg_P_all.size > 0 else lg_P_all,
                    lg_e_all, lg_q_all, lg_K1_all, lg_M1_all, lg_M2_all,
                    lg_i_all, lg_omega_all, lg_T0_all,
                ]
                for pi, d in enumerate(_lg_data_all):
                    r, c = _lg_pos(pi)
                    _lg_add_hist(fig_lg_mb, r, c, d, 'All binaries', _CLR_ALL, pi == 0)
            elif _lg_mb_view == 'Case A vs Case B':
                _lg_cA = lg_gap_sim['case_A_mask']
                _lg_cB = ~_lg_cA
                _lg_cA_data = [
                    np.log10(_lg_safe_mask(lg_gap_sim['P_days'], _lg_cA)),
                    _lg_safe_mask(lg_gap_sim['e'], _lg_cA),
                    _lg_safe_mask(lg_gap_sim['q'], _lg_cA),
                    _lg_safe_mask(lg_gap_sim['K1'], _lg_cA),
                    _lg_safe_mask(lg_gap_sim['M1'], _lg_cA),
                    _lg_safe_mask(lg_gap_sim['q'], _lg_cA) * _lg_safe_mask(lg_gap_sim['M1'], _lg_cA),
                    np.degrees(_lg_safe_mask(lg_gap_sim['i_rad'], _lg_cA)),
                    np.degrees(_lg_safe_mask(lg_gap_sim.get('omega', np.array([])), _lg_cA)) if 'omega' in lg_gap_sim else np.array([]),
                    _lg_safe_mask(lg_gap_sim.get('T0', np.array([])), _lg_cA) if 'T0' in lg_gap_sim else np.array([]),
                ]
                _lg_cB_data = [
                    np.log10(_lg_safe_mask(lg_gap_sim['P_days'], _lg_cB)),
                    _lg_safe_mask(lg_gap_sim['e'], _lg_cB),
                    _lg_safe_mask(lg_gap_sim['q'], _lg_cB),
                    _lg_safe_mask(lg_gap_sim['K1'], _lg_cB),
                    _lg_safe_mask(lg_gap_sim['M1'], _lg_cB),
                    _lg_safe_mask(lg_gap_sim['q'], _lg_cB) * _lg_safe_mask(lg_gap_sim['M1'], _lg_cB),
                    np.degrees(_lg_safe_mask(lg_gap_sim['i_rad'], _lg_cB)),
                    np.degrees(_lg_safe_mask(lg_gap_sim.get('omega', np.array([])), _lg_cB)) if 'omega' in lg_gap_sim else np.array([]),
                    _lg_safe_mask(lg_gap_sim.get('T0', np.array([])), _lg_cB) if 'T0' in lg_gap_sim else np.array([]),
                ]
                _n_cA = int(_lg_cA.sum())
                _n_cB = int(_lg_cB.sum())
                for pi, d in enumerate(_lg_cA_data):
                    r, c = _lg_pos(pi)
                    _lg_add_hist(fig_lg_mb, r, c, d, f'Case A ({_n_cA})', '#4A90D9', pi == 0)
                for pi, d in enumerate(_lg_cB_data):
                    r, c = _lg_pos(pi)
                    _lg_add_hist(fig_lg_mb, r, c, d, f'Case B ({_n_cB})', '#F5A623', pi == 0)
            else:
                _lg_det_data = [
                    np.log10(lg_P_det) if lg_P_det.size > 0 else lg_P_det,
                    lg_e_det, lg_q_det, lg_K1_det, lg_M1_det, lg_M2_det,
                    lg_i_det, lg_omega_det, lg_T0_det,
                ]
                _lg_mis_data = [
                    np.log10(lg_P_mis) if lg_P_mis.size > 0 else lg_P_mis,
                    lg_e_mis, lg_q_mis, lg_K1_mis, lg_M1_mis, lg_M2_mis,
                    lg_i_mis, lg_omega_mis, lg_T0_mis,
                ]
                if _lg_mb_view in ('Compare detected vs missed', 'Detected binaries only'):
                    for pi, d in enumerate(_lg_det_data):
                        r, c = _lg_pos(pi)
                        _lg_add_hist(fig_lg_mb, r, c, d, 'Detected', _CLR_DETECTED, pi == 0)
                if _lg_mb_view in ('Compare detected vs missed', 'Missed binaries only'):
                    for pi, d in enumerate(_lg_mis_data):
                        r, c = _lg_pos(pi)
                        _lg_add_hist(fig_lg_mb, r, c, d, 'Missed', _CLR_MISSED, pi == 0)

            fig_lg_mb.update_layout(**{
                **PLOTLY_THEME,
                'barmode': 'overlay',
                'height': 850,
                'margin': dict(l=40, r=20, t=40, b=60),
                'legend': dict(
                    orientation='h', yanchor='bottom', y=1.04,
                    xanchor='center', x=0.5,
                ),
            })
            for pi in range(_lg_n_panels):
                r, c = _lg_pos(pi)
                fig_lg_mb.update_xaxes(title_text=_lg_x_labels[pi],
                                        showgrid=False, row=r, col=c)
                fig_lg_mb.update_yaxes(showgrid=False, row=r, col=c)
            for row_i in range(1, _lg_n_rows + 1):
                fig_lg_mb.update_yaxes(title_text='Prob. density', row=row_i, col=1)

            st.plotly_chart(fig_lg_mb, use_container_width=True, key=f'{p}_orb_props')
            st.caption(
                f'Orbital parameter distributions (Langer 2020 model, best-fit: '
                f'f_bin={best_fbin_lg:.3f}, σ_single={best_sigma_lg:.1f} km/s). '
                f'**Detected** (red): {lg_detected_bin_count} binaries. '
                f'**Missed** (amber): {lg_missed_count} binaries.'
            )

            # ── Model Explorer ────────────────────────────────────────────────
            st.markdown('---')
            st.markdown('## Model Explorer')

            _lg_me1, _lg_me2, _lg_me3 = st.columns([0.35, 0.35, 0.30])
            lg_ex_fbin = _lg_me1.number_input(
                'f_bin', 0.0, 1.0, best_fbin_lg, 0.001, format='%.4f',
                key=f'{p}_explore_fbin')
            lg_ex_sigma = _lg_me2.number_input(
                'σ_single (km/s)', 0.1, 500.0, best_sigma_lg, 0.1,
                key=f'{p}_explore_sigma')
            lg_sim_btn = _lg_me3.button('Simulate model', type='primary',
                                         key=f'{p}_sim_model')
            st.caption('Pre-filled with best-fit values. Adjust to explore any model point.')

            _lg_sim_cfg_ex = SimulationConfig(
                n_stars=int(lg_n_stars),
                sigma_single=float(lg_ex_sigma),
                sigma_measure=float(lg_sigma_meas),
                cadence_library=lg_cad_a,
                cadence_weights=lg_cad_w_a,
            )

            _lg_need_sim = lg_sim_btn or f'{p}_sim_drv' not in st.session_state
            if _lg_need_sim:
                rng_lg_ex = np.random.default_rng(142)
                st.session_state[f'{p}_sim_drv'] = simulate_delta_rv_sample(
                    float(lg_ex_fbin), 0.0,
                    _lg_sim_cfg_ex, _lg_bin_cfg_ex, rng_lg_ex,
                )
                rng_lg_ex2 = np.random.default_rng(142)
                lg_rv_s, lg_rv_b = _simulate_rv_sample_full(
                    float(lg_ex_fbin), 0.0,
                    _lg_sim_cfg_ex, _lg_bin_cfg_ex, rng_lg_ex2,
                )
                st.session_state[f'{p}_sim_rv_single'] = lg_rv_s
                st.session_state[f'{p}_sim_rv_binary'] = lg_rv_b
                st.session_state[f'{p}_explore_vals'] = (
                    float(lg_ex_fbin), float(lg_ex_sigma))

            lg_sim_drv = st.session_state.get(f'{p}_sim_drv')
            lg_sim_rv_single = st.session_state.get(f'{p}_sim_rv_single')
            lg_sim_rv_binary = st.session_state.get(f'{p}_sim_rv_binary')
            lg_ex_fb_v, lg_ex_sig_v = st.session_state.get(
                f'{p}_explore_vals', (best_fbin_lg, best_sigma_lg))

            if lg_sim_drv is not None:
                # ── CDF Comparison (binned) ──────────────────────────────────
                st.markdown('### CDF Comparison  (ΔRV)')

                from wr_bias_simulation import binned_cdf, ks_two_sample_binned, DEFAULT_DRV_BIN_EDGES
                _bin_edges = DEFAULT_DRV_BIN_EDGES
                lg_obs_cdf_binned = binned_cdf(lg_obs_drv_analysis, _bin_edges)
                lg_sim_cdf_binned = binned_cdf(lg_sim_drv, _bin_edges)

                lg_D_val, lg_p_val = ks_two_sample_binned(lg_sim_drv, lg_obs_drv_analysis, _bin_edges)

                fig_lg_cdf = go.Figure()
                fig_lg_cdf.add_trace(go.Scatter(
                    x=_bin_edges, y=lg_obs_cdf_binned,
                    mode='lines', name='Observed',
                    line=dict(color='#4A90D9', width=2.5, shape='hv'),
                ))
                fig_lg_cdf.add_trace(go.Scatter(
                    x=_bin_edges, y=lg_sim_cdf_binned,
                    mode='lines', name='Simulated',
                    line=dict(color='#E25A53', width=2.5, dash='dash', shape='hv'),
                ))
                fig_lg_cdf.update_layout(**{
                    **PLOTLY_THEME,
                    'title': dict(
                        text=(f'Binned ΔRV CDF — Observed vs Langer Model  '
                              f'(f_bin={lg_ex_fb_v:.3f}, σ={lg_ex_sig_v:.1f})'),
                        font=dict(size=14)),
                    'xaxis_title': 'ΔRV (km/s)',
                    'yaxis_title': 'Cumulative fraction',
                    'height': 420,
                    'legend': dict(x=0.65, y=0.15),
                    'annotations': [dict(
                        x=0.98, y=0.95, xref='paper', yref='paper',
                        text=f'Binned {_lg_stat_name} {_lg_stat_sym} = {lg_D_val:.4f}<br>p = {lg_p_val:.4f}',
                        showarrow=False,
                        font=dict(size=12, color=pal['annotation_font']),
                        bgcolor=pal['annotation_bg'],
                        borderpad=6, xanchor='right',
                    )],
                })
                st.plotly_chart(fig_lg_cdf, use_container_width=True, key=f'{p}_cdf')
                st.caption(
                    'Binned CDF of peak-to-peak ΔRV (Langer 2020 model, 10 km/s bins). '
                    'Higher p-value indicates a better match between model and observations.'
                )

                # ── RV Distribution ───────────────────────────────────────────
                st.markdown('### RV Distribution')

                lg_obs_rv_all_list = []
                lg_obs_rv_bin_list = []
                lg_obs_rv_sin_list = []
                for star_name, info in lg_obs_detail.items():
                    rv_arr = info.get('rv')
                    if rv_arr is None or len(rv_arr) == 0:
                        continue
                    lg_obs_rv_all_list.append(rv_arr)
                    if bool(info.get('is_binary', False)):
                        lg_obs_rv_bin_list.append(rv_arr)
                    else:
                        lg_obs_rv_sin_list.append(rv_arr)

                lg_obs_rv_all = np.concatenate(lg_obs_rv_all_list) if lg_obs_rv_all_list else np.array([])
                lg_obs_rv_sin = np.concatenate(lg_obs_rv_sin_list) if lg_obs_rv_sin_list else np.array([])
                lg_obs_rv_bin = np.concatenate(lg_obs_rv_bin_list) if lg_obs_rv_bin_list else np.array([])

                _lg_rv_c1, _lg_rv_c2 = st.columns([0.4, 0.6])
                lg_rv_split = _lg_rv_c1.radio(
                    'Observed RVs', ['All combined', 'Split by classification'],
                    horizontal=True, key=f'{p}_rv_split')
                lg_show_sim_rv = _lg_rv_c2.checkbox(
                    'Overlay simulated RVs', value=True, key=f'{p}_show_sim_rv')

                fig_lg_rv = go.Figure()
                lg_nbins_rv = 40

                if lg_rv_split == 'All combined':
                    if lg_obs_rv_all.size > 0:
                        fig_lg_rv.add_trace(go.Histogram(
                            x=lg_obs_rv_all, nbinsx=lg_nbins_rv,
                            histnorm='probability density',
                            name='Observed (all)',
                            marker_color='#4A90D9', opacity=0.6,
                        ))
                else:
                    if lg_obs_rv_sin.size > 0:
                        fig_lg_rv.add_trace(go.Histogram(
                            x=lg_obs_rv_sin, nbinsx=lg_nbins_rv,
                            histnorm='probability density',
                            name='Observed — single',
                            marker_color='#4A90D9', opacity=0.5,
                        ))
                    if lg_obs_rv_bin.size > 0:
                        fig_lg_rv.add_trace(go.Histogram(
                            x=lg_obs_rv_bin, nbinsx=lg_nbins_rv,
                            histnorm='probability density',
                            name='Observed — binary',
                            marker_color='#E25A53', opacity=0.5,
                        ))

                if lg_show_sim_rv and lg_sim_rv_single is not None:
                    if lg_rv_split == 'All combined':
                        _lg_sim_rv_comb = np.concatenate([lg_sim_rv_single, lg_sim_rv_binary])
                        if _lg_sim_rv_comb.size > 0:
                            fig_lg_rv.add_trace(go.Histogram(
                                x=_lg_sim_rv_comb, nbinsx=lg_nbins_rv,
                                histnorm='probability density',
                                name='Simulated (all)',
                                marker_color='#8C8C8C', opacity=0.4,
                            ))
                    else:
                        if lg_sim_rv_single.size > 0:
                            fig_lg_rv.add_trace(go.Histogram(
                                x=lg_sim_rv_single, nbinsx=lg_nbins_rv,
                                histnorm='probability density',
                                name='Simulated — single',
                                marker_color='#7EC8E3', opacity=0.4,
                            ))
                        if lg_sim_rv_binary.size > 0:
                            fig_lg_rv.add_trace(go.Histogram(
                                x=lg_sim_rv_binary, nbinsx=lg_nbins_rv,
                                histnorm='probability density',
                                name='Simulated — binary',
                                marker_color='#F0A0A0', opacity=0.4,
                            ))

                fig_lg_rv.update_layout(**{
                    **PLOTLY_THEME,
                    'barmode': 'overlay',
                    'title': dict(text='RV Distribution (Langer)', font=dict(size=14)),
                    'xaxis_title': 'RV (km/s)',
                    'yaxis_title': 'Probability density',
                    'height': 420,
                    'legend': dict(x=0.01, y=0.99),
                })
                st.plotly_chart(fig_lg_rv, use_container_width=True, key=f'{p}_rv_dist')
                st.caption(
                    'RV distribution: observed vs simulated (Langer 2020 model).'
                )

                # ── Detection Fraction vs Threshold ───────────────────────────
                st.markdown('### Detection Fraction vs Threshold')

                lg_max_drv = max(float(np.max(lg_obs_drv_analysis)),
                                 float(np.max(lg_sim_drv)))
                lg_thresholds = np.linspace(0, lg_max_drv * 1.1, 150)
                lg_frac_obs = np.array(
                    [(lg_obs_drv_analysis > T).mean() for T in lg_thresholds])
                lg_frac_sim = np.array(
                    [(lg_sim_drv > T).mean() for T in lg_thresholds])

                lg_frac_obs_t = float((lg_obs_drv_analysis > lg_thresh_dRV).mean())
                lg_frac_sim_t = float((lg_sim_drv > lg_thresh_dRV).mean())

                fig_lg_frac = go.Figure()
                fig_lg_frac.add_trace(go.Scatter(
                    x=lg_thresholds, y=lg_frac_obs,
                    mode='lines', name='Observed',
                    line=dict(color='#4A90D9', width=2.5),
                ))
                fig_lg_frac.add_trace(go.Scatter(
                    x=lg_thresholds, y=lg_frac_sim,
                    mode='lines', name='Simulated',
                    line=dict(color='#E25A53', width=2.5, dash='dash'),
                ))
                fig_lg_frac.add_vline(
                    x=lg_thresh_dRV, line_dash='dot',
                    line_color='#DAA520', line_width=1.5,
                    annotation_text=f'Threshold = {lg_thresh_dRV} km/s',
                    annotation_position='top right',
                    annotation_font_color='#DAA520',
                )
                fig_lg_frac.add_trace(go.Scatter(
                    x=[lg_thresh_dRV, lg_thresh_dRV],
                    y=[lg_frac_obs_t, lg_frac_sim_t],
                    mode='markers+text',
                    marker=dict(size=10, color=['#4A90D9', '#E25A53'],
                                symbol='circle',
                                line=dict(color=pal['plot_bg'], width=1)),
                    text=[f'  {lg_frac_obs_t:.2%}', f'  {lg_frac_sim_t:.2%}'],
                    textposition='middle right',
                    textfont=dict(size=11),
                    showlegend=False,
                ))
                fig_lg_frac.update_layout(**{
                    **PLOTLY_THEME,
                    'title': dict(
                        text=(f'Detection Fraction vs ΔRV Threshold  '
                              f'(Langer: f_bin={lg_ex_fb_v:.3f}, σ={lg_ex_sig_v:.1f})'),
                        font=dict(size=14)),
                    'xaxis_title': 'ΔRV threshold (km/s)',
                    'yaxis_title': 'Fraction above threshold',
                    'height': 420,
                    'legend': dict(x=0.70, y=0.95),
                    'yaxis': dict(range=[0, 1.05]),
                })
                st.plotly_chart(fig_lg_frac, use_container_width=True, key=f'{p}_det_frac')
                st.caption(
                    'Detection fraction as a function of threshold (Langer 2020 model).'
                )

        # (Bug 12 removed: old summary table is now in per-method expanders)

        # ── Methodology Expander (Langer) ────────────────────────────────────
        _render_methodology_expander('langer')



