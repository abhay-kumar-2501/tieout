"""Shared header rendered above every page (PRD 6.3)."""

from __future__ import annotations

import streamlit as st

from tieout import theme as t

SCENARIO_NAME = "Demo merger"
VIEW_MODES = ("Clean team", "Integration office")
VIEW_KEY = "view_mode"


def render_header() -> None:
    if st.session_state.get(VIEW_KEY) not in VIEW_MODES:
        st.session_state[VIEW_KEY] = VIEW_MODES[0]
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns([2, 3, 2, 2], vertical_alignment="center")
        c1.markdown(f"**{SCENARIO_NAME}**")
        c2.segmented_control(
            "View mode",
            VIEW_MODES,
            key=VIEW_KEY,
            selection_mode="single",
            label_visibility="collapsed",
        )
        c3.markdown('<span class="to-muted">Headline range: —</span>', unsafe_allow_html=True)
        c4.markdown(f'<span class="to-tag">{t.ILLUSTRATIVE_LABEL}</span>', unsafe_allow_html=True)
