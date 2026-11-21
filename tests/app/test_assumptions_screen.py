"""Assumptions: forms, rejection, reset, the tornado and named scenarios."""

from __future__ import annotations

import html
import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tieout.results import Results

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app" / "main.py"
PAGE = ROOT / "app" / "screens" / "assumptions.py"
VIEW_LABELS = {"clean": "Clean team", "masked": "Integration office"}


def _open(view: str = "clean") -> AppTest:
    at = AppTest.from_file(str(MAIN), default_timeout=60)
    at.session_state["view_mode"] = VIEW_LABELS[view]
    at.run()
    at.switch_page(str(PAGE)).run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def _texts(at: AppTest) -> list[str]:
    out: list[str] = []
    for kind in ("markdown", "caption", "info", "warning", "error", "success", "code"):
        out += [str(e.value) for e in at.get(kind)]
    out += [str(b.label) for b in at.button] + [str(t.label) for t in at.toggle]
    for frame in at.dataframe:
        value = frame.value
        out += [str(c) for c in value.columns]
        out += [str(v) for v in value.to_numpy().ravel()]
    out += [e.proto.spec for e in at.get("plotly_chart")]
    return [html.unescape(t) for t in out]


def _header(at: AppTest) -> str:
    """The header's range plus the exact base figure in force (the range is rounded)."""
    shown = next(t for t in _texts(at) if "Defensible run-rate saving" in t)
    frame = _scenarios_frame(at)
    return (
        shown + frame[frame["Scenario"] == "Current assumptions"].iloc[0]["Recurring saving (base)"]
    )


def _num(at: AppTest, dotted: str):
    return next(n for n in at.number_input if n.key.startswith(f"asm:{dotted}:"))


def _button(at: AppTest, key: str):
    return next(b for b in at.button if b.key == key)


def _scenarios_frame(at: AppTest):
    return next(f.value for f in at.dataframe if "Net three-year value" in f.value.columns)


@pytest.fixture(scope="module")
def demo() -> Results:
    return Results.load(ROOT / "data" / "demo" / "results")


@pytest.mark.parametrize("view", ["clean", "masked"])
def test_page_renders_in_both_views(view: str) -> None:
    at = _open(view)
    text = "\n".join(_texts(at))
    assert "Which inputs drive the answer?" in text
    assert "All assumptions are at their defaults." in text
    assert not at.error
    assert "Take it with you" in [p.label for p in at.get("page_link")]
    assert len(at.get("plotly_chart")) == 1
    names = {s["Scenario"] for s in _scenarios_frame(at).to_dict("records")}
    assert {"Current assumptions", "Central (defaults)", "Conservative", "Stretch"} <= names


def test_every_default_is_shown_with_its_unit_and_range() -> None:
    at = _open()
    keys = {n.key.split(":")[1] for n in at.number_input}
    assert {"lever1.same_vendor.base", "caps.standard", "planning_horizon_months"} <= keys
    assert len(keys) >= 35
    text = "\n".join(_texts(at))
    assert "Default: Low 50%, Base 70%, High 85%. Valid: 0% to 100%." in text
    assert "Default: 36 months. Valid: 1 to 120 months." in text


def test_submitting_a_form_changes_the_headline_and_reset_restores_it() -> None:
    at = _open()
    before = _header(at)
    _num(at, "lever1.same_vendor.base").set_value(80.0)
    _button(at, "asm_apply_lever1").click().run()
    assert not at.exception, [e.message for e in at.exception]
    assert not at.error
    assert _header(at) != before
    assert "1 assumption changed from default." in "\n".join(_texts(at))
    assert "Base (changed)" in [n.label for n in at.number_input]
    _button(at, "asm_reset_all").click().run()
    assert _header(at) == before
    assert "All assumptions are at their defaults." in "\n".join(_texts(at))


def test_a_group_reset_restores_only_that_group() -> None:
    at = _open()
    before = _header(at)
    _num(at, "lever1.same_vendor.base").set_value(80.0)
    _button(at, "asm_apply_lever1").click().run()
    assert _header(at) != before
    _button(at, "asm_reset_lever1").click().run()
    assert _header(at) == before


def test_out_of_range_values_are_rejected_with_a_message_and_change_nothing() -> None:
    at = _open()
    before = _header(at)
    _num(at, "lever1.same_vendor.base").set_value(150.0)  # a share above 100%
    _button(at, "asm_apply_lever1").click().run()
    assert not at.exception
    assert any("must" in e.value for e in at.error)
    assert _header(at) == before
    assert "All assumptions are at their defaults." in "\n".join(_texts(at))


def test_low_above_base_is_rejected_by_the_engine() -> None:
    at = _open()
    _num(at, "lever1.same_vendor.low").set_value(95.0)
    _button(at, "asm_apply_lever1").click().run()
    assert any("low <= base <= high" in html.unescape(e.value) for e in at.error)


def test_a_range_the_engine_does_not_check_is_rejected_by_the_screen() -> None:
    at = _open()
    before = _header(at)
    _num(at, "planning_horizon_months").set_value(-5)
    _button(at, "asm_apply_general").click().run()
    assert any("planning_horizon_months must lie in [1, 120]" in e.value for e in at.error)
    assert _header(at) == before


def test_saving_a_scenario_adds_a_row_to_the_comparison() -> None:
    at = _open()
    rows = len(_scenarios_frame(at))
    _num(at, "lever2.capture.base").set_value(70.0)
    _button(at, "asm_apply_lever2").click().run()
    at.text_input(key="asm_scenario_name").set_value("Board case")
    _button(at, "asm_scenario_save").click().run()
    assert not at.exception, [e.message for e in at.exception]
    frame = _scenarios_frame(at)
    assert len(frame) == rows + 1
    assert "Board case" in list(frame["Scenario"])
    board = frame[frame["Scenario"] == "Board case"].iloc[0]
    current = frame[frame["Scenario"] == "Current assumptions"].iloc[0]
    assert board["Recurring saving (base)"] == current["Recurring saving (base)"]
    # a saved scenario can be put back in force
    _button(at, "asm_reset_all").click().run()
    at.selectbox(key="asm_scenario_pick").select("Board case")
    _button(at, "asm_scenario_use").click().run()
    assert "1 assumption changed from default." in "\n".join(_texts(at))


def test_a_scenario_needs_a_name() -> None:
    at = _open()
    _button(at, "asm_scenario_save").click().run()
    assert any("needs a name" in e.value for e in at.error)


def test_tornado_lists_twelve_inputs_and_toggles_to_a_table() -> None:
    at = _open()
    at.toggle(key="asm_tornado_as_table").set_value(True).run()
    table = next(f.value for f in at.dataframe if "Swing" in f.value.columns)
    assert len(table) == 12
    assert "Volume consolidation: chance of capturing the discount" in list(table["Assumption"])


def test_masked_page_shows_no_vendor_name(demo: Results) -> None:
    text = "\n".join(_texts(_open("masked")))
    assert "Integration-office view" in text
    names = set(demo.vendor_map["vendor_name"].dropna()) | set(
        demo.vendor_parents["parent_name"].dropna()
    )
    lowered = text.lower()
    assert not sorted(n for n in names if len(n) >= 4 and n.lower() in lowered)[:5]
    assert not re.search(r"\bCI\d{6}\b|\bLE\d{5}\b", text)
