"""Loaders for the generator's truth files (PRD 4.7), with column checks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from tieout.ingest.prepare import make_item_keys

VENDOR_TRUTH_COLUMNS = ["company", "vendor_id", "true_legal_entity", "true_parent"]
ITEM_TRUTH_COLUMNS = ["company", "item_key", "true_item_id"]
SAVINGS_TRUTH_COLUMNS = [
    "true_item_id",
    "cause",
    "true_gross_gap_usd",
    "is_unit_trap",
    "is_distractor",
]

_TRUE_TOKENS = {"true", "1", "yes", "t", "y"}
_FALSE_TOKENS = {"false", "0", "no", "f", "n", ""}


@dataclass(frozen=True)
class Truth:
    """The three truth frames of one seed."""

    vendor_map: pd.DataFrame
    item_map: pd.DataFrame
    savings: pd.DataFrame


def _read(path: Path, columns: list[str], dtype: dict[str, str]) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"truth file not found: {path}")
    frame = pd.read_csv(path, dtype=dtype, keep_default_na=False)
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}; found {list(frame.columns)}")
    return frame


def _to_bool(series: pd.Series, name: str) -> pd.Series:
    tokens = series.astype(str).str.strip().str.lower()
    unknown = sorted(set(tokens) - _TRUE_TOKENS - _FALSE_TOKENS)
    if unknown:
        raise ValueError(f"column {name}: cannot read {unknown} as boolean")
    return tokens.isin(_TRUE_TOKENS)


def load_vendor_truth(directory: str | Path) -> pd.DataFrame:
    """Read `truth_vendor_map.csv`: company, vendor_id, true_legal_entity, true_parent."""
    frame = _read(
        Path(directory) / "truth_vendor_map.csv",
        VENDOR_TRUTH_COLUMNS,
        dict.fromkeys(VENDOR_TRUTH_COLUMNS, "str"),
    )
    if frame.duplicated(["company", "vendor_id"]).any():
        raise ValueError("truth_vendor_map.csv: duplicate (company, vendor_id)")
    return frame[VENDOR_TRUTH_COLUMNS]


def load_item_truth(directory: str | Path) -> pd.DataFrame:
    """Read `truth_item_map.csv`: company, item_key, true_item_id."""
    frame = _read(
        Path(directory) / "truth_item_map.csv",
        ITEM_TRUTH_COLUMNS,
        dict.fromkeys(ITEM_TRUTH_COLUMNS, "str"),
    )
    if frame.duplicated(["company", "item_key"]).any():
        raise ValueError("truth_item_map.csv: duplicate (company, item_key)")
    return frame[ITEM_TRUTH_COLUMNS]


def load_item_truth_engine_keys(directory: str | Path) -> pd.DataFrame:
    """Item truth keyed the way the engine keys item records.

    The generator writes ``item_code``, ``mpn`` and ``manufacturer`` next to its
    own ``item_key``; the key is rebuilt from them with the engine's rule
    (``tieout.ingest.prepare.make_item_keys``), so that differences in
    manufacturer normalisation never count as matching errors. Records that
    collapse onto one engine key keep the smallest ``true_item_id``.
    """
    path = Path(directory) / "truth_item_map.csv"
    frame = _read(path, ITEM_TRUTH_COLUMNS, {})
    frame = frame.astype(str)
    if {"item_code", "mpn", "manufacturer"} <= set(frame.columns):
        source = frame[["item_code", "mpn", "manufacturer"]].replace("", None)
        frame = frame.assign(item_key=make_item_keys(source))
    frame = frame.sort_values(["company", "item_key", "true_item_id"], kind="stable")
    frame = frame.drop_duplicates(["company", "item_key"], keep="first")
    return frame[ITEM_TRUTH_COLUMNS].reset_index(drop=True)


def load_savings_truth(directory: str | Path) -> pd.DataFrame:
    """Read `truth_savings.csv`; flags become bool and the gap becomes float."""
    dtype = {"true_item_id": "str", "cause": "str"}
    frame = _read(Path(directory) / "truth_savings.csv", SAVINGS_TRUTH_COLUMNS, dtype)
    frame = frame[SAVINGS_TRUTH_COLUMNS].copy()
    frame["true_gross_gap_usd"] = pd.to_numeric(frame["true_gross_gap_usd"]).astype(float)
    for flag in ("is_unit_trap", "is_distractor"):
        frame[flag] = _to_bool(frame[flag], flag)
    return frame


def load_truth(directory: str | Path) -> Truth:
    """Load all three truth files from a `data/truth/seed_{n}/` directory."""
    return Truth(
        vendor_map=load_vendor_truth(directory),
        item_map=load_item_truth(directory),
        savings=load_savings_truth(directory),
    )
