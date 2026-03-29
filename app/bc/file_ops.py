"""bc.file_ops — File I/O, metadata scanning, and result management."""
from __future__ import annotations

import datetime as _dt
import glob as _glob
import json
import os
import sys

import numpy as np
import pandas as pd
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_RESULT_DIR = os.path.join(_ROOT, 'results')
_HISTORY_PATH = os.path.join(_ROOT, 'settings', 'run_history.json')


def _result_path(model: str) -> str:
    return os.path.join(_RESULT_DIR, f'{model}_result.npz')


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


# ── WORKING — do not change this code · cancel-save-resume ──
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


# ── WORKING — do not change this code · cancel-save-resume ──
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


# ── WORKING — do not change this code · cancel-save-resume ──
@st.cache_data(ttl=30)
def _scan_partial_metadata(model: str) -> pd.DataFrame:
    """Scan partial .npz files and return a DataFrame of metadata.

    Columns mirror ``_scan_result_metadata`` plus '% Complete' and 'Cells'.
    """
    rows: list[dict] = []
    for name, path in _list_partial_results(model):
        try:
            # ── WORKING — do not change this code · partial metadata scanner ──
            d = np.load(path, allow_pickle=True)
            ks_p = np.asarray(d.get('ks_p', d.get('logL_raw', np.array([]))))
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


# ── WORKING — do not change this code · cancel-save-resume ──
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
