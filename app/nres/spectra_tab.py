"""nres/spectra_tab.py — Spectra & CCF tab for NRES analysis."""
from __future__ import annotations

import datetime
import multiprocessing
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from shared import get_obs_manager, get_palette, apply_theme, ROOT

from nres_ccf_worker import _process_single_line, _save_single_plot
from nres.config import (
    NRES_STARS, _get_line_config_df, _save_line_config_to_disk,
    _get_overrides_df, _save_overrides_to_disk, _NRES_CFG_PATH, _NRES_OVR_PATH,
)
from nres.data import (
    _load_star_epochs, _load_normalized_flux, _get_mjd,
    _load_existing_rvs, _compute_epoch_summary,
    _load_spectra_for_star, _save_rvs_for_star,
)


def render_spectra_tab(star_name, epochs, spectra_per_epoch, cross_velo, settings):
    """Render the 'Spectra & CCF' tab."""
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

    enabled_lines = edited_line_df[edited_line_df['enabled'] == True]  # noqa: E712
    st.markdown(f'**{len(enabled_lines)} lines enabled, {n_use} spectra from {n_epochs_used} epochs selected**')

    save_plots = st.checkbox('Save CCF plots', value=True, key='nres_save_plots')

    btn_col1, btn_col2 = st.columns(2)
    run_single = btn_col1.button('Run Double CCF', type='primary', key='nres_run_ccf')
    run_both = btn_col2.button('Run CCF for Both Stars', key='nres_run_both')

    if run_single:
        _run_single_star_ccf(star_name, use_spectra, enabled_lines, cross_velo,
                             save_plots, n_epochs_used)

    if run_both:
        _run_both_stars_ccf(star_name, use_spectra, enabled_lines, cross_velo,
                            save_plots, epochs, spectra_per_epoch, settings)

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
        backup_dir = os.path.join(ROOT, 'Backups', 'overwritten')
        if os.path.isdir(backup_dir):
            backup_files = []
            for root_d, dirs, files in os.walk(backup_dir):
                for f in files:
                    if f.startswith('RVs_backup_') and f.endswith('.npz'):
                        full = os.path.join(root_d, f)
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
                    target_path = os.path.join(ROOT, 'Data', target_rel)
                    if os.path.isdir(os.path.dirname(target_path)):
                        np.savez(target_path, **data)
                        st.success(f'Restored backup to {target_rel}')
                    else:
                        st.error(f'Target directory does not exist: {os.path.dirname(target_path)}')
            else:
                st.info(f'No RV backups found for {star_name}.')
        else:
            st.info('No backup directory found.')


# ─────────────────────────────────────────────────────────────────────────────
# CCF runner helpers
# ─────────────────────────────────────────────────────────────────────────────

def _run_single_star_ccf(star_name, use_spectra, enabled_lines, cross_velo,
                         save_plots, n_epochs_used):
    """Run CCF for a single star."""
    if n_epochs_used < 2:
        st.error('Need spectra from at least 2 epochs.')
        return
    if len(enabled_lines) == 0:
        st.warning('No emission lines enabled.')
        return

    progress = st.progress(0, text='Loading spectra...')
    obs_data_all, obs_meta, common_wavegrid, tpl_f = _load_spectra_for_star(star_name, use_spectra)
    if obs_data_all is None:
        st.error('Not enough valid spectra loaded.')
        return

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


def _run_both_stars_ccf(star_name, use_spectra, enabled_lines, cross_velo,
                        save_plots, epochs, spectra_per_epoch, settings):
    """Run CCF for both NRES stars."""
    run_ts = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    n_workers = max(1, (os.cpu_count() or 2) - 1)

    all_jobs = []
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
