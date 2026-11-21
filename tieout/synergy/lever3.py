"""Lever 3, payment terms: one-time cash (PRD 5.4).

A group ``g`` is (company, parent vendor), counting only lines of vendor
records linked at tier A or B. For each parent vendor supplying both
companies on terms at least one day apart::

    T_star = min(max(T[acquirer], T[target]), maximum)
    dCash  = sum_g max(0, T_star - T[g]) / 365 x S[g] x pi3

``T[g]`` is spend-weighted: observed days-to-pay when both companies have a
payment date on at least 80% of their spend with the vendor, otherwise
stated terms for both. A vendor where a company has neither is excluded and
listed. ``S[g]`` is the group's spend net of lever 2 and lever 1, per line::

    S[l] = amount - moved - (l1 - l1 moved with it) - amount / C[c] x N2[c]

that is the spend that stays with the vendor after lever 2 moves its share,
less the lever-1 saving that stays with it and the line's spend share of its
category's lever-2 saving. Spend moved *in* under lever 2 is not in any line,
so it never enters ``S``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from tieout.synergy.cube import SpendCube
from tieout.synergy.groups import COMPANIES
from tieout.synergy.lever2 import Lever2Result
from tieout.synergy.settings import CASES

__all__ = [
    "DAYS_PER_YEAR",
    "OBSERVED_COVERAGE",
    "PAYMENT_TERMS_COLUMNS",
    "Lever3Result",
    "S",
    "T_star",
    "delta_cash",
    "lever3",
]

DAYS_PER_YEAR = 365.0
#: Observed days-to-pay need payment dates on at least this share of each company's spend.
OBSERVED_COVERAGE = 0.80
#: Terms closer than this (days) count as identical.
MIN_DIFFERENCE_DAYS = 1.0
LINKED_TIERS = ("A", "B")
NO_STATED = "observed days-to-pay cover less than 80% of spend and stated terms are missing"
NEITHER = "a company has neither stated terms nor payment dates with this vendor"
OFF_MESSAGE = (
    "Neither payment_terms_days nor payment_date is present in a file; "
    "the payment-terms lever (lever 3) is switched off."
)
PAYMENT_TERMS_COLUMNS = [
    "parent_id",
    "company",
    "status",
    "basis",
    "reason",
    "T",
    "T_star",
    "spend",
    "coverage",
    "S_low",
    "S_base",
    "S_high",
    "cash_low",
    "cash_base",
    "cash_high",
]


def T_star(T_acquirer: np.ndarray, T_target: np.ndarray, maximum: float) -> np.ndarray:
    """Target days: the longer of the two terms, capped at the user-set maximum."""
    return np.minimum(np.maximum(T_acquirer, T_target), maximum)


def delta_cash(T_star: np.ndarray, T: np.ndarray, S: np.ndarray, pi3: float) -> np.ndarray:
    """``max(0, T_star - T) / 365 x S x pi3``; no target (NaN) releases nothing."""
    return np.maximum(np.nan_to_num(T_star - T, nan=0.0), 0.0) / DAYS_PER_YEAR * S * pi3


def S(
    spend: np.ndarray,
    moved: np.ndarray,
    l1: np.ndarray,
    l1_moved: np.ndarray,
    l2_share: np.ndarray,
) -> np.ndarray:
    """Spend that stays with the vendor, net of the lever-1 and lever-2 savings on it."""
    return spend - moved - (l1 - l1_moved) - l2_share


@dataclass(frozen=True)
class Lever3Result:
    """Group frame (``PAYMENT_TERMS_COLUMNS``) plus per-line arrays.

    ``line_group`` is each cube line's row in ``groups`` (-1 when not in a
    group); ``line_S`` / ``line_cash`` are the line's share of ``S[g]`` and of
    the group's cash, zero outside contributing groups.
    """

    enabled: bool
    message: str | None
    groups: pd.DataFrame
    line_group: np.ndarray
    line_S: Mapping[str, np.ndarray]
    line_cash: Mapping[str, np.ndarray]


def _weighted(values: np.ndarray, weights: np.ndarray, key: np.ndarray, n: int) -> np.ndarray:
    """Weighted mean of ``values`` per ``key`` over finite values (NaN when none)."""
    ok = np.isfinite(values) & (weights > 0)
    num = np.bincount(key[ok], weights=(values * weights)[ok], minlength=n)
    den = np.bincount(key[ok], weights=weights[ok], minlength=n)
    return np.where(den > 0, num / np.where(den > 0, den, 1.0), np.nan)


def _basis(
    coverage: np.ndarray, observed: np.ndarray, stated: np.ndarray, observed_allowed: bool
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per parent (rows) x company (columns): basis, ``T`` and exclusion reason.

    Observed days need both companies at or above the coverage share; stated
    terms need both companies to have some. Otherwise the vendor is excluded.
    """
    use_observed = observed_allowed & (coverage >= OBSERVED_COVERAGE).all(axis=1)
    has_stated = np.isfinite(stated).all(axis=1)
    has_any = (np.isfinite(stated) | (coverage > 0)).all(axis=1)
    basis = np.where(use_observed, "observed", np.where(has_stated, "stated", "none"))
    T = np.where(use_observed[:, None], observed, stated)
    reason = np.where(
        basis != "none",
        None,
        np.where(has_any, NO_STATED, NEITHER),
    ).astype(object)
    return basis.astype(object), T, reason


