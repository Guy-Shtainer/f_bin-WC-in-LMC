"""mock_inspector_app/inspector.py — Pure plot helpers.

Each function takes numpy arrays and returns a Plotly Figure.  No
Streamlit dependency; no global state.  Ready for unit testing.

A&A journal style on every figure: white background, Times New Roman serif,
black mirrored axes, no gridlines, axis-title font ≥14pt, tick font ≥12pt.
"""
from __future__ import annotations

import os
import sys
from typing import Optional

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Sibling-import setup so we can reuse `_academic_fig` from the main app.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, '..'))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
_APP_ROOT = os.path.join(_PROJECT_ROOT, 'app')
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

from plots.theme import _academic_fig  # noqa: E402

try:
    from bc.helpers import smooth_pooled_cdf  # noqa: E402
except Exception:  # pragma: no cover — defensive fallback
    smooth_pooled_cdf = None

try:
    from bc.render_validation import _AA_OVERRIDES  # noqa: E402
except Exception:  # pragma: no cover — defensive fallback
    _AA_OVERRIDES = None


# ─────────────────────────────────────────────────────────────────────────────
# Style constants
# ─────────────────────────────────────────────────────────────────────────────

OBS_COLOR = '#2E2E2E'                    # observed step ECDF
MOCK_COLOR = '#4A90D9'                   # blue
EXPLORER_COLOR = '#E25A53'               # red
THRESHOLD_DRV = 45.5                     # km/s, project binary detection threshold

# Per-star dot colors — match the validation tab convention
# (`app/bc/render_validation.py:_CLR_SINGLE / _CLR_BINARY`).
_CLR_SINGLE = '#E25A53'                  # red dots — single stars
_CLR_BINARY = '#52B788'                  # green dots — binary stars

# Project rule (2026-04-23): axis titles ≥14pt, ticks ≥12pt.  We override
# the defaults from `plots.theme._academic_fig` (which uses 13/11) so each
# figure here is paper-grade.
_FONT_TITLE = 14
_FONT_TICK = 12
_FONT_LEGEND = 12
_FONT_ANNOT = 12


def _styled_fig(*, title: str, height: int, x_title: str, y_title: str,
                x_range: Optional[tuple] = None,
                y_range: Optional[tuple] = None) -> go.Figure:
    """Wrapper around `_academic_fig` with the inspector's font sizes
    enforced and a single-call layout setup.
    """
    fig = _academic_fig(
        title=dict(text=title,
                   font=dict(size=15, family='Times New Roman, serif',
                             color='black')),
        height=int(height),
    )
    fig.update_xaxes(
        title=dict(text=x_title, font=dict(size=_FONT_TITLE)),
        tickfont=dict(size=_FONT_TICK),
        showgrid=False, zeroline=False,
        linecolor='black', mirror=True,
        ticks='outside', tickcolor='black', tickwidth=1,
    )
    fig.update_yaxes(
        title=dict(text=y_title, font=dict(size=_FONT_TITLE)),
        tickfont=dict(size=_FONT_TICK),
        showgrid=False, zeroline=False,
        linecolor='black', mirror=True,
        ticks='outside', tickcolor='black', tickwidth=1,
    )
    if x_range is not None:
        fig.update_xaxes(range=list(x_range))
    if y_range is not None:
        fig.update_yaxes(range=list(y_range))
    fig.update_layout(
        legend=dict(font=dict(size=_FONT_LEGEND), bgcolor='rgba(255,255,255,0)',
                    bordercolor='black', borderwidth=0.5),
    )
    return fig


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Convert a #RRGGBB hex color to an rgba() string with given alpha."""
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'rgba({r},{g},{b},{alpha})'


# ─────────────────────────────────────────────────────────────────────────────
# Plot 1 — ΔRV CDF (observed step + simulated band + median)
# ─────────────────────────────────────────────────────────────────────────────

