"""bc.bin_sensitivity — Tab renderer for the Bin-Sensitivity sub-tab.

Layout (top-to-bottom):
  1. Controls (source, editable scheme list, run)
  2. Progress poller (shown only while running)
  3. Results:
     - Plot #6 (methods figure: bin-edge geometry)
     - Summary table
     - Scheme radio
     - Sub-tabs: Sensitivity | CDF Overlay | Posterior Shapes | Bin Diagnostics
     - Export button

Scope (Round 3): manual schemes only. The user adds named rows with
comma-separated edge strings; each valid row becomes one
``(name, edges)`` pair handed to ``_run_all_schemes_bg``. Parametric
scheme-builders in ``bin_schemes.py`` are still importable for programmatic
use, just not surfaced in the UI.

Hard rules followed:
- No emojis.
- No controls in ``st.expander``.
- No min/max constraints on ``st.number_input``.
- ``logL`` shown as-is (negative; higher = better).
- All plots wrapped in ``@st.fragment``.
- Progress polling via ``@st.fragment(run_every=1)``.
"""
from __future__ import annotations

import datetime
import json
import os
import sys
import threading
import uuid
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bc.helpers import _RESULT_DIR
from bc.file_ops import _list_saved_results
from bc.bin_schemes import _custom as _parse_custom_edges
from bc.bin_sensitivity_scorer import (
    SchemeResult, load_npz_context, _run_all_schemes_bg, _make_bin_cfg,
)
from bc.bin_sensitivity_plots import (
    _plot_hdi_vs_nbins, _plot_best_fit_scatter, _plot_cdf_faceted,
    _plot_marginal_posteriors, _plot_bin_occupancy, _plot_bin_edge_map,
)
from bc.validation import generate_mock_observations
from bc.bin_sensitivity_storage import (
    build_bs_filename, partial_path_for, save_bin_sensitivity_run,
    promote_partial,
    list_bs_results, list_bs_partials,
    load_bin_sensitivity_run, delete_bs_result,
)

# Default edge string for the locked dsilva_default row — matches
# ``bin_schemes._dsilva_default(threshold=45.5)``.
_DSILVA_DEFAULT_EDGES_STR = '0,45.5,250,650,inf'


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _scheme_row(r: SchemeResult) -> dict:
    """One table row per SchemeResult.

    When the scheme carries a ``ground_truth`` dict (mock mode), two extra
    signed-error columns are inserted right after ``f_bin*`` / ``pi*``:
    ``Δf_bin = best_fbin - true_fbin`` and ``Δπ = best_pi - true_pi``
    (briefing §Change 4 summary table).
    """
    lo_fb, hi_fb = r.hdi68_fbin
    lo_pi, hi_pi = r.hdi68_pi
    gt = getattr(r, 'ground_truth', None)
    row: dict = {
        'scheme':         r.scheme,
        'n_bins':         int(r.n_bins),
        'n_eff_bins':     int(r.n_eff_bins),
        'f_bin*':         round(float(r.best_fbin), 3),
    }
    if gt is not None:
        try:
            row['Δf_bin'] = round(float(r.best_fbin) - float(gt.get('f_bin')), 3)
        except (TypeError, ValueError):
            row['Δf_bin'] = float('nan')
    row['HDI68(f_bin)'] = f'[{lo_fb:.3f}, {hi_fb:.3f}]'
    row['pi*'] = round(float(r.best_pi), 3)
    if gt is not None:
        try:
            row['Δπ'] = round(float(r.best_pi) - float(gt.get('pi')), 3)
        except (TypeError, ValueError):
            row['Δπ'] = float('nan')
    row['HDI68(pi)'] = f'[{lo_pi:.3f}, {hi_pi:.3f}]'
    row['logL_max'] = round(float(r.logL_max), 2)
    row['AIC'] = round(float(r.aic), 2)
    row['KS_at_best'] = round(float(r.ks_D), 3)
    row['n_empty_bins'] = int(np.sum(r.n_obs_per_bin == 0))
    row['status'] = r.status
    row['status_reasons'] = ','.join(r.status_reasons) if r.status_reasons else ''
    return row


# ─────────────────────────────────────────────────────────────────────────────
# Scheme-list session-state helpers
# ─────────────────────────────────────────────────────────────────────────────

def _schemes_list_key(p: str) -> str:
    return f'{p}_bsn_schemes_list'


# Persistence path inside ``settings/user_settings.json``. Custom user-added
# bin schemes survive app restarts / reruns / page navigation by round-tripping
# through this key. Only the persistent fields (``name``/``edges``/``locked``)
# are written; ``rid`` is a UI-only uuid regenerated on load.
_BSN_SETTINGS_KEY = ['bin_sensitivity', 'schemes']

# Persistence path for the 5 mock-truth number_inputs (f_bin/π/σ/logPmax/seed).
# Survives app restarts so Guy doesn't retype them every reload.
_BSN_MOCK_KEY = ['bin_sensitivity', 'mock_params']


def _load_persisted_schemes() -> list[dict] | None:
    """Return the saved schemes list from user_settings.json, or None if absent.

    Each returned dict is a **copy** with a freshly minted ``rid`` so the UI
    widgets get unique keys. Returns None when the settings key is missing
    or empty, so the caller can fall back to the dsilva_default bootstrap.
    """
    try:
        from shared import get_settings_manager
        settings = get_settings_manager().load()
        saved = settings
        for k in _BSN_SETTINGS_KEY:
            if not isinstance(saved, dict) or k not in saved:
                return None
            saved = saved[k]
        if not isinstance(saved, list) or not saved:
            return None
        out = []
        for row in saved:
            if not isinstance(row, dict):
                continue
            name = str(row.get('name', '')).strip()
            edges = str(row.get('edges', ''))
            locked = bool(row.get('locked', False))
            if not name:
                continue
            out.append({
                'name': name, 'edges': edges, 'locked': locked,
                'rid': uuid.uuid4().hex[:8],
            })
        return out or None
    except Exception:
        return None


def _persist_schemes(rows: list[dict]) -> None:
    """Write current rows (minus ``rid``) to user_settings.json.

    Called on every ``_render_schemes_list`` rerun so the schemes list
    survives reruns, page navigation, and app restarts. Persistence is
    best-effort — on any failure we surface the error via ``st.toast``
    (no silent swallowing) but never break the UI.

    The first call per Streamlit session prints a debug line to the
    server console so we can verify the persist hook is firing. Remove
    the debug after Guy confirms it works.
    """
    # First-call debug print (Streamlit server console).
    _debug_key = '_bsn_persist_schemes_debugged'
    if _debug_key not in st.session_state:
        st.session_state[_debug_key] = True
        print(f'[bsn] _persist_schemes first call, {len(rows)} rows, '
              f'writing to {_BSN_SETTINGS_KEY}', flush=True)
    try:
        from shared import get_settings_manager
        payload = [
            {'name': str(r.get('name', '')).strip() or f'scheme_{i + 1}',
             'edges': str(r.get('edges', '')),
             'locked': bool(r.get('locked', False))}
            for i, r in enumerate(rows)
        ]
        get_settings_manager().save(_BSN_SETTINGS_KEY, value=payload)
    except Exception as exc:
        # Surface the error instead of hiding it. UI still renders.
        try:
            st.toast(f'schemes persist failed: {exc}', icon='⚠️')
        except Exception:
            # Last resort — if even toast fails, log to console.
            print(f'[bsn] _persist_schemes failed: {exc}', flush=True)


