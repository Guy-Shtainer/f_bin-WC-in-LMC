"""
components/param_panels.py
──────────────────────────
Reusable DMC parameter input panels for model pages.
Each function returns a Dash component tree (declarative, no side effects).
"""
from __future__ import annotations

import os

import dash_mantine_components as dmc
from dash import dcc, html
from dash_iconify import DashIconify


def build_dsilva_params(prefix: str = 'dsilva') -> dmc.Stack:
    """Build the full parameter sidebar for a Dsilva model page."""
    p = prefix
    return dmc.Stack([
        dmc.Accordion(
            value=['grid-params'],
            multiple=True,
            variant='separated',
            children=[
                _grid_params_item(p),
                _sigma_scan_item(p),
                _logPmax_scan_item(p),
                _orbital_params_item(p),
                _run_controls_item(p),
                _load_result_item(p),
            ],
        ),
        _preset_controls(p),
    ], gap='md')


def build_langer_params(prefix: str = 'langer') -> dmc.Stack:
    """Build the parameter sidebar for a Langer model page.
    Differs from Dsilva: no pi axis, σ is the x-axis, has period dist selectors."""
    p = prefix
    return dmc.Stack([
        dmc.Accordion(
            value=['grid-params'],
            multiple=True,
            variant='separated',
            children=[
                _langer_grid_params_item(p),
                _langer_period_item(p),
                _orbital_params_item(p),
                _run_controls_item(p),
                _load_result_item(p),
            ],
        ),
        _preset_controls(p),
    ], gap='md')


def build_cadence_dsilva_params(prefix: str = 'cadence-dsilva') -> dmc.Stack:
    """Cadence-aware Dsilva: same as Dsilva but grid is fbin × pi with cadence matching."""
    p = prefix
    return dmc.Stack([
        dmc.Accordion(
            value=['grid-params'],
            multiple=True,
            variant='separated',
            children=[
                _grid_params_item(p),
                _sigma_scan_item(p),
                _logPmax_scan_item(p),
                _orbital_params_item(p),
                _run_controls_item(p),
                _load_result_item(p),
            ],
        ),
        _preset_controls(p),
    ], gap='md')


def build_cadence_langer_params(prefix: str = 'cadence-langer') -> dmc.Stack:
    """Cadence-aware Langer: same as Langer but with cadence matching."""
    p = prefix
    return dmc.Stack([
        dmc.Accordion(
            value=['grid-params'],
            multiple=True,
            variant='separated',
            children=[
                _langer_grid_params_item(p),
                _langer_period_item(p),
                _orbital_params_item(p),
                _run_controls_item(p),
                _load_result_item(p),
            ],
        ),
        _preset_controls(p),
    ], gap='md')


# ── Grid Parameters ──────────────────────────────────────────────────────────

def _grid_params_item(p: str) -> dmc.AccordionItem:
    return dmc.AccordionItem(value='grid-params', children=[
        dmc.AccordionControl('Grid Parameters',
            icon=DashIconify(icon='tabler:grid-dots', width=18)),
        dmc.AccordionPanel(dmc.Stack([
            dmc.Text('f_bin range', fw=500, size='sm'),
            dmc.Group([
                dmc.NumberInput(id=f'{p}-fbin-min', label='Min', value=0.01,
                                min=0.0, max=0.5, step=0.01, decimalScale=2, w=100),
                dmc.NumberInput(id=f'{p}-fbin-max', label='Max', value=0.99,
                                min=0.5, max=1.0, step=0.01, decimalScale=2, w=100),
                dmc.NumberInput(id=f'{p}-fbin-steps', label='Steps', value=99,
                                min=10, max=500, step=1, w=90),
            ], gap='xs'),
            dmc.Text('π range (period power-law)', fw=500, size='sm'),
            dmc.Group([
                dmc.NumberInput(id=f'{p}-pi-min', label='Min', value=-3.0,
                                min=-5.0, max=0.0, step=0.1, decimalScale=1, w=100),
                dmc.NumberInput(id=f'{p}-pi-max', label='Max', value=3.0,
                                min=0.0, max=5.0, step=0.1, decimalScale=1, w=100),
                dmc.NumberInput(id=f'{p}-pi-steps', label='Steps', value=100,
                                min=10, max=500, step=1, w=90),
            ], gap='xs'),
            dmc.NumberInput(id=f'{p}-n-stars', label='N stars (per grid point)',
                            value=1000, min=100, max=50000, step=100),
            # Hidden dummies for Langer-only IDs (keep callback signatures consistent)
            html.Div(style={'display': 'none'}, children=[
                dmc.Select(id=f'{p}-dist-A', data=[], value='gaussian'),
                dmc.Select(id=f'{p}-dist-B', data=[], value='lognormal'),
            ]),
        ], gap='sm')),
    ])


