"""mock_inspector_app/app.py — Streamlit entry.

Side-by-side comparison: Mock Data pipeline (rng.choice for binary indices)
vs Model Explorer pipeline (rng.permutation for binary indices).

Launch:
    conda run -n guyenv streamlit run mock_inspector_app/app.py --server.port 8503
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time

# Sibling-import setup MUST happen before importing Streamlit or anything
# that pulls in production project modules (those modules expect the
# project root + app/ on sys.path so their own `from shared import ...`
# / `from bc import ...` lines resolve).
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
_APP_ROOT = os.path.join(_PROJECT_ROOT, 'app')
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

import numpy as np
import streamlit as st

# Local sibling modules
from mock_inspector_app import inspector, runner
from mock_inspector_app.settings import SettingsManager


# ─────────────────────────────────────────────────────────────────────────────
# Page setup
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    layout='wide',
    page_title='Mock Inspector',
    page_icon=None,
)

st.title('Mock Pipeline Inspector')
st.caption(
    'Side-by-side comparison: Mock Data (validation path, '
    'rng.choice for binary indices) vs Model Explorer (cadence-aware path, '
    'rng.permutation for binary indices).  Both pipelines share the same '
    'inner orbital samplers — the orbital histograms should be near-identical.'
)


# ─────────────────────────────────────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────────────────────────────────────

sm = SettingsManager()

# Hardcoded fallbacks (used only if settings.json is fresh).
DEFAULTS = {
    'insp_sigma_single': 15.0,
    'insp_sigma_meas':    5.0,
    'insp_f_bin':         0.46,
    'insp_pi':            0.0,
    'insp_logPmax':       5.0,
    'insp_error_model':   'gaussian',
    'insp_n_iter':        500,
    'insp_seed_base':     42,
    'insp_single_seed':   1,
    'insp_band_bins':     500,
}

ERROR_MODEL_OPTIONS = ['gaussian', 'asymmetric', 'none']


def _save_widget(key: str) -> None:
    """on_change callback — persist the widget's current value to JSON."""
    if key in st.session_state:
        sm.save(key, st.session_state[key])


def _load(key: str):
    """Read a value from settings.json, falling back to the hardcoded
    default if absent."""
    return sm.get(key, DEFAULTS[key])


# ─────────────────────────────────────────────────────────────────────────────
# Control region
# ─────────────────────────────────────────────────────────────────────────────

