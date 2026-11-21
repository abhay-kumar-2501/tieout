"""Property tests for the PRD 5.9 invariants across levers 1 to 3.

Generated matched tables span several categories, vendors, items, service
spend, payment terms and contracts. The lever-1-only invariants (one lever-1
opportunity per dollar, the bridge tie-out) are in ``test_synergy_properties``.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from synergy_fixtures import Book, run
from test_synergy_properties import money_leaves, opportunity_measures

from tieout.synergy import SynergyOutputs
from tieout.synergy.trace import figure_value, leaf_lines, resum

PROPERTY = settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
CENT = 0.01
EPS = 1e-6
CASES = ("low", "base", "high")
CATEGORIES = (("L02.01", "mro"), ("L03.01", "engineered"), ("L11.01", "indirect"))

purchase_st = st.fixed_dictionaries(
    {
        "company": st.sampled_from(["acquirer", "target"]),
        "vendor": st.sampled_from(["V1", "V2", "V3"]),
        "item": st.sampled_from([None, 0, 1, 2]),
        "qty": st.integers(-20, 400).filter(lambda q: q != 0),
        "price": st.integers(50, 5_000).map(lambda c: c / 100),
        "site": st.sampled_from(["S1", "S2"]),
        "terms": st.sampled_from([None, 30, 45, 60, 120]),
        "paid_after": st.sampled_from([None, None, 25, 50, 95]),
        "contract_end": st.sampled_from([None, None, "2026-05-31", "2027-09-30", "2030-01-31"]),
        "vendor_tier": st.sampled_from(["A", "A", "B", None]),
    }
)
category_st = st.fixed_dictionaries(
    {
        "category": st.sampled_from(CATEGORIES),
        "purchases": st.lists(purchase_st, min_size=1, max_size=8),
        "tier": st.sampled_from(["A", "B"]),
    }
)
triple_st = st.lists(st.integers(0, 100), min_size=3, max_size=3).map(
    lambda v: dict(zip(CASES, sorted(x / 100 for x in v), strict=True))
)
assumptions_st = st.fixed_dictionaries(
    {
        "lever1": st.fixed_dictionaries({"same_vendor": triple_st, "switch": triple_st}),
        "lever2": st.fixed_dictionaries(
            {
                "capture": triple_st,
                "discount": st.fixed_dictionaries(
                    {k: st.sampled_from([0.0, 0.02, 0.05, 0.3]) for k in ("mro", "engineered")}
                ),
            }
        ),
        "lever3": st.fixed_dictionaries(
            {"capture": triple_st, "max_payment_days": st.sampled_from([45, 90])}
        ),
        "caps": st.fixed_dictionaries(
            {
                k: st.sampled_from([0.3, 0.6, 0.75, 0.9, 1.0])
                for k in ("critical", "standard", "non_critical")
            }
        ),
        "benchmark": st.fixed_dictionaries(
            {"min_volume_share": st.sampled_from([0.0, 0.1]), "min_lines": st.just(1)}
        ),
    }
)
tables_st = st.lists(category_st, min_size=1, max_size=3)


def build(categories: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
    book = Book()
    bought: dict[str, set[str]] = {}
    tiers: dict[str, str] = {}
    for spec in categories:
        l2, category_type = spec["category"]
        for p in spec["purchases"]:
            item = None
            if p["item"] is not None:
                key = f"{l2}-{p['item']}"
                item = f"{p['company'][0].upper()}{key}"
                bought.setdefault(key, set()).add(p["company"])
                tiers[key] = spec["tier"]
            book.buy(
                p["company"],
                item,
                p["qty"],
                p["price"],
                site=p["site"],
                vendor=p["vendor"],
                lines=1,
                l2=l2,
                category_type=category_type,
                terms=p["terms"],
                paid_after=p["paid_after"],
                contract_end=p["contract_end"],
                vendor_tier=p["vendor_tier"],
            )
    matches = [(f"A{k}", f"T{k}", tiers[k]) for k, c in sorted(bought.items()) if len(c) == 2]
    return book.frames(matches)


def compute(categories, assumptions) -> tuple[dict[str, pd.DataFrame], SynergyOutputs]:
    frames = build(categories)
    return frames, run(frames, assumptions=assumptions)


def lever(out: SynergyOutputs, n: int) -> pd.DataFrame:
    return out.opportunities[out.opportunities["lever"] == n]


@PROPERTY
@given(categories=tables_st, assumptions=assumptions_st)
def test_no_saving_is_negative(categories, assumptions) -> None:
    _, out = compute(categories, assumptions)
    opps = out.opportunities
    for column in ("gross_gap", *CASES):
        assert (opps[column] >= -EPS).all(), column
    for name in ("lever1", "lever2", "lever3"):
        assert min(out.totals["levers"][name][c] for c in CASES) >= -EPS, name
    terms = out.payment_terms
    for column in ("S_low", "S_base", "S_high", "cash_low", "cash_base", "cash_high"):
        assert (terms[column] >= 0).all(), column
    savings = out.phasing[out.phasing["row_type"] == "saving"]
    assert (savings[list(CASES)] >= -EPS).all().all()


@PROPERTY
@given(categories=tables_st, assumptions=assumptions_st)
def test_no_lever_exceeds_its_own_base(categories, assumptions) -> None:
    _, out = compute(categories, assumptions)
    first = lever(out, 1)
    assert (first["base"] <= first["gross_gap"] + EPS).all()
    for n in (2, 3):
        opps = lever(out, n)
        for case in CASES:
            assert (opps[case] <= opps[f"basis_{case}"] + EPS).all(), (n, case)
    totals = out.totals
    assert totals["levers"]["lever1"]["base"] <= totals["levers"]["lever1"]["gross_gap"] + EPS
    for case in CASES:
        assert totals["levers"]["lever2"][case] <= totals["lever2"]["B2"][case] + EPS
    terms = out.payment_terms
    for case in CASES:
        assert (terms[f"cash_{case}"] <= terms[f"S_{case}"] + EPS).all()


@PROPERTY
@given(categories=tables_st, assumptions=assumptions_st)
def test_low_base_high_ordered_for_lever1_opportunities_lever1_total_and_total_recurring(
    categories, assumptions
) -> None:
    _, out = compute(categories, assumptions)
    first = lever(out, 1)
    assert (first["low"] <= first["base"] + EPS).all()
    assert (first["base"] <= first["high"] + EPS).all()
    for totals in (out.totals["levers"]["lever1"], out.totals["recurring"]):
        assert totals["low"] <= totals["base"] + EPS
        assert totals["base"] <= totals["high"] + EPS


@PROPERTY
@given(categories=tables_st, assumptions=assumptions_st)
def test_spend_cube_sums_to_baseline_and_nets_to_run_rate_spend_in_each_case(
    categories, assumptions
) -> None:
    frames, out = compute(categories, assumptions)
    spend = out.totals["spend"]
    assert abs(spend["baseline"] - frames["lines"]["amount"].sum()) <= CENT
    for case in CASES:
        levers = lever(out, 1)[case].sum() + lever(out, 2)[case].sum()
        assert abs(spend["baseline"] - levers - spend["net_run_rate"][case]) <= CENT


@PROPERTY
@given(categories=tables_st, assumptions=assumptions_st)
def test_recurring_and_one_time_amounts_never_appear_in_the_same_sum(
    categories, assumptions
) -> None:
    _, out = compute(categories, assumptions)
    totals = out.totals
    levers = totals["levers"]
    assert levers["lever1"]["kind"] == levers["lever2"]["kind"] == "recurring"
    assert levers["lever3"]["kind"] == "one_time_cash"
    for case in CASES:
        assert totals["recurring"][case] == levers["lever1"][case] + levers["lever2"][case]
        assert totals["one_time"]["cash"][case] == levers["lever3"][case]
    assert set(totals["one_time"]) == {"cash", "costs"}
    assert totals["defensible_range"] == {
        "low": totals["recurring"]["low"],
        "high": totals["recurring"]["high"],
    }
    recurring_nodes = set(_nodes(out, "total:recurring"))
    assert not any(n.startswith(("L3:", "lever:3", "event:")) for n in recurring_nodes)
    one_time = {
        node for path, (node, _) in out.trace.figures.items() if path.startswith("one_time")
    }
    assert not one_time & recurring_nodes


def _nodes(out: SynergyOutputs, node: str) -> list[str]:
    seen, stack = [], [node]
    while stack:
        current = stack.pop()
        if current in out.trace.children:
            seen.append(current)
            stack.extend(out.trace.children[current])
    return seen


@PROPERTY
@given(categories=tables_st, assumptions=assumptions_st)
def test_no_double_counting_between_lever1_switch_spend_and_lever2(categories, assumptions) -> None:
    _, out = compute(categories, assumptions)
    first = lever(out, 1)
    switch = first[(first["change_type"] == "switch") & (first["status"] == "in_range")]
    switch_lines = {i for o in switch["opportunity_id"] for i in leaf_lines(out.trace, o)}
    for opp_id in lever(out, 2)["opportunity_id"]:
        assert not switch_lines & set(leaf_lines(out.trace, opp_id))


@PROPERTY
@given(categories=tables_st, assumptions=assumptions_st)
def test_every_figure_and_opportunity_resums_from_its_traced_rows(categories, assumptions) -> None:
    _, out = compute(categories, assumptions)
    assert set(money_leaves(out.totals)) == set(out.trace.figures)
    for path, (node, measure) in out.trace.figures.items():
        assert abs(resum(out.trace, node, measure) - figure_value(out.totals, path)) <= CENT, path
    for _, opp in out.opportunities.iterrows():
        for column, measure in opportunity_measures(opp).items():
            value = resum(out.trace, opp["opportunity_id"], measure)
            assert abs(value - opp[column]) <= CENT, (opp["opportunity_id"], column)
