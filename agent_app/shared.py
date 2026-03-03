"""
agent_app/shared.py
───────────────────
Shared utilities for the Agent Control Panel webapp:
  - AgentSettingsManager  : load/save agent_settings.json
  - render_sidebar        : persistent sidebar on every page
  - CSS theme injection (VS Code dark theme)
  - Colour constants for pipeline stages
"""

from __future__ import annotations

import gc
import json
import os
import sys
from typing import Any

import streamlit as st

# ── Path fix ──────────────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────
SCRIPTS_DIR       = os.path.join(_ROOT, 'scripts')
AGENT_SETTINGS    = os.path.join(SCRIPTS_DIR, 'agent_settings.json')
AGENT_STATE       = os.path.join(SCRIPTS_DIR, '.agent_state.json')
AGENT_PID         = os.path.join(SCRIPTS_DIR, '.agent.pid')
AGENT_LOG         = os.path.join(SCRIPTS_DIR, 'agent_log.md')
AGENT_WORK_DIR    = os.path.join(SCRIPTS_DIR, '.agent_work')
AGENT_NOTES_DIR   = os.path.join(SCRIPTS_DIR, '.agent_notes')

# ─────────────────────────────────────────────────────────────────────────────
# Colour constants for pipeline stages
# ─────────────────────────────────────────────────────────────────────────────
COLOR_DONE       = '#52B788'   # green
COLOR_ACTIVE     = '#F5A623'   # amber
COLOR_FAILED     = '#E25A53'   # red
COLOR_PENDING    = '#555555'   # grey (visible on dark bg)
COLOR_WAITING    = '#FFD700'   # gold — awaiting human
COLOR_RUNNING    = '#4A90D9'   # steel blue

STAGE_COLORS = {
    'done':        COLOR_DONE,
    'in_progress': COLOR_ACTIVE,
    'failed':      COLOR_FAILED,
    'pending':     COLOR_PENDING,
    'waiting':     COLOR_WAITING,
}

AGENT_ROLES = [
    'planner', 'reviewer', 'implementer', 'tester',
    'regression', 'fix_planner', 'fix_implementer',
]

PIPELINE_STAGES = ['planner', 'reviewer', 'implementer', 'tester', 'regression']