def make_drv_cdf_figure(
    observed_drv: np.ndarray,
    simulated_drv_2d: np.ndarray,
    color_hex: str,
    title: str,
) -> go.Figure:
    """Empirical step-ECDF of observed ΔRVs (black) vs simulated 16-84
    percentile band + smooth median (column color).

    Parameters
    ----------
    observed_drv : (n_obs,) — peak-to-peak ΔRV per real star [km/s]
    simulated_drv_2d : (n_iter, n_stars) — peak-to-peak ΔRV per (iter, star)
    color_hex : pipeline accent color (#RRGGBB)
    title : panel title
    """
    obs = np.asarray(observed_drv, dtype=float).ravel()
    sim = np.asarray(simulated_drv_2d, dtype=float)
    if sim.ndim == 1:
        sim = sim[None, :]
    n_iter, n_stars = sim.shape

    x_max_data = float(max(np.max(obs) if obs.size else 0.0,
                           np.max(sim) if sim.size else 1.0))
    x_max_axis = max(150.0, x_max_data * 1.05)

    fig = _styled_fig(
        title=title,
        height=350,
        x_title='ΔRV [km s⁻¹]',
        y_title='Cumulative fraction',
        x_range=(0.0, x_max_axis),
        y_range=(0.0, 1.02),
    )

    # ── Simulated band + smooth median via the project's smooth_pooled_cdf
    # (2026-05-07 CDF rule).  Plot the band first so the median + observed
    # curves render on top.
    pooled = sim.ravel()
    band_added = False
    if smooth_pooled_cdf is not None and pooled.size > 0:
        result = smooth_pooled_cdf(pooled, n_sets=n_iter)
        if result is not None:
            sorted_pool, y_pool, x_fine, lo_fine, hi_fine = result
            band_color = _hex_to_rgba(color_hex, 0.25)
            # Shaded percentile band — use legendgroup so toggling the
            # legend hides band + median together (CDF legend rule).
            fig.add_trace(go.Scatter(
                x=x_fine, y=hi_fine, mode='lines',
                line=dict(width=0, color=color_hex),
                showlegend=False, hoverinfo='skip',
                legendgroup='sim',
            ))
            fig.add_trace(go.Scatter(
                x=x_fine, y=lo_fine, mode='lines',
                line=dict(width=0, color=color_hex),
                fill='tonexty', fillcolor=band_color,
                showlegend=False, hoverinfo='skip',
                legendgroup='sim',
            ))
            fig.add_trace(go.Scatter(
                x=sorted_pool, y=y_pool, mode='lines',
                line=dict(color=color_hex, width=1.8),
                name='Simulated (median + 16-84%)',
                legendgroup='sim',
            ))
            band_added = True

    if not band_added and pooled.size > 0:
        # Fallback: simple sorted-pooled CDF only, no band.
        srt = np.sort(pooled)
        y = np.arange(1, srt.size + 1, dtype=float) / srt.size
        fig.add_trace(go.Scatter(
            x=srt, y=y, mode='lines',
            line=dict(color=color_hex, width=1.8),
            name='Simulated (pooled)',
            legendgroup='sim',
        ))

    # ── Observed step ECDF (black, on top) -------------------------------
    if obs.size > 0:
        srt_o = np.sort(obs)
        y_o = np.arange(1, srt_o.size + 1, dtype=float) / srt_o.size
        fig.add_trace(go.Scatter(
            x=srt_o, y=y_o, mode='lines',
            line=dict(color=OBS_COLOR, width=2.0, shape='hv'),
            name=f'Observed ({srt_o.size} stars)',
        ))

    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Plot 2 — Detected binary fraction vs ΔRV threshold
# ─────────────────────────────────────────────────────────────────────────────

def make_fbin_vs_threshold_figure(
    simulated_drv_2d: np.ndarray,
    color_hex: str,
    title: str,
) -> go.Figure:
    """Average fraction of stars with peak-to-peak ΔRV > threshold across
    iterations, as a function of threshold from 0 to 150 km/s.
    """
    sim = np.asarray(simulated_drv_2d, dtype=float)
    if sim.ndim == 1:
        sim = sim[None, :]
    n_iter, n_stars = sim.shape

    thresh = np.linspace(0.0, 150.0, 301)
    if sim.size > 0:
        # For each iteration, fraction of stars > each threshold; then
        # mean across iterations.
        # Vectorised: use broadcasting (n_iter, 1, n_stars) > (n_thresh, 1)
        # might allocate a large array — use the per-iteration searchsorted
        # trick instead for memory efficiency.
        fbin_per_iter = np.empty((n_iter, thresh.size), dtype=float)
        for i in range(n_iter):
            srt = np.sort(sim[i])
            # fraction > t = 1 - mean(srt <= t) = 1 - searchsorted(srt, t, 'right') / n_stars
            fbin_per_iter[i] = 1.0 - np.searchsorted(srt, thresh,
                                                     side='right') / n_stars
        fbin_mean = fbin_per_iter.mean(axis=0)
    else:
        fbin_mean = np.zeros_like(thresh)

    fig = _styled_fig(
        title=title,
        height=280,
        x_title='ΔRV threshold [km s⁻¹]',
        y_title='Detected binary fraction',
        x_range=(0.0, 150.0),
        y_range=(0.0, 1.02),
    )
    fig.add_trace(go.Scatter(
        x=thresh, y=fbin_mean, mode='lines',
        line=dict(color=color_hex, width=2.0),
        name='Mean across iterations',
    ))
    # Vertical dashed threshold marker at the project's 45.5 km/s line.
    fig.add_vline(
        x=THRESHOLD_DRV,
        line=dict(color=OBS_COLOR, dash='dash', width=1.2),
        annotation_text=f'threshold = {THRESHOLD_DRV} km s⁻¹',
        annotation_position='top right',
        annotation_font=dict(size=_FONT_ANNOT, color=OBS_COLOR),
    )
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Plot 3-8 — Orbital parameter histograms
# ─────────────────────────────────────────────────────────────────────────────