# ── Langer Grid Parameters ────────────────────────────────────────────────────

def _langer_grid_params_item(p: str) -> dmc.AccordionItem:
    """Langer grid: f_bin × σ (no π axis)."""
    return dmc.AccordionItem(value='grid-params', children=[
        dmc.AccordionControl('Grid Parameters',
            icon=DashIconify(icon='tabler:grid-dots', width=18)),
        dmc.AccordionPanel(dmc.Stack([
            dmc.Text('f_bin range', fw=500, size='sm'),
            dmc.Group([
                dmc.NumberInput(id=f'{p}-fbin-min', label='Min', value=0.01,
                                min=0.0, max=0.5, step=0.01, decimalScale=2, w=100),
                dmc.NumberInput(id=f'{p}-fbin-max', label='Max', value=1.0,
                                min=0.5, max=1.0, step=0.01, decimalScale=2, w=100),
                dmc.NumberInput(id=f'{p}-fbin-steps', label='Steps', value=99,
                                min=10, max=500, step=1, w=90),
            ], gap='xs'),
            dmc.Text('σ_single range (km/s)', fw=500, size='sm'),
            dmc.Group([
                dmc.NumberInput(id=f'{p}-sigma-min', label='Min', value=3.0,
                                min=0.1, max=500.0, step=0.1, decimalScale=1, w=100),
                dmc.NumberInput(id=f'{p}-sigma-max', label='Max', value=13.0,
                                min=0.5, max=500.0, step=0.1, decimalScale=1, w=100),
                dmc.NumberInput(id=f'{p}-sigma-steps', label='Steps', value=100,
                                min=2, max=500, step=1, w=90),
            ], gap='xs'),
            dmc.NumberInput(id=f'{p}-n-stars', label='N stars (per grid point)',
                            value=1000, min=100, max=50000, step=100),
            # Hidden dummy inputs to keep callback signatures consistent.
            # Must use same component TYPES as Dsilva so callbacks get right property types.
            html.Div(style={'display': 'none'}, children=[
                dmc.NumberInput(id=f'{p}-pi-min', value=-3.0),
                dmc.NumberInput(id=f'{p}-pi-max', value=3.0),
                dmc.NumberInput(id=f'{p}-pi-steps', value=1),
                dmc.Switch(id=f'{p}-scan-sigma', checked=True),
                dmc.NumberInput(id=f'{p}-sigma-single', value=6.0),
                dmc.Switch(id=f'{p}-scan-logpmax', checked=False),
                dmc.NumberInput(id=f'{p}-logpmax-scan-min', value=1.0),
                dmc.NumberInput(id=f'{p}-logpmax-scan-max', value=6.0),
                dmc.NumberInput(id=f'{p}-logpmax-scan-steps', value=15),
                # Hidden containers for UI toggle callbacks
                html.Div(id=f'{p}-sigma-single-container'),
                html.Div(id=f'{p}-sigma-range-container'),
                html.Div(id=f'{p}-logpmax-range-container'),
                html.Div(id=f'{p}-emax-container'),
                html.Div(id=f'{p}-mass-fixed-container'),
                html.Div(id=f'{p}-mass-range-container'),
                html.Div(id=f'{p}-q-langer-container'),
            ]),
        ], gap='sm')),
    ])


# ── Langer Period Distribution ───────────────────────────────────────────────

