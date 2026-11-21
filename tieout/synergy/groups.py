"""Buying groups and item facts for lever 1 (PRD 5.2, 3.5, 4.5).

The steps, all independent of the assumptions::

    lever1_items(item_map, item_pairs)      which item records take part, as which item and tier
    tag_lines(lines, vendor_map, items)     one row per line of a lever-1 item
    apply_pack_quantities(tagged, ...)      reviewer pack quantities (``unit_flag`` decisions)
    add_line_sets(tagged)                   the naive and the defensible line sets
    build_price_groups(tagged)              one row per item x buying group
    build_item_facts(tagged, items, ...)    one row per item: unit flags, incoterms, decisions

Two line sets are kept side by side. The **defensible** set is the
price-comparable lines (PRD 3.3 and 3.5), measured in base units. The
**naive** set adds the unconverted lines, measured in their recorded unit, as
the naive figure requires; rows excluded under 3.3 are in neither set.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from tieout.match.review import latest_decisions, make_pair_id, parse_pair_id
from tieout.normalise.units import DIMENSION_BASE, STATUS_ORDER, flag_unit_errors

__all__ = [
    "COMPANIES",
    "COMPANY_RANK",
    "GROUP_KEYS",
    "add_line_sets",
    "apply_pack_quantities",
    "build_item_facts",
    "build_price_groups",
    "contract_open",
    "lever1_items",
    "pack_quantities",
    "tag_lines",
    "unit_flags",
]

COMPANIES = ("acquirer", "target")
COMPANY_RANK = {company: rank for rank, company in enumerate(COMPANIES)}
GROUP_KEYS = ["canonical_item_id", "company", "site", "parent_id"]
MATCHED_TIERS = ("A", "B")
PENDING_STATUSES = ("pending", "deferred")
CONVERTED = ("confirmed", "parsed")
#: Price-exclusion reason of lines the naive figure still compares at recorded price.
UNCONVERTED_REASON = "unit_unconverted"
VENDOR_TIER_RANK = {"A": 1, "B": 2}
_NO_STATUS = len(STATUS_ORDER)

ITEM_COLUMNS = [
    "item_record_id",
    "company",
    "canonical_item_id",
    "item_tier",
    "match_pair_id",
    "l2_code",
]


# ---------------------------------------------------------------- item scope


def lever1_items(item_map: pd.DataFrame, item_pairs: pd.DataFrame) -> pd.DataFrame:
    """Item records taking part in lever 1, with the item id and tier they count under.

    Matched records (tier A or B) keep their ``canonical_item_id``. The naive
    figure also counts tier C candidates, each record using only its single
    best candidate: pending or deferred ``item_match`` pairs between two records
    without a tier A or B partner, taken greedily by descending score, ties by
    record key. Such a pair counts as one item under the smaller of its two
    canonical ids, at tier C.
    """
    im = item_map.sort_values("item_record_id", kind="mergesort")
    matched = im[im["partner_id"].notna() & im["tier"].isin(MATCHED_TIERS)]
    rows = pd.DataFrame(
        {
            "item_record_id": matched["item_record_id"].astype(object),
            "company": matched["company"].astype(object),
            "canonical_item_id": matched["canonical_item_id"].astype(object),
            "item_tier": matched["tier"].astype(object),
            "match_pair_id": [
                make_pair_id("item_match", a, b)
                for a, b in zip(matched["item_record_id"], matched["partner_id"], strict=True)
            ],
            "l2_code": matched["l2_code"].astype(object),
        }
    )
    out = pd.concat([rows, _naive_candidates(im, item_pairs)], ignore_index=True)
    out = out.sort_values(["canonical_item_id", "company"], kind="mergesort")
    return out.reset_index(drop=True)[ITEM_COLUMNS]


def _naive_candidates(im: pd.DataFrame, item_pairs: pd.DataFrame) -> pd.DataFrame:
    free = im[im["partner_id"].isna()].set_index("item_record_id")
    pairs = item_pairs[
        (item_pairs["type"] == "item_match")
        & item_pairs["status"].isin(PENDING_STATUSES)
        & item_pairs["key_a"].isin(free.index)
        & item_pairs["key_b"].isin(free.index)
    ]
    pairs = pairs.assign(_score=pairs["score"].astype(float).fillna(-np.inf))
    pairs = pairs.sort_values(
        ["_score", "key_a", "key_b"], ascending=[False, True, True], kind="mergesort"
    )
    taken: set[str] = set()
    rows: list[dict[str, object]] = []
    for pair_id, a, b in zip(pairs["pair_id"], pairs["key_a"], pairs["key_b"], strict=True):
        if a in taken or b in taken or free.at[a, "company"] == free.at[b, "company"]:
            continue
        taken.update((a, b))
        item_id = min(free.at[a, "canonical_item_id"], free.at[b, "canonical_item_id"])
        for record in (a, b):
            rows.append(
                {
                    "item_record_id": record,
                    "company": free.at[record, "company"],
                    "canonical_item_id": item_id,
                    "item_tier": "C",
                    "match_pair_id": pair_id,
                    "l2_code": free.at[record, "l2_code"],
                }
            )
    return pd.DataFrame(rows, columns=ITEM_COLUMNS, dtype=object)


# ---------------------------------------------------------------- lines


def _text(series: pd.Series) -> pd.Series:
    """Object series with ``None`` for blanks (pandas 3 string columns use NaN)."""
    out = series.astype(object)
    return out.where(series.notna(), None)


def tag_lines(lines: pd.DataFrame, vendor_map: pd.DataFrame, items: pd.DataFrame) -> pd.DataFrame:
    """Lines of lever-1 items with parent vendor, item id and tier attached.

    Rows are sorted by ``line_id`` so that every later sum runs in one fixed
    order, whatever the input row order. A vendor key missing from
    ``vendor_map`` stands as its own parent.
    """
    record = lines["company"].astype(str) + ":" + lines["item_key"].astype(str)
    keep = lines["item_key"].notna() & record.isin(items["item_record_id"])
    sub = lines.loc[keep]
    vm = vendor_map.drop_duplicates("vendor_key").set_index("vendor_key")
    vendor_key = sub["vendor_key"].astype(str)
    parent = vendor_key.map(vm["parent_id"]).astype(object)
    item = items.set_index("item_record_id")
    rid = record[keep]
    tagged = pd.DataFrame(
        {
            "line_id": sub["line_id"].astype(str),
            "company": sub["company"].astype(str),
            "site": _text(sub["site"]).fillna(""),
            "vendor_key": vendor_key,
            "parent_id": parent.where(parent.notna(), vendor_key),
            "vendor_tier_rank": vendor_key.map(vm["tier"]).map(VENDOR_TIER_RANK).fillna(0),
            "item_record_id": rid,
            "canonical_item_id": rid.map(item["canonical_item_id"]),
            "item_tier": rid.map(item["item_tier"]),
            "l2_code": rid.map(item["l2_code"]),
            "amount": sub["amount"].astype(float),
            "quantity_ann": sub["quantity_ann"].astype(float),
            "unit_price_rc": sub["unit_price_rc"].astype(float),
            "uom_dimension": _text(sub["uom_dimension"]),
            "base_unit": _text(sub["base_unit"]),
            "base_factor": sub["base_factor"].astype(float),
            "conv_status": _text(sub["conv_status"]),
            "qty_base": sub["qty_base"].astype(float),
            "price_exclusion": _text(sub["price_exclusion"]),
            "incoterm": _text(sub["incoterm"]),
            "contract_end_date": pd.to_datetime(sub["contract_end_date"]),
        }
    )
    tagged["vendor_tier_rank"] = tagged["vendor_tier_rank"].astype(int)
    return tagged.sort_values("line_id", kind="mergesort").reset_index(drop=True)


def pack_quantities(decisions: pd.DataFrame | None) -> dict[str, float]:
    """Item record -> reviewer-entered pack quantity, from approved ``unit_flag`` decisions."""
    latest = latest_decisions(decisions)
    approved = latest[
        (latest["type"] == "unit_flag")
        & (latest["decision"] == "approve")
        & (latest["pack_qty"] > 0)
    ]
    packs: dict[str, float] = {}
    for pair_id, qty in zip(approved["pair_id"], approved["pack_qty"], strict=True):
        _, side_a, side_b = parse_pair_id(pair_id)
        packs[side_a] = packs[side_b] = float(qty)
    return packs


def apply_pack_quantities(tagged: pd.DataFrame, packs: Mapping[str, float]) -> pd.DataFrame:
    """Convert unconverted lines of the given item records with a reviewer pack quantity.

    The pack quantity is in the category's base unit (PRD 3.5), so the line
    becomes ``confirmed`` and price-comparable, and the comparison re-runs
    (PRD 4.5, ``unit_flag``).
    """
    qty = tagged["item_record_id"].map(packs).astype(float)
    hit = qty.notna() & (tagged["conv_status"] == "unconverted")
    hit &= tagged["uom_dimension"].isin(DIMENSION_BASE)
    if not hit.any():
        return tagged
    out = tagged.copy()
    out.loc[hit, "base_unit"] = out.loc[hit, "uom_dimension"].map(DIMENSION_BASE)
    out.loc[hit, "base_factor"] = qty[hit]
    out.loc[hit, "conv_status"] = "confirmed"
    out.loc[hit, "qty_base"] = out.loc[hit, "quantity_ann"] * qty[hit]
    cleared = hit & (out["price_exclusion"] == UNCONVERTED_REASON)
    out.loc[cleared, "price_exclusion"] = None
    return out


def add_line_sets(tagged: pd.DataFrame) -> pd.DataFrame:
    """Add the naive and defensible line sets and their quantities.

    ``def_ok``: price-comparable, quantity ``qty_base``. ``naive_ok``: also the
    unconverted lines, with quantity ``quantity_ann`` (their recorded unit).
    """
    out = tagged.copy()
    reason = out["price_exclusion"]
    converted = out["conv_status"].isin(CONVERTED)
    out["def_ok"] = reason.isna() & converted
    out["naive_ok"] = out["def_ok"] | (reason == UNCONVERTED_REASON)
    naive_qty = np.where(converted, out["qty_base"], out["quantity_ann"])
    out["def_w"] = np.where(out["def_ok"], out["qty_base"], 0.0)
    out["naive_w"] = np.where(out["naive_ok"], naive_qty, 0.0)
    return out


def contract_open(tagged: pd.DataFrame, limit: pd.Timestamp | None) -> np.ndarray:
    """Lines whose contract end is blank or on or before ``limit`` (all, when no limit)."""
    end = tagged["contract_end_date"]
    if limit is None:
        return np.ones(len(tagged), dtype=bool)
    return (end.isna() | (end <= limit)).to_numpy(dtype=bool)


# ---------------------------------------------------------------- groups


def _dominant(keys: pd.DataFrame, values: pd.Series, weights: pd.Series) -> pd.Series:
    """Value with the largest weight per key (blanks ignored, ties lexical)."""
    frame = keys.assign(_v=values, _w=weights).dropna(subset=["_v"])
    cols = list(keys.columns)
    sums = frame.groupby([*cols, "_v"], sort=True)["_w"].sum().reset_index()
    sums = sums.sort_values(
        [*cols, "_w", "_v"], ascending=[True] * len(cols) + [False, True], kind="mergesort"
    )
    return sums.drop_duplicates(cols).set_index(cols)["_v"]


def build_price_groups(tagged: pd.DataFrame) -> tuple[pd.DataFrame, np.ndarray]:
    """One row per (item, company, site, parent vendor) and each line's group position.

    For both line sets: amount, net quantity (credits netted), price
    ``p[k,g]`` = amount / quantity (NaN unless both are positive) and the count
    of purchase lines (positive quantity). Also the credit lines netted, the
    worst conversion status, the dominant incoterm by spend and the weakest
    vendor-link tier. Rows are sorted by the group key; the row position is the
    group code used everywhere else.
    """
    codes = tagged.groupby(GROUP_KEYS, sort=True).ngroup().to_numpy()
    positive = tagged["quantity_ann"] > 0
    status_rank = tagged["conv_status"].map(STATUS_ORDER).fillna(_NO_STATUS)
    work = tagged.assign(
        _code=codes,
        _naive_amount=np.where(tagged["naive_ok"], tagged["amount"], 0.0),
        _def_amount=np.where(tagged["def_ok"], tagged["amount"], 0.0),
        _naive_line=tagged["naive_ok"] & positive,
        _def_line=tagged["def_ok"] & positive,
        _credit_line=tagged["def_ok"] & ~positive,
        _credit_qty=np.where(tagged["def_ok"] & ~positive, tagged["qty_base"], 0.0),
        _status=np.where(tagged["naive_ok"], status_rank, _NO_STATUS),
    )
    groups = work.groupby("_code", sort=True).agg(
        canonical_item_id=("canonical_item_id", "first"),
        company=("company", "first"),
        site=("site", "first"),
        parent_id=("parent_id", "first"),
        item_tier=("item_tier", "first"),
        l2_code=("l2_code", "first"),
        lines_total=("line_id", "size"),
        naive_amount=("_naive_amount", "sum"),
        naive_qty=("naive_w", "sum"),
        naive_lines=("_naive_line", "sum"),
        amount=("_def_amount", "sum"),
        q=("def_w", "sum"),
        n_lines=("_def_line", "sum"),
        credit_lines=("_credit_line", "sum"),
        credit_qty=("_credit_qty", "sum"),
        status_rank=("_status", "min"),
        vendor_tier_rank=("vendor_tier_rank", "max"),
    )
    groups = groups.reset_index(drop=True)
    groups["naive_price"] = _price(groups["naive_amount"], groups["naive_qty"])
    groups["p"] = _price(groups["amount"], groups["q"])
    statuses = {rank: status for status, rank in STATUS_ORDER.items()}
    groups["conv_status"] = groups["status_rank"].astype(int).map(statuses).astype(object)
    groups["conv_status"] = groups["conv_status"].where(groups["conv_status"].notna(), None)
    incoterm = _dominant(work[["_code"]], work["incoterm"], work["amount"])
    groups["incoterm"] = pd.Series(groups.index, dtype=int).map(incoterm).astype(object)
    groups["incoterm"] = groups["incoterm"].where(groups["incoterm"].notna(), None)
    groups["group_id"] = (
        groups["canonical_item_id"]
        + "|"
        + groups["company"]
        + "|"
        + groups["site"]
        + "|"
        + groups["parent_id"]
    )
    return groups.drop(columns="status_rank"), codes


def _price(amount: pd.Series, qty: pd.Series) -> pd.Series:
    ok = (amount > 0) & (qty > 0)
    return (amount / qty.where(ok)).where(ok)


# ---------------------------------------------------------------- items


def _side_frame(tagged: pd.DataFrame, items: pd.Index) -> pd.DataFrame:
    """Per item and company: converted and recorded prices and the worst status (PRD 3.5)."""
    naive = tagged[tagged["naive_ok"]]
    defensible = tagged[tagged["def_ok"]]
    keys = ["canonical_item_id", "company"]
    recorded = naive.groupby(keys)["amount"].sum() / naive.groupby(keys)["quantity_ann"].sum()
    converted = defensible.groupby(keys)["amount"].sum() / defensible.groupby(keys)["def_w"].sum()
    status = naive.assign(_r=naive["conv_status"].map(STATUS_ORDER)).groupby(keys)["_r"].min()
    names = {rank: name for name, rank in STATUS_ORDER.items()}
    out = pd.DataFrame(index=items)
    for suffix, company in zip(("a", "b"), COMPANIES, strict=True):
        out[f"price_{suffix}"] = _company_column(converted, company, items).astype(float)
        out[f"recorded_{suffix}"] = _company_column(recorded, company, items).astype(float)
        statuses = _company_column(status, company, items).map(names).astype(object)
        out[f"status_{suffix}"] = statuses.where(statuses.notna(), None)
    return out


def _company_column(values: pd.Series, company: str, items: pd.Index) -> pd.Series:
    """One company's values of an (item, company) series, aligned to ``items``."""
    wide = values.unstack("company") if len(values) else pd.DataFrame(index=items)
    return wide.reindex(index=items, columns=list(COMPANIES))[company]


