"""Opportunities, timing, costs, totals and trace for levers 2 and 3 (PRD 5.1, 5.3-5.8).

:class:`State` holds one evaluation's lever results; the functions here turn
it into the outputs. Every money figure is also built per cube line (the
``measures``), so each total re-sums from source rows like lever 1's:

- lever 2: ``total:recurring -> lever:2 -> L2:{l2} -> line_id`` (the category's
  eligible lines; a line carries ``weight x (amount - lever-1 saving) x d x pi2``);
- lever 3: ``lever:3 -> L3:{parent} -> vgrp:{company}|{parent} -> line_id``;
- one-time costs: ``one_time:costs -> event:{company}|{l2}|{destination} -> line_id``;
- spend: ``spend:baseline`` and ``spend:addressable`` list lines directly.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from tieout.synergy.cube import SpendCube
from tieout.synergy.groups import COMPANIES
from tieout.synergy.lever1 import Lever1Inputs
from tieout.synergy.lever2 import ONE_COMPANY, Lever2Result
from tieout.synergy.lever3 import DAYS_PER_YEAR, Lever3Result
from tieout.synergy.opportunities import OPPORTUNITY_COLUMNS, Evaluations
from tieout.synergy.phasing import (
    MONTHS,
    QUARTERS,
    net_three_year,
    start_quarter,
    switching_cost,
    year_factors,
)
from tieout.synergy.prioritise import FACTOR_COLUMNS, prioritise
from tieout.synergy.reconcile import reconcile
from tieout.synergy.settings import CASES, DEFAULT_CRITICALITY, CategoryParams
from tieout.synergy.trace import LineIndex, children_by

__all__ = [
    "ALL_OPPORTUNITY_COLUMNS",
    "Costs",
    "State",
    "build_costs",
    "build_measures",
    "build_opportunities_all",
    "new_children",
    "new_figures",
    "new_totals",
]

ALL_OPPORTUNITY_COLUMNS = [
    *OPPORTUNITY_COLUMNS,
    "parent_id",
    "basis_low",
    "basis_base",
    "basis_high",
    "available_month",
    "start_month",
    *FACTOR_COLUMNS,
    "complexity",
    "wave",
    "beyond_month_36",
]
RE_TENDER = "(re-tender)"
_LEAD = {
    "same_vendor": "l1_same_vendor",
    "switch": "l1_switch",
    "consolidation": "l2",
    "terms": "l3",
}
_FACT_COLUMNS = ["change", "criticality", "sites", "match_tier", "match_human"]


@dataclass(frozen=True)
class State:
    """One evaluation's lever results, as the assembly functions need them.

    ``tagged_rows`` maps lever-1 lines to cube rows; ``switch`` marks groups in
    in-range ``switch`` opportunities; ``l1[case]`` is each cube line's
    lever-1 saving; ``available`` each cube line's available month (all 0 on
    the global ramp).
    """

    cube: SpendCube
    tagged: pd.DataFrame
    tagged_rows: np.ndarray
    inputs: Lever1Inputs
    lines: LineIndex
    ev: Evaluations
    opportunity: np.ndarray
    switch: np.ndarray
    params: CategoryParams
    lev2: Lever2Result
    lev2_uncapped: Lever2Result
    lev3: Lever3Result
    l1: Mapping[str, np.ndarray]
    criticality: Mapping[str, str]
    human_items: frozenset[str]
    method: str
    available: np.ndarray

    @property
    def l2(self) -> np.ndarray:
        """Each cube line's category code, 0 for unmapped lines (mask with ``cube.mapped``)."""
        return np.where(self.cube.mapped, self.cube.l2, 0)

    @property
    def in_gain(self) -> np.ndarray:
        """Cube lines in a lever-3 group that gains days (``T_star > T``)."""
        return np.append(self.gap_days > 0, False)[self.lev3.line_group]

    @property
    def gap_days(self) -> np.ndarray:
        """``max(0, T_star - T)`` per lever-3 group."""
        g = self.lev3.groups
        return np.maximum(np.nan_to_num(g["T_star"].to_numpy(float) - g["T"].to_numpy(float)), 0.0)


# ---------------------------------------------------------------- vendor facts


