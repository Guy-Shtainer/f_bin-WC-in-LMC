"""
app/app.py
──────────
Home dashboard — entry point for the WR binary analysis Streamlit app.

Launch:
    conda run -n guyenv streamlit run app/app.py
"""

from __future__ import annotations

import os
import sys

# ── Path fix ──────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import numpy as np
import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from shared import (
    inject_theme, render_sidebar, get_settings_manager,
    cached_load_observed_delta_rvs, settings_hash, preload_all_data,
    COLOR_BINARY, COLOR_SINGLE, COLOR_UNKNOWN, COLOR_CLEANED,
    load_run_history,
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
# One-time session preload — runs once when the browser first opens the app.
# After this, every page gets data from memory with no disk I/O.
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
n_cleaned  = 0  # computed below lazily

obs_frac   = (n_binary + bartzakos) / total_pop

# ─────────────────────────────────────────────────────────────────────────────
# Metric cards (4 across top)
# ─────────────────────────────────────────────────────────────────────────────
def _metric_card(container: DeltaGenerator, label: str, value: str, sub: str = '') -> None:
    container.markdown(f"""
    <div class="metric-card">
        <div class="label">{label}</div>
        <div class="value">{value}</div>
        <div class="sub">{sub}</div>
    </div>
    """, unsafe_allow_html=True)


col1, col2, col3, col4 = st.columns(4)
_metric_card(col1, 'Total stars', str(n_stars), 'in our sample')
_metric_card(col2, 'Detected binaries', str(n_binary),
             f'+ {bartzakos} Bartzakos = {n_binary + bartzakos}')
_metric_card(col3, 'Binary fraction',
             f'{obs_frac * 100:.1f}%',
             f'({n_binary}+{bartzakos})/{total_pop}')
_metric_card(col4, 'Threshold', f'{threshold:.1f} km/s', 'ΔRV detection limit')

st.markdown('<br>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# Star status table
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('## Star Status')

if data_loaded and detail:
    rows = []
    for star_name in specs.star_names:
        d = detail.get(star_name, {})
        is_bin = d.get('is_binary')
        drv    = d.get('best_dRV', 0.0)
        sigma  = d.get('best_sigma', float('nan'))
        sig_val = drv / sigma if (sigma and sigma > 0) else float('nan')

        if is_bin is True:
            status_icon = '✓ BINARY'
            status_color = 'binary'
        elif is_bin is None:
            status_icon = '? NO DATA'
            status_color = 'unknown'
        else:
            status_icon = '✗ single'
            status_color = 'single'

        n_epochs = len(d.get('rv', []))
        rows.append({
            'Star': star_name,
            'Status': status_icon,
            'ΔRV (km/s)': round(drv, 1),
            'Significance (σ)': round(sig_val, 1) if not np.isnan(sig_val) else '—',
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
        .format({'ΔRV (km/s)': '{:.1f}', 'Significance (σ)': lambda x: f'{x:.1f}' if isinstance(x, float) else x})
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
# Recent runs
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('## Recent Grid Runs')
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
    st.info('No grid runs yet. Run `python pipeline/dsilva_grid.py` or use the Grid Search page.')

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
