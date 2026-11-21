"""Accuracy metrics of PRD 4.7, as pure functions over data frames.

Matched pairs are tier A and B only, before any human decision. Pair counts are
computed from group sizes, never by materialising pairs (except for an explicit
pair list, which is already a list of pairs).

Conventions: precision is 1.0 when no pair was predicted and recall is 1.0 when
there are no true pairs (nothing wrong / nothing missed). Dollar metrics return
`None` when their denominator is zero.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import pandas as pd

MATCHED_TIERS = ("A", "B")
ACQUIRER = "acquirer"
TARGET = "target"


@dataclass(frozen=True)
class PairScore:
    """Pairwise confusion counts with precision and recall."""

    tp: int
    fp: int
    fn: int
    precision: float
    recall: float


def make_pair_score(tp: int, predicted: int, true: int) -> PairScore:
    """Build a `PairScore` from true positives, predicted pairs and true pairs."""
    precision = tp / predicted if predicted else 1.0
    recall = tp / true if true else 1.0
    return PairScore(tp=tp, fp=predicted - tp, fn=true - tp, precision=precision, recall=recall)


def _require(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise ValueError(f"{name}: missing columns {missing}")


def _within_pairs(frame: pd.DataFrame, keys: list[str]) -> int:
    """Unordered pairs inside groups: sum of n(n-1)/2."""
    if frame.empty:
        return 0
    sizes = frame.groupby(keys, sort=False).size().astype("int64")
    return int((sizes * (sizes - 1) // 2).sum())


def _cross_pairs(frame: pd.DataFrame, keys: list[str]) -> int:
    """Acquirer-target pairs inside groups: sum of n_acquirer * n_target."""
    if frame.empty:
        return 0
    counts = frame.groupby([*keys, "company"], sort=False).size().unstack("company", fill_value=0)
    if ACQUIRER not in counts or TARGET not in counts:
        return 0
    return int((counts[ACQUIRER].astype("int64") * counts[TARGET].astype("int64")).sum())


def _matched(frame: pd.DataFrame, id_column: str) -> pd.DataFrame:
    return frame[frame["tier"].isin(MATCHED_TIERS) & frame[id_column].notna()]


def _attach_truth(
    frame: pd.DataFrame, truth: pd.DataFrame, on: list[str], truth_column: str, name: str
) -> pd.DataFrame:
    merged = frame.merge(truth[[*on, truth_column]], on=on, how="left", validate="many_to_one")
    unknown = merged[truth_column].isna()
    if unknown.any():
        examples = merged.loc[unknown, on].head(3).to_dict("records")
        raise ValueError(
            f"{name}: {int(unknown.sum())} records missing from truth, e.g. {examples}"
        )
    return merged


def vendor_pair_score(vendor_map: pd.DataFrame, vendor_truth: pd.DataFrame) -> PairScore:
    """Pairwise precision/recall of vendor clustering.

    `vendor_map` columns: company, vendor_id, legal_entity_id, tier (A/B/C/None).
    `vendor_truth` columns: company, vendor_id, true_legal_entity.
    Predicted pairs: unordered pairs of tier A/B records sharing `legal_entity_id`.
    True pairs: unordered pairs of all records in `vendor_map` sharing `true_legal_entity`.
    """
    _require(vendor_map, ["company", "vendor_id", "legal_entity_id", "tier"], "vendor_map")
    _require(vendor_truth, ["company", "vendor_id", "true_legal_entity"], "vendor_truth")
    on = ["company", "vendor_id"]
    frame = _attach_truth(vendor_map, vendor_truth, on, "true_legal_entity", "vendor_map")
    matched = _matched(frame, "legal_entity_id")
    return make_pair_score(
        tp=_within_pairs(matched, ["legal_entity_id", "true_legal_entity"]),
        predicted=_within_pairs(matched, ["legal_entity_id"]),
        true=_within_pairs(frame, ["true_legal_entity"]),
    )


def item_pair_score(item_map: pd.DataFrame, item_truth: pd.DataFrame) -> PairScore:
    """Pairwise precision/recall of item matching (cross-company pairs only).

    `item_map` columns: company, item_key, canonical_item_id, tier (A/B/C/None).
    `item_truth` columns: company, item_key, true_item_id.
    Predicted pairs: acquirer-target pairs of tier A/B records sharing `canonical_item_id`.
    True pairs: acquirer-target pairs of all records in `item_map` sharing `true_item_id`.
    """
    _require(item_map, ["company", "item_key", "canonical_item_id", "tier"], "item_map")
    _require(item_truth, ["company", "item_key", "true_item_id"], "item_truth")
    on = ["company", "item_key"]
    frame = _attach_truth(item_map, item_truth, on, "true_item_id", "item_map")
    matched = _matched(frame, "canonical_item_id")
    return make_pair_score(
        tp=_cross_pairs(matched, ["canonical_item_id", "true_item_id"]),
        predicted=_cross_pairs(matched, ["canonical_item_id"]),
        true=_cross_pairs(frame, ["true_item_id"]),
    )


def item_pair_list_score(
    pairs: pd.DataFrame, item_records: pd.DataFrame, item_truth: pd.DataFrame
) -> PairScore:
    """Score an explicit (many-to-many) item pair list, e.g. from the baseline.

    `pairs` columns: item_record_id_a, item_record_id_b (acquirer/target, either order).
    `item_records` columns: item_record_id, company, item_key (the scored universe).
    `item_truth` columns: company, item_key, true_item_id.
    Duplicate and reversed pairs count once; same-company pairs are rejected.
    """
    _require(pairs, ["item_record_id_a", "item_record_id_b"], "pairs")
    _require(item_records, ["item_record_id", "company", "item_key"], "item_records")
    _require(item_truth, ["company", "item_key", "true_item_id"], "item_truth")
    universe = _attach_truth(
        item_records, item_truth, ["company", "item_key"], "true_item_id", "item_records"
    )
    indexed = universe.set_index("item_record_id")
    true_by_record = indexed["true_item_id"]
    company_by_record = indexed["company"]
    known = set(true_by_record.index)
    unknown = (set(pairs["item_record_id_a"]) | set(pairs["item_record_id_b"])) - known
    if unknown:
        raise ValueError(f"pairs: records not in item_records, e.g. {sorted(unknown)[:3]}")
    side_a = pairs["item_record_id_a"]
    side_b = pairs["item_record_id_b"]
    if (side_a.map(company_by_record) == side_b.map(company_by_record)).any():
        raise ValueError("pairs: same-company pair found; item pairs must be cross-company")
    ordered = pd.DataFrame({"a": side_a.where(side_a <= side_b, side_b)})
    ordered["b"] = side_b.where(side_a <= side_b, side_a)
    ordered = ordered.drop_duplicates()
    tp = int((ordered["a"].map(true_by_record) == ordered["b"].map(true_by_record)).sum())
    return make_pair_score(
        tp=tp, predicted=len(ordered), true=_cross_pairs(universe, ["true_item_id"])
    )


# ---------------------------------------------------------------------------
# Dollar-weighted metrics
# ---------------------------------------------------------------------------


def canonical_truth(item_map: pd.DataFrame, item_truth: pd.DataFrame) -> pd.DataFrame:
    """One row per canonical item: `canonical_item_id`, `true_item_id`, `pure`.

    `item_map` columns: company, item_key, canonical_item_id.
    `item_truth` columns: company, item_key, true_item_id.
    A canonical item is `pure` when all its records share one true item; its
    `true_item_id` is then that item (otherwise the smallest, for determinism).
    """
    _require(item_map, ["company", "item_key", "canonical_item_id"], "item_map")
    frame = _attach_truth(
        item_map.dropna(subset=["canonical_item_id"]),
        item_truth,
        ["company", "item_key"],
        "true_item_id",
        "item_map",
    )
    grouped = frame.groupby("canonical_item_id")["true_item_id"]
    out = pd.DataFrame({"true_item_id": grouped.min(), "pure": grouped.nunique() == 1})
    return out.reset_index()


def _tool_gaps_with_truth(
    tool_gaps: pd.DataFrame, item_map: pd.DataFrame, item_truth: pd.DataFrame
) -> pd.DataFrame:
    _require(tool_gaps, ["canonical_item_id", "gross_gap"], "tool_gaps")
    merged = tool_gaps.merge(
        canonical_truth(item_map, item_truth), on="canonical_item_id", how="left"
    )
    unknown = merged["pure"].isna()
    if unknown.any():
        raise ValueError(
            "tool_gaps: canonical items not in item_map, e.g. "
            f"{merged.loc[unknown, 'canonical_item_id'].head(3).tolist()}"
        )
    merged["pure"] = merged["pure"].astype(bool)
    return merged


def planted_savings_recall(
    tool_gaps: pd.DataFrame,
    truth_savings: pd.DataFrame,
    item_truth: pd.DataFrame,
    item_map: pd.DataFrame,
    *,
    real_savings_only: bool = True,
) -> float | None:
    """Sum of min(tool gap, true gap) over truly matched items, over the sum of true gaps.

    `tool_gaps`: canonical_item_id, gross_gap (before capture probability).
    `truth_savings`: true_item_id, true_gross_gap_usd, is_unit_trap, is_distractor.
    `item_truth`: company, item_key, true_item_id; `item_map`: company, item_key,
    canonical_item_id (needed to translate canonical items into true items).
    A canonical item is truly matched only when all its records share one true item;
    gaps of several canonical items for the same true item are summed first.
    With `real_savings_only`, unit traps and distractors are not planted savings and
    are left out of the denominator. Returns None when nothing is planted.
    """
    _require(truth_savings, ["true_item_id", "true_gross_gap_usd"], "truth_savings")
    planted = truth_savings
    if real_savings_only:
        planted = planted[~planted["is_unit_trap"] & ~planted["is_distractor"]]
    true_gap = planted.groupby("true_item_id")["true_gross_gap_usd"].sum()
    total = float(true_gap.sum())
    if total <= 0:
        return None
    merged = _tool_gaps_with_truth(tool_gaps, item_map, item_truth)
    tool_gap = merged[merged["pure"]].groupby("true_item_id")["gross_gap"].sum()
    found = tool_gap.reindex(true_gap.index).fillna(0.0).clip(upper=true_gap)
    return float(found.sum()) / total


def false_savings_rate(
    tool_gaps: pd.DataFrame, item_map: pd.DataFrame, item_truth: pd.DataFrame
) -> float | None:
    """Tool gap on canonical items resting on a wrong match, over total tool gap.

    `tool_gaps`: canonical_item_id, gross_gap (before capture probability).
    `item_map`: company, item_key, canonical_item_id; `item_truth`: company,
    item_key, true_item_id. A canonical item is wrong unless all its records
    share one true item. Returns None when the total tool gap is zero.
    """
    merged = _tool_gaps_with_truth(tool_gaps, item_map, item_truth)
    total = float(merged["gross_gap"].sum())
    if total <= 0:
        return None
    return float(merged.loc[~merged["pure"], "gross_gap"].sum()) / total


def unit_error_catch_rate(
    removed_at_step1_item_ids: Iterable[str],
    truth_savings: pd.DataFrame,
    item_map: pd.DataFrame,
    item_truth: pd.DataFrame,
) -> float | None:
    """Planted unit traps removed by bridge step 1, over planted unit traps.

    `removed_at_step1_item_ids`: canonical_item_ids removed by bridge step 1.
    `truth_savings`: true_item_id, is_unit_trap. `item_map`: company, item_key,
    canonical_item_id; `item_truth`: company, item_key, true_item_id.
    A trap is caught when any removed canonical item contains a record of that
    true item. Returns None when no traps are planted.
    """
    _require(truth_savings, ["true_item_id", "is_unit_trap"], "truth_savings")
    traps = set(truth_savings.loc[truth_savings["is_unit_trap"], "true_item_id"])
    if not traps:
        return None
    _require(item_map, ["company", "item_key", "canonical_item_id"], "item_map")
    records = item_map[item_map["canonical_item_id"].isin(set(removed_at_step1_item_ids))]
    keyed = _attach_truth(records, item_truth, ["company", "item_key"], "true_item_id", "item_map")
    return len(traps & set(keyed["true_item_id"])) / len(traps)
