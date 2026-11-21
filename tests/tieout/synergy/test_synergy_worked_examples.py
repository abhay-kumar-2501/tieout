"""The worked examples of PRD 5.3, 5.4 and 5.6, to the dollar, as formulas and end to end."""

from __future__ import annotations

import numpy as np
import pandas as pd
from synergy_fixtures import Book, run

from tieout.synergy.lever2 import B2, N2
from tieout.synergy.lever3 import T_star, delta_cash
from tieout.synergy.phasing import GLOBAL_RAMP, build_phasing, net_three_year, year_factors

RAMP = {"year1": 0.40, "year2": 0.85, "year3": 1.00}


def dollars(value: float) -> int:
    return round(float(value))


def test_lever2_worked_example_formula() -> None:
    # Post-move preferred spend of $2,000,000 (P_eligible + f x M), lever 1 already took $40,000.
    b2 = B2(np.array([1_500_000.0]), np.array([0.5]), np.array([1_000_000.0]), np.array([40_000.0]))
    assert dollars(b2[0]) == 1_960_000
    assert dollars(N2(b2, np.array([0.03]), np.array([0.60]))[0]) == 35_280


def test_lever2_worked_example_end_to_end() -> None:
    """Indirect category (d = 3%), cap 100%; lever 1 saves $40,000 on spend that moves."""
    book = Book()
    shared = {"vendor": "PV", "l2": "L11.01", "category_type": "indirect"}
    book.buy("acquirer", "A1", 100_000, 2.00, **shared)
    book.buy("target", "T1", 100_000, 1.50, **shared)
    book.buy("acquirer", None, 1, 1_650_000, vendor="OV", l2="L11.01", category_type="indirect")
    settings = {"category_settings": {"L11.01": {"cap": 1.0, "pi1_same_base": 0.8}}}
    out = run(book.frames([("A1", "T1", "A")]), assumptions=settings)
    assert dollars(out.totals["levers"]["lever1"]["base"]) == 40_000
    assert dollars(out.totals["lever2"]["B2"]["base"]) == 1_960_000
    assert dollars(out.totals["levers"]["lever2"]["base"]) == 35_280
    opp = out.opportunities.set_index("opportunity_id").loc["L2:L11.01"]
    assert opp["parent_id"] == "OV"
    assert dollars(opp["base"]) == 35_280


def test_lever3_worked_example_formula() -> None:
    target = T_star(np.array([30.0]), np.array([60.0]), 90.0)
    assert target[0] == 60
    s = np.array([1_200_000.0])
    assert dollars(delta_cash(target, np.array([30.0]), s, 1.0)[0]) == 98_630
    assert dollars(delta_cash(target, np.array([30.0]), s, 0.50)[0]) == 49_315


def test_lever3_worked_example_end_to_end() -> None:
    """$1,200,000 a year moves from 30 to 60 days; one vendor in the category, so no lever 2."""
    book = Book()
    book.buy("acquirer", None, 1, 1_200_000, vendor="PV", terms=30)
    book.buy("target", None, 1, 800_000, vendor="PV", terms=60)
    out = run(book.frames())
    lever3 = out.totals["levers"]["lever3"]
    assert dollars(lever3["gross"]) == 98_630
    assert dollars(lever3["base"]) == 49_315
    assert dollars(out.totals["one_time"]["cash"]["base"]) == 49_315
    assert dollars(out.totals["memo"]["financing_value"]["base"]) == dollars(49_315.068 * 0.08)
    terms = out.payment_terms.set_index("company")
    assert terms.loc["acquirer", "basis"] == "stated"
    assert terms.loc["acquirer", "T"] == 30 and terms.loc["acquirer", "T_star"] == 60
    assert terms.loc["target", "cash_base"] == 0
    assert out.totals["levers"]["lever2"]["base"] == 0


def test_phasing_worked_example() -> None:
    """Run-rate $10.0M on the global ramp: $22.5M over three years, $21.0M net of $1.5M."""
    years = 10_000_000 * year_factors(np.array([0]), GLOBAL_RAMP, RAMP)[0]
    assert [dollars(v) for v in years] == [4_000_000, 8_500_000, 10_000_000]
    assert dollars(net_three_year(years.sum(), 1_500_000)) == 21_000_000

    opportunities = pd.DataFrame(
        {
            "opportunity_id": ["L1:X:same_vendor"],
            "lever": [1],
            "wave": [1],
            "start_month": [3],
            "low": [10_000_000.0],
            "base": [10_000_000.0],
            "high": [10_000_000.0],
        }
    )
    costs = pd.DataFrame(
        {"opportunity_id": ["L1:X:same_vendor"], "low": [1.5e6], "base": [1.5e6], "high": [1.5e6]}
    )
    phasing = build_phasing(opportunities, costs, GLOBAL_RAMP, RAMP)
    savings = phasing[phasing["row_type"] == "saving"].groupby("year")["base"].sum()
    assert [dollars(v) for v in savings] == [4_000_000, 8_500_000, 10_000_000]
    cost = phasing[phasing["row_type"] == "cost"]
    assert cost["quarter"].tolist() == [1] and dollars(cost["base"].sum()) == 1_500_000
    assert dollars(net_three_year(savings.sum(), cost["base"].sum())) == 21_000_000