def _uses(cube: SpendCube) -> np.ndarray:
    """``(company rank, parent)`` pairs present in the cube, as ``rank * n_parents + parent``."""
    rank = (cube.company == COMPANIES[1]).astype(np.int64)
    return np.unique(rank * len(cube.parents) + cube.parent)


def _parent_links(cube: SpendCube) -> tuple[np.ndarray, np.ndarray]:
    """Weakest vendor-link tier per parent (``A``/``B``/``None``) and "tier A by a reviewer"."""
    n = len(cube.parents)
    has_b = np.bincount(cube.parent, weights=cube.vendor_tier == "B", minlength=n) > 0
    has_a = np.bincount(cube.parent, weights=cube.vendor_tier == "A", minlength=n) > 0
    human_a = (cube.vendor_tier == "A") & (cube.vendor_stage == "human")
    human = np.bincount(cube.parent, weights=human_a, minlength=n) > 0
    tier = np.where(has_b, "B", np.where(has_a, "A", None)).astype(object)
    return tier, human


def _sites(cube: SpendCube, key: np.ndarray, mask: np.ndarray, n: int) -> np.ndarray:
    """Distinct (company, site) per key among masked lines, at least 1."""
    frame = pd.DataFrame(
        {"key": key[mask], "site": cube.company[mask] + "|" + cube.site[mask]}
    ).drop_duplicates()
    counts = np.bincount(frame["key"].to_numpy(dtype=np.int64), minlength=n)
    return np.maximum(counts, 1)


def _max_by(key: np.ndarray, values: np.ndarray, mask: np.ndarray, n: int) -> np.ndarray:
    out = np.zeros(n, dtype=np.int64)
    np.maximum.at(out, key[mask], values[mask])
    return out


# ---------------------------------------------------------------- opportunities


def _lever1_facts(state: State, opps: pd.DataFrame) -> pd.DataFrame:
    """Available month, change and match facts for the lever-1 opportunities."""
    inputs, lines, ev = state.inputs, state.lines, state.ev
    g = inputs.groups
    n_groups = len(g)
    comp = lines.in_comparison
    group_available = _max_by(lines.group, state.available[state.tagged_rows], comp, n_groups)

    pending = inputs.items["pending"].to_numpy(dtype=bool)[inputs.item]
    holder = np.where(pending, ev.upside.holder_group, ev.cases["base"].holder_group)
    parent_codes = {p: i for i, p in enumerate(state.cube.parents)}
    dest = np.array(
        [parent_codes.get(p, -1) for p in g["parent_id"].to_numpy()[np.clip(holder, 0, None)]]
    )
    rank = inputs.company_rank
    used = np.isin(rank * len(state.cube.parents) + dest, _uses(state.cube))
    switch_change = np.where(
        holder < 0, "re_tender", np.where(used, "existing_vendor", "new_vendor")
    )
    frame = pd.DataFrame(
        {
            "opportunity_id": state.opportunity,
            "available_month": group_available,
            "change": np.where(
                [o is not None and o.endswith(":switch") for o in state.opportunity],
                switch_change,
                "same_vendor",
            ),
        }
    ).dropna(subset=["opportunity_id"])
    order = {"same_vendor": 1, "existing_vendor": 3, "re_tender": 4, "new_vendor": 5}
    frame["_rank"] = frame["change"].map(order)
    per_opp = frame.groupby("opportunity_id", sort=True).agg(
        available_month=("available_month", "max"), _rank=("_rank", "max")
    )
    names = {rank: name for name, rank in order.items()}
    per_opp = per_opp.reindex(opps["opportunity_id"])
    return pd.DataFrame(
        {
            "available_month": per_opp["available_month"].to_numpy(dtype=np.int64),
            "change": per_opp["_rank"].map(names).to_numpy(dtype=object),
            "criticality": [
                state.criticality.get(code, DEFAULT_CRITICALITY) for code in opps["l2_code"]
            ],
            "sites": opps["sites_affected"].to_numpy(),
            "match_tier": opps["tier"].to_numpy(dtype=object),
            "match_human": opps["canonical_item_id"].isin(state.human_items).to_numpy(),
            "parent_id": None,
            **{f"basis_{case}": np.nan for case in CASES},
        },
        index=opps.index,
    )


