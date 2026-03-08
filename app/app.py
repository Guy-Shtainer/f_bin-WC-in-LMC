"""
app/app.py
──────────
Home dashboard — entry point for the WR binary analysis Streamlit app.

Launch:
    conda run -n guyenv streamlit run app/app.py
"""

from __future__ import annotations

import math
import os
import sys

# ── Path fix ──────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from shared import (
    inject_theme, render_sidebar, get_settings_manager,
    cached_load_observed_delta_rvs, settings_hash, preload_all_data,
    cached_load_grid_result, cached_load_nres_rvs,
    find_best_grid_point, make_heatmap_fig,
    COLOR_BINARY, COLOR_SINGLE, COLOR_UNKNOWN, COLOR_CLEANED,
    PLOTLY_THEME, load_run_history,
)
import specs

# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title='WR Binary Analysis',
    page_icon='🌟',
    layout='wide',
    initial_sidebar_state='expanded',
)
inject_theme()

# ─────────────────────────────────────────────────────────────────────────────
# One-time session preload
# ─────────────────────────────────────────────────────────────────────────────
sm = get_settings_manager()
_settings_early = sm.load()

if not st.session_state.get('_preloaded', False):
    _prog = st.progress(0.0, text='🔭 Initializing WR Binary Analysis…')
    _prog.progress(0.2, text='Loading star RVs and classifications (parallel)…')
    try:
        preload_all_data(_settings_early)
        _prog.progress(1.0, text='Ready!')
    except Exception as _e:
        st.warning(f'Preload warning (non-fatal): {_e}')
        st.session_state['_preloaded'] = True
    _prog.empty()

settings = render_sidebar('Home')

# ─────────────────────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('# 🌟 WR Binary Analysis Dashboard')
st.markdown(
    'Monte-Carlo bias simulation for WR single + binary LMC populations '
    '(Dsilva-style power-law period model). '
    'Use the sidebar to navigate or save the current analysis state.'
)

# ─────────────────────────────────────────────────────────────────────────────
# Load observed data (already in cache from preload)
# ─────────────────────────────────────────────────────────────────────────────
sh = settings_hash(settings)

try:
    obs_delta_rv, detail = cached_load_observed_delta_rvs(sh)
    data_loaded = True
except Exception as e:
    st.warning(f'Could not load star data: {e}')
    obs_delta_rv = np.zeros(len(specs.star_names))
    detail = {}
    data_loaded = False

cls_cfg    = settings.get('classification', {})
threshold  = cls_cfg.get('threshold_dRV', 45.5)
bartzakos  = cls_cfg.get('bartzakos_binaries', 3)
total_pop  = cls_cfg.get('total_population', 28)

n_stars    = len(specs.star_names)
n_binary   = sum(1 for d in detail.values() if d.get('is_binary') is True)
n_unknown  = sum(1 for d in detail.values() if d.get('is_binary') is None)

obs_frac   = (n_binary + bartzakos) / total_pop

# Load grid result for best K-S p
grid_result = cached_load_grid_result('dsilva')
best_pval = None
if grid_result is not None:
    try:
        ks_p_2d = grid_result['ks_p_values']
        fbin_vals = grid_result['fbin_values']
        pi_vals = grid_result['pi_values']
        _, _, best_pval = find_best_grid_point(ks_p_2d, fbin_vals, pi_vals)
    except (KeyError, Exception):
        best_pval = None

# ─────────────────────────────────────────────────────────────────────────────
# Metric cards (5 across top)
# ─────────────────────────────────────────────────────────────────────────────
def _metric_card(container: DeltaGenerator, label: str, value: str, sub: str = '') -> None:
    container.markdown(f"""
    <div class="metric-card">
        <div class="label">{label}</div>
        <div class="value">{value}</div>
        <div class="sub">{sub}</div>
    </div>
    """, unsafe_allow_html=True)


col1, col2, col3, col4, col5 = st.columns(5)
_metric_card(col1, 'Total stars', str(n_stars), 'in our sample')
_metric_card(col2, 'Detected binaries', str(n_binary),
             f'+ {bartzakos} Bartzakos = {n_binary + bartzakos}')
_metric_card(col3, 'Binary fraction',
             f'{obs_frac * 100:.1f}%',
             f'({n_binary}+{bartzakos})/{total_pop}')
_metric_card(col4, 'Threshold', f'{threshold:.1f} km/s', 'ΔRV detection limit')
_metric_card(col5, 'Best K-S p',
             f'{best_pval:.3f}' if best_pval is not None else '—',
             'Dsilva grid' if best_pval is not None else 'no grid run yet')

