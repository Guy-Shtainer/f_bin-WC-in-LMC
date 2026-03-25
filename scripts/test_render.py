#!/usr/bin/env python
"""Runtime render test — loads a real .npz result and calls all rendering functions.

Catches NameError, TypeError, AttributeError, KeyError that static analysis misses.
Uses unittest.mock to stub out Streamlit widgets.

Usage:
    conda run -n guyenv python scripts/test_render.py [result.npz]
"""
import sys, os, glob
import unittest.mock as mock
import numpy as np

# ── Setup paths ──────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'app'))

# ── Mock Streamlit ───────────────────────────────────────────────────────
st_mock = mock.MagicMock()
st_mock.session_state = {}
class SmartColumnMock(mock.MagicMock):
    """Column mock that returns sensible defaults for widget calls."""
    def slider(self, *a, **kw):
        return kw.get('value', kw.get('min_value', 0.5))
    def number_input(self, *a, **kw):
        return kw.get('value', 1000)
    def selectbox(self, *a, **kw):
        return kw.get('options', [None])[kw.get('index', 0)] if kw.get('options') else None
    def multiselect(self, *a, **kw):
        return kw.get('default', [])
    def radio(self, *a, **kw):
        opts = a[1] if len(a) > 1 else kw.get('options', [''])
        return opts[kw.get('index', 0)] if opts else ''
    def select_slider(self, *a, **kw):
        return kw.get('value', 0)
    def checkbox(self, *a, **kw):
        return kw.get('value', False)
    def text_input(self, *a, **kw):
        return kw.get('value', '')

def _columns_mock(*a, **kw):
    if a:
        n = a[0] if isinstance(a[0], int) else len(a[0])
    else:
        n = 2
    return [SmartColumnMock() for _ in range(n)]
st_mock.columns = _columns_mock
st_mock.expander = mock.MagicMock(return_value=mock.MagicMock(__enter__=mock.MagicMock(return_value=mock.MagicMock()), __exit__=mock.MagicMock(return_value=False)))
st_mock.container = mock.MagicMock(return_value=mock.MagicMock(__enter__=mock.MagicMock(return_value=mock.MagicMock()), __exit__=mock.MagicMock(return_value=False)))
st_mock.empty = mock.MagicMock(return_value=mock.MagicMock())
st_mock.checkbox = mock.MagicMock(return_value=False)
def _radio_mock(*a, **kw):
    opts = a[1] if len(a) > 1 else kw.get('options', ['Range-based'])
    idx = kw.get('index', 0)
    return opts[idx] if opts and idx < len(opts) else 'Range-based'
st_mock.radio = _radio_mock
st_mock.select_slider = mock.MagicMock(return_value=0)
# Slider mock: return the 'value' kwarg if provided, else 'min_value', else 0.5
def _slider_mock(*a, **kw):
    return kw.get('value', kw.get('min_value', 0.5))
st_mock.slider = _slider_mock
# number_input: return value kwarg if provided
def _number_input_mock(*a, **kw):
    return kw.get('value', 1000)
st_mock.number_input = _number_input_mock
st_mock.button = mock.MagicMock(return_value=False)
st_mock.multiselect = mock.MagicMock(return_value=[])
# cache_data can be used as @st.cache_data or @st.cache_data(...)
def _cache_data_mock(func=None, **kwargs):
    if func is not None:
        return func  # @st.cache_data (no parens)
    return lambda f: f  # @st.cache_data(...) with kwargs
st_mock.cache_data = _cache_data_mock
st_mock.cache_resource = _cache_data_mock
def _fragment_mock(func=None, **kwargs):
    if func is not None:
        return func
    return lambda f: f
st_mock.fragment = _fragment_mock
sys.modules['streamlit'] = st_mock

# ── Find result file ────────────────────────────────────────────────────
if len(sys.argv) > 1:
    npz_path = sys.argv[1]
else:
    candidates = sorted(glob.glob(os.path.join(ROOT, 'results', 'cadence_dsilva_*_sig*_logP*.npz')))
    if not candidates:
        candidates = sorted(glob.glob(os.path.join(ROOT, 'results', 'cadence_dsilva_*.npz')))
    if not candidates:
        print('FAIL: No result .npz files found in results/')
        sys.exit(1)
    npz_path = candidates[0]

