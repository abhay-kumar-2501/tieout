"""Unit-of-measure conversion and suspected unit errors (PRD 3.5).

:func:`convert_units` adds ``base_unit``, ``base_factor``, ``conv_status``,
``qty_base`` and ``price_base`` to a ``lines`` frame. :func:`flag_unit_errors`
implements the "Suspected unit errors" rule over a small per-item frame that
the item-matching step builds.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from tieout.normalise.packs import parse_pack_qty
from tieout.reference import Uom, load_uom

__all__ = [
    "BASE_DIMENSION",
    "PACK_FACTORS",
    "STATUS_ORDER",
    "base_dimension",
    "combine_status",
    "convert_units",
    "flag_unit_errors",
]

#: Base unit of each dimension.
DIMENSION_BASE = {
    "count": "each",
    "length": "metre",
    "mass": "kilogram",
    "volume": "litre",
    "time": "hour",
}
BASE_DIMENSION = {base: dim for dim, base in DIMENSION_BASE.items()}
#: Units that already are a base unit (including the US spellings).
_BASE_ALIASES = {
    "EACH": ("each", 1.0),
    "METRE": ("metre", 1.0),
    "METER": ("metre", 1.0),
    "KILOGRAM": ("kilogram", 1.0),
    "LITRE": ("litre", 1.0),
    "LITER": ("litre", 1.0),
    "HOUR": ("hour", 1.0),
}
#: Ambiguous units: (unit, uom_dimension) -> (base, factor).
_AMBIGUOUS = {
    ("M", "length"): ("metre", 1.0),
    ("M", "count"): ("each", 1000.0),
    ("GR", "mass"): ("kilogram", 0.001),
    ("GR", "count"): ("each", 144.0),
}
_PPE_FAMILY = "ppe"

#: Price ratios that suggest a pack size (PRD 3.5).
PACK_FACTORS = (2, 4, 5, 6, 8, 10, 12, 20, 24, 25, 48, 50, 100, 144, 1000)
RATIO_TOLERANCE = 0.03
LARGE_RATIO = 3.0
_EPS = 1e-9

#: Worst-to-best order of conversion statuses.
STATUS_ORDER = {"unconverted": 0, "parsed": 1, "confirmed": 2}


def base_dimension(base_unit: str | None) -> str | None:
    """Dimension of a base unit, or ``None``."""
    return BASE_DIMENSION.get(base_unit) if base_unit else None


def _upper(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.upper().astype(object)


def convert_units(lines: pd.DataFrame, uom: Uom | None = None) -> pd.DataFrame:
    """Return ``lines`` with unit conversion columns added.

    Needs ``uom``, ``pack_qty``, ``item_description``, ``family``,
    ``uom_dimension``, ``item_key``, ``quantity_ann`` and ``unit_price_rc``.
    Lines without an item (``item_key`` is ``None``) get status ``none``.
    """
    table = uom or load_uom()
    unit = _upper(lines["uom"])
    dimension = lines["uom_dimension"].astype(object)
    family = lines["family"].astype(object)
    n = len(lines)

    base = np.full(n, None, dtype=object)
    factor = np.full(n, np.nan)
    status = np.full(n, "unconverted", dtype=object)

    def assign(
        mask: np.ndarray, base_unit: object, value: object, label: str = "confirmed"
    ) -> None:
        base[mask] = base_unit
        factor[mask] = value
        status[mask] = label

    fixed = {u: (f.base, f.factor) for u, f in table.fixed.items()}
    fixed.update(_BASE_ALIASES)
    for code, (base_unit, value) in fixed.items():
        mask = (unit == code).to_numpy(dtype=bool)
        if code == "PR":
            ppe = (family == _PPE_FAMILY).to_numpy(dtype=bool)
            assign(mask & ppe, base_unit, 1.0)
            mask = mask & ~ppe
        assign(mask, base_unit, value)

    for (code, dim), (base_unit, value) in _AMBIGUOUS.items():
        mask = ((unit == code) & (dimension == dim)).to_numpy(dtype=bool)
        assign(mask, base_unit, value)

    pack_unit = unit.isin(table.pack_units).to_numpy(dtype=bool)
    pack_base = dimension.map(DIMENSION_BASE).astype(object)
    known_base = pack_base.notna().to_numpy(dtype=bool)
    stated = pd.to_numeric(lines["pack_qty"], errors="coerce").to_numpy(dtype=float)
    from_column = pack_unit & known_base & np.isfinite(stated) & (stated > 0)
    base[from_column] = pack_base.to_numpy(dtype=object)[from_column]
    factor[from_column] = stated[from_column]
    status[from_column] = "confirmed"

    todo = pack_unit & known_base & ~from_column
    if todo.any():
        descriptions = lines["item_description"].astype(object)
        parsed = {d: parse_pack_qty(d) for d in descriptions[todo].dropna().unique()}
        qty = descriptions.map(parsed).astype(float).to_numpy()
        from_text = todo & np.isfinite(qty)
        base[from_text] = pack_base.to_numpy(dtype=object)[from_text]
        factor[from_text] = qty[from_text]
        status[from_text] = "parsed"

    no_item = lines["item_key"].isna().to_numpy(dtype=bool)
    status[no_item] = "none"
    base[no_item] = None
    factor[no_item] = np.nan
    unresolved = status == "unconverted"
    base[unresolved] = None
    factor[unresolved] = np.nan

    out = lines.copy()
    out["base_unit"] = pd.Series(base, index=lines.index, dtype=object)
    out["base_factor"] = factor
    out["conv_status"] = pd.Series(status, index=lines.index, dtype=object)
    out["qty_base"] = out["quantity_ann"] * out["base_factor"]
    out["price_base"] = out["unit_price_rc"] / out["base_factor"]
    return out


def combine_status(statuses: pd.Series) -> str:
    """The worst conversion status in ``statuses`` (``none`` values are ignored)."""
    ranked = [s for s in statuses if s in STATUS_ORDER]
    return min(ranked, key=STATUS_ORDER.__getitem__) if ranked else "none"


def flag_unit_errors(items: pd.DataFrame) -> pd.DataFrame:
    """Flag suspected unit errors for matched items (PRD 3.5).

    ``items`` has one row per matched item with columns ``price_a`` and
    ``price_b`` (volume-weighted converted prices per base unit, NaN where
    unconverted), ``recorded_a`` and ``recorded_b`` (volume-weighted prices per
    recorded unit) and ``status_a`` and ``status_b`` (conversion status per
    side). The ratio ``r`` (higher / lower) uses converted prices when both
    sides converted and recorded prices otherwise.

    Returns the input index with ``ratio``, ``factor`` (the matched pack factor
    or NaN), ``rule`` (``"a"``, ``"b"`` or ``None``), ``flagged`` and
    ``message`` (empty when not flagged). Rule (a) needs ``r`` within +-3%
    (inclusive) of a pack factor and a side that is not ``confirmed``; rule (b)
    is ``r`` >= 3.0 whatever the status.
    """
    status_a, status_b = items["status_a"], items["status_b"]
    unconverted = (status_a == "unconverted") | (status_b == "unconverted")
    price_a = items["recorded_a"].where(unconverted, items["price_a"]).astype(float)
    price_b = items["recorded_b"].where(unconverted, items["price_b"]).astype(float)
    valid = (price_a > 0) & (price_b > 0) & np.isfinite(price_a) & np.isfinite(price_b)
    high = np.maximum(price_a, price_b)
    low = np.minimum(price_a, price_b)
    ratio = (high / low).where(valid)

    factors = np.array(PACK_FACTORS, dtype=float)
    deviation = np.abs(ratio.to_numpy()[:, None] / factors[None, :] - 1.0)
    deviation = np.where(np.isnan(deviation), np.inf, deviation)
    best = deviation.argmin(axis=1)  # first minimum: the smaller factor on ties
    near = deviation[np.arange(len(items)), best] <= RATIO_TOLERANCE + _EPS
    unconfirmed = ((status_a != "confirmed") | (status_b != "confirmed")).to_numpy(dtype=bool)
    rule_a = near & unconfirmed & valid.to_numpy(dtype=bool)
    rule_b = (ratio >= LARGE_RATIO - _EPS).to_numpy(dtype=bool)

    matched = np.where(rule_a, factors[best], np.nan)
    rule = pd.Series(
        np.where(rule_a, "a", np.where(rule_b, "b", None)), index=items.index, dtype=object
    )
    messages = [
        f"This {r:.1f}× price gap looks like a pack of {int(f)}, not a saving"
        if a
        else f"This {r:.1f}× gap is too large to be a price difference; check units"
        if b
        else ""
        for r, f, a, b in zip(ratio.to_numpy(), matched, rule_a, rule_b, strict=True)
    ]
    return pd.DataFrame(
        {
            "ratio": ratio.to_numpy(),
            "factor": matched,
            "rule": rule,
            "flagged": rule_a | rule_b,
            "message": messages,
        },
        index=items.index,
    )