st.markdown('<br>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Star status table
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('## Star Status')

if data_loaded and detail:
    # Status filter
    status_options = ['All', 'Binary', 'Single', 'No data']
    status_filter = st.selectbox('Filter by status', status_options, index=0,
                                  key='home_status_filter')

    rows = []
    for star_name in specs.star_names:
        d = detail.get(star_name, {})
        is_bin = d.get('is_binary')
        drv    = d.get('best_dRV', 0.0)
        sigma  = d.get('best_sigma', float('nan'))

        # Safe sigma check — avoid numpy truth-value ambiguity (E018)
        if not math.isnan(float(sigma)) and float(sigma) > 0:
            sig_val = drv / float(sigma)
        else:
            sig_val = float('nan')

        if is_bin is True:
            status_icon = '✓ BINARY'
            status_color = 'binary'
        elif is_bin is None:
            status_icon = '? NO DATA'
            status_color = 'unknown'
        else:
            status_icon = '✗ single'
            status_color = 'single'

        # Apply filter
        if status_filter == 'Binary' and status_color != 'binary':
            continue
        elif status_filter == 'Single' and status_color != 'single':
            continue
        elif status_filter == 'No data' and status_color != 'unknown':
            continue

        # RV per epoch (safe numpy array check)
        rv_arr = d.get('rv', [])
        rv_err_arr = d.get('rv_err', [])
        if isinstance(rv_arr, np.ndarray):
            n_epochs = len(rv_arr[rv_arr != 0]) if len(rv_arr) > 0 else 0
        else:
            n_epochs = len(rv_arr) if rv_arr else 0

        rows.append({
            'Star': star_name,
            'Status': status_icon,
            'ΔRV (km/s)': round(drv, 1),
            'σ (km/s)': round(float(sigma), 1) if not math.isnan(float(sigma)) else '—',
            'Significance (σ)': round(sig_val, 1) if not math.isnan(sig_val) else '—',
            'Epochs': n_epochs,
            '_color': status_color,
        })

    df = pd.DataFrame(rows)

    # Color styling
    def _style_status(val: str) -> str:
        if 'BINARY' in val:
            return f'color: {COLOR_BINARY}; font-weight: 600'
        elif 'single' in val:
            return f'color: {COLOR_SINGLE}'
        return f'color: {COLOR_UNKNOWN}'

    display_df = df.drop(columns=['_color'])
    styled = (
        display_df.style
        .map(_style_status, subset=['Status'])
        .format({
            'ΔRV (km/s)': '{:.1f}',
            'Significance (σ)': lambda x: f'{x:.1f}' if isinstance(x, float) else x,
            'σ (km/s)': lambda x: f'{x:.1f}' if isinstance(x, float) else x,
        })
        .set_properties(**{'text-align': 'left'})
    )

    st.dataframe(styled, use_container_width=True, height=500)

    # Summary row counts
    colA, colB, colC = st.columns(3)
    colA.metric('Binary', n_binary, delta=None)
    colB.metric('Single', n_stars - n_binary - n_unknown)
    colC.metric('Insufficient data', n_unknown)
else:
    st.info('Star data not loaded. Check that Data/ directory is accessible.')

# ─────────────────────────────────────────────────────────────────────────────
# Scientific Plots (2x2 grid)
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('## Analysis Overview')

if data_loaded and detail:
    plot_col1, plot_col2 = st.columns(2)

    # ── (a) Binary fraction vs threshold ──────────────────────────────────
    with plot_col1:
        st.markdown('### Binary Fraction vs ΔRV Threshold')
        thresholds = np.linspace(5, 200, 100)
        fracs = []
        for thr in thresholds:
            n_det = sum(
                1 for d in detail.values()
                if d.get('is_binary') is not None and d.get('best_dRV', 0.0) > thr
            )
            fracs.append((n_det + bartzakos) / total_pop)
        fracs = np.array(fracs)

        fig_frac = go.Figure()
        fig_frac.add_trace(go.Scatter(
            x=thresholds, y=fracs * 100,
            mode='lines',
            line=dict(color=COLOR_BINARY, width=2),
            name='Detected fraction',
        ))
        fig_frac.add_vline(
            x=threshold, line_dash='dash', line_color='grey',
            annotation_text=f'threshold = {threshold:.1f}',
            annotation_position='top right',
        )
        fig_frac.update_layout(**{
            **PLOTLY_THEME,
            'title': dict(text='Detection Fraction vs Threshold', font=dict(size=14)),
            'xaxis_title': 'ΔRV threshold (km/s)',
            'yaxis_title': 'Binary fraction (%)',
            'height': 400,
            'margin': dict(l=60, r=20, t=50, b=50),
            'showlegend': False,
        })
        st.plotly_chart(fig_frac, use_container_width=True)
        st.caption('Fraction of stars classified as binary as a function of the ΔRV detection threshold.')

    # ── (b) K-S heatmap (if grid result available) ────────────────────────
    with plot_col2:
        st.markdown('### K-S p-value Heatmap')
        if grid_result is not None:
            try:
                fig_heatmap = make_heatmap_fig(
                    ks_p_2d, fbin_vals, pi_vals,
                    title='Dsilva K-S p-value',
                    height=400,
                )
                st.plotly_chart(fig_heatmap, use_container_width=True)
                st.caption('K-S test p-value grid: higher values (blue) indicate better agreement with observations.')
            except Exception as exc:
                st.info(f'Could not render K-S heatmap: {exc}')
        else:
            st.info('No Dsilva grid result available. Run the Bias Correction page first.')

    # ── Row 2 ─────────────────────────────────────────────────────────────
    plot_col3, plot_col4 = st.columns(2)

    # ── (c) Model detection fraction with observed toggle ─────────────────
    with plot_col3:
        st.markdown('### Model Detection Fraction')
        if grid_result is not None:
            try:
                best_fbin, best_pi, _ = find_best_grid_point(ks_p_2d, fbin_vals, pi_vals)

                sim_cfg_dict = settings.get('simulation', {})
                n_sim = sim_cfg_dict.get('n_stars_sim', 10000)

                from wr_bias_simulation import (
                    SimulationConfig, BinaryParameterConfig,
                    simulate_delta_rv_sample,
                )

                sim_cfg = SimulationConfig(n_stars=n_sim)
                bin_cfg = BinaryParameterConfig()
                rng = np.random.default_rng(42)

                # Cache simulation for reuse in CDF plot
                _sim_key = f'home_sim_{best_fbin:.4f}_{best_pi:.3f}_{n_sim}'
                if _sim_key not in st.session_state:
                    st.session_state[_sim_key] = simulate_delta_rv_sample(
                        best_fbin, best_pi, sim_cfg, bin_cfg, rng
                    )
                sim_drv = st.session_state[_sim_key]

                # Detection fraction vs threshold for model
                model_fracs = []
                for thr in thresholds:
                    model_fracs.append(np.mean(sim_drv > thr))
                model_fracs = np.array(model_fracs)

                fig_det = go.Figure()
                fig_det.add_trace(go.Scatter(
                    x=thresholds, y=model_fracs * 100,
                    mode='lines',
                    line=dict(color='#E25A53', width=2, dash='dash'),
                    name=f'Model (f={best_fbin:.2f}, π={best_pi:.2f})',
                ))

                # Toggle: overlay observed curve
                show_obs = st.checkbox('Overlay observed curve', value=True,
                                        key='home_overlay_obs')
                if show_obs:
                    fig_det.add_trace(go.Scatter(
                        x=thresholds, y=fracs * 100,
                        mode='lines',
                        line=dict(color=COLOR_BINARY, width=2),
                        name='Observed',
                    ))

                fig_det.add_vline(
                    x=threshold, line_dash='dash', line_color='grey',
                )
                fig_det.update_layout(**{
                    **PLOTLY_THEME,
                    'title': dict(text='Detection Fraction: Model vs Observed', font=dict(size=14)),
                    'xaxis_title': 'ΔRV threshold (km/s)',
                    'yaxis_title': 'Detection fraction (%)',
                    'height': 400,
                    'margin': dict(l=60, r=20, t=50, b=50),
                })
                st.plotly_chart(fig_det, use_container_width=True)
                st.caption('Simulated detection fraction at best-fit parameters compared with observed.')
            except Exception as exc:
                st.info(f'Could not render model detection fraction: {exc}')
        else:
            st.info('Run a Dsilva grid search first to see model detection fraction.')

    # ── (d) CDF comparison ────────────────────────────────────────────────
    with plot_col4:
        st.markdown('### CDF Comparison')
        if grid_result is not None and '_sim_key' in dir() and _sim_key in st.session_state:
            try:
                sim_drv_sorted = np.sort(st.session_state[_sim_key])
                obs_sorted = np.sort(obs_delta_rv[obs_delta_rv > 0])

                fig_cdf = go.Figure()
                # Observed CDF
                if len(obs_sorted) > 0:
                    obs_cdf = np.arange(1, len(obs_sorted) + 1) / len(obs_sorted)
                    fig_cdf.add_trace(go.Scatter(
                        x=obs_sorted, y=obs_cdf,
                        mode='lines',
                        line=dict(color=COLOR_SINGLE, width=2),
                        name='Observed',
                    ))
                # Simulated CDF
                sim_cdf = np.arange(1, len(sim_drv_sorted) + 1) / len(sim_drv_sorted)
                fig_cdf.add_trace(go.Scatter(
                    x=sim_drv_sorted, y=sim_cdf,
                    mode='lines',
                    line=dict(color='#E25A53', width=2, dash='dash'),
                    name='Simulated',
                ))

                fig_cdf.update_layout(**{
                    **PLOTLY_THEME,
                    'title': dict(text='ΔRV CDF: Observed vs Simulated', font=dict(size=14)),
                    'xaxis_title': 'ΔRV (km/s)',
                    'yaxis_title': 'Cumulative fraction',
                    'height': 400,
                    'margin': dict(l=60, r=20, t=50, b=50),
                })
                st.plotly_chart(fig_cdf, use_container_width=True)
                st.caption('Cumulative distribution: observed (solid) vs best-fit simulated (dashed).')
            except Exception as exc:
                st.info(f'Could not render CDF comparison: {exc}')
        else:
            st.info('Run a Dsilva grid search first to see CDF comparison.')

# ─────────────────────────────────────────────────────────────────────────────
# NRES table
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('## NRES Observations')
nres_data = cached_load_nres_rvs()
if nres_data:
    nres_rows = [{'Star': k, **v} for k, v in nres_data.items()]
    st.dataframe(pd.DataFrame(nres_rows), use_container_width=True)
    st.caption('NRES multi-fiber RV observations (supplementary to X-SHOOTER).')
else:
    st.info('No NRES data available yet. NRES observations will appear here when processed.')

# ─────────────────────────────────────────────────────────────────────────────
# Workflow Status (Task #31)
# ─────────────────────────────────────────────────────────────────────────────
with st.expander('📋 Pipeline Workflow Status', expanded=False):
    # Auto-detect statuses
    has_data = os.path.isdir(os.path.join(_ROOT, 'Data'))
    has_rvs = data_loaded and len(detail) > 0
    has_classification = has_rvs and any(
        d.get('is_binary') is not None for d in detail.values()
    )
    has_dsilva_grid = cached_load_grid_result('dsilva') is not None
    has_langer_grid = cached_load_grid_result('langer') is not None
    has_plots = os.path.isdir(os.path.join(_ROOT, 'plots')) and len(
        [f for f in os.listdir(os.path.join(_ROOT, 'plots')) if f.endswith('.png')]
    ) > 0 if os.path.isdir(os.path.join(_ROOT, 'plots')) else False

    def _status_icon(done: bool) -> str:
        return '✅' if done else '⬜'

    workflow_items = [
        ('Raw FITS data loaded', has_data),
        ('RVs computed (CCF)', has_rvs),
        ('Binary classification applied', has_classification),
        ('Dsilva grid search complete', has_dsilva_grid),
        ('Langer grid search complete', has_langer_grid),
        ('Publication plots exported', has_plots),
    ]

    for label, done in workflow_items:
        st.markdown(f'{_status_icon(done)} {label}')

    completed = sum(1 for _, d in workflow_items if d)
    st.progress(completed / len(workflow_items),
                text=f'{completed}/{len(workflow_items)} steps complete')

# ─────────────────────────────────────────────────────────────────────────────
# Recent runs (in expander)
# ─────────────────────────────────────────────────────────────────────────────
with st.expander('🕐 Recent Grid Runs', expanded=False):
    history = load_run_history()
    if history:
        recent = list(reversed(history))[:5]
        run_rows = []
        for r in recent:
            cfg = r.get('config', {})
            run_rows.append({
                'Timestamp':   r.get('timestamp', '')[:19],
                'Model':       r.get('model', '—'),
                'Grid':        f"{cfg.get('fbin_steps','?')}×{cfg.get('pi_steps','?')}",
                'N sim/pt':    cfg.get('n_stars_sim', '—'),
                'Time (s)':    r.get('elapsed_s', '—'),
                'Result file': os.path.basename(r.get('result_file', '—')),
            })
        st.dataframe(pd.DataFrame(run_rows), use_container_width=True)
    else:
        st.info('No grid runs yet. Run the Bias Correction page to generate results.')

# ─────────────────────────────────────────────────────────────────────────────
# Quick start
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('## Quick Start')
st.markdown("""
| Step | Where | What |
|------|-------|------|
| 1 | **Stars** page | Review star classifications and ΔRV values |
| 2 | **Spectrum** page | Browse spectra and RV per epoch |
| 3 | **CCF** page | Run cross-correlation to compute RVs |
| 4 | **Classification** page | Adjust threshold and sigma_factor live |
| 5 | **Grid Search** page | Run Dsilva grid and find best (f_bin, π) |
| 6 | **Results** page | Compare CDF, export tables and plots |

Use **⚙️ Settings** to edit all parameters. Use **💾 Save current state** (sidebar) to snapshot the analysis at any point.
""")
