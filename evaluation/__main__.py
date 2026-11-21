"""Command line: `python -m evaluation {tune,score,baseline,sensitivity}`."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from evaluation import runner
from evaluation.seeds import DEFAULT_SEEDS_DIR, DEFAULT_TRUTH_DIR

DEFAULT_THRESHOLDS = "tieout/reference/thresholds.toml"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evaluation", description="Tie-Out accuracy evaluation")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, handler, help_text in (
        ("tune", runner.run_tune, "grid-search automatic thresholds on the tuning seeds"),
        ("score", runner.run_score, "score the tool and the baseline; write scorecard.json"),
        ("baseline", runner.run_baseline, "score the naive baseline"),
        ("sensitivity", runner.run_sensitivity, "precompute sensitivity curves"),
    ):
        command = sub.add_parser(name, help=help_text)
        command.add_argument(
            "--truth-dir", default=str(DEFAULT_TRUTH_DIR), help="root of seed_{n} truth folders"
        )
        command.add_argument(
            "--seeds-dir", default=str(DEFAULT_SEEDS_DIR), help="root of seed_{n} input folders"
        )
        command.add_argument(
            "--thresholds", default=DEFAULT_THRESHOLDS, help="thresholds file to read (and tune)"
        )
        command.add_argument("--out", default="data/demo", help="output directory")
        command.set_defaults(handler=handler)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.handler(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
