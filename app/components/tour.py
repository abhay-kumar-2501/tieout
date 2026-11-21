"""The two-minute guided tour (PRD 2.2 step 5, 6.2).

A button on the Overview opens a dialog with five steps, one per signature
moment: a short text, a small image and a "Go there" link. It never starts on
its own. Images are in ``app/static/tour/`` (made by ``scripts/make_tour_images.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import streamlit as st
from streamlit.errors import StreamlitAPIException

from components.style import esc

__all__ = ["IMAGE_DIR", "STEPS", "TourStep", "render_tour_button"]

IMAGE_DIR = Path(__file__).resolve().parents[1] / "static" / "tour"
_STEP = "_to_tour_step"


@dataclass(frozen=True)
class TourStep:
    title: str
    text: str
    image: str
    page: str  # page module name, as in ``next_question``
    link: str


STEPS: tuple[TourStep, ...] = (
    TourStep(
        "The bridge",
        "A plain best-of-both formula says the merger is worth far more than it is. The bridge "
        "takes that naive figure down, one named step at a time, to a defensible range. Click "
        "any bar to see what it removed.",
        "bridge.png",
        "overview",
        "Go to the bridge on the Overview",
    ),
    TourStep(
        "The scorecard",
        "Matching accuracy is measured against hidden truth on a held-out dataset, next to what "
        "a naive fuzzy match would have got wrong.",
        "scorecard.png",
        "matching",
        "Go to the scorecard on Matching",
    ),
    TourStep(
        "The tie-out",
        "Every number is a door. Open a bar, then an opportunity, then see both companies' "
        "source rows side by side.",
        "tieout.png",
        "synergies",
        "Go to Synergies and open a bar",
    ),
    TourStep(
        "The price of resilience",
        "Move the concentration cap and watch the saving given up to keep the supply base "
        "from becoming too dependent on one vendor.",
        "resilience.png",
        "risk_roadmap",
        "Go to Risk & roadmap",
    ),
    TourStep(
        "The unit trap",
        "A 12-times price gap is often a box of 12, not a saving. Unit-of-measure errors are "
        "caught first and shown, so they never reach the answer.",
        "unit_trap.png",
        "matching",
        "Go to the unit checks on Matching",
    ),
)


def _go_there(step: TourStep) -> None:
    try:
        st.page_link(f"screens/{step.page}.py", label=step.link, icon=":material/arrow_forward:")
    except StreamlitAPIException:  # page run on its own, outside the navigation
        st.caption(esc(step.link))


def _rerun(in_dialog: bool) -> None:
    if in_dialog:
        st.rerun(scope="fragment")
    st.rerun()


def render_step(in_dialog: bool = True) -> None:
    """The current step's text, image and links, with Back and Next (drawn inline in tests)."""
    index = min(max(int(st.session_state.get(_STEP, 0)), 0), len(STEPS) - 1)
    step = STEPS[index]
    st.caption(f"Step {index + 1} of {len(STEPS)}")
    st.markdown(f"#### {esc(step.title)}")
    st.markdown(esc(step.text))
    st.image(str(IMAGE_DIR / step.image), width="stretch")
    back, go, forward = st.columns([1, 3, 1], vertical_alignment="center")
    if back.button("Back", key="tour_back", disabled=index == 0, icon=":material/arrow_back:"):
        st.session_state[_STEP] = index - 1
        _rerun(in_dialog)
    with go:
        _go_there(step)
    last = index == len(STEPS) - 1
    if forward.button("Done" if last else "Next", key="tour_next", type="primary"):
        st.session_state[_STEP] = 0 if last else index + 1
        if last:
            st.rerun()  # closes the dialog
        _rerun(in_dialog)


@st.dialog("Take the 2-minute tour", width="large")
def _tour() -> None:
    render_step()


def render_tour_button(*, primary: bool = False) -> None:
    """The "Take the 2-minute tour" button; the tour opens only when it is clicked."""
    if st.button(
        "Take the 2-minute tour",
        key="tour_open",
        icon=":material/tour:",
        type="primary" if primary else "secondary",
    ):
        st.session_state[_STEP] = 0
        _tour()
