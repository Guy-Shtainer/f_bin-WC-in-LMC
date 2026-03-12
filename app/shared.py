"""
app/shared.py
─────────────
Shared utilities for the Streamlit WR-binary analysis app:
  - SettingsManager  : load/save/preset/state management
  - render_sidebar   : persistent sidebar shown on every page
  - ObservationManager singleton (cached resource)
  - CSS theme injection
  - Colour constants
"""

from __future__ import annotations

import gc
import hashlib
import json
import os
import sys
from datetime import datetime
from typing import Any

import numpy as np
import streamlit as st

# ── Path fix ──────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import specs
from ObservationClass import ObservationManager as _OM

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────
_SETTINGS_PATH    = os.path.join(_ROOT, 'settings', 'user_settings.json')
_RUN_HISTORY_PATH = os.path.join(_ROOT, 'settings', 'run_history.json')
_STATES_DIR       = os.path.join(_ROOT, 'settings', 'states')
_PRESETS_DIR      = os.path.join(_ROOT, 'settings', 'presets')

# ─────────────────────────────────────────────────────────────────────────────
# Colour constants (used across pages)
# ─────────────────────────────────────────────────────────────────────────────
COLOR_BINARY   = '#E25A53'   # tomato red
COLOR_SINGLE   = '#4A90D9'   # steel blue
COLOR_UNKNOWN  = '#8C8C8C'   # grey
COLOR_CLEANED  = '#52B788'   # green

# ─────────────────────────────────────────────────────────────────────────────
# Theme palettes (light / dark)
# ─────────────────────────────────────────────────────────────────────────────
_LIGHT_PALETTE = dict(
    plot_bg='white', paper_bg='white', font_color='#333333', title_color='#222222',
    grid_color='#e0e0e0', line_color='#333333', tick_color='#333333',
    legend_bg='rgba(255,255,255,0.85)', legend_border='#cccccc',
    app_bg='#ffffff', sidebar_bg='#f5f5f5', heading_color='#222222',
    card_bg='#ffffff', card_border='#d0d0d0', card_shadow='rgba(0,0,0,0.08)',
    label_color='#666666', value_color='#222222', sub_color='#888888',
    muted_color='#888888',          # muted/secondary text
    annotation_bg='rgba(255,255,255,0.9)', annotation_border='#cccccc',
    annotation_font='#333333',
    tag_bg='#e8f0fe', tag_fg='#1a4a80',
    contour_color='#555555',        # contour lines on heatmaps
    contour_label='#333333',
)

_DARK_PALETTE = dict(
    plot_bg='#1e1e2e', paper_bg='#1e1e2e', font_color='#e0e0e0', title_color='#f0f0f0',
    grid_color='#3a3a4a', line_color='#aaaaaa', tick_color='#aaaaaa',
    legend_bg='rgba(30,30,46,0.9)', legend_border='#555555',
    app_bg='#181825', sidebar_bg='#1e1e2e', heading_color='#f0f0f0',
    card_bg='#2a2a3c', card_border='#444466', card_shadow='rgba(0,0,0,0.3)',
    label_color='#aaaaaa', value_color='#f0f0f0', sub_color='#999999',
    muted_color='#bbbbbb',
    annotation_bg='rgba(42,42,60,0.9)', annotation_border='#555555',
    annotation_font='#e0e0e0',
    tag_bg='#2a3a5c', tag_fg='#9ec5fe',
    contour_color='#cccccc',
    contour_label='#e0e0e0',
)


def _build_axis(palette: dict) -> dict:
    return dict(
        showgrid=True, gridcolor=palette['grid_color'], gridwidth=1,
        linecolor=palette['line_color'], linewidth=1, mirror=True,
        ticks='outside', tickcolor=palette['tick_color'],
    )


def _build_plotly_theme(palette: dict) -> dict:
    ax = _build_axis(palette)
    return dict(
        plot_bgcolor=palette['plot_bg'],
        paper_bgcolor=palette['paper_bg'],
        font=dict(family='serif', size=13, color=palette['font_color']),
        xaxis=dict(**ax),
        yaxis=dict(**ax),
        title=dict(font=dict(size=15, family='serif', color=palette['title_color'])),
        legend=dict(
            bgcolor=palette['legend_bg'],
            bordercolor=palette['legend_border'], borderwidth=1,
        ),
    )


# Module-level dict — mutated in-place by inject_theme() so all importers
# automatically get the active theme via **PLOTLY_THEME spreads.
PLOTLY_THEME: dict = _build_plotly_theme(_DARK_PALETTE)


