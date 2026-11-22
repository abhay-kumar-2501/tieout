"""Data (PRD 6.3, 2.3): what did we receive and what state is it in?

Demo mode and finished uploads show the same page: files, rows, period,
currency, the data-quality summary and the spend Pareto. In demo mode a picker
switches between the committed sample mergers; "Use your own data" swaps the
page for the five-step upload stepper, and "Back to demo" returns to the sample.
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
from components.style import esc, headline

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
    row = st.container(horizontal=True, vertical_alignment="bottom", gap="medium")
    if state.is_demo():
        options = state.samples()
        current = state.sample()
        if len(options) > 1:
            ids = [s.id for s in options]
            labels = {s.id: s.label for s in options}
            # Keyed by the sample shown, so the picker always opens on it.
            chosen = row.selectbox(
                f"Sample merger ({len(options)} fictional mergers)",
                ids,
                index=ids.index(current.id),
                format_func=labels.__getitem__,
                key=f"data_sample_{current.id}",
                width=460,
            )
            if chosen != current.id:
                state.set_sample(chosen)
                st.rerun()
        if row.button("Use your own data", key="data_use_own", type="primary"):
            upload_ui.start()
            st.rerun()
        st.markdown(
            '<div class="to-muted">These are the committed demo files for a fictional merger. '
            "Switching sample clears review decisions and assumption changes; saved scenarios "
            "are kept. You can size your own merger from two purchasing files instead.</div>",
            unsafe_allow_html=True,
        )
    else:
        row.markdown(
            '<div class="to-muted">These are your uploaded files. They exist in this '
            f"session's memory only. Back to demo returns to "
            f"{esc(state.sample().label)}.</div>",
            unsafe_allow_html=True,
            width="content",
        )
        if row.button("Back to demo", key="data_back_to_demo"):
            state.reset_to_demo()
            st.rerun()
    render_received(results, summary)
    render_findings(summary)
    render_pareto(results, mode)
    next_question("How were two vendor lists made one?", "matching")
