"""bc.runners_dsilva — Dsilva background simulation runner."""
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