with st.container():
    # Row A — five number_inputs (no min/max constraints, per project rule)
    cA1, cA2, cA3, cA4, cA5 = st.columns(5)
    with cA1:
        st.number_input(
            'σ_single (km/s)', value=float(_load('insp_sigma_single')),
            step=0.1, format='%.2f',
            key='insp_sigma_single',
            on_change=_save_widget, args=('insp_sigma_single',),
        )
    with cA2:
        st.number_input(
            'σ_meas (km/s)', value=float(_load('insp_sigma_meas')),
            step=0.1, format='%.2f',
            key='insp_sigma_meas',
            on_change=_save_widget, args=('insp_sigma_meas',),
        )
    with cA3:
        st.number_input(
            'f_bin', value=float(_load('insp_f_bin')),
            step=0.01, format='%.3f',
            key='insp_f_bin',
            on_change=_save_widget, args=('insp_f_bin',),
        )
    with cA4:
        st.number_input(
            'π (logP exponent)', value=float(_load('insp_pi')),
            step=0.1, format='%.2f',
            key='insp_pi',
            on_change=_save_widget, args=('insp_pi',),
        )
    with cA5:
        st.number_input(
            'True logP_max', value=float(_load('insp_logPmax')),
            step=0.5, format='%.2f',
            key='insp_logPmax',
            on_change=_save_widget, args=('insp_logPmax',),
        )

    # Row B — selectbox + n_iter + seed_base
    cB1, cB2, cB3 = st.columns([2, 1, 1])
    with cB1:
        _saved_em = _load('insp_error_model')
        if _saved_em not in ERROR_MODEL_OPTIONS:
            _saved_em = 'gaussian'
        st.selectbox(
            'Error model', ERROR_MODEL_OPTIONS,
            index=ERROR_MODEL_OPTIONS.index(_saved_em),
            key='insp_error_model',
            on_change=_save_widget, args=('insp_error_model',),
        )
    with cB2:
        st.number_input(
            'N_iterations', value=int(_load('insp_n_iter')), step=50,
            format='%d',
            key='insp_n_iter',
            on_change=_save_widget, args=('insp_n_iter',),
        )
    with cB3:
        st.number_input(
            'Seed base', value=int(_load('insp_seed_base')), step=1,
            format='%d',
            key='insp_seed_base',
            on_change=_save_widget, args=('insp_seed_base',),
        )

    # Run buttons — right-aligned via spacer column.
    # Layout: [spacer, Run ▶, single-seed + Add, Clear].
    #   - "Add single run" runs ONE Mock iteration with the chosen seed and
    #     APPENDS its per-star dots/step lines to the CDF + f_bin panels.
    #     Multiple clicks accumulate; previous overlays stay visible.
    #   - "Clear single runs" wipes the accumulated overlays.
    #   - Clicking "Run ▶" also wipes accumulated overlays so the new
    #     parameter sweep's panels start unobstructed.
    _, run_col, single_col, clear_col = st.columns([3, 1, 1.4, 1])
    with run_col:
        run_clicked = st.button(
            'Run ▶', type='primary',
            key='insp_run', use_container_width=True,
            help=('Recompute the Mock and Explorer pipelines.  Also '
                  'clears any accumulated single-run overlays.'),
        )
    with single_col:
        st.number_input(
            'Single-run seed', value=int(_load('insp_single_seed')),
            step=1, format='%d',
            key='insp_single_seed',
            on_change=_save_widget, args=('insp_single_seed',),
            help='Seed used by the next "Add single run" click.',
        )
        single_clicked = st.button(
            '🎯 Add single run',
            key='insp_add_single', use_container_width=True,
            help=('Run ONE Mock-pipeline iteration of 25 stars and APPEND '
                  'per-star dots + step line to the ΔRV CDF and f_bin '
                  'panels: red = singles, green = binaries.  Each click '
                  'adds another draw; use "Clear single runs" to reset.'),
        )
    with clear_col:
        clear_clicked = st.button(
            '🧹 Clear single runs',
            key='insp_clear_single', use_container_width=True,
            help='Remove all accumulated single-draw overlays.',
        )

st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# Compute (or pull from cache)
# ─────────────────────────────────────────────────────────────────────────────

def _params_hash() -> str:
    """Stable hash of the physics parameters that drive the simulation.
    Used as the session_state cache key so back-to-back Run clicks with
    the same params show the cached results immediately.
    """
    payload = {
        'sigma_single': float(st.session_state.insp_sigma_single),
        'sigma_meas':   float(st.session_state.insp_sigma_meas),
        'f_bin':        float(st.session_state.insp_f_bin),
        'pi':           float(st.session_state.insp_pi),
        'logPmax':      float(st.session_state.insp_logPmax),
        'error_model':  str(st.session_state.insp_error_model),
        'n_iter':       int(st.session_state.insp_n_iter),
        'seed_base':    int(st.session_state.insp_seed_base),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()
                          ).hexdigest()[:16]


_RESULT_KEY_MOCK = 'insp_result_mock'
_RESULT_KEY_EXP  = 'insp_result_explorer'
_HASH_KEY        = 'insp_result_hash'


def _need_recompute() -> bool:
    cur_hash = _params_hash()
    return st.session_state.get(_HASH_KEY) != cur_hash or \
        st.session_state.get(_RESULT_KEY_MOCK) is None or \
        st.session_state.get(_RESULT_KEY_EXP) is None


if run_clicked or (_need_recompute() and st.session_state.get(_HASH_KEY) is not None):
    # If the user changed inputs WITHOUT clicking Run, fall through to the
    # render block — we DO NOT auto-recompute (the spec asks for an
    # explicit Run gate).  Only execute the simulation when run_clicked.
    pass

