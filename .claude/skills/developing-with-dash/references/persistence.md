# State Persistence & Data Sharing

## dcc.Store — The Primary Mechanism

### Storage Types

| Type | Survives Refresh | Survives Browser Close | Shared Across Tabs | Size Limit |
|------|-----------------|----------------------|-------------------|------------|
| `'memory'` | No | No | No | ~2-5MB |
| `'session'` | Yes | No | No (per-tab) | ~5-10MB |
| `'local'` | Yes | Yes | Yes (same origin) | ~5-10MB |

### Which to Use

- **Parameter presets**: `storage_type='local'` — survives everything
- **Current simulation result**: `storage_type='memory'` — large data, don't persist
- **Theme preference**: `storage_type='local'` — persist across sessions
- **Page-specific temp state**: `storage_type='session'` — per-tab isolation

### Auto-Save Pattern (save on every param change)

```python
# In layout
dcc.Store(id='dsilva-params', storage_type='local'),
dmc.NumberInput(id='fbin-min', value=0.0),
dmc.NumberInput(id='fbin-max', value=1.0),
dmc.NumberInput(id='fbin-steps', value=100),
dmc.Select(id='e-model', value='flat'),

# Auto-save callback
@callback(
    Output('dsilva-params', 'data'),
    Input('fbin-min', 'value'),
    Input('fbin-max', 'value'),
    Input('fbin-steps', 'value'),
    Input('e-model', 'value'),
)
def auto_save_params(fbin_min, fbin_max, fbin_steps, e_model):
    return {
        'fbin_min': fbin_min,
        'fbin_max': fbin_max,
        'fbin_steps': fbin_steps,
        'e_model': e_model,
    }

# Restore on page load
@callback(
    Output('fbin-min', 'value', allow_duplicate=True),
    Output('fbin-max', 'value', allow_duplicate=True),
    Output('fbin-steps', 'value', allow_duplicate=True),
    Output('e-model', 'value', allow_duplicate=True),
    Input('dsilva-params', 'modified_timestamp'),
    State('dsilva-params', 'data'),
    prevent_initial_call=True,
)
def restore_params(ts, data):
    if data is None:
        raise PreventUpdate
    return (
        data.get('fbin_min', 0.0),
        data.get('fbin_max', 1.0),
        data.get('fbin_steps', 100),
        data.get('e_model', 'flat'),
    )
```

### Named Presets Pattern

```python
# Layout
dcc.Store(id='presets-store', storage_type='local'),
dmc.Select(id='preset-selector', label='Load Preset', data=[]),
dmc.TextInput(id='preset-name', label='Preset Name'),
dmc.Button('Save Preset', id='save-preset-btn'),
dmc.Button('Delete Preset', id='delete-preset-btn', color='red', variant='outline'),

# Save preset
@callback(
    Output('presets-store', 'data'),
    Input('save-preset-btn', 'n_clicks'),
    State('preset-name', 'value'),
    State('dsilva-params', 'data'),
    State('presets-store', 'data'),
    prevent_initial_call=True,
)
def save_preset(n_clicks, name, current_params, all_presets):
    if not name:
        raise PreventUpdate
    presets = all_presets or {}
    presets[name] = current_params
    return presets

# Update preset selector dropdown
@callback(
    Output('preset-selector', 'data'),
    Input('presets-store', 'data'),
)
def update_preset_list(presets):
    if not presets:
        return []
    return [{'value': name, 'label': name} for name in presets.keys()]

# Load preset
@callback(
    Output('dsilva-params', 'data', allow_duplicate=True),
    Input('preset-selector', 'value'),
    State('presets-store', 'data'),
    prevent_initial_call=True,
)
def load_preset(preset_name, presets):
    if not preset_name or not presets:
        raise PreventUpdate
    return presets.get(preset_name)
```

### Also Save to JSON File (for sharing across apps)

```python
import json, os

PRESETS_DIR = os.path.join(os.path.dirname(__file__), '..', 'settings', 'presets')

@callback(
    Output('save-status', 'children'),
    Input('save-to-disk-btn', 'n_clicks'),
    State('preset-name', 'value'),
    State('dsilva-params', 'data'),
    prevent_initial_call=True,
)
def save_preset_to_disk(n_clicks, name, params):
    os.makedirs(PRESETS_DIR, exist_ok=True)
    path = os.path.join(PRESETS_DIR, f'{name}.json')
    with open(path, 'w') as f:
        json.dump(params, f, indent=2)
    return f'Saved to {path}'
```

## Data Sharing Between Callbacks

### Pattern 1: Intermediate dcc.Store

Use when multiple callbacks need the same computed data.

```python
# Layout
dcc.Store(id='result-data', storage_type='memory'),
dcc.Graph(id='heatmap-graph'),
dcc.Graph(id='cdf-graph'),
html.Div(id='best-fit-text'),

# Callback 1: compute and store
@callback(Output('result-data', 'data'), Input('run-btn', 'n_clicks'), ...)
def compute_result(n_clicks, ...):
    result = run_simulation(...)
    return {k: v.tolist() if hasattr(v, 'tolist') else v for k, v in result.items()}

# Callback 2: heatmap reads from store
@callback(Output('heatmap-graph', 'figure'), Input('result-data', 'data'))
def update_heatmap(data):
    if data is None: raise PreventUpdate
    return build_heatmap_figure(data)

# Callback 3: CDF also reads from store (fires independently)
@callback(Output('cdf-graph', 'figure'), Input('result-data', 'data'))
def update_cdf(data):
    if data is None: raise PreventUpdate
    return build_cdf_figure(data)
```

### Pattern 2: Server-Side Cache (for large results >5MB)

```python
import uuid, os, json
import numpy as np

CACHE_DIR = './tmp_results'

@callback(Output('result-id', 'data'), Input('run-btn', 'n_clicks'), ...)
def compute_and_cache(n_clicks, ...):
    result = run_simulation(...)
    result_id = str(uuid.uuid4())
    os.makedirs(CACHE_DIR, exist_ok=True)
    np.savez(os.path.join(CACHE_DIR, f'{result_id}.npz'), **result)
    return result_id  # only the ID goes to the client

@callback(Output('heatmap', 'figure'), Input('result-id', 'data'))
def update_heatmap(result_id):
    if result_id is None: raise PreventUpdate
    result = dict(np.load(os.path.join(CACHE_DIR, f'{result_id}.npz')))
    return build_heatmap_figure(result)
```

## Critical Rules

1. **dcc.Store data must be JSON-serializable** — no numpy arrays, no datetime. Convert with `.tolist()`, `.isoformat()`
2. **`allow_duplicate=True` always needs `prevent_initial_call=True`** — Dash enforces this
3. **`storage_type='local'` is shared across tabs** — use unique IDs per page/instance if you need isolation
4. **Don't use global variables for state** — breaks with multiple users/workers. Always use dcc.Store or server-side cache
5. **Large data (>5MB)**: use server-side cache (file or Redis), not dcc.Store
6. **`modified_timestamp` is -1 until first write** — check for `data is None` in restore callbacks
