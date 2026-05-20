"""
scripts/plot_validation_summary.py

Validation sweep summary plot: σ_single vs. π scatter of 8 recovered points
(3 cases × {upper, representative, bottom} outlier sub-runs, minus one missing
combo) with dashed asymmetric 68% HDI cross-hairs, overlaid against 3 true
input values.

Public function:
    make_validation_summary_figure(runs_df) -> plotly.graph_objects.Figure
        No side effects (no prints, no file I/O).

Usage:
    conda run -n guyenv python scripts/plot_validation_summary.py
"""
from __future__ import annotations
import os, sys, glob, warnings
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, 'app'))

from wr_bias_simulation import compute_hdi68

# Streamlit emits MemoryCacheStorageManager warnings via its own logging
# handler during the PLOTLY_THEME import — those handlers ignore the parent
# logger's level. The only reliable way to silence them for an importable
# module is to swallow stderr during the import itself, then restore.
import io as _io
import contextlib as _contextlib
_st_buf = _io.StringIO()
warnings.filterwarnings('ignore', category=UserWarning)
with _contextlib.redirect_stderr(_st_buf):
    from shared import PLOTLY_THEME
    from bc.render_validation import _AA_OVERRIDES
warnings.resetwarnings()
del _st_buf, _io, _contextlib


# ---------------------------------------------------------------------------
# Run table — 9 sub-runs (3 cases × 3 outlier positions). Glob patterns are
# resolved under `mock_results/` and must match exactly one file each.
# ---------------------------------------------------------------------------
RUNS = [
    # Case A — easy (π=-3, σ=2)
    dict(case='A', subrun='upper',          seed=70,
         glob_pattern='validation_dsilva_fbT0.70_piT-3.00_sigT2.0_logPT3.50_seed70_*190526-1623*.npz'),
    dict(case='A', subrun='representative', seed=68,
         glob_pattern='validation_dsilva_fbT0.70_piT-3.00_sigT2.0_logPT3.50_seed68_*190526-1816*.npz'),
    dict(case='A', subrun='bottom',         seed=119,
         glob_pattern='validation_dsilva_fbT0.70_piT-3.00_sigT2.0_logPT3.50_seed119_*190526-1622*.npz'),
    # Case B — medium (π=0, σ=6)
    dict(case='B', subrun='upper',          seed=97,
         glob_pattern='validation_dsilva_fbT0.70_piT0.00_sigT6.0_logPT3.50_seed97_*200526-1717*.npz'),
    dict(case='B', subrun='representative', seed=137,
         glob_pattern='validation_dsilva_fbT0.70_piT0.00_sigT6.0_logPT3.50_seed137_*190526-1559*.npz'),
    dict(case='B', subrun='bottom',         seed=50,
         glob_pattern='validation_dsilva_fbT0.70_piT0.00_sigT6.0_logPT3.50_seed50_*200526-1726*.npz'),
    # Case C — hard (π=3, σ=10)
    dict(case='C', subrun='upper',          seed=116,
         glob_pattern='validation_dsilva_fbT0.70_piT3.00_sigT10.0_logPT3.50_seed116_*190526-1827*.npz'),
    dict(case='C', subrun='representative', seed=48,
         glob_pattern='validation_dsilva_fbT0.70_piT3.00_sigT10.0_logPT3.50_seed48_*190526-1827*.npz'),
    dict(case='C', subrun='bottom',         seed=87,
         glob_pattern='validation_dsilva_fbT0.70_piT3.00_sigT10.0_logPT3.50_seed87_*190526-1831*.npz'),
    # Case REAL — validation anchored at the real-data D'Silva inference
    # (truth params π=2.40, σ=4.5, f_bin=0.64 — rounded from the real-data
    # marginal max π=+2.46, σ=4.37, f_bin=0.65).
    dict(case='REAL', subrun='upper',          seed=124,
         glob_pattern='validation_dsilva_fbT0.64_piT2.40_sigT4.5_logPT3.50_seed124_*200526-2017*.npz'),
    dict(case='REAL', subrun='representative', seed=43,
         glob_pattern='validation_dsilva_fbT0.64_piT2.40_sigT4.5_logPT3.50_seed43_*200526-2018*.npz'),
    dict(case='REAL', subrun='bottom',         seed=324,
         glob_pattern='validation_dsilva_fbT0.64_piT2.40_sigT4.5_logPT3.50_seed324_*200526-2024*.npz'),
]


# ---------------------------------------------------------------------------
# Style maps
# ---------------------------------------------------------------------------
COLOR_BY_CASE = {
    'A':    '#4A90D9',   # blue   (Case A: easy)
    'B':    '#2E8B57',   # green  (sea green, print-safe — Case B: medium)
    'C':    '#E25A53',   # red    (Case C: hard)
    'REAL': '#7B3294',   # purple (real LMC WC sample + anchored mocks; darker shade stays clearly purple, not brown)
}
SYMBOL_BY_SUBRUN = {
    'upper':          'triangle-up',
    'representative': 'circle',
    'bottom':         'square',
    'true':           'cross',           # Plotly's 'cross' is a plus sign (+)
    'real':           'star',
}
SUBRUN_LABEL = {
    'upper':          'Upper outlier',
    'representative': 'Representative',
    'bottom':         'Bottom outlier',
    'true':           'True input value',
    'real':           "Real D'Silva result",
}
CASE_LABEL = {
    'A':    'Case A (easy, π=−3, σ=2)',
    'B':    'Case B (medium, π=0, σ=6)',
    'C':    'Case C (hard, π=3, σ=10)',
    'REAL': "Case REAL (real-data anchored, π=2.4, σ=4.5)",
}