if run_clicked:
    # Clear any leftover single-run overlays from a previous parameter
    # setting, so the new sweep's CDF + f_bin panels start unobstructed.
    st.session_state['single_runs'] = []
    st.session_state.pop('single_run', None)  # legacy key cleanup

    cur_hash = _params_hash()
    needs_compute = (st.session_state.get(_HASH_KEY) != cur_hash) or \
        (st.session_state.get(_RESULT_KEY_MOCK) is None) or \
        (st.session_state.get(_RESULT_KEY_EXP) is None)

    if needs_compute:
        # Pre-load cadence library once so both pipelines see the same data
        # and the load cost isn't doubled.
        try:
            cad, _w = runner.load_cadence_library_uncached()
            cadence_lib = [np.asarray(c, dtype=float) for c in cad]
        except Exception as exc:
            st.error(f'Cannot load cadence library: {exc}')
            st.stop()

        prog = st.progress(0.0,
                           text='Initializing Mock Data pipeline...')

        # Mock pipeline
        t0 = time.perf_counter()

        def _cb_mock(frac: float) -> None:
            # First half of the bar belongs to Mock.
            prog.progress(0.5 * float(frac),
                          text=f'Running Mock Data pipeline ({int(frac*100)}%)...')

        result_mock = runner.run_mock_pipeline(
            sigma_single=float(st.session_state.insp_sigma_single),
            sigma_meas=float(st.session_state.insp_sigma_meas),
            f_bin=float(st.session_state.insp_f_bin),
            pi=float(st.session_state.insp_pi),
            true_logPmax=float(st.session_state.insp_logPmax),
            error_model=str(st.session_state.insp_error_model),
            n_iterations=int(st.session_state.insp_n_iter),
            seed_base=int(st.session_state.insp_seed_base),
            cadence_library=cadence_lib,
            progress_cb=_cb_mock,
        )
        t_mock = time.perf_counter() - t0

        # Explorer pipeline
        prog.progress(0.5,
                      text='Running Model Explorer pipeline...')
        t1 = time.perf_counter()

        def _cb_exp(frac: float) -> None:
            prog.progress(0.5 + 0.5 * float(frac),
                          text=f'Running Model Explorer pipeline ({int(frac*100)}%)...')

        result_exp = runner.run_explorer_pipeline(
            sigma_single=float(st.session_state.insp_sigma_single),
            sigma_meas=float(st.session_state.insp_sigma_meas),
            f_bin=float(st.session_state.insp_f_bin),
            pi=float(st.session_state.insp_pi),
            true_logPmax=float(st.session_state.insp_logPmax),
            error_model=str(st.session_state.insp_error_model),
            n_iterations=int(st.session_state.insp_n_iter),
            seed_base=int(st.session_state.insp_seed_base),
            cadence_library=cadence_lib,
            progress_cb=_cb_exp,
        )
        t_exp = time.perf_counter() - t1

        prog.progress(1.0, text='Done.')
        time.sleep(0.2)
        prog.empty()

        st.session_state[_RESULT_KEY_MOCK] = result_mock
        st.session_state[_RESULT_KEY_EXP] = result_exp
        st.session_state[_HASH_KEY] = cur_hash
        st.session_state['insp_t_mock'] = t_mock
        st.session_state['insp_t_exp'] = t_exp


# ─────────────────────────────────────────────────────────────────────────────
# "Add single run" — one Mock-pipeline iteration appended to overlays
# ─────────────────────────────────────────────────────────────────────────────

if clear_clicked:
    st.session_state['single_runs'] = []

