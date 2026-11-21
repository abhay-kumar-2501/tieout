"""Export (PRD 6.3, 7): take it with you.

Workbook, deck and static charts are built in memory on request, in the
current view mode, from the same results the screens show. Review decisions
download as the re-importable CSV. Nothing is written to disk.
"""

from __future__ import annotations

import streamlit as st
from components import exports, state
from components.page import page_question, section
from components.style import esc, headline
from streamlit.errors import StreamlitAPIException

from tieout.match.review import write_decisions_csv

results = state.current_results()
mode = state.view()
label = "integration-office" if mode == "masked" else "clean-team"

page_question("Workbook and deck")
headline("Take the analysis with you: every file ties to the figures on screen.")
st.caption(
    esc(
        f"Files are built in the {label} view you have selected, from this session's results "
        "(decisions and assumptions included), and are held in memory only. Every number comes "
        "from the same calculation as the screens, so totals match what you see."
    )
)


def _offer(kind: str, title: str, text: str, action: str) -> None:
    export = exports.EXPORTS[kind]
    with st.container(border=True):
        st.markdown(f"**{esc(title)}**")
        st.markdown(esc(text))
        data = exports.cached(kind, results, mode)
        if data is None:
            if st.button(action, key=f"exp_build_{kind}", icon=":material/build:"):
                with st.spinner(f"Building {export.file_name}"):
                    exports.get(kind, results, mode)
                st.rerun()
            return
        st.download_button(
            f"Download {export.file_name} ({exports.size_text(len(data))})",
            data,
            file_name=export.file_name,
            mime=export.mime,
            key=f"exp_dl_{kind}",
            icon=":material/download:",
            type="primary",
        )


section("Workbook and deck")
left, right = st.container(key="to_grid_exp_files").columns(2, gap="medium")
with left:
    _offer(
        "workbook",
        "Workbook (.xlsx)",
        "The model behind the numbers: the summary and bridge as live formulas over the "
        "opportunity, spend and assumption tabs, with "
        + (
            "the category-level aggregates of the integration-office view."
            if mode == "masked"
            else "item-level detail, links and payment terms."
        ),
        "Export workbook",
    )
with right:
    _offer(
        "deck",
        "Deck (.pptx)",
        "Eight slides with the answer first: the bridge, the baseline, the matching scorecard, "
        "risk and phasing, the assumptions and what the analysis cannot see. Charts are native "
        "and editable, and each slide says the data is illustrative when it is.",
        "Export deck",
    )

section("Charts and review decisions")
left, right = st.container(key="to_grid_exp_more").columns(2, gap="medium")
with left:
    _offer(
        "charts",
        "Static chart images (.png, zipped)",
        "The eight charts used in the deck and on the landing page: bridge, waterfall, phasing, "
        "prioritisation, scorecard, tornado, Pareto and concentration.",
        "Export chart images",
    )
with right, st.container(border=True):
    st.markdown("**Review decisions (.csv)**")
    st.markdown(
        esc(
            "Your approve, reject and defer decisions in the format the run command reads back "
            "with --review-decisions, so a review carries over to the next run."
        )
    )
    if mode == "masked":
        st.info("Review decisions are not available in the integration-office view.")
    else:
        log = state.decisions()
        st.download_button(
            f"Download review_decisions.csv ({len(log):,} decisions)",
            write_decisions_csv(log) or "",
            file_name="review_decisions.csv",
            mime="text/csv",
            key="exp_dl_decisions",
            icon=":material/download:",
            disabled=log.empty,
        )
        if log.empty:
            st.caption("No decisions yet. Approve or reject matches on the Matching screen.")

st.divider()
try:
    st.page_link(
        "screens/method_limits.py", label="Method & limits", icon=":material/arrow_forward:"
    )
except StreamlitAPIException:  # page run on its own, outside the navigation
    st.caption("Method & limits")
