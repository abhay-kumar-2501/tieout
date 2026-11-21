"""Per-category settings and their lookup order (PRD 3.2, 5.1).

A per-category value is looked up in ``category_settings.csv`` first, then in
the global assumptions, then in the taxonomy default. ``assumptions
["category_settings"]`` (optional) holds the file: a mapping or a frame keyed
by ``l2_code`` with the file's column names; a blank or missing cell means
"use the default".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

__all__ = [
    "CASES",
    "CRITICALITIES",
    "DEFAULT_CRITICALITY",
    "CategoryParams",
    "category_params",
    "category_table",
    "number_cell",
]

CASES = ("low", "base", "high")
CRITICALITIES = ("critical", "standard", "non_critical")
DEFAULT_CRITICALITY = "standard"


def category_table(raw: object) -> dict[str, Mapping[str, object]]:
    """``assumptions["category_settings"]`` as ``l2_code`` -> row (``{}`` when absent)."""
    if raw is None:
        return {}
    if isinstance(raw, pd.DataFrame):
        frame = raw.set_index("l2_code")
        return {str(k): row.dropna().to_dict() for k, row in frame.iterrows()}
    if isinstance(raw, Mapping):
        return {str(k): dict(v) for k, v in raw.items()}
    raise TypeError("category_settings must be a mapping or a data frame")


def number_cell(value: object) -> float:
    """A category-settings cell as a number; blank means "use the default" (NaN)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return float("nan")
    return float(value)  # type: ignore[arg-type]


def _text_cell(value: object) -> str | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class CategoryParams:
    """Effective per-category values, aligned with ``l2_codes``."""

    l2_codes: tuple[str, ...]
    criticality: np.ndarray
    category_type: np.ndarray
    cap: np.ndarray
    d: np.ndarray
    pi2: Mapping[str, np.ndarray]


def category_params(
    l2_codes: Sequence[str],
    category_type: Mapping[str, str | None],
    criticality: Mapping[str, str],
    assumptions: Mapping[str, Any],
) -> CategoryParams:
    """Criticality, cap ``cap[c]``, discount ``d[c]`` and ``pi2[c]`` per case for each L2.

    Criticality: settings file, else the taxonomy, else ``standard``. Cap:
    settings file, else the global cap for the criticality. ``d``: settings
    file, else the global discount for the category type (0 when the type is
    unknown). ``pi2``: settings file, else the global triple.
    """
    table = category_table(assumptions.get("category_settings"))
    rows = [table.get(code, {}) for code in l2_codes]
    crit = [
        _text_cell(row.get("criticality")) or criticality.get(code) or DEFAULT_CRITICALITY
        for code, row in zip(l2_codes, rows, strict=True)
    ]
    unknown = sorted(set(crit) - set(CRITICALITIES))
    if unknown:
        raise ValueError(f"criticality must be one of {CRITICALITIES}, got {unknown}")
    caps = assumptions["caps"]
    discounts = assumptions["lever2"]["discount"]
    types = [category_type.get(code) for code in l2_codes]

    def pick(column: str, defaults: Sequence[float]) -> np.ndarray:
        values = [number_cell(row.get(column)) for row in rows]
        return np.array(
            [default if np.isnan(v) else v for v, default in zip(values, defaults, strict=True)],
            dtype=float,
        )

    capture = assumptions["lever2"]["capture"]
    return CategoryParams(
        l2_codes=tuple(l2_codes),
        criticality=np.array(crit, dtype=object),
        category_type=np.array(types, dtype=object),
        cap=pick("cap", [float(caps[c]) for c in crit]),
        d=pick("d", [float(discounts.get(t, 0.0)) if t else 0.0 for t in types]),
        pi2={case: pick(f"pi2_{case}", [float(capture[case])] * len(l2_codes)) for case in CASES},
    )
