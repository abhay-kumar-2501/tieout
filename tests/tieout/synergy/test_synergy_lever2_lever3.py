"""Levers 2 and 3 and the risk guardrails: PRD 10.1 edge cases and the rules of 5.3 to 5.5."""

from __future__ import annotations

import numpy as np
import pytest
from synergy_fixtures import Book, run

from tieout.synergy.lever2 import f
from tieout.synergy.risk import hhi
from tieout.synergy.trace import leaf_lines

L2 = "L11.01"  # standard criticality, cap 75%
IND = {"l2": L2, "category_type": "indirect"}


def services(book: Book, company: str, vendor: str, amount: float, **kwargs) -> None:
    book.buy(company, None, 1, amount, vendor=vendor, **(IND | kwargs))


def category_risk(out, l2: str = L2):
    return out.category_risk[out.category_risk["l2_code"] == l2].set_index("parent_id")


def opportunity(out, opp_id: str):
    return out.opportunities.set_index("opportunity_id").loc[opp_id]


def cap(value: float, l2: str = L2) -> dict:
    return {"category_settings": {l2: {"cap": value}}}


# ---------------------------------------------------------------- lever 2


def test_moved_fraction_formula() -> None:
    C, P, M = np.array([100.0, 100.0, 100.0]), np.array([50.0, 80.0, 50.0]), np.array([50.0] * 3)
    assert f(np.array([0.75, 0.75, 1.0]), C, P, M).tolist() == [0.5, 0.0, 1.0]
    assert f(np.array([0.75]), np.array([100.0]), np.array([50.0]), np.array([0.0]))[0] == 0


def test_consolidation_moves_pro_rata_up_to_the_cap() -> None:
    book = Book()
    services(book, "acquirer", "PV", 500_000)
    services(book, "target", "OV1", 300_000)
    services(book, "target", "OV2", 200_000)
    out = run(book.frames())
    risk = category_risk(out)
    # f = (0.75 x 1,000,000 - 500,000) / 500,000 = 0.5, applied to each other vendor.
    assert risk["f"].iloc[0] == pytest.approx(0.5)
    assert risk.loc["PV", "spend_after"] == pytest.approx(750_000)
    assert risk.loc["OV1", "spend_after"] == pytest.approx(150_000)
    assert risk.loc["OV2", "spend_after"] == pytest.approx(100_000)
    assert risk.loc["PV", "preferred"]
    opp = opportunity(out, f"L2:{L2}")
    assert opp["basis_base"] == pytest.approx(750_000)
    assert opp["base"] == pytest.approx(750_000 * 0.03 * 0.60)
    assert opp["low"] == pytest.approx(750_000 * 0.03 * 0.40)
    assert risk["hhi_before"].iloc[0] == pytest.approx(hhi(np.array([0.5, 0.3, 0.2])))
    assert risk["hhi_after"].iloc[0] == pytest.approx(hhi(np.array([0.75, 0.15, 0.10])))


def test_cap_already_exceeded_moves_nothing_and_reports_savings_forgone() -> None:
    book = Book()
    services(book, "acquirer", "PV", 800_000)
    services(book, "target", "OV", 200_000)
    out = run(book.frames(), assumptions=cap(0.60))
    opp = opportunity(out, f"L2:{L2}")
    assert opp["status"] == "cap_reached"
    assert opp["base"] == 0 and opp["basis_base"] == 0
    assert category_risk(out)["f"].iloc[0] == 0
    assert out.totals["lever2"]["savings_forgone"] == pytest.approx(1_000_000 * 0.03 * 0.60)


def test_consolidation_exceeding_the_cap_is_limited_and_the_forgone_saving_reported() -> None:
    book = Book()
    services(book, "acquirer", "PV", 500_000)
    services(book, "target", "OV", 500_000)
    out = run(book.frames())
    assert category_risk(out)["f"].iloc[0] == pytest.approx(0.5)
    uncapped, capped = 1_000_000 * 0.018, 750_000 * 0.018
    assert out.totals["lever2"]["savings_forgone"] == pytest.approx(uncapped - capped)
    assert category_risk(out)["savings_forgone"].iloc[0] == pytest.approx(uncapped - capped)


def test_lowering_one_categorys_cap_from_90_to_60_strictly_increases_savings_forgone() -> None:
    book = Book()
    services(book, "acquirer", "PV", 450_000)
    services(book, "target", "OV1", 350_000)
    services(book, "target", "OV2", 200_000)
    services(book, "acquirer", "PX", 400_000, l2="L12.01")
    services(book, "target", "PY", 400_000, l2="L12.01")
    at_90 = run(book.frames(), assumptions=cap(0.90))
    at_60 = run(book.frames(), assumptions=cap(0.60))
    assert 0 < category_risk(at_60)["f"].iloc[0] < category_risk(at_90)["f"].iloc[0] < 1
    assert at_60.totals["lever2"]["savings_forgone"] > at_90.totals["lever2"]["savings_forgone"]
    other = category_risk(at_60, "L12.01")["savings_forgone"].iloc[0]
    assert other == pytest.approx(category_risk(at_90, "L12.01")["savings_forgone"].iloc[0])