def _load_persisted_mock_params() -> dict | None:
    """Return {'f_bin', 'pi', 'sigma', 'logPmax', 'seed'} from settings, or None.

    Mirrors :func:`_load_persisted_schemes` — reads ``settings.bin_sensitivity
    .mock_params`` and returns a defensively-typed dict so the widgets can
    use it as ``value=`` defaults. On any parse failure returns ``None`` so
    the caller falls back to the hardcoded defaults.
    """
    try:
        from shared import get_settings_manager
        s = get_settings_manager().load()
        for k in _BSN_MOCK_KEY:
            if not isinstance(s, dict) or k not in s:
                return None
            s = s[k]
        if not isinstance(s, dict):
            return None
        out = {
            'f_bin':   float(s.get('f_bin',   0.46)),
            'pi':      float(s.get('pi',      0.0)),
            'sigma':   float(s.get('sigma',   15.0)),
            'logPmax': float(s.get('logPmax', 5.0)),
            'seed':    int(s.get('seed',      42)),
        }
        return out
    except Exception:
        return None


def _persist_mock_params(f_bin: float, pi: float, sigma: float,
                        logPmax: float, seed: int) -> None:
    """Write the 5 mock-truth values to ``user_settings.json``.

    Best-effort — if the save fails we surface a toast so the error is
    visible, rather than silently swallowing (previous behaviour hid
    genuine disk / schema bugs).
    """
    try:
        from shared import get_settings_manager
        get_settings_manager().save(_BSN_MOCK_KEY, value={
            'f_bin': float(f_bin), 'pi': float(pi),
            'sigma': float(sigma), 'logPmax': float(logPmax),
            'seed': int(seed),
        })
    except Exception as exc:
        try:
            st.toast(f'mock_params persist failed: {exc}', icon='⚠️')
        except Exception:
            print(f'[bsn] _persist_mock_params failed: {exc}', flush=True)


def _init_schemes_list(p: str) -> list[dict]:
    """Initialise (or re-hydrate) the editable scheme-row list.

    Row 0 is always the locked ``dsilva_default`` reference. Each row is a
    dict with keys ``name``, ``edges``, ``locked`` and ``rid`` (a stable uuid
    used as a widget-key suffix so Streamlit doesn't alias widgets when rows
    are inserted/deleted).

    On first call of a session we prefer the list persisted under
    ``settings['bin_sensitivity']['schemes']`` (see :func:`_load_persisted_schemes`),
    so user-added rows survive reruns / page navigation / app restarts. If the
    persisted list is missing the locked ``dsilva_default`` (e.g. a corrupt
    hand-edit), we prepend it defensively.
    """
    key = _schemes_list_key(p)
    if key not in st.session_state:
        saved = _load_persisted_schemes()
        if saved is not None:
            has_default = any(
                r.get('name') == 'dsilva_default' and r.get('locked')
                for r in saved
            )
            if not has_default:
                saved.insert(0, {
                    'name': 'dsilva_default',
                    'edges': _DSILVA_DEFAULT_EDGES_STR,
                    'locked': True,
                    'rid': uuid.uuid4().hex[:8],
                })
            st.session_state[key] = saved
        else:
            st.session_state[key] = [{
                'name': 'dsilva_default',
                'edges': _DSILVA_DEFAULT_EDGES_STR,
                'locked': True,
                'rid': uuid.uuid4().hex[:8],
            }]
    return st.session_state[key]


_INF_TOKENS = {'inf', 'infinity', '+inf', 'np.inf'}


def _parse_row_edges(edges_str: str) -> Optional[np.ndarray]:
    """Parse a row's edge string; return None when the row is invalid.

    Strict validation (stricter than :func:`bin_schemes._custom`, which
    silently skips non-numeric tokens):
      * non-empty string
      * every comma-separated token parses to a float or is an ``inf`` literal
      * after parsing, at least 2 distinct edges with 0.0 first and +inf tail
        (enforced by the downstream parser, but re-checked here as a guard)

    Rejecting stray tokens matches acceptance criterion #3: e.g. ``'0,abc,inf'``
    must flag as ``:red[invalid edges]`` instead of quietly dropping ``abc``.
    """
    s = str(edges_str or '').strip()
    if not s:
        return None
    parts = [p.strip().lower() for p in s.split(',') if p.strip()]
    if not parts:
        return None
    # Every token must be either a parseable float OR an inf literal.
    for p in parts:
        if p in _INF_TOKENS:
            continue
        try:
            float(p)
        except ValueError:
            return None
    try:
        arr = _parse_custom_edges(edges_str)
    except Exception:
        return None
    if arr.size < 2:
        return None
    if not np.isfinite(arr[0]) or arr[0] != 0.0:
        return None
    if not np.isinf(arr[-1]):
        return None
    return arr


# ─────────────────────────────────────────────────────────────────────────────
# Main tab renderer
# ─────────────────────────────────────────────────────────────────────────────

