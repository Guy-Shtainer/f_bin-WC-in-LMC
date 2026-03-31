"""
spectrum_helpers.py — Diagnostic spectral lines and absorption-line search tools.
Used by pages/02_spectrum.py for SB1/SB2 companion detection.
"""
from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

# ─────────────────────────────────────────────────────────────────────────────
# Diagnostic spectral lines (wavelength in Ångströms)
# ─────────────────────────────────────────────────────────────────────────────
DIAGNOSTIC_LINES: dict[str, list[dict]] = {
    'Hydrogen (Balmer)': [
        {'name': 'Hα',  'wave': 6562.8, 'element': 'H', 'type': 'abs'},
        {'name': 'Hβ',  'wave': 4861.3, 'element': 'H', 'type': 'abs'},
        {'name': 'Hγ',  'wave': 4340.5, 'element': 'H', 'type': 'abs'},
        {'name': 'Hδ',  'wave': 4101.7, 'element': 'H', 'type': 'abs'},
        {'name': 'Hε',  'wave': 3970.1, 'element': 'H', 'type': 'abs'},
    ],
    'He I (OB companion)': [
        {'name': 'He I 4026', 'wave': 4026.2, 'element': 'He I', 'type': 'abs'},
        {'name': 'He I 4388', 'wave': 4387.9, 'element': 'He I', 'type': 'abs'},
        {'name': 'He I 4471', 'wave': 4471.5, 'element': 'He I', 'type': 'abs'},
        {'name': 'He I 4922', 'wave': 4921.9, 'element': 'He I', 'type': 'abs'},
        {'name': 'He I 5876', 'wave': 5875.6, 'element': 'He I', 'type': 'abs'},
        {'name': 'He I 6678', 'wave': 6678.2, 'element': 'He I', 'type': 'abs'},
    ],
    'He II (hot companion)': [
        {'name': 'He II 4200', 'wave': 4199.8, 'element': 'He II', 'type': 'abs'},
        {'name': 'He II 4542', 'wave': 4541.6, 'element': 'He II', 'type': 'abs'},
        {'name': 'He II 4686', 'wave': 4685.7, 'element': 'He II', 'type': 'em'},
        {'name': 'He II 5412', 'wave': 5411.5, 'element': 'He II', 'type': 'abs'},
    ],
    'Carbon (WC diagnostic)': [
        {'name': 'C III 5696', 'wave': 5696.0, 'element': 'C', 'type': 'em'},
        {'name': 'C IV 5801', 'wave': 5801.3, 'element': 'C', 'type': 'em'},
        {'name': 'C IV 5812', 'wave': 5811.9, 'element': 'C', 'type': 'em'},
    ],
    'Nitrogen (WN diagnostic)': [
        {'name': 'N III 4634', 'wave': 4634.1, 'element': 'N', 'type': 'em'},
        {'name': 'N III 4641', 'wave': 4640.6, 'element': 'N', 'type': 'em'},
        {'name': 'N IV 4058', 'wave': 4057.8, 'element': 'N', 'type': 'em'},
        {'name': 'N V 4604',  'wave': 4603.7, 'element': 'N', 'type': 'em'},
        {'name': 'N V 4620',  'wave': 4619.9, 'element': 'N', 'type': 'em'},
    ],
    'Oxygen (WC diagnostic)': [
        {'name': 'O V 3144',  'wave': 3144.0, 'element': 'O', 'type': 'em'},
        {'name': 'O IV 3412', 'wave': 3412.0, 'element': 'O', 'type': 'em'},
        {'name': 'O VI 3811', 'wave': 3811.4, 'element': 'O', 'type': 'em'},
        {'name': 'O VI 3834', 'wave': 3834.2, 'element': 'O', 'type': 'em'},
        {'name': 'O III 5007','wave': 5006.8, 'element': 'O', 'type': 'em'},
        {'name': 'O VI 5290', 'wave': 5290.0, 'element': 'O', 'type': 'em'},
        {'name': 'O V 5590',  'wave': 5590.0, 'element': 'O', 'type': 'em'},
        {'name': 'O III 5592','wave': 5592.3, 'element': 'O', 'type': 'em'},
    ],
    'Interstellar / Other': [
        {'name': 'Na I D1', 'wave': 5895.9, 'element': 'Na', 'type': 'abs'},
        {'name': 'Na I D2', 'wave': 5889.9, 'element': 'Na', 'type': 'abs'},
        {'name': 'DIB 4430', 'wave': 4430.0, 'element': 'DIB', 'type': 'abs'},
        {'name': 'DIB 5780', 'wave': 5780.5, 'element': 'DIB', 'type': 'abs'},
        {'name': 'DIB 5797', 'wave': 5797.1, 'element': 'DIB', 'type': 'abs'},
    ],
}

LINE_COLORS = {
    'H':     '#5DADE2',
    'He I':  '#48C9B0',
    'He II': '#AF7AC5',
    'C':     '#F5B041',
    'N':     '#58D68D',
    'O':     '#E74C3C',
    'Na':    '#AEB6BF',
    'DIB':   '#AEB6BF',
}

