"""
pages/08_results.py — Results & Export
Load dsilva_result.npz, compare CDF, export tables and plots.
"""
from __future__ import annotations
import io, os, sys, zipfile
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
    cached_load_observed_delta_rvs, settings_hash,
    COLOR_BINARY, COLOR_SINGLE,
)
import specs

st.set_page_config(page_title='Results — WR Binary', page_icon='📈', layout='wide')
inject_theme()
settings = render_sidebar('Results')
sm = get_settings_manager()

st.markdown('# 📈 Results & Export')

# ─────────────────────────────────────────────────────────────────────────────
# Load result
# ─────────────────────────────────────────────────────────────────────────────
result_files = {
    'Dsilva': os.path.join(_ROOT, 'results', 'dsilva_result.npz'),
    'Langer': os.path.join(_ROOT, 'results', 'langer_result.npz'),
}
available = {k: v for k, v in result_files.items() if os.path.exists(v)}

if not available:
    st.info('No grid results found. Run the Dsilva grid first.')
    st.stop()

model_choice = st.selectbox('Model result', list(available.keys()), key='res_model')
result_path  = available[model_choice]
result       = dict(np.load(result_path, allow_pickle=True))

fbin_grid = np.asarray(result['fbin_grid'])
pi_grid   = np.asarray(result['pi_grid'])
ks_p = np.squeeze(np.asarray(result['ks_p']), axis=0)
ks_D = np.squeeze(np.asarray(result['ks_D']), axis=0)

best_flat = int(np.argmax(ks_p))
bfi = best_flat // ks_p.shape[1]
bpi = best_flat  % ks_p.shape[1]
best_fbin = float(fbin_grid[bfi])
best_pi   = float(pi_grid[bpi])
best_pval = float(ks_p[bfi, bpi])

cls_cfg   = settings.get('classification', {})
bartzakos = cls_cfg.get('bartzakos_binaries', 3)
total_pop = cls_cfg.get('total_population', 28)
threshold = cls_cfg.get('threshold_dRV', 45.5)

# Observed fraction
sh = settings_hash(settings)
try:
    obs_delta_rv, detail = cached_load_observed_delta_rvs(sh)
except Exception as e:
    st.error(str(e))
    st.stop()
n_det = int(np.sum(obs_delta_rv > threshold))
obs_frac = (n_det + bartzakos) / total_pop

# ── Summary metrics ───────────────────────────────────────────────────────────
st.markdown('## Summary')
c1, c2, c3, c4 = st.columns(4)
c1.metric('Best f_bin', f'{best_fbin:.4f}')
c2.metric('Best π', f'{best_pi:.4f}')
c3.metric('Best K-S p', f'{best_pval:.4f}')
c4.metric('Obs. binary fraction', f'{obs_frac*100:.1f}%',
          f'({n_det}+{bartzakos})/{total_pop}')

st.markdown('---')

# ─────────────────────────────────────────────────────────────────────────────
# Plots
# ─────────────────────────────────────────────────────────────────────────────
tab_heatmap, tab_cdf, tab_slice = st.tabs(['K-S Heatmap', 'CDF Comparison', 'f_bin Slice'])

with tab_heatmap:
    fig = go.Figure(go.Heatmap(
        z=ks_p, x=pi_grid, y=fbin_grid, colorscale='RdBu_r',
        colorbar=dict(title='K-S p-value'),
        hovertemplate='π=%{x:.2f}<br>f_bin=%{y:.3f}<br>p=%{z:.4f}<extra></extra>',
    ))
    fig.add_trace(go.Scatter(
        x=[best_pi], y=[best_fbin], mode='markers',
        marker=dict(symbol='star', size=14, color='gold', line=dict(width=1, color='black')),
        name=f'Best: f_bin={best_fbin:.3f}, π={best_pi:.2f}',
    ))
    fig.update_layout(
        title=f'{model_choice} — K-S p-value heatmap',
        xaxis_title='π  (period power-law index)',
        yaxis_title='f_bin  (intrinsic binary fraction)',
        plot_bgcolor='#1a1a2e', paper_bgcolor='#1a1a2e',
        font_color='#e0e0e0', height=520,
    )
    st.plotly_chart(fig, use_container_width=True)