def _render_bin_sensitivity_tab(p: str, settings: dict, sm) -> None:
    """Render the Bin Sensitivity sub-tab inside the Bias Correction page."""

    # ── Row 0: observation source (Real vs Mock) ─────────────────────────
    # Round-4: 2-option radio. In "Mock observations" mode the same .npz is
    # still required (grid parameters, cadence library, bin_cfg) but the
    # observed ΔRV array is overridden by a synthetic draw from
    # :func:`generate_mock_observations` at known truth params.
    st.markdown('#### Observation source')
    obs_mode = st.radio(
        'Observation source',
        options=['Real observations', 'Mock observations (known truth)'],
        index=0,
        horizontal=True,
        key=f'{p}_bsn_obs_mode',
        label_visibility='collapsed',
    )
    is_mock = (obs_mode == 'Mock observations (known truth)')

    # ── Row 1: source selector (.npz file) ───────────────────────────────
    # TODO(bin-sensitivity): wire a full fresh-simulation path from within
    # this tab. For now, users run fresh grids in the Cadence (Dsilva) tab
    # and return here with "Reuse existing .npz".
    st.markdown('#### Source')
    col_src_a, col_src_b = st.columns([0.35, 0.65])
    col_src_a.markdown('**Simulation source**')
    col_src_a.caption(':grey[Reuse existing .npz]')

    npz_path: Optional[str] = None
    files = _list_saved_results('cadence_dsilva')
    if not files:
        col_src_b.info(
            'No cadence_dsilva_*.npz files found in results/. '
            'Run a grid in the Cadence (Dsilva) tab first.')
    else:
        labels = [f[0] for f in files]
        paths = [f[1] for f in files]
        sel_idx = col_src_b.selectbox(
            'Result file', options=list(range(len(labels))),
            format_func=lambda i: labels[i],
            key=f'{p}_bsn_npz_idx',
            help=paths[0] if paths else '',
        )
        npz_path = paths[int(sel_idx)]
    st.caption(
        ':grey[To run a fresh simulation, use the Cadence (Dsilva) tab and '
        'then return here.]')

    # ── Row 1a: always-visible saved-runs panel ──────────────────────────
    # Mirrors cadence.py's "Load saved result" pattern — shows load/save UI
    # unconditionally so the user can recover prior runs after a browser
    # refresh (which wipes session_state and therefore ``job``).
    with st.expander('Saved runs', expanded=True):
        _render_bs_saved_runs_panel(p)

    # ── Row 1b: mock-mode true parameters + seed ─────────────────────────
    # Defaults mirror render_validation.py:93-105 (briefing §Change 4).
    # `true_logPmax=5.0` locked by briefing (render_validation uses 4.0 for its
    # recovery UI; the bin-sensitivity default is 5.0 per the approved plan).
    mock_params: Optional[dict] = None
    if is_mock:
        st.markdown('#### Mock true parameters')
        # Hydrate from user_settings.json so edits survive reruns / restarts.
        # Falls back to the hardcoded defaults when no saved values exist.
        _saved = _load_persisted_mock_params() or {}
        c1, c2, c3, c4, c5 = st.columns(5)
        _tfb = c1.number_input(
            'True f_bin',
            value=float(_saved.get('f_bin', 0.46)), step=0.01,
            key=f'{p}_bsn_mock_true_fbin',
        )
        _tpi = c2.number_input(
            'True π',
            value=float(_saved.get('pi', 0.0)), step=0.1,
            key=f'{p}_bsn_mock_true_pi',
        )
        _tsig = c3.number_input(
            'True σ_single (km/s)',
            value=float(_saved.get('sigma', 15.0)), step=0.5,
            key=f'{p}_bsn_mock_true_sigma',
        )
        _tlpm = c4.number_input(
            'True log P_max',
            value=float(_saved.get('logPmax', 5.0)), step=0.1,
            key=f'{p}_bsn_mock_true_logPmax',
        )
        _seed = c5.number_input(
            'Mock RNG seed',
            value=int(_saved.get('seed', 42)), step=1,
            key=f'{p}_bsn_mock_seed',
        )
        # Signature-gated persist (mirrors the scheme-list pattern at ~line 620):
        # only hit disk when the committed widget values actually change, so we
        # don't hammer user_settings.json on every rerun (plot toggle, etc).
        _mp_sig = (float(_tfb), float(_tpi), float(_tsig), float(_tlpm), int(_seed))
        _mp_sig_key = f'{p}_bsn_mock_last_sig'
        if st.session_state.get(_mp_sig_key) != _mp_sig:
            _persist_mock_params(_tfb, _tpi, _tsig, _tlpm, _seed)
            st.session_state[_mp_sig_key] = _mp_sig
        mock_params = dict(
            f_bin=float(_tfb), pi=float(_tpi),
            sigma=float(_tsig), logPmax=float(_tlpm),
            seed=int(_seed),
        )
        st.caption(
            ':grey[The synthetic ΔRV sample is regenerated every time you '
            'click "Run comparison" using these values — no separate '
            '"Regenerate" button.]')

    # ── Row 2: editable scheme list ──────────────────────────────────────
    st.markdown('#### Bin schemes to compare')
    st.caption(
        'Each row defines one manually-chosen bin scheme. Edges are '
        'comma-separated km/s; the parser prepends 0 and appends +inf '
        'automatically. The locked "dsilva_default" row is always present '
        'as the reference.')
    schemes_pairs = _render_schemes_list(p)

    # ── Row 3: run button ────────────────────────────────────────────────
    _, col_run = st.columns([0.75, 0.25])
    with col_run:
        run_clicked = st.button(
            'Run comparison', type='primary',
            key=f'{p}_bsn_run', use_container_width=True,
            disabled=(npz_path is None or len(schemes_pairs) == 0),
        )

    # ── Kick off the job ─────────────────────────────────────────────────
    job_key = f'{p}_bsn_job'
    if run_clicked and npz_path is not None and schemes_pairs:
        job = {
            'status': 'running', 'progress_pct': 0.0, 'progress_scheme': '',
            'progress_cell_done': 0, 'progress_cell_total': 0,
            'cancel': False, 'errors': [],
            # Session-B persistence state — reset on every fresh run so the
            # auto-save hook below fires exactly once per completed run and
            # the status badge starts as "unsaved partial".
            'autosaved_partial': None,
            'saved_permanent': None,
            'is_mock_mode': bool(is_mock),
            'mock_params': dict(mock_params) if (is_mock and mock_params is not None) else None,
        }
        st.session_state[job_key] = job

        params = dict(
            npz_path=npz_path,
            schemes=list(schemes_pairs),
            n_proc=max(1, (os.cpu_count() or 2) - 1),
        )
        # Record the source path on the job for Session-B auto-save.
        job['source_npz'] = str(npz_path)

        # Mock mode: synthesize the ΔRV sample once in the main thread and
        # pass it to the worker via `obs_override`. The .npz still supplies
        # the grid, cadence library and bin_cfg (briefing §Change 4).
        if is_mock and mock_params is not None:
            try:
                _ctx_pre = load_npz_context(npz_path)
                # Legacy .npz fallback: when cadence_library wasn't persisted
                # (pre-E048), pull it from the live loader — mirrors the same
                # fallback in :func:`rescore_scheme`.
                _cad_lib = _ctx_pre['cadence_library']
                _cad_wts = _ctx_pre['cadence_weights']
                if _cad_lib is None:
                    from shared import (
                        cached_load_cadence, settings_hash, get_settings_manager,
                    )
                    _sh = settings_hash(get_settings_manager().load())
                    _cad_lib, _cw_default = cached_load_cadence(_sh)
                    if _cad_wts is None:
                        _cad_wts = _cw_default
                _bin_cfg = _make_bin_cfg(
                    _ctx_pre['bin_cfg_dict'],
                    _ctx_pre['period_model'],
                    logP_max_override=mock_params['logPmax'],
                )
                _obs_mock = generate_mock_observations(
                    true_fbin=mock_params['f_bin'],
                    true_pi=mock_params['pi'],
                    true_sigma=mock_params['sigma'],
                    true_logPmax=mock_params['logPmax'],
                    cadence_library=_cad_lib,
                    cadence_weights=_cad_wts,
                    sigma_meas=float(_ctx_pre['sigma_meas']),
                    bin_cfg=_bin_cfg,
                    period_model=str(_ctx_pre['period_model']),
                    seed=int(mock_params['seed']),
                    n_sets=1,
                )
                params['obs_override'] = np.asarray(_obs_mock, dtype=float)
                params['ground_truth'] = dict(
                    f_bin=float(mock_params['f_bin']),
                    pi=float(mock_params['pi']),
                    sigma=float(mock_params['sigma']),
                    logPmax=float(mock_params['logPmax']),
                    seed=int(mock_params['seed']),
                )
                # Stash the synthetic sample + source on the job so the
                # auto-save hook (Session-B) can persist a mock_detail
                # block without re-generating the draw.
                job['mock_delta_rv_sample'] = params['obs_override']
                job['source_npz'] = str(npz_path)
            except Exception as exc:
                st.error(f'Could not generate mock observations: {exc}')
                job['status'] = 'error'
                job['error_trace'] = str(exc)
                return

        t = threading.Thread(
            target=_run_all_schemes_bg, args=(job, params),
            daemon=True, name=f'{p}_bsn_worker',
        )
        t.start()

    # ── Progress polling ─────────────────────────────────────────────────
    _render_progress_fragment(p, job_key)

    # ── Results presentation ─────────────────────────────────────────────
    job = st.session_state.get(job_key)
    results: Optional[dict[str, SchemeResult]] = None
    if job is not None and job.get('status') == 'done':
        results = job.get('results') or {}
        if job.get('ctx', {}).get('is_legacy'):
            st.info(
                'Legacy result — this .npz was saved before the E048 fix, so '
                'bin_cfg / cadence_library were not persisted. We re-simulate '
                'with defaults derived from the settings JSON. Re-run the grid '
                'for a bit-identical match.')
        errs = job.get('errors') or []
        if errs:
            with st.container():
                st.warning('Some schemes failed:')
                for e in errs:
                    st.caption(f'- {e}')

    if results:
        # Session-B: auto-save every completed run as .partial_<ts>.npz so the
        # user can always upgrade it via the "Save result" button in the
        # results block. Guarded by `autosaved_partial` so we don't re-write
        # on every subsequent rerun (e.g. scheme-radio toggle).
        _maybe_autosave_partial(p, job, results, npz_path)
        _render_results(p, job, results, npz_path)


