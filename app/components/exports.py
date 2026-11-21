"""In-memory exports for the Export screen (PRD 7, 9.3).

Files are built on request from the session's current results, in the current
view mode, and kept in session state against the results object they were
built from: a re-run changes nothing, and new results (a decision, an
assumption) discard the old bytes. Nothing is written to disk.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Callable
from dataclasses import dataclass

import streamlit as st

from tieout.export.charts import CHART_FUNCTIONS
from tieout.export.deck import build_deck
from tieout.export.workbook import build_workbook
from tieout.results import Results

__all__ = ["EXPORTS", "Export", "cached", "get", "size_text", "zip_of_charts"]

_KEY = "_to_exports"

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
ZIP = "application/zip"


@dataclass(frozen=True)
class Export:
    kind: str
    file_name: str
    mime: str
    build: Callable[[Results, str], bytes]


def zip_of_charts(results: Results, view: str) -> bytes:
    """Every static chart (PRD 7.3) as a PNG inside one zip, built in memory."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        for name, function in CHART_FUNCTIONS.items():
            archive.writestr(f"tieout_{name}.png", function(results, view))
    return buffer.getvalue()


EXPORTS: dict[str, Export] = {
    "workbook": Export("workbook", "tieout_workbook.xlsx", XLSX, build_workbook),
    "deck": Export("deck", "tieout_deck.pptx", PPTX, build_deck),
    "charts": Export("charts", "tieout_charts.zip", ZIP, zip_of_charts),
}


def _store(results: Results) -> dict:
    entry = st.session_state.get(_KEY)
    if entry is None or entry["results"] is not results:
        entry = {"results": results, "files": {}}
        st.session_state[_KEY] = entry
    return entry


def cached(kind: str, results: Results, view: str) -> bytes | None:
    """The file already built for these results and view, or ``None``."""
    return _store(results)["files"].get((kind, view))


def get(kind: str, results: Results, view: str) -> bytes:
    """The file for these results and view; built once, then served from session state."""
    entry = _store(results)
    key = (kind, view)
    if key not in entry["files"]:
        entry["files"][key] = EXPORTS[kind].build(results, view)
    return entry["files"][key]


def size_text(size: int) -> str:
    """A file size in plain units."""
    return f"{size / 1_000_000:.1f} MB" if size >= 1_000_000 else f"{max(size // 1000, 1)} KB"
