"""The landing page's story: its sections, and the real records it shows (PRD 9.4)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
SITE = ROOT / "site"
MANIFEST = json.loads((ROOT / "data/samples.json").read_text(encoding="utf-8"))["samples"]


def _samples() -> list[dict]:
    text = (SITE / "data.js").read_text(encoding="utf-8")
    return json.loads(re.search(r"const TIEOUT = (\{.*\});", text, re.S).group(1))["samples"]


SAMPLES = {s["id"]: s for s in _samples()}


def _html() -> str:
    return (SITE / "index.html").read_text(encoding="utf-8")


def test_page_has_the_story_sections_in_order():
    html = _html()
    ids = ["top", "story", "ch-shop", "ch-records", "money", "trust", "get", "hood"]
    positions = [html.index(f'id="{i}"') for i in ids]
    assert positions == sorted(positions)
    # One h1, chapter headings below the section headings.
    assert html.count("<h1") == 1
    assert len(re.findall(r'<h3 id="ch\d-h"', html)) == 4


def test_interactive_parts_are_buttons_and_keyboard_reachable():
    html = _html()
    assert html.count('role="tab"') == 3
    assert 'id="tie-button"' in html and 'type="button"' in html
    assert html.count("<details") >= 4 and "<summary>" in html
    script = (SITE / "main.js").read_text(encoding="utf-8")
    for key in ("ArrowRight", "ArrowLeft", "Escape", "aria-pressed", "aria-selected"):
        assert key in script


def test_motion_is_off_under_reduced_motion():
    css = (SITE / "styles.css").read_text(encoding="utf-8")
    block = css[css.index("@media (prefers-reduced-motion: reduce)") :]
    assert "animation: none" in block and "transition: none" in block
    assert "[data-reveal]" in block.split("}\n}")[0]
    assert "prefers-reduced-motion" in (SITE / "main.js").read_text(encoding="utf-8")


def test_honesty_label_stays_on_the_page():
    html = _html()
    assert html.count("Illustrative: synthetic data") >= 2
    assert "All data is synthetic and illustrative." in html


@pytest.mark.parametrize("sample", MANIFEST, ids=lambda s: s["id"])
def test_overlap_counts_come_from_the_results(sample):
    story = SAMPLES[sample["id"]]["story"]
    results = ROOT / sample["results"]
    items = pd.read_parquet(results / "item_map.parquet")
    o = story["overlap"]
    assert o["items"]["a"] == int((items["company"] == "acquirer").sum())
    assert o["items"]["b"] == int((items["company"] == "target").sum())
    assert 0 < o["items"]["both"] <= min(o["items"]["a"], o["items"]["b"])
    assert 0 < o["vendors"]["both"] <= min(o["vendors"]["a"], o["vendors"]["b"])
    spend = json.loads((results / "results.json").read_text())["meta"]["in_scope_spend"]
    assert o["spend"] == {"a": spend["acquirer"], "b": spend["target"]}


@pytest.mark.parametrize("sample", MANIFEST, ids=lambda s: s["id"])
def test_examples_are_real_records(sample):
    """Each example's text is a record's own description and supplier name, unedited."""
    examples = SAMPLES[sample["id"]]["story"]["examples"]
    assert set(examples) == {"match", "lookalike", "trap"}
    results = ROOT / sample["results"]
    items = pd.read_parquet(results / "item_map.parquet")
    lines = pd.read_parquet(results / "lines.parquet", columns=["vendor_name"])
    descriptions = set(items["description"].dropna())
    vendors = set(lines["vendor_name"].dropna())
    pairs = pd.read_parquet(results / "item_pairs.parquet")
    for kind, ex in examples.items():
        assert ex is not None, kind
        assert ex["kind"] == kind
        for side, company in (("a", "acquirer"), ("b", "target")):
            card = ex[side]
            assert card["company"] == company
            assert "".join(t for t, _ in card["item_tokens"]) == card["description"]
            assert "".join(t for t, _ in card["vendor_tokens"]) == card["vendor"]
            assert card["description"] in descriptions
            assert card["vendor"] in vendors
            assert card["price"] > 0
        if kind != "trap":
            assert ex["evidence"] in set(pairs["evidence"])
    match = examples["match"]
    assert match["same_supplier"] and match["notes"]["item"]
    groups = [{g for _, g in match[s]["item_tokens"] if g > 0} for s in "ab"]
    assert groups[0] == groups[1]  # every highlighted word has a partner on the other card
    look = examples["lookalike"]
    assert all(any(g == -3 for _, g in look[s]["item_tokens"]) for s in "ab")


@pytest.mark.parametrize("sample", MANIFEST, ids=lambda s: s["id"])
def test_trap_is_a_unit_error_removed_by_bridge_step_one(sample):
    trap = SAMPLES[sample["id"]]["story"]["examples"]["trap"]
    assert trap["a"]["uom"] != trap["b"]["uom"]
    high, low = sorted((trap["a"]["price"], trap["b"]["price"]), reverse=True)
    assert trap["ratio"] == pytest.approx(high / low, abs=0.06)
    detail = pd.read_parquet(ROOT / sample["results"] / "bridge_detail.parquet")
    step1 = detail[detail["step"] == 1].groupby("canonical_item_id")["amount_removed"].sum()
    assert any(abs(v - trap["removed"]) < 0.01 for v in step1)
    assert trap["removed"] <= SAMPLES[sample["id"]]["lever1"]["steps"][0]
