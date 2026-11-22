"""Overview (PRD 6.4): what is the answer, and how sure are we?

An inviting start that anyone can follow. The hero gives the answer in one plain
sentence beside a picture of how much of the quick estimate survives; the three
figures keep recurring apart from one-time; the bridge tells where the rest went,
each step with a one-line reason; how sure we are sits beside three findings worth
opening; and the Explore cards lead to every other screen. Renders straight from the
session's results with no spinner.
"""

from __future__ import annotations

import math

import streamlit as st
from components import state
from components.bridge import render_bar_detail, render_bridge
from components.explain import (
    glossary_popover,
    page_link,
    render_explore,
    step_reason,
)
from components.style import esc, icon_badge
from components.trace import show_working

from tieout.views import bridge, confidence_strip, money, overview_figures, worth_a_look
from tieout.views import headline as headline_view

_TERMS = (
    "Naive figure",
    "Defensible saving",
    "Run-rate saving",
    "Lever",
    "Tier A, B, C",
    "Clean team and integration office",
)
_PLAIN_TITLES = {
    "run_rate": ("Saved every year", "event_repeat"),
    "cash": ("Cash freed, once", "payments"),
    "cost": ("Cost to get there, once", "construction"),
}
_FINDING_ICONS = {
    "largest_lever1": "sell",
    "unit_trap": "straighten",
    "savings_forgone": "shield",
}


def render_tour_hook(*, key: str = "tour_open", primary: bool = True) -> None:
    """The guided-tour button (PRD 2.2 step 5), when ``components.tour`` is installed."""
    try:
        from components.tour import render_tour_button
    except ImportError:
        return
    render_tour_button(primary=primary, key=key)


def _share(part: float, whole: float) -> float:
    """``part / whole`` clipped to 0-1; 0 when either is missing."""
    if not whole or not math.isfinite(whole) or not math.isfinite(part):
        return 0.0
    return min(max(part / whole, 0.0), 1.0)


def _compare_card(top: dict) -> None:
    """Quick estimate against the defensible range, drawn to scale."""
    naive, low, base, high = top["naive"], top["low"], top["base"], top["high"]
    lo, mid, hi = (_share(v, naive) for v in (low, base, high))
    survives = round(mid * 100)
    with st.container(border=True, key="to_compare"):
        st.markdown(
            '<div class="to-compare">'
            '<div class="to-compare-row">'
            '<div class="to-compare-label to-compare-naive">Quick estimate'
            f"<span>{esc(money(naive))}</span></div>"
            '<div class="to-track"><div class="to-bar to-bar-naive" style="width:100%">'
            "</div></div></div>"
            '<div class="to-compare-row">'
            '<div class="to-compare-label to-compare-good">Holds up after checks'
            f"<span>{esc(top['range_text'])}</span></div>"
            '<div class="to-track">'
            f'<div class="to-bar to-bar-low" style="width:{lo * 100:.1f}%"></div>'
            f'<div class="to-bar to-bar-range" style="left:{lo * 100:.1f}%;'
            f'width:{max(hi - lo, 0.005) * 100:.1f}%"></div>'
            f'<div class="to-bar-mark" style="left:{mid * 100:.1f}%"></div></div>'
            '<div class="to-compare-legend">Solid: the low case. Faded: up to the high case. '
            f"Line: the base case, {esc(money(base))} a year.</div></div>"
            f'<div class="to-compare-note">About <strong>{survives}%</strong> of the quick '
            "estimate survives the checks. The bridge below shows what each check took out "
            "and why.</div></div>",
            unsafe_allow_html=True,
        )


def render_hero(results, mode: str) -> dict:
    """The answer in one plain sentence, what Tie-Out does, and where to start."""
    top = headline_view(results, mode)
    whose = "These two companies" if state.is_demo() else "Your two companies"
    with st.container(key="to_hero"):
        text, picture = st.container(key="to_grid_hero").columns(
            [7, 5], gap="large", vertical_alignment="center"
        )
        with text:
            st.markdown(
                '<div class="to-eyebrow">The answer for this merger</div>'
                f'<div class="to-hero-title">{whose} can defend '
                f'<span class="to-hl">{esc(top["range_text"])} a year</span> in savings from '
                "buying together.</div>"
                f'<div class="to-hero-sub">Not the {esc(money(top["naive"]))} a quick '
                "estimate suggests.</div>"
                '<div class="to-hero-lead">When companies merge, the quick estimate of what '
                "they save by buying together is inflated: the same supplier is spelled two "
                "ways, a box of 12 is compared with a single piece, some prices cannot be "
                "checked. Tie-Out matches the records carefully, takes out the savings that "
                "are not real, and shows where every remaining dollar comes from.</div>",
                unsafe_allow_html=True,
            )
            with st.container(horizontal=True, vertical_alignment="center", gap="small"):
                render_tour_hook()
                page_link("method_limits", "How it works", ":material/menu_book:")
                glossary_popover(_TERMS, key="glossary_overview")
                show_working(top["figure_id"], "the defensible run-rate saving", key="ov_headline")
        with picture:
            _compare_card(top)
    return top


def _figure(figure: dict, key: str) -> None:
    title, icon = _PLAIN_TITLES[figure["id"]]
    value = figure["text"] if figure["available"] else "Not assessed"
    st.markdown(
        f":material/{icon}: **{esc(title)}**",
    )
    st.markdown(
        f'<div class="to-figure-value">{esc(value)}</div>'
        f'<div class="to-figure-label">{esc(figure["label"])}</div>'
        f'<div class="to-caption">{esc(figure["explanation"])}</div>',
        unsafe_allow_html=True,
    )
    if figure["available"]:
        show_working(figure["figure_id"], figure["label"], key=key)


