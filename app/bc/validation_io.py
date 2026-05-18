"""bc.validation_io — Persistence layer for validation (mock) runs.

Mirrors ``app/bc/file_ops.py`` but writes to ``<repo_root>/mock_results/``
instead of ``results/``. Every Single-Point Recovery run produces:

  mock_results/validation_{model}_*.npz
  mock_results/mock_observations/<stem>/mock_stars.npz

The top-level .npz payload matches what ``_run_cadence_bg`` normally saves
to ``results/`` plus a small set of validation-specific fields
(``is_validation``, ``true_fbin``, ``true_pi``, ``true_sigma``,
``true_logPmax``, ``seed``, ``mock_delta_rv``, ``mock_stars_subdir``).

The sibling ``mock_stars.npz`` stores a pickled dict keyed by integer
star index (0..N-1), where each value is a small dict holding
``rvs`` / ``times`` / ``errs`` / ``is_binary``.

See `.claude/plans/mock_results_persistence.md` for the full spec.
"""
from __future__ import annotations

import datetime as _dt
import glob as _glob
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_MOCK_DIR = os.path.join(_ROOT, 'mock_results')
_MOCK_OBS_DIR = os.path.join(_MOCK_DIR, 'mock_observations')

_VALID_MODELS = ('dsilva', 'langer')


# ── Filename helpers ──────────────────────────────────────────────────────

def _truth_suffix(truth: dict) -> str:
    """Encode truth params as a compact suffix for filenames."""
    fb = float(truth.get('true_fbin', 0.0))
    pi = float(truth.get('true_pi', 0.0))
    sig = float(truth.get('true_sigma', 0.0))
    logP = float(truth.get('true_logPmax', 0.0))
    seed = int(truth.get('seed', 0))
    return (f'fbT{fb:.2f}_piT{pi:.2f}_sigT{sig:.1f}'
            f'_logPT{logP:.2f}_seed{seed}')


def _grid_suffix(grid_ranges: dict) -> str:
    """Encode recovery grid ranges as a compact suffix."""
    def _rng(key: str, label: str, fmt: str = '{:.1f}') -> str:
        lo = grid_ranges.get(f'{key}_min')
        hi = grid_ranges.get(f'{key}_max')
        n = grid_ranges.get(f'{key}_steps')
        if lo is None or hi is None or n is None:
            return ''
        if int(n) <= 1:
            return f'_{label}{fmt.format(float(lo))}'
        return (f'_{label}' + fmt.format(float(lo)) + '-'
                + fmt.format(float(hi)) + f'x{int(n)}')

    parts = []
    parts.append(_rng('fb', 'fb', '{:.1f}'))
    parts.append(_rng('pi', 'pi', '{:.1f}'))
    if 'n_sets' in grid_ranges and grid_ranges['n_sets'] is not None:
        parts.append(f"_N{int(grid_ranges['n_sets'])}")
    parts.append(_rng('sig', 'sig', '{:.1f}'))
    parts.append(_rng('logPmax', 'logP', '{:.2f}'))
    return ''.join(parts)


def build_validation_filename(
    model: str, truth: dict, grid_ranges: dict, partial: bool = False,
) -> str:
    """Build a descriptive validation .npz filename.

    Format:
      validation_{model}[_partial]_{truth_suffix}{grid_suffix}_{YYMMDD-HHMM}.npz
    """
    if model not in _VALID_MODELS:
        raise ValueError(f'model must be one of {_VALID_MODELS}, got {model!r}')
    ts = _dt.datetime.now().strftime('%d%m%y-%H%M')
    partial_tag = '_partial' if partial else ''
    truth_part = _truth_suffix(truth)
    grid_part = _grid_suffix(grid_ranges)
    return f'validation_{model}{partial_tag}_{truth_part}{grid_part}_{ts}.npz'


def validation_result_path(filename: str) -> Path:
    """Return the full path under ``mock_results/`` for a given filename."""
    return Path(_MOCK_DIR) / filename