def test_single_vendor_category_is_sole_source_with_no_consolidation_saving() -> None:
    book = Book()
    services(book, "acquirer", "PV", 500_000)
    services(book, "target", "PV", 300_000)
    out = run(book.frames())
    assert not (out.opportunities["lever"] == 2).any()
    risk = category_risk(out)
    assert risk["lever2_status"].iloc[0] == "single_vendor"
    assert risk["sole_source_category"].all()
    assert out.totals["levers"]["lever2"]["base"] == 0


def test_category_bought_by_one_company_does_not_qualify() -> None:
    book = Book()
    services(book, "acquirer", "PV", 500_000)
    services(book, "acquirer", "OV", 300_000)
    services(book, "target", "TV", 100_000, l2="L12.01")
    out = run(book.frames())
    assert category_risk(out)["lever2_status"].iloc[0] == "one_company"
    assert out.totals["spend"]["addressable"] == 0


def test_no_overlapping_vendors_or_items_still_gets_lever2_but_no_lever1_or_lever3() -> None:
    book = Book()
    book.buy("acquirer", "A1", 10_000, 30.0, vendor="VA", terms=30, **IND)
    book.buy("target", "T1", 10_000, 20.0, vendor="VB", terms=60, **IND)
    out = run(book.frames())
    assert out.totals["levers"]["lever1"]["base"] == 0
    assert out.totals["levers"]["lever3"]["base"] == 0
    assert out.payment_terms.empty
    opp = opportunity(out, f"L2:{L2}")
    # VA holds 60% of 500,000; cap 75% moves (375,000 - 300,000) / 200,000 = 37.5% of VB.
    assert opp["basis_base"] == pytest.approx(375_000)
    assert opp["base"] > 0


def test_user_can_choose_the_preferred_vendor() -> None:
    book = Book()
    services(book, "acquirer", "PV", 500_000)
    services(book, "target", "OV", 300_000)
    chosen = {"lever2": {"preferred_vendor": {L2: "OV"}}}
    out = run(book.frames(), assumptions=chosen)
    assert opportunity(out, f"L2:{L2}")["parent_id"] == "OV"
    # f = (0.75 x 800,000 - 300,000) / 500,000 = 0.6.
    assert category_risk(out)["f"].iloc[0] == pytest.approx(0.6)
    unknown = run(book.frames(), assumptions={"lever2": {"preferred_vendor": {L2: "NOPE"}}})
    assert opportunity(unknown, f"L2:{L2}")["parent_id"] == "PV"


def test_lever1_switch_spend_is_left_out_of_lever2() -> None:
    book = Book()
    book.buy("acquirer", "A1", 100_000, 2.00, vendor="V1", **IND)
    book.buy("target", "T1", 100_000, 1.00, vendor="V9", **IND)
    services(book, "target", "V9", 250_000)
    out = run(book.frames([("A1", "T1", "A")]), assumptions=cap(1.0))
    switch = opportunity(out, "L1:CI000001:switch")
    assert switch["base"] > 0
    l2 = opportunity(out, f"L2:{L2}")
    # Preferred V9 holds 350,000 of 550,000; the acquirer's 200,000 is all switch spend.
    assert l2["status"] == "nothing_to_move" and l2["base"] == 0
    assert not set(leaf_lines(out.trace, "L1:CI000001:switch")) & set(
        leaf_lines(out.trace, f"L2:{L2}")
    )


def test_lever1_savings_travel_with_moved_spend_and_are_deducted_per_case() -> None:
    book = Book()
    book.buy("acquirer", "A1", 100_000, 2.00, vendor="OV", **IND)
    book.buy("target", "T1", 100_000, 1.50, vendor="OV", **IND)
    services(book, "target", "PV", 400_000)
    out = run(book.frames([("A1", "T1", "A")]), assumptions=cap(0.75))
    risk = category_risk(out)
    frac = risk["f"].iloc[0]
    assert frac == pytest.approx((0.75 * 750_000 - 400_000) / 350_000)
    lever1 = out.totals["levers"]["lever1"]
    for case in ("low", "base", "high"):
        b2 = out.totals["lever2"]["B2"][case]
        assert b2 == pytest.approx(400_000 + frac * (350_000 - lever1[case]))


def test_sole_source_items_are_flagged() -> None:
    book = Book()
    book.buy("acquirer", "A1", 1_000, 2.00, vendor="PV", **IND)
    book.buy("target", "T1", 1_000, 2.00, vendor="PV", **IND)
    book.buy("acquirer", "A2", 1_000, 2.00, vendor="PV", **IND)
    book.buy("target", "T2", 1_000, 2.00, vendor="OV", **IND)
    out = run(book.frames([("A1", "T1", "A"), ("A2", "T2", "B")]))
    risk = category_risk(out)
    assert risk["sole_source_items"].iloc[0] == 1
    assert risk["sole_source_item_ids"].iloc[0] == "CI000001"


# ---------------------------------------------------------------- lever 3


