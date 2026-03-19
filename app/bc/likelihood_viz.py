"""bc.likelihood_viz — CDF, statistics table, and explanation for multinomial likelihood."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def render_likelihood_cdf(
    obs_delta_rv: np.ndarray,
    result: dict,
    bin_edges: np.ndarray,
    prefix: str,
    theme: dict,
    *,
    x_name: str = 'pi',
) -> np.ndarray | None:
    """CDF comparison (observed vs simulated at best-fit) with optional bin overlay.

    Returns the simulated ΔRV array (for reuse in stats table), or None on failure.
    """
    from wr_bias_simulation import (
        binned_cdf, DEFAULT_DRV_BIN_EDGES,
        simulate_delta_rv_sample, SimulationConfig, BinaryParameterConfig,
        multinomial_log_likelihood,
    )

    obs_drv = np.abs(np.asarray(obs_delta_rv))
    lk_edges = np.asarray(bin_edges)
    fine_edges = DEFAULT_DRV_BIN_EDGES

    # --- Extract best-fit parameters from result ---
    # Try likelihood-specific best, fall back to global
    _lk_p = result.get('likelihood')
    if _lk_p is None:
        _lk_p = result.get('ks_p')
    if _lk_p is None:
        st.info('No likelihood data available for CDF.')
        return None

    _lk_p = np.asarray(_lk_p, dtype=float)
    if not np.any(np.isfinite(_lk_p)):
        st.info('No finite likelihood values.')
        return None

    flat_best = int(np.nanargmax(_lk_p))
    best_idx = np.unravel_index(flat_best, _lk_p.shape)

    fbin_g = np.asarray(result.get('fbin_grid', [0.5]))
    x_g = np.asarray(result.get('pi_grid', result.get('sigma_grid', [0.0])))
    sigma_g = np.asarray(result.get('sigma_grid', [5.0]))

    # Map best index to param values depending on dimensionality
    if _lk_p.ndim == 4:
        fb = float(fbin_g[best_idx[2]])
        pi_v = float(x_g[best_idx[3]])
        sig_v = float(sigma_g[best_idx[1]])
    elif _lk_p.ndim == 3:
        fb = float(fbin_g[best_idx[1]])
        pi_v = float(x_g[best_idx[2]])
        sig_v = float(sigma_g[best_idx[0]])
    else:
        fb = float(fbin_g[best_idx[0]])
        pi_v = float(x_g[best_idx[1]])
        sig_v = float(sigma_g[0]) if sigma_g.size else 5.0

    n_obs_stars = len(obs_drv)
    n_cdf_sets = 100

    # --- Simulate ΔRV at best-fit ---
    sim_cfg = SimulationConfig(
        n_stars=n_obs_stars,
        sigma_single=sig_v,
        sigma_measure=float(result.get('sigma_meas', 3.0)),
    )
    bin_cfg = BinaryParameterConfig()

    all_cdfs = []
    all_sim_drv = []
    for seed_i in range(n_cdf_sets):
        rng = np.random.default_rng(42 + seed_i)
        sim_drv = simulate_delta_rv_sample(
            f_bin=fb, pi=pi_v,
            sim_cfg=sim_cfg, bin_cfg=bin_cfg, rng=rng)
        all_cdfs.append(binned_cdf(sim_drv, fine_edges))
        all_sim_drv.append(sim_drv)

    all_cdfs = np.array(all_cdfs)
    pooled_sim = np.concatenate(all_sim_drv)
    median_cdf = np.median(all_cdfs, axis=0)
    lo_cdf = np.percentile(all_cdfs, 16, axis=0)
    hi_cdf = np.percentile(all_cdfs, 84, axis=0)

    obs_cdf = binned_cdf(obs_drv, fine_edges)

    # Compute log-likelihood at best-fit
    logL = multinomial_log_likelihood(obs_drv, pooled_sim, lk_edges)

    # --- Build CDF plot ---
    obs_x = np.concatenate([[0.0], fine_edges])
    obs_y = np.concatenate([[0.0], obs_cdf])
    med_x = np.concatenate([[0.0], fine_edges])
    med_y = np.concatenate([[0.0], median_cdf])
    lo_y = np.concatenate([[0.0], lo_cdf])
    hi_y = np.concatenate([[0.0], hi_cdf])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=obs_x, y=obs_y,
        mode='lines', name='Observed',
        line=dict(color='#4A90D9', width=2.5),
    ))
    # Confidence band
    fig.add_trace(go.Scatter(
        x=np.concatenate([med_x, med_x[::-1]]),
        y=np.concatenate([hi_y, lo_y[::-1]]),
        fill='toself', fillcolor='rgba(226, 90, 83, 0.2)',
        line=dict(color='rgba(0,0,0,0)'),
        legendgroup='sim_lk', showlegend=False, hoverinfo='skip',
    ))
    fig.add_trace(go.Scatter(
        x=med_x, y=med_y,
        mode='lines', name=f'Simulated (f_bin={fb:.3f}, π={pi_v:.2f}, σ={sig_v:.1f})',
        legendgroup='sim_lk',
        line=dict(color='#E25A53', width=2.5, dash='dash'),
    ))

    # --- Binning overlay (checkbox) ---
    show_bins = st.checkbox('Show likelihood bins on CDF', value=False,
                            key=f'{prefix}_lk_show_bins')
    if show_bins:
        _colors = ['rgba(100,100,100,0.08)', 'rgba(100,100,100,0.15)']
        for bi in range(len(lk_edges) - 1):
            lo_e = lk_edges[bi]
            hi_e = min(lk_edges[bi + 1], fine_edges[-1] + 20)
            fig.add_vrect(
                x0=lo_e, x1=hi_e,
                fillcolor=_colors[bi % 2],
                layer='below', line_width=0,
            )
            fig.add_vline(
                x=lo_e, line=dict(color='grey', width=1, dash='dot'),
            )
            # Bin label at top
            mid = (lo_e + min(hi_e, fine_edges[-1])) / 2
            fig.add_annotation(
                x=mid, y=1.02, yref='paper',
                text=f'Bin {bi+1}', showarrow=False,
                font=dict(size=10, color='grey'),
            )

    fig.update_layout(**{
        **theme,
        'title': dict(
            text=f'CDF Comparison — Likelihood Best-Fit',
            font=dict(size=14),
        ),
        'xaxis_title': 'ΔRV (km/s)',
        'yaxis_title': 'Cumulative Fraction',
        'height': 420,
        'legend': dict(x=0.45, y=0.15),
        'annotations': fig.layout.annotations + (dict(
            x=0.98, y=0.95, xref='paper', yref='paper',
            text=f'ln L = {logL:.2f}',
            showarrow=False,
            font=dict(size=12),
            bgcolor='rgba(255,255,255,0.8)',
            borderpad=6, xanchor='right',
        ),),
    })
    st.plotly_chart(fig, use_container_width=True, key=f'{prefix}_lk_cdf')
    st.caption(
        f'Observed ΔRV CDF (solid blue) vs simulated at best-fit likelihood parameters '
        f'(dashed red, median of {n_cdf_sets} draws). '
        f'Shaded band = 16th–84th percentile.'
    )

    return pooled_sim


def render_likelihood_stats_table(
    obs_delta_rv: np.ndarray,
    sim_delta_rv_pooled: np.ndarray,
    bin_edges: np.ndarray,
) -> None:
    """Per-bin breakdown table: n_obs, n_sim, p_i, contribution to ln L."""
    obs_drv = np.abs(np.asarray(obs_delta_rv))
    sim_drv = np.asarray(sim_delta_rv_pooled)
    edges = np.asarray(bin_edges)

    n_obs = np.histogram(obs_drv, bins=edges)[0]
    n_sim = np.histogram(sim_drv, bins=edges)[0]
    total_sim = max(int(n_sim.sum()), 1)
    p_bins = n_sim.astype(float) / total_sim

    eps = 1.0 / max(sim_drv.size, 1)
    p_safe = np.maximum(p_bins, eps)
    contributions = n_obs * np.log(p_safe)

    rows = []
    for i in range(len(edges) - 1):
        lo = edges[i]
        hi = edges[i + 1]
        label = f'[{lo:.0f}, ∞)' if np.isinf(hi) else f'[{lo:.0f}, {hi:.0f})'
        rows.append({
            'Bin': label,
            'n_obs': int(n_obs[i]),
            'n_sim': int(n_sim[i]),
            'p_i': f'{p_safe[i]:.4f}',
            'ln(p_i)': f'{np.log(p_safe[i]):.3f}',
            'n_i · ln(p_i)': f'{contributions[i]:.3f}',
        })

    total_logL = float(np.sum(contributions))
    rows.append({
        'Bin': 'Total',
        'n_obs': int(n_obs.sum()),
        'n_sim': int(n_sim.sum()),
        'p_i': '—',
        'ln(p_i)': '—',
        'n_i · ln(p_i)': f'{total_logL:.3f}',
    })

    st.markdown('#### Per-Bin Likelihood Breakdown')
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.caption(
        f'Observed counts (n_obs) vs simulated bin probabilities (p_i) at best-fit. '
        f'Total ln L = {total_logL:.3f}.'
    )


def render_likelihood_explanation(
    obs_delta_rv: np.ndarray,
    bin_edges: np.ndarray,
) -> None:
    """Expandable explanation of multinomial likelihood with worked example."""
    obs_drv = np.abs(np.asarray(obs_delta_rv))
    edges = np.asarray(bin_edges)
    n_obs = np.histogram(obs_drv, bins=edges)[0]

    with st.expander('How is the likelihood calculated?', expanded=False):
        # --- Part 1: Raw log-likelihood ---
        st.markdown('##### 1. Raw Log-Likelihood')
        st.markdown(
            'The multinomial log-likelihood (Dsilva et al. 2023, §4.2) bins the '
            'observed ΔRV values into **coarse categories** and compares the '
            'observed bin counts to the simulated bin probabilities:'
        )
        st.latex(r'\ln \mathcal{L} = \sum_{i=1}^{k} n_i \cdot \ln(p_i)')
        st.markdown(
            'where **n_i** = number of observed stars in bin *i*, and '
            '**p_i** = fraction of simulated ΔRV values falling in bin *i*.'
        )

        # Worked example
        st.markdown('**Worked example** (using your observed data):')
        bin_labels = []
        for i in range(len(edges) - 1):
            lo, hi = edges[i], edges[i + 1]
            lbl = f'[{lo:.0f}, ∞)' if np.isinf(hi) else f'[{lo:.0f}, {hi:.0f})'
            bin_labels.append(lbl)

        # Use plausible example probabilities
        n_total = int(n_obs.sum())
        example_p = np.array([0.60, 0.25, 0.10, 0.05])[:len(n_obs)]
        example_p = example_p / example_p.sum()  # normalize

        ex_rows = []
        ex_total = 0.0
        for i in range(len(n_obs)):
            ni = int(n_obs[i])
            pi = example_p[i]
            contrib = ni * np.log(pi) if ni > 0 else 0.0
            ex_total += contrib
            ex_rows.append(
                f'| {bin_labels[i]} | {ni} | {pi:.2f} | '
                f'{np.log(pi):.3f} | {contrib:.3f} |'
            )

        header = '| Bin | n_i | p_i (example) | ln(p_i) | n_i · ln(p_i) |'
        sep = '|-----|-----|---------------|---------|---------------|'
        st.markdown('\n'.join([header, sep] + ex_rows))
        st.markdown(f'**Total: ln L = {ex_total:.3f}**')
        st.caption(
            'These p_i values are illustrative. The actual p_i comes from '
            'simulating at each grid point\'s (f_bin, π, σ) parameters.'
        )

        # --- Part 2: Normalization ---
        st.markdown('##### 2. Normalization to [0, 1]')
        st.markdown(
            'The raw ln L is computed at **every grid point** — each (f_bin, π, σ) '
            'combination gets its own log-likelihood. To compare them, we normalize:'
        )
        st.latex(
            r'\mathcal{L}_{\mathrm{norm}} = '
            r'\exp\!\bigl(\ln \mathcal{L} - \ln \mathcal{L}_{\max}\bigr)'
        )
        st.markdown(
            '- Find the **maximum** ln L across the entire grid → this is the best-fit point\n'
            '- Subtract it from every grid point\'s ln L, then exponentiate\n'
            '- Result: the best-fit point gets **L_norm = 1.0**, and all others get values < 1\n'
            '- This is a standard technique — it avoids numerical underflow from '
            'exponentiating large negative numbers'
        )

        # --- Part 3: Why many points cluster near 1 ---
        st.markdown('##### 3. Why Do Many Points Show L ≈ 1?')
        st.markdown(
            f'With only **{len(n_obs)} coarse bins**, many different parameter '
            'combinations produce nearly identical bin probabilities. '
            'If two models predict p_i ≈ [0.60, 0.25, 0.10, 0.05], their '
            'log-likelihoods will be almost equal — and after normalization, '
            'both map to L_norm ≈ 1.0.'
        )
        st.markdown(
            'This is a **known limitation of coarse binning**. The likelihood '
            'surface is "flat" — it lacks the discriminating power of the K-S and CvM '
            'methods, which use fine 10 km/s bins and can distinguish subtle shape '
            'differences in the ΔRV distribution.'
        )
        st.markdown(
            'The likelihood is still valuable as a **consistency check** and '
            'as a complementary statistic (Dsilva et al. 2023), but the K-S and '
            'CvM scores typically provide tighter constraints on the parameters.'
        )
