"""bc.helpers — Shared constants and utility functions for bias correction."""
from __future__ import annotations

import datetime as _dt
import glob as _glob
import hashlib
import json
import os
import sys

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

_best_point = find_best_grid_point
_make_heatmap_fig = make_heatmap_fig

_RESULT_DIR = os.path.join(_ROOT, 'results')
_HISTORY_PATH = os.path.join(_ROOT, 'settings', 'run_history.json')

_CMP_COLORS = [
    '#4A90D9', '#E25A53', '#50C878', '#9B59B6', '#F39C12',
    '#1ABC9C', '#E67E22', '#3498DB', '#E74C3C', '#2ECC71',
]
_CMP_DASHES = [
    'solid', 'dash', 'dot', 'dashdot', 'longdash',
    'longdashdot', 'solid', 'dash', 'dot', 'dashdot',
]

# ── Scoring method registry ──────────────────────────────────────────────────
# (key, display_name, p_key, D_key, color)
SCORING_METHODS = [
    ('ks',         'K-S (standard)',  'ks_p',       'ks_D',       '#4A90D9'),
    ('weighted',   'K-S (weighted)',  'weighted_p', 'weighted_D', '#50C878'),
    ('cvm',        'CvM (S-score)',   'cvm_p',      'cvm_D',      '#E25A53'),
    ('likelihood', 'Likelihood',      'likelihood', 'logL_raw',   '#DAA520'),
]

_METHOD_COLORS = {m[0]: m[4] for m in SCORING_METHODS}


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Convert hex color to rgba string for Plotly shading."""
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'rgba({r},{g},{b},{alpha})'

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

    Format (Dsilva): dsilva_fb0.0-1.0x200_pi-3.0-3.0x100_N10000_sig5.5_logP0.15-5.0_120326-1200.npz
    Format (Langer): langer_fb0.01-0.99x100_sig1.0-15.0x30_N10000_logP0.5-3.5_120326-1200.npz
    """
    ts = _dt.datetime.now().strftime('%d%m%y-%H%M')
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
    # Exclude partial checkpoints (both new and legacy naming)
    files = [f for f in files
             if not any(x in os.path.basename(f)
                        for x in ('.partial', '_partial_', '_checkpoint'))]
    # Sort by modification time, newest first
    files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    return [(os.path.basename(f).replace('.npz', ''), f) for f in files]


def _build_partial_filename(
    model: str,
    fbin_vals: np.ndarray,
    x_vals: np.ndarray,
    n_stars: int,
    sigma_vals: np.ndarray,
    logP_min: float = 0.0,
    logP_max: float = 0.0,
    x_label: str = 'pi',
) -> str:
    """Build a descriptive filename for a partial checkpoint.

    Uses the same format as ``_build_descriptive_filename`` but inserts
    ``_partial`` after the model name.
    """
    desc = _build_descriptive_filename(
        model, float(fbin_vals[0]), float(fbin_vals[-1]), len(fbin_vals),
        float(x_vals[0]), float(x_vals[-1]), len(x_vals),
        int(n_stars), sigma_vals,
        float(logP_min), float(logP_max), x_label,
    )
    # Insert '_partial' right after model prefix
    return desc.replace(f'{model}_', f'{model}_partial_', 1)


def _list_partial_results(model: str) -> list[tuple[str, str]]:
    """List partial .npz files for a model, newest first."""
    pattern = os.path.join(_RESULT_DIR, f'{model}_partial_*.npz')
    files = _glob.glob(pattern)
    # Also check legacy single-file partials
    legacy_patterns = [
        _result_path(model) + '.partial.npz',
        os.path.join(_RESULT_DIR, f'{model}_result.npz.partial'),
        os.path.join(_RESULT_DIR, f'{model}_result.npz.partial.npz'),
    ]
    for lp in legacy_patterns:
        if os.path.exists(lp) and lp not in files:
            files.append(lp)
    files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    return [(os.path.basename(f), f) for f in files]


