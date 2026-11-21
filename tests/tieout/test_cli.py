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
    scorecard = Path(__file__).parents[2] / "data" / "demo" / "scorecard.json"
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
    assert (tmp_path / "tieout_workbook.xlsx").is_file()
    assert (tmp_path / "tieout_deck.pptx").is_file()
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
    assert results.scorecard == json.loads(scorecard.read_text())
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


def test_exports_follow_the_view(small_files: dict[str, Path], tmp_path: Path) -> None:
    import io

    import openpyxl
    from pptx import Presentation

    args = ["run", str(small_files["acquirer"]), str(small_files["target"])]
    sheets = {}
    for view in ("clean", "masked"):
        out = tmp_path / view
        assert main([*args, "--out", str(out), "--view", view]) == EXIT_OK
        book = openpyxl.load_workbook(out / "tieout_workbook.xlsx")
        sheets[view] = set(book.sheetnames)
        assert len(Presentation(out / "tieout_deck.pptx").slides) == 8
        assert io.BytesIO((out / "tieout_workbook.xlsx").read_bytes()).getbuffer().nbytes > 0
    assert "Payment_Terms" in sheets["clean"]
    assert "Payment_Terms" not in sheets["masked"]


def test_no_exports_writes_neither_file(small_files: dict[str, Path], tmp_path: Path) -> None:
    args = ["run", str(small_files["acquirer"]), str(small_files["target"]), "--out", str(tmp_path)]
    assert main([*args, "--no-exports"]) == EXIT_OK
    assert not list(tmp_path.glob("tieout_*"))
