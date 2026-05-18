# Multi-Page Dash Apps

## Directory Structure

```
bias_app/
    app.py              # Entry point: Dash(), MantineProvider, AppShell, page_container
    pages/
        __init__.py
        dsilva.py       # dash.register_page(__name__, path='/dsilva')
        langer.py       # dash.register_page(__name__, path='/langer')
        comparison.py   # dash.register_page(__name__, path='/comparison')
    components/
        __init__.py
        param_panels.py # Shared component builders
    callbacks/
        __init__.py
        simulation_cb.py
    assets/
        style.css       # Auto-served by Dash
```

## app.py — Entry Point

```python
import dash_mantine_components as dmc
from dash import Dash, html, dcc, page_container, page_registry, clientside_callback, \
    Input, Output, State, DiskcacheManager, _dash_renderer
import diskcache

_dash_renderer._set_react_version("18.2.0")

cache = diskcache.Cache("./cache")
background_manager = DiskcacheManager(cache)

app = Dash(
    __name__,
    use_pages=True,                          # auto-discover pages/
    external_stylesheets=dmc.styles.ALL,
    background_callback_manager=background_manager,
    suppress_callback_exceptions=True,
)

app.layout = dmc.MantineProvider(
    id="mantine-provider",
    forceColorScheme="dark",
    children=[
        dcc.Store(id="theme-store", storage_type="local"),
        dcc.Location(id="url", refresh=False),
        dmc.AppShell(
            children=[
                dmc.AppShellHeader(
                    dmc.Group([
                        dmc.Title("Bias Correction", order=3),
                        dmc.ActionIcon(
                            dmc.DashIconify(icon="radix-icons:sun"),
                            id="theme-toggle",
                            variant="outline", size="lg",
                        ),
                    ], justify="space-between", px="md", h="100%", align="center"),
                ),
                dmc.AppShellNavbar([
                    dmc.NavLink(
                        label=pg["name"],
                        href=pg["path"],
                        id={"type": "nav-link", "index": pg["path"]},
                    )
                    for pg in sorted(page_registry.values(), key=lambda p: p.get("order", 0))
                ]),
                dmc.AppShellMain(page_container),
            ],
            header={"height": 60},
            navbar={"width": 220, "breakpoint": "sm"},
            padding="md",
        ),
    ],
)

# Theme toggle (clientside for instant response)
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

if __name__ == "__main__":
    app.run(debug=True, port=8050)
```

## Page File — pages/dsilva.py

```python
import dash
from dash import html, dcc, callback, Input, Output, State, ctx, no_update
from dash.exceptions import PreventUpdate
import dash_mantine_components as dmc

# Register this page
dash.register_page(
    __name__,
    path='/dsilva',
    name='Dsilva',
    title='Bias Correction — Dsilva',
    order=0,
)

# Page layout — module-level variable named `layout`
layout = dmc.Container([
    # Stores for this page
    dcc.Store(id="dsilva-params-store", storage_type="local"),
    dcc.Store(id="dsilva-result-store", storage_type="memory"),

    dmc.Grid([
        # Left: Parameters
        dmc.GridCol(
            dmc.Accordion(
                value=["grid-params"],
                multiple=True,
                children=[
                    dmc.AccordionItem(value="grid-params", children=[
                        dmc.AccordionControl("Grid Parameters"),
                        dmc.AccordionPanel([
                            dmc.NumberInput(id="dsilva-fbin-min", label="f_bin min",
                                            value=0.0, min=0, max=1, step=0.01),
                            dmc.NumberInput(id="dsilva-fbin-max", label="f_bin max",
                                            value=1.0, min=0, max=1, step=0.01),
                            # ... more params
                        ]),
                    ]),
                    # ... more accordion items
                ],
            ),
            span=4,
        ),
        # Right: Results with scoring tabs
        dmc.GridCol(
            dmc.Tabs(id="dsilva-scoring-tabs", value="simulation", children=[
                dmc.TabsList([
                    dmc.TabsTab("Simulation", value="simulation"),
                    dmc.TabsTab("K-S", value="ks"),
                    dmc.TabsTab("K-S Weighted", value="ks-weighted"),
                    dmc.TabsTab("CvM", value="cvm"),
                    dmc.TabsTab("Likelihood", value="likelihood"),
                ]),
                dmc.TabsPanel(value="simulation", children=[
                    dcc.Graph(id="dsilva-overview-graph"),
                ]),
                dmc.TabsPanel(value="ks", children=[
                    dcc.Graph(id="dsilva-ks-heatmap"),
                ]),
                # ... more panels
            ]),
            span=8,
        ),
    ]),
], fluid=True)

# Callbacks defined in the same file
@callback(
    Output("dsilva-overview-graph", "figure"),
    Input("dsilva-result-store", "data"),
)
def update_overview(result_data):
    if result_data is None:
        raise PreventUpdate
    # Build Plotly figure from result data
    import plotly.graph_objects as go
    fig = go.Figure()
    # ... build figure
    return fig
```

