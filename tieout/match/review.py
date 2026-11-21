"""Human review decisions for every queue type (PRD 4.5).

Decisions are an append-only log with the PRD file columns. The latest row for
a ``pair_id`` wins; undo removes the last row. Matching modules consume the
log through :func:`approved`, :func:`rejected` and :func:`deferred`.
"""

from __future__ import annotations

import io
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import IO

import pandas as pd

__all__ = [
    "DECISION_COLUMNS",
    "DECISION_VALUES",
    "QUEUE_TYPES",
    "approved",
    "decision_for",
    "deferred",
    "empty_decisions",
    "latest_decisions",
    "make_pair_id",
    "parse_pair_id",
    "read_decisions_csv",
    "record_decision",
    "rejected",
    "undo_last",
    "validate_decisions",
    "write_decisions_csv",
]

DECISION_COLUMNS: tuple[str, ...] = (
    "pair_id",
    "type",
    "decision",
    "pack_qty",
    "note",
    "decided_at",
)
QUEUE_TYPES: tuple[str, ...] = (
    "vendor_match",
    "vendor_sibling",
    "item_match",
    "unit_flag",
    "incoterm",
)
DECISION_VALUES: tuple[str, ...] = ("approve", "reject", "defer")

_TEXT_COLUMNS = ("pair_id", "type", "decision", "note", "decided_at")


def make_pair_id(pair_type: str, side_a: str, side_b: str) -> str:
    """``{type}|{company}:{key}|{company}:{key}`` with the two sides sorted."""
    if pair_type not in QUEUE_TYPES:
        raise ValueError(f"unknown queue type {pair_type!r}")
    first, second = sorted((side_a, side_b))
    return f"{pair_type}|{first}|{second}"


def parse_pair_id(pair_id: str) -> tuple[str, str, str]:
    """Split a pair id into ``(type, side_a, side_b)``."""
    parts = pair_id.split("|")
    if len(parts) != 3 or parts[0] not in QUEUE_TYPES:
        raise ValueError(f"malformed pair id {pair_id!r}")
    return parts[0], parts[1], parts[2]


def empty_decisions() -> pd.DataFrame:
    """A decisions frame with no rows and the PRD columns."""
    frame = pd.DataFrame({c: pd.Series(dtype=object) for c in DECISION_COLUMNS})
    frame["pack_qty"] = frame["pack_qty"].astype(float)
    return frame


def _text_or_none(value: object) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value)
    return text if text.strip() else None


def _float_or_nan(value: object) -> float:
    if value is None or (isinstance(value, str) and not value.strip()):
        return math.nan
    return float(value)  # type: ignore[arg-type]


def validate_decisions(decisions: pd.DataFrame | None) -> pd.DataFrame:
    """Coerce a decisions frame to the schema; raise on bad types or values."""
    if decisions is None:
        return empty_decisions()
    missing = [c for c in DECISION_COLUMNS if c not in decisions.columns]
    if missing:
        raise ValueError(f"decisions are missing columns: {missing}")
    out = pd.DataFrame(
        {c: [_text_or_none(v) for v in decisions[c]] for c in _TEXT_COLUMNS},
        index=range(len(decisions)),
    )
    out["pack_qty"] = pd.Series([_float_or_nan(v) for v in decisions["pack_qty"]], dtype=float)
    out = out[list(DECISION_COLUMNS)]
    for pair_id, pair_type in zip(out["pair_id"], out["type"], strict=True):
        if pair_id is None or parse_pair_id(pair_id)[0] != pair_type:
            raise ValueError(f"pair id {pair_id!r} does not match type {pair_type!r}")
    bad = set(out["decision"]) - set(DECISION_VALUES)
    if bad:
        raise ValueError(f"unknown decisions: {sorted(map(str, bad))}")
    return out


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def record_decision(
    decisions: pd.DataFrame | None,
    pair_id: str,
    decision: str,
    *,
    note: str | None = None,
    pack_qty: float | None = None,
    decided_at: str | None = None,
) -> pd.DataFrame:
    """Return a new log with one decision appended (the input is not changed)."""
    if decision not in DECISION_VALUES:
        raise ValueError(f"decision must be one of {DECISION_VALUES}, got {decision!r}")
    pair_type = parse_pair_id(pair_id)[0]
    row = pd.DataFrame(
        [
            {
                "pair_id": pair_id,
                "type": pair_type,
                "decision": decision,
                "pack_qty": math.nan if pack_qty is None else float(pack_qty),
                "note": note,
                "decided_at": decided_at or _now(),
            }
        ]
    )
    base = validate_decisions(decisions)
    if base.empty:
        return validate_decisions(row)
    return validate_decisions(pd.concat([base, row], ignore_index=True))


def undo_last(decisions: pd.DataFrame | None) -> pd.DataFrame:
    """Remove the most recently recorded decision (the last row)."""
    base = validate_decisions(decisions)
    return base.iloc[:-1].reset_index(drop=True) if len(base) else base


def latest_decisions(decisions: pd.DataFrame | None) -> pd.DataFrame:
    """One row per ``pair_id``: the last decision recorded for it, sorted by ``pair_id``."""
    base = validate_decisions(decisions)
    latest = base.drop_duplicates("pair_id", keep="last")
    return latest.sort_values("pair_id", kind="stable").reset_index(drop=True)


def _ids_with(decisions: pd.DataFrame | None, value: str, pair_type: str | None) -> frozenset[str]:
    latest = latest_decisions(decisions)
    mask = latest["decision"] == value
    if pair_type is not None:
        mask &= latest["type"] == pair_type
    return frozenset(latest.loc[mask, "pair_id"])


def approved(decisions: pd.DataFrame | None, pair_type: str | None = None) -> frozenset[str]:
    """Pair ids whose latest decision is ``approve`` (optionally of one type)."""
    return _ids_with(decisions, "approve", pair_type)


def rejected(decisions: pd.DataFrame | None, pair_type: str | None = None) -> frozenset[str]:
    """Pair ids whose latest decision is ``reject`` (optionally of one type)."""
    return _ids_with(decisions, "reject", pair_type)


def deferred(decisions: pd.DataFrame | None, pair_type: str | None = None) -> frozenset[str]:
    """Pair ids whose latest decision is ``defer`` (optionally of one type)."""
    return _ids_with(decisions, "defer", pair_type)


def decision_for(decisions: pd.DataFrame | None, pair_id: str) -> str | None:
    """The latest decision for one pair, or ``None``."""
    latest = latest_decisions(decisions)
    hit = latest.loc[latest["pair_id"] == pair_id, "decision"]
    return None if hit.empty else str(hit.iloc[0])


def write_decisions_csv(
    decisions: pd.DataFrame | None, path_or_buffer: str | Path | IO[str] | None = None
) -> str | None:
    """Write the log as CSV; returns the text when no destination is given."""
    frame = validate_decisions(decisions)
    return frame.to_csv(path_or_buffer, index=False)


def read_decisions_csv(path_or_buffer: str | Path | IO[str]) -> pd.DataFrame:
    """Read a decisions CSV written by :func:`write_decisions_csv` (or by hand)."""
    if isinstance(path_or_buffer, str) and "\n" in path_or_buffer:
        path_or_buffer = io.StringIO(path_or_buffer)
    raw = pd.read_csv(path_or_buffer, dtype=str, keep_default_na=False)
    return validate_decisions(raw)
