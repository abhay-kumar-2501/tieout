"""Threshold sensitivity of the base case (PRD 4.7), precomputed for the demo.

Two curves of the base-case total recurring saving: the vendor automatic
threshold from 80 to 98 in steps of 2, and the item automatic cosine from 0.60
to 0.95 in steps of 0.05, each varied alone with the other at its tuned value.
Each point re-runs assembly from the cached pair scores and then the
arithmetic (``tieout.pipeline.rematch``); no pair is rescored.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from tieout.pipeline import rematch, thresholds_of
from tieout.reference import Thresholds
from tieout.results import Results

VENDOR_GRID: tuple[float, ...] = tuple(float(t) for t in range(80, 99, 2))
ITEM_GRID: tuple[float, ...] = tuple(round(0.60 + 0.05 * i, 2) for i in range(8))


def _point(results: Results, thresholds: Thresholds, value: float) -> dict[str, float]:
    recurring = rematch(results, thresholds).totals["recurring"]
    return {"threshold": value, **{f"recurring_{c}": float(v) for c, v in recurring.items()}}


def threshold_sensitivity(
    results: Results,
    vendor_grid: Sequence[float] = VENDOR_GRID,
    item_grid: Sequence[float] = ITEM_GRID,
) -> dict[str, Any]:
    """Both curves for one pipeline run, with the run's own thresholds as ``current``."""
    current = thresholds_of(results)
    vendor = [_point(results, replace(current, vendor_auto=t), t) for t in vendor_grid]
    item = [_point(results, replace(current, item_auto_cosine=t), t) for t in item_grid]
    return {
        "seed": results.meta.get("seed"),
        "current": {
            **asdict(current),
            "recurring_base": float(results.totals["recurring"]["base"]),
        },
        "curves": {"vendor_auto": vendor, "item_auto_cosine": item},
    }


def write_sensitivity(data: dict[str, Any], path: str | Path) -> None:
    """Write ``sensitivity.json`` (sorted keys, stable formatting)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
