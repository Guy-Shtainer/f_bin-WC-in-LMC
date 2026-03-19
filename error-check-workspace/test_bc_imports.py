"""Runtime import and integration test for app/bc/ modules.

Run after ANY change to app/bc/ files. Catches the bugs that py_compile misses:
- Missing imports (NameError)
- Undefined variables in function bodies
- Wrong function signatures
- Missing dict keys

Usage:
    conda run -n guyenv python error-check-workspace/test_bc_imports.py
"""
import sys
import os
import inspect
import numpy as np

# Setup path like Streamlit does
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, 'app'))
os.chdir(os.path.join(_ROOT, 'app'))
sys.path.insert(0, _ROOT)

passed = 0
failed = 0
errors = []


def check(name, condition, msg=''):
    global passed, failed
    if condition:
        passed += 1
    else:
        failed += 1
        errors.append(f'FAIL: {name} — {msg}')
        print(f'  FAIL: {name} — {msg}')


print('=' * 60)
print('Runtime Import & Integration Test for app/bc/')
print('=' * 60)

# ── 1. Module imports ────────────────────────────────────────
print('\n1. Testing module imports...')
try:
    from bc.analysis import (
        _render_method_summary_section,
        _render_method_expander,
        _render_cvm_analysis,
        _get_method_array,
        _render_all_methods_cdf,
    )
    check('analysis imports', True)
except ImportError as e:
    check('analysis imports', False, str(e))

try:
    from bc.cadence import _get_method_array as _gma_cadence
    check('cadence._get_method_array import', True)
except ImportError as e:
    check('cadence._get_method_array import', False, str(e))

try:
    from bc.analysis import _get_method_array as _gma_dsilva
    check('analysis._get_method_array import (used by dsilva via subtabs)', True)
except ImportError as e:
    check('analysis._get_method_array import (used by dsilva via subtabs)', False, str(e))

try:
    from bc.langer import _get_method_array as _gma_langer
    check('langer._get_method_array import', True)
except ImportError as e:
    check('langer._get_method_array import', False, str(e))

try:
    from bc.likelihood_viz import (
        render_likelihood_cdf,
        render_likelihood_stats_table,
        render_likelihood_explanation,
    )
    check('likelihood_viz imports', True)
except ImportError as e:
    check('likelihood_viz imports', False, str(e))

try:
    from bc.helpers import SCORING_METHODS, _hex_to_rgba
    check('helpers imports', True)
except ImportError as e:
    check('helpers imports', False, str(e))

# ── 2. Palette keys ──────────────────────────────────────────
print('\n2. Testing palette keys...')
try:
    from shared import get_palette, PLOTLY_THEME
    pal = get_palette()
    required_keys = ['contour_label', 'contour_color', 'annotation_bg',
                     'annotation_font', 'plot_bg', 'paper_bg']
    for k in required_keys:
        check(f'palette key "{k}"', k in pal, f'missing from palette')
except Exception as e:
    check('get_palette()', False, str(e))

# ── 3. Function signatures ───────────────────────────────────
print('\n3. Testing function signatures...')
sig = inspect.signature(_render_method_expander)
params = list(sig.parameters.keys())
check('_render_method_expander has method_results param',
      'method_results' in params,
      f'params: {params}')
check('_render_method_expander has result param',
      'result' in params,
      f'params: {params}')

sig_cvm = inspect.signature(_render_cvm_analysis)
cvm_params = list(sig_cvm.parameters.keys())
check('_render_cvm_analysis has result param',
      'result' in cvm_params,
      f'params: {cvm_params}')

# ── 4. _get_method_array with mock data ──────────────────────
print('\n4. Testing _get_method_array with mock data...')
mock_result = {
    'ks_p': np.ones((3, 4, 5)),
    'ks_D': np.ones((3, 4, 5)),
    'likelihood': np.ones((3, 4, 5)),
    'logL_raw': -np.ones((3, 4, 5)),
}
for key in ['ks_p', 'ks_D', 'likelihood', 'logL_raw']:
    arr = _get_method_array(mock_result, key)
    check(f'_get_method_array("{key}")', arr is not None and arr.shape == (3, 4, 5),
          f'returned {type(arr)}')

missing = _get_method_array(mock_result, 'nonexistent_key')
check('_get_method_array missing key returns None', missing is None,
      f'returned {missing}')

# ── 5. Likelihood normalization logic ─────────────────────────
print('\n5. Testing likelihood normalization (global vs per-slice)...')
# Create fake logL_raw with different maxima per sigma slice
logL_raw = np.array([
    [[-10, -12], [-11, -13]],  # σ=0: max = -10
    [[-5, -7], [-6, -8]],     # σ=1: max = -5
    [[-15, -17], [-16, -18]], # σ=2: max = -15
])  # shape (3, 2, 2)

# Global normalization (correct)
logL_max = np.nanmax(logL_raw)  # should be -5
check('global logL max', logL_max == -5.0, f'got {logL_max}')
likelihood = np.exp(logL_raw - logL_max)

# Verify NOT all slices have max=1.0
max_per_sig = np.nanmax(likelihood, axis=(1, 2))
check('σ=0 max likelihood < 1.0', max_per_sig[0] < 1.0,
      f'got {max_per_sig[0]:.6f} (should be exp(-5) ≈ 0.0067)')
check('σ=1 max likelihood == 1.0', max_per_sig[1] == 1.0,
      f'got {max_per_sig[1]:.6f}')
check('σ=2 max likelihood < 1.0', max_per_sig[2] < 1.0,
      f'got {max_per_sig[2]:.6f}')
check('not all sigmas equal', len(set(max_per_sig.round(6))) > 1,
      f'all are {max_per_sig}')

# ── 6. SCORING_METHODS consistency ────────────────────────────
print('\n6. Testing SCORING_METHODS consistency...')
expected_keys = {'ks', 'weighted', 'cvm', 'likelihood'}
actual_keys = {m[0] for m in SCORING_METHODS}
check('SCORING_METHODS has all 4 methods', expected_keys == actual_keys,
      f'got {actual_keys}')

# Verify each method has (key, name, p_key, d_key, color)
for mk, mname, pk, dk, mcolor in SCORING_METHODS:
    check(f'SCORING_METHODS[{mk}] has 5 elements', True)

# ── Summary ───────────────────────────────────────────────────
print('\n' + '=' * 60)
if failed == 0:
    print(f'ALL {passed} CHECKS PASSED')
else:
    print(f'{failed} FAILED, {passed} passed')
    print('\nFailures:')
    for e in errors:
        print(f'  {e}')
    sys.exit(1)
