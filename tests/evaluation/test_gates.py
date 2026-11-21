"""Accuracy gates on the held-out seed (PRD 4.7, 10.2): the build fails below target.

One pipeline run on seed 4 (the session's ``seed4`` fixture), scored once
against the committed ``data/truth/seed_4``: the four pairwise targets, the two
dollar-weighted targets, and the matching time bound.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from evaluation import targets
from evaluation.evaluate import SeedTruth, tool_metrics
from evaluation.scorecard import Metrics
from evaluation.seeds import HELD_OUT_SEED

pytestmark = pytest.mark.slow

COMMITTED_TRUTH = Path(__file__).resolve().parents[2] / "data" / "truth" / f"seed_{HELD_OUT_SEED}"
MATCHING_SECONDS_MAX = 60.0


@pytest.fixture(scope="module")
def held_out(seed4) -> Metrics:
    return tool_metrics(seed4.results, SeedTruth.load(COMMITTED_TRUTH))


@pytest.mark.parametrize("metric", sorted(targets.TARGETS))
def test_gate(held_out: Metrics, metric: str) -> None:
    value = held_out[metric]
    assert targets.gate_passes(metric, value), f"{metric} = {value}"


def test_full_matching_on_seed_4_is_fast(seed4, timing_slack: float) -> None:
    assert seed4.seconds < MATCHING_SECONDS_MAX * timing_slack
