"""``sole_source``: the PRD 5.5 flags, taken from the engine's category risk."""

from __future__ import annotations

from pathlib import Path

import pytest

from tieout import results as views
from tieout.results import Results

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def results() -> Results:
    return Results.load(ROOT / "data" / "demo" / "results")


def test_flags_match_the_engine(results: Results) -> None:
    risk = results.category_risk.drop_duplicates("l2_code")
    clean = views.sole_source(results, "clean")
    assert len(clean["items"]) == int(risk["sole_source_items"].sum())
    assert int(clean["categories"]["items"].sum()) == len(clean["items"])
    assert int(clean["categories"]["category_sole_source"].sum()) <= int(
        risk["sole_source_category"].sum()
    )
    assert list(clean["items"].columns) == ["item", "description", "category"]


def test_masked_has_categories_only(results: Results) -> None:
    masked = views.sole_source(results, "masked")
    assert masked["items"].empty
    assert len(masked["categories"]) > 0
    names = set(results.vendor_parents["parent_name"].dropna())
    assert not names & set(masked["categories"]["vendor"])
