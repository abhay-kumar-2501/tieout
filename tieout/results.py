"""The single results object every surface reads (PRD 9.2).

View functions that turn a ``Results`` into displayed figures arrive in a later
milestone.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

FRAME_NAMES = (
    "lines",
    "vendor_map",
    "item_map",
    "review_queue",
    "review_log",
    "price_groups",
    "bridge_detail",
    "opportunities",
    "category_risk",
    "payment_terms",
    "phasing",
    "data_quality",
)
_JSON_NAMES = ("meta", "assumptions", "totals", "trace", "scorecard")
_JSON_FILE = "results.json"


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame()


@dataclass(frozen=True)
class Results:
    """Everything one pipeline run produces. Frames are never mutated in place."""

    meta: dict[str, Any] = field(default_factory=dict)
    assumptions: dict[str, Any] = field(default_factory=dict)
    lines: pd.DataFrame = field(default_factory=_empty_frame)
    vendor_map: pd.DataFrame = field(default_factory=_empty_frame)
    item_map: pd.DataFrame = field(default_factory=_empty_frame)
    review_queue: pd.DataFrame = field(default_factory=_empty_frame)
    review_log: pd.DataFrame = field(default_factory=_empty_frame)
    price_groups: pd.DataFrame = field(default_factory=_empty_frame)
    bridge_detail: pd.DataFrame = field(default_factory=_empty_frame)
    opportunities: pd.DataFrame = field(default_factory=_empty_frame)
    category_risk: pd.DataFrame = field(default_factory=_empty_frame)
    payment_terms: pd.DataFrame = field(default_factory=_empty_frame)
    phasing: pd.DataFrame = field(default_factory=_empty_frame)
    data_quality: pd.DataFrame = field(default_factory=_empty_frame)
    totals: dict[str, Any] = field(default_factory=dict)
    trace: dict[str, list[str]] = field(default_factory=dict)
    scorecard: dict[str, Any] | None = None

    @classmethod
    def empty(cls) -> Results:
        """Return a ``Results`` with empty frames and dictionaries."""
        return cls()

    def save(self, directory: str | Path) -> None:
        """Write one Parquet file per frame plus ``results.json`` into ``directory``."""
        out = Path(directory)
        out.mkdir(parents=True, exist_ok=True)
        for name in FRAME_NAMES:
            getattr(self, name).to_parquet(out / f"{name}.parquet", index=False)
        payload = {name: getattr(self, name) for name in _JSON_NAMES}
        (out / _JSON_FILE).write_text(json.dumps(payload, indent=2, sort_keys=True))

    @classmethod
    def load(cls, directory: str | Path) -> Results:
        """Read a ``Results`` written by :meth:`save`."""
        src = Path(directory)
        payload = json.loads((src / _JSON_FILE).read_text())
        frames = {name: pd.read_parquet(src / f"{name}.parquet") for name in FRAME_NAMES}
        return cls(**payload, **frames)
