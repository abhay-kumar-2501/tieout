"""Shared pieces of the view functions: view modes, number formats and display labels.

**Numbers (PRD 6.11).** Headline figures are a range with one shared unit,
each end rounded to the nearest $1M when the upper end is $10M or more and to
the nearest $0.1M otherwise (``$8–12M``); tables round to the nearest thousand
(``$184k``); unit prices show four decimals; percentages one decimal; negative
values carry a minus sign, never brackets.

**Integration-office view (PRD 6.9).** Implemented here once for every view:
parent vendors become codes (``Vendor 017``) numbered by descending combined
spend and fixed for the run; categories with fewer than three parent vendors
are merged into "Other"; unit prices, item-level detail and source rows are
not shown, and views that cannot be aggregated return :data:`NOT_IN_VIEW`.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Any

import pandas as pd

from tieout.reference import load_taxonomy

if TYPE_CHECKING:
    from tieout.results import Results

__all__ = [
    "CLEAN",
    "MASKED",
    "MINUS",
    "NOT_IN_VIEW",
    "OTHER",
    "UNMAPPED",
    "Unavailable",
    "category_label",
    "category_labels",
    "item_labels",
    "money",
    "money_range",
    "parent_labels",
    "percent",
    "resolve_view",
    "thousands",
    "unit_price",
    "vendor_codes",
]

CLEAN = "clean"
MASKED = "masked"
MINUS = "−"
OTHER = "Other"
UNMAPPED = "Unmapped"
MIN_PARENTS = 3  # categories with fewer parent vendors merge into "Other" when masked
_MILLION = 1e6
_TEN_MILLION = 1e7


@dataclass(frozen=True)
class Unavailable:
    """What a view returns when the active view mode, or the data, does not allow it."""

    message: str


NOT_IN_VIEW = Unavailable("Not available in the integration-office view.")


def resolve_view(results: Results, view: str | None) -> str:
    """``view`` when given, else the run's own view mode (``meta["view"]``)."""
    mode = view or str(results.meta.get("view", CLEAN))
    if mode not in (CLEAN, MASKED):
        raise ValueError(f"view must be {CLEAN!r} or {MASKED!r}, got {mode!r}")
    return mode


# ---------------------------------------------------------------- numbers


def _sign(value: float) -> str:
    return MINUS if value < 0 else ""


def _clean_zero(value: float) -> float:
    return 0.0 if value == 0 else value  # -0.0 shows as 0


def money_range(low: float, high: float) -> str:
    """A headline range with one shared unit: ``$8–12M`` or ``$6.3–9.6M`` (PRD 6.11)."""
    step, decimals = (1.0, 0) if max(abs(low), abs(high)) >= _TEN_MILLION else (0.1, 1)
    ends = [_clean_zero(round(v / _MILLION / step) * step) for v in (low, high)]
    texts = [f"{abs(e):,.{decimals}f}" for e in ends]
    if ends[0] == ends[1]:
        return f"{_sign(ends[0])}${texts[0]}M"
    if ends[0] >= 0:
        return f"${texts[0]}–{texts[1]}M"
    return f"{_sign(ends[0])}${texts[0]}M–{_sign(ends[1])}${texts[1]}M"


def money(value: float) -> str:
    """A single headline figure: nearest $1M from $10M up, else nearest $0.1M."""
    return money_range(value, value)


def thousands(value: float) -> str:
    """A table figure to the nearest thousand: ``$184k``, ``−$12k``."""
    rounded = _clean_zero(round(value / 1_000))
    return f"{_sign(rounded)}${abs(rounded):,.0f}k"


def percent(share: float) -> str:
    """A share as a percentage with one decimal: ``1.8%``."""
    value = _clean_zero(round(share * 100, 1))
    return f"{_sign(value)}{abs(value):.1f}%"


def unit_price(value: float) -> str:
    """A unit price with four decimals (clean-team view only)."""
    if value is None or math.isnan(value):
        return ""
    return f"{_sign(value)}${abs(value):,.4f}"


# ---------------------------------------------------------------- labels


@lru_cache(maxsize=1)
def _l2_names() -> dict[str, str]:
    taxonomy = load_taxonomy()
    return dict(zip(taxonomy["l2_code"], taxonomy["l2_name"], strict=True))


def _parent_spend(results: Results) -> pd.Series:
    """Combined in-scope spend per parent vendor, largest first (ties by id)."""
    lines = results.lines
    spend = lines.groupby("parent_id", sort=True)["amount"].sum()
    frame = spend.rename("spend").reset_index()
    frame = frame.sort_values(["spend", "parent_id"], ascending=[False, True], kind="mergesort")
    return frame.set_index("parent_id")["spend"]


def vendor_codes(results: Results) -> dict[str, str]:
    """``parent_id`` -> ``Vendor 017``, numbered by descending combined spend (PRD 6.9)."""
    order = _parent_spend(results).index
    width = max(3, len(str(len(order))))
    return {parent: f"Vendor {n:0{width}d}" for n, parent in enumerate(order, start=1)}


def parent_labels(results: Results, view: str) -> dict[str, str]:
    """Display name per parent vendor: its largest record's name, or its code when masked."""
    if view == MASKED:
        return vendor_codes(results)
    vendors = results.vendor_map.sort_values(
        ["parent_id", "spend", "vendor_key"], ascending=[True, False, True], kind="mergesort"
    )
    first = vendors.drop_duplicates("parent_id")
    return dict(zip(first["parent_id"], first["vendor_name"], strict=True))


def category_labels(results: Results, view: str) -> dict[str, str]:
    """``l2_code`` -> display label; masked, thin categories (< 3 parent vendors) are "Other"."""
    names = _l2_names()
    lines = results.lines.dropna(subset=["l2_code"])
    codes = sorted(set(lines["l2_code"]))
    labels = {code: f"{code} {names.get(code, '')}".strip() for code in codes}
    if view == CLEAN:
        return labels
    positive = lines.groupby(["l2_code", "parent_id"])["amount"].sum() > 0
    parents = positive.groupby(level="l2_code").sum()
    return {code: labels[code] if parents.get(code, 0) >= MIN_PARENTS else OTHER for code in codes}


def category_label(labels: Mapping[str, str], l2_code: Any) -> str:
    """The label of ``l2_code`` (``Unmapped`` for a blank code)."""
    if l2_code is None or (isinstance(l2_code, float) and math.isnan(l2_code)):
        return UNMAPPED
    return labels.get(str(l2_code), str(l2_code))


def item_labels(results: Results) -> dict[str, str]:
    """``canonical_item_id`` -> the description of its acquirer record (else the target's)."""
    items = results.item_map.sort_values(
        ["canonical_item_id", "company", "item_record_id"], kind="mergesort"
    )
    first = items.drop_duplicates("canonical_item_id")
    return dict(zip(first["canonical_item_id"], first["description"].fillna(""), strict=True))
