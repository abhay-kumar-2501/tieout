"""The wired pipeline on a small generated dataset (PRD 9.2)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from tieout.match import make_pair_id, record_decision
from tieout.pipeline import REVIEW_QUEUE_COLUMNS, PipelineInputs, match_lines, run_pipeline
from tieout.reference import load_thresholds
from tieout.results import Results


def _inputs(files: dict[str, Path], **overrides: object) -> PipelineInputs:
    kwargs: dict[str, object] = {
        "acquirer": files["acquirer"],
        "target": files["target"],
        "category_map": files["category_map"],
        "vendor_parents": files["vendor_parents"],
        "as_of": "2026-01-15",
    }
    kwargs.update(overrides)
    return PipelineInputs(**kwargs)  # type: ignore[arg-type]


@pytest.fixture(scope="module")
def results(small_files: dict[str, Path]) -> Results:
    return run_pipeline(_inputs(small_files))


def test_lines_carry_matching_ids(results: Results) -> None:
    lines = results.lines
    assert {"legal_entity_id", "parent_id", "canonical_item_id"} <= set(lines.columns)
    assert lines["legal_entity_id"].notna().all() and lines["parent_id"].notna().all()
    with_item = lines["item_key"].notna() & lines["l2_code"].notna()
    assert lines.loc[with_item, "canonical_item_id"].notna().all()
    assert lines.loc[lines["item_key"].isna(), "canonical_item_id"].isna().all()


def test_maps_cover_every_record(results: Results) -> None:
    assert results.vendor_map["vendor_key"].is_unique
    assert set(results.vendor_map["vendor_key"]) == set(results.lines["vendor_key"])
    assert results.item_map["item_record_id"].is_unique
    matched = results.item_map[results.item_map["tier"].isin(["A", "B"])]
    assert not matched.empty
    assert (matched.groupby("canonical_item_id").size() == 2).all()


def test_review_queue_holds_undecided_vendor_and_item_candidates(results: Results) -> None:
    queue = results.review_queue
    assert list(queue.columns) == list(REVIEW_QUEUE_COLUMNS)
    assert set(queue["status"]) <= {"pending", "deferred"}
    assert {"item_match", "vendor_match"} <= set(queue["type"])
    assert (queue["dollars_at_stake"] == queue["spend_a"] + queue["spend_b"]).all()
    assert queue["dollars_at_stake"].is_monotonic_decreasing
    spend = results.vendor_map.set_index("vendor_key").index
    vendor_rows = queue[queue["type"].str.startswith("vendor_")]
    assert vendor_rows["key_a"].isin(spend).all()


def test_meta_has_staged_counts_and_thresholds(results: Results) -> None:
    vendors = results.meta["matching"]["vendors"]
    assert vendors["records"] >= vendors["after_normalisation"] >= vendors["legal_entities"]
    assert vendors["legal_entities"] >= vendors["parents"]
    items = results.meta["matching"]["items"]
    assert items["records"] >= items["matchable_records"] >= items["canonical_items"]
    assert results.meta["thresholds"]["vendor_auto"] == load_thresholds().vendor_auto
    assert results.meta["report_date"] == "2026-01-15"
    assert results.meta["category_mapping"]["source"] == "supplied"
    assert results.meta["stages_run"] == ["ingest", "vendor_matching", "item_matching"]


def test_synergy_frames_stay_empty(results: Results) -> None:
    for name in ("price_groups", "bridge_detail", "opportunities", "phasing"):
        assert getattr(results, name).empty
    assert results.totals == {} and results.trace == {}


def test_cached_pairs_reassemble_without_rescoring(results: Results) -> None:
    again = match_lines(
        results.lines,
        vendor_parents=results.vendor_parents,
        thresholds=load_thresholds(),
        vendor_pairs=results.vendor_pairs,
        item_pairs=results.item_pairs,
    )
    assert_frame_equal(again.vendors.vendor_map, results.vendor_map)
    assert_frame_equal(again.items.item_map, results.item_map)


def test_decisions_are_applied_and_logged(small_files: dict[str, Path], results: Results) -> None:
    item = results.review_queue[results.review_queue["type"] == "item_match"].iloc[0]
    log = record_decision(None, item["pair_id"], "approve", decided_at="2026-01-15T00:00:00Z")
    decided = run_pipeline(_inputs(small_files), decisions=log)
    assert len(decided.review_log) == 1
    assert item["pair_id"] not in set(decided.review_queue["pair_id"])
    pair = decided.item_pairs.set_index("pair_id").loc[item["pair_id"]]
    assert pair["status"] in {"approved", "pending"}


def test_ids_are_deterministic_across_runs(small_files: dict[str, Path], results: Results) -> None:
    second = run_pipeline(_inputs(small_files))
    for name in ("vendor_map", "item_map", "review_queue", "vendor_pairs", "item_pairs"):
        assert_frame_equal(getattr(second, name), getattr(results, name))
    columns = ["line_id", "legal_entity_id", "parent_id", "canonical_item_id"]
    assert_frame_equal(second.lines[columns], results.lines[columns])


def test_frames_as_inputs_give_the_same_result(
    small_files: dict[str, Path], results: Results
) -> None:
    frames = _inputs(
        small_files,
        acquirer=pd.read_csv(small_files["acquirer"], dtype=str, keep_default_na=False),
        target=pd.read_csv(small_files["target"], dtype=str, keep_default_na=False),
    )
    assert_frame_equal(run_pipeline(frames).vendor_map, results.vendor_map)


def test_round_trip(tmp_path: Path, results: Results) -> None:
    results.save(tmp_path)
    loaded = Results.load(tmp_path)
    assert_frame_equal(loaded.vendor_map, results.vendor_map)
    assert loaded.meta == results.meta


def test_review_decision_pair_ids_follow_the_contract(results: Results) -> None:
    row = results.vendor_pairs.iloc[0]
    assert row["pair_id"] == make_pair_id(row["type"], row["key_a"], row["key_b"])
