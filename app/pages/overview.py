"""Overview (PRD 6.4): what is the answer, and how sure are we?

Renders straight from the session's results with no spinner: headline, the
three figures (recurring apart from one-time), the bridge, the confidence
strip and the three "worth a look" cards.
"""

from __future__ import annotations

import streamlit as st
from components import state
from components.bridge import render_bar_detail, render_bridge
from components.page import next_question, page_question, section
from components.style import esc, figure_card, headline
from components.trace import show_working

from tieout.views import confidence_strip, overview_figures, percent, worth_a_look
from tieout.views import headline as headline_view


def render_tour_hook() -> None:
    """The guided-tour button (PRD 2.2 step 5), when ``components.tour`` is installed."""
    try:
        from components.tour import render_tour_button
    except ImportError:
        return
    render_tour_button()


def _figure(column, figure: dict, key: str) -> None:
    with column:
        kind = "Recurring, every year" if figure["kind"] == "recurring" else "One-time"
        if figure["available"]:
            figure_card(kind, figure["label"], figure["text"], figure["explanation"])
            show_working(figure["figure_id"], figure["label"], key=key)
        else:
            figure_card(kind, figure["label"], "Not assessed", figure["explanation"])


results = state.current_results()
mode = state.view()

page_question("What is the answer, and how sure are we?")
top = headline_view(results, mode)
headline(top["text"])
left, right = st.columns([3, 1], vertical_alignment="center")
with left:
    show_working(top["figure_id"], "the defensible run-rate saving", key="ov_headline")
with right:
    render_tour_hook()

run_rate, cash, cost = overview_figures(results, mode)
recurring_box, one_time_box = st.columns([1, 2])
with recurring_box, st.container(border=True):
    _figure(st.container(), run_rate, "ov_run_rate")
with one_time_box, st.container(border=True):
    st.markdown(
        '<div class="to-caption">One-time amounts are never added to the run-rate saving.</div>',
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    _figure(c1, cash, "ov_cash")
    _figure(c2, cost, "ov_cost")

section("From the naive figure to the defensible range")
bar = render_bridge("ov_bridge")
if bar is not None:
    render_bar_detail(bar, "ov_bar")

section("How sure we are")
strip = confidence_strip(results, mode)
with st.container(border=True):
    st.markdown(esc(strip["text"]), unsafe_allow_html=True)
    st.progress(
        min(max(strip["share_a"], 0.0), 1.0),
        text=f"Tier A share of the price-harmonisation base case: {percent(strip['share_a'])}",
    )
    show_working(
        strip["figure_ids"]["pending_review"], "the saving pending review", key="ov_pending"
    )

section("Worth a look")
for column, card in zip(st.columns(3), worth_a_look(results, mode), strict=True):
    with column, st.container(border=True, height="stretch"):
        st.markdown(f"**{esc(card['title'])}**")
        st.markdown(esc(card["text"]), unsafe_allow_html=True)
        if card.get("available") and card.get("figure_id"):
            show_working(
                card["figure_id"],
                card["title"],
                key=f"ov_card_{card['id']}",
                measure=card.get("measure"),
            )

next_question("Why is it so much smaller than the naive figure?", "synergies")