def render_figures(results, mode: str) -> None:
    """The three headline figures on one ledger: recurring apart from one-time."""
    run_rate, cash, cost = overview_figures(results, mode)
    with st.container(border=True, key="to_ledger"):
        columns = st.container(key="to_grid_ov_figures").columns(3, gap="medium")
        for column, figure, key in zip(
            columns, (run_rate, cash, cost), ("ov_run_rate", "ov_cash", "ov_cost"), strict=True
        ):
            with column:
                _figure(figure, key)
        st.markdown(
            '<div class="to-caption">Only the first figure recurs. One-time amounts are '
            "never added to the run-rate saving.</div>",
            unsafe_allow_html=True,
        )


def _steps_html(frame) -> str:
    """Each step of the bridge as a numbered line: name, amount and why."""
    rows = frame[frame["kind"].isin(("decrease", "increase"))]
    cells = []
    for number, (_, row) in enumerate(rows.iterrows(), start=1):
        kind = "plus" if row["kind"] == "increase" else "minus"
        cells.append(
            f'<div class="to-step to-step-{kind}">'
            f'<div class="to-step-num">{number}</div>'
            f'<div><div class="to-step-head"><span>{esc(row["label"].lstrip("+ "))}</span>'
            f'<span class="to-step-amt">{esc(row["text"])}</span></div>'
            f'<div class="to-step-why">{esc(step_reason(row["label"]))}</div></div></div>'
        )
    return f'<div class="to-steps">{"".join(cells)}</div>'


def render_story(results, mode: str, top: dict) -> None:
    """The bridge: from the quick estimate to the defensible range, one reason at a time."""
    gone = money(max(top["naive"] - top["base"], 0.0))
    st.markdown(
        f'<div class="to-section">Where did the other {esc(gone)} go?</div>'
        '<div class="to-muted">Each bar is one check that takes out savings that are not '
        "real. Hover a bar for the reason, or click it to see every item it removed.</div>",
        unsafe_allow_html=True,
    )
    bar = render_bridge("ov_bridge")
    if bar is not None:
        render_bar_detail(bar, "ov_bar")
    st.markdown(_steps_html(bridge(results, mode)), unsafe_allow_html=True)
    page_link(
        "synergies",
        "Why is it so much smaller than the naive figure? See every item each step removed",
        ":material/arrow_forward:",
    )


def render_confidence(results, mode: str) -> None:
    strip = confidence_strip(results, mode)
    a, b = (float(strip.get(k) or 0.0) for k in ("share_a", "share_b"))
    a, b = (v if math.isfinite(v) else 0.0 for v in (a, b))
    with st.container(border=True, height="stretch", key="to_confidence"):
        st.markdown(":material/verified: **How sure are we?**")
        st.markdown(
            f'<div class="to-body">{a:.0%} of the price savings rest on matches that are '
            "certain or approved by a person (tier A); the other "
            f"{b:.0%} on strong automatic matches (tier B). Possible matches (tier C) are "
            "never counted.</div>"
            '<div class="to-stack" role="img" aria-label="Share of price savings by tier">'
            f'<div class="to-stack-a" style="width:{a * 100:.1f}%">A</div>'
            f'<div class="to-stack-b" style="width:{b * 100:.1f}%">B</div></div>'
            f'<div class="to-caption">A further {esc(money(strip["pending_review"]))} could '
            "be added once a person checks the uncertain matches.</div>",
            unsafe_allow_html=True,
        )
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            page_link("matching", "Check them yourself", ":material/fact_check:")
            show_working(
                strip["figure_ids"]["pending_review"], "the saving pending review", key="ov_pending"
            )


def render_findings(results, mode: str) -> None:
    with st.container(border=True, height="stretch", key="to_findings"):
        st.markdown(":material/search: **Three things worth a look**")
        for card in worth_a_look(results, mode):
            icon = _FINDING_ICONS.get(card["id"], "info")
            with st.container(key=f"to_finding_{card['id']}"):
                st.markdown(
                    f":material/{icon}: **{esc(card['title'])}**  \n{esc(card['text'])}",
                    unsafe_allow_html=True,
                )
                if card.get("available") and card.get("figure_id"):
                    show_working(
                        card["figure_id"],
                        card["title"],
                        key=f"ov_card_{card['id']}",
                        measure=card.get("measure"),
                    )


def _tour_card() -> None:
    st.markdown(
        icon_badge("tour", "amber") + '<div class="to-explore-title">New here?</div>'
        '<div class="to-explore-q">Two minutes, five stops: the five things most worth '
        "seeing.</div>",
        unsafe_allow_html=True,
    )
    render_tour_hook(key="tour_open_card", primary=False)


results = state.current_results()
mode = state.view()

top = render_hero(results, mode)
render_figures(results, mode)
render_story(results, mode, top)

left, right = st.container(key="to_grid_ov_sure").columns([5, 7], gap="medium")
with left:
    render_confidence(results, mode)
with right:
    render_findings(results, mode)

st.markdown(
    '<div class="to-section">Explore on your own</div>'
    '<div class="to-muted">Each screen answers one question. Start with whichever '
    "makes you curious.</div>",
    unsafe_allow_html=True,
)
render_explore(extra=_tour_card)
