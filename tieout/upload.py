"""The custom-upload flow without a screen (PRD 2.3): peek, suggest, validate, run.

Everything works on in-memory bytes; nothing is written to disk or logged.
Screens call these functions so that the step logic is tested here, not in
``app/``.

1. :func:`peek_file` reads a file's headers and row count and enforces the limits.
2. :func:`suggest_columns` suggests a header-to-field mapping (``tieout.ingest.mapping``).
3. :func:`check_upload` validates the pair under the chosen mapping, returning the
   data-quality findings and, when nothing blocks, the category suggestions.
4. :func:`run_upload` runs the pipeline with the confirmed category map.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd

from tieout.ingest import BlockingValidationError, load_file, prepare
from tieout.ingest.load import (
    FileLimitError,
    UnreadableFileError,
    _read_bytes,
    _read_csv,
    _read_xlsx,
)
from tieout.ingest.mapping import ColumnSuggestion, missing_required, suggest_mapping
from tieout.ingest.schema import COLUMNS, COMPANIES, MAX_BYTES, MAX_ROWS
from tieout.normalise.taxonomy import suggest_categories
from tieout.pipeline import CATEGORY_MAP_COLUMNS, PipelineInputs, run_pipeline
from tieout.reference import load_fx_rates, load_taxonomy
from tieout.results import Results

__all__ = [
    "MAX_BYTES",
    "MAX_ROWS",
    "FilePeek",
    "UploadCheck",
    "category_map_from",
    "check_upload",
    "mapping_problems",
    "peek_file",
    "run_upload",
    "suggest_columns",
]

_XLSX_MAGIC = b"PK\x03\x04"


@dataclass(frozen=True)
class FilePeek:
    """A file's headers (in file order), data row count and size in bytes."""

    headers: list[str]
    rows: int
    size: int


def peek_file(data: bytes, name: str = "upload") -> FilePeek:
    """Headers and row count of an uploaded CSV or XLSX.

    Raises :class:`FileLimitError` above 250,000 rows or 50 MB and
    :class:`UnreadableFileError` for anything that is not a readable CSV/XLSX.
    """
    if len(data) > MAX_BYTES:
        raise FileLimitError(f"The file is larger than {MAX_BYTES // 2**20} MB, the limit.")
    buffer = io.BytesIO(data)
    buffer.name = name  # type: ignore[attr-defined]
    raw_bytes, _ = _read_bytes(buffer)
    if raw_bytes.startswith(_XLSX_MAGIC):
        raw = _read_xlsx(raw_bytes)
    elif raw_bytes.startswith(b"\xd0\xcf\x11\xe0"):
        raise UnreadableFileError("Legacy .xls files are not supported; save the file as .xlsx.")
    else:
        raw = _read_csv(raw_bytes)
    if len(raw) > MAX_ROWS:
        raise FileLimitError(f"The file has more than {MAX_ROWS:,} rows, which is the limit.")
    headers = [str(c).strip() for c in raw.columns]
    if not headers:
        raise UnreadableFileError("The file has no header row.")
    return FilePeek(headers, int(len(raw)), len(data))


def suggest_columns(headers: list[str]) -> list[ColumnSuggestion]:
    """One suggestion per header (exact synonym, then fuzzy name match)."""
    return suggest_mapping(headers)


def mapping_problems(mapping: Mapping[str, str | None], *, aggregated: bool = False) -> list[str]:
    """Messages that stop the flow: a required field no header maps to, or one field mapped twice.

    ``uom`` is judged later, on the data (it is required only when rows carry item codes).
    """
    chosen = [f for f in mapping.values() if f]
    problems = []
    for field in sorted({f for f in chosen if chosen.count(f) > 1}):
        problems.append(f"More than one column is mapped to {field}.")
    absent = [f for f in missing_required(chosen, aggregated=aggregated, has_items=False)]
    for field in absent:
        problems.append(f"No column is mapped to the required field {field}.")
    return problems


def _clean(mapping: Mapping[str, str | None]) -> dict[str, str]:
    return {h: f for h, f in mapping.items() if f and f in COLUMNS}


def _source(data: bytes, name: str) -> io.BytesIO:
    buffer = io.BytesIO(data)
    buffer.name = name  # type: ignore[attr-defined]
    return buffer


@dataclass(frozen=True)
class UploadCheck:
    """Outcome of validating a file pair.

    ``findings`` is the data-quality frame (blocking first). ``suggestions`` is the
    category suggestion frame (``company``, ``category_native``, ``spend``,
    ``l2_code``, ``l2_name``, ``score``), empty when validation blocked.
    """

    blocked: bool
    findings: pd.DataFrame
    suggestions: pd.DataFrame
    rows: dict[str, int]
    spend: float


def check_upload(
    acquirer: bytes,
    target: bytes,
    mapping: Mapping[str, Mapping[str, str | None]],
    *,
    period_end: str | None = None,
    aggregated: bool = False,
    fx: Mapping[str, float] | None = None,
) -> UploadCheck:
    """Validate the pair under the column ``mapping`` (``{"acquirer": {...}, "target": {...}}``)."""
    frames = {
        company: load_file(_source(data, company), company, _clean(mapping.get(company, {})))
        for company, data in zip(COMPANIES, (acquirer, target), strict=True)
    }
    rows = {c: len(f) for c, f in frames.items()}
    taxonomy = load_taxonomy()
    try:
        prepared = prepare(
            frames["acquirer"],
            frames["target"],
            fx=fx if fx is not None else load_fx_rates(),
            taxonomy=taxonomy,
            period_end=period_end,
            aggregated=aggregated,
        )
    except BlockingValidationError as exc:
        empty = pd.DataFrame(
            columns=["company", "category_native", "spend", "l2_code", "l2_name", "score"]
        )
        return UploadCheck(True, exc.report.frame, empty, rows, 0.0)
    suggestions = suggest_categories(prepared.lines, taxonomy)
    spend = float(prepared.lines["amount"].sum())
    return UploadCheck(False, prepared.data_quality, suggestions, rows, spend)


def category_map_from(choices: pd.DataFrame) -> pd.DataFrame:
    """The PRD 3.2 ``category_map`` from edited suggestions; a blank ``l2_code`` is unmapped."""
    mapped = choices.dropna(subset=["l2_code"])
    mapped = mapped[mapped["l2_code"].astype(str).str.strip() != ""]
    return mapped[list(CATEGORY_MAP_COLUMNS)].reset_index(drop=True)


def run_upload(
    acquirer: bytes,
    target: bytes,
    mapping: Mapping[str, Mapping[str, str | None]],
    category_map: pd.DataFrame,
    *,
    period_end: str | None = None,
    aggregated: bool = False,
    progress: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> Results:
    """Run the full pipeline on the confirmed mappings; raises ``BlockingValidationError``."""
    inputs = PipelineInputs(
        acquirer=_source(acquirer, "acquirer"),  # type: ignore[arg-type]
        target=_source(target, "target"),  # type: ignore[arg-type]
        mapping={c: _clean(mapping.get(c, {})) for c in COMPANIES},
        category_map=category_map_from(category_map),
        period_end=period_end,
        aggregated=aggregated,
        scenario="custom",
    )
    return run_pipeline(inputs, progress=progress)
