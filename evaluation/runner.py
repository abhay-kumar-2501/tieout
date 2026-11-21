"""Entry points behind the CLI subcommands (``python -m evaluation ...``)."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

from evaluation import tune as tuning
from evaluation.evaluate import SeedTruth, baseline_metrics, run_tool, tool_metrics
from evaluation.scorecard import Metrics, build_scorecard, write_scorecard
from evaluation.seeds import HELD_OUT_SEED, TUNING_SEEDS, ensure_seed
from tieout.reference import Thresholds, load_thresholds
from tieout.results import Results

SCORECARD_FILE = "scorecard.json"


class NotWiredError(RuntimeError):
    """Raised by commands that need parts of the engine that do not exist yet."""


def _thresholds(args: Namespace) -> Thresholds:
    return load_thresholds(args.thresholds)


def _run(seed: int, args: Namespace, thresholds: Thresholds) -> tuple[Results, SeedTruth]:
    files = ensure_seed(seed, args.seeds_dir, args.truth_dir)
    return run_tool(files, thresholds), SeedTruth.load(files.truth)


def _format_row(label: str, metrics: Metrics) -> str:
    return (
        f"  {label:<10} vendor P {metrics['vendor_precision']:.4f} R {metrics['vendor_recall']:.4f}"
        f" | item P {metrics['item_precision']:.4f} R {metrics['item_recall']:.4f}"
    )


def run_tune(args: Namespace) -> None:
    """Grid-search the automatic thresholds on the tuning seeds and write them (PRD 4.7)."""
    current = _thresholds(args)
    runs = {seed: _run(seed, args, current) for seed in TUNING_SEEDS}
    result = tuning.tune(runs, current)
    chosen = tuning.tuned_thresholds(result, current)
    tuning.write_thresholds(chosen, args.thresholds)
    print(tuning.format_grid("Vendor automatic threshold", result.vendor_grid, result.vendor))
    print(tuning.format_grid("Item automatic cosine", result.item_grid, result.item))
    print(
        f"Wrote {args.thresholds}: vendor auto {chosen.vendor_auto:g}, "
        f"item auto cosine {chosen.item_auto_cosine:.2f}"
    )


def run_score(args: Namespace) -> None:
    """Score the tool and the baseline on the tuning and held-out seeds; write the scorecard."""
    thresholds = _thresholds(args)
    tool: dict[int, Metrics] = {}
    baseline: dict[int, Metrics] = {}
    for seed in (*TUNING_SEEDS, HELD_OUT_SEED):
        results, truth = _run(seed, args, thresholds)
        tool[seed] = tool_metrics(results, truth)
        baseline[seed] = baseline_metrics(results, truth)
        print(f"seed {seed}")
        print(_format_row("tool", tool[seed]))
        print(_format_row("baseline", baseline[seed]))
    scorecard = build_scorecard(
        tuning_seeds=list(TUNING_SEEDS),
        held_out_seed=HELD_OUT_SEED,
        tool_tuning={s: tool[s] for s in TUNING_SEEDS},
        tool_held_out=tool[HELD_OUT_SEED],
        baseline_tuning={s: baseline[s] for s in TUNING_SEEDS},
        baseline_held_out=baseline[HELD_OUT_SEED],
    )
    scorecard["thresholds"] = {
        "vendor_auto": thresholds.vendor_auto,
        "vendor_review": thresholds.vendor_review,
        "item_auto_cosine": thresholds.item_auto_cosine,
        "item_review_cosine": thresholds.item_review_cosine,
    }
    path = Path(args.out) / SCORECARD_FILE
    write_scorecard(scorecard, path)
    print(f"Wrote {path}")
    for failure in scorecard["failures"]:
        print(f"  gate not met: {failure}")


def run_baseline(args: Namespace) -> None:
    """Score the naive baseline on every seed and print it."""
    thresholds = _thresholds(args)
    for seed in (*TUNING_SEEDS, HELD_OUT_SEED):
        results, truth = _run(seed, args, thresholds)
        print(f"seed {seed}")
        print(_format_row("baseline", baseline_metrics(results, truth)))


def run_sensitivity(args: Namespace) -> None:
    """Precompute the threshold sensitivity curves (needs the synergy engine)."""
    raise NotWiredError(
        "`evaluation sensitivity` charts the base-case synergy figure, which needs the "
        "synergy engine of the next milestone."
    )
