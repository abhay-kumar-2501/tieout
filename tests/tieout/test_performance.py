"""Engine performance bounds on the demo data (PRD 6.14, 4.5).

The PRD targets are 30 seconds for full matching, half a second for an
assumption change and two seconds for a review decision; the tests assert
twice those bounds (times ``TIEOUT_TIMING_SLACK``) to avoid flaky runs.
"""

from __future__ import annotations

import copy
import time
from collections.abc import Callable
from dataclasses import replace

import pytest

from tieout.match import record_decision
from tieout.pipeline import apply_decisions, recompute
from tieout.results import Results

pytestmark = pytest.mark.slow

PIPELINE_SECONDS = 60.0
RECOMPUTE_SECONDS = 1.0
DECISION_SECONDS = 4.0


def _best_of(runs: int, action: Callable[[], Results]) -> float:
    best = float("inf")
    for _ in range(runs):
        start = time.perf_counter()
        action()
        best = min(best, time.perf_counter() - start)
    return best


def test_full_pipeline_on_seed_4(seed4, timing_slack: float) -> None:
    assert seed4.seconds < PIPELINE_SECONDS * timing_slack


def test_recompute_on_demo_data(seed4, timing_slack: float) -> None:
    """Both with the in-memory cache and as after ``Results.load`` (no cache)."""
    changed = copy.deepcopy(seed4.results.assumptions)
    changed["lever2"]["capture"]["base"] = 0.7
    loaded = replace(seed4.results, synergy_cache=None)
    cold = _best_of(1, lambda: recompute(loaded, changed))
    warm = _best_of(3, lambda: recompute(seed4.results, changed))
    assert cold < RECOMPUTE_SECONDS * timing_slack, f"without cache: {cold:.3f} s"
    assert warm < RECOMPUTE_SECONDS * timing_slack, f"with cache: {warm:.3f} s"


def test_review_decision_on_demo_data(seed4, timing_slack: float) -> None:
    queue = seed4.results.review_queue
    pair = queue.loc[queue["type"] == "item_match", "pair_id"].iloc[0]
    log = record_decision(None, pair, "approve", decided_at="2026-01-15T00:00:00Z")
    seconds = _best_of(1, lambda: apply_decisions(seed4.results, log))
    assert seconds < DECISION_SECONDS * timing_slack, f"{seconds:.3f} s"
