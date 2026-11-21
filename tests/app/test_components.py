"""Shared components: the "Show working" dialog, page scaffolding and Plotly helpers."""

from __future__ import annotations

import pandas as pd
from streamlit.testing.v1 import AppTest


def _working_script() -> None:
    import streamlit as st
    from components.trace import show_working

    if st.session_state.get("masked"):
        st.session_state["view_mode"] = "Integration office"
    show_working("recurring.base", "the run-rate saving", key="t")
    show_working("lever1.bridge.step_1", "unit-of-measure errors", key="s")


def _texts(at: AppTest) -> list[str]:
    out = [str(e.value) for kind in ("markdown", "caption", "info") for e in at.get(kind)]
    out += [str(v) for f in at.dataframe for v in f.value.to_numpy().ravel()]
    return out


def test_show_working_opens_a_dialog_and_drills_down() -> None:
    at = AppTest.from_function(_working_script, default_timeout=60).run()
    assert [b.label for b in at.button] == ["Show working", "Show working"]
    at.button(key="show_working_t").click().run()
    assert not at.exception
    text = "\n".join(_texts(at))
    assert "Run-rate saving (levers 1 and 2)" in text and "Source rows (" in text
    components = at.dataframe[0].value
    assert list(components["Component"]) == [
        "Price harmonisation (lever 1)",
        "Volume consolidation (lever 2)",
    ]


def _inline_script() -> None:
    from components.trace import render_trace

    render_trace("recurring.base", "inline")


def test_trace_panel_drills_down_and_back() -> None:
    """The panel inside the dialog, drawn inline: AppTest cannot re-run a dialog fragment."""
    at = AppTest.from_function(_inline_script, default_timeout=60).run()
    key = next(k for k in at.session_state if str(k).startswith("inline_components_"))
    at.session_state[key] = {"selection": {"rows": [0], "columns": [], "cells": []}}
    at.run()
    assert not at.exception
    text = "\n".join(_texts(at))
    assert "**Price harmonisation (lever 1)** (level 2)" in text
    assert "L01.05 Castings & forgings" in text  # categories under lever 1
    at.button(key="inline_back").click().run()
    assert not at.exception
    text = "\n".join(_texts(at))
    assert "**Run-rate saving (levers 1 and 2)**" in text and "(level 2)" not in text


def test_show_working_for_a_bridge_step_lists_items_in_its_own_measure() -> None:
    at = AppTest.from_function(_working_script, default_timeout=60).run()
    at.button(key="show_working_s").click().run()
    assert not at.exception
    text = "\n".join(_texts(at))
    assert "PACKING TAPE 3IN 60YD 2.0MIL TAN" in text  # the largest unit trap


def test_masked_show_working_stops_at_category_level() -> None:
    at = AppTest.from_function(_working_script, default_timeout=60)
    at.session_state["masked"] = True
    at.run()
    at.button(key="show_working_t").click().run()
    text = "\n".join(_texts(at))
    assert "Run-rate saving (levers 1 and 2)" in text
    assert "Source rows: Not available in the integration-office view." in text
    at.button(key="show_working_s").click().run()
    assert any("Not available in the integration-office view" in t for t in _texts(at))


def _page_script() -> None:
    from components.page import (
        empty_state,
        error_state,
        loading_state,
        missing_data,
        next_question,
        page_question,
        render_placeholder,
        section,
    )

    page_question("What is the answer?")
    section("A section", "A caption with $1 and $2.")
    empty_state("Nothing left to review", "All $184k cleared.", link_text="Go", target_module="x")
    loading_state(["2,480 vendor records", "1,930 after normalisation"], done=1)
    error_state("The file has no amounts.", "120 rows, $1.2M, are affected.", "Map a column.")
    missing_data("Add contract end dates to enable contract-aware phasing")
    next_question("Why is it so much smaller?", "synergies")
    render_placeholder("Placeholder?", "M9")


def test_page_scaffolding_renders_every_state_block() -> None:
    at = AppTest.from_function(_page_script, default_timeout=30).run()
    assert not at.exception
    text = "\n".join(_texts(at) + [e.value for e in at.error])
    assert "What is the answer?" in text and "Nothing left to review" in text
    assert "&#36;184k" in text  # dollar signs never start maths in Markdown
    assert "Next: Why is it so much smaller?" in text  # no navigation: plain text fallback
    assert "Coming in milestone M9" in text
    assert "120 rows" in text


def test_selection_helpers_read_both_event_shapes() -> None:
    from components.plotting import selected_point, selected_row

    assert selected_point(None) is None
    assert selected_point({"selection": {"points": []}}) is None
    assert selected_point({"selection": {"points": [{"point_index": 3}]}}) == 3
    assert selected_point({"selection": {"points": [{"point_number": 2}]}}) == 2
    assert selected_row({"selection": {"rows": [4]}}) == 4
    assert selected_row({"selection": {"rows": []}}) is None


def test_bridge_figure_stacks_bars_over_a_transparent_base() -> None:
    from components.plotting import TRANSPARENT, bridge_figure, exact_money

    from tieout import theme

    frame = pd.DataFrame(
        {
            "label": ["Naive figure", "Unit-of-measure errors", "Defensible run-rate saving"],
            "kind": ["total", "decrease", "total"],
            "amount": [100.0, -40.0, 60.0],
            "bar_base": [0.0, 60.0, 0.0],
            "bar_height": [100.0, 40.0, 60.0],
            "low": [float("nan"), float("nan"), 50.0],
            "high": [float("nan"), float("nan"), 70.0],
            "text": ["$0k", "−$0k", "$0k"],
        }
    )
    fig = bridge_figure(frame)
    base, bars = fig.data
    assert fig.layout.barmode == "stack" and base.marker.color == TRANSPARENT
    assert list(bars.y) == [100.0, 40.0, 60.0]
    assert list(bars.marker.color) == [theme.MUTED, theme.CONTROL, theme.TEAL]
    assert list(bars.error_y.array) == [0.0, 0.0, 10.0]
    assert fig.layout.font.family.startswith(theme.FONT_SANS)
    assert fig.layout.clickmode == "event+select"
    assert exact_money(-7642579.4) == "−$7,642,579"
