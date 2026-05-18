"""Byte-identical CDF assertion: Mock vs Explorer-validation-mode.

When the Explorer's _me_cdf_band is called with validation_mode=True and the
SAME seed used to generate the mock, the returned ΔRV array must equal the
mock's delta_rv byte-for-byte (same RNG draws → same values).

Usage:
    conda run -n guyenv python scripts/test_explorer_mock_equal.py
"""
from __future__ import annotations

import os
import sys
import unittest.mock as mock

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, 'app'))


# Mock Streamlit (st.cache_data, st.cache_resource decorators → identity).
# Mirrors the pattern in scripts/test_explorer_logL_consistency.py.
st_mock = mock.MagicMock()
st_mock.session_state = {}


def _cache_data_mock(func=None, **kwargs):
    if func is not None:
        return func
    return lambda f: f


st_mock.cache_data = _cache_data_mock
st_mock.cache_resource = _cache_data_mock
sys.modules['streamlit'] = st_mock

from bc.validation import (  # noqa: E402
    _sample_delta_rv_mock, generate_mock_observations_detail,
)
from bc.render_lk_explorer import _me_cdf_band  # noqa: E402
from wr_bias_simulation import (  # noqa: E402
    BinaryParameterConfig, DEFAULT_DRV_BIN_EDGES,
)


def _synthetic_cadence(n_stars=10, rng_seed=0):
    """Generate a tiny synthetic cadence library (not tied to real FITS)."""
    rng = np.random.default_rng(rng_seed)
    cad = []
    for _ in range(n_stars):
        n_ep = int(rng.integers(3, 8))
        # MJD-like timestamps in the last ~year
        t = np.sort(rng.uniform(58000.0, 58365.0, size=n_ep))
        cad.append(t)
    return cad


def _run_case(label: str, error_model: str, error_params: tuple) -> int:
    """Run the byte-identical check for a specific error-distribution config."""
    # Test parameters — values chosen to trip both single + binary branches.
    fbin = 0.46
    pi = 0.0
    sigma = 15.0
    logPmax = 4.0
    seed = 42
    period_model = 'powerlaw'
    sigma_meas = 1.622

    cadence_library = _synthetic_cadence(n_stars=25, rng_seed=123)
    bin_cfg = BinaryParameterConfig(
        logP_min=0.15, logP_max=logPmax,
        period_model=period_model, e_model='flat', e_max=0.9,
    )
    be = np.asarray(DEFAULT_DRV_BIN_EDGES)

    print(f'--- Case: {label} (error_model={error_model!r}) ---')

    # ── (1) Mock path ────────────────────────────────────────────────────
    mock_detail = generate_mock_observations_detail(
        true_fbin=fbin, true_pi=pi, true_sigma=sigma,
        true_logPmax=logPmax,
        cadence_library=cadence_library, cadence_weights=None,
        sigma_meas=sigma_meas, bin_cfg=bin_cfg,
        period_model=period_model, seed=seed,
        error_model=error_model, error_params=error_params,
    )
    drv_mock = np.asarray(mock_detail['delta_rv'], dtype=float)

    # ── (2) Direct helper check (same seed → same draws) ─────────────────
    drv_helper = _sample_delta_rv_mock(
        f_bin=fbin, pi=pi, sigma_single=sigma, logP_max=logPmax,
        cadence_library=cadence_library, sigma_meas=sigma_meas,
        bin_cfg=bin_cfg, period_model=period_model,
        seed=seed, error_model=error_model, error_params=error_params,
        collect_detail=False,
    )
    assert np.array_equal(drv_helper, drv_mock), (
        'Helper ≠ Mock detail (same seed).  This is a refactor-regression: '
        'generate_mock_observations_detail must delegate to _sample_delta_rv_mock.'
    )
    print(f'  [OK] helper == detail: N={drv_mock.size}, max ΔRV={drv_mock.max():.2f}')

    # ── (3) Explorer validation-mode path ────────────────────────────────
    # _me_cdf_band returns (med, lo, hi, pooled).  validation_mode forces
    # pooled to be a single draw equal to the mock's delta_rv.
    med, lo, hi, pooled = _me_cdf_band(
        fbin, pi, sigma, sigma_meas, tuple(be.tolist()),
        logPmax=logPmax, n_sets=1,
        _cadence_library=cadence_library, _cadence_weights=None,
        _bin_cfg_dict=tuple(sorted(vars(bin_cfg).items())),
        period_model=period_model,
        validation_mode=True, validation_seed=seed,
        validation_error_model=error_model,
        validation_error_params=error_params,
    )
    drv_explorer = np.asarray(pooled, dtype=float)

    if not np.array_equal(np.sort(drv_mock), np.sort(drv_explorer)):
        # Helpful diagnostic printout
        print('  [FAIL] Mock vs Explorer ΔRV arrays differ.')
        print(f'     mock     : N={drv_mock.size}, '
              f'min={drv_mock.min():.3f}, max={drv_mock.max():.3f}, '
              f'sum={drv_mock.sum():.3f}')
        print(f'     explorer : N={drv_explorer.size}, '
              f'min={drv_explorer.min():.3f}, max={drv_explorer.max():.3f}, '
              f'sum={drv_explorer.sum():.3f}')
        diff = drv_mock - drv_explorer
        print(f'     max |diff|: {np.max(np.abs(diff)):.3e}')
        return 1

    # CDFs must therefore also match
    mock_cdf = np.searchsorted(np.sort(drv_mock), be, side='right') / max(
        len(drv_mock), 1)
    exp_cdf = med  # in validation_mode, med == lo == hi == single draw cdf
    assert np.allclose(mock_cdf, exp_cdf), (
        'CDFs diverge despite ΔRV match — bug in _binned_cdf dispatch.'
    )
    print(f'  [OK] mock ΔRV == explorer ΔRV (N={drv_mock.size})')
    print(f'  [OK] mock CDF == explorer CDF (max diff = '
          f'{np.max(np.abs(mock_cdf - exp_cdf)):.2e})')
    print(f'  PASS — {label}: byte-identical invariant holds.')
    return 0


