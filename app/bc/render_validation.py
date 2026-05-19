"""bc.render_validation — Validation tab UI (tasks #160/#161).

Single-point recovery delegates to the cadence tab functions with
obs_override, giving true 1:1 code reuse.  Batch sweep is standalone.
"""
from __future__ import annotations

import os
import sys
import threading

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from shared import (
    cached_load_cadence,
    settings_hash,
    PLOTLY_THEME,
)


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def _render_validation_tab(p: str, settings: dict, sm) -> None:
    """Render the Validation tab for parameter recovery testing."""
    st.markdown('### Parameter Recovery Validation')
    st.caption(
        'Test whether the likelihood pipeline can recover known "true" parameters '
        'from synthetic (mock) observations. A low recovery score means good recovery.'
    )

    # Load cadence data (needed for mock generation)
    sh = settings_hash(settings) if settings else ''
    try:
        cadence_list, cadence_weights = cached_load_cadence(sh)
    except Exception as exc:
        st.error(f'Cannot load cadence data: {exc}')
        return

    # ── Model selector ────────────────────────────────────────────────────
    model_choice = st.radio(
        'Period model',
        ['Dsilva (power-law)', 'Langer 2020'],
        horizontal=True,
        key=f'{p}_val_model',
    )
    is_dsilva = model_choice.startswith('Dsilva')
    period_model = 'powerlaw' if is_dsilva else 'langer2020'

    # ── Mode tabs ─────────────────────────────────────────────────────────
    single_tab, batch_tab = st.tabs(['Single-Point Recovery', 'Batch Sweep'])

    with single_tab:
        _render_single_point(p, is_dsilva, period_model, cadence_list,
                             cadence_weights, settings, sm)

    with batch_tab:
        _render_batch_sweep(p, is_dsilva, period_model, cadence_list,
                            cadence_weights, settings, sm)


# ─────────────────────────────────────────────────────────────────────────────
# Saved validation runs table (mock_results/)
# ─────────────────────────────────────────────────────────────────────────────

def _render_validation_results_table(p: str, is_dsilva: bool) -> None:
    """Show saved validation runs + Load / Delete buttons.

    Mirrors the pattern used in app/bc/cadence.py for the normal results/
    table (around line 1052): single-row selection reveals action buttons,
    Load stuffs result + mock_detail + truth into session_state, and
    Recovery Diagnostics re-renders from those keys.
    """
    from bc import validation_io as _vio

    model = 'dsilva' if is_dsilva else 'langer'
    meta = _vio.scan_validation_metadata(model)

    # Handle pending action from the previous rerun
    _action_key = f'{p}_val_results_action'
    _pending = st.session_state.pop(_action_key, None)
    if _pending is not None:
        _act = _pending.get('action')
        _path = _pending.get('path', '')
        if _act == 'load' and os.path.exists(_path):
            try:
                result, mock_detail = _vio.load_validation_result(_path)
            except Exception as exc:
                st.error(f'Failed to load validation result: {exc}')
            else:
                st.session_state[f'{p}_result'] = result
                st.session_state[f'{p}_is_loaded_result'] = True
                st.session_state[f'{p}_loaded_path'] = _path
                if mock_detail is not None:
                    st.session_state[f'{p}_val_mock_detail'] = mock_detail
                    st.session_state[f'{p}_val_mock_drv'] = np.asarray(
                        mock_detail.get('delta_rv', []), dtype=float)
                # Rebuild (truth, period_model) tuple for downstream code
                def _get(k, d=0.0):
                    v = result.get(k, d)
                    if isinstance(v, np.ndarray):
                        try:
                            return v.item()
                        except Exception:
                            return float(v) if v.size == 1 else d
                    return v
                _pmodel = _get('period_model', 'powerlaw')
                if isinstance(_pmodel, np.ndarray):
                    try:
                        _pmodel = _pmodel.item()
                    except Exception:
                        _pmodel = 'powerlaw'
                # 8-tuple: (fbin, pi, sigma, logPmax, seed, period_model,
                # error_model, error_params).  Older saved results predate
                # the error-model fields — fall back to ('fixed', ()).
                _saved_err_model = _get('error_model', 'fixed')
                if isinstance(_saved_err_model, np.ndarray):
                    try:
                        _saved_err_model = _saved_err_model.item()
                    except Exception:
                        _saved_err_model = 'fixed'
                _saved_err_params = result.get('error_params')
                if (_saved_err_params is not None
                        and hasattr(_saved_err_params, 'item')
                        and getattr(_saved_err_params, 'ndim', 1) == 0):
                    try:
                        _saved_err_params = _saved_err_params.item()
                    except Exception:
                        _saved_err_params = ()
                try:
                    _saved_err_params = tuple(_saved_err_params) \
                        if _saved_err_params is not None else ()
                except TypeError:
                    _saved_err_params = ()
                st.session_state[f'{p}_val_mock_params'] = (
                    float(_get('true_fbin', 0.0)),
                    float(_get('true_pi', 0.0)),
                    float(_get('true_sigma', 0.0)),
                    float(_get('true_logPmax', 0.0)),
                    int(_get('seed', 0)),
                    str(_pmodel),
                    str(_saved_err_model),
                    _saved_err_params,
                )
                st.toast(f'Loaded validation: {os.path.basename(_path)}')
                st.rerun()
        elif _act == 'delete':
            try:
                _vio.delete_validation_result(_path)
                st.toast(f'Deleted: {os.path.basename(_path)}')
            except Exception as exc:
                st.error(f'Delete failed: {exc}')
            meta = _vio.scan_validation_metadata(model)

    if meta is None or meta.empty:
        st.caption('No saved validation runs yet — a new run will auto-save '
                   'to `mock_results/`.')
    else:
        with st.expander(
                f'\U0001f4c2 Saved validation runs ({len(meta)})',
                expanded=False):
            display = meta.drop(columns=['_path'], errors='ignore')
            sel = st.dataframe(
                display, use_container_width=True,
                selection_mode='single-row', on_select='rerun',
                hide_index=True,
                key=f'{p}_val_results_table',
            )
            sel_rows = sel.selection.rows if sel.selection else []
            if sel_rows:
                idx = sel_rows[0]
                path = meta.iloc[idx]['_path']
                c1, c2 = st.columns(2)
                if c1.button('\U0001f4cb Load', key=f'{p}_val_load_btn'):
                    st.session_state[_action_key] = {
                        'action': 'load', 'path': path}
                    st.rerun()
                if c2.button('\U0001f5d1\ufe0f Delete',
                             key=f'{p}_val_del_btn'):
                    st.session_state[_action_key] = {
                        'action': 'delete', 'path': path}
                    st.rerun()

    # Partial validation checkpoints
    partials = _vio.list_validation_partials(model)
    if partials:
        with st.expander(
                f'\U0001f504 Partial validation runs ({len(partials)})',
                expanded=False):
            for name, path in partials:
                c1, c2, c3 = st.columns([6, 1, 1])
                c1.write(name)
                if c2.button('\u25b6\ufe0f Resume',
                             key=f'{p}_val_resume_{name}'):
                    st.session_state[f'{p}_resume_from'] = path
                    st.session_state[f'{p}_auto_resume'] = True
                    st.toast(f'Queued resume: {name}')
                    st.rerun()
                if c3.button('\U0001f5d1\ufe0f',
                             key=f'{p}_val_del_partial_{name}'):
                    try:
                        os.remove(path)
                        _vio.scan_validation_metadata.clear()
                        st.toast(f'Deleted partial: {name}')
                        st.rerun()
                    except OSError as exc:
                        st.error(f'Delete failed: {exc}')


# ─────────────────────────────────────────────────────────────────────────────
# Mock-generation helper (used by single-click + batch buttons)
# TO-TEST (2026-05-19): extracted from inline body in _render_single_point so
# the new "Generate N mocks (ascending seeds)" batch button can reuse it
# without duplicating the BinaryParameterConfig assembly / snapshot logic.
# ─────────────────────────────────────────────────────────────────────────────

def _generate_one_mock(
    p: str,
    seed: int,
    true_fbin: float,
    true_pi: float,
    true_sigma: float,
    true_logPmax: float,
    period_model: str,
    is_dsilva: bool,
    settings: dict,
    cadence_list,
    cadence_weights,
    sigma_meas: float,
    sigma_meas_binary: float,
    error_model: str,
    error_params: tuple,
    error_model_binary: str,
    error_params_binary: tuple,
    stack_key: str,
) -> None:
    """Generate one mock realisation, set current-mock state, append to stack.

    Does NOT call ``st.rerun()`` — the caller is responsible (single-click
    triggers immediately; batch defers until the loop completes).  Does NOT
    clear the explorer CDF caches — the caller does that once at the end.
    """
    import dataclasses
    from wr_bias_simulation import BinaryParameterConfig
    from bc.validation import generate_mock_observations_detail
    from bc.helpers import _SNAPSHOT_PALETTE

    mock_key = f'{p}_val_mock_drv'
    mock_detail_key = f'{p}_val_mock_detail'
    mock_params_key = f'{p}_val_mock_params'

    e_model = 'flat' if is_dsilva else 'zero'
    # Build a base bin_cfg identical to what the grid worker uses, by
    # reading the SAME orbital sub-dict that bc.cadence._render_cadence_*
    # tabs read.  This makes the mock inherit q_range, mass_primary_*,
    # langer_*, q_flipped from the user's orbital-params widget instead
    # of falling back to dataclass defaults (q_range=(0.1,2.0)) which
    # mismatched the grid (q_range=(0.1,4.0)) and produced a visible
    # ΔRV-distribution offset in the Model Explorer.
    if is_dsilva:
        _orb = settings.get('grid_cadence_dsilva', {}).get('orbital', {})
        _base_bin_cfg = BinaryParameterConfig(
            logP_min=float(_orb.get('logP_min', 0.15)),
            logP_max=float(_orb.get('logP_max', 5.0)),
            period_model='powerlaw',
            e_model=str(_orb.get('e_model', 'flat')),
            e_max=float(_orb.get('e_max', 0.9)),
            mass_primary_model=str(_orb.get('mass_primary_model', 'fixed')),
            mass_primary_fixed=float(_orb.get('mass_primary_fixed', 10.0)),
            mass_primary_range=tuple(
                _orb.get('mass_primary_range', [10.0, 20.0])),
            q_model=str(_orb.get('q_model', 'flat')),
            q_range=tuple(_orb.get('q_range', [0.1, 2.0])),
            langer_q_mu=float(_orb.get('langer_q_mu', 0.7)),
            langer_q_sigma=float(_orb.get('langer_q_sigma', 0.2)),
        )
    else:
        _lg = settings.get('grid_cadence_langer', {})
        _lg_pp = _lg.get('langer_period_params', {})
        _base_bin_cfg = BinaryParameterConfig(
            logP_min=float(_lg.get('logP_min', 0.5)),
            logP_max=float(_lg.get('logP_max', 3.5)),
            period_model='langer2020',
            langer_period_params=dict(_lg_pp) if _lg_pp else {},
            e_model='zero',
            e_max=0.0,
            mass_primary_model=str(_lg.get('mass_primary_model', 'fixed')),
            mass_primary_fixed=float(_lg.get('mass_primary_fixed', 10.0)),
            mass_primary_range=tuple(
                _lg.get('mass_primary_range', [10.0, 20.0])),
            q_model=str(_lg.get('q_model', 'flat')),
            q_range=tuple(_lg.get('q_range', [0.25, 1.65])),
            langer_q_mu=float(_lg.get('langer_q_mu', 0.67)),
            langer_q_sigma=float(_lg.get('langer_q_sigma', 0.39)),
            q_flipped=bool(_lg.get('q_flipped', False)),
        )
    # Override only fields the mock legitimately owns.
    mock_bin_cfg = dataclasses.replace(
        _base_bin_cfg,
        logP_min=0.15,
        logP_max=true_logPmax,
        period_model=period_model,
        e_model=e_model,
        e_max=0.9,
    )
    mock_detail = generate_mock_observations_detail(
        true_fbin=true_fbin,
        true_pi=true_pi,
        true_sigma=true_sigma,
        true_logPmax=true_logPmax,
        cadence_library=cadence_list,
        cadence_weights=cadence_weights,
        sigma_meas=float(sigma_meas),
        bin_cfg=mock_bin_cfg,
        period_model=period_model,
        seed=int(seed),
        error_model=error_model,
        error_params=error_params,
        sigma_meas_binary=float(sigma_meas_binary),
        error_model_binary=error_model_binary,
        error_params_binary=error_params_binary,
    )
    st.session_state[mock_key] = mock_detail['delta_rv']
    st.session_state[mock_detail_key] = mock_detail
    st.session_state[mock_params_key] = (
        true_fbin, true_pi, true_sigma, true_logPmax,
        int(seed), period_model, error_model, error_params,
        error_model_binary, error_params_binary,
        float(sigma_meas), float(sigma_meas_binary),
    )
    # Append to visual stack — distribution-inspection only.
    # Store ONLY what the CDF render needs (no rvs_per_star / errs_per_star
    # arrays — keeps session state small even after dozens of stacked mocks).
    _existing = st.session_state[stack_key]
    _id = (max((s['id'] for s in _existing), default=0) + 1)
    _color = _SNAPSHOT_PALETTE[(_id - 1) % len(_SNAPSHOT_PALETTE)]
    _snap = {
        'id': int(_id),
        'color': _color,
        'delta_rv': np.asarray(mock_detail['delta_rv'], dtype=float).copy(),
        'is_binary': np.asarray(mock_detail['is_binary'], dtype=bool).copy(),
        'seed': int(seed),
        'true_fbin': float(true_fbin),
        'true_pi': float(true_pi),
        'true_sigma': float(true_sigma),
        'true_logPmax': float(true_logPmax),
    }
    st.session_state[stack_key].append(_snap)
    # Clear any previous cadence run state for this prefix
    st.session_state.pop(f'{p}_result', None)
    st.session_state.pop(f'{p}_job', None)


