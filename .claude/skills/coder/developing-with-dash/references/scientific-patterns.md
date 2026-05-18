# Scientific Dashboard Patterns for Bias Correction

Patterns specific to the WR binary fraction bias correction project.

## Plotly Heatmap for Grid Results

```python
import plotly.graph_objects as go
import numpy as np

def build_heatmap_figure(scores_2d, fbin_grid, x_grid, x_label='pi',
                         title='K-S p-value', theme=None):
    """Build a Plotly heatmap from a 2D scoring array.

    Args:
        scores_2d: 2D numpy array (fbin x x_param)
        fbin_grid: 1D array of f_bin values
        x_grid: 1D array of x-axis parameter values
        x_label: Label for x-axis (e.g., 'pi', 'sigma')
        title: Plot title
        theme: Dict of Plotly layout overrides
    """
    fig = go.Figure(data=go.Heatmap(
        z=scores_2d,
        x=x_grid,
        y=fbin_grid,
        colorscale='Viridis',
        colorbar=dict(title=title),
        hovertemplate=f'{x_label}: %{{x:.2f}}<br>f_bin: %{{y:.2f}}<br>{title}: %{{z:.4f}}<extra></extra>',
    ))

    # Best-fit marker
    best_idx = np.unravel_index(np.nanargmax(scores_2d), scores_2d.shape)
    fig.add_trace(go.Scatter(
        x=[x_grid[best_idx[1]]],
        y=[fbin_grid[best_idx[0]]],
        mode='markers',
        marker=dict(symbol='star', size=15, color='#DAA520', line=dict(color='black', width=1)),
        name='Best fit',
        hovertemplate=f'Best: {x_label}=%{{x:.2f}}, f_bin=%{{y:.2f}}<extra></extra>',
    ))

    fig.update_layout(
        title=dict(text=title),
        xaxis_title=x_label,
        yaxis_title='f_bin',
        **(theme or {}),
    )
    return fig
```

## CDF Comparison Plot

```python
def build_cdf_figure(obs_delta_rv, sim_delta_rv, method_label='K-S',
                     obs_color='#4A90D9', sim_color='#E25A53', theme=None):
    """Build observed vs simulated CDF comparison."""
    obs_sorted = np.sort(obs_delta_rv)
    sim_sorted = np.sort(sim_delta_rv)
    obs_cdf = np.arange(1, len(obs_sorted) + 1) / len(obs_sorted)
    sim_cdf = np.arange(1, len(sim_sorted) + 1) / len(sim_sorted)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=obs_sorted, y=obs_cdf,
        mode='lines', name='Observed',
        line=dict(color=obs_color, width=2),
    ))
    fig.add_trace(go.Scatter(
        x=sim_sorted, y=sim_cdf,
        mode='lines', name='Simulated (best-fit)',
        line=dict(color=sim_color, width=2, dash='dash'),
    ))
    fig.update_layout(
        title=f'CDF Comparison ({method_label})',
        xaxis_title='Delta RV (km/s)',
        yaxis_title='Cumulative Fraction',
        **(theme or {}),
    )
    return fig
```

## Result Data Flow

### From simulation engine to Dash Store

```python
# In background callback (runs in separate process)
from wr_bias_simulation import run_bias_grid, SimulationConfig, BinaryParameterConfig

@callback(
    Output("result-store", "data"),
    Input("run-btn", "n_clicks"),
    State("params-store", "data"),
    background=True,
    progress=[Output("progress", "value"), Output("progress-text", "children")],
    prevent_initial_call=True,
)
def run_grid(set_progress, n_clicks, params):
    cfg_sim = SimulationConfig(
        n_stars=params['n_stars'],
        sigma_single=params.get('sigma_single', 6.0),
    )
    cfg_bin = BinaryParameterConfig(
        logP_min=params.get('logP_min', 0.15),
        logP_max=params.get('logP_max', 5.0),
        e_model=params.get('e_model', 'flat'),
    )

    result = run_bias_grid(
        fbin_values=np.linspace(params['fbin_min'], params['fbin_max'], params['fbin_steps']),
        pi_values=np.linspace(params['pi_min'], params['pi_max'], params['pi_steps']),
        obs_delta_rv=np.array(params['obs_delta_rv']),
        sim_cfg=cfg_sim,
        bin_cfg=cfg_bin,
    )

    # CRITICAL: Convert all numpy arrays to lists for JSON serialization
    serializable = {}
    for k, v in result.items():
        if isinstance(v, np.ndarray):
            serializable[k] = v.tolist()
        elif isinstance(v, (np.integer, np.floating)):
            serializable[k] = v.item()
        else:
            serializable[k] = v
    return serializable
```

