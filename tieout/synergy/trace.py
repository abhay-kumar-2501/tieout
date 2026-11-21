"""The trace index: every figure down to source rows (PRD 6.6, M2 exit criterion).

**What a source row contributes.** A saving is not a line amount, so each
figure is spread over the lines it rests on. For one ``lever1`` evaluation, a
line ``l`` in buying group ``g`` contributes::

    contribution[l] = contribution[g] * w[l]
    w[l] = qty[l] / sum of qty over the group's lines in the comparison

that is, the group's gap x the line's quantity share x the multipliers
(``a``, ``pi1``). The quantity is the line's naive quantity while filter 1 is
off and its base-unit quantity once it is on. With filter 6 on, only lines
whose contract is open within the horizon share the group's dollars, since
``a[k,g]`` is exactly their quantity share. Credit lines carry negative
contributions, which is how netting shows. Weights sum to one in every group
with a non-zero contribution, so the lines re-sum to the group and to every
figure built from groups.

A bridge step's line contribution is the difference of the two evaluations
it compares; a shown step carries the lines of every raw step that lands in
it (see :mod:`tieout.synergy.bridge`).

**The index.** ``children`` maps a node to child nodes or ``line_id`` s::

    total:recurring -> lever:1 -> lever:1:cat:{l2} -> L1:{item}:{change}
                    -> grp:{item}|{company}|{site}|{parent} -> line_id

plus ``lever:1:tier:{A,B}``, ``lever:1:upside``, ``lever:1:internal``,
``bridge:naive``, ``bridge:raw:{i}`` and ``bridge:step:{i}``, which list
``item:{id}`` nodes. ``line_amounts`` holds each line's contribution per
measure, and ``figures`` maps each dotted path in ``totals`` to its node and
measure. :func:`resum` recomputes a figure from its traced lines.

Levers 2 and 3, spend, one-time costs and phasing add their own nodes and
measures over every line through :func:`extend_trace` (see
:mod:`tieout.synergy.assemble`); ``total:recurring`` then lists ``lever:1``
and ``lever:2``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from tieout.synergy.bridge import N_STEPS, Bridge
from tieout.synergy.lever1 import CASES, Lever1Inputs, Lever1Result
from tieout.synergy.opportunities import Evaluations

__all__ = [
    "LineIndex",
    "TraceIndex",
    "build_trace",
    "children_by",
    "extend_trace",
    "figure_value",
    "leaf_lines",
    "line_contributions",
    "resum",
]


@dataclass(frozen=True)
class LineIndex:
    """Line-level arrays aligned with the tagged lines (sorted by ``line_id``)."""

    line_id: np.ndarray
    group: np.ndarray
    naive_w: np.ndarray
    def_w: np.ndarray
    open: np.ndarray

    @property
    def in_comparison(self) -> np.ndarray:
        return (self.naive_w != 0) | (self.def_w != 0)


@dataclass(frozen=True)
class TraceIndex:
    """Parent id -> child ids down to ``line_id`` s, with per-line amounts per measure."""

    children: dict[str, list[str]]
    line_amounts: pd.DataFrame
    figures: dict[str, tuple[str, str]]


def line_contributions(inputs: Lever1Inputs, lines: LineIndex, result: Lever1Result) -> np.ndarray:
    """Each line's share of its group's contribution under ``result``'s filters."""
    g = inputs.groups
    if not result.filters.unit_errors:
        numerator, denominator = lines.naive_w, g["naive_qty"].to_numpy()
    elif result.filters.contract_lock_in:
        numerator, denominator = lines.def_w * lines.open, g["q_open"].to_numpy()
    else:
        numerator, denominator = lines.def_w, g["q"].to_numpy()
    per_line = denominator[lines.group]
    safe = np.where(per_line > 0, per_line, 1.0)
    weight = np.where(per_line > 0, numerator / safe, 0.0)
    return result.contribution[lines.group] * weight


def _line_amounts(
    inputs: Lever1Inputs, lines: LineIndex, bridge: Bridge, ev: Evaluations
) -> pd.DataFrame:
    figures = [line_contributions(inputs, lines, r) for r in bridge.results]
    raw = {f"raw_{i}": figures[i - 1] - figures[i] for i in range(1, N_STEPS + 1)}
    pending = inputs.items["pending"].to_numpy(dtype=bool)[inputs.item][lines.group]
    columns = {
        "naive": figures[0],
        **raw,
        **{
            f"step_{i}": sum((raw[f"raw_{j}"] for j in sources), np.zeros(len(lines.line_id)))
            for i, sources in enumerate(bridge.sources, start=1)
        },
        "gross": line_contributions(inputs, lines, ev.gross),
        **{case: line_contributions(inputs, lines, ev.cases[case]) for case in CASES},
        "upside": np.where(pending, line_contributions(inputs, lines, ev.upside), 0.0),
        "upside_gross": np.where(pending, line_contributions(inputs, lines, ev.upside_gross), 0.0),
        "internal": raw["raw_4"],
    }
    return pd.DataFrame(columns, index=pd.Index(lines.line_id, name="line_id"))


def _items_with(inputs: Lever1Inputs, values: np.ndarray) -> list[str]:
    totals = np.bincount(inputs.item, weights=np.abs(values), minlength=inputs.n_items)
    return [f"item:{i}" for i in inputs.items["canonical_item_id"].to_numpy()[totals > 0]]