def unit_flags(tagged: pd.DataFrame, items: pd.Index) -> pd.DataFrame:
    """Suspected unit errors per item (PRD 3.5): ``ratio``, ``factor``, ``rule``, ``flagged``."""
    return flag_unit_errors(_side_frame(tagged, items))


def build_item_facts(
    tagged: pd.DataFrame,
    raw_tagged: pd.DataFrame,
    items: pd.DataFrame,
    decisions: pd.DataFrame | None,
    packs: Mapping[str, float],
) -> pd.DataFrame:
    """One row per lever-1 item, sorted by id; the row position is the item code.

    ``unit_flag_raw`` is the PRD 3.5 flag on the data as received (it decides
    whether a ``unit_flag`` review item exists); ``unit_flag`` is the flag after
    reviewer pack quantities, cleared by a plain approval. ``unit_excluded``
    (removed at bridge step 1) adds items whose converted lines disagree on
    the base unit. ``incoterm_acquirer`` / ``incoterm_target`` are each
    company's dominant incoterm by spend on the item.
    """
    by_item = items.groupby("canonical_item_id", sort=True)
    facts = by_item.agg(
        item_tier=("item_tier", "first"),
        l2_code=("l2_code", "first"),
        match_pair_id=("match_pair_id", "first"),
    )
    records = items.pivot(index="canonical_item_id", columns="company", values="item_record_id")
    records = records.reindex(index=facts.index, columns=list(COMPANIES))
    facts["record_acquirer"] = records["acquirer"].astype(object)
    facts["record_target"] = records["target"].astype(object)
    facts["pending"] = facts["item_tier"] == "C"
    index = facts.index

    raw = unit_flags(raw_tagged, index)
    now = raw if raw_tagged is tagged else unit_flags(tagged, index)
    latest = latest_decisions(decisions).set_index("pair_id")
    unit_pair = _pair_ids("unit_flag", facts)
    unit_decision = unit_pair.map(latest["decision"])
    has_pack = (
        facts["record_acquirer"].isin(list(packs)) | facts["record_target"].isin(list(packs))
    ).to_numpy()
    cleared = (unit_decision == "approve").to_numpy() & ~has_pack
    facts["unit_pair_id"] = unit_pair
    facts["unit_decision"] = unit_decision.astype(object)
    facts["pack_qty"] = unit_pair.map(latest["pack_qty"]).astype(float)
    facts["unit_flag_raw"] = raw["flagged"].to_numpy(dtype=bool)
    facts["ratio_raw"] = raw["ratio"]
    facts["factor_raw"] = raw["factor"]
    facts["message_raw"] = raw["message"]
    facts["ratio"] = now["ratio"]
    facts["factor"] = now["factor"]
    facts["rule"] = now["rule"]
    facts["message"] = now["message"]
    facts["unit_flag"] = now["flagged"].to_numpy(dtype=bool) & ~cleared
    converted = tagged[tagged["conv_status"].isin(CONVERTED)]
    dimensions = converted.groupby("canonical_item_id")["base_unit"].nunique()
    facts["dimension_mismatch"] = dimensions.reindex(index).fillna(0).to_numpy() > 1
    facts["unit_excluded"] = facts["unit_flag"] | facts["dimension_mismatch"]
    unconverted = tagged["naive_ok"] & ~tagged["def_ok"]
    counts = unconverted.groupby(tagged["canonical_item_id"]).sum()
    facts["unconverted_lines"] = counts.reindex(index).fillna(0).astype(int)

    incoterm_pair = _pair_ids("incoterm", facts)
    facts["incoterm_pair_id"] = incoterm_pair
    facts["incoterm_decision"] = incoterm_pair.map(latest["decision"]).astype(object)
    facts["incoterm_approved"] = (facts["incoterm_decision"] == "approve").to_numpy()
    keys = tagged[["canonical_item_id", "company"]]
    dominant = _dominant(keys, tagged["incoterm"], tagged["amount"])
    for company in COMPANIES:
        column = _company_column(dominant, company, index).astype(object)
        facts[f"incoterm_{company}"] = column.where(column.notna(), None)
    return facts.reset_index()


def _pair_ids(pair_type: str, facts: pd.DataFrame) -> pd.Series:
    return pd.Series(
        [
            make_pair_id(pair_type, a, b) if isinstance(a, str) and isinstance(b, str) else None
            for a, b in zip(facts["record_acquirer"], facts["record_target"], strict=True)
        ],
        index=facts.index,
        dtype=object,
    )
