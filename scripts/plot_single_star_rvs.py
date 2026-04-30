"""
scripts/plot_single_star_rvs.py
Plot per-epoch RVs of all *single* stars (binary classification = False),
overlay per-star σ(RV) on a secondary axis, and highlight the stars with
the smallest and largest σ.

Usage:
    conda run -n guyenv python scripts/plot_single_star_rvs.py
"""
from __future__ import annotations
import os, sys, json
import numpy as np
import plotly.graph_objects as go

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, 'app'))

from pipeline.load_observations import load_observed_delta_rvs
from ObservationClass import ObservationManager
import specs

with open(os.path.join(_ROOT, 'settings', 'user_settings.json')) as f:
    settings = json.load(f)

obs = ObservationManager()
_, detail = load_observed_delta_rvs(settings, obs)

singles = []
for name in specs.star_names:
    d = detail.get(name, {})
    rv = np.asarray(d.get('rv', []), dtype=float)
    is_bin = d.get('is_binary')
    if is_bin is False and rv.size >= 2:
        singles.append((name, rv, np.asarray(d.get('rv_err', []), dtype=float)))

singles.sort(key=lambda t: float(np.std(t[1], ddof=1)))

names   = [t[0] for t in singles]
rvs     = [t[1] for t in singles]
rv_errs = [t[2] for t in singles]
stds    = np.array([float(np.std(r, ddof=1)) for r in rvs])
means   = np.array([float(np.mean(r))        for r in rvs])


def std_uncertainty(rv: np.ndarray, rv_err: np.ndarray) -> float:
    """
    Propagate per-epoch RV errors through the sample standard deviation.

        s² = (1/(N-1)) Σ (x_i − x̄)²    ⇒    ∂s/∂x_i = (x_i − x̄) / (s (N-1))
        var(s) = Σ (∂s/∂x_i)² σ_i²
        err(s) = √(Σ (x_i − x̄)² σ_i²) / (s (N-1))
    """
    n = rv.size
    if n < 2:
        return float('nan')
    s = float(np.std(rv, ddof=1))
    if s == 0.0:
        return float('nan')
    d = rv - rv.mean()
    return float(np.sqrt(np.sum(d**2 * rv_err**2)) / (s * (n - 1)))


std_errs = np.array([std_uncertainty(r, e) for r, e in zip(rvs, rv_errs)])

# Peak-to-peak ΔRV per star, with error = √(err_max² + err_min²)
ptp     = np.array([float(r.max() - r.min()) for r in rvs])
ptp_err = np.array([
    float(np.hypot(e[int(np.argmax(r))], e[int(np.argmin(r))]))
    for r, e in zip(rvs, rv_errs)
])

# Inverse-variance weighted mean of σ across the sample
w        = 1.0 / std_errs**2
w_mean   = float(np.sum(stds * w) / np.sum(w))
w_mean_e = float(1.0 / np.sqrt(np.sum(w)))

idx_min = int(np.argmin(stds))
idx_max = int(np.argmax(stds))

print(f'\n{len(singles)} single stars (sorted by σ ascending):')
print(f'{"Star":<20s}  {"N_ep":>4s}  {"<RV>":>8s}  {"σ":>7s}  '
      f'{"err(σ)":>8s}  {"ΔRV_pp":>8s}  {"err(ΔRV)":>9s}')
for i, (name, rv, _) in enumerate(singles):
    tag = ''
    if i == idx_min: tag = '  ← lowest σ'
    if i == idx_max: tag = '  ← largest σ'
    print(f'{name:<20s}  {len(rv):>4d}  {means[i]:>8.2f}  '
          f'{stds[i]:>7.2f}  {std_errs[i]:>8.3f}  '
          f'{ptp[i]:>8.2f}  {ptp_err[i]:>9.3f}{tag}')

print(f'\nInverse-variance weighted mean σ = {w_mean:.3f} ± {w_mean_e:.3f} km/s')
print(f'Unweighted mean σ                = {stds.mean():.3f} ± {stds.std(ddof=1)/np.sqrt(len(stds)):.3f} km/s '
      f'(scatter σ_pop = {stds.std(ddof=1):.3f})')

COLOR_RV    = '#4A90D9'   # steel blue (matches COLOR_SINGLE)
COLOR_STD   = '#E8A33D'   # amber — distinct from RV points
COLOR_MIN   = '#52B788'   # green (lowest σ)
COLOR_MAX   = '#E25A53'   # red   (largest σ)
COLOR_PTP   = '#C77DFF'   # violet — peak-to-peak ΔRV (right axis)
PALETTE_BG  = '#1e1e2e'
PALETTE_FG  = '#e0e0e0'
PALETTE_GRD = '#3a3a4a'

fig = go.Figure()

for i, (name, rv, err) in enumerate(zip(names, rvs, rv_errs)):
    fig.add_trace(go.Scatter(
        x=[name] * len(rv), y=rv,
        mode='markers',
        marker=dict(symbol='circle', size=8, color=COLOR_RV,
                    line=dict(width=0.5, color='#1c3d6b')),
        error_y=dict(type='data', array=err, visible=True,
                     color=COLOR_RV, thickness=1, width=3),
        name='RV (per epoch)' if i == 0 else None,
        legendgroup='rv',
        showlegend=(i == 0),
        hovertemplate=f'{name}<br>RV = %{{y:.2f}} km/s<extra></extra>',
    ))