@st.cache_data(ttl=30)
def _scan_partial_metadata(model: str) -> pd.DataFrame:
    """Scan partial .npz files and return a DataFrame of metadata.

    Columns mirror ``_scan_result_metadata`` plus '% Complete' and 'Cells'.
    """
    rows: list[dict] = []
    for name, path in _list_partial_results(model):
        try:
            d = np.load(path, allow_pickle=True)
            ks_p = np.asarray(d.get('ks_p', np.array([])))
            if ks_p.size == 0:
                d.close()
                continue
            n_done = int(np.count_nonzero(~np.isnan(ks_p)))
            n_total = ks_p.size
            pct = n_done / n_total * 100 if n_total > 0 else 0
            is_dsilva = 'pi_grid' in d

            def _range_str(arr):
                if arr is None or len(arr) == 0:
                    return '\u2014'
                if len(arr) == 1:
                    return f'{arr[0]:.2f}'
                return f'{arr[0]:.2f}\u2013{arr[-1]:.2f} ({len(arr)})'

            fb = np.asarray(d.get('fbin_grid', []))
            pi = np.asarray(d.get('pi_grid', []))
            sig = np.asarray(d.get('sigma_grid', []))
            logP = np.asarray(d.get('logPmax_grid', []))

            # Parse settings once
            sett = {}
            if 'settings' in d:
                try:
                    sett = json.loads(str(d['settings']))
                except Exception:
                    pass

            # Fallback: populate sett from individual top-level keys
            # (for older cadence partials saved without a settings blob)
            if not sett:
                for _sk, _nk in [('period_model', 'period_model'),
                                 ('scoring_method', 'scoring_method')]:
                    if _nk in d:
                        _v = d[_nk]
                        sett[_sk] = (_v.item() if hasattr(_v, 'item')
                                     else str(_v))

            n_stars = str(sett.get('n_stars_sim', '\u2014'))

            # Best-fit from completed cells
            best_p = float(np.nanmax(ks_p)) if n_done > 0 else 0.0

            # Best f_bin from completed cells
            best_fb = '—'
            if n_done > 0 and fb.size > 0:
                if ks_p.ndim == 3 and np.any(np.isfinite(ks_p)):
                    _flat = int(np.nanargmax(ks_p))
                    _idx = np.unravel_index(_flat, ks_p.shape)
                    best_fb = f'{float(fb[_idx[1]]):.3f}'
                elif ks_p.ndim == 2 and np.any(np.isfinite(ks_p)):
                    _flat = int(np.nanargmax(ks_p))
                    _idx = np.unravel_index(_flat, ks_p.shape)
                    best_fb = f'{float(fb[_idx[0]]):.3f}'

            # Timestamp
            ts = str(d.get('timestamp', '\u2014'))
            ts = ts.replace('T', ' ')[:19]

            n_sets_val = str(int(d['n_sets'])) if 'n_sets' in d.files else '—'

            # ΔRV bin info
            _be = d.get('bin_edges')
            drv_bin = (f'{float(_be[1] - _be[0]):.0f}'
                       if _be is not None and len(_be) > 1 else '—')
            drv_bw = d.get('drv_bin_width')
            if drv_bw is not None and drv_bin == '—':
                drv_bin = f'{float(drv_bw):.0f}'
            drv_max_val = (f'{float(d["drv_max"]):.0f}' if 'drv_max' in d
                           else '—')

            # Scoring method
            scoring_val = str(d['scoring_method']) if 'scoring_method' in d else '—'
            if scoring_val == '—':
                scoring_val = str(sett.get('scoring_method', '—'))

            # ── New fields from settings ──────────────────────────────
            sigma_meas = sett.get('sigma_measure', '—')
            if sigma_meas != '—':
                sigma_meas = f'{float(sigma_meas):.2f}'
            period_model = str(sett.get('period_model', '—'))
            e_model = str(sett.get('e_model', '—'))
            q_model = str(sett.get('q_model', '—'))
            q_min_v = sett.get('q_min')
            q_max_v = sett.get('q_max')
            q_range_str = (f'{float(q_min_v):.2f}\u2013{float(q_max_v):.2f}'
                           if q_min_v is not None and q_max_v is not None else '—')
            logP_min_s = sett.get('logP_min', '—')
            logP_max_s = sett.get('logP_max', '—')
            logP_range_str = (f'{float(logP_min_s):.2f}\u2013{float(logP_max_s):.2f}'
                              if logP_min_s != '—' and logP_max_s != '—' else '—')
            mass_model = str(sett.get('mass_primary_model', '—'))
            mass_fixed = sett.get('mass_primary_fixed', '—')
            if mass_fixed != '—':
                mass_fixed = f'{float(mass_fixed):.1f}'
            threshold_drv = sett.get('threshold_dRV', '—')
            if threshold_drv != '—':
                threshold_drv = f'{float(threshold_drv):.1f}'
            sigma_factor = sett.get('sigma_factor', '—')
            if sigma_factor != '—':
                sigma_factor = f'{float(sigma_factor):.1f}'
            q_flipped = '—'
            if 'q_flipped' in sett:
                q_flipped = 'Yes' if sett['q_flipped'] else 'No'
            lp = sett.get('langer_period_params', {})
            langer_summary = '—'
            if lp:
                _wA = lp.get('weight_A', '—')
                langer_summary = f"wA={_wA}"

            adaptive_val = '—'
            if 'adaptive_bins' in sett:
                adaptive_val = 'Yes' if sett['adaptive_bins'] else 'No'
            if adaptive_val == '—' and 'adaptive_bins' in d:
                adaptive_val = 'Yes' if bool(d['adaptive_bins']) else 'No'

            d.close()

            rows.append({
                '% Done': f'{pct:.1f}%',
                'Cells': f'{n_done}/{n_total}',
                'Date': ts,
                'f_bin': _range_str(fb),
                'pi': _range_str(pi) if is_dsilva else '\u2014',
                'sigma': _range_str(sig),
                'logP grid': _range_str(logP),
                'logP range': logP_range_str,
                'N_stars': n_stars,
                'N_sets': n_sets_val,
                'σ_meas': sigma_meas,
                'Period': period_model,
                'e_model': e_model,
                'q_model': q_model,
                'q range': q_range_str,
                'q_flip': q_flipped,
                'M₁ model': mass_model,
                'M₁': mass_fixed,
                'ΔRV thr': threshold_drv,
                'σ_factor': sigma_factor,
                'Langer': langer_summary,
                'Adaptive': adaptive_val,
                'ΔRV bin': drv_bin,
                'ΔRV max': drv_max_val,
                'Scoring': scoring_val,
                'Best p': f'{best_p:.5f}',
                'Best f_bin': best_fb,
                'File': name,
                '_path': path,
                '_pct': pct,
            })
        except Exception:
            continue
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _render_partial_table(p: str, model: str, status_slot) -> None:
    """Render partial results table with Load / Delete / Resume actions.

    Placed as an expander in the tab UI, similar to the full results table.
    Uses session_state to persist the selected row so button clicks work
    reliably (avoids dataframe on_select + button click race).
    """
    meta = _scan_partial_metadata(model)
    if meta.empty:
        return

    # ── Handle pending actions from previous rerun ─────────────────────────
    _action_key = f'{p}_partial_action'
    _pending = st.session_state.pop(_action_key, None)
    if _pending is not None:
        _act = _pending.get('action')
        _act_path = _pending.get('path', '')
        _act_pct = _pending.get('pct', 0)
        if _act == 'load' and os.path.exists(_act_path):
            ptl = np.load(_act_path, allow_pickle=True)
            st.session_state[f'{p}_result'] = {k: ptl[k] for k in ptl.files}
            ptl.close()
            status_slot.success(f'Loaded partial ({_act_pct:.1f}% complete)')
        elif _act == 'delete':
            try:
                os.remove(_act_path)
                _scan_partial_metadata.clear()
                st.toast('Partial file deleted.')
            except OSError as e:
                st.error(f'Failed to delete: {e}')
        elif _act == 'resume' and os.path.exists(_act_path):
            ptl = np.load(_act_path, allow_pickle=True)
            st.session_state[f'{p}_resume_from'] = _act_path
            st.session_state[f'{p}_result'] = {k: ptl[k] for k in ptl.files}
            ptl.close()
            st.session_state[f'{p}_auto_resume'] = True
        # Re-read metadata after possible deletion
        meta = _scan_partial_metadata(model)
        if meta.empty:
            return

    with st.expander(f'\U0001f504 Partial results ({len(meta)} found)', expanded=False):
        display = meta.drop(columns=['_path', '_pct'], errors='ignore')
        sel = st.dataframe(
            display,
            on_select='rerun',
            selection_mode='single-row',
            key=f'{p}_partial_table',
            hide_index=True,
            use_container_width=True,
        )
        sel_rows = sel.selection.rows if sel.selection else []
        if sel_rows:
            idx = sel_rows[0]
            path = meta.iloc[idx]['_path']
            pct = meta.iloc[idx]['_pct']
            c1, c2, c3 = st.columns(3)
            if c1.button('\U0001f4cb Load', key=f'{p}_load_partial'):
                st.session_state[_action_key] = {
                    'action': 'load', 'path': path, 'pct': pct}
                st.rerun()
            if c2.button('\U0001f5d1\ufe0f Delete', key=f'{p}_del_partial'):
                st.session_state[_action_key] = {
                    'action': 'delete', 'path': path, 'pct': pct}
                st.rerun()
            if c3.button('\u25b6\ufe0f Resume', key=f'{p}_resume_partial',
                         help='Load partial and start run to fill remaining cells'):
                st.session_state[_action_key] = {
                    'action': 'resume', 'path': path, 'pct': pct}
                st.rerun()