LINE_PRESETS = {
    'SB2 search (OB companion)': ['Hydrogen (Balmer)', 'He I (OB companion)', 'He II (hot companion)'],
    'WC diagnostic': ['Carbon (WC diagnostic)', 'Oxygen (WC diagnostic)'],
    'WN diagnostic': ['Nitrogen (WN diagnostic)'],
    'All absorption': ['Hydrogen (Balmer)', 'He I (OB companion)', 'He II (hot companion)', 'Interstellar / Other'],
}


# ─────────────────────────────────────────────────────────────────────────────
# Absorption depth computation
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data
def compute_absorption_metrics(
    _waves_per_epoch: dict,          # {epoch: wave_array_angstrom}
    _fluxes_per_epoch: dict,         # {epoch: flux_array}
    selected_groups: tuple[str, ...],
    half_window: float = 5.0,
) -> list[dict]:
    """Measure min flux in a window around each absorption line for each epoch."""
    rows = []
    for group_name in selected_groups:
        for linfo in DIAGNOSTIC_LINES.get(group_name, []):
            if linfo['type'] != 'abs':
                continue
            w_center = linfo['wave']
            for ep, wave in _waves_per_epoch.items():
                flux = _fluxes_per_epoch[ep]
                mask = (wave >= w_center - half_window) & (wave <= w_center + half_window)
                if not np.any(mask):
                    continue
                window_flux = flux[mask]
                rows.append({
                    'Line': linfo['name'],
                    'Wave (A)': w_center,
                    'Element': linfo['element'],
                    'Epoch': ep,
                    'Min Flux': float(np.min(window_flux)),
                    'Mean Flux': float(np.mean(window_flux)),
                })
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Render: absorption search section (both graphs)
# ─────────────────────────────────────────────────────────────────────────────
def render_absorption_search(
    star_name: str,
    band: str,
    epochs: list,
    load_spectrum_fn,
    get_mjd_fn,
    plotly_theme: dict,
):
    """Render the full absorption line search section: controls + heatmap + epoch diff."""
    st.markdown('---')
    st.markdown('## Absorption Line Search')
    st.caption(
        'Search for companion absorption features across epochs. '
        'SB2 companions (e.g., OB stars) produce absorption lines that shift with orbital phase.'
    )

    # ── Shared controls ──────────────────────────────────────────────────────
    ctrl_c1, ctrl_c2, ctrl_c3 = st.columns([2, 1, 1])
    all_groups = list(DIAGNOSTIC_LINES.keys())
    preset_name = ctrl_c1.selectbox(
        'Line preset', ['SB2 search (OB companion)'] + [k for k in LINE_PRESETS if k != 'SB2 search (OB companion)'] + ['Custom'],
        key='abs_preset',
    )
    if preset_name == 'Custom':
        default_groups = all_groups[:3]
    else:
        default_groups = LINE_PRESETS.get(preset_name, all_groups[:3])
    selected_groups = ctrl_c2.multiselect(
        'Line groups', all_groups,
        default=[g for g in default_groups if g in all_groups],
        key='abs_groups', label_visibility='collapsed',
    ) if preset_name == 'Custom' else default_groups

    threshold = ctrl_c3.slider('Detection threshold', 0.80, 1.00, 0.95, 0.01, key='abs_thresh')

    if not selected_groups:
        st.info('Select at least one line group.')
        return

    # ── Load all epoch spectra ───────────────────────────────────────────────
    waves_per_epoch = {}
    fluxes_per_epoch = {}
    for ep in epochs:
        spec = load_spectrum_fn(star_name, ep, band)
        if spec is not None:
            w = np.asarray(spec.get('wavelengths', spec.get('wave', [])))
            f = np.asarray(spec.get('normalized_flux', spec.get('flux', [])))
            if len(w) > 0:
                waves_per_epoch[ep] = w * 10.0   # nm -> Å
                fluxes_per_epoch[ep] = f

    if not waves_per_epoch:
        st.warning('No spectra loaded for absorption search.')
        return

    # ── Graph 1: Absorption Depth Heatmap ────────────────────────────────────
    rows = compute_absorption_metrics(
        {ep: w for ep, w in waves_per_epoch.items()},
        {ep: f for ep, f in fluxes_per_epoch.items()},
        tuple(selected_groups),
    )

    if not rows:
        st.info('No absorption lines in the selected groups fall within the spectral range.')
        return

    # Build heatmap arrays
    line_names = list(dict.fromkeys(r['Line'] for r in rows))  # preserves order
    ep_list = sorted(set(r['Epoch'] for r in rows))
    z = np.full((len(ep_list), len(line_names)), np.nan)
    for r in rows:
        i = ep_list.index(r['Epoch'])
        j = line_names.index(r['Line'])
        z[i, j] = r['Min Flux']

    fig_heat = go.Figure(data=go.Heatmap(
        z=z,
        x=line_names,
        y=[str(e) for e in ep_list],
        colorscale=[
            [0.0, '#E74C3C'],    # deep absorption = red
            [0.5, '#F5B041'],    # moderate
            [1.0, '#58D68D'],    # continuum = green
        ],
        zmin=0.7, zmax=1.1,
        colorbar=dict(title='Min Flux'),
        hovertemplate='Line: %{x}<br>Epoch: %{y}<br>Min Flux: %{z:.3f}<extra></extra>',
    ))

    # Add threshold line annotation
    fig_heat.update_layout(**{
        **plotly_theme,
        'title': dict(text=f'{star_name} — Absorption Depth by Line & Epoch'),
        'xaxis': {**plotly_theme.get('xaxis', {}), 'title': 'Absorption Line', 'tickangle': -45},
        'yaxis': {**plotly_theme.get('yaxis', {}), 'title': 'Epoch'},
        'height': 350,
    })
    st.plotly_chart(fig_heat, use_container_width=True)

    # Summary
    detections = [r for r in rows if r['Min Flux'] < threshold]
    if detections:
        det_lines = sorted(set(f"{d['Line']} ({d['Element']})" for d in detections))
        n_det = len(set(d['Line'] for d in detections))
        st.warning(f'Absorption detected below {threshold:.2f} in **{n_det}** line(s): {", ".join(det_lines)}')
    else:
        st.success(f'No absorption below {threshold:.2f} detected in selected lines.')

    # ── Graph 2: Epoch Difference ────────────────────────────────────────────
    st.markdown('### Epoch Difference')
    st.caption('Subtract two epochs to reveal shifting absorption features from a companion.')

    diff_c1, diff_c2 = st.columns(2)
    diff_ep1 = diff_c1.selectbox('Epoch A', ep_list, index=0, key='absdiff_ep1')
    diff_ep2_opts = [e for e in ep_list if e != diff_ep1]
    if not diff_ep2_opts:
        st.info('Need at least 2 epochs.')
        return

    diff_ep2 = diff_c2.selectbox(
        'Epoch B', diff_ep2_opts,
        index=min(len(diff_ep2_opts) - 1, 1) if len(diff_ep2_opts) > 1 else 0,
        key='absdiff_ep2',
    )

    wa, fa = waves_per_epoch[diff_ep1], fluxes_per_epoch[diff_ep1]
    wb, fb = waves_per_epoch[diff_ep2], fluxes_per_epoch[diff_ep2]
    fb_interp = np.interp(wa, wb, fb)
    diff_flux = fa - fb_interp

    mjd_a = get_mjd_fn(star_name, diff_ep1)
    mjd_b = get_mjd_fn(star_name, diff_ep2)
    mjd_a_str = f' (MJD {mjd_a:.2f})' if mjd_a else ''
    mjd_b_str = f' (MJD {mjd_b:.2f})' if mjd_b else ''

    fig_diff = go.Figure()
    # Faint context traces
    fig_diff.add_trace(go.Scatter(
        x=wa, y=fa, mode='lines', line=dict(color='#4A90D9', width=0.6),
        name=f'Ep {diff_ep1}{mjd_a_str}', opacity=0.3,
    ))
    fig_diff.add_trace(go.Scatter(
        x=wa, y=fb_interp, mode='lines', line=dict(color='#E25A53', width=0.6),
        name=f'Ep {diff_ep2}{mjd_b_str}', opacity=0.3,
    ))
    # Difference trace
    fig_diff.add_trace(go.Scatter(
        x=wa, y=diff_flux, mode='lines', line=dict(color='#58D68D', width=1.5),
        name=f'Difference (Ep {diff_ep1} - Ep {diff_ep2})',
    ))
    fig_diff.add_hline(y=0, line_width=0.5, line_dash='dash', line_color='#666')

    # Diagnostic line markers on difference plot
    wmin, wmax = float(wa.min()), float(wa.max())
    for group_name in selected_groups:
        for linfo in DIAGNOSTIC_LINES.get(group_name, []):
            w = linfo['wave']
            if w < wmin or w > wmax:
                continue
            color = LINE_COLORS.get(linfo['element'], '#AEB6BF')
            dash_style = 'dash' if linfo['type'] == 'abs' else 'dot'
            fig_diff.add_vline(
                x=w, line_width=1, line_dash=dash_style,
                line_color=color, opacity=0.6,
                annotation_text=linfo['name'],
                annotation=dict(font_size=8, font_color=color, textangle=-90, yanchor='bottom'),
                annotation_position='top',
            )

    fig_diff.update_layout(**{
        **plotly_theme,
        'title': dict(text=f'{star_name} — Epoch {diff_ep1} minus Epoch {diff_ep2}'),
        'xaxis': {**plotly_theme.get('xaxis', {}), 'title': 'Wavelength (Å)'},
        'yaxis': {**plotly_theme.get('yaxis', {}), 'title': 'Flux difference'},
        'height': 450,
        'legend': {**plotly_theme.get('legend', {}), 'bgcolor': 'rgba(30,30,46,0.85)'},
    })
    st.plotly_chart(fig_diff, use_container_width=True)

    rms = float(np.sqrt(np.mean(diff_flux**2)))
    peak = float(np.max(np.abs(diff_flux)))
    st.caption(f'RMS of difference: {rms:.4f}  |  Peak |difference|: {peak:.4f}')
