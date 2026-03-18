"""bc.runners — Background simulation runners for bias correction."""
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

def _run_dsilva_bg(job: dict, params: dict) -> None:
    """Run Dsilva grid search in a background thread.

    Writes progress to *job* dict (shared with main Streamlit thread).
    On completion sets ``job['status'] = 'done'`` and ``job['result']``.
    """
    try:
        from wr_bias_simulation import (
            BinaryParameterConfig, _single_grid_task_lite, _init_worker,
        )
        cadence_list     = params['cadence_list']
        cadence_weights  = params['cadence_weights']
        obs_delta_rv     = params['obs_delta_rv']
        n_stars_sim      = params['n_stars_sim']
        sigma_meas       = params['sigma_meas']
        n_proc           = params['n_proc']
        fbin_vals        = params['fbin_vals']
        pi_vals          = params['pi_vals']
        sigma_vals       = params['sigma_vals']
        logPmax_scan_vals = params['logPmax_scan_vals']
        stable_cfg       = params['stable_cfg']
        save_params      = params['save_params']
        bcfg             = params['bin_cfg_params']
        n_sets_cvm       = params.get('n_sets_cvm', 1000)
        _lk_bin_edges    = params.get('likelihood_bin_edges')

        _scan_logPmax = len(logPmax_scan_vals) > 1

        def _make_bin_cfg(logPmax_v):
            return BinaryParameterConfig(
                logP_min=bcfg['logP_min'], logP_max=float(logPmax_v),
                period_model='powerlaw',
                e_model=bcfg['e_model'], e_max=bcfg['e_max'],
                mass_primary_model=bcfg['mass_model'],
                mass_primary_fixed=bcfg['mass_fixed'],
                mass_primary_range=bcfg['mass_range'],
                q_model=bcfg['q_model'], q_range=bcfg['q_range'],
                langer_q_mu=bcfg['langer_q_mu'],
                langer_q_sigma=bcfg['langer_q_sig'],
            )

        n_logPmax = len(logPmax_scan_vals)
        n_sigma   = len(sigma_vals)
        n_fbin    = len(fbin_vals)
        n_pi      = len(pi_vals)

        # Accumulation arrays for all 4 scoring methods
        _shape = (n_logPmax, n_sigma, n_fbin, n_pi)
        # Support resuming from partial checkpoint (uses ks_p for completeness check)
        _prefilled_p = params.get('prefilled_ks_p')
        _prefilled_D = params.get('prefilled_ks_D')
        if (_prefilled_p is not None and _prefilled_D is not None
                and _prefilled_p.shape == _shape):
            acc_ks_p = _prefilled_p.copy()
            acc_ks_D = _prefilled_D.copy()
        else:
            acc_ks_p = np.full(_shape, np.nan)
            acc_ks_D = np.full(_shape, np.nan)
        acc_weighted_D = np.full(_shape, np.nan)
        acc_weighted_p = np.full(_shape, np.nan)
        acc_cvm_D      = np.full(_shape, np.nan)
        acc_cvm_p      = np.full(_shape, np.nan)
        acc_cvm_S_raw  = np.full(_shape, np.nan)
        acc_logL_raw   = np.full(_shape, np.nan)

        n_rows_total = n_logPmax * n_sigma * n_fbin
        # Count already-completed rows (from partial resume)
        _pre_done = 0
        for i_lp in range(n_logPmax):
            for i_s in range(n_sigma):
                for gj in range(n_fbin):
                    if not np.any(np.isnan(acc_ks_p[i_lp, i_s, gj, :])):
                        _pre_done += 1
        rows_done = _pre_done
        t_start      = time.time()

        if n_rows_total == 0:
            job['progress_pct']  = 1.0
            job['progress_text'] = 'Nothing to compute.'
        else:
            pi_to_idx = {round(float(pv), 10): i for i, pv in enumerate(pi_vals)}
            fbin_to_global = {round(float(fbin_vals[gj]), 10): gj
                              for gj in range(n_fbin)}
            seed_base        = 1234
            last_render_time = 0.0
            outer_last_render = 0.0
            outer_max_p = np.full((n_logPmax, n_sigma), np.nan)

            with mp.Pool(
                processes=int(n_proc),
                initializer=_init_worker,
                initargs=(cadence_list, cadence_weights, obs_delta_rv,
                          int(n_stars_sim), float(sigma_meas),
                          6, 3650.0, None, 0.0, None,
                          n_sets_cvm,
                          _lk_bin_edges,
                          params.get('error_model_single', 'fixed'),
                          params.get('error_params_single', ()),
                          params.get('error_model_binary', 'fixed'),
                          params.get('error_params_binary', ())),
            ) as pool:
                def _save_partial_dsilva():
                    """Save accumulated results as a partial checkpoint."""
                    os.makedirs(_RESULT_DIR, exist_ok=True)
                    _pf = os.path.join(_RESULT_DIR,
                                       _build_partial_filename(
                                           'dsilva', fbin_vals, pi_vals,
                                           n_stars_sim, sigma_vals,
                                           bcfg['logP_min'],
                                           float(logPmax_scan_vals[-1]),
                                           x_label='pi'))
                    np.savez(
                        _pf,
                        fbin_grid=fbin_vals, pi_grid=pi_vals,
                        sigma_grid=sigma_vals,
                        logPmax_grid=logPmax_scan_vals,
                        ks_p=acc_ks_p, ks_D=acc_ks_D,
                        weighted_D=acc_weighted_D, weighted_p=acc_weighted_p,
                        cvm_D=acc_cvm_D, cvm_p=acc_cvm_p,
                        cvm_S_raw=acc_cvm_S_raw, logL_raw=acc_logL_raw,
                        scoring_version=np.array(2),
                        timestamp=np.array(
                            _dt.datetime.now().isoformat()),
                        progress_pct=np.array(
                            rows_done / max(n_rows_total, 1)),
                        rows_done=np.array(rows_done),
                        total_rows=np.array(n_rows_total),
                        settings=np.array(json.dumps(stable_cfg,
                                                     default=str)),
                    )
                    job['partial_saved'] = True

                for i_lp, logPmax_v in enumerate(logPmax_scan_vals):
                    if job.get('cancel'):
                        if job.get('cancel_mode') == 'save' and rows_done > 0:
                            _save_partial_dsilva()
                        job['status'] = 'cancelled'
                        return
                    cur_bin_cfg = _make_bin_cfg(logPmax_v)

                    for i_sigma, sigma in enumerate(sigma_vals):
                        if job.get('cancel'):
                            if job.get('cancel_mode') == 'save' and rows_done > 0:
                                _save_partial_dsilva()
                            job['status'] = 'cancelled'
                            return
                        tasks = []
                        _skip_fbin = set()
                        for gj in range(n_fbin):
                            # Skip fbin rows already complete (from partial resume)
                            if not np.any(np.isnan(
                                    acc_ks_p[i_lp, i_sigma, gj, :])):
                                _skip_fbin.add(gj)
                                continue
                            for i_pi, pv in enumerate(pi_vals):
                                tasks.append((
                                    float(fbin_vals[gj]), float(pv),
                                    float(sigma), cur_bin_cfg,
                                    'powerlaw', seed_base,
                                ))
                                seed_base += 1

                        completed_per_fbin = {gj: 0 for gj in range(n_fbin)
                                              if gj not in _skip_fbin}

                        if not tasks:
                            # All fbin rows already complete for this slice
                            continue

                        for res in pool.imap_unordered(
                                _single_grid_task_lite, tasks,
                                chunksize=max(1, n_pi // 4)):
                            (fb, pi_ret, sigma_ret,
                             _ks_D, _ks_p,
                             _w_D, _w_p,
                             _cvm_D, _cvm_p, _cvm_S,
                             _logL) = res
                            gj   = fbin_to_global[round(fb, 10)]
                            i_pi = pi_to_idx[round(pi_ret, 10)]
                            acc_ks_p[i_lp, i_sigma, gj, i_pi] = _ks_p
                            acc_ks_D[i_lp, i_sigma, gj, i_pi] = _ks_D
                            acc_weighted_D[i_lp, i_sigma, gj, i_pi] = _w_D
                            acc_weighted_p[i_lp, i_sigma, gj, i_pi] = _w_p
                            acc_cvm_D[i_lp, i_sigma, gj, i_pi] = _cvm_D
                            acc_cvm_p[i_lp, i_sigma, gj, i_pi] = _cvm_p
                            acc_cvm_S_raw[i_lp, i_sigma, gj, i_pi] = _cvm_S
                            acc_logL_raw[i_lp, i_sigma, gj, i_pi] = _logL
                            completed_per_fbin[gj] += 1

                            if completed_per_fbin[gj] == n_pi:
                                rows_done += 1
                                elapsed = time.time() - t_start
                                eta_str = ''
                                if 1 < rows_done < n_rows_total:
                                    eta = elapsed / rows_done * (n_rows_total - rows_done)
                                    eta_str = f'  —  ETA {_fmt_eta(eta)}'
                                _lp_label = (f'logP_max={logPmax_v:.2f}, '
                                             if _scan_logPmax else '')
                                job['progress_pct']  = rows_done / n_rows_total
                                job['progress_text'] = (
                                    f'{_lp_label}σ={sigma:.1f} km/s, '
                                    f'row {rows_done}/{n_rows_total}{eta_str}')

                                now = time.time()
                                _is_final = (rows_done == n_rows_total)
                                if now - last_render_time > 1.0 or _is_final:
                                    last_render_time = now
                                    _lp_title = (f', logP_max={logPmax_v:.2f}'
                                                 if _scan_logPmax else '')
                                    _sig_title = f'σ={sigma:.1f} km/s{_lp_title}'
                                    _method_live = {}
                                    for _mk, _mp, _md, _ml in [
                                        ('ks', acc_ks_p, acc_ks_D, 'K-S p'),
                                        ('weighted', acc_weighted_p, acc_weighted_D, 'K-S weighted p'),
                                        ('cvm', acc_cvm_p, acc_cvm_D, 'CvM p'),
                                        ('likelihood', acc_logL_raw, acc_logL_raw, 'Likelihood'),
                                    ]:
                                        _cur = _mp[i_lp, i_sigma]
                                        _cur_d = _md[i_lp, i_sigma]
                                        # Normalize likelihood logL to [0,1]
                                        # Use running global max across ALL sigma slices
                                        # so likelihood values are comparable across σ_single
                                        if _mk == 'likelihood':
                                            _logL_slice = _cur.copy()
                                            _slice_max = np.nanmax(_logL_slice)
                                            if np.isfinite(_slice_max):
                                                _gk = '_logL_global_max'
                                                _prev = job.get(_gk, -np.inf)
                                                job[_gk] = max(_prev, _slice_max)
                                            _global_max = job.get('_logL_global_max', np.nan)
                                            if np.isfinite(_global_max):
                                                _cur = np.exp(_logL_slice - _global_max)
                                            else:
                                                _cur = np.zeros_like(_logL_slice)
                                            _cur_d = _cur  # no separate D for likelihood
                                        _method_live[_mk] = {
                                            'p': np.where(np.isnan(_cur), 0.0, _cur).copy(),
                                            'd': np.where(np.isnan(_cur_d), 0.0, _cur_d).copy(),
                                            'fbin': fbin_vals.copy(),
                                            'x': pi_vals.copy(),
                                            'title': f'{_ml}  ({_sig_title})',
                                            'is_final': _is_final,
                                        }
                                    job['live_heatmaps'] = _method_live
                                    # Build per-method status summary
                                    _status_items = []
                                    for _smk in ('ks', 'weighted', 'cvm', 'likelihood'):
                                        if _smk in _method_live:
                                            _sp = _method_live[_smk]['p']
                                            _, _, _spv = _best_point(_sp, fbin_vals, pi_vals)
                                            _status_items.append(f'{_smk}: **{_spv:.4f}**')
                                    _ks_disp = _method_live['ks']['p']
                                    bf, bp, bpv = _best_point(
                                        _ks_disp, fbin_vals, pi_vals)
                                    job['live_status'] = (
                                        f'{_lp_label}σ = **{sigma:.1f}** km/s  →  '
                                        f'best f_bin = **{bf:.4f}**, '
                                        f'π = **{bp:.3f}**  |  '
                                        + '  |  '.join(_status_items))

                        # Update outer max-p (use KS p-value as primary)
                        _slice_p = acc_ks_p[i_lp, i_sigma]
                        outer_max_p[i_lp, i_sigma] = float(np.nanmax(_slice_p))
                        if _scan_logPmax:
                            now2 = time.time()
                            _outer_final = (rows_done == n_rows_total)
                            if now2 - outer_last_render > 0.8 or _outer_final:
                                outer_last_render = now2
                                _omp = np.where(np.isnan(outer_max_p), 0.0,
                                                outer_max_p)
                                job['live_outer_heatmap'] = {
                                    'p': _omp.copy(),
                                    'y': logPmax_scan_vals.copy(),
                                    'x': sigma_vals.copy(),
                                    'is_final': _outer_final,
                                }

                    # Checkpoint after each logP_max slice
                    if rows_done > 0:
                        os.makedirs(_RESULT_DIR, exist_ok=True)
                        np.savez(
                            _result_path('dsilva') + '.partial',
                            fbin_grid=fbin_vals, pi_grid=pi_vals,
                            sigma_grid=sigma_vals,
                            logPmax_grid=logPmax_scan_vals,
                            ks_p=acc_ks_p, ks_D=acc_ks_D,
                            weighted_D=acc_weighted_D, weighted_p=acc_weighted_p,
                            cvm_D=acc_cvm_D, cvm_p=acc_cvm_p,
                            cvm_S_raw=acc_cvm_S_raw, logL_raw=acc_logL_raw,
                            scoring_version=np.array(2),
                            config_hash=_stable_cfg_hash(stable_cfg),
                            settings=np.array(json.dumps(stable_cfg)),
                            timestamp=np.array(_dt.datetime.now().isoformat()),
                        )

        elapsed_total = time.time() - t_start
        job['elapsed_total'] = elapsed_total

        # ── Save combined result ─────────────────────────────────────────
        os.makedirs(_RESULT_DIR, exist_ok=True)
        sp = save_params
        chash = _stable_cfg_hash({
            **stable_cfg,
            'fbin_min': sp['fbin_min'], 'fbin_max': sp['fbin_max'],
            'fbin_steps': sp['fbin_steps'],
            'pi_min': sp['pi_min'], 'pi_max': sp['pi_max'],
            'pi_steps': sp['pi_steps'],
            'sigma_vals': sigma_vals.tolist(),
            'logPmax_vals': logPmax_scan_vals.tolist(),
        })
        # Normalize logL → likelihood [0,1]
        _logL_max = np.nanmax(acc_logL_raw)
        if np.isfinite(_logL_max):
            acc_likelihood = np.exp(acc_logL_raw - _logL_max)
        else:
            acc_likelihood = np.zeros_like(acc_logL_raw)

        full_result = {
            'fbin_grid': fbin_vals, 'pi_grid': pi_vals,
            'sigma_grid': sigma_vals, 'logPmax_grid': logPmax_scan_vals,
            'ks_p': acc_ks_p, 'ks_D': acc_ks_D,
            'weighted_D': acc_weighted_D, 'weighted_p': acc_weighted_p,
            'cvm_D': acc_cvm_D, 'cvm_p': acc_cvm_p,
            'cvm_S_raw': acc_cvm_S_raw,
            'likelihood': acc_likelihood, 'logL_raw': acc_logL_raw,
            'scoring_version': np.array(2),
            'obs_delta_rv': obs_delta_rv,
            'likelihood_bin_edges': params.get('likelihood_bin_edges'),
        }

        # ── Compute HDI68 posterior errors and save alongside ────────────
        from wr_bias_simulation import compute_hdi68 as _hdi68
        _ks4 = acc_ks_p  # [logPmax, sigma, fbin, pi]
        _ks3 = np.sum(_ks4, axis=0)  # [sigma, fbin, pi]
        _post_fbin = np.sum(_ks3, axis=(0, 2))
        _post_pi   = np.sum(_ks3, axis=(0, 1))
        _m_fb, _lo_fb, _hi_fb = _hdi68(fbin_vals, _post_fbin)
        _m_pi, _lo_pi, _hi_pi = _hdi68(pi_vals, _post_pi)
        if sigma_vals.size > 1:
            _post_sig = np.sum(_ks3, axis=(1, 2))
            _m_sig, _lo_sig, _hi_sig = _hdi68(sigma_vals, _post_sig)
        else:
            _m_sig = float(sigma_vals[0]); _lo_sig = _hi_sig = _m_sig
        if logPmax_scan_vals.size > 1:
            _post_lp = np.sum(_ks4, axis=(1, 2, 3))
            _m_lp, _lo_lp, _hi_lp = _hdi68(logPmax_scan_vals, _post_lp)
        else:
            _m_lp = float(logPmax_scan_vals[0]); _lo_lp = _hi_lp = _m_lp
        _hdi_arrays = dict(
            mode_fbin=_m_fb, lo_fbin=_lo_fb, hi_fbin=_hi_fb,
            mode_pi=_m_pi, lo_pi=_lo_pi, hi_pi=_hi_pi,
            mode_sigma=_m_sig, lo_sigma=_lo_sig, hi_sigma=_hi_sig,
            mode_logPmax=_m_lp, lo_logPmax=_lo_lp, hi_logPmax=_hi_lp,
        )
        full_result.update(_hdi_arrays)

        _save_kwargs = dict(
            **full_result,
            config_hash=chash,
            settings=np.array(json.dumps(stable_cfg)),
            obs_delta_rv=obs_delta_rv,
            timestamp=np.array(_dt.datetime.now().isoformat()),
        )
        np.savez(_result_path('dsilva'), **_save_kwargs)
        _desc_name = _build_descriptive_filename(
            'dsilva',
            sp['fbin_min'], sp['fbin_max'], sp['fbin_steps'],
            sp['pi_min'], sp['pi_max'], sp['pi_steps'],
            int(n_stars_sim), sigma_vals,
            bcfg['logP_min'], sp['logP_max'],
            x_label='pi',
        )
        _desc_path = os.path.join(_RESULT_DIR, _desc_name)
        np.savez(_desc_path, **_save_kwargs)
        _scan_result_metadata.clear()
        _partial = _result_path('dsilva') + '.partial.npz'
        if os.path.exists(_partial):
            os.remove(_partial)
        _append_run_history({
            'timestamp': _dt.datetime.now().isoformat(),
            'model': 'dsilva_powerlaw', 'config_hash': chash,
            'config': stable_cfg, 'elapsed_s': round(elapsed_total, 1),
            'result_file': _result_path('dsilva'),
            'descriptive_file': _desc_path,
        })

        job['result']       = full_result
        job['desc_name']    = _desc_name
        job['n_rows_total'] = n_rows_total
        job['status']       = 'done'

    except Exception:
        job['error']  = _tb.format_exc()
        job['status'] = 'error'


def _run_langer_bg(job: dict, params: dict) -> None:
    """Run Langer 2020 grid search in a background thread."""
    try:
        from wr_bias_simulation import (
            BinaryParameterConfig, _single_grid_task_lite, _init_worker,
        )
        cadence_list    = params['cadence_list']
        cadence_weights = params['cadence_weights']
        obs_delta_rv    = params['obs_delta_rv']
        n_stars         = params['n_stars']
        sigma_meas      = params['sigma_meas']
        n_proc          = params['n_proc']
        fbin_vals       = params['fbin_vals']
        sigma_vals      = params['sigma_vals']
        bin_cfg         = params['bin_cfg']
        stable_cfg      = params['stable_cfg']
        save_params     = params['save_params']
        n_sets_cvm      = params.get('n_sets_cvm', 1000)
        _lg_lk_bin_edges = params.get('likelihood_bin_edges')
        # Pre-filled arrays (from partial cache reuse)
        acc_ks_p        = params['acc_ks_p']
        acc_ks_D        = params['acc_ks_D']
        missing_fbin_idx = params['missing_fbin_idx']
        # Additional method arrays
        _lg_shape = acc_ks_p.shape  # (n_fbin, n_sigma)
        acc_weighted_D = np.full(_lg_shape, np.nan)
        acc_weighted_p = np.full(_lg_shape, np.nan)
        acc_cvm_D      = np.full(_lg_shape, np.nan)
        acc_cvm_p      = np.full(_lg_shape, np.nan)
        acc_cvm_S_raw  = np.full(_lg_shape, np.nan)
        acc_logL_raw   = np.full(_lg_shape, np.nan)

        n_fbin  = len(fbin_vals)
        n_sigma = len(sigma_vals)
        n_cells_total = len(missing_fbin_idx) * n_sigma
        cells_done = 0
        t_start = time.time()

        if n_cells_total == 0:
            job['progress_pct']  = 1.0
            job['progress_text'] = 'All rows reused from cache.'
        else:
            fbin_to_global = {round(float(fbin_vals[gj]), 10): gj
                              for gj in missing_fbin_idx}
            sigma_to_idx = {round(float(sv), 10): i
                            for i, sv in enumerate(sigma_vals)}
            seed_base    = 5678
            last_render  = 0.0

            tasks = []
            for gj in missing_fbin_idx:
                for i_s, sv in enumerate(sigma_vals):
                    tasks.append((
                        float(fbin_vals[gj]), 0.0, float(sv),
                        bin_cfg, 'langer2020', seed_base,
                    ))
                    seed_base += 1

            with mp.Pool(
                processes=int(n_proc),
                initializer=_init_worker,
                initargs=(cadence_list, cadence_weights, obs_delta_rv,
                          int(n_stars), float(sigma_meas),
                          6, 3650.0, None, 0.0, None,
                          n_sets_cvm,
                          _lg_lk_bin_edges,
                          params.get('error_model_single', 'fixed'),
                          params.get('error_params_single', ()),
                          params.get('error_model_binary', 'fixed'),
                          params.get('error_params_binary', ())),
            ) as pool:
                def _save_partial_langer():
                    """Save accumulated Langer results as partial."""
                    os.makedirs(_RESULT_DIR, exist_ok=True)
                    _pf = os.path.join(_RESULT_DIR,
                                       _build_partial_filename(
                                           'langer', fbin_vals, sigma_vals,
                                           n_stars, sigma_vals,
                                           stable_cfg.get('logP_min', 0.5),
                                           stable_cfg.get('logP_max', 3.5),
                                           x_label='sig'))
                    np.savez(
                        _pf,
                        fbin_grid=fbin_vals, sigma_grid=sigma_vals,
                        ks_p=acc_ks_p, ks_D=acc_ks_D,
                        weighted_D=acc_weighted_D, weighted_p=acc_weighted_p,
                        cvm_D=acc_cvm_D, cvm_p=acc_cvm_p,
                        cvm_S_raw=acc_cvm_S_raw, logL_raw=acc_logL_raw,
                        scoring_version=np.array(2),
                        config_hash=_stable_cfg_hash(stable_cfg),
                        settings=np.array(json.dumps(stable_cfg,
                                                     default=str)),
                        timestamp=np.array(
                            _dt.datetime.now().isoformat()),
                        progress_pct=np.array(
                            cells_done / max(n_cells_total, 1)),
                        rows_done=np.array(cells_done),
                        total_rows=np.array(n_cells_total),
                    )
                    job['partial_saved'] = True

                for res in pool.imap_unordered(
                        _single_grid_task_lite, tasks,
                        chunksize=max(1, n_sigma // 4)):
                    if job.get('cancel'):
                        if job.get('cancel_mode') == 'save' and cells_done > 0:
                            _save_partial_langer()
                        job['status'] = 'cancelled'
                        return
                    (fb, _pi_ret, sigma_ret,
                     _ks_D, _ks_p,
                     _w_D, _w_p,
                     _cvm_D, _cvm_p, _cvm_S,
                     _logL) = res
                    gj  = fbin_to_global[round(fb, 10)]
                    i_s = sigma_to_idx[round(sigma_ret, 10)]
                    acc_ks_p[gj, i_s] = _ks_p
                    acc_ks_D[gj, i_s] = _ks_D
                    acc_weighted_D[gj, i_s] = _w_D
                    acc_weighted_p[gj, i_s] = _w_p
                    acc_cvm_D[gj, i_s] = _cvm_D
                    acc_cvm_p[gj, i_s] = _cvm_p
                    acc_cvm_S_raw[gj, i_s] = _cvm_S
                    acc_logL_raw[gj, i_s] = _logL
                    cells_done += 1

                    elapsed = time.time() - t_start
                    eta_str = ''
                    if 1 < cells_done < n_cells_total:
                        eta = elapsed / cells_done * (n_cells_total - cells_done)
                        eta_str = f'  —  ETA {_fmt_eta(eta)}'
                    job['progress_pct']  = cells_done / n_cells_total
                    job['progress_text'] = (
                        f'Cell {cells_done}/{n_cells_total}{eta_str}')

                    now = time.time()
                    if now - last_render > 1.0 or cells_done == n_cells_total:
                        last_render = now
                        _is_final = (cells_done == n_cells_total)
                        _method_live = {}
                        for _mk, _mp, _md, _ml in [
                            ('ks', acc_ks_p, acc_ks_D, 'K-S p'),
                            ('weighted', acc_weighted_p, acc_weighted_D, 'K-S weighted p'),
                            ('cvm', acc_cvm_p, acc_cvm_D, 'CvM p'),
                            ('likelihood', acc_logL_raw, acc_logL_raw, 'Likelihood'),
                        ]:
                            _disp_p = _mp
                            _disp_d = _md
                            # Normalize likelihood logL to [0,1]
                            if _mk == 'likelihood':
                                _logL_max_v = np.nanmax(_mp)
                                if np.isfinite(_logL_max_v):
                                    _disp_p = np.exp(_mp - _logL_max_v)
                                else:
                                    _disp_p = np.zeros_like(_mp)
                                _disp_d = _disp_p
                            _method_live[_mk] = {
                                'p': np.where(np.isnan(_disp_p), 0.0, _disp_p).copy(),
                                'd': np.where(np.isnan(_disp_d), 0.0, _disp_d).copy(),
                                'fbin': fbin_vals.copy(),
                                'x': sigma_vals.copy(),
                                'title': f'{_ml}  (Langer 2020)',
                                'is_final': _is_final,
                            }
                        job['live_heatmaps'] = _method_live
                        # Build per-method status summary
                        _status_items = []
                        for _smk in ('ks', 'weighted', 'cvm', 'likelihood'):
                            if _smk in _method_live:
                                _sp = _method_live[_smk]['p']
                                _, _, _spv = _best_point(_sp, fbin_vals, sigma_vals)
                                _status_items.append(f'{_smk}: **{_spv:.4f}**')
                        _ks_disp = _method_live['ks']['p']
                        bf, bsig, bpv = _best_point(
                            _ks_disp, fbin_vals, sigma_vals)
                        job['live_status'] = (
                            f'best f_bin = **{bf:.4f}**, '
                            f'σ_single = **{bsig:.1f}** km/s  |  '
                            + '  |  '.join(_status_items))

            # Checkpoint
            if cells_done > 0:
                os.makedirs(_RESULT_DIR, exist_ok=True)
                np.savez(
                    _result_path('langer') + '.partial',
                    fbin_grid=fbin_vals, sigma_grid=sigma_vals,
                    ks_p=acc_ks_p, ks_D=acc_ks_D,
                    weighted_D=acc_weighted_D, weighted_p=acc_weighted_p,
                    cvm_D=acc_cvm_D, cvm_p=acc_cvm_p,
                    cvm_S_raw=acc_cvm_S_raw, logL_raw=acc_logL_raw,
                    scoring_version=np.array(2),
                    config_hash=_stable_cfg_hash(stable_cfg),
                    settings=np.array(json.dumps(stable_cfg)),
                    timestamp=np.array(_dt.datetime.now().isoformat()),
                )

        elapsed_total = time.time() - t_start
        job['elapsed_total'] = elapsed_total

        # ── Save final result ────────────────────────────────────────────
        os.makedirs(_RESULT_DIR, exist_ok=True)
        sp = save_params
        lg_chash = _stable_cfg_hash({
            **stable_cfg,
            'fbin_min': sp['fbin_min'], 'fbin_max': sp['fbin_max'],
            'fbin_steps': sp['fbin_steps'],
            'sigma_min': sp['sigma_min'], 'sigma_max': sp['sigma_max'],
            'sigma_steps': sp['sigma_steps'],
        })
        # Normalize logL → likelihood [0,1]
        _logL_max = np.nanmax(acc_logL_raw)
        if np.isfinite(_logL_max):
            acc_likelihood = np.exp(acc_logL_raw - _logL_max)
        else:
            acc_likelihood = np.zeros_like(acc_logL_raw)

        full_result = {
            'fbin_grid': fbin_vals, 'sigma_grid': sigma_vals,
            'ks_p': acc_ks_p, 'ks_D': acc_ks_D,
            'weighted_D': acc_weighted_D, 'weighted_p': acc_weighted_p,
            'cvm_D': acc_cvm_D, 'cvm_p': acc_cvm_p,
            'cvm_S_raw': acc_cvm_S_raw,
            'likelihood': acc_likelihood, 'logL_raw': acc_logL_raw,
            'scoring_version': np.array(2),
            'obs_delta_rv': obs_delta_rv,
            'likelihood_bin_edges': params.get('likelihood_bin_edges'),
        }

        # ── Compute HDI68 posterior errors and save alongside ────────────
        from wr_bias_simulation import compute_hdi68 as _hdi68
        _lg_post_fbin = np.sum(acc_ks_p, axis=1)
        _lg_post_sigma = np.sum(acc_ks_p, axis=0)
        _lg_m_fb, _lg_lo_fb, _lg_hi_fb = _hdi68(fbin_vals, _lg_post_fbin)
        _lg_m_sig, _lg_lo_sig, _lg_hi_sig = _hdi68(sigma_vals, _lg_post_sigma)
        _lg_hdi = dict(
            mode_fbin=_lg_m_fb, lo_fbin=_lg_lo_fb, hi_fbin=_lg_hi_fb,
            mode_sigma=_lg_m_sig, lo_sigma=_lg_lo_sig, hi_sigma=_lg_hi_sig,
        )
        full_result.update(_lg_hdi)

        _save_kwargs = dict(
            **full_result,
            config_hash=lg_chash,
            settings=np.array(json.dumps(stable_cfg)),
            obs_delta_rv=obs_delta_rv,
            timestamp=np.array(_dt.datetime.now().isoformat()),
        )
        np.savez(_result_path('langer'), **_save_kwargs)
        _desc_name = _build_descriptive_filename(
            'langer',
            sp['fbin_min'], sp['fbin_max'], sp['fbin_steps'],
            sp['sigma_min'], sp['sigma_max'], sp['sigma_steps'],
            int(n_stars), sigma_vals,
            sp['logP_min'], sp['logP_max'],
            x_label='sig',
        )
        _wA = sp.get('weight_A', 0.3)
        if _wA == 1.0:
            _desc_name = _desc_name.replace('.npz', '_caseA.npz')
        elif _wA == 0.0:
            _desc_name = _desc_name.replace('.npz', '_caseB.npz')
        else:
            _desc_name = _desc_name.replace('.npz', f'_wA{_wA:.2f}.npz')
        _desc_path = os.path.join(_RESULT_DIR, _desc_name)
        np.savez(_desc_path, **_save_kwargs)
        _scan_result_metadata.clear()
        _partial = _result_path('langer') + '.partial.npz'
        if os.path.exists(_partial):
            os.remove(_partial)
        _append_run_history({
            'timestamp': _dt.datetime.now().isoformat(),
            'model': 'langer2020', 'config_hash': lg_chash,
            'config': stable_cfg, 'elapsed_s': round(elapsed_total, 1),
            'result_file': _result_path('langer'),
            'descriptive_file': _desc_path,
        })

        job['result']       = full_result
        job['desc_name']    = _desc_name
        job['n_cells_total'] = n_cells_total
        job['status']       = 'done'

    except Exception:
        job['error']  = _tb.format_exc()
        job['status'] = 'error'


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

        fbin_grid = np.array(fbin_vals, dtype=float)
        pi_grid   = np.array(pi_vals, dtype=float)
        sigma_grid = np.array(sigma_vals, dtype=float)
        n_sig = len(sigma_grid)
        n_fb  = len(fbin_grid)
        n_pi  = len(pi_grid)

        # Build tasks
        tasks = []
        idx = 0
        for sigma in sigma_grid:
            for fb in fbin_grid:
                for pi_val in pi_grid:
                    tasks.append((fb, pi_val, sigma, bin_cfg, period_model,
                                  1234 + idx, n_sets))
                    idx += 1
        n_tasks = len(tasks)

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

        # Support resuming from partial checkpoint
        _cad_shape = (n_sig, n_fb, n_pi)
        _pre_p = params.get('prefilled_ks_p')
        _pre_D = params.get('prefilled_ks_D')
        if (_pre_p is not None and _pre_D is not None
                and _pre_p.shape == _cad_shape):
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

        # Track overall progress (including pre-completed cells from resume)
        _total_original = n_sig * n_fb * n_pi
        _pre_done = 0

        # Filter out already-completed tasks
        if _pre_p is not None:
            tasks = [t for t in tasks
                     if np.isnan(ks_p[
                         int(np.searchsorted(sigma_grid, t[2])),
                         int(np.searchsorted(fbin_grid, t[0])),
                         int(np.searchsorted(pi_grid, t[1]))])]
            n_tasks = len(tasks)
            _pre_done = _total_original - n_tasks

        best_p = -1.0
        best_fb = 0.0
        best_median_cdf = None
        best_lo_cdf = None
        best_hi_cdf = None
        completed = 0

        import time as _time
        t_start = _time.time()

        with mp.Pool(processes=int(n_proc),
                     initializer=_init_worker,
                     initargs=_initargs) as pool:
            for res in pool.imap_unordered(_single_grid_task_cadence_aware, tasks):
                if job.get('cancel'):
                    pool.terminate()
                    # Save partial results if cancel_mode is 'save'
                    if (job.get('cancel_mode') == 'save'
                            and (_pre_done + completed) > 0):
                        # Reuse the original file path if resuming
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
                elapsed = _time.time() - t_start
                eta_str = ''
                if completed > 1 and completed < n_tasks:
                    eta = elapsed / completed * (n_tasks - completed)
                    eta_str = f'  —  ETA {_fmt_eta(eta)}'
                pct = (_pre_done + completed) / _total_original
                job['progress_pct'] = pct
                job['progress_text'] = (
                    f'{pct*100:.1f}%  ({_pre_done + completed}/{_total_original}){eta_str}')

                # Live heatmap update (throttled) — all 4 methods
                _now = _time.monotonic()
                _is_final = (completed == n_tasks)
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

        # HDI68 (p-value based)
        if n_sig == 1:
            _ks2 = ks_p[0]
            _post_fb = np.sum(_ks2, axis=1)
            _post_pi = np.sum(_ks2, axis=0)
            if _post_fb.sum() > 0:
                m_fb, lo_fb, hi_fb = _hdi68(fbin_grid, _post_fb)
                result.update(mode_fbin=m_fb, lo_fbin=lo_fb, hi_fbin=hi_fb)
            if _post_pi.sum() > 0:
                m_pi, lo_pi, hi_pi = _hdi68(pi_grid, _post_pi)
                result.update(mode_pi=m_pi, lo_pi=lo_pi, hi_pi=hi_pi)
        else:
            _ks3 = ks_p
            _post_fb = np.sum(_ks3, axis=(0, 2))
            _post_pi = np.sum(_ks3, axis=(0, 1))
            _post_sig = np.sum(_ks3, axis=(1, 2))
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
            if n_sig == 1:
                _L2 = likelihood[0]
                _Lpost_fb = np.sum(_L2, axis=1)
                _Lpost_pi = np.sum(_L2, axis=0)
                if _Lpost_fb.sum() > 0:
                    mL_fb, loL_fb, hiL_fb = _hdi68(fbin_grid, _Lpost_fb)
                    result.update(mode_fbin_L=mL_fb, lo_fbin_L=loL_fb, hi_fbin_L=hiL_fb)
                if _Lpost_pi.sum() > 0:
                    mL_pi, loL_pi, hiL_pi = _hdi68(pi_grid, _Lpost_pi)
                    result.update(mode_pi_L=mL_pi, lo_pi_L=loL_pi, hi_pi_L=hiL_pi)
            else:
                _L3 = likelihood
                _Lpost_fb = np.sum(_L3, axis=(0, 2))
                _Lpost_pi = np.sum(_L3, axis=(0, 1))
                _Lpost_sig = np.sum(_L3, axis=(1, 2))
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