def apply_theme(fig, **overrides):
    """Apply scientific Plotly theme to *fig*, with optional overrides."""
    merged = {**PLOTLY_THEME, **overrides}
    fig.update_layout(**merged)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# CSS theme
# ─────────────────────────────────────────────────────────────────────────────

def _build_css(palette: dict) -> str:
    """CSS for custom HTML elements only — Streamlit native elements are
    handled by .streamlit/config.toml [theme] base = "dark"."""
    return f"""
<style>
/* Headings: serif font (Streamlit handles color) */
h1, h2, h3 {{ font-family: serif; }}
/* Metric cards (custom HTML) */
.metric-card {{
    background: {palette['card_bg']};
    border-radius: 10px;
    padding: 16px 20px;
    text-align: center;
    border: 1px solid {palette['card_border']};
    box-shadow: 0 1px 3px {palette['card_shadow']};
}}
.metric-card .label {{
    font-size: 0.82rem;
    color: {palette['label_color']};
    text-transform: uppercase;
    letter-spacing: 0.05em;
}}
.metric-card .value {{
    font-size: 2rem;
    font-weight: 700;
    color: {palette['value_color']};
    margin-top: 4px;
}}
.metric-card .sub {{
    font-size: 0.78rem;
    color: {palette['sub_color']};
    margin-top: 2px;
}}
.status-chip-binary {{ color: #E25A53; font-weight: 600; }}
.status-chip-single {{ color: #4A90D9; }}
.status-chip-unknown {{ color: #8C8C8C; }}
/* Hide the auto-generated Streamlit page navigation (keep custom render_sidebar) */
[data-testid="stSidebarNav"] {{ display: none; }}
</style>
"""


def inject_theme() -> None:
    """Mutate PLOTLY_THEME in-place for dark mode, inject minimal CSS.
    Streamlit native elements are handled by .streamlit/config.toml."""
    # Always dark — config.toml sets base = "dark"
    palette = _DARK_PALETTE
    st.session_state['_dark_mode'] = True

    # Mutate PLOTLY_THEME in-place so all **PLOTLY_THEME spreads pick it up
    PLOTLY_THEME.clear()
    PLOTLY_THEME.update(_build_plotly_theme(palette))

    st.markdown(_build_css(palette), unsafe_allow_html=True)


def get_palette() -> dict:
    """Return the active color palette dict for use in page code."""
    dark = bool(st.session_state.get('_dark_mode', False))
    return _DARK_PALETTE if dark else _LIGHT_PALETTE


# ─────────────────────────────────────────────────────────────────────────────
# SettingsManager
# ─────────────────────────────────────────────────────────────────────────────

