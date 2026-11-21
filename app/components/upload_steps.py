"""Stepper logic of the upload flow (PRD 2.3), without Streamlit.

Which step comes next, what stops the flow, and what a change invalidates are
plain functions so they can be tested directly; ``upload_ui`` only draws them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from tieout.upload import UploadCheck, mapping_problems

__all__ = [
    "COMPANY_LABELS",
    "STEPS",
    "Facts",
    "advance",
    "blockers",
    "stale_after",
    "step_status",
]

STEPS = ("Upload", "Map columns", "Validate", "Map categories", "Run")
COMPANY_LABELS = {"acquirer": "Acquirer", "target": "Target"}

#: Session keys (suffixes) that hold work done at a step; changing a step clears the later ones.
_WORK = ("files", "mapping", "check", "categories", "run_error")
_CLEARED_BY_STEP = {
    0: _WORK[1:],  # a new file voids the mapping, the check and the categories
    1: _WORK[2:],
    2: _WORK[3:],
    3: (),
}


@dataclass(frozen=True)
class Facts:
    """What is known when deciding whether the flow may leave a step."""

    files: Mapping[str, object] = field(default_factory=dict)  # company -> loaded file info
    mapping: Mapping[str, Mapping[str, str | None]] = field(default_factory=dict)
    aggregated: bool = False
    check: UploadCheck | None = None
    mapped_categories: int = 0
    option_problems: tuple[str, ...] = ()


def blockers(step: int, facts: Facts) -> list[str]:
    """Plain-language reasons the flow cannot leave ``step``; empty when it may continue."""
    out: list[str] = []
    if step == 0:
        for company, label in COMPANY_LABELS.items():
            if company not in facts.files:
                out.append(f"Add the {label.lower()} file.")
        out += list(facts.option_problems)
    elif step == 1:
        for company, label in COMPANY_LABELS.items():
            out += [
                f"{label}: {p}"
                for p in mapping_problems(
                    facts.mapping.get(company, {}), aggregated=facts.aggregated
                )
            ]
    elif step == 2:
        if facts.check is None:
            out.append("Validation has not run yet.")
        elif facts.check.blocked:
            out.append("Fix the blocking errors and upload the corrected file.")
    elif step == 3 and facts.mapped_categories == 0:
        out.append("Map at least one category, or nothing can be matched.")
    return out


def advance(step: int, facts: Facts) -> int:
    """The step after ``step`` when nothing blocks it, else ``step`` itself."""
    if blockers(step, facts) or step >= len(STEPS) - 1:
        return step
    return step + 1


def stale_after(step: int) -> tuple[str, ...]:
    """Work (state keys) that a change made at ``step`` makes stale."""
    return _CLEARED_BY_STEP.get(step, ())


def step_status(current: int) -> list[tuple[str, str]]:
    """``(label, state)`` per step, state one of ``done``, ``current`` or ``todo``."""
    return [
        (label, "done" if i < current else "current" if i == current else "todo")
        for i, label in enumerate(STEPS)
    ]