def make_orbit_histogram(
    samples_2d: np.ndarray,
    color_hex: str,
    title: str,
    x_label: str,
    x_range: Optional[tuple] = None,
    n_bins: int = 30,
    height: int = 220,
) -> go.Figure:
    """Histogram of an orbital parameter, flattening (n_iter, n_binaries)
    to 1-D before binning.

    The caller is responsible for any unit conversion (e.g. ω rad → deg
    is done in the wrapper `make_omega_histogram_degrees`).
    """
    arr = np.asarray(samples_2d, dtype=float).ravel()
    fig = _styled_fig(
        title=title,
        height=height,
        x_title=x_label,
        y_title='Count',
        x_range=x_range,
    )
    if arr.size == 0:
        return fig

    if x_range is not None:
        bins = np.linspace(float(x_range[0]), float(x_range[1]), int(n_bins) + 1)
    else:
        bins = int(n_bins)
    counts, edges = np.histogram(arr, bins=bins)
    centers = 0.5 * (edges[:-1] + edges[1:])
    width = edges[1:] - edges[:-1]

    fig.add_trace(go.Bar(
        x=centers, y=counts, width=width,
        marker=dict(color=color_hex, line=dict(width=0)),
        name=x_label, showlegend=False,
    ))
    fig.update_layout(bargap=0.0)
    return fig


def make_omega_histogram_degrees(
    omega_radians_2d: np.ndarray,
    color_hex: str,
    title: str,
    height: int = 220,
) -> go.Figure:
    """ω histogram with rad → deg conversion done here so the wrapper
    helper stays pure (no implicit unit handling)."""
    deg = np.asarray(omega_radians_2d, dtype=float).ravel() * (180.0 / np.pi)
    return make_orbit_histogram(
        deg, color_hex, title, x_label='ω [degrees]',
        x_range=(0.0, 360.0), height=height,
    )


