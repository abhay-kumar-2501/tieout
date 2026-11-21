"""The "Show working" panel (PRD 6.6): any figure down to source rows.

``trace_for(results, figure_id)`` opens one level of the chain
``total -> lever -> category -> opportunity -> item or vendor -> source rows``:
the figure's value, its components (each re-summed from its own rows) and
every source row under it, exactly as received with file name and row number
next to its normalised form, plus a tab-separated "copy as table" block.

Masked, the panel stops at category level: components below a category and
all source rows are "not available in this view".
"""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING, Any

import pandas as pd

from tieout.synergy.trace import figure_value, leaf_lines, resum
from tieout.views.common import (
    MASKED,
    NOT_IN_VIEW,
    Unavailable,
    category_label,
    category_labels,
    item_labels,
    parent_labels,
    resolve_view,
)

if TYPE_CHECKING:
    from tieout.results import Results

__all__ = ["NORMALISED_COLUMNS", "SOURCE_COLUMNS", "node_label", "trace_for"]

#: Source row columns exactly as received (PRD 3.1), after the file name and row number.
SOURCE_COLUMNS = [
    "source_file",
    "source_row",
    "company",
    "site",
    "doc_date",
    "vendor_id",
    "vendor_name",
    "item_code",
    "mpn",
    "item_description",
    "category_native",
    "uom",
    "pack_qty",
    "quantity",
    "unit_price",
    "line_amount",
    "currency",
    "contract_end_date",
    "incoterm",
    "payment_terms_days",
]
#: The same row's normalised form.
NORMALISED_COLUMNS = [
    "line_id",
    "amount",
    "quantity_ann",
    "l2_code",
    "conv_status",
    "base_unit",
    "qty_base",
    "price_base",
    "price_exclusion",
    "legal_entity_id",
    "parent_id",
    "canonical_item_id",
]
#: Measure used for a node that is not itself a ``totals`` figure, by node prefix.
_NODE_MEASURES = (
    ("L1:", "base"),
    ("grp:", "base"),
    ("item:", "base"),
    ("lever:1", "base"),
    ("L2:", "l2_base"),
    ("lever:2", "l2_base"),
    ("L3:", "l3_base"),
    ("vgrp:", "l3_base"),
    ("lever:3", "l3_base"),
    ("event:", "cost_base"),
    ("one_time:costs", "cost_base"),
    ("spend:", "spend"),
    ("total:recurring", "recurring_base"),
)
#: Nodes at or above category level, which the masked view may open.
_CATEGORY_LEVEL = (
    "total:recurring",
    "lever:1",
    "lever:1:cat:",
    "lever:2",
    "L2:",
    "spend:",
    "one_time:costs",
    "phasing:",
)
#: Each lever's measure, by case, when it is a component of total recurring.
_LEVER_MEASURES = {"lever:1": "{case}", "lever:2": "l2_{case}"}
#: Nodes that combine totals rather than split one: no components, rows only.
_NO_COMPONENTS = ("phasing:", "spend:net")
_LEVER_NAMES = {
    "lever:1": "Price harmonisation (lever 1)",
    "lever:2": "Volume consolidation (lever 2)",
    "lever:3": "Payment terms (lever 3)",
    "total:recurring": "Run-rate saving (levers 1 and 2)",
    "one_time:costs": "One-time costs",
    "spend:baseline": "In-scope spend",
    "spend:addressable": "Addressable spend",
    "spend:net": "Net run-rate spend",
}


def _measure_for(node: str) -> str:
    for prefix, measure in _NODE_MEASURES:
        if node.startswith(prefix):
            return measure
    return "base"


def _category_level(node: str) -> bool:
    if node.startswith("lever:1:") and not node.startswith("lever:1:cat:"):
        return False  # tiers, upside and internal variance list items
    return node.startswith(_CATEGORY_LEVEL)


class _Labels:
    """Display names for one run and view mode; each table is built on first use."""

    def __init__(self, results: Results, mode: str) -> None:
        self._results, self._mode = results, mode

    @cached_property
    def categories(self) -> dict[str, str]:
        return category_labels(self._results, self._mode)

    @cached_property
    def parents(self) -> dict[str, str]:
        return parent_labels(self._results, self._mode)

    @cached_property
    def items(self) -> dict[str, str]:
        return item_labels(self._results)

    @cached_property
    def rows(self) -> dict[str, str]:
        lines = self._results.lines
        names = lines["source_file"] + " row " + lines["source_row"].astype(int).astype(str)
        return dict(zip(lines["line_id"].tolist(), names.tolist(), strict=True))

    def __call__(self, node: str) -> str:
        if node in _LEVER_NAMES:
            return _LEVER_NAMES[node]
        kind, _, rest = node.partition(":")
        if node.startswith("lever:1:cat:"):
            return category_label(self.categories, node.removeprefix("lever:1:cat:"))
        if kind == "L2":
            return category_label(self.categories, rest)
        if kind == "L1":
            item, _, change = rest.partition(":")
            return f"{self.items.get(item, item)} ({change.replace('_', ' ')})"
        if kind == "item":
            return self.items.get(rest, rest)
        if kind == "grp":
            _, company, site, parent = rest.split("|", 3)
            return f"{company} \u00b7 {site} \u00b7 {self.parents.get(parent, parent)}"
        if kind == "L3":
            return self.parents.get(rest, rest)
        if kind == "vgrp":
            company, parent = rest.split("|", 1)
            return f"{company} \u00b7 {self.parents.get(parent, parent)}"
        if kind == "event":
            company, l2, destination = rest.split("|", 2)
            target = self.parents.get(destination, destination)
            return f"{company} \u00b7 {category_label(self.categories, l2)} \u2192 {target}"
        return self.rows.get(node, node)