# ─────────────────────────────────────────────────────────────────────────────
# Single-point recovery: mock generation header + cadence tab delegation
# ─────────────────────────────────────────────────────────────────────────────

def _render_single_point(
    p: str,
    is_dsilva: bool,
    period_model: str,
    cadence_list: list,
    cadence_weights,
    settings: dict,
    sm,
) -> None:
    """Generate mock observations, then delegate to the cadence tab."""
    from wr_bias_simulation import BinaryParameterConfig
    from bc.cadence import (
        _render_cadence_dsilva_tab, _render_cadence_langer_tab,
    )

    # ── Saved validation runs (mock_results/) ─────────────────────────────
    _render_validation_results_table(p, is_dsilva)

    # ── Settings section + persisted defaults ────────────────────────────
    # True params + seed persist to disk under the same per-period-model
    # section the cadence tab uses, with `val_*` keys.  Read defaults from
    # the saved config; on_change writes back via the SettingsManager.
    _simcfg_for_errs = (
        settings.get('grid_cadence_dsilva', {}) if is_dsilva
        else settings.get('grid_cadence_langer', {})
    )
    _settings_section = (
        'grid_cadence_dsilva' if is_dsilva else 'grid_cadence_langer'
    )

    def _val_save(key: str, st_key: str):
        sm.save([_settings_section, key],
                value=st.session_state[st_key])

    st.markdown('#### True Parameters')
    st.caption('Set the "ground truth" parameters. The pipeline will try to recover these. (saved to disk on change)')

    c1, c2, c3, c4 = st.columns(4)
    _k_fbin = f'{p}_val_true_fbin'
    true_fbin = c1.slider(
        'True f_bin', 0.05, 1.0,
        float(_simcfg_for_errs.get('val_true_fbin', 0.46)), 0.01,
        key=_k_fbin,
        on_change=lambda: _val_save('val_true_fbin', _k_fbin),
    )
    if is_dsilva:
        _k_pi = f'{p}_val_true_pi'
        true_pi = c2.slider(
            'True pi', -3.0, 3.0,
            float(_simcfg_for_errs.get('val_true_pi', 0.0)), 0.1,
            key=_k_pi,
            on_change=lambda: _val_save('val_true_pi', _k_pi),
        )
    else:
        true_pi = 0.0
        c2.info('pi not used for Langer model')

    _k_sig = f'{p}_val_true_sigma'
    true_sigma = c3.slider(
        'True sigma_single (km/s)', 1.0, 40.0,
        float(_simcfg_for_errs.get('val_true_sigma', 15.0)), 0.5,
        key=_k_sig,
        on_change=lambda: _val_save('val_true_sigma', _k_sig),
    )
    _k_lpm = f'{p}_val_true_logPmax'
    true_logPmax = c4.slider(
        'True logP_max', 1.0, 6.0,
        float(_simcfg_for_errs.get('val_true_logPmax', 4.0)), 0.1,
        key=_k_lpm,
        on_change=lambda: _val_save('val_true_logPmax', _k_lpm),
    )

    _k_seed = f'{p}_val_seed'
    seed = st.number_input(
        'Random seed', 1, 99999,
        int(_simcfg_for_errs.get('val_seed', 42)), 1,
        key=_k_seed,
        on_change=lambda: _val_save('val_seed', _k_seed),
    )

    # ── Per-RV error distribution (stored per epoch; NOT added as noise
    # to RV values).  Two selectors — singles and binaries — to mirror the
    # Dsilva/Langer cadence tab layout.  Settings section is keyed per
    # period model so Dsilva/Langer keep independent persisted configs.
    from bc.extras import _render_one_error_model
    st.markdown('**Per-RV error distribution**')
    st.caption(
        'The chosen distributions populate each mock epoch\'s error bar '
        '(per-epoch σ).  These errors are added as measurement noise to '
        'the mock RV values AND stored per observation for downstream '
        'significance tests (ΔRV − 4σ > 0).  Singles and binaries can '
        'use independent error models, exactly like the Dsilva/Langer '
        'cadence grids.'
    )
    _err_col_s, _err_col_b = st.columns(2)
    with _err_col_s:
        st.markdown('**Singles**')
        _val_err_info_s = _render_one_error_model(
            p, '_val_single', _simcfg_for_errs, sm, _settings_section,
            label='Error model (singles)')
    with _err_col_b:
        st.markdown('**Binaries**')
        _val_err_info_b = _render_one_error_model(
            p, '_val_binary', _simcfg_for_errs, sm, _settings_section,
            label='Error model (binaries)')
    sigma_meas = float(_val_err_info_s['sigma_measure'])
    error_model = str(_val_err_info_s['type'])
    error_params = tuple(_val_err_info_s['params'])
    sigma_meas_binary = float(_val_err_info_b['sigma_measure'])
    error_model_binary = str(_val_err_info_b['type'])
    error_params_binary = tuple(_val_err_info_b['params'])

    # ── Generate mock observations ────────────────────────────────────────
    mock_key = f'{p}_val_mock_drv'
    mock_detail_key = f'{p}_val_mock_detail'
    mock_params_key = f'{p}_val_mock_params'

    _stack_key = f'{p}_val_mock_stack'
    st.session_state.setdefault(_stack_key, [])

    # TO-TEST (2026-05-19): three-column layout adds a batch generator
    # next to the single-click button.  Middle column hosts an N input
    # + "Generate N mocks (ascending seeds)" button; the helper
    # `_generate_one_mock` is shared between single-click and batch paths
    # to avoid duplicated BinaryParameterConfig assembly / snapshot logic.
    _gen_c1, _gen_c2, _gen_c3 = st.columns([0.55, 0.27, 0.18])
    gen_btn = _gen_c1.button('Generate Mock Observations', type='primary',
                             key=f'{p}_val_gen')

    _k_bn = f'{p}_val_batch_n'
    batch_n = _gen_c2.number_input(
        'N (batch)',
        value=int(_simcfg_for_errs.get('val_batch_n', 10)),
        step=1,
        key=_k_bn,
        on_change=lambda: _val_save('val_batch_n', _k_bn),
        help='Number of mocks to generate with ascending seeds, '
             'starting from the current "Random seed" above.',
    )
    batch_btn = _gen_c2.button(
        'Generate N mocks (ascending seeds)',
        key=f'{p}_val_gen_batch',
    )

    clear_btn = _gen_c3.button(
        f'🧹 Clear stack ({len(st.session_state[_stack_key])})',
        key=f'{p}_val_mock_clear',
        disabled=(len(st.session_state[_stack_key]) == 0),
    )
    if clear_btn:
        st.session_state[_stack_key] = []
        st.rerun()

    current_params = (true_fbin, true_pi, true_sigma, true_logPmax,
                      int(seed), period_model, error_model, error_params,
                      error_model_binary, error_params_binary,
                      float(sigma_meas), float(sigma_meas_binary))

    def _clear_explorer_cdf_caches() -> None:
        """Belt-and-braces: drop CDF caches in both Explorer twins."""
        try:
            from bc.render_lk_explorer import _me_cdf_band
            _me_cdf_band.clear()
        except Exception:
            pass
        try:
            from bc.render_lk_explorer_langer import _me_cdf_band_langer
            _me_cdf_band_langer.clear()
        except Exception:
            pass

    if gen_btn:
        _generate_one_mock(
            p=p, seed=int(seed),
            true_fbin=true_fbin, true_pi=true_pi,
            true_sigma=true_sigma, true_logPmax=true_logPmax,
            period_model=period_model, is_dsilva=is_dsilva,
            settings=settings,
            cadence_list=cadence_list, cadence_weights=cadence_weights,
            sigma_meas=sigma_meas, sigma_meas_binary=sigma_meas_binary,
            error_model=error_model, error_params=error_params,
            error_model_binary=error_model_binary,
            error_params_binary=error_params_binary,
            stack_key=_stack_key,
        )
        _clear_explorer_cdf_caches()
        st.rerun()

    if batch_btn:
        # TO-TEST (2026-05-19): batch mock generation with ascending seeds.
        # Per-iteration cost is small (single mock, no grid) but the
        # progress bar gives feedback for larger N (e.g. 100).  Single
        # st.rerun() at the end — re-rendering on every iteration would
        # discard the progress bar and break the loop.
        _n = int(batch_n)
        if _n <= 0:
            st.warning('N must be at least 1.')
        else:
            _seed0 = int(seed)
            _bar = st.progress(
                0.0, text=f'Generating mock 1/{_n} (seed={_seed0})…')
            for _i in range(_n):
                _s = _seed0 + _i
                _generate_one_mock(
                    p=p, seed=_s,
                    true_fbin=true_fbin, true_pi=true_pi,
                    true_sigma=true_sigma, true_logPmax=true_logPmax,
                    period_model=period_model, is_dsilva=is_dsilva,
                    settings=settings,
                    cadence_list=cadence_list,
                    cadence_weights=cadence_weights,
                    sigma_meas=sigma_meas,
                    sigma_meas_binary=sigma_meas_binary,
                    error_model=error_model, error_params=error_params,
                    error_model_binary=error_model_binary,
                    error_params_binary=error_params_binary,
                    stack_key=_stack_key,
                )
                _bar.progress(
                    (_i + 1) / _n,
                    text=f'Mock {_i + 1}/{_n}, seed={_s}',
                )
            _clear_explorer_cdf_caches()
            _bar.empty()
            st.rerun()

    mock_drv = st.session_state.get(mock_key)
    mock_detail = st.session_state.get(mock_detail_key)
    if mock_drv is None:
        st.info('Set true parameters and click **Generate Mock Observations** to start.')
        return

    saved_params = st.session_state.get(mock_params_key)
    st.success(
        f'Mock data ready: **{len(mock_drv)} stars**, '
        f'seed={saved_params[4] if saved_params else "?"}, '
        f'max(ΔRV)={np.max(mock_drv):.1f} km/s'
    )

    # ── Pre-simulation visualizations (above simulation parameters) ───────
    if mock_detail is not None:
        _saved = saved_params or current_params
        _input_fbin = float(_saved[0]) if _saved is not None else float(true_fbin)
        _render_mock_preview(
            p, mock_detail,
            thresh_dRV=float(settings.get('classification', {})
                             .get('threshold_dRV', 45.5)),
            input_fbin=_input_fbin,
            mock_stack=st.session_state.get(_stack_key, []),
        )

    st.markdown('---')
    st.markdown('#### Simulation Parameters & Recovery Run')
    st.caption(
        'Configure the recovery grid below, then click **▶️ Run** to run the '
        'likelihood search against the mock observations. All heatmaps, CDF '
        'comparisons and analysis plots from the Dsilva/Langer tabs are '
        'reproduced below the button once the run completes.'
    )

    # ── Stash validation-lane context so cadence.py routes saves to
    # ── mock_results/ instead of results/ (picked up at params-build time).
    st.session_state[f'{p}_val_save_backend'] = 'mock_results'
    _saved = saved_params or current_params
    st.session_state[f'{p}_val_truth_dict'] = {
        'true_fbin': float(_saved[0]),
        'true_pi': float(_saved[1]),
        'true_sigma': float(_saved[2]),
        'true_logPmax': float(_saved[3]),
        'seed': int(_saved[4]),
    }

    # ── Re-seed bin-edges widget on fresh run completion ─────────────────
    # TO-TEST (2026-05-19): when a Run transitions from "running" to "done",
    # set the one-shot `_is_loaded_result` flag so the Bin edges field
    # syncs to what the run actually used.  The result's `timestamp` is
    # written by the cadence worker (runners_cadence.py:197/662) and is
    # unique per run; we compare against `_val_last_seen_result_id` to
    # detect the transition.  Falls back to `id(result)` if timestamp is
    # missing (older saved results).  See memory/feedback_no_self_approve.md
    # — user visual sign-off still required.
    _cur_result = st.session_state.get(f'{p}_result')
    if _cur_result is not None:
        _cur_ts = _cur_result.get('timestamp')
        if _cur_ts is not None:
            try:
                _cur_ts = str(np.asarray(_cur_ts).item())
            except Exception:
                _cur_ts = str(_cur_ts)
        else:
            _cur_ts = id(_cur_result)
        _last_seen_key = f'{p}_val_last_seen_result_id'
        if st.session_state.get(_last_seen_key) != _cur_ts:
            st.session_state[f'{p}_is_loaded_result'] = True
            st.session_state[_last_seen_key] = _cur_ts

    # ── Delegate to the cadence tab with obs_override ─────────────────────
    if is_dsilva:
        _render_cadence_dsilva_tab(p, settings, sm, obs_override=mock_drv,
                                   n_sets_override=500)
    else:
        _render_cadence_langer_tab(p, settings, sm, obs_override=mock_drv,
                                   n_sets_override=500)

    # ── Post-run: parameter-recovery diagnostics ─────────────────────────
    # TO-TEST: new f_bin(t) + residual panels; see memory/feedback_no_self_approve.md
    if (st.session_state.get(f'{p}_result') is not None
            and st.session_state.get(mock_detail_key) is not None):
        _render_validation_diagnostics(
            p, st.session_state[mock_detail_key], settings,
        )

    # Clear the one-shot "freshly loaded" flag after both bin-config
    # widgets (global via cadence delegation above, explorer via
    # diagnostics) have had a chance to re-seed.  Subsequent user
    # edits to either widget are preserved normally until the next
    # Load click re-arms the flag.
    st.session_state.pop(f'{p}_is_loaded_result', None)


