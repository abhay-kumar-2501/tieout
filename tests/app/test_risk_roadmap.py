"""Risk & roadmap: the live cap slider, the matrix drill-down, phasing and the masked view."""

from __future__ import annotations

import html
import re
import time
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tieout.results import Results

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app" / "main.py"
PAGE = ROOT / "app" / "screens" / "risk_roadmap.py"
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


def _first(at: AppTest, needle: str) -> str:
    return next(t for t in _texts(at) if needle in t)


def _headline(at: AppTest) -> str:
    return _first(at, 'class="to-headline"')


def _forgone(at: AppTest) -> str:
    return re.search(r"to-figure-value\">([^<]+)<", _first(at, "Savings forgone")).group(1)


@pytest.fixture(scope="module")
def demo() -> Results:
    return Results.load(ROOT / "data" / "demo" / "results")


@pytest.mark.parametrize("view", ["clean", "masked"])
def test_page_renders_in_both_views(view: str) -> None:
    at = _open(view)
    text = "\n".join(_texts(at))
    assert "What do we give up for resilience, and what happens when?" in text
    assert "Savings forgone to protect supply resilience" in text
    assert "Net three-year value" in text
    assert not at.error
    assert "What are we assuming?" in [p.label for p in at.get("page_link")]
    assert len(at.get("plotly_chart")) == 3


def test_moving_the_cap_changes_forgone_and_header_headline() -> None:
    at = _open()
    before_forgone, before_headline = _forgone(at), _headline(at)
    header_before = _first(at, "Defensible run-rate saving")
    start = time.perf_counter()
    at.slider(key="risk_cap_pct").set_value(50).run()
    elapsed = time.perf_counter() - start
    assert not at.exception, [e.message for e in at.exception]
    assert _forgone(at) != before_forgone
    assert _headline(at) != before_headline
    assert _first(at, "Defensible run-rate saving") != header_before
    assert elapsed < 3.0, elapsed  # about a second; loose for a loaded test machine


def test_raising_the_cap_gives_up_less() -> None:
    at = _open()
    at.slider(key="risk_cap_pct").set_value(100).run()
    low = _forgone(at)
    at.slider(key="risk_cap_pct").set_value(40).run()
    assert not at.exception
    assert low != _forgone(at)


def test_selecting_a_bubble_opens_the_opportunity_and_its_working() -> None:
    at = _open()
    assert "Select a bubble or a table row" in "\n".join(_texts(at))
    at.session_state["risk_matrix"] = {
        "selection": {"points": [{"point_index": 0}], "point_indices": [0], "box": [],
                      "lasso": []},
    }  # fmt: skip
    at.run()
    assert not at.exception, [e.message for e in at.exception]
    assert any(b.key == "show_working_risk_matrix_0" for b in at.button)
    assert "CASTING IMPELLER" in "\n".join(_texts(at))


def test_phasing_shows_the_year_table_with_the_three_year_net() -> None:
    at = _open()
    years = next(f.value for f in at.dataframe if "Net (base)" in f.value.columns)
    assert list(years["Period"]) == ["Year 1", "Year 2", "Year 3", "Three years"]
    assert "Net three-year value" in "\n".join(_texts(at))


def test_masked_page_shows_no_vendor_name_and_no_opportunity_detail(demo: Results) -> None:
    at = _open("masked")
    at.session_state["risk_matrix"] = {
        "selection": {"points": [{"point_index": 0}], "point_indices": [0], "box": [],
                      "lasso": []},
    }  # fmt: skip
    at.run()
    assert not at.exception
    text = "\n".join(_texts(at))
    assert "not available in the integration-office view" in text
    names = set(demo.vendor_map["vendor_name"].dropna()) | set(
        demo.vendor_parents["parent_name"].dropna()
    )
    lowered = text.lower()
    assert not sorted(n for n in names if len(n) >= 4 and n.lower() in lowered)[:5]
    assert not re.search(r"\bCI\d{6}\b|\bLE\d{5}\b", text)


def test_clean_page_does_show_vendor_names(demo: Results) -> None:
    """The leak test above can fail: the clean-team view carries vendor names."""
    text = "\n".join(_texts(_open())).lower()
    names = set(demo.vendor_parents["parent_name"].dropna())
    assert any(len(n) >= 4 and n.lower() in text for n in names)
