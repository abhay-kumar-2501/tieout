"""Helpers that build small raw files for the ingestion tests."""

from __future__ import annotations

import io
from collections.abc import Sequence
from typing import Any

import pandas as pd

from tieout.ingest import load_file

FX = {"USD": 1.0, "CAD": 0.73, "EUR": 1.08, "GBP": 1.27}

BASE: dict[str, Any] = {
    "site": "P1",
    "doc_date": "2024-03-15",
    "vendor_id": "V1",
    "vendor_name": "Acme Fasteners",
    "item_code": "FA-1",
    "item_description": "HEX BOLT M8X40",
    "category_native": "Fasteners",
    "uom": "EA",
    "quantity": "10",
    "unit_price": "5",
    "line_amount": "50",
    "currency": "USD",
}

CATEGORY_MAP = pd.DataFrame(
    {
        "company": ["acquirer", "acquirer", "target", "target"],
        "category_native": ["Fasteners", "Freight", "Fasteners", "Freight"],
        "l2_code": ["L02.01", "L11.01", "L02.01", "L11.01"],
    }
)

Rows = Sequence[dict[str, Any]]


def make_raw(rows: Rows, company: str = "acquirer") -> pd.DataFrame:
    """A raw frame as ``load_file`` would give it, from row overrides of ``BASE``."""
    frame = pd.DataFrame([{**BASE, **row} for row in rows])
    frame = frame.dropna(axis=1, how="all")
    return load_file(io.StringIO(frame.to_csv(index=False)), company)


def many(n: int, **overrides: Any) -> list[dict[str, Any]]:
    """``n`` identical-but-for-po_line rows, so none is a duplicate."""
    return [{**overrides, "po_line": str(i)} for i in range(n)]