# Path to the real-data D'Silva bias-correction result (cadence_dsilva_*.npz).
# This file does NOT contain `true_*` keys (real data, no ground truth).
REAL_DATA_GLOB = 'cadence_dsilva_fb*_pi*_N3000_sig1.0-16.0x50_*.npz'

# Shadow alpha for the HDI rectangles (subtle tint matching marker colour).
_HDI_RECT_ALPHA = 0.20

# Per-sub-run shade offset applied on top of the case base colour so that
# overlapping rectangles within the same case are still distinguishable.
# +ve = lighter (blend toward white); -ve = darker (blend toward black).
SHADE_BY_SUBRUN = {
    'upper':          +0.55,
    'representative':  0.00,
    'bottom':         -0.30,   # asymmetric: keep distinct but not too dark
    'true':            0.00,
    'real':            0.00,
}

# Per-sub-run rectangle border dash style — pairs with marker shape so the
# rectangle's outline visually mirrors the marker (triangle → dashed,
# circle → dotted, square → solid).  Makes overlapping rectangles legible.
DASH_BY_SUBRUN = {
    'upper':          'dash',          # matches triangle-up
    'representative': 'dot',           # matches circle
    'bottom':         'solid',         # matches square
    'true':           'solid',         # no rectangle drawn anyway (NaN errors)
    'real':           'longdashdot',   # matches star (real-data anchor)
}


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """'#E25A53' + 0.2 -> 'rgba(226, 90, 83, 0.2)'."""
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f'rgba({r}, {g}, {b}, {alpha:.3f})'


def _shade(hex_color: str, factor: float) -> str:
    """Return `hex_color` shifted toward white (factor > 0) or black (factor < 0).
    Magnitudes in (-1, 1); 0.0 is unchanged.
    """
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    if factor >= 0:
        r = int(round(r + (255 - r) * factor))
        g = int(round(g + (255 - g) * factor))
        b = int(round(b + (255 - b) * factor))
    else:
        f = 1.0 + factor
        r = int(round(r * f))
        g = int(round(g * f))
        b = int(round(b * f))
    r = max(0, min(255, r))
    g = max(0, min(255, g))
    b = max(0, min(255, b))
    return f'#{r:02X}{g:02X}{b:02X}'


def _color_for(case: str, subrun: str) -> str:
    """Resolve marker / rectangle / table colour from case base + sub-run shade."""
    return _shade(COLOR_BY_CASE[case], SHADE_BY_SUBRUN[subrun])


# ---------------------------------------------------------------------------
# Loading + marginalisation
# ---------------------------------------------------------------------------
def _load_run(glob_pattern: str) -> dict | None:
    """Resolve a single .npz under mock_results/, marginalise the 3D
    likelihood, return mode + asymmetric 68% HDI for π and σ_single.

    Returns None on any failure (missing/duplicate match, wrong shape, etc.).
    The caller is responsible for printing the [SKIP] reason.
    """
    full_pattern = os.path.join(_ROOT, 'mock_results', glob_pattern)
    matches = sorted(glob.glob(full_pattern))
    if len(matches) == 0:
        return {'_error': f'no glob match for {glob_pattern}'}
    if len(matches) > 1:
        names = ', '.join(os.path.basename(m) for m in matches)
        return {'_error': f'multiple glob matches: {names}'}

    path = matches[0]
    try:
        d = np.load(path, allow_pickle=True)
    except Exception as exc:
        return {'_error': f'np.load failed: {exc}'}

    try:
        L = np.asarray(d['likelihood'], dtype=float)
        pi_g = np.asarray(d['pi_grid'], dtype=float)
        sig_g = np.asarray(d['sigma_grid'], dtype=float)
        fbin_g = np.asarray(d['fbin_grid'], dtype=float)
    except KeyError as exc:
        return {'_error': f'missing key in npz: {exc}'}

    if L.ndim != 3 or L.shape != (len(sig_g), len(fbin_g), len(pi_g)):
        return {'_error': f'unexpected likelihood shape {L.shape} '
                          f'(expected ({len(sig_g)}, {len(fbin_g)}, {len(pi_g)}))'}

    post_pi    = np.nansum(L, axis=(0, 1))   # marginalise over (σ, f_bin)
    post_sigma = np.nansum(L, axis=(1, 2))   # marginalise over (f_bin, π)
    post_fbin  = np.nansum(L, axis=(0, 2))   # marginalise over (σ, π)

    mode_pi, lo_pi, hi_pi = compute_hdi68(pi_g, post_pi)
    mode_s,  lo_s,  hi_s  = compute_hdi68(sig_g, post_sigma)
    mode_f,  lo_f,  hi_f  = compute_hdi68(fbin_g, post_fbin)

    # Likelihood ratio: L(joint argmax) / L(truth-grid-cell).
    # The npz `likelihood` array is normalised so that L_max = 1, hence the
    # ratio reduces to 1 / L_at_truth.  Guard against NaN / zero truth cells.
    true_pi_val   = float(d['true_pi'])
    true_sig_val  = float(d['true_sigma'])
    true_fbin_val = float(d['true_fbin'])
    i_pi   = int(np.argmin(np.abs(pi_g  - true_pi_val)))
    i_sig  = int(np.argmin(np.abs(sig_g - true_sig_val)))
    i_fbin = int(np.argmin(np.abs(fbin_g - true_fbin_val)))
    L_true = float(L[i_sig, i_fbin, i_pi])
    L_max  = float(np.nanmax(L))
    if not np.isfinite(L_true) or L_true <= 0.0 or not np.isfinite(L_max):
        lik_ratio = float('nan')
    else:
        lik_ratio = L_max / L_true

    return dict(
        path=path,
        mode_pi=float(mode_pi),
        lo_pi=float(lo_pi),
        hi_pi=float(hi_pi),
        mode_sigma=float(mode_s),
        lo_sigma=float(lo_s),
        hi_sigma=float(hi_s),
        mode_fbin=float(mode_f),
        lo_fbin=float(lo_f),
        hi_fbin=float(hi_f),
        lik_ratio=lik_ratio,
        true_pi=true_pi_val,
        true_sigma=true_sig_val,
        true_fbin=true_fbin_val,
    )


