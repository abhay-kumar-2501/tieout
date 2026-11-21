"""The answer and how sure we are: headline, Overview figures, bridge and waterfall.

Every money value is returned as a number next to its display text, and with
the ``figure_id`` (a dotted path in ``totals``, or a trace node) that
:func:`tieout.views.trace.trace_for` opens.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd

from tieout.synergy.lever1 import STEP_NAMES
from tieout.views.common import (
    MASKED,
    NOT_IN_VIEW,
    Unavailable,
    category_label,
    category_labels,
    item_labels,
    money,
    money_range,
    parent_labels,
    percent,
    resolve_view,
    thousands,
)

if TYPE_CHECKING:
    from tieout.results import Results

__all__ = [
    "BRIDGE_COLUMNS",
    "HEADLINE_MAX_CHARS",
    "WATERFALL_COLUMNS",
    "bridge",
    "confidence_strip",
    "headline",
    "lever1_items",
    "opportunity_labels",
    "overview_figures",
    "reconciliation_text",
    "refused_items",
    "synergy_waterfall",
    "worth_a_look",
]

HEADLINE_MAX_CHARS = 120
BRIDGE_COLUMNS = [
    "step",
    "label",
    "kind",
    "amount",
    "bar_base",
    "bar_height",
    "level",
    "low",
    "high",
    "items",
    "text",
    "figure_id",
]
WATERFALL_COLUMNS = [
    "label",
    "kind",
    "amount",
    "bar_base",
    "bar_height",
    "level",
    "low",
    "high",
    "text",
    "figure_id",
]


def _cases(node: dict[str, Any]) -> tuple[float, float, float]:
    return float(node["low"]), float(node["base"]), float(node["high"])


def headline(results: Results, view: str | None = None) -> dict[str, Any]:
    """The finding headline (PRD 6.4, 7.2) with the figures behind it.

    "{L}–{H} of run-rate savings is defensible; the naive figure of {N} is
    not." When the naive figure is not above the top of the range: "The naive
    figure of {N} holds up: {L}–{H} is defensible". A zero or missing value's
    sentence is omitted. At most 120 characters.
    """
    resolve_view(results, view)
    low, base, high = _cases(results.totals["recurring"])
    naive = float(results.totals["lever1"]["naive"])
    span, naive_text = money_range(low, high), money(naive)
    if high > 0 and naive > high:
        text = f"{span} of run-rate savings is defensible; the naive figure of {naive_text} is not."
    elif high > 0 and naive > 0:
        text = f"The naive figure of {naive_text} holds up: {span} is defensible"
    elif high > 0:
        text = f"{span} of run-rate savings is defensible."
    elif naive > 0:
        text = f"None of the naive figure of {naive_text} is defensible."
    else:
        text = "No run-rate saving was found."
    if len(text) > HEADLINE_MAX_CHARS:  # numbers are short; a guard, not an expected path
        text = text[: HEADLINE_MAX_CHARS - 1] + "…"
    return {
        "text": text,
        "range_text": span,
        "low": low,
        "base": base,
        "high": high,
        "naive": naive,
        "figure_id": "recurring.base",
    }


def _figure(
    key: str, label: str, kind: str, node: dict[str, Any], figure: str, explanation: str
) -> dict[str, Any]:
    low, base, high = _cases(node)
    return {
        "id": key,
        "label": label,
        "kind": kind,
        "available": True,
        "low": low,
        "base": base,
        "high": high,
        "text": money_range(low, high),
        "base_text": money(base),
        "explanation": explanation,
        "figure_id": figure,
    }


def overview_figures(results: Results, view: str | None = None) -> list[dict[str, Any]]:
    """The three Overview figures: run-rate saving | one-time cash release, one-time cost.

    ``kind`` separates the recurring figure from the two one-time figures,
    which are never added to it (PRD 5.1, 6.4).
    """
    resolve_view(results, view)
    totals = results.totals
    run_rate = _figure(
        "run_rate",
        "Run-rate P&L saving",
        "recurring",
        totals["recurring"],
        "recurring.base",
        "Price harmonisation plus volume consolidation each year once implemented, low to high.",
    )
    cash = _figure(
        "cash",
        "One-time cash release",
        "one_time",
        totals["one_time"]["cash"],
        "one_time.cash.base",
        "Working capital released once by harmonising payment terms; not a saving.",
    )
    if not totals["checks"]["lever3_enabled"]:
        cash |= {"available": False, "explanation": str(totals["checks"]["lever3_message"])}
    cost = _figure(
        "cost",
        "One-time cost",
        "one_time",
        totals["one_time"]["costs"],
        "one_time.costs.base",
        "Qualifying and onboarding vendors that receive spend, plus 1% of the spend moved.",
    )
    return [run_rate, cash, cost]


def _stacked(rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Bars with an invisible base series (PRD 9.3): totals stand on zero, steps float."""
    level = 0.0
    for row in rows:
        amount = row["amount"]
        if row["kind"] == "total":
            level = amount
            row["bar_base"], row["bar_height"] = min(0.0, amount), abs(amount)
        else:
            end = level + amount
            row["bar_base"], row["bar_height"] = min(level, end), abs(amount)
            level = end
        row["level"] = level
        row.setdefault("low", float("nan"))
        row.setdefault("high", float("nan"))
        row["text"] = thousands(amount)
    return pd.DataFrame(rows)


