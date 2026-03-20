"""plots/tab_ccf.py — CCF Outputs sub-tab: browse CCF PNG plots."""
from __future__ import annotations

import os
import re
import sys

import streamlit as st

from shared import ROOT

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import specs  # noqa: E402


def render_ccf_subtab():
    """Render the CCF Outputs sub-tab."""
    output_root = os.path.normpath(os.path.join(ROOT, '..', 'output'))
    st.markdown(f'### CCF plots from `{output_root}`')
    if not os.path.isdir(output_root):
        st.info('Output directory not found.')
        return

    star_f = st.selectbox('Filter by star', ['All'] + specs.star_names,
                          key='xsp_ccf_star')
    pngs = []
    for sn in specs.star_names:
        clean_sn = re.sub(r"[^A-Za-z0-9_-]", "_", sn)
        d = os.path.join(output_root, clean_sn, 'CCF')
        if os.path.isdir(d):
            for dp, _, fns in os.walk(d):
                for fn in fns:
                    if fn.lower().endswith('.png'):
                        pngs.append(os.path.join(dp, fn))
    if star_f != 'All':
        clean_filter = re.sub(r"[^A-Za-z0-9_-]", "_", star_f)
        pngs = [p for p in pngs if clean_filter in p]
    st.write(f'{len(pngs)} CCF plot(s) found.')
    n_show = st.slider('Max plots to show', 3, 30, 12, key='xsp_ccf_n')
    cols = st.columns(3)
    for i, p in enumerate(pngs[:n_show]):
        cols[i % 3].image(p, caption=os.path.basename(p), width='stretch')
    if len(pngs) > 0:
        st.caption('CCF output plots from the cross-correlation pipeline.')
    if len(pngs) > n_show:
        st.info(f'Showing first {n_show} of {len(pngs)}.')