def _blank_lever1_columns(n: int) -> dict[str, Any]:
    return {
        "canonical_item_id": np.full(n, None, dtype=object),
        "tier": np.full(n, None, dtype=object),
        "upside_base": np.zeros(n),
        "benchmark_price": np.full(n, np.nan),
        "benchmark_company": np.full(n, None, dtype=object),
        "benchmark_fallback": np.zeros(n, dtype=bool),
        "record_acquirer": np.full(n, None, dtype=object),
        "record_target": np.full(n, None, dtype=object),
    }


def _lever2_opportunities(state: State) -> pd.DataFrame:
    """One row per qualifying L2 category (``L2:{l2_code}``)."""
    cube, lev2, params = state.cube, state.lev2, state.params
    rows = np.flatnonzero(lev2.qualifies)
    n_l2 = len(cube.l2_codes)
    l2, mapped = state.l2, cube.mapped
    preferred = lev2.preferred[rows]
    tier, human = _parent_links(cube)
    moving = lev2.moved != 0
    uses = _uses(cube)
    rank = (cube.company == COMPANIES[1]).astype(np.int64)
    pref_line = np.where(mapped, lev2.preferred[l2], -1)
    new_vendor = moving & ~np.isin(rank * len(cube.parents) + pref_line, uses)
    any_new = np.bincount(l2[new_vendor], minlength=n_l2) > 0
    vendors_moving = pd.DataFrame({"l2": l2[moving], "p": cube.parent[moving]}).drop_duplicates()
    groups = np.bincount(vendors_moving["l2"].to_numpy(dtype=np.int64), minlength=n_l2) + 1
    status = np.where(
        lev2.f[rows] > 0, "in_range", np.where(lev2.M[rows] > 0, "cap_reached", "nothing_to_move")
    )
    codes = np.array(cube.l2_codes, dtype=object)[rows]
    sites = _sites(cube, l2, mapped & (lev2.weight > 0), n_l2)[rows]
    return pd.DataFrame(
        {
            "opportunity_id": "L2:" + pd.Series(codes, dtype=object),
            "lever": 2,
            "change_type": "consolidation",
            "l2_code": codes,
            "status": status,
            "vendor_tier": tier[preferred],
            "gross_gap": lev2.B2["base"][rows] * params.d[rows],
            **{case: lev2.N2[case][rows] for case in CASES},
            "sites_affected": sites,
            "groups": groups[rows],
            **_blank_lever1_columns(len(rows)),
            "parent_id": np.array(cube.parents, dtype=object)[preferred],
            **{f"basis_{case}": lev2.B2[case][rows] for case in CASES},
            "available_month": _max_by(l2, state.available, mapped & lev2.eligible, n_l2)[rows],
            "change": np.where(any_new[rows], "new_vendor", "existing_vendor"),
            "criticality": params.criticality[rows],
            "sites": sites,
            "match_tier": tier[preferred],
            "match_human": human[preferred],
        }
    )


