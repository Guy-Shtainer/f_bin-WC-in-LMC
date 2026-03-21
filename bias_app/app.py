"""
bias_app/app.py
───────────────
Entry point for the Dash bias-correction webapp.

Launch:  conda run -n guyenv python bias_app/app.py
Browse:  http://localhost:8050
"""
from __future__ import annotations

import os
import sys

# ── React 18 MUST be set BEFORE importing Dash ──────────────────────────────
from dash import _dash_renderer
_dash_renderer._set_react_version("18.2.0")

import dash
from dash import Dash, html, dcc, page_container, page_registry, \
    clientside_callback, Input, Output, State
import dash_mantine_components as dmc
from dash_iconify import DashIconify

# ── Path setup ───────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── Create the Dash app ─────────────────────────────────────────────────────
app = Dash(
    __name__,
    use_pages=True,
    pages_folder='pages',
    external_stylesheets=dmc.styles.ALL,
    suppress_callback_exceptions=True,
)
app.title = "WR Bias Correction"

# ── Pre-cache observed delta-RVs (so background callbacks don't hang) ────────
import numpy as _np
_OBS_DRV_CACHE = os.path.join(_HERE, '.obs_delta_rv_cache.npy')
if not os.path.exists(_OBS_DRV_CACHE):
    try:
        from data_loader import load_observed_delta_rvs
        _drv = load_observed_delta_rvs()
        _np.save(_OBS_DRV_CACHE, _drv)
        print(f'  Cached {len(_drv)} delta-RVs to {_OBS_DRV_CACHE}')
    except Exception as _e:
        print(f'  Warning: could not pre-cache delta-RVs: {_e}')


# ── Build navbar from page_registry ──────────────────────────────────────────
def _build_navbar():
    """Build NavLinks from registered pages, sorted by order."""
    pages = sorted(page_registry.values(), key=lambda p: p.get('order', 99))
    links = []
    for pg in pages:
        icon = pg.get('icon', 'tabler:file')
        links.append(
            dmc.NavLink(
                label=pg['name'],
                href=pg['path'],
                leftSection=DashIconify(icon=icon, width=18),
                id={'type': 'nav-link', 'path': pg['path']},
            )
        )
    return links


# ── App layout ───────────────────────────────────────────────────────────────
app.layout = dmc.MantineProvider(
    id='mantine-provider',
    forceColorScheme='dark',
    children=[
        # Global stores
        dcc.Store(id='theme-store', storage_type='local'),
        dcc.Location(id='url', refresh=False),

        # Notification provider
        dmc.NotificationProvider(position='top-right'),
        html.Div(id='notification-container'),

        # AppShell: header + navbar + main
        dmc.AppShell(
            children=[
                dmc.AppShellHeader(
                    dmc.Group(
                        [
                            dmc.Title('WR Bias Correction', order=3),
                            dmc.ActionIcon(
                                DashIconify(icon='radix-icons:sun', width=20),
                                id='theme-toggle',
                                variant='outline',
                                size='lg',
                            ),
                        ],
                        justify='space-between',
                        px='md',
                        h='100%',
                        align='center',
                    ),
                ),
                dmc.AppShellNavbar(
                    _build_navbar(),
                    p='md',
                ),
                dmc.AppShellMain(
                    page_container,
                ),
            ],
            header={'height': 60},
            navbar={'width': 220, 'breakpoint': 'sm'},
            padding='md',
        ),
    ],
)


# ── Theme toggle (clientside for instant response) ──────────────────────────
clientside_callback(
    """
    function(n_clicks, current) {
        if (!n_clicks) return window.dash_clientside.no_update;
        return current === "light" ? "dark" : "light";
    }
    """,
    Output('mantine-provider', 'forceColorScheme'),
    Input('theme-toggle', 'n_clicks'),
    State('mantine-provider', 'forceColorScheme'),
    prevent_initial_call=True,
)

# Update toggle icon to match current scheme
clientside_callback(
    """
    function(scheme) {
        // Return just the icon name — DashIconify will render it
        // Actually we need to return a full component, but clientside can't do that.
        // Instead we'll handle this server-side.
        return window.dash_clientside.no_update;
    }
    """,
    Output('theme-toggle', 'children'),
    Input('mantine-provider', 'forceColorScheme'),
    prevent_initial_call=True,
)

# Server-side icon update (clientside can't create DashIconify)
@dash.callback(
    Output('theme-toggle', 'children', allow_duplicate=True),
    Input('mantine-provider', 'forceColorScheme'),
    prevent_initial_call=True,
)
def update_theme_icon(scheme):
    icon = 'radix-icons:moon' if scheme == 'dark' else 'radix-icons:sun'
    return DashIconify(icon=icon, width=20)


# Persist theme to localStorage
clientside_callback(
    """
    function(scheme) { return scheme; }
    """,
    Output('theme-store', 'data'),
    Input('mantine-provider', 'forceColorScheme'),
)

# Restore theme from localStorage on load
clientside_callback(
    """
    function(data) { return data || "dark"; }
    """,
    Output('mantine-provider', 'forceColorScheme', allow_duplicate=True),
    Input('theme-store', 'data'),
    prevent_initial_call=True,
)


# ── Highlight active NavLink ────────────────────────────────────────────────
@dash.callback(
    Output({'type': 'nav-link', 'path': dash.ALL}, 'active'),
    Input('url', 'pathname'),
)
def highlight_active_nav(pathname):
    pages = sorted(page_registry.values(), key=lambda p: p.get('order', 99))
    return [pg['path'] == pathname for pg in pages]


# ── Run ──────────────────────────────────────────────────────────────────────
def _find_free_port(start=8050, end=8099):
    """Find the first free port in range."""
    import socket
    for port in range(start, end):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    return start  # fallback


if __name__ == '__main__':
    import threading
    import webbrowser

    port = _find_free_port()
    url = f'http://127.0.0.1:{port}'

    # Auto-open browser after server starts (like Streamlit does)
    threading.Timer(1.5, webbrowser.open, args=[url]).start()

    print(f'\n  Bias Correction App: {url}\n')
    # use_reloader=False avoids the "address in use" double-process issue
    app.run(debug=True, port=port, use_reloader=False)