# ─────────────────────────────────────────────────────────────────────────────
# Mock preview (pre-run CDF + binary fraction + table)
# ─────────────────────────────────────────────────────────────────────────────

_CLR_SINGLE = '#E25A53'   # red dots — singles
_CLR_BINARY = '#52B788'   # green dots — binaries

# ─── A&A journal overrides ───────────────────────────────────────────────
# PLOTLY_THEME is currently always DARK (app/shared.py:171 hardcodes
# _DARK_PALETTE), so **PLOTLY_THEME spreads yield a dark figure.  For any
# paper-worthy diagnostic plot, **PLOTLY_THEME first, then **_AA_OVERRIDES
# to force white bg + black serif text.  See memory/feedback_aa_journal_style.md.
_AA_OVERRIDES: dict = dict(
    plot_bgcolor='#FFFFFF', paper_bgcolor='#FFFFFF',
    font=dict(family='Times New Roman, serif', size=12, color='#000000'),
    title=dict(font=dict(color='#000000',
                         family='Times New Roman, serif')),
    xaxis=dict(showgrid=False, linecolor='#000000', linewidth=1,
               mirror=True, ticks='outside', tickcolor='#000000',
               tickfont=dict(color='#000000',
                             family='Times New Roman, serif'),
               title=dict(font=dict(color='#000000',
                                    family='Times New Roman, serif'))),
    yaxis=dict(showgrid=False, linecolor='#000000', linewidth=1,
               mirror=True, ticks='outside', tickcolor='#000000',
               tickfont=dict(color='#000000',
                             family='Times New Roman, serif'),
               title=dict(font=dict(color='#000000',
                                    family='Times New Roman, serif'))),
    legend=dict(bgcolor='rgba(255,255,255,0.9)', bordercolor='#000000',
                borderwidth=1,
                font=dict(color='#000000',
                          family='Times New Roman, serif')),
    hoverlabel=dict(bgcolor='#FFFFFF', bordercolor='#000000',
                    font=dict(color='#000000',
                              family='Times New Roman, serif')),
)

# CDF style constants (cross-file consistency — user feedback 2026-04-28
# Round 5: black mock + GRID red dashed + MARGINAL purple dashed).
# Use these in ALL CDFs (mock preview, all-methods, sanity-check,
# resim-interp, model explorer) so the convention is identical across
# every panel:
#   - observation / mock CDF  → BLACK solid step
#   - grid-best-fit            → RED  '#D62728' dashed (median + 16/84)
#   - marginal-best-fit        → PURPLE '#9467BD' dashed (median + 16/84)
# Single source of truth — do NOT redefine these constants in another
# module; import them from here.
_CDF_OBS_COLOR = '#000000'        # black — observation / mock CDF line
_CDF_FIT_COLOR = '#D62728'        # red   — GRID-argmax simulated CDF (dashed)
_CDF_FIT_MARG_COLOR = '#9467BD'   # purple — MARGINAL-best simulated CDF (dashed)
_CDF_OBS_MARKER = dict(
    color='#000000', size=6, line=dict(color='#333333', width=1),
)


