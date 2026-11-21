"""Data (PRD 6.3, 2.3): what did we receive and what state is it in?

Demo mode and finished uploads show the same page: files, rows, period,
currency, the data-quality summary and the spend Pareto. "Use your own data"
swaps it for the five-step upload stepper.
"""

from __future__ import annotations

import streamlit as st
from components import state, upload_ui
from components.data_view import (
    finding_headline,
    render_findings,
    render_pareto,
    render_received,
)
from components.page import next_question, page_question
from components.style import headline, muted

from tieout.views import data_quality_summary

page_question("What did we receive and what state is it in?")

if upload_ui.is_active():
    headline("Add your two purchasing files and Tie-Out sizes the synergies from them.")
    upload_ui.render_upload_flow()
else:
    results = state.current_results()
    mode = state.view()
    summary = data_quality_summary(results, mode)
    headline(finding_headline(summary))
    if state.is_demo():
        left, right = st.columns([3, 1], vertical_alignment="center")
        with left:
            muted("These are the committed demo files for a fictional merger.")
        if right.button("Use your own data", key="data_use_own", type="primary"):
            upload_ui.start()
            st.rerun()
    else:
        left, right = st.columns([3, 1], vertical_alignment="center")
        with left:
            muted("These are your uploaded files. They exist in this session's memory only.")
        with right:
            if st.button("Back to demo", key="data_back_to_demo"):
                state.reset_to_demo()
                st.rerun()
    render_received(results, summary)
    render_findings(summary)
    render_pareto(results, mode)
    next_question("How were two vendor lists made one?", "matching")
