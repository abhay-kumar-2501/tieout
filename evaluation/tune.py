"""Grid search of the automatic thresholds on the tuning seeds (PRD 4.7).

The vendor automatic threshold runs from 85 to 97 in steps of 1 and the item
automatic cosine from 0.70 to 0.90 in steps of 0.02. For each, the lowest value
whose mean precision on the tuning seeds is at least the target plus 0.005 is
chosen. The review thresholds stay fixed. Pair scores are computed once per
seed; every grid point re-runs only clustering and one-to-one assembly from the
cached pairs (PRD 4.5).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from evaluation import targets
from evaluation.evaluate import SeedTruth, item_score, vendor_score
from evaluation.metrics import PairScore
from tieout.match import build_item_records, build_vendor_records, match_items, match_vendors
from tieout.reference import Thresholds
from tieout.results import Results

VENDOR_GRID: tuple[float, ...] = tuple(float(v) for v in range(85, 98))
ITEM_GRID: tuple[float, ...] = tuple(round(0.70 + 0.02 * i, 2) for i in range(11))
MARGIN = 0.005

Grid = dict[float, dict[int, PairScore]]


@dataclass(frozen=True)
class Choice:
    """The chosen value of one threshold and whether it met the precision bar."""

    value: float
    met: bool
    bar: float


@dataclass(frozen=True)
class Tuning:
    vendor: Choice
    item: Choice
    vendor_grid: Grid
    item_grid: Grid


def _mean(scores: Mapping[int, PairScore], field: str) -> float:
    return sum(getattr(s, field) for s in scores.values()) / len(scores)


def vendor_grid(
    runs: Mapping[int, tuple[Results, SeedTruth]], review: float, grid: tuple[float, ...]
) -> Grid:
    """Vendor pair scores per threshold and seed, from each run's cached pairs."""
    out: Grid = {value: {} for value in grid}
    for seed, (results, truth) in sorted(runs.items()):
        records = build_vendor_records(results.lines)
        for value in grid:
            match = match_vendors(
                records,
                results.vendor_parents,
                auto_threshold=value,
                review_threshold=review,
                cached_pairs=results.vendor_pairs,
            )
            out[value][seed] = vendor_score(match.vendor_map, truth)
    return out


def item_grid(
    runs: Mapping[int, tuple[Results, SeedTruth]], review: float, grid: tuple[float, ...]
) -> Grid:
    """Item pair scores per cosine and seed, from each run's cached pairs."""
    out: Grid = {value: {} for value in grid}
    for seed, (results, truth) in sorted(runs.items()):
        records = build_item_records(results.lines)
        for value in grid:
            match = match_items(
                records,
                auto_cosine=value,
                review_cosine=review,
                cached_pairs=results.item_pairs,
            )
            out[value][seed] = item_score(match.item_map, truth)
    return out


def choose(grid: Grid, target: float) -> Choice:
    """Lowest value whose mean precision reaches ``target + MARGIN``.

    When none does, the highest (most conservative) value is kept and the
    choice is marked as not meeting the bar.
    """
    bar = round(target + MARGIN, 4)
    for value in sorted(grid):
        if _mean(grid[value], "precision") >= bar:
            return Choice(value, True, bar)
    return Choice(max(grid), False, bar)


def tune(runs: Mapping[int, tuple[Results, SeedTruth]], thresholds: Thresholds) -> Tuning:
    """Run both grid searches on ``runs`` (seed -> pipeline results and truth)."""
    vendors = vendor_grid(runs, thresholds.vendor_review, VENDOR_GRID)
    items = item_grid(runs, thresholds.item_review_cosine, ITEM_GRID)
    return Tuning(
        vendor=choose(vendors, targets.VENDOR_PRECISION_MIN),
        item=choose(items, targets.ITEM_PRECISION_MIN),
        vendor_grid=vendors,
        item_grid=items,
    )


def tuned_thresholds(tuning: Tuning, current: Thresholds) -> Thresholds:
    return Thresholds(
        vendor_auto=tuning.vendor.value,
        vendor_review=current.vendor_review,
        item_auto_cosine=tuning.item.value,
        item_review_cosine=current.item_review_cosine,
    )


def write_thresholds(thresholds: Thresholds, path: str | Path) -> None:
    """Write ``thresholds.toml`` in the shipped layout."""
    text = (
        "# Matching thresholds. The auto values are overwritten by evaluation/tune.py\n"
        "# (PRD 4.7); the review values are fixed.\n"
        "[vendor]\n"
        f"auto = {thresholds.vendor_auto:g}\n"
        f"review = {thresholds.vendor_review:g}\n"
        "\n"
        "[item]\n"
        f"auto_cosine = {thresholds.item_auto_cosine:.2f}\n"
        f"review_cosine = {thresholds.item_review_cosine:.2f}\n"
    )
    Path(path).write_text(text, encoding="utf-8")


def format_grid(name: str, grid: Grid, chosen: Choice) -> str:
    """One line per grid value: mean precision and recall, and the choice."""
    lines = [f"{name}: lowest value with mean precision >= {chosen.bar}"]
    for value in sorted(grid):
        mark = "  <- chosen" if value == chosen.value else ""
        lines.append(
            f"  {value:g}: precision {_mean(grid[value], 'precision'):.4f}, "
            f"recall {_mean(grid[value], 'recall'):.4f}{mark}"
        )
    if not chosen.met:
        lines.append("  no value reached the bar; the most conservative value is kept")
    return "\n".join(lines)
