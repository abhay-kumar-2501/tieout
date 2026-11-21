"""Generator design targets (PRD 8.3) and the M3 exit test, on the demo data (seed 4).

If a design-target test fails, the generator's price-gap scale and unit-trap
count are adjusted, never the engine (PRD 8.3).
"""

from __future__ import annotations

import copy

import pytest

from tieout.pipeline import recompute

pytestmark = pytest.mark.slow

NAIVE_SHARE = (0.04, 0.08)
DEFENSIBLE_BASE_SHARE = (0.01, 0.03)


def test_naive_lever1_is_four_to_eight_percent_of_spend(seed4) -> None:
    totals = seed4.results.totals
    share = totals["lever1"]["naive"] / totals["spend"]["baseline"]
    assert NAIVE_SHARE[0] <= share <= NAIVE_SHARE[1], f"naive {share:.2%}"


def test_defensible_base_is_one_to_three_percent_of_spend(seed4) -> None:
    totals = seed4.results.totals
    share = totals["recurring"]["base"] / totals["spend"]["baseline"]
    assert DEFENSIBLE_BASE_SHARE[0] <= share <= DEFENSIBLE_BASE_SHARE[1], f"base {share:.2%}"


def test_lowering_one_categorys_cap_increases_savings_forgone(seed4) -> None:
    """M3 exit criterion: cap 90% -> 60% on one category strictly raises savings forgone.

    The category is the lever-2 opportunity with the largest base saving.
    """
    results = seed4.results
    opps = results.opportunities
    lever2 = opps[(opps["lever"] == 2) & (opps["status"] == "in_range")]
    l2 = lever2.sort_values(["base", "l2_code"], ascending=[False, True]).iloc[0]["l2_code"]

    def forgone(cap: float) -> tuple[float, float]:
        assumptions = copy.deepcopy(results.assumptions)
        settings = dict(assumptions.get("category_settings") or {})
        settings[l2] = {**settings.get(l2, {}), "cap": cap}
        out = recompute(results, assumptions | {"category_settings": settings})
        risk = out.category_risk
        in_category = float(risk.loc[risk["l2_code"] == l2, "savings_forgone"].iloc[0])
        return in_category, float(out.totals["lever2"]["savings_forgone"])

    at_90, at_60 = forgone(0.90), forgone(0.60)
    assert at_60[0] > at_90[0]
    assert at_60[1] > at_90[1]
