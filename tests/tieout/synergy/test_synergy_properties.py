"""Property tests for the lever-1 invariants of PRD 5.9 over generated matched tables."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from synergy_fixtures import Book, run

from tieout.synergy import SynergyOutputs
from tieout.synergy.trace import figure_value, leaf_lines, resum

PROPERTY = settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
CENT = 0.01
EPS = 1e-6

line_st = st.fixed_dictionaries(
    {
        "qty": st.integers(-40, 400).filter(lambda q: q != 0),
        "price": st.integers(50, 5_000).map(lambda c: c / 100),
        "status": st.sampled_from(["confirmed"] * 6 + ["parsed", "unconverted"]),
        "exclusion": st.sampled_from([None] * 8 + ["amount_mismatch"]),
        "factor": st.sampled_from([1.0, 1.0, 1.0, 12.0]),
        "incoterm": st.sampled_from([None, "FCA", "FCA", "EXW"]),
        "contract_end": st.sampled_from([None, None, "2027-06-30", "2030-06-30"]),
    }
)
group_st = st.fixed_dictionaries(
    {
        "site": st.sampled_from(["S1", "S2", "S3"]),
        "vendor": st.sampled_from(["V1", "V2", "V3"]),
        "lines": st.lists(line_st, min_size=1, max_size=4),
    }
)
item_st = st.fixed_dictionaries(
    {
        "tier": st.sampled_from(["A", "A", "B", "C"]),
        "acquirer": st.lists(group_st, min_size=1, max_size=3),
        "target": st.lists(group_st, min_size=1, max_size=3),
    }
)
triple_st = st.lists(st.integers(0, 100), min_size=3, max_size=3).map(
    lambda v: dict(zip(("low", "base", "high"), sorted(x / 100 for x in v), strict=True))
)
assumptions_st = st.fixed_dictionaries(
    {
        "lever1": st.fixed_dictionaries({"same_vendor": triple_st, "switch": triple_st}),
        "benchmark": st.fixed_dictionaries(
            {
                "min_volume_share": st.sampled_from([0.0, 0.1, 0.3]),
                "min_lines": st.sampled_from([1, 2, 3]),
            }
        ),
    }
)


def build(items: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
    book = Book()
    matches, pending = [], []
    for n, item in enumerate(items):
        keys = {"acquirer": f"A{n}", "target": f"T{n}"}
        for company in ("acquirer", "target"):
            for group in item[company]:
                for line in group["lines"]:
                    book.buy(
                        company,
                        keys[company],
                        line["qty"],
                        line["price"],
                        site=group["site"],
                        vendor=group["vendor"],
                        lines=1,
                        factor=line["factor"],
                        status=line["status"],
                        exclusion=line["exclusion"],
                        incoterm=line["incoterm"],
                        contract_end=line["contract_end"],
                    )
        if item["tier"] == "C":
            pending.append((keys["acquirer"], keys["target"], 0.7))
        else:
            matches.append((keys["acquirer"], keys["target"], item["tier"]))
    return book.frames(matches, pending)


def independent_naive(frames: dict[str, pd.DataFrame]) -> float:
    """``sum_k sum_g (p[k,g] - min_h p[k,h]) * q[k,g]`` straight from the lines."""
    lines = frames["lines"]
    im = frames["item_map"]
    items = im.set_index("item_record_id")["canonical_item_id"].to_dict()
    for _, pair in frames["item_pairs"].iterrows():
        items[pair["key_b"]] = items[pair["key_a"]]
    parents = frames["vendor_map"].set_index("vendor_key")["parent_id"]
    keep = lines["price_exclusion"].isna() | (lines["price_exclusion"] == "unit_unconverted")
    df = lines[keep].copy()
    df["item"] = (df["company"] + ":" + df["item_key"]).map(items)
    df["parent"] = df["vendor_key"].map(parents)
    df["qty"] = np.where(df["conv_status"] == "unconverted", df["quantity_ann"], df["qty_base"])
    groups = df.groupby(["item", "company", "site", "parent"])[["amount", "qty"]].sum()
    net = groups.groupby(level="item")["qty"].sum()
    groups = groups[groups.index.get_level_values("item").map(net) > 0]
    groups = groups[(groups["amount"] > 0) & (groups["qty"] > 0)]
    price = groups["amount"] / groups["qty"]
    floor = price.groupby(level="item").transform("min")
    return float(((price - floor) * groups["qty"]).sum())


def compute(items, assumptions) -> tuple[dict[str, pd.DataFrame], SynergyOutputs]:
    frames = build(items)
    return frames, run(frames, assumptions=assumptions)


items_st = st.lists(item_st, min_size=1, max_size=5)


@PROPERTY
@given(items=items_st, assumptions=assumptions_st)
def test_no_saving_is_negative(items, assumptions) -> None:
    _, out = compute(items, assumptions)
    pg = out.price_groups
    for column in ("naive_gap", "G1", "N1_low", "N1_base", "N1_high", "upside_base"):
        assert (pg[column] >= 0).all(), column
    opps = out.opportunities
    for column in ("gross_gap", "low", "base", "high", "upside_base"):
        assert (opps[column] >= 0).all(), column
    lever = out.totals["levers"]["lever1"]
    assert lever["base"] <= lever["gross_gap"] + EPS


@PROPERTY
@given(items=items_st, assumptions=assumptions_st)
def test_low_base_high_are_ordered(items, assumptions) -> None:
    """Lever-1 opportunities, the lever-1 total and total recurring (PRD 5.9).

    Lever 2 alone is computed on a base that shrinks as lever 1 saves more, so
    its opportunities are labelled by case and not required to be ordered.
    """
    _, out = compute(items, assumptions)
    opps = out.opportunities[out.opportunities["lever"] == 1]
    assert (opps["low"] <= opps["base"] + EPS).all()
    assert (opps["base"] <= opps["high"] + EPS).all()
    lever = out.totals["levers"]["lever1"]
    assert lever["low"] <= lever["base"] + EPS <= lever["high"] + 2 * EPS
    recurring = out.totals["recurring"]
    assert recurring["low"] <= recurring["base"] + EPS <= recurring["high"] + 2 * EPS


@PROPERTY
@given(items=items_st, assumptions=assumptions_st)
def test_each_line_contributes_to_at_most_one_opportunity(items, assumptions) -> None:
    _, out = compute(items, assumptions)
    seen: set[str] = set()
    opps = out.opportunities
    for opp_id in opps.loc[opps["lever"] == 1, "opportunity_id"]:
        lines = set(leaf_lines(out.trace, opp_id))
        assert not lines & seen
        seen |= lines


@PROPERTY
@given(items=items_st, assumptions=assumptions_st)
def test_bridge_ties_out_and_steps_are_non_negative(items, assumptions) -> None:
    _, out = compute(items, assumptions)
    lever1 = out.totals["lever1"]
    steps = [lever1["bridge"][f"step_{i}"] for i in range(1, 8)]
    base = out.totals["levers"]["lever1"]["base"]
    assert abs(lever1["naive"] - sum(steps) - base) <= CENT
    raw = [lever1["bridge_raw"][f"step_{i}"] for i in range(1, 8)]
    assert min(raw[1:]) >= -EPS  # only step 1 can remove a negative amount
    assert min(steps[:-1]) >= 0
    if lever1["naive"] >= base:
        assert steps[-1] >= -EPS
    detail = out.bridge_detail.groupby("step")["amount_removed"].sum()
    for i, value in enumerate(raw, start=1):
        assert abs(detail.get(i, 0.0) - value) <= CENT


@PROPERTY
@given(items=items_st)
def test_all_filters_off_equals_the_independent_naive_formula(items) -> None:
    frames, out = compute(items, None)
    assert abs(out.totals["lever1"]["naive"] - independent_naive(frames)) <= CENT


@PROPERTY
@given(items=items_st, assumptions=assumptions_st)
def test_every_figure_and_opportunity_resums_from_its_traced_rows(items, assumptions) -> None:
    _, out = compute(items, assumptions)
    for path, (node, measure) in out.trace.figures.items():
        assert abs(resum(out.trace, node, measure) - figure_value(out.totals, path)) <= CENT, path
    for _, opp in out.opportunities.iterrows():
        for column, measure in opportunity_measures(opp).items():
            assert abs(resum(out.trace, opp["opportunity_id"], measure) - opp[column]) <= CENT


def opportunity_measures(opp: pd.Series) -> dict[str, str]:
    """Opportunity column -> trace measure that re-sums it."""
    if opp["lever"] == 1 and opp["status"] == "pending_review":
        return {"gross_gap": "upside_gross", "upside_base": "upside"}
    prefix = {1: "", 2: "l2_", 3: "l3_"}[opp["lever"]]
    gross = {1: "gross", 2: "l2_gross", 3: "l3_gross"}[opp["lever"]]
    return {"gross_gap": gross, **{case: f"{prefix}{case}" for case in ("low", "base", "high")}}


#: Floats in ``totals`` that are ratios or flags, not money.
NOT_MONEY = {"share", "band_low", "band_high"}


def money_leaves(node: object, path: str = "") -> list[str]:
    """Dotted paths of every money figure in ``totals``."""
    if isinstance(node, dict):
        return [
            p
            for k, v in node.items()
            if k not in NOT_MONEY and k != "checks"
            for p in money_leaves(v, f"{path}{k}.")
        ]
    return [path[:-1]] if isinstance(node, float) else []


def test_every_money_figure_in_totals_has_a_trace() -> None:
    frames = build(
        [
            {
                "tier": "A",
                "acquirer": [{"site": "S1", "vendor": "V1", "lines": [_line(100, 2.0)] * 3}],
                "target": [{"site": "S1", "vendor": "V1", "lines": [_line(100, 1.5)] * 3}],
            }
        ]
    )
    out = run(frames)
    assert set(money_leaves(out.totals)) == set(out.trace.figures)
    assert out.totals["levers"]["lever1"]["base"] == pytest.approx(0.5 * 300 * 0.70)


def _line(qty: float, price: float) -> dict[str, Any]:
    return {
        "qty": qty,
        "price": price,
        "status": "confirmed",
        "exclusion": None,
        "factor": 1.0,
        "incoterm": None,
        "contract_end": None,
    }
