"""The synergy stage: matched lines in; levers, bridge, risk, phasing and trace out.

Arithmetic only: matching is done before this stage, and nothing here scores
pairs. :func:`precompute` builds everything that does not depend on the
assumptions once; :func:`evaluate` runs the arithmetic for one set of
assumptions, which is what a recalculation repeats. ``compute_synergy`` is the
two in sequence.

The levers run in sequence on a declining baseline (PRD 5.1): lever 2 deducts
lever-1 savings and skips lever-1 ``switch`` spend, lever 3 nets both off.
``totals["recurring"]`` is lever 1 + lever 2; one-time amounts (lever-3 cash,
switching costs) sit under ``one_time`` and are never added to it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from tieout.assumptions import merge_overrides, validate
from tieout.reference import load_taxonomy
from tieout.synergy.assemble import (
    State,
    build_costs,
    build_measures,
    build_opportunities_all,
    new_children,
    new_figures,
    new_totals,
)
from tieout.synergy.bridge import N_STEPS, Bridge, bridge_detail, compute_bridge
from tieout.synergy.cube import SpendCube, build_cube
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
from tieout.synergy.lever1 import CASES, Filters, Lever1Inputs, Lever1Result, lever1
from tieout.synergy.lever2 import lever2
from tieout.synergy.lever3 import lever3
from tieout.synergy.opportunities import (
    Evaluations,
    build_internal_variance,
    build_opportunities,
    build_review_items,
    opportunity_ids,
)
from tieout.synergy.opportunities import (
    evaluate as evaluate_lever1,
)
from tieout.synergy.phasing import CONTRACT, GLOBAL_RAMP, build_phasing, line_available_month
from tieout.synergy.risk import build_category_risk, sole_source_items
from tieout.synergy.settings import CategoryParams, category_params
from tieout.synergy.trace import (
    LineIndex,
    TraceIndex,
    build_trace,
    extend_trace,
    line_contributions,
)

__all__ = [
    "SynergyCache",
    "SynergyOutputs",
    "close_date",
    "compute_synergy",
    "evaluate",
    "planning_limit",
    "precompute",
    "recurring_base",
]


@dataclass(frozen=True)
class SynergyOutputs:
    """Everything the synergy stage produces.

    ``item_gross_gaps`` (``canonical_item_id``, ``gross_gap``: ``G1`` before
    capture probability, matched items only) and ``removed_at_step1`` (items
    bridge step 1 removes) feed the accuracy scorecard (PRD 4.7).
    ``opportunities`` holds levers 1 to 3; ``category_risk`` one row per
    (category, parent vendor); ``payment_terms`` one row per (parent vendor,
    company) of vendors shared at tier A or B; ``phasing`` quarter x row type
    x lever x wave.
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
    category_risk: pd.DataFrame
    payment_terms: pd.DataFrame
    phasing: pd.DataFrame


@dataclass(frozen=True)
class SynergyCache:
    """The assumption-independent pieces of the stage, built once per matching result."""

    tagged: pd.DataFrame
    groups: pd.DataFrame
    line_group: np.ndarray
    facts: pd.DataFrame
    cube: SpendCube
    tagged_rows: np.ndarray
    criticality: dict[str, str]
    human_items: frozenset[str]
    meta: Mapping[str, Any]
    line_test: bool


def close_date(assumptions: Mapping[str, Any], meta: Mapping[str, Any]) -> pd.Timestamp | None:
    """``assumptions["close_date"]``, else the first day of the month after the data window."""
    close = assumptions.get("close_date")
    if close is None and meta.get("period"):
        close = (pd.Period(meta["period"]["end"], freq="M") + 1).start_time
    return None if close is None else pd.Timestamp(close)


def planning_limit(assumptions: Mapping[str, Any], meta: Mapping[str, Any]) -> pd.Timestamp | None:
    """Close date plus the planning horizon, or ``None`` when no close date is known (PRD 5.1)."""
    close = close_date(assumptions, meta)
    if close is None:
        return None
    return close + pd.DateOffset(months=int(assumptions["planning_horizon_months"]))


