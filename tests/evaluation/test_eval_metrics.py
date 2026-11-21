"""Hand-computed examples for the pairwise and dollar-weighted metrics."""

from __future__ import annotations

import pandas as pd
import pytest

from evaluation.metrics import (
    PairScore,
    false_savings_rate,
    item_pair_list_score,
    item_pair_score,
    planted_savings_recall,
    unit_error_catch_rate,
    vendor_pair_score,
)


def vendor_frames(rows: list[tuple[str, str, str | None, str | None, str]]):
    """rows: (company, vendor_id, legal_entity_id, tier, true_legal_entity)."""
    vendor_map = pd.DataFrame(
        [r[:4] for r in rows], columns=["company", "vendor_id", "legal_entity_id", "tier"]
    )
    truth = pd.DataFrame(
        [(r[0], r[1], r[4], "P") for r in rows],
        columns=["company", "vendor_id", "true_legal_entity", "true_parent"],
    )
    return vendor_map, truth


def test_vendor_mixed_example() -> None:
    # True: E1 = {a1, a2, t1} (3 pairs), E2 = {a3, t2} (1 pair) -> 4 true pairs.
    # Predicted (A/B): LE1 = {a1, a2}, LE2 = {t1, a3} -> 2 pairs, 1 correct.
    # t2 is tier C inside LE2: excluded, otherwise LE2 would have 3 members.
    vendor_map, truth = vendor_frames(
        [
            ("acquirer", "1", "LE1", "A", "E1"),
            ("acquirer", "2", "LE1", "A", "E1"),
            ("target", "1", "LE2", "B", "E1"),
            ("acquirer", "3", "LE2", "B", "E2"),
            ("target", "2", "LE2", "C", "E2"),
            ("acquirer", "4", None, None, "E3"),
        ]
    )
    score = vendor_pair_score(vendor_map, truth)
    assert score == PairScore(tp=1, fp=1, fn=3, precision=0.5, recall=0.25)


def test_vendor_cluster_of_three() -> None:
    # Three records in one correct cluster: 3 pairs, all correct.
    vendor_map, truth = vendor_frames(
        [
            ("acquirer", "1", "LE1", "A", "E1"),
            ("acquirer", "2", "LE1", "B", "E1"),
            ("target", "1", "LE1", "A", "E1"),
        ]
    )
    score = vendor_pair_score(vendor_map, truth)
    assert (score.tp, score.fp, score.fn) == (3, 0, 0)
    assert score.precision == 1.0 and score.recall == 1.0


def test_vendor_cluster_of_four_split_truth() -> None:
    # One predicted cluster of 4 (6 pairs) over truth {2, 2}: 2 correct, 4 wrong.
    vendor_map, truth = vendor_frames(
        [
            ("acquirer", "1", "LE1", "A", "E1"),
            ("acquirer", "2", "LE1", "A", "E1"),
            ("target", "1", "LE1", "B", "E2"),
            ("target", "2", "LE1", "B", "E2"),
        ]
    )
    score = vendor_pair_score(vendor_map, truth)
    assert (score.tp, score.fp, score.fn) == (2, 4, 0)
    assert score.precision == pytest.approx(1 / 3)
    assert score.recall == 1.0


def test_vendor_no_matches() -> None:
    vendor_map, truth = vendor_frames(
        [
            ("acquirer", "1", None, None, "E1"),
            ("target", "1", None, None, "E1"),
        ]
    )
    score = vendor_pair_score(vendor_map, truth)
    assert (score.tp, score.fp, score.fn) == (0, 0, 1)
    assert score.precision == 1.0  # nothing predicted, nothing wrong
    assert score.recall == 0.0


def test_vendor_no_true_pairs() -> None:
    vendor_map, truth = vendor_frames(
        [
            ("acquirer", "1", "LE1", "A", "E1"),
            ("target", "1", "LE1", "A", "E2"),
        ]
    )
    score = vendor_pair_score(vendor_map, truth)
    assert (score.tp, score.fp, score.fn) == (0, 1, 0)
    assert score.precision == 0.0
    assert score.recall == 1.0  # nothing to find


def test_vendor_missing_truth_raises() -> None:
    vendor_map, truth = vendor_frames([("acquirer", "1", "LE1", "A", "E1")])
    with pytest.raises(ValueError, match="missing from truth"):
        vendor_pair_score(vendor_map, truth.iloc[0:0])


