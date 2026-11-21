"""Shipped reference data and typed loaders for it.

Every loader reads the packaged file via ``importlib.resources`` and accepts an
optional ``path`` that overrides it (for user-edited copies).
"""

from __future__ import annotations

import csv
import json
import tomllib
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import pandas as pd

__all__ = [
    "Thresholds",
    "UnitFactor",
    "Uom",
    "load_abbreviations",
    "load_column_synonyms",
    "load_descriptor_tokens",
    "load_fx_rates",
    "load_generic_tokens",
    "load_taxonomy",
    "load_thresholds",
    "load_uom",
]

PathLike = str | Path


def _text(name: str, path: PathLike | None) -> str:
    if path is not None:
        return Path(path).read_text(encoding="utf-8")
    return resources.files(__package__).joinpath(name).read_text(encoding="utf-8")


def _rows(name: str, path: PathLike | None) -> list[dict[str, str]]:
    return list(csv.DictReader(_text(name, path).splitlines()))


def load_taxonomy(path: PathLike | None = None) -> pd.DataFrame:
    """Common category taxonomy (PRD 3.4), all columns as strings.

    ``keywords`` stays semicolon-separated, as in the file.
    """
    import io

    return pd.read_csv(io.StringIO(_text("taxonomy.csv", path)), dtype=str, keep_default_na=False)


def load_abbreviations(path: PathLike | None = None) -> dict[str, str]:
    """Whole-token abbreviation dictionary, ``abbr`` -> ``expansion``."""
    return {r["abbr"]: r["expansion"] for r in _rows("abbreviations.csv", path)}


def _tokens(name: str, path: PathLike | None) -> frozenset[str]:
    return frozenset(t.strip() for t in _text(name, path).splitlines() if t.strip())


def load_generic_tokens(path: PathLike | None = None) -> frozenset[str]:
    """Vendor-name tokens removed before fuzzy scoring (PRD 4.3)."""
    return _tokens("generic_tokens.txt", path)


def load_descriptor_tokens(path: PathLike | None = None) -> frozenset[str]:
    """Vendor-name descriptor tokens that cap fuzzy scores (PRD 4.3)."""
    return _tokens("descriptor_tokens.txt", path)


def load_column_synonyms(path: PathLike | None = None) -> dict[str, list[str]]:
    """Lower-case header synonyms per PRD 3.1 column."""
    data = json.loads(_text("column_synonyms.json", path))
    return {k: list(v) for k, v in data.items()}


def load_fx_rates(path: PathLike | None = None) -> dict[str, float]:
    """Fixed FX rates (amount x rate = reporting currency). Illustrative only."""
    return {r["currency"].strip().upper(): float(r["rate"]) for r in _rows("fx_rates.csv", path)}


@dataclass(frozen=True)
class UnitFactor:
    """One fixed-factor unit of measure."""

    base: str
    factor: float
    dimension: str


@dataclass(frozen=True)
class Uom:
    """Unit table: fixed-factor units plus pack units needing a pack quantity."""

    fixed: dict[str, UnitFactor]
    pack_units: tuple[str, ...]


def load_uom(path: PathLike | None = None) -> Uom:
    """Fixed-factor units and pack units (PRD 3.5).

    Pack units are the rows whose ``base`` is ``pack``. ``M`` and ``GR`` are
    ambiguous and are resolved in code, so they are not listed.
    """
    fixed: dict[str, UnitFactor] = {}
    packs: list[str] = []
    for r in _rows("uom.csv", path):
        unit = r["unit"].strip().upper()
        if r["base"] == "pack":
            packs.append(unit)
        else:
            fixed[unit] = UnitFactor(r["base"], float(r["factor"]), r["dimension"])
    return Uom(fixed=fixed, pack_units=tuple(packs))


@dataclass(frozen=True)
class Thresholds:
    """Automatic and review thresholds for vendor and item matching."""

    vendor_auto: float
    vendor_review: float
    item_auto_cosine: float
    item_review_cosine: float


def load_thresholds(path: PathLike | None = None) -> Thresholds:
    """Matching thresholds; tuning overwrites the packaged auto values."""
    data = tomllib.loads(_text("thresholds.toml", path))
    return Thresholds(
        vendor_auto=float(data["vendor"]["auto"]),
        vendor_review=float(data["vendor"]["review"]),
        item_auto_cosine=float(data["item"]["auto_cosine"]),
        item_review_cosine=float(data["item"]["review_cosine"]),
    )
