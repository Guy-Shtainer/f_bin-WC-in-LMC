"""
pages/11_nres_analysis.py — NRES Analysis & DeltaRV Threshold
Measure RV variability of MW WC stars (WR 52, WR17) from NRES multi-epoch
spectra to establish the single-star RV scatter floor.
"""
from __future__ import annotations
import os, sys, json, datetime, shutil, re, multiprocessing, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from scipy.interpolate import interp1d
import matplotlib
matplotlib.use('Agg')
import matplotlib.cm as mpl_cm

from shared import (
    inject_theme, render_sidebar, get_settings_manager, get_obs_manager,
    PLOTLY_THEME, apply_theme, get_palette, COLOR_BINARY, COLOR_SINGLE,
)
from CCF import CCFclass
from nres_ccf_worker import _process_single_line, _save_single_plot

st.set_page_config(page_title='NRES Analysis — WR Binary', page_icon='🔭', layout='wide')
inject_theme()
settings = render_sidebar('NRES Analysis')
sm = get_settings_manager()

# ── Constants ─────────────────────────────────────────────────────────────────
NRES_STARS = ['WR 52', 'WR17']
c_kms = 299792.458

NRES_LINE_NAMES = [
    'He II 4686', 'O VI 5210-5340', 'He II 5412 & C IV 5471',
    'C IV 5808-5812', 'C III 6700-6800', 'C IV 7063',
]


# ── Load / save emission line config ──────────────────────────────────────────
_NRES_CFG_PATH = os.path.join(_ROOT, 'settings', 'nres_line_config.json')
_NRES_OVR_PATH = os.path.join(_ROOT, 'settings', 'nres_line_overrides.json')


def _load_line_config_from_global():
    """Load defaults from the shared X-SHOOTER config (fallback)."""
    json_path = os.path.join(_ROOT, 'ccf_settings_with_global_lines.json')
    with open(json_path) as f:
        cfg = json.load(f)
    lines = cfg.get('emission_lines_default', {})
    fit_frac_default = cfg.get('fit_fraction_default', 0.95)
    result = {}
    for name in NRES_LINE_NAMES:
        if name in lines:
            rng_nm = lines[name]
            result[name] = {
                'lam_min': rng_nm[0] * 10.0,
                'lam_max': rng_nm[1] * 10.0,
                'fit_fraction': fit_frac_default,
                'enabled': True,
            }
    return result


def _save_line_config_to_disk(df):
    """Save line config DataFrame to settings/nres_line_config.json."""
    records = df.to_dict(orient='records')
    with open(_NRES_CFG_PATH, 'w') as f:
        json.dump(records, f, indent=2)


def _save_overrides_to_disk(star_name, overrides_df):
    """Save per-star overrides to settings/nres_line_overrides.json."""
    if os.path.exists(_NRES_OVR_PATH):
        with open(_NRES_OVR_PATH) as f:
            all_ovr = json.load(f)
    else:
        all_ovr = {}
    all_ovr[star_name] = overrides_df.to_dict(orient='records')
    with open(_NRES_OVR_PATH, 'w') as f:
        json.dump(all_ovr, f, indent=2)


def _get_line_config_df():
    """Global line config table (6 rows). Loads from disk config, falls back to global JSON."""
    if 'nres_line_cfg' not in st.session_state:
        if os.path.exists(_NRES_CFG_PATH):
            with open(_NRES_CFG_PATH) as f:
                records = json.load(f)
            st.session_state['nres_line_cfg'] = pd.DataFrame(records)
        else:
            cfg = _load_line_config_from_global()
            rows = []
            for name, d in cfg.items():
                rows.append({
                    'Line': name, 'lam_min': d['lam_min'], 'lam_max': d['lam_max'],
                    'fit_fraction': d['fit_fraction'], 'enabled': d['enabled'],
                })
            st.session_state['nres_line_cfg'] = pd.DataFrame(rows)
    return st.session_state['nres_line_cfg']


def _get_overrides_df(star_name):
    """Per-epoch/per-spectra override table. Loads from disk, empty by default."""
    key = f'nres_line_overrides_{star_name}'
    if key not in st.session_state:
        if os.path.exists(_NRES_OVR_PATH):
            with open(_NRES_OVR_PATH) as f:
                all_ovr = json.load(f)
            if star_name in all_ovr and all_ovr[star_name]:
                st.session_state[key] = pd.DataFrame(all_ovr[star_name])
            else:
                st.session_state[key] = pd.DataFrame(
                    columns=['Epoch', 'Spectra', 'Line', 'lam_min', 'lam_max', 'fit_fraction', 'enabled']
                )
        else:
            st.session_state[key] = pd.DataFrame(
                columns=['Epoch', 'Spectra', 'Line', 'lam_min', 'lam_max', 'fit_fraction', 'enabled']
            )
    return st.session_state[key]


