"""Score the tool and the naive baseline on one seed against its truth (PRD 4.7).

Matched pairs are tier A and B only, before any human decision, so no review
decisions are passed to the pipeline here. Dollar-weighted metrics need the
synergy engine and stay ``None`` until it exists.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from evaluation.baseline import baseline_item_pairs, baseline_vendor_map
from evaluation.metrics import PairScore, item_pair_list_score, item_pair_score, vendor_pair_score
from evaluation.scorecard import Metrics, metric_row
from evaluation.seeds import SeedFiles
from evaluation.truth import load_item_truth_engine_keys, load_vendor_truth
from tieout.match import build_item_records, build_vendor_records
from tieout.pipeline import PipelineInputs, run_pipeline
from tieout.reference import Thresholds
from tieout.results import Results

DEMO_REPORT_DATE = "2026-01-15"


@dataclass(frozen=True)
class SeedTruth:
    """The vendor and (engine-keyed) item truth of one seed."""

    vendors: pd.DataFrame
    items: pd.DataFrame

    @classmethod
    def load(cls, directory: str | Path) -> SeedTruth:
        return cls(load_vendor_truth(directory), load_item_truth_engine_keys(directory))


def seed_inputs(files: SeedFiles, thresholds: Thresholds | None = None) -> PipelineInputs:
    """Pipeline inputs for a generated seed, as the demo runs it."""
    return PipelineInputs(
        acquirer=files.acquirer,
        target=files.target,
        category_map=files.category_map,
        vendor_parents=files.vendor_parents,
        as_of=DEMO_REPORT_DATE,
        thresholds=thresholds,
        scenario="demo",
        seed=files.seed,
    )


def run_tool(files: SeedFiles, thresholds: Thresholds | None = None) -> Results:
    return run_pipeline(seed_inputs(files, thresholds))


def vendor_score(vendor_map: pd.DataFrame, truth: SeedTruth) -> PairScore:
    return vendor_pair_score(vendor_map, truth.vendors)


def item_score(item_map: pd.DataFrame, truth: SeedTruth) -> PairScore:
    return item_pair_score(item_map, truth.items)


def tool_metrics(results: Results, truth: SeedTruth) -> Metrics:
    """Pairwise metrics of a pipeline run; dollar metrics are not available yet."""
    return metric_row(vendor_score(results.vendor_map, truth), item_score(results.item_map, truth))


def baseline_metrics(results: Results, truth: SeedTruth) -> Metrics:
    """The naive design of PRD 4.7 on the same prepared lines."""
    vendors = baseline_vendor_map(build_vendor_records(results.lines))
    records = build_item_records(results.lines)
    pairs = baseline_item_pairs(records)
    return metric_row(
        vendor_pair_score(vendors, truth.vendors),
        item_pair_list_score(pairs, records, truth.items),
    )
