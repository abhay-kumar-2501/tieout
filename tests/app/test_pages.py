"""Overview and Synergies: interactions, and what the integration-office view shows.

Chart selections are injected through the chart's session-state key, the way
the front end reports a selected bar (PRD 9.3).
"""

from __future__ import annotations

import html
import re
import time
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from tieout.results import Results

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app" / "main.py"
PAGES = ROOT / "app" / "pages"
VIEW_LABELS = {"clean": "Clean team", "masked": "Integration office"}


def _open(page: str, view: str = "clean") -> AppTest:
    """The app on ``page``. Overview is the default page, so it runs under the full shell
    (header included); ``switch_page`` runs another page's script on its own."""
    at = AppTest.from_file(str(MAIN), default_timeout=60)
    at.session_state["view_mode"] = VIEW_LABELS[view]
    at.run()
    if page != "overview":
        at.switch_page(str(PAGES / f"{page}.py")).run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def _select_bar(at: AppTest, key: str, index: int) -> AppTest:
    at.session_state[key] = {
        "selection": {"points": [{"point_index": index}], "point_indices": [index], "box": [],
                      "lasso": []},
    }  # fmt: skip
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def _texts(at: AppTest) -> list[str]:
    """Every piece of rendered text: markdown, captions, alerts, widgets, tables and charts."""
    out: list[str] = []
    for kind in ("markdown", "caption", "info", "warning", "error", "success", "title",
                 "header", "subheader", "text", "code"):  # fmt: skip
        out += [str(e.value) for e in at.get(kind)]
    for widget in [*at.selectbox, *at.multiselect]:
        out += [str(o) for o in widget.options] + [str(widget.label)]
    out += [str(b.label) for b in at.button] + [str(t.label) for t in at.toggle]
    for frame in at.dataframe:
        value = frame.value
        out += [str(c) for c in value.columns]
        out += [str(v) for v in value.to_numpy().ravel()]
    out += [e.proto.spec for e in at.get("plotly_chart")]
    return [html.unescape(t) for t in out]


@pytest.fixture(scope="module")
def demo() -> Results:
    return Results.load(ROOT / "data" / "demo" / "results")


def test_overview_answers_first(demo: Results) -> None:
    at = _open("overview")
    text = "\n".join(_texts(at))
    assert "of run-rate savings is defensible" in text
    assert "Run-rate P&L saving" in text and "One-time cash release" in text
    assert "never added to the run-rate saving" in text
    assert "Why is it so much smaller than the naive figure?" in [
        p.label for p in at.get("page_link")
    ]
    assert not at.get("spinner")


def test_overview_show_working_opens_the_trace_dialog() -> None:
    at = _open("overview")
    at.button(key="show_working_ov_headline").click().run()
    assert not at.exception, [e.message for e in at.exception]
    text = "\n".join(_texts(at))
    assert "Run-rate saving (levers 1 and 2)" in text
    assert "Price harmonisation (lever 1)" in text  # a component
    assert "Source rows (" in text


def test_masked_show_working_stops_at_category_level() -> None:
    at = _open("overview", "masked")
    at.button(key="show_working_ov_card_unit_trap").click().run()
    assert not at.exception
    assert any("Not available in the integration-office view" in t for t in _texts(at))


def test_overview_bridge_bar_opens_its_refused_list() -> None:
    at = _select_bar(_open("overview"), "ov_bridge", 1)
    text = "\n".join(_texts(at))
    assert "Unit-of-measure errors" in text and "175 of 175 rows" in text


def _overview_after_change(page: str) -> None:
    import runpy

    import streamlit as st
    from components import state

    if st.session_state.pop("change", False):
        state.set_assumptions({"lever1": {"same_vendor": {"base": 0.5}, "switch": {"base": 0.2}}})
    runpy.run_path(page)


def test_overview_rerun_after_an_assumption_change_is_fast() -> None:
    at = AppTest.from_function(
        _overview_after_change, args=(str(PAGES / "overview.py"),), default_timeout=60
    ).run()
    before = [m.value for m in at.markdown]
    at.session_state["change"] = True
    started = time.perf_counter()
    at.run()
    changed = time.perf_counter() - started
    assert not at.exception, [e.message for e in at.exception]
    after = [m.value for m in at.markdown]
    assert after != before  # the figures moved
    started = time.perf_counter()
    at.run()
    assert time.perf_counter() - started < 1.0  # nothing changed: cached
    assert changed < 2.0  # about 0.4 s locally; twice the 1 s target, as for engine timings