@st.cache_data(ttl=30)
def _scan_result_metadata(model: str | None = None) -> pd.DataFrame:
    """Scan saved .npz result files and return a DataFrame of metadata.

    Parameters
    ----------
    model : str or None
        'dsilva', 'langer', or None (both).
    """
    models = [model] if model else ['dsilva', 'langer', 'cadence_dsilva', 'cadence_langer']
    rows: list[dict] = []
    for mdl in models:
        for name, path in _list_saved_results(mdl):
            try:
                d = np.load(path, allow_pickle=True)
                is_dsilva = 'pi_grid' in d
                mtype = 'dsilva' if is_dsilva else 'langer'

                def _range_str(arr):
                    if arr is None or len(arr) == 0:
                        return '—'
                    if len(arr) == 1:
                        return f'{arr[0]:.2f}'
                    return f'{arr[0]:.2f}–{arr[-1]:.2f} ({len(arr)})'

                fb = d.get('fbin_grid', np.array([]))
                pi = d.get('pi_grid', np.array([]))
                sig = d.get('sigma_grid', np.array([]))
                logP = d.get('logPmax_grid', np.array([]))

                # Parse settings once
                sett = {}
                if 'settings' in d:
                    try:
                        sett = json.loads(str(d['settings']))
                    except Exception:
                        pass

                n_stars = str(sett.get('n_stars_sim', '—'))

                # Best-fit
                ks_p = d.get('ks_p', np.array([0]))
                best_p = float(np.nanmax(ks_p))
                best_fb = f'{float(d["mode_fbin"]):.3f}' if 'mode_fbin' in d else '—'

                # Timestamp
                ts = str(d['timestamp']) if 'timestamp' in d else '—'
                ts = ts.replace('T', ' ')[:19]

                n_sets_val = str(int(d['n_sets'])) if 'n_sets' in d else '—'

                # ΔRV bin info
                _be = d.get('bin_edges')
                drv_bin = (f'{float(_be[1] - _be[0]):.0f}'
                           if _be is not None and len(_be) > 1 else '—')
                drv_max_val = (f'{float(d["drv_max"]):.0f}' if 'drv_max' in d
                               else (f'{float(_be[-1] + (_be[1] - _be[0])):.0f}'
                                     if _be is not None and len(_be) > 1
                                     else '—'))

                # Scoring method + adaptive bins
                scoring_val = str(sett.get('scoring_method', '—'))
                adaptive_val = '—'
                if 'adaptive_bins' in sett:
                    adaptive_val = 'Yes' if sett['adaptive_bins'] else 'No'
                # Fallback: check top-level key (older saves)
                if adaptive_val == '—' and 'adaptive_bins' in d:
                    adaptive_val = 'Yes' if bool(d['adaptive_bins']) else 'No'

                # ── New fields from settings ──────────────────────────────
                sigma_meas = sett.get('sigma_measure', '—')
                if sigma_meas != '—':
                    sigma_meas = f'{float(sigma_meas):.2f}'
                period_model = str(sett.get('period_model', '—'))
                e_model = str(sett.get('e_model', '—'))
                q_model = str(sett.get('q_model', '—'))
                q_min = sett.get('q_min')
                q_max = sett.get('q_max')
                q_range_str = (f'{float(q_min):.2f}–{float(q_max):.2f}'
                               if q_min is not None and q_max is not None else '—')
                logP_min_s = sett.get('logP_min', '—')
                logP_max_s = sett.get('logP_max', '—')
                logP_range_str = (f'{float(logP_min_s):.2f}–{float(logP_max_s):.2f}'
                                  if logP_min_s != '—' and logP_max_s != '—' else '—')
                mass_model = str(sett.get('mass_primary_model', '—'))
                mass_fixed = sett.get('mass_primary_fixed', '—')
                if mass_fixed != '—':
                    mass_fixed = f'{float(mass_fixed):.1f}'
                threshold_drv = sett.get('threshold_dRV', '—')
                if threshold_drv != '—':
                    threshold_drv = f'{float(threshold_drv):.1f}'
                sigma_factor = sett.get('sigma_factor', '—')
                if sigma_factor != '—':
                    sigma_factor = f'{float(sigma_factor):.1f}'
                q_flipped = '—'
                if 'q_flipped' in sett:
                    q_flipped = 'Yes' if sett['q_flipped'] else 'No'
                # Langer period params summary
                lp = sett.get('langer_period_params', {})
                langer_summary = '—'
                if lp:
                    _wA = lp.get('weight_A', '—')
                    langer_summary = f"wA={_wA}"

                d.close()

                rows.append({
                    'Model': mtype,
                    'Date': ts,
                    'f_bin': _range_str(fb),
                    'pi': _range_str(pi) if is_dsilva else '—',
                    'sigma': _range_str(sig),
                    'logP grid': _range_str(logP),
                    'logP range': logP_range_str,
                    'N_stars': n_stars,
                    'N_sets': n_sets_val,
                    'σ_meas': sigma_meas,
                    'Period': period_model,
                    'e_model': e_model,
                    'q_model': q_model,
                    'q range': q_range_str,
                    'q_flip': q_flipped,
                    'M₁ model': mass_model,
                    'M₁': mass_fixed,
                    'ΔRV thr': threshold_drv,
                    'σ_factor': sigma_factor,
                    'Langer': langer_summary,
                    'Adaptive': adaptive_val,
                    'ΔRV bin': drv_bin,
                    'ΔRV max': drv_max_val,
                    'Scoring': scoring_val,
                    'Best p': f'{best_p:.5f}',
                    'Best f_bin': best_fb,
                    'File': name,
                    '_path': path,
                })
            except Exception:
                continue
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _make_max_pval_fig(
    sigma_vals: np.ndarray,
    max_pvals: list[float],
    height: int = 300,
    x_label: str = 'σ_single',
    stat_label: str = 'K-S',
) -> go.Figure:
    """Line chart: max p-value vs a scan variable."""
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
        'title': dict(text=f'Max {stat_label} p-value vs {x_label}', font=dict(size=14)),
        'xaxis_title': x_label,
        'yaxis_title': f'Max {stat_label} p-value',
        'height': height,
        'margin': dict(l=60, r=20, t=50, b=50),
    })
    return fig


