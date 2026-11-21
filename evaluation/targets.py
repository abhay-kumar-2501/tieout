"""Acceptance targets on the held-out seed (PRD 4.7). Gates, not claims."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

VENDOR_PRECISION_MIN = 0.98
VENDOR_RECALL_MIN = 0.90
ITEM_PRECISION_MIN = 0.97
ITEM_RECALL_MIN = 0.80
FALSE_SAVINGS_RATE_MAX = 0.02
UNIT_ERROR_CATCH_RATE_MIN = 0.95

# metric name -> (direction, bound); planted_savings_recall has no gate.
TARGETS: dict[str, tuple[str, float]] = {
    "vendor_precision": (">=", VENDOR_PRECISION_MIN),
    "vendor_recall": (">=", VENDOR_RECALL_MIN),
    "item_precision": (">=", ITEM_PRECISION_MIN),
    "item_recall": (">=", ITEM_RECALL_MIN),
    "false_savings_rate": ("<=", FALSE_SAVINGS_RATE_MAX),
    "unit_error_catch_rate": (">=", UNIT_ERROR_CATCH_RATE_MIN),
}


def gate_passes(metric: str, value: float | None) -> bool:
    """True when `value` meets the target for `metric`; a missing value fails."""
    direction, bound = TARGETS[metric]
    if value is None:
        return False
    return value >= bound if direction == ">=" else value <= bound


def check(scorecard: Mapping[str, Any]) -> list[str]:
    """Return one message per failing gate on the tool's held-out metrics.

    Reads `scorecard["tool"]["held_out"]`, a mapping of metric name to value.
    A metric that is absent or None (dollar metrics before the synergy engine
    exists) counts as failing: a gate that was not measured has not been met.
    """
    held_out = scorecard.get("tool", {}).get("held_out", {})
    failures = []
    for metric, (direction, bound) in TARGETS.items():
        value = held_out.get(metric)
        if value is None:
            failures.append(f"{metric}: not available (need {direction} {bound})")
        elif not gate_passes(metric, value):
            failures.append(f"{metric}: {value:.4f} (need {direction} {bound})")
    return failures
