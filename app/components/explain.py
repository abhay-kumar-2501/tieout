"""Plain words for a newcomer: the glossary, each screen's introduction and the Explore cards.

One experience for everyone. Every screen opens with a sentence in everyday words on
what it answers and what you can do there, and the trade terms it uses are explained
in place ("What do these words mean?") rather than in a separate simple mode. The
full glossary and the method sit on Method & limits.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import streamlit as st
from streamlit.errors import StreamlitAPIException

from components.style import esc, icon_badge

__all__ = [
    "EXPLORE",
    "GLOSSARY",
    "STEP_REASONS",
    "ExploreCard",
    "glossary_popover",
    "page_link",
    "render_explore",
    "render_glossary",
    "screen_intro",
    "step_reason",
]

#: Term -> one plain sentence or two. Keys are the words as they appear on screen.
GLOSSARY: dict[str, str] = {
    "Naive figure": (
        "The quick estimate: every price gap between the two companies counted as a saving, "
        "with no checks. It is the figure the merger case usually starts from."
    ),
    "Defensible saving": (
        "What is left once every saving that cannot be checked or will not happen is "
        "removed. Each dollar traces back to rows in both companies' files."
    ),
    "Run-rate saving": (
        "The saving you get every year once the changes are in place. One-off amounts, "
        "such as cash freed or costs paid once, are kept apart and never added to it."
    ),
    "Lever": (
        "One way of saving money. Tie-Out sizes three: paying the better of the two "
        "companies' prices (price harmonisation), buying from fewer suppliers (volume "
        "consolidation) and aligning payment terms (a one-time cash release)."
    ),
    "Price harmonisation": (
        "Where one company pays more than the other for the same item, moving both to the "
        "better price. Lever 1."
    ),
    "Volume consolidation": (
        "Moving a category's spend to fewer suppliers so the larger volume earns a better "
        "price. Lever 2."
    ),
    "One-time cash release": (
        "Cash freed once when both companies pay suppliers on the same schedule. Useful, "
        "but not a yearly saving."
    ),
    "Tier A, B, C": (
        "How sure a match is. A: certain, or approved by a person. B: made automatically "
        "and backed by other evidence. C: possible, waiting for a person; never counted."
    ),
    "Pending review": (
        "Savings on matches a person has not yet confirmed. They are shown but not counted "
        "until someone approves the match on Matching."
    ),
    "Unit of measure (UoM)": (
        "How a price is quoted: each, box of 12, metre, kilogram. A price per box next to a "
        "price per piece looks like a huge gap but is not a saving."
    ),
    "Part number (MPN)": (
        "The manufacturer's own code for an item. When both companies record the same "
        "maker and code, that is the strongest sign two records are the same thing."
    ),
    "Precision and recall": (
        "Precision: of the matches the tool made, the share that are right. Recall: of the "
        "real matches, the share it found. Both are checked against an answer key the tool "
        "never sees."
    ),
    "Threshold": (
        "How similar two records must be before the tool calls them a match. Higher is "
        "stricter: fewer wrong matches, more missed ones."
    ),
    "Benchmark price": (
        "The better price an item is aimed at. It must be a price paid regularly, not a "
        "single cheap one-off purchase."
    ),
    "Capture probability": (
        "The share of a price gap expected to be won in negotiation. Not every supplier "
        "agrees to a lower price."
    ),
    "Concentration cap": (
        "The largest share of a category any one supplier group may hold after "
        "consolidation, so the business never depends too much on one supplier."
    ),
    "Concentration index": (
        "One number for how much a category's spend sits with a few suppliers: higher "
        "means more dependent on them."
    ),
    "Sole source": "An item or category bought from only one supplier: no fallback if it fails.",
    "Clean team and integration office": (
        "Before a deal closes, competition law lets only a small ring-fenced clean team see "
        "the other company's prices and supplier names. The clean-team view shows full "
        "detail; the integration-office view hides names and prices. Here it is a "
        "presentation, not a security control."
    ),
    "Scenario": "A saved set of assumptions, so you can compare one what-if with another.",
    "Tornado chart": (
        "Each assumption is nudged down and up in turn; the longest bars are the "
        "assumptions that move the answer most."
    ),
    "Spend Pareto": (
        "Suppliers sorted from largest spend to smallest, showing how few of them make up "
        "most of the money."
    ),
}

#: Bridge bar label -> why the step exists, in one line anyone can follow.
STEP_REASONS: dict[str, str] = {
    "Naive figure": "Every price gap between the two companies, counted as a saving.",
    "Unit-of-measure errors": (
        "A box of 12 next to a single piece looks like a 12× price gap. It is not a saving."
    ),
    "Unverified matches": (
        "Records we cannot yet confirm are the same item. A person can approve them later."
    ),
    "Spot-price benchmark": (
        "The cheapest one-off purchase is not a fair target; we aim at a price paid regularly."
    ),
    "Internal variance": (
        "Gaps between one company's own sites. It could fix those alone, without the merger."
    ),
    "Non-comparable terms": (
        "One price includes delivery and the other does not, so they are not like for like."
    ),
    "Contract lock-in": "Some volume is tied up in contracts that cannot change yet.",
    "Capture probability": "Not every supplier says yes; we count only what is likely to be won.",
    "Defensible price harmonisation (lever 1)": (
        "What survives: the better price, on items both companies buy."
    ),
    "+ Volume consolidation (lever 2)": (
        "Added: better prices from buying more from fewer suppliers, within safety caps."
    ),
    "Defensible run-rate saving": "The yearly saving you can defend, low to high.",
}


def step_reason(label: str) -> str:
    """The plain reason for a bridge bar, or an empty string for an unknown label."""
    return STEP_REASONS.get(label, "")


def page_link(module: str, label: str, icon: str, *, primary: bool = False) -> None:
    """A link to a screen by its module name; plain text when the page runs on its own."""
    try:
        st.page_link(
            f"screens/{module}.py",
            label=label,
            icon=icon,
            width="stretch" if primary else "content",
        )
    except StreamlitAPIException:  # outside the navigation (tests run a page on its own)
        st.caption(esc(label))


def glossary_popover(terms: Sequence[str], key: str) -> None:
    """A small "What do these words mean?" popover with the given glossary terms."""
    with st.popover("What do these words mean?", icon=":material/help:", key=key):
        for term in terms:
            st.markdown(f"**{esc(term)}**  \n{esc(GLOSSARY[term])}")
        page_link("method_limits", "All the words, and how it works", ":material/menu_book:")


def screen_intro(text: str, terms: Sequence[str] = (), *, key: str) -> None:
    """The screen's opening sentence in everyday words, with its glossary beside it."""
    with st.container(
        key=f"to_intro_{key}",
        horizontal=True,
        vertical_alignment="center",
        gap="medium",
        wrap=False,  # the stylesheet lets it wrap on a phone
    ):
        st.markdown(
            f'<div class="to-intro">{esc(text)}</div>', unsafe_allow_html=True, width="stretch"
        )
        if terms:
            glossary_popover(terms, key=f"glossary_{key}")