def _make_min_score_fig(
    sigma_vals: np.ndarray,
    min_scores: list[float],
    height: int = 300,
    x_label: str = 'σ_single',
    stat_label: str = 'CvM',
) -> go.Figure:
    """Line chart: min weighted score (S) vs a scan variable. Lower = better fit."""
    best_idx = int(np.argmin(min_scores))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sigma_vals, y=min_scores,
        mode='lines+markers',
        marker=dict(size=8, color='#E25A53'),
        line=dict(color='#E25A53', width=2),
        hovertemplate=f'{x_label}=%{{x:.2f}}<br>min weighted S=%{{y:.4f}}<extra></extra>',
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=[float(sigma_vals[best_idx])],
        y=[min_scores[best_idx]],
        mode='markers+text',
        marker=dict(symbol='star', size=16, color='#DAA520',
                    line=dict(color='black', width=1)),
        text=[f'  {x_label}={float(sigma_vals[best_idx]):.2f}, S={min_scores[best_idx]:.4f}'],
        textposition='middle right',
        textfont=dict(color='#DAA520', size=11),
        showlegend=False,
    ))
    fig.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(text=f'Min {stat_label} weighted S-score vs {x_label}', font=dict(size=14)),
        'xaxis_title': x_label,
        'yaxis_title': f'Min {stat_label} weighted S-score',
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
    stat_label: str = 'K-S',
) -> go.Figure:
    """3D stacked semi-transparent surfaces: one per sigma_single."""
    pal = get_palette()
    valid = ks_p_3d[~np.isnan(ks_p_3d)]
    global_zmax = float(np.nanmax(valid)) if valid.size > 0 else 1.0

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
            colorbar=dict(title=f'{stat_label} p', thickness=14, len=0.6)
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
# CDF Sanity Check (cadence tabs only)
# ─────────────────────────────────────────────────────────────────────────────

