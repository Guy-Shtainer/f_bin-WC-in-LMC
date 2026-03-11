"""
pages/05_bias_correction.py — Bias Correction (Dsilva / Langer 2020 grid search)

Features:
  - Two-column layout: grid/orbital params left, sigma scan + live heatmap right
  - Single persistent multiprocessing Pool — no per-f_bin overhead
  - Heatmap fills in live row-by-row via imap_unordered + throttled render
  - Sigma scan mode: run N sigma values -> max-p line chart + browse slider + animated 4D + 3D stacked
  - Smart partial cache reuse: unchanged f_bin rows reused from prior result
  - All BinaryParameterConfig orbital params exposed and editable
  - User-controllable canvas dimensions (height / width in px)
"""
from __future__ import annotations

import datetime as _dt
import glob as _glob
import hashlib
import json
import multiprocessing as mp
import os
import sys
import threading
import time
import traceback as _tb

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from shared import (
    inject_theme, render_sidebar, get_settings_manager,
    cached_load_observed_delta_rvs, cached_load_cadence,
    cached_load_grid_result, settings_hash,
    find_best_grid_point, make_heatmap_fig,
    PLOTLY_THEME, get_palette,
)

_best_point = find_best_grid_point
_make_heatmap_fig = make_heatmap_fig

st.set_page_config(
    page_title='Bias Correction — WR Binary',
    page_icon='⚡',
    layout='wide',
)
inject_theme()
settings = render_sidebar('Bias Correction')
sm = get_settings_manager()

st.markdown('# ⚡ Bias Correction')
st.caption(
    'Monte-Carlo K-S grid search over (f_bin, π) to find the intrinsic binary fraction '
    'and period-distribution power-law index that best reproduce the observed ΔRV distribution.'
)

# ─────────────────────────────────────────────────────────────────────────────
# Canvas size (page-level — used by both Dsilva and Langer tabs)
# ─────────────────────────────────────────────────────────────────────────────
with st.expander('🖼️ Canvas size', expanded=False):
    _cs_c1, _cs_c2, _ = st.columns([0.2, 0.2, 0.6])
    canvas_height = _cs_c1.number_input(
        'Height (px)', 200, 2000, 520, 20, key='bc_canvas_height')
    canvas_width = _cs_c2.number_input(
        'Width (px, 0 = auto)', 0, 3000, 0, 50, key='bc_canvas_width')

_ch = int(canvas_height)
_cw = int(canvas_width) if int(canvas_width) > 0 else None
_use_cw = (_cw is None)

_RESULT_DIR = os.path.join(_ROOT, 'results')
_HISTORY_PATH = os.path.join(_ROOT, 'settings', 'run_history.json')

# ─────────────────────────────────────────────────────────────────────────────
# Model tabs
# ─────────────────────────────────────────────────────────────────────────────
# Dynamic tabs — see bottom of file

pal = get_palette()

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_eta(seconds: float) -> str:
    """Format seconds as human-readable HH:MM:SS (with days if needed)."""
    s = int(seconds)
    if s < 60:
        return f'{s}s'
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    if d > 0:
        return f'{d}d {h:02d}:{m:02d}:{s:02d}'
    if h > 0:
        return f'{h}:{m:02d}:{s:02d}'
    return f'{m}:{s:02d}'


def _result_path(model: str) -> str:
    return os.path.join(_RESULT_DIR, f'{model}_result.npz')


def _stable_cfg_hash(cfg: dict) -> str:
    return hashlib.sha256(
        json.dumps(cfg, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


# ── Descriptive filename helpers for saved results ────────────────────────

def _build_descriptive_filename(
    model: str,
    fbin_min: float, fbin_max: float, fbin_steps: int,
    x_min: float, x_max: float, x_steps: int,
    n_stars: int,
    sigma_vals: np.ndarray,
    logP_min: float, logP_max: float,
    x_label: str = 'pi',
) -> str:
    """Build a descriptive .npz filename encoding key run parameters.

    Format (Dsilva): dsilva_fb0.0-1.0x200_pi-3.0-3.0x100_N10000_sig5.5_logP0.15-5.0_260309-1200.npz
    Format (Langer): langer_fb0.01-0.99x100_sig1.0-15.0x30_N10000_logP0.5-3.5_260309-1200.npz
    """
    ts = _dt.datetime.now().strftime('%y%m%d-%H%M')
    sig = sigma_vals
    if sig.size == 1:
        sig_part = f'sig{sig[0]:.1f}'
    else:
        sig_part = f'sig{sig[0]:.1f}-{sig[-1]:.1f}x{sig.size}'

    # Skip sig_part when x_label is already 'sig' (avoids duplication for Langer)
    name = (
        f'{model}'
        f'_fb{fbin_min:.2f}-{fbin_max:.2f}x{fbin_steps}'
        f'_{x_label}{x_min:.1f}-{x_max:.1f}x{x_steps}'
        f'_N{n_stars}'
        + (f'_{sig_part}' if x_label != 'sig' else '')
        + f'_logP{logP_min:.2f}-{logP_max:.2f}'
        f'_{ts}.npz'
    )
    return name


_FILENAME_FORMAT_HELP = (
    '**Filename format:** '
    '`{model}_fb{min}-{max}x{steps}_{axis}{min}-{max}x{steps}'
    '_N{n_stars}_sig{value_or_range}_logP{min}-{max}_{YYMMDD-HHMM}`'
)


def _list_saved_results(model: str) -> list[tuple[str, str]]:
    """List saved .npz result files for a model, newest first.

    Returns list of (display_name, full_path) tuples.
    """
    pattern = os.path.join(_RESULT_DIR, f'{model}_*.npz')
    files = _glob.glob(pattern)
    # Also include the legacy file if it exists
    legacy = _result_path(model)
    if os.path.exists(legacy) and legacy not in files:
        files.append(legacy)
    # Exclude partial checkpoints
    files = [f for f in files if not f.endswith('.partial.npz')]
    # Sort by modification time, newest first
    files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    return [(os.path.basename(f).replace('.npz', ''), f) for f in files]


def _make_max_pval_fig(
    sigma_vals: np.ndarray,
    max_pvals: list[float],
    height: int = 300,
    x_label: str = 'σ_single',
) -> go.Figure:
    """Line chart: max K-S p-value vs a scan variable."""
    best_idx = int(np.argmax(max_pvals))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sigma_vals, y=max_pvals,
        mode='lines+markers',
        marker=dict(size=8, color='#4A90D9'),
        line=dict(color='#4A90D9', width=2),
        hovertemplate=f'{x_label}=%{{x:.2f}}<br>max p=%{{y:.4f}}<extra></extra>',
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=[float(sigma_vals[best_idx])],
        y=[max_pvals[best_idx]],
        mode='markers+text',
        marker=dict(symbol='star', size=16, color='gold',
                    line=dict(color='black', width=1)),
        text=[f'  {x_label}={float(sigma_vals[best_idx]):.2f}, p={max_pvals[best_idx]:.4f}'],
        textposition='middle right',
        textfont=dict(color='gold', size=11),
        showlegend=False,
    ))
    fig.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(text=f'Max K-S p-value vs {x_label}', font=dict(size=14)),
        'xaxis_title': x_label,
        'yaxis_title': 'Max K-S p-value',
        'height': height,
        'margin': dict(l=60, r=20, t=50, b=50),
    })
    return fig


def _make_3d_stacked_fig(
    ks_p_3d: np.ndarray,
    fbin_vals: np.ndarray,
    pi_vals: np.ndarray,
    sigma_vals: np.ndarray,
    height: int = 700,
    width: int | None = None,
) -> go.Figure:
    """3D stacked semi-transparent surfaces: one per sigma_single."""
    pal = get_palette()
    valid = ks_p_3d[~np.isnan(ks_p_3d)]
    global_zmax = float(np.percentile(valid, 98)) if valid.size > 0 else 1.0

    fig = go.Figure()
    pi_mesh, fbin_mesh = np.meshgrid(pi_vals, fbin_vals)

    n_sigma = len(sigma_vals)
    # Cap layers to avoid overly heavy plots
    max_layers = 20
    if n_sigma > max_layers:
        indices = np.linspace(0, n_sigma - 1, max_layers, dtype=int)
    else:
        indices = np.arange(n_sigma)

    sigma_min_val = float(sigma_vals[indices[0]])
    sigma_max_val = float(sigma_vals[indices[-1]])
    sigma_range = max(sigma_max_val - sigma_min_val, 1.0)

    for count, i_s in enumerate(indices):
        sigma_val = float(sigma_vals[i_s])
        # z position = actual sigma value for meaningful axis
        z_layer = np.full_like(pi_mesh, sigma_val)
        p_slice = ks_p_3d[i_s]

        fig.add_trace(go.Surface(
            x=pi_mesh, y=fbin_mesh, z=z_layer,
            surfacecolor=p_slice,
            colorscale='RdBu_r',
            cmin=0.0, cmax=global_zmax,
            opacity=0.6,
            showscale=(count == len(indices) - 1),
            colorbar=dict(title='K-S p', thickness=14, len=0.6)
            if count == len(indices) - 1 else None,
            name=f'σ={sigma_val:.1f}',
            hovertemplate=(
                f'σ_single={sigma_val:.1f} km/s<br>'
                'π=%{x:.2f}<br>f_bin=%{y:.3f}<br>p=%{surfacecolor:.4f}<extra></extra>'
            ),
        ))

    layout_kw = {
        **PLOTLY_THEME,
        'title': dict(text='3D Stacked Heatmaps (f_bin x π x σ_single)',
                       font=dict(size=14)),
        'scene': dict(
            xaxis_title='π  (period power-law index)',
            yaxis_title='f_bin  (binary fraction)',
            zaxis_title='σ_single (km/s)',
            bgcolor=pal['plot_bg'],
        ),
        'height': height,
        'margin': dict(l=10, r=10, t=50, b=10),
    }
    if width is not None:
        layout_kw['width'] = width

    fig.update_layout(**layout_kw)
    return fig


def _find_reusable_fbin(
    cached: dict,
    fbin_new: np.ndarray,
    pi_new: np.ndarray,
    sigma_new: np.ndarray,
    stable_cfg: dict,
) -> tuple[list[int], list[int]] | None:
    """
    Check if cached result shares the same pi grid and simulation parameters.
    Returns (new_indices, cache_indices) for matching f_bin values, or None.
    """
    try:
        if not np.allclose(np.asarray(cached['pi_grid']), pi_new, atol=1e-6):
            return None
        if not np.allclose(np.asarray(cached['sigma_grid']), sigma_new, atol=1e-6):
            return None
        cached_cfg = json.loads(str(cached.get('settings', '{}')))
        for k in ('n_stars_sim', 'sigma_measure', 'logP_min', 'logP_max',
                   'period_model', 'e_model', 'e_max',
                   'mass_primary_model', 'mass_primary_fixed',
                   'q_model', 'q_min', 'q_max'):
            if str(cached_cfg.get(k)) != str(stable_cfg.get(k)):
                return None
        cached_fbin = np.asarray(cached['fbin_grid'])
        new_idx, cache_idx = [], []
        for i, fb in enumerate(fbin_new):
            j = int(np.argmin(np.abs(cached_fbin - fb)))
            if np.abs(cached_fbin[j] - fb) < 1e-6:
                new_idx.append(i)
                cache_idx.append(j)
        return new_idx, cache_idx
    except Exception:
        return None


def _find_reusable_fbin_langer(
    cached: dict,
    fbin_new: np.ndarray,
    sigma_new: np.ndarray,
    stable_cfg: dict,
) -> tuple[list[int], list[int]] | None:
    """Check if a cached Langer result shares the same sigma grid and config."""
    try:
        if not np.allclose(np.asarray(cached['sigma_grid']), sigma_new, atol=1e-6):
            return None
        cached_cfg = json.loads(str(cached.get('settings', '{}')))
        for k in ('n_stars_sim', 'sigma_measure', 'logP_min', 'logP_max',
                   'period_model', 'e_model', 'e_max',
                   'mass_primary_model', 'mass_primary_fixed',
                   'q_model', 'q_min', 'q_max',
                   'q_flipped', 'langer_q_mu', 'langer_q_sigma',
                   'langer_period_params'):
            if str(cached_cfg.get(k)) != str(stable_cfg.get(k)):
                return None
        cached_fbin = np.asarray(cached['fbin_grid'])
        new_idx, cache_idx = [], []
        for i, fb in enumerate(fbin_new):
            j = int(np.argmin(np.abs(cached_fbin - fb)))
            if np.abs(cached_fbin[j] - fb) < 1e-6:
                new_idx.append(i)
                cache_idx.append(j)
        return new_idx, cache_idx
    except Exception:
        return None


def _append_run_history(entry: dict) -> None:
    history = []
    if os.path.exists(_HISTORY_PATH):
        try:
            with open(_HISTORY_PATH) as f:
                history = json.load(f)
        except Exception:
            pass
    history.append(entry)
    with open(_HISTORY_PATH, 'w') as f:
        json.dump(history, f, indent=2, default=str)