def render_glossary() -> None:
    """Every term, two to a row on a wide screen (Method & limits)."""
    items = "".join(
        f'<div class="to-term"><div class="to-term-name">{esc(term)}</div>'
        f'<div class="to-term-text">{esc(text)}</div></div>'
        for term, text in GLOSSARY.items()
    )
    st.markdown(f'<div class="to-glossary">{items}</div>', unsafe_allow_html=True)


@dataclass(frozen=True)
class ExploreCard:
    module: str  # page module name, as in ``next_question``
    title: str
    icon: str  # Material icon name, without the ``:material/`` wrapper
    question: str
    action: str


EXPLORE: tuple[ExploreCard, ...] = (
    ExploreCard(
        "matching",
        "Matching",
        "join_inner",
        "How do we know two records are the same thing?",
        "Check the matches",
    ),
    ExploreCard(
        "synergies",
        "Synergies",
        "savings",
        "Which items save the most, and what did we refuse to count?",
        "Open the savings",
    ),
    ExploreCard(
        "risk_roadmap",
        "Risk & roadmap",
        "shield",
        "What does it cost to never depend on one supplier?",
        "Move the safety cap",
    ),
    ExploreCard(
        "assumptions",
        "Assumptions",
        "tune",
        "What happens if you change the assumptions?",
        "Try a what-if",
    ),
    ExploreCard(
        "data",
        "Data",
        "table_view",
        "What was in the two companies' files, and how messy was it?",
        "See the data",
    ),
    ExploreCard(
        "export",
        "Export",
        "download",
        "Can I take this into a meeting?",
        "Get the workbook and deck",
    ),
    ExploreCard(
        "method_limits",
        "Method & limits",
        "menu_book",
        "How does it work, and what can it not see?",
        "Read how it works",
    ),
)


def _card(card: ExploreCard) -> None:
    with st.container(border=True, height="stretch", key=f"to_explore_{card.module}"):
        st.markdown(
            icon_badge(card.icon) + f'<div class="to-explore-title">{esc(card.title)}</div>'
            f'<div class="to-explore-q">{esc(card.question)}</div>',
            unsafe_allow_html=True,
        )
        page_link(card.module, card.action, ":material/arrow_forward:")


def render_explore(extra=None) -> None:
    """The Explore grid: a card per screen, four to a row, two on a tablet, one on a phone.

    ``extra`` draws an eighth card in the last slot (the Overview puts the tour there).
    """
    rows = (EXPLORE[:4], EXPLORE[4:])
    for number, row in enumerate(rows):
        columns = st.container(key=f"to_quad_explore_{number}").columns(4, gap="medium")
        for column, card in zip(columns, row, strict=False):
            with column:
                _card(card)
        if number == 1 and extra is not None and len(row) < 4:
            with (
                columns[len(row)],
                st.container(border=True, height="stretch", key="to_explore_tour"),
            ):
                extra()
