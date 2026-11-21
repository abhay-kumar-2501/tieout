"""The PRD 5.2 worked example and one test per bridge filter, to the dollar.

Each filter test builds a table where exactly one step has work to do and
checks which groups' dollars that step removes.
"""

from __future__ import annotations

import pytest
from synergy_fixtures import Book, decision, removed, run, steps

from tieout.match.review import make_pair_id

ITEM = [("A1", "T1", "A")]


def _worked_example(book: Book) -> None:
    book.buy("acquirer", "A1", 10_000, 4.20, vendor="V1", parent="P")
    book.buy("target", "T1", 4_000, 3.60, vendor="V9", parent="P")


def test_worked_example_to_the_dollar() -> None:
    book = Book()
    _worked_example(book)
    out = run(book.frames(ITEM))
    lever = out.totals["levers"]["lever1"]
    assert round(lever["gross_gap"]) == 6_000
    assert (round(lever["low"]), round(lever["base"]), round(lever["high"])) == (
        3_000,
        4_200,
        5_100,
    )
    opp = out.opportunities.set_index("opportunity_id").loc["L1:CI000001:same_vendor"]
    assert opp["benchmark_company"] == "target"
    assert opp["benchmark_price"] == pytest.approx(3.60)
    assert round(opp["gross_gap"]) == 6_000
    assert opp["status"] == "in_range" and opp["tier"] == "A"


def test_worked_example_bridge_ties_out() -> None:
    book = Book()
    _worked_example(book)
    out = run(book.frames(ITEM))
    # Naive: the same single gap, then only capture probability removes dollars.
    assert out.totals["lever1"]["naive"] == pytest.approx(6_000)
    assert steps(out) == pytest.approx([0, 0, 0, 0, 0, 0, 1_800])
    assert out.totals["checks"]["bridge_tie_out_difference"] == pytest.approx(0, abs=1e-6)


def test_step1_removes_suspected_unit_error_and_unconverted_packs() -> None:
    book = Book()
    _worked_example(book)
    # A pack of 12 recorded as PK with no size: naive compares it at its recorded price.
    book.buy("acquirer", "A2", 1_200, 1.00)
    book.buy("target", "T2", 100, 12.00, status="unconverted")
    # An unconverted pack whose price ratio does not look like a pack size.
    book.buy("acquirer", "A3", 300, 1.00)
    book.buy("target", "T3", 100, 1.30, status="unconverted")
    out = run(book.frames([*ITEM, ("A2", "T2", "A"), ("A3", "T3", "A")]))
    step1 = removed(out, 1).groupby("canonical_item_id")["amount_removed"].sum()
    assert step1.to_dict() == pytest.approx({"CI000002": 1_100.0, "CI000003": 30.0})
    assert steps(out)[0] == pytest.approx(1_130)
    assert {"CI000002", "CI000003"} <= out.removed_at_step1
    assert "CI000001" not in out.removed_at_step1
    flag = out.review_items.set_index("type").loc["unit_flag"]
    assert flag["canonical_item_id"] == "CI000002"
    assert flag["message"] == "This 12.0× price gap looks like a pack of 12, not a saving"


def test_ratio_near_pack_factor_without_confirmed_conversion_is_flagged() -> None:
    book = Book()
    book.buy("acquirer", "A1", 1_200, 1.00)
    # Parsed as a pack of 1 by mistake: 11.8 per each looks like a box of 12.
    book.buy("target", "T1", 100, 11.80, status="parsed")
    out = run(book.frames(ITEM))
    assert out.totals["levers"]["lever1"]["gross_gap"] == 0
    assert removed(out, 1)["amount_removed"].sum() == pytest.approx(1_080)
    row = out.review_items.iloc[0]
    assert row["type"] == "unit_flag" and row["status"] == "pending"
    assert row["message"] == "This 11.8× price gap looks like a pack of 12, not a saving"


def test_step2_moves_tier_c_to_upside_pending_review() -> None:
    book = Book()
    _worked_example(book)
    book.buy("acquirer", "A2", 1_000, 2.00, vendor="V1", parent="P")
    book.buy("target", "T2", 1_000, 1.50, vendor="V9", parent="P")
    out = run(book.frames(ITEM, pending=[("A2", "T2", 0.7)]))
    step2 = removed(out, 2)
    assert set(step2["item_tier"]) == {"C"}
    assert step2["amount_removed"].sum() == pytest.approx(500)
    assert out.totals["lever1"]["upside_pending_review"] == pytest.approx(500 * 0.70)
    assert out.totals["levers"]["lever1"]["base"] == pytest.approx(4_200)
    pending = out.opportunities[out.opportunities["status"] == "pending_review"].iloc[0]
    assert pending["tier"] == "C" and pending["base"] == 0
    assert pending["upside_base"] == pytest.approx(350)


def test_step3_spot_buy_fails_the_test_and_next_qualifying_group_is_used() -> None:
    book = Book()
    _worked_example(book)
    book.buy("target", "T1", 50, 3.00, site="SPOT", lines=1)
    out = run(book.frames(ITEM))
    # Naive uses the $3.00 spot price: 1.20 x 10,000 + 0.60 x 4,000.
    assert out.totals["lever1"]["naive"] == pytest.approx(14_400)
    step3 = removed(out, 3).set_index("company")["amount_removed"]
    assert step3.to_dict() == pytest.approx({"acquirer": 6_000, "target": 2_400})
    assert out.totals["levers"]["lever1"]["gross_gap"] == pytest.approx(6_000)