# ─────────────────────────────────────────────────────────────────────────────
# CSS theme (VS Code dark theme)
# ─────────────────────────────────────────────────────────────────────────────
_THEME_CSS = """
<style>
/* ── VS Code Dark Theme ─────────────────────────────────────────────────── */

/* Backgrounds */
[data-testid="stAppViewContainer"] {
    background-color: #1e1e1e;
}
[data-testid="stSidebar"] {
    background-color: #252526;
}
[data-testid="stHeader"] {
    background-color: #1e1e1e;
}

/* ── Light text on ALL elements ─────────────────────────────────────────── */
[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] p,
[data-testid="stAppViewContainer"] span,
[data-testid="stAppViewContainer"] label,
[data-testid="stAppViewContainer"] li,
[data-testid="stAppViewContainer"] td,
[data-testid="stAppViewContainer"] th,
[data-testid="stAppViewContainer"] div,
[data-testid="stMarkdownContainer"],
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] td,
[data-testid="stMarkdownContainer"] th,
[data-testid="stMarkdownContainer"] span {
    color: #d4d4d4;
}

/* Sidebar text */
[data-testid="stSidebar"],
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] li,
[data-testid="stSidebar"] div,
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
    color: #d4d4d4;
}

/* Headings */
h1, h2, h3 { color: #e0e0e0; font-family: sans-serif; }

/* Form elements */
[data-testid="stAppViewContainer"] input,
[data-testid="stAppViewContainer"] textarea,
[data-testid="stAppViewContainer"] select,
[data-testid="stSidebar"] input,
[data-testid="stSidebar"] textarea,
[data-testid="stSidebar"] select {
    color: #d4d4d4 !important;
    background-color: #3c3c3c !important;
    border-color: #555555 !important;
}

/* Tab labels */
[data-testid="stAppViewContainer"] button[data-baseweb="tab"] {
    color: #d4d4d4;
}

/* Selectbox / multiselect text */
[data-testid="stAppViewContainer"] [data-baseweb="select"] span,
[data-testid="stSidebar"] [data-baseweb="select"] span {
    color: #d4d4d4 !important;
}

/* Dropdown menus */
[data-baseweb="popover"],
[data-baseweb="popover"] li,
[data-baseweb="menu"],
[data-baseweb="menu"] li {
    background-color: #2d2d2d !important;
    color: #d4d4d4 !important;
}

/* Code blocks */
[data-testid="stAppViewContainer"] code {
    color: #ce9178;
    background-color: #1a1a1a;
}

/* Links */
a { color: #569cd6; }
a:hover { color: #9cdcfe; }

/* Buttons — primary */
[data-testid="stAppViewContainer"] button[kind="primary"],
[data-testid="stSidebar"] button[kind="primary"] {
    background-color: #0e639c;
    color: #ffffff;
    border-color: #0e639c;
}

/* Buttons — secondary */
[data-testid="stAppViewContainer"] button[kind="secondary"],
[data-testid="stSidebar"] button[kind="secondary"] {
    background-color: #3c3c3c;
    color: #d4d4d4;
    border-color: #555555;
}

/* ── Custom components ──────────────────────────────────────────────────── */

.metric-card {
    background: #2d2d2d;
    border-radius: 10px;
    padding: 16px 20px;
    text-align: center;
    border: 1px solid #404040;
    box-shadow: 0 1px 3px rgba(0,0,0,0.3);
}
.metric-card .label {
    font-size: 0.82rem;
    color: #9a9a9a;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.metric-card .value {
    font-size: 2rem;
    font-weight: 700;
    color: #e0e0e0;
    margin-top: 4px;
}
.metric-card .sub {
    font-size: 0.78rem;
    color: #777777;
    margin-top: 2px;
}
/* Pipeline stage boxes */
.stage-box {
    display: inline-block;
    padding: 8px 16px;
    border-radius: 6px;
    margin: 2px 4px;
    font-size: 0.85rem;
    font-weight: 600;
    text-align: center;
    min-width: 100px;
}
.stage-arrow {
    display: inline-block;
    color: #666;
    font-size: 1.2rem;
    vertical-align: middle;
    margin: 0 2px;
}
/* Intervention banner */
.intervention-banner {
    background: #3d3520;
    border: 2px solid #B8860B;
    border-radius: 8px;
    padding: 16px 20px;
    margin: 12px 0;
}
.intervention-banner .title {
    font-size: 1.1rem;
    font-weight: 700;
    color: #FFD700;
}
.intervention-banner .detail {
    font-size: 0.9rem;
    color: #b0b0b0;
    margin-top: 6px;
}
/* Expander styling */
[data-testid="stExpander"] {
    background-color: #2d2d2d;
    border-color: #404040;
}
/* Divider / hr */
hr { border-color: #404040; }
/* Hide the auto-generated Streamlit page navigation */
[data-testid="stSidebarNav"] { display: none; }
</style>
"""