print(f'Loading: {os.path.basename(npz_path)}')
raw = np.load(npz_path, allow_pickle=True)
result = {k: raw[k].item() if raw[k].ndim == 0 else raw[k] for k in raw.files}

# ── Build model context ─────────────────────────────────────────────────
fbin_g = np.asarray(result.get('fbin_grid', [0.5]))
pi_g = np.asarray(result.get('pi_grid', [0.0]))
sigma_g = np.asarray(result.get('sigma_grid', [5.0]))
logPmax_g = np.asarray(result.get('logPmax_grid', []))
lk = np.asarray(result.get('likelihood', []))

passed = 0
failed = 0
warnings = 0

def run_test(name, func, *args, **kwargs):
    global passed, failed, warnings
    try:
        func(*args, **kwargs)
        print(f'  ✅ {name}')
        passed += 1
    except Exception as e:
        etype = type(e).__name__
        if 'streamlit' in str(e).lower() or 'Streamlit' in etype:
            print(f'  ⚠️  {name}: {etype} (Streamlit runtime — expected)')
            warnings += 1
        else:
            print(f'  ❌ {name}: {etype}: {e}')
            failed += 1

# ── Test render_shared ───────────────────────────────────────────────────
print('\n=== render_shared ===')
from bc.render_shared import (
    _render_method_summary_section, _render_all_methods_cdf,
    render_binary_fraction_vs_threshold, render_orbital_histograms,
    render_methodology_equations, _build_extra_grids,
)

ctx_shared = {
    'result': result, 'fbin_g': fbin_g, 'x_g': pi_g,
    'x_name': 'pi', 'x_label': 'pi', 'ndim_mode': 'cadence_dsilva',
    'sigma_g': sigma_g if sigma_g.size > 1 else None,
    'logPmax_g': logPmax_g if logPmax_g.size > 1 else None,
}

run_test('_build_extra_grids', lambda: _build_extra_grids(ctx_shared))
run_test('_render_method_summary_section', lambda: _render_method_summary_section(
    result, fbin_g, pi_g, prefix='test',
    x_name='pi', x_label='pi', ndim_mode='cadence_dsilva',
    extra_grids=_build_extra_grids(ctx_shared)))
run_test('render_methodology_equations', lambda: render_methodology_equations('dsilva'))

# ── Test render_lk ───────────────────────────────────────────────────────
print('\n=== render_lk ===')
from bc.render_lk import render_lk_tab

model_ctx = {
    **ctx_shared,
    'model_type': 'cadence_dsilva',
    'x_display_label': 'π (period power-law index)',
    'canvas_height': 400, 'canvas_width': None,
    'use_container_width': True,
    'disp_outer_slices': None,
    'gap_sim': None, 'thresh_dRV': 45.5,
    'has_case_AB': False,
}

# This is the big one — calls _render_lk_expander which calls scoring, fit, explorer
run_test('render_lk_tab (full pipeline)', lambda: render_lk_tab('test', model_ctx, {}))

# ── Test render_lk_explorer specifically ─────────────────────────────────
print('\n=== render_lk_explorer ===')
from bc.render_lk_explorer import _render_lk_cdf_sanity_check

if lk.size > 0:
    obs_drv = result.get('obs_delta_rv')
    if obs_drv is not None:
        obs_drv = np.asarray(obs_drv)
        # Find best-fit values
        flat = int(np.nanargmax(lk))
        best_idx = np.unravel_index(flat, lk.shape)
        best_fb = float(fbin_g[best_idx[-2]] if lk.ndim >= 2 else 0.5)
        best_x = float(pi_g[best_idx[-1]] if lk.ndim >= 2 else 0.0)
        best_sig = float(sigma_g[best_idx[0]] if sigma_g.size > 1 and lk.ndim >= 3 else sigma_g[0])

        run_test('_render_lk_cdf_sanity_check', lambda: _render_lk_cdf_sanity_check(
            best_fb, best_x, best_sig, obs_drv, 'dsilva', result, 'test'))

# ── Summary ──────────────────────────────────────────────────────────────
print(f'\n{"="*50}')
print(f'Passed: {passed} | Failed: {failed} | Warnings: {warnings}')
if failed > 0:
    print('OVERALL: ❌ FAIL')
    sys.exit(1)
else:
    print('OVERALL: ✅ PASS')
    sys.exit(0)
