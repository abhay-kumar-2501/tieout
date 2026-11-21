"""Default assumptions (PRD section 5) and their validation.

Every default the PRD calls an assumption lives in ``DEFAULTS``. The values are
illustrative starting points, not benchmarks.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

DEFAULTS: dict[str, Any] = {
    "reporting_currency": "USD",
    "planning_horizon_months": 36,
    "cost_of_capital": 0.08,
    "lever1": {
        "same_vendor": {"low": 0.50, "base": 0.70, "high": 0.85},
        "switch": {"low": 0.20, "base": 0.40, "high": 0.60},
    },
    "lever2": {
        "capture": {"low": 0.40, "base": 0.60, "high": 0.80},
        "discount": {"commodity": 0.0, "engineered": 0.02, "mro": 0.04, "indirect": 0.03},
    },
    "lever3": {
        "capture": {"low": 0.30, "base": 0.50, "high": 0.70},
        "max_payment_days": 90,
    },
    "caps": {"critical": 0.60, "standard": 0.75, "non_critical": 0.90},
    "benchmark": {"min_volume_share": 0.10, "min_lines": 3},
    "global_ramp": {"year1": 0.40, "year2": 0.85, "year3": 1.00},
    "switching_cost": {"fixed_usd": 25_000.0, "pct_of_spend_moved": 0.01},
    "lead_time_months": {"l1_same_vendor": 3, "l1_switch": 6, "l2": 6, "l3": 3},
    "reference_bands": {
        "total_spend": {"low": 0.01, "high": 0.03},
        "addressable_spend": {"low": 0.03, "high": 0.10},
    },
}

_TRIPLE_PATHS = (
    ("lever1", "same_vendor"),
    ("lever1", "switch"),
    ("lever2", "capture"),
    ("lever3", "capture"),
)
_UNIT_INTERVAL_PATHS = (
    ("lever2", "discount"),
    ("caps",),
    ("global_ramp",),
    ("benchmark", "min_volume_share"),
    ("cost_of_capital",),
    ("switching_cost", "pct_of_spend_moved"),
)


def merge_overrides(
    overrides: Mapping[str, Any] | None, defaults: Mapping[str, Any] = DEFAULTS
) -> dict[str, Any]:
    """Return a deep copy of ``defaults`` with ``overrides`` merged over it."""
    merged = copy.deepcopy(dict(defaults))
    for key, value in (overrides or {}).items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), dict):
            merged[key] = merge_overrides(value, merged[key])
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _get(node: Any, path: tuple[str, ...]) -> Any:
    for i, key in enumerate(path):
        if not isinstance(node, Mapping) or key not in node:
            raise ValueError(f"missing assumption: {'.'.join(path[: i + 1])}")
        node = node[key]
    return node


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{name} must be a number, got {value!r}")
    return float(value)


def _check_unit_interval(value: Any, name: str) -> None:
    if not 0.0 <= _number(value, name) <= 1.0:
        raise ValueError(f"{name} must lie in [0, 1], got {value!r}")


def validate(assumptions: Mapping[str, Any]) -> None:
    """Raise ``ValueError`` if ``assumptions`` break the PRD 5.1 input rules.

    Probability triples need 0 <= low <= base <= high <= 1; discounts, caps and
    other shares must lie in [0, 1]; reference bands need 0 <= low <= high.
    """
    for path in _TRIPLE_PATHS:
        name = ".".join(path)
        triple = _get(assumptions, path)
        low, base, high = (
            _number(_get(triple, (k,)), f"{name}.{k}") for k in ("low", "base", "high")
        )
        if not 0.0 <= low <= base <= high <= 1.0:
            raise ValueError(
                f"{name} must satisfy 0 <= low <= base <= high <= 1, got "
                f"low={low}, base={base}, high={high}"
            )
    for path in _UNIT_INTERVAL_PATHS:
        name = ".".join(path)
        node = _get(assumptions, path)
        if isinstance(node, Mapping):
            for key, value in node.items():
                _check_unit_interval(value, f"{name}.{key}")
        else:
            _check_unit_interval(node, name)
    for key, band in _get(assumptions, ("reference_bands",)).items():
        low = _number(_get(band, ("low",)), f"reference_bands.{key}.low")
        high = _number(_get(band, ("high",)), f"reference_bands.{key}.high")
        if not 0.0 <= low <= high:
            raise ValueError(f"reference_bands.{key} must satisfy 0 <= low <= high")
