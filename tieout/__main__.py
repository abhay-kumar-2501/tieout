"""Command-line entry point: ``python -m tieout run ACQ TGT --out DIR``."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

_FILE_OPTIONS = (
    "mapping",
    "category_map",
    "vendor_parents",
    "fx",
    "category_settings",
    "assumptions",
    "review_decisions",
)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the ``run`` command (PRD 9.2)."""
    parser = argparse.ArgumentParser(prog="tieout", description="Procurement synergy sizing.")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the pipeline on two purchasing files")
    run.add_argument("acq", type=Path, help="acquirer purchasing lines")
    run.add_argument("tgt", type=Path, help="target purchasing lines")
    run.add_argument("--out", type=Path, required=True, help="output directory")
    run.add_argument("--mapping", type=Path, help="column mapping (JSON)")
    run.add_argument("--category-map", type=Path, help="category mapping file")
    run.add_argument("--vendor-parents", type=Path, help="vendor parent table")
    run.add_argument("--fx", type=Path, help="FX rates file")
    run.add_argument("--category-settings", type=Path, help="per-category settings (CSV)")
    run.add_argument("--assumptions", type=Path, help="assumption overrides (TOML)")
    run.add_argument("--review-decisions", type=Path, help="review decisions (CSV)")
    run.add_argument("--period-end", metavar="YYYY-MM", help="last month of the data window")
    run.add_argument("--as-of", metavar="YYYY-MM-DD", help="report date")
    run.add_argument("--aggregated", action="store_true", help="inputs are pre-aggregated")
    run.add_argument("--view", choices=("clean", "masked"), default="clean")
    run.add_argument("--no-exports", action="store_true", help="skip workbook and deck")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse ``argv``, check the input files exist and return the exit code."""
    args = build_parser().parse_args(argv)
    inputs = [args.acq, args.tgt, *(getattr(args, name) for name in _FILE_OPTIONS)]
    missing = [str(path) for path in inputs if path is not None and not path.is_file()]
    if missing:
        print(f"input file not found: {', '.join(missing)}", file=sys.stderr)
        return 2
    print("pipeline not available yet", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