if single_clicked:
    # Use the SAME control settings as the main run, but with the
    # user-chosen seed (insp_single_seed) so the draw is independent and
    # reproducible per click.  APPEND to st.session_state['single_runs'] so
    # repeated clicks accumulate overlays.
    try:
        cad_s, _ws = runner.load_cadence_library_uncached()
        cadence_lib_s = [np.asarray(c, dtype=float) for c in cad_s]
    except Exception as exc:
        st.error(f'Cannot load cadence library for single run: {exc}')
    else:
        single_seed = int(st.session_state.insp_single_seed)
        single_result = runner.run_mock_pipeline(
            sigma_single=float(st.session_state.insp_sigma_single),
            sigma_meas=float(st.session_state.insp_sigma_meas),
            f_bin=float(st.session_state.insp_f_bin),
            pi=float(st.session_state.insp_pi),
            true_logPmax=float(st.session_state.insp_logPmax),
            error_model=str(st.session_state.insp_error_model),
            n_iterations=1,
            seed_base=single_seed,
            cadence_library=cadence_lib_s,
            progress_cb=None,
        )
        new_run = {
            'delta_rv':  np.asarray(single_result['delta_rv'][0],
                                    dtype=float),
            'is_binary': np.asarray(single_result['is_binary'][0],
                                    dtype=bool),
            'seed':      single_seed,
        }
        st.session_state.setdefault('single_runs', []).append(new_run)


result_mock = st.session_state.get(_RESULT_KEY_MOCK)
result_exp  = st.session_state.get(_RESULT_KEY_EXP)

if result_mock is None or result_exp is None:
    st.info('Set parameters above and click **Run ▶** to compute and compare.')
    st.stop()


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline-method captions (shown in footer below the plots)
# ─────────────────────────────────────────────────────────────────────────────

_MOCK_CAPTION = (
    'Mock Data uses rng.choice(N, n_bin) — picks n_bin distinct '
    'binary-star indices in one shot.  Both pipelines yield without-'
    'replacement subsets of size n_bin = round(N × f_bin), but the EXACT '
    'index sets differ for the same seed because they consume RNG draws '
    'differently.'
)
_EXPLORER_CAPTION = (
    'Model Explorer uses rng.permutation(N)[:n_bin] — generates a full '
    'random permutation and takes the first n_bin entries.  Both pipelines '
    'yield without-replacement subsets of size n_bin = round(N × f_bin), '
    'but the EXACT index sets differ for the same seed because they '
    'consume RNG draws differently.'
)


# ─────────────────────────────────────────────────────────────────────────────
# Top header strip — n_binaries summary shared by both pipelines
# ─────────────────────────────────────────────────────────────────────────────

n_bin_mock = np.asarray(
    result_mock.get('n_binaries_per_iter', np.array([0])), dtype=float)
n_bin_exp = np.asarray(
    result_exp.get('n_binaries_per_iter', np.array([0])), dtype=float)
st.caption(
    f'**Mock** ({result_mock.get("binary_index_method", "?")}): '
    f'n_binaries / iter = mean {n_bin_mock.mean():.2f}, '
    f'std {n_bin_mock.std():.3f}.  '
    f'**Explorer** ({result_exp.get("binary_index_method", "?")}): '
    f'n_binaries / iter = mean {n_bin_exp.mean():.2f}, '
    f'std {n_bin_exp.std():.3f}.  '
    f'Both should equal round(N × f_bin) deterministically.'
)


# ─────────────────────────────────────────────────────────────────────────────
# Row 1 — ΔRV CDF overlay (left) | Detected-fraction-vs-threshold overlay (right)
# ─────────────────────────────────────────────────────────────────────────────

st.markdown('---')
_bcol1, _bcol2, _bcol3 = st.columns([1, 3, 1])
with _bcol1:
    st.number_input(
        'Std band bins',
        value=int(_load('insp_band_bins')),
        step=50,
        key='insp_band_bins',
        on_change=_save_widget, args=('insp_band_bins',),
        help='Number of x-axis points used for the 16-84%% std band on both '
             'CDF and f_bin panels. Higher = finer x resolution; lower = '
             'coarser plateau averaging. Try 100, 500, 2000, 5000.',
    )

cdf_col, fbin_col = st.columns([1, 1])

# Accumulated single-run overlays (list of dicts).  Empty list = no overlay.
_single_runs = st.session_state.get('single_runs', []) or []
_n_runs = len(_single_runs)
_seed_strs = [str(r.get('seed', '?')) for r in _single_runs]