def test_identical_terms_give_no_lever3_opportunity() -> None:
    book = Book()
    services(book, "acquirer", "PV", 500_000, terms=45)
    services(book, "target", "PV", 300_000, terms=45)
    out = run(book.frames())
    assert not (out.opportunities["lever"] == 3).any()
    assert set(out.payment_terms["status"]) == {"identical_terms"}
    assert out.totals["one_time"]["cash"]["base"] == 0


def test_terms_less_than_a_day_apart_count_as_identical() -> None:
    book = Book()
    services(book, "acquirer", "PV", 500_000, terms=45)
    services(book, "acquirer", "PV", 1_000, terms=60)
    services(book, "target", "PV", 300_000, terms=45)
    out = run(book.frames())
    assert set(out.payment_terms["status"]) == {"identical_terms"}


def test_observed_days_used_only_when_both_companies_have_80_percent_coverage() -> None:
    book = Book()
    services(book, "acquirer", "PV", 800_000, terms=30, paid_after=40)
    services(book, "acquirer", "PV", 200_000, terms=30)
    services(book, "target", "PV", 500_000, terms=60, paid_after=75)
    observed = run(book.frames())
    terms = observed.payment_terms.set_index("company")
    assert set(terms["basis"]) == {"observed"}
    assert terms.loc["acquirer", "T"] == pytest.approx(40)
    assert terms.loc["acquirer", "coverage"] == pytest.approx(0.8)
    assert terms.loc["acquirer", "T_star"] == pytest.approx(75)

    book.buy("acquirer", None, 1, 10_000, vendor="PV", terms=30, **IND)  # coverage below 80%
    stated = run(book.frames()).payment_terms.set_index("company")
    assert set(stated["basis"]) == {"stated"}
    assert stated.loc["acquirer", "T"] == pytest.approx(30)


def test_vendor_where_a_company_has_neither_terms_nor_dates_is_excluded_and_listed() -> None:
    book = Book()
    services(book, "acquirer", "PV", 500_000, terms=30)
    services(book, "target", "PV", 300_000)
    services(book, "target", "OV", 100_000, terms=60, l2="L12.01")
    out = run(book.frames())
    terms = out.payment_terms.set_index("company")
    assert set(terms["status"]) == {"excluded"}
    assert "neither" in terms.loc["target", "reason"]
    assert not (out.opportunities["lever"] == 3).any()


def test_only_tier_a_and_b_vendor_links_count() -> None:
    book = Book()
    services(book, "acquirer", "PV", 500_000, terms=30, vendor_tier=None)
    services(book, "target", "PV", 300_000, terms=60, vendor_tier=None)
    out = run(book.frames())
    assert out.payment_terms.empty


def test_target_days_are_capped_at_the_maximum() -> None:
    book = Book()
    services(book, "acquirer", "PV", 365_000, terms=30)
    services(book, "target", "PV", 300_000, terms=120)
    out = run(book.frames())
    terms = out.payment_terms.set_index("company")
    assert terms.loc["acquirer", "T_star"] == 90
    assert out.totals["levers"]["lever3"]["gross"] == pytest.approx(60_000)


def test_lever3_spend_is_net_of_lever2_moves_and_both_levers_savings() -> None:
    book = Book()
    services(book, "acquirer", "PV", 500_000, terms=60)
    services(book, "target", "OV", 200_000, terms=30)
    services(book, "acquirer", "OV", 100_000, terms=60)
    out = run(book.frames())
    frac = category_risk(out)["f"].iloc[0]  # (600,000 - 500,000) / 300,000
    assert frac == pytest.approx(1 / 3)
    n2 = out.totals["levers"]["lever2"]["base"]
    terms = out.payment_terms.set_index("company")
    # Target's OV group keeps 2/3 of its spend, less its spend share of the lever-2 saving.
    expected = 200_000 * (1 - frac) - n2 * 200_000 / 800_000
    assert terms.loc["target", "S_base"] == pytest.approx(expected)
    assert terms.loc["target", "cash_base"] == pytest.approx(30 / 365 * expected * 0.5)
    assert terms.loc["acquirer", "cash_base"] == 0


def test_lever3_is_switched_off_without_terms_data() -> None:
    book = Book()
    services(book, "acquirer", "PV", 500_000)
    services(book, "target", "PV", 300_000, terms=60)
    out = run(book.frames())
    assert out.totals["checks"]["lever3_enabled"] is False
    assert "switched off" in out.totals["checks"]["lever3_message"]
    assert out.payment_terms.empty
    assert out.totals["one_time"]["cash"] == {"low": 0.0, "base": 0.0, "high": 0.0}


def test_cash_never_enters_a_recurring_total() -> None:
    book = Book()
    services(book, "acquirer", "PV", 1_200_000, terms=30)
    services(book, "target", "PV", 800_000, terms=60)
    out = run(book.frames())
    totals = out.totals
    assert totals["one_time"]["cash"]["base"] > 0
    assert totals["recurring"]["base"] == 0
    assert totals["defensible_range"] == {"low": 0.0, "high": 0.0}
    assert totals["spend"]["net_run_rate"]["base"] == pytest.approx(2_000_000)
