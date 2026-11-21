"""Lever-1 opportunities, internal variance and the unit-flag and incoterm review items.

An opportunity is one (canonical item, change type), aggregating that item's
buying groups with that change type (PRD 5.1). Matched items (tier A or B)
give opportunities ``in_range``; tier C candidates give opportunities
``pending_review`` whose low / base / high are zero and whose ``upside_base``
is what approval would add (PRD 4.2, 4.5).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

import numpy as np
import pandas as pd

from tieout.synergy.groups import COMPANIES
from tieout.synergy.lever1 import CASES, Filters, Lever1Inputs, Lever1Result, lever1

__all__ = [
    "INTERNAL_VARIANCE_COLUMNS",
    "OPPORTUNITY_COLUMNS",
    "REVIEW_ITEM_COLUMNS",
    "Evaluations",
    "build_internal_variance",
    "build_opportunities",
    "build_review_items",
    "evaluate",
    "opportunity_ids",
]

OPPORTUNITY_COLUMNS = [
    "opportunity_id",
    "lever",
    "canonical_item_id",
    "change_type",
    "l2_code",
    "status",
    "tier",
    "vendor_tier",
    "gross_gap",
    "low",
    "base",
    "high",
    "upside_base",
    "sites_affected",
    "groups",
    "benchmark_price",
    "benchmark_company",
    "benchmark_fallback",
    "record_acquirer",
    "record_target",
]
INTERNAL_VARIANCE_COLUMNS = [
    "canonical_item_id",
    "l2_code",
    "tier",
    "benchmark_company",
    "benchmark_price",
    "internal_variance",
    "groups",
    "sites_affected",
]
REVIEW_ITEM_COLUMNS = [
    "pair_id",
    "type",
    "canonical_item_id",
    "key_a",
    "key_b",
    "l2_code",
    "status",
    "message",
    "ratio",
    "factor",
    "pack_qty",
    "stake",
]
_TIER_LETTER = {0: None, 1: "A", 2: "B"}
_DECISION_STATUS = {"approve": "approved", "reject": "rejected", "defer": "deferred"}


@dataclass(frozen=True)
class Evaluations:
    """The ``lever1`` evaluations behind every output besides the bridge.

    ``cases``: every filter on, per case. ``gross``: filters 1 to 6 (``G1``).
    ``upside`` / ``upside_gross``: as ``cases["base"]`` / ``gross`` but with
    tier C items kept, which on those items is "if approved". ``unit_stake``:
    ``G1`` with every unit flag cleared. ``incoterm_stake``: ``G1`` with filter
    5 off.
    """

    cases: Mapping[str, Lever1Result]
    gross: Lever1Result
    upside: Lever1Result
    upside_gross: Lever1Result
    unit_stake: Lever1Result
    incoterm_stake: Lever1Result


def evaluate(
    inputs: Lever1Inputs, assumptions: Mapping[str, Any], base: Lever1Result, gross: Lever1Result
) -> Evaluations:
    """Run the evaluations not already in the bridge (``base`` is ``F_7``, ``gross`` ``F_6``)."""
    keep_c = Filters(unverified_matches=False)
    gross_filters = Filters(capture_probability=False)
    unflagged = inputs.items.assign(unit_excluded=inputs.items["dimension_mismatch"])
    cases = {
        case: base if case == "base" else lever1(inputs, Filters(), case, assumptions)
        for case in CASES
    }
    return Evaluations(
        cases=cases,
        gross=gross,
        upside=lever1(inputs, keep_c, "base", assumptions),
        upside_gross=lever1(
            inputs, replace(keep_c, capture_probability=False), "base", assumptions
        ),
        unit_stake=lever1(replace(inputs, items=unflagged), gross_filters, "base", assumptions),
        incoterm_stake=lever1(inputs, replace(gross_filters, incoterms=False), "base", assumptions),
    )


def opportunity_ids(inputs: Lever1Inputs, ev: Evaluations) -> np.ndarray:
    """Each group's opportunity id, or ``None`` when it contributes nothing."""
    pending = inputs.items["pending"].to_numpy(dtype=bool)[inputs.item]
    result = np.where(pending, ev.upside_gross.contribution, ev.gross.contribution)
    change = np.where(pending, ev.upside.change_type, ev.cases["base"].change_type)
    ids = np.array(
        [
            f"L1:{item}:{c}" if value > 0 else None
            for item, c, value in zip(
                inputs.groups["canonical_item_id"], change, result, strict=True
            )
        ],
        dtype=object,
    )
    return ids


