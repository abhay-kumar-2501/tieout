"""PRD 10.1 edge cases for lever 1, benchmark tie-breaks and fallback, review decisions."""

from __future__ import annotations

import pandas as pd
import pytest
from synergy_fixtures import META, Book, decision, removed, run

from tieout.match.review import make_pair_id

ITEM = [("A1", "T1", "A")]
UNIT_PAIR = make_pair_id("unit_flag", "acquirer:A1", "target:T1")


def _gross(out) -> float:
    return out.totals["levers"]["lever1"]["gross_gap"]


def test_item_bought_by_one_company_has_no_opportunity() -> None:
    book = Book()
    book.buy("acquirer", "A1", 1_000, 5.00, site="S1")
    book.buy("acquirer", "A1", 1_000, 3.00, site="S2")
    out = run(book.frames())
    assert out.opportunities.empty
    assert out.totals["lever1"]["naive"] == 0
    assert out.price_groups.empty


def test_group_below_the_benchmark_contributes_zero_not_negative() -> None:
    book = Book()
    book.buy("acquirer", "A1", 10_000, 4.20)
    book.buy("acquirer", "A1", 100, 3.00, site="SPOT", lines=1)  # below p*, fails the tests
    book.buy("target", "T1", 4_000, 3.60, vendor="V9")
    out = run(book.frames(ITEM))
    spot = out.price_groups.set_index("site").loc["SPOT"]
    assert spot["p_star"] == pytest.approx(3.60)
    assert spot["G1"] == 0 and spot["N1_base"] == 0
    assert _gross(out) == pytest.approx(6_000)


def test_credits_are_netted_within_the_group() -> None:
    book = Book()
    book.buy("acquirer", "A1", 10_000, 4.20)
    book.buy("acquirer", "A1", -1_000, 4.20, lines=1)
    book.buy("target", "T1", 4_000, 3.60, vendor="V9")
    out = run(book.frames(ITEM))
    group = out.price_groups.set_index("company").loc["acquirer"]
    assert group["q"] == pytest.approx(9_000)
    assert group["credit_lines"] == 1
    assert _gross(out) == pytest.approx(0.60 * 9_000)


def test_group_netting_to_zero_or_less_has_no_price() -> None:
    book = Book()
    book.buy("acquirer", "A1", 10_000, 4.20)
    book.buy("acquirer", "A1", 100, 9.00, site="S2", lines=1)
    book.buy("acquirer", "A1", -150, 9.00, site="S2", lines=1)
    book.buy("target", "T1", 4_000, 3.60, vendor="V9")
    out = run(book.frames(ITEM))
    s2 = out.price_groups.set_index("site").loc["S2"]
    assert pd.isna(s2["p"]) and s2["G1"] == 0
    assert _gross(out) == pytest.approx(6_000)


def test_item_with_net_quantity_at_or_below_zero_is_excluded() -> None:
    book = Book()
    book.buy("acquirer", "A1", 100, 5.00, lines=1)
    book.buy("acquirer", "A1", -100, 5.00, lines=1)
    book.buy("target", "T1", 50, 3.00, lines=1)
    book.buy("target", "T1", -60, 3.00, lines=1)
    out = run(book.frames(ITEM))
    assert out.totals["lever1"]["naive"] == 0
    assert out.opportunities.empty


def test_fallback_when_no_group_qualifies_uses_the_lower_company_price() -> None:
    book = Book()
    book.buy("acquirer", "A1", 10_000, 4.20, lines=2, parent="P")
    book.buy("acquirer", "A1", 500, 4.40, lines=1, site="S2", vendor="V2")
    book.buy("target", "T1", 4_000, 3.60, lines=2, vendor="V9", parent="P")
    out = run(book.frames(ITEM))
    assert out.price_groups["benchmark_fallback"].all()
    assert (out.price_groups["benchmark_company"] == "target").all()
    groups = out.price_groups[out.price_groups["company"] == "acquirer"].set_index("site")
    # Same parent also supplies the holder company: same_vendor; V2 does not: switch.
    assert groups.loc["S1", "change_type"] == "same_vendor"
    assert groups.loc["S2", "change_type"] == "switch"
    assert groups.loc["S1", "G1"] == pytest.approx(6_000)
    assert groups.loc["S2", "G1"] == pytest.approx(0.80 * 500)


def test_aggregated_mode_skips_the_line_test() -> None:
    book = Book()
    book.buy("acquirer", "A1", 10_000, 4.20, lines=1)
    book.buy("target", "T1", 4_000, 3.60, lines=1, vendor="V9")
    lines_mode = run(book.frames(ITEM))
    aggregated = run(book.frames(ITEM), meta={**META, "aggregated": True})
    assert lines_mode.price_groups["benchmark_fallback"].all()
    assert not aggregated.price_groups["benchmark_fallback"].any()
    assert not aggregated.totals["checks"]["benchmark_line_test"]
    assert _gross(aggregated) == pytest.approx(6_000)


@pytest.mark.parametrize(
    ("target_qty", "holder"),
    [(6_000, "target"), (5_000, "acquirer"), (4_000, "acquirer")],
)
def test_price_ties_go_to_larger_quantity_then_the_acquirer(target_qty: int, holder: str) -> None:
    book = Book()
    book.buy("acquirer", "A1", 5_000, 3.60)
    book.buy("acquirer", "A1", 1_000, 4.00, site="S2")
    book.buy("target", "T1", target_qty, 3.60, vendor="V9")
    out = run(book.frames(ITEM))
    assert set(out.price_groups["benchmark_company"]) == {holder}
    expected = 400.0 if holder == "target" else 0.0
    assert _gross(out) == pytest.approx(expected)


