"""Chart data for PRD 6.8: Pareto, price dispersion, matrix, phasing, concentration,
tornado, scenarios and threshold sensitivity.

Each function returns plain frames or dictionaries ready to draw; nothing here
draws. Masked (integration-office) output names parent vendors by code and
categories by label, merges thin categories into "Other", and never carries
unit prices or item-level rows.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from tieout.synergy import SCENARIOS, evaluate, tornado
from tieout.views.common import (
    MASKED,
    NOT_IN_VIEW,
    OTHER,
    Unavailable,
    category_label,
    category_labels,
    item_labels,
    parent_labels,
    resolve_view,
    unit_price,
)
from tieout.views.overview import opportunity_labels

if TYPE_CHECKING:
    from tieout.results import Results

__all__ = [
    "CURRENT",
    "PARETO_SHARE",
    "TOP_LABELS",
    "TOP_VENDORS",
    "concentration",
    "phasing_by_quarter",
    "phasing_by_year",
    "price_dispersion",
    "prioritisation_matrix",
    "scenario_table",
    "sensitivity_curves",
    "sole_source",
    "spend_pareto",
    "tornado_chart",
]

PARETO_SHARE = 0.80
TOP_LABELS = 10  # prioritisation matrix: labels for the top ten only (PRD 6.8)
TOP_VENDORS = 5  # concentration: largest vendors per category, the rest as one bar
CURRENT = "Current assumptions"
OTHER_VENDORS = "All other vendors"
WAVES = (1, 2, 3)


# ---------------------------------------------------------------- Pareto


def _pareto(spend: pd.Series, labels: list[str]) -> pd.DataFrame:
    total = float(spend.sum())
    frame = pd.DataFrame({"label": labels, "spend": spend.to_numpy(dtype=float)})
    frame.insert(0, "rank", np.arange(1, len(frame) + 1))
    cumulative = frame["spend"].cumsum()
    frame["cumulative_share"] = cumulative / total if total > 0 else 0.0
    return frame


def _vendors_to(share: float, frame: pd.DataFrame) -> int:
    reached = frame.index[frame["cumulative_share"] >= share - 1e-12]
    return int(frame.loc[reached[0], "rank"]) if len(reached) else len(frame)


def spend_pareto(results: Results, view: str | None = None) -> dict[str, Any]:
    """Vendor fragmentation before matching (vendor records) and after (parent vendors).

    Bars are spend, largest first, with the cumulative share and the number of
    vendors that make up 80% of spend. Masked, parent vendors carry their codes
    and vendor records are numbered by rank only.
    """
    mode = resolve_view(results, view)
    records = results.vendor_map.sort_values(
        ["spend", "vendor_key"], ascending=[False, True], kind="mergesort"
    )
    before_labels = (
        [f"Record {n}" for n in range(1, len(records) + 1)]
        if mode == MASKED
        else records["vendor_name"].astype(str).tolist()
    )
    before = _pareto(records["spend"], before_labels)
    parents = results.lines.groupby("parent_id", sort=True)["amount"].sum().rename("spend")
    parents = (
        parents.reset_index()
        .sort_values(["spend", "parent_id"], ascending=[False, True], kind="mergesort")
        .set_index("parent_id")["spend"]
    )
    names = parent_labels(results, mode)
    after = _pareto(parents, [names[p] for p in parents.index])
    return {
        "before": before,
        "after": after,
        "vendor_records": len(before),
        "parent_vendors": len(after),
        "share": PARETO_SHARE,
        "vendors_to_share": {
            "before": _vendors_to(PARETO_SHARE, before),
            "after": _vendors_to(PARETO_SHARE, after),
        },
    }


# ---------------------------------------------------------------- price dispersion


def price_dispersion(
    results: Results, canonical_item_id: str, view: str | None = None
) -> dict[str, Any] | Unavailable:
    """Each buying group's price for one item, with the benchmark price (clean team only)."""
    mode = resolve_view(results, view)
    if mode == MASKED:
        return NOT_IN_VIEW
    groups = results.price_groups
    item = groups[groups["canonical_item_id"] == canonical_item_id]
    if item.empty:
        return Unavailable(f"No price comparison for item {canonical_item_id}.")
    names = parent_labels(results, mode)
    points = pd.DataFrame(
        {
            "company": item["company"].to_numpy(),
            "site": item["site"].to_numpy(),
            "vendor": [names.get(p, p) for p in item["parent_id"]],
            "price": item["p"].to_numpy(dtype=float),
            "price_text": [unit_price(p) for p in item["p"].to_numpy(dtype=float)],
            "quantity": item["q"].to_numpy(dtype=float),
            "lines": item["n_lines"].to_numpy(),
            "change_type": item["change_type"].to_numpy(),
            "gross_gap": item["G1"].to_numpy(dtype=float),
            "group_id": item["group_id"].to_numpy(),
        }
    )
    benchmark = item["p_star"].dropna()
    return {
        "canonical_item_id": canonical_item_id,
        "description": item_labels(results).get(canonical_item_id, ""),
        "benchmark_price": float(benchmark.iloc[0]) if len(benchmark) else float("nan"),
        "benchmark_company": item["benchmark_company"].dropna().iloc[0]
        if item["benchmark_company"].notna().any()
        else None,
        "points": points,
    }