def _render_cdf_sanity_check(best_fbin, best_x, sigma_single,
                              obs_delta_rv, period_model, result,
                              settings, p_prefix: str) -> None:
    """Render 5 random CDF draws vs observed for cadence sanity check.

    Generates 5 independent sets of 25 simulated stars at the best-fit
    parameters, overlaid on the observed CDF. This verifies the cadence-aware
    pipeline produces sensible ΔRV distributions.
    """
    from wr_bias_simulation import (
        simulate_delta_rv_sample, BinaryParameterConfig,
        binned_cdf, DEFAULT_DRV_BIN_EDGES,
    )

    cadence_library = result.get('cadence_library')
    if cadence_library is None:
        return

    _bin_edges = DEFAULT_DRV_BIN_EDGES
    obs_cdf_b = binned_cdf(obs_delta_rv, _bin_edges)

    st.markdown('### CDF Sanity Check')
    st.caption(
        '5 random draws of 25 simulated stars at the best-fit parameters, '
        'compared to the observed CDF. Each draw uses different random seeds '
        'but identical cadence assignments.'
    )

    # Build BinaryParameterConfig from result metadata
    _bcfg_dict = result.get('bin_cfg', {})
    bcfg = BinaryParameterConfig(**_bcfg_dict) if _bcfg_dict else BinaryParameterConfig()

    fig = go.Figure()

    # Observed CDF
    fig.add_trace(go.Scatter(
        x=_bin_edges, y=obs_cdf_b,
        mode='lines', name='Observed',
        line=dict(color='#4A90D9', width=3, shape='hv'),
    ))

    # 5 random draws
    _draw_colors = ['#E25A53', '#50C878', '#9B59B6', '#F39C12', '#1ABC9C']
    for i, seed in enumerate([42, 43, 44, 45, 46]):
        try:
            drv = simulate_delta_rv_sample(
                n_stars=25,
                f_bin=best_fbin,
                sigma_single=sigma_single,
                sigma_measure=float(result.get('sigma_meas', 1.622)),
                binary_config=bcfg,
                rng_seed=seed,
                period_model=period_model,
                cadence_library=cadence_library,
            )
            sim_cdf = binned_cdf(drv, _bin_edges)
            fig.add_trace(go.Scatter(
                x=_bin_edges, y=sim_cdf,
                mode='lines', name=f'Draw {i+1} (seed={seed})',
                line=dict(color=_draw_colors[i], width=1.5,
                          dash='dash', shape='hv'),
                opacity=0.7,
            ))
        except Exception:
            pass

    fig.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(
            text=f'CDF Sanity Check  (f_bin={best_fbin:.3f}, 25 stars × 5 draws)',
            font=dict(size=14)),
        'xaxis_title': 'ΔRV (km/s)',
        'yaxis_title': 'Cumulative fraction',
        'height': 420,
        'legend': dict(x=0.55, y=0.35, font=dict(size=10)),
    })
    st.plotly_chart(fig, use_container_width=True, key=f'{p_prefix}_cdf_sanity')


