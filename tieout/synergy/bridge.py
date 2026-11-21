"""The naive-to-defensible bridge (PRD 5.2, "Bridge computation").

``F_i`` is lever 1 with filters 1 to *i* on, in the base case; ``F_0`` is the
naive figure. Step *i* is ``F_(i-1) - F_i``, so a dollar is attributed to the
first step that removes it and the steps sum to ``F_0 - F_7``. A negative step
is shown as zero and its amount is added to the next step. Only step 1 can be
negative (the defensible line set can raise a group's price), and if the carry
is still negative after step 7 it stays in step 7, so the tie-out
``naive - sum(steps) = lever-1 base net saving`` always holds.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from tieout.synergy.lever1 import STEP_NAMES, Filters, Lever1Inputs, Lever1Result, lever1

__all__ = [
    "BRIDGE_DETAIL_COLUMNS",
    "N_STEPS",
    "Bridge",
    "bridge_detail",
    "carry_negative_steps",
    "compute_bridge",
]

N_STEPS = len(STEP_NAMES)
BRIDGE_DETAIL_COLUMNS = [
    "step",
    "step_name",
    "canonical_item_id",
    "item_tier",
    "group_id",
    "company",
    "site",
    "parent_id",
    "naive_gap",
    "amount_removed",
]


@dataclass(frozen=True)
class Bridge:
    """``F_0`` to ``F_7`` (base case), the raw and the shown steps.

    ``sources[i]`` lists the raw steps (1-based) whose dollars shown step
    ``i + 1`` carries: its own, plus earlier negative steps carried into it;
    empty when the step is shown as zero.
    """

    results: tuple[Lever1Result, ...]
    raw_steps: tuple[float, ...]
    steps: tuple[float, ...]
    sources: tuple[tuple[int, ...], ...]

    @property
    def naive(self) -> float:
        return self.results[0].total

    @property
    def defensible(self) -> float:
        return self.results[-1].total

    @property
    def tie_out_difference(self) -> float:
        """``naive - sum(steps) - lever-1 base net``; zero up to floating point."""
        return self.naive - float(sum(self.steps)) - self.defensible


def carry_negative_steps(
    raw: Sequence[float],
) -> tuple[tuple[float, ...], tuple[tuple[int, ...], ...]]:
    """Shown steps and their source steps: negatives become zero and carry forward."""
    steps: list[float] = []
    sources: list[tuple[int, ...]] = []
    carry, pending = 0.0, []
    last = len(raw) - 1
    for i, value in enumerate(raw):
        pending.append(i + 1)
        shown = value + carry
        if shown < 0 and i < last:
            steps.append(0.0)
            sources.append(())
            carry = shown
        else:
            steps.append(shown)
            sources.append(tuple(pending))
            carry, pending = 0.0, []
    return tuple(steps), tuple(sources)


def compute_bridge(inputs: Lever1Inputs, assumptions: Mapping[str, Any]) -> Bridge:
    """Evaluate ``F_0`` to ``F_7`` in the base case and derive the steps."""
    results = tuple(
        lever1(inputs, Filters.through(i), "base", assumptions) for i in range(N_STEPS + 1)
    )
    totals = [r.total for r in results]
    raw = tuple(totals[i - 1] - totals[i] for i in range(1, N_STEPS + 1))
    steps, sources = carry_negative_steps(raw)
    return Bridge(results=results, raw_steps=raw, steps=steps, sources=sources)


def bridge_detail(inputs: Lever1Inputs, bridge: Bridge) -> pd.DataFrame:
    """One row per item x group x step where the step changes the group's dollars.

    ``naive_gap`` is the group's naive contribution and ``amount_removed`` its
    ``F_(i-1) - F_i``; per step the rows sum to the raw step.
    """
    g = inputs.groups
    naive = bridge.results[0].contribution
    frames = []
    for step in range(1, N_STEPS + 1):
        removed = bridge.results[step - 1].contribution - bridge.results[step].contribution
        rows = np.flatnonzero(removed != 0)
        frames.append(
            pd.DataFrame(
                {
                    "step": step,
                    "step_name": STEP_NAMES[step - 1],
                    "canonical_item_id": g["canonical_item_id"].to_numpy()[rows],
                    "item_tier": g["item_tier"].to_numpy()[rows],
                    "group_id": g["group_id"].to_numpy()[rows],
                    "company": g["company"].to_numpy()[rows],
                    "site": g["site"].to_numpy()[rows],
                    "parent_id": g["parent_id"].to_numpy()[rows],
                    "naive_gap": naive[rows],
                    "amount_removed": removed[rows],
                }
            )
        )
    detail = pd.concat(frames, ignore_index=True)
    return detail[BRIDGE_DETAIL_COLUMNS]
