"""Lever 1, price harmonisation, as one function with seven switchable filters (PRD 5.2).

``lever1(inputs, filters, case, assumptions)`` returns every buying group's
contribution. With every filter off (and so every probability at 1) the sum is
the naive figure::

    Naive = sum_k sum_g (p[k,g] - min_h p[k,h]) * q[k,g]

on the naive line set and every match including tier C. Switching the filters
on in the order of the bridge table turns it into the lever-1 net saving::

    G1[k,g] = max(0, p[k,g] - p_star[k]) * q[k,g] * a[k,g]   (other company's groups)
    N1[k]   = sum_g G1[k,g] * pi1[k,g]

1. unit errors: defensible line set (base units, unconverted lines out) and
   items with a suspected unit error or a base-dimension clash out;
2. unverified matches: tier C items out;
3. spot-price benchmark: ``p_star[k]`` (qualifying groups, fallback) in place
   of the absolute minimum price;
4. internal variance: groups of the benchmark holder's company contribute zero;
5. non-comparable terms: groups whose dominant incoterm differs from the
   holder company's (both present, not approved by a reviewer) contribute zero;
6. contract lock-in: quantity multiplied by ``a[k,g]``;
7. capture probability: multiplied by ``pi1[k,g]`` for the case.

The benchmark holder, change type and incoterm test always refer to the
reference price in use: the absolute-minimum group while filter 3 is off,
``p_star`` once it is on.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any

import numpy as np
import pandas as pd

from tieout.synergy.groups import COMPANIES, COMPANY_RANK
from tieout.synergy.settings import CASES, category_table, number_cell

__all__ = [
    "CASES",
    "STEP_NAMES",
    "Filters",
    "Lever1Inputs",
    "Lever1Result",
    "capture_probability",
    "lever1",
]

STEP_NAMES = (
    "Unit-of-measure errors",
    "Unverified matches",
    "Spot-price benchmark",
    "Internal variance",
    "Non-comparable terms",
    "Contract lock-in",
    "Capture probability",
)
#: Prices equal to this many decimal places tie (sums of the same price can differ by an ulp).
PRICE_DECIMALS = 9
#: A gap at or below this share of the reference price is no gap (floating-point noise).
GAP_TOLERANCE = 1e-9
_SHARE_TOLERANCE = 1e-12
_SETTING_COLUMNS = {("same_vendor", case): f"pi1_same_{case}" for case in CASES} | {
    ("switch", case): f"pi1_switch_{case}" for case in CASES
}


@dataclass(frozen=True)
class Filters:
    """The seven bridge filters, in the order of the PRD 5.2 bridge table."""

    unit_errors: bool = True
    unverified_matches: bool = True
    spot_benchmark: bool = True
    internal_variance: bool = True
    incoterms: bool = True
    contract_lock_in: bool = True
    capture_probability: bool = True

    @classmethod
    def through(cls, step: int) -> Filters:
        """Filters 1 to ``step`` on, the rest off (``through(0)`` is the naive figure)."""
        names = [f.name for f in fields(cls)]
        return cls(**{name: i < step for i, name in enumerate(names)})


@dataclass(frozen=True)
class Lever1Inputs:
    """Everything ``lever1`` needs, as arrays over buying groups and items.

    Group arrays are aligned with ``groups`` (the price-groups frame); item
    arrays with ``items`` (the item-facts frame); ``item`` maps a group to its
    item row.
    """

    groups: pd.DataFrame
    items: pd.DataFrame
    item: np.ndarray
    company_rank: np.ndarray
    parent_code: np.ndarray
    supplies: np.ndarray
    incoterm_code: np.ndarray
    holder_incoterm_code: np.ndarray
    l2_index: np.ndarray
    l2_codes: tuple[str, ...]
    a: np.ndarray
    line_test: bool

    @classmethod
    def build(cls, groups: pd.DataFrame, items: pd.DataFrame, line_test: bool) -> Lever1Inputs:
        """Encode the frames once; ``groups`` carries the contract share ``a``.

        ``supplies[g, r]``: group ``g``'s parent vendor also supplies the item
        to company ``r`` (the fallback change-type test).
        """
        item = pd.Index(items["canonical_item_id"]).get_indexer(groups["canonical_item_id"])
        rank = groups["company"].map(COMPANY_RANK).to_numpy(dtype=int)
        parent_code, parents = pd.factorize(groups["parent_id"], sort=True)
        n_parents = max(len(parents), 1)
        existing = np.unique(_supply_key(item, rank, parent_code, n_parents))
        supplies = np.column_stack(
            [
                np.isin(_supply_key(item, np.full_like(rank, r), parent_code, n_parents), existing)
                for r in range(len(COMPANIES))
            ]
        )
        terms = pd.Index(
            sorted(
                set(groups["incoterm"].dropna())
                | set(items["incoterm_acquirer"].dropna())
                | set(items["incoterm_target"].dropna())
            )
        )
        holder_terms = np.column_stack([_codes(terms, items[f"incoterm_{c}"]) for c in COMPANIES])
        l2_index, l2_codes = pd.factorize(groups["l2_code"].astype(object), sort=True)
        return cls(
            groups=groups,
            items=items,
            item=item.astype(np.int64),
            company_rank=rank,
            parent_code=parent_code.astype(np.int64),
            supplies=supplies.reshape(len(groups), len(COMPANIES)),
            incoterm_code=_codes(terms, groups["incoterm"]),
            holder_incoterm_code=holder_terms.reshape(len(items), len(COMPANIES)),
            l2_index=l2_index.astype(np.int64),
            l2_codes=tuple(str(c) for c in l2_codes),
            a=groups["a"].to_numpy(dtype=float),
            line_test=line_test,
        )

    @property
    def n_items(self) -> int:
        return len(self.items)


def _codes(terms: pd.Index, values: pd.Series) -> np.ndarray:
    return terms.get_indexer(values.where(values.notna(), None)).astype(np.int64)


def _supply_key(
    item: np.ndarray, rank: np.ndarray, parent: np.ndarray, n_parents: int
) -> np.ndarray:
    return (item.astype(np.int64) * len(COMPANIES) + rank) * n_parents + parent


@dataclass(frozen=True)
class Lever1Result:
    """Per-group working of one ``lever1`` evaluation.

    ``contribution`` is each group's dollars; the figure is its sum. The other
    arrays show the working: the reference price, the holder (company rank
    and group row, -1 in the fallback case), the change type and which
    filters zeroed the group.
    """

    filters: Filters
    contribution: np.ndarray
    priced: np.ndarray
    reference: np.ndarray
    holder_rank: np.ndarray
    holder_group: np.ndarray
    fallback: np.ndarray
    same_vendor: np.ndarray
    internal: np.ndarray
    mismatch_raw: np.ndarray
    mismatch: np.ndarray
    pi: np.ndarray

    @property
    def total(self) -> float:
        return float(self.contribution.sum())

    @property
    def change_type(self) -> np.ndarray:
        """``same_vendor`` / ``switch`` per priced group, ``None`` otherwise."""
        labels = np.where(self.same_vendor, "same_vendor", "switch").astype(object)
        labels[~self.priced] = None
        return labels


@dataclass(frozen=True)
class _Benchmark:
    reference: np.ndarray  # per item
    holder_rank: np.ndarray  # per item, -1 when the item has no priced group
    holder_group: np.ndarray  # per item, -1 in the fallback case
    fallback: np.ndarray  # per item


def lever1(
    inputs: Lever1Inputs, filters: Filters, case: str, assumptions: Mapping[str, Any]
) -> Lever1Result:
    """Each buying group's lever-1 contribution under ``filters`` in ``case`` (PRD 5.2)."""
    if case not in CASES:
        raise ValueError(f"case must be one of {CASES}, got {case!r}")
    g = inputs.groups
    if filters.unit_errors:
        price, qty = g["p"].to_numpy(), g["q"].to_numpy()
        amount, lines = g["amount"].to_numpy(), g["n_lines"].to_numpy()
    else:
        price, qty = g["naive_price"].to_numpy(), g["naive_qty"].to_numpy()
        amount, lines = g["naive_amount"].to_numpy(), g["naive_lines"].to_numpy()
    item = inputs.item
    item_ok = _items_in_scope(inputs, filters, qty)
    priced = item_ok[item] & (qty > 0) & np.isfinite(price) & (price > 0)

    settings = assumptions["benchmark"]
    bench = _benchmark(
        inputs,
        price,
        qty,
        amount,
        lines,
        priced,
        qualified_only=filters.spot_benchmark,
        min_share=float(settings["min_volume_share"]),
        min_lines=int(settings["min_lines"]),
    )
    reference = np.where(priced, bench.reference[item], np.nan)
    gap = np.where(priced, np.maximum(price - reference, 0.0), 0.0)
    gap[gap <= GAP_TOLERANCE * np.nan_to_num(reference)] = 0.0

    holder_rank = np.where(priced, bench.holder_rank[item], -1)
    holder_group = np.where(priced, bench.holder_group[item], -1)
    fallback = priced & bench.fallback[item]
    same_vendor = _same_vendor(inputs, priced, holder_rank, holder_group)
    internal = priced & (inputs.company_rank == holder_rank)
    holder_term = inputs.holder_incoterm_code[item, np.clip(holder_rank, 0, None)]
    mismatch_raw = (
        priced
        & (inputs.incoterm_code >= 0)
        & (holder_term >= 0)
        & (inputs.incoterm_code != holder_term)
    )
    approved = inputs.items["incoterm_approved"].to_numpy(dtype=bool)[item]
    mismatch = mismatch_raw & ~approved
    pi = capture_probability(assumptions, inputs, same_vendor, case)

    contribution = gap * qty
    if filters.internal_variance:
        contribution = np.where(internal, 0.0, contribution)
    if filters.incoterms:
        contribution = np.where(mismatch, 0.0, contribution)
    if filters.contract_lock_in:
        contribution = contribution * inputs.a
    if filters.capture_probability:
        contribution = contribution * pi
    return Lever1Result(
        filters=filters,
        contribution=contribution,
        priced=priced,
        reference=reference,
        holder_rank=holder_rank,
        holder_group=holder_group,
        fallback=fallback,
        same_vendor=same_vendor,
        internal=internal,
        mismatch_raw=mismatch_raw,
        mismatch=mismatch,
        pi=pi,
    )