def load_per_star_truth(result) -> 'np.ndarray | None':
    """Return per-star is_binary boolean array (length n_stars), or None.

    Loads the ground-truth binary flags from the sibling
    ``mock_stars.npz`` referenced by ``result['mock_stars_subdir']`` (only
    present on validation runs).  Returns ``None`` for non-validation
    flows (no key, missing file, or malformed payload) — callers must
    handle that case (omit the truth-coded markers silently).

    Parameters
    ----------
    result : dict or NpzFile-like
        Loaded validation result.  ``mock_stars_subdir`` may be relative
        to the repo root or absolute.  Tolerant of 0-d ``np.ndarray``
        wrappers produced by ``np.savez``.

    Returns
    -------
    np.ndarray of bool, shape (n_stars,), or None.
    """
    # Tolerate dict OR NpzFile-like access patterns
    try:
        if hasattr(result, 'files'):
            _sub = result['mock_stars_subdir'] if (
                'mock_stars_subdir' in result.files) else None
        else:
            _sub = result.get('mock_stars_subdir', None)
    except Exception:
        _sub = None
    if _sub is None:
        return None
    # Unwrap 0-d numpy object arrays
    if isinstance(_sub, np.ndarray):
        try:
            _sub = _sub.item()
        except Exception:
            _sub = str(_sub)
    _sub = str(_sub)
    if not _sub:
        return None

    # Resolve relative paths against repo root
    if not os.path.isabs(_sub):
        _sub = os.path.join(_ROOT, _sub)
    mock_stars_path = os.path.join(_sub, 'mock_stars.npz')
    if not os.path.exists(mock_stars_path):
        return None

    try:
        m = np.load(mock_stars_path, allow_pickle=True)
        if 'stars' not in m.files:
            m.close()
            return None
        stars = m['stars'].item()
        m.close()
        if not isinstance(stars, dict) or len(stars) == 0:
            return None
        keys_sorted = sorted(stars.keys())
        flags = np.array(
            [bool(stars[k].get('is_binary', False)) for k in keys_sorted],
            dtype=bool,
        )
        return flags
    except Exception:
        return None


def mock_observations_dir(result_filename: str) -> Path:
    """Return the mock_observations subdir for a given result .npz filename.

    The subdir is named after the .npz stem (no extension).
    """
    stem = os.path.basename(result_filename)
    if stem.endswith('.npz'):
        stem = stem[:-4]
    return Path(_MOCK_OBS_DIR) / stem


def ensure_dirs() -> None:
    """Ensure both ``mock_results/`` and ``mock_observations/`` exist."""
    os.makedirs(_MOCK_DIR, exist_ok=True)
    os.makedirs(_MOCK_OBS_DIR, exist_ok=True)


# ── Save helpers ──────────────────────────────────────────────────────────

def _build_mock_stars_payload(
    mock_detail: dict, cadence_library, sigma_meas: float,
) -> dict:
    """Build the per-star dict that goes into ``mock_stars.npz``.

    Keys are integer star indices (0..N-1). Values are small dicts
    with ``rvs`` / ``times`` / ``errs`` / ``is_binary``.

    ``errs`` is taken directly from ``mock_detail['errs_per_star'][k]``
    when present (post-2026-04-23 mock format carries per-epoch error
    magnitudes drawn from the configured distribution).  For legacy
    mocks that lack ``errs_per_star``, falls back to broadcasting the
    scalar ``sigma_meas`` across all epochs (preserves backward
    compatibility with old saved mocks).
    """
    rvs_per_star = mock_detail.get('rvs_per_star', []) or []
    errs_per_star = mock_detail.get('errs_per_star')
    is_binary = np.asarray(mock_detail.get('is_binary', []), dtype=bool)
    n_stars = len(rvs_per_star)

    stars: dict = {}
    for k in range(n_stars):
        rvs = np.asarray(rvs_per_star[k], dtype=float)
        if cadence_library is not None and k < len(cadence_library):
            times = np.asarray(cadence_library[k], dtype=float)
        else:
            times = np.array([], dtype=float)
        # Prefer per-epoch errs from the mock generator.  Fall back to
        # sigma_meas broadcast for pre-2026-04-23 mock formats.
        _err_k = (errs_per_star[k]
                  if (errs_per_star is not None and k < len(errs_per_star)
                      and errs_per_star[k] is not None)
                  else None)
        if _err_k is not None and np.asarray(_err_k).size > 0:
            errs = np.asarray(_err_k, dtype=float)
        elif rvs.size > 0:
            errs = np.full_like(rvs, float(sigma_meas))
        else:
            errs = np.array([], dtype=float)
        stars[int(k)] = {
            'rvs': rvs,
            'times': times,
            'errs': errs,
            'is_binary': bool(is_binary[k]) if k < is_binary.size else False,
        }
    return stars