def _load_real_data() -> dict | None:
    """Resolve the most-recent real-data D'Silva result under `results/` and
    return marginal-max + 68 % HDI for π, σ_single, f_bin.

    Returns None (with a [SKIP] print) on any failure.  No ground truth is
    available for real data, so the returned dict has no `true_*` keys and no
    likelihood ratio.
    """
    pattern = os.path.join(_ROOT, 'results', REAL_DATA_GLOB)
    matches = sorted(glob.glob(pattern))
    matches = [m for m in matches if 'partial' not in os.path.basename(m)]
    if not matches:
        print(f'[SKIP] REAL.real : no real-data file matches {REAL_DATA_GLOB}')
        return None
    path = max(matches, key=os.path.getmtime)

    try:
        d = np.load(path, allow_pickle=True)
    except Exception as exc:
        print(f'[SKIP] REAL.real : np.load failed: {exc}')
        return None

    try:
        L = np.asarray(d['likelihood'], dtype=float)
        pi_g = np.asarray(d['pi_grid'], dtype=float)
        sig_g = np.asarray(d['sigma_grid'], dtype=float)
        fbin_g = np.asarray(d['fbin_grid'], dtype=float)
    except KeyError as exc:
        print(f'[SKIP] REAL.real : missing key in npz: {exc}')
        return None

    if L.ndim != 3 or L.shape != (len(sig_g), len(fbin_g), len(pi_g)):
        print(f'[SKIP] REAL.real : unexpected likelihood shape {L.shape}')
        return None

    post_pi    = np.nansum(L, axis=(0, 1))
    post_sigma = np.nansum(L, axis=(1, 2))
    post_fbin  = np.nansum(L, axis=(0, 2))
    mode_pi, lo_pi, hi_pi = compute_hdi68(pi_g, post_pi)
    mode_s,  lo_s,  hi_s  = compute_hdi68(sig_g, post_sigma)
    mode_f,  lo_f,  hi_f  = compute_hdi68(fbin_g, post_fbin)

    print(f'[ OK ] REAL.real         path={os.path.basename(path)} '
          f'| π = {mode_pi:+.3f} +{hi_pi - mode_pi:.3f} / -{mode_pi - lo_pi:.3f} '
          f'| σ = {mode_s:.2f} +{hi_s - mode_s:.2f} / -{mode_s - lo_s:.2f} '
          f'| f_bin = {mode_f:.3f} +{hi_f - mode_f:.3f} / -{mode_f - lo_f:.3f}')

    return dict(
        case='REAL', subrun='real',
        pi=float(mode_pi),       sigma_single=float(mode_s),  fbin=float(mode_f),
        pi_err_low=float(max(0.0, mode_pi - lo_pi)),
        pi_err_high=float(max(0.0, hi_pi - mode_pi)),
        sigma_err_low=float(max(0.0, mode_s - lo_s)),
        sigma_err_high=float(max(0.0, hi_s - mode_s)),
        fbin_err_low=float(max(0.0, mode_f - lo_f)),
        fbin_err_high=float(max(0.0, hi_f - mode_f)),
        lik_ratio=float('nan'),
    )


