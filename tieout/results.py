"""The single results object every surface reads (PRD 9.2).

View functions that turn a ``Results`` into displayed figures arrive in a later
milestone.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from tieout.synergy.stage import SynergyCache
from tieout.synergy.trace import TraceIndex

FRAME_NAMES = (
    "lines",
    "vendor_map",
    "item_map",
    "review_queue",
    "review_log",
    "price_groups",
    "bridge_detail",
    "opportunities",
    "internal_variance",
    "category_risk",
    "payment_terms",
    "phasing",
    "data_quality",
    "vendor_pairs",
    "item_pairs",
    "vendor_parents",
)
_JSON_NAMES = ("meta", "assumptions", "totals", "trace_figures", "scorecard", "sensitivity")
_JSON_FILE = "results.json"
_TRACE_FILE = "trace.parquet"
_AMOUNTS_FILE = "trace_amounts.parquet"
_COMPRESSION = "zstd"


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame()


def _json_default(value: object) -> object:
    """numpy scalars (``np.bool_``, ``np.int64``) as their Python values."""
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")


@dataclass(frozen=True)
class Results:
    """Everything one pipeline run produces. Frames are never mutated in place.

    ``vendor_pairs`` and ``item_pairs`` are the full pair logs of vendor and
    item matching, which double as the cached pair scores: passing them back as
    ``cached_pairs`` re-runs clustering and one-to-one assembly without
    rescoring (PRD 4.5). ``vendor_parents`` is the parent table the run used,
    kept so that re-assembly needs nothing but this object.

    The trace (PRD 6.6) is three parts: ``trace`` maps a node to its child
    nodes or ``line_id`` s, ``trace_amounts`` holds each line's contribution
    per measure (index ``line_id``), and ``trace_figures`` maps each dotted
    money path in ``totals`` to its ``(node, measure)``.

    ``synergy_cache`` holds the assumption-independent part of the synergy
    stage so that a recalculation repeats only the arithmetic. It lives in
    memory only: it is not saved, is ignored by ``==``, and is rebuilt on the
    first recalculation after :meth:`load`.
    """

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
    internal_variance: pd.DataFrame = field(default_factory=_empty_frame)
    category_risk: pd.DataFrame = field(default_factory=_empty_frame)
    payment_terms: pd.DataFrame = field(default_factory=_empty_frame)
    phasing: pd.DataFrame = field(default_factory=_empty_frame)
    data_quality: pd.DataFrame = field(default_factory=_empty_frame)
    vendor_pairs: pd.DataFrame = field(default_factory=_empty_frame)
    item_pairs: pd.DataFrame = field(default_factory=_empty_frame)
    vendor_parents: pd.DataFrame = field(default_factory=_empty_frame)
    totals: dict[str, Any] = field(default_factory=dict)
    trace: dict[str, list[str]] = field(default_factory=dict)
    trace_amounts: pd.DataFrame = field(default_factory=_empty_frame)
    trace_figures: dict[str, tuple[str, str]] = field(default_factory=dict)
    scorecard: dict[str, Any] | None = None
    sensitivity: dict[str, Any] | None = None
    synergy_cache: SynergyCache | None = field(default=None, compare=False, repr=False)

    @classmethod
    def empty(cls) -> Results:
        """Return a ``Results`` with empty frames and dictionaries."""
        return cls()

    @property
    def trace_index(self) -> TraceIndex:
        """The three trace parts as one :class:`~tieout.synergy.trace.TraceIndex`."""
        return TraceIndex(self.trace, self.trace_amounts, self.trace_figures)

    def save(self, directory: str | Path) -> None:
        """Write one Parquet file per frame, the trace and ``results.json`` into ``directory``.

        Trace line amounts are written in long form with only the non-zero
        values; the line and measure orders travel as the categories.
        """
        out = Path(directory)
        out.mkdir(parents=True, exist_ok=True)
        for name in FRAME_NAMES:
            getattr(self, name).to_parquet(
                out / f"{name}.parquet", index=False, compression=_COMPRESSION
            )
        edges = [(node, child) for node, kids in self.trace.items() for child in kids]
        pd.DataFrame(edges, columns=["node", "child"], dtype=object).to_parquet(
            out / _TRACE_FILE, index=False, compression=_COMPRESSION
        )
        _amounts_long(self.trace_amounts).to_parquet(
            out / _AMOUNTS_FILE, index=False, compression=_COMPRESSION
        )
        payload = {name: getattr(self, name) for name in _JSON_NAMES}
        text = json.dumps(payload, indent=1, sort_keys=True, default=_json_default)
        (out / _JSON_FILE).write_text(text + "\n", encoding="utf-8")

    @classmethod
    def load(cls, directory: str | Path) -> Results:
        """Read a ``Results`` written by :meth:`save`."""
        src = Path(directory)
        payload = json.loads((src / _JSON_FILE).read_text(encoding="utf-8"))
        payload["trace_figures"] = {
            path: (node, measure) for path, (node, measure) in payload["trace_figures"].items()
        }
        frames = {name: _read_frame(src / f"{name}.parquet") for name in FRAME_NAMES}
        trace: dict[str, list[str]] = {}
        edges = pd.read_parquet(src / _TRACE_FILE)
        for node, child in zip(edges["node"].tolist(), edges["child"].tolist(), strict=True):
            trace.setdefault(node, []).append(child)
        amounts = _amounts_wide(pd.read_parquet(src / _AMOUNTS_FILE))
        return cls(**payload, **frames, trace=trace, trace_amounts=amounts)


def _read_frame(path: Path) -> pd.DataFrame:
    """A saved frame as it was: object text columns come back as object with ``None`` blanks.

    pandas 3 reads every text column as its ``str`` dtype (blanks as NaN); the
    pandas metadata in the file records which columns were ``object``.
    """
    frame = pd.read_parquet(path)
    metadata = pq.read_schema(path).pandas_metadata or {}
    for column in metadata.get("columns", []):
        name = column["name"]
        if column["numpy_type"] != "object" or name not in frame.columns:
            continue
        values = frame[name]
        if isinstance(values.dtype, pd.StringDtype):
            frame[name] = values.astype(object).where(values.notna(), None)
    return frame


def _amounts_long(wide: pd.DataFrame) -> pd.DataFrame:
    """Non-zero ``(line_id, measure, amount)`` rows; categories keep both orders."""
    values = wide.to_numpy(dtype=float)
    rows, cols = np.nonzero(values)
    line_ids = pd.Index(wide.index.astype(str), name="line_id")
    measures = pd.Index(wide.columns.astype(str))
    return pd.DataFrame(
        {
            "line_id": pd.Categorical.from_codes(rows, categories=line_ids),
            "measure": pd.Categorical.from_codes(cols, categories=measures),
            "amount": values[rows, cols],
        }
    )


def _amounts_wide(long: pd.DataFrame) -> pd.DataFrame:
    """Inverse of :func:`_amounts_long`."""
    line_ids = long["line_id"].cat.categories
    measures = long["measure"].cat.categories
    values = np.zeros((len(line_ids), len(measures)))
    values[long["line_id"].cat.codes.to_numpy(), long["measure"].cat.codes.to_numpy()] = long[
        "amount"
    ].to_numpy()
    index = pd.Index(line_ids.tolist(), name="line_id")
    return pd.DataFrame(values, index=index, columns=measures.tolist())
