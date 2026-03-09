"""
pages/06_plots.py — Visualization Gallery
Two top-level tabs: X-Shooter | NRES
Each with sub-tabs for spectra, RV analysis, etc.
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from shared import (
    inject_theme, render_sidebar, get_settings_manager,
    cached_load_observed_delta_rvs, settings_hash,
    get_obs_manager, COLOR_BINARY, COLOR_SINGLE,
    PLOTLY_THEME, apply_theme, get_palette,
    make_heatmap_fig, cached_load_grid_result,
)
import specs

st.set_page_config(page_title='Plots — WR Binary', page_icon='🖼️', layout='wide')
inject_theme()
settings = render_sidebar('Plots')
sm = get_settings_manager()

st.markdown('# 🖼️ Visualization Gallery')

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
NRES_STARS = ['WR 52', 'WR17']
BANDS = ['COMBINED', 'UVB', 'VIS', 'NIR']
c_kms = 299792.458

_CCF_JSON_PATH = os.path.join(_ROOT, 'ccf_settings_with_global_lines.json')


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions
# ─────────────────────────────────────────────────────────────────────────────

def _load_ccf_settings() -> dict:
    """Load the CCF settings JSON (cached in session_state)."""
    if '_ccf_json' not in st.session_state:
        with open(_CCF_JSON_PATH) as f:
            st.session_state['_ccf_json'] = json.load(f)
    return st.session_state['_ccf_json']


def _get_emission_lines() -> dict:
    """Return dict of emission line name → (min_nm, max_nm)."""
    cfg = _load_ccf_settings()
    return cfg.get('emission_lines_default', {})


def _get_star_config() -> dict:
    """Return dict of star_name → per-star config."""
    cfg = _load_ccf_settings()
    return {s['star_name']: s for s in cfg.get('stars', [])}


@st.cache_data
def _load_normalized_spec(star_name: str, epoch: int, band: str, use_cleaned: bool = True):
    """Load normalized spectrum for an X-Shooter star/epoch/band."""
    obs = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    if use_cleaned:
        data = star.load_property('cleaned_normalized_flux', epoch, band)
        if data is not None:
            return data
    data = star.load_property('normalized_flux', epoch, band)
    return data


@st.cache_data
def _load_raw_spec(star_name: str, epoch: int, band: str):
    """Load raw FITS spectrum → (wave_A, flux, err) or None."""
    obs = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    try:
        fit = star.load_observation(epoch, band)
        if fit is None:
            return None
        wave_nm = np.asarray(fit.data['WAVE'][0])
        flux = np.asarray(fit.data['FLUX'][0])
        err = np.asarray(fit.data['ERR'][0]) if 'ERR' in fit.data else None
        wave_A = wave_nm * 10.0  # nm → Å
        return wave_A, flux, err
    except Exception:
        return None


@st.cache_data
def _load_continuum(star_name: str, epoch: int, band: str):
    """Load interpolated_flux property."""
    obs = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    return star.load_property('interpolated_flux', epoch, band)


@st.cache_data
def _load_rv_property(star_name: str, epoch: int, band: str = 'COMBINED'):
    """Load RVs property for an epoch."""
    obs = get_obs_manager()
    star = obs.load_star_instance(star_name, to_print=False)
    return star.load_property('RVs', epoch, band)


def _extract_rv(rv_entry):
    """Extract full_RV from an RV property entry (handles numpy structured arrays)."""
    if rv_entry is None:
        return None, None
    if hasattr(rv_entry, 'item'):
        rv_entry = rv_entry.item()
    if isinstance(rv_entry, dict):
        rv = rv_entry.get('full_RV', None)
        err = rv_entry.get('full_RV_err', None)
        if rv is not None:
            rv = float(rv)
        if err is not None:
            err = float(err)
        return rv, err
    return None, None


def _add_emission_line_bands(fig, lines_dict: dict, yref: str = 'paper'):
    """Add semi-transparent vertical rectangles for emission line bands."""
    pal = get_palette()
    colors = [
        'rgba(255,100,100,0.10)', 'rgba(100,100,255,0.10)',
        'rgba(100,255,100,0.10)', 'rgba(255,200,100,0.10)',
        'rgba(200,100,255,0.10)', 'rgba(100,255,255,0.10)',
        'rgba(255,150,200,0.10)', 'rgba(200,200,100,0.10)',
        'rgba(150,100,100,0.10)', 'rgba(100,200,150,0.10)',
        'rgba(150,150,255,0.10)',
    ]
    for i, (name, rng) in enumerate(lines_dict.items()):
        lam_min_A = rng[0] * 10.0  # nm → Å
        lam_max_A = rng[1] * 10.0
        color = colors[i % len(colors)]
        fig.add_vrect(
            x0=lam_min_A, x1=lam_max_A,
            fillcolor=color, layer='below', line_width=0,
            annotation_text=name, annotation_position='top left',
            annotation_font=dict(size=8, color=pal['font_color']),
        )


def _epoch_colors(n: int) -> list:
    """Generate n distinct hue-spaced colors."""
    return [f'hsl({int(i * 360 / max(n, 1))},75%,55%)' for i in range(n)]


def _wilson_score_interval(k: int, n: int, z: float = 1.0) -> tuple:
    """Wilson score interval for fraction k/n."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    denom = 1 + z ** 2 / n
    center = (p + z ** 2 / (2 * n)) / denom
    margin = (z * np.sqrt((p * (1 - p) / n) + (z ** 2 / (4 * n ** 2)))) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


# ─────────────────────────────────────────────────────────────────────────────
# ΔRV Analysis Pipeline (cached)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data
def cached_load_drv_analysis(settings_hash_val: str):
    """
    Build the comprehensive ΔRV analysis DataFrame used by all RV analysis plots.

    Returns (df, drverr_map, rv_epoch_cache, ordered_lines).
    """
    cfg = _load_ccf_settings()
    lines_default = cfg.get('emission_lines_default', {})
    star_cfg = {s['star_name']: s for s in cfg.get('stars', [])}
    ordered_lines = list(lines_default.keys())

    obs = get_obs_manager()
    drverr_map = {}       # (star_name, line_key) → sigma_A
    rv_epoch_cache = {}   # (star_name, line_key) → [(ep, rv, err), ...]

    rows = []
    for star_name in specs.star_names:
        star = obs.load_star_instance(star_name, to_print=False)
        epochs = star.get_all_epoch_numbers()
        scfg = star_cfg.get(star_name, {})
        skip_epochs = scfg.get('skip_epochs', [])
        skip_lines = scfg.get('skip_emission_lines', {})

        # Detect if star has cleaned spectra → contaminated
        has_cleaned = False
        for ep in epochs:
            d = star.load_property('cleaned_normalized_flux', ep, 'COMBINED')
            if d is not None:
                has_cleaned = True
                break
        is_clean_bool = not has_cleaned

        row = {
            'Star': star_name,
            'Clean': '\u2713' if is_clean_bool else 'X',
            'is_clean_bool': is_clean_bool,
        }

        for lk in ordered_lines:
            # Check per-star skips
            skip_ep_for_line = skip_lines.get(lk, [])
            rv_vals = []
            for ep in epochs:
                if ep in skip_epochs:
                    continue
                if ep in skip_ep_for_line or 0 in skip_ep_for_line:
                    continue
                rv_prop = star.load_property('RVs', ep, 'COMBINED')
                if rv_prop is None or lk not in rv_prop:
                    continue
                rv_val, rv_err = _extract_rv(rv_prop[lk])
                if rv_val is None or rv_val == 0.0:
                    continue
                if rv_err is None:
                    rv_err = np.nan
                rv_vals.append((ep, rv_val, rv_err))

            rv_epoch_cache[(star_name, lk)] = rv_vals

            if len(rv_vals) < 2:
                row[f'dRV | {lk}'] = np.nan
                drverr_map[(star_name, lk)] = np.nan
                continue

            # Find min/max RV
            ep_min, rv_min, err_min = min(rv_vals, key=lambda t: t[1])
            ep_max, rv_max, err_max = max(rv_vals, key=lambda t: t[1])
            dRV = abs(rv_max - rv_min)
            row[f'dRV | {lk}'] = dRV

            # Combined error (quadrature)
            if np.isfinite(err_min) and np.isfinite(err_max):
                sigma_A = np.sqrt(err_min ** 2 + err_max ** 2)
            else:
                sigma_A = np.nan
            drverr_map[(star_name, lk)] = sigma_A

        # Row statistics
        drvs = [v for k, v in row.items() if isinstance(k, str) and k.startswith('dRV | ')]
        valid_drvs = [v for v in drvs if np.isfinite(v)]
        row['Mean \u0394RV'] = float(np.mean(valid_drvs)) if valid_drvs else np.nan
        row['Std \u0394RV'] = float(np.std(valid_drvs)) if valid_drvs else np.nan
        rows.append(row)

    df = pd.DataFrame(rows)
    civ_col = f'dRV | C IV 5808-5812'
    if civ_col in df.columns:
        df = df.sort_values(civ_col, ascending=False, na_position='last').reset_index(drop=True)

    return df, drverr_map, rv_epoch_cache, ordered_lines