def bridge(results: Results, view: str | None = None) -> pd.DataFrame:
    """Naive figure -> seven removal steps -> lever 1 -> + lever 2 -> defensible run rate.

    One row per bar (PRD 5.2 "Bridge chart"): ``amount`` is signed (removals
    negative), ``bar_base`` / ``bar_height`` draw it as a stacked bar, and the
    final bar carries the recurring ``low`` / ``high`` range. ``items`` counts
    the items behind a removal step.
    """
    resolve_view(results, view)
    totals = results.totals
    lever1 = totals["lever1"]
    rows: list[dict[str, Any]] = [
        {
            "step": 0,
            "label": "Naive figure",
            "kind": "total",
            "amount": float(lever1["naive"]),
            "items": len(results.trace.get("bridge:naive", [])),
            "figure_id": "lever1.naive",
        }
    ]
    for i, name in enumerate(STEP_NAMES, start=1):
        rows.append(
            {
                "step": i,
                "label": name,
                "kind": "decrease",
                "amount": -float(lever1["bridge"][f"step_{i}"]),
                "items": len(results.trace.get(f"bridge:step:{i}", [])),
                "figure_id": f"lever1.bridge.step_{i}",
            }
        )
    low, base, high = _cases(totals["recurring"])
    rows += [
        {
            "step": len(STEP_NAMES) + 1,
            "label": "Defensible price harmonisation (lever 1)",
            "kind": "total",
            "amount": float(totals["levers"]["lever1"]["base"]),
            "items": 0,
            "figure_id": "levers.lever1.base",
        },
        {
            "step": len(STEP_NAMES) + 2,
            "label": "+ Volume consolidation (lever 2)",
            "kind": "increase",
            "amount": float(totals["levers"]["lever2"]["base"]),
            "items": 0,
            "figure_id": "levers.lever2.base",
        },
        {
            "step": len(STEP_NAMES) + 3,
            "label": "Defensible run-rate saving",
            "kind": "total",
            "amount": base,
            "low": low,
            "high": high,
            "items": 0,
            "figure_id": "recurring.base",
        },
    ]
    return _stacked(rows)[BRIDGE_COLUMNS]


REFUSED_COLUMNS = [
    "canonical_item_id",
    "item",
    "category",
    "groups",
    "naive_gap",
    "amount_removed",
    "text",
    "reason",
    "figure_id",
    "measure",
]
REFUSED_MASKED_COLUMNS = ["category", "items", "amount_removed", "text", "figure_id", "measure"]


