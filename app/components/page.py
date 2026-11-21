"""Common body of a placeholder page."""

from __future__ import annotations

from components.style import headline, muted


def render_placeholder(question: str, milestone: str) -> None:
    headline(question)
    muted(f"Coming in milestone {milestone}.")