# ─────────────────────────────────────────────────────────────────────────────
# Background simulation runners (execute in daemon threads)
# ─────────────────────────────────────────────────────────────────────────────

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
        accumulated_ks_p = np.full((n_logPmax, n_sigma, n_fbin, n_pi), np.nan)
        accumulated_ks_D = np.full_like(accumulated_ks_p, np.nan)

        n_rows_total = n_logPmax * n_sigma * n_fbin
        rows_done    = 0
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
                          6, 3650.0, None, 0.0, None),
            ) as pool:
                for i_lp, logPmax_v in enumerate(logPmax_scan_vals):
                    if job.get('cancel'):
                        job['status'] = 'cancelled'
                        return
                    cur_bin_cfg = _make_bin_cfg(logPmax_v)

                    for i_sigma, sigma in enumerate(sigma_vals):
                        if job.get('cancel'):
                            job['status'] = 'cancelled'
                            return
                        tasks = []
                        for gj in range(n_fbin):
                            for i_pi, pv in enumerate(pi_vals):
                                tasks.append((
                                    float(fbin_vals[gj]), float(pv),
                                    float(sigma), cur_bin_cfg,
                                    'powerlaw', seed_base,
                                ))
                                seed_base += 1

                        completed_per_fbin = {gj: 0 for gj in range(n_fbin)}

                        for fb, pi_ret, sigma_ret, D, p_val in pool.imap_unordered(
                                _single_grid_task_lite, tasks,
                                chunksize=max(1, n_pi // 4)):
                            gj   = fbin_to_global[round(fb, 10)]
                            i_pi = pi_to_idx[round(pi_ret, 10)]
                            accumulated_ks_p[i_lp, i_sigma, gj, i_pi] = p_val
                            accumulated_ks_D[i_lp, i_sigma, gj, i_pi] = D
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
                                    cur_p = accumulated_ks_p[i_lp, i_sigma]
                                    cur_p_disp = np.where(np.isnan(cur_p), 0.0, cur_p)
                                    cur_D_disp = np.where(
                                        np.isnan(accumulated_ks_D[i_lp, i_sigma]),
                                        0.0, accumulated_ks_D[i_lp, i_sigma])
                                    _lp_title = (f', logP_max={logPmax_v:.2f}'
                                                 if _scan_logPmax else '')
                                    job['live_heatmap'] = {
                                        'p': cur_p_disp.copy(),
                                        'd': cur_D_disp.copy(),
                                        'fbin': fbin_vals.copy(),
                                        'x': pi_vals.copy(),
                                        'title': (f'K-S p-value  '
                                                  f'(σ={sigma:.1f} km/s{_lp_title})'),
                                        'is_final': _is_final,
                                    }
                                    bf, bp, bpv = _best_point(
                                        cur_p_disp, fbin_vals, pi_vals)
                                    job['live_status'] = (
                                        f'{_lp_label}σ = **{sigma:.1f}** km/s  →  '
                                        f'best f_bin = **{bf:.4f}**, '
                                        f'π = **{bp:.3f}**, '
                                        f'K-S p = **{bpv:.4f}**')

                        # Update outer max-p
                        _slice_p = accumulated_ks_p[i_lp, i_sigma]
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
                            ks_p=accumulated_ks_p, ks_D=accumulated_ks_D,
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
        full_result = {
            'fbin_grid': fbin_vals, 'pi_grid': pi_vals,
            'sigma_grid': sigma_vals, 'logPmax_grid': logPmax_scan_vals,
            'ks_p': accumulated_ks_p, 'ks_D': accumulated_ks_D,
        }

        # ── Compute HDI68 posterior errors and save alongside ────────────
        from wr_bias_simulation import compute_hdi68 as _hdi68
        _ks4 = accumulated_ks_p  # [logPmax, sigma, fbin, pi]
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
        # Pre-filled arrays (from partial cache reuse)
        acc_ks_p        = params['acc_ks_p']
        acc_ks_D        = params['acc_ks_D']
        missing_fbin_idx = params['missing_fbin_idx']

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
                          6, 3650.0, None, 0.0, None),
            ) as pool:
                for fb, _pi_ret, sigma_ret, D, p_val in pool.imap_unordered(
                        _single_grid_task_lite, tasks,
                        chunksize=max(1, n_sigma // 4)):
                    if job.get('cancel'):
                        job['status'] = 'cancelled'
                        return
                    gj  = fbin_to_global[round(fb, 10)]
                    i_s = sigma_to_idx[round(sigma_ret, 10)]
                    acc_ks_p[gj, i_s] = p_val
                    acc_ks_D[gj, i_s] = D
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
                        cur_p = np.where(np.isnan(acc_ks_p), 0.0, acc_ks_p)
                        cur_D = np.where(np.isnan(acc_ks_D), 0.0, acc_ks_D)
                        job['live_heatmap'] = {
                            'p': cur_p.copy(), 'd': cur_D.copy(),
                            'fbin': fbin_vals.copy(),
                            'x': sigma_vals.copy(),
                            'is_final': (cells_done == n_cells_total),
                        }
                        bf, bsig, bpv = _best_point(
                            cur_p, fbin_vals, sigma_vals)
                        job['live_status'] = (
                            f'best f_bin = **{bf:.4f}**, '
                            f'σ_single = **{bsig:.1f}** km/s, '
                            f'K-S p = **{bpv:.4f}**')

            # Checkpoint
            if cells_done > 0:
                os.makedirs(_RESULT_DIR, exist_ok=True)
                np.savez(
                    _result_path('langer') + '.partial',
                    fbin_grid=fbin_vals, sigma_grid=sigma_vals,
                    ks_p=acc_ks_p, ks_D=acc_ks_D,
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
        full_result = {
            'fbin_grid': fbin_vals, 'sigma_grid': sigma_vals,
            'ks_p': acc_ks_p, 'ks_D': acc_ks_D,
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


# ─────────────────────────────────────────────────────────────────────────────
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

    # ── Left column: grid + orbital parameters ───────────────────────────────
    with col_left:
        with st.expander('⚙️ Grid parameters', expanded=True):
            fbin_min = st.number_input(
                'f_bin min', 0.0, 0.5, float(gcfg.get('fbin_min', 0.01)), 0.01,
                key=f'{p}_fbin_min',
                on_change=lambda: sm.save(['grid_dsilva', 'fbin_min'],
                                          value=st.session_state[f'{p}_fbin_min']))
            fbin_max = st.number_input(
                'f_bin max', 0.5, 1.0, float(gcfg.get('fbin_max', 0.99)), 0.01,
                key=f'{p}_fbin_max',
                on_change=lambda: sm.save(['grid_dsilva', 'fbin_max'],
                                          value=st.session_state[f'{p}_fbin_max']))
            fbin_steps = st.number_input(
                'f_bin steps', 10, 500, int(gcfg.get('fbin_steps', 137)), 1,
                key=f'{p}_fbin_steps',
                on_change=lambda: sm.save(['grid_dsilva', 'fbin_steps'],
                                          value=st.session_state[f'{p}_fbin_steps']))
            pi_min = st.number_input(
                'π min', -5.0, 0.0, float(gcfg.get('pi_min', -3.0)), 0.1,
                key=f'{p}_pi_min',
                on_change=lambda: sm.save(['grid_dsilva', 'pi_min'],
                                          value=st.session_state[f'{p}_pi_min']))
            pi_max = st.number_input(
                'π max', 0.0, 5.0, float(gcfg.get('pi_max', 3.0)), 0.1,
                key=f'{p}_pi_max',
                on_change=lambda: sm.save(['grid_dsilva', 'pi_max'],
                                          value=st.session_state[f'{p}_pi_max']))
            pi_steps = st.number_input(
                'π steps', 10, 500, int(gcfg.get('pi_steps', 249)), 1,
                key=f'{p}_pi_steps',
                on_change=lambda: sm.save(['grid_dsilva', 'pi_steps'],
                                          value=st.session_state[f'{p}_pi_steps']))
            n_stars_sim = st.number_input(
                'N stars / point', 100, 50000, int(gcfg.get('n_stars_sim', 3000)), 100,
                key=f'{p}_n_stars',
                on_change=lambda: sm.save(['grid_dsilva', 'n_stars_sim'],
                                          value=st.session_state[f'{p}_n_stars']))
            sigma_meas = st.number_input(
                'σ_measure (km/s)', 0.001, 20.0,
                float(simcfg.get('sigma_measure', 1.622)), 0.001,
                format='%.3f', key=f'{p}_sigma_meas',
                on_change=lambda: sm.save(['simulation', 'sigma_measure'],
                                          value=st.session_state[f'{p}_sigma_meas']))

        with st.expander('🔧 Orbital parameters (Kepler)', expanded=False):
            st.caption('Parameters of the Kepler orbit randomization in the simulation.')

            # Period range
            logP_min_val = st.number_input(
                'log₁₀(P/days) min', 0.01, 10.0,
                float(orb.get('logP_min', gcfg.get('logP_min', 0.15))), 0.01,
                key=f'{p}_logP_min',
                on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'logP_min'],
                                          value=st.session_state[f'{p}_logP_min']))
            logP_max_val = st.number_input(
                'log₁₀(P/days) max', 0.1, 10.0,
                float(orb.get('logP_max', gcfg.get('logP_max', 5.0))), 0.1,
                key=f'{p}_logP_max',
                on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'logP_max'],
                                          value=st.session_state[f'{p}_logP_max']))

            st.markdown('---')
            # Eccentricity
            e_model = st.selectbox(
                'Eccentricity model', ['flat', 'zero'],
                index=['flat', 'zero'].index(orb.get('e_model', 'flat')),
                key=f'{p}_e_model',
                on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'e_model'],
                                          value=st.session_state[f'{p}_e_model']))
            if e_model == 'flat':
                e_max = st.number_input(
                    'e_max', 0.0, 0.99, float(orb.get('e_max', 0.9)), 0.05,
                    key=f'{p}_e_max',
                    on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'e_max'],
                                              value=st.session_state[f'{p}_e_max']))
            else:
                e_max = 0.0

            st.markdown('---')
            # Primary mass
            mass_model = st.selectbox(
                'Primary mass model', ['fixed', 'uniform'],
                index=['fixed', 'uniform'].index(orb.get('mass_primary_model', 'fixed')),
                key=f'{p}_mass_model',
                on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'mass_primary_model'],
                                          value=st.session_state[f'{p}_mass_model']))
            if mass_model == 'fixed':
                mass_fixed = st.number_input(
                    'M₁ (M☉)', 1.0, 200.0, float(orb.get('mass_primary_fixed', 10.0)), 1.0,
                    key=f'{p}_mass_fixed',
                    on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'mass_primary_fixed'],
                                              value=st.session_state[f'{p}_mass_fixed']))
                mass_range = (float(mass_fixed), float(mass_fixed))
            else:
                mass_fixed = 10.0
                _mr = orb.get('mass_primary_range', [10.0, 20.0])
                mc1, mc2 = st.columns(2)
                mass_min_v = mc1.number_input(
                    'M₁ min', 1.0, 200.0, float(_mr[0]), 1.0, key=f'{p}_mass_min',
                    on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'mass_primary_range'],
                                              value=[st.session_state[f'{p}_mass_min'],
                                                     st.session_state.get(f'{p}_mass_max', _mr[1])]))
                mass_max_v = mc2.number_input(
                    'M₁ max', 1.0, 200.0, float(_mr[1]), 1.0, key=f'{p}_mass_max',
                    on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'mass_primary_range'],
                                              value=[st.session_state.get(f'{p}_mass_min', _mr[0]),
                                                     st.session_state[f'{p}_mass_max']]))
                mass_range = (float(mass_min_v), float(mass_max_v))

            st.markdown('---')
            # Mass ratio q = M2/M1
            q_model = st.selectbox(
                'Mass ratio q model', ['flat', 'langer'],
                index=['flat', 'langer'].index(orb.get('q_model', 'flat')),
                key=f'{p}_q_model',
                on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'q_model'],
                                          value=st.session_state[f'{p}_q_model']))
            _qr = orb.get('q_range', [0.1, 2.0])
            qc1, qc2 = st.columns(2)
            q_min_v = qc1.number_input(
                'q min', 0.01, 10.0, float(_qr[0]), 0.01, key=f'{p}_q_min',
                on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'q_range'],
                                          value=[st.session_state[f'{p}_q_min'],
                                                 st.session_state.get(f'{p}_q_max', _qr[1])]))
            q_max_v = qc2.number_input(
                'q max', 0.01, 10.0, float(_qr[1]), 0.1, key=f'{p}_q_max',
                on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'q_range'],
                                          value=[st.session_state.get(f'{p}_q_min', _qr[0]),
                                                 st.session_state[f'{p}_q_max']]))
            if q_model == 'langer':
                langer_q_mu = st.number_input(
                    'Langer q mean', 0.01, 5.0,
                    float(orb.get('langer_q_mu', 0.7)), 0.05,
                    key=f'{p}_lq_mu',
                    on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'langer_q_mu'],
                                              value=st.session_state[f'{p}_lq_mu']))
                langer_q_sig = st.number_input(
                    'Langer q sigma', 0.01, 5.0,
                    float(orb.get('langer_q_sigma', 0.2)), 0.05,
                    key=f'{p}_lq_sig',
                    on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'langer_q_sigma'],
                                              value=st.session_state[f'{p}_lq_sig']))
            else:
                langer_q_mu = 0.7
                langer_q_sig = 0.2

    # ── Right column: sigma scan + actions + display ─────────────────────────
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
                logPmax_scan_vals = np.array([float(logP_max_val)])

        # Action row
        max_proc = max(1, (os.cpu_count() or 2) - 1)
        _ac1, _ac2, _ac3 = st.columns([0.15, 0.25, 0.60])
        n_proc = _ac1.number_input('Workers', 1, max_proc, max_proc, key=f'{p}_nproc')
        view_mode = _ac2.radio('View', ['K-S p-value', 'K-S D-statistic'],
                               horizontal=True, key=f'{p}_view_mode')
        show_d = view_mode == 'K-S D-statistic'
        _run_col, _load_col, _save_col = _ac3.columns(3)
        _job_running = bool(
            st.session_state.get(f'{p}_job', {}).get('status') == 'running')
        run_btn  = _run_col.button(
            '▶️ Run Bias Correction', type='primary', key=f'{p}_run',
            disabled=_job_running)
        if _job_running:
            if _run_col.button('⏹ Cancel', key=f'{p}_cancel'):
                st.session_state[f'{p}_job']['cancel'] = True
                st.rerun()

        # Load saved results dropdown
        _saved_dsilva = _list_saved_results('dsilva')
        load_btn = False
        if _saved_dsilva:
            with _load_col.popover('📂 Load saved result'):
                st.caption(_FILENAME_FORMAT_HELP)
                _load_options = [name for name, _ in _saved_dsilva]
                _load_idx = st.selectbox(
                    'Select result file', range(len(_load_options)),
                    format_func=lambda i: _load_options[i],
                    key=f'{p}_load_select',
                )
                _sel_path = _saved_dsilva[_load_idx][1]
                # Show timestamp if available
                try:
                    _preview = np.load(_sel_path, allow_pickle=True)
                    if 'timestamp' in _preview:
                        st.caption(f"Saved: {str(_preview['timestamp'])}")
                    if 'settings' in _preview:
                        with st.expander('View settings'):
                            st.json(json.loads(str(_preview['settings'])))
                    _preview.close()
                except Exception:
                    pass
                if st.button('Load selected', key=f'{p}_load_sel_btn'):
                    _loaded = dict(np.load(_sel_path, allow_pickle=True))
                    st.session_state[f'{p}_result'] = _loaded
                    st.session_state['result_dsilva'] = _loaded
                    st.toast(f'Loaded: {os.path.basename(_sel_path)}')
                    load_btn = True
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

    # ── Detect partial checkpoint (interrupted run) ───────────────────────────
    _partial_path = _result_path('dsilva') + '.partial.npz'
    _has_partial = os.path.exists(_partial_path) and not run_btn
    if _has_partial and f'{p}_result' not in st.session_state:
        try:
            _ptl = np.load(_partial_path, allow_pickle=True)
            _ptl_ks_p = np.asarray(_ptl['ks_p'])
            _n_done = int(np.count_nonzero(~np.isnan(_ptl_ks_p)))
            _n_total = _ptl_ks_p.size
            _pct = _n_done / _n_total * 100 if _n_total > 0 else 0
            _ptl_ts = str(_ptl.get('timestamp', 'unknown'))
            status_slot.warning(
                f'Interrupted run detected ({_pct:.0f}% complete, {_ptl_ts}).  \n'
                f'Click **Load partial** to view the incomplete result, '
                f'or **Run** to start fresh.'
            )
            _load_partial_btn = st.button('📋 Load partial result', key=f'{p}_load_partial')
            if _load_partial_btn:
                st.session_state[f'{p}_result'] = {
                    k: _ptl[k] for k in _ptl.files
                }
                status_slot.success(f'Loaded partial result ({_pct:.0f}% complete)')
                st.rerun()
            _ptl.close()
        except Exception:
            pass  # corrupt partial — ignore

    # ── Run grid (background thread) ─────────────────────────────────────────
    if run_btn and not _job_running:
        sh = settings_hash(settings)
        try:
            obs_delta_rv, _ = cached_load_observed_delta_rvs(sh)
            cadence_list, cadence_weights = cached_load_cadence(sh)
        except Exception as e:
            status_slot.error(f'Failed to load observations: {e}')
            st.stop()

        _job = {
            'status': 'running', 'progress_pct': 0.0,
            'progress_text': 'Starting...', 'live_heatmap': None,
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
        _t = threading.Thread(target=_run_dsilva_bg, args=(_job, _params),
                              daemon=True)
        _t.start()
        st.session_state[f'{p}_job'] = _job
        st.rerun()

    # ── Poll running / completed job ─────────────────────────────────────────
    _job = st.session_state.get(f'{p}_job')
    if _job is not None:
        if _job['status'] == 'running':
            progress_slot.progress(
                _job['progress_pct'], text=_job['progress_text'])
            if _job.get('live_heatmap'):
                hd = _job['live_heatmap']
                heatmap_slot.plotly_chart(
                    _make_heatmap_fig(
                        hd['p'], hd['fbin'], hd['x'],
                        title=hd['title'], show_d=show_d,
                        ks_d_2d=hd['d'], height=_ch, width=_cw,
                        live=not hd['is_final'],
                    ), use_container_width=_use_cw)
            if _job.get('live_outer_heatmap'):
                ohd = _job['live_outer_heatmap']
                outer_heatmap_slot.plotly_chart(
                    _make_heatmap_fig(
                        ohd['p'], ohd['y'], ohd['x'],
                        title='Max K-S p  (logP_max × σ_single)',
                        height=_ch, width=_cw,
                        x_label='σ_single (km/s)',
                        y_label='log₁₀(P_max / days)',
                        x_name='σ',
                        best_label_fmt='  logP_max={fbin:.2f}, σ={x:.1f}, p={p:.4f}',
                        live=not ohd['is_final'],
                    ), use_container_width=_use_cw)
            if _job.get('live_status'):
                status_slot.markdown(_job['live_status'])

        elif _job['status'] == 'done':
            _res = _job['result']
            st.session_state[f'{p}_result'] = _res
            st.session_state['result_dsilva'] = _res
            cached_load_grid_result.clear()
            _elapsed = _job.get('elapsed_total', 0)
            _desc = _job.get('desc_name', '')
            _nrows = _job.get('n_rows_total', 0)
            progress_slot.progress(
                1.0, text=f'Done in {_fmt_eta(_elapsed)}.')
            status_slot.success(
                f'Saved to results/{_desc}  '
                f'({_nrows} rows computed in {_fmt_eta(_elapsed)})')
            del st.session_state[f'{p}_job']

        elif _job['status'] == 'error':
            status_slot.error(
                f"Simulation failed:\n```\n{_job['error']}\n```")
            del st.session_state[f'{p}_job']

        elif _job['status'] == 'cancelled':
            status_slot.warning('Simulation cancelled.')
            del st.session_state[f'{p}_job']

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
                    title='Max K-S p-value  (logP_max × σ_single)',
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

        # Show f_bin × π heatmap for selected (logPmax, sigma)
        if not run_btn:
            _lp_title = (f', logP_max={float(logPmax_g[disp_lp_idx]):.2f}'
                         if _has_logPmax_scan else '')
            heatmap_slot.plotly_chart(
                _make_heatmap_fig(
                    ks_p_4d[disp_lp_idx, disp_sig_idx], fbin_g, pi_g,
                    title=(f'K-S p-value  '
                           f'(σ={float(sigma_g[disp_sig_idx]):.1f} km/s'
                           f'{_lp_title})'),
                    show_d=show_d,
                    ks_d_2d=ks_D_4d[disp_lp_idx, disp_sig_idx],
                    height=_ch, width=_cw,
                ),
                use_container_width=_use_cw,
            )

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

        # Slice-vs-global metrics
        _lp_lbl = (f'logP_max={_cur_logPmax_v:.2f}, '
                   if _has_logPmax_scan else '')
        _sig_lbl = f'σ={_cur_sigma_v:.1f} km/s'
        _m_col1, _m_col2 = st.columns(2)
        _m_col1.metric(
            label=f'Current slice ({_lp_lbl}{_sig_lbl})',
            value=f'f_bin={_slice_fb:.4f}, π={_slice_pi:.4f}',
            delta=f'K-S p = {_slice_pval:.6f}',
            delta_color='off',
        )
        _m_col2.metric(
            label='Global best (all slices)',
            value=f'f_bin={best_fbin_v:.4f}, π={best_pi_v:.4f}',
            delta=f'K-S p = {best_pval_v:.6f}',
            delta_color='off',
        )

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

        # ── Marginalization + HDI68 (Dsilva 2023 style) ─────────────────
        # Always compute posteriors (needed for corner plot); HDI from .npz if available
        ks_p_3d = np.sum(ks_p_4d, axis=0)  # [sigma, fbin, pi]
        post_fbin = np.sum(ks_p_3d, axis=(0, 2))
        post_pi   = np.sum(ks_p_3d, axis=(0, 1))
        if _has_sigma_scan:
            post_sigma = np.sum(ks_p_3d, axis=(1, 2))
        if _has_logPmax_scan:
            post_logPmax = np.sum(ks_p_4d, axis=(1, 2, 3))

        _res = st.session_state.get(f'{p}_result', {})
        if 'mode_fbin' in _res:
            mode_fbin = float(_res['mode_fbin'])
            lo_fbin   = float(_res['lo_fbin'])
            hi_fbin   = float(_res['hi_fbin'])
            mode_pi   = float(_res['mode_pi'])
            lo_pi     = float(_res['lo_pi'])
            hi_pi     = float(_res['hi_pi'])
            mode_sigma   = float(_res['mode_sigma'])
            lo_sigma     = float(_res['lo_sigma'])
            hi_sigma     = float(_res['hi_sigma'])
            mode_logPmax = float(_res['mode_logPmax'])
            lo_logPmax   = float(_res['lo_logPmax'])
            hi_logPmax   = float(_res['hi_logPmax'])
        else:
            from wr_bias_simulation import compute_hdi68
            mode_fbin, lo_fbin, hi_fbin = compute_hdi68(fbin_g, post_fbin)
            mode_pi, lo_pi, hi_pi = compute_hdi68(pi_g, post_pi)
            if _has_sigma_scan:
                mode_sigma, lo_sigma, hi_sigma = compute_hdi68(sigma_g, post_sigma)
            else:
                mode_sigma = float(sigma_g[0])
                lo_sigma = hi_sigma = mode_sigma
            if _has_logPmax_scan:
                mode_logPmax, lo_logPmax, hi_logPmax = compute_hdi68(logPmax_g, post_logPmax)
            else:
                mode_logPmax = float(logPmax_g[0])
                lo_logPmax = hi_logPmax = mode_logPmax

        # Compute p-value at posterior mode (nearest grid point)
        _mode_fb_idx = int(np.argmin(np.abs(fbin_g - mode_fbin)))
        _mode_pi_idx = int(np.argmin(np.abs(pi_g - mode_pi)))
        _mode_sig_idx = int(np.argmin(np.abs(sigma_g - mode_sigma)))
        _mode_lp_idx = int(np.argmin(np.abs(logPmax_g - mode_logPmax)))
        _mode_pval = float(ks_p_4d[_mode_lp_idx, _mode_sig_idx,
                                    _mode_fb_idx, _mode_pi_idx])

        # Build summary table — one row per parameter, errors as ±1σ
        _rows = []
        _rows.append(
            f'| f_bin | `{best_fbin_v:.4f}` '
            f'| `{mode_fbin:.4f}` +{hi_fbin - mode_fbin:.4f} '
            f'−{mode_fbin - lo_fbin:.4f} |'
        )
        _rows.append(
            f'| π | `{best_pi_v:.4f}` '
            f'| `{mode_pi:.4f}` +{hi_pi - mode_pi:.4f} '
            f'−{mode_pi - lo_pi:.4f} |'
        )
        if _has_sigma_scan:
            _rows.append(
                f'| σ_single (km/s) | `{best_sigma_v:.1f}` '
                f'| `{mode_sigma:.1f}` +{hi_sigma - mode_sigma:.1f} '
                f'−{mode_sigma - lo_sigma:.1f} |'
            )
        else:
            _rows.append(
                f'| σ_single (km/s) | `{best_sigma_v:.1f}` '
                f'| `{mode_sigma:.1f}` (fixed) |'
            )
        if _has_logPmax_scan:
            _rows.append(
                f'| logP_max | `{best_logPmax_v:.2f}` '
                f'| `{mode_logPmax:.2f}` +{hi_logPmax - mode_logPmax:.2f} '
                f'−{mode_logPmax - lo_logPmax:.2f} |'
            )
        else:
            _rows.append(
                f'| logP_max | `{best_logPmax_v:.2f}` '
                f'| `{mode_logPmax:.2f}` (fixed) |'
            )
        _rows.append(
            f'| **K-S p** | `{best_pval_v:.6f}` '
            f'| `{_mode_pval:.6f}` |'
        )

        result_slot.markdown(
            '| Parameter | Best fit (argmax) | Posterior mode ± 1σ |\n'
            '|---|---|---|\n'
            + '\n'.join(_rows) + '\n\n'
            f'**Observed fraction:**  '
            f'({n_det}+{bartzakos})/{total_pop} = '
            f'**{(n_det+bartzakos)/total_pop*100:.1f}%**'
        )

        # ── Corner Plot ──────────────────────────────────────────────────
        st.markdown('---')
        st.markdown('### Marginalized Posteriors (Corner Plot)')

        from plotly.subplots import make_subplots as _corner_subplots

        # Build param lists: π, f_bin, [σ_single], [logP_max]
        # π first so the off-diagonal cell (row=f_bin, col=π) has x=π, y=f_bin
        # — matching the main heatmap orientation.
        _param_names = ['π', 'f_bin']
        _param_grids = [pi_g, fbin_g]
        _param_posts = [post_pi, post_fbin]
        _param_bests = [_ana_pi, _ana_fbin]
        _param_los   = [lo_pi, lo_fbin]
        _param_his   = [hi_pi, hi_fbin]
        # Map param index → ks_p_4d axis: [logPmax=0, sigma=1, fbin=2, pi=3]
        _param_axes  = [3, 2]

        if _has_sigma_scan:
            _param_names.append('σ_single')
            _param_grids.append(sigma_g)
            _param_posts.append(post_sigma)
            _param_bests.append(_ana_sigma)
            _param_los.append(lo_sigma)
            _param_his.append(hi_sigma)
            _param_axes.append(1)

        if _has_logPmax_scan:
            _param_names.append('logP_max')
            _param_grids.append(logPmax_g)
            _param_posts.append(post_logPmax)
            _param_bests.append(_ana_logPmax)
            _param_los.append(lo_logPmax)
            _param_his.append(hi_logPmax)
            _param_axes.append(0)

        _n_params = len(_param_names)

        fig_corner = _corner_subplots(
            rows=_n_params, cols=_n_params,
            horizontal_spacing=0.06, vertical_spacing=0.06,
        )

        for i in range(_n_params):
            # Diagonal: 1D posterior
            _post_norm = _param_posts[i] / float(np.trapezoid(_param_posts[i], _param_grids[i])) \
                if float(np.trapezoid(_param_posts[i], _param_grids[i])) > 0 else _param_posts[i]

            fig_corner.add_trace(go.Scatter(
                x=_param_grids[i], y=_post_norm,
                mode='lines', line=dict(color='#4A90D9', width=2),
                showlegend=False,
            ), row=i + 1, col=i + 1)

            # HDI68 shading
            _mask_hdi = (_param_grids[i] >= _param_los[i]) & (_param_grids[i] <= _param_his[i])
            _x_hdi = _param_grids[i][_mask_hdi]
            _y_hdi = _post_norm[_mask_hdi]
            if len(_x_hdi) > 0:
                fig_corner.add_trace(go.Scatter(
                    x=np.concatenate([_x_hdi, _x_hdi[::-1]]),
                    y=np.concatenate([_y_hdi, np.zeros(len(_y_hdi))]),
                    fill='toself', fillcolor='rgba(74,144,217,0.3)',
                    line=dict(width=0), showlegend=False,
                ), row=i + 1, col=i + 1)

            # Best-fit line (argmax, matches heatmap star)
            fig_corner.add_vline(
                x=_param_bests[i], line_dash='dash',
                line_color='#E25A53', line_width=1.5,
                row=i + 1, col=i + 1,
            )

            # Off-diagonal: 2D marginalized heatmaps (lower triangle only)
            for j in range(i):
                # Marginalize ks_p_4d over all axes except the two we want
                _keep_axes = sorted([_param_axes[j], _param_axes[i]])
                _sum_axes = tuple(k for k in range(4) if k not in _keep_axes)
                if _sum_axes:
                    _2d = np.sum(ks_p_4d, axis=_sum_axes)
                else:
                    _2d = ks_p_4d.copy()

                # _2d shape: [_keep_axes[0] dim, _keep_axes[1] dim]
                # We want z[y_idx, x_idx] for Heatmap: y=param_i, x=param_j
                if _param_axes[i] == _keep_axes[0]:
                    _z = _2d        # rows=param_i, cols=param_j
                else:
                    _z = _2d.T      # need to transpose

                _z_valid = _z[~np.isnan(_z)]
                _z_max = float(np.percentile(_z_valid, 98)) if _z_valid.size > 0 else 1.0
                fig_corner.add_trace(go.Heatmap(
                    x=_param_grids[j], y=_param_grids[i],
                    z=_z,
                    colorscale='RdBu_r', zmin=0.0, zmax=_z_max,
                    zsmooth='best', showscale=False,
                    hovertemplate=f'{_param_names[j]}=%{{x:.4f}}<br>'
                                 f'{_param_names[i]}=%{{y:.4f}}<br>'
                                 f'p-sum=%{{z:.4f}}<extra></extra>',
                ), row=i + 1, col=j + 1)

                # Contour lines for 68% and 95% credible regions
                _z_flat = _z.ravel()
                _z_pos = _z_flat[_z_flat > 0]
                if len(_z_pos) > 2:
                    _z_sorted = np.sort(_z_pos)[::-1]
                    _z_cumsum = np.cumsum(_z_sorted)
                    _z_cumsum = _z_cumsum / _z_cumsum[-1]
                    _idx_68 = np.searchsorted(_z_cumsum, 0.68)
                    _idx_95 = np.searchsorted(_z_cumsum, 0.95)
                    _lvl_68 = float(_z_sorted[min(_idx_68, len(_z_sorted) - 1)])
                    _lvl_95 = float(_z_sorted[min(_idx_95, len(_z_sorted) - 1)])
                    fig_corner.add_trace(go.Contour(
                        x=_param_grids[j], y=_param_grids[i], z=_z,
                        contours=dict(
                            coloring='none', showlabels=True,
                            labelfont=dict(size=8, color=pal['contour_label']),
                        ),
                        ncontours=2,
                        contours_start=_lvl_95,
                        contours_end=_lvl_68,
                        line=dict(color=pal['contour_color'], width=1.5, dash='dot'),
                        showscale=False, hoverinfo='skip',
                    ), row=i + 1, col=j + 1)

                # Best-fit marker (argmax, matches heatmap star)
                fig_corner.add_trace(go.Scatter(
                    x=[_param_bests[j]], y=[_param_bests[i]],
                    mode='markers',
                    marker=dict(symbol='star', size=10, color='#DAA520',
                                line=dict(color='black', width=1)),
                    showlegend=False,
                ), row=i + 1, col=j + 1)

        # Axis labels (bottom row and left column)
        for i in range(_n_params):
            fig_corner.update_xaxes(title_text=_param_names[i],
                                     row=_n_params, col=i + 1)
            if i > 0:
                fig_corner.update_yaxes(title_text=_param_names[i],
                                         row=i + 1, col=1)

        # Hide upper triangle
        for i in range(_n_params):
            for j in range(i + 1, _n_params):
                fig_corner.update_xaxes(visible=False, row=i + 1, col=j + 1)
                fig_corner.update_yaxes(visible=False, row=i + 1, col=j + 1)

        fig_corner.update_layout(
            **PLOTLY_THEME,
            height=250 * _n_params,
            width=250 * _n_params,
            showlegend=False,
            margin=dict(l=60, r=20, t=30, b=60),
        )
        st.plotly_chart(fig_corner, use_container_width=True, key=f'{p}_corner_plot')
        _cap_logP = (f', logP_max = {_ana_logPmax:.2f}'
                     if _has_logPmax_scan else '')
        st.caption(
            f'Marginalized posteriors following Dsilva et al. (2023). '
            f'**Diagonal:** 1D posteriors with best fit (dashed red) and '
            f'68% HDI (blue shading). '
            f'**Off-diagonal:** 2D marginalized K-S p-value sums with '
            f'best fit (gold star) and 68%/95% credible contours (white dotted). '
            f'Analysis values: f_bin = {_ana_fbin:.4f}, '
            f'π = {_ana_pi:.4f}, '
            f'σ = {_ana_sigma:.1f} km/s'
            f'{_cap_logP}, '
            f'K-S p = {best_pval_v:.6f}.'
        )

        # ── Marginalized heatmaps: f_bin × σ and π × σ (Task #19) ───────
        if _has_sigma_scan:
            st.markdown('---')
            st.markdown('### Marginalized Heatmaps vs σ_single')
            _marg_col1, _marg_col2 = st.columns(2)

            # f_bin × σ: sum over logPmax (axis 0) and π (axis 3)
            _marg_fbin_sigma = np.nansum(ks_p_4d, axis=(0, 3)).T  # [n_fbin, n_sigma]
            with _marg_col1:
                st.plotly_chart(
                    _make_heatmap_fig(
                        _marg_fbin_sigma, fbin_g, sigma_g,
                        title='f_bin × σ_single',
                        height=_ch, width=_cw,
                        x_label='σ_single (km/s)',
                        y_label='f_bin',
                        x_name='σ',
                        best_label_fmt='  f={fbin:.3f}, σ={x:.1f}, p-sum={p:.2f}',
                    ),
                    use_container_width=True,
                    key=f'{p}_marg_fbin_sigma',
                )
                st.caption(
                    'K-S p-value summed over logP_max and π. '
                    'Shows the joint constraint on f_bin and σ_single.'
                )

            # π × σ: sum over logPmax (axis 0) and f_bin (axis 2)
            _marg_pi_sigma = np.nansum(ks_p_4d, axis=(0, 2)).T  # [n_pi, n_sigma]
            with _marg_col2:
                st.plotly_chart(
                    _make_heatmap_fig(
                        _marg_pi_sigma, pi_g, sigma_g,
                        title='π × σ_single',
                        height=_ch, width=_cw,
                        x_label='σ_single (km/s)',
                        y_label='π',
                        x_name='σ',
                        best_label_fmt='  π={fbin:.3f}, σ={x:.1f}, p-sum={p:.2f}',
                    ),
                    use_container_width=True,
                    key=f'{p}_marg_pi_sigma',
                )
                st.caption(
                    'K-S p-value summed over logP_max and f_bin. '
                    'Shows the joint constraint on π and σ_single.'
                )

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
                        text=f'Binned K-S D = {D_val:.4f}<br>p = {p_val:.4f}',
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
                    'The K-S statistic (D) measures the maximum vertical '
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

        # ── Multi-sigma visualizations (after model explorer) ────────────
        if len(sigma_g) > 1:
            st.markdown('---')

            # Animated 4D figure
            st.markdown('### Animated 4D view  (σ_single as time axis)')
            st.caption('Use the Play button or drag the slider to step through σ_single values.')

            frames = []
            for i_s, sigma_val in enumerate(sigma_g):
                z_frame = ks_p_3d[i_s]
                bf_f, bp_f, _ = _best_point(z_frame, fbin_g, pi_g)
                frames.append(go.Frame(
                    data=[
                        go.Heatmap(
                            z=z_frame, x=pi_g, y=fbin_g,
                            colorscale='RdBu_r',
                            zmin=0.0,
                            zmax=float(np.percentile(ks_p_3d, 98)),
                            zsmooth='best',
                            colorbar=dict(title='K-S p-value', thickness=14),
                        ),
                        go.Scatter(
                            x=[bp_f], y=[bf_f],
                            mode='markers',
                            marker=dict(symbol='star', size=16, color='gold',
                                        line=dict(color='black', width=1)),
                        ),
                    ],
                    name=str(i_s),
                    layout=go.Layout(
                        title_text=(
                            f'K-S p-value  —  σ_single = {sigma_val:.1f} km/s  '
                            f'(best f_bin={bf_f:.3f}, π={bp_f:.2f})'
                        )
                    ),
                ))

            anim_layout: dict = {
                **PLOTLY_THEME,
                'title': 'Bias Correction — K-S p-value animated over σ_single',
                'xaxis_title': 'π  (period power-law index)',
                'yaxis_title': 'f_bin  (intrinsic binary fraction)',
                'updatemenus': [dict(
                    type='buttons',
                    showactive=False,
                    y=1.18, x=0.5, xanchor='center',
                    buttons=[
                        dict(
                            label='▶ Play',
                            method='animate',
                            args=[None, dict(
                                frame=dict(duration=900, redraw=True),
                                fromcurrent=True, mode='immediate',
                            )],
                        ),
                        dict(
                            label='⏸ Pause',
                            method='animate',
                            args=[[None], dict(
                                mode='immediate',
                                frame=dict(duration=0, redraw=False),
                            )],
                        ),
                    ],
                )],
                'sliders': [dict(
                    active=0,
                    currentvalue=dict(
                        prefix='σ_single = ', suffix=' km/s', visible=True,
                        font=dict(size=13),
                    ),
                    pad=dict(t=55),
                    steps=[
                        dict(
                            args=[[str(i_s)], dict(
                                mode='immediate',
                                frame=dict(duration=0, redraw=True),
                            )],
                            label=f'{float(sv):.1f}',
                            method='animate',
                        )
                        for i_s, sv in enumerate(sigma_g)
                    ],
                )],
                'height': _ch + 120,
                'margin': dict(l=60, r=20, t=80, b=80),
            }
            if _cw is not None:
                anim_layout['width'] = _cw

            fig4d = go.Figure(data=frames[0].data, frames=frames,
                              layout=go.Layout(**anim_layout))
            st.plotly_chart(fig4d, use_container_width=_use_cw, key=f'{p}_anim_4d')

            # 3D stacked heatmap
            st.markdown('### 3D Stacked View')
            st.caption(
                'Semi-transparent heatmap layers stacked along σ_single. '
                'Rotate and zoom with mouse.'
            )
            fig_3d = _make_3d_stacked_fig(
                ks_p_3d, fbin_g, pi_g, sigma_g,
                height=_ch + 200, width=_cw,
            )
            st.plotly_chart(fig_3d, use_container_width=_use_cw, key=f'{p}_3d_stacked')

            # Summary table
            summary_rows = []
            for i_s, sv in enumerate(sigma_g):
                bf_s, bp_s, bpv_s = _best_point(ks_p_3d[i_s], fbin_g, pi_g)
                summary_rows.append({
                    'σ_single (km/s)': round(float(sv), 2),
                    'Best f_bin': round(bf_s, 4),
                    'Best π': round(bp_s, 4),
                    'K-S p': round(bpv_s, 5),
                })
            st.dataframe(pd.DataFrame(summary_rows), use_container_width=True)

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

    # ── Left column: grid + orbital parameters ───────────────────────────────
    with lg_col_left:
        with st.expander('⚙️ Grid parameters', expanded=True):
            lg_fbin_min = st.number_input(
                'f_bin min', 0.0, 0.5, float(lg_cfg.get('fbin_min', 0.01)), 0.01,
                key=f'{p}_fbin_min',
                on_change=lambda: sm.save(['grid_langer', 'fbin_min'],
                                          value=st.session_state[f'{p}_fbin_min']))
            lg_fbin_max = st.number_input(
                'f_bin max', 0.5, 1.0, float(lg_cfg.get('fbin_max', 0.99)), 0.01,
                key=f'{p}_fbin_max',
                on_change=lambda: sm.save(['grid_langer', 'fbin_max'],
                                          value=st.session_state[f'{p}_fbin_max']))
            lg_fbin_steps = st.number_input(
                'f_bin steps', 10, 500, int(lg_cfg.get('fbin_steps', 100)), 1,
                key=f'{p}_fbin_steps',
                on_change=lambda: sm.save(['grid_langer', 'fbin_steps'],
                                          value=st.session_state[f'{p}_fbin_steps']))

            st.markdown('---')
            lg_sigma_min = st.number_input(
                'σ_single min (km/s)', 0.1, 100.0,
                float(lg_cfg.get('sigma_min', 1.0)), 0.1,
                key=f'{p}_sigma_min',
                on_change=lambda: sm.save(['grid_langer', 'sigma_min'],
                                          value=st.session_state[f'{p}_sigma_min']))
            lg_sigma_max = st.number_input(
                'σ_single max (km/s)', 0.5, 100.0,
                float(lg_cfg.get('sigma_max', 15.0)), 0.1,
                key=f'{p}_sigma_max',
                on_change=lambda: sm.save(['grid_langer', 'sigma_max'],
                                          value=st.session_state[f'{p}_sigma_max']))
            lg_sigma_steps = st.number_input(
                'σ_single steps', 5, 500, int(lg_cfg.get('sigma_steps', 30)), 1,
                key=f'{p}_sigma_steps',
                on_change=lambda: sm.save(['grid_langer', 'sigma_steps'],
                                          value=st.session_state[f'{p}_sigma_steps']))

            st.markdown('---')
            lg_n_stars = st.number_input(
                'N stars / point', 100, 50000, int(lg_cfg.get('n_stars_sim', 10000)), 100,
                key=f'{p}_n_stars',
                on_change=lambda: sm.save(['grid_langer', 'n_stars_sim'],
                                          value=st.session_state[f'{p}_n_stars']))
            lg_sigma_meas = st.number_input(
                'σ_measure (km/s)', 0.001, 20.0,
                float(lg_sim.get('sigma_measure', 1.622)), 0.001,
                format='%.3f', key=f'{p}_sigma_meas')

        with st.expander('🔧 Orbital parameters (Langer 2020)', expanded=False):
            st.caption('Period distribution: two-component mixture in log₁₀(P/days), '
                       'fitting the combined Langer+2020 Fig. 6 shape.')

            # --- Distribution type options (shared by both components) ---
            _pd_options = ['Gaussian', 'Log-normal', 'Reflected log-normal',
                           'Empirical (Langer Fig.)', 'Flat (uniform)']
            _pd_map = {'Gaussian': 'gaussian', 'Log-normal': 'lognormal',
                       'Reflected log-normal': 'reflected_lognormal',
                       'Empirical (Langer Fig.)': 'empirical',
                       'Flat (uniform)': 'flat'}
            _pd_inv = {v: k for k, v in _pd_map.items()}

            def _mu_label(dist_key):
                if dist_key in ('lognormal', 'reflected_lognormal'):
                    return 'mode'
                return 'mean'

            # Component 1 (short-period)
            st.markdown('**Component 1** (short-period)')
            _saved_dA = lg_pp.get('dist_A', 'gaussian')
            lg_dist_A_label = st.selectbox(
                'Distribution', _pd_options,
                index=_pd_options.index(_pd_inv.get(_saved_dA, _pd_options[0])),
                key=f'{p}_dist_A',
                on_change=lambda: sm.save(
                    ['grid_langer', 'langer_period_params', 'dist_A'],
                    value=_pd_map[st.session_state[f'{p}_dist_A']]))
            lg_dist_A = _pd_map[lg_dist_A_label]
            if lg_dist_A not in ('flat', 'empirical'):
                _cA1, _cA2 = st.columns(2)
                with _cA1:
                    lg_mu_A = st.number_input(
                        f'μ₁ ({_mu_label(lg_dist_A)})', 0.01, 10.0,
                        float(lg_pp.get('mu_A', 0.80)), 0.05, key=f'{p}_mu_A',
                        on_change=lambda: sm.save(
                            ['grid_langer', 'langer_period_params', 'mu_A'],
                            value=st.session_state[f'{p}_mu_A']))
                with _cA2:
                    lg_sigma_A = st.number_input(
                        'σ₁', 0.01, 5.0,
                        float(lg_pp.get('sigma_A', 0.35)), 0.01, key=f'{p}_sigma_A',
                        on_change=lambda: sm.save(
                            ['grid_langer', 'langer_period_params', 'sigma_A'],
                            value=st.session_state[f'{p}_sigma_A']))
            else:
                lg_mu_A, lg_sigma_A = 0.80, 0.35

            # Component 2 (long-period)
            st.markdown('**Component 2** (long-period)')
            _saved_dB = lg_pp.get('dist_B', 'reflected_lognormal')
            lg_dist_B_label = st.selectbox(
                'Distribution ', _pd_options,
                index=_pd_options.index(_pd_inv.get(_saved_dB, _pd_options[2])),
                key=f'{p}_dist_B',
                on_change=lambda: sm.save(
                    ['grid_langer', 'langer_period_params', 'dist_B'],
                    value=_pd_map[st.session_state[f'{p}_dist_B']]))
            lg_dist_B = _pd_map[lg_dist_B_label]
            if lg_dist_B not in ('flat', 'empirical'):
                _cB1, _cB2 = st.columns(2)
                with _cB1:
                    lg_mu_B = st.number_input(
                        f'μ₂ ({_mu_label(lg_dist_B)})', 0.01, 10.0,
                        float(lg_pp.get('mu_B', 2.0)), 0.05, key=f'{p}_mu_B',
                        on_change=lambda: sm.save(
                            ['grid_langer', 'langer_period_params', 'mu_B'],
                            value=st.session_state[f'{p}_mu_B']))
                with _cB2:
                    lg_sigma_B = st.number_input(
                        'σ₂', 0.01, 5.0,
                        float(lg_pp.get('sigma_B', 0.45)), 0.01, key=f'{p}_sigma_B',
                        on_change=lambda: sm.save(
                            ['grid_langer', 'langer_period_params', 'sigma_B'],
                            value=st.session_state[f'{p}_sigma_B']))
            else:
                lg_mu_B, lg_sigma_B = 2.0, 0.45

            # Mixture weight
            lg_weight_A = st.slider(
                'Weight of Component 1', 0.0, 1.0,
                float(lg_pp.get('weight_A', 0.20)), 0.01, key=f'{p}_weight_A',
                on_change=lambda: sm.save(
                    ['grid_langer', 'langer_period_params', 'weight_A'],
                    value=st.session_state[f'{p}_weight_A']))

            st.markdown('---')
            # Period range (clipping bounds)
            lg_logP_min = st.number_input(
                'log₁₀(P/days) min', 0.01, 5.0,
                float(lg_cfg.get('logP_min', 0.5)), 0.01, key=f'{p}_logP_min',
                on_change=lambda: sm.save(['grid_langer', 'logP_min'],
                                          value=st.session_state[f'{p}_logP_min']))
            lg_logP_max = st.number_input(
                'log₁₀(P/days) max', 0.1, 10.0,
                float(lg_cfg.get('logP_max', 3.5)), 0.1, key=f'{p}_logP_max',
                on_change=lambda: sm.save(['grid_langer', 'logP_max'],
                                          value=st.session_state[f'{p}_logP_max']))

            st.markdown('---')
            # Eccentricity — fixed at 0 per Langer assumption
            st.markdown('**Eccentricity:** fixed at e = 0 (Langer+2020 assumption)')

            st.markdown('---')
            # Primary mass
            lg_mass_model = st.selectbox(
                'Primary mass model', ['fixed', 'uniform'],
                index=['fixed', 'uniform'].index(
                    lg_cfg.get('mass_primary_model', 'fixed')),
                key=f'{p}_mass_model')
            if lg_mass_model == 'fixed':
                lg_mass_fixed = st.number_input(
                    'M₁ (M☉)', 1.0, 200.0,
                    float(lg_cfg.get('mass_primary_fixed', 10.0)), 1.0,
                    key=f'{p}_mass_fixed')
                lg_mass_range = (float(lg_mass_fixed), float(lg_mass_fixed))
            else:
                lg_mass_fixed = 10.0
                _lg_mr = lg_cfg.get('mass_primary_range', [10.0, 20.0])
                _lgmc1, _lgmc2 = st.columns(2)
                lg_mass_min_v = _lgmc1.number_input(
                    'M₁ min', 1.0, 200.0, float(_lg_mr[0]), 1.0, key=f'{p}_mass_min')
                lg_mass_max_v = _lgmc2.number_input(
                    'M₁ max', 1.0, 200.0, float(_lg_mr[1]), 1.0, key=f'{p}_mass_max')
                lg_mass_range = (float(lg_mass_min_v), float(lg_mass_max_v))

            st.markdown('---')
            # Mass ratio q — distribution type + range
            _q_dist_options = ['Flat (uniform)', 'Gaussian', 'Log-normal',
                               'Reflected log-normal',
                               'Empirical (Langer Fig.)']
            _q_dist_map = {'Flat (uniform)': 'flat', 'Gaussian': 'langer',
                           'Log-normal': 'lognormal',
                           'Reflected log-normal': 'reflected_lognormal',
                           'Empirical (Langer Fig.)': 'empirical'}
            _q_dist_inv = {v: k for k, v in _q_dist_map.items()}
            _saved_qm = lg_cfg.get('q_model', 'lognormal')
            lg_q_dist_label = st.selectbox(
                'Mass ratio q distribution', _q_dist_options,
                index=_q_dist_options.index(
                    _q_dist_inv.get(_saved_qm, _q_dist_options[2])),
                key=f'{p}_q_dist',
                on_change=lambda: sm.save(
                    ['grid_langer', 'q_model'],
                    value=_q_dist_map[st.session_state[f'{p}_q_dist']]))
            lg_q_model = _q_dist_map[lg_q_dist_label]

            if lg_q_model != 'empirical':
                _lg_qr = lg_cfg.get('q_range', [0.1, 2.0])
                _qc1, _qc2 = st.columns(2)
                with _qc1:
                    lg_q_min = st.number_input(
                        'q min', 0.01, 50.0, float(_lg_qr[0]), 0.05,
                        key=f'{p}_q_min',
                        on_change=lambda: sm.save(
                            ['grid_langer', 'q_range'],
                            value=[st.session_state[f'{p}_q_min'],
                                   st.session_state.get(f'{p}_q_max', 2.0)]))
                with _qc2:
                    lg_q_max = st.number_input(
                        'q max', 0.01, 50.0, float(_lg_qr[1]), 0.05,
                        key=f'{p}_q_max',
                        on_change=lambda: sm.save(
                            ['grid_langer', 'q_range'],
                            value=[st.session_state.get(f'{p}_q_min', 0.1),
                                   st.session_state[f'{p}_q_max']]))
            else:
                lg_q_min, lg_q_max = 0.1, 2.0
                st.caption('Sampling directly from digitized Langer+2020 Fig. 4')

            if lg_q_model not in ('flat', 'empirical'):
                _ql = _mu_label(lg_q_model) if lg_q_model in (
                    'lognormal', 'reflected_lognormal') else 'mean'
                lg_lq_mu = st.number_input(
                    f'q μ ({_ql})', 0.01, 50.0,
                    float(lg_cfg.get('langer_q_mu', 0.65)), 0.05,
                    key=f'{p}_lq_mu',
                    on_change=lambda: sm.save(
                        ['grid_langer', 'langer_q_mu'],
                        value=st.session_state[f'{p}_lq_mu']))
                lg_lq_sig = st.number_input(
                    'q σ', 0.01, 50.0,
                    float(lg_cfg.get('langer_q_sigma', 0.3)), 0.05,
                    key=f'{p}_lq_sig',
                    on_change=lambda: sm.save(
                        ['grid_langer', 'langer_q_sigma'],
                        value=st.session_state[f'{p}_lq_sig']))
            else:
                lg_lq_mu, lg_lq_sig = 0.65, 0.3

            # q convention note and flip toggle
            lg_q_flipped = st.checkbox(
                'Flip q (M_primary / M_companion)',
                value=bool(lg_cfg.get('q_flipped', False)),
                key=f'{p}_q_flipped',
                on_change=lambda: sm.save(
                    ['grid_langer', 'q_flipped'],
                    value=st.session_state[f'{p}_q_flipped']))
            if lg_q_flipped:
                st.caption('q = M_primary / M_companion (BH as primary). '
                           'M₂ = M₁ / q.')
            else:
                st.caption('q = M_companion / M_primary (BH as companion, '
                           'typically lighter). Langer Fig. 4: M_BH/M_OB '
                           'peaks at ~0.5–0.7. M₂ = M₁ × q.')
            _q_extra = (f', μ={lg_lq_mu}, σ={lg_lq_sig}'
                        if lg_q_model not in ('flat', 'empirical') else '')
            st.caption(f'Active: q_model="{lg_q_model}", '
                       f'range=[{lg_q_min}, {lg_q_max}]{_q_extra}')

    # ── Right column: actions + display ───────────────────────────────────────
    with lg_col_right:
        # Action row
        lg_max_proc = max(1, (os.cpu_count() or 2) - 1)
        _lg_ac1, _lg_ac2, _lg_ac3 = st.columns([0.15, 0.25, 0.60])
        lg_n_proc = _lg_ac1.number_input('Workers', 1, lg_max_proc, lg_max_proc,
                                          key=f'{p}_nproc')
        lg_view_mode = _lg_ac2.radio('View', ['K-S p-value', 'K-S D-statistic'],
                                      horizontal=True, key=f'{p}_view_mode')
        lg_show_d = lg_view_mode == 'K-S D-statistic'
        _lg_run_col, _lg_load_col, _lg_save_col = _lg_ac3.columns(3)
        _lg_job_running = bool(
            st.session_state.get(f'{p}_job', {}).get('status') == 'running')
        lg_run_btn = _lg_run_col.button(
            '▶️ Run Langer Grid', type='primary', key=f'{p}_run',
            disabled=_lg_job_running)
        if _lg_job_running:
            if _lg_run_col.button('⏹ Cancel', key=f'{p}_cancel'):
                st.session_state[f'{p}_job']['cancel'] = True
                st.rerun()

        # Load saved results dropdown (Langer)
        _saved_langer = _list_saved_results('langer')
        lg_load_btn = False
        if _saved_langer:
            with _lg_load_col.popover('📂 Load saved result'):
                st.caption(_FILENAME_FORMAT_HELP)
                _lg_load_options = [name for name, _ in _saved_langer]
                _lg_load_idx = st.selectbox(
                    'Select result file', range(len(_lg_load_options)),
                    format_func=lambda i: _lg_load_options[i],
                    key=f'{p}_load_select',
                )
                _lg_sel_path = _saved_langer[_lg_load_idx][1]
                try:
                    _lg_preview = np.load(_lg_sel_path, allow_pickle=True)
                    if 'timestamp' in _lg_preview:
                        st.caption(f"Saved: {str(_lg_preview['timestamp'])}")
                    if 'settings' in _lg_preview:
                        with st.expander('View settings'):
                            st.json(json.loads(str(_lg_preview['settings'])))
                    _lg_preview.close()
                except Exception:
                    pass
                if st.button('Load selected', key=f'{p}_load_sel_btn'):
                    _lg_loaded = dict(np.load(_lg_sel_path, allow_pickle=True))
                    st.session_state[f'{p}_result'] = _lg_loaded
                    st.toast(f'Loaded: {os.path.basename(_lg_sel_path)}')
                    lg_load_btn = True
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
                st.toast(f'Saved: {_lg_desc}')
            else:
                _lg_save_col.warning('No result to save. Run first.')

        # Display slots
        lg_progress_slot = st.empty()
        lg_status_slot   = st.empty()
        lg_heatmap_slot  = st.empty()
        lg_result_slot   = st.empty()

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
    if lg_run_btn and not _lg_job_running:
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
            'progress_text': 'Starting...', 'live_heatmap': None,
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
    if _lg_job is not None:
        if _lg_job['status'] == 'running':
            lg_progress_slot.progress(
                _lg_job['progress_pct'], text=_lg_job['progress_text'])
            if _lg_job.get('live_heatmap'):
                hd = _lg_job['live_heatmap']
                lg_heatmap_slot.plotly_chart(
                    _make_heatmap_fig(
                        hd['p'], hd['fbin'], hd['x'],
                        title='Langer 2020 — K-S p-value (live)',
                        show_d=lg_show_d, ks_d_2d=hd['d'],
                        height=_ch, width=_cw,
                        x_label='σ_single (km/s)', x_name='σ',
                        best_label_fmt='  f={fbin:.3f}, σ={x:.1f}, p={p:.3f}',
                    ), use_container_width=_use_cw)
            if _lg_job.get('live_status'):
                lg_status_slot.markdown(_lg_job['live_status'])

        elif _lg_job['status'] == 'done':
            _lg_res = _lg_job['result']
            st.session_state[f'{p}_result'] = _lg_res
            cached_load_grid_result.clear()
            _lg_elapsed = _lg_job.get('elapsed_total', 0)
            _lg_desc = _lg_job.get('desc_name', '')
            _lg_nc = _lg_job.get('n_cells_total', 0)
            lg_progress_slot.progress(
                1.0, text=f'Done in {_fmt_eta(_lg_elapsed)}.')
            lg_status_slot.success(
                f'Saved to results/{_lg_desc}  '
                f'({_lg_nc} cells computed in {_fmt_eta(_lg_elapsed)})')
            del st.session_state[f'{p}_job']

        elif _lg_job['status'] == 'error':
            lg_status_slot.error(
                f"Simulation failed:\n```\n{_lg_job['error']}\n```")
            del st.session_state[f'{p}_job']

        elif _lg_job['status'] == 'cancelled':
            lg_status_slot.warning('Simulation cancelled.')
            del st.session_state[f'{p}_job']

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
                    title='Langer 2020 — K-S p-value',
                    show_d=lg_show_d, ks_d_2d=lg_ks_D_2d,
                    height=_ch, width=_cw,
                    x_label='σ_single (km/s)',
                    x_name='σ',
                    best_label_fmt='  f={fbin:.3f}, σ={x:.1f}, p={p:.3f}',
                ),
                use_container_width=_use_cw,
            )

        # Best-fit point
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

        # ── Marginalization + HDI68 ───────────────────────────────────────────
        # Always compute posteriors (needed for corner plot); HDI from .npz if available
        lg_post_fbin  = np.sum(lg_ks_p_2d, axis=1)
        lg_post_sigma = np.sum(lg_ks_p_2d, axis=0)

        _lg_res = st.session_state.get(f'{p}_result', {})
        if 'mode_fbin' in _lg_res:
            lg_mode_fbin  = float(_lg_res['mode_fbin'])
            lg_lo_fbin    = float(_lg_res['lo_fbin'])
            lg_hi_fbin    = float(_lg_res['hi_fbin'])
            lg_mode_sigma = float(_lg_res['mode_sigma'])
            lg_lo_sigma   = float(_lg_res['lo_sigma'])
            lg_hi_sigma   = float(_lg_res['hi_sigma'])
        else:
            from wr_bias_simulation import compute_hdi68
            lg_mode_fbin, lg_lo_fbin, lg_hi_fbin = compute_hdi68(lg_fbin_g, lg_post_fbin)
            lg_mode_sigma, lg_lo_sigma, lg_hi_sigma = compute_hdi68(lg_sigma_g, lg_post_sigma)

        # Compute p-value at HDI mode (nearest grid point)
        _lg_mode_fb_idx = int(np.argmin(np.abs(lg_fbin_g - lg_mode_fbin)))
        _lg_mode_sig_idx = int(np.argmin(np.abs(lg_sigma_g - lg_mode_sigma)))
        _lg_mode_pval = float(lg_ks_p_2d[_lg_mode_fb_idx, _lg_mode_sig_idx])

        lg_result_slot.markdown(
            '| Parameter | Best fit (argmax) | Posterior mode ± 1σ |\n'
            '|---|---|---|\n'
            f'| f_bin | `{best_fbin_lg:.4f}` '
            f'| `{lg_mode_fbin:.4f}` +{lg_hi_fbin - lg_mode_fbin:.4f} '
            f'−{lg_mode_fbin - lg_lo_fbin:.4f} |\n'
            f'| σ_single (km/s) | `{best_sigma_lg:.1f}` '
            f'| `{lg_mode_sigma:.1f}` +{lg_hi_sigma - lg_mode_sigma:.1f} '
            f'−{lg_mode_sigma - lg_lo_sigma:.1f} |\n'
            f'| **K-S p** | `{best_pval_lg:.6f}` '
            f'| `{_lg_mode_pval:.6f}` |\n\n'
            f'**Observed fraction:**  '
            f'({lg_n_det}+{lg_bartzakos})/{lg_total_pop} = '
            f'**{(lg_n_det + lg_bartzakos) / lg_total_pop * 100:.1f}%**'
        )

        # ── Corner Plot (2 params: f_bin × σ_single) ─────────────────────────
        st.markdown('---')
        st.markdown('### Marginalized Posteriors (Corner Plot)')

        from plotly.subplots import make_subplots as _lg_corner_subplots

        _lg_n_params = 2
        _lg_param_names = ['f_bin', 'σ_single']
        _lg_param_grids = [lg_fbin_g, lg_sigma_g]
        _lg_param_posts = [lg_post_fbin, lg_post_sigma]
        _lg_param_modes = [lg_mode_fbin, lg_mode_sigma]
        _lg_param_los   = [lg_lo_fbin, lg_lo_sigma]
        _lg_param_his   = [lg_hi_fbin, lg_hi_sigma]

        fig_lg_corner = _lg_corner_subplots(
            rows=_lg_n_params, cols=_lg_n_params,
            horizontal_spacing=0.08, vertical_spacing=0.08,
        )

        for i in range(_lg_n_params):
            # Diagonal: 1D posterior
            _lg_area = float(np.trapezoid(_lg_param_posts[i], _lg_param_grids[i]))
            _lg_pn = _lg_param_posts[i] / _lg_area if _lg_area > 0 else _lg_param_posts[i]

            fig_lg_corner.add_trace(go.Scatter(
                x=_lg_param_grids[i], y=_lg_pn,
                mode='lines', line=dict(color='#4A90D9', width=2),
                showlegend=False,
            ), row=i + 1, col=i + 1)

            # HDI68 shading
            _lg_mask = ((_lg_param_grids[i] >= _lg_param_los[i]) &
                        (_lg_param_grids[i] <= _lg_param_his[i]))
            _lg_xh = _lg_param_grids[i][_lg_mask]
            _lg_yh = _lg_pn[_lg_mask]
            if len(_lg_xh) > 0:
                fig_lg_corner.add_trace(go.Scatter(
                    x=np.concatenate([_lg_xh, _lg_xh[::-1]]),
                    y=np.concatenate([_lg_yh, np.zeros(len(_lg_yh))]),
                    fill='toself', fillcolor='rgba(74,144,217,0.3)',
                    line=dict(width=0), showlegend=False,
                ), row=i + 1, col=i + 1)

            # Mode line
            fig_lg_corner.add_vline(
                x=_lg_param_modes[i], line_dash='dash',
                line_color='#E25A53', line_width=1.5,
                row=i + 1, col=i + 1,
            )

            # Off-diagonal: 2D heatmap (lower triangle)
            for j in range(i):
                # For 2 params, axes are: param0=f_bin→axis0, param1=σ→axis1
                # ks_p_2d shape is [n_fbin, n_sigma]
                # For cell (i=1, j=0): x=f_bin (j=0), y=σ (i=1)
                # z needs to be [n_y, n_x] = [n_sigma, n_fbin] = ks_p_2d.T
                _lg_z = lg_ks_p_2d.T
                _lg_z_valid = _lg_z[~np.isnan(_lg_z)]
                _lg_z_max = float(np.percentile(_lg_z_valid, 98)) if _lg_z_valid.size > 0 else 1.0
                fig_lg_corner.add_trace(go.Heatmap(
                    x=_lg_param_grids[j], y=_lg_param_grids[i],
                    z=_lg_z,
                    colorscale='RdBu_r', zmin=0.0, zmax=_lg_z_max,
                    zsmooth='best', showscale=False,
                    hovertemplate=f'{_lg_param_names[j]}=%{{x:.4f}}<br>'
                                 f'{_lg_param_names[i]}=%{{y:.4f}}<br>'
                                 f'p=%{{z:.4f}}<extra></extra>',
                ), row=i + 1, col=j + 1)

                # Contour lines for 68% and 95% credible regions
                _lg_z_flat = _lg_z.ravel()
                _lg_z_pos = _lg_z_flat[_lg_z_flat > 0]
                if len(_lg_z_pos) > 2:
                    _lg_z_sorted = np.sort(_lg_z_pos)[::-1]
                    _lg_z_cumsum = np.cumsum(_lg_z_sorted)
                    _lg_z_cumsum = _lg_z_cumsum / _lg_z_cumsum[-1]
                    _lg_idx_68 = np.searchsorted(_lg_z_cumsum, 0.68)
                    _lg_idx_95 = np.searchsorted(_lg_z_cumsum, 0.95)
                    _lg_lvl_68 = float(_lg_z_sorted[min(_lg_idx_68, len(_lg_z_sorted) - 1)])
                    _lg_lvl_95 = float(_lg_z_sorted[min(_lg_idx_95, len(_lg_z_sorted) - 1)])
                    fig_lg_corner.add_trace(go.Contour(
                        x=_lg_param_grids[j], y=_lg_param_grids[i],
                        z=_lg_z,
                        contours=dict(
                            coloring='none', showlabels=True,
                            labelfont=dict(size=8, color=pal['contour_label']),
                        ),
                        ncontours=2,
                        contours_start=_lg_lvl_95,
                        contours_end=_lg_lvl_68,
                        line=dict(color=pal['contour_color'], width=1.5, dash='dot'),
                        showscale=False, hoverinfo='skip',
                    ), row=i + 1, col=j + 1)

                fig_lg_corner.add_trace(go.Scatter(
                    x=[_lg_param_modes[j]], y=[_lg_param_modes[i]],
                    mode='markers',
                    marker=dict(symbol='star', size=10, color='#DAA520',
                                line=dict(color='black', width=1)),
                    showlegend=False,
                ), row=i + 1, col=j + 1)

        # Axis labels
        for i in range(_lg_n_params):
            fig_lg_corner.update_xaxes(title_text=_lg_param_names[i],
                                        row=_lg_n_params, col=i + 1)
            if i > 0:
                fig_lg_corner.update_yaxes(title_text=_lg_param_names[i],
                                            row=i + 1, col=1)

        # Hide upper triangle
        for i in range(_lg_n_params):
            for j in range(i + 1, _lg_n_params):
                fig_lg_corner.update_xaxes(visible=False, row=i + 1, col=j + 1)
                fig_lg_corner.update_yaxes(visible=False, row=i + 1, col=j + 1)

        fig_lg_corner.update_layout(
            **PLOTLY_THEME,
            height=250 * _lg_n_params,
            width=250 * _lg_n_params,
            showlegend=False,
            margin=dict(l=60, r=20, t=30, b=60),
        )
        st.plotly_chart(fig_lg_corner, use_container_width=True, key=f'{p}_corner_plot')
        st.caption(
            f'Marginalized posteriors (Langer 2020 model). '
            f'**Diagonal:** 1D posteriors with mode (dashed red) and '
            f'68% HDI (blue shading). '
            f'**Off-diagonal:** 2D K-S p-value with best-fit (gold star). '
            f'f_bin = {lg_mode_fbin:.4f} '
            f'(+{lg_hi_fbin - lg_mode_fbin:.4f}/-{lg_mode_fbin - lg_lo_fbin:.4f}), '
            f'σ = {lg_mode_sigma:.1f} '
            f'(+{lg_hi_sigma - lg_mode_sigma:.1f}/-{lg_mode_sigma - lg_lo_sigma:.1f}) km/s.'
        )

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
                        text=f'Binned K-S D = {lg_D_val:.4f}<br>p = {lg_p_val:.4f}',
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

        # ── Summary table ─────────────────────────────────────────────────────
        st.markdown('---')
        lg_summary_rows = []
        for i_f in range(len(lg_fbin_g)):
            bf_v = float(lg_fbin_g[i_f])
            for i_s in range(len(lg_sigma_g)):
                sv = float(lg_sigma_g[i_s])
                pv = float(lg_ks_p_2d[i_f, i_s])
                if pv == float(np.nanmax(lg_ks_p_2d)):
                    lg_summary_rows.append({
                        'f_bin': round(bf_v, 4),
                        'σ_single (km/s)': round(sv, 2),
                        'K-S p': round(pv, 5),
                    })
        if lg_summary_rows:
            st.markdown('### Best Grid Point')
            st.dataframe(pd.DataFrame(lg_summary_rows), use_container_width=True)