def precompute(
    lines: pd.DataFrame,
    vendor_map: pd.DataFrame,
    item_map: pd.DataFrame,
    item_pairs: pd.DataFrame,
    decisions: pd.DataFrame | None,
    meta: Mapping[str, Any],
    taxonomy: pd.DataFrame | None = None,
) -> SynergyCache:
    """Buying groups, item facts and the spend cube; ``taxonomy`` gives each L2's criticality."""
    items = lever1_items(item_map, item_pairs)
    raw = tag_lines(lines, vendor_map, items)
    packs = pack_quantities(decisions)
    tagged = add_line_sets(apply_pack_quantities(raw, packs))
    groups, line_group = build_price_groups(tagged)
    facts = build_item_facts(
        tagged, add_line_sets(raw) if packs else tagged, items, decisions, packs
    )
    cube = build_cube(lines, vendor_map)
    tax = load_taxonomy() if taxonomy is None else taxonomy
    human_records = set(item_map.loc[item_map["stage"] == "human", "item_record_id"])
    human = facts["record_acquirer"].isin(human_records) | facts["record_target"].isin(
        human_records
    )
    return SynergyCache(
        tagged=tagged,
        groups=groups,
        line_group=line_group,
        facts=facts,
        cube=cube,
        tagged_rows=cube.positions(tagged["line_id"].to_numpy(dtype=object)),
        criticality=dict(zip(tax["l2_code"], tax["criticality"], strict=True)),
        human_items=frozenset(facts.loc[human, "canonical_item_id"]),
        meta=dict(meta),
        line_test=not bool(meta.get("aggregated", False)),
    )


def compute_synergy(
    lines: pd.DataFrame,
    vendor_map: pd.DataFrame,
    item_map: pd.DataFrame,
    item_pairs: pd.DataFrame,
    assumptions: Mapping[str, Any] | None,
    decisions: pd.DataFrame | None,
    meta: Mapping[str, Any],
    taxonomy: pd.DataFrame | None = None,
) -> SynergyOutputs:
    """Levers 1 to 3 with bridge, risk, phasing, prioritisation, totals and trace (PRD 5)."""
    cache = precompute(lines, vendor_map, item_map, item_pairs, decisions, meta, taxonomy)
    return evaluate(cache, assumptions)


# ---------------------------------------------------------------- lever 1 pieces


@dataclass(frozen=True)
class _Lever1Setup:
    inputs: Lever1Inputs
    lines: LineIndex
    assessed: bool


def _settings(assumptions: Mapping[str, Any] | None) -> dict[str, Any]:
    settings = merge_overrides(assumptions)
    validate(settings)
    return settings


def _lever1_setup(cache: SynergyCache, settings: Mapping[str, Any]) -> _Lever1Setup:
    """Contract share ``a`` for the horizon, then the encoded lever-1 inputs."""
    tagged, groups, line_group = cache.tagged, cache.groups, cache.line_group
    limit = planning_limit(settings, cache.meta)
    assessed = limit is not None and bool(tagged["contract_end_date"].notna().any())
    is_open = contract_open(tagged, limit if assessed else None)
    def_w = tagged["def_w"].to_numpy()
    q = groups["q"].to_numpy()
    q_open = np.bincount(line_group, weights=def_w * is_open, minlength=len(groups))
    a = np.clip(np.where(q > 0, q_open / np.where(q > 0, q, 1.0), 1.0), 0.0, 1.0)
    inputs = Lever1Inputs.build(groups.assign(q_open=q_open, a=a), cache.facts, cache.line_test)
    lines = LineIndex(
        line_id=tagged["line_id"].to_numpy(dtype=object),
        group=line_group,
        naive_w=tagged["naive_w"].to_numpy(),
        def_w=def_w,
        open=is_open,
    )
    return _Lever1Setup(inputs, lines, assessed)


def _switch_groups(inputs: Lever1Inputs, gross: Lever1Result, base: Lever1Result) -> np.ndarray:
    """Groups in an in-range lever-1 ``switch`` opportunity."""
    pending = inputs.items["pending"].to_numpy(dtype=bool)[inputs.item]
    return ~pending & (gross.contribution > 0) & (base.change_type == "switch")


def _scatter(cache: SynergyCache, values: np.ndarray) -> np.ndarray:
    """Tagged-line values placed on their cube rows (zero elsewhere)."""
    out = np.zeros(len(cache.cube), dtype=np.result_type(values, float))
    out[cache.tagged_rows] = values
    return out


def _switch_lines(cache: SynergyCache, setup: _Lever1Setup, switch: np.ndarray) -> np.ndarray:
    mask = switch[setup.lines.group] & setup.lines.in_comparison
    return _scatter(cache, mask.astype(float)) > 0


def _category_params(cache: SynergyCache, settings: Mapping[str, Any]) -> CategoryParams:
    cube = cache.cube
    return category_params(cube.l2_codes, cube.category_type, cache.criticality, settings)


def recurring_base(cache: SynergyCache, assumptions: Mapping[str, Any] | None) -> float:
    """Base-case total recurring saving (lever 1 + lever 2) without the other outputs."""
    settings = _settings(assumptions)
    setup = _lever1_setup(cache, settings)
    base = lever1(setup.inputs, Filters(), "base", settings)
    gross = lever1(setup.inputs, Filters(capture_probability=False), "base", settings)
    l1 = _scatter(cache, line_contributions(setup.inputs, setup.lines, base))
    switch = _switch_lines(cache, setup, _switch_groups(setup.inputs, gross, base))
    params = _category_params(cache, settings)
    lev2 = lever2(cache.cube, params, dict.fromkeys(CASES, l1), switch, settings)
    return base.total + float(lev2.N2["base"].sum())


