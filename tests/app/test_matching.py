"""Matching screen: renders in both views, decisions move the headline, undo, pack quantity,
and the integration-office page names no vendor or item."""

from __future__ import annotations

import html
import re
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from tieout.results import Results

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app" / "main.py"
PAGE = ROOT / "app" / "screens" / "matching.py"
VIEW_LABELS = {"clean": "Clean team", "masked": "Integration office"}


def _script(view_label: str, root: str) -> None:
    """The header and the Matching page in one run, so decisions show in the header."""
    import runpy
    import sys

    import streamlit as st

    sys.path.insert(0, root + "/app")
    from components.header import render_header

    st.session_state.setdefault("view_mode", view_label)
    render_header()
    runpy.run_path(root + "/app/screens/matching.py")


def _open(view: str = "clean") -> AppTest:
    at = AppTest.from_function(
        _script, args=(VIEW_LABELS[view], str(ROOT)), default_timeout=90
    ).run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def _texts(at: AppTest) -> list[str]:
    out: list[str] = []
    for kind in ("markdown", "caption", "info", "warning", "error", "success", "text"):
        out += [str(e.value) for e in at.get(kind)]
    for widget in [*at.selectbox, *at.multiselect]:
        out += [str(o) for o in widget.options] + [str(widget.label)]
    out += [str(b.label) for b in at.button]
    for frame in at.dataframe:
        value = frame.value
        out += [str(c) for c in value.columns] + [str(v) for v in value.to_numpy().ravel()]
    out += [e.proto.spec for e in at.get("plotly_chart")]
    return [html.unescape(t) for t in out]


def _range(at: AppTest) -> str:
    text = "\n".join(_texts(at))
    found = re.search(r"Defensible run-rate saving: </span><strong>([^<]+)</strong>", text)
    assert found, "header range not found"
    return found.group(1)


def _decisions(at: AppTest) -> pd.DataFrame:
    return at.session_state["_to_decisions"] if "_to_decisions" in at.session_state else None


@pytest.fixture(scope="module")
def demo() -> Results:
    return Results.load(ROOT / "data" / "demo" / "results")


def test_matching_renders_in_the_clean_team_view() -> None:
    at = _open()
    text = "\n".join(_texts(at))
    assert "Which vendors and items are the same, and how do we know?" in text
    assert "vendor records resolve to" in text
    assert "Approve (A)" in text and "Reject (X)" in text and "Defer (D)" in text
    assert "Vendor precision" in text  # the scorecard
    assert "What is that worth?" in text  # the closing link (a page link inside the shell)
    assert not at.get("spinner")


def _now_line(at: AppTest) -> str:
    text = "\n".join(_texts(at))
    found = re.search(r"Defensible run-rate saving now: (.*?)\. It updates", text)
    assert found, "the running figure is missing"
    return found.group(1)


def test_approving_items_moves_the_headline_and_undo_restores_it() -> None:
    at = _open()
    before = _now_line(at)
    assert _decisions(at) is None or _decisions(at).empty
    at.button(key="mt_approve").click().run()  # the first item: a vendor link, no saving yet
    assert not at.exception, [e.message for e in at.exception]
    decided = _decisions(at)
    assert len(decided) == 1 and decided["decision"].iloc[0] == "approve"
    for _ in range(4):  # a few more, until one carries a saving
        if _now_line(at) != before:
            break
        at.button(key="mt_approve").click().run()
    assert _now_line(at) != before
    assert "Defensible run-rate saving: " in "\n".join(_texts(at))  # the header, same run
    while len(_decisions(at)):
        at.button(key="mt_undo").click().run()
    assert _now_line(at) == before


def test_a_unit_of_measure_item_accepts_a_pack_quantity() -> None:
    at = _open()
    at.selectbox(key="mt_type").set_value("unit_flag").run()
    assert not at.exception, [e.message for e in at.exception]
    box = next(n for n in at.number_input if n.key.startswith("mt_pack_"))
    pair_id = box.key.removeprefix("mt_pack_")
    box.set_value(12.0).run()
    at.button(key="mt_approve").click().run()
    assert not at.exception, [e.message for e in at.exception]
    row = _decisions(at).iloc[-1]
    assert row["pair_id"] == pair_id and row["decision"] == "approve" and row["pack_qty"] == 12.0


def test_bulk_approval_shows_its_effect_and_is_one_undo() -> None:
    at = _open()
    at.selectbox(key="mt_bulk_type").set_value("vendor_match").run()
    assert any("This would approve" in t for t in _texts(at))
    at.button(key="mt_bulk_go").click().run()
    assert not at.exception, [e.message for e in at.exception]
    assert len(_decisions(at)) >= 1
    at.button(key="mt_undo").click().run()
    assert _decisions(at).empty


def test_masked_page_hides_the_queue_and_names_no_vendor_or_item(demo: Results) -> None:
    at = _open("masked")
    text = "\n".join(_texts(at))
    assert "Not available in the integration-office view" in text
    assert "Vendor precision" in text  # the scorecard stays
    assert not [b for b in at.button if b.key == "mt_approve"]
    names = set(demo.lines["vendor_name"].dropna().astype(str)) | set(
        demo.lines["item_description"].dropna().astype(str)
    )
    lowered = text.lower()
    leaked = [n for n in names if len(n) > 12 and n.lower() in lowered]
    assert not leaked[:3]
