"""bc.runners_cadence — Cadence-aware background simulation runner."""
from __future__ import annotations

import datetime as _dt
import json
import multiprocessing as mp
import os
import sys
import time
import traceback as _tb

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bc.helpers import (
    _RESULT_DIR, _HISTORY_PATH,
    _result_path, _stable_cfg_hash,
    _build_descriptive_filename, _build_partial_filename,
    _scan_result_metadata, _append_run_history,
    _fmt_eta, _best_point,
)

def _run_cadence_bg(job: dict, params: dict) -> None:
    """Run cadence-aware grid search in a background thread."""
    try:
        import multiprocessing as mp
        from wr_bias_simulation import (
            SimulationConfig, BinaryParameterConfig,
            _single_grid_task_cadence_aware, _init_worker,
            DEFAULT_DRV_BIN_EDGES, binned_cdf,
            compute_hdi68 as _hdi68,
        )

        cadence_list     = params['cadence_list']
        cadence_weights  = params['cadence_weights']
        obs_delta_rv     = params['obs_delta_rv']
        n_proc           = params['n_proc']
        fbin_vals        = params['fbin_vals']
        pi_vals          = params['pi_vals']
        sigma_vals       = params['sigma_vals']
        n_sets           = params['n_sets']
        period_model     = params['period_model']
        bin_cfg          = params['bin_cfg']
        sigma_meas       = params['sigma_meas']
        save_params      = params.get('save_params', {})
        stable_cfg       = params.get('stable_cfg', save_params)
        resume_from_path = params.get('resume_from_path')
        logPmax_scan_vals = np.asarray(
            params.get('logPmax_scan_vals', [bin_cfg.logP_max]))
        _scan_logPmax = len(logPmax_scan_vals) > 1

        fbin_grid = np.array(fbin_vals, dtype=float)
        pi_grid   = np.array(pi_vals, dtype=float)
        sigma_grid = np.array(sigma_vals, dtype=float)
        n_logPmax = len(logPmax_scan_vals)
        n_sig = len(sigma_grid)
        n_fb  = len(fbin_grid)
        n_pi  = len(pi_grid)

        def _make_cad_bin_cfg(logPmax_v):
            """Create BinaryParameterConfig with a specific logP_max."""
            from wr_bias_simulation import BinaryParameterConfig as _BPC
            return _BPC(
                logP_min=bin_cfg.logP_min, logP_max=float(logPmax_v),
                period_model=bin_cfg.period_model,
                langer_period_params=getattr(bin_cfg, 'langer_period_params', None),
                e_model=bin_cfg.e_model, e_max=bin_cfg.e_max,
                mass_primary_model=bin_cfg.mass_primary_model,
                mass_primary_fixed=bin_cfg.mass_primary_fixed,
                mass_primary_range=bin_cfg.mass_primary_range,
                q_model=bin_cfg.q_model, q_range=bin_cfg.q_range,
                langer_q_mu=getattr(bin_cfg, 'langer_q_mu', 0.5),
                langer_q_sigma=getattr(bin_cfg, 'langer_q_sigma', 0.1),
                q_flipped=getattr(bin_cfg, 'q_flipped', False),
            )

        # Build tasks for the first logPmax slice (rebuild per-slice in loop)
        def _build_tasks_for_slice(i_lp):
            cur_cfg = _make_cad_bin_cfg(logPmax_scan_vals[i_lp]) if _scan_logPmax else bin_cfg
            _tasks = []
            _idx = 1234 + i_lp * n_sig * n_fb * n_pi
            for sigma in sigma_grid:
                for fb in fbin_grid:
                    for pi_val in pi_grid:
                        _tasks.append((fb, pi_val, sigma, cur_cfg, period_model,
                                      _idx, n_sets))
                        _idx += 1
            return _tasks

        _cad_bin_edges = params.get('bin_edges', DEFAULT_DRV_BIN_EDGES)
        _initargs = (
            cadence_list, cadence_weights, obs_delta_rv,
            len(cadence_list), float(sigma_meas),
            6, 3650.0, None, 0.0, _cad_bin_edges,
            n_sets,   # n_sets_cvm
            params.get('likelihood_bin_edges'),  # coarse bins for likelihood
            params.get('error_model_single', 'fixed'),
            params.get('error_params_single', ()),
            params.get('error_model_binary', 'fixed'),
            params.get('error_params_binary', ()),
        )

        # Accumulation shape: 4-D when scanning logPmax, else 3-D
        if _scan_logPmax:
            _cad_shape = (n_logPmax, n_sig, n_fb, n_pi)
        else:
            _cad_shape = (n_sig, n_fb, n_pi)

        # Support resuming from partial checkpoint (only for non-logPmax scans)
        _pre_p = params.get('prefilled_ks_p')
        _pre_D = params.get('prefilled_ks_D')
        if (_pre_p is not None and _pre_D is not None
                and _pre_p.shape == _cad_shape and not _scan_logPmax):
            ks_p = _pre_p.copy()
            ks_D = _pre_D.copy()
        else:
            ks_D = np.full(_cad_shape, np.nan)
            ks_p = np.full(_cad_shape, np.nan)
        weighted_D = np.full(_cad_shape, np.nan)
        weighted_p = np.full(_cad_shape, np.nan)
        cvm_D      = np.full(_cad_shape, np.nan)
        cvm_p      = np.full(_cad_shape, np.nan)
        cvm_S_raw  = np.full(_cad_shape, np.nan)
        logL_raw   = np.full(_cad_shape, np.nan)

        # Track overall progress
        _total_original = n_logPmax * n_sig * n_fb * n_pi
        _pre_done = 0

        best_p = -1.0
        best_fb = 0.0
        best_median_cdf = None
        best_lo_cdf = None
        best_hi_cdf = None
        completed = 0

        import time as _time
        t_start = _time.time()

        def _save_partial_cadence():
            _partial_path = resume_from_path
            if not _partial_path:
                _p_tag = ('cadence_dsilva'
                          if period_model == 'powerlaw'
                          else 'cadence_langer')
                _x_vals = (pi_grid if period_model == 'powerlaw'
                           else sigma_grid)
                _x_lbl = ('pi' if period_model == 'powerlaw'
                          else 'sig')
                _partial_path = os.path.join(
                    _RESULT_DIR,
                    _build_partial_filename(
                        _p_tag, fbin_grid, _x_vals,
                        n_sets, sigma_grid,
                        bin_cfg.logP_min, bin_cfg.logP_max,
                        x_label=_x_lbl))
            os.makedirs(_RESULT_DIR, exist_ok=True)
            np.savez(
                _partial_path,
                ks_p=ks_p, ks_D=ks_D,
                weighted_D=weighted_D, weighted_p=weighted_p,
                cvm_D=cvm_D, cvm_p=cvm_p,
                cvm_S_raw=cvm_S_raw, logL_raw=logL_raw,
                scoring_version=np.array(2),
                fbin_grid=fbin_grid, pi_grid=pi_grid,
                sigma_grid=sigma_grid,
                logPmax_grid=logPmax_scan_vals,
                timestamp=_dt.datetime.now().isoformat(),
                progress_pct=(_pre_done + completed) / _total_original,
                rows_done=_pre_done + completed,
                total_rows=_total_original,
                period_model=period_model,
                drv_bin_width=float(params.get('drv_bin_width', 10.0)),
                drv_max=float(params.get('drv_max', 360.0)),
                adaptive_bins=bool(params.get('adaptive_bins', False)),
                settings=np.array(json.dumps(stable_cfg, default=str)),
                n_sets=np.array(n_sets),
            )
            job['partial_saved'] = True

        with mp.Pool(processes=int(n_proc),
                     initializer=_init_worker,
                     initargs=_initargs) as pool:

         for i_lp, logPmax_v in enumerate(logPmax_scan_vals):
            if job.get('cancel'):
                if job.get('cancel_mode') == 'save' and (_pre_done + completed) > 0:
                    _save_partial_cadence()
                job['status'] = 'cancelled'
                return

            slice_tasks = _build_tasks_for_slice(i_lp)

            # Filter pre-completed tasks (only for non-logPmax scans)
            if _pre_p is not None and not _scan_logPmax:
                slice_tasks = [t for t in slice_tasks
                               if (int(np.searchsorted(sigma_grid, t[2])) < n_sig
                                   and int(np.searchsorted(fbin_grid, t[0])) < n_fb
                                   and int(np.searchsorted(pi_grid, t[1])) < n_pi
                                   and np.isnan(ks_p[
                                       int(np.searchsorted(sigma_grid, t[2])),
                                       int(np.searchsorted(fbin_grid, t[0])),
                                       int(np.searchsorted(pi_grid, t[1]))]))]
                if i_lp == 0:
                    _pre_done = _total_original - len(slice_tasks)

            n_tasks = len(slice_tasks)

            for res in pool.imap_unordered(
                    _single_grid_task_cadence_aware, slice_tasks):
                if job.get('cancel'):
                    pool.terminate()
                    if (job.get('cancel_mode') == 'save'
                            and (_pre_done + completed) > 0):
                        _save_partial_cadence()
                    job['status'] = 'cancelled'
                    return
                (fb, pi_val, sigma,
                 _ks_D, _ks_p,
                 _w_D, _w_p,
                 _cvm_D, _cvm_p, _cvm_S,
                 _logL,
                 med_cdf, lo_cdf, hi_cdf) = res
                i_sig = int(np.searchsorted(sigma_grid, sigma))
                i_fb  = int(np.searchsorted(fbin_grid, fb))
                i_pi  = int(np.searchsorted(pi_grid, pi_val))
                _current_sig_idx = min(i_sig, n_sig - 1)
                if i_sig < n_sig and i_fb < n_fb and i_pi < n_pi:
                    if _scan_logPmax:
                        ks_D[i_lp, i_sig, i_fb, i_pi] = _ks_D
                        ks_p[i_lp, i_sig, i_fb, i_pi] = _ks_p
                        weighted_D[i_lp, i_sig, i_fb, i_pi] = _w_D
                        weighted_p[i_lp, i_sig, i_fb, i_pi] = _w_p
                        cvm_D[i_lp, i_sig, i_fb, i_pi] = _cvm_D
                        cvm_p[i_lp, i_sig, i_fb, i_pi] = _cvm_p
                        cvm_S_raw[i_lp, i_sig, i_fb, i_pi] = _cvm_S
                        logL_raw[i_lp, i_sig, i_fb, i_pi] = _logL
                    else:
                        ks_D[i_sig, i_fb, i_pi] = _ks_D
                        ks_p[i_sig, i_fb, i_pi] = _ks_p
                        weighted_D[i_sig, i_fb, i_pi] = _w_D
                        weighted_p[i_sig, i_fb, i_pi] = _w_p
                        cvm_D[i_sig, i_fb, i_pi] = _cvm_D
                        cvm_p[i_sig, i_fb, i_pi] = _cvm_p
                        cvm_S_raw[i_sig, i_fb, i_pi] = _cvm_S
                        logL_raw[i_sig, i_fb, i_pi] = _logL
                if _ks_p > best_p:
                    best_p = _ks_p
                    best_fb = fb
                    best_median_cdf = med_cdf
                    best_lo_cdf = lo_cdf
                    best_hi_cdf = hi_cdf
                completed += 1

                # ETA + percentage (overall, including pre-completed cells)
                _remaining_total = _total_original - _pre_done
                elapsed = _time.time() - t_start
                eta_str = ''
                if completed > 1 and completed < _remaining_total:
                    eta = elapsed / completed * (_remaining_total - completed)
                    eta_str = f'  —  ETA {_fmt_eta(eta)}'
                pct = (_pre_done + completed) / _total_original
                job['progress_pct'] = pct
                _lp_label = (f'logP_max={logPmax_v:.2f}, '
                             if _scan_logPmax else '')
                job['progress_text'] = (
                    f'{_lp_label}{pct*100:.1f}%  '
                    f'({_pre_done + completed}/{_total_original}){eta_str}')

                # Live heatmap update (throttled) — all 4 methods
                _now = _time.monotonic()
                _is_final = (completed == _remaining_total)
                _is_langer = (period_model == 'langer2020')
                if _now - job.get('_last_hm', 0) > 1.0 or _is_final:
                    job['_last_hm'] = _now

                    # Build per-method live heatmaps
                    _method_arrays = [
                        ('ks', ks_p, ks_D, 'K-S p'),
                        ('weighted', weighted_p, weighted_D, 'K-S weighted p'),
                        ('cvm', cvm_p, cvm_D, 'CvM p'),
                        ('likelihood', logL_raw, logL_raw, 'Likelihood'),
                    ]
                    _method_live = {}

                    if _is_langer and n_sig > 1:
                        # Langer with sigma scan: show f_bin × σ_single heatmap
                        for _mk, _mp, _md, _ml in _method_arrays:
                            if _scan_logPmax:
                                cur_p_2d = _mp[i_lp, :, :, 0].T
                                cur_D_2d = _md[i_lp, :, :, 0].T
                            else:
                                cur_p_2d = _mp[:, :, 0].T  # (n_fb, n_sig)
                                cur_D_2d = _md[:, :, 0].T
                            # Normalize likelihood logL to [0,1]
                            if _mk == 'likelihood':
                                _logL_max_v = np.nanmax(cur_p_2d)
                                if np.isfinite(_logL_max_v):
                                    cur_p_2d = np.exp(cur_p_2d - _logL_max_v)
                                else:
                                    cur_p_2d = np.zeros_like(cur_p_2d)
                                cur_D_2d = cur_p_2d
                            _method_live[_mk] = {
                                'p': np.where(np.isnan(cur_p_2d), 0.0, cur_p_2d).copy(),
                                'd': np.where(np.isnan(cur_D_2d), 0.0, cur_D_2d).copy(),
                                'fbin': fbin_grid.copy(),
                                'x': sigma_grid.copy(),
                                'x_label': 'σ_single (km/s)',
                                'x_name': 'σ',
                                'title': f'{_ml}  (cadence-aware, Langer 2020)',
                                'is_final': _is_final,
                            }
                        job['live_heatmaps'] = _method_live
                        # Build per-method status summary
                        _status_items = []
                        for _smk in ('ks', 'weighted', 'cvm', 'likelihood'):
                            if _smk in _method_live:
                                _sp = _method_live[_smk]['p']
                                _, _, _spv = _best_point(_sp, fbin_grid, sigma_grid)
                                _status_items.append(f'{_smk}: **{_spv:.4f}**')
                        _ks_disp = _method_live['ks']['p']
                        _bp_idx = np.unravel_index(
                            np.argmax(_ks_disp), _ks_disp.shape)
                        _bf = float(fbin_grid[_bp_idx[0]])
                        _bsig = float(sigma_grid[_bp_idx[1]])
                        job['live_status'] = (
                            f'best f_bin = **{_bf:.4f}**, '
                            f'σ_single = **{_bsig:.1f}** km/s  |  '
                            + '  |  '.join(_status_items))
                    else:
                        # Dsilva (or single-sigma Langer): show CURRENT sigma slice
                        _display_sig_idx = _current_sig_idx if n_sig > 1 else 0
                        _sig_label = f'σ={sigma_grid[_display_sig_idx]:.1f}'

                        for _mk, _mp, _md, _ml in _method_arrays:
                            if _scan_logPmax:
                                cur_p = _mp[i_lp, _display_sig_idx]
                                cur_d = _md[i_lp, _display_sig_idx]
                            else:
                                cur_p = _mp[_display_sig_idx]
                                cur_d = _md[_display_sig_idx]
                            # Normalize likelihood logL to [0,1]
                            # Use running global max across ALL sigma slices
                            if _mk == 'likelihood':
                                _logL_slice = cur_p.copy()
                                _slice_max = np.nanmax(_logL_slice)
                                if np.isfinite(_slice_max):
                                    _gk = '_logL_global_max'
                                    _prev = job.get(_gk, -np.inf)
                                    job[_gk] = max(_prev, _slice_max)
                                _global_max = job.get('_logL_global_max', np.nan)
                                if np.isfinite(_global_max):
                                    cur_p = np.exp(_logL_slice - _global_max)
                                else:
                                    cur_p = np.zeros_like(_logL_slice)
                                cur_d = cur_p
                            _method_live[_mk] = {
                                'p': np.where(np.isnan(cur_p), 0.0, cur_p).copy(),
                                'd': np.where(np.isnan(cur_d), 0.0, cur_d).copy(),
                                'fbin': fbin_grid.copy(),
                                'x': pi_grid.copy(),
                                'x_label': 'π  (period power-law index)',
                                'x_name': 'π',
                                'title': f'{_ml}  (cadence-aware, {_sig_label} km/s)',
                                'is_final': _is_final,
                            }
                        job['live_heatmaps'] = _method_live

                        # Live 1D σ graph (max KS p and max likelihood per sigma slice)
                        if n_sig > 1:
                            _live_sig_pvals = []
                            _live_sig_scores = []
                            _live_sig_likelihood = []
                            # Compute global logL max across ALL sigma slices
                            _logL_global = job.get('_logL_global_max', -np.inf)
                            for _ls in range(n_sig):
                                _lsL = logL_raw[_ls]
                                if np.any(~np.isnan(_lsL)):
                                    _sm = np.nanmax(_lsL)
                                    if np.isfinite(_sm):
                                        _logL_global = max(_logL_global, _sm)
                            if np.isfinite(_logL_global):
                                job['_logL_global_max'] = _logL_global
                            for _ls in range(n_sig):
                                _lsp = ks_p[_ls]
                                _lsd = ks_D[_ls]
                                _lsL = logL_raw[_ls]
                                if np.any(~np.isnan(_lsp)):
                                    _live_sig_pvals.append(float(np.nanmax(_lsp)))
                                else:
                                    _live_sig_pvals.append(0.0)
                                if np.any(~np.isnan(_lsd)):
                                    _live_sig_scores.append(float(np.nanmin(_lsd)))
                                else:
                                    _live_sig_scores.append(float('inf'))
                                # Max likelihood per sigma slice (globally normalized)
                                if np.any(~np.isnan(_lsL)) and np.isfinite(_logL_global):
                                    _live_sig_likelihood.append(
                                        float(np.nanmax(np.exp(_lsL - _logL_global))))
                                else:
                                    _live_sig_likelihood.append(0.0)
                            job['live_sigma_1d'] = {
                                'sigma_vals': sigma_grid.tolist(),
                                'max_pvals': _live_sig_pvals,
                                'min_scores': _live_sig_scores,
                                'max_likelihood': _live_sig_likelihood,
                            }

                        # Build per-method status items
                        _method_status_items = []
                        for _smk in ('ks', 'weighted', 'cvm', 'likelihood'):
                            if _smk in _method_live:
                                _sp = _method_live[_smk]['p']
                                _, _, _spv = _best_point(_sp, fbin_grid, pi_grid)
                                _method_status_items.append(f'{_smk}: **{_spv:.4f}**')
                        _ks_disp = _method_live['ks']['p']
                        _bp_idx = np.unravel_index(
                            np.argmax(_ks_disp), _ks_disp.shape)
                        _bf = float(fbin_grid[_bp_idx[0]])
                        _bpi = float(pi_grid[_bp_idx[1]])
                        _status_parts = [
                            f'Showing {_sig_label} km/s  →  '
                            f'f_bin = **{_bf:.4f}**, '
                            f'π = **{_bpi:.3f}**  |  '
                            + '  |  '.join(_method_status_items),
                        ]
                        if n_sig > 1:
                            _overall_best_sig = 0
                            _pmax_per_sig = [
                                float(np.nanmax(ks_p[s]))
                                if np.any(~np.isnan(ks_p[s]))
                                else -1.0
                                for s in range(n_sig)
                            ]
                            if any(v > -1.0 for v in _pmax_per_sig):
                                _overall_best_sig = int(np.argmax(_pmax_per_sig))
                            _obs = sigma_grid[_overall_best_sig]
                            _obp = _pmax_per_sig[_overall_best_sig] if _pmax_per_sig[_overall_best_sig] > -1 else 0
                            _status_parts.append(
                                f'Overall best: σ=**{_obs:.1f}** km/s, p=**{_obp:.4f}**')
                        job['live_status'] = '  |  '.join(_status_parts)

                        # Live 1D logPmax profile (cadence)
                        if _scan_logPmax and n_logPmax > 1:
                            _live_lp_pvals_c = []
                            for _lpi_c in range(n_logPmax):
                                if _lpi_c <= i_lp:
                                    _lp_sl = ks_p[_lpi_c]
                                    if np.any(~np.isnan(_lp_sl)):
                                        _live_lp_pvals_c.append(
                                            float(np.nanmax(_lp_sl)))
                                    else:
                                        _live_lp_pvals_c.append(0.0)
                                else:
                                    _live_lp_pvals_c.append(0.0)
                            job['live_logPmax_1d'] = {
                                'logPmax_vals': logPmax_scan_vals.tolist(),
                                'max_pvals': _live_lp_pvals_c,
                            }

        # Normalize logL → likelihood [0,1]
        _logL_max = np.nanmax(logL_raw)
        if np.isfinite(_logL_max):
            likelihood = np.exp(logL_raw - _logL_max)
        else:
            likelihood = np.zeros_like(logL_raw)

        # Build result with all 4 methods
        result = {
            'fbin_grid': fbin_grid,
            'pi_grid': pi_grid,
            'sigma_grid': sigma_grid,
            'logPmax_grid': logPmax_scan_vals,
            'ks_D': ks_D,
            'ks_p': ks_p,
            'weighted_D': weighted_D,
            'weighted_p': weighted_p,
            'cvm_D': cvm_D,
            'cvm_p': cvm_p,
            'cvm_S_raw': cvm_S_raw,
            'likelihood': likelihood,
            'logL_raw': logL_raw,
            'scoring_version': np.array(2),
            'obs_delta_rv': obs_delta_rv,
            'best_median_cdf': best_median_cdf,
            'best_lo_cdf': best_lo_cdf,
            'best_hi_cdf': best_hi_cdf,
            'n_sets': n_sets,
            'mode': 'cadence_aware',
            'bin_edges': _cad_bin_edges,
            'likelihood_bin_edges': params.get('likelihood_bin_edges'),
        }

        # HDI68 (p-value based) — marginalize over logPmax if 4-D
        _ks_for_hdi = ks_p
        if _scan_logPmax:
            _ks_for_hdi = np.nanmax(ks_p, axis=0)  # → (n_sig, n_fb, n_pi)
        if _ks_for_hdi.ndim == 2:
            # 2D: (n_fb, n_pi) — single sigma
            _post_fb = np.sum(_ks_for_hdi, axis=1)
            _post_pi = np.sum(_ks_for_hdi, axis=0)
            if _post_fb.sum() > 0:
                m_fb, lo_fb, hi_fb = _hdi68(fbin_grid, _post_fb)
                result.update(mode_fbin=m_fb, lo_fbin=lo_fb, hi_fbin=hi_fb)
            if _post_pi.sum() > 0:
                m_pi, lo_pi, hi_pi = _hdi68(pi_grid, _post_pi)
                result.update(mode_pi=m_pi, lo_pi=lo_pi, hi_pi=hi_pi)
        elif _ks_for_hdi.ndim == 3:
            # 3D: (n_sig, n_fb, n_pi)
            _post_fb = np.sum(_ks_for_hdi, axis=(0, 2))
            _post_pi = np.sum(_ks_for_hdi, axis=(0, 1))
            _post_sig = np.sum(_ks_for_hdi, axis=(1, 2))
            if _post_fb.sum() > 0:
                m_fb, lo_fb, hi_fb = _hdi68(fbin_grid, _post_fb)
                result.update(mode_fbin=m_fb, lo_fbin=lo_fb, hi_fbin=hi_fb)
            if _post_pi.sum() > 0:
                m_pi, lo_pi, hi_pi = _hdi68(pi_grid, _post_pi)
                result.update(mode_pi=m_pi, lo_pi=lo_pi, hi_pi=hi_pi)
            if _post_sig.sum() > 0:
                m_sig, lo_sig, hi_sig = _hdi68(sigma_grid, _post_sig)
                result.update(mode_sigma=m_sig, lo_sigma=lo_sig, hi_sigma=hi_sig)

        # HDI68 (likelihood-based — Dsilva+2023 proper posterior)
        _has_L = np.any(np.isfinite(logL_raw) & (logL_raw > -1e30))
        if _has_L:
            _L_for_hdi = likelihood
            if _scan_logPmax:
                _L_for_hdi = np.nanmax(likelihood, axis=0)
            if _L_for_hdi.ndim == 2:
                _Lpost_fb = np.sum(_L_for_hdi, axis=1)
                _Lpost_pi = np.sum(_L_for_hdi, axis=0)
                if _Lpost_fb.sum() > 0:
                    mL_fb, loL_fb, hiL_fb = _hdi68(fbin_grid, _Lpost_fb)
                    result.update(mode_fbin_L=mL_fb, lo_fbin_L=loL_fb, hi_fbin_L=hiL_fb)
                if _Lpost_pi.sum() > 0:
                    mL_pi, loL_pi, hiL_pi = _hdi68(pi_grid, _Lpost_pi)
                    result.update(mode_pi_L=mL_pi, lo_pi_L=loL_pi, hi_pi_L=hiL_pi)
            elif _L_for_hdi.ndim == 3:
                _Lpost_fb = np.sum(_L_for_hdi, axis=(0, 2))
                _Lpost_pi = np.sum(_L_for_hdi, axis=(0, 1))
                _Lpost_sig = np.sum(_L_for_hdi, axis=(1, 2))
                if _Lpost_fb.sum() > 0:
                    mL_fb, loL_fb, hiL_fb = _hdi68(fbin_grid, _Lpost_fb)
                    result.update(mode_fbin_L=mL_fb, lo_fbin_L=loL_fb, hi_fbin_L=hiL_fb)
                if _Lpost_pi.sum() > 0:
                    mL_pi, loL_pi, hiL_pi = _hdi68(pi_grid, _Lpost_pi)
                    result.update(mode_pi_L=mL_pi, lo_pi_L=loL_pi, hi_pi_L=hiL_pi)
                if _Lpost_sig.sum() > 0:
                    mL_sig, loL_sig, hiL_sig = _hdi68(sigma_grid, _Lpost_sig)
                    result.update(mode_sigma_L=mL_sig, lo_sigma_L=loL_sig, hi_sigma_L=hiL_sig)

        # Save result
        import datetime
        result['timestamp'] = datetime.datetime.now().isoformat()
        result['settings'] = json.dumps(stable_cfg, default=str)
        result['n_sets'] = n_sets

        _cad_model = 'cadence_dsilva' if period_model == 'powerlaw' else 'cadence_langer'
        _desc = (f"{_cad_model}_fb{fbin_grid[0]:.1f}-{fbin_grid[-1]:.1f}x{n_fb}"
                 f"_pi{pi_grid[0]:.1f}-{pi_grid[-1]:.1f}x{n_pi}"
                 f"_N{n_sets}"
                 f"_sig{sigma_grid[0]:.1f}")
        if n_sig > 1:
            _desc += f"-{sigma_grid[-1]:.1f}x{n_sig}"
        if _scan_logPmax:
            _desc += (f"_logP{logPmax_scan_vals[0]:.2f}"
                      f"-{logPmax_scan_vals[-1]:.2f}x{n_logPmax}")
        _ts = datetime.datetime.now().strftime('%y%m%d-%H%M')
        _fname = f"{_desc}_{_ts}.npz"
        _save_path = os.path.join(_RESULT_DIR, _fname)
        os.makedirs(_RESULT_DIR, exist_ok=True)

        _save_dict = {}
        for k, v in result.items():
            if isinstance(v, np.ndarray):
                _save_dict[k] = v
            else:
                _save_dict[k] = np.array(v, dtype=object)
        np.savez_compressed(_save_path, **_save_dict)
        result['save_path'] = _save_path
        _scan_result_metadata.clear()

        # Clean up partial checkpoint
        _p_tag = 'cadence_dsilva' if period_model == 'powerlaw' else 'cadence_langer'
        _partial_cleanup = os.path.join(_RESULT_DIR, f'{_p_tag}_result.npz.partial')
        if os.path.exists(_partial_cleanup):
            os.remove(_partial_cleanup)

        job['result'] = result
        job['status'] = 'done'

    except Exception as exc:
        import traceback
        job['error'] = traceback.format_exc()
        job['status'] = 'error'
