"""
components/scoring_tabs.py
──────────────────────────
Nested DMC Tabs for the 5 scoring methods: Simulation + 4 statistical methods.
This is the component that was impossible in Streamlit (no nested tabs).
"""
from __future__ import annotations

import dash_mantine_components as dmc
from dash import dcc, html
from dash_iconify import DashIconify


_METHODOLOGY_MD = r'''
### Simulation Overview

For each grid point (f_bin, $\pi$, $\sigma_{\rm single}$):

1. **Draw N systems** — each is binary with probability f_bin, or single
   with probability 1 − f_bin
2. **Single stars:** RV ~ N(0, $\sigma_{\rm total}^{2}$) where
   $\sigma_{\rm total} = \sqrt{\sigma_{\rm single}^{2} + \sigma_{\rm measure}^{2}}$.
   $\Delta$RV = max(v) − min(v)
3. **Binary stars:** sample orbital parameters:
   - Period P from power-law $p(\log P) \propto (\log P)^{\pi}$
   - Eccentricity $e \sim U[0, e_{\max}]$
   - Mass ratio $q = M_2 / M_1$
   - Inclination from $\sin(i)$ distribution
4. **RV semi-amplitude:**
   $K_1 = \frac{(2\pi G / P)^{1/3}\, M_2 \sin i}{(M_1+M_2)^{2/3}\,\sqrt{1-e^{2}}}$
5. **Solve Kepler's equation** $E - e\sin E = M$ via Newton-Raphson
6. **Radial velocity:** $v(t) = K_1[\cos(\omega+\nu) + e\cos\omega]$
7. **Compare** simulated vs observed $\Delta$RV distribution using K-S test

### Scoring Methods

- **K-S test:** $D = \max|F_{\rm obs}(x) - F_{\rm sim}(x)|$. Higher
  p-value → better match.
- **K-S weighted:** Variance-weighted $\chi^{2}$ distance.
- **CvM:** Cramér-von Mises integrated squared difference.
- **Likelihood:** Multinomial log-likelihood over binned $\Delta$RV histogram.

### Binary Detection Criteria (both required)
- $\Delta$RV > 45.5 km/s
- $\Delta$RV − 4$\sigma$ > 0 (significance)
'''


def build_scoring_tabs(prefix: str) -> dmc.Tabs:
    """Build nested scoring method tabs for a model page.

    Returns a dmc.Tabs component with 5 tabs:
    - Simulation: overview, method summary, CDF comparison
    - K-S: heatmap + best-fit + CDF + corner
    - K-S Weighted: same structure
    - CvM: same structure
    - Likelihood: same structure
    """
    p = prefix
    return dmc.Tabs(
        id=f'{p}-scoring-tabs',
        value='simulation',
        keepMounted=True,  # CRITICAL: preserve inner state when switching tabs
        children=[
            dmc.TabsList([
                dmc.TabsTab('Simulation', value='simulation',
                    leftSection=DashIconify(icon='tabler:chart-area-line', width=16)),
                dmc.TabsTab('K-S', value='ks',
                    leftSection=DashIconify(icon='tabler:chart-dots-2', width=16)),
                dmc.TabsTab('K-S Wt', value='weighted',
                    leftSection=DashIconify(icon='tabler:chart-dots-3', width=16)),
                dmc.TabsTab('CvM', value='cvm',
                    leftSection=DashIconify(icon='tabler:chart-histogram', width=16)),
                dmc.TabsTab('Likelihood', value='likelihood',
                    leftSection=DashIconify(icon='tabler:chart-candle', width=16)),
            ]),
            # Simulation overview tab
            dmc.TabsPanel(value='simulation', children=[
                _simulation_panel(p),
            ]),
            # Per-method tabs
            dmc.TabsPanel(value='ks', children=[
                _method_panel(p, 'ks', 'K-S (standard)'),
            ]),
            dmc.TabsPanel(value='weighted', children=[
                _method_panel(p, 'weighted', 'K-S (weighted)'),
            ]),
            dmc.TabsPanel(value='cvm', children=[
                _method_panel(p, 'cvm', 'CvM (S-score)'),
            ]),
            dmc.TabsPanel(value='likelihood', children=[
                _method_panel(p, 'likelihood', 'Likelihood'),
            ]),
        ],
    )