# ---------------------------------------------------------------- prioritisation


def _opportunity_spend(results: Results, opps: pd.DataFrame) -> np.ndarray:
    """Spend behind each opportunity: its groups (lever 1), post-move base (2), vendor (3)."""
    groups = results.price_groups.groupby("opportunity_id")["amount"].sum()
    terms = results.payment_terms.groupby("parent_id")["spend"].sum()
    spend = np.where(
        opps["lever"] == 1,
        opps["opportunity_id"].map(groups).astype(float).fillna(0.0),
        np.where(
            opps["lever"] == 2,
            opps["basis_base"].astype(float).fillna(0.0),
            opps["parent_id"].map(terms).astype(float).fillna(0.0),
        ),
    )
    return spend.astype(float)


def prioritisation_matrix(results: Results, view: str | None = None) -> pd.DataFrame:
    """Saving against complexity, coloured by wave, sized by spend (PRD 5.7, 6.8).

    One row per in-range opportunity with a positive base (lever 3 is cash).
    Labels are kept for the ten largest only. Masked, opportunities are
    aggregated to lever x category: summed saving and spend, complexity
    weighted by saving, and the wave holding most of the saving.
    """
    mode = resolve_view(results, view)
    opps = results.opportunities
    live = opps[(opps["status"] == "in_range") & (opps["base"] > 0)].copy()
    live["spend"] = _opportunity_spend(results, live)
    live["label"] = opportunity_labels(results, live, mode)
    columns = ["label", "lever", "complexity", "base", "spend", "wave"]
    if mode == MASKED:
        live["weighted"] = live["complexity"] * live["base"]
        wave_base = live.groupby(["label", "lever", "wave"])["base"].sum().reset_index()
        top_wave = wave_base.sort_values(
            ["label", "lever", "base", "wave"],
            ascending=[True, True, False, True],
            kind="mergesort",
        ).drop_duplicates(["label", "lever"])
        grouped = (
            live.groupby(["label", "lever"], sort=True)[["base", "spend", "weighted"]]
            .sum()
            .reset_index()
        )
        grouped["complexity"] = grouped["weighted"] / grouped["base"]
        live = grouped.merge(top_wave[["label", "lever", "wave"]], on=["label", "lever"])
        live["figure_id"] = None
    else:
        live["figure_id"] = live["opportunity_id"]
    live = live.sort_values(["base", "label"], ascending=[False, True], kind="mergesort")
    out = live[[*columns, "figure_id"]].reset_index(drop=True)
    out["show_label"] = out.index < TOP_LABELS
    return out


# ---------------------------------------------------------------- phasing


def _wave_columns(frame: pd.DataFrame, key: str) -> pd.DataFrame:
    savings = frame[frame["row_type"] == "saving"]
    wide = savings.pivot_table(index=key, columns="wave", values="base", aggfunc="sum")
    wide = wide.reindex(columns=list(WAVES), fill_value=0.0).fillna(0.0)
    wide.columns = [f"wave_{w}" for w in WAVES]
    return wide