def test_base_dimension_clash_is_removed_at_step1() -> None:
    book = Book()
    book.buy("acquirer", "A1", 1_000, 4.00)
    book.buy("target", "T1", 1_000, 3.80, vendor="V9")
    frames = book.frames(ITEM)
    frames["lines"].loc[frames["lines"]["company"] == "target", "base_unit"] = "kilogram"
    out = run(frames)
    assert _gross(out) == 0
    assert removed(out, 1)["amount_removed"].sum() == pytest.approx(200)
    assert "CI000001" in out.removed_at_step1


def _parsed_wrong(book: Book) -> None:
    book.buy("acquirer", "A1", 1_200, 1.00)
    book.buy("target", "T1", 100, 11.80, status="parsed", vendor="V9")


def test_approving_a_unit_flag_clears_it() -> None:
    book = Book()
    _parsed_wrong(book)
    out = run(book.frames(ITEM), decisions=decision(UNIT_PAIR))
    assert _gross(out) == pytest.approx(1_080)
    row = out.review_items.iloc[0]
    assert row["status"] == "approved" and row["stake"] == pytest.approx(1_080)


def test_rejecting_a_unit_flag_keeps_the_pair_out() -> None:
    book = Book()
    _parsed_wrong(book)
    out = run(book.frames(ITEM), decisions=decision(UNIT_PAIR, "reject"))
    assert _gross(out) == 0
    assert out.review_items.iloc[0]["status"] == "rejected"


def test_reviewer_pack_quantity_confirms_and_reruns_the_comparison() -> None:
    book = Book()
    book.buy("acquirer", "A1", 1_200, 1.00)
    book.buy("target", "T1", 100, 10.80, status="unconverted", vendor="V9")
    before = run(book.frames(ITEM))
    assert _gross(before) == 0 and before.review_items.iloc[0]["status"] == "pending"
    out = run(book.frames(ITEM), decisions=decision(UNIT_PAIR, pack_qty=12))
    target = out.price_groups.set_index("company").loc["target"]
    assert target["conv_status"] == "confirmed"
    assert target["p"] == pytest.approx(0.90)
    assert _gross(out) == pytest.approx(0.10 * 1_200)
    assert out.review_items.iloc[0]["status"] == "approved"
    assert "CI000001" not in out.removed_at_step1


def test_pack_quantity_that_still_fails_the_ratio_test_stays_pending() -> None:
    book = Book()
    book.buy("acquirer", "A1", 1_200, 1.00)
    book.buy("target", "T1", 100, 12.00, status="unconverted", vendor="V9")
    out = run(book.frames(ITEM), decisions=decision(UNIT_PAIR, pack_qty=2))
    assert _gross(out) == 0
    row = out.review_items.iloc[0]
    assert row["status"] == "pending"
    # Both sides now confirmed, so only rule (b) can fire.
    assert row["message"] == "This 6.0× gap is too large to be a price difference; check units"


def test_tier_b_savings_are_shown_separately() -> None:
    book = Book()
    book.buy("acquirer", "A1", 10_000, 4.20, parent="P")
    book.buy("target", "T1", 4_000, 3.60, vendor="V9", parent="P", vendor_tier="B")
    out = run(book.frames([("A1", "T1", "B")]))
    assert out.totals["lever1"]["tier_b"]["base"] == pytest.approx(4_200)
    assert out.totals["lever1"]["tier_a"]["base"] == 0
    opp = out.opportunities.iloc[0]
    assert (opp["tier"], opp["vendor_tier"]) == ("B", "B")


def test_tier_c_record_uses_only_its_single_best_candidate() -> None:
    book = Book()
    book.buy("acquirer", "A1", 1_000, 2.00)
    book.buy("target", "T1", 1_000, 1.50, vendor="V9")
    book.buy("target", "T2", 1_000, 1.00, vendor="V9")
    out = run(book.frames(pending=[("A1", "T1", 0.70), ("A1", "T2", 0.65)]))
    assert out.totals["lever1"]["naive"] == pytest.approx(500)
    assert removed(out, 2)["amount_removed"].sum() == pytest.approx(500)
    assert out.totals["levers"]["lever1"]["base"] == 0


def test_scorecard_outputs_cover_matched_items_only() -> None:
    book = Book()
    book.buy("acquirer", "A1", 10_000, 4.20, parent="P")
    book.buy("target", "T1", 4_000, 3.60, vendor="V9", parent="P")
    book.buy("acquirer", "A2", 1_000, 2.00)
    book.buy("target", "T2", 1_000, 1.50, vendor="V9")
    out = run(book.frames(ITEM, pending=[("A2", "T2", 0.7)]))
    gaps = out.item_gross_gaps.set_index("canonical_item_id")["gross_gap"]
    assert gaps.to_dict() == pytest.approx({"CI000001": 6_000})


def test_no_mapped_category_reports_zero_levers_without_error() -> None:
    book = Book()
    book.buy("acquirer", None, 100, 2.00, l2=None, terms=30)
    book.buy("target", None, 100, 2.00, vendor="V2", l2=None, terms=60)
    book.buy("acquirer", "A1", 100, 2.00, l2=None, terms=30)
    out = run(book.frames())
    assert out.totals["recurring"] == {"low": 0.0, "base": 0.0, "high": 0.0}
    assert out.totals["spend"]["baseline"] == pytest.approx(600)
    assert out.totals["spend"]["addressable"] == 0
    assert out.opportunities.empty
