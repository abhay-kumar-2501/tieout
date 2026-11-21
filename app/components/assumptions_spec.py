"""What the Assumptions screen shows for each input (PRD 6.7, 6.12).

``tieout.assumptions`` holds the default values and the engine's validation;
this module adds the display side the screen needs: grouping, units, the range
a value should lie in, and a one-line explanation saying which way it moves the
answer. It computes no figure.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from tieout.assumptions import DEFAULTS

__all__ = [
    "GROUPS",
    "Field",
    "Group",
    "Row",
    "changed_paths",
    "default_for",
    "field_by_dotted",
    "format_value",
    "from_display",
    "get_path",
    "nested",
    "range_error",
    "to_display",
]

#: unit -> (suffix shown after a value, stored as a fraction shown as a percentage?)
_UNITS = {
    "pct": "%",
    "months": " months",
    "days": " days",
    "usd": " USD",
    "count": " lines",
}
#: Units whose valid range the engine does not check, so the screen does.
_SCREEN_CHECKED = ("months", "days", "usd", "count")


@dataclass(frozen=True)
class Field:
    path: tuple[str, ...]
    name: str  # short name, e.g. "Low", "Base", "Commodity"
    unit: str
    low: float
    high: float

    @property
    def dotted(self) -> str:
        return ".".join(self.path)


@dataclass(frozen=True)
class Row:
    """One assumption (or a low/base/high triple) with its one-line explanation."""

    title: str
    fields: tuple[Field, ...]
    explanation: str


@dataclass(frozen=True)
class Group:
    id: str
    title: str
    blurb: str
    rows: tuple[Row, ...]


def _f(path: str, name: str, unit: str, low: float, high: float) -> Field:
    return Field(tuple(path.split(".")), name, unit, low, high)


def _triple(path: str, unit: str = "pct") -> tuple[Field, ...]:
    return tuple(_f(f"{path}.{c}", c.capitalize(), unit, 0, 100) for c in ("low", "base", "high"))


GROUPS: tuple[Group, ...] = (
    Group(
        "general",
        "General",
        "How far ahead the plan looks and what money costs.",
        (
            Row(
                "Planning horizon",
                (_f("planning_horizon_months", "Months", "months", 1, 120),),
                "How many months of contract renewals count as capturable; "
                "a longer horizon brings more opportunities in and raises the saving.",
            ),
            Row(
                "Cost of capital",
                (_f("cost_of_capital", "Rate", "pct", 0, 100),),
                "Used only to put a financing value on one-time cash; "
                "a higher rate raises that memo figure and leaves the run-rate unchanged.",
            ),
        ),
    ),
    Group(
        "lever1",
        "Lever 1: price harmonisation",
        "Paying the best price already achieved for the same item.",
        (
            Row(
                "Same-vendor renegotiation: chance of capturing the gap",
                _triple("lever1.same_vendor"),
                "Higher values raise the saving; low and high set the range.",
            ),
            Row(
                "Switching vendor: chance of capturing the gap",
                _triple("lever1.switch"),
                "Higher values raise the saving; switching is harder, so it starts lower.",
            ),
            Row(
                "Benchmark: smallest volume share",
                (_f("benchmark.min_volume_share", "Share", "pct", 0, 100),),
                "A price must cover at least this share of an item's volume to be a benchmark; "
                "raising it removes thin benchmarks and lowers the saving.",
            ),
            Row(
                "Benchmark: fewest purchase lines",
                (_f("benchmark.min_lines", "Lines", "count", 1, 100),),
                "A benchmark price needs at least this many lines; raising it lowers the saving.",
            ),
        ),
    ),
    Group(
        "lever2",
        "Lever 2: volume consolidation",
        "Moving spend to fewer vendors for a volume discount.",
        (
            Row(
                "Chance of capturing the discount",
                _triple("lever2.capture"),
                "Higher values raise the saving.",
            ),
            Row(
                "Volume discount by category type",
                tuple(
                    _f(f"lever2.discount.{k}", k.capitalize(), "pct", 0, 100)
                    for k in ("commodity", "engineered", "mro", "indirect")
                ),
                "The discount a consolidated vendor gives; higher values raise the saving.",
            ),
        ),
    ),
    Group(
        "lever3",
        "Lever 3: payment terms",
        "Paying later, which releases cash once (it is not a saving).",
        (
            Row(
                "Chance of moving to the longer terms",
                _triple("lever3.capture"),
                "Higher values raise the one-time cash release.",
            ),
            Row(
                "Longest payment term to assume",
                (_f("lever3.max_payment_days", "Days", "days", 1, 365),),
                "Terms are never stretched past this; a lower value lowers the cash release.",
            ),
        ),
    ),
    Group(
        "caps",
        "Risk: concentration caps",
        "The most any one parent vendor may hold of a category after consolidation.",
        (
            Row(
                "Cap by category criticality",
                tuple(
                    _f(f"caps.{k}", name, "pct", 0, 100)
                    for k, name in (
                        ("critical", "Critical"),
                        ("standard", "Standard"),
                        ("non_critical", "Non-critical"),
                    )
                ),
                "Lower caps protect supply and lower the volume-consolidation saving; "
                "the standard cap can also be moved on Risk & roadmap.",
            ),
        ),
    ),
    Group(
        "phasing",
        "Phasing and one-time costs",
        "When savings arrive and what it costs to get them.",
        (
            Row(
                "Global ramp (used when contract dates are missing)",
                tuple(_f(f"global_ramp.year{n}", f"Year {n}", "pct", 0, 100) for n in (1, 2, 3)),
                "Share of the run-rate realised each year; higher values raise the "
                "three-year value, not the run-rate.",
            ),
            Row(
                "Cost of switching a vendor",
                (
                    _f("switching_cost.fixed_usd", "Fixed", "usd", 0, 10_000_000),
                    _f("switching_cost.pct_of_spend_moved", "Of spend moved", "pct", 0, 100),
                ),
                "A fixed amount per switch plus a share of the spend moved; higher costs "
                "lower the three-year value.",
            ),
            Row(
                "Lead time before savings start",
                (
                    _f("lead_time_months.l1_same_vendor", "Lever 1 same vendor", "months", 0, 36),
                    _f("lead_time_months.l1_switch", "Lever 1 switch", "months", 0, 36),
                    _f("lead_time_months.l2", "Lever 2", "months", 0, 36),
                    _f("lead_time_months.l3", "Lever 3", "months", 0, 36),
                ),
                "Months after a contract frees up before the saving starts; longer lead "
                "times push savings later and lower the three-year value.",
            ),
        ),
    ),
    Group(
        "bands",
        "Reference bands",
        "The top-down range the bottom-up total is checked against.",
        (
            Row(
                "Share of total spend",
                (
                    _f("reference_bands.total_spend.low", "Low", "pct", 0, 100),
                    _f("reference_bands.total_spend.high", "High", "pct", 0, 100),
                ),
                "A sense check only: it moves the reconciliation, not the saving.",
            ),
            Row(
                "Share of addressable spend",
                (
                    _f("reference_bands.addressable_spend.low", "Low", "pct", 0, 100),
                    _f("reference_bands.addressable_spend.high", "High", "pct", 0, 100),
                ),
                "A sense check only: it moves the reconciliation, not the saving.",
            ),
        ),
    ),
)

_BY_DOTTED = {f.dotted: f for g in GROUPS for r in g.rows for f in r.fields}


def field_by_dotted(dotted: str) -> Field | None:
    return _BY_DOTTED.get(dotted)


# ---------------------------------------------------------------- values


def get_path(tree: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    node: Any = tree
    for key in path:
        node = node[key]
    return node


def nested(values: Mapping[tuple[str, ...], Any]) -> dict[str, Any]:
    """``{path: value}`` as the nested override mapping ``set_assumptions`` takes."""
    out: dict[str, Any] = {}
    for path, value in values.items():
        node = out
        for key in path[:-1]:
            node = node.setdefault(key, {})
        node[path[-1]] = value
    return out


def default_for(field: Field) -> Any:
    return get_path(DEFAULTS, field.path)


def to_display(field: Field, stored: float) -> float:
    """A stored value as the number shown: shares as percentages."""
    return round(stored * 100, 6) if field.unit == "pct" else stored


def from_display(field: Field, shown: float) -> float:
    """The number typed back to the stored value."""
    return round(shown / 100, 8) if field.unit == "pct" else shown


def format_value(field: Field | None, stored: float) -> str:
    """A stored value in words: ``70%``, ``36 months``, ``$25,000``."""
    if field is None:
        return f"{stored:g}"
    if field.unit == "pct":
        return f"{to_display(field, stored):g}%"
    if field.unit == "usd":
        return f"${stored:,.0f}"
    return f"{stored:g}{_UNITS[field.unit]}"


def range_error(field: Field, shown: float) -> str | None:
    """Ranges the engine does not check (months, days, dollars, counts); ``None`` if fine."""
    if field.unit not in _SCREEN_CHECKED:
        return None
    if isinstance(shown, float) and math.isnan(shown):
        return f"{field.dotted} must be a number"
    if not field.low <= shown <= field.high:
        return (
            f"{field.dotted} must lie in [{field.low:g}, {field.high:g}]"
            f"{_UNITS[field.unit]}, got {shown:g}"
        )
    return None


def changed_paths(current: Mapping[str, Any]) -> list[Field]:
    """The fields whose value in force differs from the default."""
    return [
        f
        for f in _BY_DOTTED.values()
        if not math.isclose(float(get_path(current, f.path)), float(default_for(f)), abs_tol=1e-9)
    ]