# ─────────────────────────────────────────────────────────────────────────────
# Compare tab renderer
# ─────────────────────────────────────────────────────────────────────────────
def _render_compare_tab(p: str) -> None:
    """Render a comparison tab for two saved bias correction results.

    Parameters
    ----------
    p : str
        Unique prefix for session-state keys (e.g. 'cmp', 'cmp2').
    """
    pal = get_palette()

    st.markdown('### Compare two saved results')
    st.caption('Load any two saved result files and compare them side-by-side or overlaid.')

    # ── List all available results (both models) ─────────────────────────
    all_results = []
    for model in ('dsilva', 'langer'):
        for name, path in _list_saved_results(model):
            all_results.append((f'[{model}] {name}', path))

    if len(all_results) < 2:
        st.info('Need at least 2 saved result files to compare. Run some simulations first!')
        return

    names = [n for n, _ in all_results]
    paths = {n: fp for n, fp in all_results}

    col_a, col_b = st.columns(2)
    with col_a:
        sel_a = st.selectbox('Result A', names, index=0, key=f'{p}_sel_a')
    with col_b:
        default_b = min(1, len(names) - 1)
        sel_b = st.selectbox('Result B', names, index=default_b, key=f'{p}_sel_b')

    if sel_a == sel_b:
        st.warning('Select two different results to compare.')
        return

    # Load both results
    try:
        res_a = dict(np.load(paths[sel_a], allow_pickle=True))
        res_b = dict(np.load(paths[sel_b], allow_pickle=True))
    except Exception as e:
        st.error(f'Error loading results: {e}')
        return

    # ── View mode toggle ─────────────────────────────────────────────────
    view_mode = st.radio(
        'View mode', ['Side-by-side', 'Overlay'],
        horizontal=True, key=f'{p}_view_mode'
    )

    st.markdown('---')

    # ── Extract common arrays ────────────────────────────────────────────
    def _get_arrays(res, label):
        """Extract heatmap arrays and axis values from a result dict.

        Handles both stored key naming conventions:
          Dsilva: ks_p shape (logPmax, sigma, fbin, pi) or (sigma, fbin, pi)
          Langer: ks_p shape (fbin, sigma)
        """
        info = {'label': label, 'settings': {}, 'heatmap': None, 'type': 'unknown'}
        ks_p = res.get('ks_p', None)
        if ks_p is None:
            return info

        fbin_vals = res.get('fbin_grid', np.array([]))
        sigma_vals = res.get('sigma_grid', np.array([]))
        pi_vals = res.get('pi_grid', np.array([]))
        logPmax_vals = res.get('logPmax_grid', np.array([]))

        if pi_vals.size > 0:
            # Dsilva-style: has pi dimension
            info['type'] = 'dsilva'
            info['fbin_vals'] = fbin_vals
            info['pi_vals'] = pi_vals
            info['sigma_vals'] = sigma_vals
            info['logPmax_vals'] = logPmax_vals
            info['ks_p_full'] = ks_p

            # Collapse to best 2D slice (fbin × pi) for heatmap display
            if ks_p.ndim == 4:
                # shape: (logPmax, sigma, fbin, pi) — find global best
                flat_idx = int(np.nanargmax(ks_p))
                idx = np.unravel_index(flat_idx, ks_p.shape)
                info['best_logPmax_idx'] = idx[0]
                info['best_sigma_idx'] = idx[1]
                info['heatmap'] = ks_p[idx[0], idx[1]]  # (fbin, pi)
                info['best_fbin'] = float(fbin_vals[idx[2]])
                info['best_pi'] = float(pi_vals[idx[3]])
                info['best_sigma'] = float(sigma_vals[idx[1]]) if sigma_vals.size > 0 else None
                info['best_logPmax'] = float(logPmax_vals[idx[0]]) if logPmax_vals.size > 0 else None
                info['best_pval'] = float(ks_p[idx])
            elif ks_p.ndim == 3:
                # shape: (sigma, fbin, pi)
                flat_idx = int(np.nanargmax(ks_p))
                idx = np.unravel_index(flat_idx, ks_p.shape)
                info['best_sigma_idx'] = idx[0]
                info['heatmap'] = ks_p[idx[0]]
                info['best_fbin'] = float(fbin_vals[idx[1]])
                info['best_pi'] = float(pi_vals[idx[2]])
                info['best_sigma'] = float(sigma_vals[idx[0]]) if sigma_vals.size > 0 else None
                info['best_pval'] = float(ks_p[idx])
            elif ks_p.ndim == 2:
                info['heatmap'] = ks_p
                flat_idx = int(np.nanargmax(ks_p))
                idx = np.unravel_index(flat_idx, ks_p.shape)
                info['best_fbin'] = float(fbin_vals[idx[0]])
                info['best_pi'] = float(pi_vals[idx[1]])
                info['best_pval'] = float(ks_p[idx])
            info['x_vals'] = pi_vals
            info['x_label'] = 'π'
        else:
            # Langer-style: 2D (fbin × sigma)
            info['type'] = 'langer'
            info['fbin_vals'] = fbin_vals
            info['sigma_vals'] = sigma_vals
            info['x_vals'] = sigma_vals
            info['x_label'] = 'σ_single'
            info['ks_p_full'] = ks_p
            if ks_p.ndim == 2:
                info['heatmap'] = ks_p
                flat_idx = int(np.nanargmax(ks_p))
                idx = np.unravel_index(flat_idx, ks_p.shape)
                info['best_fbin'] = float(fbin_vals[idx[0]])
                info['best_sigma'] = float(sigma_vals[idx[1]])
                info['best_pval'] = float(ks_p[idx])

        # Pre-computed HDI68 values (if saved in .npz)
        for _hk in ('mode_fbin', 'lo_fbin', 'hi_fbin',
                     'mode_pi', 'lo_pi', 'hi_pi',
                     'mode_sigma', 'lo_sigma', 'hi_sigma',
                     'mode_logPmax', 'lo_logPmax', 'hi_logPmax'):
            if _hk in res:
                info[_hk] = float(res[_hk])

        # Settings JSON
        if 'settings' in res:
            try:
                info['settings'] = json.loads(str(res['settings']))
            except Exception:
                info['settings'] = {}
        return info

    info_a = _get_arrays(res_a, sel_a)
    info_b = _get_arrays(res_b, sel_b)

    # ── Run parameters for each result ───────────────────────────────────
    def _format_run_params(info, res):
        """Build a markdown summary of run parameters."""
        s = info.get('settings', {})
        fbin = info.get('fbin_vals', np.array([]))
        x = info.get('x_vals', np.array([]))
        sigma = info.get('sigma_vals', np.array([]))
        logPmax = info.get('logPmax_vals', np.array([]))
        ts = str(res.get('timestamp', '—'))

        lines = []
        lines.append(f"**Model:** {info['type'].title()}")
        lines.append(f"**Timestamp:** {ts}")
        lines.append(f"**N stars:** {s.get('n_stars_sim', '—')}")
        lines.append(f"**σ_measure:** {s.get('sigma_measure', '—')} km/s")
        if fbin.size > 0:
            lines.append(f"**f_bin:** [{fbin[0]:.3f}, {fbin[-1]:.3f}] × {fbin.size} steps")
        if info['type'] == 'dsilva':
            pi = info.get('pi_vals', np.array([]))
            if pi.size > 0:
                lines.append(f"**π:** [{pi[0]:.2f}, {pi[-1]:.2f}] × {pi.size} steps")
        if sigma.size > 0:
            if sigma.size == 1:
                lines.append(f"**σ_single:** {sigma[0]:.2f} km/s")
            else:
                lines.append(f"**σ_single:** [{sigma[0]:.2f}, {sigma[-1]:.2f}] × {sigma.size} steps")
        if logPmax.size > 0:
            if logPmax.size == 1:
                lines.append(f"**logP_max:** {logPmax[0]:.2f}")
            else:
                lines.append(f"**logP_max:** [{logPmax[0]:.2f}, {logPmax[-1]:.2f}] × {logPmax.size} steps")
        lines.append(f"**logP range:** [{s.get('logP_min', '—')}, {s.get('logP_max', '—')}]")

        # Orbital params if present
        orb = s.get('orbital', {})
        if orb:
            lines.append(f"**e_model:** {orb.get('e_model', '—')}, e_max={orb.get('e_max', '—')}")
            lines.append(f"**q_model:** {orb.get('q_model', '—')}, range=[{orb.get('q_range', '—')}]")
            lines.append(f"**M₁:** {orb.get('mass_primary_model', '—')}, {orb.get('mass_primary_fixed', '—')} M⊙")

        # Langer period params
        lp = s.get('langer_period_params', {})
        if lp:
            lines.append(
                f"**Period model:** C1={lp.get('dist_A','gauss')}(μ={lp.get('mu_A','—')}, σ={lp.get('sigma_A','—')}), "
                f"C2={lp.get('dist_B','logn')}(μ={lp.get('mu_B','—')}, σ={lp.get('sigma_B','—')}), "
                f"w₁={lp.get('weight_A','—')}")

        return '\n\n'.join(lines)

    _pc1, _pc2 = st.columns(2)
    with _pc1:
        with st.expander(f'📋 Run A parameters', expanded=True):
            st.markdown(_format_run_params(info_a, res_a))
    with _pc2:
        with st.expander(f'📋 Run B parameters', expanded=True):
            st.markdown(_format_run_params(info_b, res_b))

    # ── Pre-compute HDI68 for table (needs heatmaps) ────────────────────
    from wr_bias_simulation import compute_hdi68 as _cmp_hdi68

    def _marginalize_1d(heatmap_2d, axis_vals, axis=1):
        """Marginalize 2D heatmap along given axis to get 1D posterior."""
        post = np.nansum(heatmap_2d, axis=axis)
        if post.sum() > 0 and len(axis_vals) == len(post):
            area = np.trapezoid(post, axis_vals)
            if area > 0:
                post = post / area
        return post

    def _get_hdi(info, param, grid, post):
        """Return (mode, lo, hi) from pre-computed keys or compute on-the-fly."""
        mk, lk, hk = f'mode_{param}', f'lo_{param}', f'hi_{param}'
        if mk in info and lk in info and hk in info:
            return info[mk], info[lk], info[hk]
        return _cmp_hdi68(grid, post)

    def _fmt_mode_err(mode, lo, hi, fmt='.4f'):
        return f'`{mode:{fmt}}` +{hi - mode:{fmt}} −{mode - lo:{fmt}}'

    # Compute posteriors + HDI for both results
    _hdi_a = _hdi_b = {}
    if info_a['heatmap'] is not None:
        _post_fb_a = _marginalize_1d(info_a['heatmap'], info_a['x_vals'], axis=1)
        _post_x_a  = _marginalize_1d(info_a['heatmap'], info_a['fbin_vals'], axis=0)
        _xp_a = 'pi' if info_a['type'] == 'dsilva' else 'sigma'
        _m_fb_a, _lo_fb_a, _hi_fb_a = _get_hdi(info_a, 'fbin', info_a['fbin_vals'], _post_fb_a)
        _m_x_a, _lo_x_a, _hi_x_a   = _get_hdi(info_a, _xp_a, info_a['x_vals'], _post_x_a)
        _hdi_a = {'fbin': (_m_fb_a, _lo_fb_a, _hi_fb_a),
                  'x': (_m_x_a, _lo_x_a, _hi_x_a),
                  'post_fbin': _post_fb_a, 'post_x': _post_x_a}
    if info_b['heatmap'] is not None:
        _post_fb_b = _marginalize_1d(info_b['heatmap'], info_b['x_vals'], axis=1)
        _post_x_b  = _marginalize_1d(info_b['heatmap'], info_b['fbin_vals'], axis=0)
        _xp_b = 'pi' if info_b['type'] == 'dsilva' else 'sigma'
        _m_fb_b, _lo_fb_b, _hi_fb_b = _get_hdi(info_b, 'fbin', info_b['fbin_vals'], _post_fb_b)
        _m_x_b, _lo_x_b, _hi_x_b   = _get_hdi(info_b, _xp_b, info_b['x_vals'], _post_x_b)
        _hdi_b = {'fbin': (_m_fb_b, _lo_fb_b, _hi_fb_b),
                  'x': (_m_x_b, _lo_x_b, _hi_x_b),
                  'post_fbin': _post_fb_b, 'post_x': _post_x_b}

    # ── Best-fit comparison table (with HDI68 errors) ─────────────────
    st.markdown('### Best-fit comparison')
    _tbl = '| Parameter | Best-fit A | Mode ± 1σ A | Best-fit B | Mode ± 1σ B |\n'
    _tbl += '|---|---|---|---|---|\n'

    # f_bin
    _bf_a = f"`{info_a.get('best_fbin', 0):.4f}`" if 'best_fbin' in info_a else '—'
    _bf_b = f"`{info_b.get('best_fbin', 0):.4f}`" if 'best_fbin' in info_b else '—'
    _hdi_a_fb = _fmt_mode_err(*_hdi_a['fbin']) if 'fbin' in _hdi_a else '—'
    _hdi_b_fb = _fmt_mode_err(*_hdi_b['fbin']) if 'fbin' in _hdi_b else '—'
    _tbl += f'| f_bin | {_bf_a} | {_hdi_a_fb} | {_bf_b} | {_hdi_b_fb} |\n'

    # π (Dsilva only)
    if 'best_pi' in info_a or 'best_pi' in info_b:
        _bp_a = f"`{info_a['best_pi']:.4f}`" if 'best_pi' in info_a else '—'
        _bp_b = f"`{info_b['best_pi']:.4f}`" if 'best_pi' in info_b else '—'
        _hp_a = _fmt_mode_err(*_hdi_a['x']) if ('x' in _hdi_a and info_a['type'] == 'dsilva') else '—'
        _hp_b = _fmt_mode_err(*_hdi_b['x']) if ('x' in _hdi_b and info_b['type'] == 'dsilva') else '—'
        _tbl += f'| π | {_bp_a} | {_hp_a} | {_bp_b} | {_hp_b} |\n'

    # σ_single
    if 'best_sigma' in info_a or 'best_sigma' in info_b:
        _bs_a = f"`{info_a['best_sigma']:.2f}`" if info_a.get('best_sigma') is not None else '—'
        _bs_b = f"`{info_b['best_sigma']:.2f}`" if info_b.get('best_sigma') is not None else '—'
        _hs_a = _fmt_mode_err(*_hdi_a['x'], fmt='.2f') if ('x' in _hdi_a and info_a['type'] == 'langer') else '—'
        _hs_b = _fmt_mode_err(*_hdi_b['x'], fmt='.2f') if ('x' in _hdi_b and info_b['type'] == 'langer') else '—'
        _tbl += f'| σ_single | {_bs_a} | {_hs_a} | {_bs_b} | {_hs_b} |\n'

    # logP_max
    if 'best_logPmax' in info_a or 'best_logPmax' in info_b:
        _bl_a = f"`{info_a['best_logPmax']:.2f}`" if info_a.get('best_logPmax') is not None else '—'
        _bl_b = f"`{info_b['best_logPmax']:.2f}`" if info_b.get('best_logPmax') is not None else '—'
        _tbl += f'| logP_max | {_bl_a} | — | {_bl_b} | — |\n'

    # K-S p-value
    _pv_a = f"`{info_a.get('best_pval', 0):.5f}`" if 'best_pval' in info_a else '—'
    _pv_b = f"`{info_b.get('best_pval', 0):.5f}`" if 'best_pval' in info_b else '—'
    _tbl += f'| K-S p-value | {_pv_a} | — | {_pv_b} | — |\n'

    # Model
    _tbl += f"| Model | {info_a['type']} | — | {info_b['type']} | — |\n"

    st.markdown(_tbl)

    # ── Parameter comparison table ───────────────────────────────────────
    with st.expander('📊 Settings comparison', expanded=False):
        rows = []
        all_keys = sorted(set(list(info_a['settings'].keys()) + list(info_b['settings'].keys())))
        for k in all_keys:
            va = info_a['settings'].get(k, '—')
            vb = info_b['settings'].get(k, '—')
            match = '✓' if str(va) == str(vb) else '✗'
            rows.append({'Parameter': k, 'Result A': str(va), 'Result B': str(vb), 'Match': match})
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    # ── Heatmaps ─────────────────────────────────────────────────────────
    if info_a['heatmap'] is not None and info_b['heatmap'] is not None:
        st.markdown('### K-S p-value heatmaps')

        if view_mode == 'Side-by-side':
            hc1, hc2 = st.columns(2)
            with hc1:
                st.markdown(f'**A: {info_a["label"][:40]}**')
                fig_a = _make_heatmap_fig(
                    info_a['heatmap'],
                    info_a['fbin_vals'], info_a['x_vals'],
                    title=f'K-S p-value — A ({info_a["type"]})',
                    x_label=info_a['x_label'],
                    height=400,
                )
                st.plotly_chart(fig_a, use_container_width=True, key=f'{p}_hm_a')
            with hc2:
                st.markdown(f'**B: {info_b["label"][:40]}**')
                fig_b = _make_heatmap_fig(
                    info_b['heatmap'],
                    info_b['fbin_vals'], info_b['x_vals'],
                    title=f'K-S p-value — B ({info_b["type"]})',
                    x_label=info_b['x_label'],
                    height=400,
                )
                st.plotly_chart(fig_b, use_container_width=True, key=f'{p}_hm_b')

        else:  # Overlay — contour overlay on same axes if compatible
            if (info_a['type'] == info_b['type']
                    and info_a['heatmap'].shape == info_b['heatmap'].shape):
                fig = go.Figure()
                fig.add_trace(go.Heatmap(
                    z=info_a['heatmap'],
                    x=info_a['x_vals'], y=info_a['fbin_vals'],
                    colorscale='Blues', opacity=0.6,
                    name=info_a['label'],
                    colorbar=dict(title='A p-val', x=1.0),
                ))
                fig.add_trace(go.Contour(
                    z=info_b['heatmap'],
                    x=info_b['x_vals'], y=info_b['fbin_vals'],
                    contours=dict(coloring='lines', showlabels=True),
                    line=dict(color='red', width=2, dash='dot'),
                    name=info_b['label'],
                    colorbar=dict(title='B p-val', x=1.12),
                    showscale=True,
                ))
                fig.update_layout(**{
                    **PLOTLY_THEME,
                    'title': dict(text='K-S p-value overlay'),
                    'xaxis_title': info_a['x_label'],
                    'yaxis_title': 'f_bin',
                    'height': 500,
                })
                st.plotly_chart(fig, use_container_width=True, key=f'{p}_hm_overlay')
            else:
                st.info('Overlay requires same model type and grid dimensions. Showing side-by-side.')
                hc1, hc2 = st.columns(2)
                with hc1:
                    st.markdown(f'**A: {info_a["label"][:40]}**')
                    fig_a = _make_heatmap_fig(
                        info_a['heatmap'],
                        info_a['fbin_vals'], info_a['x_vals'],
                        title=f'K-S p-value — A ({info_a["type"]})',
                        x_label=info_a['x_label'], height=400,
                    )
                    st.plotly_chart(fig_a, use_container_width=True, key=f'{p}_hm_a2')
                with hc2:
                    st.markdown(f'**B: {info_b["label"][:40]}**')
                    fig_b = _make_heatmap_fig(
                        info_b['heatmap'],
                        info_b['fbin_vals'], info_b['x_vals'],
                        title=f'K-S p-value — B ({info_b["type"]})',
                        x_label=info_b['x_label'], height=400,
                    )
                    st.plotly_chart(fig_b, use_container_width=True, key=f'{p}_hm_b2')

    # ── 1D Posteriors with HDI68 errors ─────────────────────────────────
    if info_a['heatmap'] is not None and info_b['heatmap'] is not None:
        st.markdown('### 1D Posteriors (with 68% HDI errors)')

        # Reuse posteriors + HDI computed above for the best-fit table
        post_fbin_a = _hdi_a.get('post_fbin', np.array([]))
        post_fbin_b = _hdi_b.get('post_fbin', np.array([]))
        post_x_a    = _hdi_a.get('post_x', np.array([]))
        post_x_b    = _hdi_b.get('post_x', np.array([]))
        mode_fbin_a, lo_fbin_a, hi_fbin_a = _hdi_a.get('fbin', (0, 0, 0))
        mode_fbin_b, lo_fbin_b, hi_fbin_b = _hdi_b.get('fbin', (0, 0, 0))
        mode_x_a, lo_x_a, hi_x_a = _hdi_a.get('x', (0, 0, 0))
        mode_x_b, lo_x_b, hi_x_b = _hdi_b.get('x', (0, 0, 0))

        def _add_hdi_shading(fig, grid, post, lo, hi, color, opacity=0.15):
            """Add HDI68 shaded region to a posterior plot."""
            mask = (grid >= lo) & (grid <= hi)
            x_hdi = grid[mask]
            y_hdi = post[mask]
            if len(x_hdi) > 0:
                fig.add_trace(go.Scatter(
                    x=np.concatenate([x_hdi, x_hdi[::-1]]),
                    y=np.concatenate([y_hdi, np.zeros(len(y_hdi))]),
                    fill='toself', fillcolor=color,
                    line=dict(width=0), opacity=opacity,
                    showlegend=False, hoverinfo='skip',
                ))

        def _add_mode_line(fig, mode_val, color):
            """Add vertical dashed line at posterior mode."""
            fig.add_vline(x=mode_val, line=dict(color=color, width=1.5, dash='dash'))

        if view_mode == 'Side-by-side':
            pc1, pc2 = st.columns(2)
            with pc1:
                st.markdown('**f_bin**')
                fig_pa = go.Figure()
                fig_pa.add_trace(go.Scatter(
                    x=info_a['fbin_vals'], y=post_fbin_a,
                    mode='lines', line=dict(color='#4A90D9', width=2),
                    name='A',
                ))
                _add_hdi_shading(fig_pa, info_a['fbin_vals'], post_fbin_a,
                                 lo_fbin_a, hi_fbin_a, 'rgba(74,144,217,0.2)')
                _add_mode_line(fig_pa, mode_fbin_a, '#4A90D9')
                fig_pa.add_trace(go.Scatter(
                    x=info_b['fbin_vals'], y=post_fbin_b,
                    mode='lines', line=dict(color='#E25A53', width=2, dash='dash'),
                    name='B',
                ))
                _add_hdi_shading(fig_pa, info_b['fbin_vals'], post_fbin_b,
                                 lo_fbin_b, hi_fbin_b, 'rgba(226,90,83,0.2)')
                _add_mode_line(fig_pa, mode_fbin_b, '#E25A53')
                fig_pa.update_layout(**{**PLOTLY_THEME, 'title': dict(text='f_bin posterior'), 'height': 350,
                                        'xaxis_title': 'f_bin', 'yaxis_title': 'Posterior density'})
                st.plotly_chart(fig_pa, use_container_width=True, key=f'{p}_post_fbin')
            with pc2:
                st.markdown(f'**{info_a["x_label"]} / {info_b["x_label"]}**')
                fig_pb = go.Figure()
                fig_pb.add_trace(go.Scatter(
                    x=info_a['x_vals'], y=post_x_a,
                    mode='lines', line=dict(color='#4A90D9', width=2),
                    name='A',
                ))
                _add_hdi_shading(fig_pb, info_a['x_vals'], post_x_a,
                                 lo_x_a, hi_x_a, 'rgba(74,144,217,0.2)')
                _add_mode_line(fig_pb, mode_x_a, '#4A90D9')
                fig_pb.add_trace(go.Scatter(
                    x=info_b['x_vals'], y=post_x_b,
                    mode='lines', line=dict(color='#E25A53', width=2, dash='dash'),
                    name='B',
                ))
                _add_hdi_shading(fig_pb, info_b['x_vals'], post_x_b,
                                 lo_x_b, hi_x_b, 'rgba(226,90,83,0.2)')
                _add_mode_line(fig_pb, mode_x_b, '#E25A53')
                fig_pb.update_layout(**{**PLOTLY_THEME, 'title': dict(text=f'{info_a["x_label"]} posterior'), 'height': 350,
                                        'xaxis_title': info_a['x_label'], 'yaxis_title': 'Posterior density'})
                st.plotly_chart(fig_pb, use_container_width=True, key=f'{p}_post_x')
        else:  # Overlay — both posteriors on single plots
            fig_po = go.Figure()
            fig_po.add_trace(go.Scatter(
                x=info_a['fbin_vals'], y=post_fbin_a,
                mode='lines', line=dict(color='#4A90D9', width=2),
                name=f'A: f_bin',
            ))
            _add_hdi_shading(fig_po, info_a['fbin_vals'], post_fbin_a,
                             lo_fbin_a, hi_fbin_a, 'rgba(74,144,217,0.2)')
            _add_mode_line(fig_po, mode_fbin_a, '#4A90D9')
            fig_po.add_trace(go.Scatter(
                x=info_b['fbin_vals'], y=post_fbin_b,
                mode='lines', line=dict(color='#E25A53', width=2, dash='dash'),
                name=f'B: f_bin',
            ))
            _add_hdi_shading(fig_po, info_b['fbin_vals'], post_fbin_b,
                             lo_fbin_b, hi_fbin_b, 'rgba(226,90,83,0.2)')
            _add_mode_line(fig_po, mode_fbin_b, '#E25A53')
            fig_po.update_layout(**{
                **PLOTLY_THEME,
                'title': dict(text='f_bin posterior comparison'),
                'xaxis_title': 'f_bin',
                'yaxis_title': 'Posterior density',
                'height': 400,
            })
            st.plotly_chart(fig_po, use_container_width=True, key=f'{p}_post_overlay')

            # Second-axis overlay
            if info_a['x_label'] == info_b['x_label']:
                fig_xo = go.Figure()
                fig_xo.add_trace(go.Scatter(
                    x=info_a['x_vals'], y=post_x_a,
                    mode='lines', line=dict(color='#4A90D9', width=2),
                    name='A',
                ))
                _add_hdi_shading(fig_xo, info_a['x_vals'], post_x_a,
                                 lo_x_a, hi_x_a, 'rgba(74,144,217,0.2)')
                _add_mode_line(fig_xo, mode_x_a, '#4A90D9')
                fig_xo.add_trace(go.Scatter(
                    x=info_b['x_vals'], y=post_x_b,
                    mode='lines', line=dict(color='#E25A53', width=2, dash='dash'),
                    name='B',
                ))
                _add_hdi_shading(fig_xo, info_b['x_vals'], post_x_b,
                                 lo_x_b, hi_x_b, 'rgba(226,90,83,0.2)')
                _add_mode_line(fig_xo, mode_x_b, '#E25A53')
                fig_xo.update_layout(**{
                    **PLOTLY_THEME,
                    'title': dict(text=f'{info_a["x_label"]} posterior comparison'),
                    'xaxis_title': info_a['x_label'],
                    'yaxis_title': 'Posterior density',
                    'height': 400,
                })
                st.plotly_chart(fig_xo, use_container_width=True, key=f'{p}_post_x_overlay')

    # ── Observed ΔRV CDF comparison ──────────────────────────────────────
    st.markdown('### Observed ΔRV CDF')
    st.caption('The observed ΔRV distribution is the same for both results (same dataset).')
    obs_drv_a = res_a.get('obs_delta_rv', None)
    obs_drv_b = res_b.get('obs_delta_rv', None)
    _has_obs = obs_drv_a is not None
    if _has_obs:
        obs_sorted = np.sort(obs_drv_a)
        obs_cdf_y = np.arange(1, len(obs_sorted) + 1) / len(obs_sorted)
        fig_cdf = go.Figure()
        fig_cdf.add_trace(go.Scatter(
            x=obs_sorted, y=obs_cdf_y,
            mode='lines+markers', line=dict(color='black', width=2),
            marker=dict(size=5),
            name='Observed ΔRV',
        ))
        fig_cdf.update_layout(**{
            **PLOTLY_THEME,
            'title': dict(text='Observed ΔRV CDF'),
            'xaxis_title': 'ΔRV (km/s)',
            'yaxis_title': 'Cumulative fraction',
            'height': 400,
        })
        st.plotly_chart(fig_cdf, use_container_width=True, key=f'{p}_cdf_obs')
    else:
        st.info('No observed ΔRV data found in results.')