# ─────────────────────────────────────────────────────────────────────────────
# Editable scheme-row list
# ─────────────────────────────────────────────────────────────────────────────

def _render_schemes_list(p: str) -> list[tuple[str, np.ndarray]]:
    """Render the editable list of manual bin schemes.

    Returns the list of ``(name, edges_array)`` pairs whose rows parsed to
    a valid edge array; invalid rows show a ':red[invalid edges]' caption
    and are excluded from the run.
    """
    rows = _init_schemes_list(p)
    valid: list[tuple[str, np.ndarray]] = []
    deleted_index: Optional[int] = None

    for i, row in enumerate(rows):
        rid = row.setdefault('rid', uuid.uuid4().hex[:8])
        locked = bool(row.get('locked', False))
        c_name, c_edges, c_del = st.columns([0.30, 0.55, 0.15])

        # Name column
        if locked:
            c_name.text_input(
                'Name', value=row['name'],
                key=f'{p}_bsn_row_name_{rid}',
                disabled=True, label_visibility='collapsed',
            )
            name_val = row['name']
        else:
            name_val = c_name.text_input(
                'Name', value=row['name'],
                key=f'{p}_bsn_row_name_{rid}',
                label_visibility='collapsed',
                placeholder=f'scheme_{i + 1}',
            )
            row['name'] = str(name_val).strip() or f'scheme_{i + 1}'

        # Edges column
        if locked:
            c_edges.text_input(
                'Edges', value=row['edges'],
                key=f'{p}_bsn_row_edges_{rid}',
                disabled=True, label_visibility='collapsed',
            )
            edges_val = row['edges']
        else:
            edges_val = c_edges.text_input(
                'Edges', value=row['edges'],
                key=f'{p}_bsn_row_edges_{rid}',
                label_visibility='collapsed',
                placeholder='0,45.5,250,650,inf',
            )
            row['edges'] = str(edges_val)

        # Delete column
        if locked:
            c_del.markdown(':grey[—]')
        else:
            if c_del.button('Delete', key=f'{p}_bsn_row_del_{rid}',
                            use_container_width=True):
                deleted_index = i

        # Validate + show caption if broken
        parsed = _parse_row_edges(edges_val)
        if parsed is None:
            c_edges.caption(':red[invalid edges]')
        else:
            valid.append((str(row['name']), parsed))

    # Apply pending deletion (after the loop so widgets keep their keys stable)
    if deleted_index is not None:
        rows.pop(deleted_index)
        st.session_state[_schemes_list_key(p)] = rows
        _persist_schemes(rows)
        st.rerun()

    # "+ Add scheme row" button
    if st.button('+ Add scheme row', key=f'{p}_bsn_add_row'):
        rows.append({
            'name': f'scheme_{len(rows) + 1}',
            'edges': '',
            'locked': False,
            'rid': uuid.uuid4().hex[:8],
        })
        st.session_state[_schemes_list_key(p)] = rows
        _persist_schemes(rows)
        st.rerun()

    # Persist on every render — bulletproof. SettingsManager writes ~1 KB
    # JSON to disk; this is cheap and eliminates the signature-cache edge
    # cases (e.g. the first rerun after an add / delete where the button
    # handler already wrote, but the widget values for the new row have
    # not yet committed to the signature). _render_schemes_list only runs
    # while the user is on the Bin Sensitivity tab, so the write rate is
    # bounded and errors (if any) now surface via st.toast.
    _persist_schemes(rows)

    return valid


# ─────────────────────────────────────────────────────────────────────────────
# Progress polling — dedicated fragment
# ─────────────────────────────────────────────────────────────────────────────

def _render_progress_fragment(p: str, job_key: str) -> None:
    """Poll the job dict once per second; no-ops when no job is active.

    When the background worker flips ``job['status']`` to ``'done'`` or
    ``'error'``, the fragment fires a one-shot ``st.rerun(scope='app')`` so
    the main-script top-level code picks up ``job['results']`` and renders
    it (without this, the results dict was set but never read until the
    next manual interaction). The ``_main_rerun_done`` flag guards against
    a rerun storm on subsequent polls.
    """
    @st.fragment(run_every=1)
    def _poll():
        job = st.session_state.get(job_key)
        if job is None:
            return
        status = job.get('status')
        if status == 'running':
            pct = float(job.get('progress_pct', 0.0))
            _scheme = str(job.get('progress_scheme') or '')
            _done = int(job.get('progress_cell_done', 0))
            _total = int(job.get('progress_cell_total', 0))
            if _total > 0:
                text = f'Scheme: {_scheme}  —  cell {_done}/{_total}'
            else:
                text = f'Scheme: {_scheme}'
            st.progress(min(max(pct, 0.0), 1.0), text=text)
        elif status in ('done', 'error'):
            # One-shot: trigger a full-app rerun so _render_results fires.
            # After the first rerun, the main script picks up results and
            # the fragment goes idle.
            if not job.get('_main_rerun_done'):
                job['_main_rerun_done'] = True
                st.rerun(scope='app')
            if status == 'error':
                trace = job.get('error_trace', '')
                st.error('Background worker failed.')
                if trace:
                    st.code(trace, language='python')
    _poll()


# ─────────────────────────────────────────────────────────────────────────────
# Session-B: auto-save + saved-runs panel helpers
#
# The two tables below (partials + permanent) mirror the Cadence tab exactly
# (``app/bc/file_ops.py`` — ``_scan_partial_metadata`` / ``_render_partial_table``
# / ``_scan_result_metadata``). Bin-sensitivity diverges from cadence only in
# the NPZ key names and the fact that each run is atomic (no incremental cell
# fill), so the ``% Done`` column is always 100 %.
# ─────────────────────────────────────────────────────────────────────────────