with tab_cdf:
    # Re-simulate at best point for CDF
    from wr_bias_simulation import SimulationConfig, BinaryParameterConfig, simulate_delta_rv_sample
    gcfg = settings.get('grid_dsilva', {})
    simcfg = settings.get('simulation', {})
    sim_cfg_obj = SimulationConfig(
        n_stars=int(gcfg.get('n_stars_sim', 3000)),
        sigma_single=float(simcfg.get('sigma_single', 5.5)),
        sigma_measure=float(simcfg.get('sigma_measure', 1.622)),
    )
    bin_cfg_obj = BinaryParameterConfig(
        logP_min=float(gcfg.get('logP_min', 0.15)),
        logP_max=float(gcfg.get('logP_max', 5.0)),
        period_model='powerlaw', e_model='flat',
    )
    rng     = np.random.default_rng(42)
    sim_drv = simulate_delta_rv_sample(best_fbin, best_pi, sim_cfg_obj, bin_cfg_obj, rng)

    obs_s = np.sort(obs_delta_rv)
    sim_s = np.sort(sim_drv)
    obs_c = np.arange(1, len(obs_s)+1) / len(obs_s)
    sim_c = np.arange(1, len(sim_s)+1) / len(sim_s)

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=obs_s, y=obs_c, mode='lines',
                              line=dict(color=COLOR_BINARY, width=2),
                              name=f'Observed (n={len(obs_s)})'))
    fig2.add_trace(go.Scatter(x=sim_s, y=sim_c, mode='lines',
                              line=dict(color=COLOR_SINGLE, width=2),
                              name=f'Simulated (f_bin={best_fbin:.3f}, π={best_pi:.2f})'))
    fig2.update_layout(
        xaxis_title='ΔRV (km/s)', yaxis_title='Cumulative fraction',
        title=f'Best-fit CDF comparison — K-S p = {best_pval:.4f}',
        plot_bgcolor='#1a1a2e', paper_bgcolor='#1a1a2e',
        font_color='#e0e0e0', height=420,
    )
    st.plotly_chart(fig2, use_container_width=True)

with tab_slice:
    fig3 = go.Figure(go.Scatter(
        x=fbin_grid, y=ks_p[:, bpi], mode='lines',
        line=dict(color='#4A90D9', width=2)))
    fig3.add_vline(x=best_fbin, line_dash='dash', line_color='gold',
                   annotation_text=f'Best f_bin={best_fbin:.3f}')
    fig3.update_layout(
        xaxis_title='f_bin', yaxis_title='K-S p-value (log)', yaxis_type='log',
        title=f'p-value vs f_bin at π = {best_pi:.2f}',
        plot_bgcolor='#1a1a2e', paper_bgcolor='#1a1a2e',
        font_color='#e0e0e0', height=380,
    )
    st.plotly_chart(fig3, use_container_width=True)

st.markdown('---')

# ─────────────────────────────────────────────────────────────────────────────
# Classification table + export
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('## Classification table')
rows_cls = []
for sn in specs.star_names:
    d     = detail.get(sn, {})
    is_b  = d.get('is_binary')
    drv   = d.get('best_dRV', 0.0)
    rows_cls.append({
        'Star': sn,
        'ΔRV (km/s)': round(drv, 1),
        'is_binary': is_b,
        'Status': ('Binary' if is_b is True else ('No data' if is_b is None else 'Single')),
    })
cls_df = pd.DataFrame(rows_cls)
st.dataframe(cls_df, use_container_width=True)

# ── Export ZIP ────────────────────────────────────────────────────────────────
st.markdown('### Export')
if st.button('📦 Export results ZIP (CSV + plots)'):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        # CSV
        zf.writestr('classification_table.csv', cls_df.to_csv(index=False))
        # Plots
        plots_dir = os.path.join(_ROOT, 'plots')
        if os.path.isdir(plots_dir):
            for fn in os.listdir(plots_dir):
                if fn.lower().endswith(('.png', '.pdf')):
                    zf.write(os.path.join(plots_dir, fn), fn)
    buf.seek(0)
    st.download_button('📥 Download ZIP', buf, 'wr_results.zip', 'application/zip')