def inject_theme() -> None:
    st.markdown(_THEME_CSS, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# AgentSettingsManager
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULTS: dict = {
    'default_quadrant': 'eliminate',
    'max_tasks': None,
    'include_critical': False,
    'rate_limit_sleep': 300,
    'max_fix_attempts': 2,
    'timeouts': {
        'planner': 1200, 'reviewer': 300, 'implementer': 1500,
        'tester': 300, 'regression': 300,
        'fix_planner': 300, 'fix_implementer': 600,
    },
    'intervention': {
        'wait_on_reject': True,
        'wait_on_fail': True,
        'timeout_seconds': 1800,
        'auto_replan_max': 0,
        'auto_skip_test_max': 0,
    },
    'auto_learn': False,
}


class AgentSettingsManager:
    """Load/save scripts/agent_settings.json with immediate persistence."""

    def load(self) -> dict:
        if '_agent_settings' not in st.session_state:
            st.session_state['_agent_settings'] = self._read_disk()
        return st.session_state['_agent_settings']

    def save(self, keys: list[str] | str, value: Any) -> None:
        settings = self.load()
        if isinstance(keys, str):
            keys = [keys]
        d = settings
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value
        self._write_disk(settings)

    def reload(self) -> dict:
        if '_agent_settings' in st.session_state:
            del st.session_state['_agent_settings']
        return self.load()

    @staticmethod
    def _read_disk() -> dict:
        if os.path.exists(AGENT_SETTINGS):
            with open(AGENT_SETTINGS) as f:
                loaded = json.load(f)
            # Merge with defaults for missing keys
            merged = {**_DEFAULTS}
            for k, v in loaded.items():
                if isinstance(v, dict) and isinstance(merged.get(k), dict):
                    merged[k] = {**merged[k], **v}
                else:
                    merged[k] = v
            return merged
        return dict(_DEFAULTS)

    @staticmethod
    def _write_disk(settings: dict) -> None:
        os.makedirs(os.path.dirname(AGENT_SETTINGS), exist_ok=True)
        with open(AGENT_SETTINGS, 'w') as f:
            json.dump(settings, f, indent=2, default=str)


@st.cache_resource
def get_agent_settings_manager() -> AgentSettingsManager:
    return AgentSettingsManager()


# ─────────────────────────────────────────────────────────────────────────────
# Helper: metric card
# ─────────────────────────────────────────────────────────────────────────────

def metric_card(container, label: str, value: str, sub: str = '',
                color: str | None = None) -> None:
    val_style = f'color: {color};' if color else ''
    container.markdown(f"""
    <div class="metric-card">
        <div class="label">{label}</div>
        <div class="value" style="{val_style}">{value}</div>
        <div class="sub">{sub}</div>
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: pipeline stage visualization
# ─────────────────────────────────────────────────────────────────────────────

def render_pipeline_stages(stages_done: list[str], current_stage: str | None,
                           failed_stage: str | None = None,
                           waiting: bool = False) -> str:
    """Return HTML for horizontal pipeline visualization."""
    html_parts = []
    for i, stage in enumerate(PIPELINE_STAGES):
        if stage in stages_done:
            bg = COLOR_DONE
            fg = '#fff'
        elif stage == current_stage and waiting:
            bg = COLOR_WAITING
            fg = '#1e1e1e'
        elif stage == current_stage:
            bg = COLOR_ACTIVE
            fg = '#fff'
        elif stage == failed_stage:
            bg = COLOR_FAILED
            fg = '#fff'
        else:
            bg = COLOR_PENDING
            fg = '#ccc'
        label = stage.replace('_', ' ').title()
        html_parts.append(
            f'<span class="stage-box" style="background:{bg};color:{fg};">'
            f'{label}</span>'
        )
        if i < len(PIPELINE_STAGES) - 1:
            html_parts.append('<span class="stage-arrow">&rarr;</span>')
    return ''.join(html_parts)


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

def render_sidebar(page_name: str = '') -> dict:
    """Render the persistent sidebar — call at top of every page."""
    from agent_comm import get_state, is_running

    asm = get_agent_settings_manager()
    settings = asm.load()

    if page_name:
        st.session_state['last_agent_page'] = page_name

    state = get_state()
    running = is_running()

    with st.sidebar:
        st.markdown('## Agent Control Panel')
        st.markdown('---')

        # ── Status chip ──────────────────────────────────────────────────
        if state and state.get('awaiting_intervention'):
            status_text = 'WAITING'
            status_color = COLOR_WAITING
        elif running:
            status_text = 'RUNNING'
            status_color = COLOR_RUNNING
        else:
            status_text = 'STOPPED'
            status_color = COLOR_FAILED

        task_info = ''
        if state and state.get('current_task_id'):
            tid = state['current_task_id']
            title = state.get('current_task_title', '')
            stage = state.get('current_stage', '?')
            task_info = f'Task #{tid}: {title}<br>Stage: {stage}'

        st.markdown(f"""
        <div style="font-size:0.82rem;">
        <span style="color:{status_color}; font-weight:700; font-size:1rem;">
        &#9679; {status_text}</span><br>
        {task_info}
        </div>
        """, unsafe_allow_html=True)

        st.markdown('---')

        # ── Navigation ───────────────────────────────────────────────────
        st.markdown('**Navigation**')
        st.page_link('app.py',                       label='Dashboard')
        st.page_link('pages/01_pipeline.py',         label='Pipeline Monitor')
        st.page_link('pages/02_artifacts.py',        label='Artifacts')
        st.page_link('pages/03_branches.py',         label='Branches')
        st.page_link('pages/04_interventions.py',    label='Interventions')
        st.page_link('pages/05_notes.py',            label='Agent Notes')
        st.page_link('pages/06_settings.py',         label='Settings')
        st.page_link('pages/07_log.py',              label='Log Viewer')

        st.markdown('---')

        # ── Quick stop button ────────────────────────────────────────────
        if running:
            if st.button('Stop Agent', type='primary', key='_sidebar_stop'):
                from agent_comm import stop_agent
                ok = stop_agent()
                if ok:
                    st.success('Agent stopped.')
                else:
                    st.warning('Could not stop agent.')
                st.rerun()

        # ── Clear cache ──────────────────────────────────────────────────
        if st.button('Clear cache', key='_sidebar_clear_cache'):
            st.cache_data.clear()
            gc.collect()
            st.success('Cache cleared.')

    return settings