def _maybe_autosave_partial(
    p: str,
    job: dict,
    results: dict[str, SchemeResult],
    npz_path: Optional[str],
) -> None:
    """Silently save every completed run to ``.partial_<ts>.npz``.

    Runs at most once per job (guarded by ``job['autosaved_partial']``).
    In mock mode we also persist the synthetic ΔRV sample + true params
    to a sibling ``mock_observations/<stem>/mock_stars.npz`` so that a
    later Load call can rehydrate the full ground-truth context.

    On any failure we swallow the exception and stash the string in
    ``job['autosave_error']`` so :func:`_render_results` can surface a
    small warning in the status badge row; we do NOT raise (autosave
    is best-effort — the user can still manually Export).
    """
    if job is None:
        return
    if job.get('autosaved_partial'):
        return
    try:
        is_mock = bool(job.get('is_mock_mode'))
        mock_detail: Optional[dict] = None
        if is_mock:
            mp = job.get('mock_params') or {}
            sample = job.get('mock_delta_rv_sample')
            sample_arr = (np.asarray(sample, dtype=float)
                          if sample is not None else np.array([], dtype=float))
            mock_detail = {
                'delta_rv_sample': sample_arr,
                'seed': int(mp.get('seed', 0)),
                'n_stars': int(sample_arr.size),
                'true_f_bin': float(mp.get('f_bin', 0.0)),
                'true_pi': float(mp.get('pi', 0.0)),
                'true_sigma': float(mp.get('sigma', 0.0)),
                'true_logPmax': float(mp.get('logPmax', 0.0)),
                'error_model': 'fixed',
                'error_params': (),
                'rvs_per_star': [],
                'mjds_per_star': [],
                'errors_per_star': [],
            }

        schemes_block = [
            {'name': r.scheme,
             'edges': np.asarray(r.edges, dtype=float).tolist(),
             'family': str(r.family)}
            for r in results.values()
        ]
        settings = {
            'schemes': schemes_block,
            'source_npz': str(npz_path) if npz_path else '',
            'is_mock_mode': is_mock,
            'mock_params': job.get('mock_params'),
            'timestamp_saved': datetime.datetime.now().isoformat(),
        }

        filename = build_bs_filename(mock_mode=is_mock)
        save_bin_sensitivity_run(
            list(results.values()),
            settings,
            mock_detail,
            str(npz_path) if npz_path else '',
            filename,
            is_partial=True,
        )
        job['autosaved_partial'] = str(partial_path_for(filename))
        # Drop BOTH metadata caches so the saved-runs panel sees the new file.
        try:
            _scan_bs_partial_metadata.clear()
            _scan_bs_result_metadata.clear()
        except Exception:
            pass
    except Exception as exc:  # best-effort: never break the results render
        job['autosave_error'] = str(exc)


# ─────────────────────────────────────────────────────────────────────────────
# Metadata scanners — one per table (partial + permanent)
# ─────────────────────────────────────────────────────────────────────────────

def _bs_meta_row_from_path(path: str) -> Optional[dict]:
    """Build one metadata row for a single bin-sensitivity NPZ on disk.

    Returns ``None`` if the file is unreadable / not a bin-sensitivity NPZ.
    The row matches the columns documented in the briefing §3; the scanner
    functions below just iterate ``list_bs_*`` and call this helper.
    """
    try:
        d = np.load(path, allow_pickle=True)
    except Exception:
        return None
    try:
        try:
            scheme_names = list(d['scheme_names'])
        except KeyError:
            d.close()
            return None

        n_sch = len(scheme_names)

        def _arr_get(key: str, default=None):
            return d[key] if key in d.files else default

        best_fbin = _arr_get('best_fbin')
        best_pi = _arr_get('best_pi')
        ks_D = _arr_get('ks_D')

        # index 0 is dsilva_default (guaranteed first by the scheme-list init).
        if best_fbin is not None and len(best_fbin) > 0:
            best_fb_s = f'{float(best_fbin[0]):.3f}'
        else:
            best_fb_s = '—'
        if best_pi is not None and len(best_pi) > 0:
            best_pi_s = f'{float(best_pi[0]):.3f}'
        else:
            best_pi_s = '—'
        if ks_D is not None and len(ks_D) > 0:
            best_ks_s = f'{float(ks_D[0]):.3f}'
        else:
            best_ks_s = '—'

        ts_raw = str(d['timestamp']) if 'timestamp' in d.files else ''
        ts = ts_raw.replace('T', ' ')[:19] if ts_raw else '—'

        mock_flag = bool(d['mock_mode']) if 'mock_mode' in d.files else False
        mode_str = 'MOCK' if mock_flag else 'REAL'

        src_raw = str(d['source_npz']) if 'source_npz' in d.files else ''
        src = os.path.basename(src_raw) if src_raw else '—'

        # Parse settings once; ground-truth lives under mock_params.
        sett = {}
        if 'settings' in d.files:
            try:
                sett = json.loads(str(d['settings']))
            except Exception:
                sett = {}

        mp = (sett.get('mock_params') or {}) if mock_flag else {}
        if mock_flag and isinstance(mp, dict):
            def _fmt(key, fmt):
                v = mp.get(key)
                if v is None:
                    return '—'
                try:
                    return format(float(v), fmt)
                except (TypeError, ValueError):
                    return '—'

            true_fb = _fmt('f_bin', '.3f')
            true_pi = _fmt('pi', '.3f')
            true_sigma = _fmt('sigma', '.2f')
            try:
                seed = str(int(mp.get('seed'))) if mp.get('seed') is not None else '—'
            except (TypeError, ValueError):
                seed = '—'
        else:
            true_fb = true_pi = true_sigma = seed = '—'

        d.close()
    except Exception:
        try:
            d.close()
        except Exception:
            pass
        return None

    return {
        '% Done': '100%',
        'Schemes': n_sch,
        'Date': ts,
        'Mode': mode_str,
        'Best f_bin': best_fb_s,
        'Best π': best_pi_s,
        'Best KS_D': best_ks_s,
        'Source .npz': src,
        'True f_bin': true_fb,
        'True π': true_pi,
        'True σ': true_sigma,
        'Seed': seed,
        'File': os.path.basename(str(path)),
        '_path': str(path),
    }


@st.cache_data(ttl=30)
def _scan_bs_partial_metadata() -> pd.DataFrame:
    """Scan ``bin_sensitivity_results/.partial_*.npz`` — returns a DataFrame.

    Mirrors :func:`bc.file_ops._scan_partial_metadata` but for bin-sensitivity.
    Cached for 30 s; invalidate with ``.clear()`` after any save/delete/promote.
    """
    rows: list[dict] = []
    for _label, path in list_bs_partials():
        try:
            row = _bs_meta_row_from_path(path)
            if row is not None:
                rows.append(row)
        except Exception:
            continue
    return pd.DataFrame(rows) if rows else pd.DataFrame()


@st.cache_data(ttl=30)
def _scan_bs_result_metadata() -> pd.DataFrame:
    """Scan ``bin_sensitivity_results/*.npz`` (excluding partials).

    Mirrors :func:`bc.file_ops._scan_result_metadata`. Cached 30 s.
    """
    rows: list[dict] = []
    for _label, path in list_bs_results():
        try:
            row = _bs_meta_row_from_path(path)
            if row is not None:
                rows.append(row)
        except Exception:
            continue
    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
# Render helpers — mirror _render_partial_table / the permanent-table block
# in cadence.py
# ─────────────────────────────────────────────────────────────────────────────