with cdf_col:
    fig_cdf = inspector.make_drv_cdf_overlay_figure(
        mock_simulated_drv=result_mock['delta_rv'],
        explorer_simulated_drv=result_exp['delta_rv'],
        title='ΔRV CDF: Mock vs Explorer',
        single_runs=_single_runs,
        n_band_bins=int(st.session_state.insp_band_bins),
    )
    st.plotly_chart(fig_cdf, use_container_width=True, theme=None)
    _single_caption_extra = (
        f'  {_n_runs} single-run draw(s) overlaid '
        f'(seeds: {", ".join(_seed_strs)}).  '
        'Black step lines = ECDFs; red/green dots = single/binary stars '
        'across all draws.'
        if _n_runs > 0 else ''
    )
    st.caption(
        'Pooled simulated ΔRV CDF for the two pipelines (Mock blue, '
        'Explorer red), each shown as smooth pooled CDF + 16-84% '
        'percentile band from bc.helpers.smooth_pooled_cdf.'
        + _single_caption_extra
    )

with fbin_col:
    fig_fbin = inspector.make_fbin_vs_threshold_overlay_figure(
        mock_simulated_drv=result_mock['delta_rv'],
        explorer_simulated_drv=result_exp['delta_rv'],
        title='Detected binary fraction vs threshold',
        single_runs=_single_runs,
        n_band_bins=int(st.session_state.insp_band_bins),
    )
    st.plotly_chart(fig_fbin, use_container_width=True, theme=None)
    _single_caption_extra_fbin = (
        f'  {_n_runs} single-run draw(s) overlaid '
        f'(seeds: {", ".join(_seed_strs)}).  '
        'Black step lines = single-iteration survival curves; red/green '
        'dots = single/binary stars across all draws.'
        if _n_runs > 0 else ''
    )
    st.caption(
        'Mean fraction of stars with peak-to-peak ΔRV above each threshold, '
        'across all Monte-Carlo iterations (Mock blue, Explorer red).  '
        'Vertical dashed line at the project binary-detection threshold '
        '(45.5 km s⁻¹).'
        + _single_caption_extra_fbin
    )


# ─────────────────────────────────────────────────────────────────────────────
# Row 2 — Full-width 3x3 orbital histograms grid (overlaid)
# ─────────────────────────────────────────────────────────────────────────────

st.markdown('### Binary orbital properties (Mock vs Explorer overlaid)')
fig_3x3 = inspector.make_3x3_orbital_grid(
    mock_dict=result_mock,
    explorer_dict=result_exp,
    title='',
)
st.plotly_chart(fig_3x3, use_container_width=True, theme=None)
st.caption(
    'Orbital parameter distributions of simulated binaries from each '
    'pipeline (Mock blue, Explorer red).  Bins are shared per panel so the '
    'overlay is comparable bar-for-bar.  Both pipelines invoke the same '
    'inner samplers — the panels should be near-identical for matched '
    'random seeds.'
)


# ─────────────────────────────────────────────────────────────────────────────
# Row 3 — Summary tables side by side
# ─────────────────────────────────────────────────────────────────────────────

tbl_mock_col, tbl_exp_col = st.columns([1, 1])
with tbl_mock_col:
    st.markdown('**Mock Data — summary statistics**')
    st.dataframe(
        inspector.make_summary_table(result_mock),
        hide_index=True, use_container_width=True,
    )
with tbl_exp_col:
    st.markdown('**Model Explorer — summary statistics**')
    st.dataframe(
        inspector.make_summary_table(result_exp),
        hide_index=True, use_container_width=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline-method explanation captions
# ─────────────────────────────────────────────────────────────────────────────

st.divider()
exp_mock_col, exp_exp_col = st.columns([1, 1])
with exp_mock_col:
    st.caption(f'**Mock Data path.** {_MOCK_CAPTION}')
with exp_exp_col:
    st.caption(f'**Model Explorer path.** {_EXPLORER_CAPTION}')


# Footer
st.divider()
t_mock = float(st.session_state.get('insp_t_mock', 0.0))
t_exp  = float(st.session_state.get('insp_t_exp',  0.0))
st.caption(
    f'Last compute:  Mock = {t_mock:.2f} s,  Explorer = {t_exp:.2f} s,  '
    f'N_iter = {int(st.session_state.insp_n_iter)},  '
    f'seed_base = {int(st.session_state.insp_seed_base)}.'
)
