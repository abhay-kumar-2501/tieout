"""Matching (PRD 6.3, 6.5, 4.7): which vendors and items are the same, and how do we know?

Stage counts by tier, the review queue (clean-team view only) and the accuracy scorecard with
the threshold-sensitivity curves. Every figure comes from a view function.
"""

from __future__ import annotations

from components import state
from components.explain import screen_intro
from components.matching_queue import render_queue
from components.matching_scorecard import render_scorecard, render_sensitivity
from components.matching_stages import render_stages
from components.page import empty_state, next_question, page_question, section
from components.style import headline

from tieout.views import matching_counts


def _headline(counts: dict) -> str:
    vendors, items = counts["vendors"], counts["items"]
    return (
        f"{vendors['records']:,} supplier records turn out to be {vendors['legal_entities']:,} "
        f"real companies, and {items['records']:,} item records {items['canonical_items']:,} "
        f"distinct items; {vendors['pending_review'] + items['pending_review']:,} pairs wait "
        "for a person to decide."
    )


results = state.current_results()
mode = state.view()
counts = matching_counts(results, mode)

page_question("Which vendors and items are the same, and how do we know?")
screen_intro(
    "The two companies name the same suppliers and items differently: \"Acme Corp.\" and "
    "\"ACME Corporation\", a box of 12 and a single piece. This screen shows how the records "
    "were paired up and how accurate that is. You can also decide the uncertain pairs "
    "yourself; each decision updates the saving shown at the top.",
    ("Tier A, B, C", "Part number (MPN)", "Unit of measure (UoM)", "Precision and recall",
     "Threshold"),
    key="matching",
)  # fmt: skip
headline(_headline(counts))

section(
    "How two lists became one", "Records by how they were matched; the queue below holds the rest."
)
render_stages(counts)
if not any(counts[k]["by_tier"].get(t, 0) for k in ("vendors", "items") for t in ("A", "B")):
    empty_state(
        "No overlap found",
        "The two files share no matched vendors or items. Check that both companies' categories "
        "are mapped to the common taxonomy, then run matching again.",
    )

section(
    "Review the uncertain matches",
    "Each decision re-runs the savings; watch the headline range above.",
)
render_queue()

section("How accurate is the matching?", "Scored against hidden truth the tool never sees.")
render_scorecard()

section("How much do the thresholds matter?")
render_sensitivity()

next_question("What is that worth?", "synergies")
