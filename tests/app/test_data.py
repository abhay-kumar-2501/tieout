"""The Data screen in demo mode (PRD 6.3, 6.8, 6.13)."""

from __future__ import annotations

import html
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tieout.results import Results
from tieout.views import data_quality_summary, spend_pareto

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app" / "main.py"
DATA = ROOT / "app" / "screens" / "data.py"
VIEW_LABELS = {"clean": "Clean team", "masked": "Integration office"}


def _open(view: str = "clean") -> AppTest:
    at = AppTest.from_file(str(MAIN), default_timeout=60)
    at.session_state["view_mode"] = VIEW_LABELS[view]
    at.run()
    at.switch_page(str(DATA)).run()
    assert not at.exception, [e.message for e in at.exception]
    return at


def _text(at: AppTest) -> str:
    out = [str(e.value) for kind in ("markdown", "caption", "info", "error", "success")
           for e in at.get(kind)]  # fmt: skip
    for frame in at.dataframe:
        out += [str(v) for v in frame.value.to_numpy().ravel()]
    out += [str(b.label) for b in at.button]
    return html.unescape("\n".join(out))


@pytest.fixture(scope="module")
def demo() -> Results:
    return Results.load(ROOT / "data" / "demo" / "results")


@pytest.mark.parametrize("view", ["clean", "masked"])
def test_renders_in_both_views(view: str, demo: Results) -> None:
    at = _open(view)
    text = _text(at)
    summary = data_quality_summary(demo, view)
    rows = sum(summary["rows"].values())
    assert "What did we receive and what state is it in?" in text
    assert f"{rows:,} purchasing lines" in text
    assert "What came in" in text and "What state it is in" in text
    assert "Use your own data" in text
    assert "1 blocking" not in text
    pareto = spend_pareto(demo, view)
    assert f"{pareto['vendor_records']:,} vendor records are {pareto['parent_vendors']:,}" in text
    assert len(at.get("plotly_chart")) == 2
    assert not at.get("spinner")


def test_findings_show_rows_and_dollars(demo: Results) -> None:
    at = _open()
    text = _text(at)
    findings = data_quality_summary(demo)["findings"]
    assert findings["amount_text"].iloc[0] in text
    labels = [e.label for e in at.expander]
    assert any(label.startswith("Warnings:") for label in labels)
    assert any(label.startswith("Notes:") for label in labels)


def test_pareto_has_a_table_alternative() -> None:
    at = _open()
    at.toggle(key="data_pareto_as_table").set_value(True).run()
    assert not at.exception
    assert not at.get("plotly_chart")
    assert "Cumulative share" in {c for f in at.dataframe for c in f.value.columns}


def test_ends_with_the_matching_link() -> None:
    at = _open()
    assert "How were two vendor lists made one?" in [p.label for p in at.get("page_link")]
