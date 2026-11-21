"""``python -m synthetic --seed N --out DIR [--truth-dir DIR] [--scale X] [--summary]``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from synthetic.generate import generate, write
from synthetic.summary import format_summary, summarise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m synthetic", description="Generate Tie-Out demo data."
    )
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--out", type=Path, required=True, help="directory for the input files")
    parser.add_argument(
        "--truth-dir", type=Path, default=None, help="truth directory (default OUT/truth)"
    )
    parser.add_argument(
        "--scale", type=float, default=1.0, help="multiply every count and spend figure"
    )
    parser.add_argument("--summary", action="store_true", help="print the calibration summary")
    args = parser.parse_args(argv)

    ds = generate(args.seed, scale=args.scale)
    paths = write(ds, args.out, args.truth_dir)
    print(f"wrote {paths['acquirer'].parent} and truth to {paths['truth_savings'].parent}")
    if args.summary:
        print(format_summary(summarise(ds)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