def _no_groups(n: int, enabled: bool) -> Lever3Result:
    zeros = {case: np.zeros(n) for case in CASES}
    return Lever3Result(
        enabled=enabled,
        message=None if enabled else OFF_MESSAGE,
        groups=pd.DataFrame(columns=PAYMENT_TERMS_COLUMNS),
        line_group=np.full(n, -1, dtype=np.int64),
        line_S=zeros,
        line_cash=zeros,
    )


def lever3(
    cube: SpendCube,
    l1: Mapping[str, np.ndarray],
    lev2: Lever2Result,
    assumptions: Mapping[str, Any],
    *,
    enabled: bool,
    observed_allowed: bool,
) -> Lever3Result:
    """Cash release per (company, parent vendor) group and per line, in every case."""
    if not enabled:
        return _no_groups(len(cube), enabled=False)
    settings = assumptions["lever3"]
    k = len(COMPANIES)
    n_slots = max(len(cube.parents), 1) * k
    linked = cube.mapped & np.isin(cube.vendor_tier, LINKED_TIERS)
    slot = cube.parent * k + (cube.company == COMPANIES[1])
    positive = np.where(linked, np.maximum(cube.amount, 0.0), 0.0)
    spend = np.bincount(slot, weights=positive, minlength=n_slots).reshape(-1, k)
    shared = np.flatnonzero((spend > 0).all(axis=1))
    if not len(shared):
        return _no_groups(len(cube), enabled=True)

    dated = positive * np.isfinite(cube.pay_days)
    covered = np.bincount(slot, weights=dated, minlength=n_slots).reshape(-1, k)
    coverage = covered / np.where(spend > 0, spend, 1.0)
    observed = _weighted(cube.pay_days, positive, slot, n_slots).reshape(-1, k)
    stated = _weighted(cube.terms, positive, slot, n_slots).reshape(-1, k)
    basis, T, reason = _basis(coverage[shared], observed[shared], stated[shared], observed_allowed)
    differ = np.abs(T[:, 0] - T[:, 1]) >= MIN_DIFFERENCE_DAYS
    status = np.where(
        basis == "none", "excluded", np.where(differ, "opportunity", "identical_terms")
    )
    opportunity = status == "opportunity"
    target = T_star(T[:, 0], T[:, 1], float(settings["max_payment_days"]))
    t_star = np.where(opportunity, target, np.nan)
    T_g, t_star_g = T.ravel(), np.repeat(t_star, k)
    gap = np.maximum(np.nan_to_num(t_star_g - T_g, nan=0.0), 0.0)

    group_of_slot = np.full(n_slots, -1, dtype=np.int64)
    group_of_slot[(shared[:, None] * k + np.arange(k)).ravel()] = np.arange(len(shared) * k)
    line_group = np.where(linked, group_of_slot[slot], -1)
    member = line_group >= 0
    group = np.clip(line_group, 0, None)
    gains = member & (gap[group] > 0)

    l2 = np.where(cube.mapped, cube.l2, 0)
    moved_share = np.where(lev2.moved != 0, lev2.weight, 0.0)
    pi3 = {case: float(settings["capture"][case]) for case in CASES}
    line_S, line_cash, S_group, cash_group = {}, {}, {}, {}
    for case in CASES:
        per_dollar = np.where(lev2.C > 0, lev2.N2[case] / np.where(lev2.C > 0, lev2.C, 1.0), 0.0)
        l2_share = np.where(cube.mapped, cube.amount * per_dollar[l2], 0.0)
        raw = S(cube.amount, lev2.moved, l1[case], moved_share * l1[case], l2_share)
        raw = np.where(gains, raw, 0.0)
        total = np.bincount(line_group[member], weights=raw[member], minlength=len(gap))
        kept = total > 0
        S_group[case] = np.where(kept, total, 0.0)
        line_S[case] = np.where(member & kept[group], raw, 0.0)
        cash_group[case] = delta_cash(t_star_g, T_g, S_group[case], pi3[case])
        line_cash[case] = delta_cash(t_star_g[group], T_g[group], line_S[case], pi3[case])

    groups = pd.DataFrame(
        {
            "parent_id": np.repeat(np.array(cube.parents, dtype=object)[shared], k),
            "company": np.tile(np.array(COMPANIES, dtype=object), len(shared)),
            "status": np.repeat(status, k).astype(object),
            "basis": np.repeat(basis, k),
            "reason": np.repeat(reason, k),
            "T": T_g,
            "T_star": t_star_g,
            "spend": spend[shared].ravel(),
            "coverage": coverage[shared].ravel(),
            **{f"S_{case}": S_group[case] for case in CASES},
            **{f"cash_{case}": cash_group[case] for case in CASES},
        }
    )
    return Lever3Result(
        enabled=True,
        message=None,
        groups=groups[PAYMENT_TERMS_COLUMNS],
        line_group=line_group,
        line_S=line_S,
        line_cash=line_cash,
    )
