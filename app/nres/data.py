"""nres/data.py — Data loading helpers for NRES analysis."""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import streamlit as st
from scipy.interpolate import interp1d

import matplotlib
matplotlib.use('Agg')
import matplotlib.cm as mpl_cm  # noqa: E402

from shared import get_obs_manager, ROOT

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


@st.cache_data
def _load_star_epochs(star_name):
    obs = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    epochs = star.get_all_epoch_numbers()
    spectra_per_epoch = {}
    for ep in epochs:
        spectra_per_epoch[ep] = star.get_all_spectra_in_epoch(ep)
    return epochs, spectra_per_epoch


@st.cache_data
def _load_normalized_flux(star_name, epoch, spectra_num):
    obs = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    d = star.load_property('clean_normalized_flux', epoch, spectra_num, to_print=False)
    if d is None:
        d = star.load_property('normalized_flux', epoch, spectra_num, to_print=False)
    if d is None:
        return None, None
    return np.array(d['wavelengths']), np.array(d['normalized_flux'])


@st.cache_data
def _get_mjd(star_name, epoch, spectra_num):
    obs = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    fit = star.load_observation(epoch, spectra_num, '1D')
    if fit is None:
        return None
    hdr = fit.header
    if 'MJD-OBS' in hdr:
        return float(hdr['MJD-OBS'])
    if 'DATE-OBS' in hdr:
        from astropy.time import Time
        return Time(hdr['DATE-OBS']).mjd
    return None


def _load_existing_rvs(star_name, epochs, spectra_per_epoch):
    """Scan saved RV properties across all epochs/spectra."""
    obs = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    rows = []
    for ep in epochs:
        mjd = _get_mjd(star_name, ep, spectra_per_epoch[ep][0])
        for sp in spectra_per_epoch[ep]:
            rv_data = star.load_property('RVs', ep, sp, to_print=False)
            if rv_data is None:
                continue
            for line_name, rv_info in rv_data.items():
                if not isinstance(rv_info, dict):
                    continue
                rv_val = rv_info.get('full_RV')
                rv_err = rv_info.get('full_RV_err')
                if rv_val is not None:
                    rows.append({
                        'Epoch': ep, 'Spectra': sp, 'MJD': mjd,
                        'Line': line_name,
                        'RV (km/s)': rv_val, 'RV_err (km/s)': rv_err,
                    })
    return pd.DataFrame(rows) if rows else None


def _compute_epoch_summary(rv_df):
    """Compute per-epoch weighted mean RVs from a per-spectrum DataFrame."""
    summary_rows = []
    for line_name in rv_df['Line'].unique():
        sub = rv_df[rv_df['Line'] == line_name]
        for ep in sorted(sub['Epoch'].unique()):
            ep_data = sub[sub['Epoch'] == ep]
            rvs = np.array(ep_data['RV (km/s)'].values, dtype=float)
            errs = np.array(ep_data['RV_err (km/s)'].values, dtype=float)
            valid = np.isfinite(rvs) & np.isfinite(errs) & (errs > 0)
            if valid.sum() == 0:
                continue
            rvs_v, errs_v = rvs[valid], errs[valid]
            weights = 1.0 / errs_v**2
            wmean = np.sum(rvs_v * weights) / np.sum(weights)
            werr = 1.0 / np.sqrt(np.sum(weights))
            mjd = ep_data['MJD'].iloc[0]
            summary_rows.append({
                'Epoch': ep, 'MJD': mjd, 'Line': line_name,
                'RV_mean (km/s)': round(wmean, 3),
                'RV_err (km/s)': round(werr, 3),
                'N_spectra': int(valid.sum()),
            })
    return pd.DataFrame(summary_rows) if summary_rows else None