def _hydrate_loaded_bs_run(p: str, path: str, status_slot, toast: str) -> None:
    """Load a bin-sensitivity NPZ and stash it in ``{p}_bsn_job``.

    Shared between the partial-table Load/Resume branches and the permanent
    table's Load branch. On failure the caller sees the error via
    ``status_slot.error(...)`` — no exception is raised.
    """
    try:
        loaded_results, loaded_settings, loaded_mock = (
            load_bin_sensitivity_run(path))
    except Exception as exc:
        status_slot.error(f'Failed to load bin-sensitivity run: {exc}')
        return

    mp = None
    mock_sample = None
    if loaded_mock is not None:
        meta = loaded_mock.get('meta') or {}
        mp = {
            'f_bin': float(meta.get('true_f_bin', 0.0)),
            'pi': float(meta.get('true_pi', 0.0)),
            'sigma': float(meta.get('true_sigma', 0.0)),
            'logPmax': float(meta.get('true_logPmax', 0.0)),
            'seed': int(meta.get('seed', 0)),
        }
        mock_sample = np.asarray(
            meta.get('delta_rv_sample', []), dtype=float)

    is_partial_load = os.path.basename(str(path)).startswith('.partial_')
    synthetic_job = {
        'status': 'done',
        'results': {r.scheme: r for r in loaded_results},
        'ctx': {},
        'errors': [],
        'is_mock_mode': bool(loaded_mock is not None),
        'mock_params': mp,
        'mock_delta_rv_sample': mock_sample,
        'source_npz': str(loaded_settings.get('source_npz', '')),
        'saved_permanent': None if is_partial_load else str(path),
        'autosaved_partial': str(path) if is_partial_load else None,
        '_loaded_from_disk': True,
        '_main_rerun_done': True,
    }
    st.session_state[f'{p}_bsn_job'] = synthetic_job
    status_slot.success(toast)


def _render_bs_results_table(p: str, job: dict, status_slot) -> None:
    """Permanent saved-runs table — inline (not in an expander).

    Mirrors the permanent-saves block in ``app/bc/cadence.py:1021-1068`` but
    uses the action-dispatch pattern from ``_render_partial_table`` so button
    clicks are reliable. Load/Delete only (no Resume on permanent saves).
    """
    meta = _scan_bs_result_metadata()
    if meta.empty:
        return

    _action_key = f'{p}_bsn_result_action'
    _pending = st.session_state.pop(_action_key, None)
    if _pending is not None:
        _act = _pending.get('action')
        _path = _pending.get('path', '')
        if _act == 'load' and os.path.exists(_path):
            _hydrate_loaded_bs_run(
                p, _path, status_slot,
                toast=f'Loaded: {os.path.basename(_path)}')
            st.rerun()
        elif _act == 'delete':
            try:
                delete_bs_result(_path)
                _scan_bs_partial_metadata.clear()
                _scan_bs_result_metadata.clear()
                st.toast(f'Deleted: {os.path.basename(_path)}')
            except Exception as exc:
                st.error(f'Delete failed: {exc}')
            st.rerun()
        # Re-read after possible deletion
        meta = _scan_bs_result_metadata()
        if meta.empty:
            return

    st.markdown(f'#### Saved bin-sensitivity runs ({len(meta)})')
    display = meta.drop(columns=['_path'], errors='ignore')
    sel = st.dataframe(
        display,
        on_select='rerun',
        selection_mode='single-row',
        key=f'{p}_bsn_result_table',
        hide_index=True,
        use_container_width=True,
    )
    sel_rows = sel.selection.rows if sel.selection else []
    if sel_rows:
        idx = int(sel_rows[0])
        path_sel = str(meta.iloc[idx]['_path'])
        c1, c2 = st.columns(2)
        if c1.button('\U0001f4cb Load', key=f'{p}_bsn_load_result',
                     use_container_width=True):
            st.session_state[_action_key] = {
                'action': 'load', 'path': path_sel}
            st.rerun()
        if c2.button('\U0001f5d1\ufe0f Delete', key=f'{p}_bsn_del_result',
                     use_container_width=True):
            st.session_state[_action_key] = {
                'action': 'delete', 'path': path_sel}
            st.rerun()


def _render_bs_partial_table(p: str, status_slot) -> None:
    """Partial-runs table inside an expander — Load / Delete / Resume.

    Mirrors :func:`bc.file_ops._render_partial_table`. For bin-sensitivity
    Resume is equivalent to Load (runs are atomic — there are no cells to
    fill in), so the Resume branch routes to the same loader with a
    friendlier toast.
    """
    meta = _scan_bs_partial_metadata()
    if meta.empty:
        return

    _action_key = f'{p}_bsn_partial_action'
    _pending = st.session_state.pop(_action_key, None)
    if _pending is not None:
        _act = _pending.get('action')
        _act_path = _pending.get('path', '')
        if _act == 'load' and os.path.exists(_act_path):
            _hydrate_loaded_bs_run(
                p, _act_path, status_slot,
                toast=f'Loaded partial: {os.path.basename(_act_path)}')
        elif _act == 'delete':
            try:
                delete_bs_result(_act_path)
                _scan_bs_partial_metadata.clear()
                _scan_bs_result_metadata.clear()
                st.toast('Deleted partial')
            except Exception as exc:
                st.error(f'Failed to delete: {exc}')
        elif _act == 'resume' and os.path.exists(_act_path):
            _hydrate_loaded_bs_run(
                p, _act_path, status_slot,
                toast=(
                    'Resume == Load here (bin-sensitivity runs are atomic). '
                    'Loaded the partial.'))
            status_slot.info(
                'Resume == Load here (bin-sensitivity runs are atomic). '
                'Loaded the partial.')
        # Re-read metadata after possible deletion
        meta = _scan_bs_partial_metadata()
        if meta.empty:
            return

    with st.expander(
            f'\U0001f504 Partial runs ({len(meta)} found)', expanded=False):
        display = meta.drop(columns=['_path'], errors='ignore')
        sel = st.dataframe(
            display,
            on_select='rerun',
            selection_mode='single-row',
            key=f'{p}_bsn_partial_table',
            hide_index=True,
            use_container_width=True,
        )
        sel_rows = sel.selection.rows if sel.selection else []
        if sel_rows:
            idx = int(sel_rows[0])
            path_sel = str(meta.iloc[idx]['_path'])
            c1, c2, c3 = st.columns(3)
            if c1.button('\U0001f4cb Load',
                         key=f'{p}_bsn_load_partial',
                         use_container_width=True):
                st.session_state[_action_key] = {
                    'action': 'load', 'path': path_sel}
                st.rerun()
            if c2.button('\U0001f5d1\ufe0f Delete',
                         key=f'{p}_bsn_del_partial',
                         use_container_width=True):
                st.session_state[_action_key] = {
                    'action': 'delete', 'path': path_sel}
                st.rerun()
            if c3.button(
                    '\u25b6\ufe0f Resume',
                    key=f'{p}_bsn_resume_partial',
                    use_container_width=True,
                    help=('For bin-sensitivity, Resume is equivalent to '
                          'Load — runs are atomic (no cells to fill in).')):
                st.session_state[_action_key] = {
                    'action': 'resume', 'path': path_sel}
                st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Always-visible saved-runs panel (load / save / list)
# ─────────────────────────────────────────────────────────────────────────────