def build_opportunities(
    inputs: Lever1Inputs, ev: Evaluations, opportunity: np.ndarray
) -> pd.DataFrame:
    """One row per lever-1 opportunity, sorted by id."""
    g = inputs.groups
    items = inputs.items
    pending = items["pending"].to_numpy(dtype=bool)[inputs.item]
    base = ev.cases["base"]
    holder_rank = np.where(pending, ev.upside.holder_rank, base.holder_rank)
    holder_group = np.where(pending, ev.upside.holder_group, base.holder_group)
    reference = np.where(pending, ev.upside.reference, base.reference)
    fallback = np.where(pending, ev.upside.fallback, base.fallback)
    holder_tier = np.where(
        holder_group >= 0, g["vendor_tier_rank"].to_numpy()[np.clip(holder_group, 0, None)], 0
    )
    frame = pd.DataFrame(
        {
            "opportunity_id": opportunity,
            "canonical_item_id": g["canonical_item_id"],
            "item": inputs.item,
            "change_type": np.where(pending, ev.upside.change_type, base.change_type),
            "site_key": g["company"] + "|" + g["site"],
            "vendor_rank": np.maximum(g["vendor_tier_rank"].to_numpy(), holder_tier),
            "gross_gap": np.where(pending, ev.upside_gross.contribution, ev.gross.contribution),
            "upside_base": np.where(pending, ev.upside.contribution, 0.0),
            "benchmark_price": reference,
            "benchmark_rank": holder_rank,
            "benchmark_fallback": fallback,
            **{case: ev.cases[case].contribution for case in CASES},
        }
    ).dropna(subset=["opportunity_id"])
    opps = frame.groupby("opportunity_id", sort=True).agg(
        canonical_item_id=("canonical_item_id", "first"),
        item=("item", "first"),
        change_type=("change_type", "first"),
        vendor_rank=("vendor_rank", "max"),
        gross_gap=("gross_gap", "sum"),
        low=("low", "sum"),
        base=("base", "sum"),
        high=("high", "sum"),
        upside_base=("upside_base", "sum"),
        sites_affected=("site_key", "nunique"),
        groups=("site_key", "size"),
        benchmark_price=("benchmark_price", "first"),
        benchmark_rank=("benchmark_rank", "first"),
        benchmark_fallback=("benchmark_fallback", "first"),
    )
    facts = items.iloc[opps["item"].to_numpy()]
    opps["lever"] = 1
    opps["l2_code"] = facts["l2_code"].to_numpy()
    opps["tier"] = facts["item_tier"].to_numpy()
    opps["status"] = np.where(facts["pending"], "pending_review", "in_range")
    vendor_tier = opps["vendor_rank"].map(_TIER_LETTER).astype(object)
    opps["vendor_tier"] = vendor_tier.where(vendor_tier.notna(), None)
    opps["benchmark_company"] = [COMPANIES[r] for r in opps["benchmark_rank"]]
    opps["record_acquirer"] = facts["record_acquirer"].to_numpy()
    opps["record_target"] = facts["record_target"].to_numpy()
    return opps.reset_index()[OPPORTUNITY_COLUMNS]


def build_internal_variance(
    inputs: Lever1Inputs, internal: np.ndarray, benchmark: Lever1Result
) -> pd.DataFrame:
    """Gaps of the benchmark holder's own groups per item: bridge step 4's dollars.

    ``benchmark`` is ``F_3`` (reference price ``p_star``, holder still counted).
    """
    g = inputs.groups
    rows = np.flatnonzero(internal > 0)
    frame = pd.DataFrame(
        {
            "item": inputs.item[rows],
            "canonical_item_id": g["canonical_item_id"].to_numpy()[rows],
            "site_key": (g["company"] + "|" + g["site"]).to_numpy()[rows],
            "benchmark_rank": benchmark.holder_rank[rows],
            "benchmark_price": benchmark.reference[rows],
            "internal_variance": internal[rows],
        }
    )
    out = frame.groupby("canonical_item_id", sort=True).agg(
        item=("item", "first"),
        benchmark_rank=("benchmark_rank", "first"),
        benchmark_price=("benchmark_price", "first"),
        internal_variance=("internal_variance", "sum"),
        groups=("site_key", "size"),
        sites_affected=("site_key", "nunique"),
    )
    facts = inputs.items.iloc[out["item"].to_numpy()]
    out["l2_code"] = facts["l2_code"].to_numpy()
    out["tier"] = facts["item_tier"].to_numpy()
    out["benchmark_company"] = [COMPANIES[r] for r in out["benchmark_rank"]]
    return out.reset_index()[INTERNAL_VARIANCE_COLUMNS]


