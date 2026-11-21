"""Baseline matcher behaviour on tiny inputs."""

from __future__ import annotations

import pandas as pd

from evaluation.baseline import (
    ITEM_MAP_COLUMNS,
    VENDOR_MAP_COLUMNS,
    baseline_item_map,
    baseline_item_pairs,
    baseline_vendor_map,
)
from evaluation.metrics import vendor_pair_score


def vendors(names: dict[str, str]) -> pd.DataFrame:
    rows = [(key, key.split(":")[0], key.split(":")[1], name) for key, name in names.items()]
    return pd.DataFrame(rows, columns=["vendor_key", "company", "vendor_id", "vendor_name"])


def cluster_of(result: pd.DataFrame, key: str) -> str:
    return result.set_index("vendor_key").loc[key, "legal_entity_id"]


def test_vendor_columns_and_singletons() -> None:
    result = baseline_vendor_map(vendors({"acquirer:V1": "Globex", "target:V1": "Zenith"}))
    assert list(result.columns) == VENDOR_MAP_COLUMNS
    assert result["tier"].isna().all()
    assert (result["stage"] == "none").all()
    assert result["legal_entity_id"].nunique() == 2


def test_token_subset_names_merge() -> None:
    result = baseline_vendor_map(
        vendors({"acquirer:V1": "Acme Steel", "target:V1": "ACME STEEL WORKS INTERNATIONAL"})
    )
    assert cluster_of(result, "acquirer:V1") == cluster_of(result, "target:V1")
    assert set(result["tier"]) == {"B"}
    assert (result["score"] == 100).all()


def test_chained_components_merge() -> None:
    # acme~acme steel (100), acme steel~steel (100), but acme vs steel is only 22:
    # connected components still put all three in one cluster.
    result = baseline_vendor_map(
        vendors(
            {
                "acquirer:V1": "Acme",
                "acquirer:V2": "Acme Steel",
                "target:V1": "Steel",
                "target:V2": "Globex",
            }
        )
    )
    assert cluster_of(result, "acquirer:V1") == cluster_of(result, "target:V1")
    assert cluster_of(result, "target:V2") != cluster_of(result, "acquirer:V1")


def test_vendor_ids_follow_sorted_smallest_member_and_are_order_independent() -> None:
    names = {"target:V1": "Zenith", "acquirer:V1": "Globex", "acquirer:V2": "Globex Corp"}
    forward = baseline_vendor_map(vendors(names))
    reverse = baseline_vendor_map(vendors(dict(reversed(list(names.items())))))
    pd.testing.assert_frame_equal(forward, reverse)
    assert cluster_of(forward, "acquirer:V1") == "LE00001"
    assert cluster_of(forward, "target:V1") == "LE00002"


def test_vendor_empty_and_scored_by_metric() -> None:
    assert baseline_vendor_map(vendors({})).empty
    result = baseline_vendor_map(vendors({"acquirer:V1": "Acme", "target:V1": "Acme Inc"}))
    truth = pd.DataFrame(
        {
            "company": ["acquirer", "target"],
            "vendor_id": ["V1", "V1"],
            "true_legal_entity": ["E1", "E1"],
        }
    )
    assert vendor_pair_score(result, truth).recall == 1.0


BOLT = "grade a2 stainless steel hex head bolt 50 mm fully threaded din 933 zinc"


def items(rows: list[tuple[str, str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["item_record_id", "company", "l2_code", "description"])


def test_items_pair_within_l2_without_attribute_veto() -> None:
    records = items(
        [
            ("acquirer:A1", "acquirer", "L2-1", BOLT + " m8"),
            ("target:T1", "target", "L2-1", BOLT + " m10"),  # different size: no veto, still pairs
            ("target:T2", "target", "L2-1", "ceramic floor tile glossy white"),
            ("target:T3", "target", "L2-2", BOLT + " m8"),  # same text, other L2: never paired
            ("acquirer:A2", "acquirer", "L2-1", BOLT + " m8"),  # same company as A1: no pair
        ]
    )
    pairs = baseline_item_pairs(records)
    got = set(zip(pairs["item_record_id_a"], pairs["item_record_id_b"], strict=True))
    assert got == {("acquirer:A1", "target:T1"), ("acquirer:A2", "target:T1")}
    assert (pairs["score"] >= 0.80).all()


def test_items_many_to_many() -> None:
    records = items(
        [
            ("acquirer:A1", "acquirer", "L2-1", BOLT),
            ("target:T1", "target", "L2-1", BOLT),
            ("target:T2", "target", "L2-1", BOLT),
            ("acquirer:A2", "acquirer", "L2-1", BOLT),
        ]
    )
    assert len(baseline_item_pairs(records)) == 4


def test_items_empty_inputs() -> None:
    assert baseline_item_pairs(items([])).empty
    only_blank = items(
        [("acquirer:A1", "acquirer", "L2-1", ""), ("target:T1", "target", "L2-1", "")]
    )
    assert baseline_item_pairs(only_blank).empty


def test_item_map_keeps_each_records_single_best_pair() -> None:
    records = pd.DataFrame(
        {
            "item_record_id": ["acquirer:A1", "acquirer:A2", "target:T1", "target:T2"],
            "company": ["acquirer", "acquirer", "target", "target"],
            "item_key": ["A1", "A2", "T1", "T2"],
            "l2_code": ["L02.01"] * 4,
        }
    )
    pairs = pd.DataFrame(
        {
            "item_record_id_a": ["acquirer:A1", "acquirer:A1", "acquirer:A2"],
            "item_record_id_b": ["target:T1", "target:T2", "target:T1"],
            "l2_code": ["L02.01"] * 3,
            "score": [0.95, 0.90, 0.99],
        }
    )
    result = baseline_item_map(records, pairs).set_index("item_record_id")
    assert list(result.reset_index().columns) == ITEM_MAP_COLUMNS
    # A2-T1 (0.99) goes first; A1 then takes T2, its best free partner.
    assert result.loc["acquirer:A2", "partner_id"] == "target:T1"
    assert result.loc["acquirer:A1", "partner_id"] == "target:T2"
    assert (
        result.loc["acquirer:A1", "canonical_item_id"]
        == result.loc["target:T2", "canonical_item_id"]
    )
    assert set(result["tier"]) == {"B"} and set(result["stage"]) == {"I3"}
    unmatched = baseline_item_map(records, pairs.iloc[0:0])
    assert unmatched["tier"].isna().all() and unmatched["canonical_item_id"].is_unique
