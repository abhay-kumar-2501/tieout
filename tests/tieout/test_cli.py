from pathlib import Path

import pytest

from tieout.__main__ import build_parser, main


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
    assert main(["run", str(tmp_path / "a.csv"), str(tmp_path / "t.csv"), "--out", "o"]) == 2
    assert "not found" in capsys.readouterr().err


def test_pipeline_not_available(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    acq, tgt = tmp_path / "a.csv", tmp_path / "t.csv"
    acq.write_text("x")
    tgt.write_text("x")
    assert main(["run", str(acq), str(tgt), "--out", str(tmp_path / "o")]) == 1
    assert "pipeline not available yet" in capsys.readouterr().err