## Page Registration Options

```python
dash.register_page(
    __name__,
    path='/dsilva',              # URL path
    name='Dsilva',               # Display name (used in page_registry)
    title='Dsilva Model',        # Browser tab title
    order=0,                     # Sort order in page_registry
    description='Dsilva power-law period model',
)
```

### Dynamic layout (re-evaluated on each visit)

```python
def layout(**kwargs):
    instance = kwargs.get('instance', '1')
    return dmc.Container([
        dmc.Title(f"Dsilva Instance {instance}"),
        # Use instance in component IDs for isolation
        dcc.Store(id=f"dsilva-{instance}-params"),
    ])
```

### URL path variables

```python
dash.register_page(__name__, path_template='/dsilva/<instance_id>')

def layout(instance_id="1"):
    return dmc.Container([
        dmc.Title(f"Dsilva Instance {instance_id}"),
    ])
```

## Page Navigation

### Using dcc.Link (no full page reload)

```python
dcc.Link("Go to Langer", href="/langer")
dcc.Link(dmc.Button("Comparison"), href="/comparison")
```

### Programmatic navigation

```python
dcc.Location(id="url", refresh=False)

@callback(Output("url", "pathname"), Input("nav-btn", "n_clicks"))
def navigate(n_clicks):
    return "/langer"
```

### Active NavLink highlighting

```python
@callback(
    Output({"type": "nav-link", "index": dash.ALL}, "active"),
    Input("url", "pathname"),
)
def update_active_nav(pathname):
    pages = sorted(page_registry.values(), key=lambda p: p.get("order", 0))
    return [pg["path"] == pathname for pg in pages]
```

## "New Instance" Pattern (Open in New Tab)

For running multiple independent analyses:

```python
# In navbar, add a "New Instance" button
dmc.NavLink(
    label="+ New Dsilva",
    href="/dsilva/2",    # or dynamically generate
    target="_blank",     # opens in new browser tab
)
```

Each browser tab gets its own `dcc.Store` state (when using `storage_type='session'` or `'memory'`). For `storage_type='local'`, differentiate by including instance ID in the store ID:

```python
def layout(instance_id="1"):
    return dmc.Container([
        dcc.Store(id=f"params-{instance_id}", storage_type="local"),
        # All component IDs include instance_id for isolation
    ])
```

## Key Points

- `use_pages=True` auto-discovers `pages/` directory
- Each page file needs `dash.register_page(__name__)` and a module-level `layout`
- Callbacks in page files are auto-registered
- `page_container` in app.py renders the current page
- `page_registry` dict has all registered pages (for building navigation)
- Page switching does NOT reset other pages' state or kill background callbacks
- `suppress_callback_exceptions=True` needed because not all component IDs exist at all times