def refused_items(results: Results, step: int, view: str | None = None) -> pd.DataFrame:
    """What bridge step ``step`` (1-7) removed: the filterable list behind its bar (PRD 5.2).

    Clean team: one row per canonical item, largest removal first, with its
    category, buying groups, naive gap, the amount the step removed, the
    reason (step 1: the unit-flag message; otherwise the step's name), and
    the trace node and measure that open its working. Masked: aggregated to
    category ("Other" merged), with no item and no trace link (PRD 6.9).
    The amounts re-sum to the step's bar.
    """
    mode = resolve_view(results, view)
    if step not in range(1, len(STEP_NAMES) + 1):
        raise ValueError(f"step must be 1-{len(STEP_NAMES)}, got {step!r}")
    detail = results.bridge_detail
    rows = detail[detail["step"] == step] if not detail.empty else detail
    columns = REFUSED_MASKED_COLUMNS if mode == MASKED else REFUSED_COLUMNS
    if rows.empty:
        return pd.DataFrame(columns=columns)
    l2 = results.price_groups.set_index("group_id")["l2_code"]
    labels = category_labels(results, mode)
    rows = rows.assign(
        category=[category_label(labels, l2.get(g)) for g in rows["group_id"]],
    )
    measure = f"raw_{step}"
    if mode == MASKED:
        frame = (
            rows.groupby("category", sort=True)
            .agg(
                items=("canonical_item_id", "nunique"),
                amount_removed=("amount_removed", "sum"),
            )
            .reset_index()
        )
        frame["figure_id"], frame["measure"] = None, None
    else:
        frame = (
            rows.groupby("canonical_item_id", sort=True)
            .agg(
                category=("category", "first"),
                groups=("group_id", "nunique"),
                naive_gap=("naive_gap", "sum"),
                amount_removed=("amount_removed", "sum"),
            )
            .reset_index()
        )
        names = item_labels(results)
        frame["item"] = [names.get(i, i) for i in frame["canonical_item_id"]]
        reasons: dict[str, str] = {}
        if step == 1:
            queue = results.review_queue
            flags = queue[queue["type"] == "unit_flag"].dropna(subset=["canonical_item_id"])
            reasons = dict(
                zip(flags["canonical_item_id"], flags["message"].fillna(""), strict=True)
            )
        default = _UNCONVERTED if step == 1 else STEP_NAMES[step - 1]
        frame["reason"] = [reasons.get(i) or default for i in frame["canonical_item_id"]]
        frame["figure_id"] = "item:" + frame["canonical_item_id"].astype(str)
        frame["measure"] = measure
    frame = frame[frame["amount_removed"] != 0]
    frame = frame.assign(text=[thousands(v) for v in frame["amount_removed"]])
    key = "category" if mode == MASKED else "canonical_item_id"
    frame = frame.sort_values(["amount_removed", key], ascending=[False, True], kind="mergesort")
    return frame[columns].reset_index(drop=True)


def lever1_items(results: Results, view: str | None = None) -> pd.DataFrame | Unavailable:
    """Canonical items with a lever-1 base saving, largest first (price dispersion picker).

    Clean team only: item-level rows are not shown in the integration-office view.
    """
    mode = resolve_view(results, view)
    if mode == MASKED:
        return NOT_IN_VIEW
    opps = results.opportunities
    lever1 = opps[(opps["lever"] == 1) & (opps["status"] == "in_range") & (opps["base"] > 0)]
    columns = ["canonical_item_id", "item", "category", "base", "text"]
    if lever1.empty:
        return pd.DataFrame(columns=columns)
    frame = (
        lever1.groupby("canonical_item_id", sort=True)
        .agg(l2_code=("l2_code", "first"), base=("base", "sum"))
        .reset_index()
    )
    names, labels = item_labels(results), category_labels(results, mode)
    frame["item"] = [names.get(i, i) for i in frame["canonical_item_id"]]
    frame["category"] = [category_label(labels, c) for c in frame["l2_code"]]
    frame["text"] = [thousands(v) for v in frame["base"]]
    frame = frame.sort_values(
        ["base", "canonical_item_id"], ascending=[False, True], kind="mergesort"
    )
    return frame[columns].reset_index(drop=True)


def synergy_waterfall(results: Results, view: str | None = None) -> pd.DataFrame:
    """Baseline spend -> lever 1 -> lever 2 -> net run-rate spend (PRD 6.8; recurring only)."""
    resolve_view(results, view)
    totals = results.totals
    net = totals["spend"]["net_run_rate"]
    rows: list[dict[str, Any]] = [
        {
            "label": "In-scope spend (baseline)",
            "kind": "total",
            "amount": float(totals["spend"]["baseline"]),
            "figure_id": "spend.baseline",
        },
        {
            "label": "Price harmonisation (lever 1)",
            "kind": "decrease",
            "amount": -float(totals["levers"]["lever1"]["base"]),
            "figure_id": "levers.lever1.base",
        },
        {
            "label": "Volume consolidation (lever 2)",
            "kind": "decrease",
            "amount": -float(totals["levers"]["lever2"]["base"]),
            "figure_id": "levers.lever2.base",
        },
        {
            "label": "Net run-rate spend",
            "kind": "total",
            "amount": float(net["base"]),
            # The high case saves most, so it leaves the lowest spend.
            "low": float(net["high"]),
            "high": float(net["low"]),
            "figure_id": "spend.net_run_rate.base",
        },
    ]
    return _stacked(rows)[WATERFALL_COLUMNS]