def _build_dataframe() -> pd.DataFrame:
    """Build the 11-row dataframe (≤8 recovered + ≤3 truths).

    Prints one [ OK ]/[SKIP] line per RUNS entry plus one [ OK ] line per
    truth row (one per case with at least one successful sub-run).
    """
    rows: list[dict] = []
    truths: dict[str, tuple[float, float, float]] = {}  # case → (true_pi, true_sigma, true_fbin)

    for run in RUNS:
        case, subrun, seed = run['case'], run['subrun'], run['seed']
        result = _load_run(run['glob_pattern'])
        if result is None or '_error' in result:
            reason = (result or {}).get('_error', 'unknown error')
            print(f'[SKIP] {case}.{subrun} seed={seed} : {reason}')
            continue

        mode_pi, lo_pi, hi_pi = result['mode_pi'], result['lo_pi'], result['hi_pi']
        mode_s,  lo_s,  hi_s  = result['mode_sigma'], result['lo_sigma'], result['hi_sigma']
        mode_f,  lo_f,  hi_f  = result['mode_fbin'],  result['lo_fbin'],  result['hi_fbin']

        # Asymmetric error magnitudes (always ≥ 0 by construction of HDI).
        pi_err_low  = max(0.0, mode_pi - lo_pi)
        pi_err_high = max(0.0, hi_pi - mode_pi)
        s_err_low   = max(0.0, mode_s - lo_s)
        s_err_high  = max(0.0, hi_s - mode_s)
        f_err_low   = max(0.0, mode_f - lo_f)
        f_err_high  = max(0.0, hi_f - mode_f)

        rows.append(dict(
            case=case, subrun=subrun,
            pi=mode_pi, sigma_single=mode_s, fbin=mode_f,
            pi_err_low=pi_err_low, pi_err_high=pi_err_high,
            sigma_err_low=s_err_low, sigma_err_high=s_err_high,
            fbin_err_low=f_err_low, fbin_err_high=f_err_high,
            lik_ratio=result['lik_ratio'],
        ))

        print(f'[ OK ] {case}.{subrun:<14} seed={seed:<4} '
              f'| π = {mode_pi:+.3f}  +{pi_err_high:.3f} / -{pi_err_low:.3f} '
              f'| σ = {mode_s:.2f}  +{s_err_high:.2f} / -{s_err_low:.2f} '
              f'| f_bin = {mode_f:.3f}  +{f_err_high:.3f} / -{f_err_low:.3f} '
              f'| L_max/L_true = {result["lik_ratio"]:.3g}')

        # Record (and assert consistency of) truth values per case.
        t_pi, t_s, t_f = result['true_pi'], result['true_sigma'], result['true_fbin']
        if case in truths:
            prev_pi, prev_s, prev_f = truths[case]
            if (abs(prev_pi - t_pi) > 1e-9 or abs(prev_s - t_s) > 1e-9
                    or abs(prev_f - t_f) > 1e-9):
                print(f'[WARN] {case}.{subrun} truth mismatch: '
                      f'({prev_pi}, {prev_s}, {prev_f}) vs ({t_pi}, {t_s}, {t_f})')
        else:
            truths[case] = (t_pi, t_s, t_f)

    # Append one truth row per case (in sorted case order for stable output).
    # Case 'REAL' is intentionally skipped — the real-data yellow star (added in
    # __main__ via _load_real_data) already represents the anchor parameters,
    # so a separate truth plus-sign would be redundant.
    for case in sorted(truths):
        if case == 'REAL':
            continue
        t_pi, t_s, t_f = truths[case]
        rows.append(dict(
            case=case, subrun='true',
            pi=t_pi, sigma_single=t_s, fbin=t_f,
            pi_err_low=np.nan, pi_err_high=np.nan,
            sigma_err_low=np.nan, sigma_err_high=np.nan,
            fbin_err_low=np.nan, fbin_err_high=np.nan,
            lik_ratio=np.nan,
        ))
        print(f'[ OK ] {case}.true                  '
              f'| true_pi = {t_pi:+.3f}  true_sigma = {t_s:.2f}  true_fbin = {t_f:.3f}')

    return pd.DataFrame(rows, columns=[
        'case', 'subrun', 'pi', 'sigma_single', 'fbin',
        'pi_err_low', 'pi_err_high',
        'sigma_err_low', 'sigma_err_high',
        'fbin_err_low', 'fbin_err_high',
        'lik_ratio',
    ])


# ---------------------------------------------------------------------------
# Figure construction (pure — no I/O, no prints)
# ---------------------------------------------------------------------------
def _dummy_legend_traces() -> list[go.Scatter]:
    """Build invisible legend-only traces: 3 case colours + 4 sub-run shapes
    + 1 standalone entry for the real-data star."""
    traces: list[go.Scatter] = []

    # Case group — coloured circle swatches (shape is neutral; the colour is the key).
    for case in ['A', 'B', 'C']:
        traces.append(go.Scatter(
            x=[None], y=[None], mode='markers',
            marker=dict(symbol='circle', size=12,
                        color=COLOR_BY_CASE[case],
                        line=dict(color='#000000', width=0.6)),
            name=CASE_LABEL[case],
            legendgroup='cases',
            legendgrouptitle_text='Mock cases',
            showlegend=True,
            hoverinfo='skip',
        ))

    # Sub-run group — the marker shape lives BEFORE the text in the Plotly
    # legend swatch (we can't change that), but the matching rectangle-frame
    # dash pattern is appended AFTER the label using Unicode box-drawing
    # glyphs so it isn't obscured by the marker (triangle/circle/square edges
    # were hiding the in-swatch line previously).
    _DASH_GLYPH = {
        'dash':        ' ┄ ┄ ┄ ┄ ┄',     # triple-dash horizontal
        'dot':         ' · · · · · · ·', # middle-dot row
        'solid':       ' ──────',         # solid bar
        'longdashdot': ' ── · ── ·',     # long-dash-dot
    }
    for subrun in ['upper', 'representative', 'bottom', 'true']:
        is_truth = (subrun == 'true')
        label = SUBRUN_LABEL[subrun]
        if not is_truth:
            label = f'{label}{_DASH_GLYPH[DASH_BY_SUBRUN[subrun]]}'
        traces.append(go.Scatter(
            x=[None], y=[None], mode='markers',
            marker=dict(symbol=SYMBOL_BY_SUBRUN[subrun], size=12,
                        color='#BFBFBF',
                        line=dict(color='#000000', width=1.0)),
            name=label,
            legendgroup='subruns',
            legendgrouptitle_text='Sub-run',
            showlegend=True,
            hoverinfo='skip',
        ))

    # Real-data group — single coloured star; the dash-dot frame glyph
    # follows the label in the same way as the sub-run entries.
    traces.append(go.Scatter(
        x=[None], y=[None], mode='markers',
        marker=dict(symbol=SYMBOL_BY_SUBRUN['real'], size=14,
                    color=COLOR_BY_CASE['REAL'],
                    line=dict(color='#000000', width=1.0)),
        name=f"{CASE_LABEL['REAL']}{_DASH_GLYPH[DASH_BY_SUBRUN['real']]}",
        legendgroup='real',
        legendgrouptitle_text='Real data',
        showlegend=True,
        hoverinfo='skip',
    ))

    return traces


