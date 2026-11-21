"""Score the tool and the naive baseline on one seed against its truth (PRD 4.7).

Matched pairs are tier A and B only, before any human decision, so no review
decisions are passed to the pipeline here. Dollar-weighted metrics come from
the synergy stage's outputs: each item's gross gap ``G1`` (before capture
probability) and the items bridge step 1 removes. The baseline's matches run
through the same lever 1 with every bridge filter on (PRD 4.7).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from evaluation.baseline import baseline_item_map, baseline_item_pairs, baseline_vendor_map
from evaluation.metrics import (
    PairScore,
    false_savings_rate,
    item_pair_list_score,
    item_pair_score,
    planted_savings_recall,
    unit_error_catch_rate,
    vendor_pair_score,
)
from evaluation.scorecard import Metrics, metric_row
from evaluation.seeds import SeedFiles
from evaluation.truth import load_item_truth_engine_keys, load_savings_truth, load_vendor_truth
from tieout.match import build_item_records, build_vendor_records
from tieout.pipeline import PipelineInputs, run_pipeline
from tieout.reference import Thresholds
from tieout.results import Results
from tieout.synergy import SynergyOutputs, compute_synergy, evaluate

DEMO_REPORT_DATE = "2026-01-15"
#: The baseline proposes no tier C candidates, so lever 1 gets an empty pair log.
_NO_PAIRS = pd.DataFrame(columns=["pair_id", "type", "key_a", "key_b", "score", "status"])


@dataclass(frozen=True)
class SeedTruth:
    """The vendor and (engine-keyed) item truth of one seed."""

    vendors: pd.DataFrame
    items: pd.DataFrame
    savings: pd.DataFrame

    @classmethod
    def load(cls, directory: str | Path) -> SeedTruth:
        return cls(
            load_vendor_truth(directory),
            load_item_truth_engine_keys(directory),
            load_savings_truth(directory),
        )


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


def dollar_metrics(
    outputs: SynergyOutputs, item_map: pd.DataFrame, truth: SeedTruth
) -> dict[str, float | None]:
    """Planted-savings recall, false-savings rate and unit-error catch rate (PRD 4.7)."""
    gaps, savings = outputs.item_gross_gaps, truth.savings
    return {
        "planted_savings_recall": planted_savings_recall(gaps, savings, truth.items, item_map),
        "false_savings_rate": false_savings_rate(gaps, item_map, truth.items),
        "unit_error_catch_rate": unit_error_catch_rate(
            outputs.removed_at_step1, truth.savings, item_map, truth.items
        ),
    }


def tool_metrics(results: Results, truth: SeedTruth) -> Metrics:
    """Pairwise and dollar-weighted metrics of a pipeline run."""
    outputs = evaluate(results.cached_synergy(), results.assumptions)
    return metric_row(
        vendor_score(results.vendor_map, truth),
        item_score(results.item_map, truth),
        **dollar_metrics(outputs, results.item_map, truth),
    )


def baseline_metrics(results: Results, truth: SeedTruth) -> Metrics:
    """The naive design of PRD 4.7 on the same prepared lines, through the same lever 1."""
    vendors = baseline_vendor_map(build_vendor_records(results.lines))
    records = build_item_records(results.lines)
    pairs = baseline_item_pairs(records)
    items = baseline_item_map(records, pairs)
    outputs = compute_synergy(
        results.lines, vendors, items, _NO_PAIRS, results.assumptions, None, results.meta
    )
    return metric_row(
        vendor_pair_score(vendors, truth.vendors),
        item_pair_list_score(pairs, records, truth.items),
        **dollar_metrics(outputs, items, truth),
    )
