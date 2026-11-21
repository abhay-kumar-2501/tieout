"""Risk guardrails (PRD 5.5): savings forgone, concentration index, sole-source flags.

``category_risk`` has one row per (L2 category, parent vendor) holding spend
before or after consolidation. Category-level columns (effective settings,
the lever-2 working ``C``, ``P``, ``P_eligible``, ``M``, ``f``, HHI, savings
forgone, flags) repeat on each of the category's rows; take one row per
category before summing them.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from tieout.synergy.cube import SpendCube
from tieout.synergy.lever2 import Lever2Result
from tieout.synergy.settings import CategoryParams

__all__ = [
    "CATEGORY_RISK_COLUMNS",
    "build_category_risk",
    "hhi",
    "savings_forgone",
    "shares",
    "sole_source_items",
]

CATEGORY_RISK_COLUMNS = [
    "l2_code",
    "parent_id",
    "preferred",
    "spend_before",
    "spend_after",
    "share_before",
    "share_after",
    "criticality",
    "category_type",
    "cap",
    "d",
    "lever2_status",
    "C",
    "P",
    "P_eligible",
    "M",
    "f",
    "hhi_before",
    "hhi_after",
    "parents_before",
    "parents_after",
    "sole_source_category",
    "sole_source_items",
    "sole_source_item_ids",
    "savings_forgone",
]


def shares(spend: np.ndarray) -> np.ndarray:
    """Each parent vendor's share of category spend per row; credits beyond spend count as 0."""
    positive = np.maximum(spend, 0.0)
    total = positive.sum(axis=-1, keepdims=True)
    return positive / np.where(total > 0, total, 1.0)


def hhi(s: np.ndarray) -> np.ndarray:
    """``HHI = sum_i (100 x s_i)^2`` per row of shares (0 to 10,000)."""
    return ((100.0 * s) ** 2).sum(axis=-1)


def savings_forgone(n2_uncapped: np.ndarray, n2_capped: np.ndarray) -> np.ndarray:
    """Lever-2 base saving with the cap at 100% minus the saving at the current cap."""
    return n2_uncapped - n2_capped


def sole_source_items(tagged: pd.DataFrame) -> dict[str, list[str]]:
    """L2 -> canonical items bought by both companies (tier A or B) from one parent vendor only."""
    matched = tagged[tagged["item_tier"].isin(("A", "B"))]
    per_item = matched.groupby("canonical_item_id", sort=True).agg(
        companies=("company", "nunique"), parents=("parent_id", "nunique"), l2=("l2_code", "first")
    )
    sole = per_item[(per_item["companies"] == 2) & (per_item["parents"] == 1)]
    return {str(l2): list(ids) for l2, ids in sole.groupby("l2", sort=True).groups.items()}


def _vendor_matrix(cube: SpendCube, values: np.ndarray) -> np.ndarray:
    n_l2, n_par = len(cube.l2_codes), max(len(cube.parents), 1)
    mapped = cube.mapped
    key = cube.l2[mapped] * n_par + cube.parent[mapped]
    return np.bincount(key, weights=values[mapped], minlength=n_l2 * n_par).reshape(n_l2, n_par)


def build_category_risk(
    cube: SpendCube,
    params: CategoryParams,
    lev2: Lever2Result,
    lev2_uncapped: Lever2Result,
    sole_items: Mapping[str, list[str]],
) -> pd.DataFrame:
    """Vendor shares and HHI before and after the lever-2 moves (post-move spend before savings)."""
    before = _vendor_matrix(cube, cube.amount)
    after = before - _vendor_matrix(cube, lev2.moved)
    rows = np.flatnonzero(lev2.preferred >= 0)
    after[rows, lev2.preferred[rows]] += before[rows].sum(axis=1) - after[rows].sum(axis=1)
    share_before, share_after = shares(before), shares(after)
    forgone = savings_forgone(lev2_uncapped.N2["base"], lev2.N2["base"])
    parents_before = (before > 0).sum(axis=1)
    parents_after = (after > 0).sum(axis=1)
    l2_index, parent_index = np.nonzero((before != 0) | (after != 0))
    codes = np.array(cube.l2_codes, dtype=object)
    sole_ids = [sole_items.get(code, []) for code in cube.l2_codes]
    frame = pd.DataFrame(
        {
            "l2_code": codes[l2_index],
            "parent_id": np.array(cube.parents, dtype=object)[parent_index],
            "preferred": lev2.preferred[l2_index] == parent_index,
            "spend_before": before[l2_index, parent_index],
            "spend_after": after[l2_index, parent_index],
            "share_before": share_before[l2_index, parent_index],
            "share_after": share_after[l2_index, parent_index],
            "criticality": params.criticality[l2_index],
            "category_type": params.category_type[l2_index],
            "cap": params.cap[l2_index],
            "d": params.d[l2_index],
            "lever2_status": lev2.reason[l2_index].astype(object),
            "C": lev2.C[l2_index],
            "P": lev2.P[l2_index],
            "P_eligible": lev2.P_eligible[l2_index],
            "M": lev2.M[l2_index],
            "f": lev2.f[l2_index],
            "hhi_before": hhi(share_before)[l2_index],
            "hhi_after": hhi(share_after)[l2_index],
            "parents_before": parents_before[l2_index],
            "parents_after": parents_after[l2_index],
            "sole_source_category": parents_after[l2_index] == 1,
            "sole_source_items": np.array([len(ids) for ids in sole_ids])[l2_index],
            "sole_source_item_ids": np.array([", ".join(ids) for ids in sole_ids], dtype=object)[
                l2_index
            ],
            "savings_forgone": forgone[l2_index],
        }
    )
    return frame[CATEGORY_RISK_COLUMNS]