def _is_significant_binary(star_name: str, line_key: str, drv_val: float,
                           threshold_val: float, drverr_map: dict) -> bool:
    """Binary = both dRV >= threshold AND dRV >= 4*sigma."""
    if not (pd.notna(drv_val) and np.isfinite(drv_val)):
        return False
    sigma_A = drverr_map.get((star_name, line_key), np.nan)
    if not np.isfinite(sigma_A):
        return False
    return bool(float(drv_val) >= threshold_val) and bool(float(drv_val) >= 4.0 * float(sigma_A))


# ─────────────────────────────────────────────────────────────────────────────
# Top-level tabs
# ─────────────────────────────────────────────────────────────────────────────
tab_xshooter, tab_nres = st.tabs(['X-Shooter', 'NRES'])


# =============================================================================
# X-SHOOTER TAB
# =============================================================================
with tab_xshooter:
    xs_sub = st.tabs(['Spectra', 'RV Analysis', 'Emission Lines', 'CCF Outputs', 'Grid Results'])

    # ─────────────────────────────────────────────────────────────────────────
    # X-Shooter > Spectra
    # ─────────────────────────────────────────────────────────────────────────
    with xs_sub[0]:
        st.markdown('### Spectra Viewer')

        # Selectors
        col_star, col_band = st.columns(2)
        with col_star:
            xs_star = st.selectbox('Star', specs.star_names, key='xsp_star')
        with col_band:
            xs_band = st.selectbox('Band', BANDS, key='xsp_band')

        obs = get_obs_manager()
        star_obj = obs.load_star_instance(xs_star, to_print=False)
        epochs = star_obj.get_all_epoch_numbers()

        # Toggles
        col_t1, col_t2, col_t3 = st.columns(3)
        with col_t1:
            use_cleaned = st.checkbox('Use cleaned spectra', value=True, key='xsp_clean')
        with col_t2:
            show_lines = st.checkbox('Show emission line bands', value=False, key='xsp_lines')
        with col_t3:
            xs_log = st.checkbox('Log y-scale', value=False, key='xsp_log')

        # ── Normalized spectra overlay ────────────────────────────────────
        st.markdown('#### Normalized Spectra (all epochs)')
        fig_norm = go.Figure()
        colors = _epoch_colors(len(epochs))
        for i, ep in enumerate(epochs):
            data = _load_normalized_spec(xs_star, ep, xs_band, use_cleaned)
            if data is None:
                continue
            wave = np.asarray(data.get('wavelengths', data.get('wave', [])))
            flux = np.asarray(data.get('normalized_flux', data.get('flux', [])))
            if len(wave) == 0:
                continue
            # Wavelengths from normalized_flux properties are in Å already
            fig_norm.add_trace(go.Scatter(
                x=wave, y=flux, mode='lines',
                line=dict(color=colors[i], width=1),
                name=f'Epoch {ep}',
            ))

        if show_lines:
            _add_emission_line_bands(fig_norm, _get_emission_lines())

        yaxis_kw = dict(yaxis_type='log') if xs_log else {}
        apply_theme(fig_norm, title=dict(text=f'{xs_star} — {xs_band} — all epochs'),
                    height=480, xaxis_title='Wavelength (Å)',
                    yaxis_title='Normalised flux', **yaxis_kw)
        st.plotly_chart(fig_norm, use_container_width=True)
        st.caption('Normalized spectra overlaid for all available epochs.')

        # Save button
        save_col, _ = st.columns([1, 3])
        if save_col.button('💾 Save to plots/', key='save_spec_plot'):
            os.makedirs(os.path.join(_ROOT, 'plots'), exist_ok=True)
            import plotly.io as pio
            path = os.path.join(_ROOT, 'plots',
                                f'{xs_star.replace(" ", "_")}_{xs_band}_spectra.png')
            pio.write_image(fig_norm, path, scale=2)
            st.success(f'Saved: {path}')

        # ── Raw spectrum viewer ───────────────────────────────────────────
        with st.expander('Raw Spectrum Viewer', expanded=False):
            ep_raw = st.selectbox('Epoch', epochs, key='xsp_raw_ep')
            raw_data = _load_raw_spec(xs_star, ep_raw, xs_band)

            col_r1, col_r2, col_r3 = st.columns(3)
            with col_r1:
                raw_log = st.checkbox('Log scale', value=False, key='xsp_raw_log')
            with col_r2:
                raw_cont = st.checkbox('Show continuum', value=False, key='xsp_raw_cont')
            with col_r3:
                raw_lines = st.checkbox('Show emission lines', value=False, key='xsp_raw_lines')

            if raw_data is not None:
                wave_A, flux, err = raw_data
                fig_raw = go.Figure()

                plot_flux = flux.copy()
                if raw_log:
                    mask = plot_flux > 0
                    plot_flux = np.where(mask, plot_flux, np.nan)

                fig_raw.add_trace(go.Scatter(
                    x=wave_A, y=plot_flux, mode='lines',
                    line=dict(color=COLOR_SINGLE, width=1),
                    name=f'Epoch {ep_raw}',
                ))

                if raw_cont:
                    cont_data = _load_continuum(xs_star, ep_raw, xs_band)
                    if cont_data is not None:
                        cont_flux = np.asarray(
                            cont_data.get('interpolated_flux', cont_data)
                            if isinstance(cont_data, dict) else cont_data
                        )
                        if cont_flux.ndim > 0 and len(cont_flux) == len(wave_A):
                            fig_raw.add_trace(go.Scatter(
                                x=wave_A, y=cont_flux, mode='lines',
                                line=dict(color='#DAA520', width=1.5, dash='dash'),
                                name='Continuum',
                            ))

                if raw_lines:
                    _add_emission_line_bands(fig_raw, _get_emission_lines())

                yax_kw = dict(yaxis_type='log') if raw_log else {}
                apply_theme(fig_raw,
                            title=dict(text=f'{xs_star} — {xs_band} — Epoch {ep_raw} (raw)'),
                            height=420, xaxis_title='Wavelength (Å)',
                            yaxis_title='Flux', **yax_kw)
                st.plotly_chart(fig_raw, use_container_width=True)
                st.caption('Raw FITS spectrum (wavelengths converted from nm to Å).')
            else:
                st.info('No raw data available for this star/epoch/band.')

        # ── Error spectrum viewer ─────────────────────────────────────────
        with st.expander('Error Spectrum', expanded=False):
            ep_err = st.selectbox('Epoch', epochs, key='xsp_err_ep')
            raw_err_data = _load_raw_spec(xs_star, ep_err, xs_band)
            if raw_err_data is not None and raw_err_data[2] is not None:
                wave_A, _, err = raw_err_data
                fig_err = go.Figure()
                fig_err.add_trace(go.Scatter(
                    x=wave_A, y=err, mode='lines',
                    line=dict(color='#E25A53', width=1),
                    name='Error',
                ))
                apply_theme(fig_err,
                            title=dict(text=f'{xs_star} — {xs_band} — Epoch {ep_err} (error)'),
                            height=350, xaxis_title='Wavelength (Å)',
                            yaxis_title='Error')
                st.plotly_chart(fig_err, use_container_width=True)
                st.caption('Error spectrum from FITS ERR extension.')
            else:
                st.info('No error data available for this epoch.')

        # ── 2D Spectral Image ─────────────────────────────────────────────
        with st.expander('2D Spectral Image', expanded=False):
            ep_2d = st.selectbox('Epoch', epochs, key='xsp_2d_ep')
            try:
                fit_2d = star_obj.load_2D_observation(ep_2d, xs_band)
                if fit_2d is not None and fit_2d.primary_data is not None:
                    img = fit_2d.primary_data
                    # Get wavelength axis from 1D observation
                    raw_1d = _load_raw_spec(xs_star, ep_2d, xs_band)
                    x_vals = raw_1d[0] if raw_1d is not None else None

                    c_vmin, c_vmax = st.columns(2)
                    with c_vmin:
                        vmin = st.number_input('ValMin', value=float(np.nanpercentile(img, 5)),
                                               key='xsp_2d_vmin')
                    with c_vmax:
                        vmax = st.number_input('ValMax', value=float(np.nanpercentile(img, 95)),
                                               key='xsp_2d_vmax')

                    fig_2d = go.Figure(go.Heatmap(
                        z=img, x=x_vals, colorscale='Viridis',
                        zmin=vmin, zmax=vmax,
                        colorbar=dict(title='Counts'),
                    ))
                    apply_theme(fig_2d,
                                title=dict(text=f'{xs_star} — {xs_band} — Epoch {ep_2d} (2D)'),
                                height=400, xaxis_title='Wavelength (Å)',
                                yaxis_title='Spatial pixel')
                    st.plotly_chart(fig_2d, use_container_width=True)
                    st.caption('2D spectral image from FITS primary extension.')
                else:
                    st.info('No 2D data available for this epoch/band.')
            except Exception as e:
                st.info(f'Could not load 2D image: {e}')

        # ── Epoch Consistency Check ───────────────────────────────────────
        with st.expander('Epoch Consistency Check', expanded=False):
            if len(epochs) >= 2:
                col_e1, col_e2 = st.columns(2)
                with col_e1:
                    ep1 = st.selectbox('Epoch A', epochs, index=0, key='xsp_cons_ep1')
                with col_e2:
                    ep2 = st.selectbox('Epoch B', epochs,
                                       index=min(1, len(epochs) - 1), key='xsp_cons_ep2')
                col_w1, col_w2 = st.columns(2)
                with col_w1:
                    wmin = st.number_input('λ min (Å)', value=5750, key='xsp_cons_wmin')
                with col_w2:
                    wmax = st.number_input('λ max (Å)', value=5950, key='xsp_cons_wmax')

                d1 = _load_normalized_spec(xs_star, ep1, xs_band, use_cleaned)
                d2 = _load_normalized_spec(xs_star, ep2, xs_band, use_cleaned)
                if d1 is not None and d2 is not None:
                    w1 = np.asarray(d1.get('wavelengths', []))
                    f1 = np.asarray(d1.get('normalized_flux', []))
                    w2 = np.asarray(d2.get('wavelengths', []))
                    f2 = np.asarray(d2.get('normalized_flux', []))

                    mask1 = (w1 >= wmin) & (w1 <= wmax)
                    mask2 = (w2 >= wmin) & (w2 <= wmax)

                    if np.any(mask1) and np.any(mask2):
                        from scipy.interpolate import interp1d
                        # Interpolate ep2 onto ep1's wavelength grid
                        f2_interp = interp1d(w2[mask2], f2[mask2], kind='linear',
                                             bounds_error=False, fill_value=np.nan)
                        f2_on_w1 = f2_interp(w1[mask1])
                        valid = np.isfinite(f2_on_w1) & np.isfinite(f1[mask1])

                        fig_cons = go.Figure()
                        fig_cons.add_trace(go.Scatter(
                            x=f1[mask1][valid], y=f2_on_w1[valid],
                            mode='markers', marker=dict(size=3, color=COLOR_SINGLE, opacity=0.5),
                            name='Flux comparison',
                        ))
                        # Identity line
                        fmin = min(f1[mask1][valid].min(), f2_on_w1[valid].min())
                        fmax = max(f1[mask1][valid].max(), f2_on_w1[valid].max())
                        fig_cons.add_trace(go.Scatter(
                            x=[fmin, fmax], y=[fmin, fmax], mode='lines',
                            line=dict(color='#DAA520', dash='dash', width=1),
                            name='1:1',
                        ))
                        apply_theme(fig_cons,
                                    title=dict(text=f'Epoch {ep1} vs {ep2} ({wmin}–{wmax} Å)'),
                                    height=400,
                                    xaxis_title=f'Flux (Epoch {ep1})',
                                    yaxis_title=f'Flux (Epoch {ep2})')
                        st.plotly_chart(fig_cons, use_container_width=True)
                        st.caption('Flux comparison between two epochs in a wavelength window.')
                    else:
                        st.warning('No data in the selected wavelength window.')
                else:
                    st.info('Normalized spectra not available for one of the selected epochs.')
            else:
                st.info('Need at least 2 epochs for consistency check.')

        # ── Extreme RV Comparison ─────────────────────────────────────────
        with st.expander('Extreme RV Comparison', expanded=False):
            st.markdown('Overlay of the highest and lowest RV epochs.')
            primary_line = settings.get('primary_line', 'C IV 5808-5812')

            # Find min/max RV epochs
            rv_by_ep = {}
            for ep in epochs:
                rv_prop = _load_rv_property(xs_star, ep)
                if rv_prop is None or primary_line not in rv_prop:
                    continue
                rv_val, _ = _extract_rv(rv_prop[primary_line])
                if rv_val is not None and rv_val != 0.0:
                    rv_by_ep[ep] = rv_val

            if len(rv_by_ep) >= 2:
                ep_min = min(rv_by_ep, key=rv_by_ep.get)
                ep_max = max(rv_by_ep, key=rv_by_ep.get)

                d_min = _load_normalized_spec(xs_star, ep_min, xs_band, use_cleaned)
                d_max = _load_normalized_spec(xs_star, ep_max, xs_band, use_cleaned)

                if d_min is not None and d_max is not None:
                    fig_ext = go.Figure()
                    w_min = np.asarray(d_min.get('wavelengths', []))
                    f_min = np.asarray(d_min.get('normalized_flux', []))
                    w_max = np.asarray(d_max.get('wavelengths', []))
                    f_max = np.asarray(d_max.get('normalized_flux', []))

                    fig_ext.add_trace(go.Scatter(
                        x=w_min, y=f_min, mode='lines',
                        line=dict(color=COLOR_SINGLE, width=1),
                        name=f'Ep {ep_min} (min RV={rv_by_ep[ep_min]:.1f} km/s)',
                    ))
                    fig_ext.add_trace(go.Scatter(
                        x=w_max, y=f_max, mode='lines',
                        line=dict(color=COLOR_BINARY, width=1),
                        name=f'Ep {ep_max} (max RV={rv_by_ep[ep_max]:.1f} km/s)',
                    ))

                    # Highlight primary emission line region
                    el_dict = _get_emission_lines()
                    if primary_line in el_dict:
                        rng = el_dict[primary_line]
                        fig_ext.add_vrect(
                            x0=rng[0] * 10, x1=rng[1] * 10,
                            fillcolor='rgba(218,165,32,0.12)', line_width=0,
                            annotation_text=primary_line,
                            annotation_position='top left',
                        )

                    apply_theme(fig_ext,
                                title=dict(text=f'{xs_star} — Extreme RV epochs'),
                                height=450, xaxis_title='Wavelength (Å)',
                                yaxis_title='Normalised flux')
                    st.plotly_chart(fig_ext, use_container_width=True)
                    st.caption(f'Min-RV epoch {ep_min} vs Max-RV epoch {ep_max} '
                               f'(ΔRV = {abs(rv_by_ep[ep_max] - rv_by_ep[ep_min]):.1f} km/s).')
                else:
                    st.info('Could not load spectra for extreme RV epochs.')
            else:
                st.info('Need at least 2 epochs with RV measurements.')

    # ─────────────────────────────────────────────────────────────────────────
    # X-Shooter > RV Analysis
    # ─────────────────────────────────────────────────────────────────────────
    with xs_sub[1]:
        st.markdown('### RV Analysis')

        sh = settings_hash(settings)
        cls_cfg = settings.get('classification', {})
        threshold = cls_cfg.get('threshold_dRV', 45.5)

        # Toggle for clean/contaminated
        rv_filter = st.radio('Star filter', ['All', 'Clean only', 'Contaminated only'],
                             horizontal=True, key='xsp_rv_filter')

        # Load data
        with st.spinner('Loading RV data...'):
            try:
                obs_delta_rv, detail = cached_load_observed_delta_rvs(sh)
            except Exception as e:
                st.error(str(e))
                st.stop()

            try:
                df_analysis, drverr_map, rv_epoch_cache, ordered_lines = \
                    cached_load_drv_analysis(sh)
            except Exception as e:
                st.error(f'Error building analysis DataFrame: {e}')
                st.stop()

        # Apply filter
        df_view = df_analysis.copy()
        if rv_filter == 'Clean only':
            df_view = df_view[df_view['is_clean_bool']].reset_index(drop=True)
        elif rv_filter == 'Contaminated only':
            df_view = df_view[~df_view['is_clean_bool']].reset_index(drop=True)

        # ── Plot 1: ΔRV Bar Chart ────────────────────────────────────────
        st.markdown('#### Peak-to-Peak ΔRV (all stars)')
        civ_col = f'dRV | C IV 5808-5812'
        if civ_col in df_view.columns:
            df_sorted = df_view.dropna(subset=[civ_col]).sort_values(
                civ_col, ascending=False).reset_index(drop=True)
            if len(df_sorted) > 0:
                names = df_sorted['Star'].tolist()
                drvs = df_sorted[civ_col].tolist()
                star_names_in_detail = set(detail.keys())
                colors = []
                for sn, d in zip(names, drvs):
                    if sn in star_names_in_detail and detail[sn].get('is_binary'):
                        colors.append(COLOR_BINARY)
                    else:
                        colors.append(COLOR_SINGLE)

                fig_bar = go.Figure(go.Bar(x=names, y=drvs, marker_color=colors))
                fig_bar.add_hline(y=threshold, line_dash='dash', line_color='#DAA520',
                                  annotation_text=f'{threshold:.1f} km/s')
                apply_theme(fig_bar,
                            title=dict(text='Peak-to-Peak ΔRV (C IV 5808-5812)'),
                            height=380, xaxis_title='Star', yaxis_title='ΔRV (km/s)',
                            xaxis_tickangle=-45)
                st.plotly_chart(fig_bar, use_container_width=True)
                st.caption('Stars sorted by ΔRV. Red = binary, blue = single. '
                           f'Threshold = {threshold:.1f} km/s.')

        # ── Plot 2: Binary Fraction vs Threshold ─────────────────────────
        st.markdown('#### Binary Fraction vs ΔRV Threshold')

        t_vals = np.arange(5, 401, 1)
        # Compute for each line
        frac_data = {}
        for lk in ordered_lines:
            col_name = f'dRV | {lk}'
            if col_name not in df_view.columns:
                continue
            fracs = []
            for t in t_vals:
                n_above = 0
                n_total = 0
                for _, row in df_view.iterrows():
                    dv = row.get(col_name)
                    if pd.notna(dv) and np.isfinite(dv):
                        n_total += 1
                        if _is_significant_binary(row['Star'], lk, dv, t, drverr_map):
                            n_above += 1
                f = n_above / max(n_total, 1)
                fracs.append(f)
            frac_data[lk] = fracs

        if frac_data:
            fig_frac = go.Figure()
            line_colors = _epoch_colors(len(frac_data))
            for i, (lk, fracs) in enumerate(frac_data.items()):
                fig_frac.add_trace(go.Scatter(
                    x=t_vals, y=fracs, mode='lines',
                    line=dict(color=line_colors[i], width=1.5),
                    name=lk,
                ))
            fig_frac.add_vline(x=threshold, line_dash='dash', line_color='#DAA520',
                               annotation_text=f'{threshold:.1f} km/s')
            apply_theme(fig_frac,
                        title=dict(text='Observed Binary Fraction vs ΔRV Threshold'),
                        height=420, xaxis_title='ΔRV threshold (km/s)',
                        yaxis_title='Binary fraction')
            st.plotly_chart(fig_frac, use_container_width=True)
            st.caption('Each curve shows fraction of stars above threshold for a given line.')

        # ── Plot 3: Binary Fraction per Emission Line ─────────────────────
        st.markdown('#### Binary Fraction per Emission Line')
        line_fracs = {}
        for lk in ordered_lines:
            col_name = f'dRV | {lk}'
            if col_name not in df_view.columns:
                continue
            n_above = 0
            n_total = 0
            for _, row in df_view.iterrows():
                dv = row.get(col_name)
                if pd.notna(dv) and np.isfinite(dv):
                    n_total += 1
                    if _is_significant_binary(row['Star'], lk, dv, threshold, drverr_map):
                        n_above += 1
            if n_total > 0:
                line_fracs[lk] = (n_above / n_total, n_above, n_total)

        if line_fracs:
            lf_names = list(line_fracs.keys())
            lf_vals = [line_fracs[k][0] for k in lf_names]
            lf_texts = [f'{line_fracs[k][1]}/{line_fracs[k][2]}' for k in lf_names]

            fig_lf = go.Figure(go.Bar(
                x=lf_names, y=lf_vals,
                marker_color=COLOR_SINGLE,
                text=lf_texts, textposition='outside',
            ))
            apply_theme(fig_lf,
                        title=dict(text=f'Binary Fraction per Line (threshold={threshold:.1f} km/s)'),
                        height=380, xaxis_title='Emission Line',
                        yaxis_title='Binary Fraction', xaxis_tickangle=-45)
            st.plotly_chart(fig_lf, use_container_width=True)
            st.caption(f'Fraction of stars classified as binary per emission line '
                       f'at {threshold:.1f} km/s threshold.')

        # ── Plot 4: Confidence Grading ────────────────────────────────────
        st.markdown('#### Confidence Grading')
        st.markdown('Stars grouped by how many lines agree on their classification.')

        confidence_data = {'Golden': [], 'Silver': [], 'Bronze': []}
        for _, row in df_view.iterrows():
            sn = row['Star']
            n_binary = 0
            n_single = 0
            n_valid = 0
            for lk in ordered_lines:
                col_name = f'dRV | {lk}'
                dv = row.get(col_name)
                if pd.notna(dv) and np.isfinite(dv):
                    n_valid += 1
                    if _is_significant_binary(sn, lk, dv, threshold, drverr_map):
                        n_binary += 1
                    else:
                        n_single += 1
            if n_valid == 0:
                continue
            agreement = max(n_binary, n_single) / n_valid
            if agreement >= 0.9:
                confidence_data['Golden'].append(sn)
            elif agreement >= 0.7:
                confidence_data['Silver'].append(sn)
            else:
                confidence_data['Bronze'].append(sn)

        grades = list(confidence_data.keys())
        grade_counts = [len(confidence_data[g]) for g in grades]
        grade_colors = ['#DAA520', '#C0C0C0', '#CD7F32']

        fig_grade = go.Figure(go.Bar(
            x=grades, y=grade_counts,
            marker_color=grade_colors,
            text=grade_counts, textposition='outside',
        ))
        apply_theme(fig_grade,
                    title=dict(text='Confidence Grading'),
                    height=350, xaxis_title='Grade', yaxis_title='Number of stars')
        st.plotly_chart(fig_grade, use_container_width=True)

        for g in grades:
            if confidence_data[g]:
                st.caption(f"**{g}** ({len(confidence_data[g])}): "
                           f"{', '.join(confidence_data[g])}")

        # ── Plot 5: Clean vs Contaminated ─────────────────────────────────
        st.markdown('#### Clean vs Contaminated Comparison')
        civ_col = f'dRV | C IV 5808-5812'
        if civ_col in df_analysis.columns:
            categories = ['All', 'Clean', 'Contaminated']
            counts_bin = []
            counts_sin = []
            for cat in categories:
                if cat == 'All':
                    sub = df_analysis
                elif cat == 'Clean':
                    sub = df_analysis[df_analysis['is_clean_bool']]
                else:
                    sub = df_analysis[~df_analysis['is_clean_bool']]
                n_b = 0
                n_s = 0
                for _, row in sub.iterrows():
                    dv = row.get(civ_col)
                    if pd.notna(dv) and np.isfinite(dv):
                        if _is_significant_binary(row['Star'], 'C IV 5808-5812', dv,
                                                  threshold, drverr_map):
                            n_b += 1
                        else:
                            n_s += 1
                counts_bin.append(n_b)
                counts_sin.append(n_s)

            fig_cc = go.Figure()
            fig_cc.add_trace(go.Bar(
                x=categories, y=counts_bin,
                marker_color=COLOR_BINARY, name='Binary',
                text=counts_bin, textposition='auto',
            ))
            fig_cc.add_trace(go.Bar(
                x=categories, y=counts_sin,
                marker_color=COLOR_SINGLE, name='Single',
                text=counts_sin, textposition='auto',
            ))
            apply_theme(fig_cc,
                        title=dict(text='Binary/Single by Sample'),
                        height=380, xaxis_title='Sample', yaxis_title='Count',
                        barmode='group')
            st.plotly_chart(fig_cc, use_container_width=True)
            st.caption('Binary vs single counts for all, clean-only, and contaminated-only samples.')

        # ── Plot 6: RV vs Epoch (per star) ────────────────────────────────
        st.markdown('#### RV vs Epoch')
        star_rv = st.selectbox('Star', specs.star_names, key='xsp_rv_star')
        rv_arr = detail.get(star_rv, {}).get('rv', np.array([]))
        err_arr = detail.get(star_rv, {}).get('rv_err', np.array([]))

        fig_rvep = go.Figure()
        if len(rv_arr) > 0:
            is_bin = detail.get(star_rv, {}).get('is_binary')
            marker_color = COLOR_BINARY if is_bin else COLOR_SINGLE
            fig_rvep.add_trace(go.Scatter(
                x=list(range(1, len(rv_arr) + 1)), y=rv_arr,
                error_y=dict(type='data', array=err_arr, visible=True),
                mode='markers+lines',
                marker=dict(size=8, color=marker_color),
                name='RV (C IV 5808-5812)',
            ))
        apply_theme(fig_rvep,
                    title=dict(text=f'{star_rv} — RV per epoch'),
                    height=380, xaxis_title='Observation #', yaxis_title='RV (km/s)')
        st.plotly_chart(fig_rvep, use_container_width=True)
        if len(rv_arr) > 0:
            drv_star = detail.get(star_rv, {}).get('best_dRV', 0)
            st.caption(f'ΔRV = {drv_star:.1f} km/s. '
                       f'{"Binary" if detail.get(star_rv, {}).get("is_binary") else "Single"}.')

        # ── Plot 7: Corner Plot (ΔRV correlation matrix) ──────────────────
        st.markdown('#### ΔRV Correlation Matrix')
        st.markdown('Pairwise scatter/histogram of ΔRV values across emission lines.')

        # Filter lines with enough data
        valid_lines = []
        for lk in ordered_lines:
            col_name = f'dRV | {lk}'
            if col_name in df_view.columns:
                n_valid = df_view[col_name].dropna().shape[0]
                if n_valid >= 3:
                    valid_lines.append(lk)

        corner_lines = st.multiselect('Lines to include', valid_lines,
                                      default=valid_lines[:5] if len(valid_lines) > 5 else valid_lines,
                                      key='xsp_corner_lines')

        if len(corner_lines) >= 2:
            n = len(corner_lines)
            fig_corner = make_subplots(rows=n, cols=n,
                                       horizontal_spacing=0.03, vertical_spacing=0.03)

            for i, li in enumerate(corner_lines):
                for j, lj in enumerate(corner_lines):
                    col_i = f'dRV | {li}'
                    col_j = f'dRV | {lj}'
                    xi = df_view[col_i].dropna().values
                    xj = df_view[col_j].dropna().values

                    if i == j:
                        # Histogram on diagonal
                        fig_corner.add_trace(go.Histogram(
                            x=xi, nbinsx=12,
                            marker_color=COLOR_SINGLE, opacity=0.7,
                            showlegend=False,
                        ), row=i + 1, col=j + 1)
                    else:
                        # Scatter off-diagonal
                        # Align arrays by star
                        common = df_view[['Star', col_i, col_j]].dropna()
                        colors_corner = [COLOR_BINARY if detail.get(s, {}).get('is_binary')
                                         else COLOR_SINGLE
                                         for s in common['Star']]
                        fig_corner.add_trace(go.Scatter(
                            x=common[col_j].values, y=common[col_i].values,
                            mode='markers',
                            marker=dict(size=5, color=colors_corner, opacity=0.7),
                            showlegend=False,
                            hovertext=common['Star'].values,
                        ), row=i + 1, col=j + 1)

                    # Axis labels only on edges
                    if j == 0:
                        fig_corner.update_yaxes(title_text=li[:12], row=i + 1, col=j + 1,
                                                title_font=dict(size=8))
                    if i == n - 1:
                        fig_corner.update_xaxes(title_text=lj[:12], row=i + 1, col=j + 1,
                                                title_font=dict(size=8))

            apply_theme(fig_corner,
                        title=dict(text='ΔRV Correlation Matrix'),
                        height=200 * n, showlegend=False)
            st.plotly_chart(fig_corner, use_container_width=True)
            st.caption('Diagonal: histograms. Off-diagonal: pairwise scatter. '
                       'Red = binary, blue = single.')
        elif len(corner_lines) == 1:
            st.info('Select at least 2 lines for the correlation matrix.')

    # ─────────────────────────────────────────────────────────────────────────
    # X-Shooter > Emission Lines
    # ─────────────────────────────────────────────────────────────────────────
    with xs_sub[2]:
        st.markdown('### Emission Line ΔRV Table')

        sh = settings_hash(settings)
        try:
            df_el, drverr_el, _, el_lines = cached_load_drv_analysis(sh)
        except Exception as e:
            st.error(str(e))
            st.stop()

        # Build display table
        display_cols = ['Star', 'Clean']
        for lk in el_lines:
            col_name = f'dRV | {lk}'
            if col_name in df_el.columns:
                display_cols.append(col_name)
        display_cols.extend(['Mean ΔRV', 'Std ΔRV'])

        df_display = df_el[display_cols].copy()
        # Round numeric columns
        for c in df_display.columns:
            if c not in ['Star', 'Clean', 'is_clean_bool']:
                df_display[c] = df_display[c].round(1)

        st.dataframe(df_display, use_container_width=True, height=600)
        st.caption('ΔRV (km/s) per star and emission line. '
                   'Clean = ✓ means no spatial contamination detected.')

        # Per-line comparison bar chart
        st.markdown('#### Per-Line ΔRV Comparison')
        el_star = st.selectbox('Star', specs.star_names, key='xsp_el_star')
        row_star = df_el[df_el['Star'] == el_star]
        if len(row_star) > 0:
            row_data = row_star.iloc[0]
            el_names = []
            el_drvs = []
            for lk in el_lines:
                col_name = f'dRV | {lk}'
                if col_name in row_data and pd.notna(row_data[col_name]):
                    el_names.append(lk)
                    el_drvs.append(row_data[col_name])

            if el_names:
                el_colors = [COLOR_BINARY if d > threshold else COLOR_SINGLE
                             for d in el_drvs]
                fig_elbar = go.Figure(go.Bar(
                    x=el_names, y=el_drvs, marker_color=el_colors,
                ))
                fig_elbar.add_hline(y=threshold, line_dash='dash', line_color='#DAA520',
                                    annotation_text=f'{threshold:.1f} km/s')
                apply_theme(fig_elbar,
                            title=dict(text=f'{el_star} — ΔRV per Line'),
                            height=380, xaxis_title='Emission Line',
                            yaxis_title='ΔRV (km/s)', xaxis_tickangle=-45)
                st.plotly_chart(fig_elbar, use_container_width=True)
                st.caption(f'Per-line ΔRV for {el_star}. '
                           f'Red = above threshold, blue = below.')
            else:
                st.info(f'No ΔRV data for {el_star}.')
        else:
            st.info(f'Star {el_star} not found in analysis.')

    # ─────────────────────────────────────────────────────────────────────────
    # X-Shooter > CCF Outputs
    # ─────────────────────────────────────────────────────────────────────────
    with xs_sub[3]:
        output_root = os.path.normpath(os.path.join(_ROOT, '..', 'output'))
        st.markdown(f'### CCF plots from `{output_root}`')
        if not os.path.isdir(output_root):
            st.info('Output directory not found.')
        else:
            star_f = st.selectbox('Filter by star', ['All'] + specs.star_names,
                                  key='xsp_ccf_star')
            pngs = []
            for sn in specs.star_names:
                d = os.path.join(output_root, sn, 'CCF')
                if os.path.isdir(d):
                    for dp, _, fns in os.walk(d):
                        for fn in fns:
                            if fn.lower().endswith('.png'):
                                pngs.append(os.path.join(dp, fn))
            if star_f != 'All':
                pngs = [p for p in pngs if star_f in p]
            st.write(f'{len(pngs)} CCF plot(s) found.')

            n_show = st.slider('Max plots to show', 3, 30, 12, key='xsp_ccf_n')
            cols = st.columns(3)
            for i, p in enumerate(pngs[:n_show]):
                cols[i % 3].image(p, caption=os.path.basename(p),
                                  use_container_width=True)
            if len(pngs) > n_show:
                st.info(f'Showing first {n_show} of {len(pngs)}.')

    # ─────────────────────────────────────────────────────────────────────────
    # X-Shooter > Grid Results
    # ─────────────────────────────────────────────────────────────────────────
    with xs_sub[4]:
        st.markdown('### Grid Search Results')

        model_sel = st.radio('Model', ['Dsilva', 'Langer'], horizontal=True,
                             key='xsp_grid_model')
        model_key = model_sel.lower()

        # Try loading from session state or disk
        result = st.session_state.get(f'result_{model_key}')
        if result is None:
            result = cached_load_grid_result(model_key)

        if result is None:
            # Try browsing results/ for files
            results_dir = os.path.join(_ROOT, 'results')
            if os.path.isdir(results_dir):
                npz_files = [f for f in os.listdir(results_dir)
                             if f.endswith('.npz') and model_key in f.lower()]
                if npz_files:
                    chosen_file = st.selectbox('Result file', npz_files,
                                               key='xsp_grid_file')
                    result = cached_load_grid_result(
                        model_key,
                        os.path.join(results_dir, chosen_file))

        if result is not None:
            try:
                fbin_grid = np.asarray(result['fbin_grid'])
                ks_p = np.asarray(result['ks_p'])
                if ks_p.ndim == 3:
                    ks_p = np.squeeze(ks_p, axis=0)
                ks_d = np.asarray(result.get('ks_D', np.zeros_like(ks_p)))
                if ks_d.ndim == 3:
                    ks_d = np.squeeze(ks_d, axis=0)

                if model_key == 'langer':
                    x_grid_key = 'sigma_grid'
                    x_label = 'σ  (velocity dispersion km/s)'
                    x_name = 'σ'
                else:
                    x_grid_key = 'pi_grid'
                    x_label = 'π  (period power-law index)'
                    x_name = 'π'

                x_grid = np.asarray(result.get(x_grid_key, result.get('pi_grid', [])))

                show_d = st.checkbox('Show K-S D statistic', value=False,
                                     key='xsp_grid_show_d')

                fig_hm = make_heatmap_fig(
                    ks_p, fbin_grid, x_grid,
                    title=f'{model_sel} — K-S p-value heatmap',
                    show_d=show_d, ks_d_2d=ks_d,
                    x_label=x_label, x_name=x_name,
                    height=520,
                )
                st.plotly_chart(fig_hm, use_container_width=True)
                st.caption(f'{model_sel} grid search result.')

                # f_bin slice at best x
                from shared import find_best_grid_point
                best_fbin, best_x, best_pval = find_best_grid_point(ks_p, fbin_grid, x_grid)
                bpi = int(np.argmin(np.abs(x_grid - best_x)))

                st.markdown(f'### p-value vs f_bin at best {x_name}={best_x:.3f}')
                fig_slice = go.Figure(go.Scatter(
                    x=fbin_grid, y=ks_p[:, bpi], mode='lines',
                    line=dict(color=COLOR_SINGLE, width=2),
                ))
                fig_slice.add_vline(x=best_fbin, line_dash='dash', line_color='#DAA520')
                apply_theme(fig_slice,
                            title=dict(text=f'p-value slice at {x_name}={best_x:.3f}'),
                            height=350, xaxis_title='f_bin',
                            yaxis_title='K-S p-value', yaxis_type='log')
                st.plotly_chart(fig_slice, use_container_width=True)
                st.caption(f'Best fit: f_bin={best_fbin:.3f}, {x_name}={best_x:.3f}, '
                           f'p={best_pval:.4f}')

                # Save button
                if st.button('💾 Save heatmap to plots/', key='save_grid_heatmap'):
                    import plotly.io as pio
                    os.makedirs(os.path.join(_ROOT, 'plots'), exist_ok=True)
                    path = os.path.join(_ROOT, 'plots',
                                        f'{model_key}_ks_pvalue_interactive.png')
                    pio.write_image(fig_hm, path, scale=2)
                    st.success(f'Saved: {path}')
            except Exception as e:
                st.error(f'Error displaying grid result: {e}')
        else:
            st.info(f'No {model_sel} grid result found. Run the grid search first '
                    f'(Bias Correction page).')


