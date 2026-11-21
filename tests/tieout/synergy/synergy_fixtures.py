"""Small matched tables for the synergy tests, built line by line.

``Book.buy`` records purchases; ``Book.frames`` returns the ``lines``,
``vendor_map``, ``item_map`` and ``item_pairs`` frames ``compute_synergy``
reads. A vendor's parent is its name unless given, so the same vendor name in
both companies is one parent vendor.
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

import numpy as np
import pandas as pd
from hypothesis import HealthCheck, seed, settings

from tieout.match.review import make_pair_id
from tieout.synergy import SynergyOutputs, compute_synergy

META: dict[str, Any] = {
    "aggregated": False,
    "period": {"start": "2025-01", "end": "2025-12", "months": 12},
    "reporting_currency": "USD",
}
Result = TypeVar("Result")


def _shared_seed() -> int:
    """One Hypothesis seed for every property test of a run, new on every run.

    Under pytest-xdist every worker of one run sees the same
    ``PYTEST_XDIST_TESTRUNUID``; without xdist the seed is drawn once per process.
    """
    run_id = os.environ.get("PYTEST_XDIST_TESTRUNUID")
    if run_id is None:
        return random.SystemRandom().randrange(2**32)
    return int(hashlib.sha256(run_id.encode()).hexdigest()[:8], 16)


SHARED_SEED = _shared_seed()
_PROPERTY_SETTINGS = settings(
    max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow]
)


def property_test(test: Callable[..., None]) -> Callable[..., None]:
    """100 examples, no deadline, and the run's shared seed.

    Property tests over the same strategies then draw the same 100 fresh
    examples on a run, so :func:`memoised` computes each example once instead
    of once per test, while every test still checks 100 new random examples
    per run (PRD 10.2).
    """
    return seed(SHARED_SEED)(_PROPERTY_SETTINGS(test))


def memoised(compute: Callable[..., Result]) -> Callable[..., Result]:
    """Cache a property test's computation by the example's JSON form.

    The tests only read the outputs, so one computation can serve every test
    that draws the same example.
    """
    cache: dict[str, Result] = {}

    @functools.wraps(compute)
    def wrapper(*args: Any) -> Result:
        key = json.dumps(args, sort_keys=True, default=str)
        if key not in cache:
            cache[key] = compute(*args)
        return cache[key]

    return wrapper


#: Close date 2026-01-01 + 36 months.
HORIZON_END = pd.Timestamp("2029-01-01")
DOC_DATE = pd.Timestamp("2025-06-01")


@dataclass
class Book:
    rows: list[dict[str, Any]] = field(default_factory=list)
    parents: dict[str, str] = field(default_factory=dict)
    vendor_tiers: dict[str, str | None] = field(default_factory=dict)
    vendor_stages: dict[str, str] = field(default_factory=dict)
    l2: dict[str, str] = field(default_factory=dict)

    def buy(
        self,
        company: str,
        item: str | None,
        qty: float,
        price: float,
        *,
        site: str = "S1",
        vendor: str = "V1",
        parent: str | None = None,
        lines: int = 3,
        factor: float = 1.0,
        status: str = "confirmed",
        exclusion: str | None = None,
        incoterm: str | None = None,
        contract_end: str | None = None,
        l2: str | None = "L02.01",
        vendor_tier: str | None = "A",
        vendor_stage: str = "V1",
        category_type: str = "mro",
        terms: float | None = None,
        paid_after: float | None = None,
    ) -> None:
        """``lines`` lines of ``qty / lines`` recorded units at ``price`` per recorded unit.

        ``factor`` is base units per recorded unit; ``status="unconverted"``
        leaves the line without a base quantity (excluded from comparison).
        ``item=None`` records spend with no item (services). ``terms`` are the
        stated payment days; ``paid_after`` sets ``payment_date`` that many days
        after ``doc_date``.
        """
        vendor_key = f"{company}:{vendor}"
        self.parents[vendor_key] = parent or vendor
        self.vendor_tiers[vendor_key] = vendor_tier
        self.vendor_stages[vendor_key] = vendor_stage if vendor_tier else "none"
        if item is None:
            status, exclusion = "none", "no_item"
        else:
            self.l2[f"{company}:{item}"] = l2
        unconverted = status in ("unconverted", "none")
        if status == "unconverted":
            exclusion = exclusion or "unit_unconverted"
        for _ in range(lines):
            q = qty / lines
            n = len(self.rows) + 1
            self.rows.append(
                {
                    "line_id": f"{company}:{n}",
                    "company": company,
                    "source_row": n,
                    "site": site,
                    "vendor_key": vendor_key,
                    "item_key": item,
                    "amount": q * price,
                    "quantity_ann": q,
                    "unit_price_rc": price,
                    "uom_dimension": "count",
                    "base_unit": None if unconverted else "each",
                    "base_factor": np.nan if unconverted else factor,
                    "conv_status": status,
                    "qty_base": np.nan if unconverted else q * factor,
                    "price_exclusion": exclusion,
                    "incoterm": incoterm,
                    "contract_end_date": pd.Timestamp(contract_end) if contract_end else pd.NaT,
                    "l2_code": l2,
                    "category_type": category_type if l2 else None,
                    "payment_terms_days": np.nan if terms is None else float(terms),
                    "doc_date": DOC_DATE,
                    "payment_date": (
                        pd.NaT if paid_after is None else DOC_DATE + pd.Timedelta(days=paid_after)
                    ),
                }
            )

    def frames(
        self,
        matches: list[tuple[str, str, str]] = (),  # type: ignore[assignment]
        pending: list[tuple[str, str, float]] = (),  # type: ignore[assignment]
        human: tuple[str, ...] = (),
    ) -> dict[str, pd.DataFrame]:
        """``matches``: (acquirer item, target item, tier); ``pending``: tier C candidates.

        ``human`` lists acquirer items whose match a reviewer approved.
        """
        stages = {f"acquirer:{a}": "human" for a in human}
        stages |= {f"target:{b}": "human" for a, b, _ in matches if a in human}
        lines = pd.DataFrame(self.rows)
        for column in ("contract_end_date", "payment_date", "doc_date"):
            lines[column] = pd.to_datetime(lines[column])
        lines["l2_code"] = lines["l2_code"].astype(object)
        vendor_map = pd.DataFrame(
            {
                "vendor_key": list(self.parents),
                "parent_id": list(self.parents.values()),
                "tier": list(self.vendor_tiers.values()),
                "stage": list(self.vendor_stages.values()),
            },
            dtype=object,
        )
        records = sorted(self.l2)
        partner: dict[str, tuple[str, str]] = {}
        for a, b, tier in matches:
            partner[f"acquirer:{a}"] = (f"target:{b}", tier)
            partner[f"target:{b}"] = (f"acquirer:{a}", tier)
        roots = sorted({min(r, partner[r][0]) if r in partner else r for r in records})
        canonical = {root: f"CI{n:06d}" for n, root in enumerate(roots, start=1)}
        item_map = pd.DataFrame(
            {
                "item_record_id": records,
                "company": [r.split(":")[0] for r in records],
                "item_key": [r.split(":", 1)[1] for r in records],
                "canonical_item_id": [
                    canonical[min(r, partner[r][0]) if r in partner else r] for r in records
                ],
                "partner_id": [partner[r][0] if r in partner else None for r in records],
                "tier": [partner[r][1] if r in partner else None for r in records],
                "stage": [stages.get(r, "I1") if r in partner else "none" for r in records],
                "l2_code": [self.l2[r] for r in records],
            },
            dtype=object,
        )
        pairs = pd.DataFrame(
            [
                {
                    "pair_id": make_pair_id("item_match", f"acquirer:{a}", f"target:{b}"),
                    "type": "item_match",
                    "key_a": f"acquirer:{a}",
                    "key_b": f"target:{b}",
                    "score": score,
                    "tier": "C",
                    "status": "pending",
                }
                for a, b, score in pending
            ],
            columns=["pair_id", "type", "key_a", "key_b", "score", "tier", "status"],
        )
        return {
            "lines": lines,
            "vendor_map": vendor_map,
            "item_map": item_map,
            "item_pairs": pairs,
        }


def run(
    frames: dict[str, pd.DataFrame],
    assumptions: dict[str, Any] | None = None,
    decisions: pd.DataFrame | None = None,
    meta: dict[str, Any] | None = None,
) -> SynergyOutputs:
    return compute_synergy(
        frames["lines"],
        frames["vendor_map"],
        frames["item_map"],
        frames["item_pairs"],
        assumptions,
        decisions,
        META if meta is None else meta,
    )


def decision(pair_id: str, verdict: str = "approve", pack_qty: float | None = None):
    return pd.DataFrame(
        [
            {
                "pair_id": pair_id,
                "type": pair_id.split("|")[0],
                "decision": verdict,
                "pack_qty": pack_qty,
                "note": None,
                "decided_at": "2026-01-01T00:00:00Z",
            }
        ]
    )


def steps(out: SynergyOutputs) -> list[float]:
    bridge = out.totals["lever1"]["bridge"]
    return [bridge[f"step_{i}"] for i in range(1, 8)]


def removed(out: SynergyOutputs, step: int) -> pd.DataFrame:
    detail = out.bridge_detail
    return detail[detail["step"] == step]


def _l2_of(item_key: str | None) -> str | None:
    """A fixed category per item key (five L2s), so an item's lines share one category."""
    return None if item_key is None else f"L02.0{1 + int(item_key[1:]) % 5}"


