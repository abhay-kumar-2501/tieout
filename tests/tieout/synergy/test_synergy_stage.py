"""Bridge carry rule, filter switches, determinism and the recompute time bound."""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pytest
from synergy_fixtures import Book, decision, realistic_table, run

from tieout.match.review import make_pair_id
from tieout.synergy.bridge import carry_negative_steps
from tieout.synergy.lever1 import Filters
from tieout.synergy.trace import figure_value, resum

FRAMES = (
    "price_groups",
    "bridge_detail",
    "opportunities",
    "internal_variance",
    "review_items",
    "item_gross_gaps",
)


def test_filters_through_switches_on_in_bridge_order() -> None:
    assert Filters.through(0) == Filters(*(False,) * 7)
    assert Filters.through(7) == Filters()
    assert Filters.through(3) == Filters(True, True, True, False, False, False, False)


def test_negative_step_is_shown_as_zero_and_carried_into_the_next() -> None:
    steps, sources = carry_negative_steps([-10.0, 4.0, 8.0, 0.0, 1.0, 0.0, 2.0])
    assert steps == (0.0, 0.0, 2.0, 0.0, 1.0, 0.0, 2.0)
    assert sources == ((), (), (1, 2, 3), (4,), (5,), (6,), (7,))
    assert sum(steps) == pytest.approx(5.0)


def test_carry_still_negative_after_the_last_step_stays_in_it() -> None:
    steps, _ = carry_negative_steps([-10.0, 1.0, 0.0, 0.0, 0.0, 0.0, 2.0])
    assert steps == (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -7.0)


def test_step1_can_raise_the_figure_and_the_bridge_still_ties_out() -> None:
    book = Book()
    # Naive blends cheap unconverted lines into the acquirer's price (1.25 a unit, gap 150);
    # step 1 drops them and the real gap (2.00 - 1.00) x 300 = 300 appears.
    book.buy("acquirer", "A1", 300, 2.00)
    book.buy("acquirer", "A1", 300, 0.50, status="unconverted")
    book.buy("target", "T1", 1_000, 1.00, vendor="V9")
    out = run(book.frames([("A1", "T1", "A")]))
    raw = out.totals["lever1"]["bridge_raw"]
    assert raw["step_1"] == pytest.approx(150 - 300)
    assert out.totals["lever1"]["bridge"]["step_1"] == 0
    assert out.totals["checks"]["bridge_tie_out_difference"] == pytest.approx(0, abs=1e-9)
    for path, (node, measure) in out.trace.figures.items():
        assert resum(out.trace, node, measure) == pytest.approx(
            figure_value(out.totals, path), abs=0.01
        )


def _decisions() -> pd.DataFrame:
    return pd.concat(
        [
            decision(make_pair_id("unit_flag", "acquirer:M3", "target:M3")),
            decision(make_pair_id("incoterm", "acquirer:M5", "target:M5")),
        ],
        ignore_index=True,
    )


def _shuffled(frames: dict[str, pd.DataFrame], seed: int) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    return {
        name: frame.iloc[rng.permutation(len(frame))].reset_index(drop=True)
        for name, frame in frames.items()
    }


def test_shuffling_input_rows_changes_no_output() -> None:
    frames = realistic_table(n_items=150, n_lines=6_000, seed=3)
    book = Book()
    book.buy("acquirer", "A1", 1_000, 2.00)
    book.buy("target", "T1", 1_000, 1.50, vendor="V9")
    book.buy("target", "T2", 1_000, 1.00, vendor="V9")
    extra = book.frames(pending=[("A1", "T1", 0.70), ("A1", "T2", 0.70)])
    extra["lines"]["line_id"] = "x" + extra["lines"]["line_id"]
    extra["item_map"]["canonical_item_id"] = "X" + extra["item_map"]["canonical_item_id"]
    frames = {name: pd.concat([frames[name], extra[name]], ignore_index=True) for name in frames}
    first = run(frames, decisions=_decisions())
    second = run(_shuffled(frames, 11), decisions=_decisions().iloc[::-1])
    for name in FRAMES:
        pd.testing.assert_frame_equal(getattr(first, name), getattr(second, name))
    assert first.totals == second.totals
    assert first.trace.children == second.trace.children
    pd.testing.assert_frame_equal(first.trace.line_amounts, second.trace.line_amounts)
    assert first.removed_at_step1 == second.removed_at_step1


def test_full_recompute_is_well_under_half_a_second() -> None:
    frames = realistic_table(n_items=1_500, n_lines=60_000, seed=1)
    run(frames)  # warm-up
    best = float("inf")
    for _ in range(3):
        start = time.perf_counter()
        out = run(frames)
        best = min(best, time.perf_counter() - start)
    assert out.opportunities["canonical_item_id"].nunique() > 1_000
    assert best < 1.0, f"recompute took {best:.3f} s"