### From Store to Figures

```python
@callback(
    Output("ks-heatmap", "figure"),
    Input("result-store", "data"),
    Input("scoring-tabs", "value"),  # only render when this tab is active
    State("mantine-provider", "forceColorScheme"),
)
def update_ks_heatmap(data, active_tab, color_scheme):
    if data is None or active_tab != "ks":
        raise PreventUpdate

    theme = PLOTLY_THEME_DARK if color_scheme == "dark" else PLOTLY_THEME_LIGHT
    scores = np.array(data['ks_p'])
    fbin_g = np.array(data['fbin_grid'])
    pi_g = np.array(data['pi_grid'])

    return build_heatmap_figure(scores, fbin_g, pi_g, x_label='pi',
                                 title='K-S p-value', theme=theme)
```

## Result Persistence (Save/Load .npz)

Reuse existing functions from `app/bc/file_ops.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from app.bc.file_ops import _build_descriptive_filename, _list_saved_results, _result_path
from app.bc.helpers import _stable_cfg_hash
```

These functions are framework-agnostic (pure Python, no Streamlit imports needed for the core logic).

## Scoring Methods Layout

For each of the 4 scoring methods (K-S, K-S Weighted, CvM, Likelihood), the tab content follows the same structure:

```python
def build_scoring_panel(method_key, prefix):
    """Build a scoring method panel with heatmap + metrics + CDF."""
    return dmc.Stack([
        # Heatmap with sigma/logPmax slider (if multi-dimensional)
        dcc.Graph(id=f"{prefix}-{method_key}-heatmap"),

        # Best-fit metrics
        dmc.Paper([
            dmc.Text(id=f"{prefix}-{method_key}-best-fit", size="sm"),
        ], shadow="sm", p="md", withBorder=True),

        # CDF comparison at best-fit point
        dcc.Graph(id=f"{prefix}-{method_key}-cdf"),

        # Collapsible: Corner plot
        dmc.Accordion([
            dmc.AccordionItem(value="corner", children=[
                dmc.AccordionControl("Corner Plot"),
                dmc.AccordionPanel(dcc.Graph(id=f"{prefix}-{method_key}-corner")),
            ]),
            dmc.AccordionItem(value="explorer", children=[
                dmc.AccordionControl("Model Explorer"),
                dmc.AccordionPanel(html.Div(id=f"{prefix}-{method_key}-explorer")),
            ]),
        ], multiple=True),
    ], gap="md")
```

## Numpy ↔ JSON Conversion

Always convert when writing to dcc.Store:

```python
# numpy → JSON (for dcc.Store)
def to_json_safe(obj):
    """Convert numpy types to JSON-serializable Python types."""
    if isinstance(obj, dict):
        return {k: to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj

# JSON → numpy (when reading from dcc.Store)
def from_json_safe(data, array_keys=None):
    """Convert lists back to numpy arrays for specified keys."""
    if array_keys is None:
        array_keys = {'ks_p', 'ks_D', 'weighted_p', 'weighted_D',
                      'cvm_p', 'cvm_D', 'logL_raw', 'cvm_S_raw',
                      'fbin_grid', 'pi_grid', 'sigma_grid'}
    result = {}
    for k, v in data.items():
        if k in array_keys and isinstance(v, list):
            result[k] = np.array(v)
        else:
            result[k] = v
    return result
```

## Page-Level dcc.Store Layout Pattern

Each model page needs these stores:

```python
# In each page layout
dcc.Store(id=f"{prefix}-params", storage_type="local"),    # persist params
dcc.Store(id=f"{prefix}-result", storage_type="memory"),   # current result (large)
dcc.Store(id=f"{prefix}-presets", storage_type="local"),   # saved presets
```

Use `prefix` (e.g., "dsilva", "langer") to namespace IDs and prevent collisions between pages.