def build_review_items(inputs: Lever1Inputs, ev: Evaluations) -> pd.DataFrame:
    """``unit_flag`` and ``incoterm`` review items for matched items (PRD 3.5, 4.5)."""
    items = inputs.items
    matched = ~items["pending"].to_numpy(dtype=bool)
    unit_stake = _per_item(inputs, ev.unit_stake.contribution)
    held = ev.incoterm_stake.contribution * ev.incoterm_stake.mismatch_raw
    incoterm_stake = _per_item(inputs, held)
    unit = items[matched & items["unit_flag_raw"].to_numpy(dtype=bool)]
    incoterm = items[matched & (incoterm_stake > 0)]
    frames = [
        _unit_rows(unit, unit_stake[unit.index.to_numpy()]),
        _incoterm_rows(inputs, ev, incoterm, incoterm_stake[incoterm.index.to_numpy()]),
    ]
    present = [f for f in frames if not f.empty]
    if not present:
        return pd.DataFrame(columns=REVIEW_ITEM_COLUMNS)
    out = pd.concat(present, ignore_index=True)
    return out.sort_values("pair_id", kind="mergesort").reset_index(drop=True)[REVIEW_ITEM_COLUMNS]


def _per_item(inputs: Lever1Inputs, values: np.ndarray) -> np.ndarray:
    return np.bincount(inputs.item, weights=values, minlength=inputs.n_items)


def _status(decision: pd.Series) -> pd.Series:
    return decision.map(_DECISION_STATUS).fillna("pending").astype(object)


def _unit_rows(unit: pd.DataFrame, stake: np.ndarray) -> pd.DataFrame:
    """A pack quantity re-runs the comparison, so a still-flagged item is pending again."""
    status = _status(unit["unit_decision"])
    reflagged = unit["pack_qty"].notna() & unit["unit_flag"]
    status = status.where(~reflagged, "pending")
    return pd.DataFrame(
        {
            "pair_id": unit["unit_pair_id"],
            "type": "unit_flag",
            "canonical_item_id": unit["canonical_item_id"],
            "key_a": unit["record_acquirer"],
            "key_b": unit["record_target"],
            "l2_code": unit["l2_code"],
            "status": status,
            "message": unit["message"].where(reflagged, unit["message_raw"]),
            "ratio": unit["ratio"].where(reflagged, unit["ratio_raw"]),
            "factor": unit["factor"].where(reflagged, unit["factor_raw"]),
            "pack_qty": unit["pack_qty"],
            "stake": stake,
        }
    )


def _incoterm_rows(
    inputs: Lever1Inputs, ev: Evaluations, incoterm: pd.DataFrame, stake: np.ndarray
) -> pd.DataFrame:
    result = ev.incoterm_stake
    g = inputs.groups
    held = (result.contribution > 0) & result.mismatch_raw
    found: dict[int, set[str]] = {}
    for item, term in zip(inputs.item[held], g["incoterm"].to_numpy()[held], strict=True):
        found.setdefault(int(item), set()).add(term)
    terms = {item: "/".join(sorted(values)) for item, values in found.items()}
    holder = pd.Series(result.holder_rank[held]).groupby(inputs.item[held]).first()
    messages = []
    for item, row in incoterm.iterrows():
        rank = int(holder[item])
        holder_term = row[f"incoterm_{COMPANIES[rank]}"]
        other = COMPANIES[1 - rank]
        messages.append(
            f"Incoterms differ: the benchmark holder ({COMPANIES[rank]}) buys mostly on "
            f"{holder_term}, the {other} on {terms[item]}; the gap may be freight, not price"
        )
    return pd.DataFrame(
        {
            "pair_id": incoterm["incoterm_pair_id"],
            "type": "incoterm",
            "canonical_item_id": incoterm["canonical_item_id"],
            "key_a": incoterm["record_acquirer"],
            "key_b": incoterm["record_target"],
            "l2_code": incoterm["l2_code"],
            "status": _status(incoterm["incoterm_decision"]),
            "message": messages,
            "ratio": np.nan,
            "factor": np.nan,
            "pack_qty": np.nan,
            "stake": stake,
        }
    )
