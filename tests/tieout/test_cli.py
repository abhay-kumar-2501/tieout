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


def test_run_writes_results_and_skips_exports(
    small_files: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "run", str(small_files["acquirer"]), str(small_files["target"]),
            "--out", str(tmp_path), "--category-map", str(small_files["category_map"]),
            "--vendor-parents", str(small_files["vendor_parents"]), "--as-of", "2026-01-15",
        ]
    )  # fmt: skip
    assert code == EXIT_OK
    captured = capsys.readouterr()
    assert "after matching" in captured.out
    assert "exports are not built yet" in captured.err
    results = Results.load(tmp_path / "results")
    assert not results.vendor_map.empty and results.meta["report_date"] == "2026-01-15"


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