def _compute_threshold_stats(rv_df):
    """Compute within-epoch sigma, between-epoch sigma, overall sigma, deltaRV, significance per line."""
    results = {}
    sum_df = _compute_epoch_summary(rv_df)
    if sum_df is None:
        return results
    for line_name in sum_df['Line'].unique():
        sub = sum_df[sum_df['Line'] == line_name].sort_values('MJD')
        if len(sub) < 2:
            continue
        means = sub['RV_mean (km/s)'].values
        errs = sub['RV_err (km/s)'].values
        mjds = sub['MJD'].values
        n_spectra_per_ep = sub['N_spectra'].values.tolist()

        sigma_between = np.std(means, ddof=1)

        within_sigmas = []
        line_data = rv_df[rv_df['Line'] == line_name]
        for ep in sorted(line_data['Epoch'].unique()):
            ep_rvs = line_data[line_data['Epoch'] == ep]['RV (km/s)'].values.astype(float)
            ep_rvs = ep_rvs[np.isfinite(ep_rvs)]
            if len(ep_rvs) >= 2:
                within_sigmas.append(np.std(ep_rvs, ddof=1))
        sigma_within = np.mean(within_sigmas) if within_sigmas else 0.0

        all_rvs = line_data['RV (km/s)'].values.astype(float)
        all_rvs = all_rvs[np.isfinite(all_rvs)]
        sigma_overall = np.std(all_rvs, ddof=1) if len(all_rvs) >= 2 else 0.0

        delta_rv = np.ptp(means)
        # Significance: ΔRV / (4 × σ_overall) — the 4σ certainty criterion
        significance_4sigma = delta_rv / (4.0 * sigma_overall) if sigma_overall > 0 else np.inf

        results[line_name] = {
            'sigma_within': sigma_within,
            'sigma_between': sigma_between,
            'sigma_overall': sigma_overall,
            'delta_rv': delta_rv,
            'significance': significance_4sigma,
            'n_epochs': len(means),
            'epoch_means': means.tolist(),
            'epoch_errs': errs.tolist(),
            'epoch_mjds': mjds.tolist(),
            'n_spectra_per_ep': n_spectra_per_ep,
        }
    return results


def _color_log_rainbow_text_col(col):
    """Log-gradient rainbow coloring for a DataFrame column (text color)."""
    vals = pd.to_numeric(col, errors='coerce')
    valid = vals.dropna()
    if len(valid) == 0:
        return [''] * len(col)
    log_vals = np.log1p(vals.fillna(0))
    vmin, vmax = log_vals.min(), log_vals.max()
    if vmax == vmin:
        normed = np.zeros(len(log_vals))
    else:
        normed = (log_vals - vmin) / (vmax - vmin)
    colors = []
    for v, raw in zip(normed, vals):
        if pd.isna(raw):
            colors.append('')
        else:
            rgba = mpl_cm.rainbow(float(v))
            r, g, b = int(rgba[0] * 255), int(rgba[1] * 255), int(rgba[2] * 255)
            colors.append(f'color: rgb({r},{g},{b}); font-weight: bold')
    return colors


def _load_spectra_for_star(star_name, use_spectra):
    """Load and interpolate all spectra. Returns (obs_data_all, obs_meta, common_wavegrid, tpl_f) or Nones."""
    obs_data_all = []
    obs_meta = []
    tpl_f = None
    common_wavegrid = None

    for ep, sp in use_spectra:
        w, f = _load_normalized_flux(star_name, ep, sp)
        if w is None:
            continue
        mask = np.isfinite(w) & np.isfinite(f)
        w, f = w[mask], f[mask]
        if w.size == 0:
            continue
        if common_wavegrid is None:
            tpl_f = f.copy()
            common_wavegrid = w.copy()
        interp_f = interp1d(w, f, kind='cubic', bounds_error=False, fill_value=1.0)(common_wavegrid)
        obs_data_all.append((ep, common_wavegrid.copy(), interp_f))
        obs_meta.append((ep, sp))

    if common_wavegrid is None or len(obs_data_all) < 2:
        return None, None, None, None
    return obs_data_all, obs_meta, common_wavegrid, tpl_f


def _save_rvs_for_star(star_name, result_df):
    """Save RV results to disk using NRESClass.save_property with backup."""
    obs = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    saved_count = 0
    for (ep, sp), grp in result_df.groupby(['Epoch', 'Spectra']):
        rv_dict = star.load_property('RVs', ep, sp, to_print=False) or {}
        for _, row in grp.iterrows():
            rv_dict[row['Line']] = {
                'full_RV': row['RV (km/s)'],
                'full_RV_err': row['RV_err (km/s)'],
            }
        star.save_property('RVs', rv_dict, ep, sp, overwrite=True, backup=True, create_dirs=True)
        saved_count += 1
    return saved_count