def phasing_by_quarter(results: Results, view: str | None = None) -> pd.DataFrame:
    """Realised savings by quarter and wave (base case), with one-time costs and cash apart.

    ``cost`` is negative; ``cash`` (lever 3, in the quarter of its start) is on
    its own column and never added to the savings (PRD 5.6).
    """
    resolve_view(results, view)
    phasing = results.phasing
    quarters = pd.Index(range(1, 13), name="quarter")
    out = _wave_columns(phasing, "quarter").reindex(quarters, fill_value=0.0)
    out["savings"] = out[[f"wave_{w}" for w in WAVES]].sum(axis=1)
    for row_type, sign in (("cost", -1.0), ("cash", 1.0)):
        rows = phasing[phasing["row_type"] == row_type].groupby("quarter")["base"].sum()
        out[row_type] = sign * rows.reindex(quarters, fill_value=0.0)
    out.insert(0, "year", (out.index - 1) // 4 + 1)
    return out.reset_index()


def phasing_by_year(results: Results, view: str | None = None) -> pd.DataFrame:
    """Realised savings by year and wave, one-time costs and the net three-year value.

    Rows are years 1 to 3 and a total; ``savings_low`` / ``savings_high`` and
    ``net_low`` / ``net_high`` give the range. Costs are negative.
    """
    resolve_view(results, view)
    phasing = results.phasing
    years = pd.Index([1, 2, 3], name="year")
    out = _wave_columns(phasing, "year").reindex(years, fill_value=0.0)
    savings = phasing[phasing["row_type"] == "saving"].groupby("year")[["low", "base", "high"]]
    costs = phasing[phasing["row_type"] == "cost"].groupby("year")[["low", "base", "high"]]
    saved, spent = savings.sum().reindex(years, fill_value=0.0), costs.sum()
    spent = spent.reindex(years, fill_value=0.0)
    out["savings"] = saved["base"]
    out["savings_low"], out["savings_high"] = saved["low"], saved["high"]
    out["cost"] = -spent["base"]
    for case in ("low", "base", "high"):
        out[f"net_{case}"] = saved[case] - spent[case]
    out = out.reset_index()
    total = out.drop(columns="year").sum().to_frame().T
    total.insert(0, "year", "Total")
    return pd.concat([out.astype({"year": object}), total], ignore_index=True)


# ---------------------------------------------------------------- concentration


def _top_vendors(frame: pd.DataFrame) -> pd.DataFrame:
    """The largest vendors per category by share after, the rest folded into one row."""
    frame = frame.sort_values(
        ["category", "spend_after", "vendor"], ascending=[True, False, True], kind="mergesort"
    )
    frame["rank"] = frame.groupby("category").cumcount()
    tail = frame["rank"] >= TOP_VENDORS
    frame.loc[tail, "vendor"] = OTHER_VENDORS
    frame.loc[tail, "preferred"] = False
    return frame.groupby(["category", "vendor"], sort=False, as_index=False).agg(
        spend_before=("spend_before", "sum"),
        spend_after=("spend_after", "sum"),
        preferred=("preferred", "max"),
        rank=("rank", "min"),
    )


def concentration(results: Results, view: str | None = None) -> dict[str, Any]:
    """Vendor shares by category before and after consolidation, with the cap (PRD 5.5).

    ``vendors``: one row per category and vendor (the five largest, then "All
    other vendors"), shares of category spend before and after. ``categories``:
    cap, concentration index before and after, savings forgone. Masked,
    vendors are codes and thin categories are merged into "Other" (their cap is
    blank when the merged categories' caps differ; the index is recomputed).
    """
    mode = resolve_view(results, view)
    risk = results.category_risk
    labels = category_labels(results, mode)
    names = parent_labels(results, mode)
    rows = pd.DataFrame(
        {
            "category": [category_label(labels, c) for c in risk["l2_code"]],
            "vendor": [names.get(p, p) for p in risk["parent_id"]],
            "spend_before": risk["spend_before"].clip(lower=0.0).to_numpy(dtype=float),
            "spend_after": risk["spend_after"].clip(lower=0.0).to_numpy(dtype=float),
            "preferred": risk["preferred"].to_numpy(dtype=bool),
        }
    )
    per_vendor = rows.groupby(["category", "vendor"], as_index=False).agg(
        spend_before=("spend_before", "sum"),
        spend_after=("spend_after", "sum"),
        preferred=("preferred", "max"),
    )
    for when in ("before", "after"):
        total = per_vendor.groupby("category")[f"spend_{when}"].transform("sum")
        per_vendor[f"share_{when}"] = np.where(total > 0, per_vendor[f"spend_{when}"] / total, 0.0)
    hhi = (
        per_vendor.assign(
            hhi_before=(100 * per_vendor["share_before"]) ** 2,
            hhi_after=(100 * per_vendor["share_after"]) ** 2,
        )
        .groupby("category")[["hhi_before", "hhi_after"]]
        .sum()
    )
    per_category = risk.drop_duplicates("l2_code").assign(
        category=lambda d: [category_label(labels, c) for c in d["l2_code"]]
    )
    caps = per_category.groupby("category")["cap"].agg(
        lambda c: float(c.iloc[0]) if c.nunique() == 1 else float("nan")
    )
    categories = pd.DataFrame(
        {
            "cap": caps,
            "hhi_before": hhi["hhi_before"],
            "hhi_after": hhi["hhi_after"],
            "savings_forgone": per_category.groupby("category")["savings_forgone"].sum(),
        }
    )
    categories["cap_limits"] = categories["savings_forgone"] > 0
    vendors = _top_vendors(per_vendor)
    for when in ("before", "after"):
        total = vendors.groupby("category")[f"spend_{when}"].transform("sum")
        vendors[f"share_{when}"] = np.where(total > 0, vendors[f"spend_{when}"] / total, 0.0)
    vendors["cap"] = vendors["category"].map(caps)
    columns = ["category", "vendor", "preferred", "share_before", "share_after", "cap"]
    ordered = categories.sort_values(
        ["savings_forgone", "hhi_after"], ascending=False, kind="mergesort"
    )
    return {
        "vendors": vendors[columns].reset_index(drop=True),
        "categories": ordered.reset_index().rename(columns={"index": "category"}),
        "other_label": OTHER,
    }


def sole_source(results: Results, view: str | None = None) -> dict[str, Any]:
    """Sole-source flags (PRD 5.5): categories left with one parent vendor after consolidation,
    and canonical items both companies buy from one parent vendor only.

    ``categories``: each category with a flag, whether it is left with one vendor
    (``category_sole_source``, and that vendor) and its number of flagged items (masked:
    vendors are codes and thin categories sit in "Other"). ``items``: one row
    per flagged item with its description and category; empty in the masked view, which
    carries no item-level detail.
    """
    mode = resolve_view(results, view)
    risk = results.category_risk
    labels = category_labels(results, mode)
    names = parent_labels(results, mode)
    empty_items = pd.DataFrame(columns=["item", "description", "category"])
    if risk.empty:
        return {
            "categories": pd.DataFrame(
                columns=["category", "category_sole_source", "vendor", "items"]
            ),
            "items": empty_items,
        }
    per_category = risk.drop_duplicates("l2_code")
    sole_vendor = (
        risk[risk["sole_source_category"].astype(bool) & (risk["spend_after"] > 0)]
        .drop_duplicates("l2_code")
        .set_index("l2_code")["parent_id"]
    )
    hit = per_category[
        per_category["sole_source_category"].astype(bool) | (per_category["sole_source_items"] > 0)
    ]
    categories = pd.DataFrame(
        {
            "category": [category_label(labels, c) for c in hit["l2_code"]],
            "category_sole_source": hit["sole_source_category"].astype(bool).to_numpy(),
            "vendor": [names.get(sole_vendor.get(c), "") for c in hit["l2_code"]],
            "items": hit["sole_source_items"].to_numpy(dtype=int),
        }
    )
    categories = categories.groupby("category", as_index=False).agg(
        category_sole_source=("category_sole_source", "max"),
        vendor=("vendor", "max"),
        items=("items", "sum"),
    )
    categories = categories.sort_values(
        ["category_sole_source", "items", "category"], ascending=[False, False, True]
    )
    if mode == MASKED:
        return {"categories": categories.reset_index(drop=True), "items": empty_items}
    described = item_labels(results)
    rows = []
    for l2, ids in zip(per_category["l2_code"], per_category["sole_source_item_ids"], strict=True):
        for item in [i for i in str(ids).split(", ") if i]:
            rows.append(
                {
                    "item": item,
                    "description": described.get(item, ""),
                    "category": category_label(labels, l2),
                }
            )
    items = pd.DataFrame(rows, columns=list(empty_items.columns))
    return {"categories": categories.reset_index(drop=True), "items": items}


# ---------------------------------------------------------------- assumptions


_PLAIN_NAMES = {
    "planning_horizon_months": "Planning horizon",
    "cost_of_capital": "Cost of capital",
    "lever1.same_vendor.base": "Same-vendor renegotiation: chance of capturing the gap",
    "lever1.switch.base": "Switching vendor: chance of capturing the gap",
    "lever2.capture.base": "Volume consolidation: chance of capturing the discount",
    "lever3.capture.base": "Payment terms: chance of moving to the longer terms",
    "lever3.max_payment_days": "Longest payment term to assume",
    "benchmark.min_volume_share": "Benchmark: smallest volume share",
    "benchmark.min_lines": "Benchmark: fewest purchase lines",
    "switching_cost.fixed_usd": "Fixed cost of switching a vendor",
    "switching_cost.pct_of_spend_moved": "Switching cost as a share of spend moved",
    "caps.critical": "Concentration cap, critical categories",
    "caps.standard": "Concentration cap, standard categories",
    "caps.non_critical": "Concentration cap, non-critical categories",
    "lead_time_months.l1_same_vendor": "Lead time, same-vendor renegotiation",
    "lead_time_months.l1_switch": "Lead time, switching vendor",
    "lead_time_months.l2": "Lead time, volume consolidation",
    "lead_time_months.l3": "Lead time, payment terms",
}
_TYPES = {
    "commodity": "Commodity",
    "engineered": "Engineered",
    "mro": "MRO",
    "indirect": "Indirect",
}


def _assumption_label(path: str) -> str:
    """A tornado row in the plain name the Assumptions screen uses (PRD 6.12)."""
    if path in _PLAIN_NAMES:
        return _PLAIN_NAMES[path]
    head, _, leaf = path.rpartition(".")
    if head == "lever2.discount" and leaf in _TYPES:
        return f"Volume discount, {_TYPES[leaf].lower()} categories"
    if head == "global_ramp":
        return f"Savings realised in {leaf.replace('year', 'year ')} (global ramp)"
    return path.replace("_", " ").replace(".", ": ").capitalize()


def tornado_chart(results: Results, view: str | None = None) -> pd.DataFrame:
    """The twelve assumptions that move the base total recurring saving most (PRD 6.7).

    Runs the base-case arithmetic about sixty times on the cached synergy
    inputs; recalculation of the main figures does not wait for it.
    """
    resolve_view(results, view)
    frame = tornado(results.cached_synergy(), results.assumptions)
    frame.insert(1, "label", [_assumption_label(p) for p in frame["assumption"]])
    frame["recurring_base"] = float(results.totals["recurring"]["base"])
    return frame


def _scenario_row(name: str, totals: Mapping[str, Any]) -> dict[str, Any]:
    recurring = totals["recurring"]
    return {
        "scenario": name,
        "recurring_low": float(recurring["low"]),
        "recurring_base": float(recurring["base"]),
        "recurring_high": float(recurring["high"]),
        "lever1_base": float(totals["levers"]["lever1"]["base"]),
        "lever2_base": float(totals["levers"]["lever2"]["base"]),
        "cash_base": float(totals["one_time"]["cash"]["base"]),
        "one_time_cost_base": float(totals["one_time"]["costs"]["base"]),
        "net_three_year_base": float(totals["phasing"]["net_three_year"]["base"]),
    }


def scenario_table(
    results: Results,
    scenarios: Mapping[str, Mapping[str, Any]] | None = None,
    view: str | None = None,
) -> pd.DataFrame:
    """Totals under the current assumptions, the shipped presets and any saved scenarios.

    ``scenarios`` maps a name to a complete set of assumptions (a named copy,
    PRD 6.7). Recurring and one-time figures sit in separate columns.
    """
    resolve_view(results, view)
    cache = results.cached_synergy()
    rows = [_scenario_row(CURRENT, results.totals)]
    named = {name: preset(results.assumptions) for name, preset in SCENARIOS.items()}
    for name, assumptions in {**named, **(scenarios or {})}.items():
        rows.append(_scenario_row(name, evaluate(cache, assumptions).totals))
    return pd.DataFrame(rows)


def sensitivity_curves(results: Results, view: str | None = None) -> dict[str, Any] | Unavailable:
    """The base case against the vendor and item automatic thresholds (PRD 4.7; demo only)."""
    resolve_view(results, view)
    if results.sensitivity is None:
        return Unavailable(results.meta.get("switched_off", {}).get("sensitivity", ""))
    data = results.sensitivity
    return {
        name: pd.DataFrame(data["curves"][name]) for name in ("vendor_auto", "item_auto_cosine")
    } | {"current": dict(data["current"])}
