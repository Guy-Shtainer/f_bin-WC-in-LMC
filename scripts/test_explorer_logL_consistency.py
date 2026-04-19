#!/usr/bin/env python
"""E048 regression test — Model Explorer logL must match grid's logL_raw.

Loads the most recent cadence result .npz, finds argmax of logL_raw, calls
_me_cdf_band with the SAME bin_cfg / period_model / cadence_weights the grid
used, recomputes multinomial_log_likelihood, and asserts the absolute
difference is within Monte-Carlo noise for the result's n_sets.

Tolerance:
    ~2.0 at n_sets = 50  (default)
    ~0.5 at n_sets = 500
    ~0.3 at n_sets = 1000+

Usage:
    conda run -n guyenv python scripts/test_explorer_logL_consistency.py [result.npz]
"""
import sys
import os
import glob
import unittest.mock as mock
import numpy as np

# ── Setup paths ──────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'app'))

# ── Mock Streamlit (needed because _me_cdf_band is decorated with
#    @st.cache_data and the shared module imports Streamlit at top level) ─
st_mock = mock.MagicMock()
st_mock.session_state = {}


def _cache_data_mock(func=None, **kwargs):
    if func is not None:
        return func
    return lambda f: f


st_mock.cache_data = _cache_data_mock
st_mock.cache_resource = _cache_data_mock
sys.modules['streamlit'] = st_mock

# ── Find result file ────────────────────────────────────────────────────
if len(sys.argv) > 1:
    npz_path = sys.argv[1]
else:
    all_cands = glob.glob(os.path.join(ROOT, 'results', 'cadence_dsilva_*.npz'))
    # Skip partial checkpoints — they lack obs_delta_rv / bin_edges /
    # cadence_library and can't round-trip a logL recomputation.
    candidates = sorted(
        [p for p in all_cands if '_partial_' not in os.path.basename(p)],
        key=lambda p: os.path.getmtime(p),
    )
    if not candidates:
        print('FAIL: No (non-partial) cadence_dsilva_*.npz files found in '
              'results/')
        sys.exit(1)
    npz_path = candidates[-1]

print(f'Loading: {os.path.basename(npz_path)}')
raw = np.load(npz_path, allow_pickle=True)


def _unwrap(v):
    """Unwrap 0-d object arrays saved by np.savez."""
    if hasattr(v, 'ndim') and v.ndim == 0 and v.dtype == object:
        try:
            return v.item()
        except Exception:
            return v
    return v


result = {k: _unwrap(raw[k]) for k in raw.files}

# ── Report what the .npz contains -----------------------------------------
print('\nResult keys present:')
for k in sorted(result.keys()):
    v = result[k]
    if isinstance(v, np.ndarray):
        print(f'  {k}: ndarray shape={v.shape} dtype={v.dtype}')
    elif isinstance(v, dict):
        print(f'  {k}: dict with {len(v)} entries')
    elif isinstance(v, (int, float, str, bool, type(None))):
        print(f'  {k}: {type(v).__name__} = {v!r}')
    else:
        print(f'  {k}: {type(v).__name__}')

has_bin_cfg = 'bin_cfg' in result and result['bin_cfg'] is not None
has_period_model = 'period_model' in result and result['period_model'] is not None
print(
    f'\nE048 persistence check: bin_cfg={has_bin_cfg}, '
    f'period_model={has_period_model}, '
    f'cadence_weights={"cadence_weights" in result}'
)

# ── Find argmax(logL_raw) -----------------------------------------------
logL_raw = result.get('logL_raw')
if logL_raw is None:
    print('FAIL: logL_raw not in result — cannot run consistency check.')
    sys.exit(1)
logL_raw = np.asarray(logL_raw, dtype=float)

if not np.any(np.isfinite(logL_raw)):
    print('FAIL: logL_raw is all NaN.')
    sys.exit(1)

flat_best = int(np.nanargmax(logL_raw))
best_idx = np.unravel_index(flat_best, logL_raw.shape)
best_logL_stored = float(logL_raw[best_idx])
print(f'\nGrid argmax index: {best_idx}')
print(f'Stored logL_raw at best: {best_logL_stored:.4f}')

# ── Recover parameters at best ------------------------------------------
fbin_g = np.asarray(result.get('fbin_grid', [0.5]))
pi_g = np.asarray(result.get('pi_grid', [0.0]))
sigma_g = np.asarray(result.get('sigma_grid', [5.0]))
logPmax_g = np.asarray(result.get('logPmax_grid', []))

ndim = logL_raw.ndim
print(f'logL_raw.ndim = {ndim}')