# ---------------------------------------------------------------- evaluate


def _phasing_method(cache: SynergyCache, settings: Mapping[str, Any]) -> tuple[str, np.ndarray]:
    """Contract-aware phasing when contract end dates and a close date exist, else the ramp.

    Returns the method and each cube line's available month.
    """
    cube = cache.cube
    close, limit = close_date(settings, cache.meta), planning_limit(settings, cache.meta)
    if close is None or limit is None or not bool(cube.contract_end.notna().any()):
        return GLOBAL_RAMP, np.zeros(len(cube), dtype=np.int64)
    return CONTRACT, line_available_month(cube.contract_end, close, limit)


def evaluate(cache: SynergyCache, assumptions: Mapping[str, Any] | None) -> SynergyOutputs:
    """Run every lever and output for one set of assumptions."""
    settings = _settings(assumptions)
    setup = _lever1_setup(cache, settings)
    inputs = setup.inputs
    bridge = compute_bridge(inputs, settings)
    ev = evaluate_lever1(
        inputs, settings, base=bridge.results[-1], gross=bridge.results[N_STEPS - 1]
    )
    opportunity = opportunity_ids(inputs, ev)
    lever1_opps = build_opportunities(inputs, ev, opportunity)
    internal = bridge.results[3].contribution - bridge.results[4].contribution
    trace = build_trace(inputs, setup.lines, bridge, ev, lever1_opps, opportunity)
    facts = cache.facts
    matched = ~facts["pending"].to_numpy(dtype=bool)
    gross_per_item = np.bincount(inputs.item, weights=ev.gross.contribution, minlength=len(facts))

    cube = cache.cube
    l1 = {
        case: _scatter(cache, line_contributions(inputs, setup.lines, ev.cases[case]))
        for case in CASES
    }
    switch = _switch_groups(inputs, ev.gross, ev.cases["base"])
    switch_lines = _switch_lines(cache, setup, switch)
    params = _category_params(cache, settings)
    lev2 = lever2(cube, params, l1, switch_lines, settings)
    uncapped = lever2(cube, params, l1, switch_lines, settings, cap=np.ones_like(params.cap))
    lev3 = lever3(
        cube,
        l1,
        lev2,
        settings,
        enabled=all(cube.has_terms_data.values()),
        observed_allowed=not bool(cache.meta.get("aggregated", False)),
    )
    method, available = _phasing_method(cache, settings)
    state = State(
        cube=cube,
        tagged=cache.tagged,
        tagged_rows=cache.tagged_rows,
        inputs=inputs,
        lines=setup.lines,
        ev=ev,
        opportunity=opportunity,
        switch=switch,
        params=params,
        lev2=lev2,
        lev2_uncapped=uncapped,
        lev3=lev3,
        l1=l1,
        criticality={
            **cache.criticality,
            **dict(zip(params.l2_codes, params.criticality, strict=True)),
        },
        human_items=cache.human_items,
        method=method,
        available=available,
    )
    opportunities = build_opportunities_all(state, lever1_opps, settings["lead_time_months"])
    costs = build_costs(state, settings)
    phasing = build_phasing(opportunities, costs.per_opportunity, method, settings["global_ramp"])

    totals = _totals(inputs, bridge, ev, settings, cache.meta, setup.assessed, cache.line_test)
    extra = new_totals(state, opportunities, phasing, costs, settings, totals["levers"]["lever1"])
    totals["levers"].update(extra.pop("levers"))
    totals["checks"].update(extra.pop("checks"))
    totals.update(extra)
    trace = extend_trace(
        trace,
        cube.line_id,
        build_measures(state, opportunities, costs, settings),
        new_children(state, opportunities, costs),
        new_figures(),
    )
    return SynergyOutputs(
        price_groups=_price_groups(inputs, bridge, ev, opportunity),
        bridge_detail=bridge_detail(inputs, bridge),
        opportunities=opportunities,
        internal_variance=build_internal_variance(inputs, internal, bridge.results[3]),
        review_items=build_review_items(inputs, ev),
        totals=totals,
        trace=trace,
        item_gross_gaps=pd.DataFrame(
            {
                "canonical_item_id": facts.loc[matched, "canonical_item_id"].to_numpy(),
                "gross_gap": gross_per_item[matched],
            }
        ),
        removed_at_step1=_removed_at_step1(facts),
        category_risk=build_category_risk(
            cube, params, lev2, uncapped, sole_source_items(cache.tagged)
        ),
        payment_terms=lev3.groups,
        phasing=phasing,
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
