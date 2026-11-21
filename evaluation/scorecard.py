"""Assemble, write and read the accuracy scorecard (`scorecard.json`, PRD 4.7)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from evaluation import targets
from evaluation.metrics import PairScore

SCHEMA_VERSION = 1
METRIC_NAMES = [
    "vendor_precision",
    "vendor_recall",
    "item_precision",
    "item_recall",
    "planted_savings_recall",
    "false_savings_rate",
    "unit_error_catch_rate",
]

Metrics = dict[str, float | None]


def metric_row(
    vendor: PairScore,
    items: PairScore,
    *,
    planted_savings_recall: float | None = None,
    false_savings_rate: float | None = None,
    unit_error_catch_rate: float | None = None,
) -> Metrics:
    """Flatten the pair scores and dollar metrics of one run into one metrics row."""
    return {
        "vendor_precision": vendor.precision,
        "vendor_recall": vendor.recall,
        "item_precision": items.precision,
        "item_recall": items.recall,
        "planted_savings_recall": planted_savings_recall,
        "false_savings_rate": false_savings_rate,
        "unit_error_catch_rate": unit_error_catch_rate,
    }


def mean_metrics(rows: Mapping[int, Mapping[str, float | None]]) -> Metrics:
    """Mean of each metric over seeds; None when no seed has a value for it."""
    out: Metrics = {}
    for name in METRIC_NAMES:
        values = [row[name] for row in rows.values() if row.get(name) is not None]
        out[name] = sum(values) / len(values) if values else None  # type: ignore[arg-type]
    return out


def _side(
    tuning: Mapping[int, Mapping[str, float | None]], held_out: Mapping[str, float | None]
) -> dict[str, Any]:
    return {
        "tuning": {str(seed): dict(tuning[seed]) for seed in sorted(tuning)},
        "tuning_mean": mean_metrics(tuning),
        "held_out": dict(held_out),
    }


def build_scorecard(
    *,
    tuning_seeds: list[int],
    held_out_seed: int,
    tool_tuning: Mapping[int, Mapping[str, float | None]],
    tool_held_out: Mapping[str, float | None],
    baseline_tuning: Mapping[int, Mapping[str, float | None]],
    baseline_held_out: Mapping[str, float | None],
) -> dict[str, Any]:
    """Assemble the scorecard: tool vs baseline, tuning seeds vs the held-out seed.

    Each metrics mapping uses the keys in `METRIC_NAMES`; dollar metrics may be None.
    Gates (PRD 4.7 targets) apply to the tool's held-out metrics only.
    """
    scorecard: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "tuning_seeds": list(tuning_seeds),
        "held_out_seed": held_out_seed,
        "tool": _side(tool_tuning, tool_held_out),
        "baseline": _side(baseline_tuning, baseline_held_out),
        "targets": {
            name: {"direction": direction, "bound": bound}
            for name, (direction, bound) in targets.TARGETS.items()
        },
    }
    held_out = scorecard["tool"]["held_out"]
    scorecard["gates"] = {
        name: {"value": held_out.get(name), "passed": targets.gate_passes(name, held_out.get(name))}
        for name in targets.TARGETS
    }
    failures = targets.check(scorecard)
    scorecard["failures"] = failures
    scorecard["passed"] = not failures
    return scorecard


def write_scorecard(scorecard: Mapping[str, Any], path: str | Path) -> None:
    """Write `scorecard.json` (sorted keys, stable formatting)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(scorecard, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_scorecard(path: str | Path) -> dict[str, Any]:
    """Read a scorecard written by `write_scorecard`, checking the schema version."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"unsupported scorecard schema_version {data.get('schema_version')!r}")
    return data