class SettingsManager:
    """
    Manages user_settings.json with immediate persistence and state snapshots.

    Usage in a Streamlit page:
        sm = get_settings_manager()
        settings = sm.load()
        sm.save(['classification', 'threshold_dRV'], value=50.0)
    """

    def load(self) -> dict:
        """Load settings (cached in session_state; reads disk only once per session)."""
        if '_settings' not in st.session_state:
            st.session_state['_settings'] = self._read_disk()
        return st.session_state['_settings']

    def save(self, keys: list[str] | str, value: Any) -> None:
        """
        Update a (possibly nested) key and write immediately to disk.

        Examples:
            sm.save('primary_line', value='He II 4686')
            sm.save(['classification', 'threshold_dRV'], value=50.0)
        """
        settings = self.load()
        if isinstance(keys, str):
            keys = [keys]
        d = settings
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value
        self._write_disk(settings)

    def reload(self) -> dict:
        """Force re-read from disk (clears session_state cache)."""
        if '_settings' in st.session_state:
            del st.session_state['_settings']
        return self.load()

    # ── State snapshots ────────────────────────────────────────────────────

    def save_state(self, name: str) -> str:
        """
        Snapshot current settings + UI state → settings/states/{ts}_{name}.json.
        Returns the saved file path.
        """
        os.makedirs(_STATES_DIR, exist_ok=True)
        ts       = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'{ts}_{name.replace(" ", "_")}.json'
        path     = os.path.join(_STATES_DIR, filename)
        snapshot = {
            'name':      name,
            'timestamp': datetime.now().isoformat(),
            'settings':  self.load(),
            'ui': {
                'last_star':   st.session_state.get('last_star'),
                'last_epoch':  st.session_state.get('last_epoch'),
                'last_band':   st.session_state.get('last_band'),
                'last_result': st.session_state.get('last_result'),
                'last_page':   st.session_state.get('last_page'),
            },
        }
        with open(path, 'w') as f:
            json.dump(snapshot, f, indent=2, default=str)
        return path

    def load_state(self, name_or_path: str) -> dict:
        """
        Restore settings from a state file.
        `name_or_path` can be the state file name (in states/) or a full path.
        Returns the restored settings dict.
        """
        if os.path.isabs(name_or_path):
            path = name_or_path
        else:
            path = os.path.join(_STATES_DIR, name_or_path)
        with open(path) as f:
            snap = json.load(f)
        settings = snap['settings']
        self._write_disk(settings)
        st.session_state['_settings'] = settings
        # restore UI state
        for k, v in snap.get('ui', {}).items():
            if v is not None:
                st.session_state[k] = v
        return settings

    def list_states(self) -> list[dict]:
        """Return sorted list of saved state dicts (newest first)."""
        os.makedirs(_STATES_DIR, exist_ok=True)
        out = []
        for fname in sorted(os.listdir(_STATES_DIR), reverse=True):
            if not fname.endswith('.json'):
                continue
            path = os.path.join(_STATES_DIR, fname)
            try:
                with open(path) as f:
                    meta = json.load(f)
                out.append({
                    'filename':  fname,
                    'path':      path,
                    'name':      meta.get('name', fname),
                    'timestamp': meta.get('timestamp', ''),
                })
            except Exception:
                pass
        return out

    # ── Presets ─────────────────────────────────────────────────────────────

    def save_preset(self, name: str) -> str:
        """Save current settings (no UI state) to settings/presets/{name}.json."""
        os.makedirs(_PRESETS_DIR, exist_ok=True)
        path = os.path.join(_PRESETS_DIR, f'{name.replace(" ", "_")}.json')
        with open(path, 'w') as f:
            json.dump(self.load(), f, indent=2, default=str)
        return path

    def load_preset(self, name: str) -> dict:
        """Load a preset by name (without .json extension) and apply it."""
        path = os.path.join(_PRESETS_DIR, f'{name.replace(" ", "_")}.json')
        with open(path) as f:
            settings = json.load(f)
        self._write_disk(settings)
        st.session_state['_settings'] = settings
        return settings

    def list_presets(self) -> list[str]:
        os.makedirs(_PRESETS_DIR, exist_ok=True)
        return [f[:-5] for f in os.listdir(_PRESETS_DIR) if f.endswith('.json')]

    # ── Internal ─────────────────────────────────────────────────────────────

    @staticmethod
    def _read_disk() -> dict:
        if os.path.exists(_SETTINGS_PATH):
            with open(_SETTINGS_PATH) as f:
                return json.load(f)
        return {}

    @staticmethod
    def _write_disk(settings: dict) -> None:
        os.makedirs(os.path.dirname(_SETTINGS_PATH), exist_ok=True)
        with open(_SETTINGS_PATH, 'w') as f:
            json.dump(settings, f, indent=2, default=str)


@st.cache_resource
def get_settings_manager() -> SettingsManager:
    return SettingsManager()


