"""The committed demo results (``make demo``) against a fresh run of seed 4 (PRD 9.2, 9.4)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tieout.pipeline import recompute
from tieout.results import Results, headline

pytestmark = pytest.mark.slow

DEMO_RESULTS = Path(__file__).resolve().parents[2] / "data" / "demo" / "results"


def _numbers(totals: dict) -> pd.Series:
    flat = pd.json_normalize(totals, sep=".").iloc[0]
    return flat[[isinstance(v, int | float) and not isinstance(v, bool) for v in flat]]


@pytest.fixture(scope="module")
def demo() -> Results:
    return Results.load(DEMO_RESULTS)


def test_committed_demo_results_equal_a_fresh_run(demo: Results, seed4) -> None:
    fresh = seed4.results
    expected = _numbers(fresh.totals)
    assert _numbers(demo.totals).to_dict() == pytest.approx(expected.to_dict(), abs=1e-6)
    assert demo.opportunities["opportunity_id"].tolist() == (
        fresh.opportunities["opportunity_id"].tolist()
    )
    assert headline(demo)["text"] == headline(fresh)["text"]


def test_demo_results_carry_the_evaluation_and_recompute_without_matching(demo: Results) -> None:
    assert demo.meta["scenario"] == "demo" and demo.meta["report_date"] == "2026-01-15"
    assert demo.scorecard is not None and demo.scorecard["passed"]
    assert demo.sensitivity is not None and set(demo.sensitivity["curves"]) == {
        "vendor_auto",
        "item_auto_cosine",
    }
    assert "scorecard" not in demo.meta["switched_off"]
    again = recompute(demo, demo.assumptions)
    assert _numbers(again.totals).to_dict() == pytest.approx(
        _numbers(demo.totals).to_dict(), abs=1e-6
    )
