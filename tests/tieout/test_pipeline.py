"""The wired pipeline on a small generated dataset (PRD 9.2)."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from tieout.match import make_pair_id, record_decision, undo_last
from tieout.pipeline import (
    REVIEW_QUEUE_COLUMNS,
    PipelineInputs,
    apply_decisions,
    match_lines,
    read_category_settings,
    recompute,
    run_pipeline,
)
from tieout.reference import load_thresholds
from tieout.results import FRAME_NAMES, Results
from tieout.synergy.trace import figure_value, leaf_lines, resum

#: Numeric ``totals`` leaves that are not money (reconciliation shares and bands).
NOT_MONEY = ("share", "band_low", "band_high")


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
    assert results.meta["stages_run"] == ["ingest", "vendor_matching", "item_matching", "synergy"]


def test_cached_pairs_reassemble_without_rescoring(results: Results) -> None:
    again = match_lines(
        results.lines,
        vendor_parents=results.vendor_parents,
        thresholds=load_thresholds(),
        vendor_pairs=results.vendor_pairs,
        item_pairs=results.item_pairs,
    )
    vendor_map, item_map = again.vendors.vendor_map, again.items.item_map
    assert_frame_equal(vendor_map, results.vendor_map[list(vendor_map.columns)])
    assert_frame_equal(item_map, results.item_map[list(item_map.columns)])


def test_decisions_are_applied_and_logged(small_files: dict[str, Path], results: Results) -> None:
    item = results.review_queue[results.review_queue["type"] == "item_match"].iloc[0]
    log = record_decision(None, item["pair_id"], "approve", decided_at="2026-01-15T00:00:00Z")
    decided = run_pipeline(_inputs(small_files), decisions=log)
    assert len(decided.review_log) == 1
    assert item["pair_id"] not in set(decided.review_queue["pair_id"])
    pair = decided.item_pairs.set_index("pair_id").loc[item["pair_id"]]
    assert pair["status"] in {"approved", "pending"}

    # The same decision applied to cached pair scores gives the same answer (PRD 4.5).
    applied = apply_decisions(results, log)
    assert_frame_equal(applied.vendor_map, decided.vendor_map)
    assert_frame_equal(applied.item_map, decided.item_map)
    assert_frame_equal(applied.review_queue, decided.review_queue)
    assert _leaves(applied.totals) == pytest.approx(_leaves(decided.totals), abs=1e-6)
    assert applied.meta["inputs"]["review_decisions"] == 1

    undone = apply_decisions(applied, undo_last(log))
    assert_frame_equal(undone.item_map, results.item_map)
    assert_frame_equal(undone.review_queue, results.review_queue)
    assert _leaves(undone.totals) == pytest.approx(_leaves(results.totals), abs=1e-6)


def test_ids_are_deterministic_across_runs(small_files: dict[str, Path], results: Results) -> None:
    second = run_pipeline(_inputs(small_files))
    for name in ("vendor_map", "item_map", "review_queue", "vendor_pairs", "item_pairs"):
        assert_frame_equal(getattr(second, name), getattr(results, name))
    columns = ["line_id", "legal_entity_id", "parent_id", "canonical_item_id"]
    assert_frame_equal(second.lines[columns], results.lines[columns])
    # Golden-file determinism (PRD 10.2): totals and opportunities agree within 1e-6.
    assert _leaves(second.totals) == pytest.approx(_leaves(results.totals), abs=1e-6)
    assert_frame_equal(second.opportunities, results.opportunities, atol=1e-6, rtol=0)


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
    for name in FRAME_NAMES:
        assert_frame_equal(_blanks(getattr(loaded, name)), _blanks(getattr(results, name)))
    assert_frame_equal(loaded.trace_amounts, results.trace_amounts)
    assert loaded.meta == results.meta
    assert loaded.totals == results.totals
    assert loaded.trace == results.trace
    assert loaded.trace_figures == results.trace_figures
    assert loaded.synergy_cache is None


def test_review_decision_pair_ids_follow_the_contract(results: Results) -> None:
    row = results.vendor_pairs.iloc[0]
    assert row["pair_id"] == make_pair_id(row["type"], row["key_a"], row["key_b"])


def _blanks(frame: pd.DataFrame) -> pd.DataFrame:
    """Object columns with every blank as ``None`` (engine frames mix ``None`` and NaN)."""
    out = frame.copy()
    for column in [c for c in out.columns if pd.api.types.is_object_dtype(out[c])]:
        out[column] = out[column].where(out[column].notna(), None)
    return out


def _leaves(node: Mapping[str, Any], prefix: str = "") -> dict[str, float]:
    """Every numeric (non-boolean) leaf of a nested mapping, by dotted path."""
    out: dict[str, float] = {}
    for key, value in node.items():
        path = f"{prefix}{key}"
        if isinstance(value, Mapping):
            out |= _leaves(value, f"{path}.")
        elif isinstance(value, int | float) and not isinstance(value, bool):
            out[path] = float(value)
    return out


def test_synergy_frames_and_totals_are_filled(results: Results) -> None:
    for name in ("price_groups", "bridge_detail", "opportunities", "category_risk", "phasing"):
        assert not getattr(results, name).empty, name
    assert set(results.opportunities["lever"]) == {1, 2, 3}
    recurring = results.totals["recurring"]
    assert 0 < recurring["low"] <= recurring["base"] <= recurring["high"]
    assert results.totals["checks"]["bridge_tie_out_difference"] == pytest.approx(0, abs=0.01)


def test_every_total_traces_to_source_rows_that_resum_to_it(results: Results) -> None:
    """M2 exit criterion: each figure in ``totals`` re-sums from its source rows to $0.01."""
    money = {
        path
        for path in _leaves(results.totals)
        if not path.startswith("checks.") and path.rsplit(".", 1)[-1] not in NOT_MONEY
    }
    assert money <= set(results.trace_figures)
    index = results.trace_index
    line_ids = set(results.lines["line_id"])
    for path, (node, measure) in results.trace_figures.items():
        rows = [leaf for leaf in leaf_lines(index, node) if leaf != node]
        assert set(rows) <= line_ids, path
        expected = figure_value(results.totals, path)
        assert resum(index, node, measure) == pytest.approx(expected, abs=0.01), path


def test_recompute_reruns_only_the_arithmetic(results: Results) -> None:
    again = recompute(results, results.assumptions)
    assert again.totals == results.totals
    changed = copy.deepcopy(results.assumptions)
    changed["lever2"]["capture"]["base"] = 0.7
    out = recompute(results, changed)
    assert out.assumptions["lever2"]["capture"]["base"] == 0.7
    lever2 = out.totals["levers"]["lever2"]["base"]
    assert lever2 == pytest.approx(results.totals["levers"]["lever2"]["base"] * 0.7 / 0.6)
    assert out.totals["lever1"] == results.totals["lever1"]
    for name in ("lines", "vendor_map", "item_map", "vendor_pairs", "item_pairs"):
        assert getattr(out, name) is getattr(results, name)


def test_recompute_after_load_rebuilds_the_cache(tmp_path: Path, results: Results) -> None:
    results.save(tmp_path)
    loaded = Results.load(tmp_path)
    changed = copy.deepcopy(results.assumptions)
    changed["caps"]["standard"] = 0.6
    fresh = recompute(loaded, changed)
    assert fresh.synergy_cache is not None
    expected = _leaves(recompute(results, changed).totals)
    assert _leaves(fresh.totals) == pytest.approx(expected, abs=1e-6)


def test_review_queue_carries_lever1_review_items_with_their_stake(results: Results) -> None:
    queue = results.review_queue
    flagged = queue[queue["type"].isin(["unit_flag", "incoterm"])]
    assert not flagged.empty
    assert (flagged["stake"] >= 0).all()
    assert flagged["label_a"].notna().all() and flagged["message"].notna().all()
    assert queue.loc[queue["type"].str.startswith("vendor_"), "stake"].isna().all()
    items = queue[queue["type"] == "item_match"]
    assert (items["stake"].dropna() > 0).any()


def test_meta_lists_switched_off_features(results: Results) -> None:
    assert set(results.meta["switched_off"]) == {"scorecard", "sensitivity"}


def test_category_settings_file_is_validated(tmp_path: Path) -> None:
    good = tmp_path / "good.csv"
    good.write_text("l2_code,criticality,cap,pi2_low,pi2_base\nL03.01,critical,0.5,,0.3\n")
    assert read_category_settings(good) == {
        "L03.01": {"criticality": "critical", "cap": 0.5, "pi2_base": 0.3}
    }
    bad = tmp_path / "bad.csv"
    bad.write_text("l2_code,cap\nL03.01,1.5\n")
    with pytest.raises(ValueError, match="cap"):
        read_category_settings(bad)
    unordered = tmp_path / "unordered.csv"
    unordered.write_text("l2_code,pi1_same_low,pi1_same_base\nL03.01,0.8,0.6\n")
    with pytest.raises(ValueError, match="pi1_same"):
        read_category_settings(unordered)
