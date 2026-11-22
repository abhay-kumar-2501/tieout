"""The live header rendered above every page (PRD 6.3, 6.9, 6.12).

Scenario name (the sample merger's label in demo mode), the view-mode control, the
current headline range (so every change shows its effect) and, in demo mode, the
illustrative-data tag.
"""

from __future__ import annotations

import streamlit as st

from components import state
from components.style import esc
from tieout import theme as t
from tieout.views import headline

VIEW_LABELS = tuple(state.VIEW_MODES)
_LAST_VIEW = "_to_last_view"
_SCENARIO_NAMES = {"demo": "Demo merger"}
_BANNERS = {
    "clean": "Clean-team view: full detail, including vendor names and unit prices.",
    "masked": (
        "Integration-office view: vendors appear as codes, unit prices and item detail are "
        "hidden, and results are shown by category. This is a presentation mode, "
        "not a security control."
    ),
}


def scenario_name(meta: dict) -> str:
    """The scenario's display name from ``results.meta``."""
    raw = str(meta.get("scenario") or "Uploaded data")
    return _SCENARIO_NAMES.get(raw, raw.replace("_", " "))


def display_name(results) -> str:
    """The header's name: the sample merger in demo mode, else the scenario."""
    if state.is_demo():
        return state.sample().label
    return scenario_name(results.meta)


def render_header() -> None:
    chosen = st.session_state.get(state.VIEW_KEY)
    if chosen in VIEW_LABELS:
        st.session_state[_LAST_VIEW] = chosen
    else:  # first run, or the selected option was clicked again (which clears it)
        st.session_state[state.VIEW_KEY] = st.session_state.get(_LAST_VIEW, VIEW_LABELS[0])
    results = state.current_results()
    mode = state.view()
    top = headline(results, mode)
    # One bar: a row that wraps item by item on a narrow window, with the view banner below.
    with st.container(border=True, key="to_header", gap="small"):
        with st.container(
            horizontal=True,
            horizontal_alignment="distribute",
            vertical_alignment="center",
            key="to_header_row",
        ):
            st.markdown(
                f'<span class="to-strong">{esc(display_name(results))}</span>',
                unsafe_allow_html=True,
                width="content",
            )
            st.segmented_control(
                "View mode",
                VIEW_LABELS,
                key=state.VIEW_KEY,
                selection_mode="single",
                label_visibility="collapsed",
            )
            st.markdown(
                f'<span class="to-range"><span class="to-muted">Defensible run-rate saving: '
                f"</span><strong>{esc(top['range_text'])}</strong></span>",
                unsafe_allow_html=True,
                width="content",
            )
            if state.is_demo():
                st.markdown(
                    f'<span class="to-tag">{esc(t.ILLUSTRATIVE_LABEL)}</span>',
                    unsafe_allow_html=True,
                    width="content",
                )
        st.markdown(f'<div class="to-banner">{esc(_BANNERS[mode])}</div>', unsafe_allow_html=True)
