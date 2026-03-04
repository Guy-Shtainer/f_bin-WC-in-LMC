"""
pages/05_bias_correction.py — Bias Correction (Dsilva / Langer 2020 grid search)

Features:
  - Two-column layout: grid/orbital params left, sigma scan + live heatmap right
  - Single persistent multiprocessing Pool — no per-f_bin overhead
  - Heatmap fills in live row-by-row via imap_unordered + throttled render
  - Sigma scan mode: run N sigma values -> max-p line chart + browse slider + animated 4D + 3D stacked
  - Smart partial cache reuse: unchanged f_bin rows reused from prior result
  - All BinaryParameterConfig orbital params exposed and editable
  - User-controllable canvas dimensions (height / width in px)
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import multiprocessing as mp
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from shared import (
    inject_theme, render_sidebar, get_settings_manager,
    cached_load_observed_delta_rvs, cached_load_cadence,
    cached_load_grid_result, settings_hash,
    PLOTLY_THEME,
)

st.set_page_config(
    page_title='Bias Correction — WR Binary',
    page_icon='⚡',
    layout='wide',
)
inject_theme()
settings = render_sidebar('Bias Correction')
sm = get_settings_manager()

st.markdown('# ⚡ Bias Correction')
st.caption(
    'Monte-Carlo K-S grid search over (f_bin, π) to find the intrinsic binary fraction '
    'and period-distribution power-law index that best reproduce the observed ΔRV distribution.'
)

# ─────────────────────────────────────────────────────────────────────────────
# Canvas size (page-level — used by both Dsilva and Langer tabs)
# ─────────────────────────────────────────────────────────────────────────────
with st.expander('🖼️ Canvas size', expanded=False):
    _cs_c1, _cs_c2, _ = st.columns([0.2, 0.2, 0.6])
    canvas_height = _cs_c1.number_input(
        'Height (px)', 200, 2000, 520, 20, key='bc_canvas_height')
    canvas_width = _cs_c2.number_input(
        'Width (px, 0 = auto)', 0, 3000, 0, 50, key='bc_canvas_width')

_ch = int(canvas_height)
_cw = int(canvas_width) if int(canvas_width) > 0 else None
_use_cw = (_cw is None)

_RESULT_DIR = os.path.join(_ROOT, 'results')
_HISTORY_PATH = os.path.join(_ROOT, 'settings', 'run_history.json')

# ─────────────────────────────────────────────────────────────────────────────
# Model tabs
# ─────────────────────────────────────────────────────────────────────────────
tab_dsilva, tab_langer = st.tabs(['Dsilva (power-law)', 'Langer 2020'])


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _result_path(model: str) -> str:
    return os.path.join(_RESULT_DIR, f'{model}_result.npz')


def _stable_cfg_hash(cfg: dict) -> str:
    return hashlib.sha256(
        json.dumps(cfg, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]


def _best_point(ks_p_2d: np.ndarray, fbin_vals: np.ndarray,
                pi_vals: np.ndarray) -> tuple[float, float, float]:
    idx = int(np.argmax(ks_p_2d))
    fi  = idx // ks_p_2d.shape[1]
    pi  = idx  % ks_p_2d.shape[1]
    return float(fbin_vals[fi]), float(pi_vals[pi]), float(ks_p_2d[fi, pi])


def _make_heatmap_fig(
    ks_p_2d: np.ndarray,
    fbin_vals: np.ndarray,
    x_vals: np.ndarray,
    title: str,
    show_d: bool = False,
    ks_d_2d: np.ndarray | None = None,
    height: int = 520,
    width: int | None = None,
    x_label: str = 'π  (period power-law index)',
    y_label: str = 'f_bin  (intrinsic binary fraction)',
    x_name: str = 'π',
    best_label_fmt: str = '  f={fbin:.3f}, {x_name}={x:.2f}, p={p:.3f}',
) -> go.Figure:
    """Plotly heatmap of K-S p-value (or D-stat)."""
    z = ks_d_2d if (show_d and ks_d_2d is not None) else ks_p_2d
    colorbar_title = 'K-S D' if show_d else 'K-S p-value'

    valid = z[~np.isnan(z)]
    z_max = float(np.percentile(valid, 98)) if valid.size > 0 else 1.0
    z_min = 0.0

    best_fbin, best_x, best_pval = _best_point(ks_p_2d, fbin_vals, x_vals)

    traces: list = [
        go.Heatmap(
            z=z, x=x_vals, y=fbin_vals,
            colorscale='RdBu_r',
            zmin=z_min, zmax=z_max,
            zsmooth='best',
            colorbar=dict(title=colorbar_title, thickness=14, len=0.9),
            hovertemplate=f'{x_name}=%{{x:.3f}}<br>f_bin=%{{y:.4f}}<br>' + colorbar_title +
                          '=%{z:.4f}<extra></extra>',
        ),
        go.Contour(
            z=ks_p_2d, x=x_vals, y=fbin_vals,
            contours=dict(
                coloring='none',
                showlabels=True,
                labelfont=dict(size=10, color='white'),
                start=0.05, end=0.30, size=0.05,
            ),
            line=dict(color='white', width=1, dash='dot'),
            showscale=False,
            hoverinfo='skip',
        ),
        go.Scatter(
            x=[best_x], y=[best_fbin],
            mode='markers+text',
            marker=dict(symbol='star', size=18, color='gold',
                        line=dict(color='black', width=1)),
            text=[best_label_fmt.format(fbin=best_fbin, x_name=x_name,
                                        x=best_x, p=best_pval)],
            textposition='middle right',
            textfont=dict(color='gold', size=11),
            name='Best fit',
            showlegend=False,
        ),
    ]

    layout_kw: dict = {
        **PLOTLY_THEME,
        'title': dict(text=title, font=dict(size=14)),
        'xaxis_title': x_label,
        'yaxis_title': y_label,
        'height': height,
        'margin': dict(l=60, r=20, t=50, b=50),
    }
    if width is not None:
        layout_kw['width'] = width

    fig = go.Figure(traces)
    fig.update_layout(**layout_kw)
    return fig


def _make_max_pval_fig(
    sigma_vals: np.ndarray,
    max_pvals: list[float],
    height: int = 300,
) -> go.Figure:
    """Line chart: max K-S p-value vs sigma_single."""
    best_idx = int(np.argmax(max_pvals))
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sigma_vals, y=max_pvals,
        mode='lines+markers',
        marker=dict(size=8, color='#4A90D9'),
        line=dict(color='#4A90D9', width=2),
        hovertemplate='σ_single=%{x:.1f} km/s<br>max p=%{y:.4f}<extra></extra>',
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=[float(sigma_vals[best_idx])],
        y=[max_pvals[best_idx]],
        mode='markers+text',
        marker=dict(symbol='star', size=16, color='gold',
                    line=dict(color='black', width=1)),
        text=[f'  σ={float(sigma_vals[best_idx]):.1f}, p={max_pvals[best_idx]:.4f}'],
        textposition='middle right',
        textfont=dict(color='gold', size=11),
        showlegend=False,
    ))
    fig.update_layout(**{
        **PLOTLY_THEME,
        'title': dict(text='Max K-S p-value vs σ_single', font=dict(size=14)),
        'xaxis_title': 'σ_single (km/s)',
        'yaxis_title': 'Max K-S p-value',
        'height': height,
        'margin': dict(l=60, r=20, t=50, b=50),
    })
    return fig


def _make_3d_stacked_fig(
    ks_p_3d: np.ndarray,
    fbin_vals: np.ndarray,
    pi_vals: np.ndarray,
    sigma_vals: np.ndarray,
    height: int = 700,
    width: int | None = None,
) -> go.Figure:
    """3D stacked semi-transparent surfaces: one per sigma_single."""
    valid = ks_p_3d[~np.isnan(ks_p_3d)]
    global_zmax = float(np.percentile(valid, 98)) if valid.size > 0 else 1.0

    fig = go.Figure()
    pi_mesh, fbin_mesh = np.meshgrid(pi_vals, fbin_vals)

    n_sigma = len(sigma_vals)
    # Cap layers to avoid overly heavy plots
    max_layers = 20
    if n_sigma > max_layers:
        indices = np.linspace(0, n_sigma - 1, max_layers, dtype=int)
    else:
        indices = np.arange(n_sigma)

    sigma_min_val = float(sigma_vals[indices[0]])
    sigma_max_val = float(sigma_vals[indices[-1]])
    sigma_range = max(sigma_max_val - sigma_min_val, 1.0)

    for count, i_s in enumerate(indices):
        sigma_val = float(sigma_vals[i_s])
        # z position = actual sigma value for meaningful axis
        z_layer = np.full_like(pi_mesh, sigma_val)
        p_slice = ks_p_3d[i_s]

        fig.add_trace(go.Surface(
            x=pi_mesh, y=fbin_mesh, z=z_layer,
            surfacecolor=p_slice,
            colorscale='RdBu_r',
            cmin=0.0, cmax=global_zmax,
            opacity=0.6,
            showscale=(count == len(indices) - 1),
            colorbar=dict(title='K-S p', thickness=14, len=0.6)
            if count == len(indices) - 1 else None,
            name=f'σ={sigma_val:.1f}',
            hovertemplate=(
                f'σ_single={sigma_val:.1f} km/s<br>'
                'π=%{x:.2f}<br>f_bin=%{y:.3f}<br>p=%{surfacecolor:.4f}<extra></extra>'
            ),
        ))

    layout_kw = {
        **PLOTLY_THEME,
        'title': dict(text='3D Stacked Heatmaps (f_bin x π x σ_single)',
                       font=dict(size=14)),
        'scene': dict(
            xaxis_title='π  (period power-law index)',
            yaxis_title='f_bin  (binary fraction)',
            zaxis_title='σ_single (km/s)',
            bgcolor='white',
        ),
        'height': height,
        'margin': dict(l=10, r=10, t=50, b=10),
    }
    if width is not None:
        layout_kw['width'] = width

    fig.update_layout(**layout_kw)
    return fig


def _find_reusable_fbin(
    cached: dict,
    fbin_new: np.ndarray,
    pi_new: np.ndarray,
    sigma_new: np.ndarray,
    stable_cfg: dict,
) -> tuple[list[int], list[int]] | None:
    """
    Check if cached result shares the same pi grid and simulation parameters.
    Returns (new_indices, cache_indices) for matching f_bin values, or None.
    """
    try:
        if not np.allclose(np.asarray(cached['pi_grid']), pi_new, atol=1e-6):
            return None
        if not np.allclose(np.asarray(cached['sigma_grid']), sigma_new, atol=1e-6):
            return None
        cached_cfg = json.loads(str(cached.get('settings', '{}')))
        for k in ('n_stars_sim', 'sigma_measure', 'logP_min', 'logP_max',
                   'period_model', 'e_model', 'e_max',
                   'mass_primary_model', 'mass_primary_fixed',
                   'q_model', 'q_min', 'q_max'):
            if str(cached_cfg.get(k)) != str(stable_cfg.get(k)):
                return None
        cached_fbin = np.asarray(cached['fbin_grid'])
        new_idx, cache_idx = [], []
        for i, fb in enumerate(fbin_new):
            j = int(np.argmin(np.abs(cached_fbin - fb)))
            if np.abs(cached_fbin[j] - fb) < 1e-6:
                new_idx.append(i)
                cache_idx.append(j)
        return new_idx, cache_idx
    except Exception:
        return None


def _find_reusable_fbin_langer(
    cached: dict,
    fbin_new: np.ndarray,
    sigma_new: np.ndarray,
    stable_cfg: dict,
) -> tuple[list[int], list[int]] | None:
    """Check if a cached Langer result shares the same sigma grid and config."""
    try:
        if not np.allclose(np.asarray(cached['sigma_grid']), sigma_new, atol=1e-6):
            return None
        cached_cfg = json.loads(str(cached.get('settings', '{}')))
        for k in ('n_stars_sim', 'sigma_measure', 'logP_min', 'logP_max',
                   'period_model', 'e_model', 'e_max',
                   'mass_primary_model', 'mass_primary_fixed',
                   'q_model', 'q_min', 'q_max'):
            if str(cached_cfg.get(k)) != str(stable_cfg.get(k)):
                return None
        cached_fbin = np.asarray(cached['fbin_grid'])
        new_idx, cache_idx = [], []
        for i, fb in enumerate(fbin_new):
            j = int(np.argmin(np.abs(cached_fbin - fb)))
            if np.abs(cached_fbin[j] - fb) < 1e-6:
                new_idx.append(i)
                cache_idx.append(j)
        return new_idx, cache_idx
    except Exception:
        return None


def _append_run_history(entry: dict) -> None:
    history = []
    if os.path.exists(_HISTORY_PATH):
        try:
            with open(_HISTORY_PATH) as f:
                history = json.load(f)
        except Exception:
            pass
    history.append(entry)
    with open(_HISTORY_PATH, 'w') as f:
        json.dump(history, f, indent=2, default=str)


# ─────────────────────────────────────────────────────────────────────────────
# Dsilva tab
# ─────────────────────────────────────────────────────────────────────────────
with tab_dsilva:
    gcfg   = settings.get('grid_dsilva', {})
    simcfg = settings.get('simulation', {})
    cls    = settings.get('classification', {})
    orb    = gcfg.get('orbital', {})

    col_left, col_right = st.columns([0.30, 0.70])

    # ── Left column: grid + orbital parameters ───────────────────────────────
    with col_left:
        with st.expander('⚙️ Grid parameters', expanded=True):
            fbin_min = st.number_input(
                'f_bin min', 0.0, 0.5, float(gcfg.get('fbin_min', 0.01)), 0.01,
                key='bc_fbin_min',
                on_change=lambda: sm.save(['grid_dsilva', 'fbin_min'],
                                          value=st.session_state['bc_fbin_min']))
            fbin_max = st.number_input(
                'f_bin max', 0.5, 1.0, float(gcfg.get('fbin_max', 0.99)), 0.01,
                key='bc_fbin_max',
                on_change=lambda: sm.save(['grid_dsilva', 'fbin_max'],
                                          value=st.session_state['bc_fbin_max']))
            fbin_steps = st.number_input(
                'f_bin steps', 10, 500, int(gcfg.get('fbin_steps', 137)), 1,
                key='bc_fbin_steps',
                on_change=lambda: sm.save(['grid_dsilva', 'fbin_steps'],
                                          value=st.session_state['bc_fbin_steps']))
            pi_min = st.number_input(
                'π min', -5.0, 0.0, float(gcfg.get('pi_min', -3.0)), 0.1,
                key='bc_pi_min',
                on_change=lambda: sm.save(['grid_dsilva', 'pi_min'],
                                          value=st.session_state['bc_pi_min']))
            pi_max = st.number_input(
                'π max', 0.0, 5.0, float(gcfg.get('pi_max', 3.0)), 0.1,
                key='bc_pi_max',
                on_change=lambda: sm.save(['grid_dsilva', 'pi_max'],
                                          value=st.session_state['bc_pi_max']))
            pi_steps = st.number_input(
                'π steps', 10, 500, int(gcfg.get('pi_steps', 249)), 1,
                key='bc_pi_steps',
                on_change=lambda: sm.save(['grid_dsilva', 'pi_steps'],
                                          value=st.session_state['bc_pi_steps']))
            n_stars_sim = st.number_input(
                'N stars / point', 100, 50000, int(gcfg.get('n_stars_sim', 3000)), 100,
                key='bc_n_stars',
                on_change=lambda: sm.save(['grid_dsilva', 'n_stars_sim'],
                                          value=st.session_state['bc_n_stars']))
            sigma_meas = st.number_input(
                'σ_measure (km/s)', 0.001, 20.0,
                float(simcfg.get('sigma_measure', 1.622)), 0.001,
                format='%.3f', key='bc_sigma_meas',
                on_change=lambda: sm.save(['simulation', 'sigma_measure'],
                                          value=st.session_state['bc_sigma_meas']))

        with st.expander('🔧 Orbital parameters (Kepler)', expanded=False):
            st.caption('Parameters of the Kepler orbit randomization in the simulation.')

            # Period range
            logP_min_val = st.number_input(
                'log₁₀(P/days) min', 0.01, 10.0,
                float(orb.get('logP_min', gcfg.get('logP_min', 0.15))), 0.01,
                key='bc_logP_min',
                on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'logP_min'],
                                          value=st.session_state['bc_logP_min']))
            logP_max_val = st.number_input(
                'log₁₀(P/days) max', 0.1, 10.0,
                float(orb.get('logP_max', gcfg.get('logP_max', 5.0))), 0.1,
                key='bc_logP_max',
                on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'logP_max'],
                                          value=st.session_state['bc_logP_max']))

            st.markdown('---')
            # Eccentricity
            e_model = st.selectbox(
                'Eccentricity model', ['flat', 'zero'],
                index=['flat', 'zero'].index(orb.get('e_model', 'flat')),
                key='bc_e_model',
                on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'e_model'],
                                          value=st.session_state['bc_e_model']))
            if e_model == 'flat':
                e_max = st.number_input(
                    'e_max', 0.0, 0.99, float(orb.get('e_max', 0.9)), 0.05,
                    key='bc_e_max',
                    on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'e_max'],
                                              value=st.session_state['bc_e_max']))
            else:
                e_max = 0.0

            st.markdown('---')
            # Primary mass
            mass_model = st.selectbox(
                'Primary mass model', ['fixed', 'uniform'],
                index=['fixed', 'uniform'].index(orb.get('mass_primary_model', 'fixed')),
                key='bc_mass_model',
                on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'mass_primary_model'],
                                          value=st.session_state['bc_mass_model']))
            if mass_model == 'fixed':
                mass_fixed = st.number_input(
                    'M₁ (M☉)', 1.0, 200.0, float(orb.get('mass_primary_fixed', 10.0)), 1.0,
                    key='bc_mass_fixed',
                    on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'mass_primary_fixed'],
                                              value=st.session_state['bc_mass_fixed']))
                mass_range = (float(mass_fixed), float(mass_fixed))
            else:
                mass_fixed = 10.0
                _mr = orb.get('mass_primary_range', [10.0, 20.0])
                mc1, mc2 = st.columns(2)
                mass_min_v = mc1.number_input(
                    'M₁ min', 1.0, 200.0, float(_mr[0]), 1.0, key='bc_mass_min',
                    on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'mass_primary_range'],
                                              value=[st.session_state['bc_mass_min'],
                                                     st.session_state.get('bc_mass_max', _mr[1])]))
                mass_max_v = mc2.number_input(
                    'M₁ max', 1.0, 200.0, float(_mr[1]), 1.0, key='bc_mass_max',
                    on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'mass_primary_range'],
                                              value=[st.session_state.get('bc_mass_min', _mr[0]),
                                                     st.session_state['bc_mass_max']]))
                mass_range = (float(mass_min_v), float(mass_max_v))

            st.markdown('---')
            # Mass ratio q = M2/M1
            q_model = st.selectbox(
                'Mass ratio q model', ['flat', 'langer'],
                index=['flat', 'langer'].index(orb.get('q_model', 'flat')),
                key='bc_q_model',
                on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'q_model'],
                                          value=st.session_state['bc_q_model']))
            _qr = orb.get('q_range', [0.1, 2.0])
            qc1, qc2 = st.columns(2)
            q_min_v = qc1.number_input(
                'q min', 0.01, 10.0, float(_qr[0]), 0.01, key='bc_q_min',
                on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'q_range'],
                                          value=[st.session_state['bc_q_min'],
                                                 st.session_state.get('bc_q_max', _qr[1])]))
            q_max_v = qc2.number_input(
                'q max', 0.01, 10.0, float(_qr[1]), 0.1, key='bc_q_max',
                on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'q_range'],
                                          value=[st.session_state.get('bc_q_min', _qr[0]),
                                                 st.session_state['bc_q_max']]))
            if q_model == 'langer':
                langer_q_mu = st.number_input(
                    'Langer q mean', 0.01, 5.0,
                    float(orb.get('langer_q_mu', 0.7)), 0.05,
                    key='bc_lq_mu',
                    on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'langer_q_mu'],
                                              value=st.session_state['bc_lq_mu']))
                langer_q_sig = st.number_input(
                    'Langer q sigma', 0.01, 5.0,
                    float(orb.get('langer_q_sigma', 0.2)), 0.05,
                    key='bc_lq_sig',
                    on_change=lambda: sm.save(['grid_dsilva', 'orbital', 'langer_q_sigma'],
                                              value=st.session_state['bc_lq_sig']))
            else:
                langer_q_mu = 0.7
                langer_q_sig = 0.2

    # ── Right column: sigma scan + actions + display ─────────────────────────
    with col_right:
        with st.expander('🎚️ σ_single scan (intrinsic single-star scatter)', expanded=True):
            scan_sigma = st.toggle('Scan σ_single over a range', key='bc_scan_sigma')
            if scan_sigma:
                _sigma_default = float(simcfg.get('sigma_single', 5.5))
                _sc1, _sc2, _sc3 = st.columns(3)
                sigma_min = _sc1.number_input(
                    'σ_single min (km/s)', 0.1, 500.0,
                    max(0.1, _sigma_default - 2.0), 0.1,
                    key='bc_sigma_min')
                sigma_max_val_w = _sc2.number_input(
                    'σ_single max (km/s)', 0.5, 500.0,
                    _sigma_default + 2.0, 0.1,
                    key='bc_sigma_max')
                sigma_steps = _sc3.number_input(
                    'σ_single steps', 2, 500, 5, 1, key='bc_sigma_steps')
                sigma_vals = np.linspace(max(0.1, sigma_min),
                                         max(sigma_min + 0.1, sigma_max_val_w),
                                         int(sigma_steps))
            else:
                sigma_single = st.number_input(
                    'σ_single (km/s)', 0.1, 500.0,
                    float(simcfg.get('sigma_single', 5.5)), 0.1,
                    key='bc_sigma_single',
                    on_change=lambda: sm.save(
                        ['simulation', 'sigma_single'],
                        value=st.session_state['bc_sigma_single']))
                sigma_vals = np.array([float(sigma_single)])

        # Action row
        max_proc = max(1, (os.cpu_count() or 2) - 1)
        _ac1, _ac2, _ac3, _ac4 = st.columns([0.15, 0.25, 0.30, 0.30])
        n_proc = _ac1.number_input('Workers', 1, max_proc, max_proc, key='bc_nproc')
        view_mode = _ac2.radio('View', ['K-S p-value', 'K-S D-statistic'],
                               horizontal=True, key='bc_view_mode')
        show_d = view_mode == 'K-S D-statistic'
        run_btn  = _ac3.button('▶️ Run Bias Correction', type='primary', key='bc_run')
        load_btn = _ac4.button('📂 Load cached result', key='bc_load')

        # Display slots
        progress_slot      = st.empty()
        status_slot        = st.empty()
        max_pval_line_slot = st.empty()
        sigma_browse_slot  = st.empty()
        heatmap_slot       = st.empty()
        result_slot        = st.empty()

    # ── Stable config (used for partial reuse check) ──────────────────────────
    stable_cfg = {
        'n_stars_sim':        int(n_stars_sim),
        'sigma_measure':      float(sigma_meas),
        'logP_min':           float(logP_min_val),
        'logP_max':           float(logP_max_val),
        'period_model':       'powerlaw',
        'e_model':            str(e_model),
        'e_max':              float(e_max),
        'mass_primary_model': str(mass_model),
        'mass_primary_fixed': float(mass_fixed),
        'q_model':            str(q_model),
        'q_min':              float(q_min_v),
        'q_max':              float(q_max_v),
        'primary_line':       settings.get('primary_line', 'C IV 5808-5812'),
        'threshold_dRV':      cls.get('threshold_dRV', 45.5),
        'sigma_factor':       cls.get('sigma_factor', 4.0),
    }

    fbin_vals = np.linspace(float(fbin_min), float(fbin_max), int(fbin_steps))
    pi_vals   = np.linspace(float(pi_min),   float(pi_max),   int(pi_steps))

    # ── Load cached result if requested ──────────────────────────────────────
    if load_btn:
        cached = cached_load_grid_result('dsilva')
        if cached is not None:
            st.session_state['bc_result'] = cached
            status_slot.success('Loaded cached result from results/dsilva_result.npz')
        else:
            status_slot.warning('No cached result found at results/dsilva_result.npz')

    # ── Run grid ──────────────────────────────────────────────────────────────
    if run_btn:
        sh = settings_hash(settings)
        try:
            obs_delta_rv, _ = cached_load_observed_delta_rvs(sh)
            cadence_list, cadence_weights = cached_load_cadence(sh)
        except Exception as e:
            status_slot.error(f'Failed to load observations: {e}')
            st.stop()

        from wr_bias_simulation import (
            SimulationConfig, BinaryParameterConfig, _single_grid_task,
        )

        bin_cfg = BinaryParameterConfig(
            logP_min=float(logP_min_val),
            logP_max=float(logP_max_val),
            period_model='powerlaw',
            e_model=str(e_model),
            e_max=float(e_max),
            mass_primary_model=str(mass_model),
            mass_primary_fixed=float(mass_fixed),
            mass_primary_range=tuple(mass_range),
            q_model=str(q_model),
            q_range=(float(q_min_v), float(q_max_v)),
            langer_q_mu=float(langer_q_mu),
            langer_q_sigma=float(langer_q_sig),
        )

        # ── Check for partial reuse from existing result ───────────────────
        cached_existing = None
        reuse_info = None
        existing_path = _result_path('dsilva')
        if os.path.exists(existing_path):
            try:
                cached_existing = dict(np.load(existing_path, allow_pickle=True))
                sigma_new_arr = np.array([float(s) for s in sigma_vals])
                reuse_info = _find_reusable_fbin(
                    cached_existing, fbin_vals, pi_vals, sigma_new_arr, stable_cfg)
            except Exception:
                cached_existing = None

        if reuse_info:
            reuse_new_idx, reuse_cache_idx = reuse_info
            n_reused = len(reuse_new_idx)
            status_slot.info(
                f'♻️ Reusing {n_reused}/{len(fbin_vals)} f_bin rows from cached result. '
                f'Running {len(fbin_vals) - n_reused} new f_bin values.'
            )
        else:
            reuse_new_idx, reuse_cache_idx = [], []
            n_reused = 0

        # Pre-allocate full result arrays
        n_sigma = len(sigma_vals)
        n_fbin  = len(fbin_vals)
        n_pi    = len(pi_vals)
        accumulated_ks_p = np.full((n_sigma, n_fbin, n_pi), np.nan)
        accumulated_ks_D = np.full_like(accumulated_ks_p, np.nan)

        # Fill in reused rows from cached result
        if reuse_info and cached_existing is not None:
            cached_ks_p = np.asarray(cached_existing['ks_p'])
            cached_ks_D = np.asarray(cached_existing['ks_D'])
            for new_i, cache_i in zip(reuse_new_idx, reuse_cache_idx):
                accumulated_ks_p[:, new_i, :] = cached_ks_p[:, cache_i, :]
                accumulated_ks_D[:, new_i, :] = cached_ks_D[:, cache_i, :]

        # Identify missing f_bin indices to compute
        reuse_set        = set(reuse_new_idx)
        missing_fbin_idx = [i for i in range(n_fbin) if i not in reuse_set]

        # Total rows to compute (for progress bar)
        n_rows_total = n_sigma * len(missing_fbin_idx)
        rows_done    = 0
        t_start      = time.time()

        if n_rows_total == 0:
            progress_slot.progress(1.0, text='All rows reused from cache.')
            status_slot.success('All f_bin rows already computed — no new work needed.')
        else:
            pi_to_idx = {}
            for i, pv in enumerate(pi_vals):
                pi_to_idx[round(float(pv), 10)] = i

            fbin_to_global = {}
            for gj in missing_fbin_idx:
                fbin_to_global[round(float(fbin_vals[gj]), 10)] = gj

            seed_base = 1234
            last_render_time = 0.0

            # ── Single persistent Pool for the ENTIRE run ──────────────────
            with mp.Pool(processes=int(n_proc)) as pool:
                for i_sigma, sigma in enumerate(sigma_vals):
                    sim_cfg_obj = SimulationConfig(
                        n_stars=int(n_stars_sim),
                        sigma_single=float(sigma),
                        sigma_measure=float(sigma_meas),
                        cadence_library=cadence_list,
                        cadence_weights=cadence_weights,
                    )

                    tasks = []
                    for gj in missing_fbin_idx:
                        for i_pi, pv in enumerate(pi_vals):
                            tasks.append((
                                float(fbin_vals[gj]),
                                float(pv),
                                float(sigma),
                                sim_cfg_obj,
                                bin_cfg,
                                obs_delta_rv,
                                'powerlaw',
                                seed_base,
                            ))
                            seed_base += 1

                    completed_per_fbin = {gj: 0 for gj in missing_fbin_idx}

                    for fb, pi_ret, sigma_ret, D, p in pool.imap_unordered(
                            _single_grid_task, tasks, chunksize=max(1, n_pi // 4)):
                        gj    = fbin_to_global[round(fb, 10)]
                        i_pi  = pi_to_idx[round(pi_ret, 10)]

                        accumulated_ks_p[i_sigma, gj, i_pi] = p
                        accumulated_ks_D[i_sigma, gj, i_pi] = D

                        completed_per_fbin[gj] += 1

                        if completed_per_fbin[gj] == n_pi:
                            rows_done += 1

                            elapsed = time.time() - t_start
                            eta_str = ''
                            if rows_done > 1 and rows_done < n_rows_total:
                                eta = elapsed / rows_done * (n_rows_total - rows_done)
                                eta_str = f'  —  ETA {int(eta)}s'

                            progress_slot.progress(
                                rows_done / n_rows_total,
                                text=(f'σ {i_sigma+1}/{n_sigma}, '
                                      f'f_bin row {rows_done}/{n_rows_total}  '
                                      f'(σ_single = {sigma:.1f} km/s){eta_str}')
                            )

                            now = time.time()
                            if now - last_render_time > 1.0 or rows_done == n_rows_total:
                                last_render_time = now
                                cur_p = accumulated_ks_p[i_sigma]
                                cur_p_disp = np.where(np.isnan(cur_p), 0.0, cur_p)
                                cur_D_disp = np.where(
                                    np.isnan(accumulated_ks_D[i_sigma]),
                                    0.0, accumulated_ks_D[i_sigma])
                                heatmap_slot.plotly_chart(
                                    _make_heatmap_fig(
                                        cur_p_disp, fbin_vals, pi_vals,
                                        title=f'K-S p-value  (σ_single = {sigma:.1f} km/s)',
                                        show_d=show_d,
                                        ks_d_2d=cur_D_disp,
                                        height=_ch, width=_cw,
                                    ),
                                    use_container_width=_use_cw,
                                )

                                bf, bp, bpv = _best_point(cur_p_disp, fbin_vals, pi_vals)
                                status_slot.markdown(
                                    f'σ = **{sigma:.1f}** km/s  →  '
                                    f'best f_bin = **{bf:.4f}**, π = **{bp:.3f}**, '
                                    f'K-S p = **{bpv:.4f}**'
                                )

                    # ── Checkpoint: save partial result after each sigma slice ──
                    if rows_done == n_rows_total or (rows_done > 0 and rows_done % max(1, len(missing_fbin_idx)) == 0):
                        os.makedirs(_RESULT_DIR, exist_ok=True)
                        np.savez(
                            _result_path('dsilva') + '.partial',
                            fbin_grid=fbin_vals, pi_grid=pi_vals,
                            sigma_grid=sigma_vals,
                            ks_p=accumulated_ks_p, ks_D=accumulated_ks_D,
                            config_hash=_stable_cfg_hash(stable_cfg),
                            settings=np.array(json.dumps(stable_cfg)),
                            timestamp=np.array(_dt.datetime.now().isoformat()),
                        )

        elapsed_total = time.time() - t_start
        if n_rows_total > 0:
            progress_slot.progress(1.0, text=f'Done in {elapsed_total:.0f}s.')

        # ── Save combined result ───────────────────────────────────────────
        os.makedirs(_RESULT_DIR, exist_ok=True)
        chash = _stable_cfg_hash({**stable_cfg,
                                   'fbin_min': float(fbin_min),
                                   'fbin_max': float(fbin_max),
                                   'fbin_steps': int(fbin_steps),
                                   'pi_min': float(pi_min),
                                   'pi_max': float(pi_max),
                                   'pi_steps': int(pi_steps),
                                   'sigma_vals': sigma_vals.tolist()})
        full_result = {
            'fbin_grid':  fbin_vals,
            'pi_grid':    pi_vals,
            'sigma_grid': sigma_vals,
            'ks_p':       accumulated_ks_p,
            'ks_D':       accumulated_ks_D,
        }
        np.savez(
            _result_path('dsilva'),
            **full_result,
            config_hash=chash,
            settings=np.array(json.dumps(stable_cfg)),
            obs_delta_rv=obs_delta_rv,
            timestamp=np.array(_dt.datetime.now().isoformat()),
        )
        cached_load_grid_result.clear()
        st.session_state['bc_result'] = full_result
        st.session_state['result_dsilva'] = full_result
        # Clean up partial checkpoint
        _partial = _result_path('dsilva') + '.partial.npz'
        if os.path.exists(_partial):
            os.remove(_partial)

        _append_run_history({
            'timestamp':     _dt.datetime.now().isoformat(),
            'model':         'dsilva_powerlaw',
            'config_hash':   chash,
            'config':        stable_cfg,
            'elapsed_s':     round(elapsed_total, 1),
            'result_file':   _result_path('dsilva'),
            'n_reused_fbin': n_reused,
        })

        status_slot.success(
            f'Saved to results/dsilva_result.npz  '
            f'({n_reused} f_bin rows reused, '
            f'{len(fbin_vals) - n_reused} computed in {elapsed_total:.0f}s)'
        )

    # ── Display result (always shown when result exists) ─────────────────────
    result = st.session_state.get('bc_result') or st.session_state.get('result_dsilva')

    if result is None:
        result = cached_load_grid_result('dsilva')
        if result is not None:
            st.session_state['bc_result'] = result

    if result is not None:
        fbin_g  = np.asarray(result['fbin_grid'])
        pi_g    = np.asarray(result['pi_grid'])
        sigma_g = np.asarray(result['sigma_grid'])
        ks_p_3d = np.asarray(result['ks_p'])
        ks_D_3d = np.asarray(result['ks_D'])

        # Ensure 3D shape
        if ks_p_3d.ndim == 2:
            ks_p_3d = ks_p_3d[np.newaxis, ...]
            ks_D_3d = ks_D_3d[np.newaxis, ...]

        # Compute max p-value per sigma slice
        max_pvals = [float(np.nanmax(ks_p_3d[i_s]))
                     for i_s in range(len(sigma_g))]
        best_sig_idx = int(np.argmax(max_pvals))

        # Show max-pval line chart if multiple sigma values
        if len(sigma_g) > 1:
            max_pval_line_slot.plotly_chart(
                _make_max_pval_fig(sigma_g, max_pvals, height=280),
                use_container_width=True,
                key='bc_max_pval_line',
            )

            # Sigma browse slider
            sigma_options = [f'{float(s):.1f}' for s in sigma_g]
            selected_sigma_str = sigma_browse_slot.select_slider(
                'Browse σ_single heatmaps',
                options=sigma_options,
                value=sigma_options[best_sig_idx],
                key='bc_sigma_browse',
            )
            display_idx = sigma_options.index(selected_sigma_str)
        else:
            display_idx = 0

        # Show heatmap for the selected sigma slice
        # (skip when run_btn was just clicked — live heatmap already rendered)
        if not run_btn:
            heatmap_slot.plotly_chart(
                _make_heatmap_fig(
                    ks_p_3d[display_idx], fbin_g, pi_g,
                    title=(f'K-S p-value  '
                           f'(σ_single = {float(sigma_g[display_idx]):.1f} km/s)'),
                    show_d=show_d,
                    ks_d_2d=ks_D_3d[display_idx],
                    height=_ch, width=_cw,
                ),
                use_container_width=_use_cw,
            )

        # Best across ALL sigma slices
        flat_best = int(np.argmax(ks_p_3d))
        si = flat_best // (ks_p_3d.shape[1] * ks_p_3d.shape[2])
        fi = (flat_best % (ks_p_3d.shape[1] * ks_p_3d.shape[2])) // ks_p_3d.shape[2]
        pi_i = flat_best % ks_p_3d.shape[2]
        best_fbin_v  = float(fbin_g[fi])
        best_pi_v    = float(pi_g[pi_i])
        best_pval_v  = float(ks_p_3d[si, fi, pi_i])
        best_sigma_v = float(sigma_g[si])

        bartzakos = cls.get('bartzakos_binaries', 3)
        total_pop = cls.get('total_population', 28)

        sh_curr = settings_hash(settings)
        try:
            obs_drv, _ = cached_load_observed_delta_rvs(sh_curr)
            n_det = int(np.sum(obs_drv > cls.get('threshold_dRV', 45.5)))
        except Exception:
            n_det = 0

        # ── Marginalization + HDI68 (Dsilva 2023 style) ─────────────────
        from wr_bias_simulation import compute_hdi68

        # Marginalize: sum over other dimensions → 1D posteriors
        _has_sigma_scan = len(sigma_g) > 1

        # 1D posterior for f_bin: sum over σ and π
        post_fbin = np.sum(ks_p_3d, axis=(0, 2))  # shape: (n_fbin,)
        mode_fbin, lo_fbin, hi_fbin = compute_hdi68(fbin_g, post_fbin)

        # 1D posterior for π: sum over σ and f_bin
        post_pi = np.sum(ks_p_3d, axis=(0, 1))  # shape: (n_pi,)
        mode_pi, lo_pi, hi_pi = compute_hdi68(pi_g, post_pi)

        # 1D posterior for σ_single (only if multiple σ values scanned)
        if _has_sigma_scan:
            post_sigma = np.sum(ks_p_3d, axis=(1, 2))  # shape: (n_sigma,)
            mode_sigma, lo_sigma, hi_sigma = compute_hdi68(sigma_g, post_sigma)
        else:
            mode_sigma = float(sigma_g[0])
            lo_sigma = hi_sigma = mode_sigma

        # Format errors as +upper/-lower
        def _fmt_err(mode, lo, hi):
            return f'{mode:.4f}' + f' ^{{+{hi - mode:.4f}}}_{{-{mode - lo:.4f}}}'

        result_slot.markdown(
            f'**Best fit (HDI68):**  '
            f'f_bin = `{mode_fbin:.4f}` '
            f'(+{hi_fbin - mode_fbin:.4f} / -{mode_fbin - lo_fbin:.4f}),  '
            f'π = `{mode_pi:.4f}` '
            f'(+{hi_pi - mode_pi:.4f} / -{mode_pi - lo_pi:.4f})'
            + (f',  σ = `{mode_sigma:.1f}` '
               f'(+{hi_sigma - mode_sigma:.1f} / -{mode_sigma - lo_sigma:.1f}) km/s'
               if _has_sigma_scan else
               f',  σ = `{mode_sigma:.1f}` km/s (fixed)')
            + f'  \nK-S p = `{best_pval_v:.6f}`  \n'
            f'**Observed fraction:**  '
            f'({n_det}+{bartzakos})/{total_pop} = '
            f'**{(n_det+bartzakos)/total_pop*100:.1f}%**'
        )

        # ── Corner Plot ──────────────────────────────────────────────────
        st.markdown('---')
        st.markdown('### Marginalized Posteriors (Corner Plot)')

        from plotly.subplots import make_subplots as _corner_subplots

        _n_params = 3 if _has_sigma_scan else 2
        _param_names = ['f_bin', 'π']
        _param_grids = [fbin_g, pi_g]
        _param_posts = [post_fbin, post_pi]
        _param_modes = [mode_fbin, mode_pi]
        _param_los = [lo_fbin, lo_pi]
        _param_his = [hi_fbin, hi_pi]

        if _has_sigma_scan:
            _param_names.append('σ_single')
            _param_grids.append(sigma_g)
            _param_posts.append(post_sigma)
            _param_modes.append(mode_sigma)
            _param_los.append(lo_sigma)
            _param_his.append(hi_sigma)

        fig_corner = _corner_subplots(
            rows=_n_params, cols=_n_params,
            horizontal_spacing=0.06, vertical_spacing=0.06,
        )

        for i in range(_n_params):
            # Diagonal: 1D posterior
            _post_norm = _param_posts[i] / float(np.trapezoid(_param_posts[i], _param_grids[i])) \
                if float(np.trapezoid(_param_posts[i], _param_grids[i])) > 0 else _param_posts[i]

            fig_corner.add_trace(go.Scatter(
                x=_param_grids[i], y=_post_norm,
                mode='lines', line=dict(color='#4A90D9', width=2),
                showlegend=False,
            ), row=i + 1, col=i + 1)

            # HDI68 shading
            _mask_hdi = (_param_grids[i] >= _param_los[i]) & (_param_grids[i] <= _param_his[i])
            _x_hdi = _param_grids[i][_mask_hdi]
            _y_hdi = _post_norm[_mask_hdi]
            if len(_x_hdi) > 0:
                fig_corner.add_trace(go.Scatter(
                    x=np.concatenate([_x_hdi, _x_hdi[::-1]]),
                    y=np.concatenate([_y_hdi, np.zeros(len(_y_hdi))]),
                    fill='toself', fillcolor='rgba(74,144,217,0.3)',
                    line=dict(width=0), showlegend=False,
                ), row=i + 1, col=i + 1)

            # Mode line
            fig_corner.add_vline(
                x=_param_modes[i], line_dash='dash',
                line_color='#E25A53', line_width=1.5,
                row=i + 1, col=i + 1,
            )

            # Off-diagonal: 2D marginalized heatmaps (lower triangle only)
            for j in range(i):
                # Marginalize over all other dimensions to get 2D
                axes_to_sum = [k for k in range(ks_p_3d.ndim) if k not in (
                    # Map param index to array axis:
                    # σ=axis0, f_bin=axis1, π=axis2
                    [1, 2, 0][j],
                    [1, 2, 0][i],
                )]
                if axes_to_sum:
                    _2d = np.sum(ks_p_3d, axis=tuple(axes_to_sum))
                else:
                    _2d = ks_p_3d.copy()

                # The axes mapping: param 0=f_bin→axis1, param 1=π→axis2, param 2=σ→axis0
                # We need _2d[j_axis, i_axis] → x=param_j, y=param_i
                # After summing, the remaining axes are in the order they appear
                _axis_map = {0: 1, 1: 2, 2: 0}  # param_idx → ks_p_3d axis
                _remaining = sorted([_axis_map[j], _axis_map[i]])
                # _2d shape corresponds to _remaining axes
                # We want x=param_j (cols), y=param_i (rows)
                if _axis_map[j] == _remaining[0]:
                    _z = _2d.T  # transpose so x=first remaining, y=second
                else:
                    _z = _2d

                fig_corner.add_trace(go.Heatmap(
                    x=_param_grids[j], y=_param_grids[i],
                    z=_z,
                    colorscale='Viridis', showscale=False,
                    hovertemplate=f'{_param_names[j]}=%{{x:.4f}}<br>'
                                 f'{_param_names[i]}=%{{y:.4f}}<br>'
                                 f'p-sum=%{{z:.4f}}<extra></extra>',
                ), row=i + 1, col=j + 1)

                # Best-fit marker
                fig_corner.add_trace(go.Scatter(
                    x=[_param_modes[j]], y=[_param_modes[i]],
                    mode='markers',
                    marker=dict(symbol='star', size=10, color='gold',
                                line=dict(color='black', width=1)),
                    showlegend=False,
                ), row=i + 1, col=j + 1)

        # Axis labels (bottom row and left column)
        for i in range(_n_params):
            fig_corner.update_xaxes(title_text=_param_names[i],
                                     row=_n_params, col=i + 1)
            if i > 0:
                fig_corner.update_yaxes(title_text=_param_names[i],
                                         row=i + 1, col=1)

        # Hide upper triangle
        for i in range(_n_params):
            for j in range(i + 1, _n_params):
                fig_corner.update_xaxes(visible=False, row=i + 1, col=j + 1)
                fig_corner.update_yaxes(visible=False, row=i + 1, col=j + 1)

        fig_corner.update_layout(
            **PLOTLY_THEME,
            height=250 * _n_params,
            width=250 * _n_params,
            showlegend=False,
            margin=dict(l=60, r=20, t=30, b=60),
        )
        st.plotly_chart(fig_corner, use_container_width=True, key='bc_corner_plot')
        st.caption(
            f'Marginalized posteriors following Dsilva et al. (2023). '
            f'**Diagonal:** 1D posteriors with mode (dashed red) and '
            f'68% HDI (blue shading). '
            f'**Off-diagonal:** 2D marginalized K-S p-value sums with '
            f'best-fit marked (gold star). '
            f'f_bin = {mode_fbin:.4f} '
            f'(+{hi_fbin-mode_fbin:.4f}/-{mode_fbin-lo_fbin:.4f}), '
            f'π = {mode_pi:.4f} '
            f'(+{hi_pi-mode_pi:.4f}/-{mode_pi-lo_pi:.4f})'
            + (f', σ = {mode_sigma:.1f} '
               f'(+{hi_sigma-mode_sigma:.1f}/-{mode_sigma-lo_sigma:.1f}) km/s'
               if _has_sigma_scan else '') + '.'
        )

        # ── Import simulation functions for analysis plots ─────────────────
        from wr_bias_simulation import (
            SimulationConfig, BinaryParameterConfig,
            simulate_delta_rv_sample, _simulate_rv_sample_full,
            simulate_with_params, ks_two_sample,
        )

        # Load observed data for analysis plots
        sh_analysis = settings_hash(settings)
        try:
            obs_drv_analysis, obs_detail = cached_load_observed_delta_rvs(sh_analysis)
            cadence_list_a, cadence_weights_a = cached_load_cadence(sh_analysis)
            _has_obs = True
        except Exception:
            _has_obs = False

        if _has_obs:
            thresh_dRV = float(cls.get('threshold_dRV', 45.5))

            # Build shared configs
            _bin_cfg_explore = BinaryParameterConfig(
                logP_min=float(logP_min_val),
                logP_max=float(logP_max_val),
                period_model='powerlaw',
                e_model=str(e_model),
                e_max=float(e_max),
                mass_primary_model=str(mass_model),
                mass_primary_fixed=float(mass_fixed),
                mass_primary_range=tuple(mass_range),
                q_model=str(q_model),
                q_range=(float(q_min_v), float(q_max_v)),
                langer_q_mu=float(langer_q_mu),
                langer_q_sigma=float(langer_q_sig),
            )

            # ── Simulate at best-fit for analysis plots ────────────────
            _sim_cfg_gap = SimulationConfig(
                n_stars=int(n_stars_sim),
                sigma_single=float(best_sigma_v),
                sigma_measure=float(sigma_meas),
                cadence_library=cadence_list_a,
                cadence_weights=cadence_weights_a,
            )
            if 'bc_gap_sim' not in st.session_state:
                rng_gap = np.random.default_rng(99)
                st.session_state['bc_gap_sim'] = simulate_with_params(
                    best_fbin_v, best_pi_v,
                    _sim_cfg_gap, _bin_cfg_explore, rng_gap,
                )
            gap_sim = st.session_state['bc_gap_sim']

            gap_drv = gap_sim['delta_rv']
            gap_is_bin = gap_sim['is_binary']
            gap_idx_bin = gap_sim['idx_bin']

            intrinsic_fbin = float(gap_is_bin.mean())
            detected_mask = gap_drv > thresh_dRV
            observed_fbin = float(detected_mask.mean())
            missed_count = int(np.sum(gap_is_bin & ~detected_mask))
            detected_bin_count = int(np.sum(gap_is_bin & detected_mask))
            total_bin = int(gap_is_bin.sum())

            # Classify binaries for both logP and missed-binaries plots
            _bin_drv = gap_drv[gap_idx_bin] if gap_idx_bin.size > 0 else np.array([])
            _bin_detected_mask = _bin_drv > thresh_dRV
            _bin_missed_mask = ~_bin_detected_mask

            # ── logP distribution + Intrinsic vs Observed fraction ───────
            st.markdown('---')
            _lp_col, _bf_col = st.columns(2)

            with _lp_col:
                st.markdown('### Period Distribution  (log P)')

                # Use simulated periods from gap_sim
                _CLR_DETECTED = '#E25A53'   # tomato red
                _CLR_MISSED   = '#F5A623'   # amber/orange

                fig_logP = go.Figure()

                if gap_sim['P_days'].size > 0:
                    _logP_det = np.log10(gap_sim['P_days'][_bin_detected_mask]) if np.any(_bin_detected_mask) else np.array([])
                    _logP_mis = np.log10(gap_sim['P_days'][_bin_missed_mask]) if np.any(_bin_missed_mask) else np.array([])

                    if _logP_det.size > 0:
                        fig_logP.add_trace(go.Histogram(
                            x=_logP_det, nbinsx=35,
                            histnorm='probability density',
                            name=f'Detected ({_logP_det.size})',
                            marker_color=_CLR_DETECTED, opacity=0.6,
                        ))
                    if _logP_mis.size > 0:
                        fig_logP.add_trace(go.Histogram(
                            x=_logP_mis, nbinsx=35,
                            histnorm='probability density',
                            name=f'Missed ({_logP_mis.size})',
                            marker_color=_CLR_MISSED, opacity=0.6,
                        ))

                fig_logP.add_vline(x=float(logP_min_val), line_dash='dash',
                                   line_color='#888', line_width=1.5,
                                   annotation_text='logP_min',
                                   annotation_position='top left',
                                   annotation_font_color='#888')
                fig_logP.add_vline(x=float(logP_max_val), line_dash='dash',
                                   line_color='#888', line_width=1.5,
                                   annotation_text='logP_max',
                                   annotation_position='top right',
                                   annotation_font_color='#888')
                fig_logP.update_layout(**{
                    **PLOTLY_THEME,
                    'barmode': 'overlay',
                    'title': dict(text=f'Simulated Period Distribution  (π = {best_pi_v:.3f})',
                                  font=dict(size=14)),
                    'xaxis_title': 'log₁₀(P / days)',
                    'yaxis_title': 'Probability density',
                    'height': 400,
                    'margin': dict(l=60, r=20, t=50, b=50),
                    'legend': dict(x=0.65, y=0.95),
                })
                st.plotly_chart(fig_logP, use_container_width=True, key='bc_logP_hist')
                st.caption(
                    'Period distribution of simulated binaries at the best-fit model. '
                    'Red: detected binaries (ΔRV above threshold). '
                    'Amber: missed binaries (below threshold). '
                    'Missed systems are concentrated at longer periods. '
                    'Dashed lines mark the logP bounds used in the simulation.'
                )

            with _bf_col:
                st.markdown('### Observed Binary Fraction vs Threshold')

                # Compute binary fraction as a function of ΔRV threshold
                _n_sim = len(gap_drv)
                _thresh_arr = np.linspace(0, float(np.max(gap_drv) * 1.05), 200)
                _fbin_curve = np.array([float(np.sum(gap_drv > t)) / _n_sim
                                        for t in _thresh_arr])

                # Also compute fraction of binaries detected and singles mis-classified
                _bin_drv_all = gap_drv[gap_is_bin]
                _sin_drv_all = gap_drv[~gap_is_bin]
                _missed_bin_curve = np.array(
                    [float(np.sum(_bin_drv_all <= t)) / _n_sim for t in _thresh_arr])
                _false_pos_curve = np.array(
                    [float(np.sum(_sin_drv_all > t)) / _n_sim for t in _thresh_arr])

                fig_gap = go.Figure()

                # Shaded region: missed binaries (left of threshold)
                fig_gap.add_trace(go.Scatter(
                    x=_thresh_arr, y=_missed_bin_curve,
                    fill='tozeroy', fillcolor='rgba(242,166,35,0.25)',
                    line=dict(width=0), mode='lines',
                    name='Missed binaries', showlegend=True,
                ))

                # Shaded region: false positives / singles above threshold (right of threshold)
                if np.any(_false_pos_curve > 0):
                    fig_gap.add_trace(go.Scatter(
                        x=_thresh_arr, y=_false_pos_curve,
                        fill='tozeroy', fillcolor='rgba(74,144,217,0.25)',
                        line=dict(width=0), mode='lines',
                        name='Singles above threshold', showlegend=True,
                    ))

                # Observed f_bin curve
                fig_gap.add_trace(go.Scatter(
                    x=_thresh_arr, y=_fbin_curve,
                    mode='lines',
                    name='Observed f_bin(threshold)',
                    line=dict(color='#4A90D9', width=2.5),
                ))

                # Intrinsic f_bin horizontal line
                fig_gap.add_hline(
                    y=intrinsic_fbin, line_dash='dot',
                    line_color='#E25A53', line_width=2,
                    annotation_text=f'Intrinsic f_bin = {intrinsic_fbin:.1%}',
                    annotation_position='top left',
                    annotation_font=dict(size=11, color='#E25A53'),
                )

                # Vertical line at current threshold
                fig_gap.add_vline(
                    x=thresh_dRV, line_dash='dash',
                    line_color='#F5A623', line_width=2,
                    annotation_text=f'Threshold = {thresh_dRV} km/s',
                    annotation_position='top right',
                    annotation_font=dict(size=11, color='#F5A623'),
                )

                # Mark the observed f_bin at the threshold
                fig_gap.add_trace(go.Scatter(
                    x=[thresh_dRV], y=[observed_fbin],
                    mode='markers+text',
                    marker=dict(size=12, color='#FFD700', symbol='star',
                                line=dict(width=1, color='#fff')),
                    text=[f'{observed_fbin:.1%}'],
                    textposition='top left',
                    textfont=dict(size=12, color='#FFD700'),
                    name=f'Observed @ {thresh_dRV} km/s',
                    showlegend=True,
                ))

                # Gap annotation between intrinsic and observed
                gap_pct = intrinsic_fbin - observed_fbin
                fig_gap.add_annotation(
                    x=thresh_dRV + 15,
                    y=(intrinsic_fbin + observed_fbin) / 2,
                    text=f'Gap: {gap_pct:.1%}<br>({missed_count} missed / {total_bin} binaries)',
                    showarrow=False,
                    font=dict(size=11, color='#F5A623'),
                    bgcolor='rgba(255,255,255,0.9)',
                    bordercolor='#F5A623',
                    borderwidth=1,
                    borderpad=4,
                )
                # Arrow connecting intrinsic to observed at threshold
                fig_gap.add_annotation(
                    x=thresh_dRV, y=intrinsic_fbin,
                    ax=thresh_dRV, ay=observed_fbin,
                    xref='x', yref='y', axref='x', ayref='y',
                    showarrow=True, arrowhead=3,
                    arrowwidth=2, arrowcolor='#F5A623',
                )

                fig_gap.update_layout(**{
                    **PLOTLY_THEME,
                    'title': dict(
                        text='Binary Fraction vs ΔRV Threshold',
                        font=dict(size=14)),
                    'xaxis_title': 'ΔRV threshold (km/s)',
                    'yaxis_title': 'Fraction of sample',
                    'height': 400,
                    'margin': dict(l=60, r=80, t=50, b=50),
                    'showlegend': True,
                    'legend': dict(x=0.55, y=0.95, font=dict(size=10)),
                    'yaxis': dict(range=[0, min(1.0, intrinsic_fbin * 1.5)]),
                })
                st.plotly_chart(fig_gap, use_container_width=True, key='bc_gap_chart')
                st.caption(
                    f'Observed binary fraction as a function of ΔRV threshold. '
                    f'The blue curve shows the fraction of stars classified as '
                    f'binary at each threshold. The dashed red line is the '
                    f'intrinsic f_bin = {intrinsic_fbin:.1%}. At our threshold '
                    f'({thresh_dRV} km/s), the observed fraction is '
                    f'{observed_fbin:.1%} — a gap of {gap_pct:.1%} due to '
                    f'{missed_count} undetectable binaries. '
                    f'Amber shading shows missed binaries; blue shading shows '
                    f'singles scattered above each threshold.'
                )

            # ── Binary Orbital Parameter Histograms ─────────────────────
            st.markdown('---')
            st.markdown('### Binary Orbital Properties')

            _mb_view = st.radio(
                'Show populations',
                ['Compare detected vs missed', 'Detected binaries only',
                 'Missed binaries only', 'All binaries (combined)'],
                horizontal=True, key='bc_mb_view',
            )

            # Extract orbital params for detected and missed
            def _safe_mask(arr, mask):
                return arr[mask] if arr.size > 0 else np.array([])

            P_det = _safe_mask(gap_sim['P_days'], _bin_detected_mask)
            P_mis = _safe_mask(gap_sim['P_days'], _bin_missed_mask)
            e_det = _safe_mask(gap_sim['e'], _bin_detected_mask)
            e_mis = _safe_mask(gap_sim['e'], _bin_missed_mask)
            q_det = _safe_mask(gap_sim['q'], _bin_detected_mask)
            q_mis = _safe_mask(gap_sim['q'], _bin_missed_mask)
            K1_det = _safe_mask(gap_sim['K1'], _bin_detected_mask)
            K1_mis = _safe_mask(gap_sim['K1'], _bin_missed_mask)
            M1_det = _safe_mask(gap_sim['M1'], _bin_detected_mask)
            M1_mis = _safe_mask(gap_sim['M1'], _bin_missed_mask)
            i_det = np.degrees(_safe_mask(gap_sim['i_rad'], _bin_detected_mask))
            i_mis = np.degrees(_safe_mask(gap_sim['i_rad'], _bin_missed_mask))

            # New: omega, T0, M2
            _has_omega = 'omega' in gap_sim
            if _has_omega:
                omega_det = np.degrees(_safe_mask(gap_sim['omega'], _bin_detected_mask))
                omega_mis = np.degrees(_safe_mask(gap_sim['omega'], _bin_missed_mask))
                T0_det = _safe_mask(gap_sim['T0'], _bin_detected_mask)
                T0_mis = _safe_mask(gap_sim['T0'], _bin_missed_mask)
            else:
                omega_det = omega_mis = T0_det = T0_mis = np.array([])

            M2_det = q_det * M1_det if q_det.size > 0 and M1_det.size > 0 else np.array([])
            M2_mis = q_mis * M1_mis if q_mis.size > 0 and M1_mis.size > 0 else np.array([])

            # All binaries (combined) arrays
            P_all = gap_sim['P_days']
            e_all = gap_sim['e']
            q_all = gap_sim['q']
            K1_all = gap_sim['K1']
            M1_all = gap_sim['M1']
            i_all = np.degrees(gap_sim['i_rad'])
            omega_all = np.degrees(gap_sim['omega']) if _has_omega else np.array([])
            T0_all = gap_sim['T0'] if _has_omega else np.array([])
            M2_all = q_all * M1_all if q_all.size > 0 else np.array([])

            from plotly.subplots import make_subplots

            _param_titles = [
                'log₁₀(P / days)', 'Eccentricity', 'Mass ratio q',
                'K₁ (km/s)', 'M₁ (M⊙)', 'M₂ (M⊙)',
                'Inclination (°)', 'ω (°)', 'T₀ (rad)',
            ]
            _x_labels = [
                'log₁₀(P / days)', 'e', 'q = M₂/M₁',
                'K₁ (km/s)', 'M₁ (M⊙)', 'M₂ (M⊙)',
                'i (degrees)', 'ω (degrees)', 'T₀ (rad)',
            ]
            _n_panels = 9
            _n_cols = 3
            _n_rows = 3
            _nbins_hist = 30

            fig_mb = make_subplots(rows=_n_rows, cols=_n_cols,
                                   subplot_titles=_param_titles,
                                   horizontal_spacing=0.08, vertical_spacing=0.10)

            _CLR_ALL = '#52B788'  # green for combined

            def _add_hist(fig, row, col, data, name, color, show_legend):
                if data.size == 0:
                    return
                fig.add_trace(go.Histogram(
                    x=data, nbinsx=_nbins_hist,
                    histnorm='probability density',
                    name=name,
                    marker_color=color, opacity=0.6,
                    legendgroup=name,
                    showlegend=show_legend,
                ), row=row, col=col)

            def _pos(idx):
                """Convert 0-indexed panel to (row, col)."""
                return (idx // _n_cols + 1, idx % _n_cols + 1)

            if _mb_view == 'All binaries (combined)':
                _data_sets = [
                    np.log10(P_all) if P_all.size > 0 else P_all,
                    e_all, q_all, K1_all, M1_all, M2_all, i_all,
                    omega_all, T0_all,
                ]
                for pi, d in enumerate(_data_sets):
                    r, c = _pos(pi)
                    _add_hist(fig_mb, r, c, d, 'All binaries', _CLR_ALL, pi == 0)
            else:
                _det_data = [
                    np.log10(P_det) if P_det.size > 0 else P_det,
                    e_det, q_det, K1_det, M1_det, M2_det, i_det,
                    omega_det, T0_det,
                ]
                _mis_data = [
                    np.log10(P_mis) if P_mis.size > 0 else P_mis,
                    e_mis, q_mis, K1_mis, M1_mis, M2_mis, i_mis,
                    omega_mis, T0_mis,
                ]

                if _mb_view in ('Compare detected vs missed', 'Detected binaries only'):
                    for pi, d in enumerate(_det_data):
                        r, c = _pos(pi)
                        _add_hist(fig_mb, r, c, d, 'Detected', _CLR_DETECTED, pi == 0)

                if _mb_view in ('Compare detected vs missed', 'Missed binaries only'):
                    for pi, d in enumerate(_mis_data):
                        r, c = _pos(pi)
                        _add_hist(fig_mb, r, c, d, 'Missed', _CLR_MISSED, pi == 0)

            fig_mb.update_layout(**{
                **PLOTLY_THEME,
                'barmode': 'overlay',
                'height': 850,
                'margin': dict(l=40, r=20, t=40, b=60),
                'legend': dict(
                    orientation='h', yanchor='bottom', y=1.04,
                    xanchor='center', x=0.5,
                ),
            })
            for pi in range(_n_panels):
                r, c = _pos(pi)
                fig_mb.update_xaxes(title_text=_x_labels[pi],
                                    showgrid=False, row=r, col=c)
                fig_mb.update_yaxes(showgrid=False, row=r, col=c)
            for row_i in range(1, _n_rows + 1):
                fig_mb.update_yaxes(title_text='Prob. density', row=row_i, col=1)

            st.plotly_chart(fig_mb, use_container_width=True, key='bc_missed_binaries')
            st.caption(
                f'Orbital parameter distributions of simulated binaries at the '
                f'best-fit model (f_bin={best_fbin_v:.3f}, π={best_pi_v:.2f}). '
                f'**Detected** (red): {detected_bin_count} binaries with '
                f'ΔRV > {thresh_dRV} km/s. '
                f'**Missed** (amber): {missed_count} binaries below threshold. '
                f'Use "All binaries" to view the full population as a sanity check '
                f'that input distributions match expectations.'
            )

        # ── Model Explorer ───────────────────────────────────────────────
        if _has_obs:
            st.markdown('---')
            st.markdown('## Model Explorer')

            # Model selector
            _me_c1, _me_c2, _me_c3, _me_c4 = st.columns([0.25, 0.25, 0.25, 0.25])
            explore_fbin = _me_c1.number_input(
                'f_bin', 0.0, 1.0, best_fbin_v, 0.001, format='%.4f',
                key='bc_explore_fbin')
            explore_pi = _me_c2.number_input(
                'π', -5.0, 5.0, best_pi_v, 0.01, format='%.3f',
                key='bc_explore_pi')
            explore_sigma = _me_c3.number_input(
                'σ_single (km/s)', 0.1, 500.0, best_sigma_v, 0.1,
                key='bc_explore_sigma')
            sim_btn = _me_c4.button('Simulate model', type='primary',
                                     key='bc_sim_model')
            st.caption(
                'Pre-filled with best-fit values. Adjust to explore any model point.'
            )

            # Build configs for simulation
            _sim_cfg_explore = SimulationConfig(
                n_stars=int(n_stars_sim),
                sigma_single=float(explore_sigma),
                sigma_measure=float(sigma_meas),
                cadence_library=cadence_list_a,
                cadence_weights=cadence_weights_a,
            )

            # Auto-simulate at best fit on first visit, or re-simulate on button
            _need_sim = sim_btn or 'bc_sim_drv' not in st.session_state
            if _need_sim:
                rng_explore = np.random.default_rng(42)
                st.session_state['bc_sim_drv'] = simulate_delta_rv_sample(
                    float(explore_fbin), float(explore_pi),
                    _sim_cfg_explore, _bin_cfg_explore, rng_explore,
                )
                rng_explore2 = np.random.default_rng(42)
                rv_s, rv_b = _simulate_rv_sample_full(
                    float(explore_fbin), float(explore_pi),
                    _sim_cfg_explore, _bin_cfg_explore, rng_explore2,
                )
                st.session_state['bc_sim_rv_single'] = rv_s
                st.session_state['bc_sim_rv_binary'] = rv_b
                st.session_state['bc_explore_vals'] = (
                    float(explore_fbin), float(explore_pi), float(explore_sigma))

            sim_drv = st.session_state.get('bc_sim_drv')
            sim_rv_single = st.session_state.get('bc_sim_rv_single')
            sim_rv_binary = st.session_state.get('bc_sim_rv_binary')
            ex_fb, ex_pi, ex_sig = st.session_state.get(
                'bc_explore_vals', (best_fbin_v, best_pi_v, best_sigma_v))

            if sim_drv is not None:
                # ── 1) CDF Comparison ────────────────────────────────────────
                st.markdown('### CDF Comparison  (ΔRV)')

                obs_sorted = np.sort(obs_drv_analysis)
                obs_cdf = np.arange(1, len(obs_sorted) + 1) / len(obs_sorted)
                sim_sorted = np.sort(sim_drv)
                sim_cdf = np.arange(1, len(sim_sorted) + 1) / len(sim_sorted)

                D_val, p_val = ks_two_sample(sim_drv, obs_drv_analysis)

                fig_cdf = go.Figure()
                fig_cdf.add_trace(go.Scatter(
                    x=obs_sorted, y=obs_cdf,
                    mode='lines', name='Observed',
                    line=dict(color='#4A90D9', width=2.5),
                    hovertemplate='ΔRV=%{x:.1f} km/s<br>CDF=%{y:.3f}<extra>Observed</extra>',
                ))
                fig_cdf.add_trace(go.Scatter(
                    x=sim_sorted, y=sim_cdf,
                    mode='lines', name='Simulated',
                    line=dict(color='#E25A53', width=2.5, dash='dash'),
                    hovertemplate='ΔRV=%{x:.1f} km/s<br>CDF=%{y:.3f}<extra>Simulated</extra>',
                ))
                fig_cdf.update_layout(**{
                    **PLOTLY_THEME,
                    'title': dict(
                        text=(f'ΔRV CDF — Observed vs Model  '
                              f'(f_bin={ex_fb:.3f}, π={ex_pi:.2f}, '
                              f'σ={ex_sig:.1f})'),
                        font=dict(size=14),
                    ),
                    'xaxis_title': 'ΔRV (km/s)',
                    'yaxis_title': 'Cumulative fraction',
                    'height': 420,
                    'legend': dict(x=0.65, y=0.15),
                    'annotations': [dict(
                        x=0.98, y=0.95, xref='paper', yref='paper',
                        text=f'K-S D = {D_val:.4f}<br>p = {p_val:.4f}',
                        showarrow=False,
                        font=dict(size=12, color='#333333'),
                        bgcolor='rgba(255,255,255,0.9)',
                        borderpad=6,
                        xanchor='right',
                    )],
                })
                st.plotly_chart(fig_cdf, use_container_width=True, key='bc_cdf')
                st.caption(
                    'Empirical cumulative distribution of peak-to-peak ΔRV. '
                    'The K-S statistic (D) measures the maximum vertical '
                    'distance between the two CDFs; a higher p-value indicates '
                    'a better match between model and observations.'
                )

                # ── 2) RV Distribution ───────────────────────────────────────
                st.markdown('### RV Distribution')

                obs_rv_single_list = []
                obs_rv_binary_list = []
                obs_rv_all_list = []
                for star_name, info in obs_detail.items():
                    rv_arr = info.get('rv')
                    if rv_arr is None or len(rv_arr) == 0:
                        continue
                    obs_rv_all_list.append(rv_arr)
                    if bool(info.get('is_binary', False)):
                        obs_rv_binary_list.append(rv_arr)
                    else:
                        obs_rv_single_list.append(rv_arr)

                obs_rv_all = np.concatenate(obs_rv_all_list) if obs_rv_all_list else np.array([])
                obs_rv_singles = np.concatenate(obs_rv_single_list) if obs_rv_single_list else np.array([])
                obs_rv_binaries = np.concatenate(obs_rv_binary_list) if obs_rv_binary_list else np.array([])

                _rv_c1, _rv_c2 = st.columns([0.4, 0.6])
                rv_split_mode = _rv_c1.radio(
                    'Observed RVs', ['All combined', 'Split by classification'],
                    horizontal=True, key='bc_rv_split')
                show_sim_rv = _rv_c2.checkbox(
                    'Overlay simulated RVs', value=True, key='bc_show_sim_rv')

                fig_rv = go.Figure()
                nbins = 40

                if rv_split_mode == 'All combined':
                    if obs_rv_all.size > 0:
                        fig_rv.add_trace(go.Histogram(
                            x=obs_rv_all, nbinsx=nbins,
                            histnorm='probability density',
                            name='Observed (all)',
                            marker_color='#4A90D9', opacity=0.6,
                        ))
                else:
                    if obs_rv_singles.size > 0:
                        fig_rv.add_trace(go.Histogram(
                            x=obs_rv_singles, nbinsx=nbins,
                            histnorm='probability density',
                            name='Observed — single',
                            marker_color='#4A90D9', opacity=0.5,
                        ))
                    if obs_rv_binaries.size > 0:
                        fig_rv.add_trace(go.Histogram(
                            x=obs_rv_binaries, nbinsx=nbins,
                            histnorm='probability density',
                            name='Observed — binary',
                            marker_color='#E25A53', opacity=0.5,
                        ))

                if show_sim_rv and sim_rv_single is not None:
                    if rv_split_mode == 'All combined':
                        sim_rv_combined = np.concatenate([sim_rv_single, sim_rv_binary])
                        if sim_rv_combined.size > 0:
                            fig_rv.add_trace(go.Histogram(
                                x=sim_rv_combined, nbinsx=nbins,
                                histnorm='probability density',
                                name='Simulated (all)',
                                marker_color='#8C8C8C', opacity=0.4,
                            ))
                    else:
                        if sim_rv_single.size > 0:
                            fig_rv.add_trace(go.Histogram(
                                x=sim_rv_single, nbinsx=nbins,
                                histnorm='probability density',
                                name='Simulated — single',
                                marker_color='#7EC8E3', opacity=0.4,
                            ))
                        if sim_rv_binary.size > 0:
                            fig_rv.add_trace(go.Histogram(
                                x=sim_rv_binary, nbinsx=nbins,
                                histnorm='probability density',
                                name='Simulated — binary',
                                marker_color='#F0A0A0', opacity=0.4,
                            ))

                fig_rv.update_layout(**{
                    **PLOTLY_THEME,
                    'barmode': 'overlay',
                    'title': dict(text='RV Distribution', font=dict(size=14)),
                    'xaxis_title': 'RV (km/s)',
                    'yaxis_title': 'Probability density',
                    'height': 420,
                    'legend': dict(x=0.01, y=0.99),
                })
                st.plotly_chart(fig_rv, use_container_width=True, key='bc_rv_dist')
                st.caption(
                    'Distribution of individual RV measurements. Observed data '
                    'can be shown combined or split by binary classification; '
                    'simulated data is drawn from the selected model. All '
                    'histograms are normalized to probability density for '
                    'comparison.'
                )

                # ── 3) Detection fraction vs threshold ───────────────────────
                st.markdown('### Detection Fraction vs Threshold')

                max_drv = max(float(np.max(obs_drv_analysis)),
                              float(np.max(sim_drv)))
                thresholds = np.linspace(0, max_drv * 1.1, 150)
                frac_obs_arr = np.array(
                    [(obs_drv_analysis > T).mean() for T in thresholds])
                frac_sim_arr = np.array(
                    [(sim_drv > T).mean() for T in thresholds])

                frac_obs_at_thresh = float(
                    (obs_drv_analysis > thresh_dRV).mean())
                frac_sim_at_thresh = float((sim_drv > thresh_dRV).mean())

                fig_frac = go.Figure()
                fig_frac.add_trace(go.Scatter(
                    x=thresholds, y=frac_obs_arr,
                    mode='lines', name='Observed',
                    line=dict(color='#4A90D9', width=2.5),
                ))
                fig_frac.add_trace(go.Scatter(
                    x=thresholds, y=frac_sim_arr,
                    mode='lines', name='Simulated',
                    line=dict(color='#E25A53', width=2.5, dash='dash'),
                ))
                fig_frac.add_vline(
                    x=thresh_dRV, line_dash='dot',
                    line_color='#DAA520', line_width=1.5,
                    annotation_text=f'Threshold = {thresh_dRV} km/s',
                    annotation_position='top right',
                    annotation_font_color='#DAA520',
                )
                fig_frac.add_trace(go.Scatter(
                    x=[thresh_dRV, thresh_dRV],
                    y=[frac_obs_at_thresh, frac_sim_at_thresh],
                    mode='markers+text',
                    marker=dict(size=10, color=['#4A90D9', '#E25A53'],
                                symbol='circle',
                                line=dict(color='white', width=1)),
                    text=[f'  {frac_obs_at_thresh:.2%}',
                          f'  {frac_sim_at_thresh:.2%}'],
                    textposition='middle right',
                    textfont=dict(size=11),
                    showlegend=False,
                ))
                fig_frac.update_layout(**{
                    **PLOTLY_THEME,
                    'title': dict(
                        text=(f'Detection Fraction vs ΔRV Threshold  '
                              f'(model: f_bin={ex_fb:.3f}, π={ex_pi:.2f})'),
                        font=dict(size=14),
                    ),
                    'xaxis_title': 'ΔRV threshold (km/s)',
                    'yaxis_title': 'Fraction above threshold',
                    'height': 420,
                    'legend': dict(x=0.70, y=0.95),
                    'yaxis': dict(range=[0, 1.05]),
                })
                st.plotly_chart(fig_frac, use_container_width=True, key='bc_det_frac')
                st.caption(
                    'Fraction of stars with ΔRV exceeding a given threshold. '
                    'The vertical line marks the detection threshold used for '
                    'binary classification. A good model should match the '
                    'observed curve across all thresholds, not just at the '
                    'chosen cutoff.'
                )

        # ── Multi-sigma visualizations (after model explorer) ────────────
        if len(sigma_g) > 1:
            st.markdown('---')

            # Animated 4D figure
            st.markdown('### Animated 4D view  (σ_single as time axis)')
            st.caption('Use the Play button or drag the slider to step through σ_single values.')

            frames = []
            for i_s, sigma_val in enumerate(sigma_g):
                z_frame = ks_p_3d[i_s]
                bf_f, bp_f, _ = _best_point(z_frame, fbin_g, pi_g)
                frames.append(go.Frame(
                    data=[
                        go.Heatmap(
                            z=z_frame, x=pi_g, y=fbin_g,
                            colorscale='RdBu_r',
                            zmin=0.0,
                            zmax=float(np.percentile(ks_p_3d, 98)),
                            zsmooth='best',
                            colorbar=dict(title='K-S p-value', thickness=14),
                        ),
                        go.Scatter(
                            x=[bp_f], y=[bf_f],
                            mode='markers',
                            marker=dict(symbol='star', size=16, color='gold',
                                        line=dict(color='black', width=1)),
                        ),
                    ],
                    name=str(i_s),
                    layout=go.Layout(
                        title_text=(
                            f'K-S p-value  —  σ_single = {sigma_val:.1f} km/s  '
                            f'(best f_bin={bf_f:.3f}, π={bp_f:.2f})'
                        )
                    ),
                ))

            anim_layout: dict = {
                **PLOTLY_THEME,
                'title': 'Bias Correction — K-S p-value animated over σ_single',
                'xaxis_title': 'π  (period power-law index)',
                'yaxis_title': 'f_bin  (intrinsic binary fraction)',
                'updatemenus': [dict(
                    type='buttons',
                    showactive=False,
                    y=1.18, x=0.5, xanchor='center',
                    buttons=[
                        dict(
                            label='▶ Play',
                            method='animate',
                            args=[None, dict(
                                frame=dict(duration=900, redraw=True),
                                fromcurrent=True, mode='immediate',
                            )],
                        ),
                        dict(
                            label='⏸ Pause',
                            method='animate',
                            args=[[None], dict(
                                mode='immediate',
                                frame=dict(duration=0, redraw=False),
                            )],
                        ),
                    ],
                )],
                'sliders': [dict(
                    active=0,
                    currentvalue=dict(
                        prefix='σ_single = ', suffix=' km/s', visible=True,
                        font=dict(size=13),
                    ),
                    pad=dict(t=55),
                    steps=[
                        dict(
                            args=[[str(i_s)], dict(
                                mode='immediate',
                                frame=dict(duration=0, redraw=True),
                            )],
                            label=f'{float(sv):.1f}',
                            method='animate',
                        )
                        for i_s, sv in enumerate(sigma_g)
                    ],
                )],
                'height': _ch + 120,
                'margin': dict(l=60, r=20, t=80, b=80),
            }
            if _cw is not None:
                anim_layout['width'] = _cw

            fig4d = go.Figure(data=frames[0].data, frames=frames,
                              layout=go.Layout(**anim_layout))
            st.plotly_chart(fig4d, use_container_width=_use_cw, key='bc_anim_4d')

            # 3D stacked heatmap
            st.markdown('### 3D Stacked View')
            st.caption(
                'Semi-transparent heatmap layers stacked along σ_single. '
                'Rotate and zoom with mouse.'
            )
            fig_3d = _make_3d_stacked_fig(
                ks_p_3d, fbin_g, pi_g, sigma_g,
                height=_ch + 200, width=_cw,
            )
            st.plotly_chart(fig_3d, use_container_width=_use_cw, key='bc_3d_stacked')

            # Summary table
            summary_rows = []
            for i_s, sv in enumerate(sigma_g):
                bf_s, bp_s, bpv_s = _best_point(ks_p_3d[i_s], fbin_g, pi_g)
                summary_rows.append({
                    'σ_single (km/s)': round(float(sv), 2),
                    'Best f_bin': round(bf_s, 4),
                    'Best π': round(bp_s, 4),
                    'K-S p': round(bpv_s, 5),
                })
            st.dataframe(pd.DataFrame(summary_rows), use_container_width=True)

        # ── Simulation Methodology & Equations ───────────────────────────────
        st.markdown('---')
        with st.expander('Simulation methodology & equations', expanded=False):
            st.markdown('''
**Simulation overview** — for each grid point (f_bin, π, σ_single):

1. **Draw N systems** (default 3,000). Each system is assigned as binary
   with probability f_bin, or single with probability 1 − f_bin.

2. **Assign observation cadences.** Each simulated system is randomly
   paired with a real star's observation times (MJD from FITS headers),
   preserving the actual time sampling of the survey.

3. **Single stars:** draw RV at each epoch from
   N(v_sys, σ_total) where σ_total = √(σ_single² + σ_measure²).
   Compute ΔRV = max(v) − min(v).

4. **Binary stars:** for each system, sample orbital parameters:
   - Period P from power-law distribution p(log P) ∝ (log P)^π
   - Eccentricity e from uniform [0, e_max] (or fixed at 0)
   - Primary mass M₁ (fixed or uniform)
   - Mass ratio q = M₂/M₁ (flat or Gaussian)
   - Inclination i from sin(i) distribution
   - Argument of periastron ω ~ U[0, 2π]
   - Initial mean anomaly T₀ ~ U[0, 2π]

5. **Compute the RV semi-amplitude K₁:**
''')
            st.latex(
                r'K_1 = \left(\frac{2\pi G}{P}\right)^{1/3}'
                r'\frac{M_2 \sin i}{(M_1 + M_2)^{2/3}}'
                r'\frac{1}{\sqrt{1 - e^2}}'
            )

            st.markdown('''
6. **Solve Kepler's equation** at each observation time t
   via Newton-Raphson iteration:
''')
            st.latex(r'E - e \sin E = M, \quad M = T_0 + \frac{2\pi t}{P}')

            st.markdown('7. **Compute the true anomaly** ν from E:')
            st.latex(
                r'\tan\frac{\nu}{2} = '
                r'\sqrt{\frac{1+e}{1-e}} \, \tan\frac{E}{2}'
            )

            st.markdown('8. **Compute the radial velocity curve:**')
            st.latex(
                r'v(t) = v_{\rm sys} + K_1 '
                r'\left[\cos(\omega + \nu) + e\cos\omega\right]'
            )

            st.markdown(r'''
   Then ΔRV = max(v) − min(v) over the observed epochs.

9. **Compare the simulated ΔRV distribution** to the observed one using
   the two-sample Kolmogorov-Smirnov test. The K-S statistic D is the
   maximum absolute difference between the two empirical CDFs:
''')
            st.latex(
                r'D = \max_x \left| F_{\rm obs}(x) - F_{\rm sim}(x) \right|'
            )

            st.markdown(r'''
   The associated p-value quantifies the probability that both samples
   are drawn from the same underlying distribution. Higher p → better match.

10. **Binary detection criteria** (both required):
''')
            st.latex(
                r'\Delta\mathrm{RV} > 45.5 \; \mathrm{km/s}'
                r'\quad \text{and} \quad'
                r'\Delta\mathrm{RV} - 4\sigma > 0'
            )
            st.markdown(
                'where σ is the combined measurement error of the epoch pair.'
            )


# ─────────────────────────────────────────────────────────────────────────────
# Langer 2020 tab
# ─────────────────────────────────────────────────────────────────────────────
with tab_langer:
    lg_cfg   = settings.get('grid_langer', {})
    lg_sim   = settings.get('simulation', {})
    lg_cls   = settings.get('classification', {})
    lg_pp    = lg_cfg.get('langer_period_params', {})

    lg_col_left, lg_col_right = st.columns([0.30, 0.70])

    # ── Left column: grid + orbital parameters ───────────────────────────────
    with lg_col_left:
        with st.expander('⚙️ Grid parameters', expanded=True):
            lg_fbin_min = st.number_input(
                'f_bin min', 0.0, 0.5, float(lg_cfg.get('fbin_min', 0.01)), 0.01,
                key='lg_fbin_min',
                on_change=lambda: sm.save(['grid_langer', 'fbin_min'],
                                          value=st.session_state['lg_fbin_min']))
            lg_fbin_max = st.number_input(
                'f_bin max', 0.5, 1.0, float(lg_cfg.get('fbin_max', 0.99)), 0.01,
                key='lg_fbin_max',
                on_change=lambda: sm.save(['grid_langer', 'fbin_max'],
                                          value=st.session_state['lg_fbin_max']))
            lg_fbin_steps = st.number_input(
                'f_bin steps', 10, 500, int(lg_cfg.get('fbin_steps', 100)), 1,
                key='lg_fbin_steps',
                on_change=lambda: sm.save(['grid_langer', 'fbin_steps'],
                                          value=st.session_state['lg_fbin_steps']))

            st.markdown('---')
            lg_sigma_min = st.number_input(
                'σ_single min (km/s)', 0.1, 100.0,
                float(lg_cfg.get('sigma_min', 1.0)), 0.1,
                key='lg_sigma_min',
                on_change=lambda: sm.save(['grid_langer', 'sigma_min'],
                                          value=st.session_state['lg_sigma_min']))
            lg_sigma_max = st.number_input(
                'σ_single max (km/s)', 0.5, 100.0,
                float(lg_cfg.get('sigma_max', 15.0)), 0.1,
                key='lg_sigma_max',
                on_change=lambda: sm.save(['grid_langer', 'sigma_max'],
                                          value=st.session_state['lg_sigma_max']))
            lg_sigma_steps = st.number_input(
                'σ_single steps', 5, 500, int(lg_cfg.get('sigma_steps', 30)), 1,
                key='lg_sigma_steps',
                on_change=lambda: sm.save(['grid_langer', 'sigma_steps'],
                                          value=st.session_state['lg_sigma_steps']))

            st.markdown('---')
            lg_n_stars = st.number_input(
                'N stars / point', 100, 50000, int(lg_cfg.get('n_stars_sim', 10000)), 100,
                key='lg_n_stars',
                on_change=lambda: sm.save(['grid_langer', 'n_stars_sim'],
                                          value=st.session_state['lg_n_stars']))
            lg_sigma_meas = st.number_input(
                'σ_measure (km/s)', 0.001, 20.0,
                float(lg_sim.get('sigma_measure', 1.622)), 0.001,
                format='%.3f', key='lg_sigma_meas')

        with st.expander('🔧 Orbital parameters (Langer 2020)', expanded=False):
            st.caption('Period distribution: two-Gaussian mixture in log₁₀(P/days) '
                       'approximating Langer+2020 Fig. 6 (Case B).')

            # Period distribution parameters
            lg_mu_A = st.number_input(
                'μ_A (Case A peak)', 0.1, 5.0,
                float(lg_pp.get('mu_A', 1.1)), 0.05, key='lg_mu_A',
                on_change=lambda: sm.save(
                    ['grid_langer', 'langer_period_params', 'mu_A'],
                    value=st.session_state['lg_mu_A']))
            lg_sigma_A = st.number_input(
                'σ_A (Case A width)', 0.01, 2.0,
                float(lg_pp.get('sigma_A', 0.15)), 0.01, key='lg_sigma_A',
                on_change=lambda: sm.save(
                    ['grid_langer', 'langer_period_params', 'sigma_A'],
                    value=st.session_state['lg_sigma_A']))
            lg_mu_B = st.number_input(
                'μ_B (Case B peak)', 0.1, 5.0,
                float(lg_pp.get('mu_B', 2.2)), 0.05, key='lg_mu_B',
                on_change=lambda: sm.save(
                    ['grid_langer', 'langer_period_params', 'mu_B'],
                    value=st.session_state['lg_mu_B']))
            lg_sigma_B = st.number_input(
                'σ_B (Case B width)', 0.01, 2.0,
                float(lg_pp.get('sigma_B', 0.35)), 0.01, key='lg_sigma_B',
                on_change=lambda: sm.save(
                    ['grid_langer', 'langer_period_params', 'sigma_B'],
                    value=st.session_state['lg_sigma_B']))
            lg_weight_A = st.slider(
                'Weight of Case A', 0.0, 1.0,
                float(lg_pp.get('weight_A', 0.3)), 0.01, key='lg_weight_A',
                on_change=lambda: sm.save(
                    ['grid_langer', 'langer_period_params', 'weight_A'],
                    value=st.session_state['lg_weight_A']))

            st.markdown('---')
            # Period range (clipping bounds)
            lg_logP_min = st.number_input(
                'log₁₀(P/days) min', 0.01, 5.0,
                float(lg_cfg.get('logP_min', 0.5)), 0.01, key='lg_logP_min',
                on_change=lambda: sm.save(['grid_langer', 'logP_min'],
                                          value=st.session_state['lg_logP_min']))
            lg_logP_max = st.number_input(
                'log₁₀(P/days) max', 0.1, 10.0,
                float(lg_cfg.get('logP_max', 3.5)), 0.1, key='lg_logP_max',
                on_change=lambda: sm.save(['grid_langer', 'logP_max'],
                                          value=st.session_state['lg_logP_max']))

            st.markdown('---')
            # Eccentricity — fixed at 0 per Langer assumption
            st.markdown('**Eccentricity:** fixed at e = 0 (Langer+2020 assumption)')

            st.markdown('---')
            # Primary mass
            lg_mass_model = st.selectbox(
                'Primary mass model', ['fixed', 'uniform'],
                index=['fixed', 'uniform'].index(
                    lg_cfg.get('mass_primary_model', 'fixed')),
                key='lg_mass_model')
            if lg_mass_model == 'fixed':
                lg_mass_fixed = st.number_input(
                    'M₁ (M☉)', 1.0, 200.0,
                    float(lg_cfg.get('mass_primary_fixed', 10.0)), 1.0,
                    key='lg_mass_fixed')
                lg_mass_range = (float(lg_mass_fixed), float(lg_mass_fixed))
            else:
                lg_mass_fixed = 10.0
                _lg_mr = lg_cfg.get('mass_primary_range', [10.0, 20.0])
                _lgmc1, _lgmc2 = st.columns(2)
                lg_mass_min_v = _lgmc1.number_input(
                    'M₁ min', 1.0, 200.0, float(_lg_mr[0]), 1.0, key='lg_mass_min')
                lg_mass_max_v = _lgmc2.number_input(
                    'M₁ max', 1.0, 200.0, float(_lg_mr[1]), 1.0, key='lg_mass_max')
                lg_mass_range = (float(lg_mass_min_v), float(lg_mass_max_v))

            st.markdown('---')
            # Mass ratio q — three presets
            _q_preset_options = ['Dsilva (flat 0.1–2.0)',
                                 'Langer flat (0.5–10.0)',
                                 'Langer Fig.3 Case B (Gaussian)']
            _q_preset_map = {
                'Dsilva (flat 0.1–2.0)': 'dsilva',
                'Langer flat (0.5–10.0)': 'langer_flat',
                'Langer Fig.3 Case B (Gaussian)': 'langer_fig3',
            }
            _q_preset_inv = {v: k for k, v in _q_preset_map.items()}
            _saved_q = lg_cfg.get('q_preset', 'langer_fig3')
            lg_q_preset_label = st.selectbox(
                'Mass ratio q model', _q_preset_options,
                index=_q_preset_options.index(
                    _q_preset_inv.get(_saved_q, _q_preset_options[2])),
                key='lg_q_preset',
                on_change=lambda: sm.save(
                    ['grid_langer', 'q_preset'],
                    value=_q_preset_map[st.session_state['lg_q_preset']]))
            lg_q_preset = _q_preset_map[lg_q_preset_label]

            if lg_q_preset == 'dsilva':
                lg_q_model = 'flat'
                lg_q_min, lg_q_max = 0.1, 2.0
                lg_lq_mu, lg_lq_sig = 0.7, 0.2
            elif lg_q_preset == 'langer_flat':
                lg_q_model = 'flat'
                lg_q_min, lg_q_max = 0.5, 10.0
                lg_lq_mu, lg_lq_sig = 0.7, 0.2
            else:  # langer_fig3
                lg_q_model = 'langer'
                lg_q_min, lg_q_max = 0.1, 2.0
                lg_lq_mu = st.number_input(
                    'Langer q mean', 0.01, 5.0,
                    float(lg_cfg.get('langer_q_mu', 0.7)), 0.05,
                    key='lg_lq_mu')
                lg_lq_sig = st.number_input(
                    'Langer q sigma', 0.01, 5.0,
                    float(lg_cfg.get('langer_q_sigma', 0.2)), 0.05,
                    key='lg_lq_sig')

            st.caption(f'Active: q_model="{lg_q_model}", '
                       f'range=[{lg_q_min}, {lg_q_max}]')

    # ── Right column: actions + display ───────────────────────────────────────
    with lg_col_right:
        # Action row
        lg_max_proc = max(1, (os.cpu_count() or 2) - 1)
        _lg_ac1, _lg_ac2, _lg_ac3, _lg_ac4 = st.columns([0.15, 0.25, 0.30, 0.30])
        lg_n_proc = _lg_ac1.number_input('Workers', 1, lg_max_proc, lg_max_proc,
                                          key='lg_nproc')
        lg_view_mode = _lg_ac2.radio('View', ['K-S p-value', 'K-S D-statistic'],
                                      horizontal=True, key='lg_view_mode')
        lg_show_d = lg_view_mode == 'K-S D-statistic'
        lg_run_btn = _lg_ac3.button('▶️ Run Langer Grid', type='primary', key='lg_run')
        lg_load_btn = _lg_ac4.button('📂 Load cached result', key='lg_load')

        # Display slots
        lg_progress_slot = st.empty()
        lg_status_slot   = st.empty()
        lg_heatmap_slot  = st.empty()
        lg_result_slot   = st.empty()

    # ── Stable config ─────────────────────────────────────────────────────────
    lg_period_params = {
        'mu_A': float(lg_mu_A), 'sigma_A': float(lg_sigma_A),
        'mu_B': float(lg_mu_B), 'sigma_B': float(lg_sigma_B),
        'weight_A': float(lg_weight_A),
    }
    lg_stable_cfg = {
        'n_stars_sim':        int(lg_n_stars),
        'sigma_measure':      float(lg_sigma_meas),
        'logP_min':           float(lg_logP_min),
        'logP_max':           float(lg_logP_max),
        'period_model':       'langer2020',
        'e_model':            'zero',
        'e_max':              0.0,
        'mass_primary_model': str(lg_mass_model),
        'mass_primary_fixed': float(lg_mass_fixed),
        'q_model':            str(lg_q_model),
        'q_min':              float(lg_q_min),
        'q_max':              float(lg_q_max),
        'q_preset':           str(lg_q_preset),
        'langer_period_params': lg_period_params,
        'primary_line':       settings.get('primary_line', 'C IV 5808-5812'),
        'threshold_dRV':      lg_cls.get('threshold_dRV', 45.5),
        'sigma_factor':       lg_cls.get('sigma_factor', 4.0),
    }

    lg_fbin_vals  = np.linspace(float(lg_fbin_min), float(lg_fbin_max), int(lg_fbin_steps))
    lg_sigma_vals = np.linspace(max(0.1, float(lg_sigma_min)),
                                max(float(lg_sigma_min) + 0.1, float(lg_sigma_max)),
                                int(lg_sigma_steps))

    # ── Load cached result if requested ───────────────────────────────────────
    if lg_load_btn:
        cached_lg = cached_load_grid_result('langer')
        if cached_lg is not None:
            st.session_state['lg_result'] = cached_lg
            lg_status_slot.success('Loaded cached result from results/langer_result.npz')
        else:
            lg_status_slot.warning('No cached result found at results/langer_result.npz')

    # ── Run grid ──────────────────────────────────────────────────────────────
    if lg_run_btn:
        sh_lg = settings_hash(settings)
        try:
            lg_obs_drv, _ = cached_load_observed_delta_rvs(sh_lg)
            lg_cad_list, lg_cad_weights = cached_load_cadence(sh_lg)
        except Exception as e:
            lg_status_slot.error(f'Failed to load observations: {e}')
            st.stop()

        from wr_bias_simulation import (
            SimulationConfig, BinaryParameterConfig, _single_grid_task,
        )

        lg_bin_cfg = BinaryParameterConfig(
            logP_min=float(lg_logP_min),
            logP_max=float(lg_logP_max),
            period_model='langer2020',
            langer_period_params=lg_period_params,
            e_model='zero',
            e_max=0.0,
            mass_primary_model=str(lg_mass_model),
            mass_primary_fixed=float(lg_mass_fixed),
            mass_primary_range=tuple(lg_mass_range),
            q_model=str(lg_q_model),
            q_range=(float(lg_q_min), float(lg_q_max)),
            langer_q_mu=float(lg_lq_mu),
            langer_q_sigma=float(lg_lq_sig),
        )

        # ── Check for partial reuse ──────────────────────────────────────────
        lg_cached_existing = None
        lg_reuse_info = None
        lg_existing_path = _result_path('langer')
        if os.path.exists(lg_existing_path):
            try:
                lg_cached_existing = dict(np.load(lg_existing_path, allow_pickle=True))
                lg_reuse_info = _find_reusable_fbin_langer(
                    lg_cached_existing, lg_fbin_vals, lg_sigma_vals, lg_stable_cfg)
            except Exception:
                lg_cached_existing = None

        if lg_reuse_info:
            lg_reuse_new_idx, lg_reuse_cache_idx = lg_reuse_info
            lg_n_reused = len(lg_reuse_new_idx)
            lg_status_slot.info(
                f'♻️ Reusing {lg_n_reused}/{len(lg_fbin_vals)} f_bin rows from cached result.')
        else:
            lg_reuse_new_idx, lg_reuse_cache_idx = [], []
            lg_n_reused = 0

        # Pre-allocate result arrays: shape [n_fbin, n_sigma]
        lg_n_fbin  = len(lg_fbin_vals)
        lg_n_sigma = len(lg_sigma_vals)
        lg_acc_ks_p = np.full((lg_n_fbin, lg_n_sigma), np.nan)
        lg_acc_ks_D = np.full_like(lg_acc_ks_p, np.nan)

        # Fill in reused rows
        if lg_reuse_info and lg_cached_existing is not None:
            lg_c_ks_p = np.asarray(lg_cached_existing['ks_p'])
            lg_c_ks_D = np.asarray(lg_cached_existing['ks_D'])
            for new_i, cache_i in zip(lg_reuse_new_idx, lg_reuse_cache_idx):
                lg_acc_ks_p[new_i, :] = lg_c_ks_p[cache_i, :]
                lg_acc_ks_D[new_i, :] = lg_c_ks_D[cache_i, :]

        lg_reuse_set = set(lg_reuse_new_idx)
        lg_missing_fbin_idx = [i for i in range(lg_n_fbin) if i not in lg_reuse_set]

        lg_n_cells_total = len(lg_missing_fbin_idx) * lg_n_sigma
        lg_cells_done = 0
        lg_t_start = time.time()

        if lg_n_cells_total == 0:
            lg_progress_slot.progress(1.0, text='All rows reused from cache.')
            lg_status_slot.success('All f_bin rows already computed — no new work needed.')
        else:
            lg_fbin_to_global = {}
            for gj in lg_missing_fbin_idx:
                lg_fbin_to_global[round(float(lg_fbin_vals[gj]), 10)] = gj

            lg_sigma_to_idx = {}
            for i, sv in enumerate(lg_sigma_vals):
                lg_sigma_to_idx[round(float(sv), 10)] = i

            lg_seed_base = 5678
            lg_last_render = 0.0

            # Build all tasks
            lg_tasks = []
            for gj in lg_missing_fbin_idx:
                for i_s, sv in enumerate(lg_sigma_vals):
                    lg_sim_cfg_obj = SimulationConfig(
                        n_stars=int(lg_n_stars),
                        sigma_single=float(sv),
                        sigma_measure=float(lg_sigma_meas),
                        cadence_library=lg_cad_list,
                        cadence_weights=lg_cad_weights,
                    )
                    lg_tasks.append((
                        float(lg_fbin_vals[gj]),
                        0.0,  # pi is unused for langer2020
                        float(sv),
                        lg_sim_cfg_obj,
                        lg_bin_cfg,
                        lg_obs_drv,
                        'langer2020',
                        lg_seed_base,
                    ))
                    lg_seed_base += 1

            with mp.Pool(processes=int(lg_n_proc)) as pool:
                for fb, _pi_ret, sigma_ret, D, p in pool.imap_unordered(
                        _single_grid_task, lg_tasks,
                        chunksize=max(1, lg_n_sigma // 4)):
                    gj = lg_fbin_to_global[round(fb, 10)]
                    i_s = lg_sigma_to_idx[round(sigma_ret, 10)]

                    lg_acc_ks_p[gj, i_s] = p
                    lg_acc_ks_D[gj, i_s] = D

                    lg_cells_done += 1

                    elapsed = time.time() - lg_t_start
                    eta_str = ''
                    if lg_cells_done > 1 and lg_cells_done < lg_n_cells_total:
                        eta = elapsed / lg_cells_done * (lg_n_cells_total - lg_cells_done)
                        eta_str = f'  —  ETA {int(eta)}s'

                    lg_progress_slot.progress(
                        lg_cells_done / lg_n_cells_total,
                        text=(f'Cell {lg_cells_done}/{lg_n_cells_total}{eta_str}')
                    )

                    now = time.time()
                    if now - lg_last_render > 1.0 or lg_cells_done == lg_n_cells_total:
                        lg_last_render = now
                        cur_p = np.where(np.isnan(lg_acc_ks_p), 0.0, lg_acc_ks_p)
                        cur_D = np.where(np.isnan(lg_acc_ks_D), 0.0, lg_acc_ks_D)
                        lg_heatmap_slot.plotly_chart(
                            _make_heatmap_fig(
                                cur_p, lg_fbin_vals, lg_sigma_vals,
                                title='Langer 2020 — K-S p-value (live)',
                                show_d=lg_show_d, ks_d_2d=cur_D,
                                height=_ch, width=_cw,
                                x_label='σ_single (km/s)',
                                x_name='σ',
                                best_label_fmt='  f={fbin:.3f}, σ={x:.1f}, p={p:.3f}',
                            ),
                            use_container_width=_use_cw,
                        )

                        bf, bsig, bpv = _best_point(cur_p, lg_fbin_vals, lg_sigma_vals)
                        lg_status_slot.markdown(
                            f'best f_bin = **{bf:.4f}**, σ_single = **{bsig:.1f}** km/s, '
                            f'K-S p = **{bpv:.4f}**'
                        )

            # ── Checkpoint after each batch of fbin rows ──────────────────────
            if lg_cells_done > 0:
                os.makedirs(_RESULT_DIR, exist_ok=True)
                np.savez(
                    _result_path('langer') + '.partial',
                    fbin_grid=lg_fbin_vals, sigma_grid=lg_sigma_vals,
                    ks_p=lg_acc_ks_p, ks_D=lg_acc_ks_D,
                    config_hash=_stable_cfg_hash(lg_stable_cfg),
                    settings=np.array(json.dumps(lg_stable_cfg)),
                    timestamp=np.array(_dt.datetime.now().isoformat()),
                )

        lg_elapsed_total = time.time() - lg_t_start
        if lg_n_cells_total > 0:
            lg_progress_slot.progress(1.0, text=f'Done in {lg_elapsed_total:.0f}s.')

        # ── Save final result ─────────────────────────────────────────────────
        os.makedirs(_RESULT_DIR, exist_ok=True)
        lg_chash = _stable_cfg_hash({
            **lg_stable_cfg,
            'fbin_min': float(lg_fbin_min), 'fbin_max': float(lg_fbin_max),
            'fbin_steps': int(lg_fbin_steps),
            'sigma_min': float(lg_sigma_min), 'sigma_max': float(lg_sigma_max),
            'sigma_steps': int(lg_sigma_steps),
        })
        lg_full_result = {
            'fbin_grid':  lg_fbin_vals,
            'sigma_grid': lg_sigma_vals,
            'ks_p':       lg_acc_ks_p,
            'ks_D':       lg_acc_ks_D,
        }
        np.savez(
            _result_path('langer'),
            **lg_full_result,
            config_hash=lg_chash,
            settings=np.array(json.dumps(lg_stable_cfg)),
            obs_delta_rv=lg_obs_drv,
            timestamp=np.array(_dt.datetime.now().isoformat()),
        )
        cached_load_grid_result.clear()
        st.session_state['lg_result'] = lg_full_result
        # Clean up partial checkpoint
        _lg_partial = _result_path('langer') + '.partial.npz'
        if os.path.exists(_lg_partial):
            os.remove(_lg_partial)

        _append_run_history({
            'timestamp':     _dt.datetime.now().isoformat(),
            'model':         'langer2020',
            'config_hash':   lg_chash,
            'config':        lg_stable_cfg,
            'elapsed_s':     round(lg_elapsed_total, 1),
            'result_file':   _result_path('langer'),
            'n_reused_fbin': lg_n_reused,
        })

        lg_status_slot.success(
            f'Saved to results/langer_result.npz  '
            f'({lg_n_reused} f_bin rows reused, '
            f'{len(lg_fbin_vals) - lg_n_reused} computed in {lg_elapsed_total:.0f}s)')

    # ── Display result (always shown when result exists) ─────────────────────
    lg_result = st.session_state.get('lg_result')
    if lg_result is None:
        lg_result = cached_load_grid_result('langer')
        if lg_result is not None:
            st.session_state['lg_result'] = lg_result

    if lg_result is not None:
        lg_fbin_g  = np.asarray(lg_result['fbin_grid'])
        lg_sigma_g = np.asarray(lg_result['sigma_grid'])
        lg_ks_p_2d = np.asarray(lg_result['ks_p'])
        lg_ks_D_2d = np.asarray(lg_result['ks_D'])

        # Show heatmap (skip if just ran — live heatmap already shown)
        if not lg_run_btn:
            lg_heatmap_slot.plotly_chart(
                _make_heatmap_fig(
                    lg_ks_p_2d, lg_fbin_g, lg_sigma_g,
                    title='Langer 2020 — K-S p-value',
                    show_d=lg_show_d, ks_d_2d=lg_ks_D_2d,
                    height=_ch, width=_cw,
                    x_label='σ_single (km/s)',
                    x_name='σ',
                    best_label_fmt='  f={fbin:.3f}, σ={x:.1f}, p={p:.3f}',
                ),
                use_container_width=_use_cw,
            )

        # Best-fit point
        best_fbin_lg, best_sigma_lg, best_pval_lg = _best_point(
            lg_ks_p_2d, lg_fbin_g, lg_sigma_g)

        lg_bartzakos = lg_cls.get('bartzakos_binaries', 3)
        lg_total_pop = lg_cls.get('total_population', 28)

        sh_lg_curr = settings_hash(settings)
        try:
            lg_obs_drv_a, _ = cached_load_observed_delta_rvs(sh_lg_curr)
            lg_n_det = int(np.sum(lg_obs_drv_a > lg_cls.get('threshold_dRV', 45.5)))
        except Exception:
            lg_n_det = 0

        # ── Marginalization + HDI68 ───────────────────────────────────────────
        from wr_bias_simulation import compute_hdi68

        # 1D posterior for f_bin: sum over σ
        lg_post_fbin = np.sum(lg_ks_p_2d, axis=1)
        lg_mode_fbin, lg_lo_fbin, lg_hi_fbin = compute_hdi68(lg_fbin_g, lg_post_fbin)

        # 1D posterior for σ_single: sum over f_bin
        lg_post_sigma = np.sum(lg_ks_p_2d, axis=0)
        lg_mode_sigma, lg_lo_sigma, lg_hi_sigma = compute_hdi68(lg_sigma_g, lg_post_sigma)

        lg_result_slot.markdown(
            f'**Best fit (HDI68):**  '
            f'f_bin = `{lg_mode_fbin:.4f}` '
            f'(+{lg_hi_fbin - lg_mode_fbin:.4f} / -{lg_mode_fbin - lg_lo_fbin:.4f}),  '
            f'σ_single = `{lg_mode_sigma:.1f}` '
            f'(+{lg_hi_sigma - lg_mode_sigma:.1f} / -{lg_mode_sigma - lg_lo_sigma:.1f}) km/s'
            f'  \nK-S p = `{best_pval_lg:.6f}`  \n'
            f'**Observed fraction:**  '
            f'({lg_n_det}+{lg_bartzakos})/{lg_total_pop} = '
            f'**{(lg_n_det + lg_bartzakos) / lg_total_pop * 100:.1f}%**'
        )

        # ── Corner Plot (2 params: f_bin × σ_single) ─────────────────────────
        st.markdown('---')
        st.markdown('### Marginalized Posteriors (Corner Plot)')

        from plotly.subplots import make_subplots as _lg_corner_subplots

        _lg_n_params = 2
        _lg_param_names = ['f_bin', 'σ_single']
        _lg_param_grids = [lg_fbin_g, lg_sigma_g]
        _lg_param_posts = [lg_post_fbin, lg_post_sigma]
        _lg_param_modes = [lg_mode_fbin, lg_mode_sigma]
        _lg_param_los   = [lg_lo_fbin, lg_lo_sigma]
        _lg_param_his   = [lg_hi_fbin, lg_hi_sigma]

        fig_lg_corner = _lg_corner_subplots(
            rows=_lg_n_params, cols=_lg_n_params,
            horizontal_spacing=0.08, vertical_spacing=0.08,
        )

        for i in range(_lg_n_params):
            # Diagonal: 1D posterior
            _lg_area = float(np.trapezoid(_lg_param_posts[i], _lg_param_grids[i]))
            _lg_pn = _lg_param_posts[i] / _lg_area if _lg_area > 0 else _lg_param_posts[i]

            fig_lg_corner.add_trace(go.Scatter(
                x=_lg_param_grids[i], y=_lg_pn,
                mode='lines', line=dict(color='#4A90D9', width=2),
                showlegend=False,
            ), row=i + 1, col=i + 1)

            # HDI68 shading
            _lg_mask = ((_lg_param_grids[i] >= _lg_param_los[i]) &
                        (_lg_param_grids[i] <= _lg_param_his[i]))
            _lg_xh = _lg_param_grids[i][_lg_mask]
            _lg_yh = _lg_pn[_lg_mask]
            if len(_lg_xh) > 0:
                fig_lg_corner.add_trace(go.Scatter(
                    x=np.concatenate([_lg_xh, _lg_xh[::-1]]),
                    y=np.concatenate([_lg_yh, np.zeros(len(_lg_yh))]),
                    fill='toself', fillcolor='rgba(74,144,217,0.3)',
                    line=dict(width=0), showlegend=False,
                ), row=i + 1, col=i + 1)

            # Mode line
            fig_lg_corner.add_vline(
                x=_lg_param_modes[i], line_dash='dash',
                line_color='#E25A53', line_width=1.5,
                row=i + 1, col=i + 1,
            )

            # Off-diagonal: 2D heatmap (lower triangle)
            for j in range(i):
                # For 2 params, axes are: param0=f_bin→axis0, param1=σ→axis1
                # ks_p_2d shape is [n_fbin, n_sigma]
                # For cell (i=1, j=0): x=f_bin (j=0), y=σ (i=1)
                # z needs to be [n_y, n_x] = [n_sigma, n_fbin] = ks_p_2d.T
                fig_lg_corner.add_trace(go.Heatmap(
                    x=_lg_param_grids[j], y=_lg_param_grids[i],
                    z=lg_ks_p_2d.T,
                    colorscale='Viridis', showscale=False,
                    hovertemplate=f'{_lg_param_names[j]}=%{{x:.4f}}<br>'
                                 f'{_lg_param_names[i]}=%{{y:.4f}}<br>'
                                 f'p=%{{z:.4f}}<extra></extra>',
                ), row=i + 1, col=j + 1)

                fig_lg_corner.add_trace(go.Scatter(
                    x=[_lg_param_modes[j]], y=[_lg_param_modes[i]],
                    mode='markers',
                    marker=dict(symbol='star', size=10, color='gold',
                                line=dict(color='black', width=1)),
                    showlegend=False,
                ), row=i + 1, col=j + 1)

        # Axis labels
        for i in range(_lg_n_params):
            fig_lg_corner.update_xaxes(title_text=_lg_param_names[i],
                                        row=_lg_n_params, col=i + 1)
            if i > 0:
                fig_lg_corner.update_yaxes(title_text=_lg_param_names[i],
                                            row=i + 1, col=1)

        # Hide upper triangle
        for i in range(_lg_n_params):
            for j in range(i + 1, _lg_n_params):
                fig_lg_corner.update_xaxes(visible=False, row=i + 1, col=j + 1)
                fig_lg_corner.update_yaxes(visible=False, row=i + 1, col=j + 1)

        fig_lg_corner.update_layout(
            **PLOTLY_THEME,
            height=250 * _lg_n_params,
            width=250 * _lg_n_params,
            showlegend=False,
            margin=dict(l=60, r=20, t=30, b=60),
        )
        st.plotly_chart(fig_lg_corner, use_container_width=True, key='lg_corner_plot')
        st.caption(
            f'Marginalized posteriors (Langer 2020 model). '
            f'**Diagonal:** 1D posteriors with mode (dashed red) and '
            f'68% HDI (blue shading). '
            f'**Off-diagonal:** 2D K-S p-value with best-fit (gold star). '
            f'f_bin = {lg_mode_fbin:.4f} '
            f'(+{lg_hi_fbin - lg_mode_fbin:.4f}/-{lg_mode_fbin - lg_lo_fbin:.4f}), '
            f'σ = {lg_mode_sigma:.1f} '
            f'(+{lg_hi_sigma - lg_mode_sigma:.1f}/-{lg_mode_sigma - lg_lo_sigma:.1f}) km/s.'
        )

        # ── Analysis plots (period dist, binary fraction, orbital properties) ─
        from wr_bias_simulation import (
            SimulationConfig, BinaryParameterConfig,
            simulate_delta_rv_sample, _simulate_rv_sample_full,
            simulate_with_params, ks_two_sample,
        )

        sh_lg_a = settings_hash(settings)
        try:
            lg_obs_drv_analysis, lg_obs_detail = cached_load_observed_delta_rvs(sh_lg_a)
            lg_cad_a, lg_cad_w_a = cached_load_cadence(sh_lg_a)
            _lg_has_obs = True
        except Exception:
            _lg_has_obs = False

        if _lg_has_obs:
            lg_thresh_dRV = float(lg_cls.get('threshold_dRV', 45.5))

            _lg_bin_cfg_ex = BinaryParameterConfig(
                logP_min=float(lg_logP_min),
                logP_max=float(lg_logP_max),
                period_model='langer2020',
                langer_period_params=lg_period_params,
                e_model='zero', e_max=0.0,
                mass_primary_model=str(lg_mass_model),
                mass_primary_fixed=float(lg_mass_fixed),
                mass_primary_range=tuple(lg_mass_range),
                q_model=str(lg_q_model),
                q_range=(float(lg_q_min), float(lg_q_max)),
                langer_q_mu=float(lg_lq_mu),
                langer_q_sigma=float(lg_lq_sig),
            )

            # Simulate at best-fit
            _lg_sim_cfg_gap = SimulationConfig(
                n_stars=int(lg_n_stars),
                sigma_single=float(best_sigma_lg),
                sigma_measure=float(lg_sigma_meas),
                cadence_library=lg_cad_a,
                cadence_weights=lg_cad_w_a,
            )
            if 'lg_gap_sim' not in st.session_state:
                rng_lg_gap = np.random.default_rng(199)
                st.session_state['lg_gap_sim'] = simulate_with_params(
                    best_fbin_lg, 0.0,  # pi unused for langer
                    _lg_sim_cfg_gap, _lg_bin_cfg_ex, rng_lg_gap,
                )
            lg_gap_sim = st.session_state['lg_gap_sim']

            lg_gap_drv = lg_gap_sim['delta_rv']
            lg_gap_is_bin = lg_gap_sim['is_binary']
            lg_gap_idx_bin = lg_gap_sim['idx_bin']

            lg_intrinsic_fbin = float(lg_gap_is_bin.mean())
            lg_detected_mask = lg_gap_drv > lg_thresh_dRV
            lg_observed_fbin = float(lg_detected_mask.mean())
            lg_missed_count = int(np.sum(lg_gap_is_bin & ~lg_detected_mask))
            lg_detected_bin_count = int(np.sum(lg_gap_is_bin & lg_detected_mask))
            lg_total_bin = int(lg_gap_is_bin.sum())

            _lg_bin_drv = lg_gap_drv[lg_gap_idx_bin] if lg_gap_idx_bin.size > 0 else np.array([])
            _lg_bin_det_mask = _lg_bin_drv > lg_thresh_dRV
            _lg_bin_mis_mask = ~_lg_bin_det_mask

            # ── Period Distribution + Binary Fraction vs Threshold ────────────
            st.markdown('---')
            _lg_lp_col, _lg_bf_col = st.columns(2)

            _CLR_DETECTED = '#E25A53'
            _CLR_MISSED   = '#F5A623'

            with _lg_lp_col:
                st.markdown('### Period Distribution  (log P)')

                fig_lg_logP = go.Figure()
                if lg_gap_sim['P_days'].size > 0:
                    _lg_logP_det = (np.log10(lg_gap_sim['P_days'][_lg_bin_det_mask])
                                    if np.any(_lg_bin_det_mask) else np.array([]))
                    _lg_logP_mis = (np.log10(lg_gap_sim['P_days'][_lg_bin_mis_mask])
                                    if np.any(_lg_bin_mis_mask) else np.array([]))

                    if _lg_logP_det.size > 0:
                        fig_lg_logP.add_trace(go.Histogram(
                            x=_lg_logP_det, nbinsx=35,
                            histnorm='probability density',
                            name=f'Detected ({_lg_logP_det.size})',
                            marker_color=_CLR_DETECTED, opacity=0.6,
                        ))
                    if _lg_logP_mis.size > 0:
                        fig_lg_logP.add_trace(go.Histogram(
                            x=_lg_logP_mis, nbinsx=35,
                            histnorm='probability density',
                            name=f'Missed ({_lg_logP_mis.size})',
                            marker_color=_CLR_MISSED, opacity=0.6,
                        ))

                fig_lg_logP.add_vline(x=float(lg_logP_min), line_dash='dash',
                                      line_color='#888', line_width=1.5,
                                      annotation_text='logP_min',
                                      annotation_position='top left',
                                      annotation_font_color='#888')
                fig_lg_logP.add_vline(x=float(lg_logP_max), line_dash='dash',
                                      line_color='#888', line_width=1.5,
                                      annotation_text='logP_max',
                                      annotation_position='top right',
                                      annotation_font_color='#888')
                fig_lg_logP.update_layout(**{
                    **PLOTLY_THEME,
                    'barmode': 'overlay',
                    'title': dict(
                        text='Simulated Period Distribution  (Langer 2020 mixture)',
                        font=dict(size=14)),
                    'xaxis_title': 'log₁₀(P / days)',
                    'yaxis_title': 'Probability density',
                    'height': 400,
                    'margin': dict(l=60, r=20, t=50, b=50),
                    'legend': dict(x=0.65, y=0.95),
                })
                st.plotly_chart(fig_lg_logP, use_container_width=True, key='lg_logP_hist')
                st.caption(
                    'Period distribution of simulated binaries using the Langer+2020 '
                    'two-Gaussian mixture model. Red: detected. Amber: missed.'
                )

            with _lg_bf_col:
                st.markdown('### Observed Binary Fraction vs Threshold')

                _lg_n_sim = len(lg_gap_drv)
                _lg_thresh_arr = np.linspace(0, float(np.max(lg_gap_drv) * 1.05), 200)
                _lg_fbin_curve = np.array(
                    [float(np.sum(lg_gap_drv > t)) / _lg_n_sim for t in _lg_thresh_arr])

                _lg_bin_drv_all = lg_gap_drv[lg_gap_is_bin]
                _lg_sin_drv_all = lg_gap_drv[~lg_gap_is_bin]
                _lg_missed_curve = np.array(
                    [float(np.sum(_lg_bin_drv_all <= t)) / _lg_n_sim for t in _lg_thresh_arr])
                _lg_fp_curve = np.array(
                    [float(np.sum(_lg_sin_drv_all > t)) / _lg_n_sim for t in _lg_thresh_arr])

                fig_lg_gap = go.Figure()
                fig_lg_gap.add_trace(go.Scatter(
                    x=_lg_thresh_arr, y=_lg_missed_curve,
                    fill='tozeroy', fillcolor='rgba(242,166,35,0.25)',
                    line=dict(width=0), mode='lines',
                    name='Missed binaries', showlegend=True,
                ))
                if np.any(_lg_fp_curve > 0):
                    fig_lg_gap.add_trace(go.Scatter(
                        x=_lg_thresh_arr, y=_lg_fp_curve,
                        fill='tozeroy', fillcolor='rgba(74,144,217,0.25)',
                        line=dict(width=0), mode='lines',
                        name='Singles above threshold', showlegend=True,
                    ))
                fig_lg_gap.add_trace(go.Scatter(
                    x=_lg_thresh_arr, y=_lg_fbin_curve,
                    mode='lines', name='Observed f_bin(threshold)',
                    line=dict(color='#4A90D9', width=2.5),
                ))
                fig_lg_gap.add_hline(
                    y=lg_intrinsic_fbin, line_dash='dot',
                    line_color='#E25A53', line_width=2,
                    annotation_text=f'Intrinsic f_bin = {lg_intrinsic_fbin:.1%}',
                    annotation_position='top left',
                    annotation_font=dict(size=11, color='#E25A53'),
                )
                fig_lg_gap.add_vline(
                    x=lg_thresh_dRV, line_dash='dash',
                    line_color='#F5A623', line_width=2,
                    annotation_text=f'Threshold = {lg_thresh_dRV} km/s',
                    annotation_position='top right',
                    annotation_font=dict(size=11, color='#F5A623'),
                )
                fig_lg_gap.add_trace(go.Scatter(
                    x=[lg_thresh_dRV], y=[lg_observed_fbin],
                    mode='markers+text',
                    marker=dict(size=12, color='#FFD700', symbol='star',
                                line=dict(width=1, color='#fff')),
                    text=[f'{lg_observed_fbin:.1%}'],
                    textposition='top left',
                    textfont=dict(size=12, color='#FFD700'),
                    name=f'Observed @ {lg_thresh_dRV} km/s',
                    showlegend=True,
                ))

                lg_gap_pct = lg_intrinsic_fbin - lg_observed_fbin
                fig_lg_gap.add_annotation(
                    x=lg_thresh_dRV + 15,
                    y=(lg_intrinsic_fbin + lg_observed_fbin) / 2,
                    text=f'Gap: {lg_gap_pct:.1%}<br>({lg_missed_count} missed / {lg_total_bin} binaries)',
                    showarrow=False,
                    font=dict(size=11, color='#F5A623'),
                    bgcolor='rgba(255,255,255,0.9)',
                    bordercolor='#F5A623', borderwidth=1, borderpad=4,
                )
                fig_lg_gap.add_annotation(
                    x=lg_thresh_dRV, y=lg_intrinsic_fbin,
                    ax=lg_thresh_dRV, ay=lg_observed_fbin,
                    xref='x', yref='y', axref='x', ayref='y',
                    showarrow=True, arrowhead=3,
                    arrowwidth=2, arrowcolor='#F5A623',
                )
                fig_lg_gap.update_layout(**{
                    **PLOTLY_THEME,
                    'title': dict(text='Binary Fraction vs ΔRV Threshold',
                                  font=dict(size=14)),
                    'xaxis_title': 'ΔRV threshold (km/s)',
                    'yaxis_title': 'Fraction of sample',
                    'height': 400,
                    'margin': dict(l=60, r=80, t=50, b=50),
                    'showlegend': True,
                    'legend': dict(x=0.55, y=0.95, font=dict(size=10)),
                    'yaxis': dict(range=[0, min(1.0, lg_intrinsic_fbin * 1.5)]),
                })
                st.plotly_chart(fig_lg_gap, use_container_width=True, key='lg_gap_chart')
                st.caption(
                    f'Binary fraction as a function of ΔRV threshold (Langer model). '
                    f'At {lg_thresh_dRV} km/s: observed = {lg_observed_fbin:.1%}, '
                    f'intrinsic = {lg_intrinsic_fbin:.1%}, '
                    f'gap = {lg_gap_pct:.1%} ({lg_missed_count} missed).'
                )

            # ── Binary Orbital Parameter Histograms ───────────────────────────
            st.markdown('---')
            st.markdown('### Binary Orbital Properties')

            _lg_mb_view = st.radio(
                'Show populations',
                ['Compare detected vs missed', 'Detected binaries only',
                 'Missed binaries only', 'All binaries (combined)'],
                horizontal=True, key='lg_mb_view',
            )

            def _lg_safe_mask(arr, mask):
                return arr[mask] if arr.size > 0 else np.array([])

            lg_P_det = _lg_safe_mask(lg_gap_sim['P_days'], _lg_bin_det_mask)
            lg_P_mis = _lg_safe_mask(lg_gap_sim['P_days'], _lg_bin_mis_mask)
            lg_e_det = _lg_safe_mask(lg_gap_sim['e'], _lg_bin_det_mask)
            lg_e_mis = _lg_safe_mask(lg_gap_sim['e'], _lg_bin_mis_mask)
            lg_q_det = _lg_safe_mask(lg_gap_sim['q'], _lg_bin_det_mask)
            lg_q_mis = _lg_safe_mask(lg_gap_sim['q'], _lg_bin_mis_mask)
            lg_K1_det = _lg_safe_mask(lg_gap_sim['K1'], _lg_bin_det_mask)
            lg_K1_mis = _lg_safe_mask(lg_gap_sim['K1'], _lg_bin_mis_mask)
            lg_M1_det = _lg_safe_mask(lg_gap_sim['M1'], _lg_bin_det_mask)
            lg_M1_mis = _lg_safe_mask(lg_gap_sim['M1'], _lg_bin_mis_mask)
            lg_i_det = np.degrees(_lg_safe_mask(lg_gap_sim['i_rad'], _lg_bin_det_mask))
            lg_i_mis = np.degrees(_lg_safe_mask(lg_gap_sim['i_rad'], _lg_bin_mis_mask))

            _lg_has_omega = 'omega' in lg_gap_sim
            if _lg_has_omega:
                lg_omega_det = np.degrees(_lg_safe_mask(lg_gap_sim['omega'], _lg_bin_det_mask))
                lg_omega_mis = np.degrees(_lg_safe_mask(lg_gap_sim['omega'], _lg_bin_mis_mask))
                lg_T0_det = _lg_safe_mask(lg_gap_sim['T0'], _lg_bin_det_mask)
                lg_T0_mis = _lg_safe_mask(lg_gap_sim['T0'], _lg_bin_mis_mask)
            else:
                lg_omega_det = lg_omega_mis = lg_T0_det = lg_T0_mis = np.array([])

            lg_M2_det = lg_q_det * lg_M1_det if lg_q_det.size > 0 and lg_M1_det.size > 0 else np.array([])
            lg_M2_mis = lg_q_mis * lg_M1_mis if lg_q_mis.size > 0 and lg_M1_mis.size > 0 else np.array([])

            lg_P_all = lg_gap_sim['P_days']
            lg_e_all = lg_gap_sim['e']
            lg_q_all = lg_gap_sim['q']
            lg_K1_all = lg_gap_sim['K1']
            lg_M1_all = lg_gap_sim['M1']
            lg_i_all = np.degrees(lg_gap_sim['i_rad'])
            lg_omega_all = np.degrees(lg_gap_sim['omega']) if _lg_has_omega else np.array([])
            lg_T0_all = lg_gap_sim['T0'] if _lg_has_omega else np.array([])
            lg_M2_all = lg_q_all * lg_M1_all if lg_q_all.size > 0 else np.array([])

            from plotly.subplots import make_subplots as _lg_make_subplots

            _lg_titles = [
                'log₁₀(P / days)', 'Eccentricity', 'Mass ratio q',
                'K₁ (km/s)', 'M₁ (M⊙)', 'M₂ (M⊙)',
                'Inclination (°)', 'ω (°)', 'T₀ (rad)',
            ]
            _lg_x_labels = [
                'log₁₀(P / days)', 'e', 'q = M₂/M₁',
                'K₁ (km/s)', 'M₁ (M⊙)', 'M₂ (M⊙)',
                'i (degrees)', 'ω (degrees)', 'T₀ (rad)',
            ]
            _lg_n_panels = 9
            _lg_n_cols = 3
            _lg_n_rows = 3
            _lg_nbins = 30

            fig_lg_mb = _lg_make_subplots(
                rows=_lg_n_rows, cols=_lg_n_cols,
                subplot_titles=_lg_titles,
                horizontal_spacing=0.08, vertical_spacing=0.10)

            _CLR_ALL = '#52B788'

            def _lg_add_hist(fig, row, col, data, name, color, show_legend):
                if data.size == 0:
                    return
                fig.add_trace(go.Histogram(
                    x=data, nbinsx=_lg_nbins,
                    histnorm='probability density',
                    name=name, marker_color=color, opacity=0.6,
                    legendgroup=name, showlegend=show_legend,
                ), row=row, col=col)

            def _lg_pos(idx):
                return (idx // _lg_n_cols + 1, idx % _lg_n_cols + 1)

            if _lg_mb_view == 'All binaries (combined)':
                _lg_data_all = [
                    np.log10(lg_P_all) if lg_P_all.size > 0 else lg_P_all,
                    lg_e_all, lg_q_all, lg_K1_all, lg_M1_all, lg_M2_all,
                    lg_i_all, lg_omega_all, lg_T0_all,
                ]
                for pi, d in enumerate(_lg_data_all):
                    r, c = _lg_pos(pi)
                    _lg_add_hist(fig_lg_mb, r, c, d, 'All binaries', _CLR_ALL, pi == 0)
            else:
                _lg_det_data = [
                    np.log10(lg_P_det) if lg_P_det.size > 0 else lg_P_det,
                    lg_e_det, lg_q_det, lg_K1_det, lg_M1_det, lg_M2_det,
                    lg_i_det, lg_omega_det, lg_T0_det,
                ]
                _lg_mis_data = [
                    np.log10(lg_P_mis) if lg_P_mis.size > 0 else lg_P_mis,
                    lg_e_mis, lg_q_mis, lg_K1_mis, lg_M1_mis, lg_M2_mis,
                    lg_i_mis, lg_omega_mis, lg_T0_mis,
                ]
                if _lg_mb_view in ('Compare detected vs missed', 'Detected binaries only'):
                    for pi, d in enumerate(_lg_det_data):
                        r, c = _lg_pos(pi)
                        _lg_add_hist(fig_lg_mb, r, c, d, 'Detected', _CLR_DETECTED, pi == 0)
                if _lg_mb_view in ('Compare detected vs missed', 'Missed binaries only'):
                    for pi, d in enumerate(_lg_mis_data):
                        r, c = _lg_pos(pi)
                        _lg_add_hist(fig_lg_mb, r, c, d, 'Missed', _CLR_MISSED, pi == 0)

            fig_lg_mb.update_layout(**{
                **PLOTLY_THEME,
                'barmode': 'overlay',
                'height': 850,
                'margin': dict(l=40, r=20, t=40, b=60),
                'legend': dict(
                    orientation='h', yanchor='bottom', y=1.04,
                    xanchor='center', x=0.5,
                ),
            })
            for pi in range(_lg_n_panels):
                r, c = _lg_pos(pi)
                fig_lg_mb.update_xaxes(title_text=_lg_x_labels[pi],
                                        showgrid=False, row=r, col=c)
                fig_lg_mb.update_yaxes(showgrid=False, row=r, col=c)
            for row_i in range(1, _lg_n_rows + 1):
                fig_lg_mb.update_yaxes(title_text='Prob. density', row=row_i, col=1)

            st.plotly_chart(fig_lg_mb, use_container_width=True, key='lg_orb_props')
            st.caption(
                f'Orbital parameter distributions (Langer 2020 model, best-fit: '
                f'f_bin={best_fbin_lg:.3f}, σ_single={best_sigma_lg:.1f} km/s). '
                f'**Detected** (red): {lg_detected_bin_count} binaries. '
                f'**Missed** (amber): {lg_missed_count} binaries.'
            )

            # ── Model Explorer ────────────────────────────────────────────────
            st.markdown('---')
            st.markdown('## Model Explorer')

            _lg_me1, _lg_me2, _lg_me3 = st.columns([0.35, 0.35, 0.30])
            lg_ex_fbin = _lg_me1.number_input(
                'f_bin', 0.0, 1.0, best_fbin_lg, 0.001, format='%.4f',
                key='lg_explore_fbin')
            lg_ex_sigma = _lg_me2.number_input(
                'σ_single (km/s)', 0.1, 500.0, best_sigma_lg, 0.1,
                key='lg_explore_sigma')
            lg_sim_btn = _lg_me3.button('Simulate model', type='primary',
                                         key='lg_sim_model')
            st.caption('Pre-filled with best-fit values. Adjust to explore any model point.')

            _lg_sim_cfg_ex = SimulationConfig(
                n_stars=int(lg_n_stars),
                sigma_single=float(lg_ex_sigma),
                sigma_measure=float(lg_sigma_meas),
                cadence_library=lg_cad_a,
                cadence_weights=lg_cad_w_a,
            )

            _lg_need_sim = lg_sim_btn or 'lg_sim_drv' not in st.session_state
            if _lg_need_sim:
                rng_lg_ex = np.random.default_rng(142)
                st.session_state['lg_sim_drv'] = simulate_delta_rv_sample(
                    float(lg_ex_fbin), 0.0,
                    _lg_sim_cfg_ex, _lg_bin_cfg_ex, rng_lg_ex,
                )
                rng_lg_ex2 = np.random.default_rng(142)
                lg_rv_s, lg_rv_b = _simulate_rv_sample_full(
                    float(lg_ex_fbin), 0.0,
                    _lg_sim_cfg_ex, _lg_bin_cfg_ex, rng_lg_ex2,
                )
                st.session_state['lg_sim_rv_single'] = lg_rv_s
                st.session_state['lg_sim_rv_binary'] = lg_rv_b
                st.session_state['lg_explore_vals'] = (
                    float(lg_ex_fbin), float(lg_ex_sigma))

            lg_sim_drv = st.session_state.get('lg_sim_drv')
            lg_sim_rv_single = st.session_state.get('lg_sim_rv_single')
            lg_sim_rv_binary = st.session_state.get('lg_sim_rv_binary')
            lg_ex_fb_v, lg_ex_sig_v = st.session_state.get(
                'lg_explore_vals', (best_fbin_lg, best_sigma_lg))

            if lg_sim_drv is not None:
                # ── CDF Comparison ────────────────────────────────────────────
                st.markdown('### CDF Comparison  (ΔRV)')

                lg_obs_sorted = np.sort(lg_obs_drv_analysis)
                lg_obs_cdf = np.arange(1, len(lg_obs_sorted) + 1) / len(lg_obs_sorted)
                lg_sim_sorted = np.sort(lg_sim_drv)
                lg_sim_cdf = np.arange(1, len(lg_sim_sorted) + 1) / len(lg_sim_sorted)

                lg_D_val, lg_p_val = ks_two_sample(lg_sim_drv, lg_obs_drv_analysis)

                fig_lg_cdf = go.Figure()
                fig_lg_cdf.add_trace(go.Scatter(
                    x=lg_obs_sorted, y=lg_obs_cdf,
                    mode='lines', name='Observed',
                    line=dict(color='#4A90D9', width=2.5),
                ))
                fig_lg_cdf.add_trace(go.Scatter(
                    x=lg_sim_sorted, y=lg_sim_cdf,
                    mode='lines', name='Simulated',
                    line=dict(color='#E25A53', width=2.5, dash='dash'),
                ))
                fig_lg_cdf.update_layout(**{
                    **PLOTLY_THEME,
                    'title': dict(
                        text=(f'ΔRV CDF — Observed vs Langer Model  '
                              f'(f_bin={lg_ex_fb_v:.3f}, σ={lg_ex_sig_v:.1f})'),
                        font=dict(size=14)),
                    'xaxis_title': 'ΔRV (km/s)',
                    'yaxis_title': 'Cumulative fraction',
                    'height': 420,
                    'legend': dict(x=0.65, y=0.15),
                    'annotations': [dict(
                        x=0.98, y=0.95, xref='paper', yref='paper',
                        text=f'K-S D = {lg_D_val:.4f}<br>p = {lg_p_val:.4f}',
                        showarrow=False,
                        font=dict(size=12, color='#333333'),
                        bgcolor='rgba(255,255,255,0.9)',
                        borderpad=6, xanchor='right',
                    )],
                })
                st.plotly_chart(fig_lg_cdf, use_container_width=True, key='lg_cdf')
                st.caption(
                    'CDF of peak-to-peak ΔRV (Langer 2020 model). Higher p-value '
                    'indicates a better match between model and observations.'
                )

                # ── RV Distribution ───────────────────────────────────────────
                st.markdown('### RV Distribution')

                lg_obs_rv_all_list = []
                lg_obs_rv_bin_list = []
                lg_obs_rv_sin_list = []
                for star_name, info in lg_obs_detail.items():
                    rv_arr = info.get('rv')
                    if rv_arr is None or len(rv_arr) == 0:
                        continue
                    lg_obs_rv_all_list.append(rv_arr)
                    if bool(info.get('is_binary', False)):
                        lg_obs_rv_bin_list.append(rv_arr)
                    else:
                        lg_obs_rv_sin_list.append(rv_arr)

                lg_obs_rv_all = np.concatenate(lg_obs_rv_all_list) if lg_obs_rv_all_list else np.array([])
                lg_obs_rv_sin = np.concatenate(lg_obs_rv_sin_list) if lg_obs_rv_sin_list else np.array([])
                lg_obs_rv_bin = np.concatenate(lg_obs_rv_bin_list) if lg_obs_rv_bin_list else np.array([])

                _lg_rv_c1, _lg_rv_c2 = st.columns([0.4, 0.6])
                lg_rv_split = _lg_rv_c1.radio(
                    'Observed RVs', ['All combined', 'Split by classification'],
                    horizontal=True, key='lg_rv_split')
                lg_show_sim_rv = _lg_rv_c2.checkbox(
                    'Overlay simulated RVs', value=True, key='lg_show_sim_rv')

                fig_lg_rv = go.Figure()
                lg_nbins_rv = 40

                if lg_rv_split == 'All combined':
                    if lg_obs_rv_all.size > 0:
                        fig_lg_rv.add_trace(go.Histogram(
                            x=lg_obs_rv_all, nbinsx=lg_nbins_rv,
                            histnorm='probability density',
                            name='Observed (all)',
                            marker_color='#4A90D9', opacity=0.6,
                        ))
                else:
                    if lg_obs_rv_sin.size > 0:
                        fig_lg_rv.add_trace(go.Histogram(
                            x=lg_obs_rv_sin, nbinsx=lg_nbins_rv,
                            histnorm='probability density',
                            name='Observed — single',
                            marker_color='#4A90D9', opacity=0.5,
                        ))
                    if lg_obs_rv_bin.size > 0:
                        fig_lg_rv.add_trace(go.Histogram(
                            x=lg_obs_rv_bin, nbinsx=lg_nbins_rv,
                            histnorm='probability density',
                            name='Observed — binary',
                            marker_color='#E25A53', opacity=0.5,
                        ))

                if lg_show_sim_rv and lg_sim_rv_single is not None:
                    if lg_rv_split == 'All combined':
                        _lg_sim_rv_comb = np.concatenate([lg_sim_rv_single, lg_sim_rv_binary])
                        if _lg_sim_rv_comb.size > 0:
                            fig_lg_rv.add_trace(go.Histogram(
                                x=_lg_sim_rv_comb, nbinsx=lg_nbins_rv,
                                histnorm='probability density',
                                name='Simulated (all)',
                                marker_color='#8C8C8C', opacity=0.4,
                            ))
                    else:
                        if lg_sim_rv_single.size > 0:
                            fig_lg_rv.add_trace(go.Histogram(
                                x=lg_sim_rv_single, nbinsx=lg_nbins_rv,
                                histnorm='probability density',
                                name='Simulated — single',
                                marker_color='#7EC8E3', opacity=0.4,
                            ))
                        if lg_sim_rv_binary.size > 0:
                            fig_lg_rv.add_trace(go.Histogram(
                                x=lg_sim_rv_binary, nbinsx=lg_nbins_rv,
                                histnorm='probability density',
                                name='Simulated — binary',
                                marker_color='#F0A0A0', opacity=0.4,
                            ))

                fig_lg_rv.update_layout(**{
                    **PLOTLY_THEME,
                    'barmode': 'overlay',
                    'title': dict(text='RV Distribution (Langer)', font=dict(size=14)),
                    'xaxis_title': 'RV (km/s)',
                    'yaxis_title': 'Probability density',
                    'height': 420,
                    'legend': dict(x=0.01, y=0.99),
                })
                st.plotly_chart(fig_lg_rv, use_container_width=True, key='lg_rv_dist')
                st.caption(
                    'RV distribution: observed vs simulated (Langer 2020 model).'
                )

                # ── Detection Fraction vs Threshold ───────────────────────────
                st.markdown('### Detection Fraction vs Threshold')

                lg_max_drv = max(float(np.max(lg_obs_drv_analysis)),
                                 float(np.max(lg_sim_drv)))
                lg_thresholds = np.linspace(0, lg_max_drv * 1.1, 150)
                lg_frac_obs = np.array(
                    [(lg_obs_drv_analysis > T).mean() for T in lg_thresholds])
                lg_frac_sim = np.array(
                    [(lg_sim_drv > T).mean() for T in lg_thresholds])

                lg_frac_obs_t = float((lg_obs_drv_analysis > lg_thresh_dRV).mean())
                lg_frac_sim_t = float((lg_sim_drv > lg_thresh_dRV).mean())

                fig_lg_frac = go.Figure()
                fig_lg_frac.add_trace(go.Scatter(
                    x=lg_thresholds, y=lg_frac_obs,
                    mode='lines', name='Observed',
                    line=dict(color='#4A90D9', width=2.5),
                ))
                fig_lg_frac.add_trace(go.Scatter(
                    x=lg_thresholds, y=lg_frac_sim,
                    mode='lines', name='Simulated',
                    line=dict(color='#E25A53', width=2.5, dash='dash'),
                ))
                fig_lg_frac.add_vline(
                    x=lg_thresh_dRV, line_dash='dot',
                    line_color='#DAA520', line_width=1.5,
                    annotation_text=f'Threshold = {lg_thresh_dRV} km/s',
                    annotation_position='top right',
                    annotation_font_color='#DAA520',
                )
                fig_lg_frac.add_trace(go.Scatter(
                    x=[lg_thresh_dRV, lg_thresh_dRV],
                    y=[lg_frac_obs_t, lg_frac_sim_t],
                    mode='markers+text',
                    marker=dict(size=10, color=['#4A90D9', '#E25A53'],
                                symbol='circle',
                                line=dict(color='white', width=1)),
                    text=[f'  {lg_frac_obs_t:.2%}', f'  {lg_frac_sim_t:.2%}'],
                    textposition='middle right',
                    textfont=dict(size=11),
                    showlegend=False,
                ))
                fig_lg_frac.update_layout(**{
                    **PLOTLY_THEME,
                    'title': dict(
                        text=(f'Detection Fraction vs ΔRV Threshold  '
                              f'(Langer: f_bin={lg_ex_fb_v:.3f}, σ={lg_ex_sig_v:.1f})'),
                        font=dict(size=14)),
                    'xaxis_title': 'ΔRV threshold (km/s)',
                    'yaxis_title': 'Fraction above threshold',
                    'height': 420,
                    'legend': dict(x=0.70, y=0.95),
                    'yaxis': dict(range=[0, 1.05]),
                })
                st.plotly_chart(fig_lg_frac, use_container_width=True, key='lg_det_frac')
                st.caption(
                    'Detection fraction as a function of threshold (Langer 2020 model).'
                )

        # ── Summary table ─────────────────────────────────────────────────────
        st.markdown('---')
        lg_summary_rows = []
        for i_f in range(len(lg_fbin_g)):
            bf_v = float(lg_fbin_g[i_f])
            for i_s in range(len(lg_sigma_g)):
                sv = float(lg_sigma_g[i_s])
                pv = float(lg_ks_p_2d[i_f, i_s])
                if pv == float(np.nanmax(lg_ks_p_2d)):
                    lg_summary_rows.append({
                        'f_bin': round(bf_v, 4),
                        'σ_single (km/s)': round(sv, 2),
                        'K-S p': round(pv, 5),
                    })
        if lg_summary_rows:
            st.markdown('### Best Grid Point')
            st.dataframe(pd.DataFrame(lg_summary_rows), use_container_width=True)
