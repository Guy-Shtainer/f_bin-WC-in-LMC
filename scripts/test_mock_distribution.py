"""Test that the validation tool's mock-RV generator pulls from the
distributions configured by the slider parameters.

A parallel Claude session claimed the mock data is sampled from a different
distribution than the user's slider settings. This script gives an objective
answer with numbers behind it by exercising
``app.bc.validation.generate_mock_observations_detail`` and checking the
documented two-source observational model:

- Singles : v_obs = N(0, sigma_single) + noise(error_model, sigma_meas)
- Binaries: v_obs = Kepler(...) + noise(error_model_binary, sigma_meas_binary)
- n_bin   = round(N * f_bin)  (deterministic)

So when error_model='fixed' and sigma_meas=0, singles must follow
N(0, sigma_single) exactly. When error_model='fixed' and sigma_meas>0, singles
must follow N(0, sqrt(sigma_single**2 + sigma_meas**2)) (Gaussian convolution).

Usage:
    conda run -n guyenv python scripts/test_mock_distribution.py

Exit code 0 on all-pass, 1 on any failure.
"""
from __future__ import annotations

import os
import sys
import unittest.mock as mock

import numpy as np
import scipy.stats as sst

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, 'app'))


# Mock Streamlit before any bc.* imports — st.cache_data / st.cache_resource
# decorators must behave as identity so the validation module imports cleanly
# outside the Streamlit runtime. (Same pattern as
# scripts/test_explorer_mock_equal.py:24-38.)
st_mock = mock.MagicMock()
st_mock.session_state = {}


def _cache_data_mock(func=None, **kwargs):
    if func is not None:
        return func
    return lambda f: f


st_mock.cache_data = _cache_data_mock
st_mock.cache_resource = _cache_data_mock
sys.modules['streamlit'] = st_mock

from bc.validation import generate_mock_observations_detail  # noqa: E402
from wr_bias_simulation import BinaryParameterConfig  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _synthetic_cadence(n_stars: int, n_ep_per_star: int, rng_seed: int):
    """Return a list of ``n_stars`` MJD-like time arrays of length n_ep_per_star."""
    rng = np.random.default_rng(rng_seed)
    cad = []
    for _ in range(n_stars):
        t = np.sort(rng.uniform(58000.0, 58365.0, size=n_ep_per_star))
        cad.append(t)
    return cad


def _make_bin_cfg(logPmax: float = 4.0) -> BinaryParameterConfig:
    return BinaryParameterConfig(
        logP_min=0.15, logP_max=logPmax,
        period_model='powerlaw', e_model='flat', e_max=0.9,
    )


def _pool_single_rvs(detail: dict) -> np.ndarray:
    """Concatenate per-epoch RVs across all SINGLE stars in a mock detail dict."""
    is_bin = np.asarray(detail['is_binary'], dtype=bool)
    rvs_per_star = detail['rvs_per_star']
    parts = []
    for k, isb in enumerate(is_bin):
        if not bool(isb):
            arr = np.asarray(rvs_per_star[k], dtype=float)
            if arr.size > 0:
                parts.append(arr)
    if not parts:
        return np.array([], dtype=float)
    return np.concatenate(parts)


