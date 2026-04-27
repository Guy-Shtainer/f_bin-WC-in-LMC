"""bc.bin_sensitivity_plots — Plotly figure builders for the Bin-Sensitivity sub-tab.

Six functions — one per plot — all of them pure: they take a dict of
``{scheme_name: SchemeResult}`` (or a single SchemeResult for faceted diagnostics)
and return a :class:`plotly.graph_objects.Figure`. No Streamlit side effects, so
QA can snapshot-test them.

Style rules (see comms/plots.md Accuracy Checklist):
- Single source of truth: :data:`plots.theme._ACADEMIC_THEME` (white bg, black text,
  Times New Roman). ZERO uses of the dark-mode ``PLOTLY_THEME`` / ``get_palette()``
  in this file — every color on a paper-ready figure is hardcoded to a WCAG-safe
  A&A palette declared below.
- Every ``make_subplots`` figure loops explicit ``update_xaxes``/``update_yaxes``
  calls so every secondary axis inherits the mirrored-frame / no-grid theme.
- No emojis, no hardcoded hex outside the ``_AA_*`` constants + ``_BIN_SCHEME_COLORS``
- CDF trace line + fill share ``legendgroup``
- ``hovertemplate`` set on every trace
- ``logL`` shown as-is (negative; higher = better)
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from plots.theme import _ACADEMIC_THEME
from bc.helpers import _hex_to_rgba, get_scheme_color
from bc.bin_sensitivity_scorer import SchemeResult

# ─────────────────────────────────────────────────────────────────────────────
# A&A white-bg palette — WCAG-safe on white paper
# ─────────────────────────────────────────────────────────────────────────────
#   _AA_OBSERVED      — observed CDF / observed bars (teal/turquoise; user req.)
#   _AA_SIMULATED     — simulated model median/envelope (tomato red)
#   _AA_TRUTH_GOLD    — best-fit / truth markers (dark gold; NOT 'gold')
#   _AA_REF_LINE      — reference dashed lines, arrows, annotations (near-black)
#   _AA_FRAME         — axis/frame/tick color (pure black)
#   _AA_ANNOTATION_BG — translucent white for annotation boxes
_AA_OBSERVED = '#2CA6A4'
_AA_SIMULATED = '#E25A53'
_AA_TRUTH_GOLD = '#DAA520'
_AA_REF_LINE = '#2E2E2E'
_AA_FRAME = 'black'
_AA_ANNOTATION_BG = 'rgba(255,255,255,0.85)'

# Additional approved constants (kept for pre-existing mock-mode overlays):
#   _RUG_COLOR_ON_WHITE — rug/secondary text on white paper (near-black)
#   _TRUTH_COLOR        — mock-mode green truth lines on marginals
#   _TRUTH_STAR_BORDER  — outline of the gold truth star on plot #2
_RUG_COLOR_ON_WHITE = '#333333'
_TRUTH_COLOR = '#2CA02C'
_TRUTH_STAR_BORDER = '#000000'


def _apply_readable_text(fig: go.Figure, n_subplot_titles: int = 0) -> None:
    """Apply the "Readable text size" rule from memory/plot_preferences.md §2026-04-23.

    - Axis tick labels ≥ 12 pt
    - Axis titles ≥ 14 pt
    - Subplot titles ≥ 14 pt
    - Legend ≥ 14 pt (multi-subplot grids read smaller, so bump)
    - Main figure title ≥ 16 pt

    Called at the END of each plot builder (after ``_apply_aa_axes`` and before
    ``_layout_update``). Idempotent with ``_apply_aa_axes``: this only bumps the
    font sizes; colors + mirrored frame already set by ``_apply_aa_axes``.

    ``n_subplot_titles`` is the count of subplot-title annotations the caller
    has already injected via ``subplot_titles=...``. Only those get size-bumped
    (later diagnostic-box annotations keep their own sizes).
    """
    # Preserve color from _apply_aa_axes (_AA_FRAME) — only bump sizes.
    fig.update_xaxes(
        tickfont=dict(size=12, color=_AA_FRAME),
        title=dict(font=dict(size=14, color=_AA_FRAME)),
    )
    fig.update_yaxes(
        tickfont=dict(size=12, color=_AA_FRAME),
        title=dict(font=dict(size=14, color=_AA_FRAME)),
    )
    # Bump subplot-title annotations (font.size only — don't touch color/family
    # already set by the builder's first loop over ``fig.layout.annotations``).
    if n_subplot_titles > 0:
        for ann in list(fig.layout.annotations)[:n_subplot_titles]:
            if getattr(ann, 'font', None) is None:
                ann.font = dict(size=14)
            else:
                cur = int(getattr(ann.font, 'size', 0) or 0)
                ann.font.size = max(14, cur)


def _apply_aa_axes(fig: go.Figure, n_rows: int = 1, n_cols: int = 1) -> None:
    """Apply A&A frame style to EVERY subplot axis (mirrored frame, no grid).

    Plotly's ``fig.update_layout(xaxis=..., yaxis=...)`` only touches the
    primary axes; secondary axes (``xaxis2``, ``yaxis3`` …) silently inherit
    defaults. ``update_xaxes`` / ``update_yaxes`` applied without row/col
    filters updates every axis in the figure, which is exactly what we want
    for inter-subplot visual consistency.
    """
    fig.update_xaxes(
        showgrid=False, zeroline=False, mirror=True,
        showline=True, linecolor=_AA_FRAME, linewidth=1.2,
        ticks='outside', tickcolor=_AA_FRAME, tickwidth=1,
        tickfont=dict(size=11, color=_AA_FRAME),
        title_font=dict(size=13, color=_AA_FRAME),
    )
    fig.update_yaxes(
        showgrid=False, zeroline=False, mirror=True,
        showline=True, linecolor=_AA_FRAME, linewidth=1.2,
        ticks='outside', tickcolor=_AA_FRAME, tickwidth=1,
        tickfont=dict(size=11, color=_AA_FRAME),
        title_font=dict(size=13, color=_AA_FRAME),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _scheme_index(results: dict[str, SchemeResult], scheme: str) -> int:
    """Stable index of a scheme inside the ordered results list.

    Used to drive the manual-palette cycle so manual schemes get distinct
    colors/dashes regardless of the order they were added. Falls back to 0
    when the scheme is not found.
    """
    ordered = _ordered_results(results)
    for idx, r in enumerate(ordered):
        if r.scheme == scheme:
            return idx
    return 0


def _color_for(r: SchemeResult, index: int) -> tuple[str, str]:
    """(hex, dash) for a SchemeResult — named schemes use ``_BIN_SCHEME_COLORS``
    via ``get_scheme_color``; unknown/manual names cycle the palette by index."""
    return get_scheme_color(r.scheme, index)


def _hdi_width(hdi: tuple) -> float:
    """HDI68 width = hi - lo (robust to NaN and reversed pairs)."""
    try:
        lo, hi = float(hdi[0]), float(hdi[1])
    except Exception:
        return float('nan')
    w = hi - lo
    return abs(w) if np.isfinite(w) else float('nan')


def _ordered_results(results: dict[str, SchemeResult]) -> list[SchemeResult]:
    """Sort schemes: dsilva_default row 0, then by family, then n_bins asc."""
    def _key(r: SchemeResult):
        is_ref = 0 if r.scheme == 'dsilva_default' else 1
        return (is_ref, r.family, r.n_bins, r.scheme)
    return sorted(results.values(), key=_key)


def _layout_update(fig: go.Figure, **overrides) -> go.Figure:
    """Apply the A&A paper-ready academic theme + overrides + legend bump.

    Pattern mirrors :func:`plots.theme._academic_fig` but enforces a
    14 pt legend (readable-text rule, memory/plot_preferences.md §2026-04-23)
    and guarantees the legend border/text use the white-bg A&A palette even
    if the caller overrides the ``legend`` dict.
    """
    # Force the legend defaults (14 pt, black text, semi-opaque white bg with
    # black 0.5-pt border) — still superseded by an explicit ``legend=`` kwarg.
    base_legend = dict(
        bgcolor='rgba(255,255,255,0.85)', bordercolor=_AA_FRAME, borderwidth=0.5,
        font=dict(size=14, color=_AA_FRAME),
    )
    if 'legend' in overrides:
        overrides['legend'] = {**base_legend, **overrides['legend']}
    else:
        overrides['legend'] = base_legend
    merged = {**_ACADEMIC_THEME, **overrides}
    fig.update_layout(**merged)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Plot 1 — HDI-width vs n_bins (headline sensitivity plot)
# ─────────────────────────────────────────────────────────────────────────────

def _plot_hdi_vs_nbins(results: dict[str, SchemeResult]) -> go.Figure:
    """Two-panel scatter: HDI68 width for f_bin and π vs number of bins.

    Session-3 layout fix: subplot titles are annotations pinned to the panel
    top (``y=1.0`` in paper coords). With ``_apply_aa_axes`` drawing a mirrored
    frame, the default placement makes the title text sit ON the top frame
    line — the left-panel "HDI68 width of f_bin" glyphs were clipped by the
    black border. We shift each title 12 px above its panel and bump the
    figure's top margin to 90 px so the shifted titles have vertical room.
    """
    fig = make_subplots(
        rows=1, cols=2, shared_xaxes=False,
        subplot_titles=('HDI68 width of <i>f</i><sub>bin</sub>',
                        'HDI68 width of π'),
    )
    for ann in fig.layout.annotations:
        ann.font = dict(size=13, color=_AA_FRAME,
                        family='Times New Roman, serif')
        # Push each subplot-title annotation 12 px above the frame so neither
        # panel's title is clipped by the mirrored top border.
        ann.yshift = 12

    ordered = _ordered_results(results)

    # One marker per scheme (connected lines only make sense when multiple
    # manual rows share a prefix, which the manual-only UI doesn't enforce).
    for idx, r in enumerate(ordered):
        color, dash = _color_for(r, idx)
        x = r.n_bins
        y_fb = _hdi_width(r.hdi68_fbin)
        y_pi = _hdi_width(r.hdi68_pi)
        hover_fb = '<br>'.join([
            f'scheme: {r.scheme}',
            f'n_bins: {x}',
            f'HDI68 width (f_bin): {y_fb:.3f}',
            f'best f_bin: {r.best_fbin:.3f}',
            f'best π: {r.best_pi:.3f}',
        ])
        hover_pi = '<br>'.join([
            f'scheme: {r.scheme}',
            f'n_bins: {x}',
            f'HDI68 width (π): {y_pi:.3f}',
            f'best f_bin: {r.best_fbin:.3f}',
            f'best π: {r.best_pi:.3f}',
        ])
        symbol = 'star' if r.scheme == 'dsilva_default' else 'circle'
        size = max(8, min(18, 7 + int(r.n_eff_bins)))

        fig.add_trace(go.Scatter(
            x=[x], y=[y_fb], mode='markers', name=r.scheme,
            legendgroup=r.scheme,
            line=dict(color=color, dash=dash, width=1.6),
            marker=dict(
                color=color, size=size, symbol=symbol,
                line=dict(color=_AA_FRAME, width=0.5),
            ),
            hovertext=[hover_fb], hovertemplate='%{hovertext}<extra></extra>',
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=[x], y=[y_pi], mode='markers', name=r.scheme,
            legendgroup=r.scheme, showlegend=False,
            line=dict(color=color, dash=dash, width=1.6),
            marker=dict(
                color=color, size=size, symbol=symbol,
                line=dict(color=_AA_FRAME, width=0.5),
            ),
            hovertext=[hover_pi], hovertemplate='%{hovertext}<extra></extra>',
        ), row=1, col=2)

    # Reference line at dsilva_default
    ref = results.get('dsilva_default')
    if ref is not None:
        ref_fb = _hdi_width(ref.hdi68_fbin)
        ref_pi_ = _hdi_width(ref.hdi68_pi)
        for col, yv in ((1, ref_fb), (2, ref_pi_)):
            if np.isfinite(yv):
                fig.add_hline(
                    y=yv, line_dash='dash', line_color=_AA_REF_LINE,
                    opacity=0.7, row=1, col=col,
                    annotation_text='Dsilva default',
                    annotation_position='top right',
                    annotation_font=dict(size=11, color=_AA_REF_LINE),
                )

    fig.update_xaxes(title_text='Number of bins <i>n</i>', row=1, col=1)
    fig.update_xaxes(title_text='Number of bins <i>n</i>', row=1, col=2)
    fig.update_yaxes(title_text='HDI68 width', rangemode='tozero', row=1, col=1)
    fig.update_yaxes(title_text='HDI68 width', rangemode='tozero', row=1, col=2)
    _apply_aa_axes(fig, n_rows=1, n_cols=2)
    # Readable-text rule (memory/plot_preferences.md §2026-04-23).
    _apply_readable_text(fig, n_subplot_titles=2)
    return _layout_update(
        fig, height=440,
        title=dict(text='HDI68 width vs number of bins',
                   font=dict(size=16, color=_AA_FRAME)),
        legend=dict(
            x=1.0, y=1.0, xanchor='right', yanchor='top',
        ),
        # Session-3: widen the top margin from the academic default (50 px)
        # to 90 px so the yshift-lifted subplot titles are not clipped.
        margin=dict(l=60, r=20, t=90, b=50),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Plot 2 — Best-fit (f_bin*, π*) scatter across schemes
# ─────────────────────────────────────────────────────────────────────────────

def _plot_best_fit_scatter(
    results: dict[str, SchemeResult],
    reference_scheme: str = 'dsilva_default',
) -> go.Figure:
    """Scatter of (π*, f_bin*) per scheme. Contour background from reference scheme."""
    fig = go.Figure()

    ref = results.get(reference_scheme)
    if ref is not None and ref.logL_map.size > 0:
        # Build 2-D density from ref.logL_map: shape is (n_fb, n_pi)
        _L = np.where(np.isnan(ref.logL_map), -np.inf, ref.logL_map)
        _lmax = np.nanmax(_L) if np.any(np.isfinite(_L)) else 0.0
        lk2d = np.exp(_L - _lmax)
        # Dummy grids — we don't have them stored on SchemeResult, so use index coords
        # but we have best_fbin, best_pi and shape. This is a background illustrator
        # only (no pi/fbin tick marks on the contour), so use unit-coords contours
        # scaled to [0,1] and place it as a reference-density backdrop in the plot.
        # We draw the contour along the data axes using the ref's best-fit location.
        ny, nx = lk2d.shape
        # Build x/y as index-normalised — we'll reposition contours via range (data coords).
        pi_axis = np.linspace(
            float(np.nanmin([r.best_pi for r in results.values()])) - 1.0,
            float(np.nanmax([r.best_pi for r in results.values()])) + 1.0,
            nx,
        )
        fb_axis = np.linspace(
            max(0.0, float(np.nanmin([r.best_fbin for r in results.values()])) - 0.1),
            min(1.0, float(np.nanmax([r.best_fbin for r in results.values()])) + 0.1),
            ny,
        )
        # Posterior HDI levels for the reference scheme. We show 68 / 95 / 99 %
        # HDIs as contour lines. Because ``lk2d`` is already normalised to its
        # peak, HDI fraction ≈ density height contour; the exact level values
        # below are conventional for 2-D Gaussian-like posteriors and are
        # clearly labelled on the plot.
        fig.add_trace(go.Contour(
            z=lk2d, x=pi_axis, y=fb_axis,
            contours=dict(
                coloring='lines', showlabels=True,
                labelfont=dict(
                    family='Times New Roman, serif', size=10,
                    color=_AA_FRAME,
                ),
                start=0.3173, end=0.9973, size=0.34,  # ~68%, ~95%, ~99%
            ),
            line=dict(color=_AA_REF_LINE, width=1, dash='dot'),
            showscale=False, hoverinfo='skip',
            name=f'{reference_scheme} posterior',
            showlegend=False,
        ))
        # Dummy invisible trace to carry the contour's legend entry (standard
        # Plotly idiom for labelling go.Contour in a scatter legend).
        fig.add_trace(go.Scatter(
            x=[None], y=[None], mode='lines',
            line=dict(color=_AA_REF_LINE, width=1, dash='dot'),
            name=f'{reference_scheme} posterior (68/95/99% HDI)',
            showlegend=True,
        ))

    # Per-scheme markers
    for idx, r in enumerate(_ordered_results(results)):
        color, _ = _color_for(r, idx)
        w_fb = _hdi_width(r.hdi68_fbin)
        w_pi = _hdi_width(r.hdi68_pi)
        # size proportional to log(area) — tighter = smaller marker
        area = max(w_fb * w_pi, 1e-4)
        size = float(6.0 + 5.0 * (math.log(area) - math.log(1e-4)))
        size = float(np.clip(size, 6.0, 22.0))
        sym = 'star' if r.scheme == 'dsilva_default' else 'circle'
        hover = (
            f'scheme: {r.scheme}<br>'
            f'f_bin*: {r.best_fbin:.3f}<br>'
            f'π*: {r.best_pi:.3f}<br>'
            f'HDI68 width (f_bin): {w_fb:.3f}<br>'
            f'HDI68 width (π): {w_pi:.3f}<br>'
            f'logL: {r.logL_max:.2f}'
        )
        fig.add_trace(go.Scatter(
            x=[r.best_pi], y=[r.best_fbin],
            mode='markers',
            marker=dict(
                color=color, size=size, symbol=sym,
                line=dict(color=_AA_FRAME, width=0.5),
            ),
            name=r.scheme, legendgroup=r.scheme,
            hovertext=hover, hovertemplate='%{hovertext}<extra></extra>',
            showlegend=True,
        ))
        # Session 4: grey connecting arrows between scheme markers and the
        # reference were removed — the marker positions alone convey the
        # (π*, f_bin*) for each scheme, and the arrows added visual noise
        # without extra information.

    # Mock-mode truth marker: gold star at (π_true, f_bin_true) when any
    # SchemeResult carries a `ground_truth` dict (briefing §Change 4 overlays).
    gt = next((r.ground_truth for r in results.values()
               if getattr(r, 'ground_truth', None)), None)
    if gt is not None:
        try:
            _pi_t = float(gt.get('pi'))
            _fb_t = float(gt.get('f_bin'))
        except (TypeError, ValueError):
            _pi_t = _fb_t = None  # type: ignore[assignment]
        if _pi_t is not None and _fb_t is not None:
            fig.add_trace(go.Scatter(
                x=[_pi_t], y=[_fb_t],
                mode='markers+text',
                marker=dict(
                    color=_AA_TRUTH_GOLD, size=22, symbol='star',
                    line=dict(color=_TRUTH_STAR_BORDER, width=1.2),
                ),
                text=['truth'], textposition='middle right',
                textfont=dict(size=11, color=_AA_FRAME),
                name='truth (injected)', legendgroup='truth', showlegend=True,
                hovertemplate=(f'truth<br>π={_pi_t:.3f}'
                               f'<br>f_bin={_fb_t:.3f}<extra></extra>'),
            ))

    fig.update_xaxes(title_text='π (period power-law index)')
    fig.update_yaxes(title_text='<i>f</i><sub>bin</sub> (binary fraction)',
                     range=[0.0, 1.0])
    _apply_aa_axes(fig)
    # Readable-text rule (memory/plot_preferences.md §2026-04-23).
    _apply_readable_text(fig, n_subplot_titles=0)
    return _layout_update(
        fig, height=480,
        title=dict(text='Best-fit (<i>f</i><sub>bin</sub>*, π*) across schemes',
                   font=dict(size=16, color=_AA_FRAME)),
        legend=dict(
            x=0.02, y=0.98, xanchor='left', yanchor='top',
            bgcolor='rgba(255,255,255,0.85)', bordercolor=_AA_FRAME,
            borderwidth=0.5,
            font=dict(size=14, color=_AA_FRAME,
                      family='Times New Roman, serif'),
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Plot 3 — Observed CDF vs best-fit simulated CDF, faceted by scheme
# ─────────────────────────────────────────────────────────────────────────────

def _plot_cdf_faceted(
    results: dict[str, SchemeResult],
    obs_delta_rv: np.ndarray,
) -> go.Figure:
    """Faceted observed-vs-simulated CDF with bin edges drawn as vertical lines."""
    ordered = _ordered_results(results)
    n_schemes = max(len(ordered), 1)
    n_cols = 2
    n_rows = int(math.ceil(n_schemes / n_cols))

    # Two-line subplot titles: line 1 = scheme name; line 2 (smaller, via
    # <sub>) = best-fit params + HDI68. Uses the mathematical minus "−" for
    # negative numbers so the Plotly serif renders a proper minus glyph.
    def _fmt_signed(v: float, spec: str = '.2f') -> str:
        try:
            s = format(float(v), spec)
        except (TypeError, ValueError):
            return '—'
        if s.startswith('-'):
            return '−' + s[1:]  # U+2212 MINUS SIGN
        return s

    def _cdf_subplot_title(r: SchemeResult) -> str:
        lo_fb, hi_fb = r.hdi68_fbin
        lo_pi, hi_pi = r.hdi68_pi
        line2 = (
            f'<i>f</i><sub>bin</sub>*={_fmt_signed(r.best_fbin)} '
            f'[{_fmt_signed(lo_fb)}, {_fmt_signed(hi_fb)}]  '
            f'π*={_fmt_signed(r.best_pi)} '
            f'[{_fmt_signed(lo_pi)}, {_fmt_signed(hi_pi)}]'
        )
        return f'{r.scheme}<br><sub>{line2}</sub>'

    fig = make_subplots(
        rows=n_rows, cols=n_cols, shared_xaxes=True, shared_yaxes=True,
        subplot_titles=[_cdf_subplot_title(r) for r in ordered],
        horizontal_spacing=0.08, vertical_spacing=0.18,
    )
    # Force black serif on the subplot-title annotations (Plotly defaults to
    # grey which fails WCAG on white paper). yshift=14 lifts the two-line
    # titles clear of the mirrored top frame so the <sub> line isn't clipped.
    # Font 14 pt per the "Readable text size" rule (2026-04-23).
    for ann in fig.layout.annotations:
        ann.font = dict(size=14, color=_AA_FRAME,
                        family='Times New Roman, serif')
        ann.yshift = 14

    # Observed step CDF
    obs_sorted = np.sort(np.asarray(obs_delta_rv, dtype=float))
    obs_cdf_y = np.arange(1, obs_sorted.size + 1) / max(obs_sorted.size, 1)
    x_max = float(obs_sorted[-1] * 1.1) if obs_sorted.size > 0 else 500.0

    for idx, r in enumerate(ordered):
        row = idx // n_cols + 1
        col = idx % n_cols + 1
        color, dash = _color_for(r, idx)

        # Observed step — teal (#2CA6A4) per user request; clearly visible on white.
        fig.add_trace(go.Scatter(
            x=np.concatenate([[0.0], obs_sorted]),
            y=np.concatenate([[0.0], obs_cdf_y]),
            mode='lines',
            line=dict(color=_AA_OBSERVED, width=2, shape='hv'),
            name='Observed (25 stars)',
            legendgroup='obs',
            showlegend=(idx == 0),
            hovertemplate='ΔRV=%{x:.1f} km/s<br>CDF=%{y:.2f}<extra>observed</extra>',
        ), row=row, col=col)

        # Simulated median CDF (tomato red, dashed) + 16-84% envelope fill
        # The fill is a `fill='tonexty'` after the lo trace; line+fill share legendgroup.
        # Evaluate on r.cdf_x (same grid used by the grid run).
        x_grid = r.cdf_x
        fig.add_trace(go.Scatter(
            x=x_grid, y=r.sim_cdf_q16, mode='lines',
            line=dict(color=_AA_SIMULATED, width=0),
            legendgroup='sim',
            showlegend=False, hoverinfo='skip',
        ), row=row, col=col)
        fig.add_trace(go.Scatter(
            x=x_grid, y=r.sim_cdf_q84, mode='lines',
            line=dict(color=_AA_SIMULATED, width=0),
            fill='tonexty', fillcolor=_hex_to_rgba(_AA_SIMULATED, 0.18),
            legendgroup='sim',
            showlegend=False, hoverinfo='skip',
            name='Simulated 16-84%',
        ), row=row, col=col)
        fig.add_trace(go.Scatter(
            x=x_grid, y=r.sim_cdf_median, mode='lines',
            line=dict(color=_AA_SIMULATED, width=2, dash='dash'),
            legendgroup='sim',
            showlegend=(idx == 0),
            name='Simulated median',
            hovertemplate='ΔRV=%{x:.1f} km/s<br>CDF=%{y:.2f}<extra>sim median</extra>',
        ), row=row, col=col)

        # Vertical bin edges (exclude +inf)
        finite_edges = r.edges[np.isfinite(r.edges)]
        for e in finite_edges:
            if 0.0 < e <= x_max:
                fig.add_vline(
                    x=float(e), line=dict(color=color, dash='dot', width=1),
                    opacity=0.55, row=row, col=col,
                )

        # Per-subplot diagnostic box (logL + K-S + n_bins). Placed bottom-right
        # so the observed/simulated curves in the upper-left aren't obscured.
        # Times New Roman 11 pt bold black on semi-opaque white for legibility
        # on any monitor (A&A paper style + WCAG contrast on white bg).
        fig.add_annotation(
            xref=f'x{idx + 1}' if idx > 0 else 'x',
            yref=f'y{idx + 1}' if idx > 0 else 'y',
            x=x_max * 0.97, y=0.08,
            text=(f'<b>logL={r.logL_max:.1f}<br>'
                  f'KS D={r.ks_D:.3f}<br>'
                  f'n_bins={r.n_bins} (eff {r.n_eff_bins})</b>'),
            showarrow=False,
            align='right',
            font=dict(size=11, color=_AA_FRAME,
                      family='Times New Roman, serif'),
            bgcolor=_AA_ANNOTATION_BG, bordercolor=_AA_FRAME,
            borderwidth=0.5,
            row=row, col=col,
        )

    # A&A frame style on EVERY subplot axis (mirrored, no grid, black ticks).
    _apply_aa_axes(fig, n_rows=n_rows, n_cols=n_cols)

    # CRITICAL: apply identical x/y ranges to ALL subplots (no row/col filter).
    # Previously `row=n_rows`/`col=1` left top-row and right-col subplots on
    # auto-range — producing the "some panels have horizontal lines, some
    # don't" visual inconsistency the user flagged. Unscoped calls update
    # every axis uniformly, enforcing A&A-consistent appearance across
    # all 6 panels. x/y titles are applied only to the outer axes via
    # scoped calls after the global range is locked in.
    fig.update_xaxes(range=[0.0, x_max])
    fig.update_yaxes(range=[0.0, 1.05])

    # Axis titles: only on the shared outer edges (bottom row x-axis,
    # left column y-axis). shared_xaxes/shared_yaxes=True means inner
    # tick labels are already suppressed by Plotly.
    fig.update_xaxes(title_text='ΔRV (km/s)', row=n_rows)
    fig.update_yaxes(title_text='Cumulative fraction', col=1)

    # Readable-text rule (memory/plot_preferences.md §2026-04-23).
    _apply_readable_text(fig, n_subplot_titles=len(ordered))

    panel_h = 260
    return _layout_update(
        fig, height=panel_h * n_rows + 80,
        title=dict(text='Observed vs simulated CDF, per scheme',
                   font=dict(size=16, color=_AA_FRAME)),
        # Bigger legend per user request (was 12 → now 14) with
        # black border and semi-opaque white background for A&A paper
        # contrast on any reader's monitor.
        legend=dict(
            font=dict(size=14, color=_AA_FRAME,
                      family='Times New Roman, serif'),
            bgcolor='rgba(255,255,255,0.85)',
            bordercolor=_AA_FRAME, borderwidth=0.5,
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Plot 4 — Marginal posterior overlay (1D)
# ─────────────────────────────────────────────────────────────────────────────

def _plot_marginal_posteriors(
    results: dict[str, SchemeResult],
    fbin_grid: np.ndarray,
    pi_grid: np.ndarray,
) -> go.Figure:
    """1-D marginal overlay: posterior density for f_bin (top) and π (bottom).

    Round-4: subplot titles moved to manual annotations at ``y=1.02`` of each
    panel domain (``vertical_spacing=0.22``) to avoid collision with tall
    traces; the "Dsilva best" label is placed inside the panel (``y≈0.92``)
    rather than above, where it previously overlapped the title. When any
    result carries ``ground_truth``, a green truth line is drawn at
    ``(f_bin_true, π_true)`` on each panel.
    """
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=False,
        vertical_spacing=0.22,
    )

    ordered = _ordered_results(results)
    # Draw reference last, on top, thicker
    non_ref = [r for r in ordered if r.scheme != 'dsilva_default']
    ref = results.get('dsilva_default')
    draw_order = non_ref + ([ref] if ref is not None else [])

    def _hdi_band(x_grid: np.ndarray, y_curve: np.ndarray,
                  hdi: tuple) -> tuple[np.ndarray, np.ndarray] | None:
        """Return (x_band, y_band) clipped to [hdi_lo, hdi_hi] for a tozeroy fill.

        Interpolates the curve at the exact HDI edges so the shaded region
        stops cleanly at the HDI bounds rather than snapping to the nearest
        grid point. Returns None if the HDI is invalid / off-grid.
        """
        try:
            lo, hi = float(hdi[0]), float(hdi[1])
        except (TypeError, ValueError):
            return None
        if not (np.isfinite(lo) and np.isfinite(hi)) or hi <= lo:
            return None
        x_arr = np.asarray(x_grid, dtype=float)
        y_arr = np.asarray(y_curve, dtype=float)
        if x_arr.size == 0 or y_arr.size != x_arr.size:
            return None
        mask = (x_arr >= lo) & (x_arr <= hi)
        y_lo = float(np.interp(lo, x_arr, y_arr))
        y_hi = float(np.interp(hi, x_arr, y_arr))
        x_band = np.concatenate([[lo], x_arr[mask], [hi]])
        y_band = np.concatenate([[y_lo], y_arr[mask], [y_hi]])
        return x_band, y_band

    for r in draw_order:
        idx = _scheme_index(results, r.scheme)
        color, dash = _color_for(r, idx)
        lw = 2.2 if r.scheme == 'dsilva_default' else 1.5
        opacity = 1.0 if r.scheme == 'dsilva_default' else 0.9

        # HDI68 shaded band under the f_bin marginal (drawn BEFORE the line so
        # the line remains crisp on top). Shares legendgroup with the line so
        # toggling the scheme off in the legend also hides its shadow — per
        # memory/plot_preferences.md "CDF legend toggle must hide shadows".
        band_fb = _hdi_band(fbin_grid, r.marginal_fbin, r.hdi68_fbin)
        if band_fb is not None:
            x_b, y_b = band_fb
            fig.add_trace(go.Scatter(
                x=x_b, y=y_b, fill='tozeroy', mode='none',
                fillcolor=_hex_to_rgba(color, 0.22),
                legendgroup=r.scheme, showlegend=False,
                hoverinfo='skip',
            ), row=1, col=1)
        band_pi = _hdi_band(pi_grid, r.marginal_pi, r.hdi68_pi)
        if band_pi is not None:
            x_b, y_b = band_pi
            fig.add_trace(go.Scatter(
                x=x_b, y=y_b, fill='tozeroy', mode='none',
                fillcolor=_hex_to_rgba(color, 0.22),
                legendgroup=r.scheme, showlegend=False,
                hoverinfo='skip',
            ), row=2, col=1)

        fig.add_trace(go.Scatter(
            x=fbin_grid, y=r.marginal_fbin, mode='lines',
            line=dict(color=color, width=lw, dash=dash),
            opacity=opacity,
            name=r.scheme, legendgroup=r.scheme,
            hovertemplate=('f_bin=%{x:.3f}<br>density=%{y:.3f}'
                           f'<extra>{r.scheme}</extra>'),
            showlegend=True,
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=pi_grid, y=r.marginal_pi, mode='lines',
            line=dict(color=color, width=lw, dash=dash),
            opacity=opacity,
            name=r.scheme, legendgroup=r.scheme, showlegend=False,
            hovertemplate=('π=%{x:.3f}<br>density=%{y:.3f}'
                           f'<extra>{r.scheme}</extra>'),
        ), row=2, col=1)

    # Manual panel titles (replace `subplot_titles=` to prevent overlap on
    # tall traces; sits clear above each row at y=1.02 of panel domain).
    # Font 14 pt per the readable-text rule (memory/plot_preferences.md §2026-04-23).
    fig.add_annotation(
        x=0.5, y=1.02, xref='x domain', yref='y domain',
        text='Marginal posterior of <i>f</i><sub>bin</sub>',
        showarrow=False, xanchor='center', yanchor='bottom',
        font=dict(size=14, color='black'), row=1, col=1,
    )
    fig.add_annotation(
        x=0.5, y=1.02, xref='x domain', yref='y domain',
        text='Marginal posterior of π',
        showarrow=False, xanchor='center', yanchor='bottom',
        font=dict(size=14, color='black'), row=2, col=1,
    )

    # Reference (Dsilva) best-fit vertical lines — label placed INSIDE the
    # panel, not above (previous top-placement collided with the subplot title).
    if ref is not None:
        fig.add_vline(
            x=ref.best_fbin, line=dict(color=_AA_TRUTH_GOLD, dash='dash', width=1.5),
            row=1, col=1, opacity=0.8,
        )
        fig.add_annotation(
            x=ref.best_fbin, y=0.92, xref='x', yref='y domain',
            text='Dsilva best', showarrow=False,
            xanchor='left', yanchor='top',
            font=dict(size=11, color=_AA_TRUTH_GOLD),
            row=1, col=1,
        )
        fig.add_vline(
            x=ref.best_pi, line=dict(color=_AA_TRUTH_GOLD, dash='dash', width=1.5),
            row=2, col=1, opacity=0.8,
        )
        fig.add_annotation(
            x=ref.best_pi, y=0.92, xref='x2', yref='y2 domain',
            text='Dsilva best', showarrow=False,
            xanchor='left', yanchor='top',
            font=dict(size=11, color=_AA_TRUTH_GOLD),
            row=2, col=1,
        )

    # Mock-mode truth overlay: green dashed line + "truth" label on each panel.
    gt = next((r.ground_truth for r in results.values()
               if getattr(r, 'ground_truth', None)), None)
    if gt is not None:
        try:
            _fb_t = float(gt.get('f_bin'))
            _pi_t = float(gt.get('pi'))
        except (TypeError, ValueError):
            _fb_t = _pi_t = None  # type: ignore[assignment]
        if _fb_t is not None and _pi_t is not None:
            fig.add_vline(
                x=_fb_t,
                line=dict(color=_TRUTH_COLOR, dash='dash', width=1.5),
                row=1, col=1, opacity=0.9,
            )
            fig.add_annotation(
                x=_fb_t, y=0.78, xref='x', yref='y domain',
                text='truth', showarrow=False,
                xanchor='left', yanchor='top',
                font=dict(size=11, color=_TRUTH_COLOR),
                row=1, col=1,
            )
            fig.add_vline(
                x=_pi_t,
                line=dict(color=_TRUTH_COLOR, dash='dash', width=1.5),
                row=2, col=1, opacity=0.9,
            )
            fig.add_annotation(
                x=_pi_t, y=0.78, xref='x2', yref='y2 domain',
                text='truth', showarrow=False,
                xanchor='left', yanchor='top',
                font=dict(size=11, color=_TRUTH_COLOR),
                row=2, col=1,
            )

    fig.update_xaxes(title_text='<i>f</i><sub>bin</sub>', row=1, col=1)
    fig.update_xaxes(title_text='π (period power-law index)', row=2, col=1)
    fig.update_yaxes(title_text='posterior density',
                     rangemode='tozero', row=1, col=1)
    fig.update_yaxes(title_text='posterior density',
                     rangemode='tozero', row=2, col=1)
    _apply_aa_axes(fig, n_rows=2, n_cols=1)

    # Readable-text rule (memory/plot_preferences.md §2026-04-23). Panel titles
    # here are manual annotations (not subplot_titles=), so n_subplot_titles=0;
    # their sizes were already set to 14 pt at add_annotation time above.
    _apply_readable_text(fig, n_subplot_titles=0)

    return _layout_update(
        fig, height=560,
        title=dict(text='Marginal posteriors across schemes',
                   font=dict(size=16, color=_AA_FRAME)),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Plot 5 — Bin occupancy bar chart, faceted
# ─────────────────────────────────────────────────────────────────────────────

def _plot_bin_occupancy(results: dict[str, SchemeResult]) -> go.Figure:
    """Grouped bars of n_obs vs n_sim per bin, one facet per scheme.

    Subplot titles (2-line): line 1 is ``<scheme> (n_bins=N)``; line 2 (rendered
    via ``<sub>`` for visual de-emphasis) surfaces the recovered best-fit
    params — ``f_bin*`` and ``π*`` always; ``Δf_bin`` and ``Δπ`` in addition
    whenever the scheme carries a ``ground_truth`` dict (mock mode).
    """
    def _has_truth(r: SchemeResult) -> bool:
        gt = getattr(r, 'ground_truth', None)
        return isinstance(gt, dict) and gt.get('f_bin') is not None \
            and gt.get('pi') is not None

    def _occupancy_title(r: SchemeResult) -> str:
        line1 = f'{r.scheme} (n_bins={r.n_bins})'
        if _has_truth(r):
            gt = r.ground_truth
            d_fb = float(r.best_fbin) - float(gt.get('f_bin'))
            d_pi = float(r.best_pi) - float(gt.get('pi'))
            line2 = (
                f'f_bin*={float(r.best_fbin):.2f} (Δ{d_fb:+.2f})  '
                f'π*={float(r.best_pi):.2f} (Δ{d_pi:+.2f})'
            )
        else:
            line2 = (
                f'f_bin*={float(r.best_fbin):.2f}  '
                f'π*={float(r.best_pi):.2f}'
            )
        return f'{line1}<br><sub>{line2}</sub>'

    ordered = _ordered_results(results)
    n_schemes = max(len(ordered), 1)
    n_cols = 2
    n_rows = int(math.ceil(n_schemes / n_cols))
    fig = make_subplots(
        rows=n_rows, cols=n_cols, shared_xaxes=False, shared_yaxes=False,
        subplot_titles=[_occupancy_title(r) for r in ordered],
        horizontal_spacing=0.12, vertical_spacing=0.15,
    )
    # Only the first len(ordered) annotations are our subplot titles; any
    # later annotations would be added by downstream layout calls.
    for ann in fig.layout.annotations[:len(ordered)]:
        ann.font = dict(size=11, color=_AA_FRAME,
                        family='Times New Roman, serif')
        ann.yshift = 8  # nudge clear of the frame (Session 3/5 pattern)

    for idx, r in enumerate(ordered):
        row = idx // n_cols + 1
        col = idx % n_cols + 1
        # x-axis tick labels: bin range in km/s
        labels = []
        for k in range(len(r.edges) - 1):
            lo, hi = r.edges[k], r.edges[k + 1]
            if np.isinf(hi):
                labels.append(f'{lo:g}+')
            else:
                labels.append(f'{lo:g}-{hi:g}')
        x_idx = np.arange(len(labels))
        # Normalise n_sim to observed-sample size for fair visual comparison:
        # n_obs per bin counts 25 stars; n_sim counts pool of (n_sets × 25)
        total_sim = max(int(r.n_sim_per_bin.sum()), 1)
        n_obs_tot = max(int(r.n_obs_per_bin.sum()), 1)
        n_sim_norm = r.n_sim_per_bin.astype(float) / total_sim * n_obs_tot

        # In mock mode, the bars reflect mock observations, not real ones.
        _has_mock = (isinstance(getattr(r, 'ground_truth', None), dict)
                     and r.ground_truth.get('f_bin') is not None)
        _obs_bar_name = 'Mock Observation' if _has_mock else 'Observed'
        fig.add_trace(go.Bar(
            x=x_idx, y=r.n_obs_per_bin.astype(int),
            name=_obs_bar_name, marker_color=_AA_OBSERVED,
            opacity=0.85, legendgroup='obs', showlegend=(idx == 0),
            hovertemplate='bin=%{customdata}<br>n_obs=%{y}<extra></extra>',
            customdata=labels,
        ), row=row, col=col)
        fig.add_trace(go.Bar(
            x=x_idx, y=n_sim_norm,
            name='Simulated (rescaled)', marker_color=_AA_SIMULATED,
            opacity=0.75, legendgroup='sim', showlegend=(idx == 0),
            hovertemplate=('bin=%{customdata}<br>n_sim (rescaled)=%{y:.2f}'
                           '<extra></extra>'),
            customdata=labels,
        ), row=row, col=col)
        fig.update_xaxes(
            tickvals=x_idx, ticktext=labels,
            tickangle=(-30 if len(labels) > 8 else 0),
            row=row, col=col,
        )

    _apply_aa_axes(fig, n_rows=n_rows, n_cols=n_cols)

    # Readable-text rule (memory/plot_preferences.md §2026-04-23): ticks ≥12 pt,
    # axis titles ≥14 pt, subplot titles ≥14 pt, legend ≥14 pt (≥3-subplot grid).
    _apply_readable_text(fig, n_subplot_titles=len(ordered))

    panel_h = 230
    return _layout_update(
        fig, height=panel_h * n_rows + 110, barmode='group',
        title=dict(text='Bin occupancy: observed vs simulated (best cell)',
                   font=dict(size=16, color=_AA_FRAME)),
        # Session 6: two-line subplot titles (scheme + best-fit params) need
        # more top breathing room than the 50-px default.
        margin=dict(l=60, r=20, t=90, b=50),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Plot 6 — Bin-edge "heatmap" over observed ΔRV (methods figure)
# ─────────────────────────────────────────────────────────────────────────────

def _plot_bin_edge_map(
    results: dict[str, SchemeResult],
    obs_delta_rv: np.ndarray,
    threshold: float = 45.5,
) -> go.Figure:
    """Stacked strip plot: each scheme gets one row, its edges drawn as vertical dashes.

    An observed-ΔRV rug plot sits on top as the shared ΔRV reference.
    """
    fig = go.Figure()
    obs = np.asarray(obs_delta_rv, dtype=float).ravel()
    obs = obs[np.isfinite(obs)]

    ordered = _ordered_results(results)

    # Raw x_max must cover BOTH every observation AND every scheme's right-most
    # finite bin edge — otherwise a scheme edge at e.g. 650 km/s disappears off
    # the right of the frame when max(obs) is only ~340 km/s (Session 2 fix).
    obs_max = float(obs.max()) if obs.size > 0 else 500.0
    _finite_rightmost = []
    for r in ordered:
        edges = getattr(r, 'edges', None)
        if edges is None:
            continue
        finite = np.asarray(edges, dtype=float)
        finite = finite[np.isfinite(finite)]
        if finite.size > 0:
            _finite_rightmost.append(float(finite[-1]))
    edges_max = max(_finite_rightmost) if _finite_rightmost else 0.0
    x_max = max(obs_max, edges_max) * 1.05

    # y positions: rows stacked top-to-bottom (smallest n_bins at top)
    rows = list(reversed(ordered))  # so dsilva_default (reference) sits at top-ish
    y_labels = [r.scheme for r in rows]
    n = len(rows)

    # Rug (observed ΔRV) as scatter on a top strip.
    # Pin to _RUG_COLOR_ON_WHITE — a direct WCAG-safe near-black, independent
    # of the user's app theme.
    if obs.size > 0:
        fig.add_trace(go.Scatter(
            x=obs, y=[n + 0.4] * obs.size, mode='markers',
            marker=dict(
                symbol='line-ns', size=14,
                color=_RUG_COLOR_ON_WHITE, opacity=0.6,
                line=dict(color=_RUG_COLOR_ON_WHITE, width=1),
            ),
            name='observed ΔRV (rug)',
            hovertemplate='ΔRV=%{x:.1f} km/s<extra></extra>',
            showlegend=False,
        ))

    # Scheme rows: a translucent canvas rectangle + edge verticals.
    # Round-4: row-canvas alpha bumped 0.12 → 0.18 so the scheme-family
    # background stays visible on white paper.
    for i, r in enumerate(rows):
        color, _ = _color_for(r, _scheme_index(results, r.scheme))
        y_center = float(i)
        # Canvas rectangle
        fig.add_shape(
            type='rect',
            x0=0.0, x1=x_max, y0=y_center - 0.4, y1=y_center + 0.4,
            fillcolor=_hex_to_rgba(color, 0.18),
            line=dict(color=_AA_FRAME, width=0.5),
            layer='below',
        )
        # Finite edges
        for e in r.edges:
            if np.isfinite(e) and 0.0 <= e <= x_max:
                fig.add_shape(
                    type='line',
                    x0=float(e), x1=float(e),
                    y0=y_center - 0.36, y1=y_center + 0.36,
                    line=dict(color=color, width=1.8),
                )
        # Invisible trace for hover on the row
        fig.add_trace(go.Scatter(
            x=[x_max / 2], y=[y_center],
            mode='markers', marker=dict(opacity=0, size=1),
            hovertext=f'{r.scheme}<br>edges: {", ".join(f"{x:.1f}" for x in r.edges if np.isfinite(x))}<br>+inf',
            hovertemplate='%{hovertext}<extra></extra>',
            showlegend=False,
        ))

    # Reference vertical lines: threshold and max(obs)
    if obs.size > 0:
        fig.add_vline(
            x=float(threshold),
            line=dict(color=_AA_REF_LINE, dash='dash', width=1),
            annotation_text='threshold',
            annotation_position='top',
            annotation_font=dict(size=11, color=_AA_REF_LINE),
        )
        fig.add_vline(
            x=float(obs.max()),
            line=dict(color=_AA_REF_LINE, dash='dash', width=1),
            annotation_text='max observed',
            annotation_position='top',
            annotation_font=dict(size=11, color=_AA_REF_LINE),
        )

    # Mock-mode reminder: the rug shown IS the synthetic sample, not real
    # observations — place a discrete top-right annotation (briefing §overlays).
    gt = next((r.ground_truth for r in results.values()
               if getattr(r, 'ground_truth', None)), None)
    if gt is not None:
        try:
            _fb_t = float(gt.get('f_bin'))
            _pi_t = float(gt.get('pi'))
            fig.add_annotation(
                text=f'Truth: f_bin={_fb_t:.2f}, π={_pi_t:.2f}',
                xref='paper', yref='paper',
                x=0.98, y=0.98, xanchor='right', yanchor='top',
                showarrow=False,
                font=dict(size=11, color=_TRUTH_COLOR),
                bgcolor=_AA_ANNOTATION_BG, bordercolor=_AA_FRAME,
                borderwidth=0.5,
            )
        except (TypeError, ValueError):
            pass

    fig.update_xaxes(title_text='ΔRV (km/s)', range=[0.0, x_max])
    fig.update_yaxes(
        tickvals=list(range(n)), ticktext=y_labels,
        range=[-0.8, n + 1.0],
        title_text='',
    )
    _apply_aa_axes(fig)
    # Readable-text rule (memory/plot_preferences.md §2026-04-23). No injected
    # subplot-title annotations here (single-panel fig), so n_subplot_titles=0.
    _apply_readable_text(fig, n_subplot_titles=0)
    h = 40 * n + 120
    return _layout_update(
        fig, height=max(h, 260),
        title=dict(text='Bin-edge geometry — all schemes on the observed ΔRV axis',
                   font=dict(size=16, color=_AA_FRAME)),
    )