def _lever3_opportunities(state: State) -> pd.DataFrame:
    """One row per parent vendor whose terms differ (``L3:{parent_id}``)."""
    cube, lev3 = state.cube, state.lev3
    g = lev3.groups
    gap = state.gap_days
    gains = (gap > 0) & (g["status"] == "opportunity").to_numpy()
    parent_of_group = np.searchsorted(np.array(cube.parents, dtype=object), g["parent_id"])
    in_gain = state.in_gain
    n_par = len(cube.parents)
    opp_parents = np.unique(parent_of_group[(g["status"] == "opportunity").to_numpy()])
    if not len(opp_parents):
        return pd.DataFrame()
    tier, human = _parent_links(cube)
    linked = lev3.line_group >= 0
    key = cube.l2[linked] * n_par + cube.parent[linked]
    by_l2 = pd.Series(cube.amount[linked]).groupby(key).sum()
    dominant = (
        pd.DataFrame({"key": by_l2.index, "spend": by_l2.to_numpy()})
        .assign(parent=lambda d: d["key"] % n_par, l2=lambda d: d["key"] // n_par)
        .sort_values(["parent", "spend", "l2"], ascending=[True, False, True], kind="mergesort")
        .drop_duplicates("parent")
        .set_index("parent")["l2"]
    )
    l2_codes = np.array(cube.l2_codes, dtype=object)
    l2_of = l2_codes[dominant.reindex(opp_parents).to_numpy(dtype=np.int64)]

    def per_parent(values: np.ndarray) -> np.ndarray:
        return np.bincount(parent_of_group, weights=values, minlength=n_par)[opp_parents]

    s_base = g["S_base"].to_numpy(float)
    sites = _sites(cube, cube.parent, in_gain, n_par)[opp_parents]
    return pd.DataFrame(
        {
            "opportunity_id": "L3:" + pd.Series(np.array(cube.parents, dtype=object)[opp_parents]),
            "lever": 3,
            "change_type": "terms",
            "l2_code": l2_of,
            "status": "in_range",
            "vendor_tier": tier[opp_parents],
            "gross_gap": per_parent(gap / DAYS_PER_YEAR * s_base),
            **{case: per_parent(g[f"cash_{case}"].to_numpy(float)) for case in CASES},
            "sites_affected": sites,
            "groups": np.bincount(parent_of_group[gains], minlength=n_par)[opp_parents],
            **_blank_lever1_columns(len(opp_parents)),
            "parent_id": np.array(cube.parents, dtype=object)[opp_parents],
            **{
                f"basis_{case}": per_parent(g[f"S_{case}"].to_numpy(float) * gains)
                for case in CASES
            },
            "available_month": _max_by(cube.parent, state.available, in_gain, n_par)[opp_parents],
            "change": "terms",
            "criticality": [state.criticality.get(c, DEFAULT_CRITICALITY) for c in l2_of],
            "sites": sites,
            "match_tier": tier[opp_parents],
            "match_human": human[opp_parents],
        }
    )


def build_opportunities_all(
    state: State, lever1_opps: pd.DataFrame, lead: Mapping[str, int]
) -> pd.DataFrame:
    """Levers 1 to 3 with available and start months, factor scores, complexity and wave."""
    first = pd.concat([lever1_opps, _lever1_facts(state, lever1_opps)], axis=1)
    frames = [first, _lever2_opportunities(state), _lever3_opportunities(state)]
    present = [f for f in frames if not f.empty]
    if not present:
        return pd.DataFrame(
            {
                c: pd.Series(dtype=float if c.startswith("basis") else object)
                for c in ALL_OPPORTUNITY_COLUMNS
            }
        ).astype({"start_month": np.int64, "available_month": np.int64, "lever": np.int64})
    opps = pd.concat(present, ignore_index=True)
    if not lever1_opps.empty:  # keep the lever-1 columns' dtypes (blank text stays NaN)
        opps = opps.astype({c: lever1_opps[c].dtype for c in OPPORTUNITY_COLUMNS})
    scores = prioritise(opps)
    lead_months = opps["change_type"].map(lambda c: int(lead[_LEAD[c]]))
    opps = pd.concat([opps.drop(columns=_FACT_COLUMNS), scores], axis=1)
    opps["start_month"] = opps["available_month"].to_numpy(dtype=np.int64) + lead_months
    opps["beyond_month_36"] = opps["start_month"] > MONTHS
    opps = opps.sort_values("opportunity_id", kind="mergesort").reset_index(drop=True)
    return opps[ALL_OPPORTUNITY_COLUMNS]


# ---------------------------------------------------------------- one-time costs


@dataclass(frozen=True)
class Costs:
    """Switching costs per cube line and case, the opportunity each line's cost belongs to."""

    line: Mapping[str, np.ndarray]
    opportunity: np.ndarray
    event: np.ndarray
    events: tuple[str, ...]
    per_opportunity: pd.DataFrame


def build_costs(state: State, settings: Mapping[str, Any]) -> Costs:
    """One switch event per (company, L2, destination parent) receiving moved spend (PRD 5.6).

    Lever-1 ``switch`` groups move the spend of their contract-open defensible
    lines to the benchmark group's parent vendor (``(re-tender)`` when the
    benchmark is the company-level fallback); lever 2 moves ``f x amount`` of
    each eligible line to the preferred vendor.
    """
    cube, tagged, inputs, ev = state.cube, state.tagged, state.inputs, state.ev
    n = len(cube)
    lines = state.lines
    g = inputs.groups
    group = lines.group
    moving1 = state.switch[group] & tagged["def_ok"].to_numpy(dtype=bool) & lines.open
    holder = ev.cases["base"].holder_group[group]
    dest1 = np.where(holder >= 0, g["parent_id"].to_numpy()[np.clip(holder, 0, None)], RE_TENDER)
    rows1 = state.tagged_rows[moving1]

    moved = np.zeros(n)
    moved[rows1] = tagged["amount"].to_numpy()[moving1]
    lev2_rows = np.flatnonzero(state.lev2.moved != 0)
    moved[lev2_rows] = state.lev2.moved[lev2_rows]
    l2_codes = np.array(cube.l2_codes, dtype=object)
    opportunity = np.full(n, None, dtype=object)
    opportunity[rows1] = state.opportunity[group[moving1]]
    opportunity[lev2_rows] = "L2:" + pd.Series(l2_codes[cube.l2[lev2_rows]], dtype=object)
    category = np.full(n, None, dtype=object)
    category[rows1] = g["l2_code"].to_numpy()[group[moving1]]
    category[lev2_rows] = l2_codes[cube.l2[lev2_rows]]
    dest = np.full(n, None, dtype=object)
    dest[rows1] = dest1[moving1]
    dest[lev2_rows] = np.array(cube.parents, dtype=object)[state.lev2.preferred[cube.l2[lev2_rows]]]

    moving = np.flatnonzero(pd.notna(opportunity))
    keys = (
        pd.Series(cube.company[moving], dtype=object)
        + "|"
        + pd.Series(category[moving], dtype=object).astype(str)
        + "|"
        + pd.Series(dest[moving], dtype=object).astype(str)
    )
    codes, events = pd.factorize(keys, sort=True)
    event = np.full(n, -1, dtype=np.int64)
    event[moving] = codes
    event_moved = np.bincount(codes, weights=moved[moving], minlength=len(events))
    cost_settings = settings["switching_cost"]
    line_cost = {}
    for case in CASES:
        pi = np.zeros(n)
        pi[rows1] = ev.cases[case].pi[group[moving1]]
        pi[lev2_rows] = state.params.pi2[case][cube.l2[lev2_rows]]
        line_cost[case] = np.zeros(n)
        line_cost[case][moving] = switching_cost(
            moved[moving],
            event_moved[codes],
            float(cost_settings["fixed_usd"]),
            float(cost_settings["pct_of_spend_moved"]),
            pi[moving],
        )
    per_opportunity = (
        pd.DataFrame(
            {"opportunity_id": opportunity[moving]} | {c: line_cost[c][moving] for c in CASES}
        )
        .groupby("opportunity_id", sort=True)[list(CASES)]
        .sum()
        .reset_index()
    )
    return Costs(
        line=line_cost,
        opportunity=opportunity,
        event=event,
        events=tuple(f"event:{e}" for e in events),
        per_opportunity=per_opportunity,
    )


# ---------------------------------------------------------------- measures


def _line_opportunity_rows(state: State, opps: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Row in ``opps`` of each cube line's lever-1 and lever-2 opportunity (-1 when none)."""
    index = pd.Index(opps["opportunity_id"])
    lever1 = np.full(len(state.cube), -1, dtype=np.int64)
    group_row = index.get_indexer(pd.Series(state.opportunity, dtype=object))
    lever1[state.tagged_rows] = group_row[state.lines.group]
    l2_ids = "L2:" + pd.Series(np.array(state.cube.l2_codes, dtype=object), dtype=object)
    per_l2 = index.get_indexer(l2_ids)
    lever2 = np.where(state.cube.mapped, per_l2[state.l2] if len(per_l2) else -1, -1)
    return lever1, lever2


def build_measures(
    state: State, opps: pd.DataFrame, costs: Costs, settings: Mapping[str, Any]
) -> dict[str, np.ndarray]:
    """Every new figure's contribution per cube line (the trace measures)."""
    cube, lev2, lev3 = state.cube, state.lev2, state.lev3
    l2 = state.l2
    factors = year_factors(opps["start_month"].to_numpy(), state.method, settings["global_ramp"])
    factors = np.vstack([factors, np.zeros((1, factors.shape[1]))])  # row -1: no opportunity
    row1, row2 = _line_opportunity_rows(state, opps)
    cost_row = pd.Index(opps["opportunity_id"]).get_indexer(pd.Series(costs.opportunity))
    quarters = np.append(start_quarter(opps["start_month"].to_numpy()), QUARTERS + 1)
    in_window = quarters[cost_row] <= QUARTERS
    gap = np.append(state.gap_days, 0.0)[lev3.line_group]
    coc = float(settings["cost_of_capital"])
    out: dict[str, np.ndarray] = {
        "spend": cube.amount,
        "l2_gross": lev2.line_B2["base"] * np.where(cube.mapped, state.params.d[l2], 0.0),
        "forgone": state.lev2_uncapped.line_N2["base"] - lev2.line_N2["base"],
        "l3_gross": gap / DAYS_PER_YEAR * lev3.line_S["base"],
    }
    for case in CASES:
        l1, l2_saving = state.l1[case], lev2.line_N2[case]
        out[f"l2_{case}"] = l2_saving
        out[f"B2_{case}"] = lev2.line_B2[case]
        out[f"l3_{case}"] = lev3.line_cash[case]
        out[f"fin_{case}"] = lev3.line_cash[case] * coc
        out[f"recurring_{case}"] = l1 + l2_saving
        out[f"net_{case}"] = cube.amount - l1 - l2_saving
        out[f"cost_{case}"] = costs.line[case]
        realised = np.zeros(len(cube))
        for year in range(factors.shape[1]):
            value = l1 * factors[row1, year] + l2_saving * factors[row2, year]
            out[f"realised_y{year + 1}_{case}"] = value
            realised += value
        out[f"net3_{case}"] = realised - costs.line[case] * in_window
    return out


# ---------------------------------------------------------------- totals


def _cases(values: Mapping[str, float] | Any) -> dict[str, float]:
    return {case: float(values[case]) for case in CASES}


def new_totals(
    state: State,
    opps: pd.DataFrame,
    phasing: pd.DataFrame,
    costs: Costs,
    settings: Mapping[str, Any],
    lever1_cases: Mapping[str, float],
) -> dict[str, Any]:
    """Totals for spend, levers 2 and 3, recurring, one-time, memo, phasing and reconciliation.

    Recurring (lever 1 + lever 2) and one-time amounts (lever-3 cash,
    switching costs) sit under separate keys and are never added together.
    """
    cube, lev2, lev3 = state.cube, state.lev2, state.lev3
    by_lever = {lever: opps[opps["lever"] == lever] for lever in (2, 3)}
    lever2_cases = {c: float(lev2.N2[c].sum()) for c in CASES}
    lever3_cases = {c: float(lev3.groups[f"cash_{c}"].sum()) for c in CASES}
    recurring = {c: lever1_cases[c] + lever2_cases[c] for c in CASES}
    cost = {c: float(costs.line[c].sum()) for c in CASES}
    savings = phasing[phasing["row_type"] == "saving"]
    yearly = savings.groupby("year")[list(CASES)].sum()
    window_costs = phasing[phasing["row_type"] == "cost"][list(CASES)].sum()
    realised = {f"year{y}": {c: float(yearly[c].get(y, 0.0)) for c in CASES} for y in range(1, 4)}
    three_year = {c: sum(realised[f"year{y}"][c] for y in range(1, 4)) for c in CASES}
    addressable_l2 = lev2.reason != ONE_COMPANY
    addressable = cube.mapped & addressable_l2[state.l2]
    baseline = float(cube.amount.sum())
    recurring_opps = opps[(opps["lever"] != 3) & (opps["status"] == "in_range")]
    beyond = opps[opps["beyond_month_36"] & (opps["base"] > 0)]
    coc = float(settings["cost_of_capital"])
    return {
        "spend": {
            "baseline": baseline,
            "addressable": float(cube.amount[addressable].sum()),
            "net_run_rate": {c: baseline - recurring[c] for c in CASES},
        },
        "levers": {
            "lever2": {
                "kind": "recurring",
                "gross": float(by_lever[2]["gross_gap"].sum()),
                **lever2_cases,
            },
            "lever3": {
                "kind": "one_time_cash",
                "gross": float(by_lever[3]["gross_gap"].sum()),
                **lever3_cases,
            },
        },
        "recurring": recurring,
        "defensible_range": {"low": recurring["low"], "high": recurring["high"]},
        "one_time": {"cash": dict(lever3_cases), "costs": cost},
        "memo": {"financing_value": {c: lever3_cases[c] * coc for c in CASES}},
        "lever2": {
            "B2": {c: float(lev2.B2[c].sum()) for c in CASES},
            "savings_forgone": float(state.lev2_uncapped.N2["base"].sum() - lev2.N2["base"].sum()),
        },
        "phasing": {
            "method": state.method,
            "realised": realised,
            "net_three_year": {
                c: net_three_year(three_year[c], float(window_costs[c])) for c in CASES
            },
            "beyond_month_36": beyond["opportunity_id"].tolist(),
        },
        "reconciliation": reconcile(
            recurring["base"],
            baseline,
            float(cube.amount[addressable].sum()),
            settings["reference_bands"],
            recurring_opps,
        ),
        "checks": {"lever3_enabled": lev3.enabled, "lever3_message": lev3.message},
    }


# ---------------------------------------------------------------- trace


def new_children(state: State, opps: pd.DataFrame, costs: Costs) -> dict[str, list[str]]:
    """Trace nodes for levers 2 and 3, spend, costs and phasing."""
    cube, lev2, lev3 = state.cube, state.lev2, state.lev3
    ids = cube.line_id
    l2_names = np.array(["L2:" + c for c in cube.l2_codes], dtype=object)
    children: dict[str, list[str]] = {}
    lever2_ids = opps.loc[opps["lever"] == 2, "opportunity_id"].tolist()
    lever3_ids = opps.loc[opps["lever"] == 3, "opportunity_id"].tolist()
    for node in lever2_ids:
        children[node] = []
    children.update(children_by(state.l2, cube.mapped & lev2.eligible, ids, l2_names))

    g = lev3.groups
    gains = state.gap_days > 0
    vgroups = np.array(
        [f"vgrp:{c}|{p}" for c, p in zip(g["company"], g["parent_id"], strict=True)], dtype=object
    )
    in_gain = state.in_gain
    children.update(children_by(lev3.line_group, in_gain, ids, vgroups))
    for node in lever3_ids:
        children[node] = []
    for parent, vgroup in zip(g["parent_id"].to_numpy()[gains], vgroups[gains], strict=True):
        children[f"L3:{parent}"].append(str(vgroup))

    addressable_l2 = lev2.reason != ONE_COMPANY
    events = np.array(costs.events, dtype=object)
    children.update(
        {
            "total:recurring": ["lever:1", "lever:2"],
            "lever:2": lever2_ids,
            "lever:3": lever3_ids,
            "spend:baseline": ids.tolist(),
            "spend:addressable": ids[cube.mapped & addressable_l2[state.l2]].tolist(),
            "spend:net": ["spend:baseline"],
            "one_time:costs": events.tolist(),
            "phasing:realised": ["total:recurring"],
            "phasing:net": ["total:recurring", "one_time:costs"],
        }
    )
    children.update(children_by(costs.event, costs.event >= 0, ids, events))
    return children


def new_figures() -> dict[str, tuple[str, str]]:
    """Dotted ``totals`` path -> (trace node, measure) for every new money figure."""
    figures = {
        "spend.baseline": ("spend:baseline", "spend"),
        "spend.addressable": ("spend:addressable", "spend"),
        "levers.lever2.gross": ("lever:2", "l2_gross"),
        "levers.lever3.gross": ("lever:3", "l3_gross"),
        "lever2.savings_forgone": ("lever:2", "forgone"),
        "reconciliation.total_spend.spend": ("spend:baseline", "spend"),
        "reconciliation.addressable_spend.spend": ("spend:addressable", "spend"),
    }
    for case in CASES:
        figures |= {
            f"spend.net_run_rate.{case}": ("spend:net", f"net_{case}"),
            f"levers.lever2.{case}": ("lever:2", f"l2_{case}"),
            f"levers.lever3.{case}": ("lever:3", f"l3_{case}"),
            f"recurring.{case}": ("total:recurring", f"recurring_{case}"),
            f"one_time.cash.{case}": ("lever:3", f"l3_{case}"),
            f"one_time.costs.{case}": ("one_time:costs", f"cost_{case}"),
            f"memo.financing_value.{case}": ("lever:3", f"fin_{case}"),
            f"lever2.B2.{case}": ("lever:2", f"B2_{case}"),
            f"phasing.net_three_year.{case}": ("phasing:net", f"net3_{case}"),
        }
        for year in (1, 2, 3):
            figures[f"phasing.realised.year{year}.{case}"] = (
                "phasing:realised",
                f"realised_y{year}_{case}",
            )
    for case in ("low", "high"):
        figures[f"defensible_range.{case}"] = ("total:recurring", f"recurring_{case}")
    return figures