def _render_mock_preview(p: str, detail: dict, thresh_dRV: float,
                         input_fbin: float | None = None,
                         mock_stack: list | None = None) -> None:
    """Render CDF, binary-fraction-vs-threshold and star table for the mock.

    The mock is a single deterministic draw at a fixed seed, so no
    uncertainty band is shown — a single draw has no error to display
    (removed 2026-04-28 per user feedback: a single seed cannot give
    "error shadow"; that band represented generator variability across
    OTHER seeds and was misleading on this single-draw figure).

    The binary-fraction-vs-threshold panel shows the **Input f_bin** —
    the generator parameter the user set (per-star Bernoulli probability
    of being a binary).  Realised f_bin is intentionally NOT displayed
    anywhere on this page — n_binary ≈ round(input × N) is a trivial
    derivation that adds no information (user feedback 2026-04-29).

    Detection uses BOTH binary criteria (CLAUDE.md): ΔRV > threshold AND
    ΔRV − 4σ > 0, where σ = √(σ_min² + σ_max²) from the per-epoch errors
    at the min/max RV epochs (same formula as 02_spectrum.py).
    """
    drv = np.asarray(detail['delta_rv'], dtype=float)
    is_bin = np.asarray(detail['is_binary'], dtype=bool)
    n_stars = int(drv.size)
    if n_stars == 0:
        st.warning('Mock returned zero stars.')
        return

    # Per-star σ_ΔRV from the per-epoch errors at min/max RV epochs.
    # Mirrors the classification convention in app/pages/02_spectrum.py:
    #     σ_ΔRV = √(rv_err[idx_min]² + rv_err[idx_max]²)
    rvs_per_star = detail.get('rvs_per_star', [])
    errs_per_star = detail.get('errs_per_star', [])
    sigma_drv = np.zeros(n_stars, dtype=float)
    for k in range(n_stars):
        rv_k = rvs_per_star[k] if k < len(rvs_per_star) else np.array([])
        err_k = errs_per_star[k] if k < len(errs_per_star) else np.array([])
        if rv_k.size >= 2 and err_k.size == rv_k.size:
            i_min = int(np.argmin(rv_k))
            i_max = int(np.argmax(rv_k))
            sigma_drv[k] = float(np.sqrt(err_k[i_min] ** 2 + err_k[i_max] ** 2))
        else:
            sigma_drv[k] = 0.0

    # Boolean: passes the σ-criterion (ΔRV − 4σ > 0).  Independent of the
    # ΔRV-threshold sweep since σ is per-star.
    passes_sigma = (drv - 4.0 * sigma_drv) > 0.0
    detected = (drv > thresh_dRV) & passes_sigma
    n_detected_binary = int(np.sum(detected & is_bin))
    n_detected_total = int(np.sum(detected))

    if mock_stack is not None and len(mock_stack) > 1:
        st.caption(
            f'📚 **{len(mock_stack)} mocks stacked** — prior generations '
            f'shown as dotted colored lines for distribution inspection. '
            f'The active (most recent) mock drives the recovery run below.'
        )
    st.markdown('#### Mock Observations Preview')
    _input_str = (f'Input f_bin = {input_fbin:.1%}.  '
                  if input_fbin is not None else '')
    st.caption(
        f'{_input_str}'
        f'Detected (ΔRV > {thresh_dRV:.1f} km/s AND ΔRV − 4σ > 0): '
        f'**{n_detected_total}** stars '
        f'({n_detected_binary} true binary, '
        f'{n_detected_total - n_detected_binary} false positive).'
    )

    left_col, right_col = st.columns(2)

    # ── CDF plot ──────────────────────────────────────────────────────────
    sorted_idx = np.argsort(drv)
    drv_sorted = drv[sorted_idx]
    cdf_vals = (np.arange(n_stars) + 1) / n_stars
    is_bin_sorted = is_bin[sorted_idx]

    fig_cdf = go.Figure()
    fig_cdf.add_trace(go.Scatter(
        x=drv_sorted, y=cdf_vals, mode='lines',
        line=dict(color=_CDF_OBS_COLOR, width=2.5, shape='hv'),
        name='Mock CDF',
        hovertemplate='ΔRV=%{x:.1f} km/s<br>CDF=%{y:.3f}<extra></extra>',
    ))
    sigma_drv_sorted = sigma_drv[sorted_idx]
    # Single dots (red) — horizontal error bars = σ_ΔRV
    single_mask_sorted = ~is_bin_sorted
    if np.any(single_mask_sorted):
        fig_cdf.add_trace(go.Scatter(
            x=drv_sorted[single_mask_sorted],
            y=cdf_vals[single_mask_sorted],
            mode='markers',
            marker=dict(color=_CLR_SINGLE, size=8,
                        line=dict(color='black', width=0.6)),
            error_x=dict(
                type='data',
                array=sigma_drv_sorted[single_mask_sorted],
                visible=True, thickness=1.2, width=3,
                color='rgba(0,0,0,0.55)'),
            name='Single',
            hovertemplate=('single · ΔRV=%{x:.1f} ± '
                           '%{error_x.array:.1f} km/s<extra></extra>'),
        ))
    # Binary dots (green) — horizontal error bars = σ_ΔRV
    if np.any(is_bin_sorted):
        fig_cdf.add_trace(go.Scatter(
            x=drv_sorted[is_bin_sorted],
            y=cdf_vals[is_bin_sorted],
            mode='markers',
            marker=dict(color=_CLR_BINARY, size=8,
                        line=dict(color='black', width=0.6)),
            error_x=dict(
                type='data',
                array=sigma_drv_sorted[is_bin_sorted],
                visible=True, thickness=1.2, width=3,
                color='rgba(0,0,0,0.55)'),
            name='Binary',
            hovertemplate=('binary · ΔRV=%{x:.1f} ± '
                           '%{error_x.array:.1f} km/s<extra></extra>'),
        ))
    # Prior mocks in the stack — visual stack for distribution inspection.
    # Skip the last entry (it's the current mock, already drawn above).
    if mock_stack and len(mock_stack) > 1:
        for _prior in mock_stack[:-1]:
            _pdrv = np.asarray(_prior['delta_rv'], dtype=float)
            if _pdrv.size == 0:
                continue
            _pidx = np.argsort(_pdrv)
            _pds = _pdrv[_pidx]
            _pcdf = (np.arange(_pdrv.size) + 1) / float(_pdrv.size)
            fig_cdf.add_trace(go.Scatter(
                x=_pds, y=_pcdf, mode='lines',
                line=dict(color=_prior['color'], width=1.4,
                          shape='hv', dash='dot'),
                opacity=0.7,
                name=(f"#{_prior['id']} · seed={_prior['seed']} · "
                      f"f_bin={_prior['true_fbin']:.2f}"),
                hovertemplate=(f"#{_prior['id']} · ΔRV=%{{x:.1f}} "
                               "km/s<br>CDF=%{y:.3f}<extra></extra>"),
                legendgroup=f"stack_{_prior['id']}",
            ))
    fig_cdf.add_vline(
        x=thresh_dRV, line_dash='dash', line_color='#F5A623', line_width=1.5,
        annotation_text=f'{thresh_dRV:.1f} km/s',
        annotation_position='top right', annotation_font_color='#F5A623',
    )
    fig_cdf.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(text='Mock ΔRV Empirical CDF', font=dict(size=14)),
        'xaxis_title': 'ΔRV (km/s)',
        'yaxis_title': 'Cumulative fraction',
        'height': 360,
        'margin': dict(l=60, r=30, t=50, b=50),
        'legend': dict(x=0.55, y=0.25, font=dict(size=10)),
    })
    # A&A journal theme (white bg, black serif text) — see feedback_aa_journal_style
    fig_cdf.update_layout(**_AA_OVERRIDES)
    fig_cdf.update_xaxes(**_AA_OVERRIDES['xaxis'])
    fig_cdf.update_yaxes(**_AA_OVERRIDES['yaxis'])
    left_col.plotly_chart(fig_cdf, use_container_width=True,
                          key=f'{p}_val_mock_cdf')

    # ── Binary fraction vs threshold ──────────────────────────────────────
    # Detection uses BOTH criteria (CLAUDE.md): drv > t AND drv - 4σ > 0.
    drv_max = max(float(np.max(drv)), thresh_dRV) * 1.05 if n_stars > 0 else 100.0
    thresh_arr = np.linspace(0.0, drv_max, 200)
    # Vectorised: rows = thresholds, cols = stars
    drv_row = drv[None, :]
    pass_sig_row = passes_sigma[None, :]
    is_bin_row = is_bin[None, :]
    detected_mat = (drv_row > thresh_arr[:, None]) & pass_sig_row
    fbin_curve = detected_mat.sum(axis=1) / float(n_stars)
    missed_curve = (is_bin_row & ~detected_mat).sum(axis=1) / float(n_stars)
    fp_curve = (~is_bin_row & detected_mat).sum(axis=1) / float(n_stars)

    fig_fb = go.Figure()
    # Missed/false-positive area fills FIRST so the central line renders on top.
    fig_fb.add_trace(go.Scatter(
        x=thresh_arr, y=missed_curve, fill='tozeroy',
        fillcolor='rgba(242,166,35,0.25)',
        line=dict(width=0), mode='lines',
        name='Missed binaries (failing 2-criteria)', showlegend=True,
    ))
    if np.any(fp_curve > 0):
        fig_fb.add_trace(go.Scatter(
            x=thresh_arr, y=fp_curve, fill='tozeroy',
            fillcolor='rgba(74,144,217,0.25)',
            line=dict(width=0), mode='lines',
            name='Single false positives', showlegend=True,
        ))
    fig_fb.add_trace(go.Scatter(
        x=thresh_arr, y=fbin_curve, mode='lines',
        line=dict(color='#4A90D9', width=2.5),
        name='Detected f_bin(threshold) — 2 criteria',
    ))
    # Input f_bin (the generator parameter the user set).
    if input_fbin is not None:
        fig_fb.add_hline(
            y=float(input_fbin), line_dash='solid',
            line_color='#F5A623', line_width=2,
            annotation_text=f'Input f_bin = {input_fbin:.1%}',
            annotation_position='bottom left',
            annotation_font=dict(size=11, color='#F5A623'),
        )
    fig_fb.add_vline(
        x=thresh_dRV, line_dash='dash', line_color='#F5A623', line_width=2,
        annotation_text=f'Threshold = {thresh_dRV} km/s',
        annotation_position='top right',
        annotation_font=dict(size=11, color='#F5A623'),
    )
    # Overlay per-star dots at the CDF value y = (N - rank(ΔRV))/N (fraction above)
    drv_rank = np.argsort(np.argsort(drv))
    y_stars = (n_stars - drv_rank) / n_stars
    if np.any(~is_bin):
        fig_fb.add_trace(go.Scatter(
            x=drv[~is_bin], y=y_stars[~is_bin], mode='markers',
            marker=dict(color=_CLR_SINGLE, size=8,
                        line=dict(color='black', width=0.6)),
            error_x=dict(
                type='data', array=sigma_drv[~is_bin],
                visible=True, thickness=1.2, width=3,
                color='rgba(0,0,0,0.55)'),
            name='Single',
            hovertemplate=('single · ΔRV=%{x:.1f} ± '
                           '%{error_x.array:.1f} km/s · '
                           'fraction above=%{y:.3f}<extra></extra>'),
        ))
    if np.any(is_bin):
        fig_fb.add_trace(go.Scatter(
            x=drv[is_bin], y=y_stars[is_bin], mode='markers',
            marker=dict(color=_CLR_BINARY, size=8,
                        line=dict(color='black', width=0.6)),
            error_x=dict(
                type='data', array=sigma_drv[is_bin],
                visible=True, thickness=1.2, width=3,
                color='rgba(0,0,0,0.55)'),
            name='Binary',
            hovertemplate=('binary · ΔRV=%{x:.1f} ± '
                           '%{error_x.array:.1f} km/s · '
                           'fraction above=%{y:.3f}<extra></extra>'),
        ))
    fig_fb.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(text='Mock Binary Fraction vs ΔRV Threshold',
                      font=dict(size=14)),
        'xaxis_title': 'ΔRV threshold (km/s)',
        'yaxis_title': 'Fraction of sample',
        'height': 360,
        'margin': dict(l=60, r=30, t=50, b=50),
        'legend': dict(x=0.55, y=0.95, font=dict(size=10)),
        'yaxis': dict(range=[0.0, 1.0]),
    })
    # A&A journal theme (white bg, black serif text) — see feedback_aa_journal_style
    fig_fb.update_layout(**_AA_OVERRIDES)
    fig_fb.update_xaxes(**_AA_OVERRIDES['xaxis'])
    fig_fb.update_yaxes(**_AA_OVERRIDES['yaxis'], range=[0.0, 1.0])
    right_col.plotly_chart(fig_fb, use_container_width=True,
                           key=f'{p}_val_mock_fbin')

    # ── Star table ────────────────────────────────────────────────────────
    st.markdown('##### Mock Star Table')
    rv_min = np.asarray(detail.get('rv_min', np.full(n_stars, np.nan)))
    rv_max_arr = np.asarray(detail.get('rv_max', np.full(n_stars, np.nan)))
    n_epochs = np.asarray(detail.get('n_epochs', np.zeros(n_stars, dtype=int)))

    rows = []
    for k in range(n_stars):
        rv_k = rvs_per_star[k] if k < len(rvs_per_star) else np.array([])
        if rv_k.size > 0:
            rv_str = ', '.join(f'{v:.1f}' for v in rv_k)
        else:
            rv_str = '—'
        rows.append({
            '#': k + 1,
            'Type': 'Binary' if bool(is_bin[k]) else 'Single',
            'N_ep': int(n_epochs[k]) if k < n_epochs.size else 0,
            'RV_min (km/s)': float(rv_min[k]) if k < rv_min.size else np.nan,
            'RV_max (km/s)': float(rv_max_arr[k]) if k < rv_max_arr.size else np.nan,
            'ΔRV p2p (km/s)': float(drv[k]),
            'σ_ΔRV (km/s)': float(sigma_drv[k]),
            'Detected (2-crit)': 'Yes' if bool(detected[k]) else 'No',
            'RVs per epoch (km/s)': rv_str,
        })
    df = pd.DataFrame(rows)

    def _color_type(val):
        if val == 'Binary':
            return 'background-color: rgba(82, 183, 136, 0.3)'
        if val == 'Single':
            return 'background-color: rgba(226, 90, 83, 0.3)'
        return ''

    def _color_detected(val):
        if val == 'Yes':
            return 'background-color: rgba(74, 144, 217, 0.3)'
        return ''

    styled = (df.style
              .map(_color_type, subset=['Type'])
              .map(_color_detected, subset=['Detected (2-crit)'])
              .format({
                  'RV_min (km/s)': '{:.2f}',
                  'RV_max (km/s)': '{:.2f}',
                  'ΔRV p2p (km/s)': '{:.2f}',
                  'σ_ΔRV (km/s)': '{:.2f}',
              }))
    st.dataframe(styled, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# Parameter Recovery Diagnostics (post-run): f_bin(ΔRV) + CDF w/ residuals
# TO-TEST — new diagnostics section (2026-04-20). Not visually approved yet.
# ─────────────────────────────────────────────────────────────────────────────

def _best_fit_from_result(result: dict, is_dsilva: bool,
                          p: str) -> dict:
    """Replicate ``_find_best_model`` locally to avoid cadence.py import cycle.

    The 4-D likelihood axis order in ``runners_cadence.py`` is
    ``(n_logPmax, n_sigma, n_fbin, n_pi)`` — same convention used by
    ``app/bc/cadence.py::_find_best_model`` at line 47.  Lower-dim arrays
    drop the missing leading axes.
    """
    lk = np.asarray(result.get('likelihood'))
    fbin_grid = np.asarray(result.get('fbin_grid', []))
    pi_grid = np.asarray(result.get('pi_grid', []))
    sigma_grid = np.asarray(result.get('sigma_grid', []))
    logPmax_grid = np.asarray(result.get('logPmax_grid', []))

    out = {'f_bin': np.nan, 'pi': np.nan,
           'sigma_single': np.nan, 'logP_max': np.nan}
    if lk.size == 0 or not np.any(np.isfinite(lk)):
        return out

    flat = int(np.nanargmax(lk))
    shape = lk.shape
    if lk.ndim == 4:
        lp_idx = flat // (shape[1] * shape[2] * shape[3])
        rem = flat % (shape[1] * shape[2] * shape[3])
        sig_idx = rem // (shape[2] * shape[3])
        fb_idx = (rem // shape[3]) % shape[2]
        pi_idx = rem % shape[3]
    elif lk.ndim == 3:
        lp_idx = 0
        sig_idx = flat // (shape[1] * shape[2])
        fb_idx = (flat // shape[2]) % shape[1]
        pi_idx = flat % shape[2]
    elif lk.ndim == 2:
        lp_idx = 0
        sig_idx = 0
        fb_idx = flat // shape[1]
        pi_idx = flat % shape[1]
    else:
        return out

    if fbin_grid.size > 0:
        out['f_bin'] = float(fbin_grid[fb_idx])
    if pi_grid.size > 0 and is_dsilva:
        out['pi'] = float(pi_grid[pi_idx])
    elif not is_dsilva:
        out['pi'] = 0.0
    if sigma_grid.size > 0:
        out['sigma_single'] = float(sigma_grid[sig_idx])
    # B2 fix: logP_max must be a real number, never NaN.  Priority order:
    #   1. logPmax_grid[lp_idx] when the grid scans logPmax
    #   2. argmax_logPmax stored on the result (single-slice runs still
    #      persist the scalar grid value)
    #   3. A scalar 'logP_max' key on the result (legacy .npz)
    #   4. bin_cfg.logP_max / 5.0 as an absolute last resort (NOT session
    #      state — that can drift while the user fiddles sliders)
    if logPmax_grid.size > 0:
        out['logP_max'] = float(logPmax_grid[lp_idx])
    else:
        _fallback_lp = result.get('argmax_logPmax')
        try:
            _fallback_lp_f = float(_fallback_lp) if _fallback_lp is not None else float('nan')
        except (TypeError, ValueError):
            _fallback_lp_f = float('nan')
        if not np.isfinite(_fallback_lp_f):
            _alt = result.get('logP_max')
            try:
                _fallback_lp_f = float(_alt) if _alt is not None else float('nan')
            except (TypeError, ValueError):
                _fallback_lp_f = float('nan')
        if not np.isfinite(_fallback_lp_f):
            _bc_dict = result.get('bin_cfg')
            if isinstance(_bc_dict, dict):
                try:
                    _fallback_lp_f = float(_bc_dict.get('logP_max', 5.0))
                except (TypeError, ValueError):
                    _fallback_lp_f = 5.0
            else:
                _fallback_lp_f = 5.0
        out['logP_max'] = float(_fallback_lp_f)
    return out


def _render_validation_diagnostics(p: str, mock_detail: dict,
                                   settings: dict) -> None:
    """Post-run diagnostic panels: truth-vs-recovered + f_bin(t) + CDF.

    Guards: silently no-op if the result / mock_detail artefacts are
    missing (i.e. the delegated cadence run has not completed yet).
    """
    result = st.session_state.get(f'{p}_result')
    if result is None:
        return
    if mock_detail is None:
        return

    period_model = result.get('period_model', 'powerlaw')
    is_dsilva = (period_model == 'powerlaw')

    st.markdown('---')
    st.markdown('### Parameter Recovery Diagnostics')
    st.caption(
        'f_bin(t) and the ΔRV CDF probe *different* directions in '
        'parameter space — a tight CDF residual does NOT imply small '
        '(f_bin, π) error.  Use both panels together to catch '
        '"good-looking-CDF / bad-fit" cases.'
    )

    # ── Ground truth + best-fit ──────────────────────────────────────────
    truth = st.session_state.get(f'{p}_val_mock_params')
    if truth is None:
        st.info('Mock ground-truth parameters not found in session state.')
        return
    true_fbin, true_pi, true_sigma, true_logPmax = (
        float(truth[0]), float(truth[1]),
        float(truth[2]), float(truth[3]))

    rec = _best_fit_from_result(result, is_dsilva, p)

    # ── Panel 0: Truth vs Recovered table ────────────────────────────────
    fbin_grid = np.asarray(result.get('fbin_grid', []))
    pi_grid = np.asarray(result.get('pi_grid', []))
    sigma_grid = np.asarray(result.get('sigma_grid', []))
    logPmax_grid = np.asarray(result.get('logPmax_grid', []))

    def _grid_step(g: np.ndarray) -> float:
        g = np.asarray(g, dtype=float)
        if g.size < 2:
            return np.nan
        return float(np.median(np.diff(np.sort(g))))

    # C2 (2026-04-23): the summary table's 68% HDI must agree with the
    # Corner Plot's HDI shading.  Both now read from the SAME function,
    # bc.analysis._method_best_and_hdi, so there is one canonical source.
    # This replaces the older "read lo_*_L / hi_*_L from the result dict"
    # path which used a different marginalisation convention for 4-D data
    # (np.nanmax over logPmax + np.sum over others vs. _method_best_and_hdi's
    # uniform np.nansum over all-but-one axis).
    from bc.analysis import _method_best_and_hdi as _mbh

    _lk_arr = np.asarray(result.get('likelihood'))

    # Bug 3 fix (2026-04-27): the previous build-grids-then-squeeze
    # approach silently dropped the WRONG axis whenever logPmax was
    # scanned but sigma was a single-point axis (or vice versa) — the
    # blind ``_lk_sq[0]`` lopped off whichever leading axis happened to
    # be there, even if the names list still expected it.  That is why
    # the displayed 68% HDI sometimes failed to bracket the joint
    # argmax: the marginal posterior was being computed over the wrong
    # axes, so its mode (and HDI) referred to a different parameter
    # than the table column claimed.
    #
    # Fix: always pass the FULL 4-D layout that
    # ``runners_cadence._build_tasks_for_slice`` produces — namely
    # ``(n_logPmax, n_sigma, n_fbin, n_pi)`` — and rely on the canonical
    # marginalisation in ``_method_best_and_hdi``.  Size-1 axes are
    # handled correctly by that routine: ``np.nansum`` over a size-1
    # axis is a no-op, so the HDI for that parameter collapses to the
    # sole grid value (lo == hi == mode).
    _grids_mbh = [
        logPmax_grid if logPmax_grid.size else np.array([np.nan]),
        sigma_grid if sigma_grid.size else np.array([np.nan]),
        fbin_grid,
        pi_grid if pi_grid.size else np.array([0.0]),
    ]
    _names_mbh = ['logPmax', 'sigma', 'fbin', 'pi']

    # Promote the likelihood to 4-D matching the runner's layout.
    # 3-D (sigma, fbin, pi) → prepend logPmax axis (size-1).
    # 2-D (fbin, pi) → prepend logPmax + sigma axes (both size-1).
    _lk_sq = _lk_arr.copy() if _lk_arr is not None else None
    if _lk_sq is not None:
        if _lk_sq.ndim == 3:
            _lk_sq = _lk_sq[np.newaxis, ...]
        elif _lk_sq.ndim == 2:
            _lk_sq = _lk_sq[np.newaxis, np.newaxis, ...]
        elif _lk_sq.ndim == 1:
            _lk_sq = _lk_sq[np.newaxis, np.newaxis, np.newaxis, ...]
        # Sanity: each axis size must match the grid we paired it with.
        # If not, fall back to None — the table will show '— (grid step)'.
        try:
            for _i, _g in enumerate(_grids_mbh):
                if _lk_sq.shape[_i] != len(_g):
                    _lk_sq = None
                    break
        except (IndexError, AttributeError):
            _lk_sq = None

    _hdi_info = (
        _mbh(_lk_sq, _grids_mbh, _names_mbh, is_likelihood=True)
        if (_lk_sq is not None and _lk_sq.size > 0) else None
    )
    _hdi_map = _hdi_info['hdi'] if _hdi_info else {}

    def _hdi_from_mbh(name: str) -> tuple[float, float, float]:
        """Return (mode, lo, hi) from the canonical _method_best_and_hdi call,
        or (nan, nan, nan) when the axis is not in the posterior."""
        t = _hdi_map.get(name)
        if t is None:
            return (float('nan'), float('nan'), float('nan'))
        try:
            return (float(t[0]), float(t[1]), float(t[2]))
        except (TypeError, ValueError, IndexError):
            return (float('nan'), float('nan'), float('nan'))

    # Bug 1b HDI (2026-04-28): the user explicitly authorised showing the
    # marginal-posterior peak in addition to the joint argmax — see the
    # task brief.  This overrides the prior "joint-argmax + HDI only"
    # rule (memory/feedback_honest_labels.md).  The marginal max is the
    # FIRST element of compute_hdi68's tuple (mode of the marginal).
    mode_fb_v, lo_fb_v, hi_fb_v = _hdi_from_mbh('fbin')
    mode_pi_v, lo_pi_v, hi_pi_v = _hdi_from_mbh('pi')
    mode_sig_v, lo_sig_v, hi_sig_v = _hdi_from_mbh('sigma')
    # logPmax marginal mode (when scanned).  Reuse the same _hdi_map lookup
    # so the value comes from the same canonical _method_best_and_hdi call.
    mode_lp_v, lo_lp_v, hi_lp_v = _hdi_from_mbh('logPmax')

    def _half_width_or_step(lo, hi, fallback_grid):
        if np.isfinite(lo) and np.isfinite(hi):
            return float(abs(hi - lo) / 2.0)
        return _grid_step(fallback_grid)

    sig_fbin = _half_width_or_step(lo_fb_v, hi_fb_v, fbin_grid)
    sig_pi = _half_width_or_step(lo_pi_v, hi_pi_v, pi_grid)
    sig_sigma = _half_width_or_step(lo_sig_v, hi_sig_v, sigma_grid)
    sig_logP = _grid_step(logPmax_grid)

    # Flag: did each row use a real HDI half-width, or grid-step fallback?
    def _is_real_hdi(lo, hi):
        return np.isfinite(lo) and np.isfinite(hi)

    # WORKING — do not change this code (diagnostic summary table; user-approved 2026-04-28)
    # Each row carries (label, true, joint_argmax, sigma_for_z, active,
    # marginal_max, hdi_lo, hdi_hi, real_hdi_flag).
    rows = [
        ('f_bin', true_fbin, rec['f_bin'], sig_fbin, True,
         mode_fb_v, lo_fb_v, hi_fb_v, _is_real_hdi(lo_fb_v, hi_fb_v)),
        ('π', true_pi, rec['pi'], sig_pi, is_dsilva,
         mode_pi_v, lo_pi_v, hi_pi_v, _is_real_hdi(lo_pi_v, hi_pi_v)),
        ('σ_single (km/s)', true_sigma, rec['sigma_single'], sig_sigma, True,
         mode_sig_v, lo_sig_v, hi_sig_v, _is_real_hdi(lo_sig_v, hi_sig_v)),
        ('logP_max', true_logPmax, rec['logP_max'], sig_logP, True,
         mode_lp_v, lo_lp_v, hi_lp_v, _is_real_hdi(lo_lp_v, hi_lp_v)),
    ]

    def _fmt_hdi_cell(lo, hi, real):
        if real and np.isfinite(lo) and np.isfinite(hi):
            return f'[{lo:.3f}, {hi:.3f}]'
        return '— (grid step)'

    def _fmt_marg(mv):
        return f'{mv:.3f}' if np.isfinite(mv) else '—'

    table_rows = []
    for label, tv, rv, sv, active, mv, lo_v, hi_v, real_hdi in rows:
        if not active:
            table_rows.append({
                'Parameter': label,
                'True': f'{tv:.3f}' if np.isfinite(tv) else '—',
                'Joint argmax': '— (fixed)',
                'Marginal max': '— (fixed)',
                '68% HDI': '—',
                '|Δ|': '—',
                'rel. error': '—',
                '|Δ| / HDI_half_width': '—',
            })
            continue
        if np.isfinite(tv) and np.isfinite(rv):
            delta = abs(rv - tv)
            rel = (delta / abs(tv)) if abs(tv) > 1e-12 else np.nan
            z = (delta / sv) if (np.isfinite(sv) and sv > 0) else np.nan
            table_rows.append({
                'Parameter': label,
                'True': f'{tv:.3f}',
                'Joint argmax': f'{rv:.3f}',
                'Marginal max': _fmt_marg(mv),
                '68% HDI': _fmt_hdi_cell(lo_v, hi_v, real_hdi),
                '|Δ|': f'{delta:.3f}',
                'rel. error': (f'{rel * 100:.1f}%'
                               if np.isfinite(rel) else '—'),
                '|Δ| / HDI_half_width': (f'{z:.2f}'
                            if np.isfinite(z) else '—'),
            })
        else:
            table_rows.append({
                'Parameter': label,
                'True': f'{tv:.3f}' if np.isfinite(tv) else '—',
                'Joint argmax': f'{rv:.3f}' if np.isfinite(rv) else '—',
                'Marginal max': _fmt_marg(mv),
                '68% HDI': _fmt_hdi_cell(lo_v, hi_v, real_hdi),
                '|Δ|': '—',
                'rel. error': '—',
                '|Δ| / HDI_half_width': '—',
            })

    df_tab = pd.DataFrame(table_rows)

    def _highlight_row(row):
        # Grey-out the π row for Langer (fixed).
        if (not is_dsilva) and row['Parameter'] == 'π':
            return ['color: #888888; font-style: italic'] * len(row)
        # Red row if |Δ| > 1 HDI half-width
        try:
            z_str = row['|Δ| / HDI_half_width']
            if z_str not in ('—', '') and float(z_str) > 1.0:
                return ['background-color: rgba(226, 90, 83, 0.22)'] * len(row)
        except (ValueError, TypeError):
            pass
        return [''] * len(row)

    styled_tab = df_tab.style.apply(_highlight_row, axis=1)
    st.dataframe(styled_tab, use_container_width=True, hide_index=True)
    st.caption(
        '**Joint argmax**: global maximum of the joint likelihood grid '
        '(no marginalisation). **Marginal max**: peak of the 1-D marginal '
        'posterior obtained by summing the joint likelihood over all other '
        'axes — should match the visual peak in the marginalised posterior '
        'plots. **68% HDI**: highest-density interval of the marginal '
        'posterior for that parameter. **|Δ| / HDI_half_width**: signed '
        'distance between truth and joint argmax, normalised by half the '
        'HDI width; values > 1 indicate the truth lies outside the 68% HDI. '
        'For axes with a single grid value the HDI collapses to that value '
        'and the grid step is used as the fallback denominator.'
    )
    # END WORKING — diagnostic summary table

    # ── Data arrays for panels ───────────────────────────────────────────
    drv_mock = np.asarray(mock_detail['delta_rv'], dtype=float)
    is_bin_mock = np.asarray(mock_detail['is_binary'], dtype=bool)
    n_mock = int(drv_mock.size)
    if n_mock == 0:
        st.warning('Mock ΔRV array is empty — cannot render diagnostics.')
        return

    gap_sim = st.session_state.get(f'{p}_gap_sim')
    drv_sim = None
    if gap_sim is not None and gap_sim.get('delta_rv') is not None:
        drv_sim = np.asarray(gap_sim['delta_rv'], dtype=float)
        drv_sim = drv_sim[np.isfinite(drv_sim)]
        if drv_sim.size == 0:
            drv_sim = None

    # Common x-range for both panels
    _max_mock = float(np.max(drv_mock)) if n_mock > 0 else 0.0
    _max_sim = float(np.max(drv_sim)) if drv_sim is not None else 0.0
    drv_span = max(_max_mock, _max_sim, 1.0) * 1.05

    thresh_dRV = float(settings.get('classification', {})
                       .get('threshold_dRV', 45.5))

    # ── Panel A: f_bin(ΔRV) overlay + residual ───────────────────────────
    _render_panel_a_fbin(
        p, drv_mock, is_bin_mock, drv_sim,
        rec['f_bin'], thresh_dRV, drv_span, gap_sim is not None,
    )

    # ── Panel B: ΔRV CDF overlay + residual ──────────────────────────────
    # Round-5 (2026-04-28): pass BOTH grid-argmax and marginal-best param
    # tuples so Panel B can show two simulated CDFs (red = grid, purple =
    # marginal).  The marginal-max values come from the same canonical
    # _method_best_and_hdi call used to populate the summary table above
    # — see `_hdi_from_mbh` and `mode_*_v` at lines 888-893.
    _grid_params = {
        'f_bin': float(rec['f_bin']),
        'pi': float(rec['pi']),
        'sigma': float(rec['sigma_single']),
        'logP_max': float(rec['logP_max']),
    }
    _marg_params = {
        'f_bin': (float(mode_fb_v) if np.isfinite(mode_fb_v)
                  else _grid_params['f_bin']),
        'pi': (float(mode_pi_v) if np.isfinite(mode_pi_v)
               else _grid_params['pi']),
        'sigma': (float(mode_sig_v) if np.isfinite(mode_sig_v)
                  else _grid_params['sigma']),
        'logP_max': (float(mode_lp_v) if np.isfinite(mode_lp_v)
                     else _grid_params['logP_max']),
    }
    _render_panel_b_cdf(
        p, drv_mock, is_bin_mock, drv_sim, thresh_dRV, drv_span,
        gap_sim is not None,
        grid_params=_grid_params, marg_params=_marg_params,
        result=result, settings=settings,
    )


def _render_panel_a_fbin(
    p: str,
    drv_mock: np.ndarray,
    is_bin_mock: np.ndarray,
    drv_sim: np.ndarray | None,
    recovered_fbin: float,
    thresh_dRV: float,
    drv_span: float,
    have_sim: bool,
) -> None:
    """Panel A: f_bin(t) = P(ΔRV > t) — overlay + residual vs best-fit sim."""
    from plotly.subplots import make_subplots

    st.markdown('#### Panel A — f_bin(ΔRV) overlay + residual')
    st.caption(
        'Upper: f_bin(t) = fraction of sample with ΔRV > t.  Black stairs = '
        'mock empirical; blue line = best-fit simulation (~10 000 stars).  '
        'Lower: mock − sim residual with ±1/√N Poisson band.'
    )

    n_mock = int(drv_mock.size)
    thresh_arr = np.linspace(0.0, drv_span, 300)

    # f_bin from an empirical sample: fraction with drv > t
    def _fbin_of(sample: np.ndarray, grid: np.ndarray) -> np.ndarray:
        sample = np.asarray(sample, dtype=float)
        sample = sample[np.isfinite(sample)]
        n = sample.size
        if n == 0:
            return np.zeros_like(grid)
        ss = np.sort(sample)
        # count above t == n - searchsorted(ss, t, side='right')
        counts = n - np.searchsorted(ss, grid, side='right')
        return counts.astype(float) / n

    fb_mock_curve = _fbin_of(drv_mock, thresh_arr)
    if drv_sim is not None:
        fb_sim_curve = _fbin_of(drv_sim, thresh_arr)
    else:
        fb_sim_curve = None

    # Per-star dots at their own (drv, fbin_mock(drv))
    mock_rank = np.argsort(np.argsort(drv_mock))
    y_stars = (n_mock - mock_rank - 1) / n_mock  # P(ΔRV > drv_k), exclusive

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.70, 0.30], vertical_spacing=0.06,
    )

    # ── Upper subplot (row 1) ──
    fig.add_trace(go.Scatter(
        x=thresh_arr, y=fb_mock_curve, mode='lines',
        line=dict(color='#000000', width=2.5, shape='hv'),
        name='Mock f_bin(t)',
        hovertemplate='t=%{x:.1f} km/s<br>f_bin=%{y:.3f}<extra>Mock</extra>',
    ), row=1, col=1)

    if fb_sim_curve is not None:
        fig.add_trace(go.Scatter(
            x=thresh_arr, y=fb_sim_curve, mode='lines',
            line=dict(color='#4A90D9', width=2),
            name='Best-fit sim f_bin(t)',
            hovertemplate=('t=%{x:.1f} km/s<br>f_bin=%{y:.3f}'
                           '<extra>Sim</extra>'),
        ), row=1, col=1)

    # Single dots (red), binary dots (green)
    single_mask = ~is_bin_mock
    if np.any(single_mask):
        fig.add_trace(go.Scatter(
            x=drv_mock[single_mask], y=y_stars[single_mask],
            mode='markers',
            marker=dict(color=_CLR_SINGLE, size=7,
                        line=dict(color='black', width=0.5)),
            name=f'Single ({int(single_mask.sum())})',
            hovertemplate=('single · ΔRV=%{x:.1f} km/s · '
                           'f_bin=%{y:.3f}<extra></extra>'),
        ), row=1, col=1)
    if np.any(is_bin_mock):
        fig.add_trace(go.Scatter(
            x=drv_mock[is_bin_mock], y=y_stars[is_bin_mock],
            mode='markers',
            marker=dict(color=_CLR_BINARY, size=7,
                        line=dict(color='black', width=0.5)),
            name=f'Binary ({int(is_bin_mock.sum())})',
            hovertemplate=('binary · ΔRV=%{x:.1f} km/s · '
                           'f_bin=%{y:.3f}<extra></extra>'),
        ), row=1, col=1)

    # Horizontal dashed line at recovered f_bin.  Annotation text is black
    # on white bg (WCAG ≥ 4.5:1) — line color carries the semantic cue.
    # (realised f_bin line dropped 2026-04-29 per user feedback — trivial
    # derivation from input × N, adds no information.)
    if np.isfinite(recovered_fbin):
        fig.add_hline(
            y=recovered_fbin, line_dash='dash',
            line_color='#DAA520', line_width=1.5,
            annotation_text=f'recovered f_bin = {recovered_fbin:.2f}',
            annotation_position='bottom left',
            annotation_font=dict(size=10, color='#000000',
                                 family='Times New Roman, serif'),
            row=1, col=1,
        )
    # Detection threshold (dark gold best-fit marker colour)
    fig.add_vline(
        x=thresh_dRV, line_dash='dash',
        line_color='#DAA520', line_width=1.5,
        annotation_text=f'{thresh_dRV:.1f} km/s',
        annotation_position='top right',
        annotation_font=dict(size=10, color='#000000',
                             family='Times New Roman, serif'),
        row=1, col=1,
    )

    # ── Lower subplot (row 2): residual ──
    if fb_sim_curve is not None:
        resid = fb_mock_curve - fb_sim_curve
        fig.add_trace(go.Scatter(
            x=thresh_arr, y=resid, mode='lines', fill='tozeroy',
            line=dict(color='#8c564b', width=1.5),
            fillcolor='rgba(140,86,75,0.25)',
            name='mock − sim', showlegend=False,
            hovertemplate=('t=%{x:.1f} km/s<br>Δf_bin=%{y:.3f}'
                           '<extra></extra>'),
        ), row=2, col=1)

        # ±1/√N Poisson band
        poisson_sigma = 1.0 / np.sqrt(max(n_mock, 1))
        band_x = np.concatenate([thresh_arr, thresh_arr[::-1]])
        band_y = np.concatenate([
            np.full_like(thresh_arr, +poisson_sigma),
            np.full_like(thresh_arr, -poisson_sigma)[::-1],
        ])
        fig.add_trace(go.Scatter(
            x=band_x, y=band_y, fill='toself',
            fillcolor='rgba(128,128,128,0.15)',
            line=dict(width=0), mode='lines',
            name='±1/√N', showlegend=False,
            hoverinfo='skip',
        ), row=2, col=1)

    # Residual zero reference — mid-grey dashed, paper-safe on white
    fig.add_hline(y=0.0, line_dash='dash', line_color='#555555',
                  line_width=1, row=2, col=1)

    # Layout: A&A white bg + black serif text.  PLOTLY_THEME supplies
    # layout shape; _AA_OVERRIDES forces paper-ready colours on top.
    fig.update_layout(**{
        **PLOTLY_THEME,
        **_AA_OVERRIDES,
        'height': 480,
        'margin': dict(l=60, r=30, t=40, b=55),
        'title': dict(text='',
                      font=dict(size=14, color='#000000',
                                family='Times New Roman, serif')),
        'legend': dict(x=0.60, y=0.98,
                       font=dict(size=10, color='#000000',
                                 family='Times New Roman, serif'),
                       bgcolor='rgba(255,255,255,0.9)',
                       bordercolor='#000000', borderwidth=1),
    })
    # A&A-style axes for both rows (mirrored black, outside ticks, no grid)
    fig.update_xaxes(**_AA_OVERRIDES['xaxis'])
    fig.update_yaxes(**_AA_OVERRIDES['yaxis'])
    # Row-specific titles / range (must come AFTER the bulk update)
    fig.update_yaxes(title_text='f_bin(t)', range=[-0.02, 1.02],
                     row=1, col=1)
    fig.update_yaxes(title_text='Δf_bin', row=2, col=1)
    fig.update_xaxes(title_text='ΔRV threshold t (km/s)',
                     row=2, col=1)

    st.plotly_chart(fig, use_container_width=True,
                    key=f'{p}_val_diag_panel_a')

    if not have_sim:
        st.info('Best-fit simulation not yet available — showing mock curve '
                'only.  Run the grid first to populate the blue sim line.')


def _simulate_marginal_drv(
    marg_params: dict, result: dict, settings: dict | None,
    cache_key: str,
) -> 'np.ndarray | None':
    """Simulate a 10 000-star population at the MARGINAL-best parameter
    tuple, mirroring the 'gap_sim' build in cadence.py:646.

    Cached in ``st.session_state[cache_key]`` keyed on a fingerprint of
    the marginal params + likelihood shape so we do not redraw on every
    rerun.  Returns the ``delta_rv`` ndarray, or ``None`` on failure.
    """
    from wr_bias_simulation import (
        simulate_with_params, SimulationConfig, BinaryParameterConfig,
    )

    # Fingerprint: marginal params + lk-array shape
    _lk = np.asarray(result.get('likelihood', []))
    _fp = (
        round(float(marg_params['f_bin']), 6),
        round(float(marg_params['pi']), 6),
        round(float(marg_params['sigma']), 6),
        round(float(marg_params['logP_max']), 6),
        tuple(_lk.shape),
    )
    _fp_key = cache_key + '_fp'
    if (st.session_state.get(_fp_key) == _fp
            and cache_key in st.session_state):
        return st.session_state[cache_key]

    cad_lib = result.get('cadence_library')
    cad_wt = result.get('cadence_weights')
    if cad_lib is None:
        return None

    _bcfg_dict = result.get('bin_cfg', {}) or {}
    bcfg = (BinaryParameterConfig(**_bcfg_dict)
            if _bcfg_dict else BinaryParameterConfig())
    bcfg.logP_max = float(marg_params['logP_max'])

    sigma_meas = float(result.get('sigma_meas', 1.622))
    sim_cfg = SimulationConfig(
        n_stars=10000,
        sigma_single=float(marg_params['sigma']),
        sigma_measure=sigma_meas,
        cadence_library=cad_lib,
        cadence_weights=cad_wt,
    )
    rng = np.random.default_rng(43)  # different seed from gap_sim's 42
    sim = simulate_with_params(
        float(marg_params['f_bin']), float(marg_params['pi']),
        sim_cfg, bcfg, rng,
    )
    drv = np.asarray(sim.get('delta_rv', []), dtype=float)
    drv = drv[np.isfinite(drv)]
    if drv.size == 0:
        return None
    st.session_state[cache_key] = drv
    st.session_state[_fp_key] = _fp
    return drv


def _render_panel_b_cdf(
    p: str,
    drv_mock: np.ndarray,
    is_bin_mock: np.ndarray,
    drv_sim: np.ndarray | None,
    thresh_dRV: float,
    drv_span: float,
    have_sim: bool,
    grid_params: dict | None = None,
    marg_params: dict | None = None,
    result: dict | None = None,
    settings: dict | None = None,
) -> None:
    """Panel B: ΔRV CDF overlay + residual with bootstrap 16/84 band.

    Round-5 (2026-04-28) extension: when ``marg_params`` differs from
    ``grid_params`` we also bootstrap a second simulated population (drawn
    via ``simulate_with_params`` at the marginal-best tuple) and overlay
    its 16/84 band + median in PURPLE so the user can compare both
    best-fit definitions on the same axes.  ``drv_sim`` is the existing
    grid-argmax simulation (already cached in session_state as
    ``f'{p}_gap_sim'``).
    """
    from plotly.subplots import make_subplots
    from bc.helpers import _hex_to_rgba

    st.markdown('#### Panel B — ΔRV CDF overlay + residual')
    _grid_fbin_lbl = (f"{grid_params['f_bin']:.3f}"
                      if grid_params else '—')
    _marg_fbin_lbl = (f"{marg_params['f_bin']:.3f}"
                      if marg_params else '—')
    st.caption(
        'Residuals reveal where the likelihood is blind — a tight CDF fit '
        'can still leave (f_bin, π) badly constrained; see Panel A for '
        'orthogonal info.  '
        f'**Grid f_bin = {_grid_fbin_lbl}, '
        f'Marginal f_bin = {_marg_fbin_lbl}**'
    )

    n_mock = int(drv_mock.size)
    t_grid = np.linspace(0.0, drv_span, 400)

    # Mock empirical CDF on t_grid
    def _cdf_of(sample: np.ndarray, grid: np.ndarray) -> np.ndarray:
        s = np.asarray(sample, dtype=float)
        s = s[np.isfinite(s)]
        if s.size == 0:
            return np.zeros_like(grid)
        ss = np.sort(s)
        counts = np.searchsorted(ss, grid, side='right')
        return counts.astype(float) / s.size

    cdf_mock = _cdf_of(drv_mock, t_grid)

    # Bootstrap sim CDF (GRID best-fit): resample N_mock from drv_sim, 200×
    cdf_sim_med = None
    cdf_sim_lo = None
    cdf_sim_hi = None
    if drv_sim is not None and drv_sim.size > 0:
        n_boot = 200
        rng = np.random.default_rng(2026)
        boot_cdfs = np.empty((n_boot, t_grid.size), dtype=float)
        for b in range(n_boot):
            pick = rng.choice(drv_sim, size=n_mock, replace=True)
            boot_cdfs[b] = _cdf_of(pick, t_grid)
        cdf_sim_med = np.median(boot_cdfs, axis=0)
        cdf_sim_lo = np.percentile(boot_cdfs, 16, axis=0)
        cdf_sim_hi = np.percentile(boot_cdfs, 84, axis=0)

    # Round-5 (2026-04-28): bootstrap a SECOND CDF at the marginal-best
    # parameter tuple.  Only triggered when (i) we have grid+marg dicts,
    # (ii) the result dict is available (cadence_library + bin_cfg live
    # there), and (iii) marg ≠ grid (avoid duplicate work / curves when
    # the marginal mode coincides with the joint argmax — common when
    # the posterior is unimodal).
    cdf_marg_med = None
    cdf_marg_lo = None
    cdf_marg_hi = None
    drv_marg = None
    if (grid_params is not None and marg_params is not None
            and result is not None):
        # Trigger if any param differs by more than a numerical tolerance.
        _params_differ = any(
            (not np.isclose(grid_params[k], marg_params[k], atol=1e-6))
            for k in ('f_bin', 'pi', 'sigma', 'logP_max')
        )
        if _params_differ:
            try:
                drv_marg = _simulate_marginal_drv(
                    marg_params, result, settings,
                    cache_key=f'{p}_panel_b_marg_drv',
                )
            except Exception as _exc:
                drv_marg = None
                st.caption(
                    f':orange[Marginal-best simulation failed: {_exc}]'
                )
            if drv_marg is not None and drv_marg.size > 0:
                n_boot = 200
                rng_m = np.random.default_rng(2027)
                boot_cdfs_m = np.empty((n_boot, t_grid.size), dtype=float)
                for b in range(n_boot):
                    pick_m = rng_m.choice(drv_marg, size=n_mock,
                                          replace=True)
                    boot_cdfs_m[b] = _cdf_of(pick_m, t_grid)
                cdf_marg_med = np.median(boot_cdfs_m, axis=0)
                cdf_marg_lo = np.percentile(boot_cdfs_m, 16, axis=0)
                cdf_marg_hi = np.percentile(boot_cdfs_m, 84, axis=0)

    # Per-star dots at (drv, cdf_mock(drv))
    sorted_idx = np.argsort(drv_mock)
    drv_sorted = drv_mock[sorted_idx]
    cdf_vals = (np.arange(n_mock) + 1) / n_mock
    is_bin_sorted = is_bin_mock[sorted_idx]

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        row_heights=[0.70, 0.30], vertical_spacing=0.06,
    )

    # ── Upper (row 1) ──
    # Mock observation CDF (BLACK) — drawn FIRST so the colored bands sit
    # underneath but the median lines + dots overlay it on top later.
    fig.add_trace(go.Scatter(
        x=drv_sorted, y=cdf_vals, mode='lines',
        line=dict(color=_CDF_OBS_COLOR, width=2.5, shape='hv'),
        name='Mock observation',
        hovertemplate='ΔRV=%{x:.1f} km/s<br>CDF=%{y:.3f}<extra></extra>',
    ), row=1, col=1)

    # 16/84 GRID best-fit band + median (RED dashed)
    if cdf_sim_med is not None:
        band_x = np.concatenate([t_grid, t_grid[::-1]])
        band_y = np.concatenate([cdf_sim_hi, cdf_sim_lo[::-1]])
        fig.add_trace(go.Scatter(
            x=band_x, y=band_y, fill='toself',
            fillcolor=_hex_to_rgba(_CDF_FIT_COLOR, 0.18),
            line=dict(width=0, shape='hv'), mode='lines',
            name='Grid best-fit 16/84', hoverinfo='skip',
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=t_grid, y=cdf_sim_med, mode='lines',
            line=dict(color=_CDF_FIT_COLOR, width=2.5,
                      dash='dash', shape='hv'),
            name='Grid best-fit (median)',
            hovertemplate=('t=%{x:.1f} km/s<br>CDF=%{y:.3f}'
                           '<extra>Grid</extra>'),
        ), row=1, col=1)

    # 16/84 MARGINAL best-fit band + median (PURPLE dashed)
    if cdf_marg_med is not None:
        band_x_m = np.concatenate([t_grid, t_grid[::-1]])
        band_y_m = np.concatenate([cdf_marg_hi, cdf_marg_lo[::-1]])
        fig.add_trace(go.Scatter(
            x=band_x_m, y=band_y_m, fill='toself',
            fillcolor=_hex_to_rgba(_CDF_FIT_MARG_COLOR, 0.18),
            line=dict(width=0, shape='hv'), mode='lines',
            name='Marginal best-fit 16/84', hoverinfo='skip',
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=t_grid, y=cdf_marg_med, mode='lines',
            line=dict(color=_CDF_FIT_MARG_COLOR, width=2.5,
                      dash='dash', shape='hv'),
            name='Marginal best-fit (median)',
            hovertemplate=('t=%{x:.1f} km/s<br>CDF=%{y:.3f}'
                           '<extra>Marginal</extra>'),
        ), row=1, col=1)

    # Per-star single / binary dots
    single_sorted = ~is_bin_sorted
    if np.any(single_sorted):
        fig.add_trace(go.Scatter(
            x=drv_sorted[single_sorted],
            y=cdf_vals[single_sorted],
            mode='markers',
            marker=dict(color=_CLR_SINGLE, size=7,
                        line=dict(color='black', width=0.5)),
            name=f'Single ({int(single_sorted.sum())})',
            hovertemplate=('single · ΔRV=%{x:.1f} km/s'
                           '<extra></extra>'),
        ), row=1, col=1)
    if np.any(is_bin_sorted):
        fig.add_trace(go.Scatter(
            x=drv_sorted[is_bin_sorted],
            y=cdf_vals[is_bin_sorted],
            mode='markers',
            marker=dict(color=_CLR_BINARY, size=7,
                        line=dict(color='black', width=0.5)),
            name=f'Binary ({int(is_bin_sorted.sum())})',
            hovertemplate=('binary · ΔRV=%{x:.1f} km/s'
                           '<extra></extra>'),
        ), row=1, col=1)

    fig.add_vline(
        x=thresh_dRV, line_dash='dash',
        line_color='#DAA520', line_width=1.5,
        annotation_text=f'{thresh_dRV:.1f} km/s',
        annotation_position='bottom right',
        annotation_font=dict(size=10, color='#000000',
                             family='Times New Roman, serif'),
        row=1, col=1,
    )

    # ── Lower (row 2): residual (mock − grid, mock − marginal) ──
    cdf_mock_on_grid = cdf_mock
    if cdf_sim_med is not None:
        resid = cdf_mock_on_grid - cdf_sim_med
        fig.add_trace(go.Scatter(
            x=t_grid, y=resid, mode='lines',
            line=dict(color=_CDF_FIT_COLOR, width=1.5,
                      dash='dash', shape='hv'),
            name='mock − grid', showlegend=False,
            hovertemplate=('t=%{x:.1f} km/s<br>ΔCDF=%{y:.3f}'
                           '<extra>Grid resid</extra>'),
        ), row=2, col=1)

        # Grid sim uncertainty band (red, faint)
        half = (cdf_sim_hi - cdf_sim_lo) / 2.0
        band_x = np.concatenate([t_grid, t_grid[::-1]])
        band_y = np.concatenate([+half, (-half)[::-1]])
        fig.add_trace(go.Scatter(
            x=band_x, y=band_y, fill='toself',
            fillcolor=_hex_to_rgba(_CDF_FIT_COLOR, 0.10),
            line=dict(width=0, shape='hv'), mode='lines',
            name='grid 16/84 half-width', showlegend=False,
            hoverinfo='skip',
        ), row=2, col=1)

    if cdf_marg_med is not None:
        resid_m = cdf_mock_on_grid - cdf_marg_med
        fig.add_trace(go.Scatter(
            x=t_grid, y=resid_m, mode='lines',
            line=dict(color=_CDF_FIT_MARG_COLOR, width=1.5,
                      dash='dash', shape='hv'),
            name='mock − marginal', showlegend=False,
            hovertemplate=('t=%{x:.1f} km/s<br>ΔCDF=%{y:.3f}'
                           '<extra>Marg resid</extra>'),
        ), row=2, col=1)

        half_m = (cdf_marg_hi - cdf_marg_lo) / 2.0
        band_x_m = np.concatenate([t_grid, t_grid[::-1]])
        band_y_m = np.concatenate([+half_m, (-half_m)[::-1]])
        fig.add_trace(go.Scatter(
            x=band_x_m, y=band_y_m, fill='toself',
            fillcolor=_hex_to_rgba(_CDF_FIT_MARG_COLOR, 0.10),
            line=dict(width=0, shape='hv'), mode='lines',
            name='marg 16/84 half-width', showlegend=False,
            hoverinfo='skip',
        ), row=2, col=1)
    # Residual zero reference — mid-grey dashed, paper-safe on white
    fig.add_hline(y=0.0, line_dash='dash', line_color='#555555',
                  line_width=1, row=2, col=1)

    # A&A white bg + black serif text (override PLOTLY_THEME dark defaults)
    fig.update_layout(**{
        **PLOTLY_THEME,
        **_AA_OVERRIDES,
        'height': 480,
        'margin': dict(l=60, r=30, t=40, b=55),
        'title': dict(text='',
                      font=dict(size=14, color='#000000',
                                family='Times New Roman, serif')),
        'legend': dict(x=0.60, y=0.35,
                       font=dict(size=10, color='#000000',
                                 family='Times New Roman, serif'),
                       bgcolor='rgba(255,255,255,0.9)',
                       bordercolor='#000000', borderwidth=1),
    })
    fig.update_xaxes(**_AA_OVERRIDES['xaxis'])
    fig.update_yaxes(**_AA_OVERRIDES['yaxis'])
    fig.update_yaxes(title_text='CDF', range=[-0.02, 1.02],
                     row=1, col=1)
    fig.update_yaxes(title_text='ΔCDF', row=2, col=1)
    fig.update_xaxes(title_text='ΔRV threshold t (km/s)',
                     row=2, col=1)

    st.plotly_chart(fig, use_container_width=True,
                    key=f'{p}_val_diag_panel_b')

    if not have_sim:
        st.info('Best-fit simulation not yet available — run the grid first.')