def confidence_strip(results: Results, view: str | None = None) -> dict[str, Any]:
    """Share of the lever-1 base case resting on tier A vs tier B matches, and pending dollars."""
    resolve_view(results, view)
    lever1 = results.totals["lever1"]
    tier_a, tier_b = float(lever1["tier_a"]["base"]), float(lever1["tier_b"]["base"])
    matched = tier_a + tier_b
    share_a = tier_a / matched if matched > 0 else 0.0
    share_b = tier_b / matched if matched > 0 else 0.0
    pending = float(lever1["upside_pending_review"])
    return {
        "tier_a": tier_a,
        "tier_b": tier_b,
        "share_a": share_a,
        "share_b": share_b,
        "pending_review": pending,
        "text": (
            f"{percent(share_a)} of the price-harmonisation base case rests on tier A matches "
            f"and {percent(share_b)} on tier B; {thousands(pending)} more is pending review."
        ),
        "figure_ids": {
            "tier_a": "lever1.tier_a.base",
            "tier_b": "lever1.tier_b.base",
            "pending_review": "lever1.upside_pending_review",
        },
    }


def _largest_lever1(results: Results, view: str) -> dict[str, Any]:
    opps = results.opportunities
    lever1 = opps[(opps["lever"] == 1) & (opps["status"] == "in_range")]
    card: dict[str, Any] = {"id": "largest_lever1", "title": "Largest price-harmonisation saving"}
    if lever1.empty:
        return card | {"available": False, "text": "No price-harmonisation opportunity was found."}
    if view == MASKED:
        labels = category_labels(results, view)
        by_category = (
            lever1.assign(category=[category_label(labels, c) for c in lever1["l2_code"]])
            .groupby("category", sort=True)["base"]
            .sum()
        )
        top = by_category.sort_values(ascending=False, kind="mergesort")
        subject, amount = str(top.index[0]), float(top.iloc[0])
        codes = sorted(c for c, label in labels.items() if label == subject)
        figure = f"lever:1:cat:{codes[0]}" if len(codes) == 1 else "levers.lever1.base"
    else:
        row = lever1.sort_values(
            ["base", "opportunity_id"], ascending=[False, True], kind="mergesort"
        ).iloc[0]
        subject = item_labels(results).get(row["canonical_item_id"], row["canonical_item_id"])
        amount, figure = float(row["base"]), str(row["opportunity_id"])
    return card | {
        "available": True,
        "subject": subject,
        "amount": amount,
        "text": f"{subject}: {thousands(amount)} a year in the base case.",
        "figure_id": figure,
    }


_UNCONVERTED = "Unconverted pack units: the price is per pack on one side, not a saving"


def _largest_unit_trap(results: Results, view: str) -> dict[str, Any]:
    detail = results.bridge_detail
    card: dict[str, Any] = {"id": "unit_trap", "title": "Largest unit trap removed"}
    step1 = detail[detail["step"] == 1] if not detail.empty else detail
    if step1.empty:
        return card | {"available": False, "text": "No unit-of-measure problem was removed."}
    removed = step1.groupby("canonical_item_id", sort=True)["amount_removed"].sum()
    removed = removed.sort_values(ascending=False, kind="mergesort")
    item, amount = str(removed.index[0]), float(removed.iloc[0])
    queue = results.review_queue
    flag = queue[(queue["type"] == "unit_flag") & (queue["canonical_item_id"] == item)]
    message = str(flag["message"].iloc[0]) if not flag.empty else _UNCONVERTED
    if view == MASKED:
        l2 = step1.loc[step1["canonical_item_id"] == item, "group_id"]
        code = results.price_groups.set_index("group_id").loc[l2.iloc[0], "l2_code"]
        subject = category_label(category_labels(results, view), code)
        figure = "lever1.bridge.step_1"
    else:
        subject = item_labels(results).get(item, item)
        figure = f"item:{item}"
    return card | {
        "available": True,
        "subject": subject,
        "amount": amount,
        "message": message,
        "text": f"{subject}: {message}. {thousands(amount)} of naive gap removed.",
        "figure_id": figure,
        "measure": "raw_1",
    }


