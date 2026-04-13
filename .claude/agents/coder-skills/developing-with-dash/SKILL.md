---
name: developing-with-dash
description: "Build, edit, debug, and optimize Plotly Dash + Dash Mantine Components (DMC) web applications. Use this skill for ANY task involving Dash apps: creating pages, writing callbacks, background tasks, state persistence, theming, multi-page architecture, or DMC component usage. Triggers on: dash, dmc, callback, dcc.Store, dcc.Graph, MantineProvider, bias_app/, DiskcacheManager, background callback, dash-mantine, register_page, or any Python webapp using Plotly Dash."
---

# Developing with Dash + DMC

This skill covers building Python web applications with **Plotly Dash** and **Dash Mantine Components (DMC)**. Dash is a Python framework by Plotly that creates reactive web apps using callbacks. DMC provides 90+ modern UI components (Mantine v7) with built-in theming.

## When to Use

Any task involving:
- Creating or editing Dash app files (`app.py`, `pages/*.py`)
- Writing callbacks (standard, background, clientside)
- DMC components (tabs, accordion, navbar, buttons, inputs)
- State persistence (`dcc.Store`, localStorage)
- Background tasks with progress reporting
- Multi-page Dash apps (`dash.register_page`)
- Dark/light theme toggling
- Any file in `bias_app/` directory

## Quick Reference: What to Read

| Task | Reference to Read |
|------|-------------------|
| **New app setup, MantineProvider, React 18** | This file, "App Setup" section |
| **Callbacks (basic, advanced, background)** | `references/callbacks.md` |
| **DMC components (tabs, accordion, navbar, inputs)** | `references/dmc-components.md` |
| **Multi-page architecture** | `references/multipage.md` |
| **State persistence & data sharing** | `references/persistence.md` |
| **Scientific dashboard patterns** | `references/scientific-patterns.md` |

## App Setup (CRITICAL)

DMC 0.14+ requires React 18 and MantineProvider. This is the #1 source of errors.

```python
import dash_mantine_components as dmc
from dash import Dash, html, dcc, callback, Input, Output, _dash_renderer

# REQUIRED: Must be called BEFORE creating the Dash app
_dash_renderer._set_react_version("18.2.0")

app = Dash(
    __name__,
    use_pages=True,                          # multi-page support
    external_stylesheets=dmc.styles.ALL,     # load all Mantine CSS
    suppress_callback_exceptions=True,       # needed for dynamic layouts
)

# REQUIRED: MantineProvider must wrap the ENTIRE layout
app.layout = dmc.MantineProvider(
    id="mantine-provider",
    forceColorScheme="dark",  # or "light"
    children=[
        # All app content goes here
    ],
)

if __name__ == "__main__":
    app.run(debug=True, port=8050)
```

### Setup Checklist

1. `_dash_renderer._set_react_version("18.2.0")` — BEFORE `Dash()`
2. `external_stylesheets=dmc.styles.ALL` — in `Dash()` constructor
3. `dmc.MantineProvider` — wraps entire `app.layout`
4. `suppress_callback_exceptions=True` — if using multi-page or dynamic IDs

### Installation

```bash
pip install dash dash-mantine-components diskcache
```

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Missing `_set_react_version("18.2.0")` | Add before `Dash()`. DMC 0.14+ requires React 18 |
| Layout not wrapped in `MantineProvider` | Wrap entire `app.layout` |
| Two callbacks writing to same Output | Use `allow_duplicate=True` + `prevent_initial_call=True` |
| numpy array in `dcc.Store` | Convert: `arr.tolist()` |
| `set_progress` not first arg | Background callbacks inject `set_progress` BEFORE other args |
| `set_progress(val)` not tuple | Must be tuple: `set_progress((val,))` |
| Missing `suppress_callback_exceptions` | Required for multi-page apps and pattern-matching IDs |
| `dmc.styles.ALL` not passed | Components render without styling |

## Callback Basics (Quick)

```python
from dash import callback, Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate

# Standard callback
@callback(Output('output', 'children'), Input('input', 'value'))
def update(value):
    return f'Value: {value}'

# Multiple outputs + State (non-triggering input)
@callback(
    Output('out1', 'children'),
    Output('out2', 'children'),
    Input('btn', 'n_clicks'),
    State('input', 'value'),     # read but doesn't trigger
    prevent_initial_call=True,
)
def update(n_clicks, input_value):
    if ctx.triggered_id == 'btn':
        return f'Clicked {n_clicks}', input_value
    return no_update, no_update
```