def test_vendor_missing_column_raises() -> None:
    vendor_map, truth = vendor_frames([("acquirer", "1", "LE1", "A", "E1")])
    with pytest.raises(ValueError, match="legal_entity_id"):
        vendor_pair_score(vendor_map.drop(columns="legal_entity_id"), truth)


def item_frames(rows: list[tuple[str, str, str, str | None, str]]):
    """rows: (company, item_key, canonical_item_id, tier, true_item_id)."""
    item_map = pd.DataFrame(
        [r[:4] for r in rows], columns=["company", "item_key", "canonical_item_id", "tier"]
    )
    item_map["item_record_id"] = item_map["company"] + ":" + item_map["item_key"]
    truth = pd.DataFrame(
        [(r[0], r[1], r[4]) for r in rows], columns=["company", "item_key", "true_item_id"]
    )
    return item_map, truth


ITEM_ROWS = [
    ("acquirer", "A1", "CI1", "A", "X"),
    ("acquirer", "A2", "CI1", "A", "Y"),
    ("target", "T1", "CI1", "A", "X"),
    ("target", "T2", "CI2", None, "Y"),
    ("acquirer", "A3", "CI3", "C", "Z"),
    ("target", "T3", "CI3", "C", "Z"),
]


def test_item_cross_company_only_and_tier_c_excluded() -> None:
    # CI1 = {A1, A2, T1}: cross pairs A1-T1 (true), A2-T1 (false); A1-A2 same company, ignored.
    # CI3 is tier C: excluded. True cross pairs: X (A1,T1), Y (A2,T2), Z (A3,T3) = 3.
    item_map, truth = item_frames(ITEM_ROWS)
    score = item_pair_score(item_map, truth)
    assert score == PairScore(tp=1, fp=1, fn=2, precision=0.5, recall=1 / 3)


def test_item_cluster_of_three_by_two() -> None:
    # 2 acquirer x 3 target records in one canonical item = 6 cross pairs, all true.
    rows = [("acquirer", f"A{i}", "CI1", "A", "X") for i in range(2)]
    rows += [("target", f"T{i}", "CI1", "B", "X") for i in range(3)]
    item_map, truth = item_frames(rows)
    score = item_pair_score(item_map, truth)
    assert (score.tp, score.fp, score.fn) == (6, 0, 0)


def test_item_no_matches_and_no_true_pairs() -> None:
    item_map, truth = item_frames(
        [("acquirer", "A1", "CI1", None, "X"), ("target", "T1", "CI2", None, "Y")]
    )
    score = item_pair_score(item_map, truth)
    assert (score.tp, score.fp, score.fn) == (0, 0, 0)
    assert score.precision == 1.0 and score.recall == 1.0


def test_item_single_company_group_has_no_pairs() -> None:
    item_map, truth = item_frames(
        [("acquirer", "A1", "CI1", "A", "X"), ("acquirer", "A2", "CI1", "A", "X")]
    )
    assert item_pair_score(item_map, truth).tp == 0


def test_item_pair_list_scoring() -> None:
    item_map, truth = item_frames(ITEM_ROWS)
    pairs = pd.DataFrame(
        {
            "item_record_id_a": ["acquirer:A1", "target:T1", "acquirer:A2"],
            "item_record_id_b": ["target:T1", "acquirer:A1", "target:T1"],
        }
    )
    # The reversed duplicate counts once: 2 distinct pairs, 1 true; 3 true pairs exist.
    score = item_pair_list_score(pairs, item_map, truth)
    assert score == PairScore(tp=1, fp=1, fn=2, precision=0.5, recall=1 / 3)


def test_item_pair_list_empty_and_same_company() -> None:
    item_map, truth = item_frames(ITEM_ROWS)
    empty = pd.DataFrame({"item_record_id_a": [], "item_record_id_b": []})
    score = item_pair_list_score(empty, item_map, truth)
    assert (score.tp, score.fp, score.fn) == (0, 0, 3)
    bad = pd.DataFrame({"item_record_id_a": ["acquirer:A1"], "item_record_id_b": ["acquirer:A2"]})
    with pytest.raises(ValueError, match="same-company"):
        item_pair_list_score(bad, item_map, truth)


# ---- dollar metrics -------------------------------------------------------

