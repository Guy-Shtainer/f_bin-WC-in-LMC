"""bc.polling_langer — Langer-specific live-polling UI.

Duplicate of polling.py with f_bin×π heatmaps removed.
H1-H4 (_render_top_heatmaps_langer) handle all heatmap display.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import streamlit as st

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from shared import cached_load_grid_result
from bc.helpers import (
    _scan_partial_metadata, _scan_result_metadata,
)


def _poll_cadence_job_langer(p: str) -> str:
    """Handle running / error / cancelled / done job states (Langer version).

    Same as _poll_cadence_job but without f_bin×π heatmap rendering.
    H1-H4 handle all heatmap display after completion.
    """
    _job = st.session_state.get(f'{p}_job')
    _saved_result = st.session_state.get(f'{p}_result')

    if _job is None and _saved_result is None:
        st.info('Configure parameters and click **Run** to start a '
                'cadence-aware simulation.')
        return 'idle'

    if _job is None and _saved_result is not None:
        return 'done'

    status = _job.get('status', 'idle') if _job else 'idle'

    if status == 'running':
        _render_running_fragment_langer(p)
        return 'running'

    if status == 'error':
        st.error(
            f"Simulation failed:\n```\n{_job.get('error', 'Unknown')}\n```")
        del st.session_state[f'{p}_job']
        return 'error'

    if status == 'cancelled':
        _partial_saved = _job.get('partial_saved', False) if _job else False
        if _partial_saved:
            st.warning('Simulation cancelled \u2014 partial progress saved.')
            _scan_partial_metadata.clear()
        else:
            st.warning('Simulation was cancelled.')
        del st.session_state[f'{p}_job']
        return 'cancelled'

    # status == 'done' with a job dict still present
    if _job is not None and _job.get('result'):
        result = _job['result']
        st.session_state[f'{p}_result'] = result
        del st.session_state[f'{p}_job']
        cached_load_grid_result.clear()
        _scan_result_metadata.clear()

    # No final heatmap rendering — H1-H4 handle everything
    return 'done'


def _render_running_fragment_langer(p: str) -> None:
    """Langer live-polling fragment: progress bar + live H1-H4 heatmaps.

    Renders _render_top_heatmaps_langer with partial logL_raw data
    every 3 seconds. No f_bin×π heatmap.
    """
    @st.fragment(run_every=3)
    def _cadence_live_poll():
        _j = st.session_state.get(f'{p}_job')
        if _j is None or _j.get('status') != 'running':
            st.rerun(scope='app')
            return
        st.progress(_j.get('progress_pct', 0),
                    text=_j.get('progress_text', 'Running...'))
        # Live H1-H4 heatmaps from partial logL_raw
        _logL_live = _j.get('_logL_raw_live')
        _grids = _j.get('_grids')
        if _logL_live is not None and _grids is not None:
            _lk_max = float(np.nanmax(_logL_live))
            if np.isfinite(_lk_max):
                _lk_norm = np.exp(_logL_live - _lk_max)
            else:
                _lk_norm = np.zeros_like(_logL_live)
            _partial = {'likelihood': _lk_norm, 'logL_raw': _logL_live}
            from bc.cadence import _render_top_heatmaps_langer
            _render_top_heatmaps_langer(
                p, _partial,
                np.asarray(_grids['fbin_grid']),
                np.asarray(_grids['pi_grid']),
                np.asarray(_grids['sigma_grid']),
                np.asarray(_grids['logPmax_grid']),
                _lk_norm, 0, False, 400, True,
            )
        if _j.get('live_status'):
            st.markdown(_j['live_status'])
    _cadence_live_poll()