# ─────────────────────────────────────────────────────────────────────────────
# Dynamic tab management
# ─────────────────────────────────────────────────────────────────────────────

# Initialize default tabs
if 'bc_tabs' not in st.session_state:
    st.session_state['bc_tabs'] = [
        {'type': 'dsilva', 'name': 'Dsilva (power-law)', 'prefix': 'bc'},
        {'type': 'langer', 'name': 'Langer 2020', 'prefix': 'lg'},
        {'type': 'cadence', 'name': 'Cadence-Aware', 'prefix': 'ca'},
        {'type': 'compare', 'name': 'Compare', 'prefix': 'cmp'},
    ]

# "+" button to add new tabs
_tab_mgmt_cols = st.columns([0.85, 0.15])
with _tab_mgmt_cols[1]:
    with st.popover('➕ Add tab'):
        _add_type = st.radio(
            'Tab type',
            ['Dsilva', 'Langer', 'Cadence-Aware', 'Compare'],
            key='_bc_add_tab_type',
        )
        _add_name = st.text_input('Tab name (optional)', key='_bc_add_tab_name')
        _add_col1, _add_col2 = st.columns(2)
        if _add_col1.button('Add', key='_bc_add_tab_btn', type='primary'):
            _idx = len(st.session_state['bc_tabs'])
            _type_map = {'dsilva': 'dsilva', 'langer': 'langer',
                         'cadence-aware': 'cadence', 'compare': 'compare'}
            _type_lower = _type_map.get(_add_type.lower(), _add_type.lower())
            _pfx = f'{_type_lower[:3]}{_idx}'
            st.session_state['bc_tabs'].append({
                'type': _type_lower,
                'name': _add_name or f'{_add_type} {_idx}',
                'prefix': _pfx,
            })
            st.rerun()

        # Remove last tab (if more than 3 default tabs)
        if len(st.session_state['bc_tabs']) > 3:
            if _add_col2.button('Remove last', key='_bc_rm_tab_btn'):
                st.session_state['bc_tabs'].pop()
                st.rerun()

