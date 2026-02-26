"""
pipeline/dsilva_grid.py
───────────────────────
Dsilva-style power-law period grid search:
    scan (f_bin, π) grid → K-S test vs observed ΔRV distribution.

Usage
-----
    python pipeline/dsilva_grid.py                   # full run
    python pipeline/dsilva_grid.py --load-cached     # skip grid, replot from .npz
    python pipeline/dsilva_grid.py --n-proc 8        # override core count
    python pipeline/dsilva_grid.py --line "He II 4686"

Output
------
    results/dsilva_result.npz   (grid arrays + embedded settings + config_hash)
    plots/dsilva_ks_pvalue.png
    plots/dsilva_ks_D.png
    plots/dsilva_best_cdf.png
    plots/dsilva_fbin_slice.png
    settings/run_history.json   (appended)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

# ── Path fix: allow running from pipeline/ or from project root ───────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from wr_bias_simulation import (
    SimulationConfig,
    BinaryParameterConfig,
    run_bias_grid,
)
from pipeline.load_observations import load_observed_delta_rvs, load_cadence_library
from ObservationClass import ObservationManager


# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────
_SETTINGS_PATH    = os.path.join(_ROOT, 'settings', 'user_settings.json')
_RESULT_PATH      = os.path.join(_ROOT, 'results',  'dsilva_result.npz')
_RUN_HISTORY_PATH = os.path.join(_ROOT, 'settings', 'run_history.json')
_PLOTS_DIR        = os.path.join(_ROOT, 'plots')


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _load_settings() -> dict:
    if os.path.exists(_SETTINGS_PATH):
        with open(_SETTINGS_PATH) as f:
            return json.load(f)
    return {}


def _make_obs(settings: dict) -> ObservationManager:
    return ObservationManager(
        data_dir   = os.path.join(_ROOT, 'Data/'),
        backup_dir = os.path.join(_ROOT, 'Backups/'),
    )


def _config_hash(cfg: dict) -> str:
    """Stable SHA-256 hex digest of the grid config dict."""
    serialised = json.dumps(cfg, sort_keys=True, default=str)
    return hashlib.sha256(serialised.encode()).hexdigest()[:16]


def _build_grid_config(settings: dict, line: str | None, n_proc: int | None) -> dict:
    """Extract the subset of settings that define a unique grid run."""
    g   = settings.get('grid_dsilva', {})
    cls = settings.get('classification', {})
    sim = settings.get('simulation', {})
    return {
        'model':          'dsilva_powerlaw',
        'primary_line':   line or settings.get('primary_line', 'C IV 5808-5812'),
        'fbin_min':       g.get('fbin_min',    0.01),
        'fbin_max':       g.get('fbin_max',    0.99),
        'fbin_steps':     g.get('fbin_steps',  137),
        'pi_min':         g.get('pi_min',      -3.0),
        'pi_max':         g.get('pi_max',       3.0),
        'pi_steps':       g.get('pi_steps',    249),
        'logP_min':       g.get('logP_min',     0.15),
        'logP_max':       g.get('logP_max',     5.0),
        'n_stars_sim':    g.get('n_stars_sim', 3000),
        'sigma_single':   sim.get('sigma_single',  5.5),
        'sigma_measure':  sim.get('sigma_measure', 1.622),
        'threshold_dRV':  cls.get('threshold_dRV', 45.5),
        'sigma_factor':   cls.get('sigma_factor',  4.0),
    }


def _n_processes(settings: dict, n_proc_arg: int | None) -> int:
    if n_proc_arg is not None:
        return n_proc_arg
    cfg_val = settings.get('grid_dsilva', {}).get('n_processes')
    if cfg_val:
        return int(cfg_val)
    import os as _os
    cpus = _os.cpu_count() or 2
    return max(1, cpus - 1)


def _append_run_history(entry: dict) -> None:
    history = []
    if os.path.exists(_RUN_HISTORY_PATH):
        try:
            with open(_RUN_HISTORY_PATH) as f:
                history = json.load(f)
        except (json.JSONDecodeError, ValueError):
            history = []
    history.append(entry)
    with open(_RUN_HISTORY_PATH, 'w') as f:
        json.dump(history, f, indent=2, default=str)


# ─────────────────────────────────────────────────────────────────────────────
# Plotting
# ─────────────────────────────────────────────────────────────────────────────

def _make_plots(result: dict, settings: dict, obs_delta_rv: np.ndarray,
                best_fbin: float, best_pi: float,
                best_fbin_idx: int, best_pi_idx: int) -> None:
    """Generate 4 publication-quality plots to plots/dsilva_*.png."""
    os.makedirs(_PLOTS_DIR, exist_ok=True)

    fbin_grid = result['fbin_grid']
    pi_grid   = result['pi_grid']
    # ks_p shape: [n_sigma, n_fbin, n_pi] → squeeze sigma dim (we use single sigma)
    ks_p = np.squeeze(result['ks_p'], axis=0)   # (n_fbin, n_pi)
    ks_D = np.squeeze(result['ks_D'], axis=0)

    cls = settings.get('classification', {})
    bartzakos  = cls.get('bartzakos_binaries',  3)
    total_pop  = cls.get('total_population',    28)
    threshold  = cls.get('threshold_dRV',       45.5)
    n_detected = int(np.sum(obs_delta_rv > threshold))
    frac_str   = f"({n_detected}+{bartzakos})/{total_pop} = {(n_detected+bartzakos)/total_pop*100:.1f}%"

    # ── 1. K-S p-value heatmap ──────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.pcolormesh(pi_grid, fbin_grid, ks_p,
                       norm=mcolors.LogNorm(vmin=max(ks_p.min(), 1e-10), vmax=1.0),
                       cmap='RdBu_r', shading='auto')
    fig.colorbar(im, ax=ax, label='K-S p-value')
    ax.scatter([best_pi], [best_fbin], marker='*', s=200, c='gold',
               edgecolors='black', linewidths=0.8, zorder=5,
               label=f'Best: f_bin={best_fbin:.3f}, π={best_pi:.2f}')
    ax.set_xlabel('π  (period power-law index)', fontsize=13)
    ax.set_ylabel('f_bin  (intrinsic binary fraction)', fontsize=13)
    ax.set_title(f'Dsilva grid — K-S p-value\n'
                 f'Observed binary fraction {frac_str}', fontsize=12)
    ax.legend(fontsize=10)
    plt.tight_layout()
    path1 = os.path.join(_PLOTS_DIR, 'dsilva_ks_pvalue.png')
    fig.savefig(path1, dpi=150)
    plt.close(fig)
    print(f'  Saved: {path1}')

    # ── 2. K-S D-statistic heatmap ──────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.pcolormesh(pi_grid, fbin_grid, ks_D,
                       vmin=0, vmax=ks_D.max(),
                       cmap='viridis_r', shading='auto')
    fig.colorbar(im, ax=ax, label='K-S D-statistic')
    ax.scatter([best_pi], [best_fbin], marker='*', s=200, c='gold',
               edgecolors='black', linewidths=0.8, zorder=5,
               label=f'Best: f_bin={best_fbin:.3f}, π={best_pi:.2f}')
    ax.set_xlabel('π  (period power-law index)', fontsize=13)
    ax.set_ylabel('f_bin  (intrinsic binary fraction)', fontsize=13)
    ax.set_title('Dsilva grid — K-S D-statistic', fontsize=12)
    ax.legend(fontsize=10)
    plt.tight_layout()
    path2 = os.path.join(_PLOTS_DIR, 'dsilva_ks_D.png')
    fig.savefig(path2, dpi=150)
    plt.close(fig)
    print(f'  Saved: {path2}')

    # ── 3. f_bin slice at best π ─────────────────────────────────────────────
    pval_slice = ks_p[:, best_pi_idx]
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(fbin_grid, pval_slice, color='steelblue', linewidth=2)
    ax.axvline(best_fbin, color='tomato', linestyle='--', linewidth=1.5,
               label=f'Best f_bin = {best_fbin:.3f}')
    ax.set_xlabel('f_bin  (intrinsic binary fraction)', fontsize=13)
    ax.set_ylabel('K-S p-value', fontsize=13)
    ax.set_title(f'p-value vs f_bin  (at π = {best_pi:.2f})', fontsize=12)
    ax.set_yscale('log')
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    path3 = os.path.join(_PLOTS_DIR, 'dsilva_fbin_slice.png')
    fig.savefig(path3, dpi=150)
    plt.close(fig)
    print(f'  Saved: {path3}')

    # ── 4. CDF comparison: observed vs best-fit simulated ────────────────────
    # Re-run one simulation at the best point to get the simulated ΔRV sample
    from wr_bias_simulation import simulate_delta_rv_sample

    gcfg  = settings.get('grid_dsilva', {})
    scfg  = settings.get('simulation',  {})
    sim_cfg = SimulationConfig(
        n_stars       = int(gcfg.get('n_stars_sim', 3000)),
        sigma_single  = float(scfg.get('sigma_single',  5.5)),
        sigma_measure = float(scfg.get('sigma_measure', 1.622)),
    )
    bin_cfg = BinaryParameterConfig(
        logP_min     = float(gcfg.get('logP_min', 0.15)),
        logP_max     = float(gcfg.get('logP_max', 5.0)),
        period_model = 'powerlaw',
        e_model      = 'flat',
    )
    rng = np.random.default_rng(seed=42)
    sim_drv = simulate_delta_rv_sample(best_fbin, best_pi, sim_cfg, bin_cfg, rng)

    obs_sorted = np.sort(obs_delta_rv)
    sim_sorted = np.sort(sim_drv)
    obs_cdf = np.arange(1, len(obs_sorted) + 1) / len(obs_sorted)
    sim_cdf = np.arange(1, len(sim_sorted) + 1) / len(sim_sorted)

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.step(obs_sorted, obs_cdf, where='post', color='tomato',  linewidth=2,
            label=f'Observed  (n={len(obs_sorted)})')
    ax.step(sim_sorted, sim_cdf, where='post', color='steelblue', linewidth=2,
            label=f'Simulated (f_bin={best_fbin:.3f}, π={best_pi:.2f})')
    ax.set_xlabel('ΔRV  (km/s)', fontsize=13)
    ax.set_ylabel('Cumulative fraction', fontsize=13)
    ax.set_title(f'Best-fit CDF comparison\n'
                 f'K-S p-value = {ks_p[best_fbin_idx, best_pi_idx]:.4f}', fontsize=12)
    ax.legend(fontsize=11)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    path4 = os.path.join(_PLOTS_DIR, 'dsilva_best_cdf.png')
    fig.savefig(path4, dpi=150)
    plt.close(fig)
    print(f'  Saved: {path4}')


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Dsilva power-law period grid search for WR binary fraction.')
    parser.add_argument('--load-cached', action='store_true',
                        help='Skip grid computation; replot from existing .npz')
    parser.add_argument('--n-proc', type=int, default=None, metavar='N',
                        help='Number of worker processes (default: cpu_count - 1)')
    parser.add_argument('--line', type=str, default=None,
                        help='Override emission line (default: from settings)')
    args = parser.parse_args()

    # ── Load settings ────────────────────────────────────────────────────────
    settings = _load_settings()
    gcfg     = settings.get('grid_dsilva', {})
    cls_cfg  = settings.get('classification', {})
    sim_cfg_dict = settings.get('simulation', {})

    line    = args.line or settings.get('primary_line', 'C IV 5808-5812')
    n_proc  = _n_processes(settings, args.n_proc)

    grid_config = _build_grid_config(settings, line, n_proc)
    chash       = _config_hash(grid_config)

    print(f'\n{"="*60}')
    print('Dsilva Power-Law Period Grid Search')
    print(f'{"="*60}')
    print(f'  Emission line : {line}')
    print(f'  Grid size     : {grid_config["fbin_steps"]} × {grid_config["pi_steps"]}')
    print(f'  N stars/point : {grid_config["n_stars_sim"]}')
    print(f'  Workers       : {n_proc}')
    print(f'  Config hash   : {chash}')

    # ── Check cached result ──────────────────────────────────────────────────
    result = None
    if os.path.exists(_RESULT_PATH):
        with np.load(_RESULT_PATH, allow_pickle=True) as npz:
            cached_hash = str(npz['config_hash']) if 'config_hash' in npz else None
        if cached_hash == chash:
            print(f'\n  Cached result found with matching config hash.')
            if args.load_cached:
                print('  Loading cached result (--load-cached).')
                result = dict(np.load(_RESULT_PATH, allow_pickle=True))
            else:
                ans = input('  Load cached result? [Y/n] ').strip().lower()
                if ans in ('', 'y', 'yes'):
                    result = dict(np.load(_RESULT_PATH, allow_pickle=True))
                    print('  Loaded from cache.')
                else:
                    print('  Running new grid ...')
        else:
            if args.load_cached:
                print('  WARNING: --load-cached but config hash mismatch — running fresh grid.')
            else:
                print('  Existing result has different config — running new grid.')

    # ── Load observations ────────────────────────────────────────────────────
    obs = _make_obs(settings)
    print('\nLoading observations ...')
    t0 = time.time()
    obs_delta_rv, detail = load_observed_delta_rvs(settings, obs)
    cadence_list, cadence_weights = load_cadence_library(obs)
    print(f'  Done in {time.time()-t0:.1f}s  —  '
          f'{int(np.sum(obs_delta_rv > cls_cfg.get("threshold_dRV", 45.5)))} '
          f'binaries detected in loaded sample')

    # ── Run grid ─────────────────────────────────────────────────────────────
    if result is None:
        fbin_values = np.linspace(gcfg.get('fbin_min', 0.01),
                                  gcfg.get('fbin_max', 0.99),
                                  gcfg.get('fbin_steps', 137))
        pi_values   = np.linspace(gcfg.get('pi_min', -3.0),
                                  gcfg.get('pi_max',  3.0),
                                  gcfg.get('pi_steps', 249))

        sim_cfg = SimulationConfig(
            n_stars        = int(gcfg.get('n_stars_sim', 3000)),
            sigma_single   = float(sim_cfg_dict.get('sigma_single',  5.5)),
            sigma_measure  = float(sim_cfg_dict.get('sigma_measure', 1.622)),
            cadence_library = cadence_list,
            cadence_weights = cadence_weights,
        )
        bin_cfg = BinaryParameterConfig(
            logP_min     = float(gcfg.get('logP_min', 0.15)),
            logP_max     = float(gcfg.get('logP_max', 5.0)),
            period_model = 'powerlaw',
            e_model      = 'flat',
        )

        print(f'\nRunning grid ({len(fbin_values)}×{len(pi_values)} = '
              f'{len(fbin_values)*len(pi_values)} points) ...')
        t1 = time.time()
        result = run_bias_grid(
            fbin_values        = fbin_values,
            pi_values          = pi_values,
            obs_delta_rv       = obs_delta_rv,
            sim_cfg            = sim_cfg,
            bin_cfg            = bin_cfg,
            period_model       = 'powerlaw',
            n_processes        = n_proc,
            use_multiprocessing = True,
        )
        elapsed = time.time() - t1
        print(f'  Grid done in {elapsed:.1f}s')

        # ── Save result ──────────────────────────────────────────────────────
        os.makedirs(os.path.dirname(_RESULT_PATH), exist_ok=True)
        np.savez(
            _RESULT_PATH,
            **result,
            config_hash = chash,
            settings    = np.array(json.dumps(grid_config)),
            obs_delta_rv = obs_delta_rv,
            timestamp   = np.array(datetime.now().isoformat()),
        )
        print(f'  Saved to {_RESULT_PATH}')

        # ── Log to run history ───────────────────────────────────────────────
        _append_run_history({
            'timestamp':   datetime.now().isoformat(),
            'model':       'dsilva_powerlaw',
            'config_hash': chash,
            'config':      grid_config,
            'elapsed_s':   round(elapsed, 1),
            'result_file': _RESULT_PATH,
        })
    else:
        # re-embed obs_delta_rv for plotting
        if 'obs_delta_rv' not in result:
            result['obs_delta_rv'] = obs_delta_rv

    # ── Find best point ───────────────────────────────────────────────────────
    fbin_grid = np.asarray(result['fbin_grid'])
    pi_grid   = np.asarray(result['pi_grid'])
    ks_p      = np.squeeze(np.asarray(result['ks_p']), axis=0)   # (n_fbin, n_pi)

    best_flat      = int(np.argmax(ks_p))
    best_fbin_idx  = best_flat // ks_p.shape[1]
    best_pi_idx    = best_flat  % ks_p.shape[1]
    best_fbin      = float(fbin_grid[best_fbin_idx])
    best_pi        = float(pi_grid[best_pi_idx])
    best_pval      = float(ks_p[best_fbin_idx, best_pi_idx])

    bartzakos = cls_cfg.get('bartzakos_binaries', 3)
    total_pop = cls_cfg.get('total_population',   28)
    threshold = cls_cfg.get('threshold_dRV',      45.5)
    n_detected = int(np.sum(obs_delta_rv > threshold))
    obs_frac   = (n_detected + bartzakos) / total_pop

    print(f'\n{"─"*60}')
    print('RESULT SUMMARY')
    print(f'{"─"*60}')
    print(f'  Best f_bin   : {best_fbin:.4f}')
    print(f'  Best π       : {best_pi:.4f}')
    print(f'  Best K-S p   : {best_pval:.6f}')
    print(f'  Observed fraction: ({n_detected}+{bartzakos})/{total_pop} = {obs_frac*100:.1f}%')
    print(f'{"─"*60}')

    # ── Generate plots ────────────────────────────────────────────────────────
    print('\nGenerating plots ...')
    _make_plots(
        result       = result,
        settings     = settings,
        obs_delta_rv = obs_delta_rv,
        best_fbin    = best_fbin,
        best_pi      = best_pi,
        best_fbin_idx = best_fbin_idx,
        best_pi_idx  = best_pi_idx,
    )
    print('\nDone.')


if __name__ == '__main__':
    main()