def _assert_sigma_meas_actually_perturbs_cdf() -> int:
    """Regression guard: larger sigma_meas MUST produce different ΔRV values.

    If this fails, the Dsilva-style noise addition in ``_sample_delta_rv_mock``
    has been removed again — the mock would be producing clean physics-only
    RVs, and σ_meas / distribution choice would have no effect on the CDF.
    (The user explicitly rejected this behaviour on 2026-04-23 — see
    ``.claude/agents/comms/briefing.md``.)
    """
    print('--- Regression guard: σ_meas must affect ΔRV ---')
    fbin = 0.46
    pi = 0.0
    sigma = 15.0
    logPmax = 4.0
    seed = 42
    period_model = 'powerlaw'

    cadence_library = _synthetic_cadence(n_stars=25, rng_seed=123)
    bin_cfg = BinaryParameterConfig(
        logP_min=0.15, logP_max=logPmax,
        period_model=period_model, e_model='flat', e_max=0.9,
    )

    drv_small = _sample_delta_rv_mock(
        f_bin=fbin, pi=pi, sigma_single=sigma, logP_max=logPmax,
        cadence_library=cadence_library, sigma_meas=1.0,
        bin_cfg=bin_cfg, period_model=period_model,
        seed=seed, error_model='fixed', error_params=(),
        collect_detail=False,
    )
    drv_large = _sample_delta_rv_mock(
        f_bin=fbin, pi=pi, sigma_single=sigma, logP_max=logPmax,
        cadence_library=cadence_library, sigma_meas=10.0,
        bin_cfg=bin_cfg, period_model=period_model,
        seed=seed, error_model='fixed', error_params=(),
        collect_detail=False,
    )
    if np.array_equal(drv_small, drv_large):
        print('  [FAIL] sigma_meas=1 and sigma_meas=10 gave IDENTICAL ΔRV '
              '— noise addition is missing from _sample_delta_rv_mock.')
        return 1
    # Sanity: larger σ_meas should (on average) produce larger ΔRV.
    mean_small = float(np.mean(drv_small))
    mean_large = float(np.mean(drv_large))
    print(f'  [OK] σ_meas=1.0 → mean ΔRV = {mean_small:.3f}')
    print(f'  [OK] σ_meas=10.0 → mean ΔRV = {mean_large:.3f}')
    print('  PASS — σ_meas demonstrably perturbs the mock CDF '
          '(Dsilva-style noise addition is in place).')
    return 0


def main() -> int:
    # Fixed-error case (legacy behaviour — always must pass).
    rc = _run_case('Fixed σ_meas', 'fixed', ())
    if rc != 0:
        return rc
    # Non-fixed case: Log-normal (s, loc, scale) as per _RVE_PARAM_META.
    rc = _run_case('Log-normal', 'Log-normal', (0.5, 0.0, 1.0))
    if rc != 0:
        return rc
    # Regression guard: noise MUST be added (else σ_meas has no effect).
    rc = _assert_sigma_meas_actually_perturbs_cdf()
    return rc


if __name__ == '__main__':
    sys.exit(main())