def _data_trace(row: pd.Series) -> go.Scatter:
    """Real marker trace for a single dataframe row (showlegend=False)."""
    is_truth = (row['subrun'] == 'true')
    is_real  = (row['subrun'] == 'real')
    if is_real:
        size, line_width = 16, 1.4
    elif is_truth:
        size, line_width = 14, 1.4
    else:
        size, line_width = 9, 0.9
    color = _color_for(row['case'], row['subrun'])
    symbol = SYMBOL_BY_SUBRUN[row['subrun']]
    label = f"{row['case']} · {SUBRUN_LABEL[row['subrun']]}"

    hover_lines = [
        f"<b>{label}</b>",
        f"π = {row['pi']:+.3f}",
        f"σ_single = {row['sigma_single']:.2f} km/s",
    ]
    if not is_truth:
        hover_lines.append(
            f"π HDI: [{row['pi'] - row['pi_err_low']:+.3f}, "
            f"{row['pi'] + row['pi_err_high']:+.3f}]"
        )
        hover_lines.append(
            f"σ HDI: [{max(0.0, row['sigma_single'] - row['sigma_err_low']):.2f}, "
            f"{row['sigma_single'] + row['sigma_err_high']:.2f}]"
        )

    return go.Scatter(
        x=[row['pi']],
        y=[row['sigma_single']],
        mode='markers',
        marker=dict(symbol=symbol, size=size, color=color,
                    line=dict(color='#000000', width=line_width)),
        showlegend=False,
        hovertemplate='<br>'.join(hover_lines) + '<extra></extra>',
        name=label,
    )


def _cross_hair_shapes(row: pd.Series) -> list[dict]:
    """Single semi-transparent rectangle spanning the 68 % HDI box.

    The rectangle is sized to (pi_err_low + pi_err_high) × (σ_err_low + σ_err_high)
    and is positioned so the marker sits at the joint marginal-max coordinate
    (which is the geometric centre when the HDI is symmetric, and offset when
    asymmetric).  Skips the shape if both axes have zero HDI width.
    """
    color = _color_for(row['case'], row['subrun'])
    dash  = DASH_BY_SUBRUN.get(row['subrun'], 'solid')

    x_lo = row['pi'] - row['pi_err_low']
    x_hi = row['pi'] + row['pi_err_high']
    y_lo = row['sigma_single'] - row['sigma_err_low']
    y_hi = row['sigma_single'] + row['sigma_err_high']

    if x_hi <= x_lo and y_hi <= y_lo:
        return []

    return [dict(
        type='rect', xref='x', yref='y',
        x0=x_lo, x1=x_hi,
        y0=y_lo, y1=y_hi,
        fillcolor=_hex_to_rgba(color, _HDI_RECT_ALPHA),
        line=dict(color=color, width=1.6, dash=dash),
        layer='below',
    )]