def _resolve_line_config(epoch, spectra, line_name, global_df, overrides_df):
    """Resolve line config: check overrides (exact match then epoch-wide), fall back to global."""
    if len(overrides_df) > 0:
        # Exact match: (epoch, spectra, line)
        exact = overrides_df[
            (overrides_df['Epoch'] == epoch) &
            (overrides_df['Spectra'] == spectra) &
            (overrides_df['Line'] == line_name)
        ]
        if len(exact) > 0:
            r = exact.iloc[0]
            return r['lam_min'], r['lam_max'], r['fit_fraction'], bool(r['enabled'])
        # Epoch-wide match: (epoch, 'All', line)
        epoch_wide = overrides_df[
            (overrides_df['Epoch'] == epoch) &
            (overrides_df['Spectra'] == 'All') &
            (overrides_df['Line'] == line_name)
        ]
        if len(epoch_wide) > 0:
            r = epoch_wide.iloc[0]
            return r['lam_min'], r['lam_max'], r['fit_fraction'], bool(r['enabled'])
    # Fall back to global
    g = global_df[global_df['Line'] == line_name]
    if len(g) > 0:
        r = g.iloc[0]
        return r['lam_min'], r['lam_max'], r['fit_fraction'], bool(r['enabled'])
    return None, None, None, False


# ── Helpers ───────────────────────────────────────────────────────────────────
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



# _save_single_plot imported from nres_ccf_worker (E022: avoid __main__ pickling)


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



# _process_single_line imported from nres_ccf_worker (E022: avoid __main__ pickling)


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


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE HEADER — Star selector at top
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown('# NRES Analysis & DeltaRV Threshold')

col_star, col_velo = st.columns([2, 1])
with col_star:
    star_name = st.selectbox('Select NRES Star', NRES_STARS, key='nres_star')
with col_velo:
    cross_velo = st.number_input(
        'CrossVelo (km/s)', min_value=100, max_value=5000, value=2000, step=100,
        key='nres_cross_velo',
    )