# =============================================================================
# NRES TAB
# =============================================================================
with tab_nres:
    nres_sub = st.tabs(['Spectra', 'RV Analysis', 'SNR & Quality'])

    # ─────────────────────────────────────────────────────────────────────────
    # NRES > Spectra
    # ─────────────────────────────────────────────────────────────────────────
    with nres_sub[0]:
        st.markdown('### NRES Spectra Viewer')

        nres_star = st.selectbox('Star', NRES_STARS, key='nsp_star')
        obs_nres = get_obs_manager()

        try:
            nres_obj = obs_nres.load_star_instance(nres_star, to_print=False)
            nres_epochs = nres_obj.get_all_epoch_numbers()
        except Exception as e:
            st.error(f'Could not load NRES star {nres_star}: {e}')
            nres_epochs = []

        if nres_epochs:
            nres_ep = st.selectbox('Epoch', nres_epochs, key='nsp_epoch')
            nres_spectra = nres_obj.get_all_spectra_in_epoch(nres_ep)

            if nres_spectra:
                nres_use_clean = st.checkbox('Use cleaned spectra', value=True,
                                             key='nsp_clean')

                # ── Normalized spectra overlay ────────────────────────────
                st.markdown('#### Normalized Spectra (all spectra in epoch)')
                fig_nspec = go.Figure()
                ncolors = _epoch_colors(len(nres_spectra))

                for i, sp_num in enumerate(nres_spectra):
                    try:
                        if nres_use_clean:
                            data = nres_obj.load_property('clean_normalized_flux',
                                                          nres_ep, sp_num, to_print=False)
                            if data is None:
                                data = nres_obj.load_property('normalized_flux',
                                                              nres_ep, sp_num, to_print=False)
                        else:
                            data = nres_obj.load_property('normalized_flux',
                                                          nres_ep, sp_num, to_print=False)
                    except Exception:
                        data = None

                    if data is None:
                        continue
                    wave = np.asarray(data.get('wavelengths', []))
                    flux = np.asarray(data.get('normalized_flux', []))
                    if len(wave) == 0:
                        continue

                    fig_nspec.add_trace(go.Scatter(
                        x=wave, y=flux, mode='lines',
                        line=dict(color=ncolors[i], width=1),
                        name=f'Spec {sp_num}',
                    ))

                apply_theme(fig_nspec,
                            title=dict(text=f'{nres_star} — Epoch {nres_ep} — Normalized'),
                            height=480, xaxis_title='Wavelength (Å)',
                            yaxis_title='Normalised flux')
                st.plotly_chart(fig_nspec, use_container_width=True)
                st.caption('Normalized spectra for all observations in this epoch.')

                # ── Stitched spectra (single observation) ─────────────────
                st.markdown('#### Stitched Spectrum')
                sp_sel = st.selectbox('Spectrum number', nres_spectra,
                                      key='nsp_stitch_sp')
                try:
                    wave_st, flux_st, snr_st = nres_obj.get_stitched_spectra3(
                        nres_ep, sp_sel)
                    if wave_st is not None and len(wave_st) > 0:
                        fig_stitch = go.Figure()
                        fig_stitch.add_trace(go.Scatter(
                            x=wave_st, y=flux_st, mode='lines',
                            line=dict(color=COLOR_SINGLE, width=1),
                            name='Stitched flux',
                        ))
                        apply_theme(fig_stitch,
                                    title=dict(text=f'{nres_star} — Ep {nres_ep} '
                                               f'Spec {sp_sel} (stitched)'),
                                    height=420, xaxis_title='Wavelength (Å)',
                                    yaxis_title='Flux')
                        st.plotly_chart(fig_stitch, use_container_width=True)
                        st.caption('Stitched spectrum using get_stitched_spectra3() '
                                   '(low-blaze filtering enabled).')
                    else:
                        st.info('Could not stitch spectra for this observation.')
                except Exception as e:
                    st.info(f'Stitching failed: {e}')
            else:
                st.info(f'No spectra found in epoch {nres_ep}.')
        else:
            st.info(f'No epochs found for {nres_star}.')

    # ─────────────────────────────────────────────────────────────────────────
    # NRES > RV Analysis
    # ─────────────────────────────────────────────────────────────────────────
    with nres_sub[1]:
        st.markdown('### NRES RV Analysis')

        nres_rv_star = st.selectbox('Star', NRES_STARS, key='nrv_star')
        try:
            nres_rv_obj = get_obs_manager().load_star_instance(nres_rv_star,
                                                               to_print=False)
            nres_rv_epochs = nres_rv_obj.get_all_epoch_numbers()
        except Exception:
            nres_rv_epochs = []
            nres_rv_obj = None

        if nres_rv_obj is not None and nres_rv_epochs:
            # Collect all RV measurements
            all_rvs = []  # (epoch, spectra_num, rv, err, mjd)
            for ep in nres_rv_epochs:
                spectra_nums = nres_rv_obj.get_all_spectra_in_epoch(ep)
                for sp in spectra_nums:
                    try:
                        rv_prop = nres_rv_obj.load_property('RVs', ep, sp,
                                                            to_print=False)
                        if rv_prop is None:
                            continue
                        # Look for primary line
                        for line_key in ['C IV 5808-5812', 'He II 4686']:
                            if line_key in rv_prop:
                                rv_val, rv_err = _extract_rv(rv_prop[line_key])
                                if rv_val is not None and rv_val != 0.0:
                                    # Get MJD
                                    try:
                                        fit = nres_rv_obj.load_observation(ep, sp, '1D')
                                        mjd = float(fit.header['MJD-OBS'])
                                    except Exception:
                                        mjd = float(ep)
                                    all_rvs.append((ep, sp, rv_val,
                                                    rv_err if rv_err else 0, mjd))
                                break
                    except Exception:
                        continue

            if all_rvs:
                rvs_arr = np.array(all_rvs)
                mjds = rvs_arr[:, 4]
                rvs = rvs_arr[:, 2]
                errs = rvs_arr[:, 3]
                ep_nums = rvs_arr[:, 0].astype(int)

                fig_nrv = go.Figure()
                fig_nrv.add_trace(go.Scatter(
                    x=mjds, y=rvs,
                    error_y=dict(type='data', array=errs, visible=True),
                    mode='markers',
                    marker=dict(size=6, color=COLOR_SINGLE),
                    name='Individual RVs',
                    hovertext=[f'Ep{int(r[0])} Sp{int(r[1])}' for r in rvs_arr],
                ))

                # Compute epoch means
                unique_eps = sorted(set(ep_nums))
                for ep_u in unique_eps:
                    mask = ep_nums == ep_u
                    ep_rvs = rvs[mask]
                    ep_mjds = mjds[mask]
                    if len(ep_rvs) >= 2:
                        mean_rv = np.mean(ep_rvs)
                        mean_mjd = np.mean(ep_mjds)
                        std_rv = np.std(ep_rvs)
                        fig_nrv.add_trace(go.Scatter(
                            x=[mean_mjd], y=[mean_rv],
                            error_y=dict(type='data', array=[std_rv], visible=True),
                            mode='markers',
                            marker=dict(size=12, color='#DAA520', symbol='star'),
                            name=f'Epoch {ep_u} mean',
                            showlegend=True,
                        ))

                apply_theme(fig_nrv,
                            title=dict(text=f'{nres_rv_star} — NRES RV measurements'),
                            height=420, xaxis_title='MJD', yaxis_title='RV (km/s)')
                st.plotly_chart(fig_nrv, use_container_width=True)
                st.caption('Individual measurements (dots) and epoch means (stars).')

                # Sigma summary table
                st.markdown('#### Epoch Summary')
                summary_rows = []
                for ep_u in unique_eps:
                    mask = ep_nums == ep_u
                    ep_rvs = rvs[mask]
                    summary_rows.append({
                        'Epoch': ep_u,
                        'N spectra': int(np.sum(mask)),
                        'Mean RV (km/s)': f'{np.mean(ep_rvs):.1f}',
                        'Std RV (km/s)': f'{np.std(ep_rvs):.1f}',
                        'Min RV': f'{np.min(ep_rvs):.1f}',
                        'Max RV': f'{np.max(ep_rvs):.1f}',
                    })
                st.dataframe(pd.DataFrame(summary_rows), use_container_width=True)
            else:
                st.info(f'No RV measurements found for {nres_rv_star}.')
        else:
            st.info('Could not load NRES star data.')

    # ─────────────────────────────────────────────────────────────────────────
    # NRES > SNR & Quality
    # ─────────────────────────────────────────────────────────────────────────
    with nres_sub[2]:
        st.markdown('### NRES SNR & Quality')

        nres_q_star = st.selectbox('Star', NRES_STARS, key='nq_star')
        try:
            nres_q_obj = get_obs_manager().load_star_instance(nres_q_star,
                                                              to_print=False)
            nres_q_epochs = nres_q_obj.get_all_epoch_numbers()
        except Exception:
            nres_q_epochs = []
            nres_q_obj = None

        if nres_q_obj is not None and nres_q_epochs:
            nres_q_ep = st.selectbox('Epoch', nres_q_epochs, key='nq_epoch')
            nres_q_spectra = nres_q_obj.get_all_spectra_in_epoch(nres_q_ep)

            if nres_q_spectra:
                nres_q_sp = st.selectbox('Spectrum', nres_q_spectra, key='nq_sp')

                # ── SNR vs wavelength ─────────────────────────────────────
                st.markdown('#### SNR vs Wavelength')
                try:
                    wave_snr, flux_snr, snr_arr = nres_q_obj.get_stitched_spectra3(
                        nres_q_ep, nres_q_sp)
                    if wave_snr is not None and snr_arr is not None and len(snr_arr) > 0:
                        fig_snr = go.Figure()
                        fig_snr.add_trace(go.Scatter(
                            x=wave_snr, y=snr_arr, mode='lines',
                            line=dict(color='#52B788', width=1),
                            name='SNR',
                        ))
                        apply_theme(fig_snr,
                                    title=dict(text=f'{nres_q_star} — Ep {nres_q_ep} '
                                               f'Spec {nres_q_sp} — SNR'),
                                    height=380, xaxis_title='Wavelength (Å)',
                                    yaxis_title='SNR')
                        st.plotly_chart(fig_snr, use_container_width=True)
                        st.caption('Signal-to-noise ratio from stitched spectrum.')
                    else:
                        st.info('SNR data not available.')
                except Exception as e:
                    st.info(f'Could not compute SNR: {e}')

                # ── Individual NRES Orders ────────────────────────────────
                with st.expander('Individual NRES Orders', expanded=False):
                    blaze_corr = st.checkbox('Blaze correction', value=True,
                                             key='nq_blaze')
                    try:
                        fit_nres = nres_q_obj.load_observation(nres_q_ep, nres_q_sp, '1D')
                        if fit_nres is not None:
                            flux_arr = np.flip(np.array(fit_nres.data['flux']), axis=0)
                            blaze_arr = np.flip(np.array(fit_nres.data['blaze']), axis=0)
                            wave_arr = np.flip(np.array(fit_nres.data['wavelength']), axis=0)

                            n_orders = flux_arr.shape[0]
                            # Object orders are odd indices (except WR17 ep 2,3)
                            if nres_q_star == 'WR17' and nres_q_ep in [2, 3]:
                                obj_indices = list(range(1, n_orders, 2))
                            else:
                                obj_indices = list(range(0, n_orders, 2))

                            order_sel = st.multiselect(
                                'Orders to display',
                                obj_indices,
                                default=obj_indices[:5] if len(obj_indices) > 5 else obj_indices,
                                key='nq_orders',
                            )

                            if order_sel:
                                fig_ord = go.Figure()
                                ord_colors = _epoch_colors(len(order_sel))
                                for ci, oidx in enumerate(order_sel):
                                    w = wave_arr[oidx]
                                    if blaze_corr:
                                        b = blaze_arr[oidx]
                                        b_safe = np.where(b > 0, b, 1.0)
                                        f = flux_arr[oidx] / b_safe
                                    else:
                                        f = flux_arr[oidx]
                                    fig_ord.add_trace(go.Scatter(
                                        x=w, y=f, mode='lines',
                                        line=dict(color=ord_colors[ci], width=1),
                                        name=f'Order {oidx}',
                                    ))
                                bc_label = '(blaze-corrected)' if blaze_corr else '(raw)'
                                apply_theme(fig_ord,
                                            title=dict(text=f'{nres_q_star} — Individual orders '
                                                       f'{bc_label}'),
                                            height=420, xaxis_title='Wavelength (Å)',
                                            yaxis_title='Flux')
                                st.plotly_chart(fig_ord, use_container_width=True)
                                st.caption(f'Individual NRES fiber orders '
                                           f'{"with" if blaze_corr else "without"} '
                                           f'blaze correction.')
                        else:
                            st.info('Could not load raw NRES observation.')
                    except Exception as e:
                        st.info(f'Error loading orders: {e}')

                # ── Blaze Function ────────────────────────────────────────
                with st.expander('Blaze Function', expanded=False):
                    try:
                        fit_blaze = nres_q_obj.load_observation(nres_q_ep, nres_q_sp, '1D')
                        if fit_blaze is not None:
                            blaze_data = np.flip(np.array(fit_blaze.data['blaze']), axis=0)
                            wave_data = np.flip(np.array(fit_blaze.data['wavelength']), axis=0)

                            fig_blaze = go.Figure()
                            n_o = blaze_data.shape[0]
                            bl_colors = _epoch_colors(n_o)
                            for oi in range(0, n_o, max(1, n_o // 15)):
                                fig_blaze.add_trace(go.Scatter(
                                    x=wave_data[oi], y=blaze_data[oi], mode='lines',
                                    line=dict(color=bl_colors[oi], width=1),
                                    name=f'Order {oi}',
                                    showlegend=False,
                                ))
                            apply_theme(fig_blaze,
                                        title=dict(text=f'{nres_q_star} — Blaze Functions'),
                                        height=380, xaxis_title='Wavelength (Å)',
                                        yaxis_title='Blaze')
                            st.plotly_chart(fig_blaze, use_container_width=True)
                            st.caption('Blaze function for each order, showing '
                                       'instrument response profile.')
                        else:
                            st.info('Could not load blaze data.')
                    except Exception as e:
                        st.info(f'Error loading blaze function: {e}')
            else:
                st.info(f'No spectra found in epoch {nres_q_ep}.')
        else:
            st.info(f'No data available for {nres_q_star}.')