# ─────────────────────────────────────────────────────────────────────────────
# Methodology Explainer (all tabs)
# ─────────────────────────────────────────────────────────────────────────────

_LANGER_EXPLAINER = r'''
**Langer 2020 period model** — uses physically motivated orbital parameter
distributions from binary population synthesis (Langer et al. 2020, A&A 638, A39).

1. **Draw N systems** (default 3,000). Each is binary with probability f_bin,
   or single with probability 1 − f_bin.

2. **Single stars:** draw RV at each epoch from
   N(v_sys, σ_total) where σ_total = √(σ_single² + σ_measure²).
   ΔRV = max(v) − min(v).

3. **Binary stars — period distribution:**
   Two-component mixture of Case A (short-period) and Case B (long-period)
   mass transfer channels:
   - **Case A:** Gaussian in log₁₀P with μ_A and σ_A
   - **Case B:** Log-normal in log₁₀P with mode μ_B and width σ_B
   - **Mixture weight:** w_A for Case A, (1 − w_A) for Case B

4. **Mass ratio q = M₂/M₁:** sampled from a Gaussian centered on μ_q
   with width σ_q (based on Langer+2020 Fig. 4, BH companion masses).

5. **Eccentricity e = 0** (post-RLOF circularization).

6. **Remaining steps** (K₁ computation, Kepler equation, K-S test)
   are identical to the power-law (Dsilva) model — see that tab for equations.

7. **Grid search** over f_bin × σ_single to find the best-fit parameters
   that maximize the K-S p-value.
'''

