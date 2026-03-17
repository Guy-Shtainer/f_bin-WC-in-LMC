"""bc.dsilva — Dsilva (power-law) bias correction tab renderer."""
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
    _find_reusable_fbin, _append_run_history,
    _render_methodology_expander,
    _best_point, _make_heatmap_fig,
)
from bc.analysis import (
    _render_method_summary_section, _render_method_expander,
    _render_cvm_analysis,
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
            f'{p}_sigma_min':          max(0.1, _sigma_default - 2.0),
            f'{p}_sigma_max':          _sigma_default + 2.0,
            f'{p}_sigma_steps':        5,
            f'{p}_logPmax_scan_min':   1.0,
            f'{p}_logPmax_scan_max':   6.0,
            f'{p}_logPmax_scan_steps': 20,
        }
        for _k, _v in _bc_defaults.items():
            if _k not in st.session_state:
                st.session_state[_k] = _v

        with st.expander('🎚️ σ_single scan (intrinsic single-star scatter)', expanded=True):
            scan_sigma = st.toggle('Scan σ_single over a range', key=f'{p}_scan_sigma')
            if scan_sigma:
                _sc1, _sc2, _sc3 = st.columns(3)
                sigma_min = _sc1.number_input(
                    'σ_single min (km/s)', 0.1, 500.0,
                    float(st.session_state[f'{p}_sigma_min']), 0.1,
                    key=f'{p}_sigma_min')
                sigma_max_val_w = _sc2.number_input(
                    'σ_single max (km/s)', 0.5, 500.0,
                    float(st.session_state[f'{p}_sigma_max']), 0.1,
                    key=f'{p}_sigma_max')
                sigma_steps = _sc3.number_input(
                    'σ_single steps', 2, 500,
                    int(st.session_state[f'{p}_sigma_steps']), 1,
                    key=f'{p}_sigma_steps')
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
            scan_logPmax = st.toggle('Scan logP_max over a range', key=f'{p}_scan_logPmax')
            if scan_logPmax:
                _lp_c1, _lp_c2, _lp_c3 = st.columns(3)
                logPmax_scan_min = _lp_c1.number_input(
                    'logP_max min', 0.5, 10.0,
                    float(st.session_state[f'{p}_logPmax_scan_min']), 0.1,
                    key=f'{p}_logPmax_scan_min')
                logPmax_scan_max = _lp_c2.number_input(
                    'logP_max max', 1.0, 10.0,
                    float(st.session_state[f'{p}_logPmax_scan_max']), 0.1,
                    key=f'{p}_logPmax_scan_max')
                logPmax_scan_steps = _lp_c3.number_input(
                    'logP_max steps', 3, 100,
                    int(st.session_state[f'{p}_logPmax_scan_steps']), 1,
                    key=f'{p}_logPmax_scan_steps')
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
        from wr_bias_simulation import dsilva_likelihood_bins
        _lk_threshold = _cvm_cols[1].number_input(
            'Detection threshold (km/s)', value=45.5,
            min_value=1.0, max_value=200.0, step=0.5,
            key=f'{p}_lk_threshold',
            help='First bin boundary (Dsilva+2023 Sec 4.2)')
        _lk_bin_edges = dsilva_likelihood_bins(_lk_threshold)
        _cvm_cols[1].caption(
            f'Likelihood bins: [0, {_lk_threshold:.1f}) '
            f'[{_lk_threshold:.1f}, 250) [250, 650) [650+) km/s')
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

        # ── Multi-method comparison summary (shown directly, not collapsed) ─
        _render_method_summary_section(
            result, fbin_g, pi_g,
            prefix=p, x_name='pi', x_label='pi',
            ndim_mode='dsilva',
        )

        # ── Per-method expanders ────────────────────────────────────────
        _ds_outer_slices = (disp_lp_idx, disp_sig_idx)
        for _mk, _mname, _pk, _dk, _mcolor in SCORING_METHODS:
            _m_p_arr = _get_method_array(result, _pk)
            if _m_p_arr is None:
                continue
            # Ensure 4D
            if _m_p_arr.ndim == 2:
                _m_p_arr = _m_p_arr[np.newaxis, np.newaxis, ...]
            elif _m_p_arr.ndim == 3:
                _m_p_arr = _m_p_arr[np.newaxis, ...]
            _m_d_arr = _get_method_array(result, _dk)
            if _m_d_arr is not None:
                if _m_d_arr.ndim == 2:
                    _m_d_arr = _m_d_arr[np.newaxis, np.newaxis, ...]
                elif _m_d_arr.ndim == 3:
                    _m_d_arr = _m_d_arr[np.newaxis, ...]
            with st.expander(f'{_mname}', expanded=(_mk == 'ks')):
                _render_method_expander(
                    _mk, _mname, _m_p_arr, _m_d_arr,
                    result, fbin_g, pi_g, prefix=p,
                    height=_ch, width=_cw, use_cw=_use_cw,
                    x_label='pi', x_name='pi',
                    x_display_label='pi (period power-law index)',
                    ndim_mode='dsilva',
                    disp_outer_slices=_ds_outer_slices,
                )

        # (Bug 2 removed: old heatmap_slot render is now handled by per-method expanders)

        # Best across ALL dimensions
        best_fbin_v   = float(fbin_g[best_fb_idx])
        best_pi_v     = float(pi_g[best_pi_idx])
        best_sigma_v  = float(sigma_g[best_sig_idx])
        best_logPmax_v = float(logPmax_g[best_lp_idx])
        best_pval_v   = float(ks_p_4d[best_lp_idx, best_sig_idx, best_fb_idx, best_pi_idx])

        # Current slice best
        _cur_slice_2d = ks_p_4d[disp_lp_idx, disp_sig_idx]
        _slice_fb, _slice_pi, _slice_pval = _best_point(
            _cur_slice_2d, fbin_g, pi_g)
        _cur_logPmax_v = float(logPmax_g[disp_lp_idx])
        _cur_sigma_v = float(sigma_g[disp_sig_idx])

        # (Bug 11+12 removed: old CvM expander and orphaned metrics are now in per-method expanders)

        # Apply grid exclusion mask to 4D arrays for downstream sections
        # Use stored 1D per-axis masks (includes range sliders + per-value exclusions)
        _cvm_fb_exc = st.session_state.get(f'{p}_cvm_exc_x_mask_1d')
        _cvm_pi_exc = st.session_state.get(f'{p}_cvm_exc_y_mask_1d')
        _has_fb_exc = _cvm_fb_exc is not None and np.any(_cvm_fb_exc)
        _has_pi_exc = _cvm_pi_exc is not None and np.any(_cvm_pi_exc)
        if _has_fb_exc or _has_pi_exc:
            _fb_exc = _cvm_fb_exc if _has_fb_exc else np.zeros(len(fbin_g), dtype=bool)
            _pi_exc = _cvm_pi_exc if _has_pi_exc else np.zeros(len(pi_g), dtype=bool)
            _exc_2d = _fb_exc[:, None] | _pi_exc[None, :]
            ks_p_4d = ks_p_4d.copy()
            ks_D_4d = ks_D_4d.copy()
            for _i_lp in range(ks_p_4d.shape[0]):
                for _i_sig in range(ks_p_4d.shape[1]):
                    ks_p_4d[_i_lp, _i_sig][_exc_2d] = np.nan
                    ks_D_4d[_i_lp, _i_sig][_exc_2d] = np.nan
            # Recompute best across all dimensions
            _valid_mask = np.isfinite(ks_p_4d)
            if _valid_mask.any():
                _flat_best_4d = int(np.nanargmax(ks_p_4d))
                best_lp_idx  = _flat_best_4d // (_n_sig * _n_fb * _n_pi)
                best_sig_idx = (_flat_best_4d // (_n_fb * _n_pi)) % _n_sig
                best_fb_idx  = (_flat_best_4d // _n_pi) % _n_fb
                best_pi_idx  = _flat_best_4d % _n_pi
                best_fbin_v  = float(fbin_g[best_fb_idx])
                best_pi_v    = float(pi_g[best_pi_idx])
                best_sigma_v = float(sigma_g[best_sig_idx])
                best_logPmax_v = float(logPmax_g[best_lp_idx])
                best_pval_v  = float(ks_p_4d[best_lp_idx, best_sig_idx, best_fb_idx, best_pi_idx])

        # Toggle: use current slice for downstream analysis
        _use_slice = st.checkbox(
            'Use current slice for analysis plots below',
            value=False,
            key=f'{p}_use_slice',
            help='When checked, downstream graphs use the best-fit from '
                 'the currently selected σ/logP_max slice instead of the '
                 'global argmax.',
        )

        # Determine which values drive downstream analysis
        if _use_slice:
            _ana_fbin = _slice_fb
            _ana_pi = _slice_pi
            _ana_sigma = _cur_sigma_v
            _ana_logPmax = _cur_logPmax_v
        else:
            _ana_fbin = best_fbin_v
            _ana_pi = best_pi_v
            _ana_sigma = best_sigma_v
            _ana_logPmax = best_logPmax_v

        bartzakos = cls.get('bartzakos_binaries', 3)
        total_pop = cls.get('total_population', 28)

        sh_curr = settings_hash(settings)
        try:
            obs_drv, _ = cached_load_observed_delta_rvs(sh_curr)
            n_det = int(np.sum(obs_drv > cls.get('threshold_dRV', 45.5)))
        except Exception:
            n_det = 0


        # ── Import simulation functions for analysis plots ─────────────────
        from wr_bias_simulation import (
            SimulationConfig, BinaryParameterConfig,
            simulate_delta_rv_sample, _simulate_rv_sample_full,
            simulate_with_params, ks_two_sample,
        )

        # Load observed data for analysis plots
        sh_analysis = settings_hash(settings)
        try:
            obs_drv_analysis, obs_detail = cached_load_observed_delta_rvs(sh_analysis)
            cadence_list_a, cadence_weights_a = cached_load_cadence(sh_analysis)
            _has_obs = True
        except Exception:
            _has_obs = False

        if _has_obs:
            thresh_dRV = float(cls.get('threshold_dRV', 45.5))

            # Build shared configs (use analysis logP_max)
            _bin_cfg_explore = BinaryParameterConfig(
                logP_min=float(logP_min_val),
                logP_max=float(_ana_logPmax),
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

            # ── Simulate at analysis best-fit for analysis plots ─────
            _sim_cfg_gap = SimulationConfig(
                n_stars=int(n_stars_sim),
                sigma_single=float(_ana_sigma),
                sigma_measure=float(sigma_meas),
                cadence_library=cadence_list_a,
                cadence_weights=cadence_weights_a,
            )
            # Invalidate gap_sim when analysis params change
            _gap_fingerprint = (_ana_fbin, _ana_pi, _ana_sigma, _ana_logPmax,
                                ks_p_4d.shape)
            if (st.session_state.get(f'{p}_gap_fingerprint') != _gap_fingerprint
                    or f'{p}_gap_sim' not in st.session_state):
                rng_gap = np.random.default_rng(99)
                st.session_state[f'{p}_gap_sim'] = simulate_with_params(
                    _ana_fbin, _ana_pi,
                    _sim_cfg_gap, _bin_cfg_explore, rng_gap,
                )
                st.session_state[f'{p}_gap_fingerprint'] = _gap_fingerprint
                # Also clear model explorer cache
                st.session_state.pop(f'{p}_sim_drv', None)
            gap_sim = st.session_state[f'{p}_gap_sim']

            gap_drv = gap_sim['delta_rv']
            gap_is_bin = gap_sim['is_binary']
            gap_idx_bin = gap_sim['idx_bin']

            intrinsic_fbin = float(gap_is_bin.mean())
            detected_mask = gap_drv > thresh_dRV
            observed_fbin = float(detected_mask.mean())
            missed_count = int(np.sum(gap_is_bin & ~detected_mask))
            detected_bin_count = int(np.sum(gap_is_bin & detected_mask))
            total_bin = int(gap_is_bin.sum())

            # Classify binaries for both logP and missed-binaries plots
            _bin_drv = gap_drv[gap_idx_bin] if gap_idx_bin.size > 0 else np.array([])
            _bin_detected_mask = _bin_drv > thresh_dRV
            _bin_missed_mask = ~_bin_detected_mask

            # ── logP distribution + Intrinsic vs Observed fraction ───────
            st.markdown('---')
            _lp_col, _bf_col = st.columns(2)

            with _lp_col:
                st.markdown('### Period Distribution  (log P)')

                # Use simulated periods from gap_sim
                _CLR_DETECTED = '#E25A53'   # tomato red
                _CLR_MISSED   = '#F5A623'   # amber/orange

                fig_logP = go.Figure()

                if gap_sim['P_days'].size > 0:
                    _logP_det = np.log10(gap_sim['P_days'][_bin_detected_mask]) if np.any(_bin_detected_mask) else np.array([])
                    _logP_mis = np.log10(gap_sim['P_days'][_bin_missed_mask]) if np.any(_bin_missed_mask) else np.array([])

                    if _logP_det.size > 0:
                        fig_logP.add_trace(go.Histogram(
                            x=_logP_det, nbinsx=35,
                            histnorm='probability density',
                            name=f'Detected ({_logP_det.size})',
                            marker_color=_CLR_DETECTED, opacity=0.6,
                        ))
                    if _logP_mis.size > 0:
                        fig_logP.add_trace(go.Histogram(
                            x=_logP_mis, nbinsx=35,
                            histnorm='probability density',
                            name=f'Missed ({_logP_mis.size})',
                            marker_color=_CLR_MISSED, opacity=0.6,
                        ))

                fig_logP.add_vline(x=float(logP_min_val), line_dash='dash',
                                   line_color='#888', line_width=1.5,
                                   annotation_text='logP_min',
                                   annotation_position='top left',
                                   annotation_font_color='#888')
                fig_logP.add_vline(x=float(logP_max_val), line_dash='dash',
                                   line_color='#888', line_width=1.5,
                                   annotation_text='logP_max',
                                   annotation_position='top right',
                                   annotation_font_color='#888')
                fig_logP.update_layout(**{
                    **PLOTLY_THEME,
                    'barmode': 'overlay',
                    'title': dict(text=f'Simulated Period Distribution  (π = {_ana_pi:.3f})',
                                  font=dict(size=14)),
                    'xaxis_title': 'log₁₀(P / days)',
                    'yaxis_title': 'Probability density',
                    'height': 400,
                    'margin': dict(l=60, r=20, t=50, b=50),
                    'legend': dict(x=0.65, y=0.95),
                })
                st.plotly_chart(fig_logP, use_container_width=True, key=f'{p}_logP_hist')
                st.caption(
                    'Period distribution of simulated binaries at the best-fit model. '
                    'Red: detected binaries (ΔRV above threshold). '
                    'Amber: missed binaries (below threshold). '
                    'Missed systems are concentrated at longer periods. '
                    'Dashed lines mark the logP bounds used in the simulation.'
                )

            with _bf_col:
                st.markdown('### Observed Binary Fraction vs Threshold')

                # Compute binary fraction as a function of ΔRV threshold
                _n_sim = len(gap_drv)
                _thresh_arr = np.linspace(0, float(np.max(gap_drv) * 1.05), 200)
                _fbin_curve = np.array([float(np.sum(gap_drv > t)) / _n_sim
                                        for t in _thresh_arr])

                # Also compute fraction of binaries detected and singles mis-classified
                _bin_drv_all = gap_drv[gap_is_bin]
                _sin_drv_all = gap_drv[~gap_is_bin]
                _missed_bin_curve = np.array(
                    [float(np.sum(_bin_drv_all <= t)) / _n_sim for t in _thresh_arr])
                _false_pos_curve = np.array(
                    [float(np.sum(_sin_drv_all > t)) / _n_sim for t in _thresh_arr])

                fig_gap = go.Figure()

                # Shaded region: missed binaries (left of threshold)
                fig_gap.add_trace(go.Scatter(
                    x=_thresh_arr, y=_missed_bin_curve,
                    fill='tozeroy', fillcolor='rgba(242,166,35,0.25)',
                    line=dict(width=0), mode='lines',
                    name='Missed binaries', showlegend=True,
                ))

                # Shaded region: false positives / singles above threshold (right of threshold)
                if np.any(_false_pos_curve > 0):
                    fig_gap.add_trace(go.Scatter(
                        x=_thresh_arr, y=_false_pos_curve,
                        fill='tozeroy', fillcolor='rgba(74,144,217,0.25)',
                        line=dict(width=0), mode='lines',
                        name='Singles above threshold', showlegend=True,
                    ))

                # Observed f_bin curve
                fig_gap.add_trace(go.Scatter(
                    x=_thresh_arr, y=_fbin_curve,
                    mode='lines',
                    name='Observed f_bin(threshold)',
                    line=dict(color='#4A90D9', width=2.5),
                ))

                # Intrinsic f_bin horizontal line
                fig_gap.add_hline(
                    y=intrinsic_fbin, line_dash='dot',
                    line_color='#E25A53', line_width=2,
                    annotation_text=f'Intrinsic f_bin = {intrinsic_fbin:.1%}',
                    annotation_position='top left',
                    annotation_font=dict(size=11, color='#E25A53'),
                )

                # Vertical line at current threshold
                fig_gap.add_vline(
                    x=thresh_dRV, line_dash='dash',
                    line_color='#F5A623', line_width=2,
                    annotation_text=f'Threshold = {thresh_dRV} km/s',
                    annotation_position='top right',
                    annotation_font=dict(size=11, color='#F5A623'),
                )

                # Mark the observed f_bin at the threshold
                fig_gap.add_trace(go.Scatter(
                    x=[thresh_dRV], y=[observed_fbin],
                    mode='markers+text',
                    marker=dict(size=12, color='#FFD700', symbol='star',
                                line=dict(width=1, color='#fff')),
                    text=[f'{observed_fbin:.1%}'],
                    textposition='top left',
                    textfont=dict(size=12, color='#FFD700'),
                    name=f'Observed @ {thresh_dRV} km/s',
                    showlegend=True,
                ))

                # Gap annotation between intrinsic and observed
                gap_pct = intrinsic_fbin - observed_fbin
                fig_gap.add_annotation(
                    x=thresh_dRV + 15,
                    y=(intrinsic_fbin + observed_fbin) / 2,
                    text=f'Gap: {gap_pct:.1%}<br>({missed_count} missed / {total_bin} binaries)',
                    showarrow=False,
                    font=dict(size=11, color='#F5A623'),
                    bgcolor=pal['annotation_bg'],
                    bordercolor='#F5A623',
                    borderwidth=1,
                    borderpad=4,
                )
                # Arrow connecting intrinsic to observed at threshold
                fig_gap.add_annotation(
                    x=thresh_dRV, y=intrinsic_fbin,
                    ax=thresh_dRV, ay=observed_fbin,
                    xref='x', yref='y', axref='x', ayref='y',
                    showarrow=True, arrowhead=3,
                    arrowwidth=2, arrowcolor='#F5A623',
                )

                fig_gap.update_layout(**{
                    **PLOTLY_THEME,
                    'title': dict(
                        text='Binary Fraction vs ΔRV Threshold',
                        font=dict(size=14)),
                    'xaxis_title': 'ΔRV threshold (km/s)',
                    'yaxis_title': 'Fraction of sample',
                    'height': 400,
                    'margin': dict(l=60, r=80, t=50, b=50),
                    'showlegend': True,
                    'legend': dict(x=0.55, y=0.95, font=dict(size=10)),
                    'yaxis': dict(range=[0, min(1.0, intrinsic_fbin * 1.5)]),
                })
                st.plotly_chart(fig_gap, use_container_width=True, key=f'{p}_gap_chart')
                st.caption(
                    f'Observed binary fraction as a function of ΔRV threshold. '
                    f'The blue curve shows the fraction of stars classified as '
                    f'binary at each threshold. The dashed red line is the '
                    f'intrinsic f_bin = {intrinsic_fbin:.1%}. At our threshold '
                    f'({thresh_dRV} km/s), the observed fraction is '
                    f'{observed_fbin:.1%} — a gap of {gap_pct:.1%} due to '
                    f'{missed_count} undetectable binaries. '
                    f'Amber shading shows missed binaries; blue shading shows '
                    f'singles scattered above each threshold.'
                )

            # ── Binary Orbital Parameter Histograms ─────────────────────
            st.markdown('---')
            st.markdown('### Binary Orbital Properties')

            _mb_view = st.radio(
                'Show populations',
                ['Compare detected vs missed', 'Detected binaries only',
                 'Missed binaries only', 'All binaries (combined)'],
                horizontal=True, key=f'{p}_mb_view',
            )

            # Extract orbital params for detected and missed
            def _safe_mask(arr, mask):
                return arr[mask] if arr.size > 0 else np.array([])

            P_det = _safe_mask(gap_sim['P_days'], _bin_detected_mask)
            P_mis = _safe_mask(gap_sim['P_days'], _bin_missed_mask)
            e_det = _safe_mask(gap_sim['e'], _bin_detected_mask)
            e_mis = _safe_mask(gap_sim['e'], _bin_missed_mask)
            q_det = _safe_mask(gap_sim['q'], _bin_detected_mask)
            q_mis = _safe_mask(gap_sim['q'], _bin_missed_mask)
            K1_det = _safe_mask(gap_sim['K1'], _bin_detected_mask)
            K1_mis = _safe_mask(gap_sim['K1'], _bin_missed_mask)
            M1_det = _safe_mask(gap_sim['M1'], _bin_detected_mask)
            M1_mis = _safe_mask(gap_sim['M1'], _bin_missed_mask)
            i_det = np.degrees(_safe_mask(gap_sim['i_rad'], _bin_detected_mask))
            i_mis = np.degrees(_safe_mask(gap_sim['i_rad'], _bin_missed_mask))

            # New: omega, T0, M2
            _has_omega = 'omega' in gap_sim
            if _has_omega:
                omega_det = np.degrees(_safe_mask(gap_sim['omega'], _bin_detected_mask))
                omega_mis = np.degrees(_safe_mask(gap_sim['omega'], _bin_missed_mask))
                T0_det = _safe_mask(gap_sim['T0'], _bin_detected_mask)
                T0_mis = _safe_mask(gap_sim['T0'], _bin_missed_mask)
            else:
                omega_det = omega_mis = T0_det = T0_mis = np.array([])

            M2_det = q_det * M1_det if q_det.size > 0 and M1_det.size > 0 else np.array([])
            M2_mis = q_mis * M1_mis if q_mis.size > 0 and M1_mis.size > 0 else np.array([])

            # All binaries (combined) arrays
            P_all = gap_sim['P_days']
            e_all = gap_sim['e']
            q_all = gap_sim['q']
            K1_all = gap_sim['K1']
            M1_all = gap_sim['M1']
            i_all = np.degrees(gap_sim['i_rad'])
            omega_all = np.degrees(gap_sim['omega']) if _has_omega else np.array([])
            T0_all = gap_sim['T0'] if _has_omega else np.array([])
            M2_all = q_all * M1_all if q_all.size > 0 else np.array([])

            from plotly.subplots import make_subplots

            _param_titles = [
                'log₁₀(P / days)', 'Eccentricity', 'Mass ratio q',
                'K₁ (km/s)', 'M₁ (M⊙)', 'M₂ (M⊙)',
                'Inclination (°)', 'ω (°)', 'T₀ (rad)',
            ]
            _x_labels = [
                'log₁₀(P / days)', 'e', 'q = M₂/M₁',
                'K₁ (km/s)', 'M₁ (M⊙)', 'M₂ (M⊙)',
                'i (degrees)', 'ω (degrees)', 'T₀ (rad)',
            ]
            _n_panels = 9
            _n_cols = 3
            _n_rows = 3
            _nbins_hist = 30

            fig_mb = make_subplots(rows=_n_rows, cols=_n_cols,
                                   subplot_titles=_param_titles,
                                   horizontal_spacing=0.08, vertical_spacing=0.10)

            _CLR_ALL = '#52B788'  # green for combined

            def _add_hist(fig, row, col, data, name, color, show_legend):
                if data.size == 0:
                    return
                d_min, d_max = float(data.min()), float(data.max())
                bin_sz = (d_max - d_min) / _nbins_hist if d_max > d_min else 1.0
                fig.add_trace(go.Histogram(
                    x=data,
                    xbins=dict(start=d_min, end=d_max + bin_sz * 0.01, size=bin_sz),
                    histnorm='probability density',
                    name=name,
                    marker_color=color, opacity=0.6,
                    legendgroup=name,
                    showlegend=show_legend,
                ), row=row, col=col)

            def _pos(idx):
                """Convert 0-indexed panel to (row, col)."""
                return (idx // _n_cols + 1, idx % _n_cols + 1)

            if _mb_view == 'All binaries (combined)':
                _data_sets = [
                    np.log10(P_all) if P_all.size > 0 else P_all,
                    e_all, q_all, K1_all, M1_all, M2_all, i_all,
                    omega_all, T0_all,
                ]
                for pi, d in enumerate(_data_sets):
                    r, c = _pos(pi)
                    _add_hist(fig_mb, r, c, d, 'All binaries', _CLR_ALL, pi == 0)
            else:
                _det_data = [
                    np.log10(P_det) if P_det.size > 0 else P_det,
                    e_det, q_det, K1_det, M1_det, M2_det, i_det,
                    omega_det, T0_det,
                ]
                _mis_data = [
                    np.log10(P_mis) if P_mis.size > 0 else P_mis,
                    e_mis, q_mis, K1_mis, M1_mis, M2_mis, i_mis,
                    omega_mis, T0_mis,
                ]

                if _mb_view in ('Compare detected vs missed', 'Detected binaries only'):
                    for pi, d in enumerate(_det_data):
                        r, c = _pos(pi)
                        _add_hist(fig_mb, r, c, d, 'Detected', _CLR_DETECTED, pi == 0)

                if _mb_view in ('Compare detected vs missed', 'Missed binaries only'):
                    for pi, d in enumerate(_mis_data):
                        r, c = _pos(pi)
                        _add_hist(fig_mb, r, c, d, 'Missed', _CLR_MISSED, pi == 0)

            fig_mb.update_layout(**{
                **PLOTLY_THEME,
                'barmode': 'overlay',
                'height': 850,
                'margin': dict(l=40, r=20, t=40, b=60),
                'legend': dict(
                    orientation='h', yanchor='bottom', y=1.04,
                    xanchor='center', x=0.5,
                ),
            })
            for pi in range(_n_panels):
                r, c = _pos(pi)
                fig_mb.update_xaxes(title_text=_x_labels[pi],
                                    showgrid=False, row=r, col=c)
                fig_mb.update_yaxes(showgrid=False, row=r, col=c)
            for row_i in range(1, _n_rows + 1):
                fig_mb.update_yaxes(title_text='Prob. density', row=row_i, col=1)

            st.plotly_chart(fig_mb, use_container_width=True, key=f'{p}_missed_binaries')
            st.caption(
                f'Orbital parameter distributions of simulated binaries at the '
                f'best-fit model (f_bin={_ana_fbin:.3f}, π={_ana_pi:.2f}). '
                f'**Detected** (red): {detected_bin_count} binaries with '
                f'ΔRV > {thresh_dRV} km/s. '
                f'**Missed** (amber): {missed_count} binaries below threshold. '
                f'Use "All binaries" to view the full population as a sanity check '
                f'that input distributions match expectations.'
            )

        # ── Model Explorer ───────────────────────────────────────────────
        if _has_obs:
            st.markdown('---')
            st.markdown('## Model Explorer')

            # Model selector
            _me_c1, _me_c2, _me_c3, _me_c4 = st.columns([0.25, 0.25, 0.25, 0.25])
            explore_fbin = _me_c1.number_input(
                'f_bin', 0.0, 1.0, _ana_fbin, 0.001, format='%.4f',
                key=f'{p}_explore_fbin')
            explore_pi = _me_c2.number_input(
                'π', -5.0, 5.0, _ana_pi, 0.01, format='%.3f',
                key=f'{p}_explore_pi')
            explore_sigma = _me_c3.number_input(
                'σ_single (km/s)', 0.1, 500.0, _ana_sigma, 0.1,
                key=f'{p}_explore_sigma')
            sim_btn = _me_c4.button('Simulate model', type='primary',
                                     key=f'{p}_sim_model')
            st.caption(
                'Pre-filled with best-fit values. Adjust to explore any model point.'
            )

            # Build configs for simulation
            _sim_cfg_explore = SimulationConfig(
                n_stars=int(n_stars_sim),
                sigma_single=float(explore_sigma),
                sigma_measure=float(sigma_meas),
                cadence_library=cadence_list_a,
                cadence_weights=cadence_weights_a,
            )

            # Auto-simulate at best fit on first visit, or re-simulate on button
            _need_sim = sim_btn or f'{p}_sim_drv' not in st.session_state
            if _need_sim:
                rng_explore = np.random.default_rng(42)
                st.session_state[f'{p}_sim_drv'] = simulate_delta_rv_sample(
                    float(explore_fbin), float(explore_pi),
                    _sim_cfg_explore, _bin_cfg_explore, rng_explore,
                )
                rng_explore2 = np.random.default_rng(42)
                rv_s, rv_b = _simulate_rv_sample_full(
                    float(explore_fbin), float(explore_pi),
                    _sim_cfg_explore, _bin_cfg_explore, rng_explore2,
                )
                st.session_state[f'{p}_sim_rv_single'] = rv_s
                st.session_state[f'{p}_sim_rv_binary'] = rv_b
                st.session_state[f'{p}_explore_vals'] = (
                    float(explore_fbin), float(explore_pi), float(explore_sigma))

            sim_drv = st.session_state.get(f'{p}_sim_drv')
            sim_rv_single = st.session_state.get(f'{p}_sim_rv_single')
            sim_rv_binary = st.session_state.get(f'{p}_sim_rv_binary')
            ex_fb, ex_pi, ex_sig = st.session_state.get(
                f'{p}_explore_vals', (_ana_fbin, _ana_pi, _ana_sigma))

            if sim_drv is not None:
                # ── 1) CDF Comparison (binned) ──────────────────────────────
                st.markdown('### CDF Comparison  (ΔRV)')

                from wr_bias_simulation import binned_cdf, ks_two_sample_binned, DEFAULT_DRV_BIN_EDGES
                _bin_edges = DEFAULT_DRV_BIN_EDGES
                obs_cdf_binned = binned_cdf(obs_drv_analysis, _bin_edges)
                sim_cdf_binned = binned_cdf(sim_drv, _bin_edges)

                D_val, p_val = ks_two_sample_binned(sim_drv, obs_drv_analysis, _bin_edges)

                fig_cdf = go.Figure()
                fig_cdf.add_trace(go.Scatter(
                    x=_bin_edges, y=obs_cdf_binned,
                    mode='lines', name='Observed',
                    line=dict(color='#4A90D9', width=2.5, shape='hv'),
                    hovertemplate='ΔRV=%{x:.0f} km/s<br>CDF=%{y:.3f}<extra>Observed</extra>',
                ))
                fig_cdf.add_trace(go.Scatter(
                    x=_bin_edges, y=sim_cdf_binned,
                    mode='lines', name='Simulated',
                    line=dict(color='#E25A53', width=2.5, dash='dash', shape='hv'),
                    hovertemplate='ΔRV=%{x:.0f} km/s<br>CDF=%{y:.3f}<extra>Simulated</extra>',
                ))
                fig_cdf.update_layout(**{
                    **PLOTLY_THEME,
                    'title': dict(
                        text=(f'Binned ΔRV CDF — Observed vs Model  '
                              f'(f_bin={ex_fb:.3f}, π={ex_pi:.2f}, '
                              f'σ={ex_sig:.1f})'),
                        font=dict(size=14),
                    ),
                    'xaxis_title': 'ΔRV (km/s)',
                    'yaxis_title': 'Cumulative fraction',
                    'height': 420,
                    'legend': dict(x=0.65, y=0.15),
                    'annotations': [dict(
                        x=0.98, y=0.95, xref='paper', yref='paper',
                        text=f'Binned {_stat_name} {_stat_sym} = {D_val:.4f}<br>p = {p_val:.4f}',
                        showarrow=False,
                        font=dict(size=12, color=pal['annotation_font']),
                        bgcolor=pal['annotation_bg'],
                        borderpad=6,
                        xanchor='right',
                    )],
                })
                st.plotly_chart(fig_cdf, use_container_width=True, key=f'{p}_cdf')
                st.caption(
                    'Binned cumulative distribution of peak-to-peak ΔRV '
                    f'(10 km/s bins up to 350 km/s). '
                    f'The {_stat_name} statistic ({_stat_sym}) measures the '
                    'distance between the two CDFs; a higher p-value indicates '
                    'a better match between model and observations.'
                )

                # ── 2) RV Distribution ───────────────────────────────────────
                st.markdown('### RV Distribution')

                obs_rv_single_list = []
                obs_rv_binary_list = []
                obs_rv_all_list = []
                for star_name, info in obs_detail.items():
                    rv_arr = info.get('rv')
                    if rv_arr is None or len(rv_arr) == 0:
                        continue
                    obs_rv_all_list.append(rv_arr)
                    if bool(info.get('is_binary', False)):
                        obs_rv_binary_list.append(rv_arr)
                    else:
                        obs_rv_single_list.append(rv_arr)

                obs_rv_all = np.concatenate(obs_rv_all_list) if obs_rv_all_list else np.array([])
                obs_rv_singles = np.concatenate(obs_rv_single_list) if obs_rv_single_list else np.array([])
                obs_rv_binaries = np.concatenate(obs_rv_binary_list) if obs_rv_binary_list else np.array([])

                _rv_c1, _rv_c2 = st.columns([0.4, 0.6])
                rv_split_mode = _rv_c1.radio(
                    'Observed RVs', ['All combined', 'Split by classification'],
                    horizontal=True, key=f'{p}_rv_split')
                show_sim_rv = _rv_c2.checkbox(
                    'Overlay simulated RVs', value=True, key=f'{p}_show_sim_rv')

                fig_rv = go.Figure()
                nbins = 40

                if rv_split_mode == 'All combined':
                    if obs_rv_all.size > 0:
                        fig_rv.add_trace(go.Histogram(
                            x=obs_rv_all, nbinsx=nbins,
                            histnorm='probability density',
                            name='Observed (all)',
                            marker_color='#4A90D9', opacity=0.6,
                        ))
                else:
                    if obs_rv_singles.size > 0:
                        fig_rv.add_trace(go.Histogram(
                            x=obs_rv_singles, nbinsx=nbins,
                            histnorm='probability density',
                            name='Observed — single',
                            marker_color='#4A90D9', opacity=0.5,
                        ))
                    if obs_rv_binaries.size > 0:
                        fig_rv.add_trace(go.Histogram(
                            x=obs_rv_binaries, nbinsx=nbins,
                            histnorm='probability density',
                            name='Observed — binary',
                            marker_color='#E25A53', opacity=0.5,
                        ))

                if show_sim_rv and sim_rv_single is not None:
                    if rv_split_mode == 'All combined':
                        sim_rv_combined = np.concatenate([sim_rv_single, sim_rv_binary])
                        if sim_rv_combined.size > 0:
                            fig_rv.add_trace(go.Histogram(
                                x=sim_rv_combined, nbinsx=nbins,
                                histnorm='probability density',
                                name='Simulated (all)',
                                marker_color='#8C8C8C', opacity=0.4,
                            ))
                    else:
                        if sim_rv_single.size > 0:
                            fig_rv.add_trace(go.Histogram(
                                x=sim_rv_single, nbinsx=nbins,
                                histnorm='probability density',
                                name='Simulated — single',
                                marker_color='#7EC8E3', opacity=0.4,
                            ))
                        if sim_rv_binary.size > 0:
                            fig_rv.add_trace(go.Histogram(
                                x=sim_rv_binary, nbinsx=nbins,
                                histnorm='probability density',
                                name='Simulated — binary',
                                marker_color='#F0A0A0', opacity=0.4,
                            ))

                fig_rv.update_layout(**{
                    **PLOTLY_THEME,
                    'barmode': 'overlay',
                    'title': dict(text='RV Distribution', font=dict(size=14)),
                    'xaxis_title': 'RV (km/s)',
                    'yaxis_title': 'Probability density',
                    'height': 420,
                    'legend': dict(x=0.01, y=0.99),
                })
                st.plotly_chart(fig_rv, use_container_width=True, key=f'{p}_rv_dist')
                st.caption(
                    'Distribution of individual RV measurements. Observed data '
                    'can be shown combined or split by binary classification; '
                    'simulated data is drawn from the selected model. All '
                    'histograms are normalized to probability density for '
                    'comparison.'
                )

                # ── 3) Detection fraction vs threshold ───────────────────────
                st.markdown('### Detection Fraction vs Threshold')

                max_drv = max(float(np.max(obs_drv_analysis)),
                              float(np.max(sim_drv)))
                thresholds = np.linspace(0, max_drv * 1.1, 150)
                frac_obs_arr = np.array(
                    [(obs_drv_analysis > T).mean() for T in thresholds])
                frac_sim_arr = np.array(
                    [(sim_drv > T).mean() for T in thresholds])

                frac_obs_at_thresh = float(
                    (obs_drv_analysis > thresh_dRV).mean())
                frac_sim_at_thresh = float((sim_drv > thresh_dRV).mean())

                fig_frac = go.Figure()
                fig_frac.add_trace(go.Scatter(
                    x=thresholds, y=frac_obs_arr,
                    mode='lines', name='Observed',
                    line=dict(color='#4A90D9', width=2.5),
                ))
                fig_frac.add_trace(go.Scatter(
                    x=thresholds, y=frac_sim_arr,
                    mode='lines', name='Simulated',
                    line=dict(color='#E25A53', width=2.5, dash='dash'),
                ))
                fig_frac.add_vline(
                    x=thresh_dRV, line_dash='dot',
                    line_color='#DAA520', line_width=1.5,
                    annotation_text=f'Threshold = {thresh_dRV} km/s',
                    annotation_position='top right',
                    annotation_font_color='#DAA520',
                )
                fig_frac.add_trace(go.Scatter(
                    x=[thresh_dRV, thresh_dRV],
                    y=[frac_obs_at_thresh, frac_sim_at_thresh],
                    mode='markers+text',
                    marker=dict(size=10, color=['#4A90D9', '#E25A53'],
                                symbol='circle',
                                line=dict(color=pal['plot_bg'], width=1)),
                    text=[f'  {frac_obs_at_thresh:.2%}',
                          f'  {frac_sim_at_thresh:.2%}'],
                    textposition='middle right',
                    textfont=dict(size=11),
                    showlegend=False,
                ))
                fig_frac.update_layout(**{
                    **PLOTLY_THEME,
                    'title': dict(
                        text=(f'Detection Fraction vs ΔRV Threshold  '
                              f'(model: f_bin={ex_fb:.3f}, π={ex_pi:.2f})'),
                        font=dict(size=14),
                    ),
                    'xaxis_title': 'ΔRV threshold (km/s)',
                    'yaxis_title': 'Fraction above threshold',
                    'height': 420,
                    'legend': dict(x=0.70, y=0.95),
                    'yaxis': dict(range=[0, 1.05]),
                })
                st.plotly_chart(fig_frac, use_container_width=True, key=f'{p}_det_frac')
                st.caption(
                    'Fraction of stars with ΔRV exceeding a given threshold. '
                    'The vertical line marks the detection threshold used for '
                    'binary classification. A good model should match the '
                    'observed curve across all thresholds, not just at the '
                    'chosen cutoff.'
                )


        # ── Simulation Methodology & Equations ───────────────────────────────
        st.markdown('---')
        with st.expander('Simulation methodology & equations', expanded=False):
            st.markdown('''
    **Simulation overview** — for each grid point (f_bin, π, σ_single):

    1. **Draw N systems** (default 3,000). Each system is assigned as binary
       with probability f_bin, or single with probability 1 − f_bin.

    2. **Assign observation cadences.** Each simulated system is randomly
       paired with a real star's observation times (MJD from FITS headers),
       preserving the actual time sampling of the survey.

    3. **Single stars:** draw RV at each epoch from
       N(v_sys, σ_total) where σ_total = √(σ_single² + σ_measure²).
       Compute ΔRV = max(v) − min(v).

    4. **Binary stars:** for each system, sample orbital parameters:
       - Period P from power-law distribution p(log P) ∝ (log P)^π
       - Eccentricity e from uniform [0, e_max] (or fixed at 0)
       - Primary mass M₁ (fixed or uniform)
       - Mass ratio q = M₂/M₁ (flat or Gaussian)
       - Inclination i from sin(i) distribution
       - Argument of periastron ω ~ U[0, 2π]
       - Initial mean anomaly T₀ ~ U[0, 2π]

    5. **Compute the RV semi-amplitude K₁:**
    ''')
            st.latex(
                r'K_1 = \left(\frac{2\pi G}{P}\right)^{1/3}'
                r'\frac{M_2 \sin i}{(M_1 + M_2)^{2/3}}'
                r'\frac{1}{\sqrt{1 - e^2}}'
            )

            st.markdown('''
    6. **Solve Kepler's equation** at each observation time t
       via Newton-Raphson iteration:
    ''')
            st.latex(r'E - e \sin E = M, \quad M = T_0 + \frac{2\pi t}{P}')

            st.markdown('7. **Compute the true anomaly** ν from E:')
            st.latex(
                r'\tan\frac{\nu}{2} = '
                r'\sqrt{\frac{1+e}{1-e}} \, \tan\frac{E}{2}'
            )

            st.markdown('8. **Compute the radial velocity curve:**')
            st.latex(
                r'v(t) = v_{\rm sys} + K_1 '
                r'\left[\cos(\omega + \nu) + e\cos\omega\right]'
            )

            st.markdown(r'''
       Then ΔRV = max(v) − min(v) over the observed epochs.

    9. **Compare the simulated ΔRV distribution** to the observed one using
       the two-sample Kolmogorov-Smirnov test. The K-S statistic D is the
       maximum absolute difference between the two empirical CDFs:
    ''')
            st.latex(
                r'D = \max_x \left| F_{\rm obs}(x) - F_{\rm sim}(x) \right|'
            )

            st.markdown(r'''
       The associated p-value quantifies the probability that both samples
       are drawn from the same underlying distribution. Higher p → better match.

    10. **Binary detection criteria** (both required):
    ''')
            st.latex(
                r'\Delta\mathrm{RV} > 45.5 \; \mathrm{km/s}'
                r'\quad \text{and} \quad'
                r'\Delta\mathrm{RV} - 4\sigma > 0'
            )
            st.markdown(
                'where σ is the combined measurement error of the epoch pair.'
            )


    # ─────────────────────────────────────────────────────────────────────────────
    # Langer 2020 tab
    # ─────────────────────────────────────────────────────────────────────────────