def _simulation_panel(p: str) -> dmc.Stack:
    """Simulation overview: summary table + CDF + analysis plots."""
    return dmc.Stack([
        # Method summary table (populated by callback)
        html.Div(id=f'{p}-method-summary'),

        # CDF comparison (all methods)
        dcc.Graph(id=f'{p}-sim-cdf', config={'displaylogo': False}),

        # Max p-value vs sigma scan (if sigma was scanned)
        html.Div(id=f'{p}-sigma-scan-chart-container'),

        # Analysis plots in accordion
        dmc.Accordion(
            value=[],
            multiple=True,
            variant='contained',
            children=[
                dmc.AccordionItem(value='period-dist', children=[
                    dmc.AccordionControl('Period Distribution'),
                    dmc.AccordionPanel(dmc.Stack([
                        dmc.SegmentedControl(
                            id=f'{p}-period-norm',
                            data=['Probability density', 'Fraction per bin'],
                            value='Probability density',
                            size='xs',
                        ),
                        dcc.Graph(id=f'{p}-period-dist', config={'displaylogo': False}),
                    ], gap='xs')),
                ]),
                dmc.AccordionItem(value='binary-frac', children=[
                    dmc.AccordionControl('Binary Fraction vs Threshold'),
                    dmc.AccordionPanel(
                        dcc.Graph(id=f'{p}-binary-frac', config={'displaylogo': False})),
                ]),
                dmc.AccordionItem(value='orbital-hist', children=[
                    dmc.AccordionControl('Orbital Histograms'),
                    dmc.AccordionPanel(dmc.Stack([
                        dmc.SegmentedControl(
                            id=f'{p}-orbital-view',
                            data=['Detected vs Missed', 'All binaries',
                                  'Case A vs B'],
                            value='Detected vs Missed',
                            size='xs',
                        ),
                        dcc.Graph(id=f'{p}-orbital-hist', config={'displaylogo': False}),
                    ], gap='xs')),
                ]),
                dmc.AccordionItem(value='methodology', children=[
                    dmc.AccordionControl('Methodology & Equations'),
                    dmc.AccordionPanel(dcc.Markdown(_METHODOLOGY_MD,
                                                    style={'fontSize': '0.85rem'})),
                ]),
            ],
        ),
    ], gap='md', mt='md')


def _method_panel(p: str, method: str, display_name: str) -> dmc.Stack:
    """Per-scoring-method panel: heatmap + best-fit + CDF + corner plot."""
    m = f'{p}-{method}'
    return dmc.Stack([
        # Sigma/logPmax slice selector (if multi-dimensional)
        html.Div(id=f'{m}-slice-controls'),

        # Main heatmap
        dcc.Graph(id=f'{m}-heatmap', config={'displaylogo': False}),

        # Best-fit metrics
        dmc.Paper(
            html.Div(id=f'{m}-best-fit'),
            shadow='sm', p='md', radius='md', withBorder=True,
        ),

        # CDF at best-fit point
        dcc.Graph(id=f'{m}-cdf', config={'displaylogo': False}),

        # D-statistic heatmap, 1D fbin slice, 1D x-axis slice
        dcc.Graph(id=f'{m}-d-heatmap', config={'displaylogo': False}),
        dcc.Graph(id=f'{m}-fbin-slice', config={'displaylogo': False}),
        dcc.Graph(id=f'{m}-x-slice', config={'displaylogo': False}),

        # Collapsible: corner plot + model explorer
        dmc.Accordion(
            value=[],
            multiple=True,
            variant='contained',
            children=[
                dmc.AccordionItem(value='corner', children=[
                    dmc.AccordionControl('Corner Plot'),
                    dmc.AccordionPanel(
                        dcc.Graph(id=f'{m}-corner', config={'displaylogo': False})),
                ]),
                dmc.AccordionItem(value='explorer', children=[
                    dmc.AccordionControl('Model Explorer'),
                    dmc.AccordionPanel(html.Div(id=f'{m}-explorer')),
                ]),
            ],
        ),
    ], gap='md', mt='md')