fig.add_trace(go.Scatter(
    x=names, y=means,
    mode='markers',
    marker=dict(symbol='line-ew', size=22, color=COLOR_RV,
                line=dict(width=2, color=COLOR_RV)),
    name='⟨RV⟩',
    hovertemplate='%{x}<br>⟨RV⟩ = %{y:.2f} km/s<extra></extra>',
))

std_colors = [COLOR_STD] * len(names)
std_colors[idx_min] = COLOR_MIN
std_colors[idx_max] = COLOR_MAX
std_sizes = [13] * len(names)
std_sizes[idx_min] = 18
std_sizes[idx_max] = 18

fig.add_trace(go.Scatter(
    x=names, y=stds,
    mode='markers',
    marker=dict(symbol='diamond', size=std_sizes, color=std_colors,
                line=dict(width=1.2, color='#222222')),
    error_y=dict(type='data', array=std_errs, visible=True,
                 color=COLOR_STD, thickness=1.4, width=5),
    name='σ (RV) ± err(σ)',
    customdata=std_errs,
    hovertemplate='%{x}<br>σ = %{y:.2f} ± %{customdata:.3f} km/s<extra></extra>',
))

fig.add_hline(
    y=w_mean, line=dict(color='#e0e0e0', dash='dash', width=1.2),
    annotation_text=f'weighted ⟨σ⟩ = {w_mean:.2f} ± {w_mean_e:.2f} km/s',
    annotation_position='top right',
    annotation=dict(font=dict(color='#e0e0e0', size=11),
                    bgcolor='rgba(30,30,46,0.7)',
                    bordercolor='#555555', borderwidth=1),
)
fig.add_hrect(
    y0=w_mean - w_mean_e, y1=w_mean + w_mean_e,
    fillcolor='rgba(224,224,224,0.08)', line_width=0,
)

fig.add_trace(go.Scatter(
    x=[names[idx_min]], y=[stds[idx_min]],
    mode='markers+text',
    marker=dict(symbol='diamond-open', size=26, color=COLOR_MIN,
                line=dict(width=2.5, color=COLOR_MIN)),
    text=[f'min σ = {stds[idx_min]:.2f}'],
    textposition='top center',
    textfont=dict(color=COLOR_MIN, size=11),
    name='lowest σ',
    hoverinfo='skip',
))

fig.add_trace(go.Scatter(
    x=[names[idx_max]], y=[stds[idx_max]],
    mode='markers+text',
    marker=dict(symbol='diamond-open', size=26, color=COLOR_MAX,
                line=dict(width=2.5, color=COLOR_MAX)),
    text=[f'max σ = {stds[idx_max]:.2f}'],
    textposition='top center',
    textfont=dict(color=COLOR_MAX, size=11),
    name='largest σ',
    hoverinfo='skip',
))

# Peak-to-peak ΔRV on the right axis
fig.add_trace(go.Scatter(
    x=names, y=ptp,
    mode='markers',
    marker=dict(symbol='triangle-up', size=14, color=COLOR_PTP,
                line=dict(width=1.0, color='#222222')),
    error_y=dict(type='data', array=ptp_err, visible=True,
                 color=COLOR_PTP, thickness=1.4, width=5),
    name='ΔRV peak-to-peak',
    yaxis='y2',
    customdata=ptp_err,
    hovertemplate='%{x}<br>ΔRV<sub>pp</sub> = %{y:.2f} ± '
                  '%{customdata:.3f} km/s<extra></extra>',
))

axis_kw = dict(showgrid=True, gridcolor=PALETTE_GRD, gridwidth=1,
               linecolor='#aaaaaa', linewidth=1, mirror=True,
               ticks='outside', tickcolor='#aaaaaa')

fig.update_layout(
    title=dict(text=f'Per-epoch RVs of {len(singles)} single stars '
                    f'(C IV 5808-5812)  ·  diamonds = σ(RV)  ·  '
                    f'triangles = ΔRV<sub>pp</sub>',
               font=dict(size=15, family='serif', color='#f0f0f0')),
    plot_bgcolor=PALETTE_BG,
    paper_bgcolor=PALETTE_BG,
    font=dict(family='serif', size=13, color=PALETTE_FG),
    xaxis=dict(**axis_kw, title='Star (sorted by σ ascending)', tickangle=-45,
               categoryorder='array', categoryarray=names),
    yaxis=dict(**axis_kw, title='RV  &  σ(RV)   [km s⁻¹]', zeroline=True,
               zerolinecolor='#666666', zerolinewidth=1),
    yaxis2=dict(linecolor=COLOR_PTP, linewidth=1, mirror=False,
                ticks='outside', tickcolor=COLOR_PTP,
                tickfont=dict(color=COLOR_PTP), showgrid=False,
                title=dict(text='ΔRV peak-to-peak  [km s⁻¹]',
                           font=dict(color=COLOR_PTP)),
                overlaying='y', side='right', rangemode='tozero'),
    legend=dict(bgcolor='rgba(30,30,46,0.9)', bordercolor='#555555',
                borderwidth=1, x=0.01, y=0.99),
    height=600, width=max(900, 55 * len(names) + 200),
    margin=dict(l=70, r=80, t=70, b=140),
)

out_html = os.path.join(_ROOT, 'plots', 'single_star_rvs.html')
out_png  = os.path.join(_ROOT, 'plots', 'single_star_rvs.png')
os.makedirs(os.path.dirname(out_html), exist_ok=True)
fig.write_html(out_html, include_plotlyjs='cdn')
print(f'\nSaved interactive HTML: {out_html}')
try:
    fig.write_image(out_png, scale=2)
    print(f'Saved static PNG:      {out_png}')
except Exception as e:
    print(f'(PNG export skipped: {e})')