def build_trace(
    inputs: Lever1Inputs,
    lines: LineIndex,
    bridge: Bridge,
    ev: Evaluations,
    opportunities: pd.DataFrame,
    opportunity: np.ndarray,
) -> TraceIndex:
    """Build the index for the lever-1 totals and every opportunity."""
    g = inputs.groups
    group_nodes = ("grp:" + g["group_id"]).to_numpy()
    children: dict[str, list[str]] = {}

    keep = np.flatnonzero(lines.in_comparison)
    order = keep[np.argsort(lines.group[keep], kind="stable")]
    bounds = np.searchsorted(lines.group[order], np.arange(len(g) + 1)).tolist()
    sorted_ids = lines.line_id[order].tolist()
    for node, start, end in zip(group_nodes, bounds[:-1], bounds[1:], strict=True):
        children[node] = sorted_ids[start:end]
    item_ids = inputs.items["canonical_item_id"].to_numpy()[inputs.item]
    for node, item_id, opp_id in zip(group_nodes, item_ids, opportunity, strict=True):
        children.setdefault(f"item:{item_id}", []).append(node)
        if opp_id is not None:
            children.setdefault(opp_id, []).append(node)

    in_range = opportunities[opportunities["status"] == "in_range"]
    categories = in_range.groupby("l2_code", sort=True)["opportunity_id"].agg(list)
    children["lever:1"] = [f"lever:1:cat:{l2}" for l2 in categories.index]
    for l2, opp_ids in categories.items():
        children[f"lever:1:cat:{l2}"] = opp_ids
    for tier in ("A", "B"):
        children[f"lever:1:tier:{tier}"] = in_range.loc[
            in_range["tier"] == tier, "opportunity_id"
        ].tolist()
    children["total:recurring"] = ["lever:1"]
    children["lever:1:upside"] = opportunities.loc[
        opportunities["status"] == "pending_review", "opportunity_id"
    ].tolist()

    results = bridge.results
    raw = [results[i - 1].contribution - results[i].contribution for i in range(1, N_STEPS + 1)]
    children["bridge:naive"] = _items_with(inputs, results[0].contribution)
    children["lever:1:internal"] = _items_with(inputs, raw[3])
    for i in range(1, N_STEPS + 1):
        children[f"bridge:raw:{i}"] = _items_with(inputs, raw[i - 1])
        landed = sorted({n for j in bridge.sources[i - 1] for n in children[f"bridge:raw:{j}"]})
        children[f"bridge:step:{i}"] = landed

    return TraceIndex(
        children=children,
        line_amounts=_line_amounts(inputs, lines, bridge, ev),
        figures=_figures(),
    )


def _figures() -> dict[str, tuple[str, str]]:
    figures = {
        "levers.lever1.gross_gap": ("lever:1", "gross"),
        "lever1.naive": ("bridge:naive", "naive"),
        "lever1.bridge.defensible": ("lever:1", "base"),
        "lever1.upside_pending_review": ("lever:1:upside", "upside"),
        "lever1.internal_variance": ("lever:1:internal", "internal"),
    }
    for case in CASES:
        figures[f"recurring.{case}"] = ("total:recurring", case)
        figures[f"levers.lever1.{case}"] = ("lever:1", case)
        figures[f"lever1.tier_a.{case}"] = ("lever:1:tier:A", case)
        figures[f"lever1.tier_b.{case}"] = ("lever:1:tier:B", case)
    for i in range(1, N_STEPS + 1):
        figures[f"lever1.bridge.step_{i}"] = (f"bridge:step:{i}", f"step_{i}")
        figures[f"lever1.bridge_raw.step_{i}"] = (f"bridge:raw:{i}", f"raw_{i}")
    return figures


def children_by(
    keys: np.ndarray, mask: np.ndarray, line_id: np.ndarray, names: np.ndarray
) -> dict[str, list[str]]:
    """Node ``names[k]`` -> the ``line_id`` s (in their order) of masked rows with key ``k``."""
    rows = np.flatnonzero(mask)
    order = rows[np.argsort(keys[rows], kind="stable")]
    bounds = np.searchsorted(keys[order], np.arange(len(names) + 1)).tolist()
    ids = line_id[order].tolist()
    return {
        str(name): ids[start:end]
        for name, start, end in zip(names, bounds[:-1], bounds[1:], strict=True)
        if end > start
    }


def extend_trace(
    trace: TraceIndex,
    line_id: np.ndarray,
    measures: Mapping[str, np.ndarray],
    children: Mapping[str, list[str]],
    figures: Mapping[str, tuple[str, str]],
) -> TraceIndex:
    """Add measures over every line in ``line_id`` (lever-1 measures are zero off their lines)."""
    index = pd.Index(line_id, name="line_id")
    amounts = trace.line_amounts.reindex(index, fill_value=0.0)
    amounts = pd.concat([amounts, pd.DataFrame(dict(measures), index=index)], axis=1)
    return TraceIndex(
        children={**trace.children, **children},
        line_amounts=amounts,
        figures={**trace.figures, **figures},
    )


def leaf_lines(trace: TraceIndex, node: str) -> list[str]:
    """Every ``line_id`` under ``node``, each once, in first-reached order."""
    seen: dict[str, None] = {}
    stack = [node]
    while stack:
        current = stack.pop()
        kids = trace.children.get(current)
        if kids is None:
            seen.setdefault(current, None)
        else:
            stack.extend(reversed(kids))
    return list(seen)


def resum(trace: TraceIndex, node: str, measure: str) -> float:
    """Recompute a figure as the sum of its traced lines' contributions for ``measure``."""
    ids: Iterable[str] = [i for i in leaf_lines(trace, node) if i != node]
    return float(trace.line_amounts[measure].reindex(list(ids)).fillna(0.0).sum())


def figure_value(totals: Mapping[str, object], path: str) -> float:
    """The number at a dotted ``path`` in ``totals``."""
    node: object = totals
    for key in path.split("."):
        node = node[key]  # type: ignore[index]
    return float(node)  # type: ignore[arg-type]