def node_label(results: Results, node: str, view: str | None = None) -> str:
    """A trace node in words: category, item, buying group, vendor or source row."""
    return _Labels(results, resolve_view(results, view))(node)


def _child_measure(measure: str, child: str) -> str:
    """A lever's own measure under a composite total (``recurring_base`` -> ``l2_base``)."""
    case = measure.rsplit("_", 1)[-1]
    if measure.startswith("recurring_") and child in _LEVER_MEASURES:
        return _LEVER_MEASURES[child].format(case=case)
    return measure


def _components(
    results: Results, node: str, measure: str, mode: str, labels: _Labels
) -> pd.DataFrame | Unavailable:
    """Child nodes with their re-summed amounts, largest first (zero rows left out).

    Nodes whose children do not split the figure (phasing and net spend, which
    combine totals) list source rows only.
    """
    index = results.trace_index
    if node.startswith(_NO_COMPONENTS):
        return pd.DataFrame(columns=["node", "label", "amount"])
    kids = [k for k in results.trace.get(node, []) if k in results.trace]
    if mode == MASKED and any(not _category_level(k) for k in kids):
        return NOT_IN_VIEW
    frame = pd.DataFrame(
        {
            "node": kids,
            "label": [labels(k) for k in kids],
            "amount": [resum(index, k, _child_measure(measure, k)) for k in kids],
        }
    )
    frame = frame[frame["amount"] != 0]
    if mode == MASKED and not frame.empty:  # merged categories show as one "Other" row
        frame = frame.groupby("label", as_index=False, sort=False).agg(
            node=("node", lambda n: n.iloc[0] if len(n) == 1 else None), amount=("amount", "sum")
        )[["node", "label", "amount"]]
    return frame.sort_values(
        ["amount", "label"], ascending=[False, True], kind="mergesort"
    ).reset_index(drop=True)


def _rows(results: Results, node: str, measure: str) -> pd.DataFrame:
    """Every source row under ``node`` with a non-zero contribution to ``measure``."""
    ids = [leaf for leaf in leaf_lines(results.trace_index, node) if leaf != node]
    amounts = results.trace_amounts[measure].reindex(ids).fillna(0.0)
    amounts = amounts[amounts != 0]
    lines = results.lines.set_index("line_id", drop=False).loc[amounts.index]
    columns = [c for c in SOURCE_COLUMNS if c in lines.columns]
    normalised = [c for c in NORMALISED_COLUMNS if c in lines.columns]
    rows = pd.concat(
        [lines[columns], lines[normalised].add_prefix("normalised_")], axis=1
    ).reset_index(drop=True)
    rows["contribution"] = amounts.to_numpy()
    return rows


def trace_for(
    results: Results, figure_id: str, measure: str | None = None, view: str | None = None
) -> dict[str, Any] | Unavailable:
    """Open ``figure_id`` (a dotted ``totals`` path or a trace node) one level down.

    Returns the value, ``components`` (child nodes with labels and re-summed
    amounts; empty when the children are source rows), ``rows`` (source rows
    as received next to their normalised form, with each row's contribution)
    and ``copy_table`` (the rows as tab-separated text). The rows re-sum to
    the value within $0.01 (PRD M2).
    """
    mode = resolve_view(results, view)
    if figure_id in results.trace_figures:
        node, default = results.trace_figures[figure_id]
        measure = measure or default
        value = figure_value(results.totals, figure_id)
    elif figure_id in results.trace:
        node = figure_id
        measure = measure or _measure_for(node)
        value = resum(results.trace_index, node, measure)
    else:
        return Unavailable(f"No working is recorded for {figure_id}.")
    if mode == MASKED and not _category_level(node):
        return NOT_IN_VIEW
    labels = _Labels(results, mode)
    rows: pd.DataFrame | Unavailable
    if mode == MASKED:
        rows, copy_table = NOT_IN_VIEW, ""
    else:
        rows = _rows(results, node, measure)
        copy_table = rows.to_csv(sep="\t", index=False)
    return {
        "figure_id": figure_id,
        "node": node,
        "measure": measure,
        "label": labels(node),
        "value": value,
        "components": _components(results, node, measure, mode, labels),
        "rows": rows,
        "copy_table": copy_table,
    }
