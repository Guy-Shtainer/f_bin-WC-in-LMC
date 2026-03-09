"""
nres_ccf_worker.py — Multiprocessing worker functions for NRES CCF analysis.
Separate module so multiprocessing.Pool can pickle them (E022: Streamlit pages
run as __main__, making their functions unpicklable).
"""
from __future__ import annotations
import os, sys, re, shutil
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import numpy as np
import matplotlib
matplotlib.use('Agg')

from CCF import CCFclass


def _process_single_line(args):
    """Worker: run double_ccf for one (star, line) combo. Top-level for pickling."""
    (star_name, line_name, lam_min, lam_max, fit_frac,
     obs_data_list, obs_meta, common_wavegrid, tpl_f,
     cross_velo, save_plots, run_ts, enabled_epochs) = args

    # Filter obs to enabled epochs for this line
    filtered = [(i, od) for i, od in enumerate(obs_data_list)
                if obs_meta[i][0] in enabled_epochs]
    if len(filtered) < 2:
        return star_name, line_name, [], []

    filtered_indices = [i for i, _ in filtered]
    filtered_obs_data = [od for _, od in filtered]

    ccf = CCFclass(
        PlotAll=False,
        CrossVeloMin=-cross_velo,
        CrossVeloMax=cross_velo,
        Fit_Range_in_fraction=fit_frac,
        CrossCorRangeA=[[lam_min, lam_max]],
        star_name=star_name,
        epoch=0,
        line_tag=line_name,
        nm=False,
    )

    try:
        r1, r2, (co_wave, co_flux), failed_idx, ew_meta = ccf.double_ccf(
            filtered_obs_data, common_wavegrid, tpl_f,
            return_coadd=True, return_meta=True,
        )
    except Exception:
        return star_name, line_name, [], []

    results = []
    plot_args = []

    for j, ((ep_j, w_j, f_j), (rv, rv_err)) in enumerate(zip(filtered_obs_data, r2)):
        orig_idx = filtered_indices[j]
        ep_num, sp_num = obs_meta[orig_idx]
        ew_info = ew_meta[j] if j < len(ew_meta) else {}
        results.append({
            'Epoch': ep_num, 'Spectra': sp_num,
            'Line': line_name,
            'RV (km/s)': rv, 'RV_err (km/s)': rv_err,
            'EW': ew_info.get('EW'),
            'Detected': bool(ew_info.get('detected', False)),
        })

        if save_plots and co_wave is not None:
            plot_args.append((
                star_name, ep_num, sp_num, w_j, f_j,
                co_wave, co_flux, cross_velo,
                fit_frac, lam_min, lam_max, line_name, run_ts,
            ))

    return star_name, line_name, results, plot_args


def _save_single_plot(args):
    """Worker for parallel plot saving — NRES folder structure: {line_tag}/epoch{ep}/."""
    (star_name, ep, sp_num, w, f, co_wave, co_flux, cross_velo,
     fit_frac, lam_min, lam_max, line_name, run_ts) = args
    try:
        ccf_plot = CCFclass(
            PlotAll=False,
            CrossVeloMin=-cross_velo,
            CrossVeloMax=cross_velo,
            Fit_Range_in_fraction=fit_frac,
            CrossCorRangeA=[[lam_min, lam_max]],
            star_name=star_name,
            epoch=ep,
            spectrum=sp_num,
            line_tag=line_name,
            savePlot=True,
            run_ts=run_ts,
            nm=False,
        )
        if co_wave is not None:
            ccf_plot.compute_RV(w, f, co_wave, co_flux, clean=False)

        clean_star = re.sub(r'[^A-Za-z0-9_-]', '_', star_name)
        src_dir = Path('../output') / clean_star / 'CCF' / run_ts / line_name
        if src_dir.is_dir():
            epoch_dir = src_dir / f'epoch{ep}'
            epoch_dir.mkdir(parents=True, exist_ok=True)
            for fpath in src_dir.glob(f'{clean_star}_MJD{ep}_S{sp_num}*'):
                new_name = fpath.name.replace(f'_MJD{ep}_S{sp_num}', f'_Spectra{sp_num}')
                shutil.move(str(fpath), str(epoch_dir / new_name))
        return True
    except Exception as e:
        return f'Plot failed ep={ep} sp={sp_num}: {e}'