def _items_in_scope(inputs: Lever1Inputs, filters: Filters, qty: np.ndarray) -> np.ndarray:
    """Items in the comparison: filters 1 and 2, and net quantity above zero (PRD 10.1)."""
    items = inputs.items
    ok = np.ones(inputs.n_items, dtype=bool)
    if filters.unit_errors:
        ok &= ~items["unit_excluded"].to_numpy(dtype=bool)
    if filters.unverified_matches:
        ok &= ~items["pending"].to_numpy(dtype=bool)
    net = np.bincount(inputs.item, weights=qty, minlength=inputs.n_items)
    return ok & (net > 0)


def _benchmark(
    inputs: Lever1Inputs,
    price: np.ndarray,
    qty: np.ndarray,
    amount: np.ndarray,
    lines: np.ndarray,
    priced: np.ndarray,
    *,
    qualified_only: bool,
    min_share: float,
    min_lines: int,
) -> _Benchmark:
    """The reference price per item and who holds it.

    Without ``qualified_only`` it is the lowest price of any priced group.
    With it, ``p_star``: the lowest price among groups holding at least
    ``min_share`` (inclusive) of the item's combined quantity and, unless the
    line test is skipped, at least ``min_lines`` purchase lines. Ties go to the
    larger quantity, then the acquirer, then the group key. When no group
    qualifies, the fallback is the lower company-level volume-weighted price.
    """
    n = inputs.n_items
    item, rank = inputs.item, inputs.company_rank
    candidate = priced.copy()
    if qualified_only:
        combined = np.bincount(item, weights=np.where(priced, qty, 0.0), minlength=n)
        share = np.where(priced, qty / np.where(combined > 0, combined, 1.0)[item], 0.0)
        candidate &= share >= min_share * (1 - _SHARE_TOLERANCE)
        if inputs.line_test:
            candidate &= lines >= min_lines

    reference = np.full(n, np.nan)
    holder_rank = np.full(n, -1, dtype=np.int64)
    holder_group = np.full(n, -1, dtype=np.int64)
    rows = np.flatnonzero(candidate)
    order = np.lexsort(
        (rows, rank[rows], -qty[rows], np.round(price[rows], PRICE_DECIMALS), item[rows])
    )
    ranked = rows[order]
    first_items, first = np.unique(item[ranked], return_index=True)
    best = ranked[first]
    reference[first_items] = price[best]
    holder_rank[first_items] = rank[best]
    holder_group[first_items] = best

    has_priced = np.bincount(item[priced], minlength=n) > 0
    fallback = has_priced & (holder_group < 0)
    if fallback.any():
        ref, holder = _company_fallback(inputs, qty, amount, priced)
        reference[fallback] = ref[fallback]
        holder_rank[fallback] = holder[fallback]
    return _Benchmark(reference, holder_rank, holder_group, fallback)