def realistic_table(n_items: int = 1500, n_lines: int = 60_000, seed: int = 0):
    """A large matched table: ``n_items`` matched items plus unmatched and no-item lines."""
    rng = np.random.default_rng(seed)
    company = rng.choice(["acquirer", "target"], n_lines)
    kind = rng.random(n_lines)
    matched_item = rng.integers(0, n_items, n_lines)
    other_item = rng.integers(0, 4 * n_items, n_lines)
    item_key = np.where(
        kind < 0.6,
        np.char.add("M", matched_item.astype(str)),
        np.where(kind < 0.8, np.char.add("U", other_item.astype(str)), None),
    )
    status = rng.choice(["confirmed", "parsed", "unconverted"], n_lines, p=[0.92, 0.05, 0.03])
    status = np.where(item_key == None, "none", status)  # noqa: E711
    qty = rng.integers(1, 500, n_lines).astype(float)
    qty[rng.random(n_lines) < 0.02] *= -1
    price = np.exp(rng.normal(2.0, 1.0, n_lines))
    vendor = np.char.add("V", rng.integers(0, 400, n_lines).astype(str))
    vendor_key = np.char.add(np.char.add(company.astype(str), ":"), vendor)
    converted = (status == "confirmed") | (status == "parsed")
    contract = pd.to_datetime(
        np.where(
            rng.random(n_lines) < 0.4,
            np.datetime64("2026-01-01") + rng.integers(-200, 1500, n_lines).astype("m8[D]"),
            np.datetime64("NaT", "D"),
        )
    )
    exclusion = np.where(
        item_key == None,  # noqa: E711
        "no_item",
        np.where(status == "unconverted", "unit_unconverted", None),
    )
    lines = pd.DataFrame(
        {
            "line_id": [f"{c}:{i}" for i, c in enumerate(company)],
            "company": company,
            "site": np.char.add("S", rng.integers(0, 8, n_lines).astype(str)),
            "vendor_key": vendor_key,
            "item_key": item_key,
            "amount": qty * price,
            "quantity_ann": qty,
            "unit_price_rc": price,
            "uom_dimension": "count",
            "base_unit": np.where(converted, "each", None),
            "base_factor": np.where(converted, 1.0, np.nan),
            "conv_status": status,
            "qty_base": np.where(converted, qty, np.nan),
            "price_exclusion": exclusion,
            "incoterm": rng.choice(np.array(["FCA", "EXW", None], dtype=object), n_lines),
            "contract_end_date": contract,
            "l2_code": np.where(
                item_key == None,  # noqa: E711
                np.char.add("L02.0", rng.integers(1, 6, n_lines).astype(str)),
                [_l2_of(k) for k in item_key],
            ),
            "category_type": "mro",
            "payment_terms_days": rng.choice([30.0, 45.0, 60.0], n_lines),
            "doc_date": np.datetime64("2025-06-01"),
            "payment_date": pd.to_datetime(
                np.where(
                    rng.random(n_lines) < 0.85,
                    np.datetime64("2025-06-01") + rng.integers(20, 80, n_lines).astype("m8[D]"),
                    np.datetime64("NaT", "D"),
                )
            ),
        }
    )
    keys = sorted(set(vendor_key))
    vendor_map = pd.DataFrame(
        {
            "vendor_key": keys,
            "parent_id": [k.split(":")[1] for k in keys],
            "tier": "A",
            "stage": "V1",
        }
    )
    records = lines.dropna(subset=["item_key"])[["company", "item_key"]].drop_duplicates()
    records = records.sort_values(["company", "item_key"]).reset_index(drop=True)
    rid = records["company"] + ":" + records["item_key"]
    shared = records["item_key"].str.startswith("M")
    partner = np.where(
        shared,
        np.where(records["company"] == "acquirer", "target:", "acquirer:") + records["item_key"],
        None,
    )
    partner = pd.Series(partner).where(pd.Series(partner).isin(set(rid)), None)
    root = np.where(partner.notna(), np.minimum(rid, partner.fillna(rid)), rid)
    canonical = {r: f"CI{n:06d}" for n, r in enumerate(sorted(set(root)), start=1)}
    item_map = pd.DataFrame(
        {
            "item_record_id": rid,
            "company": records["company"],
            "item_key": records["item_key"],
            "canonical_item_id": [canonical[r] for r in root],
            "partner_id": partner,
            "tier": np.where(partner.notna(), "A", None),
            "stage": np.where(partner.notna(), "I1", "none"),
            "l2_code": [_l2_of(k) for k in records["item_key"]],
        },
        dtype=object,
    )
    pairs = pd.DataFrame(columns=["pair_id", "type", "key_a", "key_b", "score", "tier", "status"])
    return {"lines": lines, "vendor_map": vendor_map, "item_map": item_map, "item_pairs": pairs}
