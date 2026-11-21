"""Column-mapping suggestions (PRD 2.3).

An exact match against the synonym list wins; otherwise the best
``token_sort_ratio`` of at least 80 against the schema names. Each schema field
is suggested for at most one header, deterministically in file order.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from rapidfuzz import fuzz

from tieout.ingest.schema import COLUMNS, required_columns
from tieout.reference import load_column_synonyms

__all__ = [
    "FUZZY_THRESHOLD",
    "ColumnSuggestion",
    "missing_required",
    "suggest_mapping",
    "to_mapping",
]

FUZZY_THRESHOLD = 80.0


@dataclass(frozen=True)
class ColumnSuggestion:
    """The suggested schema field for one of the user's headers."""

    header: str
    field: str | None
    method: str  # "exact", "fuzzy" or "none"
    score: float


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(text).lower()).split())


def suggest_mapping(
    headers: Sequence[str], synonyms: Mapping[str, Iterable[str]] | None = None
) -> list[ColumnSuggestion]:
    """One suggestion per header, in header order."""
    table = synonyms if synonyms is not None else load_column_synonyms()
    lookup: dict[str, str] = {}
    for field in COLUMNS:
        for synonym in (*table.get(field, ()), field):
            lookup.setdefault(_norm(synonym), field)

    chosen: dict[int, ColumnSuggestion] = {}
    taken: set[str] = set()
    for i, header in enumerate(headers):
        field = lookup.get(_norm(header))
        if field is not None and field not in taken:
            taken.add(field)
            chosen[i] = ColumnSuggestion(header, field, "exact", 100.0)

    candidates: list[tuple[float, int, int]] = []
    for i, header in enumerate(headers):
        if i in chosen:
            continue
        for j, field in enumerate(COLUMNS):
            if field in taken:
                continue
            score = float(fuzz.token_sort_ratio(_norm(header), _norm(field)))
            if score >= FUZZY_THRESHOLD:
                candidates.append((-score, i, j))
    for neg_score, i, j in sorted(candidates):
        field = COLUMNS[j]
        if i not in chosen and field not in taken:
            taken.add(field)
            chosen[i] = ColumnSuggestion(headers[i], field, "fuzzy", -neg_score)

    return [chosen.get(i, ColumnSuggestion(h, None, "none", 0.0)) for i, h in enumerate(headers)]


def to_mapping(suggestions: Iterable[ColumnSuggestion]) -> dict[str, str]:
    """``{header: field}`` for the suggestions that found a field."""
    return {s.header: s.field for s in suggestions if s.field is not None}


def missing_required(
    mapped_fields: Iterable[str], *, aggregated: bool = False, has_items: bool = True
) -> list[str]:
    """Required schema fields that no header maps to, in schema order.

    ``uom`` is conditionally required (needed when rows carry item codes or
    MPNs), so it is listed only when ``has_items`` is true.
    """
    present = set(mapped_fields)
    needed = list(required_columns(aggregated))
    if has_items:
        needed.append("uom")
    return [c for c in COLUMNS if c in needed and c not in present]