DOLLAR_ROWS = [
    ("acquirer", "A1", "CI1", "A", "X"),
    ("target", "T1", "CI1", "A", "X"),
    ("acquirer", "A2", "CI2", "A", "Y"),
    ("target", "T2", "CI2", "A", "Y"),
    ("acquirer", "A3", "CI3", "B", "P"),  # wrong match: P with Q
    ("target", "T3", "CI3", "B", "Q"),
    ("acquirer", "A4", "CI4", "A", "U"),
    ("target", "T4", "CI4", "A", "U"),
    ("acquirer", "A5", "CI5", "A", "W"),
    ("target", "T5", "CI5", "A", "W"),
]


def dollar_inputs():
    item_map, truth = item_frames(DOLLAR_ROWS)
    savings = pd.DataFrame(
        [
            ("X", "price", 100.0, False, False),
            ("Y", "price", 200.0, False, False),
            ("U", "unit", 50.0, True, False),
            ("W", "unit", 20.0, True, False),
            ("D", "distractor", 80.0, False, True),
        ],
        columns=["true_item_id", "cause", "true_gross_gap_usd", "is_unit_trap", "is_distractor"],
    )
    gaps = pd.DataFrame(
        {"canonical_item_id": ["CI1", "CI2", "CI3", "CI4"], "gross_gap": [150.0, 100.0, 50.0, 40.0]}
    )
    return item_map, truth, savings, gaps


def test_planted_savings_recall() -> None:
    item_map, truth, savings, gaps = dollar_inputs()
    # Real planted: X 100 + Y 200 = 300. Found: min(150,100) + min(100,200) = 200.
    # CI3 is impure and CI4 is a unit trap: neither counts.
    assert planted_savings_recall(gaps, savings, truth, item_map) == pytest.approx(200 / 300)


def test_planted_savings_recall_including_traps_and_distractors() -> None:
    item_map, truth, savings, gaps = dollar_inputs()
    # Denominator 100+200+50+20+80 = 450; numerator 200 + min(40, 50) = 240.
    result = planted_savings_recall(gaps, savings, truth, item_map, real_savings_only=False)
    assert result == pytest.approx(240 / 450)


def test_planted_savings_recall_sums_split_canonicals_and_handles_none() -> None:
    item_map, truth = item_frames(
        [
            ("acquirer", "A1", "CI1", "A", "X"),
            ("target", "T1", "CI2", "A", "X"),  # same true item split over two canonicals
        ]
    )
    savings = pd.DataFrame(
        [("X", "price", 100.0, False, False)],
        columns=["true_item_id", "cause", "true_gross_gap_usd", "is_unit_trap", "is_distractor"],
    )
    gaps = pd.DataFrame({"canonical_item_id": ["CI1", "CI2"], "gross_gap": [30.0, 40.0]})
    assert planted_savings_recall(gaps, savings, truth, item_map) == pytest.approx(0.7)
    assert planted_savings_recall(gaps.iloc[0:0], savings, truth, item_map) == 0.0
    assert planted_savings_recall(gaps, savings.iloc[0:0], truth, item_map) is None


def test_false_savings_rate() -> None:
    item_map, truth, _, gaps = dollar_inputs()
    # Only CI3 (50) is wrong; total 340.
    assert false_savings_rate(gaps, item_map, truth) == pytest.approx(50 / 340)


def test_false_savings_rate_edges() -> None:
    item_map, truth, _, gaps = dollar_inputs()
    assert false_savings_rate(gaps.iloc[0:0], item_map, truth) is None
    clean = gaps[gaps["canonical_item_id"] != "CI3"]
    assert false_savings_rate(clean, item_map, truth) == 0.0
    unknown = pd.DataFrame({"canonical_item_id": ["CI99"], "gross_gap": [1.0]})
    with pytest.raises(ValueError, match="not in item_map"):
        false_savings_rate(unknown, item_map, truth)


def test_unit_error_catch_rate() -> None:
    item_map, truth, savings, _ = dollar_inputs()
    # Traps: U (CI4) and W (CI5).
    assert unit_error_catch_rate(["CI4"], savings, item_map, truth) == 0.5
    assert unit_error_catch_rate({"CI4", "CI5", "CI1"}, savings, item_map, truth) == 1.0
    assert unit_error_catch_rate([], savings, item_map, truth) == 0.0
    no_traps = savings.assign(is_unit_trap=False)
    assert unit_error_catch_rate(["CI4"], no_traps, item_map, truth) is None