def make_validation_summary_figure(runs_df: pd.DataFrame) -> go.Figure:
    """Build the 2D recovery scatter (σ_single vs π) with dashed HDI cross-hairs.

    Parameters
    ----------
    runs_df : pd.DataFrame
        Columns: case, subrun, pi, sigma_single,
                 pi_err_low, pi_err_high, sigma_err_low, sigma_err_high.
        Truth rows (subrun == 'true') have NaN error columns.

    Returns
    -------
    plotly.graph_objects.Figure
    """
    fig = go.Figure()

    # 1. Dummy legend traces (3 case shapes + 4 sub-run colours).
    for trace in _dummy_legend_traces():
        fig.add_trace(trace)

    # 2. Real data traces — one per dataframe row.
    for _, row in runs_df.iterrows():
        fig.add_trace(_data_trace(row))

    # 3. Dashed cross-hair shapes — for non-truth rows only.
    shapes: list[dict] = []
    non_truth = runs_df[runs_df['subrun'] != 'true']
    for _, row in non_truth.iterrows():
        shapes.extend(_cross_hair_shapes(row))

    # 4. Axis ranges derived from data extent + 10% padding, clamped to
    # physical bounds (x ∈ [-3.5, 3.5]; y ≥ 0 and y ≤ 11.5).
    if len(non_truth) > 0:
        x_lo_data = float(np.nanmin(non_truth['pi'] - non_truth['pi_err_low']))
        x_hi_data = float(np.nanmax(non_truth['pi'] + non_truth['pi_err_high']))
        y_lo_data = float(np.nanmin(non_truth['sigma_single'] - non_truth['sigma_err_low']))
        y_hi_data = float(np.nanmax(non_truth['sigma_single'] + non_truth['sigma_err_high']))
    else:
        x_lo_data, x_hi_data = -3.0, 3.0
        y_lo_data, y_hi_data = 1.0, 11.0

    # Also include truth coordinates (they have NaN errors).
    truth_rows = runs_df[runs_df['subrun'] == 'true']
    if len(truth_rows) > 0:
        x_lo_data = min(x_lo_data, float(np.nanmin(truth_rows['pi'])))
        x_hi_data = max(x_hi_data, float(np.nanmax(truth_rows['pi'])))
        y_lo_data = min(y_lo_data, float(np.nanmin(truth_rows['sigma_single'])))
        y_hi_data = max(y_hi_data, float(np.nanmax(truth_rows['sigma_single'])))

    x_pad = 0.10 * max(0.5, x_hi_data - x_lo_data)
    y_pad = 0.10 * max(0.5, y_hi_data - y_lo_data)
    x_range = [max(-3.5, x_lo_data - x_pad), min(3.5, x_hi_data + x_pad)]
    y_range = [max(0.0,  y_lo_data - y_pad), min(11.5, y_hi_data + y_pad)]

    # 5. Layout — merge PLOTLY_THEME with A&A white-bg overrides
    # (overlapping keys like plot_bgcolor would otherwise raise a duplicate-kwarg
    # TypeError when spread together).  AA wins on conflicts.
    _theme = {**PLOTLY_THEME, **_AA_OVERRIDES}
    _theme['title'] = dict(
        text='Validation sweep recovery: marginal-max ± 68% HDI vs. truth',
        x=0.5, xanchor='center',
    )
    _theme['shapes'] = shapes
    _theme['legend'] = dict(
        **_AA_OVERRIDES.get('legend', {}),
        groupclick='toggleitem',
        x=1.02, y=1.0, xanchor='left', yanchor='top',
    )
    _theme['margin'] = dict(l=80, r=200, t=80, b=70)
    _theme['width'] = 900
    _theme['height'] = 620
    _theme['annotations'] = [dict(
        xref='paper', yref='paper', x=0.02, y=0.98,
        xanchor='left', yanchor='top',
        text='Markers: marginal max  •  shaded box: 68 % HDI (asymmetric)',
        showarrow=False,
        font=dict(family='Times New Roman, serif', size=11, color='#000000'),
        bgcolor='#FFFFFF', bordercolor='#000000', borderwidth=1,
        borderpad=4,
    )]
    fig.update_layout(**_theme)

    fig.update_xaxes(
        title_text='π (period power-law index)',
        range=x_range, zeroline=False,
    )
    fig.update_yaxes(
        title_text='σ<sub>single</sub> (km s⁻¹)',
        range=y_range, zeroline=False,
    )

    return fig


# ---------------------------------------------------------------------------
# Corner plot (3-panel lower-triangle: σ-π, f_bin-π, f_bin-σ)
# ---------------------------------------------------------------------------
# Per-axis physical ranges shared across all panels (matches grid extents +
# small padding).  Used to keep axis ranges consistent in the corner layout.
_AXIS_INFO = {
    'pi':           dict(title='π (period power-law index)', range=[-3.5, 3.5]),
    'sigma_single': dict(title='σ<sub>single</sub> (km s⁻¹)', range=[0.5, 11.5]),
    'fbin':         dict(title='f<sub>bin</sub>',             range=[-0.02, 1.02]),
}


def _panel_marker_trace(row: pd.Series, x_col: str, y_col: str) -> go.Scatter:
    """Real marker trace for one panel of the corner plot (no legend)."""
    is_truth = (row['subrun'] == 'true')
    is_real  = (row['subrun'] == 'real')
    if is_real:
        size, line_width = 16, 1.4
    elif is_truth:
        size, line_width = 14, 1.4
    else:
        size, line_width = 9, 0.9
    color = _color_for(row['case'], row['subrun'])
    symbol = SYMBOL_BY_SUBRUN[row['subrun']]
    label = f"{row['case']} · {SUBRUN_LABEL[row['subrun']]}"

    hover_lines = [
        f"<b>{label}</b>",
        f"{x_col} = {row[x_col]:+.3f}",
        f"{y_col} = {row[y_col]:+.3f}",
    ]
    return go.Scatter(
        x=[row[x_col]], y=[row[y_col]],
        mode='markers',
        marker=dict(symbol=symbol, size=size, color=color,
                    line=dict(color='#000000', width=line_width)),
        showlegend=False,
        hovertemplate='<br>'.join(hover_lines) + '<extra></extra>',
        name=label,
    )


def _panel_cross_hair_specs(row: pd.Series,
                            x_col: str, y_col: str,
                            x_err_low_col: str, x_err_high_col: str,
                            y_err_low_col: str, y_err_high_col: str) -> list[dict]:
    """Return a single semi-transparent rectangle dict covering the 68 % HDI
    box for one recovered row.  Caller binds it to a subplot via
    add_shape(..., row=r, col=c).  Skips if both axes have zero HDI width.
    """
    color = _color_for(row['case'], row['subrun'])
    dash  = DASH_BY_SUBRUN.get(row['subrun'], 'solid')

    x_lo = row[x_col] - row[x_err_low_col]
    x_hi = row[x_col] + row[x_err_high_col]
    y_lo = row[y_col] - row[y_err_low_col]
    y_hi = row[y_col] + row[y_err_high_col]

    if x_hi <= x_lo and y_hi <= y_lo:
        return []

    return [dict(
        type='rect',
        x0=x_lo, x1=x_hi,
        y0=y_lo, y1=y_hi,
        fillcolor=_hex_to_rgba(color, _HDI_RECT_ALPHA),
        line=dict(color=color, width=1.6, dash=dash),
        layer='below',
    )]


