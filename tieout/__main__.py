"""Command-line entry point: ``python -m tieout run ACQ TGT --out DIR`` (PRD 9.2).

Exit code 0 on success and 2 on a blocking validation error (the report is
printed) or an input that cannot be read.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from tieout.ingest import BlockingValidationError, FileLimitError, UnreadableFileError
from tieout.pipeline import PipelineInputs, run_pipeline
from tieout.results import Results

EXIT_OK = 0
EXIT_BLOCKED = 2

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


def _inputs(args: argparse.Namespace) -> PipelineInputs:
    mapping = json.loads(args.mapping.read_text(encoding="utf-8")) if args.mapping else None
    return PipelineInputs(
        acquirer=args.acq,
        target=args.tgt,
        mapping=mapping,
        category_map=args.category_map,
        vendor_parents=args.vendor_parents,
        fx=args.fx,
        category_settings=args.category_settings,
        assumptions=args.assumptions,
        decisions=args.review_decisions,
        period_end=args.period_end,
        as_of=args.as_of,
        aggregated=args.aggregated,
        view=args.view,
    )


def format_report(frame: pd.DataFrame) -> str:
    """The validation report as text: blocking errors first, each with its fix."""
    blocking = frame[frame["severity"] == "blocking"]
    others = frame[frame["severity"] != "blocking"]
    lines = ["Blocking validation errors:"]
    lines += [f"  [{r.company}] {r.message}\n      Fix: {r.fix}" for r in blocking.itertuples()]
    if not others.empty:
        lines.append(f"Other findings ({len(others)}):")
        lines += [f"  {r.severity} [{r.company}] {r.message}" for r in others.itertuples()]
    return "\n".join(lines)


def _summary(results: Results, out: Path) -> str:
    vendors = results.meta["matching"]["vendors"]
    items = results.meta["matching"]["items"]
    return "\n".join(
        [
            f"Vendor records: {vendors['records']:,} -> {vendors['after_normalisation']:,} "
            f"after normalisation -> {vendors['legal_entities']:,} after matching",
            f"Item records: {items['records']:,} -> {items['matchable_records']:,} in mapped "
            f"categories -> {items['canonical_items']:,} canonical items",
            f"Pending review: {len(results.review_queue):,} candidates",
            f"Results written to {out}",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Parse ``argv``, run the pipeline, write ``DIR/results/`` and return the exit code."""
    args = build_parser().parse_args(argv)
    inputs = [args.acq, args.tgt, *(getattr(args, name) for name in _FILE_OPTIONS)]
    missing = [str(path) for path in inputs if path is not None and not path.is_file()]
    if missing:
        print(f"input file not found: {', '.join(missing)}", file=sys.stderr)
        return EXIT_BLOCKED
    try:
        results = run_pipeline(_inputs(args))
    except BlockingValidationError as error:
        print(format_report(error.report.frame))
        return EXIT_BLOCKED
    except (FileLimitError, UnreadableFileError) as error:
        print(str(error), file=sys.stderr)
        return EXIT_BLOCKED
    out = args.out / "results"
    results.save(out)
    print(_summary(results, out))
    if not args.no_exports:
        print("Workbook and deck exports are not built yet; skipped.", file=sys.stderr)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