# ─────────────────────────────────────────────────────────────────────────────
# ObservationManager singleton
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def get_obs_manager() -> _OM:
    """One ObservationManager per session — shared across all pages."""
    return _OM(
        data_dir   = os.path.join(_ROOT, 'Data/'),
        backup_dir = os.path.join(_ROOT, 'Backups/'),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Run history helper
# ─────────────────────────────────────────────────────────────────────────────

def load_run_history() -> list[dict]:
    if not os.path.exists(_RUN_HISTORY_PATH):
        return []
    try:
        with open(_RUN_HISTORY_PATH) as f:
            return json.load(f)
    except (json.JSONDecodeError, ValueError):
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Cached data loaders (to avoid re-loading on every Streamlit re-render)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data
def cached_load_observed_delta_rvs(settings_hash: str) -> tuple[np.ndarray, dict]:
    """
    Load observed ΔRVs. settings_hash is only used as cache key.
    Call with: cached_load_observed_delta_rvs(settings_hash(settings))
    Only primary_line + classification affect this result — NOT ui/ccf/grid keys.
    """
    from pipeline.load_observations import load_observed_delta_rvs
    sm = get_settings_manager()
    return load_observed_delta_rvs(sm.load(), get_obs_manager())


@st.cache_data
def cached_load_cadence(_hash: str) -> tuple[list, np.ndarray]:
    from pipeline.load_observations import load_cadence_library
    return load_cadence_library(get_obs_manager())


@st.cache_data
def cached_load_grid_result(model: str, path: str | None = None) -> dict | None:
    """Load an existing grid .npz result. Returns None if file doesn't exist.

    If *path* is given, load from that file; otherwise use the legacy
    ``results/{model}_result.npz``.
    """
    if path is None:
        path = os.path.join(_ROOT, 'results', f'{model}_result.npz')
    if not os.path.exists(path):
        return None
    try:
        return dict(np.load(path, allow_pickle=True))
    except Exception:
        return None


def settings_hash(settings: dict) -> str:
    """
    Hash ONLY classification-relevant keys (primary_line + classification).
    Excludes ui/ccf/grid/simulation so that page navigation never invalidates
    the classification cache.
    """
    relevant = {
        'primary_line':   settings.get('primary_line'),
        'classification': settings.get('classification'),
    }
    return hashlib.sha256(
        json.dumps(relevant, sort_keys=True, default=str).encode()
    ).hexdigest()[:12]


def preload_all_data(settings: dict) -> None:
    """
    Warm all st.cache_data caches once at session startup.
    After this returns, every page gets data from memory with no disk I/O.
    Call from app.py when st.session_state['_preloaded'] is False.
    """
    sh = settings_hash(settings)
    cached_load_observed_delta_rvs(sh)   # warms RV + classification cache
    cached_load_cadence(sh)              # warms MJD cadence cache
    # Pre-load any existing grid results into session_state
    for model in ('dsilva', 'langer'):
        key = f'result_{model}'
        if key not in st.session_state:
            result = cached_load_grid_result(model)
            if result is not None:
                st.session_state[key] = result
    st.session_state['_preloaded'] = True


# ─────────────────────────────────────────────────────────────────────────────
# Shared analysis utilities (used by home page + bias correction)
# ─────────────────────────────────────────────────────────────────────────────

def find_best_grid_point(
    ks_p_2d: np.ndarray,
    fbin_vals: np.ndarray,
    x_vals: np.ndarray,
) -> tuple[float, float, float]:
    """Return (best_fbin, best_x, best_pval) from a 2-D K-S p-value grid."""
    idx = int(np.argmax(ks_p_2d))
    fi = idx // ks_p_2d.shape[1]
    pi = idx % ks_p_2d.shape[1]
    return float(fbin_vals[fi]), float(x_vals[pi]), float(ks_p_2d[fi, pi])


def make_heatmap_fig(
    ks_p_2d: np.ndarray,
    fbin_vals: np.ndarray,
    x_vals: np.ndarray,
    title: str,
    show_d: bool = False,
    ks_d_2d: np.ndarray | None = None,
    height: int = 520,
    width: int | None = None,
    x_label: str = 'π  (period power-law index)',
    y_label: str = 'f_bin  (intrinsic binary fraction)',
    x_name: str = 'π',
    best_label_fmt: str = '  f={fbin:.3f}, {x_name}={x:.2f}, p={p:.3f}',
    live: bool = False,
) -> 'go.Figure':
    """Plotly heatmap of K-S p-value (or D-stat) with contour lines and best-fit star."""
    import plotly.graph_objects as go

    z = ks_d_2d if (show_d and ks_d_2d is not None) else ks_p_2d
    colorbar_title = 'K-S D' if show_d else 'K-S p-value'

    valid = z[~np.isnan(z)]
    z_max = float(np.percentile(valid, 98)) if valid.size > 0 else 1.0
    z_min = 0.0

    best_fbin, best_x, best_pval = find_best_grid_point(ks_p_2d, fbin_vals, x_vals)

    traces: list = [
        go.Heatmap(
            z=z, x=x_vals, y=fbin_vals,
            colorscale='RdBu_r',
            zmin=z_min, zmax=z_max,
            zsmooth='best',
            colorbar=dict(title=colorbar_title, thickness=14, len=0.9),
            hovertemplate=f'{x_name}=%{{x:.3f}}<br>f_bin=%{{y:.4f}}<br>' + colorbar_title +
                          '=%{z:.4f}<extra></extra>',
        ),
    ]

    if not live:
        pal = get_palette()
        traces.append(go.Contour(
            z=ks_p_2d, x=x_vals, y=fbin_vals,
            contours=dict(
                coloring='none',
                showlabels=True,
                labelfont=dict(size=10, color=pal['contour_label']),
                start=0.05, end=0.30, size=0.05,
            ),
            line=dict(color=pal['contour_color'], width=1, dash='dot'),
            showscale=False,
            hoverinfo='skip',
        ))
        traces.append(go.Scatter(
            x=[best_x], y=[best_fbin],
            mode='markers+text',
            marker=dict(symbol='star', size=18, color='gold',
                        line=dict(color=pal['plot_bg'], width=1)),
            text=[best_label_fmt.format(fbin=best_fbin, x_name=x_name,
                                        x=best_x, p=best_pval)],
            textposition='middle right',
            textfont=dict(color='#DAA520', size=11),
            name='Best fit',
            showlegend=False,
        ))

    layout_kw: dict = {
        **PLOTLY_THEME,
        'title': dict(text=title, font=dict(size=14)),
        'xaxis_title': x_label,
        'yaxis_title': y_label,
        'height': height,
        'margin': dict(l=60, r=20, t=50, b=50),
    }
    if width is not None:
        layout_kw['width'] = width

    fig = go.Figure(traces)
    fig.update_layout(**layout_kw)
    return fig


@st.cache_data
def cached_load_nres_rvs() -> dict:
    """Load NRES star RVs. Returns empty dict if no NRES data available."""
    nres_dir = os.path.join(_ROOT, 'Data')
    result: dict = {}
    if not os.path.isdir(nres_dir):
        return result
    try:
        from NRESClass import NRES
        om = get_obs_manager()
        for star_name in specs.star_names:
            try:
                obs = om.load_observation(star_name)
                if hasattr(obs, 'nres_epochs') and obs.nres_epochs:
                    result[star_name] = {'n_epochs': len(obs.nres_epochs)}
            except Exception:
                continue
    except ImportError:
        pass
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

def render_sidebar(page_name: str = '') -> dict:
    """
    Render the persistent sidebar — call at top of every page.
    Returns the current settings dict.
    """
    sm = get_settings_manager()
    settings = sm.load()

    if page_name:
        st.session_state['last_page'] = page_name

    with st.sidebar:
        st.markdown('## WR Binary Analysis')
        st.markdown('---')

        # ── Quick metrics chip ────────────────────────────────────────────
        cls = settings.get('classification', {})
        threshold = cls.get('threshold_dRV', 45.5)
        line      = settings.get('primary_line', 'C IV 5808-5812')
        bartzakos = cls.get('bartzakos_binaries', 3)
        total_pop = cls.get('total_population', 28)

        _pal = get_palette()
        st.markdown(f"""
        <div style="font-size:0.78rem; color:{_pal['muted_color']};">
        🔭 <b>Line:</b> {line}<br>
        📐 <b>Threshold:</b> {threshold:.1f} km/s<br>
        ⭐ <b>Bartzakos binaries:</b> {bartzakos}/{total_pop}
        </div>
        """, unsafe_allow_html=True)

        st.markdown('---')

        # ── Navigation quick-links ────────────────────────────────────────
        st.markdown('**Navigation**')
        st.page_link('app.py',            label='🏠 Home')
        st.page_link('pages/01_stars.py', label='⭐ Stars')
        st.page_link('pages/02_spectrum.py', label='📊 Spectrum')
        st.page_link('pages/03_ccf.py',   label='🔄 CCF')
        st.page_link('pages/04_classification.py', label='🎯 Classification')
        st.page_link('pages/11_nres_analysis.py', label='🔭 NRES')
        st.page_link('pages/12_rv_modeling.py', label='📈 RV Modeling')
        st.page_link('pages/05_bias_correction.py', label='⚡ Bias Correction')
        st.page_link('pages/06_plots.py', label='🖼️ Plots')
        st.page_link('pages/07_tables.py', label='📋 Tables')
        st.page_link('pages/08_results.py', label='📈 Results')
        st.page_link('pages/09_settings.py', label='⚙️ Settings')
        st.page_link('pages/10_todo.py', label='📝 To-Do')

        st.markdown('---')

        st.markdown('---')

        # ── Save / Load state ─────────────────────────────────────────────
        st.markdown('**State Management**')
        state_name = st.text_input('State name', key='_sidebar_state_name',
                                   placeholder='e.g. dsilva_run1')
        if st.button('💾 Save current state', key='_sidebar_save_state'):
            if state_name.strip():
                path = sm.save_state(state_name.strip())
                st.success(f'Saved: {os.path.basename(path)}')
            else:
                st.warning('Enter a state name first.')

        states = sm.list_states()
        if states:
            state_opts = {s['name'] + '  (' + s['timestamp'][:16] + ')': s['path']
                          for s in states}
            chosen = st.selectbox('Load state', ['—'] + list(state_opts.keys()),
                                  key='_sidebar_load_state_sel')
            if chosen != '—' and st.button('↩️ Restore', key='_sidebar_restore'):
                sm.load_state(state_opts[chosen])
                st.rerun()

        st.markdown('---')

        # ── Memory management ─────────────────────────────────────────────
        if st.button('🗑️ Clear cache', key='_sidebar_clear_cache'):
            st.cache_data.clear()
            gc.collect()
            st.success('Cache cleared.')

    return settings