def _langer_period_item(p: str) -> dmc.AccordionItem:
    """Langer-specific: Case A/B period distribution parameters."""
    return dmc.AccordionItem(value='period-dist', children=[
        dmc.AccordionControl('Period Distribution (Langer)',
            icon=DashIconify(icon='tabler:chart-bell-curve-2', width=18)),
        dmc.AccordionPanel(dmc.Stack([
            dmc.Select(id=f'{p}-dist-A', label='Comp. 1 distribution',
                       data=[{'value': 'gaussian', 'label': 'Gaussian'},
                             {'value': 'lognormal', 'label': 'Log-Normal'},
                             {'value': 'flat', 'label': 'Flat'},
                             {'value': 'empirical', 'label': 'Empirical'}],
                       value='gaussian'),
            dmc.Text('Case A (short-period)', fw=500, size='sm'),
            dmc.Group([
                dmc.NumberInput(id=f'{p}-mu-A', label='μ_A (logP)', value=1.0,
                                min=0.0, max=5.0, step=0.05, decimalScale=2, w=130),
                dmc.NumberInput(id=f'{p}-sigma-A', label='σ_A', value=0.12,
                                min=0.01, max=2.0, step=0.01, decimalScale=2, w=130),
            ], gap='xs'),
            dmc.Select(id=f'{p}-dist-B', label='Comp. 2 distribution',
                       data=[{'value': 'lognormal', 'label': 'Log-Normal'},
                             {'value': 'gaussian', 'label': 'Gaussian'},
                             {'value': 'reflected_lognormal', 'label': 'Reflected Log-Normal'},
                             {'value': 'flat', 'label': 'Flat'}],
                       value='lognormal'),
            dmc.Text('Case B (long-period)', fw=500, size='sm'),
            dmc.Group([
                dmc.NumberInput(id=f'{p}-mu-B', label='μ_B (logP mode)', value=2.1,
                                min=0.0, max=5.0, step=0.05, decimalScale=2, w=130),
                dmc.NumberInput(id=f'{p}-sigma-B', label='σ_B', value=0.2,
                                min=0.01, max=2.0, step=0.01, decimalScale=2, w=130),
            ], gap='xs'),
            dmc.NumberInput(id=f'{p}-weight-A', label='Weight A (fraction Case A)',
                            value=0.08, min=0.0, max=1.0, step=0.01, decimalScale=2),
            dmc.Group([
                dmc.Button('Case A only', id=f'{p}-preset-caseA', variant='light', size='xs'),
                dmc.Button('Case B only', id=f'{p}-preset-caseB', variant='light', size='xs'),
                dmc.Button('Both (Langer)', id=f'{p}-preset-both', variant='light', size='xs'),
            ], gap='xs'),
            dmc.Select(id=f'{p}-q-preset', label='q distribution preset',
                       data=[
                           {'value': 'flat', 'label': 'Flat'},
                           {'value': 'langer_flat', 'label': 'Langer (flat, wide)'},
                           {'value': 'langer', 'label': 'Langer (Gaussian)'},
                       ],
                       value='langer_flat'),
        ], gap='sm')),
    ])


# ── Sigma Scan ───────────────────────────────────────────────────────────────

def _sigma_scan_item(p: str) -> dmc.AccordionItem:
    return dmc.AccordionItem(value='sigma-scan', children=[
        dmc.AccordionControl('σ_single Scan',
            icon=DashIconify(icon='tabler:wave-sine', width=18)),
        dmc.AccordionPanel(dmc.Stack([
            dmc.Switch(id=f'{p}-scan-sigma', label='Enable σ scan', checked=False),
            # Single value (shown when scan OFF)
            html.Div(id=f'{p}-sigma-single-container', children=[
                dmc.NumberInput(id=f'{p}-sigma-single', label='σ_single (km/s)',
                                value=6.0, min=0.1, max=500.0, step=0.1, decimalScale=1),
            ]),
            # Range (shown when scan ON)
            html.Div(id=f'{p}-sigma-range-container', style={'display': 'none'}, children=[
                dmc.Group([
                    dmc.NumberInput(id=f'{p}-sigma-min', label='Min', value=3.0,
                                    min=0.1, max=500.0, step=0.1, decimalScale=1, w=100),
                    dmc.NumberInput(id=f'{p}-sigma-max', label='Max', value=13.0,
                                    min=0.5, max=500.0, step=0.1, decimalScale=1, w=100),
                    dmc.NumberInput(id=f'{p}-sigma-steps', label='Steps', value=50,
                                    min=2, max=500, step=1, w=90),
                ], gap='xs'),
            ]),
        ], gap='sm')),
    ])


