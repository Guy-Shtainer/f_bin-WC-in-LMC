"""
pages/09_settings.py — Settings, States, Presets, Run History
Full settings editor + state/preset management.
"""
from __future__ import annotations
import gc, json, os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pandas as pd
import streamlit as st

from shared import (
    inject_theme, render_sidebar, get_settings_manager, load_run_history,
)

st.set_page_config(page_title='Settings — WR Binary', page_icon='⚙️', layout='wide')
inject_theme()
settings = render_sidebar('Settings')
sm       = get_settings_manager()

st.markdown('# ⚙️ Settings & State Management')
st.caption('All changes are saved immediately to `settings/user_settings.json`.')

# ─────────────────────────────────────────────────────────────────────────────
# Settings editor (section by section)
# ─────────────────────────────────────────────────────────────────────────────
with st.expander('📐 Classification', expanded=True):
    cls = settings.get('classification', {})
    col1, col2, col3, col4 = st.columns(4)
    col1.number_input('threshold_dRV (km/s)', value=float(cls.get('threshold_dRV', 45.5)),
        step=0.5, key='set_cls_thr',
        on_change=lambda: sm.save(['classification', 'threshold_dRV'],
                                   value=st.session_state['set_cls_thr']))
    col2.number_input('sigma_factor', value=float(cls.get('sigma_factor', 4.0)),
        step=0.1, key='set_cls_sf',
        on_change=lambda: sm.save(['classification', 'sigma_factor'],
                                   value=st.session_state['set_cls_sf']))
    col3.number_input('bartzakos_binaries', value=int(cls.get('bartzakos_binaries', 3)),
        step=1, min_value=0, key='set_cls_bartz',
        on_change=lambda: sm.save(['classification', 'bartzakos_binaries'],
                                   value=st.session_state['set_cls_bartz']))
    col4.number_input('total_population', value=int(cls.get('total_population', 28)),
        step=1, min_value=1, key='set_cls_total',
        on_change=lambda: sm.save(['classification', 'total_population'],
                                   value=st.session_state['set_cls_total']))

with st.expander('🔭 Primary line & emission lines'):
    primary_line = st.text_input(
        'Primary emission line', value=settings.get('primary_line', 'C IV 5808-5812'),
        key='set_primary_line',
        on_change=lambda: sm.save('primary_line', value=st.session_state['set_primary_line'])
    )
    em_lines = settings.get('emission_lines', {})
    st.markdown('**Emission line wavelength ranges (nm)**')
    st.caption('Format: line name → [λ_min_nm, λ_max_nm]')
    em_json = st.text_area('Emission lines (JSON)', value=json.dumps(em_lines, indent=2),
                           height=250, key='set_em_lines')
    if st.button('Apply emission lines', key='apply_em_lines'):
        try:
            new_em = json.loads(em_json)
            sm.save('emission_lines', value=new_em)
            st.success('Emission lines updated.')
        except json.JSONDecodeError as e:
            st.error(f'Invalid JSON: {e}')

with st.expander('📡 CCF'):
    ccf = settings.get('ccf', {})
    c1, c2, c3 = st.columns(3)
    c1.number_input('CrossVeloMin (km/s)', value=int(ccf.get('CrossVeloMin', -2000)),
        step=100, key='set_ccf_vmin',
        on_change=lambda: sm.save(['ccf', 'CrossVeloMin'], value=st.session_state['set_ccf_vmin']))
    c2.number_input('CrossVeloMax (km/s)', value=int(ccf.get('CrossVeloMax', 2000)),
        step=100, key='set_ccf_vmax',
        on_change=lambda: sm.save(['ccf', 'CrossVeloMax'], value=st.session_state['set_ccf_vmax']))
    c3.slider('fit_fraction_default', 0.5, 1.0,
        float(ccf.get('fit_fraction_default', 0.97)), 0.01, key='set_ccf_ff',
        on_change=lambda: sm.save(['ccf', 'fit_fraction_default'], value=st.session_state['set_ccf_ff']))

with st.expander('🎲 Simulation'):
    sim = settings.get('simulation', {})
    c1, c2 = st.columns(2)
    c1.number_input('sigma_single (km/s)', value=float(sim.get('sigma_single', 5.5)),
        step=0.1, key='set_sim_ss',
        on_change=lambda: sm.save(['simulation', 'sigma_single'], value=st.session_state['set_sim_ss']))
    c2.number_input('sigma_measure (km/s)', value=float(sim.get('sigma_measure', 1.622)),
        step=0.001, format='%.3f', key='set_sim_sm',
        on_change=lambda: sm.save(['simulation', 'sigma_measure'], value=st.session_state['set_sim_sm']))

