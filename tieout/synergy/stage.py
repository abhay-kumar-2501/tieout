"""The synergy stage: matched lines in, lever-1 figures, bridge and trace out.

Arithmetic only: matching is done before this stage, and nothing here scores
pairs. ``totals`` is keyed by lever so that levers 2 and 3 slot in beside
lever 1; ``recurring`` sums the recurring levers present.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from tieout.assumptions import merge_overrides, validate
from tieout.synergy.bridge import N_STEPS, Bridge, bridge_detail, compute_bridge
from tieout.synergy.groups import (
    COMPANIES,
    add_line_sets,
    apply_pack_quantities,
    build_item_facts,
    build_price_groups,
    contract_open,
    lever1_items,
    pack_quantities,
    tag_lines,
)
from tieout.synergy.lever1 import CASES, Lever1Inputs
from tieout.synergy.opportunities import (
    Evaluations,
    build_internal_variance,
    build_opportunities,
    build_review_items,
    evaluate,
    opportunity_ids,
)
from tieout.synergy.trace import LineIndex, TraceIndex, build_trace

__all__ = ["SynergyOutputs", "compute_synergy", "planning_limit"]


@dataclass(frozen=True)
class SynergyOutputs:
    """Everything the synergy stage produces.

    ``item_gross_gaps`` (``canonical_item_id``, ``gross_gap``: ``G1`` before
    capture probability, matched items only) and ``removed_at_step1`` (items
    bridge step 1 removes) feed the accuracy scorecard (PRD 4.7).
    """

    price_groups: pd.DataFrame
    bridge_detail: pd.DataFrame
    opportunities: pd.DataFrame
    internal_variance: pd.DataFrame
    review_items: pd.DataFrame
    totals: dict[str, Any]
    trace: TraceIndex
    item_gross_gaps: pd.DataFrame
    removed_at_step1: frozenset[str]


def planning_limit(assumptions: Mapping[str, Any], meta: Mapping[str, Any]) -> pd.Timestamp | None:
    """Close date plus the planning horizon, or ``None`` when no close date is known.

    The close date is ``assumptions["close_date"]`` when given, otherwise the
    first day of the month after the data window (PRD 5.1).
    """
    close = assumptions.get("close_date")
    if close is None and meta.get("period"):
        close = (pd.Period(meta["period"]["end"], freq="M") + 1).start_time
    if close is None:
        return None
    months = int(assumptions["planning_horizon_months"])
    return pd.Timestamp(close) + pd.DateOffset(months=months)


def compute_synergy(
    lines: pd.DataFrame,
    vendor_map: pd.DataFrame,
    item_map: pd.DataFrame,
    item_pairs: pd.DataFrame,
    assumptions: Mapping[str, Any] | None,
    decisions: pd.DataFrame | None,
    meta: Mapping[str, Any],
) -> SynergyOutputs:
    """Lever 1 with its bridge, opportunities, review items, totals and trace (PRD 5.2)."""
    settings = merge_overrides(assumptions)
    validate(settings)
    items = lever1_items(item_map, item_pairs)
    raw = tag_lines(lines, vendor_map, items)
    packs = pack_quantities(decisions)
    tagged = add_line_sets(apply_pack_quantities(raw, packs))
    groups, line_group = build_price_groups(tagged)
    facts = build_item_facts(
        tagged, add_line_sets(raw) if packs else tagged, items, decisions, packs
    )

    limit = planning_limit(settings, meta)
    assessed = limit is not None and bool(tagged["contract_end_date"].notna().any())
    is_open = contract_open(tagged, limit if assessed else None)
    def_w = tagged["def_w"].to_numpy()
    q = groups["q"].to_numpy()
    q_open = np.bincount(line_group, weights=def_w * is_open, minlength=len(groups))
    a = np.clip(np.where(q > 0, q_open / np.where(q > 0, q, 1.0), 1.0), 0.0, 1.0)
    groups = groups.assign(q_open=q_open, a=a)
    line_test = not bool(meta.get("aggregated", False))
    inputs = Lever1Inputs.build(groups, facts, line_test)
    lines_index = LineIndex(
        line_id=tagged["line_id"].to_numpy(dtype=object),
        group=line_group,
        naive_w=tagged["naive_w"].to_numpy(),
        def_w=def_w,
        open=is_open,
    )

    bridge = compute_bridge(inputs, settings)
    ev = evaluate(inputs, settings, base=bridge.results[-1], gross=bridge.results[N_STEPS - 1])
    opportunity = opportunity_ids(inputs, ev)
    opportunities = build_opportunities(inputs, ev, opportunity)
    internal = bridge.results[3].contribution - bridge.results[4].contribution
    trace = build_trace(inputs, lines_index, bridge, ev, opportunities, opportunity)
    matched = ~facts["pending"].to_numpy(dtype=bool)
    gross_per_item = np.bincount(inputs.item, weights=ev.gross.contribution, minlength=len(facts))
    return SynergyOutputs(
        price_groups=_price_groups(inputs, bridge, ev, opportunity),
        bridge_detail=bridge_detail(inputs, bridge),
        opportunities=opportunities,
        internal_variance=build_internal_variance(inputs, internal, bridge.results[3]),
        review_items=build_review_items(inputs, ev),
        totals=_totals(inputs, bridge, ev, settings, meta, assessed, line_test),
        trace=trace,
        item_gross_gaps=pd.DataFrame(
            {
                "canonical_item_id": facts.loc[matched, "canonical_item_id"].to_numpy(),
                "gross_gap": gross_per_item[matched],
            }
        ),
        removed_at_step1=_removed_at_step1(facts),
    )


def _removed_at_step1(facts: pd.DataFrame) -> frozenset[str]:
    """Items with a suspected unit error, a base-unit clash or unconverted lines dropped."""
    removed = facts["unit_excluded"] | (facts["unconverted_lines"] > 0)
    return frozenset(facts.loc[removed, "canonical_item_id"])


def _price_groups(
    inputs: Lever1Inputs, bridge: Bridge, ev: Evaluations, opportunity: np.ndarray
) -> pd.DataFrame:
    """The groups frame with the working of the naive figure and the final case."""
    base = ev.cases["base"]
    holder = np.array([*COMPANIES, None], dtype=object)  # holder rank -1 (unpriced): None
    return inputs.groups.assign(
        min_price=bridge.results[0].reference,
        naive_gap=bridge.results[0].contribution,
        p_star=base.reference,
        benchmark_company=holder[base.holder_rank],
        benchmark_fallback=base.fallback,
        change_type=base.change_type,
        internal=base.internal,
        incoterm_mismatch=base.mismatch_raw,
        incoterm_held=base.mismatch,
        pi_base=base.pi,
        G1=ev.gross.contribution,
        N1_low=ev.cases["low"].contribution,
        N1_base=base.contribution,
        N1_high=ev.cases["high"].contribution,
        upside_base=np.where(
            inputs.items["pending"].to_numpy(dtype=bool)[inputs.item], ev.upside.contribution, 0.0
        ),
        opportunity_id=opportunity,
    )


def _totals(
    inputs: Lever1Inputs,
    bridge: Bridge,
    ev: Evaluations,
    settings: Mapping[str, Any],
    meta: Mapping[str, Any],
    assessed: bool,
    line_test: bool,
) -> dict[str, Any]:
    """Money figures by lever and case; every number outside ``checks`` is traced."""
    tier = inputs.items["item_tier"].to_numpy()[inputs.item]
    pending = inputs.items["pending"].to_numpy(dtype=bool)[inputs.item]
    cases = {case: ev.cases[case].total for case in CASES}

    def by_tier(letter: str) -> dict[str, float]:
        return {c: float(ev.cases[c].contribution[tier == letter].sum()) for c in CASES}

    return {
        "currency": str(meta.get("reporting_currency", settings["reporting_currency"])),
        "levers": {"lever1": {"kind": "recurring", "gross_gap": ev.gross.total, **cases}},
        "recurring": dict(cases),
        "lever1": {
            "naive": bridge.naive,
            "bridge": {
                **{f"step_{i}": s for i, s in enumerate(bridge.steps, start=1)},
                "defensible": bridge.defensible,
            },
            "bridge_raw": {f"step_{i}": s for i, s in enumerate(bridge.raw_steps, start=1)},
            "tier_a": by_tier("A"),
            "tier_b": by_tier("B"),
            "upside_pending_review": float(ev.upside.contribution[pending].sum()),
            "internal_variance": bridge.raw_steps[3],
        },
        "checks": {
            "bridge_tie_out_difference": bridge.tie_out_difference,
            "contract_lock_in_assessed": assessed,
            "benchmark_line_test": line_test,
        },
    }
