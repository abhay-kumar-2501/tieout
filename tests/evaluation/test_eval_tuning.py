"""Tuning choice rule, thresholds file, truth re-keying and tool scoring on a small seed."""

from __future__ import annotations

from pathlib import Path

import pytest

from evaluation import tune
from evaluation.evaluate import SeedTruth, baseline_metrics, tool_metrics
from evaluation.metrics import make_pair_score
from evaluation.truth import load_item_truth_engine_keys
from tieout.reference import Thresholds, load_thresholds
from tieout.results import Results


def _grid(precisions: dict[float, list[float]]) -> tune.Grid:
    return {
        value: {seed: make_pair_score(round(p * 1000), 1000, 1000) for seed, p in enumerate(ps)}
        for value, ps in precisions.items()
    }


def test_choose_takes_the_lowest_value_over_the_bar() -> None:
    grid = _grid({0.70: [0.96, 0.97], 0.72: [0.975, 0.976], 0.74: [0.99, 0.99]})
    choice = tune.choose(grid, 0.97)
    assert (choice.value, choice.met, choice.bar) == (0.72, True, 0.975)


def test_choose_keeps_the_most_conservative_value_when_nothing_qualifies() -> None:
    choice = tune.choose(_grid({85.0: [0.90], 97.0: [0.95]}), 0.98)
    assert (choice.value, choice.met) == (97.0, False)


def test_grids_follow_the_prd() -> None:
    assert tune.VENDOR_GRID[0] == 85 and tune.VENDOR_GRID[-1] == 97 and len(tune.VENDOR_GRID) == 13
    assert tune.ITEM_GRID[0] == 0.70 and tune.ITEM_GRID[-1] == 0.90 and len(tune.ITEM_GRID) == 11


def test_thresholds_file_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "thresholds.toml"
    tune.write_thresholds(Thresholds(88.0, 75.0, 0.78, 0.60), path)
    assert load_thresholds(path) == Thresholds(88.0, 75.0, 0.78, 0.60)


def test_item_truth_is_rekeyed_with_the_engine_rule(tmp_path: Path) -> None:
    (tmp_path / "truth_item_map.csv").write_text(
        "company,item_key,true_item_id,item_code,mpn,manufacturer\n"
        "acquirer,FA-1,I1,FA-1,,\n"
        "target,MPN:AB12C|acme,I1,,ab-12c,ACME Corp.\n"
    )
    truth = load_item_truth_engine_keys(tmp_path)
    assert truth["item_key"].tolist() == ["FA-1", "MPN:AB12C|acme"]


@pytest.fixture(scope="module")
def small_scores(small_files: dict[str, Path], small_results: Results) -> tuple[dict, dict]:
    truth = SeedTruth.load(small_files["truth_dir"])
    return tool_metrics(small_results, truth), baseline_metrics(small_results, truth)


def test_tool_beats_the_baseline_on_precision_and_false_savings(
    small_scores: tuple[dict, dict],
) -> None:
    tool, baseline = small_scores
    assert tool["vendor_precision"] > baseline["vendor_precision"]
    assert tool["item_precision"] > baseline["item_precision"]
    for side in (tool, baseline):  # the dollar metrics are fed from the synergy stage
        assert all(side[m] is not None for m in ("planted_savings_recall", "false_savings_rate"))
    assert tool["false_savings_rate"] < baseline["false_savings_rate"]
    assert tool["unit_error_catch_rate"] >= baseline["unit_error_catch_rate"]