# ─────────────────────────────────────────────────────────────────────────────
# Batch sweep UI (Task #161) — standalone, not delegated
# ─────────────────────────────────────────────────────────────────────────────

def _render_batch_sweep(
    p: str,
    is_dsilva: bool,
    period_model: str,
    cadence_list: list,
    cadence_weights,
    settings: dict,
    sm,
) -> None:
    """Batch sweep: test recovery across a grid of true parameter values."""
    from wr_bias_simulation import BinaryParameterConfig

    st.markdown('#### Batch Sweep Settings')
    st.caption(
        'Test parameter recovery at many true-parameter combinations. '
        'Produces a heatmap showing where the pipeline is reliable.'
    )

    # ── True parameter sweep grid ─────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    n_true_fbin = c1.number_input('True f_bin points', 3, 10, 5, 1,
                                  key=f'{p}_val_batch_nfbin')
    if is_dsilva:
        n_true_pi = c2.number_input('True pi points', 3, 10, 5, 1,
                                    key=f'{p}_val_batch_npi')
    else:
        n_true_pi = 1
        c2.info('pi = 1 for Langer')
    n_true_sigma = c3.number_input('True sigma points', 1, 5, 1, 1,
                                   key=f'{p}_val_batch_nsigma')

    true_fbin_vals = np.linspace(0.1, 0.9, int(n_true_fbin))
    true_pi_vals = np.linspace(-2.0, 2.0, int(n_true_pi)) if is_dsilva else np.array([0.0])
    true_sigma_vals = np.linspace(5.0, 30.0, int(n_true_sigma)) if int(n_true_sigma) > 1 else np.array([15.0])

    n_total = len(true_fbin_vals) * len(true_pi_vals) * len(true_sigma_vals)
    st.info(f'Total test points: **{n_total}** '
            f'({len(true_fbin_vals)} f_bin x {len(true_pi_vals)} pi x {len(true_sigma_vals)} sigma)')

    # ── Recovery grid settings (user-configurable ranges) ─────────────────
    with st.expander('Recovery grid settings', expanded=False):
        st.caption('Configure the recovery search grid ranges.')
        fc1, fc2, fc3 = st.columns(3)
        rec_fb_min = fc1.number_input('f_bin min', 0.0, 1.0, 0.0, 0.01,
                                      key=f'{p}_val_batch_fb_min')
        rec_fb_max = fc2.number_input('f_bin max', 0.0, 1.0, 1.0, 0.01,
                                      key=f'{p}_val_batch_fb_max')
        rec_n_fbin = fc3.number_input('f_bin steps', 5, 100, 15, 5,
                                      key=f'{p}_val_batch_rec_nfbin')
        if is_dsilva:
            pc1, pc2, pc3 = st.columns(3)
            rec_pi_min = pc1.number_input('pi min', -5.0, 5.0, -3.0, 0.1,
                                          key=f'{p}_val_batch_pi_min')
            rec_pi_max = pc2.number_input('pi max', -5.0, 5.0, 3.0, 0.1,
                                          key=f'{p}_val_batch_pi_max')
            rec_n_pi = pc3.number_input('pi steps', 5, 60, 10, 5,
                                        key=f'{p}_val_batch_rec_npi')
        else:
            rec_n_pi = 1
            rec_pi_min = 0.0
            rec_pi_max = 0.0
        rec_n_sets = st.number_input('N_sets per grid point', 100, 50000, 300, 100,
                                     key=f'{p}_val_batch_nsets')

    sc1, sc2 = st.columns(2)
    batch_logPmax = sc1.slider('True logP_max (fixed)', 1.0, 6.0, 4.0, 0.1,
                               key=f'{p}_val_batch_logPmax')
    batch_sigma_meas = sc2.number_input('sigma_meas (km/s)', 0.1, 10.0, 1.622, 0.1,
                                        key=f'{p}_val_batch_sigma_meas')

    # Build recovery grids from user-specified ranges
    rec_fbin_grid = np.linspace(float(rec_fb_min), float(rec_fb_max), int(rec_n_fbin))
    if is_dsilva:
        rec_pi_grid = np.linspace(float(rec_pi_min), float(rec_pi_max), int(rec_n_pi))
    else:
        rec_pi_grid = np.array([0.0])
    rec_sigma_grid = np.array([15.0])  # single sigma for speed in batch

    e_model = 'flat' if is_dsilva else 'zero'
    bin_cfg = BinaryParameterConfig(
        logP_min=0.15,
        logP_max=float(batch_logPmax),
        period_model=period_model,
        e_model=e_model,
        e_max=0.9,
    )

    # ── Run button ────────────────────────────────────────────────────────
    run_btn = st.button('Run Batch Sweep', type='primary',
                        key=f'{p}_val_run_batch')

    batch_job_key = f'{p}_val_batch_job'
    batch_result_key = f'{p}_val_batch_result'

    if run_btn:
        st.session_state.pop(batch_result_key, None)
        progress_dict = {'n_done': 0, 'n_total': n_total,
                         'done': False, 'current_point': '', 'result': None}
        st.session_state[batch_job_key] = progress_dict

        def _batch_worker():
            from bc.validation import run_batch_validation
            try:
                result = run_batch_validation(
                    true_fbin_vals=true_fbin_vals,
                    true_pi_vals=true_pi_vals,
                    true_sigma_vals=true_sigma_vals,
                    true_logPmax=float(batch_logPmax),
                    fbin_grid=rec_fbin_grid,
                    pi_grid=rec_pi_grid,
                    sigma_grid=rec_sigma_grid,
                    cadence_library=cadence_list,
                    cadence_weights=cadence_weights,
                    sigma_meas=float(batch_sigma_meas),
                    bin_cfg=bin_cfg,
                    period_model=period_model,
                    n_sets=int(rec_n_sets),
                    progress_dict=progress_dict,
                )
                progress_dict['result'] = result
            except Exception as exc:
                progress_dict['error'] = str(exc)
            finally:
                progress_dict['done'] = True

        thread = threading.Thread(target=_batch_worker, daemon=True)
        thread.start()
        st.rerun()

    # ── Poll running batch job ────────────────────────────────────────────
    job = st.session_state.get(batch_job_key)
    if job is not None and not job.get('done', False):
        _poll_batch_job(p)
        return

    # If job just finished
    if job is not None and job.get('done', False):
        if 'error' in job:
            st.error(f'Batch sweep failed: {job["error"]}')
            st.session_state.pop(batch_job_key, None)
            return
        if job.get('result') is not None:
            st.session_state[batch_result_key] = job['result']
        st.session_state.pop(batch_job_key, None)

    # ── Display batch results ─────────────────────────────────────────────
    batch = st.session_state.get(batch_result_key)
    if batch is None:
        st.info('Configure sweep parameters and click **Run Batch Sweep**.')
        return

    _display_batch_result(p, batch, is_dsilva)


