"""Accuracy gates on the held-out seed (PRD 4.7, 10.2): the build fails below target.

One pipeline run on seed 4, shared by every test in this module. The truth is
the committed ``data/truth/seed_4``; the inputs are regenerated (byte-identical)
into a temporary directory.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from evaluation import targets
from evaluation.evaluate import SeedTruth, item_score, run_tool, vendor_score
from evaluation.metrics import PairScore
from evaluation.seeds import HELD_OUT_SEED, ensure_seed

pytestmark = pytest.mark.slow

COMMITTED_TRUTH = Path(__file__).resolve().parents[2] / "data" / "truth" / f"seed_{HELD_OUT_SEED}"
MATCHING_SECONDS_MAX = 60.0


@dataclass(frozen=True)
class HeldOut:
    vendors: PairScore
    items: PairScore
    seconds: float


@pytest.fixture(scope="module")
def held_out(tmp_path_factory: pytest.TempPathFactory) -> HeldOut:
    root = tmp_path_factory.mktemp("seed4")
    files = ensure_seed(HELD_OUT_SEED, root / "seeds", root / "truth")
    start = time.perf_counter()
    results = run_tool(files)
    seconds = time.perf_counter() - start
    truth = SeedTruth.load(COMMITTED_TRUTH)
    return HeldOut(
        vendor_score(results.vendor_map, truth), item_score(results.item_map, truth), seconds
    )


def test_vendor_precision(held_out: HeldOut) -> None:
    assert held_out.vendors.precision >= targets.VENDOR_PRECISION_MIN


def test_vendor_recall(held_out: HeldOut) -> None:
    assert held_out.vendors.recall >= targets.VENDOR_RECALL_MIN


def test_item_precision(held_out: HeldOut) -> None:
    assert held_out.items.precision >= targets.ITEM_PRECISION_MIN


def test_item_recall(held_out: HeldOut) -> None:
    assert held_out.items.recall >= targets.ITEM_RECALL_MIN


def test_full_matching_on_seed_4_is_fast(held_out: HeldOut) -> None:
    assert held_out.seconds < MATCHING_SECONDS_MAX
