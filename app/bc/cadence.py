"""bc.cadence — Cadence-aware simulation tabs (Dsilva + Langer variants)."""
from __future__ import annotations

import datetime as _dt
import json
import os
import sys
import threading
import time

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
    SCORING_METHODS, _METHOD_COLORS, _METHOD_SCORING_LABELS, _METHOD_COLORBAR_OVERRIDE,
    _RESULT_DIR, _HISTORY_PATH, _FILENAME_FORMAT_HELP,
    _hex_to_rgba, _fmt_eta, _result_path, _stable_cfg_hash,
    _build_descriptive_filename, _list_saved_results,
    _build_partial_filename, _list_partial_results,
    _scan_partial_metadata, _render_partial_table,
    _scan_result_metadata,
    _make_max_pval_fig, _make_min_score_fig,
    _find_reusable_fbin, _find_reusable_fbin_langer,
    _append_run_history,
    _render_cdf_sanity_check, _render_methodology_expander,
    _best_point, _make_heatmap_fig,
)
from bc.analysis import (
    _render_method_summary_section, _render_method_expander,
    _render_cvm_analysis, _get_method_array,
)
from bc.params import (
    _render_orbital_params_dsilva, _render_orbital_params_langer,
    _render_cadence_sigma_scan, _render_cadence_adaptive_bins,
)
from bc.runners import _run_cadence_bg
from bc.extras import _render_error_model_selector

