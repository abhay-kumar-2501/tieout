"""Truth loaders, targets, scorecard round trip and the CLI skeleton."""

from __future__ import annotations

from pathlib import Path

import pytest

from evaluation import targets
from evaluation.metrics import make_pair_score
from evaluation.scorecard import (
    METRIC_NAMES,
    build_scorecard,
    mean_metrics,
    metric_row,
    read_scorecard,
    write_scorecard,
)
from evaluation.sensitivity import threshold_sensitivity
from evaluation.truth import load_truth
from tieout.results import Results

PASSING = {
    "vendor_precision": 0.99,
    "vendor_recall": 0.92,
    "item_precision": 0.98,
    "item_recall": 0.85,
    "planted_savings_recall": 0.7,
    "false_savings_rate": 0.01,
    "unit_error_catch_rate": 1.0,
}


def test_check_passes_and_boundaries_are_inclusive() -> None:
    held_out = {
        **PASSING,
        "vendor_precision": 0.98,
        "item_recall": 0.80,
        "false_savings_rate": 0.02,
        "unit_error_catch_rate": 0.95,
    }
    assert targets.check({"tool": {"held_out": held_out}}) == []


def test_check_reports_each_failing_gate() -> None:
    held_out = {**PASSING, "vendor_recall": 0.89, "false_savings_rate": 0.03}
    failures = targets.check({"tool": {"held_out": held_out}})
    assert len(failures) == 2
    assert failures[0].startswith("vendor_recall") and failures[1].startswith("false_savings_rate")


def test_check_missing_dollar_metrics_fail_but_planted_recall_has_no_gate() -> None:
    held_out = {**PASSING, "false_savings_rate": None, "unit_error_catch_rate": None}
    held_out.pop("planted_savings_recall")
    failures = targets.check({"tool": {"held_out": held_out}})
    assert [f.split(":")[0] for f in failures] == ["false_savings_rate", "unit_error_catch_rate"]
    assert "planted_savings_recall" not in targets.TARGETS


def test_target_constants() -> None:
    assert targets.VENDOR_PRECISION_MIN == 0.98 and targets.VENDOR_RECALL_MIN == 0.90
    assert targets.ITEM_PRECISION_MIN == 0.97 and targets.ITEM_RECALL_MIN == 0.80
    assert targets.FALSE_SAVINGS_RATE_MAX == 0.02 and targets.UNIT_ERROR_CATCH_RATE_MIN == 0.95


def test_metric_row_and_mean() -> None:
    row = metric_row(make_pair_score(9, 10, 12), make_pair_score(1, 1, 1))
    assert row["vendor_precision"] == 0.9 and row["vendor_recall"] == 0.75
    assert row["item_precision"] == 1.0 and row["false_savings_rate"] is None
    mean = mean_metrics({1: row, 2: {**row, "vendor_precision": 0.7}})
    assert mean["vendor_precision"] == pytest.approx(0.8)
    assert mean["false_savings_rate"] is None


def build(held_out: dict[str, float | None]) -> dict:
    tuning = {1: dict(PASSING), 2: {**PASSING, "item_recall": 0.75}, 3: dict(PASSING)}
    baseline = {seed: {**PASSING, "false_savings_rate": 0.2} for seed in (1, 2, 3)}
    return build_scorecard(
        tuning_seeds=[1, 2, 3],
        held_out_seed=4,
        tool_tuning=tuning,
        tool_held_out=held_out,
        baseline_tuning=baseline,
        baseline_held_out={**PASSING, "false_savings_rate": 0.2},
    )


def test_scorecard_round_trip(tmp_path: Path) -> None:
    card = build({**PASSING, "unit_error_catch_rate": None})
    path = tmp_path / "out" / "scorecard.json"
    write_scorecard(card, path)
    assert read_scorecard(path) == card
    assert card["passed"] is False
    assert card["gates"]["unit_error_catch_rate"] == {"value": None, "passed": False}
    assert card["gates"]["vendor_precision"]["passed"] is True
    assert card["tool"]["tuning_mean"]["item_recall"] == pytest.approx((0.85 + 0.75 + 0.85) / 3)
    assert set(card["tool"]["held_out"]) == set(METRIC_NAMES)
    assert card["baseline"]["held_out"]["false_savings_rate"] == 0.2
    first = path.read_text()
    write_scorecard(card, path)
    assert path.read_text() == first  # deterministic text


def test_scorecard_passes_when_all_gates_met() -> None:
    card = build(dict(PASSING))
    assert card["passed"] is True and card["failures"] == []


def test_read_scorecard_rejects_unknown_schema(tmp_path: Path) -> None:
    path = tmp_path / "scorecard.json"
    path.write_text('{"schema_version": 99}')
    with pytest.raises(ValueError, match="schema_version"):
        read_scorecard(path)


def test_load_truth(tmp_path: Path) -> None:
    (tmp_path / "truth_vendor_map.csv").write_text(
        "company,vendor_id,true_legal_entity,true_parent\nacquirer,V1,LE1,P1\ntarget,V1,LE1,P1\n"
    )
    (tmp_path / "truth_item_map.csv").write_text(
        "company,item_key,true_item_id\nacquirer,FA-1,I1\ntarget,MPN:X|Y,I1\n"
    )
    (tmp_path / "truth_savings.csv").write_text(
        "true_item_id,cause,true_gross_gap_usd,is_unit_trap,is_distractor\n"
        "I1,price,1200.5,False,False\nI2,unit,10,True,False\nI3,noise,5,0,1\n"
    )
    truth = load_truth(tmp_path)
    assert len(truth.vendor_map) == 2 and truth.item_map["item_key"].tolist() == ["FA-1", "MPN:X|Y"]
    assert truth.savings["is_unit_trap"].tolist() == [False, True, False]
    assert truth.savings["is_distractor"].tolist() == [False, False, True]
    assert truth.savings["true_gross_gap_usd"].tolist() == [1200.5, 10.0, 5.0]


def test_load_truth_column_and_file_checks(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_truth(tmp_path)
    (tmp_path / "truth_vendor_map.csv").write_text("company,vendor_id\nacquirer,V1\n")
    with pytest.raises(ValueError, match="true_legal_entity"):
        load_truth(tmp_path)


def test_sensitivity_varies_each_threshold_alone(small_results: Results) -> None:
    data = threshold_sensitivity(small_results, vendor_grid=(85.0, 97.0), item_grid=(0.78, 0.9))
    current = data["current"]
    assert current["recurring_base"] == small_results.totals["recurring"]["base"]
    vendor, item = data["curves"]["vendor_auto"], data["curves"]["item_auto_cosine"]
    assert [p["threshold"] for p in vendor] == [85.0, 97.0]
    at_current = [p for p in vendor + item if p["threshold"] in (85.0, 0.78)]
    assert all(p["recurring_base"] == pytest.approx(current["recurring_base"]) for p in at_current)
    assert all(p["recurring_low"] <= p["recurring_base"] <= p["recurring_high"] for p in vendor)