def _largest_forgone(results: Results, view: str) -> dict[str, Any]:
    risk = results.category_risk
    card: dict[str, Any] = {
        "id": "savings_forgone",
        "title": "Largest saving given up for resilience",
    }
    per_category = (
        risk.drop_duplicates("l2_code")[["l2_code", "savings_forgone"]] if not risk.empty else risk
    )
    if per_category.empty or float(per_category["savings_forgone"].max()) <= 0:
        return card | {"available": False, "text": "No concentration cap limits consolidation."}
    labels = category_labels(results, view)
    grouped = (
        per_category.assign(category=[category_label(labels, c) for c in per_category["l2_code"]])
        .groupby("category", sort=True)["savings_forgone"]
        .sum()
        .sort_values(ascending=False, kind="mergesort")
    )
    subject, amount = str(grouped.index[0]), float(grouped.iloc[0])
    codes = sorted(c for c, label in labels.items() if label == subject)
    return card | {
        "available": True,
        "subject": subject,
        "amount": amount,
        "text": f"{subject}: the concentration cap gives up {thousands(amount)} a year.",
        "figure_id": f"L2:{codes[0]}" if len(codes) == 1 else "lever2.savings_forgone",
        "measure": "forgone",
    }


def worth_a_look(results: Results, view: str | None = None) -> list[dict[str, Any]]:
    """The three Overview cards (PRD 6.4), always these, in this order.

    The largest lever-1 opportunity by base saving; the unit trap with the
    largest naive gap removed; the category with the largest savings forgone.
    Masked, each is named by its category, never by item.
    """
    mode = resolve_view(results, view)
    return [
        _largest_lever1(results, mode),
        _largest_unit_trap(results, mode),
        _largest_forgone(results, mode),
    ]


_LEVER_ACTIONS = {1: "Price harmonisation", 2: "Volume consolidation", 3: "Payment terms"}


def opportunity_labels(results: Results, opps: pd.DataFrame, view: str) -> list[str]:
    """How each opportunity is named: item, category or vendor; masked, lever and category."""
    categories = category_labels(results, view)
    items = item_labels(results) if view != MASKED else {}
    parents = parent_labels(results, view) if view != MASKED else {}
    out = []
    for lever, l2, item, parent in zip(
        opps["lever"], opps["l2_code"], opps["canonical_item_id"], opps["parent_id"], strict=True
    ):
        category = category_label(categories, l2)
        if view == MASKED:
            out.append(_LEVER_ACTIONS[lever] + (f", {category}" if lever != 3 else ""))
        elif lever == 1:
            out.append(items.get(item, str(item)))
        elif lever == 2:
            out.append(f"Consolidate {category}")
        else:
            out.append(f"Payment terms with {parents.get(parent, parent)}")
    return out


def reconciliation_text(results: Results, view: str | None = None) -> dict[str, Any]:
    """The base case against the two top-down reference bands (PRD 5.8), as sentences.

    Outside either band, the three opportunities with the largest base saving
    are listed (masked: by lever and category, with no trace link).
    """
    mode = resolve_view(results, view)
    rec = results.totals["reconciliation"]
    base = float(results.totals["recurring"]["base"])
    names = {"total_spend": "total in-scope spend", "addressable_spend": "addressable spend"}
    lines = []
    for key, name in names.items():
        check = rec[key]
        band = f"{percent(check['band_low'])}–{percent(check['band_high'])}"
        if check["within"]:
            where = f"within the {band} reference band"
        elif check["share"] < check["band_low"]:
            where = f"below the {band} reference band"
        else:
            where = f"above the {band} reference band"
        lines.append(
            f"The base case of {money(base)} is {percent(check['share'])} of {name}, {where}."
        )
    opps = results.opportunities.set_index("opportunity_id", drop=False)
    chosen = opps.loc[list(rec["largest_opportunities"])]
    largest = [
        {
            "label": label,
            "base": float(base),
            "figure_id": None if mode == MASKED else opp,
        }
        for opp, base, label in zip(
            chosen["opportunity_id"],
            chosen["base"],
            opportunity_labels(results, chosen, mode),
            strict=True,
        )
    ]
    return {
        "lines": lines,
        "outside_band": bool(rec["outside_band"]),
        "largest": largest,
        "base": base,
        "total_spend": float(rec["total_spend"]["spend"]),
        "addressable_spend": float(rec["addressable_spend"]["spend"]),
    }