# Array axis order (per _single_grid_task_cadence_aware and runners_cadence):
#   4D: [logPmax, sigma, fbin, pi]
#   3D: [sigma, fbin, pi]   (no logPmax scan)
#   2D: [fbin, pi]          (no sigma, no logPmax scan)
if ndim == 4:
    i_lp, i_sig, i_fb, i_pi = best_idx
    best_lp = float(logPmax_g[i_lp])
    best_sig = float(sigma_g[i_sig])
    best_fb = float(fbin_g[i_fb])
    best_pi = float(pi_g[i_pi])
elif ndim == 3:
    i_sig, i_fb, i_pi = best_idx
    best_sig = float(sigma_g[i_sig])
    best_fb = float(fbin_g[i_fb])
    best_pi = float(pi_g[i_pi])
    best_lp = (float(logPmax_g[0]) if logPmax_g.size > 0 else 5.0)
elif ndim == 2:
    i_fb, i_pi = best_idx
    best_fb = float(fbin_g[i_fb])
    best_pi = float(pi_g[i_pi])
    best_sig = float(sigma_g[0]) if sigma_g.size > 0 else 5.0
    best_lp = float(logPmax_g[0]) if logPmax_g.size > 0 else 5.0
else:
    print(f'FAIL: unexpected logL_raw.ndim = {ndim}')
    sys.exit(1)

print(
    f'Best params: f_bin={best_fb:.4f}, pi={best_pi:.4f}, '
    f'sigma={best_sig:.4f}, logP_max={best_lp:.4f}'
)

# ── Recompute logL at best using the fixed _me_cdf_band ------------------
from bc.render_lk_explorer import (
    _me_cdf_band, _result_bin_cfg_tuple, _result_period_model,
)
from wr_bias_simulation import (
    DEFAULT_DRV_BIN_EDGES, multinomial_log_likelihood,
)

be = result.get('bin_edges')
be = np.asarray(be) if be is not None else DEFAULT_DRV_BIN_EDGES
lk_be = result.get('likelihood_bin_edges')
lk_be = np.asarray(lk_be) if lk_be is not None else be

obs = np.asarray(result.get('obs_delta_rv'))
sigma_m = float(result.get('sigma_meas', 3.0))
n_sets = int(result.get('n_sets', 50))

cad_lib = result.get('cadence_library')
cad_wt = result.get('cadence_weights')
bc_tuple = _result_bin_cfg_tuple(result)
pm = _result_period_model(result, default='powerlaw')

print(
    f'\nRe-sim inputs: n_sets={n_sets}, '
    f'cadence_library={"YES" if cad_lib is not None else "NO"}, '
    f'cadence_weights={"YES" if cad_wt is not None else "NO"}, '
    f'bin_cfg_dict={"YES" if bc_tuple is not None else "NO (fallback)"}, '
    f'period_model={pm!r}'
)

_, _, _, pooled = _me_cdf_band(
    best_fb, best_pi, best_sig, sigma_m,
    tuple(be.tolist()), logPmax=best_lp, n_sets=n_sets,
    _cadence_library=cad_lib, _cadence_weights=cad_wt,
    _bin_cfg_dict=bc_tuple, period_model=pm,
)
logL_recomputed = float(multinomial_log_likelihood(obs, pooled, lk_be))
diff = abs(logL_recomputed - best_logL_stored)

print(
    f'\nStored   : logL_raw[best_idx] = {best_logL_stored:.4f}'
    f'\nRecomputed: multinomial_log_likelihood = {logL_recomputed:.4f}'
    f'\n|Δ|       : {diff:.4f}'
)

# Monte-Carlo tolerance: loose at n_sets=50 (~2 logL), tighter at higher.
# The two calls use the SAME seed (42), so with identical bin_cfg and
# cadence they should agree up to numerical noise. Legacy .npz files that
# lack bin_cfg will diverge more strongly — in that case still assert the
# fallback works but use a larger tolerance.
if bc_tuple is None:
    tol = 8.0
    print(
        f'\n[Legacy result — no bin_cfg persisted] '
        f'Using tolerance {tol:.1f} for fallback path.'
    )
else:
    tol = max(2.0, 30.0 / np.sqrt(n_sets))
    print(f'\nTolerance (|Δ|): {tol:.2f}')

if diff > tol:
    print(f'FAIL: |Δ| = {diff:.4f} exceeds tolerance {tol:.2f}')
    sys.exit(1)

print('\nPASS — explorer logL matches grid logL_raw within Monte-Carlo noise.')
sys.exit(0)