# ── logP_max Scan ────────────────────────────────────────────────────────────

def _logPmax_scan_item(p: str) -> dmc.AccordionItem:
    return dmc.AccordionItem(value='logpmax-scan', children=[
        dmc.AccordionControl('logP_max Scan',
            icon=DashIconify(icon='tabler:clock-search', width=18)),
        dmc.AccordionPanel(dmc.Stack([
            dmc.Switch(id=f'{p}-scan-logpmax', label='Enable logP_max scan', checked=False),
            html.Div(id=f'{p}-logpmax-range-container', style={'display': 'none'}, children=[
                dmc.Group([
                    dmc.NumberInput(id=f'{p}-logpmax-scan-min', label='Min', value=1.0,
                                    min=0.5, max=10.0, step=0.1, decimalScale=1, w=100),
                    dmc.NumberInput(id=f'{p}-logpmax-scan-max', label='Max', value=6.0,
                                    min=1.0, max=10.0, step=0.1, decimalScale=1, w=100),
                    dmc.NumberInput(id=f'{p}-logpmax-scan-steps', label='Steps', value=15,
                                    min=3, max=100, step=1, w=90),
                ], gap='xs'),
            ]),
        ], gap='sm')),
    ])


# ── Orbital Parameters ───────────────────────────────────────────────────────

def _orbital_params_item(p: str) -> dmc.AccordionItem:
    return dmc.AccordionItem(value='orbital', children=[
        dmc.AccordionControl('Orbital Parameters',
            icon=DashIconify(icon='tabler:planet', width=18)),
        dmc.AccordionPanel(dmc.Stack([
            dmc.Group([
                dmc.NumberInput(id=f'{p}-logp-min', label='logP min', value=0.15,
                                min=0.01, max=10.0, step=0.01, decimalScale=2, w=130),
                dmc.NumberInput(id=f'{p}-logp-max', label='logP max', value=4.0,
                                min=0.1, max=10.0, step=0.1, decimalScale=1, w=130),
            ], gap='xs'),
            dmc.Select(id=f'{p}-e-model', label='Eccentricity model',
                       data=[{'value': 'flat', 'label': 'Flat (0 to e_max)'},
                             {'value': 'zero', 'label': 'Zero (circular)'}],
                       value='flat'),
            html.Div(id=f'{p}-emax-container', children=[
                dmc.NumberInput(id=f'{p}-e-max', label='e_max', value=0.9,
                                min=0.0, max=0.99, step=0.05, decimalScale=2),
            ]),
            dmc.Select(id=f'{p}-mass-model', label='Primary mass model',
                       data=[{'value': 'fixed', 'label': 'Fixed'},
                             {'value': 'uniform', 'label': 'Uniform'}],
                       value='fixed'),
            html.Div(id=f'{p}-mass-fixed-container', children=[
                dmc.NumberInput(id=f'{p}-mass-fixed', label='M₁ (M☉)', value=10.0,
                                min=1.0, max=200.0, step=1.0, decimalScale=0),
            ]),
            html.Div(id=f'{p}-mass-range-container', style={'display': 'none'}, children=[
                dmc.Group([
                    dmc.NumberInput(id=f'{p}-mass-min', label='M₁ min', value=10.0,
                                    min=1.0, max=200.0, step=1.0, w=130),
                    dmc.NumberInput(id=f'{p}-mass-max', label='M₁ max', value=20.0,
                                    min=1.0, max=200.0, step=1.0, w=130),
                ], gap='xs'),
            ]),
            dmc.Select(id=f'{p}-q-model', label='Mass ratio (q) model',
                       data=[{'value': 'flat', 'label': 'Flat'},
                             {'value': 'langer', 'label': 'Gaussian (Langer)'}],
                       value='flat'),
            dmc.Group([
                dmc.NumberInput(id=f'{p}-q-min', label='q min', value=0.1,
                                min=0.01, max=10.0, step=0.01, decimalScale=2, w=130),
                dmc.NumberInput(id=f'{p}-q-max', label='q max', value=2.0,
                                min=0.01, max=10.0, step=0.1, decimalScale=1, w=130),
            ], gap='xs'),
            dmc.Switch(id=f'{p}-q-flipped',
                       label='Flip q (M\u2082 = M\u2081/q instead of M\u2081\u00b7q)',
                       checked=False),
            html.Div(id=f'{p}-q-langer-container', style={'display': 'none'}, children=[
                dmc.Group([
                    dmc.NumberInput(id=f'{p}-langer-q-mu', label='μ_q', value=0.7,
                                    min=0.01, max=5.0, step=0.05, decimalScale=2, w=130),
                    dmc.NumberInput(id=f'{p}-langer-q-sigma', label='σ_q', value=0.2,
                                    min=0.01, max=5.0, step=0.05, decimalScale=2, w=130),
                ], gap='xs'),
            ]),
        ], gap='sm')),
    ])


