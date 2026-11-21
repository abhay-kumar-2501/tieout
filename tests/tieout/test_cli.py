import json
from pathlib import Path

import pandas as pd
import pytest

from tieout.__main__ import EXIT_BLOCKED, EXIT_OK, build_parser, main
from tieout.results import Results


def test_parses_every_flag() -> None:
    args = build_parser().parse_args(
        [
            "run", "a.csv", "t.csv", "--out", "o", "--mapping", "m.json",
            "--category-map", "c.csv", "--vendor-parents", "p.csv", "--fx", "fx.csv",
            "--category-settings", "s.csv", "--assumptions", "a.toml",
            "--review-decisions", "r.csv", "--period-end", "2025-12",
            "--as-of", "2026-01-15", "--aggregated", "--view", "masked", "--no-exports",
        ]
    )  # fmt: skip
    assert args.acq == Path("a.csv")
    assert args.view == "masked"
    assert args.aggregated and args.no_exports
    assert args.period_end == "2025-12"


def test_defaults() -> None:
    args = build_parser().parse_args(["run", "a", "t", "--out", "o"])
    assert args.view == "clean"
    assert not args.aggregated and not args.no_exports
    assert args.mapping is None


def test_out_is_required() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["run", "a", "t"])


def test_missing_input_exits_2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["run", str(tmp_path / "a.csv"), str(tmp_path / "t.csv"), "--out", "o"])
    assert code == EXIT_BLOCKED
    assert "not found" in capsys.readouterr().err


def test_run_writes_full_results_and_honours_every_option(
    small_files: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assumptions = tmp_path / "assumptions.toml"
    assumptions.write_text("[lever2.capture]\nlow = 0.4\nbase = 0.7\nhigh = 0.8\n")
    settings = tmp_path / "category_settings.csv"
    settings.write_text("l2_code,criticality,cap\nL03.01,critical,0.5\n")
    pair = "item_match|acquirer:NOPE|target:NOPE"
    decisions = tmp_path / "decisions.csv"
    decisions.write_text(
        "pair_id,type,decision,pack_qty,note,decided_at\n"
        f"{pair},item_match,reject,,,2026-01-15T00:00:00Z\n"
    )
    scorecard = tmp_path / "scorecard.json"
    scorecard.write_text(json.dumps({"passed": True}))
    code = main(
        [
            "run", str(small_files["acquirer"]), str(small_files["target"]),
            "--out", str(tmp_path), "--category-map", str(small_files["category_map"]),
            "--vendor-parents", str(small_files["vendor_parents"]), "--as-of", "2026-01-15",
            "--assumptions", str(assumptions), "--category-settings", str(settings),
            "--review-decisions", str(decisions), "--view", "masked",
            "--scorecard", str(scorecard),
        ]
    )  # fmt: skip
    assert code == EXIT_OK
    captured = capsys.readouterr()
    assert "after matching" in captured.out and "Defensible run-rate saving" in captured.out
    assert "exports are not built yet" in captured.err
    results = Results.load(tmp_path / "results")
    assert not results.vendor_map.empty and results.meta["report_date"] == "2026-01-15"
    assert results.meta["view"] == "masked"
    assert results.assumptions["lever2"]["capture"]["base"] == 0.7
    assert results.assumptions["category_settings"] == {
        "L03.01": {"criticality": "critical", "cap": 0.5}
    }
    risk = results.category_risk
    assert (risk.loc[risk["l2_code"] == "L03.01", "cap"] == 0.5).all()
    assert results.review_log["pair_id"].tolist() == [pair]
    assert results.scorecard == {"passed": True}
    assert results.totals["recurring"]["base"] > 0 and results.trace


def test_run_without_category_map_uses_suggestions(
    small_files: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = ["run", str(small_files["acquirer"]), str(small_files["target"]), "--out", str(tmp_path)]
    assert main([*args, "--no-exports"]) == EXIT_OK
    assert "exports" not in capsys.readouterr().err
    meta = Results.load(tmp_path / "results").meta
    assert meta["category_mapping"]["source"] == "suggested"


def test_blocking_validation_error_exits_2_with_report(
    small_files: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "acquirer.csv"
    raw = pd.read_csv(small_files["acquirer"], dtype=str, keep_default_na=False)
    raw.drop(columns=["vendor_id"]).to_csv(broken, index=False)
    code = main(["run", str(broken), str(small_files["target"]), "--out", str(tmp_path / "o")])
    assert code == EXIT_BLOCKED
    out = capsys.readouterr().out
    assert out.startswith("Blocking validation errors:") and "vendor_id" in out
    assert not (tmp_path / "o" / "results").exists()
