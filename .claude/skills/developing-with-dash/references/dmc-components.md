# DMC Components Reference

## Table of Contents
1. [Tabs (with nesting)](#tabs)
2. [Accordion](#accordion)
3. [AppShell + Navbar](#appshell)
4. [Inputs (NumberInput, Select, TextInput)](#inputs)
5. [Buttons and Actions](#buttons)
6. [Feedback (Progress, Notifications, Alerts)](#feedback)
7. [Layout (Grid, Stack, Group)](#layout)
8. [Theme Switching](#theme-switching)

## Tabs

DMC Tabs support arbitrary nesting — the primary reason for migrating from Streamlit.

### Structure: TabsList + TabsTab + TabsPanel

```python
import dash_mantine_components as dmc

dmc.Tabs(
    id="model-tabs",
    value="simulation",  # active tab value
    children=[
        dmc.TabsList([
            dmc.TabsTab("Simulation", value="simulation"),
            dmc.TabsTab("K-S Test", value="ks"),
            dmc.TabsTab("K-S Weighted", value="ks-weighted"),
            dmc.TabsTab("CvM", value="cvm"),
            dmc.TabsTab("Likelihood", value="likelihood"),
        ]),
        dmc.TabsPanel(value="simulation", children=[
            # ... simulation overview content
        ]),
        dmc.TabsPanel(value="ks", children=[
            # ... K-S test content
        ]),
        # ... more panels
    ],
)
```

### Nested Tabs (works in DMC!)

```python
dmc.Tabs(
    value="outer1",
    keepMounted=True,  # CRITICAL: preserves inner tab state when switching outer tabs
    children=[
        dmc.TabsList([
            dmc.TabsTab("Outer Tab 1", value="outer1"),
            dmc.TabsTab("Outer Tab 2", value="outer2"),
        ]),
        dmc.TabsPanel(value="outer1", children=[
            dmc.Tabs(value="inner1", variant="pills", children=[  # different variant to distinguish
                dmc.TabsList([
                    dmc.TabsTab("Inner A", value="inner1"),
                    dmc.TabsTab("Inner B", value="inner2"),
                ]),
                dmc.TabsPanel("Inner A content", value="inner1"),
                dmc.TabsPanel("Inner B content", value="inner2"),
            ])
        ]),
        dmc.TabsPanel("Outer 2 content", value="outer2"),
    ],
)
```

### Tab Styling

```python
dmc.Tabs(
    value="tab1",
    variant="outline",    # "default", "outline", "pills"
    orientation="horizontal",  # or "vertical"
    color="blue",
    children=[...],
)
```

### Tab with Callback (lazy rendering)

```python
dmc.Tabs(id="scoring-tabs", value="simulation", children=[
    dmc.TabsList([
        dmc.TabsTab("Simulation", value="simulation"),
        dmc.TabsTab("K-S", value="ks"),
    ]),
    html.Div(id="scoring-tab-content"),
])

@callback(Output("scoring-tab-content", "children"), Input("scoring-tabs", "value"))
def render_scoring_tab(tab):
    if tab == "simulation":
        return build_simulation_panel()
    elif tab == "ks":
        return build_ks_panel()
```

---

## Accordion

Collapsible sections — use for parameter groups.

```python
dmc.Accordion(
    value=["grid-params"],  # list of initially open items
    multiple=True,          # allow multiple open simultaneously
    variant="separated",    # "default", "contained", "filled", "separated"
    children=[
        dmc.AccordionItem(value="grid-params", children=[
            dmc.AccordionControl("Grid Parameters"),
            dmc.AccordionPanel([
                dmc.NumberInput(id="fbin-min", label="f_bin min", value=0.0,
                                min=0.0, max=1.0, step=0.01, precision=2),
                dmc.NumberInput(id="fbin-max", label="f_bin max", value=1.0,
                                min=0.0, max=1.0, step=0.01, precision=2),
                dmc.NumberInput(id="fbin-steps", label="Steps", value=100,
                                min=2, max=500, step=1),
            ]),
        ]),
        dmc.AccordionItem(value="orbital", children=[
            dmc.AccordionControl("Orbital Parameters"),
            dmc.AccordionPanel([
                dmc.NumberInput(id="logP-min", label="log P min", value=0.15),
                dmc.NumberInput(id="logP-max", label="log P max", value=5.0),
                dmc.Select(id="e-model", label="Eccentricity model",
                           data=["zero", "flat"], value="flat"),
            ]),
        ]),
        dmc.AccordionItem(value="load-result", children=[
            dmc.AccordionControl("Load Saved Result"),
            dmc.AccordionPanel(html.Div(id="result-table-container")),
        ]),
    ],
)
```

---

## AppShell

Full app layout with navbar, header, and main content area.

```python
dmc.AppShell(
    children=[
        dmc.AppShellHeader(
            dmc.Group([
                dmc.Title("Bias Correction", order=3),
                dmc.Group([
                    dmc.ActionIcon(
                        dmc.DashIconify(icon="radix-icons:sun"),
                        id="theme-toggle",
                        variant="outline", size="lg",
                    ),
                ]),
            ], justify="space-between", px="md", h="100%", align="center"),
        ),
        dmc.AppShellNavbar([
            dmc.NavLink(label="Dsilva", href="/dsilva", active=True),
            dmc.NavLink(label="Langer", href="/langer"),
            dmc.NavLink(label="Cadence (D)", href="/cadence-dsilva"),
            dmc.NavLink(label="Cadence (L)", href="/cadence-langer"),
            dmc.Divider(),
            dmc.NavLink(label="Comparison", href="/comparison"),
            dmc.NavLink(label="RV Errors", href="/rv-errors"),
        ]),
        dmc.AppShellMain(
            dash.page_container  # renders current page
        ),
    ],
    header={"height": 60},
    navbar={"width": 220, "breakpoint": "sm"},
    padding="md",
)
```

### NavLink Active State

```python
from dash import callback, Input, Output, ALL
import dash

# Highlight active page in navbar
@callback(
    Output({"type": "nav-link", "index": ALL}, "active"),
    Input("url", "pathname"),
)
def update_nav_active(pathname):
    pages = list(dash.page_registry.values())
    return [pg["path"] == pathname for pg in pages]
```

---

## Inputs

### NumberInput
```python
dmc.NumberInput(
    id="sigma",
    label="Sigma (km/s)",
    description="Intrinsic velocity scatter",
    value=6.0,
    min=0.1,
    max=50.0,
    step=0.1,
    precision=1,
    w=200,              # width in px
    leftSection=dmc.DashIconify(icon="mdi:sigma"),
)
```

### Select (dropdown)
```python
dmc.Select(
    id="error-model",
    label="Error Model",
    data=[
        {"value": "fixed", "label": "Fixed"},
        {"value": "normal", "label": "Normal"},
        {"value": "lognormal", "label": "Log-Normal"},
        {"value": "gamma", "label": "Gamma"},
    ],
    value="fixed",
    searchable=True,
    clearable=False,
)
```

### MultiSelect
```python
dmc.MultiSelect(
    id="scoring-methods",
    label="Scoring Methods",
    data=["K-S", "K-S Weighted", "CvM", "Likelihood"],
    value=["K-S", "Likelihood"],
)
```

### TextInput
```python
dmc.TextInput(
    id="preset-name",
    label="Preset Name",
    placeholder="Enter a name for this preset",
)
```

### Slider
```python
dmc.Slider(
    id="sigma-slider",
    min=0.1, max=20.0, step=0.1, value=6.0,
    marks=[
        {"value": 5, "label": "5"},
        {"value": 10, "label": "10"},
        {"value": 15, "label": "15"},
    ],
    w="100%",
)
```

### Switch (toggle)
```python
dmc.Switch(
    id="scan-sigma",
    label="Enable sigma scan",
    checked=False,
)
```

---

## Buttons

```python
# Standard button
dmc.Button("Run Simulation", id="run-btn", color="blue", variant="filled",
           leftSection=dmc.DashIconify(icon="mdi:play"))

# Cancel button
dmc.Button("Cancel", id="cancel-btn", color="red", variant="outline",
           leftSection=dmc.DashIconify(icon="mdi:stop"))

# Loading state (set via callback)
dmc.Button("Run", id="run-btn", loading=False)  # set loading=True via running=[]

# Icon-only button
dmc.ActionIcon(
    dmc.DashIconify(icon="mdi:plus"),
    id="add-btn",
    variant="light",
    color="blue",
    size="lg",
)

# Button group
dmc.Group([
    dmc.Button("Run", id="run-btn", color="blue"),
    dmc.Button("Cancel", id="cancel-btn", color="red", variant="outline"),
    dmc.Button("Reset", id="reset-btn", variant="subtle"),
], gap="sm")
```

---

## Feedback

### Progress Bar
```python
dmc.Progress(
    id="sim-progress",
    value=0,
    size="lg",
    striped=True,
    animated=True,   # animate stripes while running
    color="blue",
)
```

### Notification
```python
# Use NotificationProvider in the root layout
dmc.NotificationProvider(position="top-right")

# Trigger notification via callback
# Note: DMC notifications use dmc.Notification with action="show"
# Alternatively, use a simple Alert:
dmc.Alert(
    "Simulation complete! Best fit: f_bin=0.46, pi=-0.5",
    title="Success",
    color="green",
    icon=dmc.DashIconify(icon="mdi:check-circle"),
    withCloseButton=True,
    id="success-alert",
    style={"display": "none"},  # toggle via callback
)
```

### Loading Overlay
```python
dmc.LoadingOverlay(
    visible=False,
    id="loading-overlay",
    overlayProps={"radius": "sm", "blur": 2},
    children=[
        # content that gets overlaid when loading
        dcc.Graph(id="heatmap"),
    ],
)
```

---

## Layout

### Grid (responsive columns)
```python
dmc.Grid([
    dmc.GridCol(
        # Left sidebar: params
        dmc.Accordion([...]),
        span=4,   # 4 out of 12 columns
    ),
    dmc.GridCol(
        # Right area: results
        dmc.Tabs([...]),
        span=8,   # 8 out of 12 columns
    ),
])
```

### Stack (vertical)
```python
dmc.Stack([
    dmc.Text("Item 1"),
    dmc.Text("Item 2"),
    dmc.Text("Item 3"),
], gap="md")
```

### Group (horizontal)
```python
dmc.Group([
    dmc.Button("Save"),
    dmc.Button("Cancel"),
], gap="sm", justify="flex-end")
```

### Container (centered content with max-width)
```python
dmc.Container(children=[...], size="xl")  # "xs", "sm", "md", "lg", "xl"
```

### Paper (card-like container)
```python
dmc.Paper(
    children=[dmc.Text("Best fit: f_bin = 0.46")],
    shadow="sm",
    p="md",
    radius="md",
    withBorder=True,
)
```

---

## Theme Switching

### MantineProvider setup
```python
app.layout = dmc.MantineProvider(
    id="mantine-provider",
    forceColorScheme="dark",  # "dark", "light", or None (auto)
    children=[...],
)
```

### Clientside toggle (instant, no server call)
```python
from dash import clientside_callback

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

### Persist theme preference
```python
# Add to layout
dcc.Store(id="theme-store", storage_type="local")

# Save theme on toggle
clientside_callback(
    """
    function(scheme) {
        return scheme;
    }
    """,
    Output("theme-store", "data"),
    Input("mantine-provider", "forceColorScheme"),
)

# Restore theme on page load
clientside_callback(
    """
    function(data) {
        return data || "dark";
    }
    """,
    Output("mantine-provider", "forceColorScheme", allow_duplicate=True),
    Input("theme-store", "data"),
    prevent_initial_call=True,
)
```

### Plotly Theme Matching
```python
# In config.py
PLOTLY_THEME_DARK = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#c1c2c5"),
)

PLOTLY_THEME_LIGHT = dict(
    template="plotly_white",
    paper_bgcolor="white",
    plot_bgcolor="white",
    font=dict(family="Times New Roman", color="black"),
    xaxis=dict(showline=True, linecolor="black", mirror=True, ticks="outside"),
    yaxis=dict(showline=True, linecolor="black", mirror=True, ticks="outside"),
)
```

Apply in callbacks based on current theme from `dcc.Store`.

---

## DashIconify

For icons, use `dash-iconify` (install: `pip install dash-iconify`):

```python
from dash_iconify import DashIconify

DashIconify(icon="mdi:play", width=20)
DashIconify(icon="radix-icons:sun", width=20)
DashIconify(icon="radix-icons:moon", width=20)
DashIconify(icon="mdi:sigma", width=20)
```

Browse icons at https://icon-sets.iconify.design/