def _add_panel(fig: go.Figure, runs_df: pd.DataFrame,
               x_col: str, y_col: str,
               x_err_low_col: str, x_err_high_col: str,
               y_err_low_col: str, y_err_high_col: str,
               row: int, col: int) -> None:
    """Add 12 marker traces + ≤18 cross-hair shapes to one subplot of `fig`."""
    for _, r in runs_df.iterrows():
        fig.add_trace(_panel_marker_trace(r, x_col, y_col), row=row, col=col)
        if r['subrun'] == 'true':
            continue
        for spec in _panel_cross_hair_specs(
                r, x_col, y_col,
                x_err_low_col, x_err_high_col,
                y_err_low_col, y_err_high_col):
            fig.add_shape(**spec, row=row, col=col)


def _lik_ratio_table(runs_df: pd.DataFrame) -> go.Table:
    """Build the likelihood-ratio summary table (recovered rows only).

    Column 0: Case (single letter, on case-tinted background)
    Column 1: Sub-run (label)
    Column 2: L_max / L_true (joint argmax likelihood over truth-cell likelihood;
              equivalently exp(logL_argmax − logL_true_cell)).  Formatted with
              3 significant figures, scientific notation when |x| ≥ 1000.

    Rows are coloured with a light tint of their case colour to tie them
    visually to the scatter panels.
    """
    non_truth = runs_df[
        (runs_df['subrun'] != 'true') & (runs_df['subrun'] != 'real')
    ].copy()

    cases    = [r['case'] for _, r in non_truth.iterrows()]
    subrun_k = [r['subrun'] for _, r in non_truth.iterrows()]
    subruns  = [SUBRUN_LABEL[s] for s in subrun_k]
    ratios   = [f'{r["lik_ratio"]:.3g}' if np.isfinite(r['lik_ratio']) else '—'
                for _, r in non_truth.iterrows()]

    # Row backgrounds — light tint of the SAME (case, sub-run) shade used in
    # the scatter panels, so the row colour directly matches its marker.
    row_bg = [_hex_to_rgba(_color_for(c, s), 0.16) for c, s in zip(cases, subrun_k)]
    # fill_color in go.Table is [col0_row_colors, col1_row_colors, ...].
    cell_fill = [row_bg, row_bg, row_bg]

    return go.Table(
        header=dict(
            values=['<b>Case</b>', '<b>Sub-run</b>',
                    '<b>L<sub>max</sub> / L<sub>true</sub></b>'],
            fill_color='#FFFFFF',
            line_color='#000000',
            align=['center', 'left', 'right'],
            font=dict(family='Times New Roman, serif', size=12, color='#000000'),
            height=28,
        ),
        cells=dict(
            values=[cases, subruns, ratios],
            fill_color=cell_fill,
            line_color='#000000',
            align=['center', 'left', 'right'],
            font=dict(family='Times New Roman, serif', size=11, color='#000000'),
            height=24,
        ),
        columnwidth=[0.20, 0.55, 0.45],
    )