def _gen(
    f_bin: float, sigma_single: float, sigma_meas: float,
    error_model: str = 'fixed', error_params: tuple = (),
    n_stars: int = 5000, n_ep: int = 50, seed: int = 42,
) -> dict:
    cad = _synthetic_cadence(n_stars=n_stars, n_ep_per_star=n_ep,
                             rng_seed=seed + 1000)
    bin_cfg = _make_bin_cfg()
    return generate_mock_observations_detail(
        true_fbin=f_bin, true_pi=0.0, true_sigma=sigma_single,
        true_logPmax=4.0, cadence_library=cad, cadence_weights=None,
        sigma_meas=sigma_meas, bin_cfg=bin_cfg, period_model='powerlaw',
        seed=seed, error_model=error_model, error_params=error_params,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Cases
# ─────────────────────────────────────────────────────────────────────────────

def case_1() -> tuple[list[tuple[str, bool, str]], dict]:
    """Singles-only, sigma_meas=0 — sweep sigma_single in {5, 15, 30}."""
    rows = []
    failures: dict = {}
    for true_sigma in (5.0, 15.0, 30.0):
        detail = _gen(f_bin=0.0, sigma_single=true_sigma, sigma_meas=0.0,
                      n_stars=5000, n_ep=50, seed=42)
        v = _pool_single_rvs(detail)
        N = v.size
        # Expected: v ~ N(0, true_sigma)
        sample_mean = float(np.mean(v))
        sample_std = float(np.std(v, ddof=1))
        # Mean-zero check: |mean| < 4 * sigma_single / sqrt(N)
        mean_bound = 4.0 * true_sigma / np.sqrt(N)
        mean_ok = abs(sample_mean) < mean_bound
        # Std match within 1%
        rel_err = abs(sample_std / true_sigma - 1.0)
        std_ok = rel_err < 0.01
        # KS test
        ks_p = float(sst.kstest(v, 'norm', args=(0.0, true_sigma)).pvalue)
        ks_ok = ks_p > 0.001
        passed = bool(mean_ok and std_ok and ks_ok)
        label = f'1{"abc"[(int(true_sigma) // 5 - 1) // 2 if true_sigma != 30 else 2]}.'
        # simpler labelling
        if true_sigma == 5.0:
            tag = '1a'
        elif true_sigma == 15.0:
            tag = '1b'
        else:
            tag = '1c'
        detail_str = (
            f'sigma_hat = {sample_std:.3f} (input {true_sigma:.1f}, '
            f'rel err {rel_err*100:.2f}%), KS p = {ks_p:.2g}, '
            f'mean = {sample_mean:+.3f} (bound +-{mean_bound:.3f})'
        )
        rows.append((f'{tag}. sigma_meas=0, sigma_single={int(true_sigma)}',
                     passed, detail_str))
        if not passed:
            failures[tag] = {
                'true_sigma': true_sigma, 'sample_std': sample_std,
                'sample_mean': sample_mean, 'ks_p': ks_p,
                'mean_ok': mean_ok, 'std_ok': std_ok, 'ks_ok': ks_ok,
            }
    return rows, failures


def case_2() -> tuple[tuple[str, bool, str], dict]:
    """Singles-only, sigma_meas=5, fixed model. Pooled sigma should equal
    sqrt(15**2 + 5**2) = 15.811388…"""
    sigma_single = 15.0
    sigma_meas = 5.0
    expected = float(np.sqrt(sigma_single**2 + sigma_meas**2))
    detail = _gen(f_bin=0.0, sigma_single=sigma_single, sigma_meas=sigma_meas,
                  n_stars=5000, n_ep=50, seed=42)
    v = _pool_single_rvs(detail)
    N = v.size
    sample_mean = float(np.mean(v))
    sample_std = float(np.std(v, ddof=1))
    mean_bound = 4.0 * expected / np.sqrt(N)
    mean_ok = abs(sample_mean) < mean_bound
    rel_err = abs(sample_std / expected - 1.0)
    std_ok = rel_err < 0.01
    ks_p = float(sst.kstest(v, 'norm', args=(0.0, expected)).pvalue)
    ks_ok = ks_p > 0.001
    passed = bool(mean_ok and std_ok and ks_ok)
    detail_str = (
        f'sigma_hat = {sample_std:.3f} (expect {expected:.3f}, '
        f'rel err {rel_err*100:.2f}%), KS p = {ks_p:.2g}'
    )
    failures: dict = {}
    if not passed:
        # Diagnose: does sigma_hat match sigma_single (no noise) or sigma_meas
        # (sigma_single ignored) instead?
        diag = []
        if abs(sample_std - sigma_single) < 0.05 * sigma_single:
            diag.append(
                'sigma_hat matches sigma_single — noise NOT being added '
                '(suspect _draw_measurement_noise call missing or '
                'sigma_meas=0 hardcoded near validation.py:248)'
            )
        if abs(sample_std - sigma_meas) < 0.05 * sigma_meas:
            diag.append(
                'sigma_hat matches sigma_meas — sigma_single intrinsic '
                'scatter NOT being added (suspect rng.normal call '
                'missing/zeroed near validation.py:244)'
            )
        failures['2'] = {
            'expected': expected, 'sample_std': sample_std,
            'sample_mean': sample_mean, 'ks_p': ks_p,
            'diagnostic': '; '.join(diag) if diag else
                          'unknown — neither sigma_single nor sigma_meas alone',
        }
    return ('2.  sigma_meas=5,  sigma_single=15', passed, detail_str), failures


def case_3() -> tuple[tuple[str, bool, str], dict]:
    """Deterministic n_bin = round(N * f_bin)."""
    N = 100
    f_bin_vals = (0.0, 0.05, 0.25, 0.46, 0.5, 0.75, 1.0)
    misses = []
    for fb in f_bin_vals:
        detail = _gen(f_bin=fb, sigma_single=15.0, sigma_meas=2.0,
                      n_stars=N, n_ep=5, seed=42)
        is_bin = np.asarray(detail['is_binary'], dtype=bool)
        got = int(is_bin.sum())
        want = int(round(N * fb))
        if got != want:
            misses.append((fb, got, want))
    n_total = len(f_bin_vals)
    n_pass = n_total - len(misses)
    passed = len(misses) == 0
    if passed:
        detail_str = f'{n_pass}/{n_total} fbin values exact'
    else:
        detail_str = (
            f'{n_pass}/{n_total} exact; misses: ' +
            ', '.join(f'fb={fb} got={g} want={w}' for fb, g, w in misses)
        )
    failures: dict = {}
    if not passed:
        failures['3'] = {'misses': misses}
    return ('3.  n_bin = round(N*f_bin)', passed, detail_str), failures


def case_4() -> tuple[tuple[str, bool, str], dict]:
    """f_bin=1: every star binary → no single RV arrays populated.
    f_bin=0: every star single → no binary RV arrays populated.
    """
    N = 200

    # f_bin=1.0 — all should be binary; any star with is_binary[k]==False
    # should have rvs_per_star[k] empty. Should be vacuous.
    d_all = _gen(f_bin=1.0, sigma_single=15.0, sigma_meas=2.0,
                 n_stars=N, n_ep=5, seed=42)
    is_bin1 = np.asarray(d_all['is_binary'], dtype=bool)
    rvs1 = d_all['rvs_per_star']
    bad1 = []
    for k in range(N):
        if not bool(is_bin1[k]) and np.asarray(rvs1[k]).size > 0:
            bad1.append(k)
    cond_a = (int(is_bin1.sum()) == N) and (len(bad1) == 0)

    # f_bin=0.0 — all should be single; any star with is_binary[k]==True
    # should have rvs_per_star[k] empty. Should be vacuous.
    d_none = _gen(f_bin=0.0, sigma_single=15.0, sigma_meas=2.0,
                  n_stars=N, n_ep=5, seed=42)
    is_bin0 = np.asarray(d_none['is_binary'], dtype=bool)
    rvs0 = d_none['rvs_per_star']
    bad0 = []
    for k in range(N):
        if bool(is_bin0[k]) and np.asarray(rvs0[k]).size > 0:
            bad0.append(k)
    cond_b = (int(is_bin0.sum()) == 0) and (len(bad0) == 0)

    passed = bool(cond_a and cond_b)
    detail_str = (
        f'fbin=1: {int(is_bin1.sum())}/{N} binary, '
        f'mismatched-singles={len(bad1)}; '
        f'fbin=0: {int(is_bin0.sum())}/{N} binary, '
        f'mismatched-binaries={len(bad0)}'
    )
    failures: dict = {}
    if not passed:
        failures['4'] = {
            'fbin1_n_binary': int(is_bin1.sum()),
            'fbin1_mismatched_singles': bad1[:10],
            'fbin0_n_binary': int(is_bin0.sum()),
            'fbin0_mismatched_binaries': bad0[:10],
        }
    return ('4.  f_bin extremes RV dispatch', passed, detail_str), failures


def case_5() -> tuple[tuple[str, bool, str], dict]:
    """Distribution-shape sensitivity: Fixed vs Log-normal must produce
    statistically different pooled-RV distributions.

    For scipy.stats.lognorm the standard signature is lognorm.rvs(s, loc, scale).
    With s=0.5 and scale = sigma_meas/exp(0.5**2/2), the *mean* magnitude
    equals sigma_meas. The KS test on the pooled (signed-noise + intrinsic
    scatter) RVs should detect the shape difference.
    """
    sigma_single = 15.0
    sigma_meas = 10.0
    s = 0.5
    scale = sigma_meas / np.exp(s ** 2 / 2.0)
    # _draw_measurement_noise calls: dist.rvs(*params, size=size)
    # so for lognorm we pass (s, loc, scale).
    err_params = (s, 0.0, scale)

    d_fixed = _gen(f_bin=0.0, sigma_single=sigma_single, sigma_meas=sigma_meas,
                   error_model='fixed', error_params=(),
                   n_stars=5000, n_ep=50, seed=42)
    d_logn = _gen(f_bin=0.0, sigma_single=sigma_single, sigma_meas=sigma_meas,
                  error_model='Log-normal', error_params=err_params,
                  n_stars=5000, n_ep=50, seed=43)
    v_fixed = _pool_single_rvs(d_fixed)
    v_logn = _pool_single_rvs(d_logn)
    ks = sst.ks_2samp(v_fixed, v_logn)
    ks_p = float(ks.pvalue)
    passed = ks_p < 0.01
    detail_str = (
        f'KS p = {ks_p:.2g} (Nfix={v_fixed.size}, Nlog={v_logn.size}, '
        f'std_fix={np.std(v_fixed, ddof=1):.3f}, '
        f'std_log={np.std(v_logn, ddof=1):.3f})'
    )
    failures: dict = {}
    if not passed:
        failures['5'] = {
            'ks_p': ks_p,
            'std_fixed': float(np.std(v_fixed, ddof=1)),
            'std_lognormal': float(np.std(v_logn, ddof=1)),
            'diagnostic': (
                'Fixed and Log-normal pooled CDFs are indistinguishable — '
                'error_model parameter likely ignored '
                '(suspect _draw_measurement_noise dispatch at '
                'validation.py:248 / wr_bias_simulation.py:101).'
            ),
        }
    return ('5.  Fixed vs Log-normal differ', passed, detail_str), failures


# ─────────────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    print('='*72)
    print('Mock-distribution sanity test — '
          'app/bc/validation.py::generate_mock_observations_detail')
    print('='*72)

    rows: list[tuple[str, bool, str]] = []
    all_failures: dict = {}

    print('\n[Case 1] Singles-only, sigma_meas=0, sweep sigma_single ...')
    r1, f1 = case_1()
    rows.extend(r1)
    all_failures.update(f1)

    print('[Case 2] Singles-only, sigma_meas=5, sigma_single=15 ...')
    r2, f2 = case_2()
    rows.append(r2)
    all_failures.update(f2)

    print('[Case 3] Deterministic n_bin = round(N*f_bin) ...')
    r3, f3 = case_3()
    rows.append(r3)
    all_failures.update(f3)

    print('[Case 4] f_bin extremes — RV dispatch ...')
    r4, f4 = case_4()
    rows.append(r4)
    all_failures.update(f4)

    print('[Case 5] Fixed vs Log-normal distribution shape ...')
    r5, f5 = case_5()
    rows.append(r5)
    all_failures.update(f5)

    # ──────────────── results table ────────────────
    print('\n' + '─'*72)
    print(f'{"Case":<32} | {"Status":^6} | Detail')
    print('─'*72)
    for label, ok, detail in rows:
        status = '  OK  ' if ok else ' FAIL '
        print(f'{label:<32} | {status:^6} | {detail}')
    print('─'*72)

    n_pass = sum(1 for _, ok, _ in rows if ok)
    n_total = len(rows)
    print(f'\n{n_pass}/{n_total} checks passed.')

    if all_failures:
        print('\nFailure diagnostics:')
        for tag, info in all_failures.items():
            print(f'  Case {tag}: {info}')
        # Pick the most likely suspect line
        hint = ''
        if '2' in all_failures and all_failures['2'].get('diagnostic'):
            hint = ' — ' + all_failures['2']['diagnostic']
        elif '5' in all_failures:
            hint = ' — error_model dispatch broken (validation.py:248)'
        elif '3' in all_failures:
            hint = ' — non-deterministic n_bin (validation.py:222)'
        elif '1a' in all_failures or '1b' in all_failures or '1c' in all_failures:
            hint = (' — singles intrinsic scatter wrong '
                    '(suspect rng.normal scale at validation.py:244)')
        print(f'\nVERDICT: parallel-Claude claim CONFIRMED — '
              f'see failures above{hint}')
        return 1

    print('\nVERDICT: parallel-Claude claim REFUTED — '
          'mock distribution matches slider parameters across all 5 cases.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
