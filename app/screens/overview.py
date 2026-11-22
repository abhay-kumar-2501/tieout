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

_INTRO = {
    True: (
        "Tie-Out sizes the procurement savings two merging companies can defend, and opens "
        "the working behind every figure. This is a fictional sample merger (switch to "
        "another on Data); new here? The tour takes two minutes."
    ),
    False: (
        "Tie-Out has sized the procurement savings your two files can defend; select any "
        "figure or bar to see what it is made of. The tour takes two minutes."
    ),
}


def render_tour_hook() -> None:
    """The guided-tour button (PRD 2.2 step 5), when ``components.tour`` is installed."""
    try:
        from components.tour import render_tour_button
    except ImportError:
        return
    render_tour_button(primary=True)


def render_intro() -> None:
    """One plain sentence on what this is and what to do first, with the tour beside it."""
    with (
        st.container(border=True, key="to_intro"),
        st.container(
            horizontal=True,
            vertical_alignment="center",
            horizontal_alignment="distribute",
            gap="medium",
        ),
    ):
        st.markdown(
            f'<div class="to-lead">{esc(_INTRO[state.is_demo()])}</div>',
            unsafe_allow_html=True,
            width="stretch",
        )
        render_tour_hook()


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

render_intro()
page_question("What is the answer, and how sure are we?")
top = headline_view(results, mode)
headline(top["text"])
show_working(top["figure_id"], "the defensible run-rate saving", key="ov_headline")

run_rate, cash, cost = overview_figures(results, mode)
with st.container(key="to_grid_ov_figures"):
    recurring_box, one_time_box = st.columns([1, 2], gap="medium")
    with recurring_box, st.container(border=True, height="stretch"):
        st.markdown(
            '<div class="to-caption">Recurring amounts make up the run-rate saving.</div>',
            unsafe_allow_html=True,
        )
        _figure(st.container(), run_rate, "ov_run_rate")
    with one_time_box, st.container(border=True, height="stretch"):
        st.markdown(
            '<div class="to-caption">One-time amounts are never added to the run-rate '
            "saving.</div>",
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns(2, gap="medium")
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

section("Worth a look", "Three findings worth opening; each shows its working.")
cards = st.container(key="to_cards_ov_worth")
for column, card in zip(cards.columns(3, gap="medium"), worth_a_look(results, mode), strict=True):
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