def make_phase_histogram(
    phase_2d: np.ndarray,
    color_hex: str,
    title: str,
    height: int = 220,
) -> go.Figure:
    """Phase histogram on [0, 1].  Input is already T0/(2π) per the runner
    contract, so no further conversion needed here.
    """
    return make_orbit_histogram(
        phase_2d, color_hex, title, x_label='Phase φ',
        x_range=(0.0, 1.0), height=height,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Summary stats table
# ─────────────────────────────────────────────────────────────────────────────

def make_summary_table(detail_dict: dict) -> pd.DataFrame:
    """Per-orbital-parameter mean / std / min / max / n_samples + a row
    for binaries-per-iteration + a row for the binary-index method.

    Returned DataFrame is ready for `st.dataframe(df, hide_index=True)`.
    """
    rows: list[dict] = []
    label_units = [
        ('logP [days]', 'logP'),
        ('Eccentricity e', 'e'),
        ('Mass ratio q = M₂/M₁', 'q'),
        ('cos i', 'cosi'),
        ('ω [degrees]', 'omega'),
        ('Phase φ', 'phase'),
    ]
    for label, key in label_units:
        arr = np.asarray(detail_dict.get(key, np.array([])), dtype=float).ravel()
        if key == 'omega':
            arr = arr * (180.0 / np.pi)  # rad → deg for display
        if arr.size == 0:
            rows.append({
                'Parameter': label, 'Mean': np.nan, 'Std': np.nan,
                'Min': np.nan, 'Max': np.nan, 'N samples': 0,
            })
            continue
        rows.append({
            'Parameter': label,
            'Mean': float(np.mean(arr)),
            'Std': float(np.std(arr)),
            'Min': float(np.min(arr)),
            'Max': float(np.max(arr)),
            'N samples': int(arr.size),
        })

    nb = np.asarray(detail_dict.get('n_binaries_per_iter', np.array([])),
                    dtype=float).ravel()
    rows.append({
        'Parameter': 'n_binaries / iter',
        'Mean': float(np.mean(nb)) if nb.size else np.nan,
        'Std': float(np.std(nb)) if nb.size else np.nan,
        'Min': float(np.min(nb)) if nb.size else np.nan,
        'Max': float(np.max(nb)) if nb.size else np.nan,
        'N samples': int(nb.size),
    })
    rows.append({
        'Parameter': 'binary_index_method',
        'Mean': str(detail_dict.get('binary_index_method', '')),
        'Std': '', 'Min': '', 'Max': '', 'N samples': '',
    })

    return pd.DataFrame(rows, columns=['Parameter', 'Mean', 'Std',
                                        'Min', 'Max', 'N samples'])


# ─────────────────────────────────────────────────────────────────────────────
# Overlay helpers — Mock and Explorer rendered together on shared axes
# ─────────────────────────────────────────────────────────────────────────────

def _add_smoothed_cdf_traces(
    fig: go.Figure,
    sim_2d: np.ndarray,
    color_hex: str,
    legend_label: str,
    n_band_bins: int = 500,
) -> None:
    """Add a (16-84 band + smooth pooled CDF line) trio to `fig`.  All three
    traces share `legendgroup=legend_label` so the legend toggle hides
    band + line as a unit (mirrors `make_drv_cdf_figure`'s convention).

    `n_band_bins` is forwarded to `smooth_pooled_cdf(..., n_fine=...)` so the
    caller (and ultimately the user) can tune the x-resolution of the
    16-84% percentile band.
    """
    sim = np.asarray(sim_2d, dtype=float)
    if sim.ndim == 1:
        sim = sim[None, :]
    n_iter = sim.shape[0]
    pooled = sim.ravel()
    if pooled.size == 0:
        return

    if smooth_pooled_cdf is not None:
        result = smooth_pooled_cdf(pooled, n_sets=n_iter,
                                   n_fine=int(n_band_bins))
        if result is not None:
            sorted_pool, y_pool, x_fine, lo_fine, hi_fine = result
            band_color = _hex_to_rgba(color_hex, 0.25)
            fig.add_trace(go.Scatter(
                x=x_fine, y=hi_fine, mode='lines',
                line=dict(width=0, color=color_hex),
                showlegend=False, hoverinfo='skip',
                legendgroup=legend_label,
            ))
            fig.add_trace(go.Scatter(
                x=x_fine, y=lo_fine, mode='lines',
                line=dict(width=0, color=color_hex),
                fill='tonexty', fillcolor=band_color,
                showlegend=False, hoverinfo='skip',
                legendgroup=legend_label,
            ))
            fig.add_trace(go.Scatter(
                x=sorted_pool, y=y_pool, mode='lines',
                line=dict(color=color_hex, width=1.8),
                name=f'{legend_label} (median + 16-84%)',
                legendgroup=legend_label,
            ))
            return

    # Fallback: simple sorted-pooled CDF.
    srt = np.sort(pooled)
    y = np.arange(1, srt.size + 1, dtype=float) / srt.size
    fig.add_trace(go.Scatter(
        x=srt, y=y, mode='lines',
        line=dict(color=color_hex, width=1.8),
        name=f'{legend_label} (pooled)',
        legendgroup=legend_label,
    ))


def _coerce_single_runs(single_runs) -> list:
    """Normalise the optional `single_runs` argument into a list of clean
    dicts {'delta_rv': (n_stars,), 'is_binary': (n_stars,), 'seed': int}.

    Accepts:
        - None / empty list → []
        - list of dicts (preferred new shape)
        - a single dict (legacy shape, wrapped into a 1-list)
    Each entry is filtered for size>0 and matched delta_rv/is_binary lengths.
    """
    if single_runs is None:
        return []
    # Legacy single-dict shape: wrap.
    if isinstance(single_runs, dict):
        single_runs = [single_runs]
    out = []
    for entry in single_runs:
        if not isinstance(entry, dict):
            continue
        drv = np.asarray(entry.get('delta_rv', np.array([])),
                         dtype=float).ravel()
        is_bin = np.asarray(entry.get('is_binary', np.array([])),
                            dtype=bool).ravel()
        if drv.size == 0 or drv.size != is_bin.size:
            continue
        seed = entry.get('seed', None)
        try:
            seed_int = int(seed) if seed is not None else None
        except (TypeError, ValueError):
            seed_int = None
        out.append({'delta_rv': drv, 'is_binary': is_bin, 'seed': seed_int})
    return out


def make_drv_cdf_overlay_figure(
    mock_simulated_drv: np.ndarray,
    explorer_simulated_drv: np.ndarray,
    title: str = 'ΔRV CDF: Mock vs Explorer',
    single_runs=None,
    n_band_bins: int = 500,
) -> go.Figure:
    """Single-axes ECDF showing Mock smoothed CDF band/line + Explorer
    smoothed CDF band/line, on a shared ΔRV axis.

    Parameters
    ----------
    mock_simulated_drv : (n_iter, n_stars) — Mock pipeline ΔRV [km/s]
    explorer_simulated_drv : (n_iter, n_stars) — Explorer pipeline ΔRV [km/s]
    title : panel title
    single_runs : optional list of dicts (or single dict for legacy callers).
        Each dict has keys
            - 'delta_rv'  : (n_stars,) per-star peak-to-peak ΔRV [km/s]
            - 'is_binary' : (n_stars,) bool ground-truth mask
            - 'seed'      : int, RNG seed used for the draw (optional)
        For each entry a black step-ECDF line is overlaid (semi-transparent
        so accumulated draws build up visually); per-star dots are
        AGGREGATED across all entries into one red trace (singles) and one
        green trace (binaries) (matches validation-tab convention in
        `app/bc/render_validation.py`).

    The observed real-observations trace was removed 2026-05-10 — this
    inspector exists only to compare the two simulated pipelines, so the
    observed CDF is not relevant here.
    """
    mock = np.asarray(mock_simulated_drv, dtype=float)
    expl = np.asarray(explorer_simulated_drv, dtype=float)

    runs = _coerce_single_runs(single_runs)

    # Widen x-axis to fit any single-run outlier across the accumulated set.
    max_drv_single = 0.0
    if runs:
        max_drv_single = float(max(np.max(r['delta_rv']) for r in runs))

    x_max_data = float(max(
        np.max(mock) if mock.size else 0.0,
        np.max(expl) if expl.size else 1.0,
        max_drv_single,
    ))
    x_max_axis = max(150.0, x_max_data * 1.05)

    fig = _styled_fig(
        title=title,
        height=380,
        x_title='ΔRV [km s⁻¹]',
        y_title='Cumulative fraction',
        x_range=(0.0, x_max_axis),
        y_range=(0.0, 1.02),
    )

    _add_smoothed_cdf_traces(fig, mock, MOCK_COLOR, 'Mock',
                             n_band_bins=int(n_band_bins))
    _add_smoothed_cdf_traces(fig, expl, EXPLORER_COLOR, 'Explorer',
                             n_band_bins=int(n_band_bins))

    # ── Optional single-run step-ECDF lines + aggregated per-star dots -----
    # Order matters: add the step LINES first so the colored dots render on
    # top of them (Plotly draws traces in insertion order).
    if runs:
        # Per-run step ECDF lines, semi-transparent, single legend entry.
        for idx, r in enumerate(runs):
            drv = r['delta_rv']
            n = drv.size
            sorted_drv = np.sort(drv)
            ecdf_y = (np.arange(1, n + 1)) / n
            seed_str = (f'seed={r["seed"]}' if r['seed'] is not None
                        else f'#{idx + 1}')
            fig.add_trace(go.Scatter(
                x=sorted_drv, y=ecdf_y, mode='lines',
                line=dict(color='rgba(0,0,0,0.45)', width=1.2, shape='hv'),
                name='Single-run ECDFs',
                legendgroup='single_runs',
                showlegend=(idx == 0),
                hovertemplate=('ΔRV=%{x:.1f} km/s · '
                               'ECDF=%{y:.3f}'
                               f'<extra>Single run ({seed_str})</extra>'),
            ))

        # Aggregated per-star dot coordinates across all runs.
        x_singles_list, y_singles_list = [], []
        x_binaries_list, y_binaries_list = [], []
        for r in runs:
            drv = r['delta_rv']
            is_bin = r['is_binary']
            n = drv.size
            # y_i = (rank_i + 1) / N with rank the 0-indexed sorted position.
            sorted_idx = np.argsort(drv)
            y_stars = np.empty(n, dtype=float)
            y_stars[sorted_idx] = (np.arange(n) + 1) / n
            single_mask = ~is_bin
            x_singles_list.append(drv[single_mask])
            y_singles_list.append(y_stars[single_mask])
            x_binaries_list.append(drv[is_bin])
            y_binaries_list.append(y_stars[is_bin])

        x_singles = (np.concatenate(x_singles_list)
                     if x_singles_list else np.array([]))
        y_singles = (np.concatenate(y_singles_list)
                     if y_singles_list else np.array([]))
        x_binaries = (np.concatenate(x_binaries_list)
                      if x_binaries_list else np.array([]))
        y_binaries = (np.concatenate(y_binaries_list)
                      if y_binaries_list else np.array([]))

        n_runs = len(runs)
        total_singles = int(x_singles.size)
        total_binaries = int(x_binaries.size)

        if total_singles > 0:
            fig.add_trace(go.Scatter(
                x=x_singles, y=y_singles,
                mode='markers',
                marker=dict(color=_CLR_SINGLE, size=7,
                            line=dict(color='black', width=0.5)),
                name=f'Single ({total_singles} from {n_runs} runs)',
                hovertemplate=('single · ΔRV=%{x:.1f} km/s · '
                               'ECDF=%{y:.3f}<extra></extra>'),
            ))
        if total_binaries > 0:
            fig.add_trace(go.Scatter(
                x=x_binaries, y=y_binaries,
                mode='markers',
                marker=dict(color=_CLR_BINARY, size=7,
                            line=dict(color='black', width=0.5)),
                name=f'Binary ({total_binaries} from {n_runs} runs)',
                hovertemplate=('binary · ΔRV=%{x:.1f} km/s · '
                               'ECDF=%{y:.3f}<extra></extra>'),
            ))

    return fig


def make_fbin_vs_threshold_overlay_figure(
    mock_simulated_drv: np.ndarray,
    explorer_simulated_drv: np.ndarray,
    title: str = 'Detected binary fraction vs threshold',
    single_runs=None,
    n_band_bins: int = 500,
) -> go.Figure:
    """Single-axes plot of mean detected-binary fraction vs ΔRV threshold for
    Mock (blue) and Explorer (red), with the 45.5 km/s vertical line.

    Parameters
    ----------
    mock_simulated_drv : (n_iter, n_stars) — Mock pipeline ΔRV [km/s]
    explorer_simulated_drv : (n_iter, n_stars) — Explorer pipeline ΔRV [km/s]
    title : panel title
    single_runs : optional list of dicts (or single dict for legacy callers).
        Each dict has keys
            - 'delta_rv'  : (n_stars,) per-star peak-to-peak ΔRV [km/s]
            - 'is_binary' : (n_stars,) bool ground-truth mask
            - 'seed'      : int, RNG seed used for the draw (optional)
        For each entry a black step survival curve is overlaid
        (semi-transparent so accumulated draws build up visually); per-star
        dots are AGGREGATED across all entries into one red trace (singles)
        and one green trace (binaries) at (ΔRV_i, survival_i).
    """
    runs = _coerce_single_runs(single_runs)

    # Widen the x-axis range if a single-run outlier exceeds 150 km/s.
    max_drv_single = 0.0
    if runs:
        max_drv_single = float(max(np.max(r['delta_rv']) for r in runs))
    x_max_axis = max(150.0, max_drv_single * 1.05)
    thresh = np.linspace(0.0, x_max_axis, max(301,
                                              int(round(x_max_axis * 2)) + 1))

    def _fbin_curves_per_iter(sim_2d: np.ndarray) -> np.ndarray:
        """Per-iteration f_bin survival curves on the shared `thresh` grid.
        Returns an array of shape (n_iter, len(thresh)).  Empty input → a
        single-row zero array so downstream median/percentile calls still
        return well-defined arrays.
        """
        sim = np.asarray(sim_2d, dtype=float)
        if sim.ndim == 1:
            sim = sim[None, :]
        n_iter, n_stars = sim.shape
        if sim.size == 0 or n_stars == 0:
            return np.zeros((1, thresh.size), dtype=float)
        out = np.empty((n_iter, thresh.size), dtype=float)
        for i in range(n_iter):
            srt = np.sort(sim[i])
            out[i] = 1.0 - np.searchsorted(srt, thresh, side='right') / n_stars
        return out

    fig = _styled_fig(
        title=title,
        height=380,
        x_title='ΔRV threshold [km s⁻¹]',
        y_title='Detected binary fraction',
        x_range=(0.0, x_max_axis),
        y_range=(0.0, 1.02),
    )

    # Mock and Explorer get a 16-84 percentile band (rendered as
    # hi-trace + lo-trace+fill) plus a median line, all sharing a
    # `legendgroup` so toggling the legend hides band + median together
    # (mirrors the CDF panel convention from `_add_smoothed_cdf_traces`).
    # Order: Mock band+median first, then Explorer band+median, then the
    # 45.5 km/s vertical line, then single-run step lines, then dots
    # (added below).  Dots end on top.
    #
    # Implementation note: we reuse `smooth_pooled_cdf` (the same helper
    # used by the CDF panel) so the median is naturally smooth — sorted
    # over all `n_iter * n_stars` pooled ΔRVs (~12,500 points for
    # 500×25) instead of the discrete 1/25 staircase from a single
    # iteration.  We then convert pooled-CDF → survival = 1 - CDF.
    # Since survival is monotone-decreasing in ΔRV, the CDF lo-percentile
    # becomes the survival hi-percentile and vice versa.  The x-resolution
    # of the band is `n_band_bins` (default 500, user-tunable from the app).
    def _add_fbin_band_and_median(sim_2d: np.ndarray, color_hex: str,
                                  legend_label: str) -> None:
        sim = np.asarray(sim_2d, dtype=float)
        if sim.ndim == 1:
            sim = sim[None, :]
        n_iter = sim.shape[0]
        pooled = sim.ravel()
        if pooled.size == 0 or smooth_pooled_cdf is None:
            # Fallback: skip the band entirely (caller still gets the
            # vertical line, single-run lines, and dots).  This keeps
            # the trace count predictable for the no-data edge case.
            return
        result = smooth_pooled_cdf(pooled, n_sets=n_iter,
                                   n_fine=int(n_band_bins))
        if result is None:
            return
        sorted_pool, y_pool_cdf, x_fine, lo_fine_cdf, hi_fine_cdf = result
        # CDF → survival.  Survival is monotone decreasing, so the CDF
        # 16th percentile maps to the survival 84th percentile and
        # vice-versa — swap lo/hi when inverting.
        y_pool_survival = 1.0 - y_pool_cdf
        lo_fine_survival = 1.0 - hi_fine_cdf
        hi_fine_survival = 1.0 - lo_fine_cdf
        band_color = _hex_to_rgba(color_hex, 0.18)
        # Upper boundary (invisible line, anchors the fill below).
        fig.add_trace(go.Scatter(
            x=x_fine, y=hi_fine_survival, mode='lines',
            line=dict(width=0, color=color_hex),
            showlegend=False, hoverinfo='skip',
            legendgroup=legend_label,
        ))
        # Lower boundary with fill up to the previous (hi) trace.
        fig.add_trace(go.Scatter(
            x=x_fine, y=lo_fine_survival, mode='lines',
            line=dict(width=0, color=color_hex),
            fill='tonexty', fillcolor=band_color,
            showlegend=False, hoverinfo='skip',
            legendgroup=legend_label,
        ))
        # Median line (visible legend entry) — uses the pooled-sorted
        # x positions (~n_iter*n_stars points) so it is smooth by
        # construction, no per-iteration averaging artefact.
        fig.add_trace(go.Scatter(
            x=sorted_pool, y=y_pool_survival, mode='lines',
            line=dict(color=color_hex, width=1.5),
            name=f'{legend_label} (median + 16-84%)',
            legendgroup=legend_label,
        ))

    _add_fbin_band_and_median(mock_simulated_drv, MOCK_COLOR, 'Mock')
    _add_fbin_band_and_median(explorer_simulated_drv, EXPLORER_COLOR,
                              'Explorer')

    # 45.5 km/s vertical detection threshold — added before the
    # single-run traces per the agreed plot order (Mock band → Explorer
    # band → vertical line → single-run step lines → dots).
    fig.add_vline(
        x=THRESHOLD_DRV,
        line=dict(color=OBS_COLOR, dash='dash', width=1.2),
        annotation_text=f'threshold = {THRESHOLD_DRV} km s⁻¹',
        annotation_position='top right',
        annotation_font=dict(size=_FONT_ANNOT, color=OBS_COLOR),
    )

    # ── Optional per-run step-survival lines + aggregated per-star dots ----
    # Add step LINES first so the colored dots render on top.
    if runs:
        for idx, r in enumerate(runs):
            drv = r['delta_rv']
            n = drv.size
            sorted_drv = np.sort(drv)
            # Step survival line: at t=0, survival=1; just past each ΔRV_i,
            # survival drops by 1/N.
            x_step = np.concatenate([[0.0], sorted_drv])
            y_step = np.concatenate([[1.0], (n - np.arange(1, n + 1)) / n])
            seed_str = (f'seed={r["seed"]}' if r['seed'] is not None
                        else f'#{idx + 1}')
            fig.add_trace(go.Scatter(
                x=x_step, y=y_step, mode='lines',
                line=dict(color='rgba(0,0,0,0.45)', width=1.2, shape='hv'),
                name='Single-run f_bin curves',
                legendgroup='single_runs',
                showlegend=(idx == 0),
                hovertemplate=('threshold=%{x:.1f} km/s · '
                               'survival=%{y:.3f}'
                               f'<extra>Single run ({seed_str})</extra>'),
            ))

        # Aggregated per-star dot coordinates across all runs.
        x_singles_list, y_singles_list = [], []
        x_binaries_list, y_binaries_list = [], []
        for r in runs:
            drv = r['delta_rv']
            is_bin = r['is_binary']
            n = drv.size
            # y_i = (N - rank_i - 1) / N (matches render_validation.py:1228)
            sorted_idx = np.argsort(drv)
            ranks = np.empty(n, dtype=int)
            ranks[sorted_idx] = np.arange(n)
            y_stars = (n - ranks - 1) / n
            single_mask = ~is_bin
            x_singles_list.append(drv[single_mask])
            y_singles_list.append(y_stars[single_mask])
            x_binaries_list.append(drv[is_bin])
            y_binaries_list.append(y_stars[is_bin])

        x_singles = (np.concatenate(x_singles_list)
                     if x_singles_list else np.array([]))
        y_singles = (np.concatenate(y_singles_list)
                     if y_singles_list else np.array([]))
        x_binaries = (np.concatenate(x_binaries_list)
                      if x_binaries_list else np.array([]))
        y_binaries = (np.concatenate(y_binaries_list)
                      if y_binaries_list else np.array([]))

        n_runs = len(runs)
        total_singles = int(x_singles.size)
        total_binaries = int(x_binaries.size)

        if total_singles > 0:
            fig.add_trace(go.Scatter(
                x=x_singles, y=y_singles,
                mode='markers',
                marker=dict(color=_CLR_SINGLE, size=7,
                            line=dict(color='black', width=0.5)),
                name=f'Single ({total_singles} from {n_runs} runs)',
                hovertemplate=('single · ΔRV=%{x:.1f} km/s · '
                               'survival=%{y:.3f}<extra></extra>'),
            ))
        if total_binaries > 0:
            fig.add_trace(go.Scatter(
                x=x_binaries, y=y_binaries,
                mode='markers',
                marker=dict(color=_CLR_BINARY, size=7,
                            line=dict(color='black', width=0.5)),
                name=f'Binary ({total_binaries} from {n_runs} runs)',
                hovertemplate=('binary · ΔRV=%{x:.1f} km/s · '
                               'survival=%{y:.3f}<extra></extra>'),
            ))

    return fig


# ─── 3x3 orbital grid ─────────────────────────────────────────────────────────

# 9 panels in the same order as the bias-correction page
# (`render_orbital_histograms`): logP, e, q, K1, M1, M2, i, ω, T0
_ORBITAL_XLABS = [
    'log₁₀(P / days)', 'e', 'q = M₂/M₁',
    'K₁ (km/s)', 'M₁ (M⊙)', 'M₂ (M⊙)',
    'i (degrees)', 'ω (degrees)', 'T₀ (rad)',
]


def _extract_orbital_panels(detail: dict) -> list[np.ndarray]:
    """Pull the 9 per-panel 1-D arrays from a runner detail dict, applying
    the same unit conversions as `render_orbital_histograms`:
      - logP from log10(P/days)
      - i in degrees from i_rad
      - ω in degrees from omega (rad)
      - T0 in radians (raw)
    """
    P_days = np.asarray(detail.get('P_days', np.array([])), dtype=float).ravel()
    e_arr  = np.asarray(detail.get('e', np.array([])), dtype=float).ravel()
    q_arr  = np.asarray(detail.get('q', np.array([])), dtype=float).ravel()
    K1     = np.asarray(detail.get('K1', np.array([])), dtype=float).ravel()
    M1     = np.asarray(detail.get('M1', np.array([])), dtype=float).ravel()
    M2     = np.asarray(detail.get('M2', np.array([])), dtype=float).ravel()
    i_rad  = np.asarray(detail.get('i_rad', np.array([])), dtype=float).ravel()
    omega  = np.asarray(detail.get('omega', np.array([])), dtype=float).ravel()
    T0     = np.asarray(detail.get('T0', np.array([])), dtype=float).ravel()

    logP_panel = np.log10(P_days) if P_days.size > 0 else np.array([])
    i_deg = np.degrees(i_rad) if i_rad.size > 0 else np.array([])
    omega_deg = np.degrees(omega) if omega.size > 0 else np.array([])

    return [logP_panel, e_arr, q_arr, K1, M1, M2, i_deg, omega_deg, T0]


def make_3x3_orbital_grid(
    mock_dict: dict,
    explorer_dict: dict,
    title: str = 'Orbital parameter distributions',
) -> go.Figure:
    """Single 3x3 Plotly figure with Mock (blue) and Explorer (red)
    histograms overlaid in each of the 9 panels.

    Layout matches `app/bc/render_shared_langer.py:render_orbital_histograms`
    (3 rows × 3 cols, horizontal/vertical spacing 0.08/0.10, height 850,
    barmode='overlay', NBINS=30, A&A overrides at the end).
    """
    NC, NR, NBINS = 3, 3, 30
    fig = make_subplots(rows=NR, cols=NC,
                        horizontal_spacing=0.08, vertical_spacing=0.10)

    mock_panels = _extract_orbital_panels(mock_dict)
    expl_panels = _extract_orbital_panels(explorer_dict)

    def _pos(idx: int) -> tuple[int, int]:
        return (idx // NC + 1, idx % NC + 1)

    def _add_hist(row: int, col: int, data: np.ndarray,
                  name: str, color: str, show_legend: bool,
                  xstart: float, xend: float) -> None:
        if data.size == 0:
            return
        d_min, d_max = float(data.min()), float(data.max())
        if d_max == d_min:
            # Constant parameter — vertical line instead of fake histogram
            # (mirrors `_add_hist` in render_shared_langer.py).
            fig.add_trace(go.Scatter(
                x=[d_min, d_min], y=[0, 1], mode='lines',
                line=dict(color=color, width=3),
                name=name, legendgroup=name, showlegend=show_legend,
            ), row=row, col=col)
            return
        # Shared bins across BOTH pipelines for this panel so the overlay
        # is comparable bar-for-bar.
        if xend <= xstart:
            xend = xstart + 1e-9
        bsz = (xend - xstart) / NBINS
        if bsz <= 0:
            return
        fig.add_trace(go.Histogram(
            x=data,
            xbins=dict(start=xstart, end=xend + bsz * 0.01, size=bsz),
            histnorm='probability density', name=name, marker_color=color,
            opacity=0.6, legendgroup=name, showlegend=show_legend,
        ), row=row, col=col)

    for pi, (m_data, e_data, xlab) in enumerate(
            zip(mock_panels, expl_panels, _ORBITAL_XLABS)):
        # Combined min/max for shared binning across both pipelines.
        combined: list[float] = []
        if m_data.size > 0:
            combined.extend([float(m_data.min()), float(m_data.max())])
        if e_data.size > 0:
            combined.extend([float(e_data.min()), float(e_data.max())])
        if not combined:
            xstart, xend = 0.0, 1.0
        else:
            xstart, xend = min(combined), max(combined)

        r, c = _pos(pi)
        # showlegend True only on the FIRST panel for each pipeline (pi==0).
        _add_hist(r, c, m_data, 'Mock', MOCK_COLOR, pi == 0, xstart, xend)
        _add_hist(r, c, e_data, 'Explorer', EXPLORER_COLOR, pi == 0, xstart, xend)

    fig.update_layout(
        barmode='overlay',
        height=850,
        margin=dict(l=40, r=20, t=40, b=60),
        legend=dict(orientation='h', yanchor='bottom', y=1.04,
                    xanchor='center', x=0.5),
        title=dict(
            text=title,
            font=dict(size=15, family='Times New Roman, serif', color='black'),
        ) if title else None,
    )
    for pi in range(9):
        r, c = _pos(pi)
        fig.update_xaxes(title_text=_ORBITAL_XLABS[pi],
                         showgrid=False, row=r, col=c)
        fig.update_yaxes(showgrid=False, row=r, col=c)
    for ri in range(1, NR + 1):
        fig.update_yaxes(title_text='Prob. density', row=ri, col=1)

    # A&A override: white bg + serif on every subplot.  Apply LAST so it
    # supersedes any earlier theme (mirrors render_orbital_histograms).
    if _AA_OVERRIDES is not None:
        try:
            fig.update_layout(
                plot_bgcolor=_AA_OVERRIDES['plot_bgcolor'],
                paper_bgcolor=_AA_OVERRIDES['paper_bgcolor'],
                font=_AA_OVERRIDES['font'],
                legend={**_AA_OVERRIDES['legend'],
                        'orientation': 'h', 'yanchor': 'bottom', 'y': 1.04,
                        'xanchor': 'center', 'x': 0.5},
                hoverlabel=_AA_OVERRIDES['hoverlabel'],
            )
            fig.update_xaxes(**_AA_OVERRIDES['xaxis'])
            fig.update_yaxes(**_AA_OVERRIDES['yaxis'])
        except Exception:
            pass

    return fig