def _render_cadence_results(p: str, _is_dsilva: bool, bin_cfg=None) -> None:
    """Shared right-column results display for both cadence tabs."""
    pal = get_palette()
    _ch = int(st.session_state.get('bc_canvas_height', 520))
    _cw_raw = int(st.session_state.get('bc_canvas_width', 0))
    _cw = _cw_raw if _cw_raw > 0 else None
    _use_cw = (_cw is None)

    _job = st.session_state.get(f'{p}_job')
    _saved_result = st.session_state.get(f'{p}_result')

    if _job is None and _saved_result is None:
        st.info('Configure parameters and click **Run** to start a cadence-aware simulation.')
        return

    # If job is done or we have a saved result, show it
    if _job is None and _saved_result is not None:
        status = 'done'
    else:
        status = _job.get('status', 'idle') if _job else 'idle'

    if status == 'running':
        # Fragment-based polling: only re-renders itself every 3s, no flicker
        @st.fragment(run_every=3)
        def _cadence_live_poll():
            _j = st.session_state.get(f'{p}_job')
            if _j is None or _j.get('status') != 'running':
                st.rerun(scope='app')
                return
            st.progress(_j.get('progress_pct', 0),
                        text=_j.get('progress_text', 'Running...'))
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
            # Live 1D σ graph — show max likelihood per sigma
            _lsig = _j.get('live_sigma_1d')
            if _lsig and len(_lsig.get('sigma_vals', [])) > 1:
                _lsig_likelihood = _lsig.get('max_likelihood')
                if _lsig_likelihood and any(v > 0 for v in _lsig_likelihood):
                    st.plotly_chart(
                        _make_max_pval_fig(
                            np.array(_lsig['sigma_vals']),
                            _lsig_likelihood,
                            height=250,
                            x_label='σ_single (km/s)',
                            stat_label='Likelihood',
                        ), use_container_width=True)
                else:
                    st.plotly_chart(
                        _make_max_pval_fig(
                            np.array(_lsig['sigma_vals']),
                            _lsig['max_pvals'],
                            height=250,
                            x_label='σ_single (km/s)',
                            stat_label='K-S',
                        ), use_container_width=True)
        _cadence_live_poll()

    elif status == 'error':
        st.error(
            f"Simulation failed:\n```\n{_job.get('error', 'Unknown')}\n```")
        del st.session_state[f'{p}_job']

    elif status == 'cancelled':
        _partial_saved = _job.get('partial_saved', False) if _job else False
        if _partial_saved:
            st.warning('Simulation cancelled \u2014 partial progress saved.')
            _scan_partial_metadata.clear()
        else:
            st.warning('Simulation was cancelled.')
        del st.session_state[f'{p}_job']

    elif status == 'done':
        # Get result from job (first time) or saved state (subsequent reruns)
        if _job is not None and _job.get('result'):
            result = _job['result']
            st.session_state[f'{p}_result'] = result
            # Persist final live heatmaps so they remain visible after job cleanup
            if _job.get('live_heatmaps'):
                st.session_state[f'{p}_final_live_heatmaps'] = _job['live_heatmaps']
            # Persist final live sigma 1D graph so it remains visible after job cleanup
            if _job.get('live_sigma_1d'):
                st.session_state[f'{p}_final_live_sigma_1d'] = _job['live_sigma_1d']
            del st.session_state[f'{p}_job']
            # Clear caches so load table picks up auto-saved file
            cached_load_grid_result.clear()
            _scan_result_metadata.clear()
        else:
            result = _saved_result or {}

        # Show persisted final live heatmaps (Bug 1: survive job cleanup)
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

        # Show persisted final live sigma 1D graph (survive job cleanup)
        _final_lsig = st.session_state.get(f'{p}_final_live_sigma_1d')
        if _final_lsig and len(_final_lsig.get('sigma_vals', [])) > 1:
            _lsig_lk = _final_lsig.get('max_likelihood')
            if _lsig_lk and any(v > 0 for v in _lsig_lk):
                st.plotly_chart(
                    _make_max_pval_fig(
                        np.array(_final_lsig['sigma_vals']),
                        _lsig_lk, height=250,
                        x_label='σ_single (km/s)',
                        stat_label='Likelihood',
                    ), use_container_width=True,
                    key=f'{p}_final_sigma_1d_lk')
            else:
                st.plotly_chart(
                    _make_max_pval_fig(
                        np.array(_final_lsig['sigma_vals']),
                        _final_lsig['max_pvals'], height=250,
                        x_label='σ_single (km/s)',
                        stat_label='K-S',
                    ), use_container_width=True,
                    key=f'{p}_final_sigma_1d_ks')

        ks_p_arr = result.get('ks_p')
        if ks_p_arr is None:
            st.warning('No results found.')
            return

        fbin_grid = result['fbin_grid']
        pi_grid   = result['pi_grid']
        sigma_grid = result['sigma_grid']
        n_sig = len(sigma_grid)
        _is_langer_sigma = (not _is_dsilva) and n_sig > 1

        if _is_langer_sigma:
            # Langer with sigma scan: reshape to (n_fb, n_sig) — fbin × σ
            hm_z = ks_p_arr[:, :, 0].T  # (n_sig, n_fb, 1) → squeeze → transpose
            _x_vals = sigma_grid
            _x_label = 'σ_single (km/s)'
            _x_name = 'σ'
        elif n_sig == 1:
            hm_z = ks_p_arr[0]
            _x_vals = pi_grid if _is_dsilva else sigma_grid
            _x_label = 'π  (period power-law index)' if _is_dsilva else 'σ_single (km/s)'
            _x_name = 'π' if _is_dsilva else 'σ'
        else:
            # Dsilva with sigma scan: show best sigma slice
            _pmax = [float(np.nanmax(ks_p_arr[s])) for s in range(n_sig)]
            _best_s = int(np.argmax(_pmax))
            hm_z = ks_p_arr[_best_s]
            _x_vals = pi_grid
            _x_label = 'π  (period power-law index)'
            _x_name = 'π'
        # Best-fit values from K-S (used downstream for summary, diagnostics, etc.)
        _bi = np.unravel_index(np.argmax(hm_z), hm_z.shape)
        _best_x_val = float(np.asarray(_x_vals)[_bi[1]])
        _best_fb = float(fbin_grid[_bi[0]])
        _best_pval = float(hm_z[_bi])

        # ── Multi-method comparison summary (cadence) ────────────────────
        if _is_langer_sigma:
            # Cadence Langer: arrays are [n_sig, n_fb, n_pi=1], treat as 2D
            _cad_ndim_mode = 'cadence_langer'
            _cad_extra_grids = None
            _cad_x_g = np.asarray(sigma_grid)
            _cad_x_name = 'sigma'
            _cad_x_label = 'sigma_single'
            _cad_x_disp = 'sigma_single (km/s)'
        elif _is_dsilva:
            # Cadence Dsilva: arrays are [n_sig, n_fb, n_pi]
            _cad_ndim_mode = 'cadence_dsilva'
            _cad_extra_grids = [('sigma', np.asarray(sigma_grid))] if n_sig > 1 else None
            _cad_x_g = pi_grid
            _cad_x_name = 'pi'
            _cad_x_label = 'pi'
            _cad_x_disp = 'pi (period power-law index)'
        else:
            # Cadence Langer without sigma scan: single sigma, treat as 2D
            _cad_ndim_mode = 'cadence_langer'
            _cad_extra_grids = None
            _cad_x_g = np.asarray(sigma_grid)
            _cad_x_name = 'sigma'
            _cad_x_label = 'sigma_single'
            _cad_x_disp = 'sigma_single (km/s)'

        # ── Multi-method comparison summary (cadence, shown directly) ────
        _method_res = _render_method_summary_section(
            result, np.asarray(fbin_grid), _cad_x_g,
            extra_grids=_cad_extra_grids,
            prefix=p, x_name=_cad_x_name, x_label=_cad_x_label,
            ndim_mode=_cad_ndim_mode,
        )

        # ── CDF Comparison — all methods (at top, above expanders) ─────
        if _method_res:
            from bc.analysis import _render_all_methods_cdf
            with st.expander('CDF Comparison (cadence-aware)', expanded=True):
                _cdf_cols = st.columns(len(_method_res) + 1)
                _cdf_show = {}
                _cdf_cols[0].markdown('**Show:**')
                for _ci, (_mk_c, _) in enumerate(_method_res.items()):
                    _mname_c = next((n for k, n, _, _, _ in SCORING_METHODS
                                     if k == _mk_c), _mk_c)
                    _cdf_show[_mk_c] = _cdf_cols[_ci + 1].checkbox(
                        _mname_c, value=True, key=f'{p}_cdf_show_{_mk_c}')
                _shown = {k: v for k, v in _method_res.items()
                          if _cdf_show.get(k, True)}
                if _shown:
                    _render_all_methods_cdf(
                        result, _shown, np.asarray(fbin_grid), _cad_x_g,
                        prefix=f'{p}_top', x_name=_cad_x_name,
                        x_label=_cad_x_label)

        # ── Per-method expanders (cadence) ──────────────────────────────
        # Determine outer slice indices for 3D→2D slicing
        if n_sig > 1:
            _cad_best_s = 0
            if np.any(np.isfinite(ks_p_arr)):
                _pmax_list = [float(np.nanmax(ks_p_arr[s])) for s in range(n_sig)]
                _cad_best_s = int(np.argmax(_pmax_list))
            _cad_outer = (_cad_best_s,)
        else:
            _cad_outer = (0,) if ks_p_arr.ndim == 3 else None

        for _mk, _mname, _pk, _dk, _mcolor in SCORING_METHODS:
            _m_p_arr = _get_method_array(result, _pk)
            if _m_p_arr is None:
                continue
            _m_d_arr = _get_method_array(result, _dk)
            # For cadence Langer: squeeze pi dim and transpose to [n_fb, n_sig]
            if _is_langer_sigma and _m_p_arr.ndim == 3 and _m_p_arr.shape[2] == 1:
                _m_p_arr = _m_p_arr[:, :, 0].T
                if _m_d_arr is not None and _m_d_arr.ndim == 3:
                    _m_d_arr = _m_d_arr[:, :, 0].T
            with st.expander(f'{_mname}', expanded=(_mk == 'ks')):
                _render_method_expander(
                    _mk, _mname, _m_p_arr, _m_d_arr,
                    result, np.asarray(fbin_grid), _cad_x_g,
                    prefix=p,
                    height=_ch, width=_cw, use_cw=_use_cw,
                    x_label=_cad_x_label, x_name=_cad_x_name,
                    x_display_label=_cad_x_disp,
                    ndim_mode=_cad_ndim_mode,
                    disp_outer_slices=None if _is_langer_sigma else _cad_outer,
                    method_results=_method_res,
                )

        # (Bug 11 removed: old CvM expander is now in per-method expanders)

        # Apply grid exclusion mask to cadence arrays for downstream sections
        # Rebuild masks from excluded VALUE SETS (not stored 1D masks which may
        # have a different length than the cadence grid)
        _exc_fb_vals = st.session_state.get(f'{p}_cvm_exc_x_val_set', set())
        _exc_y_vals = st.session_state.get(f'{p}_cvm_exc_y_val_set', set())
        _exc_sig_list = st.session_state.get(f'{p}_cvm_stored_exc_sig_vals', [])
        _cad_ks_d = result.get('ks_D')
        _has_fb_exc = len(_exc_fb_vals) > 0
        _has_y_exc = len(_exc_y_vals) > 0
        _has_sig_exc = len(_exc_sig_list) > 0
        if _has_fb_exc or _has_y_exc or _has_sig_exc:
            # Rebuild 1D masks matching cadence grid dimensions
            _fb_exc_1d = np.array([float(v) in _exc_fb_vals for v in fbin_grid])
            _pi_exc_1d = np.array([float(v) in _exc_y_vals for v in pi_grid])
            _cad_exc_2d = _fb_exc_1d[:, None] | _pi_exc_1d[None, :]
            # Sigma exclusion: exclude entire sigma slices
            _exc_sig_set = set(float(v) for v in _exc_sig_list)
            _sig_exc_slices = {i for i, v in enumerate(sigma_grid) if float(v) in _exc_sig_set}
            # Also check if CvM y-axis was sigma (Langer case) — those values
            # should exclude sigma slices, not pi axis
            if _is_langer_sigma and _has_y_exc:
                for i, v in enumerate(sigma_grid):
                    if float(v) in _exc_y_vals:
                        _sig_exc_slices.add(i)
                # Reset pi exclusion since y-axis was sigma, not pi
                _pi_exc_1d = np.zeros(len(pi_grid), dtype=bool)
                _cad_exc_2d = _fb_exc_1d[:, None] | _pi_exc_1d[None, :]
            ks_p_arr = ks_p_arr.copy()
            if _cad_ks_d is not None:
                _cad_ks_d = np.array(_cad_ks_d).copy()
            for _i_s in range(ks_p_arr.shape[0]):
                if _i_s in _sig_exc_slices:
                    ks_p_arr[_i_s] = np.nan
                    if _cad_ks_d is not None:
                        _cad_ks_d[_i_s] = np.nan
                else:
                    ks_p_arr[_i_s][_cad_exc_2d] = np.nan
                    if _cad_ks_d is not None:
                        _cad_ks_d[_i_s][_cad_exc_2d] = np.nan
            # Recompute hm_z and best-fit after exclusion
            if _is_langer_sigma:
                hm_z = ks_p_arr[:, :, 0].T
            elif n_sig == 1:
                hm_z = ks_p_arr[0]
            else:
                _pmax = [float(np.nanmax(ks_p_arr[s])) for s in range(n_sig)]
                _best_s = int(np.argmax(_pmax))
                hm_z = ks_p_arr[_best_s]
            if np.any(np.isfinite(hm_z)):
                _bi = np.unravel_index(np.nanargmax(hm_z), hm_z.shape)
                _best_fb = float(fbin_grid[_bi[0]])
                _best_x_val = float(np.asarray(_x_vals)[_bi[1]])
                _best_pval = float(hm_z[_bi])

        # ── Best-fit summary moved into per-method expanders (Task #138) ──



        # (old summary table removed — per-method summaries are in each expander)
        # ── Diagnostic analysis (requires simulation at best-fit) ─────────────
        # ── Diagnostic analysis (requires simulation at best-fit) ─────────────
        # ── Diagnostic Analysis (auto-trigger at best-fit) ─────────────
        st.markdown('---')
        st.markdown('### Diagnostic Analysis')

        thresh_dRV = 45.5

        _diag_key = f'{p}_gap_sim'
        _diag_fp_key = f'{p}_gap_fingerprint'
        if not np.any(np.isfinite(ks_p_arr)):
            st.info('No finite values — cannot run diagnostic analysis.')
            return
        _cad_best_sigma_diag = float(sigma_grid[
            np.unravel_index(np.nanargmax(ks_p_arr), ks_p_arr.shape)[0]])

        # Auto-trigger: run simulate_with_params when best-fit changes
        from wr_bias_simulation import (
            SimulationConfig, BinaryParameterConfig, simulate_with_params,
        )
        _gap_fingerprint_cad = (_best_fb, _best_x_val, _cad_best_sigma_diag,
                                ks_p_arr.shape)
        if (st.session_state.get(_diag_fp_key) != _gap_fingerprint_cad
                or _diag_key not in st.session_state):
            # Use the bin_cfg passed from the tab UI (has correct orbital params)
            if bin_cfg is not None:
                _d_bin_cfg = bin_cfg
            else:
                # Fallback: reconstruct from session_state (legacy path)
                _d_period_model = 'powerlaw' if _is_dsilva else 'langer2020'
                _d_bin_cfg = BinaryParameterConfig(
                    logP_min=float(st.session_state.get(f'{p}_logP_min', 0.15)),
                    logP_max=float(st.session_state.get(f'{p}_logP_max', 5.0)),
                    period_model=_d_period_model,
                    e_model=str(st.session_state.get(f'{p}_e_model', 'flat')),
                    e_max=float(st.session_state.get(f'{p}_e_max', 0.9)),
                    mass_primary_model=str(st.session_state.get(f'{p}_mass_model', 'fixed')),
                    mass_primary_fixed=float(st.session_state.get(f'{p}_mass_fixed', 10.0)),
                    q_model=str(st.session_state.get(f'{p}_q_model', 'flat')),
                    q_range=(float(st.session_state.get(f'{p}_q_min', 0.1)),
                             float(st.session_state.get(f'{p}_q_max', 2.0))),
                    langer_q_mu=float(st.session_state.get(f'{p}_lq_mu', 0.7)),
                    langer_q_sigma=float(st.session_state.get(f'{p}_lq_sig', 0.2)),
                )

            _d_sigma_meas = float(st.session_state.get(f'{p}_sigma_meas', 1.622))
            _d_sim_cfg = SimulationConfig(
                n_stars=10000,
                sigma_single=_cad_best_sigma_diag,
                sigma_measure=_d_sigma_meas,
            )

            rng_diag = np.random.default_rng(42)
            _diag_result = simulate_with_params(
                _best_fb, _best_x_val if _is_dsilva else 0.0,
                _d_sim_cfg, _d_bin_cfg, rng_diag,
            )
            st.session_state[_diag_key] = _diag_result
            st.session_state[_diag_fp_key] = _gap_fingerprint_cad

        if _diag_key in st.session_state:
            gap_sim = st.session_state[_diag_key]
            gap_drv = gap_sim['delta_rv']
            gap_is_bin = gap_sim['is_binary']
            gap_idx_bin = gap_sim['idx_bin']

            intrinsic_fbin = float(gap_is_bin.mean())
            detected_mask = gap_drv > thresh_dRV
            observed_fbin = float(detected_mask.mean())
            missed_count = int(np.sum(gap_is_bin & ~detected_mask))
            detected_bin_count = int(np.sum(gap_is_bin & detected_mask))
            total_bin = int(gap_is_bin.sum())

            _bin_drv = gap_drv[gap_idx_bin] if gap_idx_bin.size > 0 else np.array([])
            _bin_detected_mask = _bin_drv > thresh_dRV
            _bin_missed_mask = ~_bin_detected_mask

            # ── Period distribution + Binary fraction vs threshold ────────
            _lp_col, _bf_col = st.columns(2)

            _CLR_DETECTED = '#E25A53'
            _CLR_MISSED = '#F5A623'

            with _lp_col:
                st.markdown('#### Period Distribution (log P)')
                fig_logP_cad = go.Figure()

                if gap_sim['P_days'].size > 0:
                    _logP_det = (np.log10(gap_sim['P_days'][_bin_detected_mask])
                                 if np.any(_bin_detected_mask) else np.array([]))
                    _logP_mis = (np.log10(gap_sim['P_days'][_bin_missed_mask])
                                 if np.any(_bin_missed_mask) else np.array([]))

                    if _logP_det.size > 0:
                        fig_logP_cad.add_trace(go.Histogram(
                            x=_logP_det, nbinsx=35,
                            histnorm='probability density',
                            name=f'Detected ({_logP_det.size})',
                            marker_color=_CLR_DETECTED, opacity=0.6,
                        ))
                    if _logP_mis.size > 0:
                        fig_logP_cad.add_trace(go.Histogram(
                            x=_logP_mis, nbinsx=35,
                            histnorm='probability density',
                            name=f'Missed ({_logP_mis.size})',
                            marker_color=_CLR_MISSED, opacity=0.6,
                        ))

                fig_logP_cad.update_layout(**{
                    **PLOTLY_THEME,
                    'barmode': 'overlay',
                    'title': dict(
                        text=f'Simulated Period Distribution',
                        font=dict(size=14)),
                    'xaxis_title': 'log10(P / days)',
                    'yaxis_title': 'Probability density',
                    'height': 400,
                    'margin': dict(l=60, r=20, t=50, b=50),
                    'legend': dict(x=0.65, y=0.95),
                })
                st.plotly_chart(fig_logP_cad, use_container_width=True,
                                key=f'{p}_logP_hist')
                st.caption(
                    'Period distribution of simulated binaries at the best-fit model. '
                    'Red: detected. Amber: missed (below threshold). '
                    'Missed systems concentrate at longer periods.'
                )

            with _bf_col:
                st.markdown('#### Binary Fraction vs Threshold')
                _n_sim = len(gap_drv)
                _thresh_arr = np.linspace(0, float(np.max(gap_drv) * 1.05), 200)
                _fbin_curve = np.array([float(np.sum(gap_drv > t)) / _n_sim
                                        for t in _thresh_arr])

                _bin_drv_all = gap_drv[gap_is_bin]
                _sin_drv_all = gap_drv[~gap_is_bin]
                _missed_bin_curve = np.array(
                    [float(np.sum(_bin_drv_all <= t)) / _n_sim for t in _thresh_arr])
                _false_pos_curve = np.array(
                    [float(np.sum(_sin_drv_all > t)) / _n_sim for t in _thresh_arr])

                fig_gap_cad = go.Figure()
                fig_gap_cad.add_trace(go.Scatter(
                    x=_thresh_arr, y=_missed_bin_curve,
                    fill='tozeroy', fillcolor='rgba(242,166,35,0.25)',
                    line=dict(width=0), mode='lines',
                    name='Missed binaries', showlegend=True,
                ))
                if np.any(_false_pos_curve > 0):
                    fig_gap_cad.add_trace(go.Scatter(
                        x=_thresh_arr, y=_false_pos_curve,
                        fill='tozeroy', fillcolor='rgba(74,144,217,0.15)',
                        line=dict(width=0), mode='lines',
                        name='Singles above threshold', showlegend=True,
                    ))
                fig_gap_cad.add_trace(go.Scatter(
                    x=_thresh_arr, y=_fbin_curve,
                    mode='lines', name='Observed f_bin(threshold)',
                    line=dict(color='#4A90D9', width=2.5),
                ))
                fig_gap_cad.add_hline(
                    y=intrinsic_fbin, line_dash='dot',
                    line_color='#E25A53', line_width=2,
                    annotation_text=f'Intrinsic f_bin = {intrinsic_fbin:.1%}',
                    annotation_position='top left',
                    annotation_font=dict(size=11, color='#E25A53'),
                )
                fig_gap_cad.add_vline(
                    x=thresh_dRV, line_dash='dash',
                    line_color='#F5A623', line_width=2,
                    annotation_text=f'Threshold = {thresh_dRV} km/s',
                    annotation_position='top right',
                    annotation_font=dict(size=11, color='#F5A623'),
                )
                fig_gap_cad.add_trace(go.Scatter(
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
                gap_pct = intrinsic_fbin - observed_fbin
                fig_gap_cad.add_annotation(
                    x=thresh_dRV + 15,
                    y=(intrinsic_fbin + observed_fbin) / 2,
                    text=f'Gap: {gap_pct:.1%}<br>({missed_count} missed / {total_bin} binaries)',
                    showarrow=False,
                    font=dict(size=11, color='#F5A623'),
                    bgcolor=pal['annotation_bg'],
                    bordercolor='#F5A623', borderwidth=1, borderpad=4,
                )
                fig_gap_cad.add_annotation(
                    x=thresh_dRV, y=intrinsic_fbin,
                    ax=thresh_dRV, ay=observed_fbin,
                    xref='x', yref='y', axref='x', ayref='y',
                    showarrow=True, arrowhead=3,
                    arrowwidth=2, arrowcolor='#F5A623',
                )
                fig_gap_cad.update_layout(**{
                    **PLOTLY_THEME,
                    'title': dict(
                        text='Binary Fraction vs dRV Threshold',
                        font=dict(size=14)),
                    'xaxis_title': 'dRV threshold (km/s)',
                    'yaxis_title': 'Fraction of sample',
                    'height': 400,
                    'margin': dict(l=60, r=80, t=50, b=50),
                    'showlegend': True,
                    'legend': dict(x=0.55, y=0.95, font=dict(size=10)),
                    'yaxis': dict(range=[0, min(1.0, intrinsic_fbin * 1.5)]),
                })
                st.plotly_chart(fig_gap_cad, use_container_width=True,
                                key=f'{p}_gap_chart')
                st.caption(
                    f'Observed binary fraction vs dRV threshold. '
                    f'Blue curve = fraction classified as binary. '
                    f'Dashed red = intrinsic f_bin = {intrinsic_fbin:.1%}. '
                    f'At threshold {thresh_dRV} km/s: observed = {observed_fbin:.1%}, '
                    f'gap = {gap_pct:.1%} ({missed_count} missed binaries).'
                )

            # ── Binary Orbital Parameter Histograms (9 panels, matches Dsilva) ─
            st.markdown('---')
            st.markdown('### Binary Orbital Properties')

            _mb_view_cad = st.radio(
                'Show populations',
                ['Compare detected vs missed', 'Detected binaries only',
                 'Missed binaries only', 'All binaries (combined)'],
                horizontal=True, key=f'{p}_mb_view',
            )

            def _safe_mask_cad(arr, mask):
                return arr[mask] if arr.size > 0 else np.array([])

            P_det = _safe_mask_cad(gap_sim['P_days'], _bin_detected_mask)
            e_det = _safe_mask_cad(gap_sim['e'], _bin_detected_mask)
            q_det = _safe_mask_cad(gap_sim['q'], _bin_detected_mask)
            K1_det = _safe_mask_cad(gap_sim['K1'], _bin_detected_mask)
            M1_det = _safe_mask_cad(gap_sim['M1'], _bin_detected_mask)
            i_det = np.degrees(_safe_mask_cad(gap_sim['i_rad'], _bin_detected_mask))

            P_mis = _safe_mask_cad(gap_sim['P_days'], _bin_missed_mask)
            e_mis = _safe_mask_cad(gap_sim['e'], _bin_missed_mask)
            q_mis = _safe_mask_cad(gap_sim['q'], _bin_missed_mask)
            K1_mis = _safe_mask_cad(gap_sim['K1'], _bin_missed_mask)
            M1_mis = _safe_mask_cad(gap_sim['M1'], _bin_missed_mask)
            i_mis = np.degrees(_safe_mask_cad(gap_sim['i_rad'], _bin_missed_mask))

            # omega, T0, M2
            _has_omega_cad = 'omega' in gap_sim
            if _has_omega_cad:
                omega_det = np.degrees(_safe_mask_cad(gap_sim['omega'], _bin_detected_mask))
                omega_mis = np.degrees(_safe_mask_cad(gap_sim['omega'], _bin_missed_mask))
                T0_det = _safe_mask_cad(gap_sim['T0'], _bin_detected_mask)
                T0_mis = _safe_mask_cad(gap_sim['T0'], _bin_missed_mask)
            else:
                omega_det = omega_mis = T0_det = T0_mis = np.array([])
            M2_det = q_det * M1_det if q_det.size > 0 and M1_det.size > 0 else np.array([])
            M2_mis = q_mis * M1_mis if q_mis.size > 0 and M1_mis.size > 0 else np.array([])

            # All binaries (combined)
            P_all = gap_sim['P_days']
            e_all = gap_sim['e']
            q_all = gap_sim['q']
            K1_all = gap_sim['K1']
            M1_all = gap_sim['M1']
            i_all = np.degrees(gap_sim['i_rad'])
            omega_all = np.degrees(gap_sim['omega']) if _has_omega_cad else np.array([])
            T0_all = gap_sim['T0'] if _has_omega_cad else np.array([])
            M2_all = q_all * M1_all if q_all.size > 0 else np.array([])

            _param_titles_cad = [
                'log₁₀(P / days)', 'Eccentricity', 'Mass ratio q',
                'K₁ (km/s)', 'M₁ (M⊙)', 'M₂ (M⊙)',
                'Inclination (°)', 'ω (°)', 'T₀ (rad)',
            ]
            _x_labels_cad = [
                'log₁₀(P / days)', 'e', 'q = M₂/M₁',
                'K₁ (km/s)', 'M₁ (M⊙)', 'M₂ (M⊙)',
                'i (degrees)', 'ω (degrees)', 'T₀ (rad)',
            ]
            _n_panels_cad = 9
            _n_cols_cad = 3
            _n_rows_cad = 3

            from plotly.subplots import make_subplots as _cad_mb_subplots
            fig_mb_cad = _cad_mb_subplots(
                rows=_n_rows_cad, cols=_n_cols_cad,
                subplot_titles=_param_titles_cad,
                horizontal_spacing=0.08, vertical_spacing=0.10)

            _CLR_ALL_CAD = '#52B788'
            _nbins_cad = 30

            def _add_hist_cad(fig, row, col, data, name, color, show_leg):
                if data.size == 0:
                    return
                d_min, d_max = float(data.min()), float(data.max())
                bsz = (d_max - d_min) / _nbins_cad if d_max > d_min else 1.0
                fig.add_trace(go.Histogram(
                    x=data,
                    xbins=dict(start=d_min, end=d_max + bsz * 0.01, size=bsz),
                    histnorm='probability density',
                    name=name, marker_color=color, opacity=0.6,
                    legendgroup=name, showlegend=show_leg,
                ), row=row, col=col)

            def _pos_cad(idx):
                return (idx // _n_cols_cad + 1, idx % _n_cols_cad + 1)

            if _mb_view_cad == 'All binaries (combined)':
                _all_data_cad = [
                    np.log10(P_all) if P_all.size > 0 else P_all,
                    e_all, q_all, K1_all, M1_all, M2_all, i_all,
                    omega_all, T0_all,
                ]
                for pi_idx, d in enumerate(_all_data_cad):
                    r, c = _pos_cad(pi_idx)
                    _add_hist_cad(fig_mb_cad, r, c, d,
                                  'All binaries', _CLR_ALL_CAD, pi_idx == 0)
            else:
                _det_data_cad = [
                    np.log10(P_det) if P_det.size > 0 else P_det,
                    e_det, q_det, K1_det, M1_det, M2_det, i_det,
                    omega_det, T0_det,
                ]
                _mis_data_cad = [
                    np.log10(P_mis) if P_mis.size > 0 else P_mis,
                    e_mis, q_mis, K1_mis, M1_mis, M2_mis, i_mis,
                    omega_mis, T0_mis,
                ]
                if _mb_view_cad in ('Compare detected vs missed',
                                     'Detected binaries only'):
                    for pi_idx, d in enumerate(_det_data_cad):
                        r, c = _pos_cad(pi_idx)
                        _add_hist_cad(fig_mb_cad, r, c, d,
                                      'Detected', _CLR_DETECTED, pi_idx == 0)
                if _mb_view_cad in ('Compare detected vs missed',
                                     'Missed binaries only'):
                    for pi_idx, d in enumerate(_mis_data_cad):
                        r, c = _pos_cad(pi_idx)
                        _add_hist_cad(fig_mb_cad, r, c, d,
                                      'Missed', _CLR_MISSED, pi_idx == 0)

            fig_mb_cad.update_layout(**{
                **PLOTLY_THEME,
                'barmode': 'overlay',
                'height': 850,
                'margin': dict(l=40, r=20, t=40, b=60),
                'legend': dict(
                    orientation='h', yanchor='bottom', y=1.06,
                    xanchor='center', x=0.5),
            })
            for pi_idx in range(_n_panels_cad):
                r, c = _pos_cad(pi_idx)
                fig_mb_cad.update_xaxes(title_text=_x_labels_cad[pi_idx],
                                        showgrid=False, row=r, col=c)
                fig_mb_cad.update_yaxes(showgrid=False, row=r, col=c)
            fig_mb_cad.update_yaxes(title_text='Prob. density', row=1, col=1)
            fig_mb_cad.update_yaxes(title_text='Prob. density', row=2, col=1)
            fig_mb_cad.update_yaxes(title_text='Prob. density', row=3, col=1)

            st.plotly_chart(fig_mb_cad, use_container_width=True,
                            key=f'{p}_missed_binaries')
            st.caption(
                f'Orbital parameter distributions of simulated binaries at '
                f'best-fit (f_bin={_best_fb:.3f}). '
                f'**Detected** (red): {detected_bin_count} with '
                f'dRV > {thresh_dRV} km/s. '
                f'**Missed** (amber): {missed_count} below threshold.'
            )

            # ── RV Distribution ───────────────────────────────────────────
            st.markdown('---')
            _rv_col, _det_col = st.columns(2)

            with _rv_col:
                st.markdown('#### RV Distribution')
                fig_rv_cad = go.Figure()
                _sim_single_drv = gap_drv[~gap_is_bin]
                _sim_bin_drv = gap_drv[gap_is_bin]
                nbins_rv = 50
                if _sim_single_drv.size > 0:
                    fig_rv_cad.add_trace(go.Histogram(
                        x=_sim_single_drv, nbinsx=nbins_rv,
                        histnorm='probability density',
                        name='Single stars',
                        marker_color='#7EC8E3', opacity=0.5,
                    ))
                if _sim_bin_drv.size > 0:
                    fig_rv_cad.add_trace(go.Histogram(
                        x=_sim_bin_drv, nbinsx=nbins_rv,
                        histnorm='probability density',
                        name='Binary stars',
                        marker_color='#F0A0A0', opacity=0.5,
                    ))
                # Overlay observed if available
                obs_drv_diag = result.get('obs_delta_rv')
                if obs_drv_diag is not None and len(obs_drv_diag) > 0:
                    fig_rv_cad.add_trace(go.Histogram(
                        x=obs_drv_diag, nbinsx=nbins_rv,
                        histnorm='probability density',
                        name='Observed (all)',
                        marker_color='#4A90D9', opacity=0.6,
                    ))
                fig_rv_cad.update_layout(**{
                    **PLOTLY_THEME,
                    'barmode': 'overlay',
                    'title': dict(text='dRV Distribution', font=dict(size=14)),
                    'xaxis_title': 'dRV (km/s)',
                    'yaxis_title': 'Probability density',
                    'height': 420,
                    'legend': dict(x=0.55, y=0.95),
                })
                st.plotly_chart(fig_rv_cad, use_container_width=True,
                                key=f'{p}_rv_dist')
                st.caption(
                    'Distribution of dRV values. Simulated single and binary '
                    'populations shown separately, with observed data overlaid.'
                )

            # ── Detection fraction vs threshold ───────────────────────────
            with _det_col:
                st.markdown('#### Detection Fraction vs Threshold')
                _max_drv_det = float(np.max(gap_drv))
                if obs_drv_diag is not None and len(obs_drv_diag) > 0:
                    _max_drv_det = max(_max_drv_det, float(np.max(obs_drv_diag)))
                _thresholds_det = np.linspace(0, _max_drv_det * 1.1, 150)
                _frac_sim = np.array(
                    [(gap_drv > T).mean() for T in _thresholds_det])

                fig_frac_cad = go.Figure()
                fig_frac_cad.add_trace(go.Scatter(
                    x=_thresholds_det, y=_frac_sim,
                    mode='lines', name='Simulated',
                    line=dict(color='#E25A53', width=2.5, dash='dash'),
                ))
                if obs_drv_diag is not None and len(obs_drv_diag) > 0:
                    _frac_obs = np.array(
                        [(obs_drv_diag > T).mean() for T in _thresholds_det])
                    fig_frac_cad.add_trace(go.Scatter(
                        x=_thresholds_det, y=_frac_obs,
                        mode='lines', name='Observed',
                        line=dict(color='#4A90D9', width=2.5),
                    ))
                    _fr_obs_t = float((obs_drv_diag > thresh_dRV).mean())
                else:
                    _fr_obs_t = None

                _fr_sim_t = float((gap_drv > thresh_dRV).mean())
                fig_frac_cad.add_vline(
                    x=thresh_dRV, line_dash='dot',
                    line_color='#DAA520', line_width=1.5,
                    annotation_text=f'Threshold = {thresh_dRV} km/s',
                    annotation_position='top right',
                    annotation_font_color='#DAA520',
                )
                _det_markers_x = [thresh_dRV]
                _det_markers_y = [_fr_sim_t]
                _det_markers_c = ['#E25A53']
                _det_markers_t = [f'  {_fr_sim_t:.2%}']
                if _fr_obs_t is not None:
                    _det_markers_x.append(thresh_dRV)
                    _det_markers_y.append(_fr_obs_t)
                    _det_markers_c.append('#4A90D9')
                    _det_markers_t.append(f'  {_fr_obs_t:.2%}')
                fig_frac_cad.add_trace(go.Scatter(
                    x=_det_markers_x, y=_det_markers_y,
                    mode='markers+text',
                    marker=dict(size=10, color=_det_markers_c,
                                symbol='circle',
                                line=dict(color=pal['plot_bg'], width=1)),
                    text=_det_markers_t,
                    textposition='middle right',
                    textfont=dict(size=11),
                    showlegend=False,
                ))
                fig_frac_cad.update_layout(**{
                    **PLOTLY_THEME,
                    'title': dict(
                        text=f'Detection Fraction vs dRV Threshold  '
                             f'(f_bin={_best_fb:.3f})',
                        font=dict(size=14)),
                    'xaxis_title': 'dRV threshold (km/s)',
                    'yaxis_title': 'Fraction above threshold',
                    'height': 420,
                    'legend': dict(x=0.70, y=0.95),
                    'yaxis': dict(range=[0, 1.05]),
                })
                st.plotly_chart(fig_frac_cad, use_container_width=True,
                                key=f'{p}_det_frac')
                st.caption(
                    'Fraction of stars with dRV exceeding a given threshold. '
                    'A good model should match the observed curve across all '
                    'thresholds, not just at the chosen cutoff.'
                )

        # CDF comparison with error band
        st.markdown('### CDF Comparison (cadence-aware)')

        from wr_bias_simulation import binned_cdf, DEFAULT_DRV_BIN_EDGES
        _bin_edges = result.get('bin_edges')
        if _bin_edges is None:
            _bin_edges = DEFAULT_DRV_BIN_EDGES
        obs_drv = result.get('obs_delta_rv')
        med_cdf = result.get('best_median_cdf')
        lo_cdf  = result.get('best_lo_cdf')
        hi_cdf  = result.get('best_hi_cdf')

        # If exclusion changed the best-fit, recompute CDF from diagnostic sim
        _diag_gap = st.session_state.get(f'{p}_gap_sim')
        _exc_active = (_has_fb_exc or _has_y_exc) if '_has_fb_exc' in dir() else False
        if _exc_active and _diag_gap is not None and 'delta_rv' in _diag_gap:
            _diag_drv = _diag_gap['delta_rv']
            med_cdf = binned_cdf(_diag_drv, _bin_edges)
            # Bootstrap error bands: split 10K stars into sets of 25
            _n_sample = 25  # match real sample size
            _n_boot = min(400, len(_diag_drv) // _n_sample)
            if _n_boot >= 10:
                _rng_boot = np.random.default_rng(42)
                _boot_cdfs = np.zeros((_n_boot, len(_bin_edges)))
                for _ib in range(_n_boot):
                    _samp = _rng_boot.choice(_diag_drv, size=_n_sample, replace=True)
                    _boot_cdfs[_ib] = binned_cdf(_samp, _bin_edges)
                lo_cdf = np.percentile(_boot_cdfs, 16, axis=0)
                hi_cdf = np.percentile(_boot_cdfs, 84, axis=0)
            else:
                lo_cdf = None
                hi_cdf = None

        if obs_drv is not None and med_cdf is not None:
            obs_cdf_b = binned_cdf(obs_drv, _bin_edges)

            fig_cdf = go.Figure()
            # 68% band (only if available)
            if lo_cdf is not None and hi_cdf is not None:
                fig_cdf.add_trace(go.Scatter(
                    x=np.concatenate([_bin_edges, _bin_edges[::-1]]),
                    y=np.concatenate([hi_cdf, lo_cdf[::-1]]),
                    fill='toself', fillcolor='rgba(226, 90, 83, 0.15)',
                    line=dict(width=0), name='68% band',
                    hoverinfo='skip', showlegend=True,
                ))
            # Observed
            fig_cdf.add_trace(go.Scatter(
                x=_bin_edges, y=obs_cdf_b,
                mode='lines', name='Observed',
                line=dict(color='#4A90D9', width=2.5, shape='hv'),
            ))
            # Simulated
            _sim_label = 'Simulated (median)' if lo_cdf is not None else 'Simulated (diagnostic)'
            fig_cdf.add_trace(go.Scatter(
                x=_bin_edges, y=med_cdf,
                mode='lines', name=_sim_label,
                line=dict(color='#E25A53', width=2.5, dash='dash', shape='hv'),
            ))
            _stat_label = 'K-S D'
            _D_val = float(np.max(np.abs(med_cdf - obs_cdf_b)))
            fig_cdf.update_layout(**{
                **PLOTLY_THEME,
                'title': dict(
                    text=f'Cadence-aware CDF  (f_bin={_best_fb:.3f}, N_sets={result.get("n_sets", "?")})',
                    font=dict(size=14)),
                'xaxis_title': 'ΔRV (km/s)',
                'yaxis_title': 'Cumulative fraction',
                'height': 450,
                'legend': dict(x=0.55, y=0.15),
                'annotations': [dict(
                    x=0.98, y=0.95, xref='paper', yref='paper',
                    text=f'Binned {_stat_label} = {_D_val:.4f}<br>'
                         f'p = {_best_pval:.4f}',
                    showarrow=False,
                    font=dict(size=12, color=pal['annotation_font']),
                    bgcolor=pal['annotation_bg'],
                    borderpad=6, xanchor='right',
                )],
            })
            # Bin edges toggle
            _show_bins = st.checkbox('Show bin edges', key=f'{p}_show_bins')
            if _show_bins:
                # Detect adaptive bins: check if edges are unevenly spaced
                _edges_arr = np.asarray(_bin_edges, dtype=float)
                _is_adaptive = False
                if len(_edges_arr) > 2:
                    _diffs = np.diff(_edges_arr)
                    _is_adaptive = not np.allclose(_diffs, _diffs[0], rtol=0.01)
                for _ev in _edges_arr:
                    fig_cdf.add_vline(
                        x=float(_ev), line_dash='dot',
                        line_color='#DAA520' if _is_adaptive else '#888888',
                        line_width=0.8,
                        annotation_text='', opacity=0.6)
                # If adaptive, also show fixed edges for comparison
                if _is_adaptive:
                    for _fv in DEFAULT_DRV_BIN_EDGES:
                        if float(_fv) <= float(_edges_arr[-1]) * 1.1:
                            fig_cdf.add_vline(
                                x=float(_fv), line_dash='dot',
                                line_color='#888888', line_width=0.5,
                                opacity=0.3)
                    st.caption(
                        f'Gold lines: {len(_edges_arr)} adaptive bin edges. '
                        f'Grey lines: fixed 10 km/s bins (for comparison).')
                else:
                    st.caption(f'Grey lines: {len(_edges_arr)} fixed bin edges.')

            st.plotly_chart(fig_cdf, use_container_width=True, key=f'{p}_cdf')
            st.caption(
                f'Cadence-aware CDF comparison. Each of {result.get("n_sets", "?")} sets '
                f'contains exactly 25 simulated stars with observation cadences matching '
                f'the real sample. The shaded band shows the 68% confidence interval across sets.'
            )

        # ── CDF Sanity Check (5 random draws) ──────────────────────────────────
        _render_cdf_sanity_check(
            best_fbin=_best_fb,
            best_x=_best_x_val,
            sigma_single=float(result.get('best_sigma_single',
                                result.get('sigma_single', 15.0))),
            obs_delta_rv=obs_drv if obs_drv is not None else np.array([]),
            period_model='powerlaw' if _is_dsilva else 'langer2020',
            result=result,
            settings={},
            p_prefix=p,
        )

        # ── Methodology Expander ────────────────────────────────────────────────
        _tab_type = 'cadence_dsilva' if _is_dsilva else 'cadence_langer'
        _render_methodology_expander(_tab_type)



def _cadence_run_and_results(p: str, _is_dsilva: bool, _period_model: str,
                              fb_min, fb_max, fb_steps,
                              pi_min, pi_max, pi_steps,
                              n_sets, sigma_vals, _bin_cfg,
                              _sigma_meas, settings, sm) -> None:
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
        _drv_bin_width = float(st.session_state.get(f'{p}_drv_bin_width', 5.0))
        _drv_max = float(st.session_state.get(f'{p}_drv_max', 360.0))
        _cad_bin_edges = np.arange(0.0, _drv_max, _drv_bin_width)

    # ── Load saved results (full width) ──────────────────────────────────
    _cad_meta = _scan_result_metadata(_cad_tag)
    if _cad_meta is not None and len(_cad_meta) > 0:
        with st.expander(f'📂 Load saved result ({len(_cad_meta)})', expanded=True):
            _cad_disp = _cad_meta.drop(columns=['_path'], errors='ignore')
            _cad_sel = st.dataframe(
                _cad_disp, use_container_width=True,
                selection_mode='single-row', on_select='rerun',
                key=f'{p}_load_table',
            )
            _cad_sel_rows = _cad_sel.selection.rows if _cad_sel.selection else []
            if _cad_sel_rows:
                _cad_idx = _cad_sel_rows[0]
                _cad_sel_path = _cad_meta.iloc[_cad_idx]['_path']
                if st.session_state.get(f'{p}_loaded_path') != _cad_sel_path:
                    _cad_loaded = dict(np.load(_cad_sel_path, allow_pickle=True))
                    st.session_state[f'{p}_result'] = _cad_loaded
                    st.session_state[f'{p}_loaded_path'] = _cad_sel_path
                    st.toast(f"Loaded: {_cad_meta.iloc[_cad_idx]['File']}")
                    st.rerun()
                if st.button('🗑️ Delete this result', key=f'{p}_del_full'):
                    os.remove(_cad_sel_path)
                    _scan_result_metadata.clear()
                    st.session_state.pop(f'{p}_loaded_path', None)
                    st.session_state.pop(f'{p}_result', None)
                    st.toast(f"Deleted: {_cad_meta.iloc[_cad_idx]['File']}")
                    st.rerun()
    else:
        st.caption('No saved results yet.')

    # ── Partial results table ────────────────────────────────────────────
    _render_partial_table(p, _cad_tag, st)

    # Workers
    _n_proc = os.cpu_count() - 1

    # All 4 scoring methods are computed in a single run
    # Likelihood bin threshold (cadence tabs)
    from wr_bias_simulation import dsilva_likelihood_bins
    _lk_cols = st.columns([0.3, 0.7])
    _lk_threshold = _lk_cols[0].number_input(
        'Detection threshold (km/s)', value=45.5,
        min_value=1.0, max_value=200.0, step=0.5,
        key=f'{p}_lk_threshold',
        help='First bin boundary (Dsilva+2023 Sec 4.2)')
    _lk_bin_edges = dsilva_likelihood_bins(_lk_threshold)
    _lk_cols[1].caption(
        f'Likelihood bins: [0, {_lk_threshold:.1f}) '
        f'[{_lk_threshold:.1f}, 250) [250, 650) [650+) km/s')

    # Action buttons
    _a1, _a2, _a3, _a4 = st.columns(4)
    _run_btn = _a1.button('\u25b6\ufe0f Run', key=f'{p}_run_btn', type='primary')
    _save_clicked = _a2.button('\U0001f4be Save result', key=f'{p}_save_btn')
    _cancel_btn = _a3.button('\u23f9 Cancel', key=f'{p}_cancel_btn')
    _cancel_save_btn = _a4.button('\U0001f4be Cancel & Save', key=f'{p}_cancel_save_btn')

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
                0.5, 3.5,  # logP range defaults
                x_label='sig',
            )
            _cad_save_path = os.path.join(_RESULT_DIR, _cad_desc)
            os.makedirs(_RESULT_DIR, exist_ok=True)
            np.savez(_cad_save_path, **_cad_save_kw)
            cached_load_grid_result.clear()
            _scan_result_metadata.clear()
            st.toast(f'Saved: {_cad_desc}')
            st.success(f'Result saved as `{_cad_desc}`. Refresh the page to see it in the load table.')
        else:
            st.warning('No result to save. Run first.')

    if _cancel_btn and f'{p}_job' in st.session_state:
        st.session_state[f'{p}_job']['cancel'] = True
        st.session_state[f'{p}_job']['cancel_mode'] = 'discard'
    if _cancel_save_btn and f'{p}_job' in st.session_state:
        st.session_state[f'{p}_job']['cancel'] = True
        st.session_state[f'{p}_job']['cancel_mode'] = 'save'

    _cad_auto_resume = st.session_state.pop(f'{p}_auto_resume', False)
    _job_running = (f'{p}_job' in st.session_state
                    and st.session_state[f'{p}_job'].get('status') == 'running')
    if _run_btn and _job_running:
        st.warning('A simulation is already running in this tab. '
                   'Cancel it or wait for completion before starting a new run.')
    if (_run_btn or _cad_auto_resume) and not _job_running:
        _sh = settings_hash(settings)
        obs_drv, obs_det = cached_load_observed_delta_rvs(_sh)
        cad_list, cad_wts = cached_load_cadence(_sh)

        fbin_vals = np.linspace(fb_min, fb_max, fb_steps).tolist()
        if _is_dsilva:
            pi_v = np.linspace(pi_min, pi_max, pi_steps).tolist()
        else:
            pi_v = [0.0]

        # Build stable_cfg with full metadata (mirrors Dsilva pattern)
        _cad_stable_cfg = {
            'n_stars_sim':        len(cad_list),
            'sigma_measure':      float(_sigma_meas),
            'logP_min':           float(_bin_cfg.logP_min),
            'logP_max':           float(_bin_cfg.logP_max),
            'period_model':       _period_model,
            'e_model':            str(_bin_cfg.e_model),
            'e_max':              float(_bin_cfg.e_max),
            'mass_primary_model': str(_bin_cfg.mass_primary_model),
            'mass_primary_fixed': float(_bin_cfg.mass_primary_fixed),
            'q_model':            str(_bin_cfg.q_model),
            'q_min':              float(_bin_cfg.q_range[0]),
            'q_max':              float(_bin_cfg.q_range[1]),
            'q_flipped':          bool(getattr(_bin_cfg, 'q_flipped', False)),
            'primary_line':       settings.get('primary_line', 'C IV 5808-5812'),
            'threshold_dRV':      settings.get('classification', {}).get('threshold_dRV', 45.5),
            'sigma_factor':       settings.get('classification', {}).get('sigma_factor', 4.0),
            'adaptive_bins':      _use_adaptive,
            'n_sets':             n_sets,
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
            'cadence_list': cad_list,
            'cadence_weights': cad_wts,
            'obs_delta_rv': obs_drv,
            'n_proc': _n_proc,
            'fbin_vals': fbin_vals,
            'pi_vals': pi_v,
            'sigma_vals': sigma_vals,
            'n_sets': n_sets,
            'period_model': _period_model,
            'bin_cfg': _bin_cfg,
            'sigma_meas': _sigma_meas,
            'bin_edges': _cad_bin_edges,
            'adaptive_bins': _use_adaptive,
            'drv_bin_width': float(st.session_state.get(f'{p}_drv_bin_width', 5.0)),
            'drv_max': float(st.session_state.get(f'{p}_drv_max', 360.0)),
            'likelihood_bin_edges': _lk_bin_edges,
            'stable_cfg': _cad_stable_cfg,
            'save_params': {
                'mode': 'cadence_aware',
                'period_model': _period_model,
                'n_sets': n_sets,
                'adaptive_bins': _use_adaptive,
            },
        }

        # ── Check for partial resume ──────────────────────────────────────
        _cad_resume_path = st.session_state.pop(f'{p}_resume_from', None)
        if _cad_resume_path and os.path.exists(_cad_resume_path):
            try:
                _cad_ptl = np.load(_cad_resume_path, allow_pickle=True)
                params['prefilled_ks_p'] = np.asarray(_cad_ptl['ks_p'])
                params['prefilled_ks_D'] = np.asarray(_cad_ptl['ks_D'])
                _n_pre = int(np.count_nonzero(
                    ~np.isnan(params['prefilled_ks_p'])))
                _n_tot = params['prefilled_ks_p'].size
                # Save the original file path so cancel-save updates it
                params['resume_from_path'] = _cad_resume_path
                st.info(
                    f'\u267b\ufe0f Resuming from checkpoint '
                    f'({_n_pre}/{_n_tot} cells, '
                    f'{_n_pre/_n_tot*100:.0f}%).')
                _cad_ptl.close()
            except Exception:
                pass

        import threading
        t = threading.Thread(target=_run_cadence_bg, args=(job, params), daemon=True)
        t.start()
        st.rerun()



def _render_cadence_dsilva_tab(p: str, settings: dict, sm) -> None:
    """Render Cadence-Aware simulation tab (Dsilva / power-law period model)."""
    _is_dsilva = True
    _period_model = 'powerlaw'
    _sec = 'grid_cadence_dsilva'

    gcfg = settings.get(_sec, {})
    orb  = gcfg.get('orbital', {})
    simcfg = settings.get('simulation', {})

    # Pre-initialise session_state from settings (only on first visit)
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

    # ── LEFT: Parameters ─────────────────────────────────────────────────────
    with left_col:
        st.markdown('#### Cadence-Aware — Dsilva (power-law)')

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
            pi_min = _c4.number_input('π min', -5.0, 5.0,
                float(gcfg.get('pi_min', -3.0)), 0.1, key=f'{p}_pi_min',
                on_change=lambda: sm.save([_sec, 'pi_min'],
                                          value=st.session_state[f'{p}_pi_min']))
            pi_max = _c5.number_input('π max', -5.0, 5.0,
                float(gcfg.get('pi_max', 3.0)), 0.1, key=f'{p}_pi_max',
                on_change=lambda: sm.save([_sec, 'pi_max'],
                                          value=st.session_state[f'{p}_pi_max']))
            pi_steps = _c6.number_input('π steps', 5, 500,
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
            _cad_err_info = _render_error_model_selector(p, gcfg, sm, 'grid_cadence_dsilva')
            _sigma_meas = _cad_err_info['sigma_measure']

        with st.expander('Sigma scan', expanded=False):
            sigma_vals = _render_cadence_sigma_scan(p, _sec, sm, gcfg, settings)

    # ── RIGHT: Orbital params + action buttons + results ────────────────────
    with right_col:
        with st.expander('🔧 Orbital parameters (Kepler)', expanded=False):
            _orb_vals = _render_orbital_params_dsilva(p, _sec, sm, orb, gcfg)

        from wr_bias_simulation import BinaryParameterConfig
        _bin_cfg = BinaryParameterConfig(
            logP_min=_orb_vals['logP_min'], logP_max=_orb_vals['logP_max'],
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

        # Action buttons + run logic
        _cadence_run_and_results(
            p, _is_dsilva, _period_model,
            fb_min, fb_max, fb_steps,
            pi_min, pi_max, pi_steps,
            n_sets, sigma_vals, _bin_cfg, _sigma_meas,
            settings, sm)

    _render_cadence_results(p, _is_dsilva, _bin_cfg)

    # NOTE: Auto-refresh handled by global @st.fragment(run_every=3) at page bottom



def _render_cadence_langer_tab(p: str, settings: dict, sm) -> None:
    """Render Cadence-Aware simulation tab (Langer 2020 period model)."""
    _is_dsilva = False
    _period_model = 'langer2020'
    _sec = 'grid_cadence_langer'

    lg_cfg = settings.get(_sec, {})
    lg_pp  = lg_cfg.get('langer_period_params', {})
    simcfg = settings.get('simulation', {})

    # Pre-initialise session_state from settings (only on first visit)
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
        f'{p}_mass_fixed':  float(lg_cfg.get('mass_primary_fixed', 10.0)),
        f'{p}_q_min':       float(lg_cfg.get('q_range', [0.25, 1.65])[0]),
        f'{p}_q_max':       float(lg_cfg.get('q_range', [0.25, 1.65])[1]),
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

    # ── LEFT: Parameters ─────────────────────────────────────────────────────
    with left_col:
        st.markdown('#### Cadence-Aware — Langer 2020')

        with st.expander('Grid parameters', expanded=True):
            _c1, _c2, _c3 = st.columns(3)
            fb_min = _c1.number_input('f_bin min', 0.0, 1.0,
                float(lg_cfg.get('fbin_min', 0.0)), 0.01, key=f'{p}_fb_min',
                on_change=lambda: sm.save([_sec, 'fbin_min'],
                                          value=st.session_state[f'{p}_fb_min']))
            fb_max = _c2.number_input('f_bin max', 0.0, 1.0,
                float(lg_cfg.get('fbin_max', 1.0)), 0.01, key=f'{p}_fb_max',
                on_change=lambda: sm.save([_sec, 'fbin_max'],
                                          value=st.session_state[f'{p}_fb_max']))
            fb_steps = _c3.number_input('steps', 5, 500,
                int(lg_cfg.get('fbin_steps', 100)), 5, key=f'{p}_fb_steps',
                on_change=lambda: sm.save([_sec, 'fbin_steps'],
                                          value=st.session_state[f'{p}_fb_steps']))

        with st.expander('Cadence-aware settings', expanded=True):
            n_sets = st.number_input('N_sets', 100, 100000,
                int(lg_cfg.get('n_sets', 10000)), 100, key=f'{p}_n_sets',
                on_change=lambda: sm.save([_sec, 'n_sets'],
                                          value=st.session_state[f'{p}_n_sets']))
            _use_adaptive, _cad_bin_edges_l, drv_bin_width, drv_max = \
                _render_cadence_adaptive_bins(p, _sec, sm, lg_cfg, settings)
            _cl_err_info = _render_error_model_selector(p, lg_cfg, sm, 'grid_cadence_langer')
            _sigma_meas = _cl_err_info['sigma_measure']

        with st.expander('Sigma scan', expanded=False):
            sigma_vals = _render_cadence_sigma_scan(p, _sec, sm, lg_cfg, settings)

    # ── RIGHT: Orbital params + action buttons + results ──────────────────
    with right_col:
        with st.expander('🔧 Orbital parameters (Langer 2020)', expanded=False):
            _cl_orb = _render_orbital_params_langer(p, _sec, sm, lg_pp, lg_cfg)

            # Build BinaryParameterConfig
            from wr_bias_simulation import BinaryParameterConfig
            _period_params = {
                'dist_A': _cl_orb['dist_A'], 'mu_A': _cl_orb['mu_A'],
                'sigma_A': _cl_orb['sigma_A'],
                'dist_B': _cl_orb['dist_B'], 'mu_B': _cl_orb['mu_B'],
                'sigma_B': _cl_orb['sigma_B'],
                'weight_A': _cl_orb['weight_A'],
            }
            _bin_cfg = BinaryParameterConfig(
                logP_min=_cl_orb['logP_min'], logP_max=_cl_orb['logP_max'],
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

        # Action buttons + run logic
        pi_min, pi_max, pi_steps = 0.0, 0.0, 1
        _cadence_run_and_results(
            p, _is_dsilva, _period_model,
            fb_min, fb_max, fb_steps,
            pi_min, pi_max, pi_steps,
            n_sets, sigma_vals, _bin_cfg, _sigma_meas,
            settings, sm)

    _render_cadence_results(p, _is_dsilva, _bin_cfg)

    # NOTE: Auto-refresh handled by global @st.fragment(run_every=3) at page bottom




