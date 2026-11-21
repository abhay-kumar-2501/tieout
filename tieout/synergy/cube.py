"""The unified spend cube: every in-scope line with its parent vendor and category.

Levers 2 and 3, risk and phasing work on these arrays. Rows are sorted by
``line_id`` so every sum runs in one fixed order whatever the input order. The
cube's spend sums to the baseline (PRD 5.1, 5.9).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from tieout.synergy.groups import COMPANY_RANK

__all__ = ["SpendCube", "build_cube"]


@dataclass(frozen=True)
class SpendCube:
    """Line arrays plus integer codes for category (``l2``) and parent vendor.

    ``l2`` is -1 for unmapped lines, which no lever touches. ``pay_days`` is
    ``payment_date - doc_date`` in days (NaN when either is blank).
    ``vendor_tier`` / ``vendor_stage`` are the line's vendor record's link
    tier and stage in ``vendor_map``.
    """

    line_id: np.ndarray
    company: np.ndarray
    site: np.ndarray
    amount: np.ndarray
    l2: np.ndarray
    l2_codes: tuple[str, ...]
    category_type: dict[str, str | None]
    parent: np.ndarray
    parents: tuple[str, ...]
    vendor_tier: np.ndarray
    vendor_stage: np.ndarray
    terms: np.ndarray
    pay_days: np.ndarray
    contract_end: pd.DatetimeIndex
    has_terms_data: dict[str, bool]

    def __len__(self) -> int:
        return len(self.line_id)

    @property
    def mapped(self) -> np.ndarray:
        return self.l2 >= 0

    def positions(self, line_ids: np.ndarray) -> np.ndarray:
        """Row of each given ``line_id`` in the cube."""
        return np.searchsorted(self.line_id, line_ids)


def _object(series: pd.Series) -> np.ndarray:
    out = series.astype(object).to_numpy(copy=True)
    out[series.isna().to_numpy()] = None
    return out


def build_cube(lines: pd.DataFrame, vendor_map: pd.DataFrame) -> SpendCube:
    """One row per line, sorted by ``line_id``; a vendor missing from the map is its own parent."""
    df = lines.assign(line_id=lines["line_id"].astype(str))
    df = df.sort_values("line_id", kind="mergesort").reset_index(drop=True)
    vm = vendor_map.drop_duplicates("vendor_key").set_index("vendor_key")
    vendor_key = df["vendor_key"].astype(str)
    parent = vendor_key.map(vm["parent_id"]).astype(object)
    parent = parent.where(parent.notna(), vendor_key)
    parent_code, parents = pd.factorize(parent, sort=True)
    l2 = df["l2_code"].astype(object).where(df["l2_code"].notna(), None)
    l2_code, l2_codes = pd.factorize(l2, sort=True)
    types = df.dropna(subset=["l2_code", "category_type"]).groupby("l2_code", sort=True)
    category_type = types["category_type"].agg(lambda s: s.mode().iloc[0]).to_dict()
    terms = df["payment_terms_days"].astype(float)
    paid = pd.to_datetime(df["payment_date"]) - pd.to_datetime(df["doc_date"])
    has_terms = terms.notna() | df["payment_date"].notna()
    return SpendCube(
        line_id=df["line_id"].to_numpy(dtype=object),
        company=df["company"].astype(str).to_numpy(dtype=object),
        site=df["site"].astype(object).where(df["site"].notna(), "").to_numpy(dtype=object),
        amount=df["amount"].to_numpy(dtype=float),
        l2=l2_code.astype(np.int64),
        l2_codes=tuple(str(c) for c in l2_codes),
        category_type={str(k): (None if pd.isna(v) else str(v)) for k, v in category_type.items()},
        parent=parent_code.astype(np.int64),
        parents=tuple(str(p) for p in parents),
        vendor_tier=_object(vendor_key.map(vm["tier"])),
        vendor_stage=_object(vendor_key.map(vm["stage"])),
        terms=terms.to_numpy(dtype=float),
        pay_days=(paid.dt.days.astype(float)).to_numpy(dtype=float),
        contract_end=pd.DatetimeIndex(pd.to_datetime(df["contract_end_date"])),
        has_terms_data={
            company: bool(has_terms[df["company"] == company].any()) for company in COMPANY_RANK
        },
    )
