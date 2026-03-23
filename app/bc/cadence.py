"""bc.cadence — Cadence-aware simulation tabs (Dsilva + Langer variants)."""
from __future__ import annotations

import datetime as _dt
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
    _RESULT_DIR,
    _build_descriptive_filename,
    _render_partial_table,
    _scan_result_metadata,
    _make_max_pval_fig, _make_heatmap_fig,
)
from bc.params import (
    _render_orbital_params_dsilva, _render_orbital_params_langer,
    _render_cadence_sigma_scan, _render_cadence_adaptive_bins,
    _render_likelihood_bin_config, _render_logPmax_scan,
)
from bc.analysis import _get_method_array  # noqa: F401 — re-export for tests
from bc.runners import _run_cadence_bg
from bc.extras import _render_error_model_selector
from bc.subtabs import render_model_subtabs
from bc.polling import _poll_cadence_job


# ─────────────────────────────────────────────────────────────────────────────
# Result display: build model_ctx + delegate to subtabs
# ─────────────────────────────────────────────────────────────────────────────

def _render_cadence_results(p: str, _is_dsilva: bool, bin_cfg=None,
                            settings: dict = None) -> None:
    """Shared right-column results display for both cadence tabs."""
    _ch = int(st.session_state.get('bc_canvas_height', 520))
    _cw_raw = int(st.session_state.get('bc_canvas_width', 0))
    _cw = _cw_raw if _cw_raw > 0 else None
    _use_cw = (_cw is None)

    # Poll job status; only proceed to analysis on 'done'
    status = _poll_cadence_job(p)
    if status != 'done':
        return

    result = st.session_state.get(f'{p}_result')
    if result is None or result.get('likelihood') is None:
        st.warning('No results found.')
        return

    # ── Extract grids ─────────────────────────────────────────────────────
    fbin_grid = np.asarray(result['fbin_grid'])
    pi_grid = np.asarray(result['pi_grid'])
    sigma_grid = np.asarray(result['sigma_grid'])
    logPmax_grid = np.asarray(result.get('logPmax_grid', []))
    _has_logPmax_scan = len(logPmax_grid) > 1
    lk_arr = np.asarray(result['likelihood'])

    n_sig = len(sigma_grid)
    _is_langer_sigma = (not _is_dsilva) and n_sig > 1

    # ── Handle logPmax dimension: browse slider ───────────────────────────
    _cad_lp_idx = 0
    if _has_logPmax_scan and lk_arr.ndim == 4:
        _has_sigma_scan = n_sig > 1
        if _has_sigma_scan:
            _cad_outer = np.nanmax(lk_arr, axis=(2, 3))
            st.plotly_chart(
                _make_heatmap_fig(
                    _cad_outer, logPmax_grid, sigma_grid,
                    title='Max Likelihood  (logP_max \u00d7 \u03c3_single)',
                    height=_ch, width=_cw,
                    x_label='\u03c3_single (km/s)',
                    y_label='log\u2081\u2080(P_max / days)',
                    x_name='\u03c3',
                ), use_container_width=_use_cw)
        else:
            _lp_max_lk = [float(np.nanmax(lk_arr[i_lp]))
                          if np.any(np.isfinite(lk_arr[i_lp])) else 0.0
                          for i_lp in range(len(logPmax_grid))]
            st.plotly_chart(
                _make_max_pval_fig(
                    logPmax_grid, _lp_max_lk, height=280,
                    x_label='logP_max'),
                use_container_width=True)
        if np.any(np.isfinite(lk_arr)):
            _best_flat = int(np.nanargmax(lk_arr))
            _best_lp = _best_flat // (
                lk_arr.shape[1] * lk_arr.shape[2] * lk_arr.shape[3])
        else:
            _best_lp = 0
        _lp_opts = [round(float(v), 4) for v in logPmax_grid]
        _sel_lp = st.select_slider(
            'Browse logP_max',
            options=_lp_opts,
            value=_lp_opts[min(_best_lp, len(_lp_opts) - 1)],
            format_func=lambda v: f'{v:.2f}',
            key=f'{p}_logPmax_browse',
        )
        _cad_lp_idx = int(np.argmin(np.abs(logPmax_grid - _sel_lp)))

    # ── Determine x-axis and ndim_mode ────────────────────────────────────
    if _is_langer_sigma:
        _cad_ndim_mode = 'cadence_langer'
        _cad_x_g = np.asarray(sigma_grid)
        _cad_x_name = 'sigma'
        _cad_x_label = 'sigma_single'
        _cad_x_disp = 'sigma_single (km/s)'
    elif _is_dsilva:
        _cad_ndim_mode = 'cadence_dsilva'
        _cad_x_g = np.asarray(pi_grid)
        _cad_x_name = 'pi'
        _cad_x_label = 'pi'
        _cad_x_disp = 'pi (period power-law index)'
    else:
        _cad_ndim_mode = 'cadence_langer'
        _cad_x_g = np.asarray(sigma_grid)
        _cad_x_name = 'sigma'
        _cad_x_label = 'sigma_single'
        _cad_x_disp = 'sigma_single (km/s)'

    # ── Determine best-fit indices for outer slice selection ───────────────
    # For lk_arr that might be 3D or 4D, find best sigma slice
    _lk_for_slice = lk_arr
    if _has_logPmax_scan and _lk_for_slice.ndim == 4:
        _lk_for_slice = _lk_for_slice[_cad_lp_idx]

    _cad_outer_list = []
    if _has_logPmax_scan:
        _cad_outer_list.append(_cad_lp_idx)
    if n_sig > 1:
        _cad_best_s = 0
        if np.any(np.isfinite(_lk_for_slice)):
            _lkmax_list = [float(np.nanmax(_lk_for_slice[s]))
                           for s in range(n_sig)]
            _cad_best_s = int(np.argmax(_lkmax_list))
        _cad_outer_list.append(_cad_best_s)
    elif _lk_for_slice.ndim == 3 and not _has_logPmax_scan:
        _cad_outer_list.append(0)
    _cad_outer = tuple(_cad_outer_list) if _cad_outer_list else None

    # ── Find global best-fit for gap_sim ──────────────────────────────────
    _full_lk = np.asarray(result['likelihood'])
    if not np.any(np.isfinite(_full_lk)):
        st.warning('No finite likelihood values in grid \u2014 cannot run analysis.')
        return

    _flat_best = int(np.nanargmax(_full_lk))
    _shape = _full_lk.shape
    if _full_lk.ndim == 4:
        _best_lp_idx = _flat_best // (_shape[1] * _shape[2] * _shape[3])
        _rem = _flat_best % (_shape[1] * _shape[2] * _shape[3])
        _best_sig_idx = _rem // (_shape[2] * _shape[3])
        _best_fb_idx = (_rem // _shape[3]) % _shape[2]
        _best_pi_idx = _rem % _shape[3]
    elif _full_lk.ndim == 3:
        _best_lp_idx = 0
        _best_sig_idx = _flat_best // (_shape[1] * _shape[2])
        _best_fb_idx = (_flat_best // _shape[2]) % _shape[1]
        _best_pi_idx = _flat_best % _shape[2]
    else:
        _best_lp_idx = 0
        _best_sig_idx = 0
        _best_fb_idx = _flat_best // _shape[1]
        _best_pi_idx = _flat_best % _shape[1]

    best_fbin_v = float(fbin_grid[_best_fb_idx])
    best_pi_v = float(pi_grid[_best_pi_idx]) if _is_dsilva else 0.0
    best_sigma_v = float(sigma_grid[_best_sig_idx])
    ana_logPmax = float(logPmax_grid[_best_lp_idx]) if len(logPmax_grid) > 0 \
        else float(st.session_state.get(f'{p}_logP_max', 5.0))

    # ── Load observed data ────────────────────────────────────────────────
    _settings = settings or {}
    cls = _settings.get('classification', {})
    thresh_dRV = float(cls.get('threshold_dRV', 45.5))
    sh_analysis = settings_hash(_settings) if _settings else ''
    try:
        obs_drv_analysis, obs_detail = cached_load_observed_delta_rvs(sh_analysis)
        cadence_list_a, cadence_weights_a = cached_load_cadence(sh_analysis)
        _has_obs = True
    except Exception:
        obs_drv_analysis = obs_detail = cadence_list_a = cadence_weights_a = None
        _has_obs = False

    # ── Compute gap_sim at best-fit for analysis plots ────────────────────
    gap_sim = None
    _bin_cfg_explore = None
    if _has_obs:
        from wr_bias_simulation import (
            SimulationConfig, BinaryParameterConfig, simulate_with_params,
        )
        if bin_cfg is not None:
            _bin_cfg_explore = bin_cfg
        else:
            _d_period_model = 'powerlaw' if _is_dsilva else 'langer2020'
            _bin_cfg_explore = BinaryParameterConfig(
                logP_min=float(st.session_state.get(f'{p}_logP_min', 0.15)),
                logP_max=float(st.session_state.get(f'{p}_logP_max', 5.0)),
                period_model=_d_period_model,
                e_model=str(st.session_state.get(f'{p}_e_model', 'flat')),
                e_max=float(st.session_state.get(f'{p}_e_max', 0.9)),
                mass_primary_model=str(
                    st.session_state.get(f'{p}_mass_model', 'fixed')),
                mass_primary_fixed=float(
                    st.session_state.get(f'{p}_mass_fixed', 10.0)),
                q_model=str(st.session_state.get(f'{p}_q_model', 'flat')),
                q_range=(float(st.session_state.get(f'{p}_q_min', 0.1)),
                         float(st.session_state.get(f'{p}_q_max', 2.0))),
                langer_q_mu=float(
                    st.session_state.get(f'{p}_lq_mu', 0.7)),
                langer_q_sigma=float(
                    st.session_state.get(f'{p}_lq_sig', 0.2)),
            )

        _d_sigma_meas = float(
            st.session_state.get(f'{p}_sigma_meas', 1.622))
        _sim_cfg_gap = SimulationConfig(
            n_stars=10000,
            sigma_single=best_sigma_v,
            sigma_measure=_d_sigma_meas,
            cadence_library=cadence_list_a,
            cadence_weights=cadence_weights_a,
        )
        _gap_fp = (best_fbin_v, best_pi_v, best_sigma_v,
                   ana_logPmax, _full_lk.shape)
        if (st.session_state.get(f'{p}_gap_fingerprint') != _gap_fp
                or f'{p}_gap_sim' not in st.session_state):
            rng_diag = np.random.default_rng(42)
            st.session_state[f'{p}_gap_sim'] = simulate_with_params(
                best_fbin_v, best_pi_v,
                _sim_cfg_gap, _bin_cfg_explore, rng_diag,
            )
            st.session_state[f'{p}_gap_fingerprint'] = _gap_fp
            st.session_state.pop(f'{p}_sim_drv', None)
        gap_sim = st.session_state[f'{p}_gap_sim']

    # ── Inject missing keys into result (backward compat for old .npz) ───
    if 'obs_delta_rv' not in result and obs_drv_analysis is not None:
        result['obs_delta_rv'] = obs_drv_analysis
    if 'sigma_meas' not in result:
        result['sigma_meas'] = float(
            st.session_state.get(f'{p}_sigma_meas', 1.622))
    if 'cadence_library' not in result and cadence_list_a is not None:
        result['cadence_library'] = cadence_list_a

    # ── Build model_ctx and delegate to subtabs ───────────────────────────
    _model_type = 'cadence_dsilva' if _is_dsilva else 'cadence_langer'
    _period_model = 'powerlaw' if _is_dsilva else 'langer2020'

    model_ctx = {
        'model_type': _model_type,
        'ndim_mode': _cad_ndim_mode,
        'x_name': _cad_x_name,
        'x_label': _cad_x_label,
        'x_display_label': _cad_x_disp,
        'period_model': _period_model,
        'has_case_AB': not _is_dsilva,
        'result': result,
        'fbin_g': fbin_grid,
        'x_g': _cad_x_g,
        'sigma_g': np.asarray(sigma_grid),
        'logPmax_g': logPmax_grid if len(logPmax_grid) > 0 else np.array(
            [float(st.session_state.get(f'{p}_logP_max', 5.0))]),
        'gap_sim': gap_sim,
        'obs_delta_rv': obs_drv_analysis,
        'obs_detail': obs_detail,
        'cadence_list': cadence_list_a,
        'cadence_weights': cadence_weights_a,
        'n_stars_sim': 10000,
        'sigma_meas': float(
            st.session_state.get(f'{p}_sigma_meas', 1.622)),
        'bin_cfg': _bin_cfg_explore,
        'logP_min': float(st.session_state.get(f'{p}_logP_min', 0.15)),
        'logP_max': ana_logPmax,
        'thresh_dRV': thresh_dRV,
        'canvas_height': _ch,
        'canvas_width': _cw,
        'use_container_width': _use_cw,
        'disp_outer_slices': _cad_outer,
        'settings': _settings,
        'classification': cls,
    }

    render_model_subtabs(p, model_ctx)


# ─────────────────────────────────────────────────────────────────────────────
# Run + load/save logic (shared by both cadence variants)
# ─────────────────────────────────────────────────────────────────────────────

def _cadence_run_and_results(p: str, _is_dsilva: bool, _period_model: str,
                              fb_min, fb_max, fb_steps,
                              pi_min, pi_max, pi_steps,
                              n_sets, sigma_vals, _bin_cfg,
                              _sigma_meas, settings, sm,
                              err_info: dict = None,
                              logPmax_scan_vals: np.ndarray = None) -> None:
    """Shared action buttons + right column for cadence tabs."""
    _cad_tag = 'cadence_dsilva' if _is_dsilva else 'cadence_langer'

    # K-S bin edges (user-configurable or adaptive)
    _use_adaptive = bool(st.session_state.get(f'{p}_adaptive_bins', True))
    if _use_adaptive:
        from wr_bias_simulation import adaptive_bin_edges as _abe, DEFAULT_DRV_BIN_EDGES
        try:
            _sh_bins = settings_hash(settings) if 'settings' in dir() else ''
            _obs_drv_bins, _ = cached_load_observed_delta_rvs(_sh_bins)
        except Exception:
            _obs_drv_bins = None
        if _obs_drv_bins is not None and len(_obs_drv_bins) > 0:
            _cad_bin_edges = _abe(_obs_drv_bins, min_gap=1.0)
        else:
            _cad_bin_edges = DEFAULT_DRV_BIN_EDGES
    else:
        _drv_bin_width = float(
            st.session_state.get(f'{p}_drv_bin_width', 5.0))
        _drv_max = float(st.session_state.get(f'{p}_drv_max', 360.0))
        _cad_bin_edges = np.arange(0.0, _drv_max, _drv_bin_width)

    # ── Load saved results ────────────────────────────────────────────────
    _cad_meta = _scan_result_metadata(_cad_tag)
    if _cad_meta is not None and len(_cad_meta) > 0:
        with st.expander(
                f'\U0001f4c2 Load saved result ({len(_cad_meta)})',
                expanded=True):
            _cad_disp = _cad_meta.drop(columns=['_path'], errors='ignore')
            _cad_sel = st.dataframe(
                _cad_disp, use_container_width=True,
                selection_mode='single-row', on_select='rerun',
                key=f'{p}_load_table',
            )
            _cad_sel_rows = (
                _cad_sel.selection.rows if _cad_sel.selection else [])
            if _cad_sel_rows:
                _cad_idx = _cad_sel_rows[0]
                _cad_sel_path = _cad_meta.iloc[_cad_idx]['_path']
                if st.session_state.get(f'{p}_loaded_path') != _cad_sel_path:
                    _cad_loaded = dict(np.load(
                        _cad_sel_path, allow_pickle=True))
                    # Backward compat: compute likelihood from logL_raw if missing
                    if 'likelihood' not in _cad_loaded and 'logL_raw' in _cad_loaded:
                        _logL = np.asarray(_cad_loaded['logL_raw'], dtype=float)
                        _logL_max = np.nanmax(_logL)
                        if np.isfinite(_logL_max):
                            _cad_loaded['likelihood'] = np.exp(_logL - _logL_max)
                        else:
                            _cad_loaded['likelihood'] = np.zeros_like(_logL)
                    # Default likelihood_bin_edges if missing
                    if 'likelihood_bin_edges' not in _cad_loaded:
                        from wr_bias_simulation import DSILVA_LIKELIHOOD_BINS
                        _cad_loaded['likelihood_bin_edges'] = DSILVA_LIKELIHOOD_BINS
                    st.session_state[f'{p}_result'] = _cad_loaded
                    st.session_state[f'{p}_loaded_path'] = _cad_sel_path
                    st.toast(
                        f"Loaded: {_cad_meta.iloc[_cad_idx]['File']}")
                    st.rerun()
                if st.button(
                        '\U0001f5d1\ufe0f Delete this result',
                        key=f'{p}_del_full'):
                    os.remove(_cad_sel_path)
                    _scan_result_metadata.clear()
                    st.session_state.pop(f'{p}_loaded_path', None)
                    st.session_state.pop(f'{p}_result', None)
                    st.toast(
                        f"Deleted: {_cad_meta.iloc[_cad_idx]['File']}")
                    st.rerun()
    else:
        st.caption('No saved results yet.')

    # ── Partial results table ─────────────────────────────────────────────
    _render_partial_table(p, _cad_tag, st)

    # Workers
    _n_proc = os.cpu_count() - 1

    # Likelihood bin edges
    _lk_bin_edges = _render_likelihood_bin_config(p, sm=sm)

    # Action buttons
    _a1, _a2, _a3, _a4 = st.columns(4)
    _run_btn = _a1.button(
        '\u25b6\ufe0f Run', key=f'{p}_run_btn', type='primary')
    _save_clicked = _a2.button(
        '\U0001f4be Save result', key=f'{p}_save_btn')
    # ── WORKING · cancel-save-resume ──
    _cancel_btn = _a3.button(
        '\u23f9 Cancel', key=f'{p}_cancel_btn')
    _cancel_save_btn = _a4.button(
        '\U0001f4be Cancel & Save', key=f'{p}_cancel_save_btn')

    if _save_clicked:
        _cad_cur_res = st.session_state.get(f'{p}_result')
        if _cad_cur_res is not None:
            _cad_save_kw = {
                **{k: v for k, v in _cad_cur_res.items()
                   if k not in ('timestamp', 'config_hash')},
                'config_hash': np.array('manual_save'),
                'timestamp': np.array(_dt.datetime.now().isoformat()),
            }
            _cad_desc = _build_descriptive_filename(
                _cad_tag,
                float(fb_min), float(fb_max), int(fb_steps),
                float(sigma_vals[0]) if len(sigma_vals) > 0 else 1.0,
                float(sigma_vals[-1]) if len(sigma_vals) > 0 else 15.0,
                len(sigma_vals),
                int(n_sets), np.array(sigma_vals),
                0.5, 3.5, x_label='sig',
            )
            _cad_save_path = os.path.join(_RESULT_DIR, _cad_desc)
            os.makedirs(_RESULT_DIR, exist_ok=True)
            np.savez(_cad_save_path, **_cad_save_kw)
            cached_load_grid_result.clear()
            _scan_result_metadata.clear()
            st.toast(f'Saved: {_cad_desc}')
            st.success(f'Result saved as `{_cad_desc}`.')
        else:
            st.warning('No result to save. Run first.')

    # ── WORKING · cancel-save-resume ──
    if _cancel_btn and f'{p}_job' in st.session_state:
        st.session_state[f'{p}_job']['cancel'] = True
        st.session_state[f'{p}_job']['cancel_mode'] = 'discard'
    if _cancel_save_btn and f'{p}_job' in st.session_state:
        st.session_state[f'{p}_job']['cancel'] = True
        st.session_state[f'{p}_job']['cancel_mode'] = 'save'

    # ── WORKING · cancel-save-resume ──
    _cad_auto_resume = st.session_state.pop(f'{p}_auto_resume', False)
    _job_running = (f'{p}_job' in st.session_state
                    and st.session_state[f'{p}_job'].get('status')
                    == 'running')
    if _run_btn and _job_running:
        st.warning(
            'A simulation is already running. Cancel or wait before '
            'starting a new run.')
    # ── WORKING · cancel-save-resume ──
    if (_run_btn or _cad_auto_resume) and not _job_running:
        _sh = settings_hash(settings)
        obs_drv, obs_det = cached_load_observed_delta_rvs(_sh)
        cad_list, cad_wts = cached_load_cadence(_sh)

        fbin_vals = np.linspace(fb_min, fb_max, fb_steps).tolist()
        pi_v = (np.linspace(pi_min, pi_max, pi_steps).tolist()
                if _is_dsilva else [0.0])

        _cad_stable_cfg = {
            'n_stars_sim': len(cad_list),
            'sigma_measure': float(_sigma_meas),
            'logP_min': float(_bin_cfg.logP_min),
            'logP_max': float(_bin_cfg.logP_max),
            'period_model': _period_model,
            'e_model': str(_bin_cfg.e_model),
            'e_max': float(_bin_cfg.e_max),
            'mass_primary_model': str(_bin_cfg.mass_primary_model),
            'mass_primary_fixed': float(_bin_cfg.mass_primary_fixed),
            'q_model': str(_bin_cfg.q_model),
            'q_min': float(_bin_cfg.q_range[0]),
            'q_max': float(_bin_cfg.q_range[1]),
            'q_flipped': bool(getattr(_bin_cfg, 'q_flipped', False)),
            'primary_line': settings.get(
                'primary_line', 'C IV 5808-5812'),
            'threshold_dRV': settings.get(
                'classification', {}).get('threshold_dRV', 45.5),
            'sigma_factor': settings.get(
                'classification', {}).get('sigma_factor', 4.0),
            'adaptive_bins': _use_adaptive,
            'n_sets': n_sets,
        }
        if not _is_dsilva:
            _cad_stable_cfg['langer_period_params'] = getattr(
                _bin_cfg, 'langer_period_params', {})

        job = {
            'status': 'running',
            'progress_pct': 0.0,
            'progress_text': 'Starting...',
            'live_heatmaps': None,
            'live_status': '',
            '_last_hm': 0,
        }
        st.session_state[f'{p}_job'] = job

        params = {
            'cadence_list': cad_list, 'cadence_weights': cad_wts,
            'obs_delta_rv': obs_drv,
            'n_proc': _n_proc,
            'fbin_vals': fbin_vals, 'pi_vals': pi_v,
            'sigma_vals': sigma_vals,
            'n_sets': n_sets,
            'period_model': _period_model,
            'bin_cfg': _bin_cfg,
            'sigma_meas': _sigma_meas,
            'bin_edges': _cad_bin_edges,
            'adaptive_bins': _use_adaptive,
            'drv_bin_width': float(
                st.session_state.get(f'{p}_drv_bin_width', 5.0)),
            'drv_max': float(
                st.session_state.get(f'{p}_drv_max', 360.0)),
            'likelihood_bin_edges': _lk_bin_edges,
            'error_model_single': (err_info or {}).get(
                'type_single', 'fixed'),
            'error_params_single': (err_info or {}).get(
                'params_single', ()),
            'error_model_binary': (err_info or {}).get(
                'type_binary', 'fixed'),
            'error_params_binary': (err_info or {}).get(
                'params_binary', ()),
            'logPmax_scan_vals': (
                logPmax_scan_vals if logPmax_scan_vals is not None
                else np.array([_bin_cfg.logP_max])),
            'stable_cfg': _cad_stable_cfg,
            'save_params': {
                'mode': 'cadence_aware',
                'period_model': _period_model,
                'n_sets': n_sets,
                'adaptive_bins': _use_adaptive,
            },
        }

        # ── WORKING · cancel-save-resume ──
        # Check for partial resume
        _cad_resume_path = st.session_state.pop(
            f'{p}_resume_from', None)
        if _cad_resume_path and os.path.exists(_cad_resume_path):
            try:
                _cad_ptl = np.load(
                    _cad_resume_path, allow_pickle=True)
                # Load likelihood arrays from checkpoint
                params['prefilled_logL_raw'] = np.asarray(
                    _cad_ptl['logL_raw']) if 'logL_raw' in _cad_ptl else None
                # Backward compat: old checkpoints may have ks_p but no logL_raw
                if params['prefilled_logL_raw'] is None and 'ks_p' in _cad_ptl:
                    params['prefilled_logL_raw'] = None  # skip old-format checkpoints
                # Override grid params from checkpoint
                params['fbin_vals'] = (
                    _cad_ptl['fbin_grid'].tolist())
                params['pi_vals'] = (
                    _cad_ptl['pi_grid'].tolist())
                params['sigma_vals'] = (
                    _cad_ptl['sigma_grid'].tolist())
                if 'logPmax_grid' in _cad_ptl:
                    params['logPmax_scan_vals'] = np.asarray(
                        _cad_ptl['logPmax_grid'])
                if 'n_sets' in _cad_ptl:
                    params['n_sets'] = int(_cad_ptl['n_sets'])
                if 'drv_bin_width' in _cad_ptl:
                    params['drv_bin_width'] = float(
                        _cad_ptl['drv_bin_width'])
                if 'drv_max' in _cad_ptl:
                    params['drv_max'] = float(
                        _cad_ptl['drv_max'])
                if 'adaptive_bins' in _cad_ptl:
                    params['adaptive_bins'] = bool(
                        _cad_ptl['adaptive_bins'])
                # Progress info
                _pf = params.get('prefilled_logL_raw')
                _n_pre = int(np.count_nonzero(~np.isnan(_pf))) if _pf is not None else 0
                _n_tot = _pf.size if _pf is not None else 1
                params['resume_from_path'] = _cad_resume_path
                st.info(
                    f'\u267b\ufe0f Resuming from checkpoint '
                    f'({_n_pre}/{_n_tot} cells, '
                    f'{_n_pre / _n_tot * 100:.0f}%).')
                _cad_ptl.close()
            except Exception as e:
                st.warning(
                    f'\u26a0\ufe0f Failed to load checkpoint: {e}')

        t = threading.Thread(
            target=_run_cadence_bg, args=(job, params), daemon=True)
        t.start()
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Cadence Dsilva tab
# ─────────────────────────────────────────────────────────────────────────────

def _render_cadence_dsilva_tab(p: str, settings: dict, sm) -> None:
    """Render Cadence-Aware simulation tab (Dsilva / power-law)."""
    _is_dsilva = True
    _period_model = 'powerlaw'
    _sec = 'grid_cadence_dsilva'

    gcfg = settings.get(_sec, {})
    orb = gcfg.get('orbital', {})
    simcfg = settings.get('simulation', {})

    _defaults = {
        f'{p}_fb_min':      float(gcfg.get('fbin_min', 0.0)),
        f'{p}_fb_max':      float(gcfg.get('fbin_max', 1.0)),
        f'{p}_fb_steps':    int(gcfg.get('fbin_steps', 100)),
        f'{p}_pi_min':      float(gcfg.get('pi_min', -3.0)),
        f'{p}_pi_max':      float(gcfg.get('pi_max', 3.0)),
        f'{p}_pi_steps':    int(gcfg.get('pi_steps', 60)),
        f'{p}_n_sets':      int(gcfg.get('n_sets', 10000)),
        f'{p}_scan_sigma':  bool(gcfg.get('scan_sigma', False)),
        f'{p}_sigma_single': float(gcfg.get('sigma_single',
            float(settings.get('grid', {}).get('sigma_single', 15.0)))),
        f'{p}_sig_min':     float(gcfg.get('sigma_min', 5.0)),
        f'{p}_sig_max':     float(gcfg.get('sigma_max', 30.0)),
        f'{p}_sig_steps':   int(gcfg.get('sigma_steps', 10)),
        f'{p}_logP_min':    float(orb.get('logP_min', 0.15)),
        f'{p}_logP_max':    float(orb.get('logP_max', 5.0)),
        f'{p}_scan_logPmax':       bool(gcfg.get('scan_logPmax', False)),
        f'{p}_logPmax_scan_min':   float(gcfg.get('logPmax_scan_min', 1.0)),
        f'{p}_logPmax_scan_max':   float(gcfg.get('logPmax_scan_max', 6.0)),
        f'{p}_logPmax_scan_steps': int(gcfg.get('logPmax_scan_steps', 15)),
        f'{p}_e_max':       float(orb.get('e_max', 0.9)),
        f'{p}_mass_fixed':  float(orb.get('mass_primary_fixed', 10.0)),
        f'{p}_q_min':       float(orb.get('q_range', [0.1, 2.0])[0]),
        f'{p}_q_max':       float(orb.get('q_range', [0.1, 2.0])[1]),
        f'{p}_lq_mu':       float(orb.get('langer_q_mu', 0.7)),
        f'{p}_lq_sig':      float(orb.get('langer_q_sigma', 0.2)),
        f'{p}_sigma_meas':  float(simcfg.get('sigma_measure', 1.622)),
        f'{p}_drv_bin_width': float(gcfg.get('drv_bin_width', 5.0)),
        f'{p}_drv_max':       float(gcfg.get('drv_max', 360.0)),
        f'{p}_adaptive_bins': bool(gcfg.get('adaptive_bins', True)),
    }
    for _k, _v in _defaults.items():
        if _k not in st.session_state:
            st.session_state[_k] = _v

    left_col, right_col = st.columns([0.30, 0.70])

    with left_col:
        st.markdown('#### Cadence-Aware \u2014 Dsilva (power-law)')

        with st.expander('Grid parameters', expanded=True):
            _c1, _c2, _c3 = st.columns(3)
            fb_min = _c1.number_input('f_bin min', 0.0, 1.0,
                float(gcfg.get('fbin_min', 0.0)), 0.01, key=f'{p}_fb_min',
                on_change=lambda: sm.save([_sec, 'fbin_min'],
                    value=st.session_state[f'{p}_fb_min']))
            fb_max = _c2.number_input('f_bin max', 0.0, 1.0,
                float(gcfg.get('fbin_max', 1.0)), 0.01, key=f'{p}_fb_max',
                on_change=lambda: sm.save([_sec, 'fbin_max'],
                    value=st.session_state[f'{p}_fb_max']))
            fb_steps = _c3.number_input('steps', 5, 500,
                int(gcfg.get('fbin_steps', 100)), 5, key=f'{p}_fb_steps',
                on_change=lambda: sm.save([_sec, 'fbin_steps'],
                    value=st.session_state[f'{p}_fb_steps']))

            _c4, _c5, _c6 = st.columns(3)
            pi_min = _c4.number_input('\u03c0 min', -5.0, 5.0,
                float(gcfg.get('pi_min', -3.0)), 0.1, key=f'{p}_pi_min',
                on_change=lambda: sm.save([_sec, 'pi_min'],
                    value=st.session_state[f'{p}_pi_min']))
            pi_max = _c5.number_input('\u03c0 max', -5.0, 5.0,
                float(gcfg.get('pi_max', 3.0)), 0.1, key=f'{p}_pi_max',
                on_change=lambda: sm.save([_sec, 'pi_max'],
                    value=st.session_state[f'{p}_pi_max']))
            pi_steps = _c6.number_input('\u03c0 steps', 5, 500,
                int(gcfg.get('pi_steps', 60)), 5, key=f'{p}_pi_steps',
                on_change=lambda: sm.save([_sec, 'pi_steps'],
                    value=st.session_state[f'{p}_pi_steps']))

        with st.expander('Cadence-aware settings', expanded=True):
            n_sets = st.number_input('N_sets', 100, 100000,
                int(gcfg.get('n_sets', 10000)), 100, key=f'{p}_n_sets',
                on_change=lambda: sm.save([_sec, 'n_sets'],
                    value=st.session_state[f'{p}_n_sets']))
            _use_adaptive, _cad_bin_edges_d, drv_bin_width, drv_max = \
                _render_cadence_adaptive_bins(p, _sec, sm, gcfg, settings)
            _cad_err_info = _render_error_model_selector(
                p, gcfg, sm, 'grid_cadence_dsilva')
            _sigma_meas = _cad_err_info['sigma_measure']

        with st.expander('Sigma scan', expanded=False):
            sigma_vals = _render_cadence_sigma_scan(
                p, _sec, sm, gcfg, settings)

    with right_col:
        with st.expander(
                '\U0001f527 Orbital parameters (Kepler)', expanded=False):
            _orb_vals = _render_orbital_params_dsilva(
                p, _sec, sm, orb, gcfg)

        from wr_bias_simulation import BinaryParameterConfig
        _bin_cfg = BinaryParameterConfig(
            logP_min=_orb_vals['logP_min'],
            logP_max=_orb_vals['logP_max'],
            period_model='powerlaw',
            e_model=_orb_vals['e_model'], e_max=_orb_vals['e_max'],
            mass_primary_model=_orb_vals['mass_model'],
            mass_primary_fixed=_orb_vals['mass_fixed'],
            mass_primary_range=tuple(_orb_vals['mass_range']),
            q_model=_orb_vals['q_model'],
            q_range=(_orb_vals['q_min'], _orb_vals['q_max']),
            langer_q_mu=_orb_vals['lq_mu'],
            langer_q_sigma=_orb_vals['lq_sig'],
        )

        with st.expander(
                '\U0001f39a\ufe0f logP_max scan', expanded=False):
            _cd_logPmax_vals = _render_logPmax_scan(
                p, 'grid_cadence_dsilva', sm, default_logP_max=5.0)

        _cadence_run_and_results(
            p, _is_dsilva, _period_model,
            fb_min, fb_max, fb_steps,
            pi_min, pi_max, pi_steps,
            n_sets, sigma_vals, _bin_cfg, _sigma_meas,
            settings, sm, err_info=_cad_err_info,
            logPmax_scan_vals=_cd_logPmax_vals)

    _render_cadence_results(p, _is_dsilva, _bin_cfg, settings=settings)


# ─────────────────────────────────────────────────────────────────────────────
# Cadence Langer tab
# ─────────────────────────────────────────────────────────────────────────────

def _render_cadence_langer_tab(p: str, settings: dict, sm) -> None:
    """Render Cadence-Aware simulation tab (Langer 2020)."""
    _is_dsilva = False
    _period_model = 'langer2020'
    _sec = 'grid_cadence_langer'

    lg_cfg = settings.get(_sec, {})
    lg_pp = lg_cfg.get('langer_period_params', {})
    simcfg = settings.get('simulation', {})

    _defaults = {
        f'{p}_fb_min':      float(lg_cfg.get('fbin_min', 0.0)),
        f'{p}_fb_max':      float(lg_cfg.get('fbin_max', 1.0)),
        f'{p}_fb_steps':    int(lg_cfg.get('fbin_steps', 100)),
        f'{p}_n_sets':      int(lg_cfg.get('n_sets', 10000)),
        f'{p}_scan_sigma':  bool(lg_cfg.get('scan_sigma', False)),
        f'{p}_sigma_single': float(lg_cfg.get('sigma_single',
            float(settings.get('grid', {}).get('sigma_single', 15.0)))),
        f'{p}_sig_min':     float(lg_cfg.get('sigma_min', 5.0)),
        f'{p}_sig_max':     float(lg_cfg.get('sigma_max', 30.0)),
        f'{p}_sig_steps':   int(lg_cfg.get('sigma_steps', 10)),
        f'{p}_sigma_meas':  float(lg_cfg.get('sigma_meas',
            float(simcfg.get('sigma_measure', 1.622)))),
        f'{p}_dist_A':      str(lg_pp.get('dist_A', 'empirical')),
        f'{p}_mu_A':        float(lg_pp.get('mu_A', 1.0)),
        f'{p}_sigma_A':     float(lg_pp.get('sigma_A', 0.12)),
        f'{p}_dist_B':      str(lg_pp.get('dist_B', 'empirical')),
        f'{p}_mu_B':        float(lg_pp.get('mu_B', 2.1)),
        f'{p}_sigma_B':     float(lg_pp.get('sigma_B', 0.2)),
        f'{p}_weight_A':    float(lg_pp.get('weight_A', 0.08)),
        f'{p}_logP_min':    float(lg_cfg.get('logP_min', 0.5)),
        f'{p}_logP_max':    float(lg_cfg.get('logP_max', 3.5)),
        f'{p}_scan_logPmax':       bool(lg_cfg.get('scan_logPmax', False)),
        f'{p}_logPmax_scan_min':   float(
            lg_cfg.get('logPmax_scan_min', 1.0)),
        f'{p}_logPmax_scan_max':   float(
            lg_cfg.get('logPmax_scan_max', 6.0)),
        f'{p}_logPmax_scan_steps': int(
            lg_cfg.get('logPmax_scan_steps', 15)),
        f'{p}_mass_fixed':  float(
            lg_cfg.get('mass_primary_fixed', 10.0)),
        f'{p}_q_min':       float(
            lg_cfg.get('q_range', [0.25, 1.65])[0]),
        f'{p}_q_max':       float(
            lg_cfg.get('q_range', [0.25, 1.65])[1]),
        f'{p}_lq_mu':       float(lg_cfg.get('langer_q_mu', 0.67)),
        f'{p}_lq_sig':      float(lg_cfg.get('langer_q_sigma', 0.39)),
        f'{p}_q_flipped':   bool(lg_cfg.get('q_flipped', False)),
        f'{p}_drv_bin_width': float(lg_cfg.get('drv_bin_width', 5.0)),
        f'{p}_drv_max':       float(lg_cfg.get('drv_max', 360.0)),
        f'{p}_adaptive_bins': bool(lg_cfg.get('adaptive_bins', True)),
    }
    for _k, _v in _defaults.items():
        if _k not in st.session_state:
            st.session_state[_k] = _v

    left_col, right_col = st.columns([0.30, 0.70])

    with left_col:
        st.markdown('#### Cadence-Aware \u2014 Langer 2020')

        with st.expander('Grid parameters', expanded=True):
            _c1, _c2, _c3 = st.columns(3)
            fb_min = _c1.number_input('f_bin min', 0.0, 1.0,
                float(lg_cfg.get('fbin_min', 0.0)), 0.01,
                key=f'{p}_fb_min',
                on_change=lambda: sm.save([_sec, 'fbin_min'],
                    value=st.session_state[f'{p}_fb_min']))
            fb_max = _c2.number_input('f_bin max', 0.0, 1.0,
                float(lg_cfg.get('fbin_max', 1.0)), 0.01,
                key=f'{p}_fb_max',
                on_change=lambda: sm.save([_sec, 'fbin_max'],
                    value=st.session_state[f'{p}_fb_max']))
            fb_steps = _c3.number_input('steps', 5, 500,
                int(lg_cfg.get('fbin_steps', 100)), 5,
                key=f'{p}_fb_steps',
                on_change=lambda: sm.save([_sec, 'fbin_steps'],
                    value=st.session_state[f'{p}_fb_steps']))

        with st.expander('Cadence-aware settings', expanded=True):
            n_sets = st.number_input('N_sets', 100, 100000,
                int(lg_cfg.get('n_sets', 10000)), 100,
                key=f'{p}_n_sets',
                on_change=lambda: sm.save([_sec, 'n_sets'],
                    value=st.session_state[f'{p}_n_sets']))
            _use_adaptive, _cad_bin_edges_l, drv_bin_width, drv_max = \
                _render_cadence_adaptive_bins(
                    p, _sec, sm, lg_cfg, settings)
            _cl_err_info = _render_error_model_selector(
                p, lg_cfg, sm, 'grid_cadence_langer')
            _sigma_meas = _cl_err_info['sigma_measure']

        with st.expander('Sigma scan', expanded=False):
            sigma_vals = _render_cadence_sigma_scan(
                p, _sec, sm, lg_cfg, settings)

    with right_col:
        with st.expander(
                '\U0001f527 Orbital parameters (Langer 2020)',
                expanded=False):
            _cl_orb = _render_orbital_params_langer(
                p, _sec, sm, lg_pp, lg_cfg)

            from wr_bias_simulation import BinaryParameterConfig
            _period_params = {
                'dist_A': _cl_orb['dist_A'],
                'mu_A': _cl_orb['mu_A'],
                'sigma_A': _cl_orb['sigma_A'],
                'dist_B': _cl_orb['dist_B'],
                'mu_B': _cl_orb['mu_B'],
                'sigma_B': _cl_orb['sigma_B'],
                'weight_A': _cl_orb['weight_A'],
            }
            _bin_cfg = BinaryParameterConfig(
                logP_min=_cl_orb['logP_min'],
                logP_max=_cl_orb['logP_max'],
                period_model='langer2020',
                langer_period_params=_period_params,
                e_model='zero', e_max=0.0,
                mass_primary_model=_cl_orb['mass_model'],
                mass_primary_fixed=_cl_orb['mass_fixed'],
                mass_primary_range=tuple(_cl_orb['mass_range']),
                q_model=_cl_orb['q_model'],
                q_range=(_cl_orb['q_min'], _cl_orb['q_max']),
                langer_q_mu=_cl_orb['lq_mu'],
                langer_q_sigma=_cl_orb['lq_sig'],
                q_flipped=_cl_orb['q_flipped'],
            )

        with st.expander(
                '\U0001f39a\ufe0f logP_max scan', expanded=False):
            _cl_logPmax_vals = _render_logPmax_scan(
                p, 'grid_cadence_langer', sm, default_logP_max=3.5)

        pi_min, pi_max, pi_steps = 0.0, 0.0, 1
        _cadence_run_and_results(
            p, _is_dsilva, _period_model,
            fb_min, fb_max, fb_steps,
            pi_min, pi_max, pi_steps,
            n_sets, sigma_vals, _bin_cfg, _sigma_meas,
            settings, sm, err_info=_cl_err_info,
            logPmax_scan_vals=_cl_logPmax_vals)

    _render_cadence_results(p, _is_dsilva, _bin_cfg, settings=settings)