def _render_bs_saved_runs_panel(p: str) -> None:
    """Always-visible saved-runs panel for the Bin Sensitivity tab.

    Renders in 4 blocks, independent of whether a job is currently active
    (previously these lived inside ``_render_results``, which only ran when
    a job had status='done' — so after a browser refresh wiped session_state
    the user could never load an old run or promote the auto-saved partial):

      1. Status badge row — shows "Unsaved partial" / "Saved" / "Auto-save
         failed" pulled from the current job, or "No active run" if no job.
      2. Save result button — disabled unless an unsaved partial exists.
      3. Permanent saved-runs table — always visible, from list_bs_results().
      4. Partial runs expander — always visible, from list_bs_partials().

    The Load action on either table hydrates ``st.session_state[f'{p}_bsn_job']``
    with a synthetic ``status='done'`` job via :func:`_hydrate_loaded_bs_run`
    so the existing _render_results path takes over on the next rerun.
    """
    job = st.session_state.get(f'{p}_bsn_job')
    saved_perm = job.get('saved_permanent') if job else None
    partial = job.get('autosaved_partial') if job else None
    autosave_err = job.get('autosave_error') if job else None

    _status_slot = st.container()
    c_status, c_save = st.columns([0.78, 0.22])
    with c_status:
        if saved_perm:
            st.caption(f':green[✓ Saved to `{os.path.basename(saved_perm)}`]')
        elif partial:
            st.caption(
                f':orange[Unsaved partial — auto-saved to '
                f'`{os.path.basename(partial)}`. Click **Save result** to '
                'keep permanently.]')
        elif autosave_err:
            st.caption(f':red[Auto-save failed: {autosave_err}]')
        elif job is None:
            st.caption(':grey[No active run — load a saved run below or '
                       'click **Run comparison** to start a new one.]')
    with c_save:
        can_save = bool(partial) and not saved_perm
        save_help = (None if can_save
                     else ('No active run to save.' if job is None
                           else 'No unsaved partial — run a new comparison '
                                'or load a partial below.'))
        if st.button(
                'Save result', type='primary',
                key=f'{p}_bsn_save_btn',
                use_container_width=True,
                disabled=not can_save,
                help=save_help):
            try:
                final = promote_partial(partial)
                job['saved_permanent'] = str(final)
                job['autosaved_partial'] = None
                _scan_bs_partial_metadata.clear()
                _scan_bs_result_metadata.clear()
                st.toast(f'Saved: {final.name}')
                st.rerun()
            except Exception as exc:
                st.error(f'Save failed: {exc}')

    # Permanent saved runs — inline, above partials (mirrors cadence layout).
    _render_bs_results_table(p, job, _status_slot)

    # Partial runs — expander, below.
    _render_bs_partial_table(p, _status_slot)


# ─────────────────────────────────────────────────────────────────────────────
# Results block
# ─────────────────────────────────────────────────────────────────────────────

def _render_results(
    p: str,
    job: dict,
    results: dict[str, SchemeResult],
    npz_path: Optional[str],
) -> None:
    """Render the plot-6 methods figure, summary table, scheme radio, sub-tabs.

    Note: the status badge + Save button + saved-runs tables live in
    :func:`_render_bs_saved_runs_panel`, which is rendered at the top of
    the tab (independent of job state) so the user can always load / save
    even after a browser refresh wipes session_state.
    """
    # Ordered schemes: dsilva_default first, then alpha
    def _row_key(name: str) -> tuple:
        return (0 if name == 'dsilva_default' else 1, name)
    ordered_names = sorted(results.keys(), key=_row_key)

    ctx = load_npz_context(npz_path) if npz_path else None
    obs = ctx['obs_delta_rv'] if ctx else results[ordered_names[0]].cdf_x
    fbin_grid = ctx['fbin_grid'] if ctx else np.linspace(0, 1, results[ordered_names[0]].marginal_fbin.size)
    pi_grid = ctx['pi_grid'] if ctx else np.linspace(-3, 3, results[ordered_names[0]].marginal_pi.size)

    # Plot 6 at top — the methods figure
    @st.fragment
    def _fig6():
        fig = _plot_bin_edge_map(results, obs, threshold=45.5)
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            'Each row shows where one scheme places its bin edges. The rug '
            'above marks the observed ΔRV values. Edges beyond "max observed" '
            'contribute no likelihood information.')
    _fig6()

    # Summary table
    st.markdown('#### Summary')
    rows = [_scheme_row(results[n]) for n in ordered_names]
    df = pd.DataFrame(rows)
    # Apply row opacity for FAIL rows via Styler (lighter background)

    def _style_status(val: str) -> str:
        if val == 'FAIL':
            return 'color: #E25A53; font-weight: 600;'
        if val == 'WARN':
            return 'color: #DAA520; font-weight: 500;'
        if val == 'OK':
            return 'color: #1B9E77;'
        return ''

    def _style_row(row):
        base = ['color: #AAAAAA;' if row['status'] == 'FAIL' else '' for _ in row]
        return base

    try:
        styler = (df.style
                    .map(_style_status, subset=['status'])
                    .apply(_style_row, axis=1))
        st.dataframe(styler, use_container_width=True, hide_index=True)
    except Exception:
        # Styler can be flaky in some Streamlit versions; fall back to raw df.
        st.dataframe(df, use_container_width=True, hide_index=True)

    with st.expander("📖 Column definitions", expanded=False):
        st.markdown("""
| Column | Meaning |
|---|---|
| **scheme** | Binning scheme name (e.g. dsilva_default, default, default X 2) |
| **n_bins** | Total number of bins in the scheme |
| **n_eff_bins** | Bins with ≥1 observation AND ≥1 simulated count — the only bins that actually contribute to logL |
| **f_bin\\*** | Best-fit binary fraction (posterior mode from the (f_bin, π) grid) |
| **Δf_bin** | f_bin\\* − injected truth (mock mode only); measures recovery bias — positive = scheme over-recovers binaries |
| **HDI68(f_bin)** | 68% highest-density interval for f_bin (≈ ±1σ for a unimodal posterior) |
| **pi\\*** | Best-fit period-distribution power-law index (log-period ∝ π) |
| **Δπ** | pi\\* − injected truth (mock mode only) |
| **HDI68(pi)** | 68% HDI for π |
| **logL_max** | Maximum log-likelihood at (f_bin\\*, π\\*). Shown as-is (higher = better). **NOT comparable across schemes** — the Poisson log-likelihood's scale depends on the histogram. |
| **AIC** | 2k − 2·logL_max (k=2 free parameters). **Also NOT comparable across schemes here** — since k is fixed, ΔAIC = −2·ΔlogL and inherits logL's binning-dependent normalization. See next expander for details. |
| **KS_at_best** | Kolmogorov–Smirnov D-statistic between observed and simulated ΔRV CDFs at (f_bin\\*, π\\*). Lower = better. **Binning-independent** (operates on raw samples) — this IS comparable across schemes. |
| **n_empty_bins** | Bins with zero observed or zero simulated counts (excluded from logL) |
| **status** | Automated check pass/warn/fail (OK / WARN / FAIL) |
| **status_reasons** | Which check fired — P1–P5 codes (see memory/likelihood_bin_sensitivity.md §3) |
""")

    with st.expander("🧪 Which scores are comparable across binnings?", expanded=False):
        st.markdown("""
**Comparable across binnings:**

- **KS D-statistic** — computed on the *raw unbinned* ΔRV samples (observed vs simulated). D is the maximum vertical distance between the two empirical CDFs. Because it operates on raw samples, D is **binning-independent**. Lower = better.
  - Do **not** convert to a p-value: p tests whether a single fit is adequate, not which of two fits is better.
- **Consistency of (f_bin\\*, π\\*) and HDI overlap across schemes** — the primary robustness diagnostic. If schemes agree within their 68 % HDIs, the answer is binning-robust. If they don't, binning choice is driving the result.
- **Recovery bias Δf_bin, Δπ (mock mode only)** — the truth is known, so each scheme's bias against the *same* truth is directly comparable.

**NOT comparable across binnings:**

- **logL_max** — the Poisson log-likelihood's absolute scale depends on the histogram (more bins → more Poisson terms, each with finer counts). Use within a single scheme to rank (f_bin, π) pairs, but **not** to rank schemes.
- **AIC = 2k − 2·logL_max** — since k = 2 is fixed across every scheme in this tab, ΔAIC = −2·ΔlogL and AIC inherits logL's binning-dependent normalization. **AIC is not a valid cross-scheme comparator here.** (AIC is only legitimate for comparing models with *different* numbers of free parameters on the *same* data representation.)
- **BIC** = k·log(N) − 2·logL — same problem for the same reason.
- **Reduced χ²** — dof = n_bins − 2, so χ²/dof is also binning-dependent.

**Practical implication:** for ranking schemes, use **KS_at_best** (lower = better). For robustness, look at the spread of (f_bin\\*, π\\*) and HDI widths across schemes in the **Sensitivity** subtab — if schemes agree within uncertainty, the binary-fraction result is robust to the binning choice.
""")

    st.caption(
        'logL shown as-is (higher = better) but CANNOT be compared across '
        'schemes — the Poisson scale depends on the histogram. AIC inherits '
        'the same problem (k=2 is fixed). Use **KS_at_best** (lower = better) '
        'and the (f_bin\\*, π\\*) consistency shown in the Sensitivity subtab '
        'for cross-scheme comparison. See expander above. See '
        'memory/likelihood_bin_sensitivity.md §3.1.')

    # Scheme radio for inspection
    selected_scheme = st.radio(
        'Inspect scheme in plots',
        options=ordered_names,
        horizontal=True,
        key=f'{p}_bsn_selected_scheme',
    )

    # Sub-tabs for plots
    sub_tabs = st.tabs(['Sensitivity', 'CDF Overlay', 'Posterior Shapes', 'Bin Diagnostics'])

    with sub_tabs[0]:
        @st.fragment
        def _fig_sens():
            col1 = st.container()
            col2 = st.container()
            with col1:
                st.plotly_chart(_plot_hdi_vs_nbins(results), use_container_width=True)
                st.caption('HDI68 width per scheme vs number of bins. '
                           'Reference (dsilva_default) drawn as a dashed horizontal line.')
            with col2:
                st.plotly_chart(
                    _plot_best_fit_scatter(results, reference_scheme='dsilva_default'),
                    use_container_width=True)
                st.caption(
                    'Best-fit (π*, f_bin*) for each binning scheme. Contours '
                    'show the 2D posterior density of the **dsilva_default** '
                    'scheme (68%, 95%, and 99% HDIs) as a reference. Star '
                    'marks the injected truth (mock-mode only). Disagreement '
                    'between scheme markers indicates binning-driven variance '
                    'in the best-fit parameters.')
        _fig_sens()

    with sub_tabs[1]:
        @st.fragment
        def _fig_cdf():
            st.plotly_chart(_plot_cdf_faceted(results, obs), use_container_width=True)
            st.caption('Observed ΔRV CDF (step, light) overlaid on simulated '
                       'median CDF (red dashed) with 16-84% envelope. Vertical '
                       'dotted lines show the scheme\u2019s bin edges.')
        _fig_cdf()

    with sub_tabs[2]:
        @st.fragment
        def _fig_post():
            st.plotly_chart(
                _plot_marginal_posteriors(results, fbin_grid, pi_grid),
                use_container_width=True)
            # Round-4: caption text locked by briefing §Change 2.
            st.caption(
                '*1-D marginal posteriors over f_bin (top) and π (bottom), '
                'one curve per bin scheme. Each curve is the posterior density '
                'marginalised over the other parameter, normalised to unit '
                'area. The gold dashed line marks the Dsilva-default best-fit '
                'cell. If curves from different schemes peak near the same '
                'value, the bin choice is not biasing the recovered binary '
                'fraction; if they peak at different locations the posterior '
                'is bin-sensitive. Multi-modal curves (two separate peaks in '
                'one scheme) usually indicate an ε-floor artifact — a '
                'near-empty bin dominated by the 1/N_sim floor. See '
                '`memory/likelihood_bin_sensitivity.md §4` for pitfall '
                'details.*')
        _fig_post()

    with sub_tabs[3]:
        @st.fragment
        def _fig_diag():
            st.plotly_chart(_plot_bin_occupancy(results), use_container_width=True)
            # Round-4: caption text locked by briefing §Change 3.
            st.caption(
                '*Grey = observed per-bin counts; red = simulated counts at '
                'the best-fit cell, rescaled so their total equals the '
                'observed sample size for visual comparability. A '
                'well-fitting model has obs and sim bars matching within each '
                'bin — which is an indicator of fit quality, not of '
                'bin-choice methodology. A separate question is whether the '
                'obs heights should be roughly equal **across** bins '
                '(quantile/equal-count binning). Quantile binning maximises '
                'statistical power per bin and avoids ε-floor artifacts, but '
                'its edges are data-driven, which mildly reduces '
                'interpretability. It is a legitimate choice, not '
                'cherry-picking; the recommended practice is to compare a '
                'physically-anchored scheme (the Dsilva default) against a '
                'quantile scheme and report the spread as a systematic '
                'uncertainty. To try a quantile scheme, add a row with edges '
                'at the 20/40/60/80 percentiles of your observed ΔRV '
                'distribution.*')
        _fig_diag()

    # Export button
    _render_export(p, results, selected_scheme)


