"""Entry points behind the CLI subcommands; wired to the pipeline at integration."""

from __future__ import annotations

from argparse import Namespace


class NotWiredError(RuntimeError):
    """Raised by commands that need the pipeline and generator (not built yet)."""


def _not_wired(command: str) -> NotWiredError:
    return NotWiredError(
        f"`evaluation {command}` is wired in at integration: it needs tieout.pipeline "
        "and the synthetic generator, which are not part of this milestone's package."
    )


def run_tune(args: Namespace) -> None:
    """Grid-search the automatic thresholds on the tuning seeds (PRD 4.7)."""
    raise _not_wired("tune")


def run_score(args: Namespace) -> None:
    """Score the tool on all seeds and write scorecard.json."""
    raise _not_wired("score")


def run_baseline(args: Namespace) -> None:
    """Score the naive baseline on all seeds."""
    raise _not_wired("baseline")


def run_sensitivity(args: Namespace) -> None:
    """Precompute the threshold sensitivity curves."""
    raise _not_wired("sensitivity")
