"""The live header rendered above every page (PRD 6.3, 6.9, 6.12).

Scenario name (the sample merger's label in demo mode), the view-mode control, the
current headline range (so every change shows its effect) and, in demo mode, the
illustrative-data tag. Every session opens on a random sample merger, so the header
names it ("You're looking at") and offers the others beside it.
"""

from __future__ import annotations

import streamlit as st

from components import state
from components.explain import GLOSSARY
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
#: The same, short enough for two lines on a phone.
_BANNERS_SHORT = {
    "clean": "Full detail, including vendor names and unit prices.",
    "masked": "Vendor codes, no prices or item detail. A presentation, not a security control.",
}
_TAG_SHORT = "Synthetic data"


def _wide_or_phone(wide: str, phone: str) -> str:
    """Both texts as HTML; the stylesheet shows one, by window width."""
    return f'<span class="to-wide-only">{wide}</span><span class="to-phone-only">{phone}</span>'


def scenario_name(meta: dict) -> str:
    """The scenario's display name from ``results.meta``."""
    raw = str(meta.get("scenario") or "Uploaded data")
    return _SCENARIO_NAMES.get(raw, raw.replace("_", " "))


def display_name(results) -> str:
    """The header's name: the sample merger in demo mode, else the scenario."""
    if state.is_demo():
        return state.sample().label
    return scenario_name(results.meta)


def render_sample_switch(key: str) -> None:
    """A "Try another sample" popover listing the other sample mergers (demo mode only)."""
    if not state.is_demo() or len(state.samples()) < 2:
        return
    current = state.sample()
    with st.popover("Try another sample", icon=":material/swap_horiz:", key=f"{key}_popover"):
        st.caption(
            "Four fictional mergers, each with its own data. Switching clears review "
            "decisions and assumption changes; saved scenarios are kept."
        )
        for option in state.samples():
            chosen = option.id == current.id
            if st.button(
                option.label,
                key=f"{key}_{option.id}",
                icon=":material/check:" if chosen else ":material/arrow_forward:",
                disabled=chosen,
                width="stretch",
            ):
                state.set_sample(option.id)
                st.rerun()


def render_header() -> None:
    chosen = st.session_state.get(state.VIEW_KEY)
    if chosen in VIEW_LABELS:
        st.session_state[_LAST_VIEW] = chosen
    else:  # first run, or the selected option was clicked again (which clears it)
        st.session_state[state.VIEW_KEY] = st.session_state.get(_LAST_VIEW, VIEW_LABELS[0])
    results = state.current_results()
    mode = state.view()
    top = headline(results, mode)
    # Two rows that wrap item by item on a narrow window: what you are looking at and the
    # answer, then the view mode with its banner.
    with st.container(border=True, key="to_header", gap="small"):
        with st.container(
            horizontal=True,
            horizontal_alignment="distribute",
            vertical_alignment="center",
            key="to_header_row",
        ):
            with st.container(
                horizontal=True,
                vertical_alignment="center",
                gap="medium",
                width="content",
                key="to_header_name",
            ):
                eyebrow = "You're looking at" if state.is_demo() else "Your data"
                name = esc(display_name(results))
                st.markdown(
                    f'<span class="to-eyebrow">{eyebrow}</span>'
                    f'<span class="to-strong" title="{name}">{name}</span>',
                    unsafe_allow_html=True,
                    width="content",
                )
                render_sample_switch("header_sample")
            with st.container(
                horizontal=True,
                vertical_alignment="center",
                gap="medium",
                width="content",
                key="to_header_answer",
            ):
                st.markdown(
                    '<span class="to-range"><span class="to-muted">'
                    + _wide_or_phone("Defensible run-rate saving: ", "Defensible: ")
                    + f"</span><strong>{esc(top['range_text'])}</strong> a year</span>",
                    unsafe_allow_html=True,
                    width="content",
                    help=GLOSSARY["Run-rate saving"] + " " + GLOSSARY["Defensible saving"],
                )
                if state.is_demo():
                    st.markdown(
                        '<span class="to-tag">'
                        + _wide_or_phone(esc(t.ILLUSTRATIVE_LABEL), _TAG_SHORT)
                        + "</span>",
                        unsafe_allow_html=True,
                        width="content",
                    )
        # How you are looking at it: the view and what it shows.
        with st.container(
            horizontal=True, vertical_alignment="center", gap="medium", key="to_header_view"
        ):
            st.segmented_control(
                "View mode",
                VIEW_LABELS,
                key=state.VIEW_KEY,
                selection_mode="single",
                label_visibility="collapsed",
                help=GLOSSARY["Clean team and integration office"],
            )
            st.markdown(
                '<div class="to-banner">'
                + _wide_or_phone(esc(_BANNERS[mode]), esc(_BANNERS_SHORT[mode]))
                + "</div>",
                unsafe_allow_html=True,
                width="stretch",
            )