# ─────────────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────────────

def _render_export(
    p: str,
    results: dict[str, SchemeResult],
    selected_scheme: str,
) -> None:
    """Export .csv + .json into results/bin_sensitivity_{timestamp}.*."""
    col_exp, _ = st.columns([0.25, 0.75])
    with col_exp:
        if st.button('Export results', key=f'{p}_bsn_export'):
            ts = datetime.datetime.now().strftime('%y%m%d-%H%M')
            os.makedirs(_RESULT_DIR, exist_ok=True)
            csv_path = os.path.join(_RESULT_DIR, f'bin_sensitivity_{ts}.csv')
            json_path = os.path.join(_RESULT_DIR, f'bin_sensitivity_{ts}.json')

            rows = [_scheme_row(r) for r in results.values()]
            pd.DataFrame(rows).to_csv(csv_path, index=False)

            # JSON: include bin edges + CDFs
            payload = {
                'timestamp': ts,
                'selected_scheme': selected_scheme,
                'schemes': {
                    name: {
                        'family': r.family,
                        'edges': [
                            ('Infinity' if np.isinf(x) else float(x))
                            for x in r.edges
                        ],
                        'n_bins': int(r.n_bins),
                        'n_eff_bins': int(r.n_eff_bins),
                        'best_fbin': float(r.best_fbin),
                        'best_pi': float(r.best_pi),
                        'hdi68_fbin': [float(r.hdi68_fbin[0]), float(r.hdi68_fbin[1])],
                        'hdi68_pi': [float(r.hdi68_pi[0]), float(r.hdi68_pi[1])],
                        'logL_max': float(r.logL_max),
                        'aic': float(r.aic),
                        'ks_D': float(r.ks_D),
                        'ks_p': float(r.ks_p),
                        'n_obs_per_bin': r.n_obs_per_bin.tolist(),
                        'n_sim_per_bin': r.n_sim_per_bin.tolist(),
                        'status': r.status,
                        'status_reasons': list(r.status_reasons),
                    }
                    for name, r in results.items()
                },
            }
            with open(json_path, 'w') as f:
                json.dump(payload, f, indent=2)
            st.success(f'Exported to {csv_path} and {json_path}')
