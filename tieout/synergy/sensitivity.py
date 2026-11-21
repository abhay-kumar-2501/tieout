"""Tornado chart and scenario presets (PRD 6.7).

The tornado ranks assumptions by their effect on the base total recurring
saving: each probability triple has its base moved to its low and its high
value; caps move by 10 percentage points, the planning horizon by 12 months,
and every other number by 25%. Each move re-runs only the base-case recurring
arithmetic on the precomputed :class:`~tieout.synergy.stage.SynergyCache`.

Scenarios are assumption transforms: "Central (defaults)" is the defaults
(keeping the ``category_settings`` file, which is input data), and
"Conservative" / "Stretch" set every base probability to its low / high value.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd

from tieout.assumptions import merge_overrides
from tieout.synergy.settings import category_table
from tieout.synergy.stage import SynergyCache, recurring_base

__all__ = [
    "SCENARIOS",
    "TORNADO_COLUMNS",
    "TOP",
    "Move",
    "central",
    "conservative",
    "moves",
    "stretch",
    "tornado",
]

TOP = 12
RELATIVE = 0.25
CAP_POINTS = 0.10
HORIZON_MONTHS = 12
TRIPLES = (
    ("lever1", "same_vendor"),
    ("lever1", "switch"),
    ("lever2", "capture"),
    ("lever3", "capture"),
)
#: Category-settings probability columns, as ``{prefix}_{case}``.
SETTING_TRIPLES = ("pi1_same", "pi1_switch", "pi2")
_INTEGER = ("benchmark.min_lines", "lead_time_months.", "lever3.max_payment_days")
_SHARES = ("lever2.discount.", "global_ramp.", "benchmark.min_volume_share", "cost_of_capital")
_SKIP = ("reference_bands", "category_settings", "close_date", "reporting_currency")
TORNADO_COLUMNS = [
    "assumption",
    "base_setting",
    "low_setting",
    "high_setting",
    "recurring_at_low",
    "recurring_at_high",
    "effect_low",
    "effect_high",
    "swing",
]


@dataclass(frozen=True)
class Move:
    """One tornado bar: an assumption's dotted path and its low and high settings."""

    path: str
    base: float
    low: float
    high: float


def _leaves(node: Mapping[str, Any], prefix: str = "") -> Iterator[tuple[str, Any]]:
    for key, value in node.items():
        path = f"{prefix}{key}"
        if isinstance(value, Mapping):
            yield from _leaves(value, f"{path}.")
        else:
            yield path, value


def _relative(path: str, value: float) -> tuple[float, float]:
    low, high = value * (1 - RELATIVE), value * (1 + RELATIVE)
    if path.startswith(_INTEGER):
        return float(round(low)), float(round(high))
    if path.startswith(_SHARES):
        return low, min(high, 1.0)
    return low, high


def moves(settings: Mapping[str, Any]) -> list[Move]:
    """The tornado's moves for merged ``settings``, in a fixed order."""
    triple_paths = {".".join(path) for path in TRIPLES}
    out: list[Move] = []
    for path in triple_paths:
        triple = settings[path.split(".")[0]][path.split(".")[1]]
        out.append(Move(f"{path}.base", triple["base"], triple["low"], triple["high"]))
    for path, value in _leaves(settings):
        if path.startswith(_SKIP) or any(path.startswith(f"{t}.") for t in triple_paths):
            continue
        if isinstance(value, bool) or not isinstance(value, int | float):
            continue
        if path.startswith("caps."):
            low, high = max(value - CAP_POINTS, 0.0), min(value + CAP_POINTS, 1.0)
        elif path == "planning_horizon_months":
            low, high = max(value - HORIZON_MONTHS, 0), value + HORIZON_MONTHS
        else:
            low, high = _relative(path, float(value))
        out.append(Move(path, float(value), float(low), float(high)))
    return sorted(out, key=lambda m: m.path)


def _with(settings: Mapping[str, Any], path: str, value: float) -> dict[str, Any]:
    out = copy.deepcopy(dict(settings))
    node = out
    *parents, leaf = path.split(".")
    for key in parents:
        node = node[key]
    node[leaf] = int(value) if isinstance(node[leaf], int) else value
    return out


def tornado(
    cache: SynergyCache, assumptions: Mapping[str, Any] | None, top: int = TOP
) -> pd.DataFrame:
    """The ``top`` assumptions by effect on the base total recurring saving.

    Sorted by ``swing`` (the larger absolute effect), ties by assumption path.
    """
    settings = merge_overrides(assumptions)
    base = recurring_base(cache, settings)
    rows = []
    for move in moves(settings):
        at_low = recurring_base(cache, _with(settings, move.path, move.low))
        at_high = recurring_base(cache, _with(settings, move.path, move.high))
        rows.append(
            {
                "assumption": move.path,
                "base_setting": move.base,
                "low_setting": move.low,
                "high_setting": move.high,
                "recurring_at_low": at_low,
                "recurring_at_high": at_high,
                "effect_low": at_low - base,
                "effect_high": at_high - base,
                "swing": max(abs(at_low - base), abs(at_high - base)),
            }
        )
    frame = pd.DataFrame(rows, columns=TORNADO_COLUMNS)
    frame = frame.sort_values(["swing", "assumption"], ascending=[False, True], kind="mergesort")
    return frame.head(top).reset_index(drop=True)


# ---------------------------------------------------------------- scenarios


def central(assumptions: Mapping[str, Any] | None) -> dict[str, Any]:
    """The defaults, keeping the run's ``category_settings`` file."""
    kept = {k: v for k, v in (assumptions or {}).items() if k == "category_settings"}
    return merge_overrides(kept)


def _base_to(assumptions: Mapping[str, Any] | None, case: str) -> dict[str, Any]:
    settings = merge_overrides(assumptions)
    for group, name in TRIPLES:
        triple = settings[group][name]
        triple["base"] = triple[case]
    table = category_table(settings.get("category_settings"))
    if table:
        rows = {}
        for l2, row in table.items():
            row = dict(row)
            for prefix in SETTING_TRIPLES:
                if f"{prefix}_{case}" in row:
                    row[f"{prefix}_base"] = row[f"{prefix}_{case}"]
                else:
                    row.pop(f"{prefix}_base", None)
            rows[l2] = row
        settings["category_settings"] = rows
    return settings


def conservative(assumptions: Mapping[str, Any] | None) -> dict[str, Any]:
    """Every base probability set to its low value."""
    return _base_to(assumptions, "low")


def stretch(assumptions: Mapping[str, Any] | None) -> dict[str, Any]:
    """Every base probability set to its high value."""
    return _base_to(assumptions, "high")


SCENARIOS: dict[str, Callable[[Mapping[str, Any] | None], dict[str, Any]]] = {
    "Central (defaults)": central,
    "Conservative": conservative,
    "Stretch": stretch,
}
