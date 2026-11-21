"""Lever 2, volume consolidation (PRD 5.3).

For each qualifying L2 category ``c`` (both companies have spend, at least two
parent vendors)::

    f     = clamp((cap x C - P) / M, 0, 1)
    B2[c] = P_eligible + f x M - L1        (0 when f = 0)
    N2[c] = B2[c] x d[c] x pi2[c]

``M`` and ``P_eligible`` leave out lines of lever-1 ``switch`` opportunities;
``L1`` is the lever-1 saving, in the same case, on ``P_eligible`` and on the
moved fraction of ``M``, so lever-1 savings travel with the spend that moves.

Everything is also kept per line: a line's *weight* is 1 for the preferred
vendor's eligible lines, ``f`` for the other vendors' eligible lines and 0
otherwise, and its share of ``B2`` is ``weight x (amount - lever-1 saving)``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from tieout.synergy.cube import SpendCube
from tieout.synergy.groups import COMPANY_RANK
from tieout.synergy.settings import CASES, CategoryParams

__all__ = ["B2", "N2", "Lever2Result", "f", "lever2", "preferred_vendors"]

QUALIFIES = "qualifies"
ONE_COMPANY = "one_company"
SINGLE_VENDOR = "single_vendor"


def f(cap: np.ndarray, C: np.ndarray, P: np.ndarray, M: np.ndarray) -> np.ndarray:
    """Moved fraction ``clamp((cap x C - P) / M, 0, 1)``; 0 when nothing can move (``M <= 0``)."""
    safe = np.where(M > 0, M, 1.0)
    return np.where(M > 0, np.clip((cap * C - P) / safe, 0.0, 1.0), 0.0)


def B2(
    P_eligible: np.ndarray,
    f: np.ndarray,
    M: np.ndarray,
    L1: np.ndarray,
) -> np.ndarray:
    """``P_eligible + f x M - L1``, zero when ``f = 0`` and never negative."""
    return np.where(f > 0, np.maximum(P_eligible + f * M - L1, 0.0), 0.0)


def N2(B2: np.ndarray, d: np.ndarray, pi2: np.ndarray) -> np.ndarray:
    """``B2 x d x pi2``."""
    return B2 * d * pi2


@dataclass(frozen=True)
class Lever2Result:
    """Per-category arrays (aligned with ``cube.l2_codes``) and per-line arrays.

    ``reason`` is ``qualifies``, ``one_company`` or ``single_vendor``;
    ``preferred`` is a parent code (-1 when the category does not qualify).
    ``eligible`` marks the lines lever 2 rests on (the preferred vendor's and
    the other vendors' eligible lines in qualifying categories); ``moved`` is
    the spend each line moves to the preferred vendor (``f x amount``).
    """

    reason: np.ndarray
    preferred: np.ndarray
    C: np.ndarray
    P: np.ndarray
    P_eligible: np.ndarray
    M: np.ndarray
    f: np.ndarray
    B2: Mapping[str, np.ndarray]
    N2: Mapping[str, np.ndarray]
    eligible: np.ndarray
    weight: np.ndarray
    moved: np.ndarray
    line_B2: Mapping[str, np.ndarray]
    line_N2: Mapping[str, np.ndarray]

    @property
    def qualifies(self) -> np.ndarray:
        return self.reason == QUALIFIES


def _per_l2(cube: SpendCube, values: np.ndarray, mask: np.ndarray) -> np.ndarray:
    return np.bincount(cube.l2[mask], weights=values[mask], minlength=len(cube.l2_codes)).astype(
        float
    )


def _vendor_spend(cube: SpendCube, mask: np.ndarray) -> np.ndarray:
    """Net spend per (category, parent vendor) as an ``(n_l2, n_parents)`` array."""
    n_l2, n_par = len(cube.l2_codes), max(len(cube.parents), 1)
    key = cube.l2[mask] * n_par + cube.parent[mask]
    spend = np.bincount(key, weights=cube.amount[mask], minlength=n_l2 * n_par)
    return spend.reshape(n_l2, n_par)


def preferred_vendors(
    cube: SpendCube, spend: np.ndarray, overrides: Mapping[str, str]
) -> np.ndarray:
    """Parent code per category: the user's choice when it has spend there, else the largest.

    Ties go to the smaller parent id (parents are coded in sorted order).
    """
    preferred = np.argmax(spend, axis=1) if spend.size else np.zeros(0, dtype=np.int64)
    codes = {p: i for i, p in enumerate(cube.parents)}
    for row, l2 in enumerate(cube.l2_codes):
        chosen = codes.get(str(overrides.get(l2, "")), -1)
        if chosen >= 0 and spend[row, chosen] > 0:
            preferred[row] = chosen
    return preferred.astype(np.int64)


def _reasons(cube: SpendCube, spend: np.ndarray) -> np.ndarray:
    mapped = cube.mapped
    by_company = [
        _per_l2(cube, cube.amount, mapped & (cube.company == company)) for company in COMPANY_RANK
    ]
    both = np.logical_and.reduce([s > 0 for s in by_company])
    vendors = (spend > 0).sum(axis=1)
    return np.where(~both, ONE_COMPANY, np.where(vendors < 2, SINGLE_VENDOR, QUALIFIES))


def lever2(
    cube: SpendCube,
    params: CategoryParams,
    l1: Mapping[str, np.ndarray],
    switch: np.ndarray,
    assumptions: Mapping[str, Any],
    cap: np.ndarray | None = None,
) -> Lever2Result:
    """Lever 2 per category and per line in every case.

    ``l1[case]`` is each cube line's lever-1 net saving; ``switch`` marks
    lines of lever-1 ``switch`` opportunities. ``cap`` replaces the
    category caps (savings forgone runs it at 100%).
    """
    caps = params.cap if cap is None else cap
    mapped = cube.mapped
    spend = _vendor_spend(cube, mapped)
    reason = _reasons(cube, spend)
    overrides = assumptions["lever2"].get("preferred_vendor") or {}
    preferred = preferred_vendors(cube, spend, overrides)
    ok = reason == QUALIFIES
    in_ok = mapped & cube.per_line(ok)
    is_pref = in_ok & (cube.parent == cube.per_line(preferred))
    eligible_line = in_ok & ~switch
    other = _vendor_spend(cube, eligible_line & ~is_pref)
    cell = np.where(mapped, cube.l2 * other.shape[1] + cube.parent, other.size)
    positive_vendor = np.append(other.ravel(), 0.0)[cell] > 0
    m_line = eligible_line & ~is_pref & positive_vendor
    p_line = eligible_line & is_pref

    C = _per_l2(cube, cube.amount, in_ok)
    P = _per_l2(cube, cube.amount, is_pref)
    P_eligible = _per_l2(cube, cube.amount, p_line)
    M = _per_l2(cube, cube.amount, m_line)
    frac = np.where(ok, f(caps, C, P, M), 0.0)
    frac_line = cube.per_line(frac)
    weight = np.where(p_line, 1.0, np.where(m_line, frac_line, 0.0))

    L1, b2, n2, line_b2, line_n2 = {}, {}, {}, {}, {}
    for case in CASES:
        L1[case] = _per_l2(cube, weight * l1[case], p_line | m_line)
        b2[case] = B2(P_eligible, frac, M, L1[case])
        raw = P_eligible + frac * M - L1[case]
        kept = (frac > 0) & (raw > 0)
        line_b2[case] = np.where(cube.per_line(kept), weight * (cube.amount - l1[case]), 0.0)
        n2[case] = N2(b2[case], params.d, params.pi2[case])
        line_n2[case] = line_b2[case] * cube.per_line(params.d * params.pi2[case])
    return Lever2Result(
        reason=reason,
        preferred=np.where(ok, preferred, -1),
        C=C,
        P=P,
        P_eligible=P_eligible,
        M=M,
        f=frac,
        B2=b2,
        N2=n2,
        eligible=p_line | m_line,
        weight=weight,
        moved=np.where(m_line, frac_line * cube.amount, 0.0),
        line_B2=line_b2,
        line_N2=line_n2,
    )