def make_validation_corner_figure(runs_df: pd.DataFrame) -> go.Figure:
    """Build a 3-panel lower-triangle corner plot for (π, σ_single, f_bin).

    Panels:
        (1,1)  σ_single vs π
        (2,1)  f_bin    vs π
        (2,2)  f_bin    vs σ_single

    No 1-D marginal histograms (the corner shows only pairwise scatter +
    dashed asymmetric 68 % HDI cross-hairs and green-filled truth markers).
    """
    fig = make_subplots(
        rows=2, cols=2,
        specs=[[{'type': 'xy'},     {'type': 'domain'}],
               [{'type': 'xy'},     {'type': 'xy'}]],
        horizontal_spacing=0.10,
        vertical_spacing=0.10,
    )

    # Dummy legend traces (placed in panel (1,1) — they are point-less so they
    # do not change axis ranges).
    for trace in _dummy_legend_traces():
        fig.add_trace(trace, row=1, col=1)

    # Likelihood-ratio table in the empty (1,2) quadrant.
    fig.add_trace(_lik_ratio_table(runs_df), row=1, col=2)

    # Panel (1,1): σ_single (y) vs π (x)
    _add_panel(fig, runs_df,
               x_col='pi',           y_col='sigma_single',
               x_err_low_col='pi_err_low',    x_err_high_col='pi_err_high',
               y_err_low_col='sigma_err_low', y_err_high_col='sigma_err_high',
               row=1, col=1)

    # Panel (2,1): f_bin (y) vs π (x)
    _add_panel(fig, runs_df,
               x_col='pi',           y_col='fbin',
               x_err_low_col='pi_err_low',   x_err_high_col='pi_err_high',
               y_err_low_col='fbin_err_low', y_err_high_col='fbin_err_high',
               row=2, col=1)

    # Panel (2,2): f_bin (y) vs σ_single (x)
    _add_panel(fig, runs_df,
               x_col='sigma_single', y_col='fbin',
               x_err_low_col='sigma_err_low', x_err_high_col='sigma_err_high',
               y_err_low_col='fbin_err_low',  y_err_high_col='fbin_err_high',
               row=2, col=2)

    # Theme — merge PLOTLY_THEME with A&A white-bg overrides.  We strip the
    # `xaxis`/`yaxis` keys before passing as layout kwargs because they apply
    # only to the first subplot's axes; the per-axis styling is applied via
    # update_xaxes/update_yaxes below (broadcasts to ALL subplots).
    _theme = {**PLOTLY_THEME, **_AA_OVERRIDES}
    _theme.pop('xaxis', None)
    _theme.pop('yaxis', None)
    _theme['title'] = dict(
        text='Validation sweep recovery — corner plot (marginal max ± 68 % HDI)',
        x=0.5, xanchor='center',
    )
    _theme['legend'] = dict(
        **_AA_OVERRIDES.get('legend', {}),
        groupclick='toggleitem',
        x=1.02, y=1.0, xanchor='left', yanchor='top',
    )
    _theme['margin'] = dict(l=90, r=210, t=90, b=80)
    _theme['width'] = 1100
    _theme['height'] = 900
    _theme['annotations'] = [dict(
        xref='paper', yref='paper', x=0.02, y=0.99,
        xanchor='left', yanchor='top',
        text='Markers: marginal max  •  shaded box: 68 % HDI (asymmetric)',
        showarrow=False,
        font=dict(family='Times New Roman, serif', size=11, color='#000000'),
        bgcolor='#FFFFFF', bordercolor='#000000', borderwidth=1,
        borderpad=4,
    )]
    fig.update_layout(**_theme)

    # Broadcast A&A axis styling to ALL subplots — strip the `title` key so
    # we don't overwrite per-axis titles set below.
    _aa_x = {k: v for k, v in _AA_OVERRIDES['xaxis'].items() if k != 'title'}
    _aa_y = {k: v for k, v in _AA_OVERRIDES['yaxis'].items() if k != 'title'}
    fig.update_xaxes(**_aa_x)
    fig.update_yaxes(**_aa_y)

    # Per-panel axis labels and ranges.
    _title_font = dict(family='Times New Roman, serif', size=13, color='#000000')

    # Panel (1,1): σ_single (y) vs π (x)
    fig.update_xaxes(title_text=_AXIS_INFO['pi']['title'],
                     title_font=_title_font,
                     range=_AXIS_INFO['pi']['range'],
                     zeroline=False, row=1, col=1)
    fig.update_yaxes(title_text=_AXIS_INFO['sigma_single']['title'],
                     title_font=_title_font,
                     range=_AXIS_INFO['sigma_single']['range'],
                     zeroline=False, row=1, col=1)
    # Panel (2,1): f_bin (y) vs π (x)
    fig.update_xaxes(title_text=_AXIS_INFO['pi']['title'],
                     title_font=_title_font,
                     range=_AXIS_INFO['pi']['range'],
                     zeroline=False, row=2, col=1)
    fig.update_yaxes(title_text=_AXIS_INFO['fbin']['title'],
                     title_font=_title_font,
                     range=_AXIS_INFO['fbin']['range'],
                     zeroline=False, row=2, col=1)
    # Panel (2,2): f_bin (y) vs σ_single (x)
    fig.update_xaxes(title_text=_AXIS_INFO['sigma_single']['title'],
                     title_font=_title_font,
                     range=_AXIS_INFO['sigma_single']['range'],
                     zeroline=False, row=2, col=2)
    fig.update_yaxes(title_text=_AXIS_INFO['fbin']['title'],
                     title_font=_title_font,
                     range=_AXIS_INFO['fbin']['range'],
                     zeroline=False, row=2, col=2)

    return fig


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    df = _build_dataframe()

    # Append the real-data D'Silva result as a single extra row (case='REAL',
    # subrun='real').  No truth values, NaN likelihood ratio.
    real_row = _load_real_data()
    if real_row is not None:
        df = pd.concat([df, pd.DataFrame([real_row])], ignore_index=True)

    n_recovered = int(((df['subrun'] != 'true') & (df['subrun'] != 'real')).sum())
    n_truth     = int((df['subrun'] == 'true').sum())
    n_real      = int((df['subrun'] == 'real').sum())

    out_dir = os.path.join(_ROOT, 'plots')
    os.makedirs(out_dir, exist_ok=True)

    def _save(fig: go.Figure, basename: str) -> None:
        out_html = os.path.join(out_dir, f'{basename}.html')
        out_png  = os.path.join(out_dir, f'{basename}.png')
        fig.write_html(out_html, include_plotlyjs='cdn')
        print(f'Saved HTML: {os.path.abspath(out_html)}')
        try:
            fig.write_image(out_png, scale=2)
            print(f'Saved PNG:  {os.path.abspath(out_png)}')
        except ImportError as exc:
            print(f'PNG export skipped: {exc}')
        except Exception as exc:
            print(f'PNG export skipped: {exc}')

    # 1. Single-panel σ-vs-π (original deliverable).
    _save(make_validation_summary_figure(df), 'validation_summary_sigma_vs_pi')
    # 2. Corner plot — 3-panel lower-triangle (σ-π, f_bin-π, f_bin-σ).
    _save(make_validation_corner_figure(df), 'validation_summary_corner')

    print(f'Plotted {n_recovered}/{len(RUNS)} recovered points '
          f'+ {n_truth}/3 truths + {n_real}/1 real-data point.')
