"""bc.polling — Live-polling UI for background simulation jobs."""
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
    _METHOD_SCORING_LABELS, _METHOD_COLORBAR_OVERRIDE,
    _scan_partial_metadata, _scan_result_metadata,
    _make_max_pval_fig, _make_heatmap_fig,
)


def _poll_cadence_job(p: str) -> str:
    """Handle running / error / cancelled / done job states.

    Returns the current status string ('running', 'error', 'cancelled',
    'done', or 'idle') so the caller knows whether to proceed to analysis.
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
        _render_running_fragment(p)
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
        if _job.get('live_heatmaps'):
            st.session_state[f'{p}_final_live_heatmaps'] = (
                _job['live_heatmaps'])
        if _job.get('live_sigma_1d'):
            st.session_state[f'{p}_final_live_sigma_1d'] = (
                _job['live_sigma_1d'])
        if _job.get('live_logPmax_1d'):
            st.session_state[f'{p}_final_live_logPmax_1d'] = (
                _job['live_logPmax_1d'])
        del st.session_state[f'{p}_job']
        cached_load_grid_result.clear()
        _scan_result_metadata.clear()

    # Show persisted final live heatmaps (survive job cleanup)
    _render_final_heatmaps(p)
    _render_final_sigma_1d(p)

    return 'done'


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _render_heatmap_row(pairs, lhm):
    """Render a row of 2 live/final heatmaps."""
    c1, c2 = st.columns(2)
    for mk, col in pairs:
        if mk in lhm:
            hd = lhm[mk]
            with col:
                st.plotly_chart(
                    _make_heatmap_fig(
                        hd['p'] if mk == 'likelihood' else hd['d'],
                        hd['fbin'], hd['x'],
                        title=hd['title'], height=300,
                        live=not hd.get('is_final', True),
                        scoring_label=_METHOD_SCORING_LABELS[mk],
                        colorbar_title_override=(
                            _METHOD_COLORBAR_OVERRIDE.get(mk))),
                    use_container_width=True)


def _render_running_fragment(p: str) -> None:
    """Streamlit fragment that polls a running cadence job every 3s."""
    @st.fragment(run_every=3)
    def _cadence_live_poll():
        _j = st.session_state.get(f'{p}_job')
        if _j is None or _j.get('status') != 'running':
            st.rerun(scope='app')
            return
        st.progress(_j.get('progress_pct', 0),
                    text=_j.get('progress_text', 'Running...'))
        if _j.get('live_heatmaps'):
            _lhm = _j['live_heatmaps']
            # Single likelihood tile (full width)
            if 'likelihood' in _lhm:
                _hd = _lhm['likelihood']
                st.plotly_chart(
                    _make_heatmap_fig(
                        _hd['p'], _hd['fbin'], _hd['x'],
                        title=_hd['title'], height=400,
                        live=not _hd.get('is_final', True),
                        scoring_label='Likelihood',
                        colorbar_title_override='Normalized Likelihood'),
                    use_container_width=True)
        if _j.get('live_status'):
            st.markdown(_j['live_status'])
        # Live 1D sigma graph (likelihood only)
        _lsig = _j.get('live_sigma_1d')
        if _lsig and len(_lsig.get('sigma_vals', [])) > 1:
            _lsig_lk = _lsig.get('max_likelihood', [])
            if _lsig_lk and any(v > 0 for v in _lsig_lk):
                st.plotly_chart(
                    _make_max_pval_fig(
                        np.array(_lsig['sigma_vals']),
                        _lsig_lk, height=250,
                        x_label='σ_single (km/s)',
                        stat_label='Likelihood',
                    ), use_container_width=True)
        # Live 1D logP_max graph (likelihood only)
        _llp = _j.get('live_logPmax_1d')
        if _llp and len(_llp.get('logPmax_vals', [])) > 1:
            _llp_lk = _llp.get('max_likelihood', [])
            if _llp_lk and any(v > 0 for v in _llp_lk):
                st.plotly_chart(
                    _make_max_pval_fig(
                        np.array(_llp['logPmax_vals']),
                        _llp_lk, height=250,
                        x_label='logP_max', stat_label='Likelihood',
                    ), use_container_width=True)
    _cadence_live_poll()


def _render_final_heatmaps(p: str) -> None:
    """Show persisted final live heatmaps after job cleanup."""
    _final_lhm = st.session_state.get(f'{p}_final_live_heatmaps')
    if not _final_lhm:
        return
    # Mark all as final
    for mk in _final_lhm:
        _final_lhm[mk]['is_final'] = True
    # Single likelihood tile (full width)
    if 'likelihood' in _final_lhm:
        _hd = _final_lhm['likelihood']
        st.plotly_chart(
            _make_heatmap_fig(
                _hd['p'], _hd['fbin'], _hd['x'],
                title=_hd['title'], height=400,
                live=False,
                scoring_label='Likelihood',
                colorbar_title_override='Normalized Likelihood'),
            use_container_width=True)


def _render_final_sigma_1d(p: str) -> None:
    """Show persisted final sigma 1D graph after job cleanup."""
    _final_lsig = st.session_state.get(f'{p}_final_live_sigma_1d')
    if not _final_lsig or len(_final_lsig.get('sigma_vals', [])) <= 1:
        return
    _lsig_lk = _final_lsig.get('max_likelihood')
    if _lsig_lk and any(v > 0 for v in _lsig_lk):
        st.plotly_chart(
            _make_max_pval_fig(
                np.array(_final_lsig['sigma_vals']),
                _lsig_lk, height=250,
                x_label='\u03c3_single (km/s)',
                stat_label='Likelihood',
            ), use_container_width=True,
            key=f'{p}_final_sigma_1d_lk')
    else:
        st.plotly_chart(
            _make_max_pval_fig(
                np.array(_final_lsig['sigma_vals']),
                _final_lsig['max_pvals'], height=250,
                x_label='\u03c3_single (km/s)',
                stat_label='K-S',
            ), use_container_width=True,
            key=f'{p}_final_sigma_1d_ks')