def test_step3_volume_share_is_inclusive_at_ten_percent() -> None:
    book = Book()
    book.buy("acquirer", "A1", 9_000, 4.00)
    book.buy("target", "T1", 1_000, 3.00)  # exactly 10%: qualifies
    out = run(book.frames(ITEM))
    assert out.totals["levers"]["lever1"]["gross_gap"] == pytest.approx(9_000)


def test_step4_removes_gaps_against_the_same_company() -> None:
    book = Book()
    _worked_example(book)
    book.buy("target", "T1", 3_000, 4.00, site="S2", vendor="V9", parent="P")
    out = run(book.frames(ITEM))
    step4 = removed(out, 4)
    assert step4[["company", "site"]].values.tolist() == [["target", "S2"]]
    assert step4["amount_removed"].sum() == pytest.approx(1_200)
    assert out.totals["lever1"]["internal_variance"] == pytest.approx(1_200)
    assert out.internal_variance["internal_variance"].tolist() == pytest.approx([1_200])
    assert out.totals["levers"]["lever1"]["gross_gap"] == pytest.approx(6_000)


def test_step5_holds_incoterm_mismatch_and_blank_is_not_assessed() -> None:
    book = Book()
    book.buy("acquirer", "A1", 10_000, 4.20, incoterm="DDP", parent="P")
    book.buy("acquirer", "A1", 1_000, 4.60, site="S2", incoterm=None, parent="P")
    book.buy("target", "T1", 4_000, 3.60, vendor="V9", parent="P", incoterm="EXW")
    out = run(book.frames(ITEM))
    step5 = removed(out, 5)
    assert step5["site"].tolist() == ["S1"]
    assert step5["amount_removed"].sum() == pytest.approx(6_000)
    assert out.totals["levers"]["lever1"]["gross_gap"] == pytest.approx(1_000)
    review = out.review_items.set_index("type").loc["incoterm"]
    assert review["stake"] == pytest.approx(6_000)
    assert "EXW" in review["message"] and "DDP" in review["message"]


def test_incoterm_approval_makes_the_terms_comparable() -> None:
    book = Book()
    book.buy("acquirer", "A1", 10_000, 4.20, incoterm="DDP", parent="P")
    book.buy("target", "T1", 4_000, 3.60, vendor="V9", parent="P", incoterm="EXW")
    pair = make_pair_id("incoterm", "acquirer:A1", "target:T1")
    out = run(book.frames(ITEM), decisions=decision(pair))
    assert out.totals["levers"]["lever1"]["gross_gap"] == pytest.approx(6_000)
    assert out.review_items.iloc[0]["status"] == "approved"


def test_step6_removes_gap_on_volume_locked_beyond_the_horizon() -> None:
    book = Book()
    book.buy("acquirer", "A1", 5_000, 4.20, parent="P", contract_end="2029-06-30")
    book.buy("acquirer", "A1", 5_000, 4.20, parent="P", contract_end="2029-01-01")
    book.buy("target", "T1", 4_000, 3.60, vendor="V9", parent="P")
    out = run(book.frames(ITEM))
    assert steps(out)[5] == pytest.approx(3_000)
    groups = out.price_groups.set_index("company")
    assert groups.loc["acquirer", "a"] == pytest.approx(0.5)
    assert out.totals["checks"]["contract_lock_in_assessed"]


def test_no_contract_dates_means_a_is_one_and_not_assessed() -> None:
    book = Book()
    _worked_example(book)
    out = run(book.frames(ITEM))
    assert (out.price_groups["a"] == 1).all()
    assert not out.totals["checks"]["contract_lock_in_assessed"]


def test_step7_capture_probability_by_change_type() -> None:
    book = Book()
    _worked_example(book)
    book.buy("acquirer", "A1", 1_000, 4.60, site="S2", vendor="V2")  # another parent: switch
    out = run(book.frames(ITEM))
    opps = out.opportunities.set_index("change_type")
    assert opps.loc["same_vendor", "base"] == pytest.approx(6_000 * 0.70)
    assert opps.loc["switch", "base"] == pytest.approx(1_000 * 0.40)
    assert steps(out)[6] == pytest.approx(6_000 * 0.30 + 1_000 * 0.60)


def test_category_setting_overrides_the_global_probability() -> None:
    book = Book()
    _worked_example(book)
    settings = {"category_settings": {"L02.01": {"pi1_same_base": 0.5, "pi1_same_low": ""}}}
    out = run(book.frames(ITEM), assumptions=settings)
    lever = out.totals["levers"]["lever1"]
    assert lever["base"] == pytest.approx(3_000)
    assert lever["low"] == pytest.approx(3_000)  # blank cell: global default 0.50


def test_global_probability_override() -> None:
    book = Book()
    _worked_example(book)
    out = run(book.frames(ITEM), assumptions={"lever1": {"same_vendor": {"base": 0.8}}})
    assert out.totals["levers"]["lever1"]["base"] == pytest.approx(4_800)
