# Dash Callbacks — Complete Reference

## Table of Contents
1. [Basic Callbacks](#basic-callbacks)
2. [Advanced: ctx, no_update, PreventUpdate](#advanced-patterns)
3. [Pattern-Matching Callbacks](#pattern-matching)
4. [Background Callbacks](#background-callbacks)
5. [Clientside Callbacks](#clientside-callbacks)
6. [Patch() for Efficient Updates](#patch)

## Basic Callbacks

```python
from dash import callback, Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate
```

### Single Input/Output
```python
@callback(Output('output', 'children'), Input('input', 'value'))
def update(value):
    return f'Value: {value}'
```

### Multiple Inputs (positional, in declaration order)
```python
@callback(
    Output('graph', 'figure'),
    Input('x-col', 'value'),
    Input('y-col', 'value'),
    Input('year', 'value'),
)
def update_graph(x_col, y_col, year):
    return px.scatter(df[df['Year'] == year], x=x_col, y=y_col)
```

### Multiple Outputs
```python
@callback(
    Output('out1', 'children'),
    Output('out2', 'children'),
    Input('input', 'value'),
)
def update(value):
    return f'Output 1: {value}', f'Output 2: {value}'
```

### State (read without triggering)
```python
@callback(
    Output('output', 'children'),
    Input('submit-btn', 'n_clicks'),
    State('text-input', 'value'),   # read on click, but typing doesn't trigger
    prevent_initial_call=True,
)
def submit(n_clicks, text_value):
    return f'Submitted: {text_value}'
```

### prevent_initial_call
By default, callbacks fire on page load with initial values. Add `prevent_initial_call=True` to suppress this.

---

## Advanced Patterns

### PreventUpdate — Skip ALL outputs
```python
@callback(Output('output', 'children'), Input('btn', 'n_clicks'))
def update(n_clicks):
    if n_clicks is None:
        raise PreventUpdate  # nothing happens
    return f'Clicked {n_clicks}'
```

### no_update — Skip SPECIFIC outputs
```python
@callback(
    Output('out1', 'children'),
    Output('out2', 'children'),
    Input('btn', 'n_clicks'),
)
def update(n_clicks):
    if n_clicks % 2 == 0:
        return f'Even: {n_clicks}', no_update  # only update out1
    return no_update, f'Odd: {n_clicks}'        # only update out2
```

### ctx.triggered_id — Which input fired
```python
@callback(
    Output('output', 'children'),
    Input('btn-a', 'n_clicks'),
    Input('btn-b', 'n_clicks'),
)
def update(a_clicks, b_clicks):
    if ctx.triggered_id == 'btn-a':
        return 'Button A clicked'
    elif ctx.triggered_id == 'btn-b':
        return 'Button B clicked'
    return 'No clicks yet'
```

### allow_duplicate — Multiple callbacks to same Output
```python
# RULE: allow_duplicate REQUIRES prevent_initial_call=True
@callback(
    Output('slider', 'value', allow_duplicate=True),
    Input('input-box', 'value'),
    prevent_initial_call=True,  # REQUIRED with allow_duplicate
)
def sync_input_to_slider(value):
    return value
```

---

## Pattern-Matching Callbacks

For dynamically created components with variable IDs.

```python
from dash import ALL, MATCH, ALLSMALLER

# Component IDs are dicts, not strings
dcc.Input(id={'type': 'param-input', 'index': 0}, value=0)
dcc.Input(id={'type': 'param-input', 'index': 1}, value=0)

# ALL — trigger when ANY matching component changes, receive list of all values
@callback(
    Output('summary', 'children'),
    Input({'type': 'param-input', 'index': ALL}, 'value'),
)
def update_summary(all_values):
    # all_values = [value_of_index_0, value_of_index_1, ...]
    return f'Sum: {sum(v or 0 for v in all_values)}'

# MATCH — one-to-one: each component triggers its own paired output
@callback(
    Output({'type': 'param-display', 'index': MATCH}, 'children'),
    Input({'type': 'param-input', 'index': MATCH}, 'value'),
)
def update_display(value):
    return f'Current: {value}'
```

---

## Background Callbacks

For long-running tasks (simulations, grid searches). Runs in a separate process — survives page navigation.

### Setup
```python
from dash import Dash, DiskcacheManager
import diskcache

cache = diskcache.Cache("./cache")
background_manager = DiskcacheManager(cache)

app = Dash(__name__, background_callback_manager=background_manager)
```

### Full Pattern with Progress + Cancel
```python
import dash_mantine_components as dmc

# Layout
dmc.Button("Run", id="run-btn"),
dmc.Button("Cancel", id="cancel-btn", color="red", display="none"),
dmc.Progress(id="progress", value=0, size="lg", striped=True, animated=True),
dmc.Text(id="progress-text", children=""),
html.Div(id="result"),

# Callback
@callback(
    Output("result", "children"),
    Input("run-btn", "n_clicks"),
    State("params-store", "data"),
    background=True,
    running=[
        (Output("run-btn", "disabled"), True, False),
        (Output("run-btn", "loading"), True, False),           # DMC loading state
        (Output("cancel-btn", "display"), "block", "none"),    # show cancel
        (Output("progress", "animated"), True, False),
    ],
    progress=[
        Output("progress", "value"),
        Output("progress-text", "children"),
    ],
    cancel=[Input("cancel-btn", "n_clicks")],
    prevent_initial_call=True,
)
def run_simulation(set_progress, n_clicks, params):
    # set_progress is ALWAYS the FIRST argument
    # params comes from State, after n_clicks from Input
    import time
    total = params.get('n_steps', 100)
    for i in range(total):
        time.sleep(0.1)
        pct = int((i + 1) / total * 100)
        set_progress((pct, f"Step {i+1}/{total}"))  # tuple of values matching progress outputs
    return "Simulation complete!"
```

### Background Callback Parameters
- `background=True` — marks as background
- `running=[(Output, while_running, when_done), ...]` — toggle UI states
- `progress=[Output(...), ...]` — outputs for progress; `set_progress` injected as first arg
- `cancel=[Input(...)]` — cancel trigger
- `prevent_initial_call=True` — almost always needed

### Background + multiprocessing.Pool
```python
@callback(
    Output("result-store", "data"),
    Input("run-btn", "n_clicks"),
    State("params-store", "data"),
    background=True,
    progress=[Output("progress", "value")],
    prevent_initial_call=True,
)
def run_grid(set_progress, n_clicks, params):
    from wr_bias_simulation import run_bias_grid, SimulationConfig, BinaryParameterConfig
    import multiprocessing as mp

    # CRITICAL: Use 'spawn' context inside background callbacks.
    # 'fork' causes deadlocks because background callbacks already run in a separate process.
    ctx = mp.get_context('spawn')

    cfg_sim = SimulationConfig(**params['sim_config'])
    cfg_bin = BinaryParameterConfig(**params['bin_config'])

    # run_bias_grid uses multiprocessing internally — pass ctx if possible,
    # or set mp.set_start_method('spawn') at module level
    result = run_bias_grid(
        fbin_values=np.linspace(params['fbin_min'], params['fbin_max'], params['fbin_steps']),
        pi_values=np.linspace(params['pi_min'], params['pi_max'], params['pi_steps']),
        obs_delta_rv=np.array(params['obs_delta_rv']),
        sim_cfg=cfg_sim,
        bin_cfg=cfg_bin,
        n_processes=params.get('n_processes', mp.cpu_count() - 1),
    )

    # Convert numpy arrays to lists for JSON serialization (dcc.Store)
    return {k: v.tolist() if hasattr(v, 'tolist') else v for k, v in result.items()}
```

### Key Gotchas — Background Callbacks
- `set_progress` values MUST be a tuple even for single output: `set_progress((val,))`
- Background callbacks run in a SEPARATE PROCESS — no shared memory with the main app
- Data must be JSON-serializable (no numpy arrays — use `.tolist()`)
- DiskcacheManager stores task state on disk — `./cache` directory grows, clean periodically
- Background jobs survive page navigation — this is the key advantage over Streamlit

---

## Clientside Callbacks

Run JavaScript in the browser — no server round-trip. Use for simple UI toggles.

```python
from dash import clientside_callback

# Theme toggle (runs instantly in browser)
clientside_callback(
    """
    function(n_clicks, current) {
        if (!n_clicks) return window.dash_clientside.no_update;
        return current === "light" ? "dark" : "light";
    }
    """,
    Output("mantine-provider", "forceColorScheme"),
    Input("theme-toggle", "n_clicks"),
    State("mantine-provider", "forceColorScheme"),
    prevent_initial_call=True,
)
```

### When to Use Clientside
- Theme toggling (instant, no flicker)
- Show/hide elements
- Simple data transforms from dcc.Store
- Anything that avoids unnecessary server calls

### Limitations
- No Python libraries available (it's JavaScript)
- Use `window.dash_clientside.no_update` instead of `PreventUpdate`
- Debug via browser console, not Python

---

## Patch() for Efficient Updates

Update parts of a component without re-sending the entire thing.

```python
from dash import Patch

# Append to a list of children
@callback(Output("container", "children"), Input("add-btn", "n_clicks"))
def add_item(n_clicks):
    patched = Patch()
    patched.append(html.Div(f"Item {n_clicks}"))
    return patched  # only sends the new item, not all children

# Update part of a figure
@callback(Output("graph", "figure"), Input("add-trace-btn", "n_clicks"))
def add_trace(n_clicks):
    patched = Patch()
    patched['data'].append(go.Scatter(x=[1,2,3], y=[n_clicks]*3))
    return patched

# Delete from list
@callback(Output("container", "children"), Input("remove-btn", "n_clicks"))
def remove_last(n_clicks):
    patched = Patch()
    del patched[-1]
    return patched
```

Operations: `append`, `prepend`, `insert(i, item)`, `extend`, `clear`, `del patched[i]`, `patched[i] = new`, `patched['key'] = value`
