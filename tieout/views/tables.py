"""Data, matching and method views: data quality, staged counts, scorecard, limits."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pandas as pd

from tieout.views.common import Unavailable, money, percent, resolve_view, thousands

if TYPE_CHECKING:
    from tieout.results import Results

__all__ = [
    "CANNOT_SEE",
    "SCORECARD_METRICS",
    "data_quality_summary",
    "matching_counts",
    "scorecard_table",
]

#: PRD 6.10: the fixed "What this analysis cannot see" panel (screen, deck and workbook).
CANNOT_SEE: tuple[str, ...] = (
    "Rebates, credits and off-invoice discounts",
    "Specification, quality and lead-time differences between apparently identical items",
    "Freight and delivery terms, unless incoterms are supplied",
    "Contract clauses such as minimum volumes, exclusivity and change of control",
    "Index-linked prices caught at different dates",
    "Supplier capacity and willingness to serve the combined volume",
    "Services and other spend with neither an item code nor an MPN, beyond vendor and "
    "category totals",
    "Corporate parent links not supplied in the parent table",
)
#: Scorecard rows in display order: metric key -> plain label.
SCORECARD_METRICS: dict[str, str] = {
    "vendor_precision": "Vendor precision",
    "vendor_recall": "Vendor recall",
    "item_precision": "Item precision",
    "item_recall": "Item recall",
    "planted_savings_recall": "Planted-savings recall",
    "false_savings_rate": "False-savings rate",
    "unit_error_catch_rate": "Unit-error catch rate",
}
_SEVERITY_ORDER = {"blocking": 0, "warning": 1, "info": 2}


def data_quality_summary(results: Results, view: str | None = None) -> dict[str, Any]:
    """What was received and its state (Data screen): spend, coverage and findings.

    Findings are sorted blocking first, then by dollars affected.
    """
    resolve_view(results, view)
    meta = results.meta
    findings = results.data_quality.copy()
    if not findings.empty:
        findings["order"] = findings["severity"].map(_SEVERITY_ORDER).fillna(3)
        findings = findings.sort_values(
            ["order", "amount", "rule", "company"],
            ascending=[True, False, True, True],
            kind="mergesort",
        ).drop(columns="order")
        findings["amount_text"] = [thousands(a) for a in findings["amount"]]
    spend = meta["in_scope_spend"]
    no_item = meta["not_item_addressable"]
    return {
        "rows": dict(meta["rows"]),
        "in_scope_spend": {k: float(v) for k, v in spend.items()},
        "period": dict(meta.get("period") or {}),
        "scaled": bool(meta.get("scaled", False)),
        "not_item_addressable": {
            "amount": float(no_item["amount"]["total"]),
            "share": float(no_item["share"]["total"]),
            "text": (
                f"{money(no_item['amount']['total'])} ({percent(no_item['share']['total'])}) "
                "of spend has neither an item code nor an MPN"
            ),
        },
        "unmapped_spend": float(meta["unmapped_spend"]["total"]),
        "findings": findings.reset_index(drop=True),
        "switched_off": dict(meta.get("switched_off", {})),
    }


def _stage_text(counts: dict[str, int], steps: list[tuple[str, str]]) -> str:
    return " → ".join(f"{counts[key]:,} {words}" for key, words in steps)


def matching_counts(results: Results, view: str | None = None) -> dict[str, Any]:
    """Staged matching counts (PRD 6.13) with tiers and the pending review count."""
    resolve_view(results, view)
    matching = results.meta["matching"]
    vendors, items = matching["vendors"], matching["items"]
    return {
        "vendors": {
            **vendors,
            "text": _stage_text(
                vendors,
                [
                    ("records", "vendor records"),
                    ("after_normalisation", "after normalisation"),
                    ("legal_entities", "after matching"),
                ],
            ),
        },
        "items": {
            **items,
            "text": _stage_text(
                items,
                [
                    ("records", "item records"),
                    ("matchable_records", "in mapped categories"),
                    ("canonical_items", "canonical items"),
                ],
            ),
        },
    }


def scorecard_table(results: Results, view: str | None = None) -> pd.DataFrame | Unavailable:
    """Accuracy on the held-out seed, tool against the naive baseline (PRD 4.7; demo only).

    The scorecard stays in the integration-office view (PRD 6.9).
    """
    resolve_view(results, view)
    card = results.scorecard
    if card is None:
        return Unavailable(results.meta.get("switched_off", {}).get("scorecard", ""))
    tool, baseline = card["tool"], card["baseline"]
    rows = []
    for key, label in SCORECARD_METRICS.items():
        target = card.get("targets", {}).get(key)
        gate = card.get("gates", {}).get(key)
        rows.append(
            {
                "metric": key,
                "label": label,
                "tool": tool["held_out"].get(key),
                "baseline": baseline["held_out"].get(key),
                "tool_tuning_mean": tool["tuning_mean"].get(key),
                "baseline_tuning_mean": baseline["tuning_mean"].get(key),
                "target": f"{target['direction']} {target['bound']:g}" if target else "",
                "passed": None if gate is None else bool(gate["passed"]),
            }
        )
    return pd.DataFrame(rows)