For advanced patterns (background callbacks, pattern-matching, Patch, clientside), read `references/callbacks.md`.

## DMC Components (Quick)

```python
import dash_mantine_components as dmc

# Nested Tabs (THE reason we moved from Streamlit)
dmc.Tabs(value="tab1", children=[
    dmc.TabsList([
        dmc.TabsTab("Overview", value="tab1"),
        dmc.TabsTab("K-S Test", value="tab2"),
    ]),
    dmc.TabsPanel(value="tab1", children=[
        # NEST TABS INSIDE TABS — this works in DMC!
        dmc.Tabs(value="inner1", children=[
            dmc.TabsList([
                dmc.TabsTab("Sub A", value="inner1"),
                dmc.TabsTab("Sub B", value="inner2"),
            ]),
            dmc.TabsPanel("Content A", value="inner1"),
            dmc.TabsPanel("Content B", value="inner2"),
        ])
    ]),
    dmc.TabsPanel("K-S content", value="tab2"),
])

# Accordion (collapsible sections)
dmc.Accordion(children=[
    dmc.AccordionItem(value="params", children=[
        dmc.AccordionControl("Grid Parameters"),
        dmc.AccordionPanel([
            dmc.NumberInput(id="fbin-min", label="f_bin min", value=0.0, step=0.01),
            dmc.NumberInput(id="fbin-max", label="f_bin max", value=1.0, step=0.01),
        ]),
    ]),
])

# Dark/Light Toggle
dmc.ActionIcon(
    dmc.DarkThemeIcon(),  # or use DashIconify
    id="theme-toggle",
    variant="outline",
    size="lg",
)
```

For all DMC components, read `references/dmc-components.md`.

## Background Callbacks (Quick)

```python
from dash import DiskcacheManager
import diskcache

cache = diskcache.Cache("./cache")
background_manager = DiskcacheManager(cache)

app = Dash(__name__, background_callback_manager=background_manager)

@callback(
    Output("result", "children"),
    Input("run-btn", "n_clicks"),
    background=True,
    running=[(Output("run-btn", "disabled"), True, False)],
    progress=[Output("progress", "value")],
    cancel=[Input("cancel-btn", "n_clicks")],
    prevent_initial_call=True,
)
def run_simulation(set_progress, n_clicks):
    # set_progress is FIRST arg (before n_clicks)
    for i in range(100):
        time.sleep(0.1)
        set_progress((i + 1,))  # MUST be tuple
    return "Done!"
```

For full background callback patterns, read `references/callbacks.md`.

## State Persistence (Quick)

```python
# Persist params to browser localStorage
dcc.Store(id='params-store', storage_type='local')

# Auto-save on every change
@callback(
    Output('params-store', 'data'),
    Input('fbin-min', 'value'),
    Input('fbin-max', 'value'),
)
def auto_save(fbin_min, fbin_max):
    return {'fbin_min': fbin_min, 'fbin_max': fbin_max}

# Restore on page load
@callback(
    Output('fbin-min', 'value', allow_duplicate=True),
    Output('fbin-max', 'value', allow_duplicate=True),
    Input('params-store', 'modified_timestamp'),
    State('params-store', 'data'),
    prevent_initial_call=True,
)
def restore(ts, data):
    if data is None:
        raise PreventUpdate
    return data.get('fbin_min', 0.0), data.get('fbin_max', 1.0)
```

For full persistence patterns and data sharing, read `references/persistence.md`.

## Multi-Page Apps (Quick)

```
bias_app/
    app.py          # Dash(__name__, use_pages=True) + MantineProvider + navbar
    pages/
        dsilva.py   # dash.register_page(__name__, path='/dsilva')
        langer.py   # dash.register_page(__name__, path='/langer')
```

```python
# pages/dsilva.py
import dash
dash.register_page(__name__, path='/dsilva', name='Dsilva', order=0)

layout = dmc.Container([...])  # module-level `layout` variable

@callback(...)  # callbacks defined in same file
def update(...): ...
```

For full multi-page architecture, read `references/multipage.md`.
