"""bc.runners_langer — Langer 2020 background simulation runner."""
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

def _run_langer_bg(job: dict, params: dict) -> None:
    """Run Langer 2020 grid search in a background thread.

    Supports logP_max scanning: when ``logPmax_scan_vals`` has >1 entry the
    accumulation arrays become 3-D ``(n_logPmax, n_fbin, n_sigma)``.
    """
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
        logPmax_scan_vals = np.asarray(
            params.get('logPmax_scan_vals', [bin_cfg.logP_max]))
        _scan_logPmax = len(logPmax_scan_vals) > 1

        n_logPmax = len(logPmax_scan_vals)
        n_fbin    = len(fbin_vals)
        n_sigma   = len(sigma_vals)

        # Accumulation arrays — 3-D when scanning logP_max, else 2-D
        if _scan_logPmax:
            _lg_shape = (n_logPmax, n_fbin, n_sigma)
        else:
            _lg_shape = (n_fbin, n_sigma)

        # Pre-filled arrays (from partial cache reuse) — only for 2-D
        _prefilled_p = params.get('acc_ks_p')
        _prefilled_D = params.get('acc_ks_D')
        if (_prefilled_p is not None and _prefilled_D is not None
                and _prefilled_p.shape == _lg_shape and not _scan_logPmax):
            acc_ks_p = _prefilled_p.copy()
            acc_ks_D = _prefilled_D.copy()
        else:
            acc_ks_p = np.full(_lg_shape, np.nan)
            acc_ks_D = np.full(_lg_shape, np.nan)
        acc_weighted_D = np.full(_lg_shape, np.nan)
        acc_weighted_p = np.full(_lg_shape, np.nan)
        acc_cvm_D      = np.full(_lg_shape, np.nan)
        acc_cvm_p      = np.full(_lg_shape, np.nan)
        acc_cvm_S_raw  = np.full(_lg_shape, np.nan)
        acc_logL_raw   = np.full(_lg_shape, np.nan)

        missing_fbin_idx = params.get('missing_fbin_idx')
        if missing_fbin_idx is None or _scan_logPmax:
            missing_fbin_idx = list(range(n_fbin))

        def _make_lg_bin_cfg(logPmax_v):
            """Create BinaryParameterConfig with a specific logP_max."""
            return BinaryParameterConfig(
                logP_min=bin_cfg.logP_min, logP_max=float(logPmax_v),
                period_model='langer2020',
                langer_period_params=bin_cfg.langer_period_params,
                e_model=bin_cfg.e_model, e_max=bin_cfg.e_max,
                mass_primary_model=bin_cfg.mass_primary_model,
                mass_primary_fixed=bin_cfg.mass_primary_fixed,
                mass_primary_range=bin_cfg.mass_primary_range,
                q_model=bin_cfg.q_model, q_range=bin_cfg.q_range,
                langer_q_mu=bin_cfg.langer_q_mu,
                langer_q_sigma=bin_cfg.langer_q_sigma,
                q_flipped=bin_cfg.q_flipped,
            )

        n_cells_total = n_logPmax * len(missing_fbin_idx) * n_sigma
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
                    _partial_kw = dict(
                        fbin_grid=fbin_vals, sigma_grid=sigma_vals,
                        logPmax_grid=logPmax_scan_vals,
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
                    np.savez(_pf, **_partial_kw)
                    job['partial_saved'] = True

                for i_lp, logPmax_v in enumerate(logPmax_scan_vals):
                    if job.get('cancel'):
                        if job.get('cancel_mode') == 'save' and cells_done > 0:
                            _save_partial_langer()
                        job['status'] = 'cancelled'
                        return
                    cur_bin_cfg = _make_lg_bin_cfg(logPmax_v)

                    tasks = []
                    for gj in missing_fbin_idx:
                        for i_s, sv in enumerate(sigma_vals):
                            tasks.append((
                                float(fbin_vals[gj]), 0.0, float(sv),
                                cur_bin_cfg, 'langer2020', seed_base,
                            ))
                            seed_base += 1

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
                        if _scan_logPmax:
                            acc_ks_p[i_lp, gj, i_s] = _ks_p
                            acc_ks_D[i_lp, gj, i_s] = _ks_D
                            acc_weighted_D[i_lp, gj, i_s] = _w_D
                            acc_weighted_p[i_lp, gj, i_s] = _w_p
                            acc_cvm_D[i_lp, gj, i_s] = _cvm_D
                            acc_cvm_p[i_lp, gj, i_s] = _cvm_p
                            acc_cvm_S_raw[i_lp, gj, i_s] = _cvm_S
                            acc_logL_raw[i_lp, gj, i_s] = _logL
                        else:
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
                        _lp_label = (f'logP_max={logPmax_v:.2f}, '
                                     if _scan_logPmax else '')
                        job['progress_pct']  = cells_done / n_cells_total
                        job['progress_text'] = (
                            f'{_lp_label}Cell {cells_done}/{n_cells_total}{eta_str}')

                        now = time.time()
                        if now - last_render > 1.0 or cells_done == n_cells_total:
                            last_render = now
                            _is_final = (cells_done == n_cells_total)
                            # Live heatmap: show current logPmax slice (fbin × sigma)
                            if _scan_logPmax:
                                _disp_slice = {k: v[i_lp] for k, v in [
                                    ('ks_p', acc_ks_p), ('ks_D', acc_ks_D),
                                    ('w_p', acc_weighted_p), ('w_D', acc_weighted_D),
                                    ('cvm_p', acc_cvm_p), ('cvm_D', acc_cvm_D),
                                    ('logL', acc_logL_raw),
                                ]}
                            else:
                                _disp_slice = {
                                    'ks_p': acc_ks_p, 'ks_D': acc_ks_D,
                                    'w_p': acc_weighted_p, 'w_D': acc_weighted_D,
                                    'cvm_p': acc_cvm_p, 'cvm_D': acc_cvm_D,
                                    'logL': acc_logL_raw,
                                }
                            _method_live = {}
                            for _mk, _pk, _dk, _ml in [
                                ('ks', 'ks_p', 'ks_D', 'K-S p'),
                                ('weighted', 'w_p', 'w_D', 'K-S weighted p'),
                                ('cvm', 'cvm_p', 'cvm_D', 'CvM p'),
                                ('likelihood', 'logL', 'logL', 'Likelihood'),
                            ]:
                                _mp = _disp_slice[_pk]
                                _md = _disp_slice[_dk]
                                if _mk == 'likelihood':
                                    _logL_max_v = np.nanmax(_mp)
                                    if np.isfinite(_logL_max_v):
                                        _mp = np.exp(_mp - _logL_max_v)
                                    else:
                                        _mp = np.zeros_like(_mp)
                                    _md = _mp
                                _lp_title = (f', logP_max={logPmax_v:.2f}'
                                             if _scan_logPmax else '')
                                _method_live[_mk] = {
                                    'p': np.where(np.isnan(_mp), 0.0, _mp).copy(),
                                    'd': np.where(np.isnan(_md), 0.0, _md).copy(),
                                    'fbin': fbin_vals.copy(),
                                    'x': sigma_vals.copy(),
                                    'title': f'{_ml}  (Langer 2020{_lp_title})',
                                    'is_final': _is_final,
                                }
                            job['live_heatmaps'] = _method_live
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
                                f'{_lp_label}best f_bin = **{bf:.4f}**, '
                                f'σ_single = **{bsig:.1f}** km/s  |  '
                                + '  |  '.join(_status_items))

                            # Live 1D logPmax profile
                            if _scan_logPmax and n_logPmax > 1:
                                _live_lp_pvals = []
                                for _lpi in range(n_logPmax):
                                    _lp_slice = acc_ks_p[_lpi]
                                    if np.any(~np.isnan(_lp_slice)):
                                        _live_lp_pvals.append(
                                            float(np.nanmax(_lp_slice)))
                                    else:
                                        _live_lp_pvals.append(0.0)
                                job['live_logPmax_1d'] = {
                                    'logPmax_vals': logPmax_scan_vals.tolist(),
                                    'max_pvals': _live_lp_pvals,
                                }

            # Checkpoint
            if cells_done > 0:
                os.makedirs(_RESULT_DIR, exist_ok=True)
                np.savez(
                    _result_path('langer') + '.partial',
                    fbin_grid=fbin_vals, sigma_grid=sigma_vals,
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
            'logPmax_grid': logPmax_scan_vals,
            'ks_p': acc_ks_p, 'ks_D': acc_ks_D,
            'weighted_D': acc_weighted_D, 'weighted_p': acc_weighted_p,
            'cvm_D': acc_cvm_D, 'cvm_p': acc_cvm_p,
            'cvm_S_raw': acc_cvm_S_raw,
            'likelihood': acc_likelihood, 'logL_raw': acc_logL_raw,
            'scoring_version': np.array(2),
            'obs_delta_rv': obs_delta_rv,
            'likelihood_bin_edges': params.get('likelihood_bin_edges'),
        }

        # ── Compute HDI68 posterior errors ────────────────────────────────
        from wr_bias_simulation import compute_hdi68 as _hdi68
        if _scan_logPmax:
            # Marginalize over logPmax for HDI
            _ks_marg = np.nanmax(acc_ks_p, axis=0)  # (n_fbin, n_sigma)
        else:
            _ks_marg = acc_ks_p
        _lg_post_fbin = np.sum(_ks_marg, axis=1)
        _lg_post_sigma = np.sum(_ks_marg, axis=0)
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
