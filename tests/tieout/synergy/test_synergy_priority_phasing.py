"""Prioritisation (PRD 5.7), phasing and one-time costs (5.6), reconciliation (5.8), tornado."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from synergy_fixtures import META, Book, run

from tieout.synergy.phasing import (
    CONTRACT,
    GLOBAL_RAMP,
    line_available_month,
    months_active,
    start_quarter,
)
from tieout.synergy.prioritise import (
    CHANGE_SCORES,
    complexity,
    contract_score,
    criticality_score,
    match_score,
    sites_score,
    wave,
)
from tieout.synergy.reconcile import band_check
from tieout.synergy.sensitivity import SCENARIOS, TOP, moves, tornado
from tieout.synergy.stage import precompute, recurring_base

CLOSE = pd.Timestamp("2026-01-01")
LIMIT = pd.Timestamp("2029-01-01")


def opportunity(out, opp_id: str) -> pd.Series:
    return out.opportunities.set_index("opportunity_id").loc[opp_id]


# ---------------------------------------------------------------- factor tables


def test_contract_lock_in_score_table() -> None:
    months = [0, 1, 6, 7, 12, 13, 24, 25, 40]
    assert contract_score(np.array(months)).tolist() == [1, 2, 2, 3, 3, 4, 4, 5, 5]


def test_sites_score_table() -> None:
    sites = [1, 2, 3, 4, 5, 9, 10, 30]
    assert sites_score(np.array(sites)).tolist() == [1, 2, 3, 3, 4, 4, 5, 5]


def test_change_criticality_and_match_score_tables() -> None:
    assert CHANGE_SCORES == {
        "same_vendor": 1,
        "terms": 2,
        "existing_vendor": 3,
        "re_tender": 4,
        "new_vendor": 5,
    }
    crit = criticality_score(np.array(["non_critical", "standard", "critical"]))
    assert crit.tolist() == [1, 3, 5]
    tiers = np.array(["A", "A", "B", None], dtype=object)
    assert match_score(tiers, np.array([False, True, False, False])).tolist() == [1, 2, 5, 1]


def test_complexity_is_the_weighted_average() -> None:
    scores = pd.DataFrame(
        {
            "score_contract": [1, 5],
            "score_change": [1, 5],
            "score_criticality": [3, 1],
            "score_sites": [2, 5],
            "score_match": [1, 5],
        }
    )
    expected = [0.3 + 0.25 + 0.6 + 0.2 + 0.15, 1.5 + 1.25 + 0.2 + 0.5 + 0.75]
    assert complexity(scores) == pytest.approx(expected)


def test_wave_rules_apply_in_order() -> None:
    lever = np.array([1, 1, 3, 1, 2, 3, 1])
    change = np.array(["same_vendor", "same_vendor", "terms", "switch", "consolidation", "terms",
                       "same_vendor"])  # fmt: skip
    available = np.array([13, 3, 0, 0, 0, 4, 2])
    score = np.array([1.0, 2.5, 2.0, 1.0, 1.0, 1.0, 2.6])
    assert wave(lever, change, available, score).tolist() == [3, 1, 1, 2, 2, 2, 2]


# ---------------------------------------------------------------- end-to-end priority


def test_quick_same_vendor_opportunity_is_wave_one() -> None:
    book = Book()
    book.buy("acquirer", "A1", 1_000, 2.00, l2="L07.01")  # non-critical
    book.buy("target", "T1", 1_000, 1.50, l2="L07.01")
    out = run(book.frames([("A1", "T1", "A")]))
    opp = opportunity(out, "L1:CI000001:same_vendor")
    assert opp[["score_contract", "score_change", "score_criticality"]].tolist() == [1, 1, 1]
    assert opp["score_sites"] == 1 and opp["score_match"] == 1
    assert opp["complexity"] == pytest.approx(1.0)
    assert opp["available_month"] == 0 and opp["start_month"] == 3
    assert opp["wave"] == 1


def test_switch_to_a_vendor_new_to_the_company_scores_five_and_is_wave_two() -> None:
    book = Book()
    book.buy("acquirer", "A1", 1_000, 2.00, vendor="V1", l2="L01.02")  # critical
    book.buy("target", "T1", 1_000, 1.50, vendor="V9", l2="L01.02")
    out = run(book.frames([("A1", "T1", "B")], human=()))
    opp = opportunity(out, "L1:CI000001:switch")
    assert opp["score_change"] == 5 and opp["score_criticality"] == 5 and opp["score_match"] == 5
    assert opp["start_month"] == 6 and opp["wave"] == 2


def test_human_approved_tier_a_match_scores_two() -> None:
    book = Book()
    book.buy("acquirer", "A1", 1_000, 2.00)
    book.buy("target", "T1", 1_000, 1.50)
    out = run(book.frames([("A1", "T1", "A")], human=("A1",)))
    assert opportunity(out, "L1:CI000001:same_vendor")["score_match"] == 2


def test_every_opportunity_gets_complexity_wave_and_months() -> None:
    book = Book()
    book.buy("acquirer", "A1", 1_000, 2.00, vendor="PV", terms=30, l2="L11.01")
    book.buy("target", "T1", 1_000, 1.50, vendor="PV", terms=60, l2="L11.01")
    book.buy("target", None, 1, 5_000, vendor="OV", terms=60, l2="L11.01")
    out = run(book.frames([("A1", "T1", "A")]))
    opps = out.opportunities
    assert set(opps["lever"]) == {1, 2, 3}
    for column in ("complexity", "wave", "start_month", "available_month"):
        assert opps[column].notna().all()
    terms = opportunity(out, "L3:PV")
    assert terms["score_change"] == 2 and terms["start_month"] == 3 and terms["wave"] == 1
    assert opportunity(out, "L2:L11.01")["start_month"] == 6


# ---------------------------------------------------------------- phasing


def test_available_month_counts_from_the_close_month() -> None:
    ends = pd.DatetimeIndex(["2025-12-31", "2026-01-15", "2026-06-30", "2028-12-31", "2029-02-01",
                             None])  # fmt: skip
    assert line_available_month(ends, CLOSE, LIMIT).tolist() == [0, 2, 7, 37, 0, 0]


def test_months_active_and_start_quarter() -> None:
    start = np.array([0, 3, 4, 10, 36, 40])
    assert months_active(start, 1).tolist() == [3, 1, 0, 0, 0, 0]
    assert months_active(start, 4).tolist() == [3, 3, 3, 3, 0, 0]
    assert months_active(start, 12).tolist() == [3, 3, 3, 3, 1, 0]
    assert start_quarter(start).tolist() == [1, 1, 2, 4, 12, 14]


def test_contract_aware_phasing_and_the_beyond_month_36_list() -> None:
    book = Book()
    book.buy("acquirer", "A1", 1_000, 2.00, contract_end="2026-06-30")
    book.buy("target", "T1", 1_000, 1.50)
    book.buy("acquirer", "A2", 1_000, 2.00, contract_end="2028-12-31")
    book.buy("target", "T2", 1_000, 1.50)
    out = run(book.frames([("A1", "T1", "A"), ("A2", "T2", "A")]))
    assert out.totals["phasing"]["method"] == CONTRACT
    soon = opportunity(out, "L1:CI000001:same_vendor")
    late = opportunity(out, "L1:CI000002:same_vendor")
    assert (soon["available_month"], soon["start_month"], soon["wave"]) == (7, 10, 2)
    assert (late["available_month"], late["start_month"], late["wave"]) == (37, 40, 3)
    assert late["beyond_month_36"] and not soon["beyond_month_36"]
    assert out.totals["phasing"]["beyond_month_36"] == ["L1:CI000002:same_vendor"]
    run_rate = soon["base"]
    realised = out.totals["phasing"]["realised"]
    assert realised["year1"]["base"] == pytest.approx(run_rate * 3 / 12)
    assert realised["year2"]["base"] == pytest.approx(run_rate)
    saving = out.phasing[out.phasing["row_type"] == "saving"]
    q4 = saving[saving["quarter"] == 4]["base"].sum()
    assert q4 == pytest.approx(run_rate * 3 / 12)
    assert saving[saving["quarter"] == 3]["base"].sum() == 0


def test_global_ramp_is_used_without_contract_dates() -> None:
    book = Book()
    book.buy("acquirer", "A1", 1_000, 2.00)
    book.buy("target", "T1", 1_000, 1.50)
    out = run(book.frames([("A1", "T1", "A")]))
    phasing = out.totals["phasing"]
    run_rate = out.totals["recurring"]["base"]
    assert phasing["method"] == GLOBAL_RAMP
    shares = [phasing["realised"][f"year{y}"]["base"] / run_rate for y in (1, 2, 3)]
    assert shares == pytest.approx([0.40, 0.85, 1.00])
    quarters = out.phasing[out.phasing["row_type"] == "saving"].groupby("quarter")["base"].sum()
    assert quarters.loc[1] == pytest.approx(run_rate * 0.40 / 4)
    assert phasing["net_three_year"]["base"] == pytest.approx(run_rate * 2.25)


def test_no_close_date_falls_back_to_the_global_ramp() -> None:
    book = Book()
    book.buy("acquirer", "A1", 1_000, 2.00, contract_end="2026-06-30")
    book.buy("target", "T1", 1_000, 1.50)
    out = run(book.frames([("A1", "T1", "A")]), meta={**META, "period": None})
    assert out.totals["phasing"]["method"] == GLOBAL_RAMP


def test_lever3_cash_appears_once_in_its_start_quarter_on_its_own_row() -> None:
    book = Book()
    book.buy("acquirer", None, 1, 1_200_000, vendor="PV", terms=30, contract_end="2026-08-31")
    book.buy("target", None, 1, 800_000, vendor="PV", terms=60)
    out = run(book.frames())
    opp = opportunity(out, "L3:PV")
    assert opp["start_month"] == 9 + 3
    cash = out.phasing[out.phasing["row_type"] == "cash"]
    assert cash["quarter"].tolist() == [4]
    assert cash["base"].sum() == pytest.approx(out.totals["one_time"]["cash"]["base"])
    assert (out.phasing.loc[out.phasing["row_type"] == "saving", "base"] == 0).all()


def test_switch_event_costs_fixed_plus_share_of_spend_times_capture_probability() -> None:
    book = Book()
    book.buy("acquirer", "A1", 1_000, 2.00, vendor="V1")
    book.buy("acquirer", "A2", 1_000, 3.00, vendor="V1")
    book.buy("target", "T1", 1_000, 1.50, vendor="V9")
    book.buy("target", "T2", 1_000, 2.00, vendor="V9")
    no_lever2 = {"category_settings": {"L02.01": {"cap": 0.0}}}
    out = run(book.frames([("A1", "T1", "A"), ("A2", "T2", "A")]), assumptions=no_lever2)
    costs = out.totals["one_time"]["costs"]
    # One event (acquirer, L02.01, V9) receives 2,000 + 3,000 of spend.
    for case, pi in (("low", 0.20), ("base", 0.40), ("high", 0.60)):
        assert costs[case] == pytest.approx((25_000 + 0.01 * 5_000) * pi)
    rows = out.phasing[out.phasing["row_type"] == "cost"]
    assert rows["quarter"].tolist() == [2]  # start month 6
    assert rows["base"].sum() == pytest.approx(costs["base"])
    assert out.trace.children["one_time:costs"] == ["event:acquirer|L02.01|V9"]


def test_lever2_moves_are_switch_events_too() -> None:
    book = Book()
    book.buy("acquirer", None, 1, 500_000, vendor="PV")
    book.buy("target", None, 1, 300_000, vendor="OV1")
    book.buy("target", None, 1, 200_000, vendor="OV2")
    out = run(book.frames())
    # f = 0.5: 150,000 and 100,000 move to PV in one event (target, L02.01, PV).
    assert out.trace.children["one_time:costs"] == ["event:target|L02.01|PV"]
    costs = out.totals["one_time"]["costs"]
    assert costs["base"] == pytest.approx((25_000 + 0.01 * 250_000) * 0.60)


def test_same_vendor_renegotiation_carries_no_switching_cost() -> None:
    book = Book()
    book.buy("acquirer", "A1", 1_000, 2.00)
    book.buy("target", "T1", 1_000, 1.50)
    out = run(book.frames([("A1", "T1", "A")]))
    assert out.totals["one_time"]["costs"] == {"low": 0.0, "base": 0.0, "high": 0.0}


# ---------------------------------------------------------------- reconciliation


def test_bands_are_inclusive() -> None:
    band = {"low": 0.01, "high": 0.03}
    assert band_check(1.0, 100.0, band)["within"]
    assert band_check(3.0, 100.0, band)["within"]
    assert not band_check(3.01, 100.0, band)["within"]
    assert band_check(0.0, 0.0, band)["share"] == 0


def test_outside_a_band_lists_the_three_largest_opportunities() -> None:
    book = Book()
    for n, gap in enumerate([0.5, 0.4, 0.3, 0.2]):
        book.buy("acquirer", f"A{n}", 1_000, 2.00 + gap)
        book.buy("target", f"T{n}", 1_000, 2.00)
    out = run(book.frames([(f"A{n}", f"T{n}", "A") for n in range(4)]))
    rec = out.totals["reconciliation"]
    assert rec["outside_band"]
    assert rec["total_spend"]["share"] == pytest.approx(
        out.totals["recurring"]["base"] / out.totals["spend"]["baseline"]
    )
    assert rec["largest_opportunities"] == [f"L1:CI00000{n}:same_vendor" for n in (1, 2, 3)]
    wide = {"reference_bands": {"total_spend": {"low": 0, "high": 1}}}
    wide["reference_bands"]["addressable_spend"] = {"low": 0, "high": 1}
    assert (
        run(book.frames([(f"A{n}", f"T{n}", "A") for n in range(4)]), wide).totals[
            "reconciliation"
        ]["largest_opportunities"]
        == []
    )


# ---------------------------------------------------------------- sensitivity


def _cache():
    book = Book()
    book.buy("acquirer", "A1", 1_000, 2.00, vendor="V1", l2="L11.01", category_type="indirect")
    book.buy("target", "T1", 1_000, 1.50, vendor="V1", l2="L11.01", category_type="indirect")
    book.buy("target", None, 1, 3_000, vendor="V2", l2="L11.01", category_type="indirect")
    frames = book.frames([("A1", "T1", "A")])
    return precompute(
        frames["lines"], frames["vendor_map"], frames["item_map"], frames["item_pairs"], None, META
    )


def test_tornado_moves_triples_to_low_and_high_and_others_by_the_rules() -> None:
    from tieout.assumptions import merge_overrides

    by_path = {m.path: m for m in moves(merge_overrides(None))}
    same = by_path["lever1.same_vendor.base"]
    assert (same.low, same.base, same.high) == (0.50, 0.70, 0.85)
    assert by_path["caps.standard"].low == pytest.approx(0.65)
    assert by_path["caps.standard"].high == pytest.approx(0.85)
    assert (by_path["planning_horizon_months"].low, by_path["planning_horizon_months"].high) == (
        24,
        48,
    )
    assert by_path["lever2.discount.mro"].high == pytest.approx(0.05)
    assert by_path["lead_time_months.l2"].low == 4  # 6 x 0.75, in whole months
    assert "lever1.same_vendor.low" not in by_path


def test_tornado_ranks_by_effect_on_base_recurring_saving() -> None:
    cache = _cache()
    frame = tornado(cache, None)
    assert len(frame) == TOP
    assert frame["swing"].is_monotonic_decreasing
    row = frame.set_index("assumption").loc["lever1.same_vendor.base"]
    base = recurring_base(cache, None)
    low = recurring_base(cache, {"lever1": {"same_vendor": {"base": 0.50}}})
    assert row["effect_low"] == pytest.approx(low - base)
    assert row["effect_low"] < 0 < row["effect_high"]


def test_scenarios_are_assumption_transforms() -> None:
    settings = {"category_settings": {"L11.01": {"pi2_low": 0.1, "pi2_base": 0.5}}}
    conservative = SCENARIOS["Conservative"](settings)
    assert conservative["lever1"]["switch"]["base"] == 0.20
    assert conservative["lever3"]["capture"]["base"] == 0.30
    assert conservative["category_settings"]["L11.01"]["pi2_base"] == 0.1
    stretch = SCENARIOS["Stretch"](settings)
    assert stretch["lever2"]["capture"]["base"] == 0.80
    assert "pi2_base" not in stretch["category_settings"]["L11.01"]
    central = SCENARIOS["Central (defaults)"]({"cost_of_capital": 0.2, **settings})
    assert central["cost_of_capital"] == 0.08
    assert central["category_settings"] == settings["category_settings"]
    cache = _cache()
    assert recurring_base(cache, conservative) <= recurring_base(cache, stretch)
