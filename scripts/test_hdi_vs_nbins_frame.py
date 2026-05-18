"""Session-3 verification: HDI68-width two-panel plot frame + title fix.

Builds a minimal ``dict[str, SchemeResult]`` fixture with three schemes of
varying ``n_bins``, calls :func:`_plot_hdi_vs_nbins`, and asserts that:

1. Both subplot axes have ``mirror=True`` and ``linecolor='black'`` — the
   left and right panels must have identical mirrored frames.
2. Every subplot-title annotation uses ``font.color='black'`` (WCAG on white).
3. The top margin is >= 80 px so the shifted subplot titles are not clipped.
4. Each subplot-title annotation has a non-zero ``yshift`` lifting it above
   the frame.

Exit 0 on success, non-zero on any failed assertion.
"""
from __future__ import annotations

import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_APP = os.path.join(_ROOT, 'app')
for p in (_APP, _ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from bc.bin_sensitivity_scorer import SchemeResult  # type: ignore
from bc.bin_sensitivity_plots import _plot_hdi_vs_nbins  # type: ignore


def _make_result(scheme: str, n_bins: int,
                 hdi_fb: tuple[float, float],
                 hdi_pi: tuple[float, float]) -> SchemeResult:
    edges = np.linspace(0.0, 500.0, n_bins + 1)
    zeros = np.zeros(n_bins, dtype=float)
    return SchemeResult(
        scheme=scheme,
        family=scheme.split('_')[0],
        edges=edges,
        n_bins=n_bins,
        n_eff_bins=n_bins,
        best_fbin=0.45,
        best_pi=-0.5,
        hdi68_fbin=hdi_fb,
        hdi68_pi=hdi_pi,
        logL_max=-123.4,
        aic=250.0,
        ks_D=0.12,
        ks_p=0.8,
        logL_map=np.zeros((5, 5)),
        marginal_fbin=np.ones(5),
        marginal_pi=np.ones(5),
        sim_cdf_median=np.linspace(0, 1, 10),
        sim_cdf_q16=np.linspace(0, 1, 10),
        sim_cdf_q84=np.linspace(0, 1, 10),
        cdf_x=np.linspace(0, 500, 10),
        n_obs_per_bin=zeros.copy(),
        n_sim_per_bin=zeros.copy(),
        status='OK',
    )


def main() -> int:
    fixture = {
        'dsilva_default': _make_result('dsilva_default', 7,
                                       (0.30, 0.60), (-1.2, 0.2)),
        'equal_width_5': _make_result('equal_width_5', 5,
                                      (0.25, 0.70), (-1.4, 0.3)),
        'equal_width_10': _make_result('equal_width_10', 10,
                                       (0.35, 0.55), (-1.0, 0.1)),
    }

    fig = _plot_hdi_vs_nbins(fixture)

    # ── Assertion 1 — both panel x/y axes have mirrored black frames ─────
    ax_pairs = [
        ('xaxis',  fig.layout.xaxis),
        ('xaxis2', fig.layout.xaxis2),
        ('yaxis',  fig.layout.yaxis),
        ('yaxis2', fig.layout.yaxis2),
    ]
    for name, ax in ax_pairs:
        assert bool(ax.mirror) is True, f'{name}.mirror should be True, got {ax.mirror!r}'
        assert ax.linecolor == 'black', f'{name}.linecolor should be black, got {ax.linecolor!r}'
        assert ax.showline is True, f'{name}.showline should be True, got {ax.showline!r}'

    # ── Assertion 2 — subplot-title annotations are black serif text ─────
    # (fig may have additional hline annotations; only the first two are titles)
    subplot_title_anns = [a for a in fig.layout.annotations
                          if 'HDI68 width' in (a.text or '')]
    assert len(subplot_title_anns) == 2, (
        f'expected 2 subplot-title annotations, got {len(subplot_title_anns)}'
    )
    for ann in subplot_title_anns:
        assert ann.font.color == 'black', (
            f'subplot-title annotation {ann.text!r} font.color should be black, '
            f'got {ann.font.color!r}'
        )
        # ── Assertion 4 — yshift lifts each title above the frame ────────
        assert ann.yshift is not None and ann.yshift > 0, (
            f'subplot-title annotation {ann.text!r} should have yshift>0, '
            f'got {ann.yshift!r}'
        )

    # ── Assertion 3 — top margin accommodates the shifted titles ─────────
    assert fig.layout.margin.t >= 80, (
        f'margin.t should be >= 80, got {fig.layout.margin.t}'
    )

    print('PASS — both panels mirrored, titles black + lifted, top margin',
          fig.layout.margin.t)
    return 0


if __name__ == '__main__':
    sys.exit(main())