_CADENCE_EXPLAINER = r'''
**Cadence-aware modification:**

Unlike the basic simulation which draws random observation times, the
cadence-aware mode preserves the **exact observation timestamps** from the
real survey:

1. Each of **N_sets** iterations (default 10,000) generates a complete
   set of 25 simulated stars.
2. Each simulated star is assigned the **exact MJD sequence** of a randomly
   chosen real star (with replacement, weighted by epoch count).
3. RV curves are computed at those specific times, producing one ΔRV per star.
4. The 25-star ΔRV sample is compared to the observed via binned K-S test.
5. The **median, 16th, and 84th percentile** CDFs across all N_sets are
   stored — the median CDF is used for the K-S statistic, while the
   percentiles define the 68% confidence band.

This approach captures the effects of:
- Uneven time sampling between stars
- Varying number of epochs per star
- Correlated observation windows (multi-star campaigns)

**Scoring methods:**

- **K-S (standard):** D = max|CDF_sim − CDF_obs| across all ΔRV bins.
  All bins contribute equally to the statistic.
- **K-S (variance-weighted):** χ² = Σ (sim_i − obs_i)² / σ²_i, where σ²_i
  is the variance of the simulated CDF at bin i across all N_sets repetitions.
  Bins with high simulation variance contribute less to the statistic.
  The p-value is the chi-squared survival function (higher = better fit).
- **CvM (S-score):** S = Σ (sim_i − obs_i)² / σ²_i (variance-weighted Cramér–von Mises).
  Unlike K-S, uses ALL bins — the full CDF shape matters, not just the single worst bin.
  Bins with high simulation variance contribute less (inverse-variance weighting).
  The p-value is **empirical**: for each of the N_sets simulated star sets, we compute
  S against the median CDF. The p-value = fraction with S ≥ S_obs.
  Models with p outside [0.05, 0.95] are masked as implausible (white on heatmap).
  The true minimum is found via spline interpolation over the valid region.
'''


def _render_methodology_expander(tab_type: str) -> None:
    """Render a methodology expander for the given tab type.

    Parameters
    ----------
    tab_type : str
        One of 'dsilva', 'langer', 'cadence_dsilva', 'cadence_langer'.
    """
    if tab_type == 'dsilva':
        # Dsilva already has its own inline expander (lines 2704-2781)
        return

    st.markdown('---')
    with st.expander('📖 How this bias correction works', expanded=False):
        if tab_type == 'langer':
            st.markdown(_LANGER_EXPLAINER)
        elif tab_type == 'cadence_dsilva':
            st.markdown(
                'This tab uses the **power-law period model** (Dsilva 2023) '
                'with cadence-aware sampling. See the Dsilva tab for the full '
                'methodology equations.'
            )
            st.markdown(_CADENCE_EXPLAINER)
        elif tab_type == 'cadence_langer':
            st.markdown(_LANGER_EXPLAINER)
            st.markdown(_CADENCE_EXPLAINER)