# ── Run Controls ─────────────────────────────────────────────────────────────

def _run_controls_item(p: str) -> dmc.AccordionItem:
    n_cpu = os.cpu_count() or 4
    return dmc.AccordionItem(value='run', children=[
        dmc.AccordionControl('Run Simulation',
            icon=DashIconify(icon='tabler:player-play', width=18)),
        dmc.AccordionPanel(dmc.Stack([
            dmc.SegmentedControl(id=f'{p}-view-mode',
                data=['K-S p-value', 'K-S D-statistic'], value='K-S p-value'),
            dmc.NumberInput(id=f'{p}-n-sets-cvm', label='CvM variance sets',
                            value=1000, min=100, max=50000, step=100),
            dmc.NumberInput(id=f'{p}-n-proc', label='Workers',
                            value=max(1, n_cpu - 1), min=1, max=n_cpu - 1, step=1),
            dmc.Group([
                dmc.Button('Run', id=f'{p}-run-btn', color='blue',
                           leftSection=DashIconify(icon='tabler:player-play', width=16)),
                dmc.Button('Cancel', id=f'{p}-cancel-btn', color='red',
                           variant='outline', display='none',
                           leftSection=DashIconify(icon='tabler:player-stop', width=16)),
            ], gap='sm'),
            dmc.Progress(id=f'{p}-progress', value=0, size='lg',
                         striped=True, animated=False),
            dmc.Text(id=f'{p}-progress-text', size='sm', c='dimmed'),
        ], gap='sm')),
    ])


# ── Load Saved Result ────────────────────────────────────────────────────────

def _load_result_item(p: str) -> dmc.AccordionItem:
    return dmc.AccordionItem(value='load-result', children=[
        dmc.AccordionControl('Load Saved Result',
            icon=DashIconify(icon='tabler:folder-open', width=18)),
        dmc.AccordionPanel(dmc.Stack([
            dmc.Select(id=f'{p}-result-select', label='Select result file',
                       data=[], placeholder='No saved results', searchable=True),
            dmc.Group([
                dmc.Button('Load', id=f'{p}-load-btn', variant='light',
                           leftSection=DashIconify(icon='tabler:download', width=16)),
                dmc.Button('Refresh', id=f'{p}-refresh-results-btn', variant='subtle',
                           leftSection=DashIconify(icon='tabler:refresh', width=16)),
            ], gap='sm'),
        ], gap='sm')),
    ])


# ── Preset Controls ──────────────────────────────────────────────────────────

def _preset_controls(p: str) -> dmc.Paper:
    return dmc.Paper(
        dmc.Stack([
            dmc.Text('Presets', fw=600, size='sm'),
            dmc.Group([
                dmc.TextInput(id=f'{p}-preset-name', placeholder='Preset name',
                              size='sm', style={'flex': 1}),
                dmc.Button('Save', id=f'{p}-save-preset-btn', size='sm',
                           variant='light', color='green'),
            ], gap='xs'),
            dmc.Select(id=f'{p}-preset-select', label='Load preset',
                       data=[], placeholder='No presets saved', size='sm'),
        ], gap='xs'),
        shadow='sm', p='md', radius='md', withBorder=True,
    )