def _company_fallback(
    inputs: Lever1Inputs, qty: np.ndarray, amount: np.ndarray, priced: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Lower company-level volume-weighted price per item; ties: larger quantity, acquirer."""
    n, k = inputs.n_items, len(COMPANIES)
    slot = inputs.item * k + inputs.company_rank
    total_qty = np.bincount(slot, weights=np.where(priced, qty, 0.0), minlength=n * k)
    total_amount = np.bincount(slot, weights=np.where(priced, amount, 0.0), minlength=n * k)
    with np.errstate(divide="ignore", invalid="ignore"):
        company_price = np.where(total_qty > 0, total_amount / total_qty, np.inf).reshape(n, k)
    total_qty = total_qty.reshape(n, k)
    key = np.round(company_price, PRICE_DECIMALS)
    target_wins = (key[:, 1] < key[:, 0]) | (
        (key[:, 1] == key[:, 0]) & (total_qty[:, 1] > total_qty[:, 0])
    )
    holder = target_wins.astype(np.int64)
    return company_price[np.arange(n), holder], holder


def _same_vendor(
    inputs: Lever1Inputs, priced: np.ndarray, holder_rank: np.ndarray, holder_group: np.ndarray
) -> np.ndarray:
    """Group's parent vendor is the benchmark group's (fallback: also supplies the holder)."""
    has_group = holder_group >= 0
    benchmark_parent = inputs.parent_code[np.where(has_group, holder_group, 0)]
    rows = np.arange(len(holder_rank))
    supplies = inputs.supplies[rows, np.clip(holder_rank, 0, None)]
    return priced & np.where(has_group, inputs.parent_code == benchmark_parent, supplies)


def capture_probability(
    assumptions: Mapping[str, Any], inputs: Lever1Inputs, same_vendor: np.ndarray, case: str
) -> np.ndarray:
    """``pi1[k,g]`` per group: category setting, else the global value (PRD 5.1 lookup order).

    ``assumptions["category_settings"]`` (optional) maps an ``l2_code`` to its
    ``category_settings.csv`` row, as a mapping or a frame with an ``l2_code``
    column; a blank or missing cell falls back to ``assumptions["lever1"]``.
    """
    settings = category_table(assumptions.get("category_settings"))
    by_change = {}
    for change in ("same_vendor", "switch"):
        default = float(assumptions["lever1"][change][case])
        column = _SETTING_COLUMNS[(change, case)]
        values = [number_cell(settings.get(code, {}).get(column)) for code in inputs.l2_codes]
        per_l2 = np.array([default if np.isnan(v) else v for v in values] + [default])
        by_change[change] = per_l2[inputs.l2_index]  # index -1 (no category): the default
    return np.where(same_vendor, by_change["same_vendor"], by_change["switch"])