def save_mock_stars(path: str, stars: dict) -> None:
    """Write the pickled per-star dict to ``path``."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # Wrap the dict in an object array so np.savez can pickle it.
    np.savez(path, stars=np.array(stars, dtype=object))


def _result_to_save_dict(result: dict) -> dict:
    """Replicate the normalization done in ``_run_cadence_bg``'s save block.

    Every non-ndarray value is wrapped as ``np.array(v, dtype=object)`` so
    ``np.savez_compressed`` can serialize it.
    """
    out: dict = {}
    for k, v in result.items():
        if isinstance(v, np.ndarray):
            out[k] = v
        else:
            out[k] = np.array(v, dtype=object)
    return out


def save_validation_result(
    result: dict,
    mock_detail: dict | None,
    truth: dict,
    cadence_library=None,
    sigma_meas: float = 1.622,
    *,
    partial: bool = False,
    existing_path: str | None = None,
) -> tuple[str, str | None]:
    """Save a validation run.

    Writes:
      - ``mock_results/<filename>.npz`` — full result payload
      - ``mock_results/mock_observations/<stem>/mock_stars.npz`` — per-star dict

    Parameters
    ----------
    result : dict
        The full cadence-run result dict (as produced by ``_run_cadence_bg``).
    mock_detail : dict or None
        Output of ``generate_mock_observations_detail``. Required on first
        save (fresh run). On subsequent partial saves it can be ``None``
        (mock_stars file is stable and written only once).
    truth : dict
        Must contain ``true_fbin``, ``true_pi``, ``true_sigma``,
        ``true_logPmax``, ``seed``.
    cadence_library : list or None
        Per-star MJD arrays — used for the ``times`` field in mock_stars.
        If ``None``, falls back to the cadence array stored in ``result``.
    sigma_meas : float
        Measurement uncertainty. Broadcast to per-epoch ``errs``.
    partial : bool
        If True, writes a ``*_partial_*`` checkpoint file. mock_stars is
        written only if the target subdir does not yet contain one.
    existing_path : str or None
        For partial saves: reuse the existing partial path instead of
        minting a new timestamp.

    Returns
    -------
    (result_path, mock_stars_path_or_None)
    """
    ensure_dirs()

    # Build a grid_ranges dict from the result arrays for the filename
    fbin_grid = np.asarray(result.get('fbin_grid', []), dtype=float)
    pi_grid = np.asarray(result.get('pi_grid', []), dtype=float)
    sigma_grid = np.asarray(result.get('sigma_grid', []), dtype=float)
    logPmax_grid = np.asarray(result.get('logPmax_grid', []), dtype=float)
    grid_ranges = {
        'fb_min': float(fbin_grid[0]) if fbin_grid.size else None,
        'fb_max': float(fbin_grid[-1]) if fbin_grid.size else None,
        'fb_steps': int(fbin_grid.size) if fbin_grid.size else None,
        'pi_min': float(pi_grid[0]) if pi_grid.size else None,
        'pi_max': float(pi_grid[-1]) if pi_grid.size else None,
        'pi_steps': int(pi_grid.size) if pi_grid.size else None,
        'sig_min': float(sigma_grid[0]) if sigma_grid.size else None,
        'sig_max': float(sigma_grid[-1]) if sigma_grid.size else None,
        'sig_steps': int(sigma_grid.size) if sigma_grid.size else None,
        'logPmax_min': (float(logPmax_grid[0])
                        if logPmax_grid.size else None),
        'logPmax_max': (float(logPmax_grid[-1])
                        if logPmax_grid.size else None),
        'logPmax_steps': (int(logPmax_grid.size)
                          if logPmax_grid.size > 1 else None),
        'n_sets': int(result.get('n_sets', 0)) or None,
    }

    period_model = str(result.get('period_model', 'powerlaw'))
    model = 'dsilva' if period_model == 'powerlaw' else 'langer'

    # Determine output path
    if existing_path:
        result_path = existing_path
        result_filename = os.path.basename(result_path)
    else:
        result_filename = build_validation_filename(
            model, truth, grid_ranges, partial=partial)
        result_path = str(validation_result_path(result_filename))

    # Augment result with validation-specific fields before saving
    mock_subdir = mock_observations_dir(result_filename)
    augmented = dict(result)
    augmented['is_validation'] = True
    augmented['true_fbin'] = float(truth.get('true_fbin', np.nan))
    augmented['true_pi'] = float(truth.get('true_pi', np.nan))
    augmented['true_sigma'] = float(truth.get('true_sigma', np.nan))
    augmented['true_logPmax'] = float(truth.get('true_logPmax', np.nan))
    augmented['seed'] = int(truth.get('seed', 0))
    # mock_delta_rv may already be present; fall back to mock_detail if not
    if 'mock_delta_rv' not in augmented and mock_detail is not None:
        augmented['mock_delta_rv'] = np.asarray(
            mock_detail.get('delta_rv', []), dtype=float)
    augmented['mock_stars_subdir'] = os.path.relpath(
        str(mock_subdir), _ROOT)

    # Ensure timestamp + settings survive round-trip if missing
    if 'timestamp' not in augmented:
        augmented['timestamp'] = _dt.datetime.now().isoformat()

    save_dict = _result_to_save_dict(augmented)
    os.makedirs(_MOCK_DIR, exist_ok=True)
    np.savez_compressed(result_path, **save_dict)

    # Write mock_stars.npz (only if mock_detail provided and file missing)
    mock_stars_path = None
    if mock_detail is not None:
        # Fall back to the cadence_library stored in the result if caller
        # did not pass one explicitly (e.g. partial saves).
        _cad = cadence_library
        if _cad is None:
            _cad = result.get('cadence_library')
            if isinstance(_cad, np.ndarray):
                _cad = list(_cad)
        mock_subdir_str = str(mock_subdir)
        mock_stars_path = os.path.join(mock_subdir_str, 'mock_stars.npz')
        already_exists = os.path.exists(mock_stars_path)
        if not (partial and already_exists):
            stars = _build_mock_stars_payload(
                mock_detail, _cad, float(sigma_meas))
            save_mock_stars(mock_stars_path, stars)

    # Invalidate any cached metadata scan after a new save
    try:
        scan_validation_metadata.clear()
    except Exception:
        pass

    return result_path, mock_stars_path


# ── List / load helpers ───────────────────────────────────────────────────

def list_validation_results(model: str | None = None) -> list[tuple[str, str]]:
    """List saved validation .npz result files, newest first.

    Parameters
    ----------
    model : 'dsilva', 'langer', or None (both).

    Returns
    -------
    list of (display_name, full_path) tuples.
    """
    ensure_dirs()
    models = [model] if model in _VALID_MODELS else list(_VALID_MODELS)
    files: list[str] = []
    for mdl in models:
        pattern = os.path.join(_MOCK_DIR, f'validation_{mdl}_*.npz')
        files.extend(_glob.glob(pattern))
    # Exclude partial checkpoints
    files = [f for f in files
             if '_partial_' not in os.path.basename(f)]
    files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    return [(os.path.basename(f).replace('.npz', ''), f) for f in files]


def list_validation_partials(model: str | None = None) -> list[tuple[str, str]]:
    """List partial validation .npz files, newest first."""
    ensure_dirs()
    models = [model] if model in _VALID_MODELS else list(_VALID_MODELS)
    files: list[str] = []
    for mdl in models:
        pattern = os.path.join(_MOCK_DIR, f'validation_{mdl}_partial_*.npz')
        files.extend(_glob.glob(pattern))
    files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    return [(os.path.basename(f), f) for f in files]


def load_validation_result(path: str) -> tuple[dict, dict | None]:
    """Load a validation result + its sibling mock_stars file.

    Returns
    -------
    (result_dict, mock_detail_or_None)
        ``mock_detail`` mirrors the structure produced by
        ``generate_mock_observations_detail`` — keys ``delta_rv``,
        ``is_binary``, ``rvs_per_star``, ``n_epochs``, ``rv_min``,
        ``rv_max``, ``seed``. Returns ``None`` if the mock_stars file
        is missing.

    Bug 4 (2026-04-27): files saved before Sprint 4 only carry the
    legacy ``mode_*`` (marginal-mode) keys.  We refuse to silently
    surface those as joint-argmax — the loader emits a Streamlit
    warning so the user knows to re-run the validation grid.
    """
    d = np.load(path, allow_pickle=True)
    _file_keys = set(d.files)
    result: dict = {}
    for k in d.files:
        v = d[k]
        # Unwrap 0-d object arrays back to Python scalars where possible
        if isinstance(v, np.ndarray) and v.dtype == object and v.shape == ():
            try:
                result[k] = v.item()
            except Exception:
                result[k] = v
        else:
            result[k] = v
    d.close()

    # Bug 4 (2026-04-27): warn on legacy .npz files that only have
    # marginal-mode keys.  Honest-labels rule forbids substituting them
    # for joint-argmax; the loader stays loud so the user knows the
    # saved-runs table will show '—' for best-fit columns.
    _has_argmax = any(k in _file_keys for k in (
        'argmax_fbin', 'argmax_pi', 'argmax_sigma', 'argmax_logPmax'))
    _has_mode = any(k in _file_keys for k in (
        'mode_fbin', 'mode_pi', 'mode_sigma'))
    if _has_mode and not _has_argmax:
        try:
            import streamlit as _st
            _st.warning(
                f'`{os.path.basename(path)}` was saved before Sprint 4 '
                '(only marginal-mode keys present).  Joint-argmax '
                'columns will display "—" for this run.  Re-run the '
                'validation grid to regenerate with honest labels.'
            )
        except Exception:
            print(
                f'[validation_io] WARN: legacy .npz {path} has only '
                'mode_* keys; joint argmax columns will be blank.',
                file=sys.stderr,
            )

    # Locate mock_stars.npz
    result_filename = os.path.basename(path)
    mock_subdir = mock_observations_dir(result_filename)
    mock_stars_path = mock_subdir / 'mock_stars.npz'
    mock_detail: dict | None = None
    if mock_stars_path.exists():
        m = np.load(mock_stars_path, allow_pickle=True)
        if 'stars' in m.files:
            raw = m['stars'].item()
            # Rebuild the detail structure expected by the UI
            n = len(raw)
            delta_rv = np.zeros(n, dtype=float)
            is_binary = np.zeros(n, dtype=bool)
            rvs_per_star: list = []
            n_epochs = np.zeros(n, dtype=int)
            rv_min = np.full(n, np.nan, dtype=float)
            rv_max = np.full(n, np.nan, dtype=float)
            for k in range(n):
                star = raw.get(k, {})
                rvs = np.asarray(star.get('rvs', []), dtype=float)
                rvs_per_star.append(rvs)
                n_epochs[k] = int(rvs.size)
                if rvs.size > 0:
                    rv_min[k] = float(rvs.min())
                    rv_max[k] = float(rvs.max())
                    delta_rv[k] = float(rvs.max() - rvs.min()) if rvs.size >= 2 else 0.0
                is_binary[k] = bool(star.get('is_binary', False))
            mock_detail = {
                'delta_rv': delta_rv,
                'is_binary': is_binary,
                'rvs_per_star': rvs_per_star,
                'n_epochs': n_epochs,
                'rv_min': rv_min,
                'rv_max': rv_max,
                'seed': int(result.get('seed', 0)),
            }
        m.close()

    return result, mock_detail


def delete_validation_result(path: str) -> None:
    """Delete a validation .npz and its sibling mock_observations subdir."""
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    subdir = mock_observations_dir(os.path.basename(path))
    if subdir.exists():
        shutil.rmtree(subdir, ignore_errors=True)
    try:
        scan_validation_metadata.clear()
    except Exception:
        pass


# ── Metadata scanner (cached) ─────────────────────────────────────────────

def _range_str(arr) -> str:
    a = np.asarray(arr) if arr is not None else None
    if a is None or a.size == 0:
        return '—'
    if a.size == 1:
        return f'{float(a[0]):.2f}'
    return f'{float(a[0]):.2f}\u2013{float(a[-1]):.2f} ({a.size})'


@st.cache_data(ttl=30)
def scan_validation_metadata(model: str | None = None) -> pd.DataFrame:
    """Scan saved validation .npz result files; return a display DataFrame.

    Columns: Date, truth_f_bin, truth_pi, truth_sigma, truth_logPmax, seed,
    f_bin range, pi range, sigma range, logP range, N_stars, N_sets,
    sigma_meas, period_model, best_fbin, best_pi, best_sigma, Runtime,
    File name, _path.
    """
    rows: list[dict] = []
    for name, path in list_validation_results(model):
        try:
            d = np.load(path, allow_pickle=True)

            # Truth params
            def _safe_float(key, default=np.nan):
                if key not in d.files:
                    return float(default)
                try:
                    return float(np.asarray(d[key]).item())
                except Exception:
                    try:
                        return float(d[key])
                    except Exception:
                        return float(default)

            true_fb = _safe_float('true_fbin')
            true_pi = _safe_float('true_pi')
            true_sig = _safe_float('true_sigma')
            true_lp = _safe_float('true_logPmax')
            seed = int(_safe_float('seed', 0))

            fb = np.asarray(d.get('fbin_grid', np.array([])))
            pi = np.asarray(d.get('pi_grid', np.array([])))
            sig = np.asarray(d.get('sigma_grid', np.array([])))
            logP = np.asarray(d.get('logPmax_grid', np.array([])))

            # Settings (for sigma_meas, period_model, n_stars etc.)
            sett = {}
            if 'settings' in d.files:
                try:
                    sett = json.loads(str(d['settings']))
                except Exception:
                    pass
            n_stars = str(sett.get('n_stars_sim', '—'))
            sigma_meas = sett.get('sigma_measure', '—')
            if sigma_meas != '—':
                try:
                    sigma_meas = f'{float(sigma_meas):.2f}'
                except Exception:
                    sigma_meas = '—'

            period_model = '—'
            if 'period_model' in d.files:
                try:
                    period_model = str(np.asarray(d['period_model']).item())
                except Exception:
                    period_model = str(d['period_model'])
            elif 'period_model' in sett:
                period_model = str(sett['period_model'])

            n_sets_val = (str(int(np.asarray(d['n_sets']).item()))
                          if 'n_sets' in d.files else '—')

            # Best recovered params (joint argmax only).
            # Bug 4 (2026-04-27): the mode_* back-compat fallback has been
            # removed per memory/feedback_honest_labels.md — silently
            # substituting the MARGINAL mode for the JOINT argmax in the
            # saved-runs table is exactly the dishonest-label trap that
            # rule forbids.  Pre-Sprint-4 .npz files (which only carry
            # mode_* keys) now show '—' here; the loader path emits a
            # clear warning when those files are opened so the user knows
            # to re-run the validation grid to regenerate.
            best_fb = (f'{_safe_float("argmax_fbin"):.3f}'
                       if 'argmax_fbin' in d.files else '—')
            best_pi = (f'{_safe_float("argmax_pi"):.3f}'
                       if 'argmax_pi' in d.files else '—')
            best_sig = (f'{_safe_float("argmax_sigma"):.3f}'
                        if 'argmax_sigma' in d.files else '—')

            # Runtime
            if 'runtime_seconds' in d.files:
                _rt = _safe_float('runtime_seconds', 0.0)
                if _rt >= 3600:
                    runtime_str = f'{_rt/3600:.1f}h'
                elif _rt >= 60:
                    runtime_str = f'{_rt/60:.1f}m'
                else:
                    runtime_str = f'{_rt:.0f}s'
            else:
                runtime_str = '—'

            # Timestamp
            ts = '—'
            if 'timestamp' in d.files:
                try:
                    ts = str(np.asarray(d['timestamp']).item())
                except Exception:
                    ts = str(d['timestamp'])
                ts = ts.replace('T', ' ')[:19]

            d.close()

            rows.append({
                'Date': ts,
                'truth_f_bin': (f'{true_fb:.3f}'
                                if np.isfinite(true_fb) else '—'),
                'truth_pi': (f'{true_pi:.3f}'
                             if np.isfinite(true_pi) else '—'),
                'truth_sigma': (f'{true_sig:.2f}'
                                if np.isfinite(true_sig) else '—'),
                'truth_logPmax': (f'{true_lp:.2f}'
                                  if np.isfinite(true_lp) else '—'),
                'seed': seed,
                'f_bin range': _range_str(fb),
                'pi range': _range_str(pi),
                'sigma range': _range_str(sig),
                'logP range': _range_str(logP),
                'N_stars': n_stars,
                'N_sets': n_sets_val,
                'sigma_meas': sigma_meas,
                'period_model': period_model,
                'best_fbin': best_fb,
                'best_pi': best_pi,
                'best_sigma': best_sig,
                'Runtime': runtime_str,
                'File name': name,
                '_path': path,
            })
        except Exception:
            continue
    return pd.DataFrame(rows) if rows else pd.DataFrame()