epochs, spectra_per_epoch = _load_star_epochs(star_name)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_spec, tab_thresh = st.tabs(['Spectra & CCF', 'Threshold Analysis'])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: Spectra, Line Config & CCF (merged)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_spec:
    pal = get_palette()

    # ── Epoch & spectra selection with show/use toggles ───────────────────────
    st.markdown('### Epoch & Spectra Selection')

    if f'nres_spectra_cfg_{star_name}' not in st.session_state:
        cfg = {}
        for ep in epochs:
            for sp in spectra_per_epoch[ep]:
                cfg[(ep, sp)] = {'show': False, 'use': True}
            if spectra_per_epoch[ep]:
                cfg[(ep, spectra_per_epoch[ep][0])]['show'] = True
        st.session_state[f'nres_spectra_cfg_{star_name}'] = cfg

    spec_cfg = st.session_state[f'nres_spectra_cfg_{star_name}']

    for ep in epochs:
        mjd = _get_mjd(star_name, ep, spectra_per_epoch[ep][0])
        mjd_str = f' (MJD {mjd:.2f})' if mjd else ''
        with st.expander(f'Epoch {ep}{mjd_str} — {len(spectra_per_epoch[ep])} spectra', expanded=False):
            bc1, bc2, bc3, bc4 = st.columns(4)
            if bc1.button('Show all', key=f'show_all_{ep}'):
                for sp in spectra_per_epoch[ep]:
                    spec_cfg[(ep, sp)]['show'] = True
                    st.session_state[f'show_{star_name}_{ep}_{sp}'] = True
                st.rerun()
            if bc2.button('Hide all', key=f'hide_all_{ep}'):
                for sp in spectra_per_epoch[ep]:
                    spec_cfg[(ep, sp)]['show'] = False
                    st.session_state[f'show_{star_name}_{ep}_{sp}'] = False
                st.rerun()
            if bc3.button('Use all', key=f'use_all_{ep}'):
                for sp in spectra_per_epoch[ep]:
                    spec_cfg[(ep, sp)]['use'] = True
                    st.session_state[f'use_{star_name}_{ep}_{sp}'] = True
                st.rerun()
            if bc4.button('Use none', key=f'use_none_{ep}'):
                for sp in spectra_per_epoch[ep]:
                    spec_cfg[(ep, sp)]['use'] = False
                    st.session_state[f'use_{star_name}_{ep}_{sp}'] = False
                st.rerun()

            n_cols = min(6, len(spectra_per_epoch[ep]))
            sp_cols = st.columns(n_cols)
            for i, sp in enumerate(spectra_per_epoch[ep]):
                show_key = f'show_{star_name}_{ep}_{sp}'
                use_key = f'use_{star_name}_{ep}_{sp}'
                if show_key not in st.session_state:
                    st.session_state[show_key] = spec_cfg[(ep, sp)]['show']
                if use_key not in st.session_state:
                    st.session_state[use_key] = spec_cfg[(ep, sp)]['use']
                with sp_cols[i % n_cols]:
                    show = st.checkbox(f'Show #{sp}', key=show_key)
                    use = st.checkbox(f'Use #{sp}', key=use_key)
                    spec_cfg[(ep, sp)]['show'] = show
                    spec_cfg[(ep, sp)]['use'] = use

    # ── Global emission line configuration ───────────────────────────────────
    st.markdown('### Emission Line Configuration')

    line_df = _get_line_config_df()

    col_zoom, _ = st.columns([2, 2])
    with col_zoom:
        zoom_options = ['Full spectrum'] + list(line_df['Line'])
        zoom_choice = st.selectbox('Zoom to line', zoom_options, key='nres_zoom')

    edited_line_df = st.data_editor(
        line_df,
        column_config={
            'Line': st.column_config.TextColumn('Line', disabled=True),
            'lam_min': st.column_config.NumberColumn('λ_min (Å)', format='%.1f'),
            'lam_max': st.column_config.NumberColumn('λ_max (Å)', format='%.1f'),
            'fit_fraction': st.column_config.NumberColumn('Fit fraction', min_value=0.5, max_value=1.0, step=0.01, format='%.2f'),
            'enabled': st.column_config.CheckboxColumn('Enabled'),
        },
        use_container_width=True,
        hide_index=True,
        key='nres_line_editor',
    )
    st.session_state['nres_line_cfg'] = edited_line_df
    _save_line_config_to_disk(edited_line_df)

    # Add/remove line + reset + overrides
    ctl1, ctl2, ctl3 = st.columns(3)
    with ctl1:
        with st.expander('Add custom emission line'):
            new_name = st.text_input('Line name', key='nres_new_line_name')
            nc1, nc2, nc3 = st.columns(3)
            new_lmin = nc1.number_input('λ_min (Å)', value=5000.0, key='nres_new_lmin')
            new_lmax = nc2.number_input('λ_max (Å)', value=6000.0, key='nres_new_lmax')
            new_ff = nc3.number_input('Fit fraction', value=0.95, min_value=0.5, max_value=1.0, step=0.01, key='nres_new_ff')
            if st.button('Add line', key='nres_add_line'):
                if new_name and new_name not in edited_line_df['Line'].values:
                    new_row = pd.DataFrame([{
                        'Line': new_name, 'lam_min': new_lmin,
                        'lam_max': new_lmax, 'fit_fraction': new_ff, 'enabled': True,
                    }])
                    updated = pd.concat([edited_line_df, new_row], ignore_index=True)
                    st.session_state['nres_line_cfg'] = updated
                    _save_line_config_to_disk(updated)
                    st.rerun()
                elif new_name in edited_line_df['Line'].values:
                    st.warning('Line name already exists.')

    with ctl2:
        with st.expander('Remove emission line'):
            line_to_del = st.selectbox(
                'Select line to remove', edited_line_df['Line'].tolist(),
                key='nres_del_line_sel',
            )
            if st.button('Remove', key='nres_del_line'):
                updated = edited_line_df[edited_line_df['Line'] != line_to_del].reset_index(drop=True)
                st.session_state['nres_line_cfg'] = updated
                _save_line_config_to_disk(updated)
                st.rerun()

    with ctl3:
        if st.button('Reset to defaults', key='nres_reset_lines'):
            if 'nres_line_cfg' in st.session_state:
                del st.session_state['nres_line_cfg']
            if os.path.exists(_NRES_CFG_PATH):
                os.remove(_NRES_CFG_PATH)
            ovr_key = f'nres_line_overrides_{star_name}'
            if ovr_key in st.session_state:
                del st.session_state[ovr_key]
            if os.path.exists(_NRES_OVR_PATH):
                os.remove(_NRES_OVR_PATH)
            st.rerun()

    # ── Per-epoch / per-spectra overrides (dropdown picker) ──────────────────
    overrides_df = _get_overrides_df(star_name)
    with st.expander(f'Per-epoch / per-spectra overrides ({len(overrides_df)} active)'):
        if len(overrides_df) > 0:
            st.dataframe(overrides_df, use_container_width=True, hide_index=True)
            ovr_to_del = st.selectbox(
                'Remove override #',
                list(range(len(overrides_df))),
                format_func=lambda i: f'{overrides_df.iloc[i]["Line"]} — Ep{overrides_df.iloc[i]["Epoch"]} Sp{overrides_df.iloc[i]["Spectra"]}',
                key='nres_ovr_del_sel',
            )
            if st.button('Remove selected override', key='nres_ovr_del'):
                updated_ovr = overrides_df.drop(ovr_to_del).reset_index(drop=True)
                st.session_state[f'nres_line_overrides_{star_name}'] = updated_ovr
                _save_overrides_to_disk(star_name, updated_ovr)
                st.rerun()

        st.markdown('**Add override:**')
        oc1, oc2, oc3 = st.columns(3)
        ovr_epoch = oc1.selectbox('Epoch', epochs, key='nres_ovr_epoch')
        spectra_options = ['All'] + [str(s) for s in spectra_per_epoch.get(ovr_epoch, [])]
        ovr_spectra = oc2.selectbox('Spectra', spectra_options, key='nres_ovr_spectra')
        ovr_line = oc3.selectbox('Line', edited_line_df['Line'].tolist(), key='nres_ovr_line')

        # Pre-fill from global config
        g_row = edited_line_df[edited_line_df['Line'] == ovr_line]
        g_lmin = float(g_row['lam_min'].iloc[0]) if len(g_row) > 0 else 5000.0
        g_lmax = float(g_row['lam_max'].iloc[0]) if len(g_row) > 0 else 6000.0
        g_ff = float(g_row['fit_fraction'].iloc[0]) if len(g_row) > 0 else 0.95

        oc4, oc5, oc6, oc7 = st.columns(4)
        ovr_lmin = oc4.number_input('λ_min', value=g_lmin, key='nres_ovr_lmin')
        ovr_lmax = oc5.number_input('λ_max', value=g_lmax, key='nres_ovr_lmax')
        ovr_ff = oc6.number_input('Fit frac', value=g_ff, min_value=0.5, max_value=1.0, step=0.01, key='nres_ovr_ff')
        ovr_enabled = oc7.checkbox('Enabled', value=True, key='nres_ovr_enabled')

        if st.button('Add override', key='nres_ovr_add'):
            new_ovr = pd.DataFrame([{
                'Epoch': ovr_epoch, 'Spectra': ovr_spectra, 'Line': ovr_line,
                'lam_min': ovr_lmin, 'lam_max': ovr_lmax,
                'fit_fraction': ovr_ff, 'enabled': ovr_enabled,
            }])
            updated_ovr = pd.concat([overrides_df, new_ovr], ignore_index=True)
            st.session_state[f'nres_line_overrides_{star_name}'] = updated_ovr
            _save_overrides_to_disk(star_name, updated_ovr)
            st.rerun()

    # ── Spectrum plot with downsampling & separation sliders ─────────────────
    st.markdown('### Spectra')

    sl1, sl2, sl3 = st.columns(3)
    with sl1:
        bin_window = st.slider('Downsample (every Nth point)', 1, 50, 10, key='nres_bin_window')
    with sl2:
        epoch_sep = st.slider('Epoch separation', 0, 500, 0, step=10, key='nres_epoch_sep')
    with sl3:
        spec_sep = st.slider('Spectra separation', 0, 100, 0, step=5, key='nres_spec_sep')

    epoch_colors = ['#4A90D9', '#E25A53', '#52B788', '#DAA520', '#9B59B6', '#E67E22']

    fig = go.Figure()
    for ep_idx, ep in enumerate(epochs):
        color = epoch_colors[ep_idx % len(epoch_colors)]
        sp_count = 0
        for sp in spectra_per_epoch[ep]:
            if not spec_cfg.get((ep, sp), {}).get('show', False):
                continue
            w, f = _load_normalized_flux(star_name, ep, sp)
            if w is None:
                continue
            w_plot = w[::bin_window]
            f_plot = f[::bin_window] + ep_idx * epoch_sep + sp_count * spec_sep
            fig.add_trace(go.Scatter(
                x=w_plot, y=f_plot, mode='lines',
                name=f'Ep{ep} Sp{sp}',
                line=dict(color=color, width=1),
                legendgroup=f'epoch_{ep}',
            ))
            sp_count += 1

    # Add emission line bands
    band_colors = [
        'rgba(74,144,217,0.12)', 'rgba(226,90,83,0.12)', 'rgba(82,183,136,0.12)',
        'rgba(218,165,32,0.12)', 'rgba(155,89,182,0.12)', 'rgba(230,126,34,0.12)',
    ]
    for i, (_, row) in enumerate(edited_line_df.iterrows()):
        if not row['enabled']:
            continue
        fig.add_vrect(
            x0=row['lam_min'], x1=row['lam_max'],
            fillcolor=band_colors[i % len(band_colors)],
            line_width=0, layer='below',
            annotation_text=row['Line'], annotation_position='top left',
            annotation=dict(font_size=9, font_color=pal['muted_color']),
        )

    if zoom_choice != 'Full spectrum':
        row_zoom = edited_line_df[edited_line_df['Line'] == zoom_choice].iloc[0]
        padding = 50.0
        fig.update_xaxes(range=[row_zoom['lam_min'] - padding, row_zoom['lam_max'] + padding])

    apply_theme(fig, title=f'{star_name} — Normalized Spectra',
                xaxis_title='Wavelength (Å)', yaxis_title='Normalized Flux',
                height=550)
    st.plotly_chart(fig, use_container_width=True)
    st.caption('Colored bands mark emission line ranges. Adjust sliders to downsample and separate overlapping spectra.')

    # ═══════════════════════════════════════════════════════════════════════════
    # CCF SECTION
    # ═══════════════════════════════════════════════════════════════════════════
    st.divider()
    st.markdown('### RV Measurement')

    load_existing = st.toggle('Load existing RVs', value=True, key='nres_load_existing')

    if load_existing:
        rv_df = _load_existing_rvs(star_name, epochs, spectra_per_epoch)
        if rv_df is not None and len(rv_df) > 0:
            sum_df = _compute_epoch_summary(rv_df)
            if sum_df is not None:
                st.markdown('#### Per-Epoch Weighted Mean RVs (saved)')
                st.dataframe(sum_df, use_container_width=True, hide_index=True)
                with st.expander('Per-spectrum detail'):
                    st.dataframe(rv_df, use_container_width=True, hide_index=True)

                fig_rv = go.Figure()
                for ln in sum_df['Line'].unique():
                    s = sum_df[sum_df['Line'] == ln].sort_values('MJD')
                    fig_rv.add_trace(go.Scatter(
                        x=s['MJD'], y=s['RV_mean (km/s)'],
                        error_y=dict(type='data', array=s['RV_err (km/s)'].values, visible=True),
                        mode='markers+lines', name=ln, marker=dict(size=8),
                    ))
                apply_theme(fig_rv, title=f'{star_name} — RV Time Series (saved)',
                            xaxis_title='MJD', yaxis_title='RV (km/s)', height=400)
                st.plotly_chart(fig_rv, use_container_width=True)
        else:
            st.info('No saved RVs found for this star.')

    # ── Run CCF (multiprocessed) ─────────────────────────────────────────────
    st.markdown('#### Run Double CCF')

    use_spectra = []
    for ep in epochs:
        for sp in spectra_per_epoch[ep]:
            if spec_cfg.get((ep, sp), {}).get('use', True):
                use_spectra.append((ep, sp))
    n_use = len(use_spectra)
    n_epochs_used = len(set(ep for ep, sp in use_spectra))

    enabled_lines = edited_line_df[edited_line_df['enabled'] == True]
    st.markdown(f'**{len(enabled_lines)} lines enabled, {n_use} spectra from {n_epochs_used} epochs selected**')

    save_plots = st.checkbox('Save CCF plots', value=True, key='nres_save_plots')

    btn_col1, btn_col2 = st.columns(2)
    run_single = btn_col1.button('Run Double CCF', type='primary', key='nres_run_ccf')
    run_both = btn_col2.button('Run CCF for Both Stars', key='nres_run_both')

    if run_single:
        if n_epochs_used < 2:
            st.error('Need spectra from at least 2 epochs.')
        elif len(enabled_lines) == 0:
            st.warning('No emission lines enabled.')
        else:
            progress = st.progress(0, text='Loading spectra...')
            obs_data_all, obs_meta, common_wavegrid, tpl_f = _load_spectra_for_star(star_name, use_spectra)
            if obs_data_all is None:
                st.error('Not enough valid spectra loaded.')
            else:
                # Add MJD to results after pool completes
                run_ts = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                n_lines = len(enabled_lines)
                all_epochs_set = set(ep for ep, sp in use_spectra)

                # Build jobs for Pool
                line_jobs = []
                for _, lr in enabled_lines.iterrows():
                    line_jobs.append((
                        star_name, lr['Line'], lr['lam_min'], lr['lam_max'], lr['fit_fraction'],
                        obs_data_all, obs_meta, common_wavegrid, tpl_f,
                        cross_velo, save_plots, run_ts, all_epochs_set,
                    ))

                progress.progress(0.1, text=f'Running CCF for {n_lines} lines in parallel...')
                n_workers = max(1, (os.cpu_count() or 2) - 1)
                all_results = []
                all_plot_args = []

                with multiprocessing.Pool(n_workers) as pool:
                    for i, (sn, ln, results, plot_args) in enumerate(pool.imap_unordered(_process_single_line, line_jobs)):
                        all_results.extend(results)
                        all_plot_args.extend(plot_args)
                        progress.progress((i + 1) / n_lines * 0.7 + 0.1,
                                          text=f'Completed {i + 1}/{n_lines} lines...')

                # Save plots in background (non-blocking)
                if all_plot_args:
                    def _bg_save(args, nw):
                        with ThreadPoolExecutor(max_workers=nw) as ex:
                            list(ex.map(_save_single_plot, args))
                    threading.Thread(target=_bg_save, args=(all_plot_args, n_workers), daemon=True).start()
                    st.toast(f'Saving {len(all_plot_args)} plots in background...')

                progress.progress(1.0, text='Done!')

                if all_results:
                    result_df = pd.DataFrame(all_results)
                    # Add MJD
                    result_df['MJD'] = result_df.apply(
                        lambda r: _get_mjd(star_name, r['Epoch'], r['Spectra']), axis=1
                    )
                    st.session_state[f'nres_ccf_results_{star_name}'] = result_df
                    sum_df = _compute_epoch_summary(result_df)
                    if sum_df is not None:
                        st.markdown('#### Per-Epoch Weighted Mean RVs (new)')
                        st.dataframe(sum_df, use_container_width=True, hide_index=True)
                        with st.expander('Per-spectrum detail'):
                            st.dataframe(result_df, use_container_width=True, hide_index=True)
                else:
                    st.warning('No valid CCF results obtained.')

    if run_both:
        run_ts = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        n_workers = max(1, (os.cpu_count() or 2) - 1)

        # Build flat job list across both stars and all lines
        all_jobs = []
        star_obs_data = {}  # cache loaded spectra per star
        progress = st.progress(0, text='Loading spectra for both stars...')

        for si, sn in enumerate(NRES_STARS):
            ep_list, sp_per_ep = _load_star_epochs(sn)
            if sn == star_name:
                sn_use = use_spectra
            else:
                sn_use = [(ep, sp) for ep in ep_list for sp in sp_per_ep[ep]]

            obs_data, obs_meta_sn, cw, tf = _load_spectra_for_star(sn, sn_use)
            if obs_data is None:
                st.warning(f'{sn}: Not enough valid spectra.')
                continue
            star_obs_data[sn] = (obs_data, obs_meta_sn, cw, tf, sn_use)
            all_epochs_set = set(ep for ep, sp in sn_use)

            for _, lr in enabled_lines.iterrows():
                all_jobs.append((
                    sn, lr['Line'], lr['lam_min'], lr['lam_max'], lr['fit_fraction'],
                    obs_data, obs_meta_sn, cw, tf,
                    cross_velo, save_plots, run_ts, all_epochs_set,
                ))
            progress.progress((si + 1) / len(NRES_STARS) * 0.1,
                              text=f'Loaded {sn} spectra...')

        if all_jobs:
            n_total = len(all_jobs)
            progress.progress(0.1, text=f'Running {n_total} (star, line) jobs in parallel...')

            star_results = {}
            all_plot_args = []

            with multiprocessing.Pool(n_workers) as pool:
                for i, (sn, ln, results, plot_args) in enumerate(pool.imap_unordered(_process_single_line, all_jobs)):
                    if sn not in star_results:
                        star_results[sn] = []
                    star_results[sn].extend(results)
                    all_plot_args.extend(plot_args)
                    progress.progress((i + 1) / n_total * 0.7 + 0.1,
                                      text=f'Completed {i + 1}/{n_total} jobs...')

            # Save plots in background (non-blocking)
            if all_plot_args:
                def _bg_save_both(args, nw):
                    with ThreadPoolExecutor(max_workers=nw) as ex:
                        list(ex.map(_save_single_plot, args))
                threading.Thread(target=_bg_save_both, args=(all_plot_args, n_workers), daemon=True).start()
                st.toast(f'Saving {len(all_plot_args)} plots in background...')

            # Auto-save RVs for both stars
            progress.progress(0.9, text='Saving RVs...')
            for sn, res_list in star_results.items():
                if res_list:
                    rdf = pd.DataFrame(res_list)
                    rdf['MJD'] = rdf.apply(
                        lambda r, star=sn: _get_mjd(star, r['Epoch'], r['Spectra']), axis=1
                    )
                    st.session_state[f'nres_ccf_results_{sn}'] = rdf
                    n_saved = _save_rvs_for_star(sn, rdf)
                    st.success(f'{sn}: {len(rdf)} measurements, {n_saved} files saved.')

            progress.progress(1.0, text='Done!')

    # ── Save / Load RVs ──────────────────────────────────────────────────────
    st.divider()
    save_col, load_col = st.columns(2)

    with save_col:
        st.markdown('#### Save RVs')
        ccf_key = f'nres_ccf_results_{star_name}'
        if ccf_key in st.session_state:
            if st.button('Save RVs to disk (auto-backup)', key='nres_save_rvs'):
                n_saved = _save_rvs_for_star(star_name, st.session_state[ccf_key])
                st.success(f'Saved RVs for {n_saved} spectrum files (backups in Backups/overwritten/).')
        else:
            st.info('Run CCF first to have results to save.')

    with load_col:
        st.markdown('#### Restore from Backup')
        backup_dir = os.path.join(_ROOT, 'Backups', 'overwritten')
        if os.path.isdir(backup_dir):
            backup_files = []
            for root, dirs, files in os.walk(backup_dir):
                for f in files:
                    if f.startswith('RVs_backup_') and f.endswith('.npz'):
                        full = os.path.join(root, f)
                        rel = os.path.relpath(full, backup_dir)
                        if star_name in rel:
                            backup_files.append((rel, full))
            if backup_files:
                backup_files.sort(reverse=True)
                labels = [r for r, _ in backup_files]
                selected = st.selectbox('Select backup to restore', labels, key='nres_backup_sel')
                if st.button('Restore selected backup', key='nres_restore_backup'):
                    idx = labels.index(selected)
                    backup_path = backup_files[idx][1]
                    data = dict(np.load(backup_path, allow_pickle=True))
                    parts = selected.split(os.sep)
                    target_rel = os.sep.join(parts)
                    target_rel = target_rel.rsplit('_backup_', 1)[0] + '.npz'
                    target_path = os.path.join(_ROOT, 'Data', target_rel)
                    if os.path.isdir(os.path.dirname(target_path)):
                        np.savez(target_path, **data)
                        st.success(f'Restored backup to {target_rel}')
                    else:
                        st.error(f'Target directory does not exist: {os.path.dirname(target_path)}')
            else:
                st.info(f'No RV backups found for {star_name}.')
        else:
            st.info('No backup directory found.')


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: Threshold Analysis
# ═══════════════════════════════════════════════════════════════════════════════
with tab_thresh:
    st.markdown('### Single-Star RV Variability & Detection Threshold')
    st.caption(
        'WR 52 and WR17 are assumed single or very long-period binaries. '
        'Their RV scatter (σ_overall) is the noise floor used as σ in the '
        'binary detection criterion: **ΔRV − 4σ > 0**. '
        'The 45.5 km/s ΔRV threshold is a separate criterion; both must be met.'
    )

    # Gather data for both stars
    analysis_data = {}
    analysis_rv_dfs = {}
    for sn in NRES_STARS:
        ccf_key = f'nres_ccf_results_{sn}'
        if ccf_key in st.session_state:
            rv_df_t = st.session_state[ccf_key]
        else:
            ep_list, sp_per_ep = _load_star_epochs(sn)
            rv_df_t = _load_existing_rvs(sn, ep_list, sp_per_ep)

        if rv_df_t is not None and len(rv_df_t) > 0:
            stats = _compute_threshold_stats(rv_df_t)
            if stats:
                analysis_data[sn] = stats
                analysis_rv_dfs[sn] = rv_df_t

    if not analysis_data:
        st.info('No RV data available for either star. Run CCF in the "Spectra & CCF" tab first.')
    else:
        # ── Structured table: rows=(star,line), columns grouped by epoch ─────
        st.markdown('### RV Summary Table')

        # Build the table
        table_rows = []
        all_within = []
        all_between = []
        all_overall = []

        for sn, line_results in analysis_data.items():
            for line_name, stats in line_results.items():
                row = {'Star': sn, 'Line': line_name}
                for ei, (mu, err, n_sp) in enumerate(zip(
                    stats['epoch_means'], stats['epoch_errs'],
                    stats.get('n_spectra_per_ep', [0] * stats['n_epochs'])
                )):
                    row[f'Ep{ei + 1} μ'] = round(mu, 2)
                    row[f'Ep{ei + 1} σ'] = round(stats['sigma_within'], 2) if ei == 0 else ''
                    row[f'Ep{ei + 1} N'] = int(n_sp)
                # Recalculate per-epoch σ individually
                rv_df_line = analysis_rv_dfs[sn]
                rv_line = rv_df_line[rv_df_line['Line'] == line_name]
                for ei, ep in enumerate(sorted(rv_line['Epoch'].unique())):
                    ep_rvs = rv_line[rv_line['Epoch'] == ep]['RV (km/s)'].values.astype(float)
                    ep_rvs = ep_rvs[np.isfinite(ep_rvs)]
                    row[f'Ep{ei + 1} σ'] = round(np.std(ep_rvs, ddof=1), 2) if len(ep_rvs) >= 2 else 0.0

                row['Total μ'] = round(np.mean(stats['epoch_means']), 2)
                row['Total σ'] = round(stats['sigma_overall'], 2)
                row['ΔRV'] = round(stats['delta_rv'], 2)
                row['ΔRV/4σ'] = round(stats['significance'], 2)
                table_rows.append(row)

                all_within.append(stats['sigma_within'])
                all_between.append(stats['sigma_between'])
                all_overall.append(stats['sigma_overall'])

        summary_df = pd.DataFrame(table_rows)
        # Apply rainbow coloring to ΔRV and σ columns
        color_cols = [c for c in summary_df.columns if c in ['ΔRV', 'Total σ', 'ΔRV/4σ']]
        styler = summary_df.style
        if color_cols:
            styler = styler.apply(_color_log_rainbow_text_col, subset=color_cols)
        # Format numeric columns
        for c in summary_df.columns:
            if c not in ['Star', 'Line'] and summary_df[c].dtype in ['float64', 'int64']:
                styler = styler.format('{:.2f}', subset=[c], na_rep='—')
        st.dataframe(styler, use_container_width=True, hide_index=True)
        st.caption(
            'μ = weighted mean RV (km/s), σ = std of spectra RVs within epoch, '
            'N = number of spectra, ΔRV/4σ = significance for 4σ criterion. '
            'Colors: log-gradient rainbow (violet=low, red=high).'
        )

        # Per-spectra detail
        with st.expander('Per-spectra RV detail'):
            for sn in analysis_rv_dfs:
                st.markdown(f'**{sn}**')
                st.dataframe(analysis_rv_dfs[sn], use_container_width=True, hide_index=True)

        # ── Build color map for (star, line) ────────────────────────────────
        trace_colors_list = px.colors.qualitative.Plotly
        color_map = {}
        ci = 0
        for sn in analysis_data:
            for ln in analysis_data[sn]:
                color_map[(sn, ln)] = trace_colors_list[ci % len(trace_colors_list)]
                ci += 1

        # ── MJD-to-date helper ────────────────────────────────────────────────
        from astropy.time import Time as AstropyTime
        def _mjd_to_dates(mjds):
            return [AstropyTime(m, format='mjd').datetime for m in mjds]

        # ── Filters ───────────────────────────────────────────────────────────
        st.divider()
        st.markdown('### RV vs Date')
        all_lines_set = sorted({ln for sn in analysis_data for ln in analysis_data[sn]})

        fc1, fc2 = st.columns([1, 2])
        with fc1:
            star_filter = st.radio('Star', ['Both stars'] + NRES_STARS, horizontal=True, key='nres_rv_plot_filter')
        with fc2:
            visible_lines = st.multiselect('Lines', all_lines_set, default=all_lines_set, key='nres_rv_line_filter')

        # ── Epoch-mean RV plot ────────────────────────────────────────────────
        fig_rv_date = go.Figure()
        for sn in analysis_data:
            if star_filter != 'Both stars' and sn != star_filter:
                continue
            for line_name, stats in analysis_data[sn].items():
                if line_name not in visible_lines:
                    continue
                dates = _mjd_to_dates(stats['epoch_mjds'])
                fig_rv_date.add_trace(go.Scatter(
                    x=dates,
                    y=stats['epoch_means'],
                    error_y=dict(type='data', array=stats['epoch_errs'], visible=True),
                    mode='markers+lines',
                    name=f'{sn} — {line_name}',
                    marker=dict(size=8, color=color_map.get((sn, line_name), '#333')),
                    customdata=stats['epoch_mjds'],
                    hovertemplate='Date: %{x}<br>RV: %{y:.2f} km/s<br>MJD: %{customdata:.2f}<extra>%{fullData.name}</extra>',
                    legendgroup=f'{sn}_{line_name}',
                ))
        apply_theme(fig_rv_date, title='Per-Epoch Weighted Mean RV vs Date',
                    xaxis_title='Date', yaxis_title='RV (km/s)', height=450)
        st.plotly_chart(fig_rv_date, use_container_width=True)
        st.caption('Each point is the weighted mean RV of all spectra in that epoch. Error bars are the weighted error.')

        # ── All individual RVs scatter plot ───────────────────────────────────
        st.markdown('### All Individual RVs vs Date')
        fig_all_rv = go.Figure()
        for sn in analysis_rv_dfs:
            if star_filter != 'Both stars' and sn != star_filter:
                continue
            rv_df_sn = analysis_rv_dfs[sn]
            for line_name in rv_df_sn['Line'].unique():
                if line_name not in visible_lines:
                    continue
                sub = rv_df_sn[rv_df_sn['Line'] == line_name].copy()
                sub = sub[sub['RV (km/s)'].apply(lambda v: np.isfinite(float(v)))]
                if len(sub) == 0:
                    continue
                dates = _mjd_to_dates(sub['MJD'].values)
                fig_all_rv.add_trace(go.Scatter(
                    x=dates,
                    y=sub['RV (km/s)'].values.astype(float),
                    error_y=dict(type='data', array=sub['RV_err (km/s)'].values.astype(float), visible=True),
                    mode='markers',
                    name=f'{sn} — {line_name}',
                    marker=dict(size=6, color=color_map.get((sn, line_name), '#333'),
                                symbol='circle' if sn == NRES_STARS[0] else 'diamond'),
                    customdata=sub['MJD'].values,
                    hovertemplate='Date: %{x}<br>RV: %{y:.2f} km/s<br>MJD: %{customdata:.2f}<br>Ep%{text}<extra>%{fullData.name}</extra>',
                    text=[f'{int(r["Epoch"])} Sp{int(r["Spectra"])}' for _, r in sub.iterrows()],
                    legendgroup=f'{sn}_{line_name}',
                ))
        apply_theme(fig_all_rv, title='All Individual Spectrum RVs vs Date',
                    xaxis_title='Date', yaxis_title='RV (km/s)', height=450)
        st.plotly_chart(fig_all_rv, use_container_width=True)
        st.caption('Every individual spectrum RV measurement. Different marker shapes per star (circle vs diamond).')

        # ── Combined summary with per-star breakdown ──────────────────────────
        st.divider()
        st.markdown('### Combined Estimate (Both Stars)')

        # Per-star sigma averages
        star_sigma_rows = []
        for sn in analysis_data:
            sn_within = [s['sigma_within'] for s in analysis_data[sn].values()]
            sn_between = [s['sigma_between'] for s in analysis_data[sn].values()]
            sn_overall = [s['sigma_overall'] for s in analysis_data[sn].values()]
            star_sigma_rows.append({
                'Source': sn,
                'σ_within (km/s)': round(np.mean(sn_within), 2) if sn_within else 0,
                'σ_between (km/s)': round(np.mean(sn_between), 2) if sn_between else 0,
                'σ_overall (km/s)': round(np.mean(sn_overall), 2) if sn_overall else 0,
                '4σ_overall (km/s)': round(4 * np.mean(sn_overall), 2) if sn_overall else 0,
            })

        mean_within = np.mean(all_within) if all_within else 0
        mean_between = np.mean(all_between) if all_between else 0
        mean_overall = np.mean(all_overall) if all_overall else 0
        star_sigma_rows.append({
            'Source': 'Combined (mean)',
            'σ_within (km/s)': round(mean_within, 2),
            'σ_between (km/s)': round(mean_between, 2),
            'σ_overall (km/s)': round(mean_overall, 2),
            '4σ_overall (km/s)': round(4 * mean_overall, 2),
        })

        sigma_table = pd.DataFrame(star_sigma_rows)
        st.dataframe(sigma_table, use_container_width=True, hide_index=True)

        st.caption(
            'σ_within: measurement precision (avg std within epochs). '
            'σ_between: short-term variability (std of epoch means). '
            'σ_overall: combined noise + variability (std of all individual RVs). '
            '**Binary criterion: ΔRV > 45.5 km/s AND ΔRV − 4σ > 0.** '
            f'Combined 4σ = {4 * mean_overall:.2f} km/s. '
            + ' '.join(f'{r["Source"]}: 4σ = {r["4σ_overall (km/s)"]} km/s.' for r in star_sigma_rows if r['Source'] != 'Combined (mean)')
        )

        # ── Impact plot ──────────────────────────────────────────────────────
        st.markdown('### Impact on Binary Classification')
        try:
            from pipeline.load_observations import load_observed_delta_rvs
            thresholds = np.arange(10, 100, 5)
            fractions = []
            for thresh in thresholds:
                test_settings = dict(settings)
                test_settings['classification'] = {
                    'threshold_dRV': float(thresh),
                    'sigma_factor': settings.get('classification', {}).get('sigma_factor', 4.0),
                }
                obs = get_obs_manager()
                delta_rvs, detail = load_observed_delta_rvs(test_settings, obs)
                bartzakos = settings.get('classification', {}).get('bartzakos_binaries', 3)
                total_pop = settings.get('classification', {}).get('total_population', 28)
                n_bin = sum(1 for d in detail.values() if d.get('is_binary'))
                fractions.append((n_bin + bartzakos) / total_pop if detail else 0)

            fig_impact = go.Figure()
            fig_impact.add_trace(go.Scatter(
                x=thresholds, y=fractions, mode='lines+markers', name='f_bin(observed)',
                line=dict(color=COLOR_BINARY),
            ))
            fig_impact.add_vline(x=45.5, line_dash='dash', line_color=COLOR_SINGLE,
                                 annotation_text='ΔRV threshold (45.5)')
            fig_impact.add_vline(x=4 * mean_overall, line_dash='dot', line_color='#DAA520',
                                 annotation_text=f'4σ ({4 * mean_overall:.1f})')
            apply_theme(fig_impact, title='Observed Binary Fraction vs ΔRV Threshold',
                        xaxis_title='ΔRV Threshold (km/s)',
                        yaxis_title='Observed Binary Fraction', height=400)
            st.plotly_chart(fig_impact, use_container_width=True)
        except Exception as e:
            st.warning(f'Could not compute impact analysis: {e}')
