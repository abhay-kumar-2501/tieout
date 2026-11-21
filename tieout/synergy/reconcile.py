"""Reconciliation to a top-down reference band (PRD 5.8).

The base-case run-rate saving is shown as a share of total in-scope spend and
of addressable spend (categories where both companies buy), each against a
user-set inclusive band. Outside either band, the three opportunities with the
largest base saving are listed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

__all__ = ["LARGEST", "band_check", "reconcile"]

LARGEST = 3


def band_check(saving: float, spend: float, band: Mapping[str, float]) -> dict[str, Any]:
    """``saving / spend`` against an inclusive ``{low, high}`` band (share 0 when no spend)."""
    share = saving / spend if spend > 0 else 0.0
    low, high = float(band["low"]), float(band["high"])
    return {
        "spend": float(spend),
        "share": float(share),
        "band_low": low,
        "band_high": high,
        "within": bool(low <= share <= high),
    }


def reconcile(
    base_saving: float,
    total_spend: float,
    addressable_spend: float,
    bands: Mapping[str, Mapping[str, float]],
    recurring_opportunities: pd.DataFrame,
) -> dict[str, Any]:
    """Both band checks, and the largest opportunities when either check fails."""
    checks = {
        "total_spend": band_check(base_saving, total_spend, bands["total_spend"]),
        "addressable_spend": band_check(base_saving, addressable_spend, bands["addressable_spend"]),
    }
    outside = not all(check["within"] for check in checks.values())
    ranked = recurring_opportunities.sort_values(
        ["base", "opportunity_id"], ascending=[False, True], kind="mergesort"
    )
    largest = ranked["opportunity_id"].head(LARGEST).tolist() if outside else []
    return {**checks, "outside_band": outside, "largest_opportunities": largest}