@st.fragment(run_every=3)
def _poll_batch_job(p: str) -> None:
    """Poll background batch validation job — displays live progress bar."""
    job_key = f'{p}_val_batch_job'
    job = st.session_state.get(job_key)
    if job is None:
        return
    if job.get('done', False):
        st.rerun(scope='app')
    else:
        n_done = job.get('n_done', 0)
        n_tot = job.get('n_total', 1)
        cur = job.get('current_point', '')
        st.progress(n_done / max(n_tot, 1),
                    text=f'Batch sweep: {n_done}/{n_tot} — {cur}')


def _display_batch_result(p: str, batch, is_dsilva: bool) -> None:
    """Display batch sweep results."""
    from bc.validation import batch_to_recovery_heatmap

    st.markdown('##### Recovery Quality Heatmap')

    if is_dsilva:
        st.caption(
            'Mean recovery score per (f_bin, pi) cell, marginalized over sigma. '
            'Green = good recovery, red = poor recovery.'
        )
    else:
        st.caption(
            'Mean recovery score per (f_bin, sigma) cell. '
            'Green = good recovery, red = poor recovery.'
        )

    scores_2d, y_vals, x_vals = batch_to_recovery_heatmap(batch, is_dsilva)

    # Custom heatmap with green-yellow-red color scale
    fig = go.Figure(data=go.Heatmap(
        z=scores_2d,
        x=np.round(x_vals, 3),
        y=np.round(y_vals, 3),
        colorscale=[
            [0.0, '#2ECC71'],    # green = good (low score)
            [0.15, '#82E0AA'],
            [0.30, '#F7DC6F'],   # yellow = fair
            [0.50, '#F0B27A'],
            [1.0, '#E74C3C'],    # red = poor (high score)
        ],
        colorbar=dict(
            title=dict(
                text='Recovery<br>Score',
                font=dict(color='#000000',
                          family='Times New Roman, serif'),
            ),
            tickfont=dict(color='#000000',
                          family='Times New Roman, serif'),
        ),
        zmin=0.0,
        zmax=max(0.5, float(np.nanmax(scores_2d)) if np.any(np.isfinite(scores_2d)) else 0.5),
        hovertemplate=(
            'x: %{x:.3f}<br>y: %{y:.3f}<br>'
            'Score: %{z:.4f}<extra></extra>'
        ),
    ))

    x_title = 'True pi' if is_dsilva else 'True sigma_single (km/s)'
    fig.update_layout(**{**PLOTLY_THEME,
        'title': dict(text='Recovery Quality Across Parameter Space'),
        'xaxis': {**PLOTLY_THEME.get('xaxis', {}), 'title': x_title},
        'yaxis': {**PLOTLY_THEME.get('yaxis', {}), 'title': 'True f_bin'},
        'height': 520,
    })
    # A&A journal theme (white bg, black serif text)
    fig.update_layout(**_AA_OVERRIDES)
    fig.update_xaxes(**_AA_OVERRIDES['xaxis'])
    fig.update_yaxes(**_AA_OVERRIDES['yaxis'])

    st.plotly_chart(fig, use_container_width=True, key=f'{p}_val_batch_heatmap')

    # ── Summary statistics ────────────────────────────────────────────────
    st.markdown('##### Summary Statistics')

    scores_flat = np.array([pt.recovery_score for pt in batch.points])
    finite = scores_flat[np.isfinite(scores_flat)]

    if len(finite) > 0:
        mc1, mc2, mc3, mc4 = st.columns(4)
        mc1.metric('Mean Score', f'{np.mean(finite):.4f}')
        mc2.metric('Median Score', f'{np.median(finite):.4f}')
        mc3.metric('Best (min)', f'{np.min(finite):.4f}')
        mc4.metric('Worst (max)', f'{np.max(finite):.4f}')

        good_frac = np.mean(finite < 0.10)
        fair_frac = np.mean((finite >= 0.10) & (finite < 0.25))
        poor_frac = np.mean(finite >= 0.25)

        qc1, qc2, qc3 = st.columns(3)
        qc1.metric('Good (< 0.10)', f'{good_frac:.0%}')
        qc2.metric('Fair (0.10-0.25)', f'{fair_frac:.0%}')
        qc3.metric('Poor (> 0.25)', f'{poor_frac:.0%}')

    # ── Detailed results table ────────────────────────────────────────────
    with st.expander('Detailed Results Table', expanded=False):
        rows = []
        for pt in batch.points:
            row = {
                'True f_bin': pt.true_fbin,
                'True pi': pt.true_pi,
                'True sigma': pt.true_sigma,
                'Rec f_bin': pt.rec_fbin,
                'Rec pi': pt.rec_pi,
                'Rec sigma': pt.rec_sigma,
                'Score': pt.recovery_score,
            }
            rows.append(row)
        if rows:
            df = pd.DataFrame(rows)

            def _color_score(val):
                if not isinstance(val, (int, float)) or np.isnan(val):
                    return ''
                if val < 0.10:
                    return 'background-color: rgba(46, 204, 113, 0.3)'
                elif val < 0.25:
                    return 'background-color: rgba(247, 220, 111, 0.3)'
                else:
                    return 'background-color: rgba(231, 76, 60, 0.3)'

            styled = df.style.map(_color_score, subset=['Score'])
            st.dataframe(styled, use_container_width=True, hide_index=True)

    # ── Score distribution histogram ──────────────────────────────────────
    st.markdown('##### Score Distribution')
    if len(finite) > 0:
        fig_hist = go.Figure(data=go.Histogram(
            x=finite,
            nbinsx=20,
            marker_color='#4A90D9',
            opacity=0.8,
        ))
        fig_hist.update_layout(**{**PLOTLY_THEME,
            'title': dict(text='Distribution of Recovery Scores'),
            'xaxis': {**PLOTLY_THEME.get('xaxis', {}),
                      'title': 'Recovery Score'},
            'yaxis': {**PLOTLY_THEME.get('yaxis', {}),
                      'title': 'Count'},
            'height': 350,
        })
        # A&A journal theme (white bg, black serif text)
        fig_hist.update_layout(**_AA_OVERRIDES)
        fig_hist.update_xaxes(**_AA_OVERRIDES['xaxis'])
        fig_hist.update_yaxes(**_AA_OVERRIDES['yaxis'])
        st.plotly_chart(fig_hist, use_container_width=True,
                        key=f'{p}_val_batch_hist')