with st.expander('🔲 Dsilva grid'):
    gd = settings.get('grid_dsilva', {})
    c1, c2, c3 = st.columns(3)
    c1.number_input('fbin_min', 0.0, 0.5, float(gd.get('fbin_min', 0.01)), 0.01, key='set_gd_fmin',
        on_change=lambda: sm.save(['grid_dsilva', 'fbin_min'], value=st.session_state['set_gd_fmin']))
    c1.number_input('fbin_max', 0.5, 1.0, float(gd.get('fbin_max', 0.99)), 0.01, key='set_gd_fmax',
        on_change=lambda: sm.save(['grid_dsilva', 'fbin_max'], value=st.session_state['set_gd_fmax']))
    c1.number_input('fbin_steps', 10, 500, int(gd.get('fbin_steps', 137)), 1, key='set_gd_fsteps',
        on_change=lambda: sm.save(['grid_dsilva', 'fbin_steps'], value=st.session_state['set_gd_fsteps']))
    c2.number_input('pi_min', -5.0, 0.0, float(gd.get('pi_min', -3.0)), 0.1, key='set_gd_pimin',
        on_change=lambda: sm.save(['grid_dsilva', 'pi_min'], value=st.session_state['set_gd_pimin']))
    c2.number_input('pi_max', 0.0, 5.0, float(gd.get('pi_max', 3.0)), 0.1, key='set_gd_pimax',
        on_change=lambda: sm.save(['grid_dsilva', 'pi_max'], value=st.session_state['set_gd_pimax']))
    c2.number_input('pi_steps', 10, 500, int(gd.get('pi_steps', 249)), 1, key='set_gd_pisteps',
        on_change=lambda: sm.save(['grid_dsilva', 'pi_steps'], value=st.session_state['set_gd_pisteps']))
    c3.number_input('n_stars_sim', 100, 50000, int(gd.get('n_stars_sim', 3000)), 100, key='set_gd_n',
        on_change=lambda: sm.save(['grid_dsilva', 'n_stars_sim'], value=st.session_state['set_gd_n']))
    c3.number_input('logP_min', 0.0, 2.0, float(gd.get('logP_min', 0.15)), 0.01, key='set_gd_lpmin',
        on_change=lambda: sm.save(['grid_dsilva', 'logP_min'], value=st.session_state['set_gd_lpmin']))
    c3.number_input('logP_max', 3.0, 10.0, float(gd.get('logP_max', 5.0)), 0.1, key='set_gd_lpmax',
        on_change=lambda: sm.save(['grid_dsilva', 'logP_max'], value=st.session_state['set_gd_lpmax']))

# ── Reset to defaults ─────────────────────────────────────────────────────────
st.markdown('---')
if st.button('⚠️ Reset all settings to defaults'):
    _defaults_path = os.path.join(_ROOT, 'settings', 'presets', 'default.json')
    if os.path.exists(_defaults_path):
        sm.load_preset('default')
        st.success('Settings reset to default preset.')
        st.rerun()
    else:
        st.warning('No default.json preset found in settings/presets/.')

# ─────────────────────────────────────────────────────────────────────────────
# State management
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('---')
st.markdown('## 💾 State Management')
st.caption('A saved state includes all settings + the current UI context (star, page, result).')

col_save, col_load = st.columns(2)

with col_save:
    st.markdown('**Save current state**')
    sn_input = st.text_input('State name', placeholder='e.g. pre_langer_run', key='set_state_name')
    if st.button('Save state', key='set_btn_save_state'):
        if sn_input.strip():
            path = sm.save_state(sn_input.strip())
            st.success(f'Saved: {os.path.basename(path)}')
        else:
            st.warning('Enter a name first.')

    st.markdown('**Save preset (settings only)**')
    pr_input = st.text_input('Preset name', placeholder='e.g. publication', key='set_preset_name')
    if st.button('Save preset', key='set_btn_save_preset'):
        if pr_input.strip():
            path = sm.save_preset(pr_input.strip())
            st.success(f'Saved: {os.path.basename(path)}')
        else:
            st.warning('Enter a name first.')

with col_load:
    st.markdown('**Saved states**')
    states = sm.list_states()
    if states:
        for s in states:
            cols = st.columns([3, 1])
            cols[0].write(f"**{s['name']}**  {s['timestamp'][:16]}")
            if cols[1].button('Load', key=f'load_state_{s["filename"]}'):
                sm.load_state(s['path'])
                st.success(f'Loaded: {s["name"]}')
                st.rerun()
    else:
        st.info('No saved states yet.')

    st.markdown('**Saved presets**')
    presets = sm.list_presets()
    if presets:
        for p in presets:
            cols = st.columns([3, 1])
            cols[0].write(f'**{p}**')
            if cols[1].button('Load', key=f'load_preset_{p}'):
                sm.load_preset(p)
                st.success(f'Loaded preset: {p}')
                st.rerun()
    else:
        st.info('No presets yet.')

# ─────────────────────────────────────────────────────────────────────────────
# Run history
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('---')
st.markdown('## 📜 Run History')
history = load_run_history()
if history:
    rows = []
    for r in reversed(history):
        cfg = r.get('config', {})
        rows.append({
            'Timestamp': r.get('timestamp', '')[:19],
            'Model':     r.get('model', '—'),
            'Config hash': r.get('config_hash', '—'),
            'Grid':      f"{cfg.get('fbin_steps','?')}×{cfg.get('pi_steps','?')}",
            'N sim/pt':  cfg.get('n_stars_sim', '—'),
            'Time (s)':  r.get('elapsed_s', '—'),
            'Result':    os.path.basename(r.get('result_file', '—')),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
else:
    st.info('No runs yet.')

# ─────────────────────────────────────────────────────────────────────────────
# Cache / memory
# ─────────────────────────────────────────────────────────────────────────────
st.markdown('---')
st.markdown('## 🗑️ Cache & Memory')
st.caption(
    'Use "Clear cache" if the app feels slow or if you have updated data on disk '
    'and want Streamlit to re-read it.'
)
if st.button('🗑️ Clear all caches'):
    st.cache_data.clear()
    gc.collect()
    st.success('All caches cleared.')