def _header_script() -> None:
    import streamlit as st
    from components import state
    from components.header import render_header

    render_header()
    st.markdown(f"VIEW={state.view()}")


def test_view_switch_in_the_header() -> None:
    """The header's control sets the view every page reads; clicking the selected option
    again (which clears a segmented control) keeps the last view."""
    at = AppTest.from_function(_header_script, default_timeout=60).run()
    text = "\n".join(_texts(at))
    assert "VIEW=clean" in text and "Clean-team view" in text
    assert "Demo merger" in text and "Illustrative — synthetic data" in text
    assert "Defensible run-rate saving: " in text and "$6–13M" in text
    at.get("button_group")[0].set_value("Integration office").run()
    text = "\n".join(_texts(at))
    assert "VIEW=masked" in text and "not a security control" in text
    at.get("button_group")[0].set_value(None).run()
    assert not at.exception
    assert any("VIEW=masked" in t for t in _texts(at))


def test_masked_overview_names_categories_not_items() -> None:
    text = "\n".join(_texts(_open("overview", "masked")))
    assert "not a security control" in text
    assert "L01.05 Castings & forgings" in text  # the largest saving, by category


def test_synergies_bar_selection_drives_the_refused_list() -> None:
    at = _open("synergies")
    assert at.selectbox(key="syn_step").value == 1
    at = _select_bar(at, "syn_bridge", 2)
    assert at.selectbox(key="syn_step").value == 2
    assert any("907 of 907 rows" in t for t in _texts(at))
    # The user can still pick another step after a chart selection.
    at.selectbox(key="syn_step").set_value(4).run()
    assert at.selectbox(key="syn_step").value == 4
    # Selecting a total opens its working inline.
    at = _select_bar(at, "syn_bridge", 10)
    assert any("Run-rate saving (levers 1 and 2)" in t for t in _texts(at))


def test_synergies_refused_item_opens_its_source_rows() -> None:
    at = _open("synergies")
    at.session_state["syn_refused_list_1"] = {"selection": {"rows": [0], "columns": [],
                                                            "cells": []}}  # fmt: skip
    at.run()
    assert not at.exception
    assert any("Source rows (" in t for t in _texts(at))


def test_synergies_view_as_table_and_dispersion() -> None:
    at = _open("synergies")
    assert any("buying groups pay between" in t for t in _texts(at))
    at.toggle(key="syn_bridge_as_table").set_value(True).run()
    assert not at.exception
    tables = [f.value for f in at.dataframe]
    assert any(list(t.columns) == ["Bar", "Amount", "Items"] for t in tables)


@pytest.mark.parametrize("page", ["overview", "synergies"])
def test_masked_view_shows_no_vendor_name_unit_price_or_item(page: str, demo: Results) -> None:
    at = _open(page, "masked")
    texts = _texts(at)
    chart = {"overview": "ov_bridge", "synergies": "syn_bridge"}[page]
    at = _select_bar(at, chart, 2)  # a removal step's refused list
    texts += _texts(at)
    at = _select_bar(at, chart, 10)  # the run-rate total's working
    texts += _texts(at)
    text = "\n".join(texts)
    if page == "overview":
        assert "Integration-office view" in text  # the header ran too

    names = set(demo.vendor_map["vendor_name"].dropna()) | set(
        demo.vendor_parents["parent_name"].dropna()
    )
    lowered = text.lower()
    leaked = sorted(n for n in names if len(n) >= 4 and n.lower() in lowered)
    assert not leaked, leaked[:5]
    descriptions = {d for d in demo.item_map["description"].dropna() if len(d) >= 12}
    assert not [d for d in descriptions if d in text]
    assert not re.search(r"\$\d[\d,]*\.\d{4}\b", text)  # no unit price
    assert not re.search(r"\bCI\d{6}\b|\bLE\d{5}\b", text)  # no item or vendor id


def test_clean_view_does_show_detail(demo: Results) -> None:
    """The leak test above can fail: the clean-team view carries the same detail."""
    at = _open("synergies")
    text = "\n".join(_texts(at))
    descriptions = {d for d in demo.item_map["description"].dropna() if len(d) >= 12}
    assert [d for d in descriptions if d in text]
    assert re.search(r"\$\d[\d,]*\.\d{4}\b", text)
    assert isinstance(at.dataframe[0].value, pd.DataFrame)