# Create dynamic tabs
_tab_names = [t['name'] for t in st.session_state['bc_tabs']]
_tab_widgets = st.tabs(_tab_names)

for _tw, _ti in zip(_tab_widgets, st.session_state['bc_tabs']):
    with _tw:
        if _ti['type'] == 'dsilva':
            _render_dsilva_tab(_ti['prefix'], settings, sm)
        elif _ti['type'] == 'langer':
            _render_langer_tab(_ti['prefix'], settings, sm)
        elif _ti['type'] == 'cadence':
            _render_cadence_tab(_ti['prefix'], settings, sm)
        elif _ti['type'] == 'compare':
            _render_compare_tab(_ti['prefix'])

# ─────────────────────────────────────────────────────────────────────────────
# Auto-refresh while any background simulation is running
# ─────────────────────────────────────────────────────────────────────────────
_any_job_running = any(
    st.session_state.get(f"{t['prefix']}_job", {}).get('status') == 'running'
    for t in st.session_state.get('bc_tabs', [])
)
if _any_job_running:
    @st.fragment(run_every=3)
    def _auto_refresh():
        _still = any(
            st.session_state.get(f"{t['prefix']}_job", {}).get('status') == 'running'
            for t in st.session_state.get('bc_tabs', [])
        )
        if _still:
            st.rerun(scope='app')
    _auto_refresh()
